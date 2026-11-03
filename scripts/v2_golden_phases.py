"""Zlatá data funkcí fází kroku (``cee.v2.phases``): záznam vstupů a výstupů ze skutečných běhů.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně a čtyři další světy, které
spustí vzácné cesty: přízvuk, nové koncovky, ponechání starých tvarů, exaptaci)
zaznamená každé volání čisté funkce nad poli, jak ho udělal Python
(``CEE_NATIVE=0``), s vstupem i výstupem. Rust implementace funkcí se pak ověří bit po bitu stejným souborem
(``tests/v2/test_v2_golden_phases.py``).

Zaznamenává se tohle (podle modulu, tři soubory):

- ``golden_innovation.json.gz``: klíče skupin, očekávané počty, losy počtu
  (``hash_poisson``), míry a váhy míst, výběr místa;
- ``golden_vocabulary.json.gz``: milníky a ustálení inovací, přechody přes
  práh, aktivace procesů a stopy trajektorií v bloku před a po přenosu;
- ``golden_grammar.json.gz``: rozhodnutí o analogiích, nových koncovkách,
  pravidle přízvuku a tvarové funkce ``level``, ``extend``, ``rebracket``.

Záznam je výřez a vzniká pokaždé stejný (bez náhody, bajt po bajtu): volání
se zbaví opakování; u funkcí nad bloky živých proměnných (výstup je po
řádcích nezávislý) se do záznamu vezmou jen řádky, kde se něco děje, a
několik dalších; z volání se ponechá pevně vybraný počet podle otisku.
Vstupy i výstupy jsou pole (``dtype``, tvar, data) a čísla; ``float64`` se
ukládá jako nejkratší text, který se čte zpět na stejný bit.

Použití:  python scripts/v2_golden_phases.py [--output-dir tests/v2/data]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from collections import defaultdict
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

import cee.v2.morphology as morphology_module  # noqa: E402
import cee.v2.simulation as simulation_module  # noqa: E402
from cee.v2 import phases  # noqa: E402
from cee.v2.language.constructions import Construction  # noqa: E402
from cee.v2.language.lexicon import UnitForm  # noqa: E402
from cee.v2.scenarios import SYNTAX_GRAMMAR, village_grid  # noqa: E402
from cee.v2.simulation import Simulation, SimulationConfig  # noqa: E402

digest_worlds = import_module("v2_digests").worlds

NO_CASE = {
    **{name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "OBJ"},
    "DEFINITE": Construction("DEFINITE", "zero"),
}
TENSELESS = {name: construction for name, construction in SYNTAX_GRAMMAR.items() if name != "PAST"}
EXAPTATION = {
    **SYNTAX_GRAMMAR,
    "DEFINITE": Construction("DEFINITE", "zero"),
    "ORDER": Construction("ORDER", "fixed", order="SVO"),
}

#: Scénáře a počet let. Vzácné cesty (nová koncovka, exaptace, pravidlo přízvuku)
#: se v krátkých scénářích nestanou, proto čtyři další světy.
SCENARIOS: dict[str, tuple[Callable[[], Any], int]] = {}
for _name, _build, _years in digest_worlds(False):
    if _name in ("grid-5x5", "shift", "valley-50"):
        SCENARIOS[_name] = (_build, {"grid-5x5": 1000, "shift": 900, "valley-50": 400}[_name])
SCENARIOS["grammar"] = (lambda: (village_grid(6, seed=8, grammar=NO_CASE, semantics=True), ()), 3000)
SCENARIOS["past"] = (
    lambda: (village_grid(6, seed=6, grammar={**TENSELESS, "PAST": Construction("PAST", "zero")}, semantics=True), ()),
    2500,
)
SCENARIOS["exaptation"] = (lambda: (village_grid(6, seed=4, grammar=EXAPTATION, semantics=True), ()), 1500)
SCENARIOS["stress"] = (
    lambda: (village_grid(3, 2, seed=5, syntax=True, semantics=True, morphology=True), ()), 3000,
)

#: Kolik řádků bloku (nebo skupin) smí mít jeden záznam: ty, kde se něco děje, a pár dalších.
ROW_LIMIT = 6
PLAIN_ROWS = 2
GROUP_LIMIT = 8


def encode(value: Any) -> Any:
    """Hodnota v JSON: pole jako ``{"nd": dtype, "shape": [...], "data": [...]}``, n-tice jako ``{"t": [...]}``."""
    if isinstance(value, np.ndarray):
        return {"nd": str(value.dtype), "shape": list(value.shape), "data": value.ravel().tolist()}
    if isinstance(value, UnitForm):
        return {"unit": [list(value.form), value.boundary, value.exponent]}
    if isinstance(value, tuple):
        return {"t": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Nelze zakódovat {type(value)}.")


def dump(value: Any) -> str:
    return json.dumps(encode(value), separators=(",", ":"), sort_keys=True)


def evenly(count: int, limit: int) -> np.ndarray:
    """Až ``limit`` pevně rozložených indexů z ``count``."""
    if count <= limit:
        return np.arange(count)
    return np.unique(np.linspace(0, count - 1, limit).astype(np.intp))


def pick_rows(count: int, interesting: np.ndarray) -> np.ndarray:
    """Řádky záznamu: až ``ROW_LIMIT`` zajímavých (rovnoměrně) a ``PLAIN_ROWS`` dalších."""
    found = np.unique(interesting)
    chosen = found[evenly(len(found), ROW_LIMIT)] if len(found) else found
    rest = np.setdiff1d(np.arange(count), found)
    plain = rest[evenly(len(rest), PLAIN_ROWS)] if len(rest) else rest
    return np.union1d(chosen, plain).astype(np.intp)


class Recorder:
    """Sbírá volání jedné funkce: dvě hromádky (zajímavá a ostatní), každá s pevným stropem podle otisku."""

    def __init__(self, name: str, original: Callable[..., Any], limit: int,
                 narrow: Callable[..., tuple[tuple[Any, ...], dict[str, Any]]] | None = None,
                 is_interesting: Callable[[Any], bool] | None = None) -> None:
        self.name, self.original, self.limit = name, original, limit
        self.narrow, self.is_interesting = narrow, is_interesting
        self.buckets: dict[bool, dict[str, str]] = {True: {}, False: {}}
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        actual = result = self.original(*args, **kwargs)
        self.calls += 1
        if self.narrow is not None:
            args, kwargs = self.narrow(self.original, args, kwargs, result)
            result = self.original(*args, **kwargs)
        flag = bool(self.is_interesting(result)) if self.is_interesting is not None else True
        call = {"args": list(args), "kwargs": kwargs, "result": result}
        text = dump(call)
        key = hashlib.blake2b(dump([args, kwargs]).encode(), digest_size=8).hexdigest()
        bucket = self.buckets[flag]
        bucket[key] = text
        if len(bucket) > 2 * self.limit:
            for stale in sorted(bucket)[self.limit:]:
                del bucket[stale]
        return actual

    def records(self) -> list[Any]:
        """Ponechá až 3/4 stropu zajímavých volání a zbytek ostatních, seřazeno podle otisku."""
        interesting = sorted(self.buckets[True])[: self.limit * 3 // 4]
        plain = sorted(self.buckets[False])[: self.limit - len(interesting)]
        return [json.loads(self.buckets[flag][key]) for flag, keys in ((True, interesting), (False, plain)) for key in keys]


def rows_of(result: Any) -> np.ndarray:
    """Čísla řádků, ve kterých výsledek (n-tice polí či vnořené n-tice) cokoli obsahuje."""
    first = result
    while isinstance(first, tuple):
        if first and isinstance(first[0], tuple):
            return np.unique(np.concatenate([rows_of(part) for part in first]))
        first = first[0] if first else np.zeros(0, dtype=np.intp)
    return np.asarray(first, dtype=np.intp)


def narrow_block(row_args: tuple[int, ...]) -> Callable[..., tuple[tuple[Any, ...], dict[str, Any]]]:
    """Zúží argumenty bloku (řádky na prvním rozměru) na zajímavé řádky; ostatní argumenty nechá."""
    def narrow(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
        rows = pick_rows(len(args[row_args[0]]), rows_of(result))
        return tuple(arg[rows] if index in row_args else arg for index, arg in enumerate(args)), kwargs
    return narrow


def narrow_mask(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    """``innovation_mask``: zúží řádky a sloupec ``change`` zmenší na odkazované položky (čísla se přečíslují)."""
    slot_numbers, column = args
    rows = pick_rows(len(slot_numbers), np.flatnonzero(result.any(axis=1)))
    narrowed = slot_numbers[rows]
    if not len(column):
        return (narrowed, column), kwargs
    used = np.unique(narrowed[narrowed >= 0])
    renumbered = np.where(narrowed >= 0, np.searchsorted(used, np.maximum(narrowed, 0)), -1)
    # Odkaz na −1 indexuje poslední položku sloupce; přečíslovaný sloupec ji proto drží na konci.
    return (renumbered.astype(slot_numbers.dtype), np.concatenate([column[used], column[-1:]])), kwargs


def narrow_groups(group_args: tuple[int, ...]) -> Callable[..., tuple[tuple[Any, ...], dict[str, Any]]]:
    """Zúží argumenty na pevně rozložených pár skupin (první rozměr); výpočet je po skupinách nezávislý."""
    def narrow(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
        groups = evenly(len(args[group_args[0]]), GROUP_LIMIT)
        return tuple(arg[groups] if index in group_args else arg for index, arg in enumerate(args)), kwargs
    return narrow


def narrow_poisson(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    """``hash_poisson`` s maticí skupiny × změny: řádky s nenulovým losem a pár dalších; každý prvek je nezávislý."""
    if kwargs.get("pairwise"):
        return args, kwargs
    rows = pick_rows(len(args[0]), np.flatnonzero((result > 0).any(axis=1)))
    return (args[0][rows], args[1], args[2][rows]), kwargs


def has_event(result: Any) -> bool:
    """Obsahuje výsledek (n-tice polí) aspoň jednu položku?"""
    if isinstance(result, tuple):
        return any(has_event(part) for part in result)
    return bool(np.size(result))


def build_recorders() -> dict[str, list[tuple[Any, str, Recorder]]]:
    """Zaměnit funkce za zapisovače; vrací je rozdělené podle souboru: (modul, atribut, zapisovač)."""
    def make(module: Any, name: str, limit: int, **options: Any) -> tuple[Any, str, Recorder]:
        return module, name, Recorder(f"{module.__name__}.{name}", getattr(module, name), limit, **options)

    return {
        "innovation": [
            make(phases, "innovation_group_keys", 40),
            make(phases, "expected_counts", 60, narrow=narrow_groups((0, 1, 2)), is_interesting=any_positive),
            make(simulation_module, "hash_poisson", 80, narrow=narrow_poisson, is_interesting=any_positive),
            make(phases, "uniform_rate", 120),
            make(phases, "rate_total", 80),
            make(phases, "normalize_rates", 60),
            make(phases, "site_weights", 60, is_interesting=has_weights),
            make(phases, "category_loss_rates", 150, is_interesting=any_positive),
            make(phases, "draw_site", 200),
        ],
        "vocabulary": [
            make(phases, "innovation_mask", 40, narrow=narrow_mask, is_interesting=any_nonzero),
            make(phases, "change_events", 40, narrow=narrow_block((0, 1, 2)), is_interesting=has_event),
            make(phases, "threshold_crossings", 40, narrow=narrow_block((0, 1, 2)), is_interesting=has_event),
            make(phases, "activation_cells", 40, narrow=narrow_block((0, 1)), is_interesting=has_event),
            make(phases, "trace_cells", 20, narrow=narrow_block((0, 1)), is_interesting=has_event),
        ],
        "grammar": [
            make(phases, "analogy_decisions", 120, is_interesting=any_nonzero),
            make(phases, "grammar_ready", 120, is_interesting=any_nonzero),
            make(phases, "ending_actions", 60, is_interesting=any_nonzero),
            make(phases, "stress_updates", 120, is_interesting=any_nonzero),
            make(morphology_module, "level", 120),
            make(morphology_module, "extend", 120),
            make(morphology_module, "rebracket", 120),
        ],
    }


def any_positive(result: Any) -> bool:
    return bool(np.any(np.asarray(result) > 0))


def any_nonzero(result: Any) -> bool:
    return bool(np.any(np.asarray(result) != 0))


def has_weights(result: Any) -> bool:
    return result[1] is not None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/v2/data")
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), help="jen tyto scénáře (zkouška)")
    args = parser.parse_args()
    recorders = build_recorders()
    originals = [(module, name, getattr(module, name)) for group in recorders.values() for module, name, _ in group]
    for group in recorders.values():
        for module, name, recorder in group:
            setattr(module, name, recorder)
    try:
        for name in args.scenarios:
            build, years = SCENARIOS[name]
            world, events = build()
            # Stopy trajektorií jsou vstupem ``trace_cells``; deník událostí se tím nemění.
            simulation = Simulation(world, SimulationConfig(record_trajectories=True), events=events)
            simulation.run(years)
            kinds = defaultdict(int)
            for event in simulation.history.events:
                kinds[str(event["kind"])] += 1
            print(f"{name}: {years} let, událostí {len(simulation.history.events)} "
                  f"(analogy {kinds['analogy']}, grammaticalized {kinds['grammaticalized']}, "
                  f"exapted {kinds['exapted']}, stress_rule_changed {kinds['stress_rule_changed']})", flush=True)
    finally:
        for module, name, original in originals:
            setattr(module, name, original)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for module_name, group in recorders.items():
        data = {"functions": {recorder.name: {"calls": recorder.calls, "records": recorder.records()}
                              for _, _, recorder in group}}
        path = output / f"golden_{module_name}.json.gz"
        # Bez jména a času v hlavičce, ať je soubor při každém běhu bajt po bajtu stejný.
        with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
        print(f"{path}: {path.stat().st_size / 1024:.0f} kB")
        for name, entry in data["functions"].items():
            print(f"    {name}: {len(entry['records'])} záznamů z {entry['calls']} volání")


if __name__ == "__main__":
    main()

"""Zlatá data funkcí přenosu (``cee.v2.phases_transmission``): záznam vstupů a výstupů ze skutečných běhů.

Za běhu scénářů (grid-5x5, shift, valley-50 zkráceně, svět s elitou a obchodem
a svět s církví, školou a liturgií, aby se pokryly všechny kanály) zaznamená
každé volání čisté funkce nad poli, jak ho udělal Python (``CEE_NATIVE=0``),
s vstupem i výstupem. Rust implementace (``hear``, ``settle``, ``normalized``) se ověřuje bit po bitu
stejným souborem (``tests/v2/test_v2_golden_transmission.py`` a ``test_v2_native_transmission.py``).

Soubor ``tests/v2/data/golden_transmission.json.gz`` obsahuje:

- přípravu kroku: ``mixing_from_links``, ``components``, ``foreign_mask``,
  ``elite_shares``, ``trade_shares``, ``neighbor_fraction``, ``internal_blocks``,
  ``cross_blocks``, ``cohort_scales``, ``channel_weights``;
- faktory proměnných: ``borrowing_factors``, ``interference_factors``,
  ``reading_factors``, ``school_factors``, ``liturgy_factors``;
- přenos bloku: ``mix``, ``hear``, ``settle``, ``normalized``.

Záznam je výřez a vzniká pokaždé stejný (bez náhody, bajt po bajtu), stejně
jako u ``scripts/v2_golden_phases.py``: opakovaná volání se zahodí a u funkcí
nad bloky živých proměnných (řádky jsou na sobě nezávislé, ``settle`` je navíc
nezávislý po skupinách) se vezmou jen řádky a skupiny, kde se něco děje, a pár
dalších.

Použití:  python scripts/v2_golden_transmission.py [--output-dir tests/v2/data]
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

os.environ["CEE_NATIVE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from cee.v2 import phases_transmission as phases  # noqa: E402
from cee.v2.background import EliteAssimilation, ForeignElite, TradeShift, generate  # noqa: E402
from cee.v2.events import Codification, ReligiousChange, Schooling  # noqa: E402
from cee.v2.parameters import NEUTRAL_CHANNEL_DOMAINS, Parameters  # noqa: E402
from cee.v2.scenarios import (  # noqa: E402
    Language,
    Place,
    ProtoLanguage,
    Region,
    contact_world,
    language_shift,
    region_world,
)
from cee.v2.simulation import Simulation  # noqa: E402

golden = import_module("v2_golden_phases")
digest_worlds = import_module("v2_digests").worlds
Recorder, evenly, pick_rows = golden.Recorder, golden.evenly, golden.pick_rows


def trade_elite_world() -> tuple[Any, list[Any]]:
    """Šest regionů ve dvou jazycích s cizí elitou a obchodní cestou (kanály ``elite`` a ``trade``)."""
    params = Parameters()
    regions = tuple(
        Region(f"r{i}", (60.0 * (i % 3), 60.0 * (i // 3)), language="b" if i >= 3 else "a", villages=2,
               neighbours=tuple(f"r{j}" for j in range(6)
                                if j != i and abs(j % 3 - i % 3) + abs(j // 3 - i // 3) == 1))
        for i in range(6)
    )
    world = region_world(regions, seed=3, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True,
                         params=params)
    events = list(generate([(r.id, r.neighbours, r.language) for r in regions], start=0.0, end=600.0,
                           level_name="turbulent", seed=3, params=params))
    events += [ForeignElite(50.0, "r3", "r0"), TradeShift(60.0, ("r1", "r4"), 2.0),
               TradeShift(300.0, ("r1", "r4"), 0.5), EliteAssimilation(300.0, "r3", "r0")]
    return world, events


def church_school_world() -> tuple[Any, list[Any]]:
    """Vesnice a město s písmem, církví a školou (kanály čtení, škola a liturgie)."""
    world = contact_world([
        Language("v", tuple(Place(f"v{i}", (i * 10.0, 0.0), population=600) for i in range(4))),
        Language("r", (Place("r0", (500.0, 0.0), population=5000, prestige=1.0),),
                 consonants=("t", "k", "s", "n", "m", "l", "r", "f", "x", "kʷ", "j", "d")),
    ], seed=2, params=Parameters())
    villages = tuple(f"v{i}" for i in range(4))
    events = [Codification(100.0, "r0", ("r0",), 0.1), ReligiousChange(150.0, "written:r0", villages, 0.3),
              Codification(200.0, "v1", villages, 0.2), Schooling(400.0, villages, 0.5, 0.5)]
    return world, events


def neutral_shift_world() -> tuple[Any, list[Any]]:
    """Přechod jazyka s neutrálními vahami domén: kanály elita a obchod splynou s obecným kontaktem."""
    world, events = language_shift(2, start=300.0)
    world.params = Parameters(channel_domains=NEUTRAL_CHANNEL_DOMAINS, borrowability_strength=0.0)
    return world, events


SCENARIOS: dict[str, tuple[Callable[[], Any], int]] = {}
for _name, _build, _years in digest_worlds(False):
    if _name in ("grid-5x5", "shift", "valley-50"):
        SCENARIOS[_name] = (_build, {"grid-5x5": 1000, "shift": 900, "valley-50": 400}[_name])
SCENARIOS["trade-elite"] = (trade_elite_world, 600)
SCENARIOS["church-school"] = (church_school_world, 800)
SCENARIOS["shift-neutral"] = (neutral_shift_world, 900)

#: Kolik řádků a skupin smí mít jeden záznam bloku (ty, kde se něco děje, a pár dalších).
ROWS = 5
GROUPS = 8
FACTOR_ROWS = 24


def _changed_rows(result: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Řádky bloku (osa 0), ve kterých se výsledek liší od reference."""
    return np.flatnonzero((result != reference).reshape(len(result), -1).any(axis=1))


def narrow_hear(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    current, present, members, blocks, alone, alone_weight, flows, channels = args
    rows = pick_rows(len(current), _changed_rows(result, current))
    narrowed_flows = [(factor[rows], cross) for factor, cross in flows]
    narrowed_channels = [(factor[rows], learners, sources, weights) for factor, learners, sources, weights in channels]
    return (current[rows], present[rows], members, blocks, alone, alone_weight, narrowed_flows,
            narrowed_channels), kwargs


def narrow_mix(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    values = args[0]
    active = np.flatnonzero((result != 0).reshape(len(result), -1).any(axis=1))
    rows = pick_rows(len(values), active)
    return (values[rows], *args[1:]), kwargs


def narrow_settle(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    """Řádky a skupiny, kde se stav mění; ``settle`` je po buňkách (řádek, skupina) nezávislé."""
    (current, previous, present, heard, fitness, slot_keys, row_keys, drift_scale, renewal, loss_floor,
     *scalars) = args
    updated, baseline = result
    changed = (updated != current).any(axis=2) | (baseline != previous).any(axis=2)
    rows = pick_rows(len(current), np.union1d(np.flatnonzero(changed.any(axis=1)),
                                              np.flatnonzero((~present).any(axis=1))[:2]))
    shown = np.flatnonzero(changed[rows].any(axis=0))
    rest = np.setdiff1d(np.arange(current.shape[1]), shown)
    absent = np.flatnonzero((~present[rows]).any(axis=0))
    groups = np.union1d(np.union1d(shown[evenly(len(shown), GROUPS)] if len(shown) else shown,
                                   rest[evenly(len(rest), 2)] if len(rest) else rest),
                        absent[evenly(len(absent), 2)] if len(absent) else absent).astype(np.intp)

    def block(array: np.ndarray) -> np.ndarray:
        return array[rows][:, groups]

    return (block(current), block(previous), block(present), block(heard), block(fitness), slot_keys[rows],
            row_keys[groups], drift_scale[groups], renewal[groups], loss_floor[groups], *scalars), kwargs


def narrow_normalized(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
    array, fallback = args
    many = (array > 0).sum(axis=-1) >= 2
    rows = pick_rows(len(array), np.flatnonzero(many.reshape(len(array), -1).any(axis=1)))
    shown = np.flatnonzero(many[rows].any(axis=0))
    rest = np.setdiff1d(np.arange(array.shape[1]), shown)
    groups = np.union1d(shown[evenly(len(shown), GROUPS)] if len(shown) else shown,
                        rest[evenly(len(rest), 2)] if len(rest) else rest).astype(np.intp)
    return (array[rows][:, groups], fallback[rows][:, groups]), kwargs


def narrow_factors(row_args: tuple[int, ...], interesting: int) -> Callable[..., Any]:
    """Řádky proměnných (první osa argumentů ``row_args``): jiné než výchozí váhy domény a pestré druhy."""
    def narrow(original: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> Any:
        weight = np.asarray(args[interesting])
        kinds = np.asarray(args[0])
        special = np.flatnonzero(weight != 1.0)
        chosen = np.union1d(special[evenly(len(special), FACTOR_ROWS // 2)] if len(special) else special,
                            np.concatenate([np.flatnonzero(kinds == kind)[:3] for kind in np.unique(kinds)]))
        rows = chosen[evenly(len(chosen), FACTOR_ROWS)].astype(np.intp)
        return tuple(arg[rows] if index in row_args else arg for index, arg in enumerate(args)), kwargs
    return narrow


def any_cross(result: Any) -> bool:
    return any(bool(np.any(block != 0)) for block in result)


def multi_slot(result: Any) -> bool:
    return bool(((np.asarray(result) > 0).sum(axis=-1) >= 2).any())


def build_recorders() -> list[tuple[Any, str, Recorder]]:
    def make(name: str, limit: int, **options: Any) -> tuple[Any, str, Recorder]:
        return phases, name, Recorder(f"cee.v2.phases_transmission.{name}", getattr(phases, name), limit, **options)

    # ``hear``: zajímavé je volání s víc vazbami mezi jazyky nebo víc kanály (to se podle výsledku nepozná).
    rich = {"flag": False}
    real_hear = phases.hear

    def tracking_hear(*args: Any, **kwargs: Any) -> Any:
        rich["flag"] = len(args[6]) >= 2 or len(args[7]) >= 2
        return real_hear(*args, **kwargs)

    interesting_settle = {"flag": False}
    real_settle = phases.settle

    def tracking_settle(*args: Any, **kwargs: Any) -> Any:
        result = real_settle(*args, **kwargs)
        interesting_settle["flag"] = bool(not args[2].all() or multi_slot(result[0]))
        return result

    settle = (phases, "settle", Recorder("cee.v2.phases_transmission.settle", tracking_settle, 28,
                                         narrow=narrow_settle, is_interesting=lambda result: interesting_settle["flag"]))
    hear = (phases, "hear", Recorder("cee.v2.phases_transmission.hear", tracking_hear, 24, narrow=narrow_hear,
                                     is_interesting=lambda result: rich["flag"]))

    return [
        make("mixing_from_links", 10),
        make("components", 10),
        make("foreign_mask", 6),
        make("elite_shares", 6),
        make("trade_shares", 6),
        make("neighbor_fraction", 6),
        make("internal_blocks", 10),
        make("cross_blocks", 12, is_interesting=any_cross),
        make("cohort_scales", 10),
        make("channel_weights", 12),
        make("borrowing_factors", 12, narrow=narrow_factors((0, 2, 3), 3)),
        make("interference_factors", 6, narrow=narrow_factors((0,), 0)),
        make("reading_factors", 8, narrow=narrow_factors((0, 2, 4), 4)),
        make("school_factors", 8, narrow=narrow_factors((0, 2), 2)),
        make("liturgy_factors", 8, narrow=narrow_factors((0, 1, 2), 2)),
        make("mix", 30, narrow=narrow_mix),
        hear,
        settle,
        make("normalized", 30, narrow=narrow_normalized, is_interesting=multi_slot),
    ]


def synthetic_settle() -> list[Any]:
    """Volání ``settle`` se skupinami bez proměnné (ve skutečných bězích se nestane, každá skupina má všechny živé proměnné).

    Vstup je pevně semínkovaný a uložený v záznamu; výsledek spočítá Python.
    """
    generator = np.random.default_rng(20261103)
    shape = (3, 6, 4)
    current = generator.dirichlet(np.ones(4), size=shape[:2])
    current[:, :, 3] = 0.0
    current[1, :, 2:] = 0.0
    current /= current.sum(axis=2, keepdims=True)
    previous = np.clip(current + generator.normal(0.0, 0.05, shape), 0.0, None)
    present = np.ones(shape[:2], dtype=bool)
    present[0, 1] = present[1, 4] = present[2, 0] = False
    current[~present] = 0.0
    previous[~present] = 0.0
    heard = np.clip(current + generator.normal(0.0, 0.1, shape), 0.0, None)
    heard[1, :, 0] = 0.97
    heard[1, :, 1] = 0.03
    fitness = generator.uniform(-1.0, 1.0, shape)
    slot_keys = generator.integers(1, 2**63, size=(3, 4), dtype=np.uint64)
    row_keys = generator.integers(1, 2**63, size=6, dtype=np.uint64)
    args = (current, previous, present, heard, fitness, slot_keys, row_keys, np.full(6, 0.05), np.full(6, 0.4),
            np.full(6, 0.01), 1.0, 0.3, 0.05, 0.9)
    return [json.loads(golden.dump({"args": list(args), "kwargs": {}, "result": phases.settle(*args)}))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="tests/v2/data")
    parser.add_argument("--scenarios", nargs="*", default=list(SCENARIOS), help="jen tyto scénáře (zkouška)")
    args = parser.parse_args()
    recorders = build_recorders()
    originals = [(module, name, getattr(module, name)) for module, name, _ in recorders]
    for module, name, recorder in recorders:
        setattr(module, name, recorder)
    try:
        for name in args.scenarios:
            build, years = SCENARIOS[name]
            world, events = build()
            simulation = Simulation(world, events=events)
            simulation.run(years)
            print(f"{name}: {years} let, událostí {len(simulation.history.events)}", flush=True)
    finally:
        for module, name, original in originals:
            setattr(module, name, original)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = {"functions": {recorder.name: {"calls": recorder.calls, "records": recorder.records()}
                          for _, _, recorder in recorders}}
    data["functions"]["cee.v2.phases_transmission.settle"]["records"] += synthetic_settle()
    path = output / "golden_transmission.json.gz"
    # Bez jména a času v hlavičce, ať je soubor při každém běhu bajt po bajtu stejný.
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
    print(f"{path}: {path.stat().st_size / 1024:.0f} kB")
    for name, entry in data["functions"].items():
        print(f"    {name}: {len(entry['records'])} záznamů z {entry['calls']} volání")


if __name__ == "__main__":
    main()

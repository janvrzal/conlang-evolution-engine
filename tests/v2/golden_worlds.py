"""Společné části zlatých dat tlaků a hledání míst inovací: scénáře, výběr vzorku, kódování a sondy.

Skripty ``scripts/v2_golden_pressures.py`` a ``scripts/v2_golden_sites.py`` zaznamenají
zlatá data, testy ``test_v2_golden_pressures.py`` a ``test_v2_golden_sites.py`` je
ověří. Obojí používá tytéž scénáře, tentýž výběr ticků a skupin a tytéž sondy, aby
záznam a ověření nemohly dělat něco jiného.

**Hranice, kterou zlatá data hlídají** (nemění se při předělání indexů na čísla z registru):

- tlaky: vstupem je dávka (:class:`cee.v2.pressures.base.PressureBatch`) a stav světa
  v ticku, výstupem pole ``scores``;
- hledání míst: vstupem je stav světa na začátku inovační fáze ticku a skupina,
  výstupem ``sites``, ``rates``, ``total_rate`` a ``weighted_sites`` každého druhu změny.

**Stav světa se neukládá, ale deterministicky se vyrobí.** Snímek světa (pickle
checkpointu) má i po stlačení 1 až 3 MB, limit na soubor je 1 MB. Svět v kterémkoli
ticku scénáře proto vznikne během ze scénáře (:data:`SCENARIOS`), který je bitově
shodný (otisky ``scripts/v2_digests.py``); v souboru jsou jen očekávané výstupy
a vstupy dávek jako pole. Sondy se napojují na běh bez zásahu do zdroje modelu:
``Simulation._innovate`` na instanci a ``transmission.fitness_of`` s ``Pressure.scores``
na modulu a třídách.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import types
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cee.v2 import transmission
from cee.v2.changes import DEFAULT_CHANGES, Change, InnovationContext
from cee.v2.language.constructions import Construction
from cee.v2.pressures.base import Pressure, PressureBatch
from cee.v2.rng import Stream
from cee.v2.scenarios import (
    ProtoLanguage,
    Region,
    language_shift,
    region_world,
    village_grid,
)
from cee.v2.simulation import Simulation
from tests.v2.edit_worlds import church_school, trade_elite

DATA = Path(__file__).parent / "data"

#: Délka kroku simulace v letech (``SimulationConfig.dt``).
DT = 25.0


# --- scénáře ------------------------------------------------------------------------


def grid() -> tuple[Any, list[Any], float]:
    return village_grid(5, 5, seed=2, morphology=True, semantics=True), [], 1000.0


def shift() -> tuple[Any, list[Any], float]:
    world, events = language_shift(2, start=300.0)
    return world, events, 900.0


def valley() -> tuple[Any, list[Any], float]:
    """Údolí 10 × 5 se syntaxí a významem, zkráceně (celý běh je 2 000 let)."""
    return village_grid(10, 5, seed=1, syntax=True, semantics=True), [], 400.0


#: Gramatika, ve které se hned od začátku najdou místa vzácných cest syntaxe: opis, přiklonění
#: (``PAST``), srůst s koncovkou (``FUTURE``), exaptace (pevný slovosled, ``DEFINITE`` bez výrazu,
#: pád ``OBJ``) a zkrácení zápornice (``NEG``).
RARE_GRAMMAR = {
    "PAST": Construction("PAST", "periphrastic", "have", "free"),
    "FUTURE": Construction("FUTURE", "periphrastic", "want", "clitic"),
    "ASPECT": Construction("ASPECT", "zero"),
    "DEFINITE": Construction("DEFINITE", "zero"),
    "PL": Construction("PL", "synthetic"),
    "OBJ": Construction("OBJ", "synthetic"),
    "NEG": Construction("NEG", "embraced", "not", reinforcer="step"),
    "ORDER": Construction("ORDER", "fixed", order="SVO"),
}


def rare_grammar() -> tuple[Any, list[Any], float]:
    """Vzácné cesty syntaxe a tabuizovaný pojem (``TabooReplacement``, ``Taboo``)."""
    world = village_grid(3, seed=3, grammar=RARE_GRAMMAR, semantics=True, taboo=("water",))
    return world, [], 1000.0


#: Slova se skupinou ``sC`` na začátku (prothesis), palatalizované souhlásky, nosová samohláska a tóny.
_SC_WORDS = ["spata", "stola", "skani", "spito", "kʲana", "smola", "skapa", "ɡʲitã", "stipa", "tʲoka"]


def rare_sounds() -> tuple[Any, list[Any], float]:
    """Hlásky, které se v obyčejných scénářích nenajdou: počáteční ``sC`` a tóny."""
    from cee.v2.scenarios import DEFAULT_CONCEPTS

    words = {concept: _SC_WORDS[index % len(_SC_WORDS)] for index, concept in enumerate(DEFAULT_CONCEPTS)}
    language = ProtoLanguage("a", consonants=("p", "t", "k", "s", "n", "m", "l", "r", "j", "kʲ", "ɡʲ", "tʲ"), words=words,
                             tones=("˥", "˦", "˧"))
    world = region_world((Region("r", (0.0, 0.0), villages=3),), seed=2, languages=(language,), phonology=True,
                         semantics=True)
    return world, [], 750.0


def trade_elite_world() -> tuple[Any, list[Any], float]:
    """Cizí elita a obchodní cesta (kanály ``elite`` a ``trade``)."""
    return trade_elite()


def church_school_world() -> tuple[Any, list[Any], float]:
    """Písmo, církev, liturgie a škola (tlak ``Norm``)."""
    return church_school()


#: Scénáře v pevném pořadí: jméno → sestavení světa (svět, události, počet let běhu).
SCENARIOS: dict[str, Callable[[], tuple[Any, list[Any], float]]] = {
    "grid-5x5": grid,
    "shift": shift,
    "valley-50": valley,
    "trade-elite": trade_elite_world,
    "church-school": church_school_world,
    "rare-grammar": rare_grammar,
    "rare-sounds": rare_sounds,
}


def new_simulation(name: str) -> tuple[Simulation, int]:
    """Nový běh scénáře a jeho počet ticků."""
    world, events, years = SCENARIOS[name]()
    return Simulation(world, events=events), int(years / DT + 1e-9)


# --- náhodný výběr vzorku ----------------------------------------------------------


def sample(stream: Stream, items: Sequence[Any], count: int) -> list[Any]:
    """``count`` různých položek v původním pořadí; losy ze ``Stream`` postupně z toho, co zbývá."""
    left = list(range(len(items)))
    picked = [left.pop(stream.integers(len(left))) for _ in range(min(count, len(items)))]
    return [items[index] for index in sorted(picked)]


def sample_ticks(name: str, ticks: int, count: int, purpose: str = "") -> list[int]:
    """Tiky vzorku scénáře (1 až ``ticks``), deterministicky ze ``Stream``; ``purpose`` odliší vzorky."""
    parts = (name, purpose) if purpose else (name,)
    return sample(Stream(0, "golden-ticks", *parts), list(range(1, ticks + 1)), count)


def sample_groups(name: str, tick: int, group_ids: Sequence[str], count: int) -> list[str]:
    """Skupiny vzorku v ticku (``group_ids`` jsou seřazené), deterministicky ze ``Stream``."""
    return sample(Stream(0, "golden-groups", name, tick), list(group_ids), count)


# --- kódování polí do JSON -----------------------------------------------------------


def encode(value: Any) -> Any:
    """Hodnota v JSON: pole jako ``{"nd": dtype, "shape": [...], "data": [...]}``, n-tice jako ``{"t": [...]}``."""
    if isinstance(value, np.ndarray):
        return {"nd": str(value.dtype), "shape": list(value.shape), "data": value.ravel().tolist()}
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


def decode(value: Any) -> Any:
    """Opak :func:`encode`."""
    if isinstance(value, dict):
        if "nd" in value:
            return np.array(value["data"], dtype=value["nd"]).reshape(value["shape"])
        if "t" in value:
            return tuple(decode(item) for item in value["t"])
        return {key: decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode(item) for item in value]
    return value


def same(actual: Any, expected: Any) -> bool:
    """Přesná shoda: pole včetně ``dtype``, tvaru a bitů, čísla bez ohledu na obal (``np.float64`` či ``float``)."""
    if isinstance(actual, np.ndarray) or isinstance(expected, np.ndarray):
        return (isinstance(actual, np.ndarray) and isinstance(expected, np.ndarray)
                and actual.dtype == expected.dtype and actual.shape == expected.shape
                and actual.tobytes() == expected.tobytes())
    if isinstance(actual, (tuple, list)) and isinstance(expected, (tuple, list)):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, dict) and isinstance(expected, dict):
        return set(actual) == set(expected) and all(same(actual[key], expected[key]) for key in actual)
    if isinstance(actual, (float, np.floating)) and isinstance(expected, (float, np.floating)):
        return float(actual).hex() == float(expected).hex()
    return bool(actual == expected)


def write_gzip(path: Path, data: Any) -> None:
    """Zapíše JSON stlačený bez jména a času v hlavičce, ať je soubor při každém běhu bajt po bajtu stejný."""
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
        handle.write(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())


def read_gzip(path: Path) -> Any:
    with gzip.open(path, "rt") as handle:
        return json.load(handle)


# --- hledání míst inovací ------------------------------------------------------------


class SiteStrings:
    """Tabulka řetězců míst: v záznamu jsou místa jako čísla do ní (soubor je pak několikrát menší)."""

    def __init__(self, table: Sequence[str] = ()) -> None:
        self.table = list(table)
        self.numbers = {text: number for number, text in enumerate(self.table)}

    def numbers_of(self, sites: Sequence[str]) -> list[int]:
        found = []
        for site in sites:
            number = self.numbers.get(site)
            if number is None:
                number = self.numbers[site] = len(self.table)
                self.table.append(site)
            found.append(number)
        return found

    def sites_of(self, numbers: Sequence[int]) -> list[str]:
        return [self.table[number] for number in numbers]


def site_entry(change: Change, context: InnovationContext, strings: SiteStrings) -> dict[str, Any]:
    """Výsledek hledání míst jednoho druhu změny ve skupině: ``sites``, ``rates``, ``total_rate``, ``weighted_sites``."""
    sites = list(change.sites(context))
    uniform = change.uses_uniform_rate()
    entry: dict[str, Any] = {"kind": change.kind, "sites": strings.numbers_of(sites)}
    if sites:
        rates = [float(rate) for rate in change.rates(context, sites)]
        if uniform:
            assert len(set(rates)) == 1, change.kind
            entry["rate"] = rates[0]
            entry["rate_scale"] = float(change.rate_scale(context))
        else:
            entry["rates"] = rates
    entry["total_rate"] = float(change.total_rate(context))
    weighted_sites, weights = change.weighted_sites(context)
    if not len(weighted_sites):
        entry["weighted"] = "empty"
    else:
        assert list(weighted_sites) == sites, change.kind
        entry["weighted"] = "same"
    entry["weights"] = None if weights is None else [float(weight) for weight in weights]
    return entry


def informative(entry: dict[str, Any]) -> bool:
    """Má druh změny v tomto stavu místa a nenulovou celkovou míru (může vyrobit inovaci)?"""
    return bool(entry["sites"]) and entry["total_rate"] > 0.0 and entry["weighted"] == "same"


def inventory_contexts(simulation: Simulation, group_ids: Sequence[str]) -> list[tuple[str, InnovationContext]]:
    """Kontexty inovační fáze právě probíhajícího ticku (jako ve ``Simulation._innovate``)."""
    year = simulation.year
    world = simulation.world
    return [(group_id, InnovationContext(world, world.groups[group_id], world.groups[group_id].main_code,
                                         simulation.tick, year))
            for group_id in group_ids]


def innovating_groups(simulation: Simulation) -> list[str]:
    """Skupiny, ve kterých se inovuje (psaný kód se nemění), seřazené."""
    return [group_id for group_id in simulation.world.group_ids() if not simulation.world.groups[group_id].written]


@contextlib.contextmanager
def probing_innovation(simulation: Simulation, probe: Callable[[Simulation], None]) -> Iterator[None]:
    """Před inovační fází každého ticku zavolá ``probe(simulation)`` (stav světa je tak, jak ho vidí ``_innovate``)."""
    original = simulation._innovate

    def innovate(self: Simulation, year: float) -> None:
        probe(self)
        original(year)

    simulation._innovate = types.MethodType(innovate, simulation)  # type: ignore[method-assign]
    try:
        yield
    finally:
        del simulation._innovate


KINDS = tuple(change.kind for change in DEFAULT_CHANGES)


# --- tlaky --------------------------------------------------------------------------

#: Kolik řádků (proměnných) a skupin smí mít jeden záznam dávky: ty, kde se něco děje, a pár dalších.
ROWS = 5
GROUPS = 6


def pressure_classes() -> list[type[Pressure]]:
    """Všechny třídy tlaků, které definují ``scores`` (i podtřídy)."""
    # Moduly tlaků se načtou importem balíčku.
    import cee.v2.pressures  # noqa: F401
    import cee.v2.pressures.lexical  # noqa: F401
    import cee.v2.pressures.morphological  # noqa: F401
    import cee.v2.pressures.syntactic  # noqa: F401

    found: list[type[Pressure]] = []
    stack = [Pressure]
    while stack:
        current = stack.pop()
        for subclass in current.__subclasses__():
            stack.append(subclass)
            if "scores" in subclass.__dict__:
                found.append(subclass)
    return sorted(found, key=lambda item: item.__qualname__)


def full_scores(scores: Any, shape: tuple[int, ...]) -> np.ndarray:
    return np.broadcast_to(np.asarray(scores), shape)


@contextlib.contextmanager
def probing_pressures(ticks: Callable[[int], bool], handle: Callable[[int, int, list[Any]], None]) -> Iterator[None]:
    """Po každém volání ``transmission.fitness_of`` v ticku, pro který ``ticks(tick)`` platí, zavolá ``handle``.

    ``handle(tick, first, batches)``: ``first`` je pořadí první dávky tohoto volání v ticku
    (od nuly), ``batches`` seznam dávek ``(batch, [(tlak, výsledek), ...])`` v pořadí volání.
    Tlaky se při tom nijak nemění; ``scores`` se obalí jen po dobu sledovaného volání.
    """
    state: dict[str, Any] = {"calls": None, "counted": {}}
    patched: list[tuple[type[Pressure], Any]] = []
    for cls in pressure_classes():
        original = cls.__dict__["scores"]

        def make(original: Callable[..., Any]) -> Callable[..., Any]:
            def scores(self: Pressure, batch: PressureBatch) -> Any:
                result = original(self, batch)
                if state["calls"] is not None:
                    state["calls"].append((self, batch, np.array(result)))
                return result
            return scores

        cls.scores = make(original)  # type: ignore[method-assign]
        patched.append((cls, original))
    original_fitness = transmission.fitness_of

    def fitness_of(world: Any, block: Any, inputs: Any, pressures: Any, heard: Any, columns: Any = None) -> Any:
        if columns is not None or not ticks(inputs.tick):
            return original_fitness(world, block, inputs, pressures, heard, columns)
        state["calls"] = []
        try:
            result = original_fitness(world, block, inputs, pressures, heard, columns)
        finally:
            calls, state["calls"] = state["calls"], None
        grouped: list[Any] = []
        for pressure, batch, scores in calls:
            if grouped and grouped[-1][0] is batch:
                grouped[-1][1].append((pressure, scores))
            else:
                grouped.append((batch, [(pressure, scores)]))
        first = state["counted"].get(inputs.tick, 0)
        state["counted"][inputs.tick] = first + len(grouped)
        handle(inputs.tick, first, grouped)
        return result

    transmission.fitness_of = fitness_of  # type: ignore[assignment]
    try:
        yield
    finally:
        transmission.fitness_of = original_fitness  # type: ignore[assignment]
        for cls, original in patched:
            cls.scores = original  # type: ignore[method-assign]


def informative_cells(outputs: Sequence[tuple[Pressure, np.ndarray]], shape: tuple[int, ...]) -> np.ndarray:
    """Buňky (řádek, skupina), ve kterých cokoli kromě konformity (nenulové všude) není nula."""
    active = np.zeros(shape[:2], dtype=bool)
    for pressure, scores in outputs:
        if pressure.name != "conformity":
            active |= (full_scores(scores, shape) != 0).any(axis=2)
    return active


def evenly(count: int, limit: int) -> np.ndarray:
    """Až ``limit`` pevně rozložených indexů z ``count``."""
    if count <= limit:
        return np.arange(count)
    return np.unique(np.linspace(0, count - 1, limit).astype(np.intp))


def choose(active: np.ndarray, rows: int = ROWS, groups: int = GROUPS) -> tuple[np.ndarray, np.ndarray]:
    """Řádky a skupiny záznamu: zajímavé (rovnoměrně) a po jedné obyčejné navíc."""
    live_rows = np.flatnonzero(active.any(axis=1))
    chosen_rows = live_rows[evenly(len(live_rows), rows)] if len(live_rows) else live_rows
    rest = np.setdiff1d(np.arange(active.shape[0]), live_rows)
    chosen_rows = np.union1d(chosen_rows, rest[evenly(len(rest), 1)] if len(rest) else rest).astype(np.intp)
    live_columns = np.flatnonzero(active[chosen_rows].any(axis=0))
    chosen_columns = live_columns[evenly(len(live_columns), groups)] if len(live_columns) else live_columns
    rest = np.setdiff1d(np.arange(active.shape[1]), live_columns)
    chosen_columns = np.union1d(chosen_columns, rest[evenly(len(rest), 1)] if len(rest) else rest).astype(np.intp)
    return chosen_rows, chosen_columns


def narrowed(batch: PressureBatch, rows: np.ndarray, columns: np.ndarray) -> PressureBatch:
    """Výřez dávky na zvolené řádky a skupiny (tlaky jsou po řádcích a po skupinách nezávislé)."""
    return PressureBatch(
        world=batch.world,
        variable_ids=[batch.variable_ids[row] for row in rows],
        group_ids=[batch.group_ids[column] for column in columns],
        freqs=batch.freqs[rows][:, columns],
        slots=[list(batch.slots[row]) for row in rows],
        tick=batch.tick,
        heard=batch.heard[rows][:, columns],
        numbers=batch.slot_numbers()[rows],
    )


def batch_record(batch: PressureBatch) -> dict[str, Any]:
    """Vstup dávky jako pole (bez světa)."""
    return {
        "variable_ids": list(batch.variable_ids), "group_ids": list(batch.group_ids), "tick": batch.tick,
        "freqs": batch.freqs, "heard": batch.heard, "numbers": batch.slot_numbers(),
        "slots": [list(row) for row in batch.slots],
    }


def batch_from_record(world: Any, record: dict[str, Any]) -> PressureBatch:
    """Dávka ze záznamu (pole), nad živým světem, ze kterého tlaky čtou stav."""
    return PressureBatch(
        world=world, variable_ids=record["variable_ids"], group_ids=record["group_ids"],
        freqs=record["freqs"], slots=record["slots"], tick=record["tick"], heard=record["heard"],
        numbers=record["numbers"],
    )


PARAMETERS = (
    "stress_strength_multiplier", "clarity_short_factor", "functional_load_scale", "dispersion_factor",
    "coda_tolerance_scale", "entrenchment_strength", "entrenchment_frequency_exponent", "entrenchment_base",
    "emergence_need_scale", "economy_word_cost", "fusion_bonus", "learnability_strength", "order_rigidity",
)


def reads_of(batch: PressureBatch) -> dict[str, Any]:
    """Co tlaky čtou ze světa kromě dávky, jako pole nebo čísla (pro tlaky, kde je to čistá hodnota).

    Dávka a tyto vstupy stačí k výpočtu těchto tlaků bez živého světa: ``Appeal``, ``Motivation``,
    ``Entrenchment``, ``Actuation`` a ``LexicalActuation`` (sloupce variant, frekvence pojmů, semínko),
    ``Conformity`` (nic), ``Articulation``, ``Clarity``, ``FunctionalLoad``, ``Dispersion``
    a ``Phonotactics`` (hodnocení procesů a rysy skupin, ``process_*``, ``cell_*``), ``Conservation``,
    ``Distinctiveness``, ``Teachability``, ``Uniformity`` (hodnocení tvarů, ``form_*``) a váhy
    z ``Parameters``. Zbývající tlaky čtou index nebo objekt světa a jejich vstupy zlatá data
    neobsahují, jen výstup ze stavu světa v daném ticku (viz ``scripts/v2_golden_pressures.py``).
    """
    from cee.v2.assessment import assess_many
    from cee.v2.language.form_assessment_index import assess
    from cee.v2.phonology import changed_id
    from cee.v2.pressures.linguistic import coda_share

    world = batch.world
    rows, columns = len(batch.variable_ids), len(batch.group_ids)
    groups = [world.groups[group_id] for group_id in batch.group_ids]
    variables = [world.variables[variable_id] for variable_id in batch.variable_ids]
    reads: dict[str, Any] = {
        "seed": world.seed,
        "params": {name: float(getattr(world.params, name)) for name in PARAMETERS},
        "origin_names": list(world.columns.variants.payload_origins.names),
        "slot_appeal": batch.slot_column("appeal", -1.0),
        "slot_change": batch.slot_column("change", -1.0),
        "slot_morpheme": batch.slot_column("morpheme", -1.0),
        "slot_origin": batch.slot_column("origin", -1.0),
        "concept_frequency": np.array(
            [world.concept_frequency(variable.key) if variable.kind == "lexical" else np.nan
             for variable in variables], dtype=np.float64),
        "group_l2_share": np.array([group.main_code.l2_share for group in groups], dtype=np.float64),
        "group_schooling": np.array([group.schooling for group in groups], dtype=np.float64),
        "group_strong_stress": np.array(
            [getattr(group.main_code, "stress_strength", "weak") == "strong" for group in groups], dtype=bool),
        "group_coda_share": np.array([coda_share(world, group_id) for group_id in batch.group_ids],
                                     dtype=np.float64),
        "taboo": np.array([[variable.kind == "lexical" and variable.key in group.taboo for group in groups]
                           for variable in variables], dtype=bool).reshape(rows, columns),
    }
    process_slot = np.full(rows, -1, dtype=np.intp)
    process_values = np.zeros((rows, 4))
    cells: list[tuple[int, int, Any]] = []
    form_slot = np.full(rows, -1, dtype=np.intp)
    form_flags = np.zeros((rows, 2), dtype=bool)
    form_cells: list[tuple[int, int, Any]] = []
    for row, variable_id in enumerate(batch.variable_ids):
        process = world.processes.get(variable_id)
        change = world.form_changes.get(variable_id)
        if process is None and change is None:
            continue
        changed = changed_id(variable_id)
        if changed not in batch.slots[row]:
            continue
        slot = list(batch.slots[row]).index(changed)
        reached = np.flatnonzero((batch.freqs[row, :, slot] > 0) | (batch.heard[row, :, slot] > 0))
        if process is not None:
            process_slot[row] = slot
            process_values[row] = (
                process.ease, process.clarity,
                bool(getattr(process, "reductive", False) and getattr(process, "stress", None) == "unstressed"),
                bool(getattr(process, "family", "") == "apocope"),
            )
            found = assess_many(world, [batch.group_ids[int(column)] for column in reached], variable_id, batch.tick)
            cells += [(row, int(column), item) for column, item in zip(reached, found)]
        else:
            form_slot[row] = slot
            form_flags[row] = (change.operation == "level", change.lexeme_wide)
            for column in reached:
                form_cells.append((row, int(column), assess(world, batch.group_ids[int(column)], variable_id)))
    reads["process_slot"] = process_slot
    reads["process_values"] = process_values
    reads["cell_row"] = np.array([row for row, _, _ in cells], dtype=np.intp)
    reads["cell_column"] = np.array([column for _, column, _ in cells], dtype=np.intp)
    reads["cell_assessment"] = np.array(
        [[item.merge_mass, item.short_share, item.dispersion_delta, item.markedness_delta] for _, _, item in cells],
        dtype=np.float64).reshape(len(cells), 4)
    reads["form_slot"] = form_slot
    reads["form_flags"] = form_flags
    reads["form_cell_row"] = np.array([row for row, _, _ in form_cells], dtype=np.intp)
    reads["form_cell_column"] = np.array([column for _, column, _ in form_cells], dtype=np.intp)
    reads["form_cell_present"] = np.array([item is not None for _, _, item in form_cells], dtype=bool)
    reads["form_cell_values"] = np.array(
        [[0.0, 0.0, 0.0, 0.0] if item is None else
         [item.gain, item.frequency, item.syncretic_before, item.syncretic_after] for _, _, item in form_cells],
        dtype=np.float64).reshape(len(form_cells), 4)
    return reads

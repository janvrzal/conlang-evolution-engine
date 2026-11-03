"""Funkce fází kroku nad poli (``cee.v2.phases``): zlatá data a drobné případy.

Zlatá data (``tests/v2/data/golden_innovation.json.gz``, ``golden_vocabulary.json.gz``
a ``golden_grammar.json.gz``) zaznamenal ``scripts/v2_golden_phases.py`` ze
skutečných běhů v Pythonu: vstupy a výstupy každé čisté funkce. Funkce musí dát
přesně tytéž výsledky (pole bit po bitu včetně ``dtype`` a tvaru); tentýž soubor
později ověří Rust implementace. Druhá část hlídá, že záznam pokrývá všechny
větve funkcí, a třetí ověřuje význam funkcí na drobných případech.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import cee.v2.morphology
import cee.v2.simulation
from cee.v2 import phases, rng
from cee.v2.language import morphology as language_morphology
from cee.v2.language.lexicon import UnitForm

DATA = Path(__file__).parent / "data"

#: Název zaznamenané funkce → funkce, kterou test zavolá (zapisovač zaznamenával volání v modulech, kde se používají).
FUNCTIONS: dict[str, Callable[..., Any]] = {
    **{f"cee.v2.phases.{name}": getattr(phases, name) for name in (
        "innovation_group_keys", "expected_counts", "uniform_rate", "rate_total", "normalize_rates",
        "site_weights", "category_loss_rates", "draw_site", "innovation_mask", "change_events",
        "threshold_crossings", "activation_cells", "trace_cells", "analogy_decisions", "grammar_ready",
        "ending_actions", "stress_updates",
    )},
    "cee.v2.simulation.hash_poisson": rng.hash_poisson,
    "cee.v2.morphology.level": language_morphology.level,
    "cee.v2.morphology.extend": language_morphology.extend,
    "cee.v2.morphology.rebracket": language_morphology.rebracket,
}
MODULES = ("innovation", "vocabulary", "grammar")


def decode(value: Any) -> Any:
    """Opak ``encode`` ze zapisovače: pole, n-tice a tvary slov."""
    if isinstance(value, dict):
        if "nd" in value:
            return np.array(value["data"], dtype=value["nd"]).reshape(value["shape"])
        if "t" in value:
            return tuple(decode(item) for item in value["t"])
        if "unit" in value:
            form, boundary, exponent = value["unit"]
            return UnitForm(tuple(form), boundary, exponent)
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
    if isinstance(actual, UnitForm) or isinstance(expected, UnitForm):
        return isinstance(actual, UnitForm) and isinstance(expected, UnitForm) and tuple(actual) == tuple(expected)
    if isinstance(actual, tuple) and isinstance(expected, tuple):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, (float, np.floating)) and isinstance(expected, (float, np.floating)):
        return float(actual).hex() == float(expected).hex()
    return bool(actual == expected)


@pytest.fixture(scope="module")
def golden() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for module in MODULES:
        with gzip.open(DATA / f"golden_{module}.json.gz", "rt") as handle:
            found.update(json.load(handle)["functions"])
    return found


@pytest.mark.parametrize("name", sorted(FUNCTIONS))
def test_golden_records_match_python(golden: dict[str, dict[str, Any]], name: str) -> None:
    entry = golden[name]
    assert entry["records"], f"{name}: zlatá data jsou prázdná, nahraj je skriptem znovu"
    function = FUNCTIONS[name]
    for number, record in enumerate(entry["records"]):
        args = [decode(arg) for arg in record["args"]]
        kwargs = {key: decode(value) for key, value in record["kwargs"].items()}
        actual = function(*args, **kwargs)
        assert same(actual, decode(record["result"])), f"{name}: záznam {number} se liší"


def _records(golden: dict[str, dict[str, Any]], name: str) -> list[tuple[list[Any], Any]]:
    return [([decode(arg) for arg in record["args"]], decode(record["result"]))
            for record in golden[f"cee.v2.phases.{name}"]["records"]]


def test_golden_covers_every_branch(golden: dict[str, dict[str, Any]]) -> None:
    """Záznam obsahuje všechny druhy výsledků, ne jen prázdné případy."""
    # Výběr místa: rovnoměrný i podle vah.
    draws = _records(golden, "draw_site")
    assert any(args[2] is None for args, _ in draws) and any(args[2] is not None for args, _ in draws)
    # Milníky, ustálení, zánik; odchody i příchody přes práh; aktivace; stopy.
    events = _records(golden, "change_events")
    assert any(len(result[0][0]) for _, result in events)
    assert any(len(result[1][0]) for _, result in events)
    assert any(len(result[2][0]) for _, result in events)
    crossings = _records(golden, "threshold_crossings")
    assert any(len(result[0][0]) for _, result in crossings) and any(len(result[1][0]) for _, result in crossings)
    assert any(len(result[0]) for _, result in _records(golden, "activation_cells"))
    assert any(len(result[0]) for _, result in _records(golden, "trace_cells"))
    # Všechna tři rozhodnutí o analogii, nová koncovka (s dárcem i bez) a změna přízvuku.
    decisions = {int(value) for _, result in _records(golden, "analogy_decisions") for value in result}
    assert decisions == {phases.ANALOGY_WAIT, phases.ANALOGY_REMOVE, phases.ANALOGY_APPLY}
    assert any(result.any() for _, result in _records(golden, "grammar_ready"))
    actions = _records(golden, "ending_actions")
    assert any(args[0] for args, _ in actions) and any(not args[0] for args, _ in actions)
    seen = {int(value) for _, result in actions for value in result}
    assert {phases.ENDING_SKIP, phases.ENDING_KEPT, phases.ENDING_FROM_DONOR, phases.ENDING_FROM_CITATION} <= seen
    assert any(result.any() for _, result in _records(golden, "stress_updates"))
    # Tvarové funkce: vyrovnání, rozšíření a obě reanalýzy hranice.
    assert golden["cee.v2.morphology.level"]["records"] and golden["cee.v2.morphology.extend"]["records"]
    rebracketed = [decode(record["result"]) for record in golden["cee.v2.morphology.rebracket"]["records"]]
    assert any(result is not None for result in rebracketed)


def test_golden_files_stay_small() -> None:
    for module in MODULES:
        assert (DATA / f"golden_{module}.json.gz").stat().st_size < 1_000_000


def test_recorded_functions_are_what_the_engine_calls() -> None:
    """Zapisovač nahrazuje funkce v modulech, kde se volají; ta jména musí existovat a být tytéž funkce."""
    assert cee.v2.morphology.level is language_morphology.level
    assert cee.v2.morphology.extend is language_morphology.extend
    assert cee.v2.morphology.rebracket is language_morphology.rebracket
    assert cee.v2.simulation.hash_poisson is rng.hash_poisson


# --- drobné případy -----------------------------------------------------------


def test_expected_counts_uses_generation_or_step_tempo() -> None:
    sums = np.array([[2.0, 3.0], [0.0, 4.0]])
    renewals = np.array([0.5, 0.25])
    frequencies = np.array([2.0, 1.0])
    expected = phases.expected_counts(
        sums, renewals, frequencies, 25.0, np.array([True, False]), np.array([1.0, 0.5])
    )
    # Změna 0 podle generace: míra × obnova × četnost; změna 1 podle roku: míra × krok × četnost × násobek.
    np.testing.assert_array_equal(expected, [[2.0 * 0.5 * 2.0, 3.0 * 25.0 * 2.0 * 0.5], [0.0, 4.0 * 25.0 * 1.0 * 0.5]])


def test_site_weights_normalize_and_reject_empty_total() -> None:
    total, weights = phases.site_weights([1.0, 3.0])
    assert total == 4.0 and weights is not None
    np.testing.assert_array_equal(weights, [0.25, 0.75])
    assert phases.site_weights([0.0, 0.0]) == (0.0, None)


def test_draw_site_continues_the_stream() -> None:
    """Výběr místa dá totéž co proud a vrátí jeho stav, ze kterého se pokračuje."""
    stream = rng.Stream(7, "innovation", 3)
    state = stream.state
    index, after = phases.draw_site(state, 5, None)
    assert index == stream.integers(5) and after == stream.state
    cumulated = rng.cumulative([0.2, 0.0, 0.8])
    index, after = phases.draw_site(after, 3, cumulated)
    assert index == rng.Stream.pick(cumulated, stream.random()) and after == stream.state
    assert index in (0, 2)


def test_category_loss_rates_follow_the_pressure_rules() -> None:
    present = np.array([True, True, True, True, False])
    free = np.array([True, False, False, False, False])
    bound = np.array([False, False, True, True, True])
    synthetic = np.array([False, False, False, True, True])
    weakness = np.array([0.0, 0.0, 0.7, 0.4, 0.9])
    rates = phases.category_loss_rates(0.02, present, free, bound, synthetic, weakness, 0.5, 0.2)
    # Volný opis 1, nevázaný výraz 0, vázaný nesyntetický jen L2 příměs, syntetický slabost + L2 příměs, chybějící 0.
    np.testing.assert_array_equal(rates, [0.02 * 1.0, 0.0, 0.02 * (0.0 + 0.5 * 0.2), 0.02 * (0.4 + 0.5 * 0.2), 0.0])


def test_change_events_milestones_established_and_extinct() -> None:
    before = np.zeros((2, 2, 2))
    after = np.zeros((2, 2, 2))
    before[0, 0, 1], after[0, 0, 1] = 0.05, 0.6  # přešla 0,1 a 0,5
    before[0, 1, 1], after[0, 1, 1] = 0.95, 1.0  # ustálení
    before[1, 0, 0], after[1, 0, 0] = 0.3, 0.0  # zanikla ve všech skupinách
    innovation = np.array([[False, True], [True, False]])
    milestones, established, extinct = phases.change_events(before, after, innovation, np.array([0.1, 0.5, 0.9]))
    assert list(zip(*milestones)) == [(0, 0, 1, 0, 2)]
    assert list(zip(*established)) == [(0, 1, 1)]
    assert list(zip(*extinct)) == [(1, 0)]


def test_threshold_crossings_and_activation_cells() -> None:
    before = np.array([[[0.6, 0.0], [0.4, 0.0]], [[0.6, 0.0], [0.4, 0.0]]])
    after = np.array([[[0.4, 0.0], [0.6, 0.0]], [[0.4, 0.0], [0.6, 0.0]]])
    leave, enter = phases.threshold_crossings(before, after, np.array([True, False]), 0.5)
    assert list(zip(*leave)) == [(0, 0, 0)] and list(zip(*enter)) == [(0, 1, 0)]
    rows, columns = phases.activation_cells(after, np.array([0, -1]), 0.5)
    assert list(rows) == [0] and list(columns) == [1]


def test_analogy_decisions_and_grammar_ready() -> None:
    decisions = phases.analogy_decisions(np.array([0.0, 0.2, 0.5, 0.9]), 0.5)
    assert list(decisions) == [phases.ANALOGY_REMOVE, phases.ANALOGY_WAIT, phases.ANALOGY_APPLY, phases.ANALOGY_APPLY]
    ready = phases.grammar_ready(
        np.array([0.9, 0.9, 0.9, 0.4]), 0.8,
        np.array([True, False, True, True]), np.array([True, True, False, True]), np.array([False, False, False, False]),
    )
    assert list(ready) == [True, False, False, False]


def test_ending_actions_with_and_without_donor() -> None:
    exists = np.array([True, True, False])
    frequency = np.array([0.9, 0.1, 0.0])
    none = np.zeros(0, dtype=bool)
    plain = phases.ending_actions(False, exists, none, none, frequency, 0.5)
    assert list(plain) == [phases.ENDING_KEPT, phases.ENDING_FROM_CITATION, phases.ENDING_FROM_CITATION]
    donor = phases.ending_actions(
        True, exists, np.array([True, True, False]), np.array([True, False, True]), frequency, 0.5
    )
    assert list(donor) == [phases.ENDING_FROM_DONOR, phases.ENDING_SKIP, phases.ENDING_SKIP]


def test_stress_updates_need_a_clear_and_different_winner() -> None:
    changed = phases.stress_updates(
        np.array([0.9, 0.4, 0.9, 0.0]), np.array([2, 2, 3, -1]), np.array([1, 1, 3, 1])
    )
    assert list(changed) == [True, False, False, False]

"""Funkce přenosu nad poli (``cee.v2.phases_transmission``): zlatá data, pokrytí větví a drobné případy.

Zlatá data (``tests/v2/data/golden_transmission.json.gz``) zaznamenal
``scripts/v2_golden_transmission.py`` ze skutečných běhů v Pythonu: vstupy a
výstupy každé čisté funkce. Funkce musí dát přesně tytéž výsledky (pole bit po
bitu včetně ``dtype`` a tvaru); tentýž soubor později ověří Rust implementace.
Druhá část hlídá, že záznam pokrývá všechny větve, třetí ověřuje význam funkcí
a shodu polí s dosavadními skalárními funkcemi světa, čtvrtá přenos po kusech.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cee.v2 import contact, institutions
from cee.v2 import phases_transmission as phases
from cee.v2 import transmission as transmission_module
from cee.v2.parameters import NEUTRAL_CHANNEL_DOMAINS, Parameters
from cee.v2.scenarios import ProtoLanguage, Region, region_world, village_grid
from cee.v2.simulation import Simulation

DATA = Path(__file__).parent / "data" / "golden_transmission.json.gz"
PREFIX = "cee.v2.phases_transmission."
FUNCTIONS = (
    "mixing_from_links", "components", "foreign_mask", "elite_shares", "trade_shares", "neighbor_fraction",
    "internal_blocks", "cross_blocks", "cohort_scales", "channel_weights", "borrowing_factors",
    "interference_factors", "reading_factors", "school_factors", "liturgy_factors", "mix", "hear", "settle",
    "normalized",
)


def decode(value: Any) -> Any:
    """Opak ``encode`` ze zapisovače: pole, n-tice a seznamy."""
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
    """Přesná shoda: pole včetně ``dtype``, tvaru a bitů, čísla bez ohledu na obal."""
    if isinstance(actual, np.ndarray) or isinstance(expected, np.ndarray):
        return (isinstance(actual, np.ndarray) and isinstance(expected, np.ndarray)
                and actual.dtype == expected.dtype and actual.shape == expected.shape
                and actual.tobytes() == expected.tobytes())
    if isinstance(actual, (tuple, list)) and isinstance(expected, (tuple, list)):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    if isinstance(actual, (float, np.floating)) and isinstance(expected, (float, np.floating)):
        return float(actual).hex() == float(expected).hex()
    return bool(actual == expected)


@pytest.fixture(scope="module")
def golden() -> dict[str, dict[str, Any]]:
    with gzip.open(DATA, "rt") as handle:
        found: dict[str, dict[str, Any]] = json.load(handle)["functions"]
    return found


def _records(golden: dict[str, dict[str, Any]], name: str) -> list[tuple[list[Any], Any]]:
    return [([decode(arg) for arg in record["args"]], decode(record["result"]))
            for record in golden[PREFIX + name]["records"]]


@pytest.mark.parametrize("name", FUNCTIONS)
def test_golden_records_match_python(golden: dict[str, dict[str, Any]], name: str) -> None:
    entry = golden[PREFIX + name]
    assert entry["records"], f"{name}: zlatá data jsou prázdná, nahraj je skriptem znovu"
    function = getattr(phases, name)
    for number, record in enumerate(entry["records"]):
        args = [decode(arg) for arg in record["args"]]
        kwargs = {key: decode(value) for key, value in record["kwargs"].items()}
        assert same(function(*args, **kwargs), decode(record["result"])), f"{name}: záznam {number} se liší"


def test_golden_covers_every_branch(golden: dict[str, dict[str, Any]]) -> None:
    """Záznam obsahuje všechny druhy vstupů a výsledků, ne jen prázdné případy."""
    # Vazby mezi jazyky: obecný kontakt (celá vazba i zlomek), elita a obchod.
    cross = _records(golden, "cross_blocks")
    assert any(args[3] is None for args, _ in cross) and any(args[3] is not None for args, _ in cross)
    assert any(any(block.any() for block in result) for _, result in cross)
    assert _records(golden, "elite_shares") and _records(golden, "trade_shares")
    assert any(len(args[0]) > 1 for args, _ in _records(golden, "neighbor_fraction"))
    # Skupiny bez sousedů i propojené komponenty.
    assert any(len(result) > 1 for _, result in _records(golden, "components"))
    assert any(len(members) == 1 for _, result in _records(golden, "components") for members in result)
    # Míšení: vazby uvnitř jazyka, přes jazyky v jednom i více kanálech a všechny čtyři kanály mimo vazby sítě.
    hears = _records(golden, "hear")
    assert any(not args[6] and not args[7] for args, _ in hears)
    assert any(len(args[6]) >= 1 for args, _ in hears) and any(len(args[6]) >= 3 for args, _ in hears)
    assert any(len(args[7]) >= 1 for args, _ in hears) and any(len(args[7]) >= 2 for args, _ in hears)
    # Přenos bloku: ustálení, zánik pod prahem, skupina bez proměnné, soutěž dvou variant a drift.
    settles = _records(golden, "settle")
    threshold = lambda args: args[13]  # noqa: E731
    assert any(((np.max(result[0], axis=2) >= threshold(args)) & (np.max(result[0], axis=2) < 1.0)).any()
               or ((np.max(result[0], axis=2) == 1.0) & ((args[3] > 0).sum(axis=2) > 1)).any()
               for args, result in settles), "ustálení"
    assert any(((args[3] > 0) & (result[0] == 0)).any() for args, result in settles), "zánik varianty"
    assert any((~args[2]).any() for args, _ in settles), "skupina bez proměnné"
    assert any(((result[0] > 0).sum(axis=2) >= 2).any() for _, result in settles), "soutěž variant"
    assert any((args[5] != 0).any() and (np.abs(result[0] - args[0]) > 0).any() for args, result in settles)
    # Normalizace: do dvou slotů (bez řazení) i od tří.
    widths = {args[0].shape[-1] for args, _ in _records(golden, "normalized")}
    assert any(width <= 2 for width in widths) and any(width >= 3 for width in widths)
    # Faktory: slova s jinou než výchozí váhou domény, ostatní druhy proměnných.
    for name, weight_index in (("borrowing_factors", 3), ("reading_factors", 4), ("school_factors", 2),
                               ("liturgy_factors", 2)):
        records = _records(golden, name)
        assert any((args[weight_index] != 1.0).any() for args, _ in records), name
        assert any((args[0] != phases.LEXICAL).any() for args, _ in records), name
        assert any((result > 0).any() for _, result in records), name


def test_golden_file_stays_small() -> None:
    assert DATA.stat().st_size < 1_000_000


# --- drobné případy -----------------------------------------------------------


def test_mixing_rows_sum_to_one_and_isolated_groups_hear_themselves() -> None:
    # Skupiny 0 a 1 jsou propojené (zdroj → cíl), skupina 2 je osamocená; skupina 3 není v kroku.
    source = np.array([0, 1, 3], dtype=np.intp)
    target = np.array([1, 0, 0], dtype=np.intp)
    strength = np.array([0.5, 0.25, 0.9])
    place = np.array([0, 1, 2, -1], dtype=np.intp)
    mixing = phases.mixing_from_links(source, target, strength, place, np.array([1.0, 2.0, 1.0]),
                                      np.array([0.2, 0.4, 0.3]))
    assert mixing.shape == (3, 3)
    np.testing.assert_allclose(mixing.sum(axis=1), 1.0)
    assert mixing[2].tolist() == [0.0, 0.0, 1.0]  # bez sousedů se otevřenost bere za nulu
    assert mixing[0, 0] == 1.0 - 0.2 and mixing[0, 1] == 0.2
    assert [list(part) for part in phases.components(mixing)] == [[0, 1], [2]]


def test_mix_multiplies_components_separately_and_alone_by_weight() -> None:
    matrix = np.array([[0.75, 0.25], [0.5, 0.5]])
    values = np.arange(12, dtype=np.float64).reshape(2, 3, 2)
    result = phases.mix(values, [np.array([0, 1])], [matrix], np.array([2]), np.array([0.5]))
    np.testing.assert_array_equal(result[:, 2], 0.5 * values[:, 2])
    np.testing.assert_array_equal(result[0, :2], matrix @ values[0, :2])


def test_hear_without_cross_or_channels_is_the_normalized_mix() -> None:
    matrix = np.array([[0.5, 0.5], [0.0, 1.0]])
    current = np.array([[[1.0, 0.0], [0.0, 0.0]]])
    present = np.array([[True, False]])
    heard = phases.hear(current, present, [np.array([0, 1])], [matrix], np.zeros(0, dtype=np.intp),
                        np.zeros(0), [], [])
    # Skupina 1 proměnnou nemá: skupina 0 slyší jen sebe, převážené na celý vstup.
    np.testing.assert_array_equal(heard[0, 0], [1.0, 0.0])
    np.testing.assert_array_equal(heard[0, 1], [0.0, 0.0])


def test_hear_channel_replaces_a_share_of_the_input() -> None:
    current = np.array([[[1.0, 0.0], [0.0, 1.0]]])
    present = np.array([[True, True]])
    eye = np.eye(2)
    heard = phases.hear(current, present, [np.array([0, 1])], [eye], np.zeros(0, dtype=np.intp), np.zeros(0), [],
                        [(np.array([0.5]), np.array([0]), np.array([1]), np.array([0.5]))])
    # Skupina 0 slyší 75 % sebe a 25 % skupiny 1 (podíl = faktor × váha).
    np.testing.assert_array_equal(heard[0, 0], [0.75, 0.25])
    np.testing.assert_array_equal(heard[0, 1], [0.0, 1.0])


def test_settle_keeps_a_single_variant_and_has_no_trend_for_it() -> None:
    current = np.array([[[1.0, 0.0]], [[0.6, 0.4]]])
    previous = current.copy()
    present = np.ones((2, 1), dtype=bool)
    updated, baseline = phases.settle(
        current, previous, present, current.copy(), np.zeros_like(current), np.array([[1, 2], [1, 2]], dtype=np.uint64),
        np.array([7], dtype=np.uint64), np.array([0.0]), np.array([0.5]), np.array([0.0]), 1.0, 0.3, 0.05, 0.9,
    )
    np.testing.assert_array_equal(updated[0, 0], [1.0, 0.0])
    np.testing.assert_array_equal(baseline[0, 0], [1.0, 0.0])
    np.testing.assert_allclose(updated[1, 0], [0.6, 0.4])


# --- pole proti dosavadním skalárním funkcím ----------------------------------------


def _contact_world(params: Parameters):
    regions = (Region("p", (0.0, 0.0), language="a", villages=2, neighbours=("q",)),
               Region("q", (30.0, 0.0), language="b", villages=2, neighbours=("p",)))
    world = region_world(regions, languages=(ProtoLanguage("a"), ProtoLanguage("b")), semantics=True, params=params)
    Simulation(world)  # načte živé proměnné
    return world


@pytest.mark.parametrize("params", [Parameters(), Parameters(channel_domains=NEUTRAL_CHANNEL_DOMAINS,
                                                              borrowability_strength=0.0)])
def test_factor_arrays_equal_the_scalar_functions_bit_for_bit(params: Parameters) -> None:
    world = _contact_world(params)
    variable_ids = sorted(world.variables)
    assert {world.variables[variable_id].kind for variable_id in variable_ids} >= {"lexical", "construction"}
    columns = contact.variable_columns(world, variable_ids)
    for channel in ("neighbor", "elite", "trade", "liturgy", "reading", "school"):
        array = contact.borrowing_factors(world, columns, channel)
        assert [float(value).hex() for value in array] == [
            float(contact.borrowing_factor(world, variable_id, channel)).hex() for variable_id in variable_ids
        ]
    for factors, scalar in ((contact.interference_factors, contact.interference_factor),
                            (institutions.reading_factors, institutions.reading_factor),
                            (institutions.school_factors, institutions.school_factor),
                            (institutions.liturgy_factors, institutions.liturgy_factor)):
        assert [float(value).hex() for value in factors(world, columns)] == [
            float(scalar(world, variable_id)).hex() for variable_id in variable_ids
        ]


# --- přenos po kusech -----------------------------------------------------------------


def test_chunked_transmission_gives_the_same_history(monkeypatch: pytest.MonkeyPatch) -> None:
    def run() -> str:
        world = village_grid(4, 3, seed=5, syntax=True, semantics=True, morphology=True)
        simulation = Simulation(world)
        simulation.run(500)
        return simulation.history.digest()

    whole = run()
    monkeypatch.setattr(transmission_module, "CHUNK_CELLS", 64)
    assert run() == whole

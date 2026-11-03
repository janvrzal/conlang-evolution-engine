"""Tlaky (``Pressure.scores``): zlatá data dávek a výstupů.

Zlatá data (``tests/v2/data/golden_pressures.json.gz``) zaznamenal ``scripts/v2_golden_pressures.py``
ze skutečných běhů v Pythonu: dávky (``PressureBatch``) jako pole a výstup ``scores`` každého
tlaku, bit po bitu včetně ``dtype`` a tvaru. Tlaky čtou kromě dávky i stav světa (tvary, slovní
zásobu, hodnocení procesů a tvarů, konstrukce). Ten se neukládá (snímek má 1 až 3 MB, limit je
1 MB na soubor): vyrobí ho běh scénáře, který je bitově shodný (``tests/v2/golden_worlds.py``).
Test běh zopakuje, v ticích záznamů sestaví dávku ze záznamu (pole) nad světem z běhu, spočte
``scores`` a porovná je se záznamem; tentýž soubor později ověří Rust.

Běhy jsou označené ``slow``; kontrola pokrytí záznamu běh nepotřebuje.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from cee.v2.changes import DEFAULT_CHANGES, pressures_by_kind
from cee.v2.pressures.base import Pressure, PressureBatch
from tests.v2 import golden_worlds as worlds

KINDS = ("lexical", "process", "form", "construction", "prosody")
NAMES = sorted({pressure.name for weighted in pressures_by_kind(DEFAULT_CHANGES).values()
                for pressure, _ in weighted})


def compute(pressure: Pressure, batch: PressureBatch) -> np.ndarray:
    """Výpočet tlaku, který zlatá data ověřují; Rust ho nahradí svou implementací."""
    return np.array(pressure.scores(batch))


@pytest.fixture(scope="module")
def golden() -> dict[str, list[dict[str, Any]]]:
    data = worlds.read_gzip(worlds.DATA / "golden_pressures.json.gz")
    return {name: [worlds.decode(item) for item in scenario["records"]] for name, scenario in data["scenarios"].items()}


def all_records(golden: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [record for records in golden.values() for record in records]


def test_zlata_data_pokryvaji_kazdy_tlak_a_druh_promennych(golden):
    """Každý tlak má aspoň jeden záznam s nenulovým výstupem a každý druh proměnných dávky."""
    assert set(golden) == set(worlds.SCENARIOS)
    records = all_records(golden)
    assert {record["kind"] for record in records} == set(KINDS)
    found = {name for record in records for name, scores in record["scores"].items() if np.any(scores != 0)}
    assert found == set(NAMES)
    # Tlaky konkrétního druhu proměnných se zapisují jen v dávkách tohoto druhu.
    expected = {kind: {pressure.name for pressure, _ in weighted}
                for kind, weighted in pressures_by_kind(DEFAULT_CHANGES).items()}
    for record in records:
        assert set(record["scores"]) == expected[record["kind"]]


def test_davky_jsou_pole_bez_ziveho_sveta(golden):
    """Vstup dávky jsou čísla, řetězce a pole (načte se bez světa); tvary spolu sedí."""
    for record in all_records(golden):
        batch = record["batch"]
        rows, columns, slots = batch["freqs"].shape
        assert batch["freqs"].dtype == batch["heard"].dtype == np.float64 and batch["heard"].shape == (rows, columns, slots)
        assert batch["numbers"].shape == (rows, slots) and len(batch["slots"]) == rows
        assert len(batch["variable_ids"]) == rows and len(batch["group_ids"]) == columns
        for row in range(rows):
            assert len(batch["slots"][row]) == slots
            # Prázdný slot je −1 a None, obsazený číslo ≥ 0 a ID varianty.
            assert [number < 0 for number in batch["numbers"][row]] == [item is None for item in batch["slots"][row]]
        for scores in record["scores"].values():
            assert scores.dtype == np.float64 and scores.shape[0] == rows and scores.shape[2] == slots
            assert scores.shape[1] in (1, columns)


def test_konformita_je_funkce_cetnosti(golden):
    """Význam záznamu: konformita nečte nic než ``freqs``."""
    checked = 0
    for record in all_records(golden):
        if "conformity" in record["scores"]:
            assert worlds.same(record["scores"]["conformity"], 2.0 * record["batch"]["freqs"] - 1.0)
            checked += 1
    assert checked > 100


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(worlds.SCENARIOS))
def test_tlaky_odpovidaji_zlatym_datum(golden, name, monkeypatch):
    # Reference v Pythonu: s Rustem počítá tlaky sám přenos a ``fitness_of`` se nevolá; přes Rust
    # prochází tatáž data ``test_v2_native_pressures``.
    monkeypatch.setenv("CEE_NATIVE", "0")
    expected: dict[int, dict[int, dict[str, Any]]] = {}
    for record in golden[name]:
        expected.setdefault(record["tick"], {})[record["call"]] = record
    simulation, ticks = worlds.new_simulation(name)
    visited: set[tuple[int, int]] = set()
    compute_scores: Callable[[Pressure, PressureBatch], np.ndarray] = compute

    def handle(tick: int, first: int, batches: list[Any]) -> None:
        world = simulation.world
        for offset, (live, outputs) in enumerate(batches):
            record = expected[tick].get(first + offset)
            if record is None:
                continue
            visited.add((tick, first + offset))
            where = f"{name}: tik {tick}, dávka {first + offset}"
            stored_batch = record["batch"]
            assert world.variables[live.variable_ids[0]].kind == record["kind"], where
            # Dávka ze záznamu je výřez dávky z běhu (jinak by se svět z běhu lišil od zaznamenaného).
            rows = [live.variable_ids.index(variable_id) for variable_id in stored_batch["variable_ids"]]
            columns = [live.group_ids.index(group_id) for group_id in stored_batch["group_ids"]]
            assert worlds.same(stored_batch["freqs"], live.freqs[rows][:, columns]), where
            assert worlds.same(stored_batch["heard"], live.heard[rows][:, columns]), where
            assert worlds.same(stored_batch["numbers"], live.slot_numbers()[rows]), where
            assert stored_batch["slots"] == [list(live.slots[row]) for row in rows], where
            batch = worlds.batch_from_record(world, stored_batch)
            assert [pressure.name for pressure, _ in outputs] == list(record["scores"]), where
            for pressure, _ in outputs:
                assert worlds.same(compute_scores(pressure, batch), record["scores"][pressure.name]), (
                    f"{where}, tlak {pressure.name}")
            assert worlds.same(worlds.reads_of(batch), record["reads"]), where

    with worlds.probing_pressures(lambda tick: tick in expected, handle):
        simulation.run(simulation.world.start_year + max(expected) * worlds.DT)
    assert visited == {(tick, call) for tick, calls in expected.items() for call in calls}
    assert ticks >= max(expected)

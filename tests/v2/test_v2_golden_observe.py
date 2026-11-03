"""Pozorování (``cee.v2.observe``): zlatá data.

Zlatá data (``tests/v2/data/golden_observe.json.gz``) zaznamenal ``scripts/v2_golden_observe.py``
(Python reference) ze skutečných běhů: v pár tickách každého scénáře rysy mluvených skupin, kandidáty
sloučení, dialekty a jazyky pro dvě dvojice prahů, otisk matice vzdáleností kódů a editační vzdálenosti
vybraných tvarů (obsah záznamu v ``tests/v2/golden_observe.py``). Stav světa se neukládá (snímek má 1 až
3 MB, limit je 1 MB na soubor): vyrobí ho běh scénáře, který je bitově shodný
(``tests/v2/golden_worlds.py``). Test běh zopakuje, v tickách záznamů spočte totéž Python referencí
a (je-li rozšíření) Rustem a porovná bit po bitu.

Běhy jsou označené ``slow``; kontrola pokrytí záznamu běh nepotřebuje.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from cee.v2 import native
from cee.v2.observe import LineageTracker
from cee.v2.simulation import Simulation
from tests.v2 import golden_observe as observed
from tests.v2 import golden_worlds as worlds


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return worlds.read_gzip(worlds.DATA / "golden_observe.json.gz")["scenarios"]


def test_zlata_data_pokryvaji_scenare_a_netrivialni_shluky(golden):
    assert set(golden) == set(worlds.SCENARIOS)
    dialects = languages = spread = events = distances = 0
    for scenario in golden.values():
        assert scenario["records"]
        for record in scenario["records"]:
            assert record["groups"] and len(record["features"]["squares"]) == len(record["groups"])
            assert len(record["edit"]["distances"]) == len(record["edit"]["forms"]) * (len(record["edit"]["forms"]) - 1) // 2
            spread += record["features"]["spread"]["entries"] > 0
            for run in record["runs"]:
                dialects += len(run["dialects"]) > 1
                languages += len(run["languages"]) > 1
                events += bool(run["events"])
                distances += "distances" in run
    assert dialects > 5 and languages > 3 and spread > 5 and events > 5 and distances > 15


def replayed(name: str, golden: dict[str, Any], use_native: bool) -> None:
    """Běh scénáře: v tickách záznamů porovná výpočet v daném režimu se zlatým záznamem."""
    simulation, ticks = worlds.new_simulation(name)
    expected = {record["tick"]: record for record in golden[name]["records"]}
    assert golden[name]["ticks"] == ticks
    trackers = [LineageTracker() for _ in observed.THRESHOLDS]
    seen = []

    def probe(running: Simulation) -> None:
        if running.tick in expected:
            found = observed.record_tick(running, name, trackers, use_native)
            assert worlds.same(found, expected[running.tick]), (name, running.tick, use_native)
            seen.append(running.tick)

    with worlds.probing_innovation(simulation, probe):
        simulation.run(simulation.world.start_year + ticks * worlds.DT)
    assert seen == sorted(expected)


@pytest.mark.slow
@pytest.mark.parametrize("name", list(worlds.SCENARIOS))
def test_zlata_data_pozorovani_v_pythonu(golden, name):
    replayed(name, golden, False)


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.observe_enabled(),
    reason="rozšíření cee_core není sestavené, je vypnuté, nebo se numpy a knihovny systému s Rustem rozcházejí",
)
@pytest.mark.parametrize("name", list(worlds.SCENARIOS))
def test_zlata_data_pozorovani_v_rustu(golden, name):
    replayed(name, golden, True)

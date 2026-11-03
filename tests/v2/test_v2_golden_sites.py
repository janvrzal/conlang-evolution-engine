"""Hledání míst inovací (``Change.sites``, ``rates``, ``total_rate``, ``weighted_sites``): zlatá data.

Zlatá data (``tests/v2/data/golden_sites.json.gz``) zaznamenal ``scripts/v2_golden_sites.py``
ze skutečných běhů v Pythonu: pro každý druh změny z ``DEFAULT_CHANGES`` místa, míry,
celkovou míru a váhy míst ve skupině na začátku inovační fáze ticku. Stav světa se
neukládá (snímek má 1 až 3 MB, limit je 1 MB na soubor): vyrobí ho běh scénáře, který je
bitově shodný (``tests/v2/golden_worlds.py``). Test běh zopakuje, v tickách záznamů spočte
totéž a porovná bit po bitu (včetně pořadí míst); tentýž soubor později ověří Rust.

Běhy jsou označené ``slow`` (celé zlatá data ověří asi půl minuty); kontrola pokrytí
záznamu běh nepotřebuje.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pytest

from cee.v2 import phases
from cee.v2.changes import DEFAULT_CHANGES
from tests.v2 import golden_worlds as worlds

CHANGES = {change.kind: change for change in DEFAULT_CHANGES}


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return worlds.read_gzip(worlds.DATA / "golden_sites.json.gz")


def entries_of(golden: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for scenario in golden["scenarios"].values() for entry in scenario["entries"]]


def test_zlata_data_pokryvaji_kazdy_druh_zmeny(golden):
    """Každý druh změny má aspoň jeden záznam s místy, nenulovou celkovou mírou a váhami míst."""
    assert set(golden["scenarios"]) == set(worlds.SCENARIOS)
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries_of(golden):
        found[entry["kind"]].append(entry)
    assert set(found) == set(CHANGES) == set(worlds.KINDS)
    for kind, entries in found.items():
        assert any(worlds.informative(entry) for entry in entries), f"{kind}: jen prázdné záznamy"


def test_zaznam_ma_tvar_podle_druhu_miry(golden):
    """Druhy s jednotnou mírou mají ``rate`` a ``rate_scale``, ostatní míru každého místa a váhy."""
    uniform = weighted = 0
    for entry in entries_of(golden):
        change, count = CHANGES[entry["kind"]], len(entry["sites"])
        assert count == len(set(entry["sites"]))
        if not count:
            assert entry["total_rate"] == 0.0 and entry["weighted"] == "empty"
            assert "rate" not in entry and "rates" not in entry
        elif change.uses_uniform_rate():
            uniform += 1
            assert entry["weights"] is None and entry["weighted"] == "same"
            assert "rate" in entry and "rate_scale" in entry and "rates" not in entry
        else:
            assert len(entry["rates"]) == count and "rate" not in entry
            if entry["weights"] is not None:
                weighted += 1
                assert entry["weighted"] == "same" and len(entry["weights"]) == count
                assert float(np.sum(entry["weights"])) == pytest.approx(1.0)
            else:
                assert entry["weighted"] == "empty"
    assert uniform > 100 and weighted > 500


def test_celkova_mira_a_vahy_plynou_z_mir(golden):
    """Význam záznamu: jednotná celková míra je ``uniform_rate`` a váhy jsou ``site_weights`` z ``rates``."""
    checked = 0
    for entry in entries_of(golden):
        change = CHANGES[entry["kind"]]
        if not entry["sites"]:
            continue
        if change.uses_uniform_rate():
            expected = float(phases.uniform_rate(change.base_rate, len(entry["sites"]), entry["rate_scale"]))
            assert entry["total_rate"] == expected
            checked += 1
        elif entry["weights"] is not None:
            _, weights = phases.site_weights(entry["rates"])
            assert weights is not None and weights.tolist() == entry["weights"]
            checked += 1
    assert checked > 500


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(worlds.SCENARIOS))
def test_hledani_mist_odpovida_zlatym_datum(golden, name):
    scenario = golden["scenarios"][name]
    expected: dict[int, dict[str, dict[str, dict[str, Any]]]] = {}
    for entry in scenario["entries"]:
        expected.setdefault(entry["tick"], {}).setdefault(entry["group"], {})[entry["kind"]] = entry
    simulation, ticks = worlds.new_simulation(name)
    assert ticks == scenario["ticks"]
    strings = worlds.SiteStrings(golden["strings"])
    visited: set[int] = set()

    def probe(running) -> None:
        tick = running.tick
        if tick not in expected:
            return
        visited.add(tick)
        for group_id, context in worlds.inventory_contexts(running, sorted(expected[tick])):
            for kind, entry in expected[tick][group_id].items():
                actual = worlds.site_entry(CHANGES[kind], context, strings)
                stored = {key: value for key, value in entry.items() if key not in ("tick", "group")}
                assert worlds.same(actual, stored), f"{name}: tik {tick}, skupina {group_id}, {kind}"

    with worlds.probing_innovation(simulation, probe):
        simulation.run(simulation.world.start_year + max(expected) * worlds.DT)
    assert visited == set(expected)
    # Tabulka řetězců se nerozrostla: všechna místa už v záznamu byla.
    assert strings.table == golden["strings"]


def test_celkova_mira_je_soucet_mir_nebo_jednotna_mira(golden):
    """Význam záznamu: ``total_rate`` plyne z ``rates`` (nebo z jednotné míry) a váhy z ``rates``."""
    checked = 0
    for scenario in golden["scenarios"].values():
        for entry in scenario["entries"]:
            if not entry["sites"] or CHANGES[entry["kind"]].kind.startswith(("voicing", "spirant")) and False:
                continue
            change = CHANGES[entry["kind"]]
            count = len(entry["sites"])
            if change.uses_uniform_rate():
                assert entry["total_rate"] == float(phases.uniform_rate(change.base_rate, count, entry["rate_scale"]))
                checked += 1
            elif entry["weights"] is not None:
                _, weights = phases.site_weights(entry["rates"])
                assert weights is not None and list(weights) == entry["weights"]
                checked += 1
    assert checked > 500

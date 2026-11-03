"""Stav fonologie kódu v Rustu (B6c): četnosti užití, kopie a uložení mezi režimy.

Fronty, dominantní kořeny a paměť četností užití žijí v ``cee_core.NativeCode``. Běhy s Rustem
a bez něj porovnává ``test_v2_native_phonology.py`` (otisky a celý stav); tady jsou věci, které
se v těch bězích nevidí: četnosti užití proti výpočtu od nuly a uložení stavu v jednom režimu
s obnovou ve druhém.
"""

from __future__ import annotations

import copy
import os
import pickle

import pytest

from cee.v2 import native
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from cee.v2.world import _UsageMemo

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.available(),
    reason="rozšíření cee_core není sestavené (nebo je vypnuté CEE_NATIVE=0)",
)


def _world(years: float):
    world = village_grid(4, seed=2, morphology=True, semantics=True)
    Simulation(world).run(years)
    return world


@needs_native
def test_cetnosti_uziti_z_rustu_sedi_s_vypoctem_od_nuly():
    world = _world(700.0)
    checked = 0
    for group in world.groups.values():
        code = group.main_code
        assert code.phonology.core is not None
        units = sorted(code.phonology.vocabulary)
        memo = _UsageMemo((0, 0), 0)
        reference = [world._usage_compute(code, world.morphemes[unit], memo) for unit in units]
        assert world.usage_frequencies(code, units) == reference
        assert [world.usage_frequency(code, unit) for unit in units] == reference
        checked += len(units)
    assert checked > 100


@needs_native
def test_cetnosti_uziti_sledují_zmenu_cetnosti_pojmu_a_dominantnich_korenu():
    world = _world(300.0)
    code = next(iter(world.groups.values())).main_code
    state = code.phonology
    concept, root = next(iter(state.dominant.items()))
    before = world.usage_frequency(code, root)
    world.concept_frequencies[concept] = 0.05
    memo = _UsageMemo((0, 0), 0)
    assert world.usage_frequency(code, root) == world._usage_compute(code, world.morphemes[root], memo)
    assert world.usage_frequency(code, root) != before or before == 0.05
    state.set_dominant(concept, None)
    state.lexicon_version += 1  # jako ``Simulation._follow_vocabulary``: keš pojmů kořene podle verze slovníku
    memo = _UsageMemo((0, 0), 0)
    assert world.usage_frequency(code, root) == world._usage_compute(code, world.morphemes[root], memo)


def _queues(world):
    return [group.main_code.phonology.processes_snapshot() for _, group in sorted(world.groups.items())]


@needs_native
def test_stav_ulozeny_s_rustem_se_obnovi_bez_nej_i_zpet(monkeypatch):
    world = _world(700.0)
    expected = _queues(world)
    assert any(item["live"] and item["queue"] for found in expected for item in found)
    blob = pickle.dumps(world)
    assert _queues(copy.deepcopy(world)) == expected
    with monkeypatch.context() as patch:
        patch.setattr(native, "enabled", lambda: False)
        python = pickle.loads(blob)
        assert all(group.main_code.phonology.core is None for group in python.groups.values())
        assert _queues(python) == expected
        again = pickle.dumps(python)
    restored = pickle.loads(again)
    assert all(group.main_code.phonology.core is not None for group in restored.groups.values())
    assert _queues(restored) == expected

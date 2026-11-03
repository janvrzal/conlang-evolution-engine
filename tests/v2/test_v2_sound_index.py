"""Číselný index prostředí a opor zvukových změn: Rust proti Pythonu, přírůstkově proti od nuly (B5)."""

from __future__ import annotations

import copy
import pickle

import numpy as np
import pytest

from cee.v2 import native
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.sound import CATALOG, FAMILY_INDEX, SOUND_CHANGES, sound_index
from cee.v2.language.index import ContextIndex
from cee.v2.language.sound_index import NativeSoundIndex, SoundIndex
from cee.v2.phonology import enter_vocabulary, leave_vocabulary
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation

needs_rust = pytest.mark.skipif(not (native.enabled() and native.sums_match()), reason="rozšíření cee_core není k dispozici")


def _contexts(index, world, code):
    columns = index.context_counts(code, world)
    return sorted(zip(*(column.tolist() for column in columns)))


def _assert_same(left, right, world, codes) -> None:
    """Dva indexy dávají nad týmiž kódy bit po bitu totéž (součty měr, místa, míry, opory, prostředí)."""
    families = len(SOUND_CHANGES)
    assert left.totals(codes, families).tobytes() == right.totals(codes, families).tobytes()
    for code in codes:
        assert left.inventory(code) == right.inventory(code)
        assert left.has_families(code) == right.has_families(code)
        assert _contexts(left, world, code) == _contexts(right, world, code)
        if not left.has_families(code):
            continue
        assert left.supports(code).tolist() == right.supports(code).tolist()
        for family in range(families):
            sites_l, rates_l, total_l = left.family(code, family)
            sites_r, rates_r, total_r = right.family(code, family)
            assert sites_l.tolist() == sites_r.tolist()
            assert rates_l.tobytes() == rates_r.tobytes()
            assert float(total_l).hex() == float(total_r).hex()


def _fresh(world, codes, kind):
    index = kind()
    index.sync(world, codes, CATALOG, force=True)
    return index


@needs_rust
def test_rust_a_python_davaji_totez_po_kazdem_kroku_i_od_nuly() -> None:
    world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
    sim = Simulation(world)
    codes = [world.groups[group].main_code for group in world.group_ids()]
    assert isinstance(sound_index(world), NativeSoundIndex)
    reference = SoundIndex()
    for _ in sim.iterate(500):
        live = sound_index(sim.world)
        live.sync(sim.world, codes, CATALOG)
        reference.sync(sim.world, codes, CATALOG)
        _assert_same(live, reference, sim.world, codes)
        # Přírůstkově = od nuly (v Rustu i v Pythonu).
        _assert_same(live, _fresh(sim.world, codes, SoundIndex), sim.world, codes)
    fresh_native = NativeSoundIndex(native.new_sound_index(CATALOG.scales), CATALOG.scales)
    fresh_native.sync(sim.world, codes, CATALOG)
    _assert_same(live, fresh_native, sim.world, codes)


@needs_rust
def test_slovnik_a_inventar_se_meni_stejne_v_rustu_i_v_pythonu() -> None:
    world = village_grid(2, seed=5, phonology=True)
    Simulation(world)  # naplní slovní zásobu
    group = next(iter(world.groups.values()))
    code = group.main_code
    live, reference = sound_index(world), SoundIndex()
    state = code.phonology

    def compare() -> None:
        live.sync(world, [code], CATALOG)
        reference.sync(world, [code], CATALOG, force=True)
        _assert_same(live, reference, world, [code])

    compare()
    sample = min(state.vocabulary)
    leave_vocabulary(code, sample)
    compare()
    enter_vocabulary(world, code, sample)
    compare()
    before = live.inventory(code)
    for word in sorted(state.vocabulary)[:20]:
        state.vocabulary.remove(word)
        compare()
    occurrences = reference.slots[code.forms.token].occurrences
    rarest = min((s for s, count in occurrences.items() if count > 0), key=lambda s: (occurrences[s], s))
    for unit in list(state.vocabulary):
        if rarest in world.form_of(code, unit):
            state.vocabulary.remove(unit)
    compare()
    assert rarest not in live.inventory(code) and len(live.inventory(code)) < len(before)
    for unit in sorted(state.vocabulary):
        state.vocabulary.remove(unit)
    compare()  # prázdná slovní zásoba: žádný inventář, žádné rodiny
    assert live.inventory(code) == () and not live.has_families(code)


@needs_rust
def test_kopie_a_pickle_zachovaji_stav_indexu_v_rustu() -> None:
    world = village_grid(3, 2, seed=7, syntax=True, semantics=True)
    sim = Simulation(world)
    sim.run(150)
    codes = [world.groups[group].main_code for group in world.group_ids()]
    live = sound_index(world)
    live.sync(world, codes, CATALOG)
    for restored in (copy.deepcopy(world), pickle.loads(pickle.dumps(world))):
        again = [restored.groups[group].main_code for group in restored.group_ids()]
        assert isinstance(restored.sound, NativeSoundIndex) and restored.sound is not live
        restored.sound.sync(restored, again, CATALOG)
        _assert_same(live, restored.sound, restored, codes)


@needs_rust
def test_facade_prostredi_pro_kontakt_dava_inventar() -> None:
    world = village_grid(2, seed=5, phonology=True)
    Simulation(world)
    code = next(iter(world.groups.values())).main_code
    facade = ContextIndex()
    facade.sync(world, code)
    assert facade.inventory() == sound_index(world).inventory(code) != ()


def test_modul_sound_changes_ma_zname_poradi_rodin() -> None:
    assert [change.kind for change in SOUND_CHANGES] == sorted(FAMILY_INDEX, key=FAMILY_INDEX.get)
    assert len(CATALOG.scales) == len(SOUND_CHANGES)
    assert np.all(np.array(CATALOG.scales) > 0)


def test_davka_dava_totez_co_total_rate_po_jednom() -> None:
    world = village_grid(3, seed=2, phonology=True)
    sim = Simulation(world)
    sim.run(200)
    contexts = [
        InnovationContext(world, group, group.main_code, sim.tick, sim.year) for group in world.groups.values()
    ]
    for change in SOUND_CHANGES:
        assert change.total_rates(contexts) == [change.total_rate(context) for context in contexts]

"""Číselné tvary, slovní zásoba a izolace kopií."""

import numpy as np
import pytest

from cee.v2.language.bank import FormBank
from cee.v2.language.lexicon import FormStore, Morpheme, UnitForm
from cee.v2.language.registry import IdRegistry
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_navazani_a_vetveni_zachova_samostatne_zapisy():
    world = village_grid(1, seed=2, phonology=True)
    registry, exponents, bank = IdRegistry(), IdRegistry(), FormBank(world.table)
    store = FormStore()
    first = UnitForm((1, 2), 1, "ending")
    store.set("z", first)
    store.bind(registry, bank, exponents)
    assert store.get("z") == first and store.log == ["z"]
    assert store.form_ids[registry.index_of("z")] == bank.id_of(first.form)
    assert store.boundaries[registry.index_of("z")] == 1
    assert exponents.id_of(int(store.exponent_ids[registry.index_of("z")])) == "ending"
    store.bind(registry, bank, exponents)
    with pytest.raises(ValueError):
        store.bind(IdRegistry(), bank, exponents)
    branch = store.branch()
    branch.set("z", UnitForm((2, 3), None, None))
    store.set("z", UnitForm((3, 4), None, None))
    assert branch.get("z").form == (2, 3)
    assert store.get("z").form == (3, 4)
    assert not np.shares_memory(branch.form_ids, store.form_ids)
    assert branch.log == ["z"] and store.log == ["z", "z"]


def test_hromadne_tvary_default_dynamicke_slovo_a_slovnik():
    world = village_grid(1, seed=2, phonology=True)
    code = next(iter(world.groups.values())).main_code
    existing = next(iter(world.morphemes))
    world.morphemes["new"] = Morpheme("new", "new", (1, 2))
    words = ["new", existing, "new"]
    ids = world.form_ids(code, words)
    assert [world.form_bank().forms[index] for index in ids] == [world.form_of(code, w) for w in words]
    code.forms.set("new", UnitForm((2, 3), None, None))
    assert world.form_bank().forms[world.form_ids(code, ["new"])[0]] == (2, 3)
    code.phonology.vocabulary.update(words)
    code.phonology.lexicon_version += 1
    snapshot = world.vocabulary_ids(code)
    assert [world.morpheme_registry.id_of(int(i)) for i in snapshot] == sorted(set(words))
    code.phonology.vocabulary.discard("new")
    code.phonology.lexicon_version += 1
    assert len(world.vocabulary_ids(code)) == 1


def test_checkpoint_kopiruje_registr_a_pole_ale_sdili_banku():
    world = village_grid(1, seed=2, phonology=True)
    code = next(iter(world.groups.values())).main_code
    word = next(iter(world.morphemes))
    code.forms.set(word, UnitForm((1, 2), None, None))
    world.form_ids(code, [word])
    simulation = Simulation(world)
    resumed = Simulation.resume(simulation.checkpoint())
    other = resumed.world
    other_code = next(iter(other.groups.values())).main_code
    assert other.bank is world.bank
    assert other.morpheme_registry is not world.morpheme_registry
    assert not np.shares_memory(code.forms.form_ids, other_code.forms.form_ids)
    other_code.forms.set(word, UnitForm((2, 3), None, None))
    assert code.forms.get(word).form == (1, 2)
    assert other.form_ids(other_code, [word])[0] != world.form_ids(code, [word])[0]


def test_pozdni_navazani_vrstvy_a_sourozenci():
    world = village_grid(1, seed=2, phonology=True)
    bank = FormBank(world.table)
    registry, exponents = IdRegistry(), IdRegistry()
    root = FormStore()
    root.set("a", UnitForm((1, 2), 1, "one"))
    left = root.branch()
    left.set("b", UnitForm((1, 2), None, "two"))
    sibling = left.branch()
    left.bind(registry, bank, exponents)
    sibling.bind(registry, bank, exponents)
    left.set("c", UnitForm((2, 3), None, None))
    sibling.set("d", UnitForm((3, 4), None, None))
    assert sibling.get("a") == root.get("a")
    assert sibling.get("b").boundary is None
    assert sibling.form_id(registry.index_of("a")) == sibling.form_id(registry.index_of("b"))
    assert sibling.get("a").exponent != sibling.get("b").exponent
    assert sibling.form_id(registry.index_of("c")) == -1
    with pytest.raises(IndexError):
        sibling.form_id(-1)
    assert not sibling._base.form_ids.flags.writeable
    assert not sibling._base._base.form_ids.flags.writeable
    frozen_child = sibling.freeze().branch()
    assert not sibling.form_ids.flags.writeable
    frozen_child.set("a", UnitForm((4, 5), None, None))
    assert sibling.get("a").form == (1, 2)

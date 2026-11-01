"""Číselné registry entit (krok A2): pořadí vzniku, přibývání, izolace kopií."""

import copy

from cee.v2.registry import RegisteredDict, Registry
from cee.v2.repertoire import Variable
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_cisla_se_prideluji_v_poradi_vzniku_a_nemeni_se():
    registry = Registry()
    numbering = registry.morphemes
    assert [numbering.intern(name) for name in ("b", "a", "b", "c")] == [0, 1, 0, 2]
    assert numbering.names == ["b", "a", "c"]
    assert numbering.get("zzz") == -1 and "a" in numbering
    # Pořadí řetězců není pořadí čísel: ranks() je odvozené z řetězců.
    assert numbering.ranks().tolist() == [1, 0, 2]
    numbering.intern("0")
    assert numbering.ranks().tolist() == [2, 1, 3, 0]


def test_slovnik_sveta_zapisuje_klice_do_registru_a_odebrani_cislo_nebere():
    registry = Registry()
    items = RegisteredDict(registry, "group", {"x": 1})
    items["y"] = 2
    items.setdefault("z", 3)
    items.update({"w": 4})
    assert registry.groups.names == ["x", "y", "z", "w"]
    del items["y"]
    assert registry.groups.get("y") == 1 and list(items) == ["x", "z", "w"]
    lexical = RegisteredDict(registry, "variable")
    lexical["v"] = Variable("lexical", "water")
    lexical["u"] = Variable("process", "p")
    assert registry.concepts.names == ["water"]


def test_svet_cisluje_entity_pri_vzniku_a_kopie_ma_vlastni_registr():
    world = village_grid(3, seed=2, syntax=True, semantics=True)
    registry = world.registry
    assert registry.morphemes.names == list(world.morphemes)
    assert registry.variables.names == list(world.variables)
    assert registry.variants.names == list(world.variants)
    assert registry.groups.names == list(world.groups)
    assert set(registry.concepts.names) >= {v.key for v in world.variables.values() if v.kind == "lexical"}
    simulation = Simulation(world)
    simulation.run(200)
    checkpoint = simulation.checkpoint()
    copied = checkpoint.state[0]
    assert copied.registry is not world.registry
    assert copied.morphemes._registry is copied.registry
    before = len(copied.registry.morphemes)
    simulation.run(400)
    # Pokračování původního běhu kopii nezměnilo a naopak.
    assert len(copied.registry.morphemes) == before
    assert copied.registry.morphemes.names == list(copied.morphemes)
    resumed = Simulation.resume(checkpoint)
    resumed.run(400)
    assert resumed.world.registry.morphemes.names == list(resumed.world.morphemes)
    assert resumed.world.registry.morphemes.names == world.registry.morphemes.names
    branch = copy.deepcopy(world)
    branch.registry.morphemes.intern("jen-ve-vetvi")
    assert "jen-ve-vetvi" not in world.registry.morphemes

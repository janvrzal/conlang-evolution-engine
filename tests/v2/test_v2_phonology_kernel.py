"""Shoda dávkové fonologizace s referencí včetně interakcí procesů."""

import copy

import pytest

from cee.v2 import phonology
from cee.v2.history import History
from cee.v2.language.processes import Process
from cee.v2.language.segments import default_table
from cee.v2.repertoire import Distribution, Origin
from cee.v2.simulation import Simulation
from cee.v2.world import Code, SpeechGroup, Territory, World


def _world(second_target):
    table = default_table()
    world = World(seed=5)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(["a", "b", "c"], {"a": "pata", "b": "kata", "c": "paka"})
    code = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())])).main_code
    code.phonology.vocabulary.update(world.morphemes)
    for source, target in (("t", "d"), (second_target, "s")):
        process = Process(source, table.segments([source]), "replace", segment=table.id_of(target))
        variable, _ = phonology.register(world, process, Origin(source, 0, 0.0, "v"))
        code.repertoire.set(variable, Distribution.fixed(phonology.changed_id(variable)))
        phonology.activate(world, code, variable)
    return world


def _compare(left, right, histories):
    a, b = left.groups["v"].main_code, right.groups["v"].main_code
    for word in left.morphemes:
        assert left.unit_of(a, word) == right.unit_of(b, word)
    for name in ("pending", "queued", "restructured", "closed", "order", "version", "fixed_since"):
        assert getattr(a.phonology, name) == getattr(b.phonology, name)
    assert a.forms.log == b.forms.log
    assert histories[0].digest() == histories[1].digest()


@pytest.mark.parametrize("second_target", ["d", "t"])
def test_davka_sedi_s_referenci_pri_feeding_a_bleeding(second_target):
    world = _world(second_target)
    code = world.groups["v"].main_code
    first = next(iter(code.phonology.pending))
    words = sorted(code.phonology.vocabulary)
    # Stejný práh i pořadí ID; poslední je přesně na hranici a nesmí projít.
    level = phonology._logit(1.0)
    code.phonology.pending[first] = [(0.0, words[0]), (0.0, words[1]), (level, words[2])]
    code.phonology.queued[first] = set(words)
    reference = copy.deepcopy(world)
    histories = History(), History()
    for tick in (1, 2, 3):
        phonology.restructure(world, "v", tick, 25.0, histories[0], tick * 25.0)
        phonology._restructure_reference(reference, "v", tick, 25.0, histories[1], tick * 25.0)
        _compare(world, reference, histories)


def test_duplicitni_fronta_pouzije_referenci_a_checkpoint_zustane_izolovany():
    world = _world("d")
    code = world.groups["v"].main_code
    variable = next(iter(code.phonology.pending))
    entry = code.phonology.pending[variable][0]
    code.phonology.pending[variable].insert(0, entry)
    reference = copy.deepcopy(world)
    histories = History(), History()
    point = Simulation(world).checkpoint()
    phonology.restructure(world, "v", 1, 25.0, histories[0], 25.0)
    phonology._restructure_reference(reference, "v", 1, 25.0, histories[1], 25.0)
    _compare(world, reference, histories)
    restored = Simulation.resume(point).world
    assert restored.groups["v"].main_code.phonology.pending[variable].count(entry) == 2

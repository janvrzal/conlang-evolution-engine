"""Průběžná slabost buněk a sdílení členství s analogií."""

from dataclasses import replace

from cee.v2 import syntax
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.morphology import Extension, Leveling
from cee.v2.history import History
from cee.v2.language.constructions import Construction
from cee.v2.language.lexicon import UnitForm
from cee.v2.repertoire import Distribution, Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def _check(world, group):
    code = world.groups[group].main_code
    context = InnovationContext(world, world.groups[group], code, 1, 25.0)
    for change in (Leveling(), Extension()):
        assert change._sites(context) == change.candidates(context)
    for function in ("OBJ", "PAST", "ORDER", "missing"):
        assert syntax.weakness(world, code, function) == syntax._weakness_reference(world, code, function)


def test_sdileni_a_poradi_konzumentu_zmeny_a_checkpoint():
    world = village_grid(1, seed=3, syntax=True, semantics=True)
    Simulation(world)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    _check(world, group)
    words = sorted(unit for unit in code.phonology.vocabulary if world.morphemes[unit].kind == "word")
    for target in (words[0], world.morphemes[words[1]].lexeme_id):
        unit = world.unit_of(code, target)
        code.forms.set(target, UnitForm(unit.form[::-1], unit.boundary, unit.exponent))
        code.phonology.version += 1
        syntax.weakness(world, code, "OBJ")
        _check(world, group)
    code.phonology.vocabulary.remove(words[0])
    code.phonology.leave_vocabulary(words[1])
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    _check(world, group)
    code.phonology.enter_vocabulary(words[0])
    code.phonology.enter_vocabulary(words[1])
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    _check(world, group)
    restored = Simulation.resume(Simulation(world).checkpoint()).world
    _check(restored, group)
    code.forms = code.forms.branch()
    code.phonology.version += 1
    _check(world, group)


def test_pridani_synteticke_bunky_a_shoda():
    world = village_grid(1, seed=3, syntax=True, semantics=True)
    Simulation(world)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    _check(world, group)
    entry = syntax.catalog()["PAST"]
    paradigm = world.paradigms[entry.word_class]
    world.paradigms[entry.word_class] = replace(
        paradigm, cells=tuple(cell for cell in paradigm.cells if cell != entry.cell),
        weights=tuple(weight for cell, weight in zip(paradigm.cells, paradigm.weights) if cell != entry.cell),
    )
    for unit in list(code.phonology.vocabulary):
        if world.morphemes[unit].cell == entry.cell and world.morphemes[unit].word_class == entry.word_class:
            code.phonology.leave_vocabulary(unit)
    code.phonology.version += 1
    code.phonology.lexicon_version += 1
    _check(world, group)
    affix = syntax.new_affix(world, code, Construction("PAST", "periphrastic", "finish", "clitic"), group, 5)
    variable, variant = syntax.register(world, Construction("PAST", "synthetic", "finish", exponent=affix),
                                        Origin("test", 0, 0.0, group))
    code.repertoire.set(variable, Distribution.fixed(variant.id))
    syntax.restructure(world, group, 5, History(), 125.0)
    assert entry.cell in world.paradigms[entry.word_class].cells
    _check(world, group)

"""Průběžní kandidáti analogie proti úplnému výpočtu."""

from cee.v2.changes.base import InnovationContext
from cee.v2.changes.morphology import Extension, Leveling
from cee.v2.language.lexicon import UnitForm
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def _context():
    world = village_grid(1, seed=9, phonology=True, morphology=True)
    group = next(iter(world.groups.values()))
    group.main_code.phonology.vocabulary.update(world.morphemes)
    return InnovationContext(world, group, group.main_code, 0, 0.0)


def _check(context):
    for change in (Leveling(), Extension()):
        assert change._sites(context) == change.candidates(context)
        assert list(change.sites(context)) == sorted(change.candidates(context))


def test_zmeny_bunek_korene_a_clenstvi_proti_referenci():
    context = _context()
    world, code = context.world, context.code
    units = sorted(unit for unit in code.phonology.vocabulary if world.morphemes[unit].kind == "word")
    assert len(units) > 2
    _check(context)
    for unit in units[:4]:
        value = world.unit_of(code, unit)
        code.forms.set(unit, UnitForm(value.form[::-1], value.boundary, value.exponent))
        code.phonology.version += 1
        _check(context)
    root = world.morphemes[units[0]].lexeme_id
    value = world.unit_of(code, root)
    code.forms.set(root, UnitForm(value.form[::-1], value.boundary, value.exponent))
    code.phonology.version += 1
    _check(context)
    unit = units[0]
    for enter in (False, True):
        (code.phonology.enter_vocabulary if enter else code.phonology.leave_vocabulary)(unit)
        code.phonology.version += 1
        code.phonology.lexicon_version += 1
        _check(context)
    code.forms = code.forms.branch()
    code.phonology.version += 1
    _check(context)
    restored = Simulation.resume(Simulation(world).checkpoint()).world
    group = next(iter(restored.groups.values()))
    _check(InnovationContext(restored, group, group.main_code, 0, 0.0))


def test_jedina_bunka_neprepocita_nezavisle_jednotky(monkeypatch):
    context = _context()
    world, code = context.world, context.code
    change = Leveling()
    change._sites(context)
    unit = next(unit for unit in sorted(code.phonology.vocabulary) if world.morphemes[unit].kind == "word")
    value = world.unit_of(code, unit)
    calls = []
    original = Leveling._candidate

    def recorded(self, ctx, target):
        calls.append(target)
        return original(self, ctx, target)

    monkeypatch.setattr(Leveling, "_candidate", recorded)
    code.forms.set(unit, UnitForm(value.form, 0, value.exponent))
    code.phonology.version += 1
    change._sites(context)
    assert calls == [unit]


def test_zmena_produktivni_koncovky_a_prazdne_podoby():
    context = _context()
    world, code = context.world, context.code
    grouped = {}
    for unit in sorted(code.phonology.vocabulary):
        item = world.morphemes[unit]
        if item.kind == "word":
            grouped.setdefault((item.word_class, item.cell), []).append(unit)
    units = next(group for group in grouped.values() if len(group) >= 3)
    _check(context)
    for i, unit in enumerate(units):
        value = world.unit_of(code, unit)
        exponent = "test-a" if i < len(units) // 2 else "test-b"
        boundary = len(value.form) if i % 2 == 0 else max(0, len(value.form) - 1)
        code.forms.set(unit, UnitForm(value.form, boundary, exponent))
        code.phonology.version += 1
        _check(context)
    for unit in units:
        value = world.unit_of(code, unit)
        code.forms.set(unit, UnitForm(value.form, len(value.form), value.exponent))
        code.phonology.version += 1
    _check(context)


def test_smiseny_zapis_deniku_a_prima_mutace_slovni_zasoby():
    context = _context()
    code, world = context.code, context.world
    words = sorted(unit for unit in code.phonology.vocabulary if world.morphemes[unit].kind == "word")
    assert len(words) >= 3
    _check(context)
    removed, entered, logged = words[:3]
    code.phonology.vocabulary.remove(removed)
    code.phonology.vocabulary.remove(entered)
    code.phonology.leave_vocabulary(logged)
    code.phonology.enter_vocabulary(entered)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    _check(context)

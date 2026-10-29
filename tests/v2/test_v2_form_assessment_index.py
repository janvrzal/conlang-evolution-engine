"""Přírůstková morfologická hodnocení a jejich závislosti."""

import cee.v2.morphology as morphology
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.morphology import FormChange
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def _setup():
    world = village_grid(1, seed=9, phonology=True, morphology=True, semantics=True)
    group_id = next(iter(world.groups))
    code = world.groups[group_id].main_code
    code.phonology.vocabulary.update(world.morphemes)
    words = sorted(unit for unit in code.phonology.vocabulary if world.morphemes[unit].kind == "word")
    return world, group_id, code, words


def test_zmeny_bunky_korene_koncovky_a_checkpoint():
    world, group, code, words = _setup()
    unit = words[0]
    value = world.unit_of(code, unit)
    variables = [morphology.register(world, change, Origin("test", 0, 0.0, group))[0] for change in (
        FormChange("level", unit), FormChange("extend", unit, value.exponent),
        FormChange("drop_initial", unit, segment=value.form[0]),
    )]

    def check():
        for variable in variables:
            assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)

    check()
    for target in (unit, world.morphemes[unit].lexeme_id, words[1]):
        current = world.unit_of(code, target)
        code.forms.set(target, UnitForm(current.form[::-1], current.boundary, current.exponent))
        code.phonology.version += 1
        check()
    point = Simulation(world).checkpoint()
    restored = Simulation.resume(point).world
    for variable in variables:
        assert morphology.assess(restored, group, variable) == morphology._assess_reference(restored, group, variable)


def test_nezavisly_tvar_nerusi_cache_a_none_je_cacheovan(monkeypatch):
    world, group, code, words = _setup()
    unit = words[0]
    change = FormChange("drop_initial", unit, segment=-99)
    variable, _ = morphology.register(world, change, Origin("test", 0, 0.0, group))
    assert morphology.assess(world, group, variable) is None
    original = morphology._assess_reference
    calls = []

    def counted(*args):
        calls.append(args[-1])
        return original(*args)

    monkeypatch.setattr(morphology, "_assess_reference", counted)
    unrelated = next(word for word in words if world.morphemes[word].lexeme_id != world.morphemes[unit].lexeme_id)
    current = world.unit_of(code, unrelated)
    code.forms.set(unrelated, UnitForm(current.form[::-1], current.boundary, current.exponent))
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) is None
    assert not calls
    current = world.unit_of(code, unit)
    code.forms.set(unit, UnitForm(current.form[::-1], current.boundary, current.exponent))
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) is None
    assert calls == [variable]


def test_frekvence_polysemie_a_prechod_none_na_hodnotu():
    world, group, code, words = _setup()
    unit = words[0]
    root = world.morphemes[unit].lexeme_id
    current = world.unit_of(code, unit)
    variable, _ = morphology.register(world, FormChange("drop_initial", unit, segment=current.form[0]),
                                      Origin("test", 0, 0.0, group))
    code.forms.set(unit, UnitForm((current.form[0],), None, None))
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) is None
    code.forms.set(unit, current)
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)
    assert morphology.assess(world, group, variable) is not None
    concept = next(iter(world.concept_frequencies))
    code.phonology.set_dominant(concept, root)
    code.phonology.adjust_uses(root, 1)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)
    world.concept_frequencies[concept] = 0.99
    code.phonology.version += 1
    assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)


def test_zmena_poctu_a_podoby_koncovky_dorovna_cached_zmenu():
    world, group, code, words = _setup()
    unit = words[0]
    item = world.morphemes[unit]
    peers = [word for word in words if (world.morphemes[word].word_class, world.morphemes[word].cell)
             == (item.word_class, item.cell)]
    assert len(peers) >= 2
    variable, _ = morphology.register(world, FormChange("extend", unit, "novy"), Origin("test", 0, 0, group))
    assert morphology.assess(world, group, variable) is None
    for i, word in enumerate(peers):
        current = world.unit_of(code, word)
        boundary = len(current.form) if i % 2 == 0 else len(current.form) - 1
        code.forms.set(word, UnitForm(current.form, boundary, "novy"))
        code.phonology.version += 1
        assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)


def test_prime_i_zaznamenane_zmeny_dominance_obnovi_dotcene_frekvence():
    world, group, code, words = _setup()
    roots = list(dict.fromkeys(world.morphemes[word].lexeme_id for word in words))
    assert len(roots) >= 3
    selected = [next(word for word in words if world.morphemes[word].lexeme_id == root) for root in roots[:3]]
    variables = []
    for unit in selected:
        form = world.unit_of(code, unit).form
        variable, _ = morphology.register(world, FormChange("prepend", unit, segment=form[0]),
                                          Origin("test", 0, 0.0, group))
        variables.append(variable)
    concepts = list(world.concept_frequencies)[:3]
    for concept, root in zip(concepts, roots):
        code.phonology.set_dominant(concept, root)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    for variable in variables:
        morphology.assess(world, group, variable)
    code.phonology.dominant[concepts[0]] = roots[1]
    code.phonology.dominant[concepts[1]] = roots[2]
    code.phonology.set_dominant(concepts[2], roots[0])
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    for variable in variables:
        assert morphology.assess(world, group, variable) == morphology._assess_reference(world, group, variable)

"""Přírůstkové hodnocení se musí shodovat s výpočtem od začátku."""

from cee.v2.assessment import _assess_batch, _assess_batch_reference
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.processes import Process
from cee.v2.phonology import register
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_prubezne_hodnoceni_shodne_po_zmenach_a_checkpointu():
    world = village_grid(2, seed=7, phonology=True, semantics=True)
    table = world.table
    process = Process("test", table.segments(["t"]), "replace", segment=table.id_of("d"))
    variable, _ = register(world, process, Origin("test", 0, 0.0, "v"))
    groups = sorted(world.groups)
    for step in range(5):
        for group_id in groups:
            code = world.groups[group_id].main_code
            words = sorted(code.phonology.vocabulary or world.morphemes)
            code.phonology.vocabulary.update(words)
            word = words[step % len(words)]
            current = world.unit_of(code, word)
            code.forms.set(word, UnitForm(current.form[::-1], current.boundary, current.exponent))
            code.phonology.version += 1
        assert _assess_batch(world, groups, variable) == _assess_batch_reference(world, groups, variable)
    resumed = Simulation.resume(Simulation(world).checkpoint()).world
    assert _assess_batch(resumed, groups, variable) == _assess_batch_reference(resumed, groups, variable)


def test_zmenene_pozice_a_frekvence_nemeni_vyber_vzorku():
    from cee.v2.assessment import _vocabulary
    from cee.v2.language.assessment_index import AssessmentVocabularyIndex

    world = village_grid(1, seed=4, phonology=True, semantics=True)
    code = next(iter(world.groups.values())).main_code
    code.phonology.vocabulary.update(world.morphemes)
    initial = _vocabulary(world, next(iter(world.groups)))
    words = initial.morphemes.copy()
    index = code.phonology.cache["assessment-vocabulary-index"][1]
    assert isinstance(index, AssessmentVocabularyIndex)
    word = words[0]
    original = world.unit_of(code, word)
    code.forms.set(word, UnitForm(original.form[::-1], original.boundary, original.exponent))
    code.phonology.version += 1
    updated = _vocabulary(world, next(iter(world.groups)))
    assert updated.morphemes == words
    assert len(index.changes) <= 1
    concept = next(iter(world.concept_frequencies), None)
    if concept is not None:
        world.concept_frequencies[concept] = 0.99
        assert _vocabulary(world, next(iter(world.groups))).morphemes == words


def test_ruzne_sirky_lexikon_a_frekvence():
    import struct

    from cee.v2.assessment import _vocabulary, _vocabulary_reference

    world = village_grid(3, seed=12, phonology=True, morphology=True, semantics=True)
    groups = sorted(world.groups)
    table = world.table
    variable, _ = register(
        world, Process("x", table.segments(["t"]), "replace", segment=table.id_of("d")),
        Origin("x", 0, 0.0, "v"),
    )
    for n, group_id in enumerate(groups):
        code = world.groups[group_id].main_code
        words = sorted(world.morphemes)[: 4 + n * 3]
        code.phonology.vocabulary.update(words)
        code.phonology.lexicon_version += 1
        code.phonology.version += 1
    for tick in range(4):
        code = world.groups[groups[tick % len(groups)]].main_code
        word = sorted(code.phonology.vocabulary)[tick % len(code.phonology.vocabulary)]
        unit = world.unit_of(code, word)
        code.forms.set(word, UnitForm(unit.form[::-1], unit.boundary, unit.exponent))
        code.phonology.version += 1
        actual = _assess_batch(world, groups, variable)
        expected = _assess_batch_reference(world, groups, variable)
        assert [struct.pack("5d", *vars(item).values()) for item in actual] == [
            struct.pack("5d", *vars(item).values()) for item in expected
        ]
        for group_id in groups:
            current, reference = _vocabulary(world, group_id), _vocabulary_reference(world, group_id)
            assert current.morphemes == reference.morphemes
            assert current.frequency == reference.frequency
            assert current.forms == reference.forms
    concept = next(iter(world.concept_frequencies), None)
    if concept is not None:
        world.concept_frequencies[concept] = 0.83
        group_id = groups[0]
        world.groups[group_id].main_code.phonology.version += 1
        assert _vocabulary(world, group_id).frequency == _vocabulary_reference(world, group_id).frequency


def test_stale_ticks_zachovava_okamzik_prepocitani(monkeypatch):
    import cee.v2.assessment as assessment

    world = village_grid(1, seed=11, phonology=True)
    group_id = next(iter(world.groups))
    code = world.groups[group_id].main_code
    code.phonology.vocabulary.update(world.morphemes)
    variable, _ = register(
        world, Process("x", world.table.segments(["t"]), "replace", segment=world.table.id_of("d")),
        Origin("x", 0, 0.0, "v"),
    )
    calls = []
    original = assessment._assess_batch

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(assessment, "_assess_batch", counted)
    assessment.assess_many(world, [group_id], variable, 0)
    code.phonology.version += 1
    assessment.assess_many(world, [group_id], variable, assessment.STALE_TICKS - 1)
    assert len(calls) == 1
    assessment.assess_many(world, [group_id], variable, assessment.STALE_TICKS)
    assert len(calls) == 2


def test_zmena_dominance_a_gramatiky_shoda():
    world = village_grid(1, seed=8, phonology=True, morphology=True, semantics=True, syntax=True)
    group_id = next(iter(world.groups))
    code = world.groups[group_id].main_code
    code.phonology.vocabulary.update(world.morphemes)
    table = world.table
    variable, _ = register(
        world, Process("x", table.segments(["t"]), "replace", segment=table.id_of("d")),
        Origin("x", 0, 0.0, "v"),
    )
    words = sorted(code.phonology.vocabulary)
    code.phonology.set_dominant("test-concept", words[0])
    code.phonology.adjust_uses(words[0], 1)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    assert _assess_batch(world, [group_id], variable) == _assess_batch_reference(world, [group_id], variable)
    code.phonology.set_dominant("test-concept", words[1])
    code.phonology.adjust_uses(words[0], -1)
    code.phonology.adjust_uses(words[1], 1)
    code.phonology.record_grammar("test-grammar")
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    assert _assess_batch(world, [group_id], variable) == _assess_batch_reference(world, [group_id], variable)


def test_puvodni_vzorek_po_zmene_frekvence_a_vetveni():
    from cee.v2.assessment import _vocabulary, _vocabulary_reference

    world = village_grid(1, seed=4, phonology=True, semantics=True)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    code.phonology.vocabulary.update(world.morphemes)
    code.phonology.lexicon_version += 1
    chosen = _vocabulary(world, group).morphemes.copy()
    for concept in world.concept_frequencies:
        world.concept_frequencies[concept] = 1.0 - world.concept_frequencies[concept]
    code.forms = code.forms.branch()
    code.phonology.version += 1
    assert _vocabulary(world, group).morphemes == chosen
    assert _vocabulary_reference(world, group).morphemes == chosen


def test_skutecna_syntakticka_kompenzace_homofonu():
    from cee.v2 import syntax
    from cee.v2.language.constructions import Construction
    from cee.v2.repertoire import Distribution

    world = village_grid(1, seed=8, phonology=True, morphology=True, semantics=True, syntax=True)
    Simulation(world)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    code.phonology.vocabulary.update(world.morphemes)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    table = world.table
    process = Process("drop-m", table.segments(["m"]), "delete", right=table.BOUNDARY)
    variable, _ = register(world, process, Origin("drop-m", 0, 0.0, group))
    assert not syntax.compensated(world, group, "OBJ")
    before = _assess_batch(world, [group], variable)[0]
    assert before == _assess_batch_reference(world, [group], variable)[0]
    order_id, variant = syntax.register(world, Construction("ORDER", "fixed", order="SVO"),
                                        Origin("order", 0, 0.0, group))
    code.repertoire.set(order_id, Distribution.fixed(variant.id))
    code.phonology.record_grammar(order_id)
    assert syntax.compensated(world, group, "OBJ")
    after = _assess_batch(world, [group], variable)[0]
    assert after == _assess_batch_reference(world, [group], variable)[0]
    assert before.merge_mass > 0 and after.merge_mass < before.merge_mass


def test_frekvence_se_projevi_az_pri_zmene_verze_i_u_noveho_procesu():
    from cee.v2.assessment import _vocabulary, _vocabulary_reference

    world = village_grid(1, seed=8, phonology=True, semantics=True)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    code.phonology.vocabulary.update(world.morphemes)
    for concept, root in zip(sorted(world.concept_frequencies), sorted(world.morphemes)):
        code.phonology.set_dominant(concept, root)
    code.phonology.lexicon_version += 1
    code.phonology.version += 1
    cached = _vocabulary(world, group)
    _vocabulary_reference(world, group)
    old_weights = cached.weights.copy()
    for concept in world.concept_frequencies:
        world.concept_frequencies[concept] = 0.99
    variable, _ = register(
        world, Process("new", world.table.segments(["t"]), "delete"), Origin("x", 0, 0.0, group)
    )
    assert (_vocabulary(world, group).weights == old_weights).all()
    assert _assess_batch(world, [group], variable) == _assess_batch_reference(world, [group], variable)
    code.phonology.version += 1
    updated = _vocabulary(world, group)
    reference = _vocabulary_reference(world, group)
    assert updated.frequency == reference.frequency
    assert (updated.weights == reference.weights).all()
    assert (updated.weights != old_weights).any()
    assert _assess_batch(world, [group], variable) == _assess_batch_reference(world, [group], variable)


def test_zmena_tvaru_cte_jen_dotcene_slovo(monkeypatch):
    from cee.v2.assessment import _vocabulary
    from cee.v2.world import World

    world = village_grid(1, seed=4, phonology=True, semantics=True)
    group = next(iter(world.groups))
    code = world.groups[group].main_code
    code.phonology.vocabulary.update(world.morphemes)
    code.phonology.lexicon_version += 1
    sample = _vocabulary(world, group)
    word = sample.morphemes[0]
    old = world.unit_of(code, word)
    replacement = old.form + (old.form[0],)
    code.forms.set(word, UnitForm(replacement, old.boundary, old.exponent))
    code.phonology.version += 1
    calls = []
    original = World.form_of

    def recorded(self, code_arg, morpheme_id):
        calls.append(morpheme_id)
        return original(self, code_arg, morpheme_id)

    monkeypatch.setattr(World, "form_of", recorded)
    updated = _vocabulary(world, group)
    assert calls == [word]
    assert updated.forms[word] == replacement

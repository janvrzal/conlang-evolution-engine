"""Konstrukce, gramatikalizace a syntaktické tlaky enginu v2 (milník M4)."""

import numpy as np

from cee.v2 import morphology, syntax
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import Conversion
from cee.v2.changes.syntax import Affixation, Cliticization, NegationReduction, Periphrasis
from cee.v2.history import History
from cee.v2.language.constructions import Construction
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.morphology import FormChange
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.syntactic import Ambiguity
from cee.v2.repertoire import Distribution, Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def _world():
    world = village_grid(1, seed=3, syntax=True, semantics=True)
    Simulation(world)  # naplní slovní zásobu a dominantní kořeny
    group = world.groups[world.group_ids()[0]]
    return world, group, group.main_code


def _context(world, group):
    return InnovationContext(world, group, group.main_code, 1, 25.0)


def _set(world, code, construction):
    variable, variant = syntax.register(world, construction, Origin("test", 0, 0.0, None))
    code.repertoire.set(variable, Distribution.fixed(variant.id))
    return variant


def test_stejna_konstrukce_je_tataz_varianta_a_pocita_slova():
    world, _, _ = _world()
    first = syntax.register(world, Construction("PAST", "periphrastic", "have", "free"), Origin("a", 1, 0, "x"))
    second = syntax.register(world, Construction("PAST", "periphrastic", "have", "free"), Origin("b", 9, 0, "y"))
    assert first[1] is second[1]
    assert Construction("NEG", "embraced", "not", reinforcer="step").words == 2
    assert Construction("PAST", "periphrastic", "have", "clitic").words == 0


def test_gramatikalizace_jde_jednim_smerem():
    world, group, code = _world()
    context = _context(world, group)
    rng = np.random.default_rng(0)
    assert not Periphrasis().sites(context)  # vedle neporušené koncovky opis nevzniká
    for unit in sorted(code.phonology.vocabulary):
        if world.morphemes[unit].cell == "PAST":
            citation = morphology.citation_form(world, code, unit)
            code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
    code.phonology.version += 1
    assert Periphrasis().sites(context) == ["construction:PAST"]  # zeslabená koncovka → opis
    free = Periphrasis().next(context, Construction("PAST", "synthetic"), rng)
    assert free.kind == "periphrastic" and free.stage == "free"
    clitic = Cliticization().next(context, free, rng)
    assert clitic.stage == "clitic"
    assert not Cliticization().applies(context, clitic)  # zpět k volnému slovu nic nevede
    synthetic = Affixation().next(context, clitic, rng)
    assert synthetic.kind == "synthetic" and synthetic.exponent is not None
    affix = world.morphemes[synthetic.exponent].form
    assert len(affix) <= 2 and any(world.table.is_vowel(segment) for segment in affix)
    reduced = NegationReduction().next(context, Construction("NEG", "embraced", "not", reinforcer="step"), rng)
    assert reduced == Construction("NEG", "post", "step")


def test_nova_koncovka_se_zapise_a_caste_sloveso_si_drzi_stary_tvar():
    world, group, code = _world()
    affix = syntax.new_affix(world, code, Construction("PAST", "periphrastic", "finish", "clitic"), group.id, 5)
    variant = _set(world, code, Construction("PAST", "synthetic", "finish", exponent=affix))
    verbs = [unit for unit in sorted(code.phonology.vocabulary) if world.morphemes[unit].cell == "PAST"]
    frequent = [unit for unit in verbs if world.usage_frequency(code, world.morphemes[unit].lexeme_id) >= 0.7]
    before = {unit: world.unit_of(code, unit) for unit in verbs}
    history = History()
    syntax.restructure(world, group.id, 5, history, 125.0)
    event = history.of_kind("grammaticalized")[0]
    assert event["words"] + event["kept"] == len(verbs)
    rare = [unit for unit in verbs if unit not in frequent]
    assert all(world.unit_of(code, unit).exponent == affix for unit in rare)
    assert all(world.unit_of(code, unit) == before[unit] for unit in frequent)
    assert variant.id in code.phonology.grammar_applied


def test_volny_slovosled_bez_padu_je_nevyhodny():
    world, group, code = _world()
    for unit in sorted(code.phonology.vocabulary):
        if world.morphemes[unit].cell == "OBJ":
            citation = morphology.citation_form(world, code, unit)
            code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
    code.phonology.version += 1
    assert syntax.weakness(world, code, "OBJ") == 1.0
    free = syntax.register(world, Construction("ORDER", "free"), Origin(None, 0, 0, None))[1]
    fixed = syntax.register(world, Construction("ORDER", "fixed", order="SVO"), Origin("t", 0, 0, None))[1]
    batch = PressureBatch(world=world, variable_ids=["construction:ORDER"], group_ids=[group.id],
                          freqs=np.array([[[0.5, 0.5]]]), slots=[[free.id, fixed.id]], tick=0,
                          heard=np.array([[[0.5, 0.5]]]))
    scores = Ambiguity().scores(batch)[0, 0]
    assert scores[0] == -1.0 and scores[1] == 0.0


def test_reanalyza_hranice_presune_hlasku_ve_vsech_tvarech_lexemu():
    world, group, code = _world()
    root = next(m for m in world.morphemes.values() if m.word_class == "verb" and m.kind == "root")
    units = morphology.units_of(world, code, root.id)
    before = [world.form_of(code, unit) for unit in units]
    segment = world.table.id_of("n")
    variable, _ = morphology.register(world, FormChange("prepend", root.id, segment=segment), Origin("t", 0, 0, None))
    code.repertoire.set(variable, Distribution.fixed(changed_id(variable)))
    morphology.activate(world, code, variable)
    morphology.restructure(world, group.id, 1, History(), 25.0)
    after = [world.form_of(code, unit) for unit in units]
    assert all(new == (segment, *old) for old, new in zip(before, after))


def test_konverze_da_slovu_tridu_ciloveho_pojmu():
    world, group, code = _world()
    change = Conversion()
    context = _context(world, group)
    sites = change.sites(context)
    assert sites
    site = sites[0]
    variant = change.propose(context, site, np.random.default_rng(0), 0)
    morpheme = world.morphemes[variant.payload["morpheme"]]
    source = world.morphemes[code.phonology.dominant[variant.payload["from"][0]]]
    assert morpheme.word_class == world.concept_classes[site.split(":", 1)[1]] != source.word_class
    assert morpheme.form == world.form_of(code, source.id)

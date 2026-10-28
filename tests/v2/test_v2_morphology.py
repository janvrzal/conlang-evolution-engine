"""Paradigmata, morfologizace a analogie enginu v2 (milník M3)."""

import numpy as np
import pytest

from cee.v2 import morphology, phonology
from cee.v2.history import History
from cee.v2.language.morphology import FormChange, Paradigm
from cee.v2.language.processes import Process
from cee.v2.language.segments import default_table
from cee.v2.morphology import assess, units_of
from cee.v2.repertoire import Distribution, Origin
from cee.v2.scenarios import PROTO_ENDINGS
from cee.v2.world import Code, SpeechGroup, Territory, World


@pytest.fixture(scope="module")
def table():
    return default_table()


def _village(words, endings, frequencies=None):
    world = World(seed=3)
    world.paradigms["noun"] = Paradigm("noun", ("SG", "PL"), (1.0, 0.4))
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(list(words), dict(words), frequencies,
                              {concept: "noun" for concept in words}, endings)
    group = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())]))
    code = group.main_code
    for morpheme in list(world.morphemes.values()):
        if morpheme.kind == "root":
            code.phonology.vocabulary.update(units_of(world, code, morpheme.id))
    return world, code


def _impose(world, code, process, share=1.0):
    variable, _ = phonology.register(world, process, Origin(process.family, 0, 0.0, "v"))
    code.repertoire.set(variable, Distribution.fixed(phonology.changed_id(variable)))
    phonology.activate(world, code, variable)
    return variable


def _forms(world, code, concept):
    root = next(m for m in world.morphemes.values() if m.meaning == concept and m.kind == "root")
    return [world.table.render(world.form_of(code, unit)) for unit in units_of(world, code, root.id)]


def test_protojazyk_dostane_tvary_bunek_s_hranici_a_koncovkou(table):
    world, code = _village({"dog": "kat", "cat": "mus"}, {("noun", "PL"): (("i", 1.0),)})
    assert _forms(world, code, "dog") == ["kat", "kati"]
    plural = world.unit_of(code, units_of(world, code, next(
        m.id for m in world.morphemes.values() if m.meaning == "dog" and m.kind == "root"))[1])
    assert plural.boundary == 3 and table.render(plural.ending) == "i"


def test_koncovky_se_rozdeli_podle_vah():
    concepts = [f"c{index}" for index in range(400)]
    words = {concept: "pata" for concept in concepts}
    world, _ = _village(words, PROTO_ENDINGS)
    endings = [world.morphemes[m.exponent].form for m in world.morphemes.values() if m.kind == "word"]
    share = sum(len(form) == 1 for form in endings) / len(endings)
    assert 0.58 < share < 0.72  # -i u 65 %, -an u 35 %


def test_morfologizace_vznikne_z_podminene_zmeny_a_pozdejsi_ztraty_podminky(table):
    """Typ přehlásky: plurál nakonec nese jen alternace kmene.

    Slova se sklonem proti některé změně zůstanou reliktní výjimkou, proto
    se ověřuje většina z deseti lexémů, ne každý.
    """
    words = {f"c{index}": f"{onset}at" for index, onset in enumerate("kmlsnpbdrw")}
    world, code = _village(words, {("noun", "PL"): (("i", 1.0),)})
    palatal = Process(
        family="palatalization", target=table.segments(["t"]), operation="change",
        changes=table.features_of("t͡s", ["cor", "ant", "distr", "hi", "lo", "back", "delrel", "strid", "lab"]),
        right=table.pattern({"hi": "+", "back": "-"}),
    )
    apocope = Process(family="apocope", target=table.VOWEL, operation="delete",
                      left=table.CONSONANT, right=table.BOUNDARY, stress="unstressed")
    for tick, process in enumerate((palatal, apocope), start=1):
        _impose(world, code, process)
        phonology.restructure(world, "v", tick, 25.0, History(), 25.0 * tick)
    morphologized = 0
    for concept, onset in zip(words, "kmlsnpbdrw"):
        singular, plural = _forms(world, code, concept)
        root = next(m.id for m in world.morphemes.values() if m.meaning == concept and m.kind == "root")
        ending = world.unit_of(code, units_of(world, code, root)[1]).ending
        if (singular, plural) == (f"{onset}at", f"{onset}at͡s") and ending == ():
            morphologized += 1  # koncovka zanikla, kontrast nese kmen
    assert morphologized >= 8


def test_vyrovnani_ktere_by_slilo_plural_se_singularem_je_nevyhodne(table):
    world, code = _village({"dog": "kat"}, {("noun", "PL"): (("i", 1.0),)})
    root = next(m.id for m in world.morphemes.values() if m.kind == "root")
    plural = units_of(world, code, root)[1]
    from cee.v2.language.lexicon import UnitForm

    code.forms.set(plural, UnitForm(table.parse("kat͡s"), 4, world.unit_of(code, plural).exponent))
    variable, _ = morphology.register(world, FormChange("level", plural), Origin("leveling", 0, 0.0, "v"))
    result = assess(world, "v", variable)
    assert result is not None and result.syncretic_after and not result.syncretic_before


def test_nove_slovo_dostane_produktivni_koncovku_a_rozsireni_obnovi_rozdil(table):
    world, code = _village(
        {"a": "pata", "b": "mesu", "c": "lomi", "d": "kur"},
        {("noun", "PL"): (("an", 1.0),)},
    )
    root = next(m for m in world.morphemes.values() if m.meaning == "d" and m.kind == "root")
    plural = units_of(world, code, root.id)[1]
    from cee.v2.language.lexicon import Morpheme, UnitForm

    # Koncovka u slova „d“ zvukovými změnami zanikla: plurál splynul se singulárem.
    code.forms.set(plural, UnitForm(table.parse("kur"), 3, world.unit_of(code, plural).exponent))
    code.phonology.version += 1
    stats = morphology.class_stats(world, code)
    exponent = stats.productive("noun", "PL")
    variable, _ = morphology.register(world, FormChange("extend", plural, exponent), Origin("extension", 0, 0.0, "v"))
    result = assess(world, "v", variable)
    assert result is not None and result.syncretic_before and not result.syncretic_after

    coined = Morpheme("new", "e", table.parse("sapo"), word_class="noun")
    world.morphemes[coined.id] = coined
    assert _forms(world, code, "e") == ["sapo", "sapoan"]


def test_casta_slova_odolavaji_analogii(table):
    """Vyrovnání stejné alternace: u častého slova nevýhoda, u vzácného výhoda."""
    from cee.v2.language.lexicon import UnitForm
    from cee.v2.pressures.base import PressureBatch
    from cee.v2.pressures.morphological import Conservation

    world, code = _village({"a": "pata", "b": "mesu"}, {("noun", "PL"): (("an", 1.0),)},
                           frequencies={"a": 0.9, "b": 0.05})
    scores = {}
    for concept, alternant in (("a", "pota"), ("b", "mosu")):
        root = next(m.id for m in world.morphemes.values() if m.meaning == concept and m.kind == "root")
        plural = units_of(world, code, root)[1]
        exponent = world.unit_of(code, plural).exponent
        code.forms.set(plural, UnitForm(table.parse(alternant + "an"), 4, exponent))
        code.phonology.version += 1
        variable, variant = morphology.register(world, FormChange("level", plural), Origin("leveling", 0, 0.0, "v"))
        slots = sorted([variant.id, phonology.none_id(variable)])
        batch = PressureBatch(
            world=world, variable_ids=[variable], group_ids=["v"], freqs=np.array([[[0.5, 0.5]]]),
            slots=[slots], tick=0, heard=np.array([[[0.5, 0.5]]]),
        )
        scores[concept] = float(Conservation().scores(batch)[0, 0, slots.index(variant.id)])
    assert scores["a"] < 0 < scores["b"]

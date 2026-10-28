"""Hlásky, procesy a fonologizace enginu v2 (milník M2)."""

import pytest

from cee.v2 import phonology
from cee.v2.assessment import _assess, _dispersion_gain
from cee.v2.history import History
from cee.v2.language.lexicon import Morpheme
from cee.v2.language.processes import Process
from cee.v2.language.segments import default_table
from cee.v2.repertoire import Distribution, Origin
from cee.v2.world import Code, SpeechGroup, Territory, World


@pytest.fixture(scope="module")
def table():
    return default_table()


def _voicing(table, symbol="t", reductive=False):
    return Process(
        family="voicing", target=table.segments([symbol]), operation="change",
        changes=(("voi", "+"),), left=table.VOWEL, right=table.VOWEL, reductive=reductive,
    )


def test_zmena_rysu_vede_vzdy_na_skutecnou_hlasku(table):
    def changed(symbol, *changes):
        return table.ipa[table.changed(table.id_of(symbol), tuple(changes))]

    assert changed("o", ("hi", "+")) == "u"  # ne velarizované oˠ
    assert changed("p", ("voi", "+")) == "b"
    assert changed("d", ("cont", "+"), ("strid", "-")) == "ð"
    assert changed("k", *table.features_of("t͡ʃ", ["cor", "ant", "distr", "hi", "back", "delrel", "strid"])) == "t͡ʃ"


def test_proces_se_aplikuje_dvoufazove_a_jen_v_prostredi(table):
    process = _voicing(table)
    assert table.render(process.apply(table.parse("tatata"), table, "penult")) == "tadada"
    assert process.apply(table.parse("tap"), table, "penult") is None


def test_slovo_nesmi_zaniknout_ani_ztratit_posledni_vokal(table):
    apocope = Process(family="apocope", target=table.VOWEL, operation="delete",
                      left=table.CONSONANT, right=table.BOUNDARY, stress="unstressed")
    assert table.render(apocope.apply(table.parse("pataka"), table, "penult")) == "patak"
    assert apocope.apply(table.parse("pa"), table, "penult") is None


def test_synkopa_nezasahuje_prvni_ani_posledni_slabiku(table):
    syncope = Process(family="syncope", target=table.VOWEL, operation="delete",
                      left=table.CONSONANT, right=table.CONSONANT, stress="unstressed", medial=True)
    # Přízvuk na předposlední: nepřízvučné vnitřní a zmizí, první ani poslední ne.
    assert table.render(syncope.apply(table.parse("pakatapa"), table, "penult")) == "paktapa"
    assert syncope.apply(table.parse("pakata"), table, "final") is not None
    assert syncope.apply(table.parse("paka"), table, "final") is None


def test_vlozeni_nezdvoji_stejnou_hlasku(table):
    diphthong = Process(family="diphthongization", target=table.segments(["e"]),
                        operation="insert_before", segment=table.id_of("j"))
    assert table.render(diphthong.apply(table.parse("pe"), table, "penult")) == "pje"
    assert diphthong.apply(table.parse("pje"), table, "penult") is None


def _one_village(words, frequencies=None, seed=5):
    world = World(seed=seed)
    world.add_territory(Territory("world", "world"))
    world.add_territory(Territory("v", "settlement", parent="world"))
    base = world.seed_lexicon(list(words), dict(words), frequencies)
    group = world.add_group(SpeechGroup("v", "v", 500, [Code("main", base.branch())]))
    group.main_code.phonology.vocabulary.update(
        morpheme.id for morpheme in world.morphemes.values()
    )
    return world, group


def _set_share(world, variable_id, share):
    changed, none = phonology.changed_id(variable_id), phonology.none_id(variable_id)
    if share >= 1.0:
        distribution = Distribution.fixed(changed)
    else:
        import numpy as np

        distribution = Distribution(tuple(sorted((changed, none))),
                                    np.array([share, 1 - share] if changed < none else [1 - share, share]))
    world.groups["v"].main_code.repertoire.set(variable_id, distribution)


def test_stejna_zmena_ve_dvou_skupinach_je_tataz_promenna(table):
    world, _ = _one_village({"water": "pata"})
    first, variant = phonology.register(world, _voicing(table), Origin("voicing", 1, 25.0, "a"))
    second, again = phonology.register(world, _voicing(table), Origin("voicing", 9, 225.0, "b"))
    assert first == second and variant is again
    assert world.stored("v", first).variants == (phonology.none_id(first),)


def test_fonologizace_je_pravidelna_s_malo_vyjimkami_a_pak_se_uzavre(table):
    words = {f"c{index}": syllables for index, syllables in enumerate(
        a + "t" + b for a in ("pa", "ma", "la", "sa", "ka", "na", "ra", "wa", "ja", "ba")
        for b in ("a", "o", "u", "e", "i", "ar", "ol", "um", "en", "is")
    )}
    world, group = _one_village(words)
    code = group.main_code
    variable, _ = phonology.register(world, _voicing(table), Origin("voicing", 0, 0.0, "v"))
    history = History()
    _set_share(world, variable, 1.0)
    phonology.activate(world, code, variable)
    for tick in range(1, 4):
        phonology.restructure(world, "v", tick, 25.0, history, tick * 25.0)

    closed = history.of_kind("process_closed")
    assert len(closed) == 1
    relics = closed[0]["relics"]
    assert closed[0]["restructured"] > 80
    assert 0 < relics < 10
    rendered = {table.render(world.form_of(code, morpheme.id)) for morpheme in world.morphemes.values()}
    assert "pada" in rendered or any(form.startswith("pad") for form in rendered)

    # Po uzavření nové slovo změnou už neprojde.
    late = Morpheme("late", "late", table.parse("kata"))
    world.morphemes[late.id] = late
    phonology.enter_vocabulary(world, code, late.id)
    assert table.render(phonology.surface(world, "v", late.id)) == "kata"


def test_casta_slova_vedou_v_redukcni_zmene(table):
    words = {f"c{index}": f"{'pmlskn'[index % 6]}at{'aoueiə'[index // 6 % 6]}" for index in range(36)}
    frequencies = {concept: (0.95 if index % 2 else 0.05) for index, concept in enumerate(words)}
    world, group = _one_village(words, frequencies)
    variable, _ = phonology.register(world, _voicing(table, reductive=True), Origin("voicing", 0, 0.0, "v"))
    _set_share(world, variable, 0.35)
    phonology.activate(world, group.main_code, variable)
    phonology.restructure(world, "v", 1, 25.0, History(), 25.0)
    rewritten = group.main_code.phonology.restructured.get(variable, set())
    frequencies_of = [world.morphemes[morpheme].frequency for morpheme in rewritten]
    assert rewritten
    assert sum(frequency > 0.5 for frequency in frequencies_of) > len(frequencies_of) / 2


def test_drivejsi_zmena_pripravi_pudu_pozdejsi(table):
    world, group = _one_village({"water": "pata", "fire": "kaso"})
    code = group.main_code
    voicing, _ = phonology.register(world, _voicing(table), Origin("voicing", 0, 0.0, "v"))
    spirant = Process(family="spirantization", target=table.segments(["d"]), operation="change",
                      changes=(("cont", "+"), ("strid", "-")), left=table.VOWEL, right=table.VOWEL)
    spirant_id, _ = phonology.register(world, spirant, Origin("spirantization", 0, 0.0, "v"))
    for variable in (voicing, spirant_id):
        _set_share(world, variable, 1.0)
        phonology.activate(world, code, variable)
    phonology.restructure(world, "v", 1, 25.0, History(), 25.0)
    phonology.restructure(world, "v", 2, 25.0, History(), 50.0)
    water = next(m for m in world.morphemes.values() if m.meaning == "water")
    assert table.render(world.form_of(code, water.id)) == "paða"


def test_retezovy_posun_uvolnene_misto_zvyhodni_souseda(table):
    """Tažný řetěz: e → i je drahé splynutí, dokud i existuje.

    Jakmile i odejde (zde se změnilo na ai), stejný posun e → i už žádné
    slovo neslije a jeho cena zmizí. Posun souseda do uvolněného místa tak
    vznikne sám, bez zvláštního pravidla pro řetězové posuny.
    """
    e_to_i = Process(family="vowel_shift", target=table.segments(["e"]), operation="replace",
                     segment=table.id_of("i"))
    vowels = {table.id_of(symbol) for symbol in "ieaou"}
    # Splynutí s existujícím vokálem není zisk disperze; nese ho funkční zátěž.
    assert _dispersion_gain(e_to_i, vowels, vowels - {table.id_of("e")}, table) == 0.0

    def merge_mass(words):
        world, _ = _one_village(words)
        variable, _ = phonology.register(world, e_to_i, Origin("vowel_shift", 0, 0.0, "v"))
        return _assess(world, "v", variable).merge_mass

    occupied = merge_mass({"a": "pe", "b": "pi", "c": "me", "d": "mi", "e": "ta"})
    vacated = merge_mass({"a": "pe", "b": "pai", "c": "me", "d": "mai", "e": "ta"})
    assert occupied > 0
    assert vacated == 0

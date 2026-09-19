"""Minimální derivační kontrakty pro historicky pojmenovaná schémata.

Každý kontrakt obsahuje pozitivní i negativní sondu: schéma nesmí jen
"něco" měnit, ale musí zasáhnout právě v historicky deklarovaném prostředí.
"""

from cee.engine.inventory import InventoryView
from cee.engine.schemas import SCHEMA_REGISTRY


def _rule(mapper, schema_id, phones):
    inventory = InventoryView(mapper, phones)
    rule = SCHEMA_REGISTRY[schema_id].generate_rule(inventory, year=100)
    assert rule is not None
    return rule


def test_asimilace_znelosti_kopiruje_sousedni_obstruentu_ne_vokal(mapper):
    rule = _rule(mapper, "assimilation", {"a", "t", "d", "k", "ɡ"})

    before_voiced = mapper.parse_word("x", "atd")
    before_voiceless = mapper.parse_word("x", "adk")
    before_vowel = mapper.parse_word("x", "ata")
    assert rule.apply_to_word(before_voiced)
    assert mapper.render_word(before_voiced) == "add"
    assert rule.apply_to_word(before_voiceless)
    assert mapper.render_word(before_voiceless) == "atk"
    assert not rule.apply_to_word(before_vowel)
    assert mapper.render_word(before_vowel) == "ata"


def test_monoftongizace_maze_jen_klouzavy_druhy_clen_diftongu(mapper):
    rule = _rule(mapper, "monophthongization", {"a", "i", "j", "w", "p"})

    diphthong = mapper.parse_word("x", "paj")
    plain_high_vowel = mapper.parse_word("x", "pi")
    assert rule.apply_to_word(diphthong)
    assert mapper.render_word(diphthong) == "pa"
    assert not rule.apply_to_word(plain_high_vowel)
    assert mapper.render_word(plain_high_vowel) == "pi"


def test_kompenzacni_dlouzeni_ve_stejne_udalosti_maze_kodu(mapper):
    rule = _rule(mapper, "compensatory_lengthening", {"a", "s", "t"})

    coda = mapper.parse_word("x", "ast")
    onset = mapper.parse_word("x", "asa")
    assert rule.apply_to_word(coda)
    assert mapper.render_word(coda) == "aːt"
    assert not rule.apply_to_word(onset)
    assert mapper.render_word(onset) == "asa"


def test_proteze_resi_jen_pocatecni_shluk(mapper):
    rule = _rule(mapper, "prothesis", {"a", "s", "t", "p"})

    cluster = mapper.parse_word("x", "sta")
    simple_onset = mapper.parse_word("x", "ta")
    assert rule.apply_to_word(cluster)
    assert mapper.render_word(cluster) == "asta"
    assert not rule.apply_to_word(simple_onset)
    assert mapper.render_word(simple_onset) == "ta"


def test_palatalizace_vytvori_novy_fonem_i_kdyz_predtim_chybi(mapper):
    inventory = InventoryView(mapper, {"a", "i", "t"})
    rule = _rule(mapper, "palatalization", {"a", "i", "t"})
    assert "t͡ʃ" not in inventory

    word = mapper.parse_word("x", "ati")
    assert rule.apply_to_word(word)
    assert mapper.render_word(word) == "at͡ʃi"
    assert all(mapper.is_exact_segment(segment) for segment in word.segments)
    assert "t͡ʃ" in inventory.apply(rule)

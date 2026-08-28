"""
Lexikální retence — metrika (A) z CEE_master.md 5.1.

Klíčové je, že měří jinou osu než fonetická vzdálenost: drastická zvuková
změna může mít stoprocentní retenci.
"""
import pytest

from cee.core.models import Lexicon, Word
from cee.metrics.retention import LexicalRetention, RetentionResult


def _slovo(concept_id, source_id=None):
    return Word(concept_id=concept_id, segments=[], source_id=source_id)


DIAGNOSTIKA = ["voda", "vlk", "strom", "kámen"]


def test_domaci_slova_drzi_retenci():
    lex = Lexicon(words=[_slovo(c) for c in DIAGNOSTIKA])
    r = LexicalRetention.evaluate(lex, DIAGNOSTIKA)

    assert r.ratio == 1.0
    assert r.total == 4
    assert r.borrowed == [] and r.lost == []


def test_vypujcka_se_nepocita_jako_retence():
    """Výpůjčka slot obsadí, ale původní kořen v něm už není."""
    lex = Lexicon(words=[
        _slovo("voda"),
        _slovo("vlk", source_id="north"),
        _slovo("strom"),
    ])
    r = LexicalRetention.evaluate(lex, DIAGNOSTIKA)

    assert r.retained == ["voda", "strom"]
    assert r.borrowed == ["vlk"]
    assert r.lost == ["kámen"]
    assert r.ratio == 0.5


def test_domaci_slovo_prebije_soubeznou_vypujcku():
    """Když slot drží domácí i přejaté slovo, kořen se udržel."""
    lex = Lexicon(words=[_slovo("vlk"), _slovo("vlk", source_id="north")])
    r = LexicalRetention.evaluate(lex, ["vlk"])

    assert r.retained == ["vlk"]
    assert r.ratio == 1.0


def test_polysemie_obsadi_slot():
    """Slovo pokrývá i koncepty ze své polysemie (viz Lexicon.get_words)."""
    slovo = _slovo("slunce")
    slovo.polysemy = {"den"}
    r = LexicalRetention.evaluate(Lexicon(words=[slovo]), ["den"])

    assert r.retained == ["den"]


def test_prazdna_diagnostika_nedeli_nulou():
    r = LexicalRetention.evaluate(Lexicon(), [])
    assert r.total == 0
    assert r.ratio == 0.0


def test_retence_je_nezavisla_na_fonetickem_rozpadu(mapper):
    """
    Osa (A) a (B) se nesmí míchat: `*kʷetwores` -> `čtyři` je fonologicky
    brutální a lexikálně nulová změna.
    """
    puvodni = Word(concept_id="ctyri", segments=mapper.parse_word("x", "kʷetwores").segments)
    potomek = Word(concept_id="ctyri", segments=mapper.parse_word("x", "tʃtiri").segments)

    r = LexicalRetention.evaluate(Lexicon(words=[potomek]), ["ctyri"])
    assert r.ratio == 1.0

    import lingpy
    eroze = lingpy.edit_dist(mapper.render_word(puvodni), mapper.render_word(potomek),
                             normalized=True)
    assert eroze > 0.5, "Fonetická vzdálenost má být vysoká, zatímco retence je plná."


@pytest.mark.parametrize(
    "ratio, years, ocekavano",
    [
        (0.85, 1000, True),    # uvnitř pásma 75–95 %
        (0.50, 1000, False),   # příliš rychlá náhrada
        (0.99, 1000, False),   # nepravděpodobně konzervativní
        (0.85, 0, None),       # nulová hloubka: pásmo nedává smysl
    ],
)
def test_volne_pasmo_retence(ratio, years, ocekavano):
    pocet = 100
    drzi = round(ratio * pocet)
    r = RetentionResult(
        retained=[f"c{i}" for i in range(drzi)],
        borrowed=[f"b{i}" for i in range(pocet - drzi)],
        lost=[],
    )
    assert r.in_plausible_band(years) is ocekavano


def test_diagnostika_z_protojazyka():
    lex = Lexicon(words=[_slovo("b"), _slovo("a"), _slovo("a")])
    assert LexicalRetention.diagnostic_from(lex) == ["a", "b"]


def test_vetve_se_meri_stejnym_pristrojem():
    vetve = {
        "north": Lexicon(words=[_slovo("voda"), _slovo("vlk")]),
        "south": Lexicon(words=[_slovo("voda"), _slovo("vlk", source_id="north")]),
    }
    vysledky = LexicalRetention.evaluate_family(vetve, DIAGNOSTIKA)

    assert {b: r.total for b, r in vysledky.items()} == {"north": 4, "south": 4}
    assert vysledky["north"].ratio > vysledky["south"].ratio

"""
Invarianty šablon zvukových změn.

Chrání před třemi třídami tichých chyb, které se v enginu už vyskytly:

1. **Nesplnitelné prostředí** — env {"syl": "+", "cons": "+"}. Segment nemůže
   být zároveň vokál i konsonant, takže schéma nikdy nezasáhne.
2. **Nekonzistentní výsledná matice** — akce nastaví rysy do kombinace, která
   v panphon tabulce neexistuje (/v/ + {cont: -} bez {strid: -}). Mapper pak
   sáhne po přibližné shodě a do výstupu propašuje cizí znak.
3. **Příliš široký terč** — {cons: +, voi: +, cont: +} bez {son: -} pohltí
   kromě znělých frikativ i likvidy /l/ a /r/.
"""
import random

import pytest

from cee.engine.inventory import InventoryView
from cee.engine.schemas import SCHEMA_REGISTRY

# Sondy pokrývají vokály, neznělé okluzivy, znělé frikativy na začátku slova,
# likvidy a koncovou souhlásku — tedy prostředí všech schémat v registru.
SONDY = ["petrakofis", "vata", "zata", "amat", "peto", "lata", "rata"]

SEEDS = range(6)


@pytest.fixture(scope="module")
def bohaty_inventar(mapper):
    """Inventář, ve kterém má oporu každé schéma."""
    return InventoryView(mapper, set("aeiouptkbdɡfvszlrmn"))


def _rules(schema_id, inventory):
    return [
        SCHEMA_REGISTRY[schema_id].generate_rule(inventory, year=100, rng=random.Random(seed))
        for seed in SEEDS
    ]


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_schema_vygeneruje_pravidlo(schema_id, bohaty_inventar):
    for rule in _rules(schema_id, bohaty_inventar):
        assert rule is not None
        assert rule.year == 100


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_schema_realne_zasahne(mapper, schema_id, bohaty_inventar):
    """Aspoň na jedné sondě musí schéma něco změnit."""
    for rule in _rules(schema_id, bohaty_inventar):
        for sonda in SONDY:
            if rule.apply_to_word(mapper.parse_word("x", sonda)):
                return
    pytest.fail(f"Schéma '{schema_id}' nikdy nezasáhne — zkontroluj rysy v target/env.")


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_vysledek_odpovida_realne_hlasce(mapper, schema_id, bohaty_inventar):
    """Po aplikaci musí každý segment odpovídat existující IPA hlásce."""
    for rule in _rules(schema_id, bohaty_inventar):
        for sonda in SONDY:
            word = mapper.parse_word("x", sonda)
            rule.apply_to_word(word)
            for i, segment in enumerate(word.segments):
                assert mapper.is_exact_segment(segment), (
                    f"Schéma '{schema_id}' vyrobilo na sondě '{sonda}' (segment {i}) "
                    f"matici, která neodpovídá žádné hlásce; "
                    f"mapper ji odhadl jako '{mapper.segment_to_ipa(segment)}'."
                )


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_schema_odmitne_prazdny_inventar(mapper, schema_id):
    """Bez opory v inventáři nemá podle 4.3 pravidlo vůbec vzniknout."""
    prazdny = InventoryView(mapper, set())
    assert SCHEMA_REGISTRY[schema_id].generate_rule(prazdny, year=100) is None


def test_fortice_odmitne_jazyk_bez_znelych_frikativ(mapper):
    bez_frikativ = InventoryView(mapper, set("aiuptk"))
    assert SCHEMA_REGISTRY["fortition"].generate_rule(bez_frikativ, year=100) is None

    s_frikativami = InventoryView(mapper, set("aiuptkvz"))
    assert SCHEMA_REGISTRY["fortition"].generate_rule(s_frikativami, year=100) is not None


def test_fortice_nesahne_na_likvidy(mapper, bohaty_inventar):
    """
    /l/ a /r/ jsou taky [cons +, voi +, cont +]. Bez [son: -] v terči je
    fortice měnila na okluzivy a mapper z toho dělal tónovou značku.
    """
    rule = SCHEMA_REGISTRY["fortition"].generate_rule(bohaty_inventar, year=100)
    for vstup, ocekavano in [("vata", "bata"), ("zata", "data"), ("ɣata", "ɡata"),
                             ("lata", "lata"), ("rata", "rata")]:
        word = mapper.parse_word("x", vstup)
        rule.apply_to_word(word)
        assert mapper.render_word(word) == ocekavano


def test_synkopa_maze_jen_vokal_sve_kvality(mapper, bohaty_inventar):
    """
    Synkopa nezasáhne celý vokalismus naráz — cílí na kvalitu vokálu.
    Jedno pravidlo dřív vygumovalo všechny vnitřní vokály a jazyk se pak
    neměl jak dál vyvíjet.
    """
    # peritoka má ve vnitřní pozici přední (e), vysoký (i) i zadní (o) vokál,
    # takže na ni dosáhne každá varianta.
    vysledky = {}
    for seed in range(24):
        rule = SCHEMA_REGISTRY["syncope"].generate_rule(
            bohaty_inventar, year=100, rng=random.Random(seed)
        )
        word = mapper.parse_word("x", "peritoka")
        rule.apply_to_word(word)
        vysledky[rule.name] = mapper.render_word(word)

    assert len(vysledky) >= 3, f"Losují se jen varianty {list(vysledky)}."

    for name, vysledek in vysledky.items():
        assert vysledek != "prtka", f"'{name}' vygumovala celý vokalismus."
        assert vysledek != "peritoka", f"'{name}' nezasáhla nic."

    # Výchozí varianta (bez rng) cílí na vysoké vokály — zmizí jen /i/.
    vysoke = SCHEMA_REGISTRY["syncope"].generate_rule(bohaty_inventar, year=100)
    word = mapper.parse_word("x", "peritoka")
    vysoke.apply_to_word(word)
    assert mapper.render_word(word) == "pertoka"


def test_vowel_shift_zvysuje_obe_rady(mapper, bohaty_inventar):
    """Přední i zadní řada musí dát čistý výsledek (e -> i, o -> u)."""
    vysledky = set()
    for seed in range(10):
        rule = SCHEMA_REGISTRY["vowel_shift"].generate_rule(
            bohaty_inventar, year=100, rng=random.Random(seed)
        )
        word = mapper.parse_word("x", "peto")
        rule.apply_to_word(word)
        vysledky.add(mapper.render_word(word))

    assert vysledky == {"pito", "petu"}


# --- schémata, která slova prodlužují ---------------------------------------


def test_epenteze_rozbiji_souhlaskovy_shluk(mapper, bohaty_inventar):
    """
    Bez vkládacích schémat umí engine jen ubírat, takže se lexikon nutně
    scvrkne do shluků souhlásek.
    """
    rule = SCHEMA_REGISTRY["epenthesis"].generate_rule(bohaty_inventar, year=100)
    word = mapper.parse_word("x", "ptra")

    assert rule.apply_to_word(word) is True
    vysledek = mapper.render_word(word)
    assert len(vysledek) > len("ptra")
    assert all(mapper.is_exact_segment(s) for s in word.segments)


def test_epenteze_vklada_hlasku_z_inventare(mapper):
    """Epentetický vokál cizí celému jazyku by byl nepravděpodobný."""
    jen_u = InventoryView(mapper, set("ptkru"))
    rule = SCHEMA_REGISTRY["epenthesis"].generate_rule(jen_u, year=100)

    assert rule.insert_label in set(jen_u)


def test_epenteze_odmitne_jazyk_bez_vokalu(mapper):
    bez_vokalu = InventoryView(mapper, set("ptk"))
    assert SCHEMA_REGISTRY["epenthesis"].generate_rule(bez_vokalu, year=100) is None


def test_diftongizace_prodlouzi_vokalismus(mapper, bohaty_inventar):
    rule = SCHEMA_REGISTRY["diphthongization"].generate_rule(bohaty_inventar, year=100)
    word = mapper.parse_word("x", "petra")

    assert rule.apply_to_word(word) is True
    assert len(mapper.render_word(word)) > len("petra")


def test_registr_obsahuje_i_prodluzujici_schemata():
    """
    Kdyby v registru zůstala jen schémata, která ubírají, slova by mohla
    pouze krátnout — což se v reálných jazycích neděje.
    """
    from cee.engine.schemas import DiphthongizationSchema, EpenthesisSchema

    prodluzujici = [
        s for s in SCHEMA_REGISTRY.values()
        if isinstance(s, (EpenthesisSchema, DiphthongizationSchema))
    ]
    assert len(prodluzujici) >= 2

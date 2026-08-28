"""
Invarianty generovaných schémat.

Chrání před dvěma třídami tichých chyb, které se v enginu už vyskytly:

1. **Nesplnitelné prostředí** — např. env {"syl": "+", "cons": "+"}. Segment
   nemůže být zároveň vokál i konsonant, takže schéma nikdy nezasáhne
   a generátor tiše nevyrobí žádnou změnu.
2. **Nekonzistentní výsledná matice** — akce nastaví rysy do kombinace, která
   v panphon tabulce neexistuje (/v/ + {cont: -} bez {strid: -}). Mapper pak
   sáhne po přibližné shodě a do výstupu propašuje cizí znak (třeba tónovou
   značku ˧ místo /b/).
"""
import random

import pytest

from cee.core.models import Inventory
from cee.engine.schemas import SCHEMA_REGISTRY

# Sondy pokrývají vokály, neznělé okluzivy, znělé frikativy na začátku slova,
# likvidy a koncovou souhlásku — tedy prostředí všech schémat v registru.
SONDY = ["petrakofis", "vata", "zata", "amat", "peto"]

SEEDS = range(6)


def _rules(schema_id):
    return [
        SCHEMA_REGISTRY[schema_id].generate_rule(Inventory(), year=100, rng=random.Random(seed))
        for seed in SEEDS
    ]


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_schema_vygeneruje_pravidlo(schema_id):
    for rule in _rules(schema_id):
        assert rule is not None
        assert rule.year == 100


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_schema_realne_zasahne(mapper, schema_id):
    """Aspoň na jedné sondě musí schéma něco změnit."""
    for rule in _rules(schema_id):
        for sonda in SONDY:
            if rule.apply_to_word(mapper.parse_word("x", sonda)):
                return
    pytest.fail(f"Schéma '{schema_id}' nikdy nezasáhne — zkontroluj rysy v target/env.")


@pytest.mark.parametrize("schema_id", sorted(SCHEMA_REGISTRY))
def test_vysledek_odpovida_realne_hlasce(mapper, schema_id):
    """Po aplikaci musí každý segment odpovídat existující IPA hlásce."""
    for rule in _rules(schema_id):
        for sonda in SONDY:
            word = mapper.parse_word("x", sonda)
            rule.apply_to_word(word)
            for i, segment in enumerate(word.segments):
                assert mapper.is_exact_segment(segment), (
                    f"Schéma '{schema_id}' vyrobilo na sondě '{sonda}' (segment {i}) "
                    f"matici, která neodpovídá žádné hlásce; "
                    f"mapper ji odhadl jako '{mapper.segment_to_ipa(segment)}'."
                )


def test_fortice_meni_frikativy_na_okluzivy(mapper):
    rule = SCHEMA_REGISTRY["fortition"].generate_rule(Inventory(), year=100)
    for vstup, ocekavano in [("vata", "bata"), ("zata", "data"), ("ɣata", "ɡata")]:
        word = mapper.parse_word("x", vstup)
        rule.apply_to_word(word)
        assert mapper.render_word(word) == ocekavano


def test_synkopa_maze_vokal_mezi_souhlaskami(mapper):
    rule = SCHEMA_REGISTRY["syncope"].generate_rule(Inventory(), year=100)
    word = mapper.parse_word("x", "petrako")
    assert rule.apply_to_word(word) is True
    assert mapper.render_word(word) == "ptrko"


def test_vowel_shift_zvysuje_obe_rady(mapper):
    """Přední i zadní řada musí dát čistý výsledek (e -> i, o -> u)."""
    vysledky = set()
    for seed in range(10):
        rule = SCHEMA_REGISTRY["vowel_shift"].generate_rule(
            Inventory(), year=100, rng=random.Random(seed)
        )
        word = mapper.parse_word("x", "peto")
        rule.apply_to_word(word)
        vysledky.add(mapper.render_word(word))

    assert vysledky == {"pito", "petu"}

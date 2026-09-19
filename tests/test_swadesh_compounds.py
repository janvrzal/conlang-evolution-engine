from cee.core.models import Inventory, Lexicon, State
from cee.semantics.swadesh import (
    SWADESH_100,
    apply_suggestion,
    automatic_suggestions,
    available_suggestions,
    suggestions_for,
    swadesh_coverage,
)


def test_swadesh_pack_pokryva_cely_diagnosticky_seznam():
    coverage = swadesh_coverage()
    assert set(coverage) == set(SWADESH_100)
    assert len(SWADESH_100) == 100
    assert len(suggestions_for("fingernail")) == 2
    assert suggestions_for("I") == []  # základní zájmeno se nenutí do složeniny


def test_nabidka_a_aplikace_slozeniny_pouziva_soucasny_morfologicky_engine(mapper):
    sky = mapper.parse_word("sky", "mi")
    water = mapper.parse_word("water", "ka")
    state = State("proto", Inventory(), Lexicon([sky, water]), map={"compound_head": "final"})
    options = available_suggestions(state, "rain")
    assert len(options) == 1
    rain = apply_suggestion(state, options[0])
    assert rain is not None
    assert mapper.render_word(rain) == "kami"
    assert rain.origin_type == "compound"


def test_automaticky_recept_nabidne_jen_chybejici_koncept_se_zdroji(mapper):
    sky = mapper.parse_word("sky", "mi")
    water = mapper.parse_word("water", "ka")
    state = State("proto", Inventory(), Lexicon([sky, water]))

    options = automatic_suggestions(state)

    assert [(option.target, option.head, option.modifier) for option in options] == [
        ("rain", "sky", "water")
    ]

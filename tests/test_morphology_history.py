from cee.core.models import Inventory, Lexicon, State
from cee.engine.morphology import MorphologyEvaluator


def test_opakovana_konstrukce_gramatikalizuje_afix_a_eroze_vytvori_nepravidelnost(mapper):
    first = mapper.parse_word("first", "pata")
    second = mapper.parse_word("second", "kama")
    affix = mapper.parse_word("plural", "mi")
    affix.frequency = 0.9
    state = State("x", Inventory(), Lexicon([first, second, affix]), year=300)
    morphology = MorphologyEvaluator()
    first_form = morphology.derive(state, "first", "plural", "first.pl")
    second_form = morphology.derive(state, "second", "plural", "second.pl")
    assert first_form and second_form
    first_form.frequency = second_form.frequency = 0.9

    assert morphology.promote_productive_affixes(state) == 1
    assert affix.is_grammatical is True
    assert affix.grammatical_features["morphology.productivity"]

    assert morphology.erode_productive_affixes(state) == 2
    assert all(word.grammatical_features["morphology.eroded"] == "true" for word in (first_form, second_form))
    assert len(first_form.segments) == len(first.segments) + 1

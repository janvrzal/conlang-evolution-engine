import random

from cee.core.models import Inventory, Lexicon, State
from cee.engine.lexicon import LexicalEvaluator


def test_lexikalni_nahrada_se_siri_po_epochach_a_teprve_pak_vyhrava(mapper):
    incumbent = mapper.parse_word("fire", "pata")
    donor = mapper.parse_word("donor", "kama")
    incumbent.frequency = 0.2
    donor.frequency = 0.9
    state = State("x", Inventory(), Lexicon([incumbent, donor]), social={"mobility": 1.0})
    evaluator = LexicalEvaluator(replacement_rate=1.0, loss_rate=0.01)

    evaluator.evaluate(state, 100, random.Random(4))
    variants = state.lexicon.get_words("fire")
    assert len(variants) == 2
    innovator = next(word for word in variants if word is not incumbent)
    assert innovator.grammatical_features["lexical.stage"] in {"spreading", "dominant"}
    assert incumbent.active is True

    resolved_once = False
    for year in range(200, 800, 100):
        evaluator.evaluate(state, year, random.Random(4))
        resolved_once = resolved_once or any(item["resolved"] for item in evaluator.last_competitions)

    assert innovator.grammatical_features["lexical.stage"] == "established"
    assert incumbent.active is False
    assert resolved_once is True

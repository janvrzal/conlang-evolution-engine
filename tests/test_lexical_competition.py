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


def test_lexikalni_inovace_se_siri_rychleji_pres_sit_a_bilingvismus(mapper):
    def state_with(connection: float):
        incumbent = mapper.parse_word("fire", "pata")
        innovator = mapper.parse_word("fire", "kama")
        incumbent.frequency = innovator.frequency = 0.4
        incumbent.grammatical_features["social.group"] = "village"
        innovator.grammatical_features.update({"social.group": "city", "lexical.variant_for": incumbent.id})
        return State(
            "x", Inventory(), Lexicon([incumbent, innovator]),
            social={"mobility": 0.5},
            map={"communities": [{"id": "city", "bilingualism": {"village": connection}}, {"id": "village"}]},
        ), innovator

    connected, connected_innovator = state_with(1.0)
    isolated, isolated_innovator = state_with(0.0)
    evaluator = LexicalEvaluator()
    evaluator._advance_competitions(connected, mobility=0.5, standard=0.0)
    evaluator._advance_competitions(isolated, mobility=0.5, standard=0.0)

    assert connected_innovator.frequency > isolated_innovator.frequency
    assert evaluator.last_competitions[0]["network_spread"] == 0.25

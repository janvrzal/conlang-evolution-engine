from cee.core.models import Inventory, Lexicon, State
from cee.engine.lexicon import LexicalEvaluator
from cee.engine.graph_builder import GraphBuilder
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph, VerticalEdge


def _word(mapper, concept, ipa, frequency, domain="The body"):
    word = mapper.parse_word(concept, ipa)
    word.frequency = frequency
    word.grammatical_features = {"semantic.roles": "reference", "semantic.domains": domain}
    return word


def test_legitimni_strategie_homofonie_jsou_casovane_a_dohledatelne(mapper):
    words = [
        _word(mapper, "hand", "pata", 0.95),
        _word(mapper, "arm", "pata", 0.80),
        _word(mapper, "tree", "kumi", 0.95, "Agriculture and vegetation"),
        _word(mapper, "forest", "kumi", 0.80, "Agriculture and vegetation"),
        _word(mapper, "woodland", "saku", 0.70, "Agriculture and vegetation"),
        _word(mapper, "stone", "nasa", 0.95, "The physical world"),
        _word(mapper, "rock", "nasa", 0.80, "The physical world"),
        _word(mapper, "rock_root", "taku", 0.70, "The physical world"),
        _word(mapper, "collective", "mi", 0.70, "Quantity"),
        _word(mapper, "river", "lapa", 0.95, "The physical world"),
        _word(mapper, "stream", "lapa", 0.80, "The physical world"),
        _word(mapper, "water", "ma", 0.70, "The physical world"),
        _word(mapper, "flow", "ki", 0.70, "Motion"),
    ]
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "lexical": {
                    "enabled": True,
                    "replacement_rate": 0.0,
                    "homophony_policy": "resolve",
                    "homophony_resolution_rate": 1.0,
                    "homophony_strategies": {
                        "arm": {"kind": "colexification"},
                        "forest": {"kind": "semantic_shift", "source": "woodland"},
                        "rock": {"kind": "derivation", "root": "rock_root", "affix": "collective"},
                        "stream": {"kind": "compound", "head": "water", "modifier": "flow"},
                    },
                },
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, end_year=100, graph_builder=builder).simulate(
        State("proto", Inventory(), Lexicon(words), year=0)
    )["child"]

    hand = state.lexicon.get_word("hand")
    woodland = state.lexicon.get_word("woodland")
    rock = state.lexicon.get_word("rock")
    stream = state.lexicon.get_word("stream")
    assert hand is not None and "arm" in hand.polysemy
    assert woodland is not None and "forest" in woodland.polysemy
    assert rock is not None and rock.origin_type == "homophony_derivation"
    assert stream is not None and stream.origin_type == "homophony_compound"
    assert all(word.origin_type != "homophony_resolution" for word in state.lexicon.words)
    actions = {event["action"] for event in builder.events if event.get("kind") == "homophony_pressure"}
    pending = [event for event in builder.events if event.get("kind") == "homophony_pending"]
    assert all(event["status"] == "pending" for event in pending)
    assert {"colexification", "semantic_shift", "derivation", "compound"} <= actions


def test_recept_slozeniny_je_legitimni_automaticka_reakce_na_homofonii(mapper):
    import random

    cloud = _word(mapper, "cloud", "pata", 0.95, "The physical world")
    rain = _word(mapper, "rain", "pata", 0.8, "The physical world")
    sky = _word(mapper, "sky", "mi", 0.6, "The physical world")
    water = _word(mapper, "water", "ka", 0.6, "The physical world")
    state = State("x", Inventory(), Lexicon([cloud, rain, sky, water]))
    evaluator = LexicalEvaluator(homophony_policy="resolve", homophony_resolution_rate=1.0)

    evaluator.evaluate(state, 100, random.Random(2), render=mapper.render_word)

    resolved = state.lexicon.get_word("rain")
    assert resolved is not None
    assert resolved.origin_type == "homophony_compound"
    assert mapper.render_word(resolved) == "kami"


def test_produktivni_afix_je_legitimni_automaticka_reakce_na_homofonii(mapper):
    import random

    winner = _word(mapper, "stone", "pata", 0.95, "The physical world")
    loser = _word(mapper, "pebble", "pata", 0.8, "The physical world")
    affix = _word(mapper, "diminutive", "mi", 0.7, "Grammar")
    affix.is_grammatical = True
    affix.grammatical_features["morphology.productivity"] = "0.8"
    state = State("x", Inventory(), Lexicon([winner, loser, affix]))
    evaluator = LexicalEvaluator(homophony_policy="resolve", homophony_resolution_rate=1.0)

    evaluator.evaluate(state, 100, random.Random(2), render=mapper.render_word)

    resolved = state.lexicon.get_word("pebble")
    assert resolved is not None
    assert resolved.origin_type == "homophony_productive_derivation"
    assert mapper.render_word(resolved) == "patami"

"""Kontakt jako doložitelný původ konstrukcí a oprav homofonie."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph


def test_contact_can_resolve_loaded_homophony_with_matching_loan(mapper):
    winner = mapper.parse_word("water", "pata")
    loser = mapper.parse_word("river", "pata")
    for word in (winner, loser):
        word.frequency = 1.0
        word.grammatical_features["semantic.roles"] = "reference"
        word.grammatical_features["semantic.domains"] = "nature"
    donor = mapper.parse_word("river", "kumi")
    donor.frequency = 1.0
    graph = EvolutionGraph(node_configs={"source": {}, "target": {}})
    builder = GraphBuilder()
    simulator = EvolutionSimulator(graph, mapper, graph_builder=builder)
    source = State("source", Inventory(), Lexicon([donor]))
    target = State("target", Inventory(), Lexicon([winner, loser]))
    for index, word in enumerate(target.lexicon.words):
        word.id = f"target-{index}"
    donor.id = "source-river"

    simulator._apply_contact(source, target, 100, 1, resolve_homophony=True)

    resolved = next(word for word in target.lexicon.words if word.concept_id == "river" and word.id != "target-1")
    assert mapper.render_word(resolved) == "kumi"
    assert resolved.grammatical_features["homophony.resolution"] == "contact_loan"
    assert any(event["kind"] == "homophony_contact_resolution" for event in builder.events)


def test_contact_transfers_selected_productive_construction(mapper):
    source_root = mapper.parse_word("trade", "taka")
    source_affix = mapper.parse_word("agent", "mi")
    source_affix.is_grammatical = True
    target_root = mapper.parse_word("trade", "palu")
    graph = EvolutionGraph(node_configs={
        "source": {"morphology": {"constructions": [{
            "id": "agentive", "kind": "derivation", "root_concept": "trade",
            "affix_concept": "agent", "result_concept": "trader", "prefix": False,
        }]}},
        "target": {},
    })
    builder = GraphBuilder()
    simulator = EvolutionSimulator(graph, mapper, graph_builder=builder)
    source = State("source", Inventory(), Lexicon([source_root, source_affix]))
    target = State("target", Inventory(), Lexicon([target_root]))

    simulator._apply_contact(source, target, 100, 1, construction_ids=["agentive"])

    trader = target.lexicon.get_word("trader")
    assert trader is not None
    assert trader.grammatical_features["morphology.borrowed_construction"] == "agentive"
    assert graph.node_configs["target"]["morphology"]["borrowed_constructions"][0]["id"] == "agentive"
    assert any(event["kind"] == "construction_transfer" for event in builder.events)


def test_opakovany_politicky_kontakt_ma_rozpocet_a_nepujcuje_tentyz_koncept(mapper):
    source_words = [mapper.parse_word(f"concept-{index}", f"pa{vowel}ta") for index, vowel in enumerate("eiou")]
    for word in source_words:
        word.frequency = 1.0
    target_word = mapper.parse_word("local", "kumi")
    graph = EvolutionGraph(node_configs={"source": {}, "target": {}})
    simulator = EvolutionSimulator(graph, mapper)
    source = State("source", Inventory(), Lexicon(source_words))
    target = State("target", Inventory(), Lexicon([target_word]))

    for year in (100, 200, 300):
        simulator._apply_contact(source, target, year, 8, domain="polity")

    loans = [word for word in target.lexicon.words if word.source_id == "source"]
    assert len(loans) == 3
    assert len({word.concept_id for word in loans}) == 3

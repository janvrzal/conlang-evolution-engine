"""Regrese pro demografii, komunity a lehké dialektní variety."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph, VerticalEdge


def test_populacni_profil_a_komunity_se_nactou_ze_stavu(mapper):
    state = State(
        "proto",
        Inventory(),
        Lexicon([mapper.parse_word("water", "pata")]),
        map={
            "population": {"size": 12000, "area": 320, "concentration": 0.7, "centers": 3},
            "communities": [
                {"id": "court", "share": 3, "domains": ["administration"]},
                {"id": "valley", "share": 1, "kind": "regional"},
            ],
        },
    )

    assert state.population.size == 12000
    assert state.population.centers == 3
    assert state.communities["court"].share == 0.75
    assert state.communities["valley"].variety_id == "variety:valley"
    assert "variety:valley" in state.varieties


def test_komunity_jsou_ohniskem_a_vytvari_audit_dialektni_divergence(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "map": {
                    "isolation": 1.0,
                    "social": {"mobility": 0.1},
                    "population": {"size": 80, "area": 100, "centers": 2},
                    "communities": [
                        {"id": "city", "share": 0.6, "kind": "urban"},
                        {"id": "upland", "share": 0.4, "kind": "regional"},
                    ],
                },
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    builder = GraphBuilder()
    states = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=700).simulate(
        State(
            "proto",
            Inventory(),
            Lexicon([mapper.parse_word("water", "pata"), mapper.parse_word("fire", "kumi")]),
        )
    )

    child = states["child"]
    assert all("social.group" in word.grammatical_features for word in child.lexicon.words)
    assert all(variety.divergence > 0 for variety in child.varieties.values())
    assert any(event["kind"] == "variety_divergence" for event in builder.events)
    assert any(event["kind"] == "language_split_candidate" for event in builder.events)

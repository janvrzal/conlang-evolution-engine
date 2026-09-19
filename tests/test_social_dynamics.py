"""Regrese pro demografii, komunity a lehké dialektní variety."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.social import SocialDynamicsEngine
from cee.engine.simulator import EvolutionSimulator
from cee.engine.events import SocialEvent
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


def test_propojene_variety_se_navzajem_difuzuji(mapper):
    state = State(
        "x", Inventory(), Lexicon([mapper.parse_word("water", "pata")]),
        map={"communities": [
            {"id": "town", "kind": "urban", "links": {"village": 1.0}, "mobility": 1.0},
            {"id": "village", "kind": "rural", "links": {"town": 1.0}, "mobility": 1.0},
        ]},
    )
    state.varieties["variety:town"].divergence = 0.8
    state.varieties["variety:village"].divergence = 0.1

    dynamics = SocialDynamicsEngine()
    dynamics.advance(state, 100)
    events = dynamics.advance(state, 200)

    assert any(event["kind"] == "variety_diffusion" for event in events)
    assert state.varieties["variety:town"].divergence < 0.8


def test_sit_komunit_meni_prah_konkreti_fonologicke_inovace(mapper):
    word = mapper.parse_word("water", "pata")
    word.grammatical_features["social.group"] = "village"
    connected = State(
        "x", Inventory(), Lexicon([word]),
        map={"communities": [{"id": "city", "links": {"village": 1.0}}, {"id": "village"}]},
    )
    isolated = State(
        "x", Inventory(), Lexicon([mapper.parse_word("water", "pata")]),
        map={"communities": [{"id": "city"}, {"id": "village"}]},
    )
    isolated.lexicon.words[0].grammatical_features["social.group"] = "village"

    assert EvolutionSimulator._network_adoption_bias(connected, "city", word) < EvolutionSimulator._network_adoption_bias(
        isolated, "city", isolated.lexicon.words[0]
    )


def test_migrace_presune_podil_mezi_komunitami(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {"year": 0, "map": {"communities": [{"id": "a", "share": 0.8}, {"id": "b", "share": 0.2}]},
                      "social_history": [{"year": 50, "migration": {"from": "a", "to": "b", "share": 0.3}}]},
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    state = EvolutionSimulator(graph, mapper, end_year=60).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["child"]
    assert state.communities["a"].share == 0.5
    assert state.communities["b"].share == 0.5


def test_autorske_rozhodnuti_asimiluje_nebo_podpori_varietu(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "map": {"communities": [{"id": "upland", "kind": "regional"}]},
                "social_history": [{
                    "year": 50,
                    "changes": {"variety_action": {"variety_id": "variety:upland", "action": "assimilate"}},
                }],
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=60).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["child"]

    assert state.varieties["variety:upland"].divergence == 0.0
    assert state.communities["upland"].status == "assimilated"
    assert any(event["kind"] == "variety_decision" for event in builder.events)


def test_migrace_muze_zalozit_novou_komunitu_a_vazbu(mapper):
    graph = EvolutionGraph(
        node_configs={
            "proto": {},
            "child": {
                "year": 0,
                "map": {"communities": [{"id": "coast", "share": 1.0, "kind": "urban", "urbanity": 0.8}]},
                "social_history": [{"year": 50, "changes": {"migration": {
                    "from": "coast", "to": "interior", "share": 0.3,
                    "create": {"kind": "regional", "urbanity": 0.2, "link_strength": 0.7, "bilingualism": 0.6},
                }}}],
            },
        },
        vertical_edges=[VerticalEdge("proto", "child", [])],
    )
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=60).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["child"]

    assert state.communities["interior"].share == 0.3
    assert state.communities["coast"].links["interior"] == 0.7
    assert state.communities["interior"].bilingualism["coast"] == 0.6
    assert "variety:interior" in state.varieties
    assert any(event["kind"] == "migration_community_created" for event in builder.events)


def test_kohorty_se_obnovuji_a_mesto_ovlivni_sireni(mapper):
    state = State(
        "x", Inventory(), Lexicon([mapper.parse_word("water", "pata")]),
        map={"communities": [
            {"id": "city", "kind": "urban", "urbanity": 1.0, "generation": "young", "links": {"village": 1.0}},
            {"id": "village", "kind": "rural", "urbanity": 0.0, "generation": "elder", "links": {"city": 1.0}},
        ]},
    )
    state.varieties["variety:city"].divergence = 0.7
    dynamics = SocialDynamicsEngine()
    dynamics.advance(state, 100)
    events = dynamics.advance(state, 200)

    assert any(event["kind"] == "cohort_turnover" for event in events)
    diffusion = next(event for event in events if event["kind"] == "variety_diffusion" and event["community_id"] == "village")
    assert diffusion["cohort_receptivity"] < 0

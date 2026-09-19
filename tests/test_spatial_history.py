"""Regrese pro státy, obchodní trasy a autorské historické události."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import (
    EvolutionGraph,
    HistoricalEventSpec,
    Polity,
    TradeRoute,
    VerticalEdge,
)


def _two_branch_graph():
    return EvolutionGraph(
        node_configs={"proto": {}, "a": {"year": 0}, "b": {"year": 0}},
        vertical_edges=[VerticalEdge("proto", "a"), VerticalEdge("proto", "b")],
    )


def test_polity_generates_internal_contact_and_standardization(mapper):
    graph = _two_branch_graph()
    graph.polities["realm"] = Polity(
        "realm", "Říše", institutions={"internal_contact": 1.0, "standardization": 0.9},
        language_ids=["a", "b"],
    )
    builder = GraphBuilder()
    states = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=100).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )

    assert states["a"].social["standardization"] == 0.9
    assert states["b"].social["standardization"] == 0.9
    assert any(event["kind"] == "contact" and event["domain"] == "polity" for event in builder.events)


def test_route_respects_time_window_and_generates_trade_contact(mapper):
    graph = _two_branch_graph()
    graph.trade_routes.append(TradeRoute("river", "river", 0.8, ["a", "b"], 100, 100))
    builder = GraphBuilder()
    EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=200).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )

    contacts = [event for event in builder.events if event["kind"] == "contact" and event["domain"] == "trade"]
    assert contacts
    assert {event["year"] for event in contacts} == {100}


def test_drawn_route_only_connects_languages_near_its_corridor(mapper):
    graph = _two_branch_graph()
    graph.node_configs["a"]["position"] = {"x": 100, "y": 0}
    graph.node_configs["b"]["position"] = {"x": 100, "y": 800}
    graph.trade_routes.append(TradeRoute(
        "land", "land", 1.0, ["a", "b"], 100, 100,
        [{"x": 0, "y": 0}, {"x": 200, "y": 0}],
    ))
    builder = GraphBuilder()
    EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=100).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )

    assert not [event for event in builder.events if event["kind"] == "contact" and event["domain"] == "trade"]


def test_historical_event_targets_polity_and_keeps_audit_trace(mapper):
    graph = _two_branch_graph()
    graph.polities["realm"] = Polity("realm", "Říše", language_ids=["a", "b"])
    graph.historical_events.append(HistoricalEventSpec(
        "reform", "standardization", 100, 0, target_polity_id="realm"
    ))
    builder = GraphBuilder()
    states = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=150).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )

    assert states["a"].social["standardization"] == 0.8
    assert states["b"].social["standardization"] == 0.8
    history = [event for event in builder.events if event["kind"] == "historical_event"]
    assert len(history) == 2
    assert {event["end_year"] for event in history} == {100}


def test_temporary_historical_effect_is_released_at_event_end(mapper):
    graph = _two_branch_graph()
    graph.historical_events.append(HistoricalEventSpec(
        "war", "war", 100, 50, target_language_ids=["a"]
    ))
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=160).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["a"]

    assert state.social["mobility"] == 0.0
    phases = [event["phase"] for event in builder.events if event["kind"] == "historical_event"]
    assert phases == ["start", "end"]


def test_overlapping_historical_intervals_restore_the_remaining_layer(mapper):
    graph = _two_branch_graph()
    graph.historical_events.extend([
        HistoricalEventSpec("war", "war", 100, 100, target_language_ids=["a"]),
        HistoricalEventSpec(
            "standard", "standardization", 150, 150, target_language_ids=["a"]
        ),
    ])
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=301).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["a"]

    # V roce 200 skončí válka, ale standardizační vrstva dál trvá; její konec
    # v roce 300 teprve odkryje původní nulu.
    social_changes = [
        event for event in builder.events
        if event["kind"] == "social_change" and event["language_id"] == "a"
    ]
    at_war_end = next(event for event in social_changes if event["year"] == 200)
    assert at_war_end["changes"]["standardization"] == 0.8
    assert state.social["standardization"] == 0.0


def test_political_event_can_change_endonym_and_exonym(mapper):
    graph = _two_branch_graph()
    graph.node_configs["a"]["endonym"] = "Staré"
    graph.historical_events.append(HistoricalEventSpec(
        "name", "rename", 100, target_language_ids=["a"],
        effects={"name_change": {"endonym": "Nové", "exonym": "New"}},
    ))
    builder = GraphBuilder()
    EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=120).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )

    assert graph.node_configs["a"]["endonym"] == "Nové"
    assert graph.node_configs["a"]["exonym"] == "New"
    assert any(event["kind"] == "language_name_change" for event in builder.events)


def test_curve_effects_are_composed_and_persistent_consequence_remains(mapper):
    graph = _two_branch_graph()
    graph.historical_events.extend([
        HistoricalEventSpec(
            "urban", "urbanization", 100, 100, target_language_ids=["a"],
            effects={
                "mobility": {"value": 0.8, "curve": "linear"},
                "urbanity": {"value": 0.9, "curve": "persistent"},
            },
        ),
        HistoricalEventSpec(
            "war", "war", 125, 50, target_language_ids=["a"],
            effects={"contact_intensity": {"value": 0.1, "curve": "pulse"}},
        ),
    ])
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=201).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["a"]

    # Náběh mobility a válečný puls skončí, urbanita je explicitní následek.
    assert state.social["mobility"] == 0.0
    assert state.social["contact_intensity"] == 0.0
    assert state.social["urbanity"] == 0.9
    samples = [event for event in builder.events if event["kind"] == "historical_event"]
    urban_peak = next(event for event in samples if event["id"] == "urban" and event["year"] == 150)
    assert any(effect["parameter"] == "mobility" and effect["strength"] == 0.5 for effect in urban_peak["effects"])


def test_migration_materializes_community_and_network_only_once(mapper):
    graph = _two_branch_graph()
    graph.node_configs["a"]["map"] = {"communities": [{"id": "coast", "share": 1.0}]}
    graph.historical_events.append(HistoricalEventSpec(
        "settlement", "migration", 100, 100, target_language_ids=["a"],
        effects={"migration": {
            "from": "coast", "to": "interior", "share": 0.3,
            "create": {"link_strength": 0.7, "bilingualism": 0.6},
        }},
    ))
    builder = GraphBuilder()
    state = EvolutionSimulator(graph, mapper, graph_builder=builder, end_year=250).simulate(
        State("proto", Inventory(), Lexicon([mapper.parse_word("water", "pata")]))
    )["a"]

    assert state.communities["interior"].share == 0.3
    assert state.communities["coast"].links["interior"] == 0.7
    assert len([event for event in builder.events if event["kind"] == "migration"]) == 1

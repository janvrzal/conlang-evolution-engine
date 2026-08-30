from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.phonology import FeatureMapper
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import ContactEdge, EvolutionGraph


def test_simulation_with_only_contact_edges():
    graph = EvolutionGraph()
    # Add a contact edge but no vertical edges
    graph.contact_edges.append(
        ContactEdge(year=100, source_id="proto", target_id="orphan", volume=5)
    )

    mapper = FeatureMapper()
    lexicon = Lexicon([mapper.parse_word("test", "a")])

    builder = GraphBuilder()
    root_state = State(node_id="proto", year=0, inventory=Inventory(), lexicon=lexicon)

    simulator = EvolutionSimulator(graph, mapper)
    simulator.graph_builder = builder
    states = simulator.simulate(root_state)

    assert "proto" in states
    assert len(builder.nodes) == 1
    assert builder.nodes[0]["language_id"] == "proto"
    assert "orphan" not in states


def test_simulation_with_no_edges():
    graph = EvolutionGraph()

    mapper = FeatureMapper()
    lexicon = Lexicon([mapper.parse_word("test", "a")])

    builder = GraphBuilder()
    root_state = State(node_id="proto", year=0, inventory=Inventory(), lexicon=lexicon)

    simulator = EvolutionSimulator(graph, mapper)
    simulator.graph_builder = builder
    states = simulator.simulate(root_state)

    assert "proto" in states
    assert len(builder.nodes) == 1
    assert builder.nodes[0]["language_id"] == "proto"

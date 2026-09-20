"""Nezávislé protojazyky sdílejí historii jen skrze explicitní kontakt."""

from cee.core.models import Lexicon
from cee.engine.phonology import FeatureMapper
from cee.engine.topology import ContactEdge, EvolutionGraph, VerticalEdge
from cee.pipeline import SimulationConfig, run_multiroot_simulation


def _lexicon(mapper, concept, ipa):
    return Lexicon(words=[mapper.parse_word(concept, ipa)])


def test_dve_protorodiny_maji_vlastni_dedicnost_a_mohou_se_stretnout():
    mapper = FeatureMapper()
    graph = EvolutionGraph()
    graph.node_configs = {
        "proto-a": {"isProto": True, "year": 0},
        "proto-b": {"isProto": True, "year": 0},
        "a-dcera": {"year": 100},
        "b-dcera": {"year": 100},
    }
    graph.vertical_edges = [
        VerticalEdge("proto-a", "a-dcera", []),
        VerticalEdge("proto-b", "b-dcera", []),
    ]
    graph.contact_edges = [ContactEdge(150, "a-dcera", "b-dcera", 1, mutual=False)]

    states = run_multiroot_simulation(
        {
            "proto-a": _lexicon(mapper, "sun", "sula"),
            "proto-b": _lexicon(mapper, "moon", "miko"),
        },
        graph,
        mapper,
        SimulationConfig(years=200, enable_semantics=False, evolve_root=True, seed=7),
    )

    assert states["a-dcera"].parent_id == "proto-a"
    assert states["b-dcera"].parent_id == "proto-b"
    assert {word.concept_id for word in states["a-dcera"].lexicon.words} == {"sun"}
    loans = [word for word in states["b-dcera"].lexicon.words if word.source_id == "a-dcera"]
    assert len(loans) == 1
    assert loans[0].concept_id == "sun"

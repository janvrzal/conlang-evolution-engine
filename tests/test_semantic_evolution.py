"""Kauzální a postupné sémantické změny na společné časové ose."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.graph_builder import GraphBuilder
from cee.engine.semantics import SemanticEvaluator
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph, VerticalEdge


class OneShiftGraph:
    def __init__(self, edge_type: str = "colexification"):
        self.edge_type = edge_type

    def get_possible_shifts(self, concept_id: str):
        if concept_id.lower() == "sun":
            return [
                ("SKY", "sky", 5.0, self.edge_type),
                ("FIRE", "fire", 1.0, self.edge_type),
            ]
        return []


def _root(mapper) -> State:
    word = mapper.parse_word("sun", "sula")
    word.frequency = 1.0
    return State("proto", Inventory(), Lexicon([word]))


def test_navrh_vybira_nejsilneji_dolozeny_posun(mapper):
    evaluator = SemanticEvaluator(OneShiftGraph(), shift_prob=1.0, seed=3)
    word = mapper.parse_word("sun", "sula")
    word.frequency = 1.0
    word.lineage_id = "lexeme-sun"

    proposals = evaluator.propose_changes(Lexicon([word]))

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.word_lineage_id == "lexeme-sun"
    assert proposal.source_concept == "sun"
    assert proposal.target_concept == "sky"
    assert proposal.kind == "extension"
    assert proposal.pressure == 1.0
    assert proposal.duration() == 144


def test_rozsireni_vyznamu_neprobehne_okamzite(mapper):
    builder = GraphBuilder()
    states = EvolutionSimulator(
        EvolutionGraph(),
        mapper,
        semantic_evaluator=SemanticEvaluator(OneShiftGraph(), shift_prob=1.0),
        graph_builder=builder,
        end_year=300,
        evolve_root=True,
    ).simulate(_root(mapper))

    assert "sky" in states["proto"].lexicon.words[0].polysemy
    semantic_versions = [
        node
        for node in builder.nodes
        if node["language_id"] == "proto" and "sky" in node["polysemy"]
    ]
    assert [node["year"] for node in semantic_versions] == [172]
    started = [event for event in builder.events if event["kind"] == "semantic_change_started"]
    assert started[0]["year"] == 100
    assert started[0]["duration"] == 144
    assert started[0]["pressure"] == 1.0


def test_uplny_posun_ma_obdobi_polysemie(mapper):
    builder = GraphBuilder()
    states = EvolutionSimulator(
        EvolutionGraph(),
        mapper,
        semantic_evaluator=SemanticEvaluator(OneShiftGraph("shift"), shift_prob=1.0),
        graph_builder=builder,
        end_year=300,
        evolve_root=True,
    ).simulate(_root(mapper))

    semantic_versions = [
        node for node in builder.nodes if node["language_id"] == "proto" and node["year"] > 0
    ]
    assert semantic_versions[0]["concept_id"] == "sun"
    assert semantic_versions[0]["polysemy"] == ["sky"]
    assert semantic_versions[-1]["concept_id"] == "sky"
    assert semantic_versions[-1]["polysemy"] == []
    assert states["proto"].lexicon.words[0].concept_id == "sky"


def test_rozbehnutou_zmenu_zdedi_nova_vetev(mapper):
    graph = EvolutionGraph(
        node_configs={"proto": {}, "daughter": {"year": 150}},
        vertical_edges=[VerticalEdge("proto", "daughter", [])],
    )
    states = EvolutionSimulator(
        graph,
        mapper,
        semantic_evaluator=SemanticEvaluator(OneShiftGraph(), shift_prob=1.0),
        end_year=300,
        evolve_root=True,
    ).simulate(_root(mapper))

    assert "sky" in states["proto"].lexicon.words[0].polysemy
    assert "sky" in states["daughter"].lexicon.words[0].polysemy
    assert (
        states["proto"].lexicon.words[0].lineage_id
        == states["daughter"].lexicon.words[0].lineage_id
    )

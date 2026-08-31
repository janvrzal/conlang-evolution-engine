"""Kauzální a postupné sémantické změny na společné časové ose."""

from cee.core.models import Inventory, Lexicon, State
from cee.engine.events import SemanticChangeEvent, SemanticChangeSpreadEvent
from cee.engine.graph_builder import GraphBuilder
from cee.engine.semantic_history import SemanticChangeRuntime
from cee.engine.semantics import SemanticEvaluator
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph, VerticalEdge
from cee.semantics.concepts import ConceptMetadata


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


class EmptyGraph:
    def get_possible_shifts(self, concept_id: str):
        return []


class MechanismGraph:
    _relations = {
        "sun": [("SKY", "sky", 1.0, "shift", "metaphor", None, None)],
        "hand": [("EAT", "eat", 1.0, "shift", "metonymy", "instrument_action", None)],
        "child": [("PERSON", "person", 1.0, "shift", "generalization", None, "broader")],
        "animal": [("DOG", "dog", 1.0, "shift", "specialization", None, "narrower")],
    }

    def get_possible_relations(self, concept_id: str):
        return self._relations.get(concept_id.lower(), [])

    def get_possible_shifts(self, concept_id: str):
        return [relation[:4] for relation in self.get_possible_relations(concept_id)]


class MechanismConceptIndex:
    _domains = {
        "sun": "celestial bodies",
        "sky": "weather",
        "hand": "the body",
        "eat": "the body",
    }

    def lookup(self, concept_id: str):
        domain = self._domains.get(concept_id.lower(), "")
        return ConceptMetadata("", concept_id.upper(), domain, "") if domain else None


class IncompleteMechanismConceptIndex(MechanismConceptIndex):
    _domains = {"sun": "celestial bodies"}


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


def test_kuratorovany_mechanismus_urcuje_typ_semanticke_zmeny(mapper):
    words = [mapper.parse_word(concept, "sula") for concept in MechanismGraph._relations]
    evaluator = SemanticEvaluator(
        MechanismGraph(), shift_prob=1.0, concept_index=MechanismConceptIndex()
    )

    proposals = evaluator.extension_candidates(Lexicon(words))
    by_mechanism = {proposal.mechanism: proposal for proposal in proposals}

    assert by_mechanism["metaphor"].kind == "extension"
    assert by_mechanism["metonymy"].kind == "extension"
    assert by_mechanism["generalization"].kind == "extension"
    assert by_mechanism["specialization"].kind == "shift"
    assert by_mechanism["metaphor"].mechanism_reason == "cross-domain bridge"
    assert by_mechanism["metonymy"].mechanism_reason == "same-domain instrument_action bridge"


def test_autoruv_prepis_oznaci_neoznacenou_hranu_bez_odhadu(mapper):
    graph = OneShiftGraph("shift")
    evaluator = SemanticEvaluator(
        graph,
        shift_prob=1.0,
        mechanism_overrides={"sun->sky": "metaphor"},
        concept_index=MechanismConceptIndex(),
    )
    word = mapper.parse_word("sun", "sula")

    proposal = next(
        item
        for item in evaluator.extension_candidates(Lexicon([word]))
        if item.target_concept == "sky"
    )

    assert proposal.mechanism == "metaphor"
    assert proposal.kind == "extension"


def test_autoruv_strukturalni_most_aktivuje_metonymii(mapper):
    class HandGraph:
        def get_possible_shifts(self, concept_id: str):
            return [("EAT", "eat", 1.0, "shift")] if concept_id.lower() == "hand" else []

    evaluator = SemanticEvaluator(
        HandGraph(),
        mechanism_overrides={"hand->eat": "metonymy"},
        relation_overrides={"hand->eat": {"bridge": "instrument_action"}},
        concept_index=MechanismConceptIndex(),
    )
    word = mapper.parse_word("hand", "sula")

    proposal = evaluator.extension_candidates(Lexicon([word]))[0]

    assert proposal.mechanism == "metonymy"
    assert proposal.mechanism_reason == "same-domain instrument_action bridge"


def test_mechanismus_bez_sve_evidence_se_nespusti(mapper):
    word = mapper.parse_word("sun", "sula")
    evaluator = SemanticEvaluator(
        OneShiftGraph("shift"),
        mechanism_overrides={"sun->sky": "metaphor"},
        concept_index=IncompleteMechanismConceptIndex(),
    )

    assert not [
        proposal
        for proposal in evaluator.extension_candidates(Lexicon([word]))
        if proposal.target_concept == "sky"
    ]


def test_neoznaceny_datovy_posun_se_netvari_jako_konkretni_mechanismus(mapper):
    word = mapper.parse_word("sun", "sula")
    proposal = SemanticEvaluator(OneShiftGraph("shift")).extension_candidates(Lexicon([word]))[0]

    assert proposal.mechanism is None
    assert proposal.kind == "shift"


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


def test_mechanismus_je_soucasti_auditni_udalosti(mapper):
    builder = GraphBuilder()
    states = EvolutionSimulator(
        EvolutionGraph(),
        mapper,
        semantic_evaluator=SemanticEvaluator(
            MechanismGraph(), shift_prob=1.0, concept_index=MechanismConceptIndex()
        ),
        graph_builder=builder,
        end_year=300,
        evolve_root=True,
    ).simulate(_root(mapper))

    started = [event for event in builder.events if event["kind"] == "semantic_change_started"]
    assert states["proto"].lexicon.words[0].polysemy == {"sky"}
    assert started[0]["mechanism"] == "metaphor"
    assert started[0]["mechanism_pressure"] == 1.0


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


def test_slabsi_synonym_vytvari_tlak_na_ztratu_vyznamu(mapper):
    weak = mapper.parse_word("sun", "sula")
    strong = mapper.parse_word("sun", "tara")
    weak.frequency, strong.frequency = 0.1, 1.0
    weak.lineage_id, strong.lineage_id = "weak", "strong"
    evaluator = SemanticEvaluator(EmptyGraph(), shift_prob=0.0, forget_prob=1.0, seed=1)

    candidates = evaluator.loss_candidates(Lexicon([weak, strong]))

    assert len(candidates) == 1
    assert candidates[0].kind == "loss"
    assert candidates[0].word_lineage_id == "weak"
    assert candidates[0].source_concept == "sun"
    assert candidates[0].target_concept is None
    assert candidates[0].competitor_lineage_id == "strong"
    assert candidates[0].pressure > 0.6
    assert evaluator.propose_changes(Lexicon([weak, strong]))[0].kind == "loss"


def test_vzacny_vyznam_bez_nahrady_se_nezapomene(mapper):
    only = mapper.parse_word("sun", "sula")
    only.frequency = 0.01
    evaluator = SemanticEvaluator(EmptyGraph(), shift_prob=0.0, forget_prob=1.0)

    assert evaluator.loss_candidates(Lexicon([only])) == []
    assert evaluator.propose_changes(Lexicon([only])) == []


def test_odlisny_registr_snizuje_konkurenci_synonym(mapper):
    weak = mapper.parse_word("sun", "sula")
    strong = mapper.parse_word("sun", "tara")
    weak.frequency, strong.frequency = 0.1, 1.0
    evaluator = SemanticEvaluator(EmptyGraph(), shift_prob=0.0, forget_prob=1.0)

    same_context = evaluator.loss_candidates(Lexicon([weak, strong]))[0].pressure
    weak.grammatical_features["lexical.register"] = "ritual"
    strong.grammatical_features["lexical.register"] = "ordinary"
    split_context = evaluator.loss_candidates(Lexicon([weak, strong]))[0].pressure

    assert split_context < same_context


def test_neprekryvajici_se_kontexty_synonyma_nevytesnuji(mapper):
    first = mapper.parse_word("sun", "sula")
    second = mapper.parse_word("sun", "tara")
    first.frequency, second.frequency = 0.1, 1.0
    first.grammatical_features = {
        "semantic.roles": "reference",
        "semantic.domains": "nature",
    }
    second.grammatical_features = {
        "semantic.roles": "event",
        "semantic.domains": "ritual",
    }
    evaluator = SemanticEvaluator(EmptyGraph(), shift_prob=0.0, forget_prob=1.0)

    assert evaluator.loss_candidates(Lexicon([first, second])) == []


def test_zuzovani_odstrani_jen_konkurencni_vyznam(mapper):
    weak = mapper.parse_word("star", "sula")
    weak.polysemy.add("sun")
    weak.frequency = 0.0
    strong = mapper.parse_word("sun", "tara")
    strong.frequency = 1.0
    root = State("proto", Inventory(), Lexicon([weak, strong]))
    builder = GraphBuilder()

    states = EvolutionSimulator(
        EvolutionGraph(),
        mapper,
        semantic_evaluator=SemanticEvaluator(EmptyGraph(), shift_prob=0.0, forget_prob=1.0),
        graph_builder=builder,
        end_year=400,
        evolve_root=True,
    ).simulate(root)

    result = states["proto"].lexicon.get_word("star")
    assert result is not None and result.active
    assert "sun" not in result.polysemy
    starts = [event for event in builder.events if event["kind"] == "semantic_change_started"]
    assert starts[0]["change_kind"] == "loss"
    assert starts[0]["competitor_lineage_id"] is not None


def _loss_event(weak, strong, *, duration=0):
    return SemanticChangeEvent(
        year=100,
        branch_id="proto",
        change_id="loss-1",
        word_lineage_id=weak.lineage_id,
        source_concept="sun",
        target_concept=None,
        kind="loss",
        duration=duration,
        pressure=1.0,
        evidence_weight=1.0,
        evidence_type="synonym-competition:heuristic",
        adoption_threshold=0.4,
        competitor_lineage_id=strong.lineage_id,
    )


def test_posledni_uziti_lexemu_muze_zaniknout_jen_s_nahradou(mapper):
    weak = mapper.parse_word("sun", "sula")
    strong = mapper.parse_word("sun", "tara")
    weak.lineage_id, strong.lineage_id = "weak", "strong"
    state = State("proto", Inventory(), Lexicon([weak, strong]))
    runtime = SemanticChangeRuntime()

    runtime.start(
        state,
        _loss_event(weak, strong),
        lambda *_: None,
        2,
        lambda *_: 1,
        lambda *_: {},
    )

    assert weak.active is False
    assert strong.active is True


def test_ztrata_se_zrusi_pokud_konkurent_mezitim_zmizi(mapper):
    weak = mapper.parse_word("sun", "sula")
    strong = mapper.parse_word("sun", "tara")
    weak.lineage_id, strong.lineage_id = "weak", "strong"
    state = State("proto", Inventory(), Lexicon([weak, strong]))
    runtime = SemanticChangeRuntime()
    queued = []
    runtime.start(
        state,
        _loss_event(weak, strong, duration=80),
        lambda _year, _priority, event: queued.append(event),
        2,
        lambda *_: 0,
        lambda *_: {},
    )
    strong.active = False
    final = next(
        event
        for event in queued
        if isinstance(event, SemanticChangeSpreadEvent) and event.progress == 1.0
    )

    runtime.spread(state, final, lambda *_: 0, lambda *_: {})

    assert weak.active is True
    assert "loss-1" not in runtime.changes

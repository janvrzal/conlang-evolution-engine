from cee.core.models import Inventory, Lexicon, State
from cee.engine.phonology import FeatureMapper
from cee.engine.simulator import EvolutionSimulator
from cee.engine.topology import EvolutionGraph
from cee.metrics.language_distance import compare_languages
from cee.metrics.divergence_audit import audit_branch_divergence
from cee.metrics.scenario_calibration import MetricTarget, calibrate_replicates, run_replicates


def _state(mapper, node_id, records):
    return State(
        node_id=node_id,
        inventory=Inventory(),
        lexicon=Lexicon(words=[mapper.parse_word(concept, ipa) for concept, ipa in records]),
    )


def test_branch_divergence_profile_changes_only_its_macro_rate():
    graph = EvolutionGraph()
    graph.node_configs = {
        "fast": {"divergence": {"phonological_rate": 2.0}},
        "slow": {"divergence": {"phonological_rate": 0.5}},
    }
    mapper = FeatureMapper()
    simulator = EvolutionSimulator(graph, mapper)

    fast = simulator._current_macro(_state(mapper, "fast", [("one", "pata")])).change_rate
    slow = simulator._current_macro(_state(mapper, "slow", [("one", "pata")])).change_rate
    assert fast / slow == 4.0


def test_distance_vector_keeps_cognacy_inventory_phonotactics_and_contact_separate():
    mapper = FeatureMapper()
    left = _state(mapper, "left", [("water", "pata"), ("fire", "miko")])
    right = _state(mapper, "right", [("water", "kata"), ("fire", "miko")])
    for word in left.lexicon.words + right.lexicon.words:
        word.lineage_id = f"root:{word.concept_id}"
    right.lexicon.words[1].source_id = "donor"
    right.affixation_strategy = "prefix"

    vector = compare_languages(left, right, mapper.render_word)

    assert vector.lexical.ldnd is not None
    assert vector.cognate.retention == 1.0
    assert vector.inventory_jaccard > 0
    assert vector.phonotactic_js >= 0
    assert vector.structural.distance == 0.5
    assert vector.contact_right.sources == {"donor": 1}
    assert vector.contact_right.domains == {"unspecified": 1}


def test_divergence_audit_reports_profile_and_realized_changes_separately():
    audit = audit_branch_divergence([
        {"kind": "branch_divergence_profile", "language_id": "a", "phonological_rate": 1.5},
        {"kind": "sound_change", "language_id": "a", "hit_count": 3},
        {"kind": "lexicon", "language_id": "a", "hit_count": 2},
        {"kind": "contact", "language_id": "a"},
    ])["a"]

    assert audit.profile["phonological_rate"] == 1.5
    assert (audit.sound_changes, audit.lexical_changes, audit.contact_events, audit.changed_words) == (1, 1, 1, 5)


def test_multiseed_calibration_uses_median_and_keeps_metrics_separate():
    result = calibrate_replicates(
        [{"lexical": {"ldnd": 0.6}, "contact": {"loan_ratio": 0.1}},
         {"lexical": {"ldnd": 0.8}, "contact": {"loan_ratio": 0.2}},
         {"lexical": {"ldnd": 0.7}, "contact": {"loan_ratio": 0.1}}],
        [MetricTarget("lexical.ldnd", 0.7, 0.1, 2), MetricTarget("contact.loan_ratio", 0.1, 0.1, 1)],
    )
    assert result.score == 0
    assert result.summaries["lexical.ldnd"].stddev > 0


def test_replicate_runner_returns_one_vector_per_seed_and_pair():
    mapper = FeatureMapper()
    def simulate(_seed):
        return {"a": _state(mapper, "a", [("one", "pata")]), "b": _state(mapper, "b", [("one", "kata")])}
    report = run_replicates([3, 4], simulate, [("a", "b")], mapper.render_word)
    assert report.seeds == (3, 4)
    assert len(report.vectors["a-b"]) == 2

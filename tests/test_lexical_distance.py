from cee.metrics.lexical_distance import asjp_ldnd, normalized_levenshtein


def test_normalized_levenshtein_is_zero_for_identical_forms():
    assert normalized_levenshtein("pata", "pata") == 0
    assert normalized_levenshtein("pata", "kata") == 0.25


def test_ldnd_corrects_same_meaning_distance_by_background_similarity():
    left = {"water": "pata", "fire": "miku", "sun": "lano"}
    right = {"water": "pata", "fire": "miko", "sun": "lani"}
    result = asjp_ldnd(left, right)

    assert result.shared_meanings == 3
    assert 0 < result.same_meaning_nld < result.different_meaning_nld
    assert result.ldnd is not None and 0 < result.ldnd < 1


def test_european_calibration_scenario_has_independent_roots_and_late_contacts():
    from cee.engine.parser import YamlParser

    graph = YamlParser.parse_topology("src/cee/data/scenarios/european-contact-calibration.yaml")
    roots = {node_id for node_id, cfg in graph.node_configs.items() if cfg.get("isProto")}

    assert roots == {"proto_germanic", "proto_romance", "proto_slavic"}
    assert all(edge.year >= 1066 for edge in graph.contact_edges)

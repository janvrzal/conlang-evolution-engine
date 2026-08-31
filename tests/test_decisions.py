from cee.engine.decisions import ChangeDecisionEngine


def test_stejna_semanticka_role_a_domena_zvysuji_tlak_homofonie(mapper):
    first = mapper.parse_word("hand", "pata")
    second = mapper.parse_word("arm", "pata")
    for word in (first, second):
        word.frequency = 0.9
        word.grammatical_features = {"semantic.roles": "reference", "semantic.domains": "body"}

    decision = ChangeDecisionEngine().assess_homophones([first, second])[0]
    assert decision.pressure == 0.9
    assert decision.evidence_level == "semantic-metadata"
    assert decision.action == "needs_legitimate_innovation"


def test_rozdilne_role_snizuji_tlak_bez_rucniho_pos(mapper):
    first = mapper.parse_word("hand", "pata")
    second = mapper.parse_word("see", "pata")
    for word in (first, second):
        word.frequency = 0.9
    first.grammatical_features = {"semantic.roles": "reference", "semantic.domains": "body"}
    second.grammatical_features = {"semantic.roles": "event", "semantic.domains": "perception"}

    decision = ChangeDecisionEngine().assess_homophones([first, second])[0]
    assert decision.pressure == 0.0
    assert decision.action == "monitor"

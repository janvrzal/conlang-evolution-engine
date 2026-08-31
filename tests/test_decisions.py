from cee.core.models import Inventory, Lexicon, State
from cee.engine.decisions import ChangeDecisionEngine
from cee.engine.rules import Rule


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


def test_caste_slovo_prijme_zvukovou_inovaci_drive_nez_okrajove(mapper):
    frequent = mapper.parse_word("common", "pata")
    rare = mapper.parse_word("rare", "pata")
    frequent.frequency, rare.frequency = 0.9, 0.1
    rule = Rule("lenice", {"cons": "+"}, {"voi": "+"})

    assert ChangeDecisionEngine.sound_change_adoption_threshold(frequent, rule, 0.5) < (
        ChangeDecisionEngine.sound_change_adoption_threshold(rare, rule, 0.5)
    )


def test_morfemova_hranice_zpomali_lexikalni_sireni(mapper):
    plain = mapper.parse_word("plain", "pata")
    boundary = mapper.parse_word("boundary", "pata")
    boundary.morpheme_boundaries = {1}
    rule = Rule("lenice", {"cons": "+"}, {"voi": "+"})

    assert ChangeDecisionEngine.sound_change_adoption_threshold(boundary, rule, 0.5) > (
        ChangeDecisionEngine.sound_change_adoption_threshold(plain, rule, 0.5)
    )


def test_funkcni_zatez_snizi_prioritu_kolapsu_kontrastu(mapper):
    unvoiced = mapper.parse_word("p", "apa")
    voiced = mapper.parse_word("b", "aba")
    state = State("x", Inventory(), Lexicon([unvoiced, voiced]))
    rule = Rule(
        "plošné odznělení b",
        target=dict(voiced.segments[1].features),
        action={"voi": "-"},
    )

    decision = ChangeDecisionEngine.assess_sound_change(state, rule, mapper)

    assert decision.contrast_retention == 0.5
    assert decision.pressure < 1.0

from cee.engine.rules import Rule
from cee.metrics.generator_validation import compare_profiles, profile_rules


def test_v2a_profil_rozeznava_typ_a_prostredi_zmeny():
    rules = [
        Rule("a", {}, {}, schema_id="lenition", env_before={"syl": "+"}, env_after={"syl": "+"}),
        Rule("b", {}, {}, schema_id="coda_loss", env_after={"_boundary": "+"}),
    ]
    profile = profile_rules(rules, years=500)

    assert profile.schemas == {"coda_loss": 1, "lenition": 1}
    assert profile.environments == {"medial_conditioned": 1, "word_final": 1}
    assert profile.changes_per_millennium == 4.0


def test_v2a_stejne_profily_maji_nulovou_vzdalenost():
    rules = [Rule("a", {}, {}, schema_id="lenition")]
    profile = profile_rules(rules, years=1000)

    assert compare_profiles(profile, profile) == {
        "schema_hellinger": 0.0,
        "comparable_schema_hellinger": 0.0,
        "attested_schema_coverage": 1.0,
        "environment_hellinger": 0.0,
        "rate_delta_per_millennium": 0.0,
    }

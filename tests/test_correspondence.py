from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.correspondence import (
    build_gled_correspondence_profile,
    correspondence_hellinger,
    profile_simulated_word_pairs,
)


def test_gled_profile_is_family_balanced_and_does_not_infer_direction(tmp_path):
    source = tmp_path / "gled.tsv"
    source.write_text(
        "FAMILY\tCOGSET\tID\tALIGNMENT\n"
        "A\ta.one\t1\tp a\n"
        "A\ta.one\t2\tp i\n"
        "A\ta.two\t3\tt a\n"
        "A\ta.two\t4\tt i\n"
        "B\tb.one\t5\tk a\n"
        "B\tb.one\t6\tk a\n",
        encoding="utf-8",
    )

    profile = build_gled_correspondence_profile(source)

    assert profile.forms == 6
    assert profile.cognate_sets == 3
    assert profile.families == 2
    assert profile.compared_pairs == 3
    assert profile.family_distribution == {"identity": 0.75, "substitution": 0.25}
    assert "insertion" not in profile.family_distribution


def test_cli_writes_correspondence_profile(tmp_path):
    source = tmp_path / "gled.tsv"
    source.write_text(
        "FAMILY\tCOGSET\tID\tALIGNMENT\nA\ta.one\t1\tp a\nA\ta.one\t2\tp i\n",
        encoding="utf-8",
    )
    output = tmp_path / "profile.json"

    result = CliRunner().invoke(
        app,
        ["calibrate", "correspondences", "--gled-tsv", str(source), "--out", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()


def test_simulated_pairs_are_aligned_and_compared_without_direction(mapper):
    word_a = mapper.parse_word("one", "pa")
    word_b = mapper.parse_word("one", "pi")

    profile = profile_simulated_word_pairs([(word_a, word_b)], mapper)

    assert profile == {"identity": 0.5, "substitution": 0.5}
    assert correspondence_hellinger(profile, profile) == 0.0

import pytest

from scripts.build_v2_typology import weighted_distribution


def test_genus_weighting_splits_only_languages_with_feature_data() -> None:
    languages = {
        "a1": {"ID": "a1", "Genus": "large-genus"},
        "a2": {"ID": "a2", "Genus": "large-genus"},
        "a3": {"ID": "a3", "Genus": "large-genus"},
        "b1": {"ID": "b1", "Genus": "small-genus"},
        "isolate": {"ID": "isolate", "Genus": ""},
        # Has a genus but no observation for this feature: must not affect A's
        # denominator or otherwise contribute weight.
        "missing": {"ID": "missing", "Genus": "large-genus"},
    }
    observations = [
        ("a1", "X"), ("a2", "X"), ("a3", "Y"),
        ("b1", "Y"), ("isolate", "X"),
    ]

    distribution, genus_sizes = weighted_distribution(
        observations, languages, {"X": "x", "Y": "y", "Z": "z"}
    )

    assert genus_sizes == {"large-genus": 3, "small-genus": 1, "__language__:isolate": 1}
    assert distribution == pytest.approx({"X": 5 / 9, "Y": 4 / 9, "Z": 0.0})

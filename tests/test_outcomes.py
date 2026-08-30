import json

from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.outcome_search import score_metrics
from cee.metrics.outcomes import build_outcome_profile


def _write_sample(tmp_path):
    languages = tmp_path / "languages.csv"
    languages.write_text(
        "ID,Family,Macroarea\n"
        "a,Fam-1,Eurasia\n"
        "b,Fam-1,Eurasia\n"
        "c,Fam-2,Africa\n"
        "d,Fam-2,Africa\n",
        encoding="utf-8",
    )
    forms = tmp_path / "forms.csv"
    forms.write_text(
        "Language_ID,Parameter_ID,Segments\n"
        "a,one,k a\n"
        "a,two,t r a\n"
        "a,three,k a\n"
        "b,one,k a\n"
        "b,two,s a\n"
        "c,one,m i\n"
        "c,two,n d a\n"
        "d,one,m i\n"
        "d,two,p l a\n",
        encoding="utf-8",
    )
    return forms, languages


def test_outcome_profile_groups_languages_and_cluster_bootstraps(tmp_path):
    forms, languages = _write_sample(tmp_path)

    profile = build_outcome_profile(forms, languages, bootstrap_replicates=100, bootstrap_seed=7)

    groups = {(group.kind, group.id): group for group in profile.groups}
    global_group = groups[("global", "global")]
    assert (global_group.languages, global_group.families) == (4, 2)
    assert groups[("macroarea", "Eurasia")].languages == 2
    assert groups[("family", "Fam-1")].languages == 2
    assert global_group.metrics["mean_segment_length"].interval_95 is not None
    assert global_group.metrics["wordlist_homophony_rate"].mean > 0


def test_outcome_profile_cli_writes_auditable_json(tmp_path):
    forms, languages = _write_sample(tmp_path)
    out = tmp_path / "outcomes.json"

    result = CliRunner().invoke(
        app,
        [
            "calibrate", "outcomes", "--forms", str(forms), "--languages", str(languages),
            "--out", str(out), "--bootstrap-replicates", "100",
        ],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert {group["kind"] for group in document["groups"]} == {
        "global", "macroarea", "family",
    }


def test_outcome_profile_joins_optional_phoible_inventory_metric(tmp_path):
    forms, languages = _write_sample(tmp_path)
    languages.write_text(
        languages.read_text(encoding="utf-8").replace("ID,Family,Macroarea", "ID,Family,Macroarea,Glottocode").replace(
            "a,Fam-1,Eurasia", "a,Fam-1,Eurasia,lang-a"
        ).replace("b,Fam-1,Eurasia", "b,Fam-1,Eurasia,lang-b").replace(
            "c,Fam-2,Africa", "c,Fam-2,Africa,lang-c"
        ).replace("d,Fam-2,Africa", "d,Fam-2,Africa,lang-d"),
        encoding="utf-8",
    )
    phoible = tmp_path / "phoible.csv"
    phoible.write_text(
        "InventoryID,Glottocode,Phoneme,Marginal\n"
        "1,lang-a,p,False\n1,lang-a,a,False\n1,lang-a,x,True\n"
        "2,lang-b,p,False\n2,lang-b,a,False\n"
        "3,lang-c,p,False\n3,lang-c,a,False\n"
        "4,lang-d,p,False\n4,lang-d,a,False\n",
        encoding="utf-8",
    )

    profile = build_outcome_profile(forms, languages, phoible, bootstrap_replicates=100)

    global_group = next(group for group in profile.groups if group.kind == "global")
    assert global_group.metrics["phoible_inventory_size"].mean == 2.0
    assert "phoible" in profile.source_checksums


def test_outcome_score_is_zero_inside_intervals():
    score, inside, compared = score_metrics(
        {"mean_segment_length": 4.5, "coda_segment_rate": 0.3},
        {
            "mean_segment_length": {"interval_95": [4.0, 5.0]},
            "coda_segment_rate": {"interval_95": [0.2, 0.4]},
        },
    )
    assert (score, inside, compared) == (0.0, 2, 2)

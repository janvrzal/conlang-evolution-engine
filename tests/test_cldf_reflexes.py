import csv

from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.cldf_reflexes import extract_reflex_candidates


def _forms(tmp_path):
    path = tmp_path / "forms.csv"
    path.write_text(
        "ID,Language_ID,Parameter_ID,Segments,Origin_ID,Relation\n"
        "proto-1,proto-x,water,w a t a,,\n"
        "child-1,child-x,water,w a d a,proto-1,inherited\n"
        "loan-1,child-y,water,v a t a,proto-1,borrowed\n",
        encoding="utf-8",
    )
    return path


def test_extracts_only_inherited_proto_reflexes(tmp_path):
    candidates = extract_reflex_candidates(_forms(tmp_path), "family-x", ["proto-x"])

    assert len(candidates) == 1
    assert candidates[0].proto_form == "w a t a"
    assert candidates[0].reflex_form == "w a d a"
    assert candidates[0].parameter_id == "water"


def test_cli_writes_auditable_candidate_queue(tmp_path):
    out = tmp_path / "candidates.csv"
    result = CliRunner().invoke(
        app,
        ["calibrate", "candidates", "--forms", str(_forms(tmp_path)), "--family-id", "family-x",
         "--proto-language", "proto-x", "--out", str(out)],
    )

    assert result.exit_code == 0, result.output
    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{
        "family_id": "family-x", "proto_form_id": "proto-1", "proto_language_id": "proto-x",
        "proto_form": "w a t a", "reflex_form_id": "child-1", "reflex_language_id": "child-x",
        "reflex_form": "w a d a", "parameter_id": "water", "relation": "inherited",
    }]

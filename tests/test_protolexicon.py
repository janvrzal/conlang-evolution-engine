import csv
import json

from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.protolexicon import extract_protolexicon


def _source(tmp_path):
    languages = tmp_path / "languages.csv"
    languages.write_text(
        "ID,Name,Is_Proto\nproto-x,Proto X,true\nchild-x,Child X,false\n",
        encoding="utf-8",
    )
    forms = tmp_path / "forms.csv"
    forms.write_text(
        "ID,Language_ID,Parameter_ID,Segments,Doubt\n"
        "x-1,proto-x,water,w a + t a,false\n"
        "x-2,proto-x,water,v a t a,false\n"
        "x-3,proto-x,fire,k i,true\n"
        "x-4,child-x,water,w a t a,false\n",
        encoding="utf-8",
    )
    return forms, languages


def test_extract_protolexicon_keeps_one_parseable_form_per_concept(tmp_path):
    forms, languages = _source(tmp_path)

    export = extract_protolexicon(forms, languages, "proto-x")

    assert export.records == [{"id": "water", "ipa_proto": "wata"}]
    assert export.skipped_duplicate_concepts == 1
    assert export.skipped_doubtful == 1


def test_protolexicon_cli_writes_csv_and_provenance(tmp_path):
    forms, languages = _source(tmp_path)
    out = tmp_path / "proto.csv"
    metadata = tmp_path / "proto.metadata.json"

    result = CliRunner().invoke(
        app,
        [
            "calibrate", "protolexicon", "--forms", str(forms), "--languages", str(languages),
            "--proto-language-id", "proto-x", "--out", str(out), "--metadata-out", str(metadata),
        ],
    )

    assert result.exit_code == 0, result.output
    with out.open(encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"id": "water", "ipa_proto": "wata"}]
    document = json.loads(metadata.read_text(encoding="utf-8"))
    assert document["proto_language"]["name"] == "Proto X"
    assert document["records"] == 1

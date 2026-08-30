import json

import pytest
from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.global_baseline import (
    ChangeObservation,
    CorpusSource,
    train_from_manifest,
    train_global_baseline,
)


def _source() -> CorpusSource:
    return CorpusSource("open", "changes.csv", "CC-BY-4.0", "2026.1", "Open corpus")


def test_globally_balanced_training_does_not_reward_the_largest_family():
    rows = [
        *(ChangeObservation("lenition", "conditioned", "family-a", "open") for _ in range(100)),
        ChangeObservation("vowel_shift", "unconditional", "family-b", "open"),
    ]
    baseline = train_global_baseline(rows, [_source()], {"open": "abc"}, ["lenition", "vowel_shift"])

    assert baseline.observations == 101
    assert baseline.families == 2
    assert baseline.schema_distribution == {"lenition": 0.5, "vowel_shift": 0.5}
    assert baseline.schema_multipliers == {"lenition": 1.0, "vowel_shift": 1.0}


def test_unseen_schema_is_smoothed_not_disabled():
    row = ChangeObservation("lenition", "conditioned", "family-a", "open")
    baseline = train_global_baseline([row], [_source()], {"open": "abc"}, ["lenition", "apocope"])

    assert 0 < baseline.schema_multipliers["apocope"] < baseline.schema_multipliers["lenition"]


def test_noncommercial_source_is_rejected():
    source = CorpusSource("closed", "changes.csv", "CC-BY-NC-SA-4.0", "1", "Not usable")
    row = ChangeObservation("lenition", "conditioned", "family-a", "closed")

    with pytest.raises(ValueError, match="NC/SA"):
        train_global_baseline([row], [source], {"closed": "abc"}, ["lenition"])


def test_manifest_records_provenance_and_csv_checksum(tmp_path):
    (tmp_path / "changes.csv").write_text(
        "schema_id,environment,family_id,language_id\nlenition,conditioned,fam-a,lang-a\n",
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "lexibank-curation",
                        "path": "changes.csv",
                        "license": "CC-BY-4.0",
                        "version": "v1",
                        "citation": "Curated open observations",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    baseline = train_from_manifest(tmp_path / "manifest.json", ["lenition", "apocope"])

    assert baseline.observations == 1
    assert baseline.source_checksums["lexibank-curation"]


def test_cli_trains_and_measures_a_calibration(tmp_path):
    (tmp_path / "changes.csv").write_text(
        "schema_id,environment,family_id\nlenition,conditioned,fam-a\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": [
                    {
                        "id": "open",
                        "path": "changes.csv",
                        "license": "CC-BY-4.0",
                        "version": "1",
                        "citation": "Open",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "baseline.json"
    runner = CliRunner()

    trained = runner.invoke(app, ["calibrate", "global", "--manifest", str(manifest), "--out", str(output)])
    measured = runner.invoke(
        app,
        [
            "calibrate",
            "measure",
            "--baseline",
            str(output),
            "--preset",
            "src/cee/data/presets/fantasy_preset.yaml",
            "--runs",
            "1",
        ],
    )

    assert trained.exit_code == 0, trained.output
    assert output.exists()
    assert measured.exit_code == 0, measured.output
    assert "Hellinger (typ změny)" in measured.output

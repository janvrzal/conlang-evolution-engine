from typer.testing import CliRunner

from cee.cli.main import app
from cee.metrics.local_research import build_local_research_profile, classify_change
from cee.metrics.schema_profiles import save_local_schema_profile
from cee.pipeline import SimulationConfig, build_global_schema_multipliers


def test_classifier_stays_conservative():
    assert classify_change("t", "d", "V_V") == "lenition"
    assert classify_change("a", "∅", "_#") == "apocope"
    assert classify_change("q", "ʡ") is None


def test_cli_creates_only_acknowledged_local_profile(tmp_path):
    data = tmp_path / "changes.csv"
    data.write_text("source,target,context\nt,d,V_V\na,∅,_#\n", encoding="utf-8")
    out = tmp_path / "local.json"
    args = ["calibrate", "research-profile", "--changes", str(data), "--out", str(out)]
    assert CliRunner().invoke(app, args).exit_code != 0
    result = CliRunner().invoke(app, [*args, "--acknowledge-local-research"])
    assert result.exit_code == 0, result.output
    assert '"kind": "user-local-research"' in out.read_text(encoding="utf-8")


def test_local_profile_can_be_selected_for_a_simulation(tmp_path):
    data = tmp_path / "changes.csv"
    data.write_text("source,target,context\nt,d,V_V\n", encoding="utf-8")
    profile, _, _ = build_local_research_profile(data, "research", "Research")
    profile_path = tmp_path / "research.json"
    save_local_schema_profile(profile, profile_path)

    config = SimulationConfig(local_schema_profile_path=str(profile_path))
    assert build_global_schema_multipliers(config) == profile.schema_multipliers

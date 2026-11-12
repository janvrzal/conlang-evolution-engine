"""Endpointy enginu v2 (``/api/v2``): schéma, ověření a běh s průběhem.

Volají se přímo funkce routeru, jako v ``test_api.py`` (bez HTTP klienta).
"""

import time

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from cee.api import v2  # noqa: E402
from cee.api.server import app, health_check  # noqa: E402

SPEC = {
    "end_year": 150,
    "languages": [{"id": "a"}, {"id": "b"}],
    "regions": [
        {"id": "c", "position": [0, 0], "density": 2, "neighbours": ["x"], "language": "a", "villages": 2},
        {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 2},
    ],
    "events": [{"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c", "policy": "enforced"}],
    "semantics": False,
}


def wait(run_id):
    for _ in range(1200):
        status = v2.run_status(run_id)
        if status["status"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("běh neskončil")


def test_router_je_v_aplikaci():
    paths = set(app.openapi()["paths"])
    assert {"/api/v2/schema", "/api/v2/validate", "/api/v2/runs", "/api/v2/runs/{run_id}", "/api/v2/runs/{run_id}/names"} <= paths


def test_schema_a_overeni():
    schema = v2.schema()
    assert schema["format"] == "cee-v2-world/1"
    assert "state" in schema["event_kinds"] and "terrain_access" in schema["levels"]
    parameters = {item["name"]: item for item in schema["parameters"]["items"]}
    assert len(parameters) == 86 and schema["parameters"]["groups"]
    assert parameters["capital_prestige"]["default"] == 2.0 and parameters["capital_prestige"]["kind"] == "number"
    assert parameters["capital_prestige"]["role"] == "active"
    assert all("role" in p and p["role"] in {"world", "active", "fixed"} for p in parameters.values())
    assert parameters["policy_levels"]["levels"] == ["enforced", "promoted", "tolerant"]
    assert parameters["channel_domains"]["min"] == 0.0 and parameters["channel_domains"]["description"]
    assert v2.validate(SPEC) == {"ok": True, "issues": []}
    bad_parameter = v2.validate({**SPEC, "parameters": {"capital_prestige": "x"}})
    assert bad_parameter["issues"][0]["path"] == "parameters.capital_prestige"
    bad = v2.validate({**SPEC, "events": [{"kind": "collapse", "year": 0, "state": "z"}]})
    assert bad["ok"] is False and bad["issues"][0]["path"] == "events.0"


def test_beh_s_prubehem_a_vysledkem():
    with pytest.raises(HTTPException) as invalid:
        v2.start_run({**SPEC, "regions": []})
    assert invalid.value.status_code == 422 and invalid.value.detail["issues"]
    run_id = v2.start_run(SPEC)["run_id"]
    status = wait(run_id)
    assert status["status"] == "done" and status["progress"] == 1.0 and status["frames"]
    assert v2.run_status(run_id, since=status["frame_count"])["frames"] == []
    result = v2.run_result(run_id)
    assert result["format"] == "cee-v2/1" and result["states"][0]["id"] == "k"
    with pytest.raises(HTTPException) as missing:
        v2.run_status("nic")
    assert missing.value.status_code == 404


def test_generator_jmen_sidel_a_osob():
    run_id = v2.start_run(SPEC)["run_id"]
    assert wait(run_id)["status"] == "done"
    places = v2.run_names(run_id, {"region": "c", "year": 0, "count": 3, "urban": True})
    assert places["region"] == "c" and places["tradition"] and len(places["names"]) == 3
    first = places["names"][0]
    assert first["name"] and first["founded"]["year"] == 0 and first["founded"]["meaning"]
    assert first["timeline"][0]["cause"] == "founded"
    # stejný dotaz dá stejná jména, jiný pokus jiná
    assert v2.run_names(run_id, {"region": "c", "year": 0, "count": 3})["names"] == places["names"]
    other = v2.run_names(run_id, {"region": "c", "year": 0, "count": 3, "attempt": 1})["names"]
    assert [n["name"] for n in other] != [n["name"] for n in places["names"]]
    people = v2.run_names(run_id, {"region": "x", "year": 100, "count": 2, "kind": "person"})
    assert people["kind"] == "person" and len(people["names"]) == 2 and people["tradition"]
    with pytest.raises(HTTPException) as unknown:
        v2.run_names(run_id, {"region": "nic", "year": 0})
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        v2.run_names("nic", {"region": "c", "year": 0})
    assert missing.value.status_code == 404


def test_udalost_s_polem_from_dojde_do_enginu():
    # pydantic má pole jako ``from_`` s aliasem ``from``; engine dostane ``from``
    spec = {**SPEC, "events": [*SPEC["events"], {"kind": "settlement", "year": 50, "from": "x", "to": "c", "share": 0.1}]}
    assert v2.validate(spec)["ok"] is True
    run_id = v2.start_run(spec)["run_id"]
    assert wait(run_id)["status"] == "done"


def test_nedokonceny_beh_nema_vysledek_a_jde_zrusit():
    run_id = v2.start_run({**SPEC, "end_year": 5000})["run_id"]
    with pytest.raises(HTTPException) as early:
        v2.run_result(run_id)
    assert early.value.status_code == 409
    v2.cancel_run(run_id)
    assert wait(run_id)["status"] == "cancelled"


def test_engine_skonci_s_aplikaci():
    import subprocess
    import sys

    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; from cee.api.server import _exit_with_parent; "
         f"_exit_with_parent({parent.pid}, interval=0.1); time.sleep(10)"],
    )
    parent.wait()
    assert child.wait(timeout=8) == 0


def test_overeni_vraci_varovani_slovniku_s_vaznosti_a_beh_je_nezastavi():
    assert v2.schema()["vocabulary"]["default"] == 149
    warned = v2.validate({**SPEC, "vocabulary": 200})
    assert warned["ok"] is True
    assert [(item["path"], item["severity"]) for item in warned["issues"]] == [("vocabulary", "warning")]
    mixed = v2.validate({**SPEC, "vocabulary": 200, "concepts": [{"id": "a", "related": [{"concept": "nic"}]}]})
    assert mixed["ok"] is False
    assert [item["severity"] for item in mixed["issues"]] == ["error", "warning", "warning"]
    assert v2.start_run({**SPEC, "vocabulary": 200, "end_year": 5})["status"] in {"running", "done"}


def test_health_vraci_v2_binding_fresh():
    health = health_check()
    assert health["v2_binding_fresh"] is True


def test_schema_role_filtruje_parametry_a_obsahuje_parameters_by_role():
    world_schema = v2.schema(role="world")
    assert len(world_schema["parameters"]["items"]) == 12

    active_schema = v2.schema(role="active")
    assert len(active_schema["parameters"]["items"]) == 24

    all_schema = v2.schema()
    assert "parameters_by_role" in all_schema
    by_role = all_schema["parameters_by_role"]
    assert set(by_role.keys()) == {"world", "active", "fixed"}
    assert len(by_role["world"]["items"]) == 12
    assert len(by_role["active"]["items"]) == 24


def test_persistence_behu_na_disk_a_list_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("CEE_V2_RUNS_DIR", str(tmp_path))
    v2._runs.clear()

    run_id = v2.start_run(SPEC)["run_id"]
    status = wait(run_id)
    assert status["status"] == "done"

    # Seznam běhů v paměti
    runs = v2.list_runs()
    assert len(runs) >= 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["status"] == "done"
    assert runs[0]["end_year"] == 150

    # Výsledek byl uložen na disk
    saved_file = tmp_path / f"{run_id}.json.gz"
    assert saved_file.is_file()
    result_before = v2.run_result(run_id)

    # Simulace restartu serveru (vyčištění paměti)
    v2._runs.clear()
    assert run_id not in v2._runs

    # list_runs najde běh z disku
    runs_after = v2.list_runs()
    assert len(runs_after) >= 1
    assert any(r["run_id"] == run_id for r in runs_after)

    # run_status i run_result po restartu vrátí data z disku místo 404
    status_after = v2.run_status(run_id)
    assert status_after["status"] == "done"
    assert status_after["progress"] == 1.0

    result_after = v2.run_result(run_id)
    assert result_after == result_before

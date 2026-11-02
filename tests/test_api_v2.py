"""Endpointy enginu v2 (``/api/v2``): schéma, ověření a běh s průběhem.

Volají se přímo funkce routeru, jako v ``test_api.py`` (bez HTTP klienta).
"""

import time

import pytest

pytest.importorskip("fastapi")
from fastapi import HTTPException  # noqa: E402

from cee.api import v2  # noqa: E402
from cee.api.server import app  # noqa: E402

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
    assert {"/api/v2/schema", "/api/v2/validate", "/api/v2/runs", "/api/v2/runs/{run_id}"} <= paths


def test_schema_a_overeni():
    schema = v2.schema()
    assert schema["format"] == "cee-v2-world/1"
    assert "state" in schema["event_kinds"] and "terrain_access" in schema["levels"]
    assert v2.validate(SPEC) == {"ok": True, "issues": []}
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

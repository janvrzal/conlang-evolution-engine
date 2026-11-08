"""HTTP endpointy enginu v2: schéma světa, ověření a běhy s průběhem.

UI pošle popis světa (``cee.v2.spec.WorldSpec`` jako JSON), spustí běh,
průběžně se ptá na stav a nové snímky a na konci si vezme úplný export.
Běhy žijí v paměti serveru; drží se jen několik posledních.
"""

import gzip
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from cee.v2 import runner
from cee.v2.parameters import parameter_schema
from cee.v2.runner import check
from cee.v2.spec import (
    EVENT_KINDS,
    FORMAT,
    SpecError,
    WorldSpec,
    errors,
    levels,
    vocabulary_options,
)

router = APIRouter(prefix="/api/v2", tags=["engine-v2"])

#: Kolik dokončených běhů server drží v paměti.
KEEP_RUNS = 8
_runs: dict[str, runner.Run] = {}
_lock = threading.Lock()


def _runs_dir() -> Path:
    raw = os.environ.get("CEE_V2_RUNS_DIR")
    path = Path(raw) if raw else (Path.home() / ".cee" / "v2_runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_run_to_disk(run: runner.Run) -> None:
    if run.status != "done" or run.result is None:
        return
    runs_dir = _runs_dir()
    path = runs_dir / f"{run.id}.json.gz"
    if path.exists():
        return
    payload = {
        "id": run.id,
        "status": run.status,
        "started": run.started,
        "start_year": run.spec.start_year,
        "end_year": run.spec.end_year,
        "seconds": round(run.seconds, 2),
        "result": run.result,
    }
    tmp_path = runs_dir / f"{run.id}.tmp.{uuid.uuid4().hex}"
    with gzip.open(tmp_path, "wt", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp_path.replace(path)


def _load_run_from_disk(run_id: str) -> dict[str, Any] | None:
    path = _runs_dir() / f"{run_id}.json.gz"
    if not path.is_file():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _issues(issues: list[Any]) -> list[dict[str, str]]:
    return [{"path": issue.path, "message": issue.message, "severity": issue.severity} for issue in issues]


@router.get("/schema")
def schema(role: str | None = None):
    """JSON schéma popisu světa, možnosti slovních úrovní, druhy událostí a metaparametry pro UI."""
    return {
        "format": FORMAT,
        "json_schema": WorldSpec.model_json_schema(),
        "levels": levels(),
        "parameters": parameter_schema(role=role),
        "parameters_by_role": {
            "world": parameter_schema(role="world"),
            "active": parameter_schema(role="active"),
            "fixed": parameter_schema(role="fixed"),
        },
        "event_kinds": list(EVENT_KINDS),
        "vocabulary": vocabulary_options(runner.native().vocabulary_max_size()),
    }


@router.post("/validate")
def validate(spec: dict[str, Any]):
    """Chyby a varování popisu světa s cestou k poli.

    Každá položka má ``severity``: ``error`` (svět nejde postavit) nebo ``warning``
    (běh nezastaví, jen upozorní; například že jiný slovník dá jiné výsledky než
    výchozí). ``ok`` je pravda, když nejsou chyby. Chyby jdou před varováními.
    """
    found = check(spec)
    return {"ok": not errors(found), "issues": _issues(found)}


def _forget_old() -> None:
    finished = sorted((run for run in _runs.values() if run.status != "running"), key=lambda run: run.started)
    for run in finished[:max(0, len(finished) - KEEP_RUNS)]:
        _save_run_to_disk(run)
        del _runs[run.id]


@router.get("/runs")
def list_runs():
    """Seznam známých běhů z paměti i z disku, seřazený od nejnovějšího."""
    runs_map: dict[str, dict[str, Any]] = {}
    with _lock:
        for run in _runs.values():
            if run.status == "done" and run.result is not None:
                _save_run_to_disk(run)
            runs_map[run.id] = {
                "run_id": run.id,
                "status": run.status,
                "started": run.started,
                "start_year": run.spec.start_year,
                "end_year": run.spec.end_year,
                "seconds": round(run.seconds, 2),
            }

    runs_dir = _runs_dir()
    if runs_dir.is_dir():
        for path in runs_dir.glob("*.json.gz"):
            run_id = path.name[:-8] if path.name.endswith(".json.gz") else path.stem
            if run_id in runs_map:
                continue
            meta = _load_run_from_disk(run_id)
            if meta is not None:
                runs_map[run_id] = {
                    "run_id": meta.get("id", run_id),
                    "status": meta.get("status", "done"),
                    "started": meta.get("started", 0.0),
                    "start_year": meta.get("start_year"),
                    "end_year": meta.get("end_year"),
                    "seconds": meta.get("seconds", 0.0),
                }

    return sorted(runs_map.values(), key=lambda item: item["started"], reverse=True)


@router.post("/runs", status_code=202)
def start_run(spec: dict[str, Any]):
    """Spustí běh na pozadí; neplatný popis vrátí 422 se seznamem chyb."""
    run_id = uuid.uuid4().hex[:12]
    try:
        run = runner.start(run_id, spec)
    except SpecError as error:
        raise HTTPException(status_code=422, detail={"issues": _issues(error.issues)}) from error
    with _lock:
        _forget_old()
        _runs[run_id] = run
    return {"run_id": run_id, "status": run.status}


def _run(run_id: str) -> runner.Run:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Běh nebyl nalezen (server ho nedrží nebo byl restartován).")
    return run


@router.get("/runs/{run_id}")
def run_status(run_id: str, since: int = 0):
    """Stav běhu a snímky od indexu ``since`` (kolik jich klient už má)."""
    with _lock:
        run = _runs.get(run_id)
    if run is not None:
        if run.status == "done" and run.result is not None:
            _save_run_to_disk(run)
        return run.status_view(max(0, since))

    data = _load_run_from_disk(run_id)
    if data is not None:
        return {
            "id": data.get("id", run_id),
            "status": data.get("status", "done"),
            "year": float(data.get("end_year") or 0.0),
            "progress": 1.0,
            "start_year": data.get("start_year"),
            "end_year": data.get("end_year"),
            "seconds": data.get("seconds", 0.0),
            "error": None,
            "frame_count": 0,
            "frames": [],
        }

    raise HTTPException(status_code=404, detail="Běh nebyl nalezen (server ho nedrží nebo byl restartován).")


@router.get("/runs/{run_id}/result")
def run_result(run_id: str):
    """Úplný export dokončeného běhu (409, dokud běh neskončil)."""
    with _lock:
        run = _runs.get(run_id)
    if run is not None:
        if run.status != "done" or run.result is None:
            raise HTTPException(status_code=409, detail=f"Běh není dokončený (stav {run.status}).")
        _save_run_to_disk(run)
        return run.result

    data = _load_run_from_disk(run_id)
    if data is not None:
        if data.get("status") != "done" or data.get("result") is None:
            raise HTTPException(status_code=409, detail=f"Běh není dokončený (stav {data.get('status')}).")
        return data["result"]

    raise HTTPException(status_code=404, detail="Běh nebyl nalezen (server ho nedrží nebo byl restartován).")


@router.delete("/runs/{run_id}")
def cancel_run(run_id: str):
    """Zruší běh; projeví se po dokončení rozpracovaného kroku."""
    with _lock:
        run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Běh nebyl nalezen (server ho nedrží nebo byl restartován).")
    run.cancel()
    return {"run_id": run_id, "status": run.status}

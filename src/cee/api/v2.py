"""HTTP endpointy enginu v2: schéma světa, ověření a běhy s průběhem.

UI pošle popis světa (``cee.v2.spec.WorldSpec`` jako JSON), spustí běh,
průběžně se ptá na stav a nové snímky a na konci si vezme úplný export.
Běhy žijí v paměti serveru; drží se jen několik posledních.
"""

import threading
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from cee.v2 import runner
from cee.v2.parameters import Parameters, parameter_schema
from cee.v2.spec import (
    EVENT_KINDS,
    FORMAT,
    SpecError,
    WorldSpec,
    check,
    errors,
    levels,
    vocabulary_options,
)

router = APIRouter(prefix="/api/v2", tags=["engine-v2"])

#: Kolik dokončených běhů server drží v paměti.
KEEP_RUNS = 8
_runs: dict[str, runner.Run] = {}
_lock = threading.Lock()


def _issues(issues: list[Any]) -> list[dict[str, str]]:
    return [{"path": issue.path, "message": issue.message, "severity": issue.severity} for issue in issues]


@router.get("/schema")
def schema():
    """JSON schéma popisu světa, možnosti slovních úrovní, druhy událostí a metaparametry pro UI."""
    defaults = Parameters()
    return {
        "format": FORMAT,
        "json_schema": WorldSpec.model_json_schema(),
        "levels": levels(defaults),
        "parameters": parameter_schema(),
        "event_kinds": list(EVENT_KINDS),
        "vocabulary": vocabulary_options(),
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
        del _runs[run.id]


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
    return _run(run_id).status_view(max(0, since))


@router.get("/runs/{run_id}/result")
def run_result(run_id: str):
    """Úplný export dokončeného běhu (409, dokud běh neskončil)."""
    run = _run(run_id)
    if run.status != "done" or run.result is None:
        raise HTTPException(status_code=409, detail=f"Běh není dokončený (stav {run.status}).")
    return run.result


@router.delete("/runs/{run_id}")
def cancel_run(run_id: str):
    """Zruší běh; projeví se po dokončení rozpracovaného kroku."""
    run = _run(run_id)
    run.cancel()
    return {"run_id": run_id, "status": run.status}

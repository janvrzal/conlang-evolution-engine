"""HTTP endpointy pro jeden persistovaný běh simulace."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from cee.storage.genealogy import RunNotFoundError, get_genealogy_store

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _store_or_503():
    try:
        return get_genealogy_store()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{run_id}/languages/{node_id}")
def get_language(run_id: str, node_id: str, year: Optional[int] = None):
    """Vrátí aktuální řez slovníkem jazyka v daném roce."""
    try:
        return {"status": "success", "words": _store_or_503().language(run_id, node_id, year)}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc


@router.get("/{run_id}/isogloss/{concept_id}")
def get_isogloss(run_id: str, concept_id: str, year: Optional[int] = None):
    try:
        return {"status": "success", "isogloss": _store_or_503().isogloss(run_id, concept_id, year)}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc


@router.get("/{run_id}/words/{word_id}/trace")
def get_word_trace(run_id: str, word_id: str):
    try:
        return {"status": "success", "trace": _store_or_503().word_trace(run_id, word_id)}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc


@router.get("/{run_id}/export")
def export_run(run_id: str):
    """Strojově čitelný export celé genealogie, nezávislý na backendu."""
    try:
        return _store_or_503().export(run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc

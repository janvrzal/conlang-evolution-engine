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


@router.get("/{run_id}/languages/{node_id}/page")
def get_language_page(
    run_id: str,
    node_id: str,
    year: Optional[int] = None,
    offset: int = 0,
    limit: int = 100,
    query: str = "",
    register: Optional[str] = None,
    community: Optional[str] = None,
    lexical_class: Optional[str] = None,
):
    """Stránkovaný slovník pro UI; nikdy neposílá tisíce položek naslepo."""
    try:
        words = _store_or_503().language(run_id, node_id, year)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc

    def feature(word, key: str) -> str:
        return str(word.get("grammatical_features", {}).get(key, ""))

    query = query.strip().lower()
    filtered = [
        word
        for word in words
        if (
            not query
            or query
            in " ".join(
                [str(word.get("to", "")), str(word.get("concept_id", "")), *word.get("polysemy", [])]
            ).lower()
        )
        and (not register or feature(word, "lexical.register") == register)
        and (not community or feature(word, "social.group") == community)
        and (not lexical_class or feature(word, "lexical.class") == lexical_class)
    ]
    safe_offset = max(0, offset)
    safe_limit = max(1, min(250, limit))
    form_counts: dict[str, int] = {}
    concept_counts: dict[str, int] = {}
    for word in filtered:
        form_counts[word["to"]] = form_counts.get(word["to"], 0) + 1
        concept_counts[word["concept_id"]] = concept_counts.get(word["concept_id"], 0) + 1
    return {
        "status": "success",
        "words": filtered[safe_offset : safe_offset + safe_limit],
        "total": len(filtered),
        "next_offset": safe_offset + safe_limit if safe_offset + safe_limit < len(filtered) else None,
        "facets": {
            "registers": sorted({feature(word, "lexical.register") for word in words if feature(word, "lexical.register")}),
            "communities": sorted({feature(word, "social.group") for word in words if feature(word, "social.group")}),
            "lexical_classes": sorted({feature(word, "lexical.class") for word in words if feature(word, "lexical.class")}),
            "homonym_forms": sorted(form for form, count in form_counts.items() if count > 1),
            "synonym_concepts": sorted(concept for concept, count in concept_counts.items() if count > 1),
        },
    }


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


@router.get("/{run_id}/grammars/{node_id}")
def get_grammar(run_id: str, node_id: str):
    """Markdownový gramatický náčrt konkrétní výsledné větve."""
    try:
        grammars = _store_or_503().export(run_id).get("artifacts", {}).get("grammars", {})
        if node_id not in grammars:
            raise HTTPException(status_code=404, detail="Gramatika větve nebyla nalezena.")
        return {"status": "success", "grammar_md": grammars[node_id]}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc


@router.get("/{run_id}/metrics")
def get_run_metrics(run_id: str):
    """Auditovatelný profil skutečně aplikovaných pravidel daného běhu."""
    try:
        return {"status": "success", "metrics": _store_or_503().export(run_id).get("artifacts", {}).get("metrics", {})}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc


@router.get("/{run_id}/edges/{child_id}/rules")
def get_edge_rules(run_id: str, child_id: str):
    """Seznam zvukových zákonů aplikovaných na větev vedoucí k uzlu."""
    try:
        events = _store_or_503().export(run_id).get("events", [])
        rules = [
            {key: event.get(key) for key in ("year", "rule", "schema_id", "hit_count", "deleted_segments")}
            for event in events
            if event.get("kind") == "sound_change" and event.get("language_id") == child_id
        ]
        return {"status": "success", "rules": rules}
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Výsledek simulace nebyl nalezen.") from exc

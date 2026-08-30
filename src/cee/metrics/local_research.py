"""Lokální transformace uživatelem dodaných záznamů změn na pracovní profil."""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from cee.engine.schemas import SCHEMA_REGISTRY
from cee.metrics.schema_profiles import SchemaProfile

_EMPTY = {"", "∅", "Ø", "0", "null"}
_VOWELS = set("aeiouyəɛɔɨʉɯɪʊœøæɑɒ")
_LENITION = {("p", "b"), ("t", "d"), ("k", "ɡ"), ("g", "ɣ"), ("s", "z"), ("f", "v")}


def classify_change(source: str, target: str, context: str = "") -> str | None:
    """Konzervativní klasifikace; neznámé řádky zůstávají mimo váhy."""
    source, target, context = source.strip(), target.strip(), context.strip()
    if target.lower() in _EMPTY and source.lower() not in _EMPTY:
        return "apocope" if "_#" in context.replace(" ", "") else "syncope"
    if source.lower() in _EMPTY and target.lower() not in _EMPTY:
        return "epenthesis"
    if (source, target) in _LENITION:
        return "lenition"
    if source and target and any(char in _VOWELS for char in source) and any(char in _VOWELS for char in target):
        return "vowel_shift"
    return None


def build_local_research_profile(
    path: str | Path, profile_id: str, label: str, source_column: str = "source",
    target_column: str = "target", context_column: str = "context",
) -> tuple[SchemaProfile, int, int]:
    """Vytvoří pouze lokální profil; vrací profil, použitá a přeskočená pozorování."""
    source_path = Path(path)
    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {source_column, target_column}
        if reader.fieldnames is None or (missing := required - set(reader.fieldnames)):
            raise ValueError(f"Vstup nemá sloupce: {sorted(missing)}")
        rows = list(reader)
    counts = Counter(classify_change(row[source_column], row[target_column], row.get(context_column, "")) for row in rows)
    skipped = counts.pop(None, 0)
    if not counts:
        raise ValueError("Žádný řádek nešel konzervativně přiřadit ke schématu CEE.")
    total = sum(counts.values())
    smoothing = 0.25
    keys = sorted(SCHEMA_REGISTRY)
    denominator = total + smoothing * len(keys)
    multipliers = {key: round(((counts.get(key, 0) + smoothing) / denominator) * len(keys), 8) for key in keys}
    checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return SchemaProfile(
        id=profile_id, kind="user-local-research", label=label,
        description="Lokální výzkumný profil vytvořený z uživatelem dodaných změn.",
        schema_multipliers=multipliers, license="user-supplied",
        provenance=f"local input SHA-256: {checksum}; classified={total}; skipped={skipped}",
    ), total, skipped

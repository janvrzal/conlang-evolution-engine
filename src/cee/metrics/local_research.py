"""Lokální transformace uživatelem dodaných záznamů změn na pracovní profil."""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from cee.engine.schemas import SCHEMA_REGISTRY
from cee.metrics.generator_validation import GeneratorProfile
from cee.metrics.schema_profiles import SchemaProfile

_EMPTY = {"", "∅", "Ø", "0", "null"}
_VOWELS = set("aeiouyəɛɔɨʉɯɪʊœøæɑɒ")
_LENITION = {("p", "b"), ("t", "d"), ("k", "ɡ"), ("g", "ɣ"), ("s", "z"), ("f", "v")}


def _read_rows(
    path: str | Path,
    source_column: str,
    target_column: str,
    context_column: str,
) -> list[dict[str, str]]:
    source_path = Path(path)
    with source_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {source_column, target_column}
        if reader.fieldnames is None or (missing := required - set(reader.fieldnames)):
            raise ValueError(f"Vstup nemá sloupce: {sorted(missing)}")
        return [
            {
                "source": row[source_column],
                "target": row[target_column],
                "context": row.get(context_column, ""),
            }
            for row in reader
        ]


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


def classify_environment(context: str) -> str:
    """Převede zápis kontextu Indexu na společnou osu V2a."""
    compact = context.replace(" ", "")
    if "_#" in compact:
        return "word_final"
    if "#_" in compact:
        return "word_initial"
    return "conditioned" if compact else "unconditional"


def profile_local_research_changes(
    path: str | Path,
    source_column: str = "source",
    target_column: str = "target",
    context_column: str = "context",
) -> tuple[GeneratorProfile, int, int]:
    """Profiluje jen záznamy, které lze přiřadit bez lingvistické domněnky."""
    schema_counts: Counter[str] = Counter()
    environment_counts: Counter[str] = Counter()
    skipped = 0
    for row in _read_rows(path, source_column, target_column, context_column):
        schema = classify_change(row["source"], row["target"], row["context"])
        if schema is None:
            skipped += 1
            continue
        schema_counts[schema] += 1
        environment_counts[classify_environment(row["context"])] += 1
    if not schema_counts:
        raise ValueError("Žádný řádek nešel konzervativně přiřadit ke schématu CEE.")
    used = sum(schema_counts.values())
    return (
        GeneratorProfile(
            changes=used,
            schemas=dict(sorted(schema_counts.items())),
            environments=dict(sorted(environment_counts.items())),
            # Index CSV nemá časové intervaly, proto rychlost úmyslně neznáme.
            changes_per_millennium=0.0,
        ),
        used,
        skipped,
    )


def build_local_research_profile(
    path: str | Path, profile_id: str, label: str, source_column: str = "source",
    target_column: str = "target", context_column: str = "context",
) -> tuple[SchemaProfile, int, int]:
    """Vytvoří pouze lokální profil; vrací profil, použitá a přeskočená pozorování."""
    source_path = Path(path)
    rows = _read_rows(path, source_column, target_column, context_column)
    counts = Counter(
        classify_change(row["source"], row["target"], row["context"]) for row in rows
    )
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

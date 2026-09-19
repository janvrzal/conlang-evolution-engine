"""Lokální, verzovatelná metadata Concepticonu pro lexikální rozhodování."""

from __future__ import annotations

import csv
import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cee.core.models import Word

CONCEPTICON_TSV_URL = (
    "https://raw.githubusercontent.com/concepticon/concepticon-data/master/"
    "concepticondata/concepticon.tsv"
)


def normalize_concept_key(value: str) -> str:
    """Klíč kompatibilní s Concepticon GLOSS i uzly CLICS4."""
    return " ".join(value.replace("_", " ").strip().upper().split())


@dataclass(frozen=True)
class ConceptMetadata:
    concepticon_id: str
    gloss: str
    semantic_field: str
    ontological_category: str

    @property
    def roles(self) -> tuple[str, ...]:
        """Převede ontologii Concepticonu na jazykově agnostické role."""
        category = self.ontological_category.strip().lower()
        if "action" in category or "process" in category:
            return ("event",)
        if "property" in category:
            return ("property",)
        if "number" in category or "classifier" in category:
            return ("quantification",)
        if self.semantic_field.strip().lower() in {"spatial relations", "possession"}:
            return ("relation",)
        if self.semantic_field.strip().lower() == "miscellaneous function words":
            return ("operator",)
        return ("reference",)


class ConcepticonIndex:
    """Index Concepticonu podle stabilního ID i normalizovaného glosu."""

    def __init__(self, entries: list[ConceptMetadata], provenance: str):
        self.provenance = provenance
        self._by_id = {entry.concepticon_id: entry for entry in entries if entry.concepticon_id}
        self._by_gloss = {normalize_concept_key(entry.gloss): entry for entry in entries if entry.gloss}

    @classmethod
    def from_tsv(cls, path: str) -> "ConcepticonIndex":
        entries: list[ConceptMetadata] = []
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                entries.append(
                    ConceptMetadata(
                        concepticon_id=(row.get("ID") or row.get("CONCEPTICON_ID") or "").strip(),
                        gloss=(row.get("GLOSS") or row.get("CONCEPTICON_GLOSS") or "").strip(),
                        semantic_field=(row.get("SEMANTICFIELD") or row.get("SEMANTIC_FIELD") or "").strip(),
                        ontological_category=(row.get("ONTOLOGICAL_CATEGORY") or row.get("ONTOLOGY") or "").strip(),
                    )
                )
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        return cls(entries, provenance=f"{Path(path).resolve()}#sha256={digest}")

    def lookup(self, concept_id: str, features: dict[str, str] | None = None) -> ConceptMetadata | None:
        features = features or {}
        explicit_id = features.get("concepticon.id", "").strip()
        if explicit_id and explicit_id in self._by_id:
            return self._by_id[explicit_id]
        if concept_id.strip() in self._by_id:
            return self._by_id[concept_id.strip()]
        return self._by_gloss.get(normalize_concept_key(features.get("concepticon.gloss", concept_id)))


def default_path() -> str:
    return os.path.join(str(Path.home()), ".cee", "data", "concepticon", "concepticon.tsv")


def download_concepticon(out_path: str | None = None) -> str:
    """Stáhne otevřená metadata jen na výslovnou žádost klienta/CLI."""
    path = out_path or default_path()
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    urllib.request.urlretrieve(CONCEPTICON_TSV_URL, path)  # noqa: S310 - pevný oficiální zdroj
    return path


def annotate_concept_metadata(word: Word, index: ConcepticonIndex | None) -> bool:
    """Doplní metadata bez přepsání explicitní autorské konfigurace."""
    if index is None:
        return False
    metadata = index.lookup(word.concept_id, word.grammatical_features)
    if metadata is None:
        return False
    word.grammatical_features.setdefault("concepticon.id", metadata.concepticon_id)
    word.grammatical_features.setdefault("concepticon.gloss", metadata.gloss)
    if metadata.semantic_field:
        word.grammatical_features.setdefault("semantic.domains", metadata.semantic_field)
    word.grammatical_features.setdefault("semantic.ontology", metadata.ontological_category)
    word.grammatical_features.setdefault("semantic.roles", ",".join(metadata.roles))
    word.grammatical_features.setdefault("semantic.provenance", f"concepticon:{index.provenance}")
    return True

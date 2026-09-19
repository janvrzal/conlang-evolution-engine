"""Importovatelný, auditovatelný prior lexikální retence.

Concepticon poskytuje identitu a domény, ne naměřenou stabilitu. Tento adaptér
proto nepředstírá vestavěný „správný“ globální korpus: přijme lokální CSV/TSV
od autora či výzkumníka, ověří jeho rozsah a zapíše přesně použitý zdroj ke
každému lexému. Formát je schválně malý a kompatibilní s tabulkami, které
klíčují Concepticonovým ID nebo glosem.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cee.core.models import Lexicon, Word
from cee.semantics.concepts import normalize_concept_key

_ID_COLUMNS = ("concepticon_id", "Concepticon_ID", "id", "ID")
_GLOSS_COLUMNS = ("concepticon_gloss", "Concepticon_Gloss", "gloss", "Gloss")
_VALUE_COLUMNS = ("retention", "retention_rate", "stability", "stability_score")

# Tyto dvě tabulky jsou součástí otevřených dat Concepticonu (CC-BY-4.0).
# Nezacházíme s nimi jako s univerzální pravdou: jde o explicitně volitelný
# globální prior, jehož rozsah je přibližně několik stovek základních konceptů.
CONCEPTICON_STABILITY_SOURCES = {
    "swadesh-1955": (
        "https://raw.githubusercontent.com/concepticon/concepticon-data/master/"
        "concepticondata/conceptlists/Swadesh-1955-215.tsv"
    ),
    "peust-2013": (
        "https://raw.githubusercontent.com/concepticon/concepticon-data/master/"
        "concepticondata/conceptlists/Peust-2013-54.tsv"
    ),
}


def _first(row: dict[str, str], names: Iterable[str]) -> str:
    return next((str(row.get(name, "")).strip() for name in names if str(row.get(name, "")).strip()), "")


@dataclass(frozen=True)
class ConceptRetentionModel:
    """Naměřená retence konceptů normalizovaná na uzavřený interval 0–1."""

    by_id: dict[str, float]
    by_gloss: dict[str, float]
    provenance: str

    @classmethod
    def from_table(cls, path: str | Path) -> "ConceptRetentionModel":
        source = Path(path)
        dialect = "excel-tab" if source.suffix.lower() == ".tsv" else "excel"
        by_id: dict[str, float] = {}
        by_gloss: dict[str, float] = {}
        with source.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, dialect=dialect):
                raw_value = _first(row, _VALUE_COLUMNS)
                try:
                    value = max(0.0, min(1.0, float(raw_value)))
                except (TypeError, ValueError):
                    continue
                identifier = _first(row, _ID_COLUMNS)
                gloss = normalize_concept_key(_first(row, _GLOSS_COLUMNS))
                if identifier:
                    by_id[identifier] = value
                if gloss:
                    by_gloss[gloss] = value
        if not by_id and not by_gloss:
            raise ValueError("Retenční tabulka nemá žádný platný koncept a hodnotu 0–1.")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        return cls(by_id, by_gloss, f"retention-corpus:{source.name}:sha256={digest}")

    def lookup(self, word: Word) -> float | None:
        concept_id = word.grammatical_features.get("concepticon.id", "").strip()
        if concept_id and concept_id in self.by_id:
            return self.by_id[concept_id]
        for key in (
            word.grammatical_features.get("concepticon.gloss", ""),
            word.concept_id,
        ):
            value = self.by_gloss.get(normalize_concept_key(key))
            if value is not None:
                return value
        return None

    def annotate(self, lexicon: Lexicon) -> int:
        """Zapíše prior pouze tam, kde má tabulka skutečně doloženou hodnotu."""
        annotated = 0
        for word in lexicon.words:
            value = self.lookup(word)
            if value is None:
                continue
            word.grammatical_features["semantic.stability"] = f"{value:.6f}"
            word.grammatical_features["semantic.stability_source"] = "empirical_retention"
            word.grammatical_features["semantic.stability_provenance"] = self.provenance
            annotated += 1
        return annotated


def default_concepticon_retention_path() -> Path:
    return Path.home() / ".cee" / "data" / "concepticon" / "retention-global.csv"


def _source_stability(row: dict[str, str]) -> float | None:
    """Normalizuje explicitní Concepticonovu stabilitní škálu na 0–1."""
    raw = (row.get("STABILITY_SCORE") or row.get("STABILITY") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    # Swadesh používá procenta, Peust stupnici 1–6.
    if value > 6:
        return max(0.0, min(1.0, value / 100.0))
    return max(0.0, min(1.0, value / 6.0))


def build_concepticon_retention_prior(
    source_paths: dict[str, str | Path], out_path: str | Path | None = None
) -> Path:
    """Sloučí otevřené stabilitní seznamy do auditovatelného CSV prioru."""
    values: dict[tuple[str, str], list[float]] = {}
    sources: dict[tuple[str, str], list[str]] = {}
    for source_name, source_path in source_paths.items():
        with Path(source_path).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                value = _source_stability(row)
                identifier = (row.get("CONCEPTICON_ID") or "").strip()
                gloss = normalize_concept_key(row.get("CONCEPTICON_GLOSS") or "")
                if value is None or not (identifier or gloss):
                    continue
                key = (identifier, gloss)
                values.setdefault(key, []).append(value)
                sources.setdefault(key, []).append(source_name)
    destination = Path(out_path or default_concepticon_retention_path())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["concepticon_id", "concepticon_gloss", "retention", "sources"],
        )
        writer.writeheader()
        for (identifier, gloss), scores in sorted(values.items()):
            writer.writerow({
                "concepticon_id": identifier,
                "concepticon_gloss": gloss,
                "retention": f"{sum(scores) / len(scores):.6f}",
                "sources": ";".join(sorted(sources[(identifier, gloss)])),
            })
    manifest = {
        "format": "cee-concepticon-retention-v1",
        "sources": list(source_paths),
        "rows": len(values),
        "license": "CC-BY-4.0 (Concepticon data; cite the underlying concept lists)",
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
    }
    destination.with_suffix(".json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return destination


def download_concepticon_retention_prior(out_path: str | Path | None = None) -> Path:
    """Stáhne jen otevřené Concepticonovy zdroje a vytvoří výchozí prior."""
    destination = Path(out_path or default_concepticon_retention_path())
    source_dir = destination.parent / "retention-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, url in CONCEPTICON_STABILITY_SOURCES.items():
        path = source_dir / f"{name}.tsv"
        if not path.exists():
            # Použijeme systémový TLS store. Některé macOS Python buildy nemají
            # připojený certifikační bundle, přestože systémový klient jej má;
            # ověřování certifikátu se tím nikdy nevypíná.
            subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error", url, "--output", str(path)],
                check=True,
            )
        paths[name] = path
    return build_concepticon_retention_prior(paths, destination)


def concepticon_retention_status(path: str | Path | None = None) -> dict[str, object]:
    source = Path(path or default_concepticon_retention_path())
    if not source.is_file():
        return {"available": False, "path": str(source), "sources": list(CONCEPTICON_STABILITY_SOURCES)}
    model = ConceptRetentionModel.from_table(source)
    return {
        "available": True,
        "path": str(source),
        # ID a glosa jsou dva indexy týchž řádků, nesmí se sčítat.
        "concepts": len(model.by_id) or len(model.by_gloss),
        "provenance": model.provenance,
        "sources": list(CONCEPTICON_STABILITY_SOURCES),
    }

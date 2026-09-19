"""Reprodukovatelná diagnostika lexika a sémantiky nad hotovým během.

Tento modul nic nemění na simulaci ani z retenčního korpusu nedělá prior
enginu.  Přijímá explicitní seznam konceptů, finální stavy a auditní události
a z nich vytváří přenositelný JSON/CSV/Markdown report.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from cee.core.models import State

REPORT_FORMAT = "cee-empirical-diagnostic-v1"


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


@dataclass(frozen=True)
class RetentionCorpus:
    """Samostatný, verzovaný vstup pro lokální kalibraci a pokrytí."""

    rows: tuple[dict[str, str], ...]
    provenance: dict[str, Any]

    REQUIRED = ("concepticon_id", "gloss", "source", "value", "method_note")

    @classmethod
    def from_csv(cls, path: str | Path, manifest: str | Path | None = None) -> "RetentionCorpus":
        source = Path(path)
        dialect = "excel-tab" if source.suffix.lower() == ".tsv" else "excel"
        with source.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, dialect=dialect)
            headers = set(reader.fieldnames or [])
            missing = set(cls.REQUIRED) - headers
            if missing:
                raise ValueError("Retenční korpus postrádá povinné sloupce: " + ", ".join(sorted(missing)))
            rows = []
            identities: set[tuple[str, str]] = set()
            for number, raw in enumerate(reader, start=2):
                row = {name: str(raw.get(name, "")).strip() for name in reader.fieldnames or []}
                if not row["concepticon_id"] and not row["gloss"]:
                    raise ValueError(f"Řádek {number} nemá Concepticon ID ani glosu.")
                if not row["source"] or not row["method_note"]:
                    raise ValueError(f"Řádek {number} nemá zdroj nebo metodickou poznámku.")
                try:
                    value = float(row["value"])
                except ValueError as exc:
                    raise ValueError(f"Řádek {number} nemá číselnou stabilitu 0–1.") from exc
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"Řádek {number} má stabilitu mimo interval 0–1.")
                identity = (row["concepticon_id"], _key(row["gloss"]))
                if identity in identities:
                    raise ValueError(f"Duplicitní koncept v retenčním korpusu na řádku {number}.")
                identities.add(identity)
                row["value"] = f"{value:.6f}"
                rows.append(row)
        if not rows:
            raise ValueError("Retenční korpus neobsahuje žádný řádek.")
        metadata: dict[str, Any] = {}
        if manifest:
            metadata = json.loads(Path(manifest).read_text(encoding="utf-8"))
        provenance = {
            "path": str(source), "sha256": file_sha256(source), "rows": len(rows),
            "imported_at": metadata.get("imported_at", date.today().isoformat()),
            "source_version": metadata.get("source_version", "unspecified"),
            "license": metadata.get("license", "unspecified"),
            "manifest": str(manifest) if manifest else None,
        }
        return cls(tuple(rows), provenance)

    def coverage(self, concepts: Iterable[Mapping[str, str] | str]) -> dict[str, Any]:
        ids = {row["concepticon_id"] for row in self.rows if row["concepticon_id"]}
        glosses = {_key(row["gloss"]) for row in self.rows if row["gloss"]}
        total = matched_id = matched_gloss = missing = 0
        for concept in concepts:
            total += 1
            if isinstance(concept, str):
                identifier, gloss = "", concept
            else:
                identifier, gloss = concept.get("concepticon_id", ""), concept.get("gloss", "")
            if identifier and identifier in ids:
                matched_id += 1
            elif _key(gloss) in glosses:
                matched_gloss += 1
            else:
                missing += 1
        return {"total": total, "matched_id": matched_id, "matched_gloss": matched_gloss,
                "fallback_heuristic": missing, "coverage_ratio": (total - missing) / total if total else 0.0}


def diagnostic_concepts(concepts: Sequence[str]) -> list[str]:
    """Validuje a kanonizuje měřicí seznam; pořadí je součástí vstupu reportu."""
    result = [str(item).strip() for item in concepts]
    if not result or any(not item for item in result):
        raise ValueError("Diagnostický seznam musí obsahovat neprázdné koncepty.")
    if len(set(result)) != len(result):
        raise ValueError("Diagnostický seznam obsahuje duplicity.")
    return result


def _branch_metrics(state: State, concepts: Sequence[str]) -> dict[str, Any]:
    lexical = Counter()
    semantic_lost: list[str] = []
    semantic_new: Counter[str] = Counter()
    polysemy = Counter()
    for concept in concepts:
        covering = state.lexicon.get_words(concept)
        roots = [word for word in covering if word.concept_id == concept]
        inherited = [word for word in roots if word.source_id is None]
        contact = [word for word in roots if word.source_id is not None]
        if inherited:
            lexical["inherited"] += 1
        elif contact:
            lexical["contact_replacement"] += 1
        elif covering:
            lexical["replacement"] += 1
        else:
            lexical["lost"] += 1
        if not covering:
            semantic_lost.append(concept)
    for word in state.lexicon.words:
        if not word.active:
            continue
        polysemy[str(1 + len(word.polysemy))] += 1
        for meaning in word.polysemy:
            semantic_new[meaning] += 1
    total = len(concepts)
    return {
        "year": state.year,
        "lexical_retention": {**{key: lexical[key] for key in ("inherited", "contact_replacement", "replacement", "lost")},
                              "ratio": lexical["inherited"] / total if total else 0.0},
        "semantic_retention": {"active_original_coverage": total - len(semantic_lost), "lost_coverage": semantic_lost,
                               "new_coverage": dict(sorted(semantic_new.items()))},
        "polysemy_size_distribution": dict(sorted(polysemy.items(), key=lambda item: int(item[0]))),
    }


def _event_metrics(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    started: dict[str, Mapping[str, Any]] = {}
    coexistence: list[dict[str, Any]] = []
    origin = Counter()
    distances = Counter()
    for event in events:
        kind = event.get("kind")
        if kind == "semantic_change_started":
            started[str(event["change_id"])] = event
            origin["contact" if event.get("evidence_type") == "contact-calque" else "inherited"] += 1
            # Engine zatím nezná globální vzdálenost konceptů. Přímá hrana je
            # jediná korektně doložená velikost; vše ostatní zůstává unknown.
            distances[str(event.get("concept_distance", "unknown"))] += 1
        elif kind == "semantic_change_progress" and event.get("phase") == "completed":
            start = started.get(str(event.get("change_id")))
            if start:
                coexistence.append({"change_id": event["change_id"], "branch": event.get("language_id"),
                                    "years": max(0, int(event["year"]) - int(start["year"])),
                                    "kind": start.get("change_kind"), "origin": "contact" if start.get("evidence_type") == "contact-calque" else "inherited"})
    small = large = 0
    for key, count in distances.items():
        try:
            distance = float(key)
        except (TypeError, ValueError):
            continue
        if distance <= 1.0:
            small += count
        else:
            large += count
    return {"semantic_origins": dict(origin), "coexistence": coexistence,
            "semantic_jump_distance": {"small": small, "large": large, "unknown": distances["unknown"],
                                         "note": "Bez explicitní concept_distance se vzdálenost neodhaduje heuristikou."}}


def build_report(states: Mapping[str, State], concepts: Sequence[str], *, seed: int,
                 simulator_version: str, inputs: Mapping[str, str | Path], events: Iterable[Mapping[str, Any]] = (),
                 corpus: RetentionCorpus | None = None) -> dict[str, Any]:
    concepts = diagnostic_concepts(concepts)
    branches = {name: _branch_metrics(state, concepts) for name, state in sorted(states.items())}
    retention_values = [data["lexical_retention"]["ratio"] for data in branches.values()]
    report = {"format": REPORT_FORMAT, "inputs": {"seed": seed, "simulator_version": simulator_version,
              "concept_list": concepts, "concept_list_sha256": hashlib.sha256("\n".join(concepts).encode()).hexdigest(),
              "files": {name: {"path": str(path), "sha256": file_sha256(path)} for name, path in sorted(inputs.items())}},
              "branches": branches, "events": _event_metrics(events),
              "sibling_divergence": {"retention_range": (max(retention_values) - min(retention_values)) if retention_values else 0.0},
              "limitations": ["Diagnostika a lokální kalibrace, nikoli potvrzení obecného historického modelu.",
                              "Fonetická divergence kognátů se zde záměrně nemíchá s výměnou kořene."]}
    if corpus:
        report["retention_corpus"] = {"provenance": corpus.provenance, "coverage": corpus.coverage(concepts)}
    return report


def aggregate_reports(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Agreguje porovnatelné běhy přes seedy bez ztráty jednotlivých výsledků."""
    if not reports:
        raise ValueError("Pro agregaci je potřeba alespoň jeden report.")
    concept_hash = reports[0]["inputs"]["concept_list_sha256"]
    if any(item["inputs"]["concept_list_sha256"] != concept_hash for item in reports):
        raise ValueError("Reporty nemají identický konceptový seznam.")
    grouped: dict[str, list[float]] = defaultdict(list)
    for report in reports:
        for branch, data in report["branches"].items():
            grouped[branch].append(float(data["lexical_retention"]["ratio"]))
    return {
        "format": "cee-empirical-diagnostic-aggregate-v1",
        "concept_list_sha256": concept_hash,
        "seeds": [item["inputs"]["seed"] for item in reports],
        "branches": {
            branch: {"runs": len(values), "lexical_retention_mean": sum(values) / len(values),
                     "lexical_retention_min": min(values), "lexical_retention_max": max(values)}
            for branch, values in sorted(grouped.items())
        },
    }


def write_report(report: Mapping[str, Any], out_dir: str | Path) -> tuple[Path, Path, Path]:
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path, csv_path, md_path = (destination / "empirical-report.json", destination / "empirical-branches.csv", destination / "empirical-report.md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["branch", "year", "lexical_retention", "inherited", "contact_replacement", "replacement", "lost"])
        writer.writeheader()
        for branch, data in report["branches"].items():
            lexical = data["lexical_retention"]
            writer.writerow({"branch": branch, "year": data["year"], "lexical_retention": lexical["ratio"], **{key: lexical[key] for key in ("inherited", "contact_replacement", "replacement", "lost")}})
    lines = ["# Empirická diagnostika", "", "Toto je reprodukovatelná diagnostika a lokální kalibrace; není to potvrzení obecného historického modelu.", "", "## Větve", "", "| Větev | Rok | Lexikální retence | Kontakt | Náhrada | Ztráta |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for branch, data in report["branches"].items():
        item = data["lexical_retention"]
        lines.append(f"| {branch} | {data['year']} | {item['ratio']:.1%} | {item['contact_replacement']} | {item['replacement']} | {item['lost']} |")
    lines += ["", "## Omezení", ""] + [f"- {note}" for note in report["limitations"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, md_path

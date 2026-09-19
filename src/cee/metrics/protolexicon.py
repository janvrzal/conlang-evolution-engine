"""Převod otevřených CLDF protoforem na vstupní lexikon CEE.

Zdrojová data zůstávají mimo repozitář. Export protolexikonu je malý,
auditovatelný artefakt pro konkrétní experiment: vedle CSV protoforem vzniká
metadata JSON se zdrojem, checksumy a počty vyřazených záznamů.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cee.engine.phonology import FeatureMapper

_TRUE_VALUES = {"1", "true", "yes"}
_BOUNDARY_TOKENS = {"+", "_", "#", "-"}


@dataclass(frozen=True)
class ProtoLexiconExport:
    proto_language_id: str
    proto_language_name: str
    records: list[dict[str, str]]
    skipped_doubtful: int
    skipped_unparseable: int
    skipped_duplicate_concepts: int
    source_checksums: dict[str, str]

    def metadata(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "proto_language": {
                "id": self.proto_language_id,
                "name": self.proto_language_name,
            },
            "records": len(self.records),
            "skipped": {
                "doubtful": self.skipped_doubtful,
                "unparseable": self.skipped_unparseable,
                "duplicate_concepts": self.skipped_duplicate_concepts,
            },
            "source_checksums": self.source_checksums,
        }


def _rows(path: str | Path) -> Iterable[dict[str, str]]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _checksum(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalise_segments(segments: str) -> str:
    """Spojí CLDF segmenty, ale zachová pouze fonologické tokeny.

    CLDF používá mezery mezi segmenty a někdy morfémové hranice. Hranice se
    pro současný CSV vstup CEE neexportují; u složitější morfologie zůstává
    rozhodnutí na kurátorovi místo tichého vymýšlení analýzy.
    """
    return "".join(token for token in segments.split() if token not in _BOUNDARY_TOKENS)


def extract_protolexicon(
    forms_path: str | Path,
    languages_path: str | Path,
    proto_language_id: str | None = None,
    include_doubtful: bool = False,
) -> ProtoLexiconExport:
    """Vyexportuje jednu explicitně označenou CLDF protořeč do CSV CEE.

    Pokud zdroj obsahuje více protojazyků, je nutné ID zvolit explicitně.
    Na koncept se ponechá první nedvojitá, segmentovatelná forma v pořadí
    zdroje. Tím zůstává výsledek deterministický a velikost lexikonu nezkreslí
    množství alternativních rekonstrukcí téhož hesla.
    """
    languages = {row.get("ID", "").strip(): row for row in _rows(languages_path)}
    candidates = [
        (language_id, row)
        for language_id, row in languages.items()
        if row.get("Is_Proto", "").strip().lower() in _TRUE_VALUES
    ]
    if proto_language_id is None:
        if len(candidates) != 1:
            available = ", ".join(language_id for language_id, _ in candidates[:8])
            raise ValueError(
                "Zdroj obsahuje více protojazyků; zadej --proto-language-id "
                f"(např. {available})."
            )
        proto_language_id = candidates[0][0]
    language = languages.get(proto_language_id)
    if language is None:
        raise ValueError(f"Protojazyk {proto_language_id!r} není v languages.csv.")
    if language.get("Is_Proto", "").strip().lower() not in _TRUE_VALUES:
        raise ValueError(f"Jazyk {proto_language_id!r} není ve zdroji označený Is_Proto.")

    mapper = FeatureMapper()
    records: list[dict[str, str]] = []
    used_concepts: set[str] = set()
    skipped_doubtful = skipped_unparseable = skipped_duplicates = 0
    for row in _rows(forms_path):
        if row.get("Language_ID", "").strip() != proto_language_id:
            continue
        if not include_doubtful and row.get("Doubt", "").strip().lower() in _TRUE_VALUES:
            skipped_doubtful += 1
            continue
        concept_id = row.get("Parameter_ID", "").strip() or row.get("ID", "").strip()
        ipa = _normalise_segments(row.get("Segments", "").strip())
        if not concept_id or not ipa or not mapper.parse_word(concept_id, ipa).segments:
            skipped_unparseable += 1
            continue
        if concept_id in used_concepts:
            skipped_duplicates += 1
            continue
        used_concepts.add(concept_id)
        records.append({"id": concept_id, "ipa_proto": ipa})
    if not records:
        raise ValueError(f"Pro {proto_language_id!r} nevznikla žádná použitelná protoforma.")
    return ProtoLexiconExport(
        proto_language_id=proto_language_id,
        proto_language_name=language.get("Name", "").strip() or proto_language_id,
        records=records,
        skipped_doubtful=skipped_doubtful,
        skipped_unparseable=skipped_unparseable,
        skipped_duplicate_concepts=skipped_duplicates,
        source_checksums={"forms": _checksum(forms_path), "languages": _checksum(languages_path)},
    )


def write_protolexicon(export: ProtoLexiconExport, out: str | Path, metadata_out: str | Path) -> None:
    """Zapíše simulovatelný CSV a jeho samostatný auditní manifest."""
    output = Path(out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "ipa_proto"])
        writer.writeheader()
        writer.writerows(export.records)
    manifest = Path(metadata_out)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(export.metadata(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

"""Extrahuje auditovatelné kandidáty protoforma → reflex z historického CLDF.

Modul záměrně neurčuje zvukový zákon automaticky. Shoda dvou segmentů v jedné
etymologii sama o sobě není historická změna; výsledkem je proto fronta pro
lidskou anotaci, nikoli vstup přímo do tréninku vah.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ReflexCandidate:
    family_id: str
    proto_form_id: str
    proto_language_id: str
    proto_form: str
    reflex_form_id: str
    reflex_language_id: str
    reflex_form: str
    parameter_id: str
    relation: str


def _form(row: dict[str, str]) -> str:
    """Preferuje segmentovaný tvar, ale nestrká prázdný řádek do fronty."""
    return (row.get("Segments") or row.get("Form") or row.get("Value") or "").strip()


def extract_reflex_candidates(
    forms_path: str | Path,
    family_id: str,
    proto_language_ids: Iterable[str],
) -> list[ReflexCandidate]:
    """Vrátí přímé, ne-výpůjční vazby `Origin_ID` z generického CLDF forms.csv.

    Vyžaduje pouze `ID` a `Language_ID`; `Origin_ID`, `Relation`, `Segments`,
    `Form` a `Parameter_ID` jsou volitelné. Vícenásobné zdroje oddělené
    středníkem rozbalí na samostatné kandidáty. Vztahy výslovně označené jako
    výpůjčka se nezaměňují za dědičné reflexy.
    """
    proto_ids = {value.strip() for value in proto_language_ids if value.strip()}
    if not family_id.strip():
        raise ValueError("family_id nesmí být prázdné.")
    if not proto_ids:
        raise ValueError("Zadej alespoň jeden proto_language_id.")

    path = Path(forms_path)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"ID", "Language_ID"}
        if reader.fieldnames is None or (missing := required - set(reader.fieldnames)):
            raise ValueError(f"{path} nemá povinné sloupce: {sorted(missing)}")
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    by_id = {row["ID"]: row for row in rows if row["ID"]}
    candidates: list[ReflexCandidate] = []
    seen: set[tuple[str, str]] = set()
    for reflex in rows:
        relation = reflex.get("Relation", "").strip()
        if "borrow" in relation.lower():
            continue
        for origin_id in (value.strip() for value in reflex.get("Origin_ID", "").split(";")):
            proto = by_id.get(origin_id)
            if not proto or proto.get("Language_ID") not in proto_ids:
                continue
            if not _form(proto) or not _form(reflex):
                continue
            key = (origin_id, reflex["ID"])
            if key in seen:
                continue
            seen.add(key)
            candidates.append(ReflexCandidate(
                family_id=family_id.strip(),
                proto_form_id=origin_id,
                proto_language_id=proto["Language_ID"],
                proto_form=_form(proto),
                reflex_form_id=reflex["ID"],
                reflex_language_id=reflex["Language_ID"],
                reflex_form=_form(reflex),
                parameter_id=reflex.get("Parameter_ID", ""),
                relation=relation or "inherited",
            ))
    return sorted(candidates, key=lambda row: (row.proto_form_id, row.reflex_form_id))


def write_reflex_candidates(candidates: Iterable[ReflexCandidate], path: str | Path) -> None:
    """Zapíše frontu v deterministickém CSV formátu pro kurátorský nástroj."""
    rows = [asdict(candidate) for candidate in candidates]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = list(ReflexCandidate.__annotations__)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

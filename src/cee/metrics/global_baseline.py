"""Globální, licenčně auditovatelná kalibrace generátoru.

Nezaměňuje synchronní podobnost kognátů za směr zvukové změny. Vstupem jsou
výhradně *anotovaná směrovaná pozorování* z otevřených zdrojů nebo vlastní
kurace. Každé pozorování nese rodinu a zdroj, takže dobře popsaná rodina
nemůže převážit globální profil jen počtem řádků.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

# CC-BY a CC0 dovolují, aby otevřené jádro i placené rozhraní distribuovaly
# odvozené váhy. NC nebo SA se sem záměrně nedostanou bez právního rozhodnutí.
COMMERCIAL_COMPATIBLE_LICENSES = frozenset({"CC0-1.0", "CC-BY-4.0", "BSD-3-Clause", "MIT"})


@dataclass(frozen=True)
class CorpusSource:
    """Verzovaný a citovatelný zdroj jednoho vstupního souboru."""

    id: str
    path: str
    license: str
    version: str
    citation: str
    url: str = ""

    def validate(self) -> None:
        if self.license not in COMMERCIAL_COMPATIBLE_LICENSES:
            raise ValueError(
                f"Zdroj '{self.id}' má licenci {self.license!r}; "
                "pro distribuované globální váhy nejsou povoleny NC/SA ani neznámé licence."
            )
        if not self.id or not self.path or not self.version or not self.citation:
            raise ValueError(f"Zdroj '{self.id}' musí mít id, path, version a citation.")


@dataclass(frozen=True)
class ChangeObservation:
    """Jedna směrovaná, lidsky/zdrojově anotovaná historická změna."""

    schema_id: str
    environment: str
    family_id: str
    source_id: str
    language_id: str = ""
    area: str = ""


@dataclass(frozen=True)
class GlobalBaseline:
    """Rodinně vyvážený profil a hladké multiplikátory vah schémat."""

    observations: int
    families: int
    schema_distribution: dict[str, float]
    environment_distribution: dict[str, float]
    schema_multipliers: dict[str, float]
    source_checksums: dict[str, str]
    sources: list[CorpusSource]
    smoothing: float = 1.0

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["sources"] = [asdict(source) for source in self.sources]
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "GlobalBaseline":
        raw = cast(Mapping[str, Any], data)
        return cls(
            observations=int(raw["observations"]),
            families=int(raw["families"]),
            schema_distribution={
                str(k): float(v) for k, v in dict(raw["schema_distribution"]).items()
            },
            environment_distribution={
                str(k): float(v) for k, v in dict(raw["environment_distribution"]).items()
            },
            schema_multipliers={
                str(k): float(v) for k, v in dict(raw["schema_multipliers"]).items()
            },
            source_checksums={str(k): str(v) for k, v in dict(raw["source_checksums"]).items()},
            sources=[CorpusSource(**source) for source in list(raw["sources"])],
            smoothing=float(raw.get("smoothing", 1.0)),
        )


def _normalise(counts: Mapping[str, float]) -> dict[str, float]:
    total = sum(counts.values())
    return {key: value / total for key, value in sorted(counts.items())} if total else {}


def _family_balanced_distribution(
    observations: Iterable[ChangeObservation], attribute: str
) -> dict[str, float]:
    """Průměr rozdělení v rodinách, nikoli prosté rozdělení všech řádků."""
    per_family: dict[str, Counter[str]] = defaultdict(Counter)
    for observation in observations:
        value = getattr(observation, attribute)
        per_family[observation.family_id][value] += 1

    averaged: dict[str, float] = defaultdict(float)
    for counts in per_family.values():
        local = _normalise(counts)
        for value, share in local.items():
            averaged[value] += share
    return _normalise(averaged)


def train_global_baseline(
    observations: Iterable[ChangeObservation],
    sources: Iterable[CorpusSource],
    source_checksums: Mapping[str, str],
    schema_ids: Iterable[str],
    smoothing: float = 1.0,
) -> GlobalBaseline:
    """Odhadne hladké relativní váhy nad explicitně povoleným vstupem.

    Multiplikátor je poměr smoothed podílu schématu k rovnoměrnému prioru.
    Hodnota 1.0 tedy znamená bez evidence, nikoli „změna je nemožná“.
    """
    source_list = list(sources)
    for source in source_list:
        source.validate()
    known_sources = {source.id for source in source_list}
    rows = list(observations)
    if not rows:
        raise ValueError("Globální baseline potřebuje alespoň jedno anotované pozorování.")
    if any(not row.family_id or not row.schema_id or not row.environment for row in rows):
        raise ValueError("Každé pozorování musí mít schema_id, environment a family_id.")
    if unknown := {row.source_id for row in rows} - known_sources:
        raise ValueError(f"Pozorování odkazují na neregistrované zdroje: {sorted(unknown)}")
    if smoothing <= 0:
        raise ValueError("Smoothing musí být kladný.")

    schema_keys = sorted(set(schema_ids))
    if not schema_keys:
        raise ValueError("Pro trénink musí být zadané alespoň jedno schéma generátoru.")
    distribution = _family_balanced_distribution(rows, "schema_id")
    # Zahrne i schémata, která zatím nemají evidence: tím se nula nepromění
    # v zákaz historicky možné změny.
    smoothed = {
        schema: distribution.get(schema, 0.0) + smoothing / len(schema_keys)
        for schema in schema_keys
    }
    smoothed = _normalise(smoothed)
    uniform = 1 / len(schema_keys)
    multipliers = {schema: round(share / uniform, 8) for schema, share in smoothed.items()}

    return GlobalBaseline(
        observations=len(rows),
        families=len({row.family_id for row in rows}),
        schema_distribution=distribution,
        environment_distribution=_family_balanced_distribution(rows, "environment"),
        schema_multipliers=multipliers,
        source_checksums=dict(sorted(source_checksums.items())),
        sources=source_list,
        smoothing=smoothing,
    )


def load_observations(
    source: CorpusSource, base_dir: str | Path
) -> tuple[list[ChangeObservation], str]:
    """Načte malý CSV kontrakt pro kurátory a externí převodníky.

    Povinné sloupce: ``schema_id,environment,family_id``. Dobrovolné:
    ``language_id,area``. Samotný manifest drží licenci, verzi a citaci.
    """
    source.validate()
    path = Path(base_dir) / source.path
    if not path.is_file():
        raise FileNotFoundError(f"Vstup pro zdroj '{source.id}' neexistuje: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"schema_id", "environment", "family_id"}
        if reader.fieldnames is None or (missing := required - set(reader.fieldnames)):
            raise ValueError(f"{path} nemá povinné sloupce: {sorted(missing)}")
        rows = [
            ChangeObservation(
                schema_id=row["schema_id"].strip(),
                environment=row["environment"].strip(),
                family_id=row["family_id"].strip(),
                source_id=source.id,
                language_id=row.get("language_id", "").strip(),
                area=row.get("area", "").strip(),
            )
            for row in reader
        ]
    return rows, hashlib.sha256(path.read_bytes()).hexdigest()


def train_from_manifest(path: str | Path, schema_ids: Iterable[str]) -> GlobalBaseline:
    """Sestaví baseline z JSON manifestu a relativních CSV souborů."""
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Manifest musí mít schema_version: 1.")
    sources = [CorpusSource(**source) for source in manifest.get("sources", [])]
    observations: list[ChangeObservation] = []
    checksums: dict[str, str] = {}
    for source in sources:
        rows, checksum = load_observations(source, manifest_path.parent)
        observations.extend(rows)
        checksums[source.id] = checksum
    return train_global_baseline(
        observations,
        sources,
        checksums,
        schema_ids,
        smoothing=float(manifest.get("smoothing", 1.0)),
    )


def save_global_baseline(baseline: GlobalBaseline, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(baseline.as_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_global_baseline(path: str | Path) -> GlobalBaseline:
    return GlobalBaseline.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

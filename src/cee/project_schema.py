"""Verzované schéma persistentního projektu a čisté migrace."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


CURRENT_PROJECT_SCHEMA = 2


class ProtoLexeme(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    ipa: str


class TimelineSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class ProjectData(BaseModel):
    """Kanonický obsah projektu; neznámá pole zachová pro dopřednou kompatibilitu."""

    model_config = ConfigDict(extra="allow")

    generatedProtoLexicon: list[ProtoLexeme] = Field(default_factory=list)
    timeSteps: list[int] = Field(default_factory=lambda: [0, 500, 1000, 1500])
    snapshots: dict[str, TimelineSnapshot] = Field(default_factory=dict)
    protoLanguages: list[dict[str, Any]] = Field(default_factory=list)
    simulationRunAt: str | None = None
    simulationRunId: str | None = None


def migrate_data(version: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Vrátí aktuální tvar bez mutace vstupního JSONu."""
    if version > CURRENT_PROJECT_SCHEMA:
        raise ValueError(
            f"Projekt má novější schéma {version}; tato verze CEE umí nejvýše {CURRENT_PROJECT_SCHEMA}."
        )
    migrated = dict(data)
    current = version
    if current < 2:
        migrated.setdefault("generatedProtoLexicon", [])
        migrated.setdefault("timeSteps", [0, 500, 1000, 1500])
        migrated.setdefault("snapshots", {})
        migrated.setdefault("protoLanguages", [])
        migrated.setdefault("simulationRunAt", None)
        migrated.setdefault("simulationRunId", None)
        migrated["timeSteps"] = sorted({int(year) for year in migrated["timeSteps"]})
        migrated["snapshots"] = {
            str(int(year)): value for year, value in migrated["snapshots"].items()
        }
        current = 2
    return current, migrated


def normalize_data(version: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Migruje a Pydanticem zkontroluje data zapisovaná na disk."""
    migrated_version, migrated = migrate_data(version, data)
    # Nepřidáváme výchozí pole do nových minimalistických projektů jen kvůli
    # serializaci. Migrace V1 je naopak vloží výslovně, takže se zachovají.
    return migrated_version, ProjectData.model_validate(migrated).model_dump(
        mode="json", round_trip=True, exclude_unset=True
    )

"""
Ukládání projektů na disk.

Projekt je celý uživatelův rozdělaný stav — topologie, časová osa, proto-slovník
i nastavení. Bez něj se všechno drží jen v paměti prohlížeče a zmizí při
přechodu mezi stránkami nebo po F5.

Formát je prostý JSON, aby šel číst a verzovat i mimo aplikaci.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ID projektu se stává jménem souboru, takže musí projít přísným sítem —
# jinak by `../../` v URL ukázalo kamkoli po disku.
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

SCHEMA_VERSION = 1


class ProjectError(Exception):
    """Chyba při práci s uloženým projektem."""


class InvalidProjectId(ProjectError):
    pass


class ProjectNotFound(ProjectError):
    pass


def projects_dir() -> Path:
    """Kde projekty bydlí. Lze přesměrovat přes CEE_PROJECTS_DIR (užitečné v testech)."""
    override = os.environ.get("CEE_PROJECTS_DIR")
    base = Path(override) if override else Path.home() / ".cee" / "projects"
    base.mkdir(parents=True, exist_ok=True)
    return base


def validate_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not SAFE_ID.match(project_id):
        raise InvalidProjectId(
            f"Neplatné ID projektu {project_id!r}. Povolena jsou písmena, číslice, "
            f"pomlčka a podtržítko, nejvýše 64 znaků."
        )
    return project_id


def _path_for(project_id: str) -> Path:
    path = (projects_dir() / f"{validate_id(project_id)}.json").resolve()

    # Pás navíc ke šlím: i kdyby síto výše někdo obešel, cesta musí zůstat uvnitř.
    if path.parent != projects_dir().resolve():
        raise InvalidProjectId(f"ID {project_id!r} ukazuje mimo složku projektů.")
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Project:
    """Uložený stav jednoho projektu."""

    id: str
    name: str = "Nový projekt"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    schema_version: int = SCHEMA_VERSION

    # Volný obsah z UI: topologie, časová osa, proto-slovník, nastavení.
    # Engine do něj nezasahuje, takže se frontend může vyvíjet bez migrací.
    data: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Project":
        return cls(
            id=payload["id"],
            name=payload.get("name", "Nový projekt"),
            created_at=payload.get("created_at", _now()),
            updated_at=payload.get("updated_at", _now()),
            schema_version=payload.get("schema_version", SCHEMA_VERSION),
            data=payload.get("data", {}),
        )


def save(project: Project) -> Project:
    """
    Uloží projekt atomicky.

    Zápis jde nejdřív do dočasného souboru a teprve pak se přejmenuje. Kdyby
    aplikace spadla uprostřed, na disku zůstane předchozí verze, ne půlka nové.
    """
    path = _path_for(project.id)
    project.updated_at = _now()
    payload = json.dumps(project.as_dict(), ensure_ascii=False, indent=2)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{project.id}.", suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp.write(payload)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)

    tmp_path.replace(path)
    return project


def load(project_id: str) -> Project:
    path = _path_for(project_id)
    if not path.exists():
        raise ProjectNotFound(f"Projekt {project_id!r} neexistuje.")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"Projekt {project_id!r} je poškozený: {exc}") from exc

    payload.setdefault("id", project_id)
    return Project.from_dict(payload)


def load_or_create(project_id: str, name: Optional[str] = None) -> Project:
    """Načte projekt, a když ještě neexistuje, založí prázdný."""
    try:
        return load(project_id)
    except ProjectNotFound:
        return save(Project(id=validate_id(project_id), name=name or project_id))


def delete(project_id: str) -> None:
    path = _path_for(project_id)
    if not path.exists():
        raise ProjectNotFound(f"Projekt {project_id!r} neexistuje.")
    path.unlink()


def list_projects() -> List[Dict[str, Any]]:
    """Přehled uložených projektů, nejčerstvější první. Bez obsahu `data`."""
    summaries = []
    for path in projects_dir().glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # poškozený soubor nemá shodit výpis ostatních
        summaries.append(
            {
                "id": payload.get("id", path.stem),
                "name": payload.get("name", path.stem),
                "created_at": payload.get("created_at"),
                "updated_at": payload.get("updated_at"),
            }
        )

    return sorted(summaries, key=lambda p: p.get("updated_at") or "", reverse=True)

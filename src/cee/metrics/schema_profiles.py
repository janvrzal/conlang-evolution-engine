"""Přenositelné profily vah schémat s jasným původem a licenčním režimem."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

PROFILE_KINDS = frozenset({"heuristic", "cc-by-empirical", "user-local-research"})
_BUILTIN_DIR = Path(__file__).resolve().parents[1] / "data" / "profiles"


@dataclass(frozen=True)
class SchemaProfile:
    id: str
    kind: str
    label: str
    description: str
    schema_multipliers: dict[str, float]
    macro: dict[str, float] = field(default_factory=dict)
    # Lexikální profil nese kromě čísel i politiku homofonie (`audit`/`resolve`).
    lexical: dict[str, Any] = field(default_factory=dict)
    license: str = ""
    provenance: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SchemaProfile":
        profile = cls(
            id=str(data["id"]), kind=str(data["kind"]), label=str(data["label"]),
            description=str(data["description"]),
            schema_multipliers={str(k): float(v) for k, v in dict(data.get("schema_multipliers", {})).items()},
            macro={str(k): float(v) for k, v in dict(data.get("macro", {})).items()},
            lexical={str(k): v for k, v in dict(data.get("lexical", {})).items()},
            license=str(data.get("license", "")), provenance=str(data.get("provenance", "")),
        )
        if profile.kind not in PROFILE_KINDS:
            raise ValueError(f"Neznámý typ profilu: {profile.kind!r}")
        if not profile.id or not profile.label:
            raise ValueError("Profil musí mít id a label.")
        if any(value < 0 for value in profile.schema_multipliers.values()):
            raise ValueError("Násobky vah profilu nesmí být záporné.")
        return profile


def load_schema_profile(profile_id: str) -> SchemaProfile:
    """Načte výhradně vestavěný profil; externí soubory jsou import uživatele."""
    path = _BUILTIN_DIR / f"{profile_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Vestavěný profil '{profile_id}' neexistuje.")
    return SchemaProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def available_schema_profiles() -> list[SchemaProfile]:
    return [load_schema_profile(path.stem) for path in sorted(_BUILTIN_DIR.glob("*.json"))]


def load_local_schema_profile(path: str | Path) -> SchemaProfile:
    """Načte uživatelem dodaný profil; volající rozhoduje, zda jej smí použít."""
    return SchemaProfile.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_local_schema_profile(profile: SchemaProfile, path: str | Path) -> None:
    Path(path).write_text(json.dumps(profile.__dict__, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

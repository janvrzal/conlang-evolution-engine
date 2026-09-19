"""Offline adaptér pro PHOIBLE jako kontrolu fonologického inventáře.

Globální kalibrace změn je samostatná v :mod:`cee.metrics.global_baseline`.
PHOIBLE popisuje synchronní inventáře, a proto jej nelze vydávat za korpus
směrovaných historických změn.
"""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from cee.engine.inventory import InventoryView

PHOIBLE_REPOSITORY_URL = "https://github.com/phoible/dev.git"


def _git_revision(repository: Path) -> Optional[str]:
    """Vrátí lokální commit zdroje, pokud cache vznikla z Git repozitáře."""
    if not (repository / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def default_paths(cache_dir: Optional[str | Path] = None) -> Dict[str, Path]:
    """Cesty k lokální, verzované cache PHOIBLE."""
    root = Path(cache_dir) if cache_dir else Path.home() / ".cee" / "phonology"
    return {
        "root": root,
        "phoible_repository": root / "phoible",
        "phoible_raw": root / "phoible" / "data" / "phoible.csv",
        "phoible_model": root / "phoible-inventories.json",
    }


@dataclass(frozen=True)
class InventoryValidationReport:
    accepted: bool
    reasons: List[str] = field(default_factory=list)
    nearest_similarity: float = 0.0


@dataclass
class PhoibleInventoryModel:
    """Lehký model reálných inventářů PHOIBLE, určený jako filtr kandidátů."""

    inventories: List[frozenset[str]]
    provenance: Dict[str, str]

    @classmethod
    def from_csv(cls, path: str | Path) -> "PhoibleInventoryModel":
        source = Path(path)
        grouped: Dict[str, set[str]] = {}
        with source.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                inventory_id, phoneme = row.get("InventoryID"), row.get("Phoneme")
                if inventory_id and phoneme:
                    grouped.setdefault(inventory_id, set()).add(phoneme)
        provenance = {
            "source": "PHOIBLE",
            "format": "phoible.csv",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        revision = _git_revision(source.parent.parent)
        if revision:
            provenance["revision"] = revision
        return cls(
            inventories=[frozenset(value) for value in grouped.values() if value],
            provenance=provenance,
        )

    def as_dict(self) -> Dict[str, object]:
        return {
            "inventories": [sorted(inventory) for inventory in self.inventories],
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhoibleInventoryModel":
        inventories = [
            frozenset(str(phone) for phone in inventory)
            for inventory in list(data.get("inventories", []))
        ]
        return cls(
            inventories=inventories,
            provenance={
                str(key): str(value) for key, value in dict(data.get("provenance", {})).items()
            },
        )

    def validate(self, inventory: InventoryView) -> InventoryValidationReport:
        phones = set(inventory)
        reasons: List[str] = []
        if not phones:
            return InventoryValidationReport(False, ["empty inventory"])

        voiced_pairs = (("b", "p"), ("d", "t"), ("ɡ", "k"), ("g", "k"))
        for voiced, voiceless in voiced_pairs:
            if voiced in phones and voiceless not in phones:
                reasons.append(f"{voiced} lacks voiceless counterpart {voiceless}")

        similarities = [
            len(phones & set(real)) / len(phones | set(real))
            for real in self.inventories
            if phones | set(real)
        ]
        nearest = max(similarities, default=0.0)
        if len(phones) < 2:
            reasons.append("inventory is too small compared with PHOIBLE")
        return InventoryValidationReport(not reasons, reasons, nearest)


def save_phoible_model(model: PhoibleInventoryModel, path: str | Path) -> None:
    """Uloží kompaktní model bez nutnosti číst CSV během simulace."""
    Path(path).write_text(
        json.dumps(model.as_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_phoible_model(path: str | Path) -> PhoibleInventoryModel:
    return PhoibleInventoryModel.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def phoible_status(cache_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """Popis lokální offline cache bez přístupu k síti."""
    paths = default_paths(cache_dir)
    model_path = paths["phoible_model"]
    status: Dict[str, Any] = {
        "available": model_path.is_file(),
        "repository_present": paths["phoible_repository"].is_dir(),
        "model_path": str(model_path),
        "revision": _git_revision(paths["phoible_repository"]),
    }
    if model_path.is_file():
        try:
            model = load_phoible_model(model_path)
            status.update({
                "inventories": len(model.inventories),
                "provenance": model.provenance,
            })
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            status.update({"available": False, "error": str(exc)})
    return status


def update_phoible_cache(cache_dir: Optional[str | Path] = None) -> Dict[str, Any]:
    """Aktualizuje zdroj a vytvoří reprodukovatelný lokální model PHOIBLE."""
    paths = default_paths(cache_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    repository = paths["phoible_repository"]
    if (repository / ".git").is_dir():
        subprocess.run(["git", "-C", str(repository), "pull", "--ff-only"], check=True)
    else:
        subprocess.run(
            ["git", "clone", "--depth", "1", PHOIBLE_REPOSITORY_URL, str(repository)],
            check=True,
        )
    model = PhoibleInventoryModel.from_csv(paths["phoible_raw"])
    save_phoible_model(model, paths["phoible_model"])
    return phoible_status(cache_dir)

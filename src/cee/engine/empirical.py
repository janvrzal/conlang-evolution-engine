"""Offline adaptéry pro empirické fonologické zdroje.

Index Diachronica Redux poskytuje doložené změny ve volném textu; PHOIBLE
poskytuje inventáře v CSV. Tento modul je převádí do malých, verzovaných dat,
která může generátor číst bez sítě a bez závislosti na konkrétní verzi zdroje.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from cee.engine.inventory import InventoryView


def _sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


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
    """Cesty k lokální, verzované cache empirických zdrojů.

    Data nikdy nepatří do repozitáře: čerstvá instalace funguje bez nich a
    uživatel je stáhne explicitním příkazem. Parametr ``cache_dir`` usnadňuje
    testy i izolované běhy.
    """
    root = Path(cache_dir) if cache_dir else Path.home() / ".cee" / "phonology"
    return {
        "root": root,
        "diachronica_raw": root / "index-diachronica-redux",
        "diachronica_priors": root / "index-diachronica-priors.json",
        "phoible_repository": root / "phoible",
        "phoible_raw": root / "phoible" / "data" / "phoible.csv",
        "phoible_model": root / "phoible-inventories.json",
    }


@dataclass(frozen=True)
class DiachronicaPriors:
    """Počty klasifikovaných doložených změn a jejich provenance."""

    counts: Dict[str, int]
    observations: int
    provenance: Dict[str, str]
    #: Normalizovaná strukturální prostředí; nezávislá osa pro V2a.
    environments: Dict[str, int] = field(default_factory=dict)
    annotations: Dict[str, int] = field(default_factory=dict)
    family_annotations: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def balanced_annotations(self, weight: int = 1000) -> Dict[str, int]:
        """Globální baseline s rovnou vahou každé rodiny, ne každého řádku.

        Bez toho by rodina s nejlepším popisem převážila profil jen počtem
        citovaných změn. `weight` je virtuální velikost vzorku na rodinu.
        """
        result: Dict[str, int] = {}
        for counts in self.family_annotations.values():
            total = sum(counts.values())
            if not total:
                continue
            for category, count in counts.items():
                result[category] = result.get(category, 0) + round(weight * count / total)
        return result or dict(self.annotations)

    def multiplier(self, schema_id: str) -> float:
        """Vyhlazený poměr vůči rovnoměrnému prioru (nikdy nula)."""
        if not self.counts or self.observations <= 0:
            return 1.0
        average = self.observations / max(1, len(self.counts))
        # Additivní vyhlazení chrání málo pokrytá schémata před vynulováním.
        return (self.counts.get(schema_id, 0) + 1.0) / (average + 1.0)

    def as_dict(self) -> Dict[str, object]:
        return {"counts": self.counts, "observations": self.observations, "provenance": self.provenance, "environments": self.environments, "annotations": self.annotations, "family_annotations": self.family_annotations}

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "DiachronicaPriors":
        return cls(
            counts={str(key): int(value) for key, value in dict(data.get("counts", {})).items()},
            observations=int(data.get("observations", 0)),
            provenance={str(key): str(value) for key, value in dict(data.get("provenance", {})).items()},
            environments={str(key): int(value) for key, value in dict(data.get("environments", {})).items()},
            annotations={str(key): int(value) for key, value in dict(data.get("annotations", {})).items()},
            family_annotations={str(family): {str(key): int(value) for key, value in dict(counts).items()} for family, counts in dict(data.get("family_annotations", {})).items()},
        )


def _clean_ipa(value: str) -> str:
    return value.replace("*", "").replace("[", "").replace("]", "").strip()


def _is_vowel(value: str) -> bool:
    return bool(re.search(r"[aeiouəɛɔɨʉæɑɒyøœ]", value))


def _classify_change(source: str, target: str, context: str) -> str:
    source, target, context = _clean_ipa(source), _clean_ipa(target), context.lower()
    if not target:
        if "#" in context:
            return "apocope" if _is_vowel(source) else "coda_loss"
        return "syncope" if _is_vowel(source) else "coda_loss"
    if "_i" in context or "_ i" in context or "front" in context:
        return "palatalization"
    if "v _ v" in context or "v_v" in context.replace(" ", ""):
        return "intervocalic_spirantization"
    if _is_vowel(source) and _is_vowel(target):
        return "vowel_shift"
    if source in {"p", "t", "k", "q"} and target in {"f", "s", "x", "h", "ɸ", "θ"}:
        return "unconditional_fricatization"
    if source in {"p", "t", "k"} and target in {"b", "d", "ɡ", "g"}:
        return "lenition"
    if source in {"b", "d", "ɡ", "g"} and target in {"p", "t", "k"}:
        return "unconditional_devoicing"
    return "other_attested"


def _classify_environment(context: str) -> str:
    """Převod zápisu Reduxu na malé, auditovatelné třídy prostředí."""
    compact = re.sub(r"\s+", "", context)
    if not compact:
        return "unconditional"
    if "_#" in compact:
        return "word_final"
    if "#_" in compact:
        return "word_initial"
    if "_" in compact:
        return "conditioned"
    # Poznámkové podmínky (např. /& in onset) nejsou segmentové prostředí.
    return "structural_or_uncertain"


def _annotation_class(source: str, target: str) -> str:
    """Široká V2a anotace, která nezaměňuje nejisté reflexy za schéma enginu."""
    source, target = _clean_ipa(source), _clean_ipa(target)
    if not target:
        return "deletion"
    if _is_vowel(source) and _is_vowel(target):
        return "vowel_change"
    if any(marker in source + target for marker in "[{"):
        return "complex_or_split"
    if source and target:
        return "consonant_change"
    return "unparsed"


def build_diachronic_priors(changes_dir: str | Path) -> DiachronicaPriors:
    """Načte textové změny z Index Diachronica Redux bez závislosti na parseru UI."""
    directory = Path(changes_dir)
    paths = list(directory.glob("*.txt"))
    counts: Dict[str, int] = {}
    environments: Dict[str, int] = {}
    annotations: Dict[str, int] = {}
    family_annotations: Dict[str, Dict[str, int]] = {}
    observations = 0
    for path in paths:
        family = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- "):
                continue
            # Redux používá lomítko i pro prázdný výsledek (`*a / / _#`),
            # proto nesmíme dělit jen přes přesně mezerovaný oddělovač.
            fields = [field.strip() for field in line[2:].split("/")]
            if len(fields) < 2:
                continue
            source, target = fields[0], fields[1]
            context = " / ".join(fields[2:]) if len(fields) > 2 else ""
            category = _classify_change(source, target, context)
            counts[category] = counts.get(category, 0) + 1
            environment = _classify_environment(context)
            environments[environment] = environments.get(environment, 0) + 1
            annotation = _annotation_class(source, target)
            annotations[annotation] = annotations.get(annotation, 0) + 1
            per_family = family_annotations.setdefault(family, {})
            per_family[annotation] = per_family.get(annotation, 0) + 1
            observations += 1
    provenance = {
        "source": "Index Diachronica Redux",
        "format": "changes/*.txt",
        "sha256": _sha256(paths),
    }
    revision = _git_revision(directory.parent.parent)
    if revision:
        provenance["revision"] = revision
    return DiachronicaPriors(
        counts=counts,
        observations=observations,
        provenance=provenance,
        environments=environments,
        annotations=annotations,
        family_annotations=family_annotations,
    )


def save_diachronic_priors(priors: DiachronicaPriors, path: str | Path) -> None:
    Path(path).write_text(json.dumps(priors.as_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def load_diachronic_priors(path: str | Path) -> DiachronicaPriors:
    return DiachronicaPriors.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


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
    def from_dict(cls, data: Dict[str, object]) -> "PhoibleInventoryModel":
        inventories = [
            frozenset(str(phone) for phone in inventory)
            for inventory in list(data.get("inventories", []))
        ]
        return cls(
            inventories=inventories,
            provenance={str(key): str(value) for key, value in dict(data.get("provenance", {})).items()},
        )

    def validate(self, inventory: InventoryView) -> InventoryValidationReport:
        phones = set(inventory)
        reasons: List[str] = []
        if not phones:
            return InventoryValidationReport(False, ["empty inventory"])

        # PHOIBLE-backed sanity rules: znělá okluziva bez odpovídající neznělé
        # je natolik vzácná, že ji jako generovaný mezistav odmítáme.
        voiced_pairs = (("b", "p"), ("d", "t"), ("ɡ", "k"), ("g", "k"))
        for voiced, voiceless in voiced_pairs:
            if voiced in phones and voiceless not in phones:
                reasons.append(f"{voiced} lacks voiceless counterpart {voiceless}")

        similarities = [len(phones & set(real)) / len(phones | set(real)) for real in self.inventories if phones | set(real)]
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


def build_empirical_cache(cache_dir: Optional[str | Path] = None) -> Dict[str, str]:
    """Převede už stažené zdroje na cache používanou simulátorem.

    Síťovou část záměrně nedrží tady: testy a runtime mohou funkci používat
    nad lokálními soubory a jediným účelem cache je zafixovat vstupní verzi.
    """
    paths = default_paths(cache_dir)
    changes_dir = paths["diachronica_raw"] / "data" / "changes"
    if not changes_dir.is_dir():
        raise FileNotFoundError(f"Index Diachronica changes nebyly nalezeny: {changes_dir}")
    if not paths["phoible_raw"].is_file():
        raise FileNotFoundError(f"PHOIBLE CSV nebylo nalezeno: {paths['phoible_raw']}")

    priors = build_diachronic_priors(changes_dir)
    model = PhoibleInventoryModel.from_csv(paths["phoible_raw"])
    paths["root"].mkdir(parents=True, exist_ok=True)
    save_diachronic_priors(priors, paths["diachronica_priors"])
    save_phoible_model(model, paths["phoible_model"])
    return {
        "diachronica_sha256": priors.provenance["sha256"],
        "phoible_sha256": model.provenance["sha256"],
        "diachronica_revision": priors.provenance.get("revision", "local-files"),
        "phoible_revision": model.provenance.get("revision", "local-files"),
        "observations": str(priors.observations),
        "inventories": str(len(model.inventories)),
    }

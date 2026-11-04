"""Výřez sémantických vztahů pro základní slovní zásobu enginu v2.

Ze stažených dat (``cee`` cache v ``~/.cee``) vytáhne vztahy mezi pojmy
``default_concepts`` v ``src/cee/data/v2_defaults.json`` a uloží je do
``src/cee/data/v2_core_semantics.json``. Výřez je malý, nese citace,
licence a SHA-256 vstupů, takže simulace i CI fungují bez sítě a bez cache.

- **DatSemShift** (Zalizniak a kol. 2024, CC BY 4.0): orientované posuny
  významu (``polysemy``) a odvození (``derivation``), počítané po rodinách.
- **CLICS⁴** (Tjuka a kol. 2024, CC BY 4.0): kolexifikace, počet jazyků.

Spuštění: ``python scripts/build_v2_core_semantics.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import networkx as nx

HOME = Path.home() / ".cee"
DATSEMSHIFT = HOME / "data" / "datsemshift" / "cldf" / "parameters.csv"
COMBINED = HOME / "semantics" / "graph.graphml"
OUT = Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_core_semantics.json"
DEFAULT_CONCEPTS = json.loads(
    (Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_defaults.json").read_text(encoding="utf-8")
)["default_concepts"]

#: Pojmy, jejichž Concepticon glos se liší od anglického ID.
GLOSS_OVERRIDES = {
    "we": "WE (INCLUSIVE)", "horn": "HORN (ANATOMY)", "breasts": "BREAST",
    "fly": "FLY (MOVE THROUGH AIR)", "lie": "LIE (REST)", "rain": "RAIN (PRECIPITATION)",
    "earth": "EARTH (SOIL)", "smoke": "SMOKE (EXHAUST)", "burn": "BURN (SOMETHING)",
    "day": "DAY (NOT NIGHT)", "trade": "TRADE OR BARTER", "work": "WORK (LABOUR)",
    "old": "OLD (AGED)", "grease": "FAT (ORGANIC SUBSTANCE)",
}
#: Kolexifikace slabší než tolik jazyků se nebere (šum jednotlivých slovníků).
MIN_COLEXIFICATION_LANGUAGES = 5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    gloss_of = {concept: GLOSS_OVERRIDES.get(concept, concept.upper()) for concept in DEFAULT_CONCEPTS}
    concept_of = {gloss: concept for concept, gloss in gloss_of.items()}
    relations: dict[tuple[str, str], dict[str, int]] = {}

    local: dict[str, str] = {}
    rows = list(csv.DictReader(DATSEMSHIFT.open(encoding="utf-8")))
    for row in rows:
        gloss = (row.get("Concepticon_Gloss") or "").strip().upper()
        if gloss in concept_of:
            local[row["ID"]] = concept_of[gloss]
    for row in rows:
        source = local.get(row["ID"])
        if source is None:
            continue
        for entry in json.loads(row.get("Target_Concepts") or "[]"):
            target = local.get(entry.get("ID"))
            if target is None or target == source:
                continue
            item = relations.setdefault((source, target), {})
            item["polysemy"] = item.get("polysemy", 0) + int(entry.get("PolysemyByFamily") or 0)
            item["derivation"] = item.get("derivation", 0) + int(entry.get("DerivationByFamily") or 0)

    graph = nx.read_graphml(COMBINED)
    for u, v, data in graph.edges(data=True):
        source, target = concept_of.get(str(u).upper()), concept_of.get(str(v).upper())
        if source is None or target is None or source == target:
            continue
        if data.get("type") != "colexification":
            continue
        weight = int(data.get("weight") or 0)
        if weight >= MIN_COLEXIFICATION_LANGUAGES:
            relations.setdefault((source, target), {})["colexification"] = weight

    found = {concept for pair in relations for concept in pair}
    payload = {
        "description": "Sémantické vztahy mezi pojmy základní slovní zásoby enginu v2.",
        "sources": [
            {
                "name": "DatSemShift", "license": "CC-BY-4.0", "file": "cldf/parameters.csv",
                "sha256": _sha256(DATSEMSHIFT),
                "citation": "Zalizniak A. et al. (2024). Database of Semantic Shifts. Moscow: "
                            "Institute of Linguistics, Russian Academy of Sciences.",
            },
            {
                "name": "CLICS4", "license": "CC-BY-4.0", "file": "clics4-graph.gml via graph.graphml",
                "sha256": _sha256(COMBINED),
                "citation": "Tjuka A., Forkel R., Rzymski C., List J.-M. (2024). CLICS⁴: "
                            "Database of Cross-Linguistic Colexifications.",
            },
        ],
        "concepts": {concept: gloss_of[concept] for concept in DEFAULT_CONCEPTS if concept in found},
        "relations": [
            {"source": source, "target": target, **{key: value for key, value in values.items() if value}}
            for (source, target), values in sorted(relations.items())
            if any(values.values())
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{len(payload['relations'])} vztahů mezi {len(payload['concepts'])} pojmy → {OUT}")


if __name__ == "__main__":
    main()

"""Výřez sémantických vztahů pro celý katalog pojmů enginu v2.

Jako ``build_v2_core_semantics.py``, jen pro všechny významy katalogu WOLD
(``cee/data/v2_concepts.json``, ``catalog``) s Concepticonem, ne jen pro
149 pojmů ``DEFAULT_CONCEPTS``. Výřez je samostatný soubor
``src/cee/data/v2_catalog_semantics.json``, aby se výchozí
``v2_core_semantics.json`` a tím i výsledky výchozího světa nezměnily.
Čte ho ``cee.v2.vocabulary`` pro slovníky větší než výchozí.

- **DatSemShift** (Zalizniak a kol. 2024, CC BY 4.0): orientované posuny
  významu (``polysemy``) a odvození (``derivation``), počítané po rodinách.
- **CLICS⁴** (Tjuka a kol. 2024, CC BY 4.0): kolexifikace, počet jazyků
  (aspoň ``MIN_COLEXIFICATION_LANGUAGES``).

Pojmy se spojují přes ID Concepticonu (DatSemShift má sloupec
``Concepticon_ID``, uzly grafu CLICS se párují podle glosu), takže
výřez nezávisí na ID pojmů enginu. Soubor je úsporný: jeden vztah na řádek,
``[zdroj, cíl, polysemy, derivation, colexification]``.

Pojmy ``DEFAULT_CONCEPTS`` mají v ``v2_core_semantics.json`` glos, který se
občas liší od glosu jejich významu ve WOLD (*mountain*: MOUNTAIN proti
MOUNTAIN OR HILL). Takové pojmy dostanou v ``aliases`` druhé ID Concepticonu,
aby se jejich vztahy k novým pojmům nepřišly o doklady, které už má výchozí
výřez.

Spuštění: ``python scripts/build_v2_catalog_semantics.py``.
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
CLICS4 = HOME / "data" / "clics4" / "clics4-graph.gml"
DATA = Path(__file__).resolve().parents[1] / "src" / "cee" / "data"
CONCEPTS = DATA / "v2_concepts.json"
CORE = DATA / "v2_core_semantics.json"
OUT = DATA / "v2_catalog_semantics.json"

#: Kolexifikace slabší než tolik jazyků se nebere (šum jednotlivých slovníků).
MIN_COLEXIFICATION_LANGUAGES = 5


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    catalog = json.loads(CONCEPTS.read_text(encoding="utf-8"))["catalog"]
    gloss_of = {int(item["concepticon_id"]): str(item["concepticon_gloss"])
                for item in catalog if item["concepticon_id"] and item["concepticon_gloss"]}
    relations: dict[tuple[int, int], dict[str, int]] = {}

    rows = list(csv.DictReader(DATSEMSHIFT.open(encoding="utf-8")))
    graph = nx.read_graphml(COMBINED)
    # Glos semantického výřezu pojmu enginu → ID Concepticonu (z DatSemShift). Uzly CLICS
    # se spojují přes glos, ne přes jejich ``concepticon_id``: ten se u některých pojmů
    # liší od ID v Concepticonu, ze kterého je katalog.
    by_gloss = {str(row["Concepticon_Gloss"]).upper(): int(row["Concepticon_ID"])
                for row in rows if row.get("Concepticon_ID") and row.get("Concepticon_Gloss")}
    core = json.loads(CORE.read_text(encoding="utf-8"))["concepts"]
    wold_of = {concept: int(entry["concepticon_id"])
               for concept, entry in json.loads(CONCEPTS.read_text(encoding="utf-8"))["concepts"].items()
               if entry["concepticon_id"]}
    aliases = {}
    for concept, gloss in sorted(core.items()):
        alias = by_gloss.get(str(gloss).upper())
        if alias is not None and alias != wold_of.get(concept):
            aliases[concept] = alias
            gloss_of.setdefault(alias, str(gloss))

    local: dict[str, int] = {}
    for row in rows:
        if row.get("Concepticon_ID") and int(row["Concepticon_ID"]) in gloss_of:
            local[row["ID"]] = int(row["Concepticon_ID"])
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

    ids = {gloss.upper(): concept for concept, gloss in gloss_of.items()}
    for u, v, data in graph.edges(data=True):
        source, target = ids.get(str(u).upper()), ids.get(str(v).upper())
        if source not in gloss_of or target not in gloss_of or source == target:
            continue
        if data.get("type") != "colexification":
            continue
        weight = int(data.get("weight") or 0)
        if weight >= MIN_COLEXIFICATION_LANGUAGES:
            relations.setdefault((source, target), {})["colexification"] = weight

    kept = [(pair, values) for pair, values in sorted(relations.items()) if any(values.values())]
    found = sorted({concept for pair, _ in kept for concept in pair})
    payload = {
        "description": "Sémantické vztahy mezi významy katalogu WOLD (spojené přes ID Concepticonu) "
                       "pro slovníky enginu v2 větší než výchozí. Vztah: [zdroj, cíl, polysemy, "
                       "derivation, colexification].",
        "sources": [
            {
                "name": "DatSemShift", "license": "CC-BY-4.0", "file": "cldf/parameters.csv",
                "sha256": _sha256(DATSEMSHIFT),
                "citation": "Zalizniak A. et al. (2024). Database of Semantic Shifts. Moscow: "
                            "Institute of Linguistics, Russian Academy of Sciences.",
            },
            {
                "name": "CLICS4", "license": "CC-BY-4.0", "file": "clics4-graph.gml via graph.graphml",
                "sha256": {"graph.graphml": _sha256(COMBINED), "clics4-graph.gml": _sha256(CLICS4)},
                "citation": "Tjuka A., Forkel R., Rzymski C., List J.-M. (2024). CLICS⁴: "
                            "Database of Cross-Linguistic Colexifications.",
            },
            {
                "name": "Katalog významů WOLD (cee/data/v2_concepts.json)", "license": "CC-BY-4.0",
                "sha256": {"v2_concepts.json": _sha256(CONCEPTS), "v2_core_semantics.json": _sha256(CORE)},
                "citation": "Haspelmath, Martin & Tadmor, Uri (eds.) 2009. World Loanword Database. Leipzig: "
                            "Max Planck Institute for Evolutionary Anthropology.",
            },
        ],
        "min_colexification_languages": MIN_COLEXIFICATION_LANGUAGES,
        "aliases": aliases,
        "concepts": {str(concept): gloss_of[concept] for concept in found},
    }
    head = json.dumps({**payload, "relations": "@RELATIONS@"}, ensure_ascii=False, indent=1)
    lines = ",\n".join(
        "  " + json.dumps([source, target, values.get("polysemy", 0), values.get("derivation", 0),
                           values.get("colexification", 0)])
        for (source, target), values in kept
    )
    OUT.write_text(head.replace('"@RELATIONS@"', "[\n" + lines + "\n ]") + "\n", encoding="utf-8")
    print(f"{len(kept)} vztahů mezi {len(found)} pojmy z {len(gloss_of)} → {OUT} ({OUT.stat().st_size} B)")


if __name__ == "__main__":
    main()

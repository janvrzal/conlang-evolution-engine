"""Data o pojmech z World Loanword Database (WOLD) pro engine v2.

Z CLDF verze WOLD (Haspelmath & Tadmor 2009; lexibank/wold, CC BY 4.0;
stažené v ``~/.cee/data/wold``) vytáhne pro každý význam sémantickou oblast
a skóre výpůjčky, stáří a jednoduchosti (průměry přes 41 jazyků) a uloží je
do ``src/cee/data/v2_concepts.json``:

- ``concepts``: pojmy enginu (``default_concepts`` v ``src/cee/data/v2_defaults.json``)
  spárované s významem WOLD přes glos Concepticonu;
- ``catalog``: všechny významy WOLD doložené aspoň v ``MIN_LANGUAGES``
  jazycích (zásobník pro větší slovník);
- ``fields`` a ``domains``: oblasti WOLD a jejich přiřazení k doménám
  enginu, tedy k mechanismům, které na slova té domény působí nejvíc
  (elita, liturgie, obchod, čtení). Přiřazení je náš úsudek (``DOMAINS``),
  ne data WOLD.

Výřez nese citaci, licenci, verzi a SHA-256 vstupu, takže engine i CI
fungují bez sítě a bez cache.

Stažení dat:  ``curl -L -o wold.zip https://codeload.github.com/lexibank/wold/zip/refs/heads/master``
do ``~/.cee/data/wold`` a rozbalit. Spuštění: ``python scripts/build_v2_concepts.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

WOLD = Path.home() / ".cee" / "data" / "wold" / "wold-master" / "cldf"
OUT = Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_concepts.json"
DEFAULT_CONCEPTS = json.loads(
    (Path(__file__).resolve().parents[1] / "src" / "cee" / "data" / "v2_defaults.json").read_text(encoding="utf-8")
)["default_concepts"]
#: Verze dat (commit lexibank/wold), ze které je výřez.
WOLD_COMMIT = "1df62b9bdc7292b35982aea49b4d5bd1951f6f3e"
#: Význam doložený v méně jazycích je doplněk jednoho slovníku (ID ``…-999xx``).
MIN_LANGUAGES = 10

#: Glos Concepticonu u pojmů enginu, kde se liší od glosu ve WOLD.
GLOSS = {
    "child": "CHILD (YOUNG HUMAN)", "god": "DEITY", "hair": "HAIR (HEAD)", "know": "KNOW (SOMETHING)",
    "lie": "LIE DOWN", "louse": "HEAD LOUSE", "mountain": "MOUNTAIN OR HILL", "old": "OLD",
    "river": "FLOWING BODY OF WATER", "spirit": "SOUL", "stone": "STONE OR ROCK", "war": "BATTLE",
    "trade": "TRADE OR BARTER", "close": "SHUT",
    # WOLD nemá obecný obřad; nejbližší obecný význam oblasti víry.
    "ritual": "WORSHIP",
}

#: Domény enginu: které oblasti WOLD do nich patří a který mechanismus na ně
#: působí nejvíc. Úsudek podle průměrné půjčitelnosti oblastí a podle toho,
#: kudy výpůjčky do jazyka přicházejí (Thomason & Kaufman 1988; Tadmor 2009).
DOMAINS = {
    "power": {
        "description": "moc, správa, právo a válka; vymění je nová elita (dobytí, cizí vládci)",
        "fields": ("Social and political relations", "Law", "Warfare and hunting"),
    },
    "religion": {
        "description": "víra a obřady; přicházejí s liturgickým jazykem",
        "fields": ("Religion and belief",),
    },
    "culture": {
        "description": "věci, technika, jídlo, oblečení, hospodaření a počítání; přicházejí obchodem a kontaktem",
        "fields": ("Modern world", "Agriculture and vegetation", "Food and drink", "Clothing and grooming",
                   "The house", "Possession", "Basic actions and technology", "Quantity"),
    },
    "learned": {
        "description": "řeč, myšlení, city a čas; přicházejí čtením a školou",
        "fields": ("Speech and language", "Cognition", "Emotions and values", "Time"),
    },
    "core": {
        "description": "domácí jádro: tělo, prostor, vnímání, pohyb, příroda, příbuzní, zvířata, funkční slova",
        "fields": ("The body", "Spatial relations", "Sense perception", "Motion", "The physical world",
                   "Kinship", "Animals", "Miscellaneous function words"),
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _score(value: str) -> float | None:
    return round(float(value), 4) if value else None


def main() -> None:
    domain_of = {field: domain for domain, entry in DOMAINS.items() for field in entry["fields"]}
    parameters = list(csv.DictReader((WOLD / "parameters.csv").open(encoding="utf-8")))
    languages = Counter()
    seen: set[tuple[str, str]] = set()
    for row in csv.DictReader((WOLD / "forms.csv").open(encoding="utf-8")):
        key = (row["Parameter_ID"], row["Language_ID"])
        if key not in seen:
            seen.add(key)
            languages[row["Parameter_ID"]] += 1
    unknown = sorted({row["Semantic_field"] for row in parameters} - set(domain_of))
    if unknown:
        raise SystemExit(f"Oblasti WOLD bez domény: {unknown}")

    def entry(row: dict[str, str]) -> dict[str, object]:
        return {
            "wold_id": row["ID"], "name": row["Name"],
            "concepticon_id": int(row["Concepticon_ID"]) if row["Concepticon_ID"] else None,
            "concepticon_gloss": row["Concepticon_Gloss"] or None,
            "field": row["Semantic_field"], "category": row["Semantic_category"],
            "domain": domain_of[row["Semantic_field"]],
            "borrowed": _score(row["Borrowed_score"]), "age": _score(row["Age_score"]),
            "simplicity": _score(row["Simplicity_score"]),
            "languages": languages[row["ID"]], "core_list": row["Core_list"] == "yes",
        }

    catalog = [entry(row) for row in parameters if languages[row["ID"]] >= MIN_LANGUAGES]
    by_gloss: dict[str, dict[str, object]] = {}
    for item in catalog:
        gloss = item["concepticon_gloss"]
        if isinstance(gloss, str) and gloss not in by_gloss:
            by_gloss[gloss] = item
    semantics = dict(json.loads((OUT.parent / "v2_core_semantics.json").read_text(encoding="utf-8"))["concepts"])
    concepts = {}
    for concept in DEFAULT_CONCEPTS:
        found = by_gloss.get(GLOSS.get(concept, semantics.get(concept, concept.upper())))
        if found is not None:
            concepts[concept] = found
    missing = [concept for concept in DEFAULT_CONCEPTS if concept not in concepts]
    if missing:
        raise SystemExit(f"Pojmy bez významu ve WOLD (doplň je do GLOSS): {missing}")
    fields = {}
    for field in sorted(domain_of):
        scores = [item["borrowed"] for item in catalog if item["field"] == field and item["borrowed"] is not None]
        fields[field] = {"domain": domain_of[field], "meanings": len(scores),
                         "borrowed_mean": round(sum(scores) / len(scores), 4)}  # type: ignore[arg-type]
    data = {
        "description": "Sémantická oblast, doména enginu a skóre výpůjčky, stáří a jednoduchosti pojmů "
                       "(průměry přes jazyky WOLD; 1 = ve všech jazycích přejaté, staré, jednoduché).",
        "sources": [{
            "name": "World Loanword Database (CLDF, lexibank/wold)",
            "citation": "Haspelmath, Martin & Tadmor, Uri (eds.) 2009. World Loanword Database. Leipzig: "
                        "Max Planck Institute for Evolutionary Anthropology. https://wold.clld.org",
            "license": "CC BY 4.0", "url": "https://github.com/lexibank/wold", "commit": WOLD_COMMIT,
            "sha256": {"parameters.csv": _sha256(WOLD / "parameters.csv"), "forms.csv": _sha256(WOLD / "forms.csv")},
        }],
        "min_languages": MIN_LANGUAGES,
        "domains": {name: {"description": entry["description"], "fields": list(entry["fields"])}
                    for name, entry in DOMAINS.items()},
        "fields": fields,
        "concepts": concepts,
        "catalog": catalog,
    }
    # Katalog po jednom řádku na význam (čitelné v diffu, třetinová velikost).
    catalog_text = ",\n".join("  " + json.dumps(item, ensure_ascii=False) for item in catalog)
    head = json.dumps({**data, "catalog": "@CATALOG@"}, ensure_ascii=False, indent=1)
    OUT.write_text(head.replace('"@CATALOG@"', "[\n" + catalog_text + "\n ]") + "\n", encoding="utf-8")
    print(f"{len(concepts)} pojmů enginu, katalog {len(catalog)} významů → {OUT}")


if __name__ == "__main__":
    main()

"""Frekvence pojmů pro engine v2 z dat (``src/cee/data/v2_concept_frequencies.json``).

Engine dosud frekvence pojmů generoval (prvních 20 pojmů 0,9, ostatní
log-rovnoměrně náhodně). Skript je odhadne z dat s licencí CC BY:

1. **Calude & Pagel (2011)**, seznam ``Calude-2011-200`` v Concepticonu
   (CC BY 4.0): logaritmus četnosti 200 pojmů Swadeshova seznamu na milion
   slov v korpusech 17 jazyků. Bere se průměr přes jazyky; četnosti se mezi
   jazyky shodují (průměrná korelace 0,73), takže je to mezijazyková
   frekvence pojmu.
2. **Leipzig Corpora Collection** (stažené korpusy, CC BY; Goldhahn,
   Eckart & Quasthoff 2012) a slova WOLD: pro každý význam WOLD se sečte
   četnost jeho slov v sedmi jazycích (``CORPORA``) na milion slov;
   slovo, které WOLD v jazyce uvádí u více významů, se mezi ně rozdělí.
   Každý jazyk se posune na stupnici Calude & Pagel (průměrný rozdíl na
   společných pojmech) a jazyky se zprůměrují.
3. Význam bez obou (žádné jeho slovo v korpusech) dostane odhad regresí
   z vlastností WOLD (stáří, jednoduchost, půjčitelnost, slovní druh,
   základní seznam) naučenou na ostatních.

Pojmy Swadeshova seznamu berou Calude & Pagel, ostatní korpusy Leipzig.
Výsledek je ``log10`` výskytů na milion slov a zdroj odhadu, pro pojmy
enginu i pro katalog WOLD (``v2_concepts.json``).

Data: korpusy ``CORPORA`` z https://downloads.wortschatz-leipzig.de/corpora/
rozbalené v ``~/.cee/data/leipzig`` (stačí ``*-words.txt``),
WOLD v ``~/.cee/data/wold`` (viz ``build_v2_concepts.py``).
Spuštění: ``python scripts/build_v2_concept_frequencies.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONCEPTS = ROOT / "src" / "cee" / "data" / "v2_concepts.json"
OUT = ROOT / "src" / "cee" / "data" / "v2_concept_frequencies.json"
DATA = Path.home() / ".cee" / "data"
CALUDE = DATA / "concepticon-lists" / "Calude-2011-200.tsv"
CALUDE_URL = ("https://raw.githubusercontent.com/concepticon/concepticon-data/"
              "35a9d237b2fb836e629774c7f5515f26c5e5ecd1/concepticondata/conceptlists/Calude-2011-200.tsv")
WOLD_FORMS = DATA / "wold" / "wold-master" / "cldf" / "forms.csv"
LEIPZIG = DATA / "leipzig"
LEIPZIG_URL = "https://downloads.wortschatz-leipzig.de/corpora/{}.tar.gz"
#: Jazyk WOLD → korpusy Leipzig (zprávy a Wikipedie, kde jsou obojí).
CORPORA = {
    "English": ("eng_news_2024_300K", "eng_wikipedia_2016_300K"),
    "Dutch": ("nld_news_2024_300K", "nld_wikipedia_2021_300K"),
    "Romanian": ("ron_news_2024_300K", "ron_wikipedia_2021_300K"),
    "Indonesian": ("ind_news_2024_300K", "ind_wikipedia_2021_300K"),
    "Vietnamese": ("vie_news_2022_300K", "vie_wikipedia_2021_300K"),
    "Swahili": ("swa_wikipedia_2021_100K",),
    "Malagasy": ("plt_wikipedia_2021_100K",),
}
#: Jazyky, jejichž zápis ve WOLD nese přízvuk navíc proti pravopisu.
STRIP_ACCENTS = {"Malagasy"}


def normalized(language: str, word: str) -> str:
    """Tvar slova WOLD v pravopisu korpusu (malá písmena, bez čísla homonyma)."""
    word = re.sub(r"\s*\(\d+\)", "", word).strip().lower()
    if language in STRIP_ACCENTS:
        word = "".join(char for char in unicodedata.normalize("NFD", word) if not unicodedata.combining(char))
    if language == "Romanian":
        word = word.replace("ş", "ș").replace("ţ", "ț")
    return unicodedata.normalize("NFC", word)


def corpus(name: str) -> tuple[dict[str, float], int]:
    """Četnost slov (malá písmena) na milion slov a počet slov korpusu."""
    # Počet slov korpusu je součet četností seznamu (korpusy Wikipedie nemají
    # metadata; u všech se tak počítá stejně).
    folder = LEIPZIG / name
    counts: Counter[str] = Counter()
    with (folder / f"{name}-words.txt").open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                # Rumunské ş/ţ se cedilou a ș/ț s čárkou jsou totéž písmeno.
                word = unicodedata.normalize("NFC", parts[1].lower()).replace("ş", "ș").replace("ţ", "ț")
                counts[word] += int(parts[2])
    tokens = sum(counts.values())
    return {word: count * 1e6 / tokens for word, count in counts.items()}, tokens


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    concepts = json.loads(CONCEPTS.read_text(encoding="utf-8"))
    catalog = concepts["catalog"]
    wanted = {item["wold_id"] for item in catalog}
    if not CALUDE.exists():
        CALUDE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CALUDE_URL, CALUDE)  # noqa: S310
    calude: dict[int, float] = {}
    with CALUDE.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            # Chybějící hodnota je prázdná nebo „-“.
            values = [float(value) for key, value in row.items()
                      if key.endswith("_FREQUENCY") and value and value != "-"]
            if row["CONCEPTICON_ID"] and values:
                calude[int(row["CONCEPTICON_ID"])] = sum(values) / len(values)

    # Slova WOLD v jazycích korpusů: (jazyk, tvar) → významy.
    words: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in csv.DictReader(WOLD_FORMS.open(encoding="utf-8")):
        if row["Language_ID"] in CORPORA and row["Parameter_ID"] in wanted:
            word = normalized(row["Language_ID"], row["Value"])
            if word and " " not in word and "_" not in word:
                words[(row["Language_ID"], word)].add(row["Parameter_ID"])
    per_language: dict[str, dict[str, float]] = {}
    corpora_info = []
    for language, names in CORPORA.items():
        loaded = [corpus(name) for name in names]
        corpora_info += [{"name": name, "language": language, "tokens": tokens}
                         for name, (_, tokens) in zip(names, loaded)]
        totals: dict[str, float] = defaultdict(float)
        for (word_language, word), meanings in words.items():
            if word_language != language:
                continue
            frequency = statistics.mean(table.get(word, 0.0) for table, _ in loaded)
            for meaning in meanings:
                totals[meaning] += frequency / len(meanings)
        per_language[language] = {meaning: math.log10(value) for meaning, value in totals.items() if value > 0}

    by_id = {item["wold_id"]: item for item in catalog}
    offsets = {}
    for language, values in per_language.items():
        shared = [calude[by_id[m]["concepticon_id"]] - v for m, v in values.items()
                  if by_id[m]["concepticon_id"] in calude]
        offsets[language] = statistics.mean(shared)
    corpus_mean: dict[str, tuple[float, int]] = {}
    for meaning in wanted:
        values = [per_language[language][meaning] + offsets[language]
                  for language in CORPORA if meaning in per_language[language]]
        if values:
            corpus_mean[meaning] = (statistics.mean(values), len(values))
    pairs = [(corpus_mean[m][0], calude[by_id[m]["concepticon_id"]]) for m in corpus_mean
             if by_id[m]["concepticon_id"] in calude]
    correlation = float(np.corrcoef([a for a, _ in pairs], [b for _, b in pairs])[0, 1])

    estimate: dict[str, tuple[float, str, int]] = {}
    for item in catalog:
        if item["concepticon_id"] in calude:
            estimate[item["wold_id"]] = (calude[item["concepticon_id"]], "calude2011", 17)
        elif item["wold_id"] in corpus_mean:
            value, count = corpus_mean[item["wold_id"]]
            estimate[item["wold_id"]] = (value, "leipzig", count)
    categories = sorted({item["category"] for item in catalog})

    def features(item: dict) -> list[float]:
        return [1.0, item["age"] or 0.0, item["simplicity"] or 0.0, item["borrowed"] or 0.0,
                1.0 if item["core_list"] else 0.0] + [1.0 if item["category"] == c else 0.0 for c in categories]

    known = [item for item in catalog if item["wold_id"] in estimate]
    coefficients, *_ = np.linalg.lstsq(np.array([features(item) for item in known]),
                                       np.array([estimate[item["wold_id"]][0] for item in known]), rcond=None)
    for item in catalog:
        if item["wold_id"] not in estimate:
            estimate[item["wold_id"]] = (float(np.dot(coefficients, features(item))), "wold-model", 0)

    data = {
        "description": "Frekvence pojmu: log10 výskytů na milion slov na stupnici Calude & Pagel 2011. "
                       "Zdroj: calude2011 = průměr 17 jazyků; leipzig = průměr jazyků korpusů Leipzig "
                       "(slova WOLD), posunutých na stupnici Calude & Pagel; wold-model = odhad z vlastností WOLD.",
        "sources": [
            {"name": "Calude & Pagel 2011 (Concepticon Calude-2011-200)",
             "citation": "Calude, Andreea S. & Pagel, Mark 2011. How do we use language? Shared patterns in the "
                         "frequency of word use across 17 world languages. Phil. Trans. R. Soc. B 366: 1101–1107.",
             "license": "CC BY 4.0 (Concepticon)", "url": CALUDE_URL, "sha256": _sha256(CALUDE)},
            {"name": "Leipzig Corpora Collection",
             "citation": "Goldhahn, Dirk, Eckart, Thomas & Quasthoff, Uwe 2012. Building Large Monolingual "
                         "Dictionaries at the Leipzig Corpora Collection: From 100 to 200 Languages. LREC 2012.",
             "license": "CC BY (korpusy ke stažení)", "url": LEIPZIG_URL.format("*"), "corpora": corpora_info},
            {"name": "World Loanword Database (slova jazyků korpusů)", "license": "CC BY 4.0",
             "sha256": {"forms.csv": _sha256(WOLD_FORMS)}},
        ],
        "alignment": {
            "offsets": {language: round(value, 4) for language, value in offsets.items()},
            "meanings": {language: len(values) for language, values in per_language.items()},
            "leipzig_vs_calude": {"pairs": len(pairs), "correlation": round(correlation, 3)},
        },
        "concepts": {concept: {"log_frequency": round(estimate[entry["wold_id"]][0], 4),
                               "source": estimate[entry["wold_id"]][1],
                               "languages": estimate[entry["wold_id"]][2]}
                     for concept, entry in concepts["concepts"].items()},
        "catalog": {wold_id: [round(value, 4), source, languages]
                    for wold_id, (value, source, languages) in sorted(estimate.items())},
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Leipzig proti Calude: {len(pairs)} společných pojmů, r = {correlation:.3f}")
    print("významů po jazycích:", data["alignment"]["meanings"])
    print("zdroje katalogu:", dict(Counter(source for _, source, _ in estimate.values())))
    print("zdroje pojmů enginu:", dict(Counter(entry["source"] for entry in data["concepts"].values())))


if __name__ == "__main__":
    main()

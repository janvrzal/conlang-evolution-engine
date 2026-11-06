"""Skutečné tempo hláskových změn z IE-CoR pro cíl ``m9::tempo`` (dok. 24).

Pro dvojice (starý jazyk, potomek, časová hloubka v letech) vezme příbuzná slova stejného
významu (stejná sada kognátů, první slovo významu), převede fonemický zápis na hlásky tabulky
enginu stejně jako ``build_v2_iecor_words.py`` (bez přízvuku, délky a melodického přízvuku)
a spočítá průměrnou normalizovanou Levenshteinovu vzdálenost ``d`` a tempo
``r = −ln(1 − d)`` za tisíciletí. Dvojice ``LADĚNÍ`` dávají pásmo cíle, ``KONTROLA`` se k
ladění nepoužívají.

Data: IE-CoR (Heggarty, Anderson a Scarborough 2024, verze 1.1, CC BY 4.0) v
``~/.cee/data/iecor``. Spuštění: ``python scripts/iecor_form_rates.py``.
"""

from __future__ import annotations

import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v2_iecor_words as words  # noqa: E402

LADĚNÍ = [
    ("Latin", 2050, ["Italian", "Spanish", "Portuguese", "French", "Romanian", "Catalan", "Sardinian: Logudoro"]),
    ("Old Church Slavonic", 1100, ["Russian", "Czech", "Polish", "Bulgarian", "Serbo-Croat", "Slovak", "Slovene", "Ukrainian"]),
    ("Old English", 1100, ["English"]),
    ("Old High German", 1100, ["German"]),
]
KONTROLA = [
    ("Greek: Ancient", 2400, ["Greek: Modern Std"]),
    ("Old Icelandic", 800, ["Norwegian: Nynorsk"]),
    ("Old Irish", 1200, ["Gaelic: Irish", "Gaelic: Scottish", "Gaelic: Manx"]),
    ("Armenian: Classical", 1550, ["Armenian: Eastern", "Armenian: Western"]),
]


def levenshtein(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (x != y))
    return row[-1]


def main() -> int:
    cldf = words.CLDF
    known = words.symbols()
    ids = {r["Name"]: r["ID"] for r in csv.DictReader((cldf / "languages.csv").open(encoding="utf-8"))}
    forms: dict[str, dict[str, list[str]]] = defaultdict(dict)
    cognates: dict[str, dict[str, str]] = defaultdict(dict)
    for row in csv.DictReader((cldf / "forms.csv").open(encoding="utf-8")):
        if row["ID"].endswith("-1") and row["Phonemic_Segments"]:
            forms[row["Language_ID"]][row["Parameter_ID"]] = row["Phonemic_Segments"].split()
    for row in csv.DictReader((cldf / "cognates.csv").open(encoding="utf-8")):
        if row["Form_ID"].endswith("-1"):
            language, parameter = row["Form_ID"].split("-")[:2]
            cognates[language][parameter] = row["Cognateset_ID"]

    def clean(segments: list[str]) -> list[str]:
        return [s for s in (words.clean(x, known) for x in segments) if s]

    for title, pairs in (("ladění", LADĚNÍ), ("kontrola", KONTROLA)):
        rates = []
        print(f"== {title}")
        for old, years, modern in pairs:
            a = ids[old]
            for name in modern:
                b = ids[name]
                distances = []
                for parameter, segments in forms[a].items():
                    same = cognates[a].get(parameter)
                    if parameter in forms[b] and same and same == cognates[b].get(parameter):
                        x, y = clean(segments), clean(forms[b][parameter])
                        if x and y:
                            distances.append(levenshtein(x, y) / max(len(x), len(y)))
                d = statistics.mean(distances)
                rate = -math.log(1 - d) / (years / 1000)
                rates.append(rate)
                print(f"  {old} → {name} ({years} let): d = {d:.2f}, r = {rate:.2f} za tisíciletí, n = {len(distances)}")
        print(f"  medián r = {statistics.median(rates):.2f}, rozsah {min(rates):.2f}–{max(rates):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

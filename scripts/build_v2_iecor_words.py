"""Slovníky starých jazyků z IE-CoR pro scénáře engine v2 (dok. 23, M8e).

Z CLDF verze IE-CoR (Heggarty, Anderson a Scarborough 2024, Indo-European Cognate
Relationships database, verze 1.1; lexibank/iecor, CC BY 4.0; stažené v
``~/.cee/data/iecor``) vybere pro pojmy enginu (``default_concepts``) slovo vybraných
starých jazyků a uloží ho do ``src/cee/data/v2_iecor_words.json``:

- pojem enginu se s významem IE-CoR páruje přes ID Concepticonu (``v2_concepts.json``);
- bere se první slovo významu (``…-1``) ve fonemickém zápisu (``Phonemic_Segments``);
- přízvuk, délka a melodický přízvuk se zahodí (engine přízvuk určuje pravidlem, délku
  latina také nemá; čárka by se četla jako tón), stejně jako ostatní diakritika, kterou
  tabulka hlásek nezná;
- u jmen a sloves se odstraní koncovka slovníkového tvaru (``ENDINGS``), protože engine
  přidává vlastní koncovky (latina má z téhož důvodu kmen akuzativu bez ``-m``).
  Seznam koncovek je náš úsudek, ne data IE-CoR.

Galština v IE-CoR fonemický zápis nemá; její pravopis je skoro fonemický a převádí se
pravidly (``GAULISH``). Pojmy, které mají v IE-CoR jiné ID Concepticonu (kámen, hora, řeka …),
se párují podle jména (``ALIASES``). Pojmy, které IE-CoR nemá vůbec (zájmena, zápor,
příbuzenství, kulturní slova), doplní autorský doplněk ``v2_proto_supplement.json`` (dok. 30);
zbytek engine dogeneruje z inventáře hlásek. Se ``--scenario`` skript zapíše slova i do
scénáře Evropy (``scenarios/evropa.json``).

Spuštění: ``python scripts/build_v2_iecor_words.py`` (data:
``curl -L -o iecor.zip https://codeload.github.com/lexibank/iecor/zip/refs/heads/master``
do ``~/.cee/data/iecor`` a rozbalit).
"""

from __future__ import annotations

import csv
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLDF = Path.home() / ".cee" / "data" / "iecor" / "iecor-master" / "cldf"
OUT = ROOT / "src" / "cee" / "data" / "v2_iecor_words.json"
DATA = ROOT / "src" / "cee" / "data"

#: Jazyk scénáře → jazyk IE-CoR.
LANGUAGES = {
    "germanic": "Gothic",
    "slavic": "Old Church Slavonic",
    "greek": "Greek: Ancient",
    "gaulish": "Gaulish",
    "baltic": "Lithuanian",
}
#: Koncovky slovníkového tvaru podle druhu slova (nejdelší první); kmen musí mít
#: aspoň dvě hlásky.
ENDINGS = {
    "Gothic": {"Noun": [["s"]], "Adjective": [["s"]], "Verb": [["j", "a", "n"], ["a", "n"], ["o", "n"]]},
    "Old Church Slavonic": {"Noun": [["ʊ"], ["ɪ"]], "Adjective": [["ʊ"], ["ɪ"]], "Verb": [["t", "i"]]},
    "Greek: Ancient": {
        "Noun": [["o", "s"], ["o", "n"], ["s"]],
        "Adjective": [["o", "s"], ["s"]],
        "Verb": [["o", "m", "a", "i̯"], ["o", "m", "a", "ɪ̯"], ["m", "i"], ["o"], ["ɔ"]],
    },
    "Gaulish": {"Noun": [["o", "s"], ["o", "n"]], "Adjective": [["o", "s"]]},
    # Litevština: jmenné -as, -is, -ys, -us, slovesné -ti (s měkkou i tvrdou souhláskou).
    "Lithuanian": {
        "Noun": [["a", "s"], ["ɪ", "s"], ["i", "s"], ["ʊ", "s"], ["u", "s"], ["ɛ", "s"]],
        "Adjective": [["a", "s"], ["ʊ", "s"], ["u", "s"], ["ɪ", "s"], ["i", "s"]],
        "Verb": [["tʲ", "ɪ"], ["t", "ɪ"], ["tʲ", "i"], ["t", "i"]],
    },
}
#: Pojem enginu → význam IE-CoR (``Name``) tam, kde se ID Concepticonu liší (STONE OR ROCK
#: proti STONE apod.) nebo IE-CoR má blízký význam (maso za flesh, jít za walk).
ALIASES = {
    "stone": "stone", "mountain": "mountain", "river": "river", "rain": "rain", "burn": "burn",
    "flesh": "meat", "walk": "go", "fingernail": "nail", "fly": "fly_V", "louse": "louse",
    "swim": "swim", "skin": "skin",
}
#: Galský pravopis → IPA (nejdelší první).
GAULISH = [
    ("ch", "x"), ("qu", "kʷ"), ("th", "θ"), ("ss", "t͡s"), ("đđ", "t͡s"), ("đ", "t͡s"),
    ("c", "k"), ("x", "x"), ("y", "i"), ("v", "w"),
    ("a", "a"), ("e", "e"), ("i", "i"), ("o", "o"), ("u", "u"),
    ("b", "b"), ("d", "d"), ("g", "ɡ"), ("k", "k"), ("p", "p"), ("t", "t"),
    ("m", "m"), ("n", "n"), ("l", "l"), ("r", "r"), ("s", "s"), ("w", "w"), ("j", "j"), ("f", "f"),
]
#: Značky, které se vždy zahodí: přízvuk, délka, slabičná hranice, melodický přízvuk.
DROP = {
    "ˈ", "ˌ", "ː", "ˑ", ".",
    "\u0301", "\u0300", "\u0302", "\u0342", "\u0304", "\u030b", "\u030f",  # tóny a melodický přízvuk
    "\u031e", "\u031d",  # snížení a zvýšení samohlásky (attické e̞, o̞ = e, o)
}
#: Značky zahozené jen u jednoho jazyka: řecký cirkumflex je v IE-CoR vlnovka, ne nosovost.
EXTRA_DROP = {"Greek: Ancient": frozenset({"\u0303"})}
#: Afrikáty píše IE-CoR bez spojovacího obloučku, tabulka hlásek s ním.
AFFRICATES = {"ts": "t͡s", "dz": "d͡z", "tʃ": "t͡ʃ", "dʒ": "d͡ʒ", "tɕ": "t͡ɕ", "dʑ": "d͡ʑ"}


def symbols() -> set[str]:
    return set(json.loads((DATA / "v2_segments.json").read_text(encoding="utf-8"))["symbols"])


def clean(segment: str, known: set[str], extra: frozenset[str] = frozenset()) -> str | None:
    """Hláska bez zahozených značek; neznámou diakritiku ubírá od konce (tabulka je v NFD)."""
    text = "".join(ch for ch in unicodedata.normalize("NFD", segment) if ch not in DROP and ch not in extra)
    for plain, tied in AFFRICATES.items():
        if text.startswith(plain):
            text = tied + text[len(plain) :]
            break
    while text and text not in known:
        decomposed = unicodedata.normalize("NFD", text)
        marks = [i for i, ch in enumerate(decomposed) if unicodedata.combining(ch) or ch in "ʰʲʷˠˤ̯"]
        if not marks:
            return None
        decomposed = decomposed[: marks[-1]] + decomposed[marks[-1] + 1 :]
        text = decomposed
    return text or None


def gaulish_segments(form: str) -> list[str]:
    word = form.replace("/", ",").split(",")[0].strip().lower()
    word = word.replace("(", "").replace(")", "").replace("-", "").replace("*", "")
    out, i = [], 0
    while i < len(word):
        for spelling, ipa in GAULISH:
            if word.startswith(spelling, i):
                out.append(ipa)
                i += len(spelling)
                break
        else:
            i += 1  # neznámý znak se vynechá
    # u, i před samohláskou na začátku slabiky jsou polosamohlásky
    vowels = {"a", "e", "i", "o", "u"}
    for k in range(len(out) - 1):
        if out[k] in ("u", "i") and out[k + 1] in vowels and (k == 0 or out[k - 1] in vowels):
            out[k] = "w" if out[k] == "u" else "j"
    return out


def strip_ending(segments: list[str], language: str, category: str) -> list[str]:
    for ending in ENDINGS.get(language, {}).get(category, []):
        if len(segments) - len(ending) >= 2 and segments[-len(ending) :] == ending:
            return segments[: -len(ending)]
    return segments


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cldf = Path(args[0]) if args else CLDF
    known = symbols()
    concepts = json.loads((DATA / "v2_concepts.json").read_text(encoding="utf-8"))["concepts"]
    defaults = json.loads((DATA / "v2_defaults.json").read_text(encoding="utf-8"))["default_concepts"]
    by_concepticon = {concepts[c]["concepticon_id"]: c for c in defaults if c in concepts}
    parameter_concept = {
        row["ID"]: by_concepticon.get(int(row["Concepticon_ID"]))
        for row in csv.DictReader((cldf / "parameters.csv").open(encoding="utf-8"))
        if row.get("Concepticon_ID")
    }
    by_name = {v: k for k, v in ALIASES.items() if k in defaults}
    for row in csv.DictReader((cldf / "parameters.csv").open(encoding="utf-8")):
        if parameter_concept.get(row["ID"]) is None and row["Name"] in by_name:
            parameter_concept[row["ID"]] = by_name[row["Name"]]
    supplement = json.loads((DATA / "v2_proto_supplement.json").read_text(encoding="utf-8"))["languages"]
    language_ids = {
        row["Name"]: row["ID"] for row in csv.DictReader((cldf / "languages.csv").open(encoding="utf-8"))
    }
    wanted = {language_ids[name]: name for name in LANGUAGES.values()}
    first: dict[tuple[str, str], dict] = {}
    for row in csv.DictReader((cldf / "forms.csv").open(encoding="utf-8")):
        name = wanted.get(row["Language_ID"])
        concept = parameter_concept.get(row["Parameter_ID"])
        if name and concept and (name, concept) not in first:
            first[(name, concept)] = row
    result: dict[str, dict] = {}
    for scenario_id, name in LANGUAGES.items():
        words, dropped = {}, Counter()
        for concept in defaults:
            row = first.get((name, concept))
            if row is None:
                continue
            if name == "Gaulish":
                raw = gaulish_segments(row["Form"])
            else:
                raw = row["Phonemic_Segments"].split()
            segments = []
            for segment in raw:
                cleaned = clean(segment, known, EXTRA_DROP.get(name, frozenset()))
                if cleaned is None:
                    dropped[segment] += 1
                else:
                    segments.append(cleaned)
            segments = strip_ending(segments, name, concepts[concept]["category"])
            if len(segments) >= 2:
                words[concept] = "".join(segments)
        added = 0
        for concept, word in supplement.get(scenario_id, {}).items():
            if concept in defaults and concept not in words:
                words[concept] = unicodedata.normalize("NFD", word)
                added += 1
        inventory = Counter(s for w in words.values() for s in split(w, known))
        result[scenario_id] = {
            "iecor_language": name,
            "words": dict(sorted(words.items())),
            "inventory": [s for s, _ in inventory.most_common()],
        }
        print(f"{scenario_id} ({name}): {len(words)} pojmů (doplněk {added}), vynecháno {dict(dropped)}")
    if "--scenario" in sys.argv:
        path = DATA / "scenarios" / "evropa.json"
        scenario = json.loads(path.read_text(encoding="utf-8"))
        for language in scenario["languages"]:
            if language["id"] in result:
                language["words"] = result[language["id"]]["words"]
                # Hlásky doplňku, které inventář jazyka ještě nemá (řecké b z β).
                listed = set(language.get("consonants", [])) | set(language.get("vowels", []))
                for word in language["words"].values():
                    for segment in split(word, known):
                        if listed and segment not in listed:
                            kind = "vowels" if syllabic(segment) else "consonants"
                            language[kind].append(segment)
                            listed.add(segment)
        path.write_text(json.dumps(scenario, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT.write_text(
        json.dumps(
            {
                "description": "Slova starých jazyků pro pojmy enginu z IE-CoR a autorského doplňku v2_proto_supplement.json (scripts/build_v2_iecor_words.py, dok. 23 a 30).",
                "source": {
                    "citation": "Heggarty, Paul & Anderson, Cormac & Scarborough, Matthew 2024. Indo-European Cognate Relationships database (IE-CoR version 1.1). Leipzig: Max Planck Institute for Evolutionary Anthropology. https://iecor.clld.org",
                    "license": "CC BY 4.0",
                    "url": "https://github.com/lexibank/iecor",
                },
                "languages": result,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def syllabic(segment: str) -> bool:
    """Je hláska slabičná (rys ``syl`` tabulky hlásek)?"""
    table = json.loads((DATA / "v2_segments.json").read_text(encoding="utf-8"))
    at = table["ipa"].index(segment)
    return table["vectors"][at][table["features"].index("syl")] == "2"


def split(word: str, known: set[str]) -> list[str]:
    """Rozdělí slovo na hlásky tabulky (nejdelší shoda)."""
    out, i = [], 0
    longest = max(len(s) for s in known)
    while i < len(word):
        for size in range(min(longest, len(word) - i), 0, -1):
            if word[i : i + size] in known:
                out.append(word[i : i + size])
                i += size
                break
        else:
            out.append(word[i])
            i += 1
    return out


if __name__ == "__main__":
    raise SystemExit(main())

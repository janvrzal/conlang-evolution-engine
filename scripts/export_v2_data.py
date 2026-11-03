"""Jednorázový export dat pro engine v2 v Rustu (``rust/cee_engine``).

Rust nezná PanPhon ani PyYAML, takže tohle, co Python čte za běhu, vyrobí
jednou do ``src/cee/data/``:

- ``v2_segments.json``: tabulka hlásek (symboly IPA, rysy PanPhon a vlastní
  rozlišovací rysy, sekundární artikulace, tóny) a slovník symbolů pro rozbor
  zápisu IPA;
- ``v2_grammar.json``: katalog gramatických funkcí (``v2_grammar.yaml``);
- ``v2_defaults.json``: výchozí pojmy a konstanty scénářů (pořadí pojmů,
  slovesa, neohebná slova, recepty složenin).

Atribuce: tabulka hlásek vychází z PanPhon (David R. Mortensen a kol.,
https://github.com/dmort27/panphon, licence MIT; Mortensen, Littell, Bharadwaj,
Goyal, Dyer, Levin 2016: *PanPhon: A Resource for Mapping IPA Segments to
Articulatory Feature Vectors*, COLING 2016) a z vlastních rozlišovacích rysů
``cee.v2.language.segments``. Výstup je odvozená data, spouští se jen při změně
tabulky hlásek nebo katalogu.

Použití:  PYTHONPATH=src python scripts/export_v2_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cee.semantics.swadesh import _OPTIONS
from cee.v2.language import segments as seg
from cee.v2.language.constructions import CATALOG, GRAMMATICAL_SOURCES
from cee.v2.language.protoforms import DEFAULT_CONSONANTS, DEFAULT_VOWELS
from cee.v2.scenarios import DEFAULT_CONCEPTS, UNINFLECTED, VERBS

DATA = Path(__file__).resolve().parents[1] / "src" / "cee" / "data"
LICENSE = (
    "Odvozeno z PanPhon (MIT, https://github.com/dmort27/panphon; Mortensen et al. 2016, COLING) "
    "a z cee.v2.language.segments."
)


def _row(vector: list[int]) -> str:
    """Rysy jedné hlásky jako řetězec: znak ``chr(48 + hodnota + 1)`` za každý rys."""
    return "".join(chr(48 + int(value) + 1) for value in vector)


def segments() -> dict[str, object]:
    table = seg.default_table()
    rows = len(table.ipa)
    # Znaky, které k zápisu potřebují povolení v ``allow`` (viz ``_allowed_marks``).
    def needs(ipa: str) -> list[str]:
        import unicodedata

        out = []
        for char in unicodedata.normalize("NFD", ipa):
            benign = (char.isalpha() and char not in "ʰʷʲˠˤʼ") or char in seg._PLAIN_MARKS
            if not benign:
                out.append(char)
        return sorted(set(out))

    symbols: dict[str, int] = {}
    for key in sorted(set(table._parser.seg_dict) | set(table.ipa)):
        try:
            parsed = table.parse(key)
        except (ValueError, KeyError):
            continue
        if len(parsed) == 1:
            symbols[seg._normalized(key)] = parsed[0]
    return {
        "license": LICENSE,
        "features": list(table.names) + list(seg.DETAIL_NAMES),
        "old_count": table.old_count,
        "ipa": list(table.ipa),
        "vectors": [_row(list(map(int, table.vectors[index]))) for index in range(rows)],
        "plain": [int(value) for value in table.plain],
        "secondary": [sorted(marks) for marks in table._secondary],
        "needs": [needs(ipa) for ipa in table.ipa],
        # Tónová samohláska: (číslo hlásky, číslo základu, kód tónu).
        "tone_base": [[segment, base, code] for segment, (base, code) in sorted(table._tone_base.items())],
        "tones": list(seg.TONES),
        "tone_marks": dict(seg.TONE_MARKS),
        "symbols": symbols,
    }


def grammar() -> dict[str, object]:
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    # JSON se řadí podle klíčů, pořadí funkcí v katalogu (řídí buňky paradigmat) se proto nese zvlášť.
    data["order"] = list(data["functions"])
    return data


def defaults() -> dict[str, object]:
    return {
        "default_concepts": list(DEFAULT_CONCEPTS),
        "grammatical_sources": list(GRAMMATICAL_SOURCES),
        "verbs": sorted(VERBS),
        "uninflected": sorted(UNINFLECTED),
        "default_consonants": list(DEFAULT_CONSONANTS),
        "default_vowels": list(DEFAULT_VOWELS),
        "compounds": {
            target: [[head, modifier] for head, modifier, _ in options] for target, options in _OPTIONS.items()
        },
    }


def main() -> None:
    for name, payload in (
        ("v2_segments.json", segments()), ("v2_grammar.json", grammar()), ("v2_defaults.json", defaults()),
    ):
        path = DATA / name
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                        encoding="utf-8")
        print(f"{path.relative_to(DATA.parents[2])}: {path.stat().st_size} B")


if __name__ == "__main__":
    main()

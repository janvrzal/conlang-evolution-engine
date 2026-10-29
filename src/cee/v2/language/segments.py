"""Tabulka hlásek nad rysy PanPhon.

Každý rozlišený vektor rysů dostane stabilní celočíselné ID; forma slova je
pak n-tice celých čísel. Změna rysů se vždy převede na *skutečnou* hlásku
(nejbližší existující vektor), nikdy na neexistující matici — to byla
opakovaná past legacy jádra (AGENT.md 3.1b).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import panphon

Form = tuple[int, ...]
IntArray = npt.NDArray[np.int8]
BoolArray = npt.NDArray[np.bool_]

_VALUES = {"+": 1, "-": -1, "0": 0}


class Pattern:
    """Množina hlásek (přirozená třída) a případně hranice slova.

    Maska přes celou tabulku se spočítá jednou; dotaz na hlásku je pak jen
    indexování. Poslední prvek masky je hranice slova (``#``).
    """

    __slots__ = ("key", "mask")

    def __init__(self, key: str, mask: BoolArray):
        self.key = key
        self.mask = mask

    def __contains__(self, segment: int) -> bool:
        return bool(self.mask[segment])


class SegmentTable:
    def __init__(self, features: panphon.FeatureTable | None = None):
        table = features or panphon.FeatureTable()
        self.names: tuple[str, ...] = tuple(table.names)
        self.index = {name: position for position, name in enumerate(self.names)}
        shortest: dict[tuple[int, ...], str] = {}
        for ipa, segment in table.seg_dict.items():
            vector = tuple(int(value) for value in segment.numeric())
            if vector not in shortest or (len(ipa), ipa) < (len(shortest[vector]), shortest[vector]):
                shortest[vector] = ipa
        # Řazení podle IPA dává stabilní ID nezávislé na pořadí v PanPhonu.
        ordered = sorted(shortest.items(), key=lambda item: (item[1], item[0]))
        self.ipa: tuple[str, ...] = tuple(ipa for _, ipa in ordered)
        self.vectors: IntArray = np.array([vector for vector, _ in ordered], dtype=np.int8)
        self._by_vector = {vector: position for position, (vector, _) in enumerate(ordered)}
        self._parser = table
        self.boundary = len(self.ipa)
        self._patterns: dict[tuple[tuple[str, str], ...], Pattern] = {}
        self._enumerated: dict[tuple[int, ...], Pattern] = {}
        self._parsed: dict[str, Form] = {}
        syllabic = self.vectors[:, self.index["syl"]] == 1
        self.vowel_mask: BoolArray = np.append(syllabic, False)
        count = len(self.ipa)
        #: Jen hranice slova.
        self.BOUNDARY = Pattern("#", np.append(np.zeros(count, dtype=bool), True))
        #: Cokoli včetně hranice.
        self.ANY = Pattern("_", np.ones(count + 1, dtype=bool))
        self.VOWEL = Pattern("V", self.vowel_mask.copy())
        self.CONSONANT = Pattern("C", np.append(~syllabic, False))
        # Výstupem změny smí být jen „obyčejná“ hláska: bez sekundární
        # artikulace (ʰ ʷ ˠ …). Jinak by nejbližší vektor k /o/ se zvýšeným
        # jazykem byl velarizované /oˠ/, ne /u/.
        self.plain: BoolArray = np.array([_is_plain(ipa) for ipa in self.ipa], dtype=bool)

    # --- převody --------------------------------------------------------

    def parse(self, ipa: str) -> Form:
        # Rozbor přes PanPhon je drahý a zápis se opakuje (vzory zvukových
        # změn se sestavují z týchž hlásek), proto se pamatuje.
        found = self._parsed.get(ipa)
        if found is None:
            # Běžná záměna: ASCII „g“ místo IPA „ɡ“.
            segments = self._parser.word_fts(ipa.replace("g", "ɡ"))
            if not segments:
                raise ValueError(f"Tvar '{ipa}' neobsahuje žádnou známou hlásku.")
            found = self._parsed[ipa] = tuple(
                self._by_vector[tuple(int(v) for v in segment.numeric())] for segment in segments
            )
        return found

    def render(self, form: Iterable[int]) -> str:
        return "".join(self.ipa[segment] for segment in form)

    def id_of(self, ipa: str) -> int:
        (segment,) = self.parse(ipa)
        return segment

    # --- dotazy ---------------------------------------------------------

    def pattern(self, features: Mapping[str, str]) -> Pattern:
        """Hlásky s danými hodnotami rysů; hranice slova do třídy nepatří."""
        items = tuple(sorted(features.items()))
        cached = self._patterns.get(items)
        if cached is None:
            mask = np.ones(len(self.vectors), dtype=bool)
            for name, value in items:
                mask &= self.vectors[:, self.index[name]] == _VALUES[value]
            key = ",".join(f"{value}{name}" for name, value in items) or "*"
            cached = self._patterns[items] = Pattern(key, np.append(mask, False))
        return cached

    def segments(self, ipa: Iterable[str]) -> Pattern:
        """Výčtová třída konkrétních hlásek."""
        ids = tuple(sorted(self.id_of(symbol) for symbol in ipa))
        cached = self._enumerated.get(ids)
        if cached is None:
            mask = np.zeros(len(self.vectors) + 1, dtype=bool)
            mask[list(ids)] = True
            cached = self._enumerated[ids] = Pattern("{" + ",".join(self.ipa[i] for i in ids) + "}", mask)
        return cached

    def is_vowel(self, segment: int) -> bool:
        return bool(self.vowel_mask[segment])

    def feature(self, segment: int, name: str) -> int:
        return int(self.vectors[segment, self.index[name]])

    def sonority(self, segment: int) -> int:
        """Hrubá škála sonority: vokál 4, aproximanta 3, likvida 2, nazála 1, obstruent 0."""
        vector = self.vectors[segment]
        if vector[self.index["syl"]] == 1:
            return 4
        if vector[self.index["son"]] != 1:
            return 0
        if vector[self.index["cons"]] != 1:
            return 3
        return 1 if vector[self.index["nas"]] == 1 else 2

    def vowel_coordinates(self, segment: int) -> tuple[float, float, float]:
        """(výška, zadnost, zaokrouhlení) v hrubé mřížce pro posuny a disperzi."""
        hi, lo = self.feature(segment, "hi"), self.feature(segment, "lo")
        height = 2.0 if hi == 1 else 0.0 if lo == 1 else 1.0
        if height == 1.0 and self.feature(segment, "tense") == -1:
            height = 0.6  # otevřené středové ɛ, ɔ, ə
        back = 1.0 if self.feature(segment, "back") == 1 else 0.0
        if self.ipa[segment] in ("ə", "ɨ"):
            back = 0.5
        rounded = 1.0 if self.feature(segment, "round") == 1 else 0.0
        return height, back, rounded

    def changed(self, segment: int, changes: tuple[tuple[str, str], ...]) -> int | None:
        return _closest(self, segment, changes)

    def features_of(self, ipa: str, names: Iterable[str]) -> tuple[tuple[str, str], ...]:
        """Hodnoty vybraných rysů konkrétní hlásky, jako požadavek pro změnu."""
        segment = self.id_of(ipa)
        symbols = {1: "+", -1: "-", 0: "0"}
        return tuple(sorted((name, symbols[self.feature(segment, name)]) for name in names))


@lru_cache(maxsize=1 << 16)
def _closest_cached(table_id: int, segment: int, changes: tuple[tuple[str, str], ...]) -> int | None:
    table = _TABLES[table_id]
    vectors = table.vectors
    candidates = table.plain.copy()
    for name, value in changes:
        candidates &= vectors[:, table.index[name]] == _VALUES[value]
    if not candidates.any():
        return None
    source = vectors[segment]
    distance = (vectors != source).sum(axis=1).astype(np.int64)
    distance[~candidates] = 1 << 20
    best = int(np.argmin(distance))
    # Víc než dva další změněné rysy už není „tatáž hláska s jiným rysem“.
    required = sum(int(source[table.index[name]] != _VALUES[value]) for name, value in changes)
    if best == segment or distance[best] > required + 2:
        return None
    return best


_TABLES: dict[int, SegmentTable] = {}


def _closest(table: SegmentTable, segment: int, changes: tuple[tuple[str, str], ...]) -> int | None:
    """Nejbližší skutečná hláska s požadovanými rysy, nebo ``None``."""
    _TABLES.setdefault(id(table), table)
    return _closest_cached(id(table), segment, changes)


@lru_cache(maxsize=1)
def default_table() -> SegmentTable:
    """Sdílená tabulka; stavba trvá zlomek sekundy, ale nemá se opakovat."""
    return SegmentTable()


_PLAIN_MARKS = {"\u0361", "ː"}


def _is_plain(ipa: str) -> bool:
    return all(char.isalpha() or char in _PLAIN_MARKS for char in ipa) and not any(
        char in "ʰʷʲˠˤʼ" for char in ipa
    )


def inventory(forms: Iterable[Sequence[int]]) -> set[int]:
    return {segment for form in forms for segment in form}

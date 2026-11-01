"""Tabulka hlásek nad rysy PanPhon.

Každý rozlišený vektor rysů dostane stabilní celočíselné ID; forma slova je
pak n-tice celých čísel. Změna rysů se vždy převede na *skutečnou* hlásku
(nejbližší existující vektor), nikdy na neexistující matici — to byla
opakovaná past legacy jádra (AGENT.md 3.1b).

**Úplné IPA.** PanPhon má 24 rysů a některé rozdíly IPA nevyjádří: *ɐ* a *e*,
*ɜ* a *ə*, *ɾ* a *r*, *tˠ* a *tʲ* mají stejný vektor a jemnou diakritiku
(apikální, zvýšená, kořen jazyka, neuvolněná…) PanPhon u mnoha hlásek
ignoruje. Tabulka proto za rysy PanPhonu přidává vlastní rozlišovací rysy
(``DETAIL_NAMES``) a hlásky, které se jimi liší, jako další řádky. Původní
hlásky mají vlastní rysy nulové a jejich ID se nemění, takže dynamika světů,
které nové hlásky nepoužívají, zůstává beze změny; nová hláska je od
původní o rys dál, a změna rysů ji proto nikdy nevybere místo ní. Tóny
zapsané diakritikou (*á*, *ǎ*) se převedou na tónové značky (*a˦*, *a˩˥*),
které tabulka zná jako samostatné hlásky; vývoj tónů model zatím nemá.
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache
from typing import Iterable, Mapping, Sequence

import numpy as np
import numpy.typing as npt
import panphon

Form = tuple[int, ...]
IntArray = npt.NDArray[np.int8]
BoolArray = npt.NDArray[np.bool_]

_VALUES = {"+": 1, "-": -1, "0": 0}


def _value(value: str) -> int:
    """Hodnota rysu: ``+ - 0`` u rysů PanPhonu, číslo u vlastních rysů (kód tónu)."""
    found = _VALUES.get(value)
    return int(value) if found is None else found

#: Vlastní rozlišovací rysy nad PanPhonem (0 = jako hláska bez značky).
#: ``x_variant`` odliší zápisy, které by jinak měly stejné rysy (PanPhon *qʷ* a *kʷ*).
DETAIL_NAMES: tuple[str, ...] = (
    "x_height", "x_place", "x_round", "x_root", "x_tip", "x_phonation", "x_release",
    "x_length", "x_manner", "x_secondary", "x_rhotic", "x_epiglottal",
    "x_labial", "x_palatal", "x_aspirated", "x_ejective", "x_nasal", "x_long", "x_variant", "x_tone",
)

#: Tóny jako rys samohlásky (``x_tone``): 0 bez tónu, pak úrovně a průběhy
#: zapsané tónovými značkami (˩ nejnižší, ˥ nejvyšší).
_LEVELS = "˩˨˧˦˥"
TONES: tuple[str, ...] = (
    *_LEVELS,
    *(a + b for a in _LEVELS for b in _LEVELS if a != b),
    "˨˩˦", "˧˦˧", "˧˨˧", "˨˦˨", "˦˨˦", "˩˥˩", "˥˩˥",
)
#: Tónové značky → kód tónu (1 = ˩ … 5 = ˥, průběhy dál).
TONE_CODES: dict[str, int] = {tone: code for code, tone in enumerate(TONES, start=1)}

#: Značka IPA → (vlastní rys, hodnota). Rys se nastaví jen tam, kde by se
#: značka ve vektoru PanPhonu ztratila (u /n̥/ ji PanPhon vyjádří, u /d̥/ ne;
#: /t̻/ by splynulo s /t̪/, /e̙/ s /ɛ/).
DETAIL_MARKS: dict[str, tuple[str, int]] = {
    "\u031d": ("x_height", 1), "\u031e": ("x_height", -1),
    "\u031f": ("x_place", 1), "\u0320": ("x_place", -1), "\u0308": ("x_place", 2), "\u033d": ("x_place", 3),
    "\u0339": ("x_round", 1), "\u031c": ("x_round", -1),
    "\u0318": ("x_root", 1), "\u0319": ("x_root", -1),
    "\u033a": ("x_tip", 1), "\u033b": ("x_tip", -1), "\u033c": ("x_tip", 2), "\u032a": ("x_tip", 3),
    "\u0325": ("x_phonation", -1), "\u032c": ("x_phonation", 1),
    "\u0324": ("x_phonation", 2), "\u0330": ("x_phonation", 3), "ʱ": ("x_phonation", 4), "ˀ": ("x_phonation", 5),
    "\u031a": ("x_release", 1), "ⁿ": ("x_release", 2), "ˡ": ("x_release", 3),
    "ˑ": ("x_length", 1), "\u0306": ("x_length", -1),
    "ˠ": ("x_secondary", 1), "ˤ": ("x_secondary", 2), "\u0334": ("x_secondary", 3),
    "˞": ("x_rhotic", 1),
    "ʷ": ("x_labial", 1), "ʲ": ("x_palatal", 1), "ʰ": ("x_aspirated", 1), "ʼ": ("x_ejective", 1),
    "\u0303": ("x_nasal", 1), "ː": ("x_long", 1),
}

#: Písmena, která PanPhon slévá s jiným nebo nezná: písmeno → (základ, vlastní rysy).
DETAIL_LETTERS: dict[str, tuple[str, tuple[tuple[str, int], ...]]] = {
    "ɐ": ("a", (("x_height", 1),)),
    "ɜ": ("ə", (("x_height", -1),)),
    "ɾ": ("r", (("x_manner", 1),)),
    "ⱱ": ("v", (("x_manner", 1),)),
    "ʜ": ("ħ", (("x_epiglottal", 1),)),
    "ʢ": ("ʕ", (("x_epiglottal", 1),)),
    "ʡ": ("ʔ", (("x_epiglottal", 1),)),
    "ɚ": ("ə", (("x_rhotic", 1),)),
    "ɝ": ("ə", (("x_height", -1), ("x_rhotic", 1))),
}

#: Tóny zapsané diakritikou nad slabičným jádrem → tónové značky.
TONE_MARKS: dict[str, str] = {
    "\u030b": "˥", "\u0301": "˦", "\u0304": "˧", "\u0300": "˨", "\u030f": "˩",
    "\u0302": "˥˩", "\u030c": "˩˥", "\u1dc4": "˧˥", "\u1dc5": "˩˧", "\u1dc6": "˧˩", "\u1dc7": "˥˧",
    "\u1dc8": "˧˦˧", "\u1dc9": "˧˨˧",
}
_TONE_LETTERS = "˥˦˧˨˩"
#: Značky, které visí na předchozí hlásce (kromě kombinačních znaků).
_MODIFIERS = "ʰʱʷʲˠˤʼˀːˑⁿˡ˞ᶿˣᵊ"
#: Značky nových řádků, které se při změně rysů dědí jako sekundární artikulace.
_NEW_SECONDARY = "ʰʱʷʲˠˤʼˀⁿˡˑ˞˥˦˧˨˩"


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
        # Append explicit secondary-articulation symbols without renumbering
        # existing IDs. PanPhon assigns k and kʲ (and ɡ and ɡʲ) the same vector.
        # Palatalized velars are phonetically advanced velars: setting back=0
        # (central) distinguishes them from plain velars (back=1) and from palatals
        # c/ɟ (back=-1) without any vector collisions across the entire inventory.
        existing = {ipa for _, ipa in ordered}
        aliases = [base + mark for base in ("p", "t", "k", "b", "d", "ɡ", "s", "m", "n", "l", "r")
                   for mark in ("ʲ",)]
        aliases += [base + "ʷ" for base in ("k", "ɡ")]
        aliases += [base + "\u0303" for base in ("a", "e", "i", "o", "u", "ɛ", "ɔ", "ə")]
        appended = []
        back_index = self.index["back"]
        for ipa in aliases:
            parsed = table.word_fts(ipa)
            if len(parsed) == 1 and ipa not in existing:
                vec = [int(value) for value in parsed[0].numeric()]
                if ipa in ("kʲ", "ɡʲ"):
                    vec[back_index] = 0
                appended.append((tuple(vec), ipa))
        self.ipa: tuple[str, ...] = tuple(ipa for _, ipa in (*ordered, *appended))
        self.vectors: IntArray = np.array([vector for vector, _ in (*ordered, *appended)], dtype=np.int8)
        self._by_vector = {vector: position for position, (vector, _) in enumerate(ordered)}
        self._aliases = {ipa: position for position, ipa in enumerate(self.ipa) if ipa in aliases}
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
        self._secondary = tuple(_secondary_marks(ipa) for ipa in self.ipa)
        self._secondary_tuple = tuple(tuple(sorted(marks)) for marks in self._secondary)
        self._allowed_masks: dict[tuple[str, ...], BoolArray] = {}
        self._extend(table)

    # --- úplné IPA ----------------------------------------------------------

    def _extend(self, table: panphon.FeatureTable) -> None:
        """Přidá vlastní rysy a řádky hlásek, které PanPhon slévá nebo nezná.

        Původní řádky dostanou vlastní rysy nulové a jejich ID se nezmění.
        Nová hláska je zápis, který se přes PanPhon nezapíše zpět stejně;
        dostane rysy PanPhonu bez ztracených značek a vlastní rysy za ně.
        """
        old = len(self.ipa)
        self.old_count = old
        self.detail_names = DETAIL_NAMES
        for position, name in enumerate(DETAIL_NAMES):
            self.index[name] = len(self.names) + position
        variant = DETAIL_NAMES.index("x_variant")
        rows: dict[tuple[tuple[int, ...], tuple[int, ...]], str] = {}
        by_symbol: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {}

        def add(cluster: str) -> None:
            cluster = _normalized(cluster)
            if _signature(cluster) in by_symbol:
                return
            try:
                if self._faithful_plain(cluster) is not None:
                    return
                vector, detail = self._cluster_key(cluster)
            except ValueError:
                return
            key = (vector, detail)
            while (key in rows or (not any(key[1]) and vector in self._by_vector)) and \
                    (key not in rows or _signature(rows[key]) != _signature(cluster)):
                bumped = list(key[1])
                bumped[variant] += 1
                key = (vector, tuple(bumped))
            rows[key] = cluster
            by_symbol[_signature(cluster)] = key

        for letter in sorted(DETAIL_LETTERS):
            add(letter)
        for first, second in (("k", "p"), ("ɡ", "b"), ("ŋ", "m"), ("t", "p"), ("d", "b"), ("n", "m")):
            add(f"{first}\u0361{second}")  # dvojí artikulace, kterou PanPhon nezná
        for symbol in sorted(table.seg_dict, key=lambda s: (len(s), s)):
            add(symbol)
        letters = sorted({s for s in table.seg_dict if len(s) == 1 and s.isalpha()} | set(DETAIL_LETTERS))
        bases = letters + sorted(
            ipa for ipa in self.ipa
            if len(_normalized(ipa)) == 2 and ipa[0].isalpha() and _normalized(ipa)[1] in "ʰʷʲːʼ\u0303\u032a"
        )
        for base in bases:
            base = _normalized(base)
            for mark in sorted(DETAIL_MARKS):
                # Kombinační značka patří hned za písmeno, před ː ʰ ʷ ʲ (ɛ̞ː, ne ɛː̞).
                add(base[0] + mark + base[1:] if unicodedata.combining(mark) else base + mark)
        ordered = sorted(rows.items(), key=lambda item: (len(item[1]), item[1]))
        toned = self._toned_rows(by_symbol)
        ordered += [(key, ipa) for key, ipa, _ in toned]
        width = len(DETAIL_NAMES)
        padded = np.hstack([self.vectors, np.zeros((old, width), dtype=np.int8)])
        extra = np.array([[*vector, *detail] for (vector, detail), _ in ordered], dtype=np.int8)
        self.vectors = np.vstack([padded, extra.reshape(-1, len(self.names) + width)])
        self.ipa = (*self.ipa, *(unicodedata.normalize("NFC", cluster) for _, cluster in ordered))
        self._by_detail = {key: old + offset for offset, (key, _) in enumerate(ordered)}
        self._toned: dict[tuple[int, int], int] = {}
        self._tone_base: dict[int, tuple[int, int]] = {}
        first_toned = old + len(ordered) - len(toned)
        self._by_symbol = {signature: self._by_detail[key] for signature, key in by_symbol.items()}
        count = len(self.ipa)
        syllabic = self.vectors[:, self.index["syl"]] == 1
        self.vowel_mask = np.append(syllabic, False)
        self.boundary = count
        self.BOUNDARY = Pattern("#", np.append(np.zeros(count, dtype=bool), True))
        self.ANY = Pattern("_", np.ones(count + 1, dtype=bool))
        self.VOWEL = Pattern("V", self.vowel_mask.copy())
        self.CONSONANT = Pattern("C", np.append(~syllabic, False))
        new_ipa = self.ipa[old:]
        self.plain = np.append(self.plain, [_is_plain(ipa) and not any(c in _NEW_SECONDARY for c in ipa)
                                            for ipa in new_ipa])
        secondary = [_secondary_marks(ipa) | frozenset(c for c in ipa if c in _NEW_SECONDARY) for ipa in new_ipa]
        self._secondary = (*self._secondary, *secondary)
        self._secondary_tuple = tuple(tuple(sorted(marks)) for marks in self._secondary)
        tone = DETAIL_NAMES.index("x_tone")
        for offset, ((_, detail), _, base_ipa) in enumerate(toned):
            (base,) = self.parse(base_ipa)
            self._toned[(base, detail[tone])] = first_toned + offset
            self._tone_base[first_toned + offset] = (base, detail[tone])

    def _toned_rows(self, by_symbol) -> list[tuple[tuple[tuple[int, ...], tuple[int, ...]], str, str]]:
        """Řádky samohlásek s tónem: běžné samohlásky (i dlouhé, nosové, dyšné,
        skřípavé a nové ɐ ɜ ɚ ɝ) × všechny tóny ``TONES``; (klíč, zápis, základ)."""
        tone = DETAIL_NAMES.index("x_tone")
        width = len(DETAIL_NAMES)
        out = []
        seen: set[str] = set()
        for symbol in "iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒɚɝ":
            for variant in ("", "ː", "\u0303", "\u0324", "\u0330", "\u0303ː"):
                ipa = unicodedata.normalize("NFC", symbol + variant)
                if ipa in seen:
                    continue
                seen.add(ipa)
                old = self._faithful_plain(_normalized(ipa))
                if old is not None:
                    vector, detail = tuple(int(v) for v in self.vectors[old]), (0,) * width
                elif _signature(ipa) in by_symbol:
                    vector, detail = by_symbol[_signature(ipa)]
                else:
                    continue
                for letters, code in TONE_CODES.items():
                    toned = list(detail)
                    toned[tone] = code
                    out.append(((vector, tuple(toned)), ipa + letters, ipa))
        return out

    def tone_of(self, segment: int) -> int:
        """Kód tónu samohlásky (0 = bez tónu)."""
        return self._tone_base.get(segment, (segment, 0))[1]

    def with_tone(self, segment: int, code: int) -> int | None:
        """Táž samohláska s tónem ``code`` (0 = bez tónu); None, když ji tabulka nemá."""
        base = self._tone_base.get(segment, (segment, 0))[0]
        if code == 0:
            return base
        return self._toned.get((base, code))

    def _vector(self, cluster: str) -> tuple[int, ...]:
        segments = self._parser.word_fts(cluster)
        if len(segments) == 2 and "\u0361" in cluster:
            # Dvojí artikulace (ŋ͡m): první hláska s místem tvoření i druhé.
            first, second = ([int(v) for v in segment.numeric()] for segment in segments)
            for name in ("lab", "cor", "ant"):
                position = self.index[name]
                first[position] = max(first[position], second[position])
            return tuple(first)
        if len(segments) != 1:
            raise ValueError(f"'{cluster}' není jedna hláska.")
        return tuple(int(value) for value in segments[0].numeric())

    def _faithful_plain(self, cluster: str) -> int | None:
        """ID z původní tabulky, když ho PanPhon zapíše zpět stejně (jinak None)."""
        try:
            found = self._parse_plain(cluster)
        except ValueError:
            return None
        if len(found) == 1 and _signature(self.ipa[found[0]]) == _signature(cluster):
            return found[0]
        return None

    def _cluster_key(self, cluster: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """(vektor PanPhonu, vlastní rysy) jedné hlásky zapsané i se značkami."""
        detail = dict.fromkeys(DETAIL_NAMES, 0)
        if cluster[0] in DETAIL_LETTERS:
            base, extra = DETAIL_LETTERS[cluster[0]]
            cluster = base + cluster[1:]
            for name, value in extra:
                detail[name] = value
        kept = "".join(c for c in cluster if c not in DETAIL_MARKS)
        for mark in (c for c in cluster if c in DETAIL_MARKS):
            name, value = DETAIL_MARKS[mark]
            if mark != "ˠ":  # PanPhon ji zaměňuje s ʲ
                try:
                    with_mark = self._vector(kept + mark)
                    same = self._by_vector.get(with_mark)
                    if with_mark != self._vector(kept) and same is not None and mark in _normalized(self.ipa[same]):
                        kept += mark  # PanPhon značku vyjádří sám
                        continue
                except ValueError:
                    pass
            detail[name] = value
        return self._vector(kept), tuple(detail[name] for name in DETAIL_NAMES)

    # --- převody --------------------------------------------------------

    def parse(self, ipa: str) -> Form:
        # Rozbor přes PanPhon je drahý a zápis se opakuje (vzory zvukových
        # změn se sestavují z týchž hlásek), proto se pamatuje.
        found = self._parsed.get(ipa)
        if found is not None:
            return found
        if _needs_detail(ipa):
            found = self._parse_detail(ipa)
        else:
            found = self._parse_plain(ipa)
            # Zápis, který by PanPhon slil s jiným (qʷ → kʷ, dʱ → d), se rozebere po hláskách.
            if _signature(self.render(found)) != _signature(_normalized(ipa)):
                try:
                    found = self._parse_detail(ipa)
                except ValueError:
                    pass
        self._parsed[ipa] = found
        return found

    def _parse_plain(self, ipa: str) -> Form:
        """Původní rozbor přes PanPhon (hlásky bez vlastních rysů)."""
        # Běžná záměna: ASCII „g“ místo IPA „ɡ“.
        segments = self._parser.word_fts(ipa.replace("g", "ɡ"))
        if not segments:
            raise ValueError(f"Tvar '{ipa}' neobsahuje žádnou známou hlásku.")
        symbols = self._parser.ipa_segs(ipa.replace("g", "ɡ"))
        found = tuple(
            self._aliases.get(symbol, self._by_vector.get(tuple(int(v) for v in segment.numeric()), -1))
            for symbol, segment in zip(symbols, segments)
        )
        if -1 in found or len(found) != len(segments):
            raise ValueError(f"Tvar '{ipa}' obsahuje nepodporovanou hlásku.")
        return found

    def _parse_detail(self, ipa: str) -> Form:
        """Rozbor po hláskách: původní tabulka, kde zapíše věrně, jinak nové řádky."""
        out: list[int] = []
        for cluster, tones in _clusters(_normalized(ipa)):
            if cluster:
                if cluster[0] in _TONE_LETTERS:
                    self._attach_tone(out, cluster)
                else:
                    out.append(self._segment(ipa, cluster))
            if tones:
                self._attach_tone(out, tones)
        return tuple(out)

    def _attach_tone(self, out: list[int], letters: str) -> None:
        """Tón patří předchozí samohlásce; kde tabulka takovou samohlásku nemá,
        zůstane tónová značka samostatnou hláskou (jako dřív)."""
        code = TONE_CODES.get(letters)
        if out and code is not None and self.is_vowel(out[-1]) and self.tone_of(out[-1]) == 0:
            toned = self.with_tone(out[-1], code)
            if toned is not None:
                out[-1] = toned
                return
        out.extend(self._parse_plain(letters))

    def _segment(self, ipa: str, cluster: str) -> int:
        plain = self._faithful_plain(cluster)
        if plain is not None:
            return plain
        found = self._by_symbol.get(_signature(cluster))
        if found is None:
            vector, detail = self._cluster_key(cluster)
            found = self._by_detail.get((vector, detail))
            if found is None and not any(detail):
                found = self._by_vector.get(vector)
        if found is None:
            raise ValueError(f"Tvar '{ipa}' obsahuje hlásku '{unicodedata.normalize('NFC', cluster)}', kterou engine "
                             "zatím neumí zapsat (nezvyklá kombinace značek).")
        return found

    def render(self, form: Iterable[int]) -> str:
        return "".join(self.ipa[segment] for segment in form)

    def id_of(self, ipa: str) -> int:
        (segment,) = self.parse(ipa)
        return segment

    def lossless(self, ipa: str) -> bool:
        """Zapíše se tvar zpět beze ztráty? Tóny diakritikou se počítají jako
        tónové značky; přízvuk a hranice slabik (ˈ ˌ .) určuje jazyk, ne zápis."""
        expected = "".join(cluster + tones for cluster, tones in _clusters(_normalized(ipa)))
        expected = "".join(c for c in expected if c not in "ˈˌ.‿|‖")
        return _signature(self.render(self.parse(ipa))) == _signature(expected)

    # --- dotazy ---------------------------------------------------------

    def pattern(self, features: Mapping[str, str]) -> Pattern:
        """Hlásky s danými hodnotami rysů; hranice slova do třídy nepatří."""
        items = tuple(sorted(features.items()))
        cached = self._patterns.get(items)
        if cached is None:
            mask = np.ones(len(self.vectors), dtype=bool)
            for name, value in items:
                mask &= self.vectors[:, self.index[name]] == _value(value)
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

    def changed(
        self, segment: int, changes: tuple[tuple[str, str], ...], allow: tuple[str, ...] = ()
    ) -> int | None:
        # Preserve secondary articulation already present on the input. A
        # feature change must not silently depalatalize or denasalize it;
        # explicit reverse processes use ``replace`` to remove the mark.
        if not allow:
            allow_key = self._secondary_tuple[segment]
        else:
            inherited = self._secondary[segment]
            allow_key = allow if not inherited else tuple(sorted(inherited | set(allow)))
        return _closest(self, segment, changes, allow_key)

    def features_of(self, ipa: str, names: Iterable[str]) -> tuple[tuple[str, str], ...]:
        """Hodnoty vybraných rysů konkrétní hlásky, jako požadavek pro změnu."""
        segment = self.id_of(ipa)
        symbols = {1: "+", -1: "-", 0: "0"}
        return tuple(sorted((name, symbols[self.feature(segment, name)]) for name in names))


@lru_cache(maxsize=1 << 16)
def _closest_cached(
    table_id: int, segment: int, changes: tuple[tuple[str, str], ...], allow: tuple[str, ...]
) -> int | None:
    table = _TABLES[table_id]
    vectors = table.vectors
    if allow:
        cached = table._allowed_masks.get(allow)
        if cached is None:
            cached = table._allowed_masks[allow] = np.array([
                set(allow).issubset(marks) and _allowed_marks(ipa, allow)
                for ipa, marks in zip(table.ipa, table._secondary)
            ], dtype=bool)
        candidates = cached.copy()
    else:
        candidates = table.plain.copy()
    for name, value in changes:
        candidates &= vectors[:, table.index[name]] == _value(value)
    if not candidates.any():
        return None
    source = vectors[segment]
    distance = (vectors != source).sum(axis=1).astype(np.int64)
    distance[~candidates] = 1 << 20
    best = int(np.argmin(distance))
    # Víc než dva další změněné rysy už není „tatáž hláska s jiným rysem“.
    required = sum(int(source[table.index[name]] != _value(value)) for name, value in changes)
    if best == segment or distance[best] > required + 2:
        return None
    return best


_TABLES: dict[int, SegmentTable] = {}


def _closest(
    table: SegmentTable, segment: int, changes: tuple[tuple[str, str], ...], allow: tuple[str, ...]
) -> int | None:
    """Nejbližší skutečná hláska s požadovanými rysy, nebo ``None``."""
    _TABLES.setdefault(id(table), table)
    return _closest_cached(id(table), segment, changes, allow)


@lru_cache(maxsize=1)
def default_table() -> SegmentTable:
    """Sdílená tabulka; stavba trvá zlomek sekundy, ale nemá se opakovat."""
    return SegmentTable()


_PLAIN_MARKS = {"\u0361", "ː"}


def _ipa_normalized(ipa: str) -> str:
    return unicodedata.normalize("NFD", ipa)


def _secondary_marks(ipa: str) -> frozenset[str]:
    return frozenset(char for char in _ipa_normalized(ipa)
                     if char in "ʰʷʲˠˤʼ" or (unicodedata.combining(char) and char not in _PLAIN_MARKS))


def _allowed_marks(ipa: str, allow: tuple[str, ...]) -> bool:
    ipa = _ipa_normalized(ipa)
    return all(char.isalpha() and char not in "ʰʷʲˠˤʼ" or char in _PLAIN_MARKS or char in allow
               for char in ipa) and all(
        not unicodedata.combining(char) or char in allow or char in _PLAIN_MARKS for char in ipa
    )


def _is_plain(ipa: str) -> bool:
    ipa = _ipa_normalized(ipa)
    return all(char.isalpha() or char in _PLAIN_MARKS for char in ipa) and not any(
        char in "ʰʷʲˠˤʼ" for char in ipa
    )


def _normalized(ipa: str) -> str:
    """Jednotný zápis: rozložené znaky, IPA ɡ, oblouček nad písmeny, ̥ místo ̊."""
    return (unicodedata.normalize("NFD", ipa).replace("g", "ɡ").replace("\u035c", "\u0361")
            .replace("\u030a", "\u0325"))


def _signature(ipa: str) -> str:
    """Totožnost zápisu bez ohledu na pořadí značek (kʷʰ = kʰʷ)."""
    return "".join(sorted(_normalized(ipa)))


def _needs_detail(ipa: str) -> bool:
    """Obsahuje zápis značky, písmena nebo tóny, které PanPhon sám nerozliší?"""
    text = _normalized(ipa)
    return any(c in DETAIL_LETTERS or c in TONE_MARKS or c in _TONE_LETTERS
               or (c in DETAIL_MARKS and c not in "ʷʲʰʼːˀ\u0303") for c in text)


def _clusters(text: str) -> list[tuple[str, str]]:
    """Rozdělí zápis na hlásky (písmeno, spojené obloučkem, se značkami) a tóny z diakritiky."""
    out: list[tuple[str, str]] = []
    cluster, tones = "", ""
    tie = False
    for char in text:
        if char in _TONE_LETTERS:
            if cluster and cluster[0] in _TONE_LETTERS:
                cluster += char
                continue
            if cluster or tones:
                out.append((cluster, tones))
            cluster, tones, tie = char, "", False
        elif char in TONE_MARKS:
            tones += TONE_MARKS[char]
        elif unicodedata.combining(char) or char in _MODIFIERS:
            cluster += char
            tie = char == "\u0361"
        elif tie:
            cluster += char
            tie = False
        else:
            if cluster or tones:
                out.append((cluster, tones))
            cluster, tones = char, ""
    if cluster or tones:
        out.append((cluster, tones))
    return out


def inventory(forms: Iterable[Sequence[int]]) -> set[int]:
    return {segment for form in forms for segment in form}

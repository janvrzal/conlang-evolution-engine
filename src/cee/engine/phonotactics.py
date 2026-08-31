"""Naučený, vysvětlitelný model slabikové stavby jazyka.

Nejde o univerzální seznam zakázaných shluků. Profil se odvozuje z živého
lexikonu konkrétního jazyka a po každé změně umí určit, zda nová forma jeho
dosavadní gramatiku ještě respektuje.  Konfigurace uzlu může profil záměrně
uvolnit nebo zpřísnit, ale výchozí hodnota není skrytý evropský prior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cee.core.models import Segment, Word


def _is_consonant(segment: Segment) -> bool:
    return segment.features.get("cons") == "+"


def _runs_around_nuclei(word: Word) -> tuple[list[int], list[int]]:
    """Vrátí délky onsetů a kod podle jader, bez závislosti na ortografii."""
    nuclei = word.syllable_nuclei()
    if not nuclei:
        return [], []
    onsets: list[int] = []
    codas: list[int] = []
    start = 0
    for position, nucleus in enumerate(nuclei):
        onset = 0
        for segment in word.segments[start:nucleus]:
            onset = onset + 1 if _is_consonant(segment) else 0
        onsets.append(onset)

        next_nucleus = nuclei[position + 1] if position + 1 < len(nuclei) else len(word.segments)
        between = word.segments[nucleus + 1 : next_nucleus]
        # Maximal-onset dělení: jediná intervokalická C patří k následující
        # slabice, u delšího řetězce zůstává první část v kodě.
        coda = max(0, len([segment for segment in between if _is_consonant(segment)]) - 1)
        if position == len(nuclei) - 1:
            coda = len([segment for segment in between if _is_consonant(segment)])
        codas.append(coda)
        start = next_nucleus - 1 if position + 1 < len(nuclei) else next_nucleus
    return onsets, codas


@dataclass(frozen=True)
class PhonotacticProfile:
    """Souhrn toho, co je v daném lexikonu strukturálně doložené."""

    max_onset: int = 1
    max_coda: int = 1
    nucleus_required: bool = True

    @classmethod
    def learn(cls, words: Iterable[Word]) -> "PhonotacticProfile":
        onsets: list[int] = []
        codas: list[int] = []
        has_nucleus = False
        for word in words:
            if not word.active:
                continue
            word_onsets, word_codas = _runs_around_nuclei(word)
            onsets.extend(word_onsets)
            codas.extend(word_codas)
            has_nucleus = has_nucleus or bool(word.syllable_nuclei())
        # Jedno extrémní slovo nesmí automaticky legalizovat libovolný shluk.
        # Devadesátý percentil zachovává produktivní strukturu, ale izolovaný
        # relikt nechává jako označenou výjimku.
        def percentile(values: list[int], default: int) -> int:
            if not values:
                return default
            ordered = sorted(values)
            return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.9))]

        return cls(
            max_onset=percentile(onsets, 1),
            max_coda=percentile(codas, 1),
            nucleus_required=has_nucleus,
        )

    def violation(self, word: Word) -> str | None:
        if self.nucleus_required and not word.syllable_nuclei():
            return "missing_nucleus"
        onsets, codas = _runs_around_nuclei(word)
        if any(length > self.max_onset for length in onsets):
            return "onset_cluster"
        if any(length > self.max_coda for length in codas):
            return "coda_cluster"
        return None

    def repair(self, word: Word) -> bool:
        """Opraví pouze strukturu, kterou vlastní profil označí za neplatnou."""
        violation = self.violation(word)
        if violation is None:
            return False
        vowel = next((segment for segment in word.segments if segment.features.get("syl") == "+"), None)
        if vowel is None:
            return False
        # Vložíme kopii existujícího jádra do prvního nadlimitního shluku.
        run = 0
        for index, segment in enumerate(word.segments):
            if _is_consonant(segment):
                run += 1
                limit = self.max_onset + self.max_coda + 1
                if run > max(1, limit):
                    word.segments.insert(index, Segment(features=dict(vowel.features)))
                    word.ensure_stress()
                    return True
            else:
                run = 0
        return False

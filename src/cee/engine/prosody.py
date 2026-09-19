"""Prosodická kostra: slabiky, přízvuk a konzervativní opravy shluků."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from cee.core.models import Segment, Word


@dataclass(frozen=True)
class Syllable:
    start: int
    nucleus: int
    end: int

    @property
    def is_open(self) -> bool:
        return self.end == self.nucleus + 1


def syllabify(word: Word) -> List[Syllable]:
    """Vrátí slabiky podle jader; souhlásky mezi jádry dělí maximal onset."""
    nuclei = word.syllable_nuclei()
    if not nuclei:
        return []
    result: List[Syllable] = []
    start = 0
    for offset, nucleus in enumerate(nuclei):
        next_nucleus = nuclei[offset + 1] if offset + 1 < len(nuclei) else len(word.segments)
        # Jedna intervokalická souhláska patří do onsetu další slabiky,
        # delší řetězec ponechá první souhlásku jako kodu.
        gap = next_nucleus - nucleus - 1
        end = next_nucleus - 1 if gap > 1 else next_nucleus
        result.append(Syllable(start=start, nucleus=nucleus, end=end))
        start = end
    return result


def syllable_position(word: Word, segment_index: int) -> str | None:
    for syllable in syllabify(word):
        if segment_index == syllable.nucleus:
            return "nucleus"
        if syllable.start <= segment_index < syllable.nucleus:
            return "onset"
        if syllable.nucleus < segment_index < syllable.end:
            return "coda"
    return None


def repair_clusters(word: Word) -> bool:
    """Rozbije pouze trojité souhláskové shluky vložením jazykového vokálu."""
    word.ensure_stress()
    vowel = next((segment for segment in word.segments if segment.features.get("syl") == "+"), None)
    if vowel is None:
        return False

    repaired: List[Segment] = []
    changed = False
    consonant_run = 0
    for segment in word.segments:
        if segment.features.get("cons") == "+":
            consonant_run += 1
            if consonant_run >= 3:
                repaired.append(Segment(features=dict(vowel.features)))
                consonant_run = 1
                changed = True
        else:
            consonant_run = 0
        repaired.append(segment)
    if changed:
        word.segments = repaired
        word.ensure_stress()
    return changed

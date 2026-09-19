"""Naučená, vážená fonotaktika konkrétního jazyka.

Profil se netváří jako univerzální seznam zakázaných shluků. Z vlastního
lexikonu rozlišuje produktivní struktury, řídké historické výjimky a míru
porušení. Simulátor tak opraví nově vzniklou nepravděpodobnou formu, aniž by
přepisoval doložené relikty.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from cee.core.models import Segment, Word


def _is_consonant(segment: Segment) -> bool:
    return segment.features.get("cons") == "+"


def _sonority(segment: Segment) -> int:
    """Malá, transparentní sonoritní škála nad dostupnými rysy PanPhonu."""
    if segment.features.get("syl") == "+":
        return 6
    if segment.features.get("son") == "-":
        return 1
    if segment.features.get("nas") == "+":
        return 2
    if segment.features.get("approx") == "+":
        return 4
    return 3


def _signature(segments: Iterable[Segment]) -> tuple[int, ...]:
    return tuple(_sonority(segment) for segment in segments if _is_consonant(segment))


def _runs_around_nuclei(word: Word) -> tuple[list[list[Segment]], list[list[Segment]]]:
    """Onsety a kody po maximal-onset dělení, tentokrát i s rysy segmentů."""
    nuclei = word.syllable_nuclei()
    if not nuclei:
        return [], []
    onsets: list[list[Segment]] = []
    codas: list[list[Segment]] = []
    previous = 0
    for position, nucleus in enumerate(nuclei):
        onsets.append([segment for segment in word.segments[previous:nucleus] if _is_consonant(segment)])
        next_nucleus = nuclei[position + 1] if position + 1 < len(nuclei) else len(word.segments)
        between = [segment for segment in word.segments[nucleus + 1 : next_nucleus] if _is_consonant(segment)]
        codas.append(between if position == len(nuclei) - 1 else between[:-1])
        previous = next_nucleus - 1 if position + 1 < len(nuclei) else next_nucleus
    return onsets, codas


def _rising(values: tuple[int, ...]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))


def _falling(values: tuple[int, ...]) -> bool:
    return all(left > right for left, right in zip(values, values[1:]))


@dataclass(frozen=True)
class PhonotacticProfile:
    """Produktivní a výjimečné vzory naučené z živého lexikonu."""

    max_onset: int = 1
    max_coda: int = 1
    nucleus_required: bool = True
    productive_onsets: tuple[tuple[int, ...], ...] = ()
    productive_codas: tuple[tuple[int, ...], ...] = ()
    exceptional_onsets: tuple[tuple[int, ...], ...] = ()
    exceptional_codas: tuple[tuple[int, ...], ...] = ()
    onset_weight: float = 1.0
    coda_weight: float = 1.0
    sonority_weight: float = 1.0

    @classmethod
    def learn(cls, words: Iterable[Word]) -> "PhonotacticProfile":
        onset_counts: Counter[tuple[int, ...]] = Counter()
        coda_counts: Counter[tuple[int, ...]] = Counter()
        onsets: list[int] = []
        codas: list[int] = []
        has_nucleus = False
        for word in words:
            if not word.active:
                continue
            word_onsets, word_codas = _runs_around_nuclei(word)
            onset_counts.update(signature for signature in map(_signature, word_onsets) if signature)
            coda_counts.update(signature for signature in map(_signature, word_codas) if signature)
            onsets.extend(map(len, word_onsets))
            codas.extend(map(len, word_codas))
            has_nucleus = has_nucleus or bool(word.syllable_nuclei())

        def percentile(values: list[int], default: int) -> int:
            if not values:
                return default
            ordered = sorted(values)
            return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * 0.9))]

        productive_onsets = tuple(sorted(signature for signature, count in onset_counts.items() if count >= 2))
        productive_codas = tuple(sorted(signature for signature, count in coda_counts.items() if count >= 2))
        exceptional_onsets = tuple(sorted(signature for signature, count in onset_counts.items() if count == 1))
        exceptional_codas = tuple(sorted(signature for signature, count in coda_counts.items() if count == 1))
        return cls(
            max_onset=percentile(onsets, 1),
            max_coda=percentile(codas, 1),
            nucleus_required=has_nucleus,
            productive_onsets=productive_onsets,
            productive_codas=productive_codas,
            exceptional_onsets=exceptional_onsets,
            exceptional_codas=exceptional_codas,
        )

    def score(self, word: Word) -> dict[str, float]:
        """Vážené porušení; nula znamená produktivně přípustnou formu."""
        if self.nucleus_required and not word.syllable_nuclei():
            return {"missing_nucleus": 4.0}
        onsets, codas = _runs_around_nuclei(word)
        score: Counter[str] = Counter()
        for run in onsets:
            signature = _signature(run)
            if len(run) > self.max_onset:
                score["onset_cluster"] += (len(run) - self.max_onset) * self.onset_weight
            if len(run) > 1 and not _rising(signature) and signature not in self.exceptional_onsets:
                score["onset_sonority"] += self.sonority_weight
        for run in codas:
            signature = _signature(run)
            if len(run) > self.max_coda:
                score["coda_cluster"] += (len(run) - self.max_coda) * self.coda_weight
            if len(run) > 1 and not _falling(signature) and signature not in self.exceptional_codas:
                score["coda_sonority"] += self.sonority_weight
        return dict(score)

    def violation(self, word: Word) -> str | None:
        scores = self.score(word)
        for key in ("missing_nucleus", "onset_cluster", "coda_cluster", "onset_sonority", "coda_sonority"):
            if key in scores:
                return key
        return None

    def repair(self, word: Word) -> bool:
        """Nejméně invazivní oprava nového porušení: epenteze v místě zlomu."""
        violation = self.violation(word)
        if violation is None or violation == "missing_nucleus":
            return False
        vowel = next((segment for segment in word.segments if segment.features.get("syl") == "+"), None)
        if vowel is None:
            return False
        run_start: int | None = None
        run: list[Segment] = []
        for index, segment in enumerate([*word.segments, Segment(features={"syl": "+"})]):
            if _is_consonant(segment):
                if run_start is None:
                    run_start = index
                run.append(segment)
                continue
            if len(run) > 1:
                signature = _signature(run)
                bad_sonority = (violation.startswith("onset") and not _rising(signature)) or (
                    violation.startswith("coda") and not _falling(signature)
                )
                if len(run) > self.max_onset + self.max_coda or bad_sonority:
                    split = run_start + max(1, len(run) // 2)
                    word.segments.insert(split, Segment(features=dict(vowel.features)))
                    word.ensure_stress()
                    return True
            run_start, run = None, []
        return False

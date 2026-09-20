"""Nezávislé osy pro srovnání výsledných jazyků.

LDND měří pouze povrchovou podobu lexika. Tento modul drží ostatní osy
odděleně, aby kalibrátor nemohl zaměnit společný původ, podobný inventář a
skutečný kontakt za jednu hodnotu.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from math import log2
from typing import Callable, Iterable

from cee.core.models import State, Word
from cee.metrics.lexical_distance import LexicalDistance, asjp_ldnd


def _segment_key(word: Word) -> tuple[tuple[str, str], ...]:
    return tuple(tuple(sorted(segment.features.items())) for segment in word.segments)


def _feature_set(words: Iterable[Word]) -> set[tuple[str, str]]:
    return {feature for word in words for segment in word.segments for feature in segment.features.items()}


def _inventory_set(words: Iterable[Word]) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(segment.features.items())) for word in words for segment in word.segments}


def _jaccard_distance(left: set, right: set) -> float:
    union = left | right
    return 0.0 if not union else 1.0 - len(left & right) / len(union)


def _js_divergence(left: Counter, right: Counter) -> float:
    keys = set(left) | set(right)
    total_left, total_right = sum(left.values()), sum(right.values())
    if not keys or not total_left or not total_right:
        return 0.0
    result = 0.0
    for key in keys:
        p, q = left[key] / total_left, right[key] / total_right
        midpoint = (p + q) / 2
        if p:
            result += 0.5 * p * log2(p / midpoint)
        if q:
            result += 0.5 * q * log2(q / midpoint)
    return result


def _bigrams(words: Iterable[Word]) -> Counter:
    return Counter(
        (_segment_key(word)[index], _segment_key(word)[index + 1])
        for word in words if word.active
        for index in range(max(0, len(word.segments) - 1))
    )


@dataclass(frozen=True)
class CognateDistance:
    shared_meanings: int
    shared_lineages: int
    retention: float
    distance: float


def cognate_distance(left: State, right: State) -> CognateDistance:
    """Vzdálenost podle provenance, nikoli podobnosti povrchových forem."""
    def by_concept(state: State) -> dict[str, set[str]]:
        result: dict[str, set[str]] = {}
        for word in state.lexicon.words:
            if word.active:
                result.setdefault(word.concept_id, set()).add(word.lineage_id or word.id)
        return result
    left_by_concept, right_by_concept = by_concept(left), by_concept(right)
    shared = sorted(set(left_by_concept) & set(right_by_concept))
    retained = sum(bool(left_by_concept[item] & right_by_concept[item]) for item in shared)
    ratio = retained / len(shared) if shared else 0.0
    return CognateDistance(len(shared), retained, ratio, 1.0 - ratio)


@dataclass(frozen=True)
class ContactProfile:
    active_words: int
    loan_words: int
    loan_ratio: float
    sources: dict[str, int]
    domains: dict[str, int]


def contact_profile(state: State) -> ContactProfile:
    words = [word for word in state.lexicon.words if word.active]
    sources = Counter(word.source_id for word in words if word.source_id)
    domains = Counter(
        word.grammatical_features.get("contact.domain", "unspecified")
        for word in words if word.source_id
    )
    return ContactProfile(len(words), sum(sources.values()), sum(sources.values()) / len(words) if words else 0.0, dict(sorted(sources.items())), dict(sorted(domains.items())))


@dataclass(frozen=True)
class LexiconHealth:
    active_words: int
    mean_segments: float
    short_content_words: int
    collision_groups: int
    words_in_collision: int


def lexicon_health(state: State) -> LexiconHealth:
    words = [word for word in state.lexicon.words if word.active]
    counts = Counter(_segment_key(word) for word in words)
    content = [word for word in words if not word.is_grammatical]
    return LexiconHealth(
        len(words),
        sum(len(word.segments) for word in words) / len(words) if words else 0.0,
        sum(len(word.segments) <= 2 for word in content),
        sum(count > 1 for count in counts.values()),
        sum(count for count in counts.values() if count > 1),
    )


@dataclass(frozen=True)
class StructuralDistance:
    """Malé jádro strukturálních rysů, které engine už explicitně modeluje."""
    comparable_features: int
    mismatches: int
    distance: float


def structural_distance(left: State, right: State) -> StructuralDistance:
    pairs = (
        (left.affixation_strategy, right.affixation_strategy),
        (left.compound_head, right.compound_head),
    )
    mismatches = sum(first != second for first, second in pairs)
    return StructuralDistance(len(pairs), mismatches, mismatches / len(pairs))


@dataclass(frozen=True)
class LanguageDistanceVector:
    lexical: LexicalDistance
    cognate: CognateDistance
    inventory_jaccard: float
    feature_jaccard: float
    phonotactic_js: float
    structural: StructuralDistance
    contact_left: ContactProfile
    contact_right: ContactProfile

    def as_dict(self) -> dict:
        return asdict(self)


def compare_languages(left: State, right: State, render: Callable[[Word], str]) -> LanguageDistanceVector:
    """Vrátí vektor metrik bez jejich násilného sloučení do jediného skóre."""
    left_words = [word for word in left.lexicon.words if word.active]
    right_words = [word for word in right.lexicon.words if word.active]
    left_forms = {word.concept_id: render(word) for word in left_words}
    right_forms = {word.concept_id: render(word) for word in right_words}
    return LanguageDistanceVector(
        lexical=asjp_ldnd(left_forms, right_forms),
        cognate=cognate_distance(left, right),
        inventory_jaccard=_jaccard_distance(_inventory_set(left_words), _inventory_set(right_words)),
        feature_jaccard=_jaccard_distance(_feature_set(left_words), _feature_set(right_words)),
        phonotactic_js=_js_divergence(_bigrams(left_words), _bigrams(right_words)),
        structural=structural_distance(left, right),
        contact_left=contact_profile(left),
        contact_right=contact_profile(right),
    )

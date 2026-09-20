"""Srovnatelné lexikální vzdálenosti nad seznamy stejných významů.

ASJP používá LDND: průměrnou normalizovanou Levenshteinovu vzdálenost slov
stejného významu, dělenou průměrnou vzdáleností slov různých významů. Druhý
člen koriguje náhodnou podobnost danou inventářem a délkou forem.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


def normalized_levenshtein(left: str, right: str) -> float:
    """Levenshteinova vzdálenost normalizovaná délkou delší formy."""
    row = list(range(len(right) + 1))
    for index, value in enumerate(left, 1):
        old, row[0] = row[0], index
        for other_index, other_value in enumerate(right, 1):
            old, row[other_index] = row[other_index], min(
                row[other_index] + 1,
                row[other_index - 1] + 1,
                old + (value != other_value),
            )
    return row[-1] / max(1, len(left), len(right))


@dataclass(frozen=True)
class LexicalDistance:
    shared_meanings: int
    same_meaning_nld: float
    different_meaning_nld: float
    ldnd: float | None

    def as_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def asjp_ldnd(left: Mapping[str, str], right: Mapping[str, str]) -> LexicalDistance:
    """Vrátí ASJP-style LDND pro dvě slovní zásoby indexované konceptem.

    Vstup musí být fonetický přepis; pravopis by do výsledku míchal ortografii.
    LDND není omezeno na 0–1, proto se neinterpretuje jako pravděpodobnost.
    """
    shared = sorted(set(left) & set(right))
    if not shared:
        return LexicalDistance(0, 1.0, 0.0, None)
    same = [normalized_levenshtein(left[concept], right[concept]) for concept in shared]
    different = [
        normalized_levenshtein(left[first], right[second])
        for first in shared
        for second in shared
        if first != second
    ]
    same_meaning = sum(same) / len(same)
    different_meaning = sum(different) / len(different) if different else 0.0
    return LexicalDistance(
        shared_meanings=len(shared),
        same_meaning_nld=round(same_meaning, 6),
        different_meaning_nld=round(different_meaning, 6),
        ldnd=round(same_meaning / different_meaning, 6) if different_meaning else None,
    )

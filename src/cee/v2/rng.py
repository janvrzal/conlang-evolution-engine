"""Deterministická náhoda enginu v2.

Každý náhodný tah závisí jen na seedu světa a na stabilních ID toho, čeho se
týká (tick, skupina, změna, varianta), nikdy na pořadí ani na počtu ostatních
objektů. Přidání nesouvisející skupiny proto nezmění tahy těch ostatních — na
tom stojí přiblížení mapy (specifikace, oddíl Determinismus).
"""

from __future__ import annotations

import hashlib

import numpy as np
import numpy.typing as npt

_MASK64 = (1 << 64) - 1
_FLOAT53 = float(1 << 53)


def stable_int(*parts: object) -> int:
    """64bitový otisk libovolných částí; ("ab", "c") a ("a", "bc") se liší."""
    digest = hashlib.blake2b(digest_size=8)
    for part in parts:
        digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8"))
    return int.from_bytes(digest.digest(), "big")


def stable_id(prefix: str, *parts: object) -> str:
    """Čitelný a stabilní identifikátor odvozený z původu objektu."""
    return f"{prefix}:{stable_int(prefix, *parts):016x}"


def generator(seed: int, *parts: object) -> np.random.Generator:
    """Samostatný generátor pro jednu kombinaci (seed, části)."""
    return np.random.Generator(
        np.random.PCG64(np.random.SeedSequence([seed & _MASK64, stable_int(*parts)]))
    )


def _splitmix64(values: npt.NDArray[np.uint64]) -> npt.NDArray[np.uint64]:
    values = values + np.uint64(0x9E3779B97F4A7C15)
    values = (values ^ (values >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    values = (values ^ (values >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return values ^ (values >> np.uint64(31))


def hash_normal(
    row_keys: npt.NDArray[np.uint64],
    column_keys: npt.NDArray[np.uint64],
    *,
    pairwise: bool = False,
) -> npt.NDArray[np.float64]:
    """Hodnoty N(0, 1), z nichž každá závisí jen na svém páru klíčů.

    Bez ``pairwise`` vrací matici všech kombinací řádek × sloupec, s ním
    jednu hodnotu pro každou dvojici na stejné pozici. Generátor pro každou
    dvojici (skupina, varianta) by byl deterministický, ale tisíckrát
    pomalejší. Hashovaný šum je vektorový a přitom nezávislý na tom, které
    jiné skupiny či varianty ve stejném kroku existují.
    """
    rows = row_keys.astype(np.uint64)
    columns = column_keys.astype(np.uint64)
    if not pairwise:
        rows, columns = rows[:, None], columns[None, :]
    with np.errstate(over="ignore"):
        first = _splitmix64(rows ^ _splitmix64(columns))
        second = _splitmix64(first)
    uniform_a = ((first >> np.uint64(11)).astype(np.float64) + 0.5) / _FLOAT53
    uniform_b = ((second >> np.uint64(11)).astype(np.float64) + 0.5) / _FLOAT53
    normal: npt.NDArray[np.float64] = np.sqrt(-2.0 * np.log(uniform_a)) * np.cos(
        2.0 * np.pi * uniform_b
    )
    return normal

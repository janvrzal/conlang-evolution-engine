"""Deterministická náhoda enginu v2.

Každý náhodný tah závisí jen na seedu světa a na stabilních ID toho, čeho se
týká (tick, skupina, změna, varianta), nikdy na pořadí ani na počtu ostatních
objektů. Přidání nesouvisející skupiny proto nezmění tahy těch ostatních — na
tom stojí přiblížení mapy (specifikace, oddíl Determinismus).
"""

from __future__ import annotations

import hashlib
import math
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from itertools import accumulate

import numpy as np
import numpy.typing as npt

_MASK64 = (1 << 64) - 1
_FLOAT53 = float(1 << 53)
_GOLDEN = 0x9E3779B97F4A7C15
_MIX_1 = 0xBF58476D1CE4E5B9
_MIX_2 = 0x94D049BB133111EB
#: Nejvyšší střední hodnota jednoho kusu Poissonova tahu (viz :meth:`Stream.poisson`).
_POISSON_CHUNK = 30.0
#: Pojistka inverze Poissonova rozdělení; pro λ ≤ 30 je P(X > 120) pod 1e-37.
_POISSON_MAX = 120


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


class Stream:
    """Přenositelný proud náhody pro jednu kombinaci (seed, části).

    Nahrazuje ``numpy.random.Generator`` všude, co běží během simulace.
    Algoritmy jsou záměrně jednoduché, aby je šlo přepsat do Rustu bit po bitu
    (``u64`` s přetékáním, ``f64``, ``u128`` pro Lemirovo násobení). Celé
    chování určují tyto kroky; žádný jiný stav než ``state`` neexistuje.

    **Klíč.** ``key = stable_int("stream", seed & (2**64 - 1), *parts)``
    (blake2b, ``digest_size=8``, viz :func:`stable_int`). Stav začíná ``key``.

    **Jádro (SplitMix64).** Každé ``next_u64()``::

        state = (state + 0x9E3779B97F4A7C15) mod 2**64
        z = ((state ^ (state >> 30)) * 0xBF58476D1CE4E5B9) mod 2**64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) mod 2**64
        return z ^ (z >> 31)

    **random().** Jedno ``next_u64()``: ``(x >> 11) / 2**53``, tedy ``[0, 1)``
    s 53 bity, dělení je přesná mocnina dvou.

    **integers(n)** (celé číslo ``0 <= i < n``, ``n >= 1``): Lemirova metoda
    bez zkreslení. Jedno ``x = next_u64()``; ``m = x * n`` (128bitově);
    ``low = m mod 2**64``. Když ``low < n``, spočte se ``t = (2**64 - n) mod n``
    a dokud ``low < t``, vezme se nové ``x`` a přepočte ``m`` a ``low``.
    Výsledek je ``m >> 64``. Jedno ``next_u64()`` se spotřebuje vždy, i pro
    ``n = 1``; víc jen při odmítnutí (pravděpodobnost ``< n / 2**64``).

    **choice(n, p)**: bez ``p`` je to ``integers(n)``. S ``p`` (váhy, ne nutně
    normalizované, nezáporné, součet kladný a konečný) se kumulativní součty
    ``c[i] = c[i-1] + p[i]`` počítají *postupně v pořadí indexů* v ``f64``
    (``c[-1]`` je ``total``), vezme se ``u = random()``, ``target = u * total``
    a výsledek je první index s ``c[i] > target`` (``bisect_right``). Nulová
    váha se tím nikdy nevybere (její ``c`` se od předchozí neliší, takže
    ``c[i] > target`` platí už dřív nebo vůbec). Kdyby zaokrouhlení dalo
    ``target >= total``, vybere se poslední index s kladnou váhou, tj. první
    ``i`` s ``c[i] == total``. Jedno ``next_u64()`` na tah.

    **normal(mean, sd)**: Box–Muller, dvě ``next_u64()``, obě převedená na
    ``u = ((x >> 11) + 0.5) / 2**53`` (tedy ``(0, 1)``)::

        z = sqrt(-2 * ln(u1)) * cos(2 * pi * u2)
        return mean + sd * z

    (druhá hodnota páru se zahazuje, takže tah spotřebuje vždy dvě čísla.)
    ``ln`` a ``cos`` jsou funkce libm (Python ``math``, Rust ``f64::ln`` a
    ``f64::cos``); na různých platformách se mohou lišit v posledním bitu.

    **poisson(lam)**: viz :meth:`poisson`.
    """

    __slots__ = ("state",)

    def __init__(self, seed: int, *parts: object) -> None:
        self.state = stable_int("stream", seed & _MASK64, *parts)

    @classmethod
    def from_key(cls, key: int) -> Stream:
        """Proud s daným 64bitovým klíčem (počáteční stav)."""
        stream = cls.__new__(cls)
        stream.state = key & _MASK64
        return stream

    def next_u64(self) -> int:
        state = self.state = (self.state + _GOLDEN) & _MASK64
        z = ((state ^ (state >> 30)) * _MIX_1) & _MASK64
        z = ((z ^ (z >> 27)) * _MIX_2) & _MASK64
        return z ^ (z >> 31)

    def random(self) -> float:
        """Rovnoměrně na ``[0, 1)`` s 53 bity."""
        return (self.next_u64() >> 11) / _FLOAT53

    def integers(self, n: int) -> int:
        """Celé číslo ``0 <= i < n`` bez zkreslení (Lemirova metoda)."""
        if n < 1:
            raise ValueError("integers: n musí být aspoň 1.")
        m = self.next_u64() * n
        low = m & _MASK64
        if low < n:
            threshold = ((1 << 64) - n) % n
            while low < threshold:
                m = self.next_u64() * n
                low = m & _MASK64
        return m >> 64

    def choice(self, n: int, p: Sequence[float] | npt.NDArray[np.float64] | None = None) -> int:
        """Index ``0 <= i < n``; s vahami ``p`` úměrně váze, jinak rovnoměrně."""
        if p is None:
            return self.integers(n)
        return self.pick(cumulative(p), self.random())

    @staticmethod
    def pick(cumulated: Sequence[float], u: float) -> int:
        """Index podle předpočtených kumulativních vah (:func:`cumulative`) a ``u``."""
        total = cumulated[-1]
        index = bisect_right(cumulated, u * total)
        if index >= len(cumulated):
            index = bisect_left(cumulated, total)
        return index

    def normal(self, mean: float = 0.0, sd: float = 1.0) -> float:
        """Normální rozdělení N(mean, sd²), Box–Muller (dva tahy)."""
        u1 = ((self.next_u64() >> 11) + 0.5) / _FLOAT53
        u2 = ((self.next_u64() >> 11) + 0.5) / _FLOAT53
        return mean + sd * (math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2))

    def poisson(self, lam: float) -> int:
        """Poissonův tah se střední hodnotou ``lam`` (součet kusů po nejvýš 30).

        Střední hodnota se rozdělí na ``m = ceil(lam / 30)`` stejných kusů
        ``lam / m`` (nejvýš 30) a tahy kusů, každý z jednoho ``random()``,
        se sečtou. Součet nezávislých Poissonových veličin je Poissonova,
        takže rozdělení je přesné a stačí k tomu jen ``exp``. Kus se losuje
        inverzí :func:`poisson_inversion`. ``lam <= 0`` vrací 0 bez tahu.
        """
        if lam <= 0.0:
            return 0
        chunks = max(1, math.ceil(lam / _POISSON_CHUNK))
        part = lam / chunks
        return sum(poisson_inversion(part, self.random()) for _ in range(chunks))


def cumulative(weights: Sequence[float] | npt.NDArray[np.float64]) -> list[float]:
    """Kumulativní součty vah počítané postupně v ``f64`` v pořadí indexů.

    Pro :meth:`Stream.choice` a :meth:`Stream.pick`. Váhy musí být nezáporné
    a konečné a jejich součet kladný, jinak ``ValueError``.
    """
    values = weights.tolist() if isinstance(weights, np.ndarray) else [float(w) for w in weights]
    if not values:
        raise ValueError("choice: prázdné váhy.")
    cumulated = list(accumulate(values))
    total = cumulated[-1]
    if not (total > 0.0 and math.isfinite(total)) or min(values) < 0.0:
        raise ValueError("choice: váhy musí být nezáporné a konečné se součtem kladným.")
    return cumulated


def poisson_inversion(lam: float, u: float) -> int:
    """Poissonův tah inverzí CDF pro ``0 < lam <= 30`` a ``u`` z ``[0, 1)``.

    ``p = exp(-lam)``, ``cdf = p``; pro ``k = 1, 2, ...`` dokud ``u > cdf``
    (nejvýš do ``k = 120``): ``p = p * (lam / k)``, ``cdf = cdf + p``. Výsledek
    je poslední ``k``, při kterém se cyklus provedl (0, když ``u <= exp(-lam)``).
    """
    p = math.exp(-lam)
    cdf = p
    count = 0
    while u > cdf and count < _POISSON_MAX:
        count += 1
        p = p * (lam / count)
        cdf = cdf + p
    return count


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


def hash_poisson(
    row_keys: npt.NDArray[np.uint64],
    column_keys: npt.NDArray[np.uint64],
    expected: npt.NDArray[np.float64],
    *,
    pairwise: bool = False,
) -> npt.NDArray[np.int64]:
    """Celočíselné náhodné tahy Poissonova rozdělení závislé jen na svých klíčích.

    Podobně jako :func:`hash_normal` nevyžaduje sdílený stav generátoru napříč
    skupinami ani postupné volání. Bez ``pairwise`` vrací matici všech kombinací
    řádek × sloupec, s ním hodnoty pro dvojice na stejné pozici.
    Pro malé a střední střední hodnoty (do 30) využívá inverzní CDF transformaci
    s 53bitovou rovnoměrnou náhodou odvozenou ze SplitMix64. Pro vyšší střední
    hodnoty losuje :class:`Stream` s klíčem ``splitmix64(first)`` daného prvku
    (:meth:`Stream.poisson`: součet inverzních tahů kusů po nejvýš 30).
    """
    lam = np.asarray(expected, dtype=np.float64)
    rows = np.asarray(row_keys, dtype=np.uint64)
    columns = np.asarray(column_keys, dtype=np.uint64)

    if np.any(np.isnan(lam)) or np.any(lam < 0.0) or np.any(np.isinf(lam)):
        raise ValueError("Střední hodnoty Poissonova rozdělení musí být nezáporná konečná čísla.")

    if not pairwise:
        rows, columns = rows[:, None], columns[None, :]
        mixed_shape = (rows.shape[0], columns.shape[1])
        if mixed_shape != lam.shape:
            raise ValueError(
                f"Výsledný tvar klíčů {mixed_shape} neodpovídá tvaru očekávaných hodnot {lam.shape}."
            )
    else:
        if not (rows.shape == columns.shape == lam.shape):
            raise ValueError(
                f"V režimu pairwise musí mít klíče i expected stejný tvar: "
                f"{rows.shape} vs. {columns.shape} vs. {lam.shape}."
            )

    counts = np.zeros(lam.shape, dtype=np.int64)
    positive = lam > 0.0
    if not np.any(positive):
        return counts

    with np.errstate(over="ignore"):
        first = _splitmix64(rows ^ _splitmix64(columns))

    small = positive & (lam <= 30.0)
    if np.any(small):
        sub_lam = lam[small]
        sub_u = ((first[small] >> np.uint64(11)).astype(np.float64) + 0.5) / _FLOAT53
        sub_counts = np.zeros(sub_lam.shape, dtype=np.int64)
        p = np.exp(-sub_lam)
        cdf = p.copy()
        for k in range(1, 121):
            still = (sub_u > cdf) & ((cdf + p > cdf) | (k <= sub_lam))
            if not np.any(still):
                break
            sub_counts[still] = k
            p = p * (sub_lam / k)
            cdf = cdf + p
        counts[small] = sub_counts

    large = lam > 30.0
    if np.any(large):
        first_flat = first.reshape(-1)
        lam_flat = lam.reshape(-1)
        counts_flat = counts.reshape(-1)
        for idx in np.flatnonzero(large):
            with np.errstate(over="ignore"):
                seed64 = int(_splitmix64(first_flat[idx : idx + 1])[0])
            counts_flat[idx] = Stream.from_key(seed64).poisson(float(lam_flat[idx]))

    return counts


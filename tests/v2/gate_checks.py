"""Pomocné statistické a vyhodnocovací funkce pro zpevnění milníkových bran.

Obsahuje přesné výpočty Wilsonova konfidenčního intervalu, binomické distribuční
funkce, prahů k z N a společné vyhodnocovací funkce tvrzení.
"""

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

#: Kritická hodnota standardního normálního rozdělení pro 95% oboustranný interval.
Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Spočte Wilsonův skórový interval spolehlivosti pro binomický podíl.

    Vstupy musí splňovat ``0 <= successes <= total`` a ``total > 0``.
    Výsledné meze jsou oříznuty do intervalu ``[0.0, 1.0]``.
    """
    if not isinstance(successes, int) or not isinstance(total, int):
        raise ValueError("Počet úspěchů i celkový počet musí být celá čísla.")
    if total <= 0:
        raise ValueError(f"Celkový počet pokusů musí být kladný, zadáno: {total}.")
    if successes < 0 or successes > total:
        raise ValueError(
            f"Počet úspěchů ({successes}) musí ležet v rozsahu 0..{total}."
        )

    z2 = z * z
    denom = total + z2
    p = successes / total
    center = successes + z2 / 2.0
    spread = z * math.sqrt(total * p * (1.0 - p) + z2 / 4.0)

    lower = max(0.0, min(1.0, (center - spread) / denom))
    upper = max(0.0, min(1.0, (center + spread) / denom))
    return lower, upper


def binomial_cdf_lt(k: int, n: int, p: float) -> float:
    """Spočte přesnou pravděpodobnost P(Bin(n, p) < k).

    Platí pro ``n >= 0`` a ``0.0 <= p <= 1.0``.
    Okrajové případy:
    - ``k <= 0`` vrací 0.0,
    - ``k > n`` vrací 1.0.
    """
    if n < 0:
        raise ValueError(f"Počet pokusů n musí být nezáporný, zadáno: {n}.")
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"Pravděpodobnost p musí ležet v [0.0, 1.0], zadáno: {p}.")

    if k <= 0:
        return 0.0
    if k > n:
        return 1.0

    if p == 0.0:
        # P(X = 0) = 1.0, pro k >= 1 je P(X < k) = 1.0.
        return 1.0
    if p == 1.0:
        # P(X = n) = 1.0, pro k <= n je P(X < k) = 0.0.
        return 0.0

    total_prob = sum(
        math.comb(n, j) * (p**j) * ((1.0 - p) ** (n - j)) for j in range(k)
    )
    return max(0.0, min(1.0, float(total_prob)))


def threshold_k(n: int, p_lower: float, alpha: float = 0.01) -> int:
    """Vrátí největší k v 0..n takové, že P(Bin(n, p_lower) < k) <= alpha."""
    if n < 0:
        raise ValueError(f"Počet pokusů n musí být nezáporný, zadáno: {n}.")
    for k in range(n, -1, -1):
        if binomial_cdf_lt(k, n, p_lower) <= alpha:
            return k
    return 0


def classify_rate(successes: int, total: int) -> str:
    """Zařadí míru průchodu do kategorie: robustní, křehká nebo slabá."""
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError(f"Neplatné hodnoty: successes={successes}, total={total}.")
    if successes * 20 >= 19 * total:
        return "robustní"
    if successes * 2 >= total:
        return "křehká"
    return "slabá"


def passes(
    check_fn: Callable[..., Any], *args: Any, **kwargs: Any
) -> tuple[bool, str | None]:
    """Zavolá kontrolní funkci a zachytí pouze AssertionError.

    Vrací ``(True, None)`` při úspěchu a ``(False, str(exc))`` při AssertionError.
    Jakákoliv jiná výjimka probublá bez zachycení.
    """
    try:
        check_fn(*args, **kwargs)
    except AssertionError as exc:
        return False, str(exc) or "AssertionError"
    return True, None


def assert_k_of_n(
    seeds: Sequence[int],
    passed_seeds: Sequence[int],
    k: int,
    failures: Mapping[int, str] | None = None,
) -> None:
    """Ověří, že počet úspěšných seedů je alespoň k."""
    passed = list(passed_seeds)
    total = len(seeds)
    if len(passed) < k:
        msg = (
            f"Brána neprošla: úspěšných seedů {len(passed)}/{total} "
            f"(požadováno >= {k}). Úspěšné seedy: {passed}."
        )
        if failures:
            details = [
                f"seed {s}: {failures.get(s, 'AssertionError')}"
                for s in seeds
                if s not in passed
            ]
            msg += f" Selhání: {', '.join(details)}"
        raise AssertionError(msg)


def evaluate_seeds(
    runs_by_seed: Mapping[int, Any],
    check_one: Callable[[Any], None],
    k: int,
) -> None:
    """Vyhodnotí kontrolu check_one pro každý seed a ověří průchod alespoň k seedů."""
    seeds = list(runs_by_seed.keys())
    passed_seeds: list[int] = []
    failures: dict[int, str] = {}
    for seed in seeds:
        data = runs_by_seed[seed]
        passed, err = passes(check_one, data)
        if passed:
            passed_seeds.append(seed)
        else:
            failures[seed] = err or "AssertionError"
    assert_k_of_n(seeds, passed_seeds, k=k, failures=failures)

"""Otisky logu enginu v2 pro kontrolu bitové shody po optimalizaci.

Spustí pevnou sadu světů (zvuk, morfologie, význam, syntax, kontakt, město
s ostrovem, údolí s 50 vesnicemi) a vypíše otisk historie každého z nich.
Optimalizace, která nemá měnit výsledek, musí dát přesně stejný výpis jako
předchozí commit.

Použití:  python scripts/v2_digests.py [--quick]

Reference fáze 5 (dávkové losování inovací přes skupiny, krok 1):
    phonology    91e46de9b912a8847fb7b1595c007c18c5ff0bbf4ca52eb414980df7f2bad4f4
    morphology   7ea78265d605f629dab2edc1f90e7d594d47fde4215d8392e5c3472bb9d5fa87
    syntax       9e1abfe36cce76d10594a7a5087ae61f5f82e0ab6f2b94bae56897e75625dd0c
    grid-5x5     36767c976a7af2c7c989dce2e37b86a582ee97233c2c4cce0e5fc3bde5f2b9bf
    shift        1bfbc2a466d61db09d5762ff2d718069adde6da343eb289bbffee5ce44de36eb
    island-city  3577e966ab9e39320f55688982c42e0d95b9ccfb0b6eb37b6388d937bf20c29e
    valley-50    6246ebdba75988f78e32d386c320bfd6d6842f6dc09d833537b05ef94544a08d
"""

from __future__ import annotations

import sys
import time

from cee.v2.scenarios import island_and_city, language_shift, village_grid
from cee.v2.simulation import Simulation


def worlds(quick: bool):
    yield "phonology", lambda: (village_grid(4, seed=2, phonology=True), ()), 1000
    yield "morphology", lambda: (village_grid(4, seed=2, morphology=True, semantics=True), ()), 1000
    yield "syntax", lambda: (village_grid(4, seed=2, syntax=True, semantics=True), ()), 1000
    yield "grid-5x5", lambda: (village_grid(5, 5, seed=2, morphology=True, semantics=True), ()), 1000
    yield "shift", lambda: language_shift(2, start=300.0), 900
    yield "island-city", lambda: (island_and_city(2), ()), 800
    if not quick:
        yield "valley-50", lambda: (village_grid(10, 5, seed=1, syntax=True, semantics=True), ()), 2000


def main() -> None:
    quick = "--quick" in sys.argv
    for name, build, years in worlds(quick):
        world, events = build()
        simulation = Simulation(world, events=events)
        started = time.perf_counter()
        simulation.run(years)
        print(f"{name:12s} {simulation.history.digest()}  {time.perf_counter() - started:6.1f} s", flush=True)


if __name__ == "__main__":
    main()

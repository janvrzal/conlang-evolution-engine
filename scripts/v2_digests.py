"""Otisky logu enginu v2 pro kontrolu bitové shody po optimalizaci.

Spustí pevnou sadu světů (zvuk, morfologie, význam, syntax, kontakt, město
s ostrovem, údolí s 50 vesnicemi) a vypíše otisk historie každého z nich.
Optimalizace, která nemá měnit výsledek, musí dát přesně stejný výpis jako
předchozí commit.

Použití:  python scripts/v2_digests.py [--quick]
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

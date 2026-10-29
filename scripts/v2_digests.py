"""Otisky logu enginu v2 pro kontrolu bitové shody po optimalizaci.

Spustí pevnou sadu světů (zvuk, morfologie, význam, syntax, kontakt, město
s ostrovem, údolí s 50 vesnicemi) a vypíše otisk historie každého z nich.
Optimalizace, která nemá měnit výsledek, musí dát přesně stejný výpis jako
předchozí commit.

Použití:  python scripts/v2_digests.py [--quick]

Reference zpevnění bran (neutrální klíč ``innovation-change``):
    phonology    8d7971c1a6afe5f6b8ca9f33919b8b3e2e929d56832ae4e04c738efa18c53840
    morphology   3567be70a272f42662ecd44838079d33abf953d090c59a9a2da4079467933a06
    syntax       eefb5db5be7bfac8284c400b7a0ebc81fe4a65c04325aaafa9b1cdb39d50fc38
    grid-5x5     a6aa9a33f1a416e33144a0235d19194c442bb27ede6f966c5092a7b7342b08c0
    shift        47d69ad8a511366b2dedba0a9c30550c0c1d0045aa24ce3eafbdde03663da71a
    island-city  a082c2463488378f975fc050a9265f62856e716d6b1dd0b4d813f7d5323ab2cf
    valley-50    02ccc3819e155cff096d791466f3dcdab88142a4e31e9b1920f92fc9898b1272
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

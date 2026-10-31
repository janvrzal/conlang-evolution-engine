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

Reference části B typologie (doplněk M2, sekundární artikulace):
    phonology    cd79626de3a0b02f19fea574cf5637971ad012a1f89aeacb9a59a04e8064dd62
    morphology   b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849
    syntax       3dca8fd6c3e511c3ef059d4e0d5550eadd2e3d94024afcc550b7e730fbaefcf0
    grid-5x5     83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95
    shift        d1a1e9e5af395b3120426fb3035912720dccdc5727168e62aa6dee1799dd6816
    island-city  13717cb46affdc42b9938627d9314ab09c23fec227595ce6f53cfa099a22d4aa
    valley-50    0d462e154e885753e74ad645d2ecb9085bd4d1e442cc86f9229d693f366fca00

Reference části D typologie (prozódie, posun přízvuku a zakončení části D):
    phonology    1c1bd2c691a4b9aacd499e038b945cdd1c759f6a5a5b1de7ba204362f35fa755
    morphology   b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849
    syntax       9c9803132e86d566e7ccc623f381622a19aedc042c443ed0a1f3d0dc964b0084
    grid-5x5     83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95
    shift        c6892607c6779018a02633a9da44f5d10f9fa98c458e1d31c91cee3b75d6784e
    island-city  59e723ed5d4eb316f73c817e92972017e7cb69578746121381b4a609948c4abd
    valley-50    9c2e85f1aa5448e50811ffa2db9587bda771ee84564b815243814ddc6ecf2476

Reference části E (zánik kategorie bez prahu a `Learnability`; mění jen
scénáře s L2 mluvčími; parametry jako data otisky nezměnily):
    phonology    1c1bd2c691a4b9aacd499e038b945cdd1c759f6a5a5b1de7ba204362f35fa755
    morphology   b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849
    syntax       9c9803132e86d566e7ccc623f381622a19aedc042c443ed0a1f3d0dc964b0084
    grid-5x5     83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95
    shift        c934bff8888225fd23621c0ee3288c4c208b4b9ce6f535fd9a34b2adfb67e342
    island-city  e3b1ba4d2a3410424595f13c8213f48987455299fd5c83de024d782bb4892b65
    valley-50    9c2e85f1aa5448e50811ffa2db9587bda771ee84564b815243814ddc6ecf2476

Reference lineárního pozorování (průměrná vazba mezi sousedícími shluky ze
součtů, ``observe.constrained_average_linkage``; simulace se nemění, liší se
jen záznamy o jazycích tam, kde je pozorovatel rozpozná jinak):
    phonology    1c1bd2c691a4b9aacd499e038b945cdd1c759f6a5a5b1de7ba204362f35fa755
    morphology   b673137d804d7542106c47e7203f93c9bf63268d8951909b49df12755b29e849
    syntax       9c9803132e86d566e7ccc623f381622a19aedc042c443ed0a1f3d0dc964b0084
    grid-5x5     83d79ffb6e029604422730b9906dcf7b68d2ed522ef5f405fe706a6dbf6d5c95
    shift        c934bff8888225fd23621c0ee3288c4c208b4b9ce6f535fd9a34b2adfb67e342
    island-city  e3b1ba4d2a3410424595f13c8213f48987455299fd5c83de024d782bb4892b65
    valley-50    c745056a17646c83224a5aa599997050602f81a288bb1b9e276c7241e37b234b
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

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
Reference tónů (2026-11-01; tón jako rys samohlásky a pět tónových rodin
zvukových změn s vlastním rozpočtem inovací, ``changes.sound.ToneFromOnset`` ad.;
celé IPA v tabulce hlásek otisky nezměnilo):
    phonology    8c5c7a9213138b3eebef7b843fe335138dc254bbfea4345f0462af4e81a7258e
    morphology   4513fcc9c32e4e23c025804f6e3edac03f5cb5f6bca79afd4608a3ed01fd1a4e
    syntax       360182dca78fade984da6794b855bf35e76210bd56e4d56c46c6bcb4bcbe025d
    grid-5x5     e1cd39209596a00f1b423802e53e4681081d0de1a5ce623a6dc0fa223e68a0fa
    shift        5462ab0d60b7091fe6afc589f11722a29ab0450310bfbaafe6d273cab9a37d2e
    island-city  2467a8174cef5f6431a37686106d7e9d5a3d6b2c7a63142eeaea36c49596994e
    valley-50    011ca86444d970a59367396e7b99739907ef765e0edacab462c51a34f77a56db

Reference výpůjček (2026-11-01; změna ``changes.lexicon.LexicalBorrowing``,
působí jen ve světech s více jazyky, proto se změnil jen ``shift``; pozadí
dějin s výchozí mírou ``none`` otisky nezměnilo):
    phonology    8c5c7a9213138b3eebef7b843fe335138dc254bbfea4345f0462af4e81a7258e
    morphology   4513fcc9c32e4e23c025804f6e3edac03f5cb5f6bca79afd4608a3ed01fd1a4e
    syntax       360182dca78fade984da6794b855bf35e76210bd56e4d56c46c6bcb4bcbe025d
    grid-5x5     e1cd39209596a00f1b423802e53e4681081d0de1a5ce623a6dc0fa223e68a0fa
    shift        629d8d5a56b6d6bf2f687e5f21954196027ba8d86002f63e3933cb068cc30460
    island-city  2467a8174cef5f6431a37686106d7e9d5a3d6b2c7a63142eeaea36c49596994e
    valley-50    011ca86444d970a59367396e7b99739907ef765e0edacab462c51a34f77a56db

Reference souběžné variability protojazyka (2026-11-01; ``cee.v2.variation``
rozdá variabilitu slovní zásoby podle ``cee/data/v2_standing_variation.json``,
jen světy se sémantikou; svět bez ní je beze změny):
    phonology    8c5c7a9213138b3eebef7b843fe335138dc254bbfea4345f0462af4e81a7258e
    morphology   2d2fb0297b2e87508def9f1f64f128a2a54f08edebbffbb2f0a47f7f579ed3f4
    syntax       d1f4c81011ef7826ff4eac45281cd8e9bdb0180077f15ddc49186b5e0fc8da02
    grid-5x5     a275faf2a41bcbdded1cf2979bedb062eb8a1156bd1213e97be1d4236bee6eb1
    shift        b1b7266fd342099cf16515d3a652f16e5bc51e035a9aa164fbd3b1954c72103e
    island-city  4c1c53554286862612aa9377fdc26831c88cd1c28da557d5218156262564cd2b
    valley-50    13556259eaec43e0ae265487f8c645e48a91b2fd0b867e2ba9faba77f7c4ca22
Reference přenositelné náhody (2026-11-02, krok A6 přípravy na Rust; losy během
simulace jdou přes ``rng.Stream`` místo ``numpy.random.Generator``: výběr místa
inovace, návrhy změn, sklony slov, velká λ v ``hash_poisson``; tvorba světa
zůstala na numpy a svět po ``build()`` je beze změny. Vědomá změna otisků):
    phonology    3ffcb70c000f5624e98a927ee24163bff04a28f8dae527151cb2622ca804b8f5
    morphology   22bdbef0509feac65bf8d14a1f3e183b5aac6ab2237190c51817de5b8c634ee0
    syntax       1e3bb9676c9f59d211168b489223f9dd3caaceba28ebc243984141075167d3d6
    grid-5x5     967217a5e6adbdafce1fa1f9220ec2820ca813ca7aa95eb632a733b81a0b2179
    shift        a512ae04fdc30e0367b025182a579422a687706e3366a64b1c97bec072abf829
    island-city  2435b71bc725c5eb22d1f6fb18225df6077e3f2ec4d37dfd018facd45b105391
    valley-50    768ddc6716549b2d31332b4d90fc5be2f8c5e006a30281e98fef91c530db1839
Reference variability podle světa (2026-11-02; ``variation.seed`` dávkuje
variabilitu každé vesnici podle naměřeného modelu vesnice a šíří ji po grafu
vazeb, čtení šetří častá slova ``Parameters.reading_core_resistance``; svět
bez sémantiky, phonology, je beze změny):
    phonology    3ffcb70c000f5624e98a927ee24163bff04a28f8dae527151cb2622ca804b8f5
    morphology   7ffa92b662336c5faf8741f12176cc274b90cc98bb39a75014904e87e97e6b74
    syntax       108cfeeb9c23e7d8c4a3084b20dd9c277d4f4e5ee68b54f5929399923766a9d0
    grid-5x5     376109562b71f977ae4c479cab2283a2bf4b3d5c27018ff45002933d0ec37ee0
    shift        ddb8bc542e421d6ca32bc9dbdda2768496e72cb3b87fbab8cfb408c57b93771c
    island-city  a557c9ff15e9dbc96bd7c3c4b8031618bbaa4783524362c29ba91d9e7ec7411c
    valley-50    f138e7187f19d5f02581c5be0d3c6067f6d1ff95ff41c0eddb458b6ba4d0f3d2
Reference frekvencí pojmů z dat (2026-11-02; ``protolanguage`` bere frekvence
z ``cee.v2.concept_data`` (Calude & Pagel 2011, korpusy Leipzig) místo
generovaných, koše souběžné variability podle nich přeměřeny; tvary slov
protojazyka beze změny):
    phonology    37e949768bf1f5fe2e0bdb106d39cbf199b842c24750ced943ca4c4ba9f7d2f4
    morphology   1f082a14909f724f98a7fe6aa39c4d8fff092f32ac126b3d217d94eb824e423c
    syntax       c270c0b059eb21af1bb0fa68a17f6efd69eb895040cfafdb11c5d4e04a7ef531
    grid-5x5     f00c56442b3e798fe844df0678d7637de59906480528ce0acb416056efd2dc1f
    shift        45300517345cc5ff3e22a1ff39bf1b1e48b0365662a8e33ada1a95088b06872c
    island-city  d8801215f07f7ad45b657d15ca4c1def5d4678706c1af0603e4ca4eb08ffd2a7
    valley-50    a035aa06625e0293f67f487f69ba174367ae6c9e7f478402b2e5e118c01a8f7b
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

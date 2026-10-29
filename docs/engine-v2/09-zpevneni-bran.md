# Zpevnění milníkových bran enginu v2

Navazuje na dokončenou fázi 5 M6e (`f3a9dfd`, deník `08-davkova-inovace.md`)
podle zadání `docs/engine-v2/zadani-zpevneni-bran.md`.

Ve fázi 5 ukázal přechod z `PCG64.poisson` na `hash_poisson`, že několik
jednoseedových milníkových bran v `tests/v2/*_gate.py` prochází i na původním
enginu pouze v 30–80 % seedů, a doménová konstanta `"innovation-change-34"`
byla zvolena účelově tak, aby všechny brány prošly. Před kalibrací M7 je proto
nutné:

1. přepnout doménovou konstantu klíče inovací na neutrální `"innovation-change"`,
2. změřit míru průchodu všech stochastických tvrzení v `tests/v2/*_gate.py` na
   nezávislé řadě seedů `101..120`,
3. křehké brány (`10–18/20`) převést na agregaci `k` z `N` na souvislé řadě
   seedů `1..N` s prahem odvozeným z dolní meze Wilsonova 95% intervalu,
4. slabé brány (`< 10/20`) nahlásit uživateli k rozhodnutí a u převedených bran
   ověřit negativní kontroly se vypnutým mechanismem.

## Krok 1: neutrální konstanta a nové otisky

V `src/cee/v2/simulation.py` byla zavedena modulová konstanta
`_INNOVATION_CHANGE_DOMAIN = "innovation-change"` a nahradila účelový řetězec
`"innovation-change-34"` v `Simulation._configure` i v kusové variantě
`Simulation._innovate_with` (v zadání zmíněné `_apply_innovations` dostává už
vylosovaný počet `count` a volá `generator(..., "innovation", ...)`).

### Nové referenční otisky (`v2_digests.py`)

Měřeno sériově (`.venv/bin/python scripts/v2_digests.py`, Python 3.11.9,
NumPy 2.4.6) bez souběžné zátěže:

| Scénář | Čas (s) | Předchozí otisk (`f3a9dfd`) | Nový otisk (`innovation-change`) |
|---|---:|---|---|
| `phonology` | 0,2 | `91e46de9b912a8847fb7b1595c007c18c5ff0bbf4ca52eb414980df7f2bad4f4` | `8d7971c1a6afe5f6b8ca9f33919b8b3e2e929d56832ae4e04c738efa18c53840` |
| `morphology` | 0,4 | `7ea78265d605f629dab2edc1f90e7d594d47fde4215d8392e5c3472bb9d5fa87` | `3567be70a272f42662ecd44838079d33abf953d090c59a9a2da4079467933a06` |
| `syntax` | 0,8 | `9e1abfe36cce76d10594a7a5087ae61f5f82e0ab6f2b94bae56897e75625dd0c` | `eefb5db5be7bfac8284c400b7a0ebc81fe4a65c04325aaafa9b1cdb39d50fc38` |
| `grid-5x5` | 2,5 | `36767c976a7af2c7c989dce2e37b86a582ee97233c2c4cce0e5fc3bde5f2b9bf` | `a6aa9a33f1a416e33144a0235d19194c442bb27ede6f966c5092a7b7342b08c0` |
| `shift` | 0,8 | `1bfbc2a466d61db09d5762ff2d718069adde6da343eb289bbffee5ce44de36eb` | `47d69ad8a511366b2dedba0a9c30550c0c1d0045aa24ce3eafbdde03663da71a` |
| `island-city` | 0,6 | `3577e966ab9e39320f55688982c42e0d95b9ccfb0b6eb37b6388d937bf20c29e` | `a082c2463488378f975fc050a9265f62856e716d6b1dd0b4d813f7d5323ab2cf` |
| `valley-50` | **25,4** | `6246ebdba75988f78e32d386c320bfd6d6842f6dc09d833537b05ef94544a08d` | `02ccc3819e155cff096d791466f3dcdab88142a4e31e9b1920f92fc9898b1272` |

Rychlá sada testů (`pytest -m "not slow" -q`: 585 testů za 32,8 s), `ruff` i
`mypy` procházejí bez chyb. Pomalé stochastické milníkové brány mohou po této
změně proudu náhody padat – to je očekávané a řeší je kroky 2–4.

# Deník přepisu datového jádra M6e

Výchozí commit: `3d1016c6687d83e165a49601582a86de59cbfbdc`.
Pracovní větev: `engine-v2-numba`. Koordinátor řídí implementátorky
Terra 6.1 a Luna 6; měření a simulace se spouštějí postupně.

## Výchozí měření (2026-10-29)

Python 3.11.9, macOS arm64, NumPy 2.4.6. Neinstrumentovaný běh
`scripts/v2_digests.py`, před změnou jádra:

| Scénář | Čas (s) | SHA-256 historie |
|---|---:|---|
| phonology | 0,2 | `cdb5587f3219f08954564b08042e7f213e3ffdfdad1647b2f8f08fcff1e69bc3` |
| morphology | 0,4 | `2572f5dcef8af309e1d1a57c984e7e462820ae3fa5ffef8bca2f726d11ac7a25` |
| syntax | 0,6 | `941dc5c7b919f86db6bdac74d9251c7203aca85e0ebd115504bdfbef0d704117` |
| grid-5x5 | 3,7 | `ce9409e7363199218ebdc91f78bfe32d5500c2099fc3910c14e4c80cfea874ab` |
| shift | 1,2 | `41764bcdf9bfaa8ca22b93378df2181fb810288a695ac2565c04fa3e3c16cfda` |
| island-city | 0,9 | `c98d204cc23fb9db05d079724272638b63dbc24901875c0c8815f5575dd8a7ab` |
| valley-50 | 39,1 | `e0626b7c844628596d7bf71929d5a96b14643f2af8a1c484f9579790308f43ea` |

Všech sedm otisků přesně souhlasí se zadáním. Uživatelské rozpracované
soubory v `ui/`, `src/cee/project_schema.py` a `tests/test_projects.py`
zůstávají mimo rozsah přepisu a mimo jeho commity.

## Fáze 0: prostředí a měřič

Nainstalována Numba 0.68.1 a llvmlite 0.50.0 do `.venv`; existují
binární balíčky CPython 3.11 pro macOS 12+ arm64 i Linux x86_64
(manylinux 2.27/2.28, včetně závislostí ověřeno stažením).
Na tomto macOS se ověřuje skutečné spuštění, linuxové spuštění zde
ověřit nelze. Závislost projektu dovoluje resolveru vybrat kompatibilní
verzi `numba>=0.61` pro daný Python, NumPy a platformu.

Měřič `scripts/v2_timing.py` používá stopky kolem stávajících metod,
zachovává návraty a výjimky a po skončení obnoví původní metody.
Časy jsou inkluzivní (tlaky a fonologizace jsou uvnitř přenosu);
instrumentace má vlastní režii. `--quick` používá stejných šest scénářů
jako skript otisků; `--years` výslovně zkracuje simulaci a mění otisk.
`--warmup` provede před měřením nezapočítaný běh.

Ověření: výchozí celá sada 587 prošlo / 2 chyby otevření lokálního
socketu kvůli omezení prostředí, 287,66 s. Opakovaná rychlá sada s
oprávněním otevřít lokální porty: 526 prošlo, 72 přeskočeno, 18,57 s.
Nové cílené testy registru, sloupců, měřiče a jader: 32 prošlo, 6,29 s.
Ruff i mypy čisté. Měřič testuje i zděděné metody, průchod výjimek a
obnovení metod po ukončení měření.

## Fáze 1: registr a sloupce za fasádou

`IdRegistry` pouze přidává ID, jejich číselné pozice nemění a poskytuje
explicitní lexikografické pořadí. `FormStore.bind` naváže číselné sloupce
tvaru, hranice a koncovky na registry světa a banku tvarů. Původní
`UnitForm` zůstává rychlou čtecí cache; všechny zápisy synchronizují
sloupce a stále zapisují deník. Sdílené copy-on-write vrstvy jsou chráněné
proti zápisu. Checkpoint má vlastní registry a pole, sdílí pouze dosavadní
append-only banku. Hromadné čtení tvarů i číselná slovní zásoba se používají
při aktivaci procesů; pořadí stále určuje řetězcové ID.

Všech sedm otisků zůstalo shodných. Orientační běh po změně: mřížka 3,6 s,
údolí 38,9 s; nejde o průkazné zrychlení. Do závěru tohoto běhu zasáhlo
ověření nových jader, proto jeho čas není podkladem pro srovnání výkonu.
Průkazné závěrečné porovnání musí běžet postupně proti výchozí kopii.

Celá sada po fázi 1 s povoleným lokálním socketem: **618 prošlo za
290,04 s**. Zahrnuje i do té doby připravené izolované testy jader;
produkční simulace v tomto běhu ještě používala původní aplikátor.

Výchozí kopie s měřičem: údolí 37,700 s, stejný otisk. Inovace
14,244 s, přenos 21,102 s (uvnitř artikulace 5,167 s, lexikální jasnost
3,331 s, fonologizace 2,689 s), pozorování 2,352 s. Údaje jsou inkluzivní.

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

## Fáze 2: funkčně shodný experiment, výkonnostní brána nesplněna

`Process.apply_tracked` na cache miss volá číselné jádro; původní
`Process._apply` zůstává čistou Python referencí. Výstupní mapa rysové
změny se doplňuje jen pro skutečně přítomné cílové hlásky. Banka drží
rostoucí matici a hromadně vyhodnocuje neznámé tvary ve stejném pořadí
`np.unique` jako dosud. Fonologizace dávkuje pouze způsobilý začátek fronty
jednoho procesu. Přepisy, verze, deník a zařazování do ostatních front
stále provádí postupně Python; referenční smyčka zůstává pro testy.

### Mikrobenchmark

`scripts/v2_kernel_bench.py`: 265 skutečných prototvarů z morfologického
scénáře, 1 000 řádků na dávku, medián 7 opakování po zahřátí. Kandidáti
mají skutečné zásahy; každé měření předem ověří shodu s Pythonem.

| Operace | Python (ms) | Skalární produkční adaptér (ms) | Samotné dávkové jádro (ms) | Dávka včetně převodů fasády (ms) |
|---|---:|---:|---:|---:|
| change | 1,244 | 3,787 | 0,128 | 0,861 |
| delete | 1,866 | 1,864 | 0,133 | 0,765 |
| insert_before | 1,334 | 1,829 | 0,141 | 0,730 |
| merge_next | 0,663 | 1,762 | 0,133 | 0,693 |
| replace | 1,860 | 1,922 | 0,136 | 0,864 |

Samotné dávkové jádro přináší asi 5–14×, ale po převodech n-tice → pole →
n-tice zbývá přibližně 1–2,4× (u merge_next mírné zpomalení). Poslední
sloupec nezahrnuje internování výsledků zpět do banky ani mutace stavu
simulace, tedy ani on není příslibem zrychlení `ProcessTable.results`.
Skalární adaptér má vlastní režii a může být až 3× pomalejší než Python.
První skalární dispatch v tomto procesu trval 101,935 ms, dávkový
3,363 ms; jde o první volání s již dostupnou diskovou cache, **nikoli
měření úplného překladu od nuly**. První volání nejsou v mediánech.

### Plné scénáře a rozhodnutí

První běh po integraci: všech sedm otisků přesně shodných, údolí 39,0 s,
mřížka 3,7 s. Závěrečné porovnání běželo v jednom sledu se stejným
interpretem a závislostmi: nejprve výchozí kopie commitu v `/tmp`, poté
aktuální větev; žádná souběžná simulace ani testy.

| Scénář | Výchozí commit (s) | Fáze 2 (s) | Cíl (s) |
|---|---:|---:|---:|
| grid-5x5 | 3,7 | 3,7 | ≤ 1 |
| valley-50 | 37,7 | 38,9 | ≤ 8 |

Otisky v obou bězích přesně odpovídají tabulce na začátku deníku.
Údolí je v tomto páru přibližně o 3 % pomalejší. **Výkonnostní cíl nebyl
splněn a praktický odhad 10–50× se nepotvrdil.** Podle výslovné brány ve
fázi 2 zadání se práce zastavuje před fází 3 a plán má přehodnotit
uživatel. Experiment zůstává na pracovní větvi pro kontrolu; do
`engine-v2` se neslučuje. Izolovaný rozpracovaný kód pro další jádra byl
odstraněn, aby větev neobsahovala nevyužitý budoucí kód.

Finální celá sada: **623 prošlo za 287,43 s (4 min 47 s)**, včetně
milníkových bran, checkpointů a všech nových testů. Výchozí sada měla
587 úspěšných testů a dvě chyby kvůli omezenému oprávnění k socketu;
finální běh má oprávnění k lokálním portům a žádné selhání. Časy celých
sad jsou s různým počtem testů, proto samy nedokazují zrychlení enginu.
Ruff i mypy čisté; `git diff --check` bez chyb. Nezávislá kontrola F1/F2
neodhalila konkrétní chybu správnosti. Automaticky porovnány čtyři úplné
sady otisků (fáze 1, fáze 2, závěrečný výchozí a aktuální běh): všechny
se přesně shodují se sedmi požadovanými hodnotami.
Finální rychlá sada: **551 prošlo, 72 vynecháno, 19,77 s**.

### Návrh dalšího rozhodnutí

Dosavadní fáze 1 jsou kompatibilní číselné sloupce vedle slovníkové
čtecí cache, nikoli dokončená hlavní číselná datová cesta. Horká smyčka
se proto stále vrací k řetězcům, `UnitForm` a n-ticím a připravuje mnoho
malých dávek. Překlad dalších izolovaných smyček tuto cenu sám neodstraní.

Doporučený další experiment, pokud uživatel schválí upravený plán:

1. Vybrat jednu skutečně dominantní operaci podle stopkového měřiče.
2. Vést její vstup, výstup i aktualizaci stavu pouze přes číselná pole,
   s rekonstrukcí fasády až na okraji a s referencí v Pythonu.
3. Měřit celou cestu včetně internování a aktualizací, ne pouze jádro.
   Pokračovat až při alespoň 2× zrychlení této celé operace a zlepšení
   celého údolí nad šum měření, při zachování všech otisků a checkpointů.

Alternativa: vrátit produkční integraci fáze 2 a ponechat ověřený měřič,
benchmarky a kompatibilní datový základ pro cílenější další práci.
Ani jedna varianta zatím neslibuje splnění 8 s bez dalšího měření.

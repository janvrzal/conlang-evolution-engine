# Zadání: tabulky světa jako sloupce (krok A4 přípravy na Rust)

Plán celé přípravy je v `docs/engine-v2/18-priprava-na-rust.md`, přečti ho.
Kroky A1 (horké cesty) a A2+A3 (registry, stav kódu v polích:
`cee.v2.registry`, `FormStore`, `language/columns.py`) jsou hotové a sloučené.
Navazuješ na ně a čísla bereš z `world.registry`.

## Cíl

Tabulky světa, které čtou horké cesty, mají být dostupné jako sloupce
indexované čísly z registru. Nad nimi budou pracovat Rust jádra (fáze B).
Rychlost se v tomto kroku nemusí zlepšit, nesmí se ale zhoršit o víc než
pár procent. **Výsledky musí zůstat bitově stejné.**

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-columns`
  na větvi `engine-v2-columns`. Jiné adresáře **neměň** (`CEE`,
  `CEE-dynamika`, `CEE-registry`, `CEE-rng`, `CEE-datamodel`, `CEE-m7a`).
  Současně ve `CEE-rng` běží jiný agent, který mění náhodu.
- Python spouštěj z kořene worktree:
  `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
- Stroj má 16 GB RAM a běží na něm i druhý agent. Pouštěj jen jeden těžký běh
  najednou (valley-50 nebo celá sada), žádný paralelní pytest.
- Commituj na `engine-v2-columns` po malých krocích. Zpráva anglicky, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.

## Co udělat

Pro tyto tabulky přidej sloupcové reprezentace. Slovníky objektů
(`world.morphemes`, `world.variants`, `world.variables`, `world.links`)
zůstávají zdrojem pravdy a veřejným API. Sloupce se udržují spolu s nimi:
přidávají se při uložení entity, u měnitelných údajů se verzují nebo
přepočítávají při změně.

1. **Morfémy** (`Morpheme` je frozen): číslo výchozího tvaru v `FormBank`,
   frekvence (`float64`), druh (`int8` kód), jazyk (číslo), třída slova,
   lexém (číslo morfému), koncovka, hranice. Číslo je číslo morfému
   z registru.
2. **Varianty** (`Variant` je frozen): proměnná (číslo), původ (změna
   jako kód, tick, skupina) a payload podle typu proměnné. Pro lexikální
   variantu je to číslo morfému, pro ostatní typy to, co horké cesty skutečně
   čtou; zbytek payloadu nech v objektu.
3. **Proměnné**: druh (kód), klíč (číslo pojmu u lexikálních), výchozí varianta.
4. **Vazby** (`world.links`, dnes slovník dvojic): řídká matice ve tvaru CSR
   (`indptr`, `indices`, síla a další číselná pole `Link`) podle čísel skupin.
   Obnovuje se při změně vazeb (události, státy, kontakt), například přes
   verzi nebo deník. Pozor: dnes se iteruje `world.links.items()` v pořadí
   vkládání nebo `sorted(...)`. Kde na pořadí záleží (sčítání plovoucích
   čísel, výběr, log), musí zůstat stejné. Číslo skupiny pořadí neurčuje.

Pak převeď na sloupce horká místa, kde to jde bez změny pořadí. Nejdřív změř
(cProfile valley-50, viz `zadani-datovy-model.md` v `CEE-datamodel` pro
postup), co z `world.morphemes[...]`, `world.variants[...].payload` a
`world.links` čtou horké cesty nejčastěji. Typicky to jsou `transmission.py`
(vazby), lexikální tlaky a indexy (frekvence, lexém, payload morfému),
`pools.py`/přenos a `word_bias` (lexém).

Postupuj po malých krocích, každý krok jeden commit s ověřením:
morfémy, varianty a proměnné, vazby, horká místa. Když narazíš na místo, kde
by převod změnil pořadí nebo výsledek, nech ho, jak je, a zapiš si ho.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda**: `scripts/v2_digests.py` po každém kroku vypíše přesně
  ```
  phonology    8c5c7a9213138b3eebef7b843fe335138dc254bbfea4345f0462af4e81a7258e
  morphology   2d2fb0297b2e87508def9f1f64f128a2a54f08edebbffbb2f0a47f7f579ed3f4
  syntax       d1f4c81011ef7826ff4eac45281cd8e9bdb0180077f15ddc49186b5e0fc8da02
  grid-5x5     a275faf2a41bcbdded1cf2979bedb062eb8a1156bd1213e97be1d4236bee6eb1
  shift        b1b7266fd342099cf16515d3a652f16e5bc51e035a9aa164fbd3b1954c72103e
  island-city  4c1c53554286862612aa9377fdc26831c88cd1c28da557d5218156262564cd2b
  valley-50    13556259eaec43e0ae265487f8c645e48a91b2fd0b867e2ba9faba77f7c4ca22
  ```
  `--quick` pouštěj po každém kroku, valley-50 aspoň po každém druhém kroku
  a na konci. Pořadí sčítání čísel s plovoucí čárkou se nesmí změnit:
  `np.sum` sčítá párově, smyčka postupně.
- **Determinismus**: žádné `hash()` ani `uuid4` a žádná iterace přes `set`,
  na jejímž pořadí záleží. Čísla z registru nesmí určovat pořadí.
- **Checkpointy**: kopie světa nesdílí měnitelná pole se zdrojem. Výjimkou jsou
  jen data, která pouze přibývají (`FormBank`). Pokračování z checkpointu dá
  stejný otisk (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu**: nesahej na konstanty, `Parameters`, brány
  (`tests/v2/*_gate.py`) ani chování. Existující testy neupravuj tak, aby
  prošly. Nové testy přidávat můžeš, například shodu sloupců s objekty po
  skutečném běhu, včetně vazeb po událostech, nebo izolaci kopií.
- **Paměť**: změř špičku valley-50 před a po (`/usr/bin/time -l`).
  Nesmí výrazně vzrůst.
- **Veřejné API** zůstává (`Simulation`, `World.form_of/unit_of/distribution`,
  `export`, `scenarios`).
- Komentáře a docstringy piš česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` musí být čistý.

## Ověřování

Po každém kroku:
```bash
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests/v2/test_v2_checkpoints.py tests/v2/test_v2_m1_gate.py tests/v2/test_v2_datamodel.py tests/v2/test_v2_registry.py tests/v2/test_v2_formstore.py tests/v2/test_v2_columns.py
/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2
```
Na konci pusť na pozadí celou sadu (asi 12 minut):
`PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests`.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- otisky, čas a špičku paměti valley-50 a grid-5x5 před a po,
- výsledek celé sady testů,
- místa, která zůstala na objektech, a proč,
- popis sloupců (jméno, typ, význam, kdy se obnovují), aby šlo navrhnout
  rozhraní pro Rust.

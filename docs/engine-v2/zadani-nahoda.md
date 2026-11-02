# Zadání: přenositelná náhoda v simulační smyčce (krok A6 přípravy na Rust)

Plán celé přípravy je v `docs/engine-v2/18-priprava-na-rust.md`, přečti ho.
Kroky A1 až A3 jsou hotové. Paralelně s tebou ve `CEE-columns` běží krok A4
(tabulky světa jako sloupce); na stejné soubory skoro nesahá.

## Cíl

Rust implementace musí dát stejné náhodné tahy jako Python. Hashovaný šum
(`rng.stable_int` na blake2b, `hash_normal` a `hash_poisson` na splitmix64)
se v Rustu zopakuje snadno. `numpy.random.Generator` (PCG64 se SeedSequence
a algoritmy numpy pro `choice`, `normal`, `poisson`, `integers`, `random`,
`uniform`) ale ne. Nahraď ho **ve všem, co běží během simulace**, vlastním
malým generátorem s přesně popsanými algoritmy.

Tohle je **vědomá změna otisků**. Výsledky se změní, statisticky ale mají
zůstat stejné. To ověří brány a srovnání na seedech.

## Rozsah

**Patří sem** (losy během kroku simulace):
- `simulation.py` `_apply_innovations` (výběr místa inovace),
- `changes/base.py`, `changes/lexicon.py`, `changes/morphology.py`,
  `changes/prosody.py`, `changes/sound.py`, `changes/syntax.py`: všechno, co
  dostane nebo vytvoří `rng`,
- `phonology.py` `_draw_bias` (sklon slova, počítá se líně během běhu),
- `rng.hash_poisson`: větev pro velké střední hodnoty (nad 30), která dnes
  staví lokální numpy generátor,
- cokoli dalšího, co během `Simulation.step` sahá na `generator()` nebo na
  `np.random`. Najdi to sám, třeba přes
  `grep -rnE "rng\.|generator\(|np\.random" src/cee/v2`, a vypiš to.

**Sem nepatří, nech na numpy** (tvorba světa zůstane v Pythonu, viz fáze B
a krok A8; uživatelé tak se stejným seedem dostanou stejný protojazyk):
- `language/protoforms.py` (tvary a frekvence protojazyka),
- `background.py` (generátor pozadí dějin),
- `variation.py` (rozdání souběžné variability při tvorbě světa).

Pokud se něco z toho volá i během běhu (například nově vzniklé skupiny nebo
jazyky v událostech), napiš to do zprávy a nesahej na to.

## Co udělat

1. V `src/cee/v2/rng.py` napiš přenositelný generátor (třeba `Stream`),
   určený jen seedem a stabilními ID jako dnešní `generator(seed, *parts)`.
   Zachovej princip modulu: tah závisí jen na seedu a ID toho, čeho se týká.
   - Jádro je čítač a splitmix64 (nebo jiná jednoduchá 64bitová funkce bez
     stavu mimo čítač). Klíč odvoď z `stable_int`.
   - `random()`: 53 bitů → `[0, 1)`, stejně jako `hash_normal`.
   - `integers(n)`: bez zkreslení (Lemirova metoda nebo odmítání), přesně popsaná.
   - `choice(n, p)`: kumulativní součet **postupně v Pythonu** v pořadí
     indexů (ne `np.cumsum`, který se může lišit) a vyhledání prvního indexu
     s kumulativní hodnotou nad `u * total`. Ošetři nulové váhy a zaokrouhlení
     na konci.
   - `normal(mean, sd)`: Box–Muller přes `math.log`, `math.sqrt`, `math.cos`
     (libm; tytéž funkce má Rust `std`). Nepoužívej numpy.
   - `poisson(lam)`, pokud ho smyčka potřebuje: algoritmus přesně popsaný,
     třeba inverze pro malé λ a pro velké jiná přesně popsaná metoda (PTRS
     nebo normální aproximace se zaokrouhlením; rozhodni a zdůvodni).
   - `uniform(a, b)` a další, co místa použití skutečně volají.
   Do docstringu napiš algoritmy tak, aby je šlo v Rustu přepsat bit po bitu.
2. Přidej test `tests/v2/test_v2_stream.py`:
   - pevné referenční hodnoty, tedy prvních pár tahů pro daný seed jako
     čísla v testu; budou sloužit i jako zlatá data pro Rust,
   - statistika rozdělení (průměr, rozptyl, χ² pro `choice`),
   - nezávislost na pořadí volání různých proudů.
3. Nahraď numpy generátor na místech z rozsahu. **Každé místo nahraď zvlášť,
   nebo po souborech, a ověř.** Pořadí a počet tahů na místě nech stejné
   jako dnes, kde to jde. Změní se jen zdroj náhody.
4. Aktualizuj referenční otisky ve `scripts/v2_digests.py` a všude, kde jsou
   zapsané jako reference. Do zprávy uveď staré i nové.

## Ověření změny (nutné, změna otisků se bez něj nepřijme)

- **Celá sada testů** včetně všech bran (`tests/v2/*_gate.py`) musí projít.
  Brány neupravuj a konstanty, seedy ani `Parameters` neladi tak, aby prošly.
  Když brána selže, zastav se a popiš, kde a o kolik.
- **Audit stochastických bran**: `scripts/v2_gate_rates.py` (podívej se na
  jeho volby). Pusť ho před změnou a po ní na stejných seedech (výchozí
  101..120) a porovnej podíly úspěchu. Je to dlouhé, pouštěj to na pozadí
  a s nejvýš 2 procesy, protože na stroji běží i jiný agent.
- **Statistické srovnání** klíčových metrik před a po na aspoň 8 seedech.
  Použij `scripts/v2_calibrate_retention.py` (retence izolovaného jazyka
  a kontaktu) a `scripts/v2_innovation_stats.py`. Uveď průměry, rozptyly
  a jestli je rozdíl v šumu.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-rng` na větvi
  `engine-v2-rng`. Jiné adresáře **neměň**.
- Python spouštěj z kořene worktree:
  `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
- Stroj má 16 GB RAM a běží na něm i druhý agent. Pouštěj jen jeden těžký běh
  najednou a nejvýš 2 procesy v kalibračních skriptech (`--workers 2`).
  Žádný paralelní pytest. Skripty s `multiprocessing` (spawn) vždy ulož do
  souboru, nikdy je nepouštěj přes `python - <<EOF`.
- Commituj na `engine-v2-rng` po malých krocích. Zpráva anglicky, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.

## Invarianty

- **Determinismus**: žádné `hash()` ani `uuid4` a žádná iterace přes `set`,
  na jejímž pořadí záleží. Stejný seed dá stejný otisk, ověř to dvěma běhy
  a také s jiným `PYTHONHASHSEED`.
- **Checkpointy** fungují a pokračování dá stejný otisk
  (`tests/v2/test_v2_checkpoints.py`).
- Tvorba světa (protojazyk, pozadí dějin, variabilita) dá **stejný výsledek
  jako dřív**. Ověř to porovnáním světa po `build()` před simulací:
  tvary morfémů, frekvence, události a distribuce.
- Model, konstanty, `Parameters` ani brány neměň.
- Rychlost se nesmí výrazně zhoršit: změř valley-50 před a po. Generátor
  v čistém Pythonu může být pomalejší než numpy. Kde je tahů hodně
  (`choice` ve smyčce), změř to a případně tahy dělej vektorově se stejným
  výsledkem.
- Komentáře a docstringy piš česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` musí být čistý.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- seznam nahrazených míst a míst, která zůstala na numpy, a proč,
- popis algoritmů generátoru (pro Rust),
- staré a nové otisky,
- celou sadu testů, audit bran (tabulka před a po) a statistické srovnání,
- čas valley-50 před a po.

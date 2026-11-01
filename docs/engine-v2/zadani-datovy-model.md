# Zadání: číselný datový model horkých cest (krok 1 před Rust jádry)

## Cíl

Zrychlit engine v2 bez změny výsledků tím, že horké cesty přestanou
procházet slovníky s textovými klíči. Je to příprava na Rust jádra (krok 2):
ta budou pracovat nad poli, která tady vzniknou. **Výsledky musí zůstat
bitově stejné.**

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-datamodel`,
  větev `engine-v2-datamodel`. Jiné adresáře (`/Users/janvrzal/Documents/CEE`,
  `CEE-dynamika`, `CEE-m7a`) **neměň**.
- Python: `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`
  (spouštěj z kořene worktree). Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
- Stroj má 16 GB RAM. Nespouštěj víc než jeden těžký běh najednou (celá
  sada testů nebo valley-50 bere 1,5–2 GB), žádné paralelní pytest.
- Commity na větev `engine-v2-datamodel` jsou v pořádku, po malých krocích,
  anglická zpráva, na konci řádek
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Soubory přidávej
  jménem (`git add cesta`), nikdy `git add -A`. Nic nepushuj, nemerguj, neměň
  jiné větve, nepoužívej `git stash`.

## Kde je čas (změřeno 2026-11-01, údolí `village_grid(10, 5, seed=1, syntax=True, semantics=True)`, 1 000 let, cProfile)

| volání | počet | čas (vlastní + vnořený) |
|---|---|---|
| `World.usage_frequency` (`world.py:249`) | 981 510 | 2,2 s |
| `World.unit_of` / `form_of` (`world.py:289`, `:302`), `FormStore.get` | 1,7 mil. | 2,0 s |
| `language/lexical_index.py` `score` / `scores_many` | 2,9 mil. | 2,7 s |
| `language/assessment_index.py` `sync` | 1 872 | 2,9 s |
| `changes/sound.py` `_get_support_index` → `sync` | 67 747 | 1,9 s |
| `language/semantic_index.py` `sync` | 22 125 | 1,2 s |
| `morphology.assess` / `form_assessment_index.assess` | 129 038 | 2,3 s |
| `phonology._queue` / `activate` | 229 016 | 1,7 s |
| `rng.stable_int` | 200 518 | 0,5 s |

Celkem 25 s za 1 000 let. Stopkami (`scripts/v2_timing.py --scenario valley-50`,
2 000 let, 41 s): přenos 29 s (fonologizace 8 s, tlak Articulation 5,5 s,
LexicalClarity 3,8 s, Conservation 2,2 s), inovace 10 s.

## Co udělat

Postupuj po krocích, každý krok = jeden commit, po každém ověř otisky:

1. **Nejdřív změř sám** (`scripts/v2_timing.py --scenario valley-50` a cProfile
   jako výše), ať máš výchozí čísla na tomto stroji.
2. Pak postupně, podle toho, co měření ukáže jako nejdražší:
   - **Četnost užití a tvary slov**: `usage_frequency`, `unit_of`, `form_of`
     volané milionkrát. Číselný registr morfémů (řetězec → index) a pro každý
     kód pole/čísla tvarů (do `FormBank`), případně verzované cache
     (`PhonologyState.version`, `lexicon_version`). Veřejné metody zůstanou
     jako fasáda.
   - **Lexikální jasnost**: `lexical_index.score` voláno po jednom slovu;
     převeď na hromadné (numpy) hodnocení celé skupiny nebo bloku.
   - **Synchronizace indexů** (`assessment_index.sync`, `sound.py` podpora,
     `semantic_index.sync`): zjisti, proč jsou drahé, a omez práci na skutečné
     změny.
3. Skonči, až budeš mít aspoň 4 kroky hotové, nebo až valley-50 klesne pod
   polovinu výchozího času, nebo když narazíš na problém, který vyžaduje
   změnu architektury (pak se zastav a popiš ho).

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda.** `scripts/v2_digests.py` musí po každém kroku vypsat přesně:
  ```
  phonology    8c5c7a9213138b3eebef7b843fe335138dc254bbfea4345f0462af4e81a7258e
  morphology   2d2fb0297b2e87508def9f1f64f128a2a54f08edebbffbb2f0a47f7f579ed3f4
  syntax       d1f4c81011ef7826ff4eac45281cd8e9bdb0180077f15ddc49186b5e0fc8da02
  grid-5x5     a275faf2a41bcbdded1cf2979bedb062eb8a1156bd1213e97be1d4236bee6eb1
  shift        b1b7266fd342099cf16515d3a652f16e5bc51e035a9aa164fbd3b1954c72103e
  island-city  4c1c53554286862612aa9377fdc26831c88cd1c28da557d5218156262564cd2b
  valley-50    13556259eaec43e0ae265487f8c645e48a91b2fd0b867e2ba9faba77f7c4ca22
  ```
  (`--quick` vynechá valley-50; ten pusť aspoň po každém druhém kroku a na konci.)
  Pozor na pořadí sčítání čísel s plovoucí čárkou: `np.sum` sčítá párově, smyčka
  postupně. Kde dnes kód sčítá postupně nebo v určitém pořadí, zachovej ho.
- **Determinismus**: žádné `hash()`, `uuid4`, iterace přes `set`, na jejímž pořadí
  záleží. Číselné indexy nesmí určovat pořadí ničeho, co ovlivní výsledek nebo
  log; tam, kde dnes kód řadí podle řetězcových ID, musí řadit dál stejně.
- **Checkpointy**: `Simulation.checkpoint/resume/branch` dělá hlubokou kopii;
  kopie nesmí sdílet měnitelná pole se zdrojem (výjimka: data jen přibývající,
  jako `FormBank`). Pokračování z checkpointu dá stejný otisk
  (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu**: nesahej na konstanty, `Parameters`, brány
  (`tests/v2/*_gate.py`) ani na chování. Testy se nesmí upravovat tak, aby
  prošly; nové testy přidávat můžeš (např. shoda nového hromadného výpočtu
  s původním na skutečných datech).
- **Veřejné API** zůstává: `Simulation`, `World.form_of/unit_of/distribution`,
  `cee.v2.export`, `cee.v2.scenarios`.
- Komentáře a docstringy česky ve stylu okolního kódu, identifikátory anglicky.
  `ruff` čistý.

## Ověřování

Po každém kroku:
```bash
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests/v2/test_v2_checkpoints.py tests/v2/test_v2_m1_gate.py
/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2
```
Na konci celá sada (asi 12 minut, běž ji na pozadí a počkej):
`PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests`.

## Výstup (závěrečná zpráva)

- seznam commitů a co každý dělá,
- otisky a čas valley-50 a grid-5x5 před a po (stejný stroj, nevytížený),
- výsledek celé sady testů (počet prošlých a neprošlých, s výpisem chyb),
- co zůstalo drahé a co doporučuješ přesunout do Rust jader (krok 2),
- cokoli, co nešlo udělat bez porušení invariantu.

Nic nepřikrášluj: pokud se otisk změnil nebo test padá, napiš to.

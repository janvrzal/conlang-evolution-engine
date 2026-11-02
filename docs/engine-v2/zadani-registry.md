# Zadání: číselné registry a stav kódu v polích (kroky A2 a A3 přípravy na Rust)

Plán celé přípravy je v `docs/engine-v2/18-priprava-na-rust.md`; přečti ho.
Krok A1 (horké cesty, `zadani-datovy-model.md`) je hotový a sloučený.

## Cíl

Připravit datový model tak, aby nad ním mohla pracovat Rust jádra:
entity mají číselná ID a stav každého kódu je v polích. Rychlost se
v tomto kroku nemusí zlepšit (nesmí se ale zhoršit o víc než pár procent),
**výsledky musí zůstat bitově stejné**.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-registry`,
  větev `engine-v2-registry`. Jiné adresáře (`CEE`, `CEE-dynamika`,
  `CEE-datamodel`, `CEE-m7a`) **neměň**.
- Python: `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`
  (z kořene worktree). Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
- 16 GB RAM: jeden těžký běh najednou, žádný paralelní pytest.
- Commity na `engine-v2-registry` po malých krocích, anglická zpráva, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Soubory přidávej
  jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.

## Co udělat

**A2: registry.** Nový modul (např. `src/cee/v2/registry.py`) s registrem
řetězec → číslo a zpět pro morfémy, varianty, proměnné, pojmy, skupiny a
procesy, uložený ve `World`. Čísla se přidělují v pořadí vzniku (to je
deterministické). Registr je jen přidávací. Pravidla:
- čísla **nesmí určovat pořadí** ničeho, co ovlivní výsledek nebo log: kde dnes
  kód řadí podle řetězcových ID (`sorted(...)`), musí řadit dál stejně;
- registr patří světu a kopíruje se s ním (checkpoint je hluboká kopie; dvě
  větve běhu mohou vytvořit různé morfémy se stejným číslem, a to je v pořádku,
  jen se nesmí sdílet);
- textová ID zůstávají v historii, exportu a veřejném API.

**A3: stav kódu v polích** za stávajícími fasádami:
- `FormStore` (tvary morfémů kódu; dnes vrstvy slovníků s copy-on-write
  `branch`): pole podle čísla morfému s číslem tvaru do `FormBank` (−1 =
  výchozí tvar), hranicí koncovky a koncovkou. Zachovej sémantiku `branch`,
  deníku (`token`, `log`) a toho, že větev nesdílí měnitelná pole se zdrojem.
- `PhonologyState`: slovní zásoba (morfém → počet užití), převládající kořen
  pojmu (pojem → morfém) a fronty fonologizace v polích nebo číselných
  strukturách.
- `World.unit_of`, `form_of`, `FormStore.get/set/branch/log` a metody
  `PhonologyState` zůstanou jako fasáda (asi 40 míst volání se nemusí měnit
  najednou). Horká místa, která A1 našel (`phonology._queue`, `_needed`,
  `enter_vocabulary`, `lexical_index`, indexy klíčované n-ticemi tvarů),
  převeď na čísla, kde to jde bez změny pořadí.

Postupuj po malých krocích (registr, pak `FormStore`, pak `PhonologyState`,
pak horká místa), každý krok jeden commit s ověřením. Když narazíš na místo,
kde by převod změnil pořadí nebo výsledek, nech ho na řetězcích a zapiš si ho.

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
  (`--quick` po každém kroku, valley-50 aspoň po každém druhém a na konci.)
- **Determinismus**: žádné `hash()`, `uuid4`, iterace přes `set`, na jejímž pořadí záleží.
- **Checkpointy** fungují a pokračování dá stejný otisk (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu**, konstant, `Parameters`, bran (`tests/v2/*_gate.py`);
  testy neupravuj, aby prošly. Nové testy přidávat můžeš (registr, shoda polí
  s dřívějšími slovníky, izolace větví `FormStore`).
- **Paměť**: změř špičku paměti valley-50 před a po (např. `/usr/bin/time -l`);
  nesmí výrazně vzrůst.
- Komentáře a docstringy česky ve stylu okolního kódu, identifikátory anglicky; `ruff` čistý.

## Ověřování

Po každém kroku:
```bash
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests/v2/test_v2_checkpoints.py tests/v2/test_v2_m1_gate.py tests/v2/test_v2_datamodel.py
/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2
```
Na konci celá sada (asi 12 minut, na pozadí):
`PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests`.

## Výstup (závěrečná zpráva, česky, nic nepřikrášluj)

- commity a co každý dělá,
- otisky; čas a špička paměti valley-50 a grid-5x5 před a po,
- výsledek celé sady testů,
- místa, která zůstala na řetězcích, a proč,
- jak teď vypadá stav kódu (pole, jejich typy a význam), aby šlo navrhnout
  rozhraní pro Rust.

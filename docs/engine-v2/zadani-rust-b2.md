# Zadání: fonologizace a aplikace zvukových změn v Rustu (fáze B, krok 2)

Přečti si:
- plán `docs/engine-v2/18-priprava-na-rust.md`, hlavně řádek B1 a oddíl
  Fáze B;
- zadání a výsledek kroku B1 (`docs/engine-v2/zadani-rust-b1.md`). Krok B1
  je hotový: crate `rust/cee_core` (PyO3, maturin), `cee.v2.native`
  s fallbackem, banka tvarů a tabulky procesů v Rustu, zlatá data.

## Proč

Rust v B1 počítá sám asi 1 s, ale valley-50 zrychlil jen o 5 %. Zbývající
cena je Python obal kolem asi 4 milionů jednotlivých volání `may_apply`
(z `phonology.restructure`), asi 1 milionu `result` a `process_table`.
Fonologizace (`src/cee/v2/phonology.py`: `restructure`, `_queue`,
`requeue`, `activate`, `enter_vocabulary`, `_needed`, `_leads`,
`word_bias`) volá banku po jednom tvaru. Cílem je, aby jeden krok
fonologizace jednoho kódu proběhl v Rustu najednou.

## Co udělat

1. **Změř** profil valley-50 a grid-5x5 (cProfile, s Rustem z B1) a zapiš,
   kolik času jde do fonologizace a kolik do hranice Python–Rust.
2. **Dávkové rozhraní** v crate pro krok fonologizace kódu:
   - vstupy jsou pole, která už existují: `FormStore` (`_form`,
     `_boundary`, `_exponent` podle čísla morfému), `PhonologyState`
     (`language/columns.py`: `ProcessQueue` `needed`/`morphemes`,
     `queued`/`restructured` bitové sady, slovní zásoba, `dominant`),
     tabulky procesů banky a podíly změněných tvarů procesů;
   - výstupy jsou přepsané tvary, změny front a deník pro historii
     a indexy (`FormStore.log`, `state.version`, záznamy `history`)
     **ve stejném pořadí jako dnes**.

   Navrhni to sám, ale po dávkách. Pořadí zpracování procesů, front
   i přepisů musí zůstat přesně stejné jako v Pythonu (řazení fronty podle
   (potřebný logit, jméno morfému); pro jména použij `Numbering.ranks()`
   z `cee.v2.registry`).
3. **Logity a sklony** (`_logit`, `_needed`, `_lead`, `word_bias`) používají
   `math.log`/`exp`. Rust `f64::ln`/`exp` volá na macOS tutéž systémovou
   libm, takže by výsledky měly být stejné, ale ověř to testem na skutečných
   datech. Kdyby se lišily v posledním bitu, nech tyto výpočty v Pythonu
   a předávej Rustu hotová pole. Sklony slov (`word_biases`, losované
   `Stream`) nech v Pythonu, Rust dostane hotové sloupce.
4. **Napojení v Pythonu** za stávající fasádou (`phonology.restructure`
   atd.), s fallbackem na Python přes `cee.v2.native` (`CEE_NATIVE=0`,
   chybějící rozšíření, jiná verze rozhraní). Verzi rozhraní zvyš.
5. **Zlatá data a testy**: záznam vstupů a výstupů kroku fonologizace ze
   skutečných běhů (do 1 MB v `tests/`) a test Rust proti Pythonu, jako
   v B1.
6. **Ověření** s Rustem i bez něj, viz níže.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-rust-b2`
  na větvi `engine-v2-rust-b2`. Jiné adresáře **neměň**. V `CEE-dynamika`
  současně pracuje jiný agent na slovníku (tlaky, změny slov, variabilita).
- Rozšíření sestavuj jako v B1: `maturin build --release`. Instaluj ho
  `pip install --no-deps --target rust/cee_core/target/py <wheel>` a používej
  `PYTHONPATH=src:.:rust/cee_core/target/py`. **Do sdíleného venv nic
  neinstaluj** (`maturin develop` je zakázané). Žádné další komponenty
  toolchainu ani balíčky neinstaluj; `rustfmt` a `clippy` už jsou.
- Python spouštěj z kořene worktree:
  `/Users/janvrzal/Documents/CEE/.venv/bin/python`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
  Rust: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test`.
- Stroj má 16 GB RAM a souběžně na něm běží jiné těžké běhy. Pouštěj jen
  jeden těžký běh najednou, `CARGO_BUILD_JOBS=4`, žádný paralelní pytest.
- Commituj na `engine-v2-rust-b2` po malých krocích. Zpráva anglicky, na
  konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda**: `scripts/v2_digests.py` vypíše s Rustem (všech 7)
  i s `CEE_NATIVE=0` (`--quick`) přesně:
  ```
  phonology    37e949768bf1f5fe2e0bdb106d39cbf199b842c24750ced943ca4c4ba9f7d2f4
  morphology   1f082a14909f724f98a7fe6aa39c4d8fff092f32ac126b3d217d94eb824e423c
  syntax       c270c0b059eb21af1bb0fa68a17f6efd69eb895040cfafdb11c5d4e04a7ef531
  grid-5x5     f00c56442b3e798fe844df0678d7637de59906480528ce0acb416056efd2dc1f
  shift        45300517345cc5ff3e22a1ff39bf1b1e48b0365662a8e33ada1a95088b06872c
  island-city  d8801215f07f7ad45b657d15ca4c1def5d4678706c1af0603e4ca4eb08ffd2a7
  valley-50    a035aa06625e0293f67f487f69ba174367ae6c9e7f478402b2e5e118c01a8f7b
  ```
- **Fallback**: bez rozšíření projde celá sada jako dnes.
- **Determinismus**: v cestě, na které záleží pořadí, žádné hashovací
  struktury s náhodnou solí a žádná vlákna měnící pořadí.
- **Checkpointy**: kopie a pickle světa fungují
  (`tests/v2/test_v2_checkpoints.py`). Stav v Rustu se nesmí sdílet mezi
  kopiemi; výjimkou je jen banka tvarů, ta jen přibývá.
- **Žádné změny modelu**, konstant, `Parameters` ani bran. Existující testy
  neupravuj tak, aby prošly.
- Komentáře a docstringy piš česky ve stylu okolního kódu, i v Rustu.
  `ruff` i `clippy` musí být čisté.

## Ověřování

```bash
cd rust/cee_core && CARGO_BUILD_JOBS=4 /Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python && cd ../..
PYTHONPATH=src:.:rust/cee_core/target/py /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py
CEE_NATIVE=0 PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
PYTHONPATH=src:.:rust/cee_core/target/py /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests/v2/test_v2_checkpoints.py tests/v2/test_v2_datamodel.py tests/v2/test_v2_native_bank.py tests/v2/test_v2_m1_gate.py
```
Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí:
`... -m pytest -q -p no:cacheprovider tests`.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- profil před a po a čas valley-50 a grid-5x5 s Rustem a bez něj (střídavě,
  s poznámkou o vytížení stroje),
- otisky v obou režimech a výsledky obou celých sad,
- rozhraní a co z něj převezmou další moduly,
- co zůstalo v Pythonu a proč,
- co nešlo; pokud ti cokoli systém zamítl, napiš to a neobcházej to.

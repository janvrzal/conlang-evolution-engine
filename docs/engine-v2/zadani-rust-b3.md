# Zadání: hodnocení a tlaky v Rustu (fáze B, krok 3, s tlakovou částí A5)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md` (fáze A a B, řádky B1 a B2);
- zadání B1 a B2 (`docs/engine-v2/zadani-rust-b1.md`, `zadani-rust-b2.md`),
  protože vzor rozhraní je hotový: `cee.v2.native`, `NativeBank`, verze
  rozhraní, fallback, smyčka `needs`, zlatá data.

## Proč

Po B1 a B2 trvá valley-50 s Rustem asi 30 s. Fonologizace je už jen asi
osmina času. Podle profilu z A1 jde nejvíc času do hodnocení: podpora
zvukových změn asi 17 %, artikulace asi 14 %, lexikální jasnost asi 8 %
a tlaky. Tohle je největší zbývající blok, který se modelem nemění.

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/assessment.py`;
- `src/cee/v2/language/assessment_index.py`, `form_assessment_index.py`,
  `lexical_index.py`, `index.py`;
- `src/cee/v2/changes/sound.py` (index podpory zvukových změn);
- všechny `src/cee/v2/pressures/*.py`;
- `rust/cee_core/`, `src/cee/v2/native.py`, `src/cee/v2/language/bank.py`
  (jen pokud je to nutné).

**Nesahej na:**
- `transmission.py`, `pools.py`, `contact.py`, `institutions.py`,
  `events.py`, `background.py`, `polity.py` (pracuje na nich agent na
  domény kontaktu);
- `simulation.py`, `changes/base.py`, `changes/morphology.py`,
  `changes/syntax.py`, `changes/prosody.py`, `morphology.py`, `syntax.py`,
  `prosody.py`, `language/morphology*.py`, `language/semantic_index.py`
  (pracuje na nich agent na A5).

Tlaky volá přenos přes `PressureBatch`. To rozhraní zachovej, změna je
uvnitř tlaků a hodnocení.

## Co udělat

1. **Změř** profil valley-50 a grid-5x5 s Rustem z B2 (cProfile,
   `PYTHONPATH=src:.:rust/cee_core/target/py`). Zapiš, kolik času jde do
   hodnocení, indexů a jednotlivých tlaků.
2. **Tlaky jako funkce nad poli** (tlaková část A5): každý tlak počítá
   z polí bloku (četnosti, sloty variant jako čísla, sloupce světa), ne
   z objektů. Třídy zůstanou tenkou fasádou.
3. **Rust**:
   - nejdražší výpočty hodnocení po dávkách: podpora zvukových změn,
     artikulace a funkční zátěž, lexikální jasnost, synchronizace indexů;
   - vzor jako v B1 a B2: Python je zdroj pravdy, Rust počítá dávky, při
     chybějících datech vrátí `needs`;
   - zvyš verzi rozhraní;
   - pozor na pořadí sčítání plovoucích čísel (`np.sum` sčítá párově,
     smyčka postupně; zachovej, co dělá Python);
   - transcendentní funkce (`exp`, `log`) nech počítat v Pythonu jako
     v B2, nebo dokaž testem, že Rust dává bit po bitu totéž.
4. **Zlatá data** (A7 pro tyto funkce): záznam vstupů a výstupů hodnocení
   a tlaků ze skutečných běhů (do 1 MB v `tests/`) a test Rust proti
   Pythonu.
5. **Ověření** s Rustem i bez něj (viz níže) a čas před a po.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-rust-b3`
  na větvi `engine-v2-rust-b3`. Jiné adresáře **neměň**.
- Rozšíření sestavuj `maturin build --release` a instaluj
  `pip install --no-deps --target rust/cee_core/target/py <wheel>`, pak
  používej `PYTHONPATH=src:.:rust/cee_core/target/py`. **Do sdíleného venv
  nic neinstaluj**, žádné komponenty toolchainu ani balíčky.
- Python: `/Users/janvrzal/Documents/CEE/.venv/bin/python` z kořene
  worktree. Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
  Rust: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test`.
- Stroj má 16 GB RAM a souběžně na něm pracují dva další agenti. Pouštěj
  jeden těžký běh najednou, nejvýš 2 procesy, `CARGO_BUILD_JOBS=3`, žádný
  paralelní pytest. Pomocné soubory ukládej do worktree, ne do scratchpadu,
  protože ten stroj průběžně čistí.
- Commituj na `engine-v2-rust-b3` po malých krocích. Zpráva anglicky, na
  konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda**: `scripts/v2_digests.py` vypíše s Rustem (všech 7)
  i s `CEE_NATIVE=0` (`--quick`) přesně:
  ```
  phonology    3990a6381c1a91b4c4ffddf42731d42915325960dc128c834b6eec74ba2f97a3
  morphology   710009d641a04a0b1f007d29fa18a3d273780e322667b826bb3d9a7e7165d43b
  syntax       a55966f235d171ee1b772c2196b7bb2c2a742172a064d2b293c17a4df7553482
  grid-5x5     cc4ef6e136b0eaa543c08fc4c7e424ca53d781bcdd0e905858d3cb32de0bcc61
  shift        f74dad095fcbaa129349dddd4ed74da4c3d1ced888dfe2ed81bc692212612559
  island-city  a3efb455923bf5a6489b55e68ca877ed4e5ab2b422076a0ed4d7a569d6313e47
  valley-50    79b033067955967931819647325eb42d83f4aa21e826587be4f2d49f13373e88
  ```
  Shodný musí zůstat i připnutý otisk v `tests/v2/test_v2_vocabulary.py`.
- **Fallback**: bez rozšíření projde celá sada jako dnes.
- **Determinismus**: v cestě, na které záleží pořadí, žádné hashovací
  struktury s náhodnou solí a žádná vlákna měnící pořadí.
- **Checkpointy a pickle** fungují (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu**, konstant, `Parameters` ani bran. Existující testy
  neupravuj tak, aby prošly.
- Komentáře a docstringy piš česky ve stylu okolního kódu, i v Rustu.
  `ruff` i `clippy` musí být čisté.

## Ověřování

```bash
cd rust/cee_core && CARGO_BUILD_JOBS=3 /Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python && cd ../..
PYTHONPATH=src:.:rust/cee_core/target/py /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py
CEE_NATIVE=0 PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
```
Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- profil před a po a čas valley-50 a grid-5x5 s Rustem a bez něj
  (s poznámkou o vytížení stroje),
- otisky v obou režimech a výsledky obou celých sad,
- rozhraní a co z něj převezmou další moduly,
- co zůstalo v Pythonu a proč,
- co nešlo a proč.

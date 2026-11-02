# Zadání: první modul v Rustu (fáze B, krok 1: banka tvarů a tabulky procesů)

Přečti si celý plán v `docs/engine-v2/18-priprava-na-rust.md`. Kroky A1 až
A4 a A6 jsou hotové:
- stav kódu je v polích podle čísel z registru (`cee.v2.registry`,
  `FormStore`, `language/columns.py`);
- tabulky světa jsou sloupce (`cee.v2.tables`);
- náhoda během běhu jde přes přenositelný `rng.Stream`.

Fáze B se přepisuje modul po modulu za stávajícími rozhraními (PyO3,
maturin). Začínáme spodní vrstvou, na které nic dalšího nestojí.

## Cíl

V Rustu napiš jádro:
- **banky tvarů** (`src/cee/v2/language/bank.py`: `FormBank`, ploché pole
  hlásek, bitové předfiltry, `ProcessTable`);
- **aplikace zvukového procesu na tvar** (`src/cee/v2/language/processes.py`
  a co z `segments.py` k tomu potřebuje: rysy hlásek, prostředí, přízvuk).

Python bude jádro volat přes stávající fasádu. Když rozšíření není
sestavené, nebo je nastavené `CEE_NATIVE=0`, poběží stávající Python beze
změny. **Výsledky musí být bitově stejné s Rustem i bez něj.**

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-rust` na větvi
  `engine-v2-rust`. Jiné adresáře **neměň**. V `CEE-dynamika` současně
  pracuje jiný agent na datech pojmů.
- Rust je nainstalovaný (`~/.cargo/bin/cargo`, rustc 1.99). Do venv
  `/Users/janvrzal/Documents/CEE/.venv` si nainstaluj `maturin`
  (`/Users/janvrzal/Documents/CEE/.venv/bin/python -m pip install maturin`).
  Nic jiného do venv neinstaluj; PyO3 je závislost crate, ne Pythonu.
- Python spouštěj z kořene worktree:
  `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2`.
  Pro Rust: `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test`.
- Stroj má 16 GB RAM. Pouštěj jen jeden těžký běh najednou, žádný paralelní
  pytest. Release build sestavuj s nejvýš 4 vlákny (`CARGO_BUILD_JOBS=4`).
- Commituj na `engine-v2-rust` po malých krocích. Zpráva anglicky, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Soubory
  přidávej jménem. `rust/**/target/` přidej do `.gitignore`. Nic nepushuj,
  nemerguj, nepoužívej `git stash`.

## Co udělat

1. **Změř**, kolik času jde do banky tvarů a tabulek procesů:
   - cProfile na `scripts/v2_timing.py --scenario valley-50` a grid-5x5;
   - podíl `FormBank`, `ProcessTable` a aplikace procesů na celkovém čase;
   - z toho odhad horní meze zrychlení.

   Výsledek napiš poctivě, i kdyby byl malý. Je to první modul a jde hlavně
   o to postavit cestu Python ↔ Rust, na které budou stát další moduly.
2. **Crate** `rust/cee_core` (PyO3 + maturin, modul `cee._native` nebo
   podobný, vlastní `pyproject.toml` v crate):
   - Rozhraní dělej po dávkách, ne po jednom tvaru. Hranice Python–Rust má
     režii a A1 kvůli tomu převedl horké cesty na hromadné volání
     (`ProcessTable.results`, `ids_of`, předfiltry). Data předávej jako
     numpy pole nebo pole čísel, ne jako n-tice.
   - Datový model v Rustu odpovídá polím z A1–A3: plochá `Vec<i64>` hlásek
     se začátky a délkami, čísla tvarů, tabulky výsledků procesů
     (−1 = beze změny, −2 = nezkoumáno), bitové sady.
3. **Napojení v Pythonu**: modul (např. `cee.v2.native`) zkusí rozšíření
   načíst. `FormBank` a `ProcessTable` delegují dávkové výpočty do Rustu,
   když je k dispozici, jinak počítají jako dnes. Veřejné rozhraní tříd
   se nemění.
4. **Zlatá data** (část kroku A7 pro tento modul):
   - skript v `scripts/`, který při skutečných bězích (grid-5x5, shift,
     valley-50 zkráceně) zaznamená vstupy a výstupy aplikace procesů:
     tvar, proces, pravidlo přízvuku, výsledek;
   - malý výřez uložený do `tests/` (do 1 MB);
   - test, který ověří Rust proti Pythonu na zlatých datech i na náhodných
     tvarech.
5. **Ověření**: otisky a celá sada testů s Rustem i bez něj, čas před a po.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda**: `scripts/v2_digests.py` vypíše s rozšířením i bez něj
  (`CEE_NATIVE=0`) přesně:
  ```
  phonology    3ffcb70c000f5624e98a927ee24163bff04a28f8dae527151cb2622ca804b8f5
  morphology   7ffa92b662336c5faf8741f12176cc274b90cc98bb39a75014904e87e97e6b74
  syntax       108cfeeb9c23e7d8c4a3084b20dd9c277d4f4e5ee68b54f5929399923766a9d0
  grid-5x5     376109562b71f977ae4c479cab2283a2bf4b3d5c27018ff45002933d0ec37ee0
  shift        ddb8bc542e421d6ca32bc9dbdda2768496e72cb3b87fbab8cfb408c57b93771c
  island-city  a557c9ff15e9dbc96bd7c3c4b8031618bbaa4783524362c29ba91d9e7ec7411c
  valley-50    f138e7187f19d5f02581c5be0d3c6067f6d1ff95ff41c0eddb458b6ba4d0f3d2
  ```
- **Fallback**: bez sestaveného rozšíření musí celá sada testů projít jako
  dnes. Nikdo nesmí být nucen mít Rust.
- **Determinismus**: v Rustu žádné `HashMap` s náhodným hasherem v cestě, na
  které záleží pořadí (použij `BTreeMap`, `Vec` nebo pevný hasher), žádné
  vlákna měnící pořadí výsledků.
- **Checkpointy**: `FormBank` se mezi kopiemi světa sdílí, protože jen
  přibývá. Stav v Rustu musí tohle dodržet a deepcopy a pickle světa musí
  dál fungovat (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu**, konstant, `Parameters` ani bran. Existující testy
  neupravuj tak, aby prošly.
- Komentáře a docstringy piš česky ve stylu okolního kódu, a to i v Rustu.
  Identifikátory anglicky. `ruff` i `clippy` musí být čisté.

## Ověřování

```bash
CARGO_BUILD_JOBS=4 /Users/janvrzal/Documents/CEE/.venv/bin/maturin develop --release -m rust/cee_core/Cargo.toml
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py
CEE_NATIVE=0 PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python scripts/v2_digests.py --quick
PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests/v2/test_v2_checkpoints.py tests/v2/test_v2_datamodel.py tests/v2/test_v2_m1_gate.py
```
Pozor: `maturin develop` instaluje rozšíření do sdíleného venv. Ostatní
worktree ho pak také uvidí, a proto musí fallback fungovat, když se rozšíření
a Python kód rozejdou. Do rozšíření dej verzi rozhraní a Python ho při
nesouladu nepoužije.

Na konci pusť celou sadu na pozadí dvakrát, s rozšířením a s `CEE_NATIVE=0`
(každá asi 13 minut):
`PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests`.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- profil (kolik času jde do tohoto modulu) a čas valley-50 a grid-5x5
  s Rustem a bez něj,
- otisky s Rustem i bez něj a výsledky obou celých sad,
- jak vypadá rozhraní Python ↔ Rust a co z něj převezmou další moduly
  (aplikace změn, fonologizace),
- dobu překladu (čistý release build, inkrementální po malé změně),
- co nešlo a proč.

# Zadání: přenos a živé fondy v Rustu (fáze B, krok 4)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md`: fáze A (A5, A7) a fáze B (B1 až
  B3 a bod 4), oddíl „Bitová shoda při přechodu do Rustu“;
- zadání B2 a B3 (`zadani-rust-b2.md`, `zadani-rust-b3.md`), kde je hotový vzor:
  `cee.v2.native`, `NativeBank`, `native.kernel`, verze rozhraní,
  fallback, smyčka `needs`, `pairwise_sum` a `sums_match`;
- `zadani-prenos.md` a modul `src/cee/v2/phases_transmission.py`
  (funkce přenosu nad poli) a `src/cee/v2/pools.py` (řídké fondy).

## Proč

Přenos je jádro hlavní smyčky. Aby šla jednou celá smyčka do Rustu (B6),
musí v Rustu být fondy a přenos. Samotná čísla přenosu (míšení, výběr,
drift) dnes stojí jen asi 4 % času valley-50, většinu přenosu berou tlaky.
**Cíl tohoto kroku tedy není hlavně rychlost.** Cílem je mít přenos a fondy
v Rustu správně a bitově stejně, s jasným rozhraním, na které se pak napojí
tlaky.

## Hlavní překážka: pořadí sčítání v míšení

`phases_transmission.mix` násobí matice přes BLAS (`matrix @ flat`). Pořadí
sčítání v BLAS závisí na knihovně, verzi a tvaru matic, takže ho Rust bitově
nezopakuje. Postup:

1. **Nejdřív v Pythonu** nahraď BLAS násobení součtem s pevně daným pořadím,
   který jde v Rustu zopakovat (např. postupně přes zdroje, nebo párově jako
   `pairwise_sum`). Vyber variantu, která je v numpy rozumně rychlá. Je to
   **vědomá změna otisků** stejně jako A6 (přenositelná náhoda):
   - změř čas před a po (valley-50, grid-5x5, mapa 20×20);
   - pusť audit bran (`scripts/v2_gate_rates.py --fresh`, seedy 101–120)
     před a po a porovnej Fisherovým testem jako v A6;
   - pusť retenci (`scripts/v2_calibrate_retention.py --seeds 1-8`
     s `--contact` i bez);
   - zapiš nový blok referencí do `scripts/v2_digests.py` (s popisem)
     a nové připnuté otisky (`test_v2_vocabulary.py` `DEFAULT_DIGEST`,
     `test_v2_domains.py`, `test_v2_edits.py`, zlatá data přenosu
     přegeneruj skriptem). **Nic jiného** se změnit nesmí: změna otisků
     musí jít jen z pořadí sčítání. Ověř to tím, že staré a nové míšení
     se na stejném vstupu liší jen v posledních bitech (relativní rozdíl
     řádu 1e-15);
   - pokud brány ukážou významnou změnu (p < 0,05), zastav se a popiš to.
2. **Pak Rust**: stejné pořadí v Rustu, ověřené zlatými daty a testem bit po
   bitu na šířkách 1 až několik set.

Totéž zkontroluj u všech ostatních součtů přenosu (`settle`, normalizace,
faktory). Kde se sčítá přes `np.sum`, zachovej párový součet
(`pairwise_sum`, hlídač `sums_match`). Transcendentní funkce (`exp`, `log`,
`**`, `hash_normal`) nech v Pythonu jako v B2, nebo dokaž testem, že Rust dává
bit po bitu totéž.

## Co udělat

1. Krok 1 výše (pevné pořadí míšení v Pythonu, vědomá změna otisků
   s ověřením), samostatný commit.
2. **Fondy v Rustu**: řídké uložení po variantách (`RowCells`) a hustý pohled
   pro přenos. Python `LivePools` zůstane fasádou se stejnými veřejnými
   metodami (`load`, `innovate`, `release`, `get`, `dominant`, `frequency`,
   `holds`, `sync_groups`, `load_differing`, `range_of`, `compact`). Testy
   fixují `block.freqs` a `block.slots` jako pohled, ty zachovej.
3. **Přenos v Rustu**: `hear` (míšení po komponentách a kanálech) a `settle`
   (výběr, trend, drift, ztráta, ustálení). Tlaky (`fitness`) dál počítá
   Python mezi `hear` a `settle`. Navrhni rozhraní tak, aby se do něj
   později daly napojit tlaky z Rustu bez přepisu (pole `fitness` po
   blocích).
4. **Zlatá data**: `tests/v2/data/golden_transmission.json.gz` přegeneruj
   pro nové pořadí. Test Rust proti Pythonu bit po bitu.
5. **Ověření** s Rustem i bez něj, čas před a po, zápis do
   `18-priprava-na-rust.md` (bod 4 fáze B, včetně nové kapitoly do oddílu
   „Bitová shoda při přechodu do Rustu“ o pořadí sčítání v míšení).

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/phases_transmission.py`, `transmission.py`, `pools.py`;
- `src/cee/v2/simulation.py`: jen `_transmit` a co s ním přímo souvisí;
- `src/cee/v2/pressures/base.py`: jen vnitřek `PressureBatch`, rozhraní
  tlaků zachovej;
- `src/cee/v2/native.py` a `rust/cee_core/`: nový kód Rustu dej do
  vlastních souborů (`pools.rs`, `transmission.rs`), v `lib.rs`
  a `python.rs` jen registrace. Zvyš verzi rozhraní na 4;
- `scripts/v2_digests.py`, připnuté otisky v testech (jen kvůli vědomé
  změně pořadí sčítání), zlatá data přenosu.

**Nesahej na:** `contact.py`, `edits.py`, `events.py`, `polity.py`,
`background.py`, tlaky (`pressures/*` kromě vnitřku `PressureBatch`),
indexy v `language/`, `changes/`, `assessment.py`. Souběžně pracuje agent
na zlatých datech tlaků a míst a na `contact.community_step`. Až se tvoje
změna otisků potká s jeho zlatými daty, sloučí to hlavní agent.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-worktrees/rust-b4`
  na větvi `engine-v2-rust-b4`. Jiné adresáře **neměň**.
- Rozšíření sestavuj
  `cd rust/cee_core && CARGO_BUILD_JOBS=3 /Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python`
  a instaluj
  `pip install --no-deps --target rust/cee_core/target/py <wheel>` (nejdřív
  smaž starý obsah `target/py`; teď je tam zkopírovaná verze 3). Pak
  `PYTHONPATH=src:.:rust/cee_core/target/py`. **Do sdíleného venv nic
  neinstaluj**, ani komponenty toolchainu.
- Python: `/Users/janvrzal/Documents/CEE/.venv/bin/python` z kořene
  worktree. Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
  Rust: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test`.
- Stroj má 16 GB RAM a souběžně pracuje ještě jeden agent. Pouštěj jeden
  těžký běh najednou, nejvýš 2 procesy (audit bran běží v jednom procesu),
  `CARGO_BUILD_JOBS=3`, žádný paralelní pytest. Pomocné soubory ukládej do
  worktree, ne do scratchpadu, a na konci je smaž. Když čekáš na proces na
  pozadí, nehledej ho přes `pgrep -f` s textem, který obsahuje i tvůj
  vlastní příkaz (najde sám sebe a čeká donekonečna). Čekej přímo na PID
  nebo na soubor s výsledkem.
- Commituj na `engine-v2-rust-b4` po malých krocích. Zpráva anglicky, na
  konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda** po kroku 1: nové otisky s Rustem (všech 7) i s
  `CEE_NATIVE=0` (`--quick`) jsou stejné. Do kroku 1 platí dnešní:
  ```
  phonology    3990a6381c1a91b4c4ffddf42731d42915325960dc128c834b6eec74ba2f97a3
  morphology   710009d641a04a0b1f007d29fa18a3d273780e322667b826bb3d9a7e7165d43b
  syntax       a55966f235d171ee1b772c2196b7bb2c2a742172a064d2b293c17a4df7553482
  grid-5x5     cc4ef6e136b0eaa543c08fc4c7e424ca53d781bcdd0e905858d3cb32de0bcc61
  shift        5d66d45559b5043c19e9259a9b4d7e5d8ce1349d2558f69107db7d6bd1737261
  island-city  a3efb455923bf5a6489b55e68ca877ed4e5ab2b422076a0ed4d7a569d6313e47
  valley-50    79b033067955967931819647325eb42d83f4aa21e826587be4f2d49f13373e88
  ```
- **Fallback**: bez rozšíření projde celá sada.
- **Determinismus**: v cestě, na které záleží pořadí, žádné hashovací
  struktury s náhodnou solí a žádná vlákna měnící pořadí.
- **Checkpointy a pickle** fungují, i s fondy v Rustu (stav se musí dát
  uložit a obnovit).
- **Žádné změny modelu** kromě pořadí sčítání v kroku 1. Konstanty,
  `Parameters` a brány beze změny. Existující testy neupravuj tak, aby
  prošly (kromě připnutých otisků v kroku 1).
- Komentáře a docstringy česky ve stylu okolního kódu, i v Rustu. `ruff`
  i `clippy` čisté.

Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:
- commity a co každý dělá;
- krok 1: zvolené pořadí sčítání, čas před a po, audit bran (tabulka změn
  s p-hodnotami), retence, staré a nové otisky;
- rozhraní Rustu (fondy a přenos) a co z něj převezmou tlaky a B6;
- čas valley-50, grid-5x5 a mapy 20×20 s Rustem a bez (s poznámkou
  o vytížení stroje), paměť;
- výsledky obou celých sad;
- co zůstalo v Pythonu a proč, co nešlo.

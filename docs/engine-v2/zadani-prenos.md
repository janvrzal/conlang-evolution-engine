# Zadání: přenos a řídké fondy jako funkce nad poli (zbytek A5) se zlatými daty (A7)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md`: fáze A (hlavně řádek A5 s řídkými
  fondy a A7), fáze B (B1 až B3, hlavně závěr B3 o indexech a obalech);
- zadání a výsledky A5 (`zadani-faze.md`, modul `cee.v2.phases`) a B3
  (`zadani-rust-b3.md`), protože tam je vzor funkcí nad poli, zlatých dat
  a hlídání pořadí sčítání;
- `docs/engine-v2/19-pojmy.md`, oddíl o doménách v kanálech kontaktu
  (`CrossFlow`, `channel_domains`, `borrowability_strength`).

## Proč

Podle profilu jde ve valley-50 asi **41 % času do přenosu a jeho přípravy**
(`transmission.prepare` a `transmit`). Je to největší blok, který ještě
v Rustu není. B3 ukázal, že čas nejde do samotných čísel, ale do Python
obalů a struktur klíčovaných řetězci. Živé fondy (`pools.py`) dnes drží
každou proměnnou jako husté pole skupiny × sloty a sloty jsou řetězcová ID
variant, která se při každé dávce překládají na čísla.

## Cíl

1. **Změř** profil přenosu (valley-50, grid-5x5 a jeden větší svět, např.
   `village_grid` 12×12 nebo víc) s Rustem: čas a špičku paměti. Rozepiš,
   kolik stojí `prepare`, míšení, výběr, drift, filtr kontaktu
   (`contact.borrowing_factor` po kanálech), instituce a převody slotů.
2. **Přenos jako funkce nad poli**: příprava vstupů kroku (matice vazeb,
   bloky komponent, kanály `CrossFlow`), míšení, faktory kontaktu
   a institucí po proměnných jako pole (ne volání po jedné proměnné),
   výběr a drift. Třídy a `StepInputs` zůstanou tenkou fasádou. Popiš
   hranici: co je čistá funkce polí a co zůstává na objektech.
3. **Řídké fondy podle variant** (rozhodnuto s uživatelem, viz řádek A5):
   - sloty jako čísla variant z registru, ne řetězce;
   - výskyt varianty jako řídký seznam (skupina, podíl) po variantách, tedy
     mapa rozšíření slova přímo v datech;
   - přenos potřebuje „co je u mě a u sousedů“, proto navrhni a změř dvojí
     index (po variantách i po skupinách), nebo husté bloky jen pro
     proměnné rozšířené skoro všude;
   - **bitová shoda je povinná**. Pokud by řídké uložení změnilo pořadí
     sčítání, počítej přenos dál nad hustými bloky sestavenými z řídkého
     uložení (nebo naopak) a pořadí zachovej. Když to bez změny otisků
     nejde, zastav se a popiš proč a kolik by to přineslo. Otisky
     neměň sám;
   - změř paměť a čas před a po na valley-50 a na větším světě. Cíl je, aby
     paměť a čas rostly s počtem skutečných výskytů, ne se součinem vesnic
     a variant.
4. **Zlatá data (A7)** pro funkce přenosu: skript v `scripts/`, záznam ze
   skutečných běhů (grid-5x5, shift, valley-50 zkráceně, svět s elitou,
   obchodem a liturgií, aby se pokryly kanály), výřez do `tests/v2/data/`
   (do 1 MB na modul), test proti Pythonu včetně pokrytí větví.
5. **Profil po** a zápis do `docs/engine-v2/18-priprava-na-rust.md` (řádky
   A5 a A7).

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/transmission.py`, `pools.py`, `contact.py`, `institutions.py`;
- `src/cee/v2/simulation.py`: jen `_transmit` a co s přenosem a fondy přímo
  souvisí;
- `src/cee/v2/world.py`: jen části týkající se živých fondů (`live`)
  a distribucí;
- `src/cee/v2/pressures/base.py`: jen vnitřek `PressureBatch`, pokud ho
  změna slotů vyžaduje. Rozhraní tlaků (`slot_column`, `assess_many`,
  memo klíče) zachovej, existující testy tlaků ho fixují;
- `src/cee/v2/phases.py` můžeš rozšířit, nebo založ `transmission`
  funkce ve vlastním modulu;
- nové skripty a testy.

**Nesahej na:**
- `events.py`, `polity.py`, `background.py` (souběžně na nich pracuje agent
  na A8, hranici pro události). Když událost dnes sahá přímo do fondů
  (`load`, `innovate`, `release`), zachovej tyto metody `LivePools` funkční
  se stejným významem;
- `rust/`, `native.py` a fonologii (Rust se v tomto kroku nepíše);
- modelové konstanty, `Parameters` a brány.

Když bez změny v cizím souboru nejde pokračovat, zastav se a popiš proč.

## Prostředí

- Pracuješ výhradně ve worktree
  `/Users/janvrzal/Documents/CEE-worktrees/transmission` na větvi
  `engine-v2-transmission`. Jiné adresáře **neměň**.
- Python z kořene worktree: `/Users/janvrzal/Documents/CEE/.venv/bin/python`.
  S Rustem: `PYTHONPATH=src:.:rust/cee_core/target/py` (rozšíření verze
  rozhraní 3 je už zkopírované, nestav ho). Bez Rustu:
  `CEE_NATIVE=0 PYTHONPATH=src:.`. Lint:
  `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM a souběžně pracuje ještě jeden agent. Pouštěj jeden
  těžký běh najednou a nejvýš 2 procesy. Žádný paralelní pytest. Skripty
  s `multiprocessing` jen ze souboru. Pomocné soubory ukládej do worktree,
  ne do scratchpadu (ten stroj průběžně čistí), a na konci je smaž.
- Nic neinstaluj. Commituj na `engine-v2-transmission` po malých krocích.
  Zpráva anglicky, na konci
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Soubory
  přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`. Když ti
  systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Bitová shoda** s Rustem (všech 7) i s `CEE_NATIVE=0` (`--quick`):
  `scripts/v2_digests.py` vypíše přesně
  ```
  phonology    3990a6381c1a91b4c4ffddf42731d42915325960dc128c834b6eec74ba2f97a3
  morphology   710009d641a04a0b1f007d29fa18a3d273780e322667b826bb3d9a7e7165d43b
  syntax       a55966f235d171ee1b772c2196b7bb2c2a742172a064d2b293c17a4df7553482
  grid-5x5     cc4ef6e136b0eaa543c08fc4c7e424ca53d781bcdd0e905858d3cb32de0bcc61
  shift        5d66d45559b5043c19e9259a9b4d7e5d8ce1349d2558f69107db7d6bd1737261
  island-city  a3efb455923bf5a6489b55e68ca877ed4e5ab2b422076a0ed4d7a569d6313e47
  valley-50    79b033067955967931819647325eb42d83f4aa21e826587be4f2d49f13373e88
  ```
  `--quick` spouštěj po každém kroku, valley-50 aspoň po každém druhém
  a na konci. Shodné musí zůstat i otisky v `tests/v2/test_v2_vocabulary.py`
  a `tests/v2/test_v2_domains.py` (neutrální váhy domén).
- **Determinismus**: žádné `hash()` ani `uuid4`, žádná iterace přes `set`,
  na jejímž pořadí záleží. Čísla z registrů neurčují pořadí, kde dnes
  rozhoduje řetězec (použij `Numbering.ranks()`).
- **Checkpointy a pickle** fungují (`tests/v2/test_v2_checkpoints.py`).
- **Žádné změny modelu.** Existující testy neupravuj tak, aby prošly. Když
  test fixuje vnitřek, který se mění (např. řetězcové sloty), zastav se
  a popiš to, místo abys test přepsal.
- Komentáře a docstringy česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` čistý.

Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:
- commity a co každý dělá;
- funkce přenosu: vstupní a výstupní pole (jména, typy, význam), aby šlo
  navrhnout rozhraní pro Rust (B4);
- návrh a stav řídkých fondů, paměť a čas před a po (valley-50, větší svět)
  s poznámkou o vytížení stroje;
- zlatá data (skript, velikost, pokrytí);
- profil před a po;
- otisky a výsledky obou celých sad;
- co zůstalo na objektech a proč, co nešlo.

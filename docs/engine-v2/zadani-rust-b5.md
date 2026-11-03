# Zadání: indexy na čísla z registru a hledání míst inovací v Rustu (fáze B, krok 5)

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md`: celá fáze A (registry A2, stav
  v polích A3, sloupce A4, funkce nad poli A5) a fáze B (B1 až B3 a bod 5);
  hlavně závěr B3: čas nejde do čísel, ale do indexů nad řetězcovými
  slovníky a do Python obalů;
- zadání B2 a B3 (`zadani-rust-b2.md`, `zadani-rust-b3.md`), kde je vzor:
  `cee.v2.native`, `NativeBank`, `native.kernel`, verze rozhraní,
  fallback, smyčka `needs`, `pairwise_sum` a `sums_match`;
- `zadani-faze.md` (`cee.v2.phases`) a profil v řádku A7.

## Proč

Hledání míst inovací stojí asi 30 % času valley-50 a tlaky asi 36 %.
V obou případech čas nejde do aritmetiky, ale do indexů pod nimi:
- `ContextIndex` a synchronizace indexů zvukových změn
  (`SoundSupportIndex`, sestavení kandidátů, `eval_supports`): asi 22 %
  celku;
- `LexicalClarityIndex`: asi 11 %;
- `AssessmentVocabularyIndex`, `FormAssessmentIndex` a hodnocení tvarů;
- `MorphologyCandidateIndex`, `ExponentIndex`, `SemanticSitesIndex`.

Indexy dnes drží stav ve slovnících a množinách klíčovaných řetězci
(`Counter`, `dict[str, ...]`, `set[str]`) a aktualizují se po jednotlivých
položkách z Pythonu. Rust jádra uvnitř takových indexů přinesla v B3 jen
asi 10 %. **Uživatel rozhodl:** indexy se převedou na čísla z registru
a přejdou do Rustu celé. Testy, které fixují jejich objektovou podobu, se
smí vědomě přepsat (podmínky níže). **Uživatel chce, aby výsledek byl
v Rustu co nejefektivnější.** To je hlavní kritérium návrhu.

## Zásady návrhu pro efektivitu (závazné)

1. **Data podle čísel, ne podle jmen.** Stav indexů tvoří ploché sloupce
   (struktura polí, SoA), indexované číslem z registru (morfém, tvar,
   pojem, proměnná, varianta, proces, hláska, skupina). V horkých cestách
   nepoužívej žádné řetězce a žádné hashovací mapy. Kde je vztah řídký,
   použij CSR nebo seřazené vektory, kde je hustý, `Vec` po číslech.
   Řetězce se převádějí jen na hranici (vstup ze světa a výstup pro
   historii nebo export).
2. **Stav žije v Rustu.** Index je objekt v Rustu (jako `NativeBank`),
   který přežívá mezi tiky. Python drží jen rukojeť a posílá **změny**
   (deníky: `FrequencyMap.log`, verze a tokeny tvarů, slovní zásoba,
   vznik a zánik variant a procesů), ne celý stav. Při každém ticku se nic
   znovu nestaví z Pythonu.
3. **Málo přechodů Python ↔ Rust.** Jedno volání na skupinu a tik,
   nejlépe jedno na tik pro všechny skupiny, ne volání na místo, proměnnou
   nebo tvar. Pole předávej bez kopírování (numpy pohledy, `PyReadonlyArray`)
   a výstupy vracej jako pole.
4. **Přírůstkově.** Přepočítej jen to, co se změnilo: špinavé položky jako
   bitová maska nebo seznam čísel z deníků. Měř, jaký podíl položek se za
   tik opravdu mění, a podle toho navrhni, kdy přepočítat vše naráz
   (husté vektorové průchody) a kdy jen změny.
5. **Bez alokací ve smyčkách.** Buffery drž v objektu a znovu je používej.
   Rozvržení dat vol tak, aby se četlo souvisle (vhodné pro cache).
6. **Vlákna jen deterministicky.** Paralelizace po skupinách (např.
   `rayon`) je povolená jen tam, kde každá skupina zapisuje do vlastního
   výstupu a nic se mezi vlákny nesčítá. Výsledek musí být bitově stejný
   s jedním vláknem i s více vlákny, to ověří test. Počet vláken musí jít
   nastavit (výchozí 1, dokud to neověříme na celé sadě). Ve zprávě uveď
   zrychlení s více vlákny.
7. **Python reference ve stejné podobě.** Nejdřív převeď indexy v Pythonu
   na čísla a pole (fáze A styl, bitově stejné otisky), pak je přepiš 1:1 do
   Rustu. Python verze zůstane jako fallback (`CEE_NATIVE=0`) a jako
   reference pro test Rust proti Pythonu.
8. **Pořadí sčítání a transcendentní funkce** jako v B3: párové součty
   (`pairwise_sum`, hlídač `sums_match`), `exp`, `log` a `**` v Pythonu, nebo
   dokaž testem, že Rust dává bit po bitu totéž.
9. **Měř.** Profil před a po (valley-50, grid-5x5, mapa 20×20) a ke každé
   větší změně čas. Kde návrh volíš mezi variantami, rozhoduj měřením.

## Co udělat

1. **Profil a inventura**: pro každý index popiš, jaký stav drží, z čeho se
   aktualizuje (které deníky), kdo ho čte (které změny a tlaky) a kolik
   stojí. Navrhni číselnou podobu (sloupce, CSR, špinavé masky) a hranici
   volání. Návrh zapiš do `docs/engine-v2/18-priprava-na-rust.md` (bod 5
   fáze B) ještě před implementací. Pořadí práce řiď cenou: nejdřív
   `ContextIndex` a indexy zvukových změn, pak lexikální jasnost, pak
   ostatní.
2. **Python na čísla** (po indexech, každý samostatný commit, otisky beze
   změny).
3. **Rust** (po indexech, verze rozhraní **5**; souběžně pracuje agent na
   B4, který zvedá verzi na 4, sloučení vyřeší hlavní agent). Nový kód dej
   do vlastních souborů (`index.rs`, `sites.rs`, `clarity.rs` …), v `lib.rs`
   a `python.rs` jen registrace.
4. **Hledání míst inovací** (`Change.sites`, `rates`, `total_rate`,
   `weighted_sites`) přes nové indexy, po dávkách pro všechny skupiny
   a druhy změn. Hranice s Pythonem: návrh varianty (`propose`) zůstává
   v Pythonu (viz A5).
5. **Zlatá data**: souběžně je agent na A7 zaznamenává na hranici, která se
   nemění (snímek světa a skupina → místa a míry, dávka → skóre tlaků).
   Až budou hotová, hlavní agent je sloučí a tvoje implementace musí projít
   i proti nim. Do té doby si udělej vlastní test Rust proti Pythonu na
   úrovni indexů a ověřuj otisky.

## Přepis existujících testů (uživatel souhlasil, za těchto podmínek)

Smíš přepsat testy, které fixují **vnitřní podobu** indexů a tlaků
(objektový přístup, řetězcové klíče, jména soukromých metod, `Counter`
a slovníky). Patří sem hlavně `test_v2_lexical_matrix.py`,
`test_v2_process_scores.py`, `test_v2_form_scores.py`,
`test_v2_morphology_index.py`, `test_v2_lexical_index.py` a části dalších
testů, které čtou vnitřek indexů. Podmínky:
- přepsaný test ověřuje **stejné chování**: stejné hodnoty, stejné případy,
  stejné hraniční situace, jen přes nové rozhraní. Aserce na hodnoty se
  nesmí oslabit ani vypustit;
- nesmíš sáhnout na brány (`test_v2_m*_gate.py` a jiné testy bran), na
  testy otisků a determinismu ani na připnuté otisky;
- každý přepsaný test vypiš ve zprávě: co fixoval, proč to už neplatí, čím
  je to nahrazené.

## Rozsah

**Tvoje soubory:**
- `src/cee/v2/language/index.py`, `lexical_index.py`, `assessment_index.py`,
  `form_assessment_index.py`, `morphology_index.py`, `semantic_index.py`;
- `src/cee/v2/assessment.py`, `src/cee/v2/changes/*.py` (hledání míst
  a míry; `propose` jen pokud to rozhraní nutně vyžaduje);
- `src/cee/v2/pressures/*.py` kromě `base.py` (tlaky čtou nové indexy);
- `src/cee/v2/morphology.py`, `phonology.py` jen v místech, kde se indexy
  aktualizují;
- `src/cee/v2/native.py`, `src/cee/v2/language/bank.py` a `rust/cee_core/`
  (vlastní soubory, registrace);
- testy výše za uvedených podmínek, nové testy a skripty.

**Nesahej na:** `transmission.py`, `phases_transmission.py`, `pools.py`,
`pressures/base.py`, `simulation.py` kromě míst, která volají hledání míst
inovací (`_innovate` a spol.), `contact.py`, `edits.py`, `events.py`,
`polity.py`, `background.py`. Na nich souběžně pracují agenti na B4 a A7.
Když bez změny v cizím souboru nejde pokračovat, zastav se a popiš proč.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-worktrees/rust-b5`
  na větvi `engine-v2-rust-b5`. Jiné adresáře **neměň**.
- Rozšíření sestavuj
  `cd rust/cee_core && CARGO_BUILD_JOBS=3 /Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python`
  a instaluj `pip install --no-deps --target rust/cee_core/target/py <wheel>`
  (nejdřív smaž starý obsah `target/py`, teď je tam zkopírovaná verze 3).
  Pak `PYTHONPATH=src:.:rust/cee_core/target/py`. **Do sdíleného venv nic
  neinstaluj**, ani komponenty toolchainu. Nová závislost crate (např.
  `rayon`) je povolená, jen pokud má licenci MIT nebo Apache-2.0.
- Python: `/Users/janvrzal/Documents/CEE/.venv/bin/python` z kořene
  worktree. Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
  Rust: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`,
  `cargo test`.
- Stroj má 16 GB RAM a souběžně pracují ještě dva agenti, jeden také
  překládá Rust. Pouštěj jeden těžký běh najednou, nejvýš 2 procesy,
  `CARGO_BUILD_JOBS=3`, žádný paralelní pytest. Časy měř opakovaně
  a střídavě (základ, nový, základ…), protože stroj je vytížený. Pomocné
  soubory ukládej do worktree, ne do scratchpadu, a na konci je smaž. Když
  čekáš na proces na pozadí, nehledej ho přes `pgrep -f` s textem, který
  obsahuje i tvůj vlastní příkaz (najde sám sebe a čeká donekonečna). Čekej
  přímo na PID nebo na soubor s výsledkem.
- Commituj na `engine-v2-rust-b5` po malých krocích. Zpráva anglicky, na
  konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.
- Práce je velká. Když nestihneš všechno, dotáhni čistě to, co je hotové
  (otisky, testy, commit), a ve zprávě přesně popiš, co zbývá a v jakém
  pořadí pokračovat.

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
  Shodné musí zůstat i otisky v `test_v2_vocabulary.py`, `test_v2_domains.py`
  a `test_v2_edits.py`. (Agent na B4 otisky vědomě změní kvůli pořadí
  sčítání v míšení. To se tě netýká, ty drž tyto.)
- **Fallback**: bez rozšíření projde celá sada.
- **Determinismus**: v cestě, na které záleží pořadí, žádné hashovací
  struktury s náhodnou solí. Vlákna jen podle zásady 6.
- **Checkpointy a pickle** fungují, i se stavem indexů v Rustu (stav se
  dá uložit a obnovit, nebo se po obnovení deterministicky přestaví).
- **Žádné změny modelu**, konstant, `Parameters` ani bran.
- Komentáře a docstringy česky ve stylu okolního kódu, i v Rustu. `ruff`
  i `clippy` čisté.

Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:
- commity a co každý dělá;
- návrh: číselná podoba každého indexu, hranice volání, přírůstkové
  aktualizace (podíl změněných položek za tik);
- profil a čas před a po (valley-50, grid-5x5, mapa 20×20) s Rustem a bez,
  s jedním a více vlákny, s poznámkou o vytížení stroje; paměť;
- přepsané testy (co, proč, čím nahrazeno);
- otisky a výsledky obou celých sad;
- co zůstalo v Pythonu a proč, co nešlo, co zbývá.

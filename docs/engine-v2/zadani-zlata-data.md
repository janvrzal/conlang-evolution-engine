# Zadání: dokončení zlatých dat (A7) pro tlaky a hledání míst inovací, kontakt komunit přes API změn

Přečti si:
- `docs/engine-v2/18-priprava-na-rust.md`: fáze A (řádky A5, A7 a A8,
  oddíl „A8: API změn světa“) a fáze B (B1 až B3 a body 4 a 5);
- zadání a skripty dosavadních zlatých dat: `zadani-faze.md`
  (`scripts/v2_golden_phases.py`), `zadani-prenos.md`
  (`scripts/v2_golden_transmission.py`), `zadani-rust-b3.md`
  (`scripts/v2_golden_assessment.py`) a testy `tests/v2/test_v2_golden_*.py`.

## Proč

Zlatá data jsou měřítko, proti kterému se Rust ověřuje kus po kusu. Hotová
jsou pro banku tvarů, fonologizaci, hodnocení zvukových procesů, funkce
fází kroku a přenos. Chybí pro dvě věci, které teď stojí nejvíc času a půjdou
do Rustu jako další:
- **tlaky** (`Pressure.scores` po třídách), dohromady asi 36 % času
  valley-50: artikulace asi 12 %, lexikální jasnost asi 11 %, zachování tvarů
  asi 8 %;
- **hledání míst inovací** (`Change.sites`, `rates`, `total_rate`,
  `weighted_sites` po druzích změn), asi 30 % času. Z toho jsou asi dvě
  třetiny synchronizace indexů zvukových změn.

Indexy pod tím (`ContextIndex`, `LexicalClarityIndex`,
`AssessmentVocabularyIndex`, `FormAssessmentIndex`, `SoundSupportIndex`,
`MorphologyCandidateIndex`, `SemanticSitesIndex`) se budou předělávat na
čísla z registru. Proto zlatá data zaznamenej **na hranici, která se
nemění**: vstup je stav světa v daném ticku a skupina, výstup jsou místa
a míry, resp. skóre tlaků. Na vnitřní podobě indexů záviset nesmí.

## Cíl

1. **Zlatá data tlaků**: pro každou třídu tlaku ze skutečných běhů zaznamenej
   dávku (`PressureBatch`: proměnné, sloty jako čísla i ID variant, skupiny,
   četnosti) a výstup `scores` bit po bitu. Formát vstupu navrhni tak, aby šel
   načíst bez živého světa, tedy jako pole. Kde tlak čte stav světa (tvary,
   slovní zásobu, frekvence, hodnocení), zaznamenej i tyto vstupy jako pole,
   nebo popiš, co přesně z něj čte, a ulož snímek světa (pickle checkpointu) pro přehrání. Test ověří
   výstupy proti Pythonu.
2. **Zlatá data hledání míst**: pro každý druh změny (`DEFAULT_CHANGES`)
   v náhodně vybraných (deterministicky, `Stream`) ticích a skupinách
   zaznamenej `sites`, `rates` (nebo jednotnou míru), `total_rate`
   a `weighted_sites`. Vstupem je snímek světa (checkpoint) a skupina.
   Test načte snímek, spočte totéž a porovná bit po bitu. Hlídej pokrytí:
   každý druh změny aspoň s jedním neprázdným výsledkem. Kde se ve
   scénářích nestane, přidej malý svět, kde se stane.
3. **Scénáře**: grid-5x5, shift, valley-50 zkráceně, svět s elitou,
   obchodem a liturgií (viz `tests/v2/edit_worlds.py`) a světy pro vzácné
   cesty, jako to dělá `v2_golden_phases.py`. Výřez do `tests/v2/data/`
   do 1 MB na soubor. Snímky světa jsou větší, proto ulož jen tolik, kolik
   test potřebuje, a velikost hlídej. Když se snímky do limitu nevejdou,
   generuj je v testu deterministicky během (s `pytest.mark.slow`, pokud
   v projektu existuje, jinak krátké běhy) a ulož jen očekávané výstupy.
4. **Kontakt komunit přes API změn** (zbytek A8): `contact.community_step`
   dnes mění skupiny a vazby přímo. Převeď ho na operace `cee.v2.edits`
   (podle oddílu A8 v dokumentu operace stačí: `set_group`, `add_group`,
   `set_code`, `remove_group`, `connect`, `set_border_factor`,
   `set_prestige_mirror`). Rozšiř test přehrání deníku (`test_v2_edits.py`)
   o svět, kde komunity přecházejí, a hlídač rozboru zdrojového kódu
   o `contact.py` (jen `community_step` a jeho pomocníky).
5. **Dokumentace**: řádky A7 a A8 v `18-priprava-na-rust.md`.

## Rozsah

**Tvoje soubory:**
- nové skripty `scripts/v2_golden_pressures.py`, `scripts/v2_golden_sites.py`
  (nebo jeden společný), nové testy a data v `tests/v2/`;
- `src/cee/v2/contact.py`: jen `community_step` a jeho pomocníci;
- `src/cee/v2/edits.py` a `tests/v2/test_v2_edits.py`,
  `tests/v2/edit_worlds.py` (rozšíření);
- `docs/engine-v2/18-priprava-na-rust.md` (řádky A7 a A8).

**Nesahej na** ostatní soubory v `src/` (souběžně pracuje agent na B4:
`transmission.py`, `pools.py`, `phases_transmission.py`, `simulation.py`,
`rust/`, `native.py`). Pokud záznam potřebuje háček v kódu, nahraď funkci
za běhu ve skriptu (monkeypatch) jako `v2_golden_phases.py`, ne změnou
zdroje. Když to nejde, zastav se a popiš proč.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-worktrees/golden`
  na větvi `engine-v2-golden`. Jiné adresáře **neměň**.
- Python z kořene worktree: `/Users/janvrzal/Documents/CEE/.venv/bin/python`.
  S Rustem: `PYTHONPATH=src:.:rust/cee_core/target/py` (rozšíření je
  zkopírované, nestav ho). Bez Rustu: `CEE_NATIVE=0 PYTHONPATH=src:.`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM a souběžně pracuje ještě jeden agent (překládá Rust).
  Pouštěj jeden těžký běh najednou a nejvýš 2 procesy. Žádný paralelní
  pytest. Pomocné soubory ukládej do worktree, ne do scratchpadu, a na konci
  je smaž. Když čekáš na proces na pozadí, nehledej ho přes `pgrep -f`
  s textem, který obsahuje i tvůj vlastní příkaz (najde sám sebe a čeká
  donekonečna). Čekej přímo na PID nebo na soubor s výsledkem.
- Nic neinstaluj. Commituj na `engine-v2-golden` po malých krocích. Zpráva
  anglicky, na konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

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
  a `test_v2_edits.py`.
- Zlaté soubory jsou při opakovaném běhu skriptu bajt po bajtu stejné.
- **Determinismus**, **checkpointy a pickle** fungují.
- **Žádné změny modelu.** Existující testy neupravuj tak, aby prošly.
- Komentáře a docstringy česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` čistý.

Na konci pusť celou sadu s Rustem a s `CEE_NATIVE=0`, po jedné, na pozadí.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:
- commity a co každý dělá;
- formát zlatých dat (co je vstup a výstup, jak je načíst bez živého světa);
- pokrytí (tlaky a druhy změn, které mají neprázdná data, a které ne a proč);
- velikosti souborů a dobu testů;
- převod `community_step` a rozšířený test přehrání;
- otisky a výsledky obou celých sad;
- co nešlo a proč.

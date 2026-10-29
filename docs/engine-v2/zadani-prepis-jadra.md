# Zadání: datově orientovaný přepis jádra enginu v2 s Numbou

Pro dvojici agentů: **Sol** (koordinátor) a **Terra** (implementátor).

## Role

**Sol, koordinátor**
- Přečte toto zadání, `AGENT.md` (oddíl 1b) a `docs/engine-v2/05-specifikace.md`
  (hlavně oddíly „Výkon: banka tvarů a průběžné indexy“ a „Determinismus“).
- Upřesní plán fází níže, rozdělí ho na malé úkoly a každý úkol předá
  Terře s jasným rozhraním, dotčenými soubory a kritérii přijetí.
- Po každém úkolu zkontroluje diff, spustí ověření (viz Ověřování) a
  rozhodne: přijmout, vrátit k opravě, nebo změnit plán.
- Vede deník měření a na konci aktualizuje specifikaci a `AGENT.md`.
- Sám velké části kódu nepíše; drží architekturu, invarianty a tempo.

**Terra, implementátorka**
- Implementuje úkoly od Sola přesně v zadaném rozsahu.
- Ke každému úkolu přidá testy (u přeložených jader test shody s
  referenční implementací v čistém Pythonu).
- Odevzdá diff, výpis `scripts/v2_digests.py` a časy; nic nepřikrášluje.
- Když narazí na rozpor se zadáním nebo s invariantem, zastaví se a
  zeptá se Sola, místo aby ho obešla.

## Kontext

- Repozitář `CEE`, větev `engine-v2`. Pracujte na nové větvi
  `engine-v2-numba` vytvořené z commitu, ve kterém je tento soubor.
- Nové simulační jádro je v `src/cee/v2/`; legacy (`src/cee/engine/`) se
  nemění. Simulace jazykové evoluce: skupiny mluvčích (vesnice), jejich
  repertoáry variant, zvukové změny jako procesy, fonologizace slov,
  morfologie, syntax, kontakt jazyků. Dokumentace a komentáře jsou česky,
  identifikátory anglicky.
- **Nesahejte** na necommitnuté soubory uživatele: `ui/`,
  `src/cee/project_schema.py`, `tests/test_projects.py`.
- Prostředí: Python 3.11 ve `.venv/`, `numpy`; Numba zatím není
  nainstalovaná (viz fáze 0).

## Cíl

Řádově zrychlit plný model **při zachování bitově stejných výsledků**.

| Měření (`scripts/v2_digests.py`) | Dnes | Cíl |
|---|---|---|
| `valley-50`: údolí, 50 vesnic, syntax + význam, 2 000 let | asi 38 s | **≤ 8 s** |
| `grid-5x5`: 25 vesnic, morfologie + význam, 1 000 let | asi 3,6 s | ≤ 1 s |
| celá sada testů | asi 4 min 50 s | výrazně méně |

Výkonový rozpočet specifikace je 5 s pro údolí a 60 s pro region (200
skupin, 3 000 let). Cíl ≤ 8 s je první krok; pokud se ukáže dosažitelný
rozpočet, tím lépe.

## Výchozí stav

Otisky logu (sha256 historie) a časy na výchozím commitu. Po každém kroku
přepisu musí `python scripts/v2_digests.py` vypsat **přesně stejné otisky**:

```
phonology    cdb5587f3219f08954564b08042e7f213e3ffdfdad1647b2f8f08fcff1e69bc3
morphology   2572f5dcef8af309e1d1a57c984e7e462820ae3fa5ffef8bca2f726d11ac7a25
syntax       941dc5c7b919f86db6bdac74d9251c7203aca85e0ebd115504bdfbef0d704117
grid-5x5     ce9409e7363199218ebdc91f78bfe32d5500c2099fc3910c14e4c80cfea874ab
shift        41764bcdf9bfaa8ca22b93378df2181fb810288a695ac2565c04fa3e3c16cfda
island-city  c98d204cc23fb9db05d079724272638b63dbc24901875c0c8815f5575dd8a7ab
valley-50    e0626b7c844628596d7bf71929d5a96b14643f2af8a1c484f9579790308f43ea
```

(Na začátku je ověřte znovu; pokud se liší, prostředí není stejné a je
třeba to vyjasnit dřív, než se cokoli změní.)

**Kam jde čas** (údolí, 2 000 let, měřeno stopkami, ne profilerem; cProfile
výrazně nadhodnocuje části s mnoha drobnými voláními):

| Oblast | Podíl |
|---|---|
| přenos celkem (`Simulation._transmit`) | 55 % |
| — tlak Articulation (první tlak, plní hodnocení procesů z `assessment.py`) | 14 % |
| — lexikální jasnost (`pressures/lexical.py`, `LexicalClarity`) | 8 % |
| — fonologizace (`phonology.restructure`) | 8 % |
| hledání míst inovací (`Simulation._innovate`) | 39 % |
| — zvukové změny (`changes/sound.py`, `_supported`, `context_stats`) | 15 % |
| — lexikální změny (`changes/lexicon.py`, `SemanticChange._sites`) | 13 % |
| — analogie (`changes/morphology.py`) | 6 % |
| — syntax (`changes/syntax.py`, `syntax.weakness`) | 4 % |
| pozorování (`observe.py`, `cognate_matrix`) | 7 % |

To je 4 000 výpočtů „skupina × krok“ po zhruba 9 ms. Na 8 s je potřeba
asi 2 ms. Čas není v jednom místě: je to Python, který v každém kroku
prochází stovky slov každé skupiny přes slovníky s textovými klíči.

## Co už existuje (stavte na tom)

- **Banka tvarů** `src/cee/v2/language/bank.py`: `FormBank` čísluje různé
  tvary (n-tice čísel hlásek), drží délky a odvozené vlastnosti;
  `ProcessTable` drží pro každou zvukovou změnu „číslo tvaru → číslo
  výsledku“ (−1 = nemění, −2 = neznámo); `FormBank.screen` je hromadný
  předfiltr míst všech změn nad maticemi masek.
- **Průběžné indexy** `src/cee/v2/language/index.py`: `FormStore` vede deník
  přepsaných morfémů (`token`, `log`); `ContextIndex` a `ExponentIndex` si
  dorovnají jen změny. Index drží jen data, ne odkazy na svět (kvůli
  kopiím stavu).
- **Verze** v `PhonologyState`: `version` (každá změna tvaru nebo slovní
  zásoby) a `lexicon_version` (jen slovní zásoba).
- **Hromadné hodnocení** `assessment.assess_many` / `_assess_batch`: matice
  skupiny × slova vzorku.
- **Checkpointy** `Simulation.checkpoint/resume/branch`: hluboká kopie
  stavu, banka tvarů, tabulka hlásek a graf pojmů se sdílejí. Musí dál
  fungovat a pokračování z checkpointu musí dát stejný otisk jako běh od
  začátku (`tests/v2/test_v2_checkpoints.py`).

## Cílová architektura (návrh, Sol upřesní)

1. **Čísla místo řetězců v horkých cestách.** Registr morfémů (řetězec →
   index), skupin a procesů. Řetězcová ID zůstanou na okraji: log
   historie, export, veřejné API. Pořadí, ve kterém se morfémy zpracovávají,
   musí zůstat stejné jako dnes (dnes typicky `sorted(...)` podle řetězce);
   indexy nesmí zavést jiné pořadí.
2. **Stav skupin v polích.** Pro každý kód pole `form_id[morfém]` do banky
   tvarů (−1 = výchozí tvar), hranice koncovky a koncovka; slovní zásoba
   jako pole ano/ne nebo seřazené pole indexů. `World.unit_of/form_of` a
   `FormStore.get/set/branch/log` zůstanou jako fasáda, aby se zbytek kódu
   nemusel přepsat najednou.
3. **Přeložená jádra (Numba, `@njit(cache=True)`)** nad těmito poli:
   - aplikace zvukové změny na tvar a dávku tvarů (`Process.apply_tracked`:
     místa podle cíle, sousedů, přízvuku a pozice; operace change, replace,
     delete, insert_before, insert_after, merge_next; sledování hranice
     kmen | koncovka; pravidlo minimálního slova);
   - fonologizace skupiny: fronty změn (seřazené podle potřebného logitu),
     přepis slov, opětovné zařazení do front ostatních změn;
   - statistika prostředí hlásek a opory kandidátů zvukových změn;
   - hodnocení funkční zátěže (zasažená slova, homofony, zkrácení,
     příznakovost);
   - lexikální jasnost (mapa homofonů, eroze).
   Ke každému jádru zůstane referenční implementace v čistém Pythonu (dnešní
   kód) a test shody na náhodných i skutečných tvarech.
4. Zbytek (události, kontakt, syntax, export, log, pozorování) zůstane v
   Pythonu, pokud ho měření neukáže jako brzdu.

## Fáze

**Fáze 0: základ.**
- Přidejte `numba` do `pyproject.toml` (závislost jádra; ověřte instalaci
  pro Python 3.11 na macOS arm64 i Linuxu) a do `.venv`.
- Ověřte výchozí otisky a časy.
- Napište měřicí skript s rozpadem času po fázích kroku (stopky kolem
  `_innovate`, `_transmit`, jednotlivých tlaků a změn, ne cProfile).

**Fáze 1: čísla a pole za stávajícím rozhraním.** Registr indexů, pole tvarů
skupin, slovní zásoba jako pole. Rychlost se nemusí změnit; otisky musí
sedět. Checkpointy musí fungovat.

**Fáze 2: první jádro.** Aplikace změn a fonologizace v Numbě. Změřte. Tady
se rozhodne, jestli odhad (horká místa 10–50×) platí. Pokud ne, Sol zastaví
a s uživatelem přehodnotí plán.

**Fáze 3: další jádra** podle měření: statistika prostředí a opory
kandidátů, hodnocení funkční zátěže, lexikální jasnost, kandidáti analogie a
syntaxe.

**Fáze 4: úklid a dokumentace.** Odstranit, co přepis nahradil (kromě
referenčních implementací pro testy), aktualizovat specifikaci (nový oddíl
„Stav M6e: datově orientované jádro“ s měřeními) a `AGENT.md`.

## Invarianty (porušení = úkol se nepřijme)

- **Bitová shoda**: `scripts/v2_digests.py` vypíše stejné otisky jako
  výchozí commit. Pozor na pořadí sčítání čísel s plovoucí čárkou: smyčka
  v Numbě sčítá postupně jako Python, `np.sum` párově (jinak). Kde dnes
  Python sčítá postupně, sčítejte postupně.
- **Determinismus** (`AGENT.md`, specifikace „Determinismus“): náhoda jen
  z `cee.v2.rng` se stabilními ID; žádné `hash()`, `uuid4`, iterace přes
  `set` v pořadí, na kterém záleží. Indexy jsou interní a nesmí určovat
  pořadí čehokoli, co ovlivňuje výsledek nebo log.
- **Izolace oblastí**: zjemnění jedné oblasti nesmí změnit historii
  nepropojené oblasti (testy v `test_v2_m1_gate.py`, `test_v2_m2_gate.py`).
- **Checkpointy**: kopie stavu nesmí sdílet měnitelná pole se zdrojem
  (výjimka: data jen přibývající a neměnná, jako banka tvarů).
- **Brány milníků se neupravují.** Prahy v `tests/v2/*_gate.py` se nesmí měnit,
  aby test prošel. Když brána padá, je to chyba přepisu.
- **Veřejné API** zůstává: `Simulation` (`run`, `iterate`, `step`,
  `checkpoint`, `resume`, `branch`), `World.form_of/unit_of/distribution`,
  `cee.v2.export`, scénáře v `cee.v2.scenarios`.
- `ruff check src/cee/v2 tests/v2` a `mypy src/cee/v2` čisté. Komentáře a
  docstringy česky, ve stylu okolního kódu.

## Ověřování (po každém úkolu)

```bash
.venv/bin/python scripts/v2_digests.py           # otisky + časy, musí sedět
.venv/bin/python -m pytest -m "not slow" -q      # rychlá sada (~20 s)
.venv/bin/ruff check src/cee/v2 tests/v2
.venv/bin/mypy src/cee/v2
```

Po každé fázi navíc celá sada: `.venv/bin/python -m pytest -q`.

Časy měřte na nevytíženém stroji a vždy proti výchozímu commitu ve stejném
běhu (souběžné běhy se navzájem brzdí a čísla pak kolísají o ±2 s).

## Výstupy

- Commit po každém přijatém úkolu na větvi `engine-v2-numba`, zpráva
  anglicky v imperativu (styl `git log`), popis co a proč, s uvedenými
  otisky a časy.
- Na konci: souhrn pro uživatele česky (co se změnilo, měření před a po,
  co zůstalo pomalé a proč), aktualizovaná specifikace a `AGENT.md`.
- Merge do `engine-v2` až po schválení uživatelem.

## Rizika a tipy

- **Proměnná délka tvarů** (vkládání a mazání hlásek): pracujte s
  maticí banky (tvar = řádek, výplň −1) a délkami, výsledky zapisujte do
  nových řádků banky.
- **Lexikální difuze**: fonologizace přepisuje slova postupně podle
  potřebného logitu (`phonology._needed`: logit prahu − náskok frekvence −
  sklon slova); pořadí fronty a přepisů musí zůstat stejné.
- **Sklon slova** (`phonology.word_bias`) se generuje z `rng.generator` se
  stabilními ID; v jádře ho předávejte jako předpočítané číslo, negenerujte
  ho uvnitř.
- **Řetězcové klíče v keších** (`state.cache`) a deníky indexů: při přechodu
  na pole hlídejte, aby se neztratila invalidace podle `version` a
  `lexicon_version`.
- **První překlad** Numby trvá sekundy; `cache=True` ho uloží na disk. Do
  měření výkonu ho nezapočítávejte, ale zmiňte ho.
- Při nejistotě, jestli změna drží bitovou shodu, ji nejdřív ověřte na
  `--quick` sadě (`scripts/v2_digests.py --quick`, bez údolí, asi 7 s).

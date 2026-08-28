# CEE (Conlang Evolution Engine) - LLM Agent Context

Tento soubor slouží jako vstupní bod a referenční manuál pro budoucí LLM agenty pracující na tomto projektu. Obsahuje klíčová architektonická pravidla a konvence. **ČTI PEČLIVĚ PŘED KAŽDÝM ZÁSAHEM DO KÓDU!**

## 1. Základní principy a pravidla (MUST FOLLOW)
1. **Determinismus a reprodukovatelnost:** Jakýkoliv běh simulace musí při stejném nastavení a stejném "seedu" vygenerovat 100% stejný výsledek. Všechna náhodnost je řízena pomocí fixních seedů.
2. **Offline sémantika a jazykový engine:** Nezapojujeme živé LLM API do samotného běhu simulátoru! LLM se používá pouze pro **offline** úkoly (jako extrakce dat, generování vstupních slovníků z JSON/CSV, nebo psaní kódů enginu). Při samotné generaci zvukových změn nebo sémantických posunů používá CEE vlastní kód a lokální Markovovy řetězce (s váhami v YAML presetech).
3. **Data nepatří na Git:** Složky jako `runs/`, výstupní `.csv` soubory a vygenerovaná velká data necommitujeme.
4. **Vlastnosti slova (`origin_year` atd.):** Slova musí nést historii. Například výpůjčky dostávají `origin_year`, díky kterému unikají starším zvukovým změnám. Tento systém se používá místo psaní složitých `IF` bloků a udržuje kód elegantní.

## 2. Architektura Projektu

Projekt je rozdělen do několika logických bloků (uvnitř `src/cee`):
* **`core/`**: Datové modely.
  * `Word`: Drží kořenový `concept_id`, pole fonologických `Segment`ů a množinu `polysemy` (dodatečné sémantické významy).
  * `Lexicon`: Kolekce slov a metody na jejich vyhledávání (podporuje polysemii).
  * `State`: Historický uzel jazyka v čase. Obsahuje `Inventory` (aktivní fonémy).
* **`engine/`**: Logika simulace.
  * `phonology.py`: Zajišťuje překlad IPA stringů do rysových matic a zpět pomocí knihovny **Panphon**.
  * `rules.py`: Třída `RuleEvaluator`. Aplikuje historická hlásková pravidla na segmenty.
  * `fold.py`: `DerivationFold` spouští série pravidel nad celým lexikonem a aktualizuje stavový `Inventory`.
  * `simulator.py`: Globální "lockstep" simulátor větvení a kontaktů.
  * `generator.py` a `schemas.py`: Plug-and-Play generátor náhodných pravidel s podporou presetů.
  * `topology.py`: Třídy pro síťový graf vývoje (hrany dědičnosti a kontaktů).
  * `semantics.py`: `SemanticEvaluator` spouští pravděpodobnostní Markovovy řetězce nad `SemanticGraph` a posouvá významy.
* **`semantics/`**: Abstrakce pro graf sémantických posunů z CLICS a DatSemShift.
* **`metrics/`**: Vyhodnocování úspěšnosti (např. pomocí **LingPy** na editační vzdálenosti).
* **`cli/`**: Typer command-line interface.

## 3. Kritická Pravidla a Znalosti pro LLM

### 3.1 Panphon Rysy (Features)
Nejčastější chyba LLM! Knihovna `panphon` používá zkrácené názvy rysů.
* **ŠPATNĚ:** `voice`, `coronal`, `anterior`, `syllabic`, `consonantal`
* **SPRÁVNĚ:** `voi`, `cor`, `ant`, `syl`, `cons`
* Před psaním testů nebo YAML pravidel si *vždy* ověř přesný název rysu (např. `hi`, `lo`, `back`, `round`, `tense`, `cont`, `delrel`, `lat`, `nas`, `strid`).

### 3.2 Aplikátor Pravidel (Dvoufázovost)
Aplikace pravidel (`rules.py`) probíhá **dvoufázově**, aby se zamezilo artefaktům (self-feeding).
1. Fáze identifikace: Projde PŮVODNÍ segmenty a najde indexy, které splňují `target`, `env_before` a `env_after`.
2. Fáze mutace: Aplikuje změny z `action` simultánně pouze na nalezené indexy.
*Nikdy nemutuj segmenty během iterace, pokud zároveň kontroluješ jejich okolí!*

### 3.3 Sémantika a Polysemie
* Sémantická data se generují z repozitářů Concepticon a DatSemShift do lokální cache `~/.cee/semantics/graph.graphml`. Tato data se **NIKDY necommitují do Gitu**.
* Sémantický posun neukládáme tak, že slovo ztratí kořenový `concept_id`. Místo toho slovo získává nová ID do atributu `polysemy` (množina). Slovo tak získává další významy jako v přirozených jazycích (např. "koruna" stromu / "koruna" krále).
* `SemanticEvaluator` **musí** využívat deterministický lokální `random.Random(seed)`, jinak by evoluční stromy generovaly při každém běhu jiná slova!

### 3.4 Změny a Hygiena
* Všechny konfigurační YAML, CSV datasetů a high-level dokumentace (`CEE_master.md`, `CEE_GDD.md`) jsou ignorovány v `.gitignore` (respektive by neměly být commitovány pokud to není explicitně potřeba). Držíme repozitář čistý pouze se zdrojovými kódy CEE samotného.
* CLI je stavěné přes `Typer` v `src/cee/cli/main.py`.

## 4. Workflow
Předtím, než začnete psát kód:
1. Přečtěte si `docs/CEE_master.md` pro hluboký architektonický kontext.
2. Dodržujte existující návrhové vzory (např. používání `dataclasses`).
3. Při rozšiřování CEE se drž klasického TDD přístupu. Otevři `tests/`, napiš test na novou lingvistickou funkcionalitu (simulace lenice, palatalizace, asimilace) s důrazem na **správné Panphon rysy** a teprve pak upravuj jádro.
4. Používejte existující testovací scénáře (např. `scenario_generator.yaml`) pro otestování vašich úprav pomocí `cee simulate`.

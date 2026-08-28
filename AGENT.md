# CEE (Conlang Evolution Engine) - LLM Agent Context

Tento soubor slouží jako vstupní bod a referenční manuál pro budoucí LLM agenty pracující na tomto projektu. Obsahuje klíčová architektonická pravidla a konvence. **ČTI PEČLIVĚ PŘED KAŽDÝM ZÁSAHEM DO KÓDU!**

## 1. Architektura Projektu

Projekt je rozdělen do několika logických bloků (uvnitř `src/cee`):
* **`core/`**: Datové modely.
  * `Word`: Drží kořenový `concept_id`, pole fonologických `Segment`ů a množinu `polysemy` (dodatečné sémantické významy).
  * `Lexicon`: Kolekce slov a metody na jejich vyhledávání (podporuje polysemii).
  * `State`: Historický uzel jazyka v čase. Obsahuje `Inventory` (aktivní fonémy).
* **`engine/`**: Logika simulace.
  * `phonology.py`: Zajišťuje překlad IPA stringů do rysových matic a zpět pomocí knihovny **Panphon**.
  * `rules.py`: Třída `RuleEvaluator`. Aplikuje historická hlásková pravidla na segmenty.
  * `fold.py`: `DerivationFold` spouští série pravidel nad celým lexikonem a aktualizuje stavový `Inventory`.
  * `semantics.py`: `SemanticEvaluator` spouští pravděpodobnostní Markovovy řetězce nad `SemanticGraph` a posouvá významy.
* **`semantics/`**: Abstrakce pro graf sémantických posunů z CLICS a DatSemShift.
* **`metrics/`**: Vyhodnocování úspěšnosti (např. pomocí **LingPy** na editační vzdálenosti).

## 2. Kritická Pravidla a Znalosti pro LLM

### 2.1 Panphon Rysy (Features)
Nejčastější chyba LLM! Knihovna `panphon` používá zkrácené názvy rysů.
* **ŠPATNĚ:** `voice`, `coronal`, `anterior`, `syllabic`, `consonantal`
* **SPRÁVNĚ:** `voi`, `cor`, `ant`, `syl`, `cons`
* Před psaním testů nebo YAML pravidel si *vždy* ověř přesný název rysu (např. `hi`, `lo`, `back`, `round`, `tense`, `cont`, `delrel`, `lat`, `nas`, `strid`).

### 2.2 Aplikátor Pravidel (Dvoufázovost)
Aplikace pravidel (`rules.py`) probíhá **dvoufázově**, aby se zamezilo artefaktům (self-feeding).
1. Fáze identifikace: Projde PŮVODNÍ segmenty a najde indexy, které splňují `target`, `env_before` a `env_after`.
2. Fáze mutace: Aplikuje změny z `action` simultánně pouze na nalezené indexy.
*Nikdy nemutuj segmenty během iterace, pokud zároveň kontroluješ jejich okolí!*

### 2.3 Sémantika a Polysemie
* Sémantická data (stahována `builder.py`) se generují z repozitářů Concepticon a DatSemShift do lokální cache `~/.cee/semantics/graph.graphml`. Tato data se **NIKDY necommitují do Gitu**.
* Sémantický posun neukládáme tak, že slovo ztratí kořenový `concept_id`. Místo toho slovo získává nová ID do atributu `polysemy` (množina). Slovo tak získává další významy jako v přirozených jazycích (např. "koruna" stromu / "koruna" krále).
* `SemanticEvaluator` **musí** využívat deterministický lokální `random.Random(seed)`, jinak by evoluční stromy generovaly při každém běhu jiná slova!

### 2.4 Změny a Hygiena
* Všechny konfigurační YAML, CSV datasetů a high-level dokumentace (`CEE_master.md`, `CEE_GDD.md`) jsou ignorovány v `.gitignore`. Držíme repozitář čistý pouze se zdrojovými kódy CEE samotného.
* CLI je stavěné přes `Typer` v `src/cee/cli/main.py`.

## 3. Workflow
Při rozšiřování CEE se drž klasického TDD přístupu. Otevři `tests/`, napiš test na novou lingvistickou funkcionalitu (simulace lenice, palatalizace, asimilace) s důrazem na **správné Panphon rysy** a teprve pak upravuj jádro.

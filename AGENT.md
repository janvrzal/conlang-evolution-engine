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
  * `rules.py`: Třída `Rule`. Aplikuje historická hlásková pravidla na segmenty (dvoufázově, viz 3.2).
  * `fold.py`: `DerivationFold` spouští série pravidel nad celým lexikonem a aktualizuje stavový `Inventory`.
  * `inventory.py`: `InventoryView` — inventář jako **dotazovatelná** množina přirozených tříd (`.has()`, `.matching()`, `.apply(rule)`). `Inventory` v `core/models` drží jen IPA řetězce a na rysové dotazy nestačí.
  * `simulator.py`: Globální "lockstep" simulátor větvení a kontaktů. Zvládá strom libovolné hloubky — každý uzel se odštěpí od rodiče v roce svého prvního pravidla.
  * `generator.py` a `schemas.py`: Plug-and-Play generátor náhodných pravidel s podporou presetů.
  * `topology.py`: Třídy pro síťový graf vývoje (hrany dědičnosti a kontaktů).
  * `semantics.py`: `SemanticEvaluator` spouští pravděpodobnostní Markovovy řetězce nad `SemanticGraph` a posouvá významy.
* **`semantics/`**: Abstrakce pro graf sémantických posunů z CLICS a DatSemShift.
* **`metrics/`**: Dvojí metrika dle `docs/CEE_master.md` 5.1. **Jedna nestačí** — měří dvě nezávislé osy a nesmí se míchat:
  * `validation.py`: **(B) fonetická vzdálenost** kognátů = *eroze* tvaru (LingPy).
  * `retention.py`: **(A) lexikální retence** = *náhrada* kořene. Diagnostický seznam je měřicí přístroj, ne vlastnost jazyka — musí být pro všechny porovnávané uzly **identický a fixní**, jinak jsou hodnoty nesrovnatelné.
* **`pipeline.py`**: Servisní vrstva mezi enginem a rozhraními. CLI i HTTP API volají `run_simulation()` a `build_branch_views()` odsud — logika simulace **nepatří** do `cli/` ani do `api/`.
* **`api/`**: FastAPI server. Jen překlad HTTP <-> volání `pipeline`. `ports.py` hledá volný port.
* **`cli/`**: Typer command-line interface.

## 3. Kritická Pravidla a Znalosti pro LLM

### 3.1 Panphon Rysy (Features)
Nejčastější chyba LLM! Knihovna `panphon` používá zkrácené názvy rysů.
* **ŠPATNĚ:** `voice`, `coronal`, `anterior`, `syllabic`, `consonantal`
* **SPRÁVNĚ:** `voi`, `cor`, `ant`, `syl`, `cons`
* Před psaním testů nebo YAML pravidel si *vždy* ověř přesný název rysu (např. `hi`, `lo`, `back`, `round`, `tense`, `cont`, `delrel`, `lat`, `nas`, `strid`).

### 3.1b Pasti rysových matic (ověř, než napíšeš `action`)
Správný název rysu nestačí. `action` musí vyrobit matici, která **přesně** odpovídá nějaké reálné hlásce — jinak `segment_to_ipa` sáhne po přibližné shodě a tiše vloží do výstupu cizí znak (např. tónovou značku `˧` místo `/b/`). Konkrétní past, na kterou už engine doplatil:

| Změna | Nestačí | Je potřeba | Proč |
|---|---|---|---|
| `o` → `u` | `{hi: +}` | `{hi: +, lab: +}` | panphon má `o` jako `[lab: -]`, ale `u` jako `[lab: +]` |
| `e` → `i` | — | `{hi: +}` | přední řada se liší jen v `[hi]`, je symetrická |
| `v` → `b`, `z` → `d` | `{cont: -}` | `{cont: -, strid: -}` | `v`/`z` jsou `[+strid]`, `b`/`d` jsou `[-strid]` |
| `ɣ` → `ɡ` | `{cont: -}` | `{cont: -}` | velára `[-strid]` už je, funguje samo |

Postup: rozdíl dvou hlásek si nech vypsat, nehádej ho.
```python
fa, fb = (
    mapper.parse_word("x", "v").segments[0].features,
    mapper.parse_word("x", "b").segments[0].features,
)
print({k: (fa[k], fb[k]) for k in fa if fa[k] != fb[k]})
```
K ověření slouží `FeatureMapper.is_exact_segment(segment)` → `False` znamená, že matice žádné hlásce neodpovídá. Hlídá to test `tests/test_schemas.py::test_vysledek_odpovida_realne_hlasce` nad každým schématem v `SCHEMA_REGISTRY`.

**Prostředí musí být splnitelné.** Segment je buď vokál `[syl: +, cons: -]`, nebo konsonant `[syl: -, cons: +]` — nikdy obojí. `env` typu `{"syl": "+", "cons": "+"}` proto nikdy nesedne a schéma je trvale mrtvé, aniž by cokoli spadlo. Kontrolu dělá `test_schema_realne_zasahne`.

### 3.2 Aplikátor Pravidel (Dvoufázovost)
Aplikace pravidel (`rules.py`) probíhá **dvoufázově**, aby se zamezilo artefaktům (self-feeding).
1. Fáze identifikace: Projde PŮVODNÍ segmenty a najde indexy, které splňují `target`, `env_before` a `env_after`.
2. Fáze mutace: Aplikuje změny z `action` simultánně pouze na nalezené indexy.
*Nikdy nemutuj segmenty během iterace, pokud zároveň kontroluješ jejich okolí!*

### 3.2b Kompozita a další per-uzel chování
Morfologické operace **nepatří natvrdo do `simulator.py`**. Složeniny předepisuje topologie u konkrétního uzlu:

```yaml
nodes:
  - id: north
    map:
      compound_head: initial   # nebo final
    compounds:
      - head: "město"
        modifier: "zlatý"
        id: "zlaté_město"
```
Chybějící `head`/`modifier` v lexikonu se ohlásí varováním, simulace nespadne.

### 3.2c Generátor se ptá inventáře (NEJDŮLEŽITĚJŠÍ)
Tohle je ústřední tvrzení projektu (`docs/CEE_master.md` 4.3): **cílová třída pravidla je dotaz do aktuálního inventáře. Pravidlo mířící na prázdnou třídu se nemá vygenerovat.**

* `Schema.build()` popisuje jen *tvar* změny. Kontrolu obsazenosti tříd dělá `Schema.generate_rule()` na jednom místě — potomci ji **nepřepisují**.
* Vrátí-li schéma `None`, generátor losuje jiné; slot v chronologii se neztratí (`MAX_ATTEMPTS_PER_SLOT`).
* Inventář se mezi pravidly aktualizuje přes `InventoryView.apply()`, takže pozdější změna vidí, co jí ta předchozí připravila (feeding).
* Filtr věrohodnosti navíc zakazuje **okamžité zvrácení** předchozí změny (`generator._reverses`) — lenice hned následovaná ztrátou znělosti týchž hlásek je v reálných dějinách krajně vzácná.

Nové schéma proto vždy: (1) přidej třídu do `SCHEMA_REGISTRY`, (2) ověř, že `tests/test_schemas.py` projde — parametrizované testy hlídají, že schéma někde zasáhne, že nevyrobí neexistující hlásku a že odmítne prázdný inventář.

### 3.3 Sémantika a Polysemie
* Sémantická data se generují z repozitářů Concepticon a DatSemShift do lokální cache `~/.cee/semantics/graph.graphml`. Tato data se **NIKDY necommitují do Gitu**.
* Sémantický posun neukládáme tak, že slovo ztratí kořenový `concept_id`. Místo toho slovo získává nová ID do atributu `polysemy` (množina). Slovo tak získává další významy jako v přirozených jazycích (např. "koruna" stromu / "koruna" krále).
* `SemanticEvaluator` **musí** využívat deterministický lokální `random.Random(seed)`, jinak by evoluční stromy generovaly při každém běhu jiná slova!

### 3.4 Změny a Hygiena
* Všechny konfigurační YAML, CSV datasetů a high-level dokumentace (`CEE_master.md`, `CEE_GDD.md`) jsou ignorovány v `.gitignore` (respektive by neměly být commitovány pokud to není explicitně potřeba). Držíme repozitář čistý pouze se zdrojovými kódy CEE samotného.
* CLI je stavěné přes `Typer` v `src/cee/cli/main.py`. Varování z enginu (`warnings.warn`) se uživateli zobrazují jako `⚠️` hlášky — používej je všude, kde by engine jinak tiše nic neudělal.
* Vstupy, bez kterých projekt nejde ověřit (fixtures `tests/fixtures/`, data balíčku `src/cee/data/`, ukázkové scénáře `scenario_*.yaml`), jsou z ignorování **výslovně vyjmuté** v `.gitignore`. Negace musí zůstat před závěrečným blokem `__pycache__/`, protože pozdější pravidlo přebíjí dřívější.

## 4. Workflow
Předtím, než začnete psát kód:
1. Přečtěte si `docs/CEE_master.md` pro hluboký architektonický kontext.
2. Nejprve detailně vymyslete postup implementace, dbejte na to, aby implementace nové featury nezasahovala do funkčnosti ostatních.
3. Při rozšiřování stávající featury je potřeba zachovat její funkcionalitu, pokud požadavek od uživatele tvrdí něco jiného, je potřeba nejprve se ho zeptat, která verze je správná.
2. Dodržujte existující návrhové vzory (např. používání `dataclasses`).
3. Při rozšiřování CEE se drž klasického TDD přístupu. Otevři `tests/`, napiš test na novou lingvistickou funkcionalitu (simulace lenice, palatalizace, asimilace) s důrazem na **správné Panphon rysy** a teprve pak upravuj jádro.
4. Používejte existující testovací scénáře (např. `scenario_generator.yaml`) pro otestování vašich úprav pomocí `cee simulate`.

## 5. Aktuální úkoly a cíle (Current Tasks)
`AGENT.md` není roadmapa. Aktuální implementovaný rozsah a vědomé mezery
jsou v `docs/CURRENT_STATE.md`; tam se stav udržuje při každém dokončeném
milníku.

### 5.1 Co už je součástí jádra

- Nepodmíněná i podmíněná zvuková schémata, prosodie a derivační kontrakty.
- CLICS4/DatSemShift s lokální cache a fallbackem, izoglosa v UI.
- PHOIBLE jako volitelný inventářový filtr (`cee phonology update-data`).
  Globální váhy změn vznikají pouze z odděleného, licenčně auditovaného
  manifestu; synchronní inventáře ani neorientované kognátní formy nejsou
  zdrojem směrovaných změn.

### 5.2 Co nesmí agent prezentovat jako hotové

- Vědecká kalibrace V2a/V2b proti reálným rodinám.
- Content-addressed hash stavů, rerolly/freeze a cache podle hashů.
- CLDF, Lexurgy, PDF a Anki exporty.
- Plnohodnotný sociolingvistický agentový model nebo biomová maska.

# Pokyny pro LLM a Agenty

Tento soubor slouží jako vstupní bod pro jakékoliv AI agenty a jazykové modely (LLM), které pracují na vývoji Conlang Evolution Engine (CEE).

## Co je CEE?
CEE je deterministický simulátor vývoje jazykových rodin v čase a prostoru (na mapě).
Cílem projektu je umožnit worldbuilderům (autorům fantasy a sci-fi) simulovat vznik reálně působících jazykových rodin, aniž by museli ručně aplikovat stovky zvukových změn na tisíce slov.

## Základní principy a pravidla (MUST FOLLOW)
1. **Determinismus a reprodukovatelnost:** Jakýkoliv běh simulace musí při stejném nastavení a stejném "seedu" vygenerovat 100% stejný výsledek. Všechna náhodnost je řízena pomocí fixních seedů.
2. **Offline sémantika a jazykový engine:** Nezapojujeme živé LLM API do samotného běhu simulátoru! LLM se používá pouze pro **offline** úkoly (jako extrakce dat, generování vstupních slovníků z JSON/CSV, nebo psaní kódů enginu). Při samotné generaci zvukových změn nebo sémantických posunů používá CEE vlastní kód a lokální Markovovy řetězce (s váhami v YAML presetech).
3. **Data nepatří na Git:** Složky jako `runs/`, výstupní `.csv` soubory a vygenerovaná velká data necommitujeme.
4. **Vlastnosti slova (`origin_year` atd.):** Slova musí nést historii. Například výpůjčky dostávají `origin_year`, díky kterému unikají starším zvukovým změnám. Tento systém se používá místo psaní složitých `IF` bloků a udržuje kód elegantní.

## Architektura kódu
Kód je dělen do následujících modulů ve složce `src/cee`:
- `core/`: Základní modely dat (Lexicon, Word, State, Inventory).
- `engine/`: Logika simulace.
  - `phonology.py`: Definice IPA rysů (Features) a `FeatureMapper`.
  - `rules.py`: Fonologická pravidla (`Rule`).
  - `simulator.py`: Globální "lockstep" simulátor větvení a kontaktů.
  - `generator.py` a `schemas.py`: Plug-and-Play generátor náhodných pravidel s podporou presetů.
  - `topology.py`: Třídy pro síťový graf vývoje (hrany dědičnosti a kontaktů).
- `cli/`: Typer command-line interface.

## Jak přistupovat ke změnám?
Předtím, než začnete psát kód:
1. Přečtěte si `docs/CEE_master.md` pro hluboký architektonický kontext.
2. Dodržujte existující návrhové vzory (např. používání `dataclasses`).
3. Používejte existující testovací scénáře (např. `scenario_generator.yaml`) pro otestování vašich úprav pomocí `cee simulate`.

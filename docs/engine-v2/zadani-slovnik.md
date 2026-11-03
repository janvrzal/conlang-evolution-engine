# Zadání: vlastní pojmy a velikost slovníku (nástroje pro autora světa)

Přečti si:
- `docs/engine-v2/19-pojmy.md` (data o pojmech z WOLD, frekvence, plán
  kroků 3 a 4);
- `docs/engine-v2/16-rozhrani-ui.md` (specifikace světa pro UI);
- `src/cee/v2/spec.py` (`WorldSpec`), `src/cee/v2/concept_data.py`,
  `src/cee/v2/scenarios.py` (`DEFAULT_CONCEPTS`, `VERBS`, `UNINFLECTED`,
  `region_world`), `src/cee/v2/language/protoforms.py`,
  `scripts/build_v2_core_semantics.py`, `scripts/build_v2_concepts.py`.

## Cíl

Engine dnes simuluje pevných 149 pojmů. Autor světa má dostat dva nástroje:

1. **Velikost slovníku**: ve specifikaci světa zvolí, kolik pojmů se
   simuluje (např. `vocabulary: 149 | 200 | 500 | 1000`; výchozí =
   dnešních 149 `DEFAULT_CONCEPTS`, beze změny výsledků). Větší slovník =
   `DEFAULT_CONCEPTS` + další pojmy z katalogu WOLD
   (`concept_data.data()["catalog"]`, 1 458 významů) v deterministickém
   pořadí, které navrhneš a zdůvodníš (např. podle frekvence z dat, se
   základním seznamem WOLD napřed).
   - Validace specifikace (`spec.check`) vydá **varování** (ne chybu), že
     jiný slovník dá jiné výsledky než výchozí. Zjisti, jestli existuje
     mechanismus varování (`Issue` má jen chyby?), a když ne, přidej ho
     tak, aby ho UI mohlo zobrazit.
2. **Vlastní pojmy**: autor přidá pojmy, vymyšlené i reálné:
   - povinné je ID, volitelně anglický glos nebo vazba na Concepticon
     či WOLD (pak se frekvence, doména a půjčitelnost převezmou z dat);
   - dále volitelně doména (`concept_data.DOMAINS`), frekvence, slovní
     druh (podstatné jméno, sloveso, neohebné) a příbuzné pojmy pro
     posuny významu (seznam s typem vztahu a vahou);
   - co autor nezadá, doplní engine rozumnou výchozí hodnotou podle domény
     a dat (doménu `core`, průměrnou půjčitelnost a frekvenci pojme
     z katalogu) a zdokumentuje to.

## Co k tomu potřeba

- **Sémantické vztahy pro katalog**: `build_v2_core_semantics.py` dnes
  vyřízne vztahy (DatSemShift, CLICS⁴, obojí CC BY 4.0, data
  v `~/.cee/data`) jen pro `DEFAULT_CONCEPTS`. Rozšiř výřez na všechny
  pojmy katalogu WOLD s glosem Concepticonu. Ulož ho jako samostatný soubor,
  aby se výchozí `v2_core_semantics.json` nezměnil a výchozí výsledky
  zůstaly bitově stejné. Velikost souboru drž rozumnou (do pár MB, jinak
  komprese nebo jen vztahy nad prahem).
- **Slovní druh** pojmu z katalogu podle kategorie WOLD (Noun, Verb,
  Adjective, Function word, Adverb) místo ručních množin `VERBS`
  a `UNINFLECTED`, které platí jen pro výchozí pojmy. Výchozí pojmy si
  zatřídění ponechají.
- **Frekvence**: `concept_data.frequency` už umí katalog
  (`v2_concept_frequencies.json`); využij to i pro pojmy katalogu mimo
  `DEFAULT_CONCEPTS`. Dnes `frequency()` hledá jen v `concepts`.
- **Výkon**: změř čas a paměť světa `region_world` 3 × 2 kraje
  s 149, 500 a 1 000 pojmy (1 000 let) a zapiš výsledek. Velký slovník
  smí být pomalejší, ale je potřeba vědět o kolik.
- **Testy**: výchozí slovník dá stejné otisky; vlastní pojem se objeví ve
  slovní zásobě, dostane frekvenci a doménu a při zadaných příbuzných
  pojmech i posuny významu; slovník o 500 pojmech proběhne; varování se
  zobrazí; `spec` zamítne nesmyslné vstupy (neznámá doména, frekvence mimo
  rozsah, duplicitní ID, odkaz na neexistující příbuzný pojem).
- **Dokumentace**: nový oddíl v `docs/engine-v2/19-pojmy.md` a popis polí
  pro UI v `docs/engine-v2/16-rozhrani-ui.md`.

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-vocabulary`
  na větvi `engine-v2-vocabulary`. Jiné adresáře **neměň**. Souběžně jiný
  agent mění fonologii v Rustu (`phonology.py`, `language/bank.py`,
  `rust/`) a v `CEE-dynamika` se mění tlaky a změny slov
  (`pressures/lexical.py`, `changes/lexicon.py`, `variation.py`,
  `parameters.py`). Těchto souborů se pokud možno nedotýkej; když musíš,
  drž změny malé a napiš o nich.
- Python: `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`
  (z kořene worktree). Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM a běží na něm i další těžké úlohy. Pouštěj jen jeden
  těžký běh najednou a nejvýš 2 procesy. Žádný paralelní pytest. Skripty
  s `multiprocessing` vždy ze souboru.
- Nic neinstaluj (žádné balíčky ani do venv, ani do systému). Data jsou
  v `~/.cee/data`, a když něco chybí, napiš to.
- Commituj na `engine-v2-vocabulary` po malých krocích. Zpráva anglicky,
  na konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty (porušení = práce se nepřijme)

- **Výchozí svět beze změny**: `scripts/v2_digests.py` (`--quick` po
  každém kroku, celý na konci) vypíše přesně:
  ```
  phonology    37e949768bf1f5fe2e0bdb106d39cbf199b842c24750ced943ca4c4ba9f7d2f4
  morphology   1f082a14909f724f98a7fe6aa39c4d8fff092f32ac126b3d217d94eb824e423c
  syntax       c270c0b059eb21af1bb0fa68a17f6efd69eb895040cfafdb11c5d4e04a7ef531
  grid-5x5     f00c56442b3e798fe844df0678d7637de59906480528ce0acb416056efd2dc1f
  shift        45300517345cc5ff3e22a1ff39bf1b1e48b0365662a8e33ada1a95088b06872c
  island-city  d8801215f07f7ad45b657d15ca4c1def5d4678706c1af0603e4ca4eb08ffd2a7
  valley-50    a035aa06625e0293f67f487f69ba174367ae6c9e7f478402b2e5e118c01a8f7b
  ```
- **Determinismus**: žádné `hash()` ani `uuid4` a žádná iterace přes `set`,
  na jejímž pořadí záleží. Pořadí pojmů je deterministické a nezávisí na
  pořadí ve slovníku specifikace.
- **Licence dat**: jen CC0, CC BY, MIT, BSD. Každý nový datový soubor nese
  citaci, licenci a SHA-256 vstupů.
- **Žádné změny modelu**, konstant, `Parameters` ani bran. Existující testy
  neupravuj tak, aby prošly.
- Komentáře a docstringy piš česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` musí být čistý.

Na konci pusť celou sadu na pozadí
(`PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python -m pytest -q -p no:cacheprovider tests`).

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- nová pole specifikace (název, typ, výchozí hodnota, validace),
- pořadí pojmů velkého slovníku a proč,
- výřez sémantických vztahů pro katalog (velikost, pokrytí, zdroje),
- čas a paměť pro 149, 500 a 1 000 pojmů,
- otisky výchozího světa a výsledek celé sady,
- co nešlo a proč.

# Zadání: domény slov v mechanismech kontaktu (krok 3)

Přečti si:
- `docs/engine-v2/19-pojmy.md`: data o pojmech z WOLD (oblasti, domény,
  půjčitelnost), frekvence, plynulá výměna slov, slovník;
- `docs/engine-v2/17-pozadi-dejin.md`: kalibrace kontaktu, cizí elity,
  výpůjček, čtení;
- kód `src/cee/v2/contact.py` (`borrowing_factor`), `src/cee/v2/institutions.py`
  (`liturgy_factor`, `reading_factor`), `src/cee/v2/transmission.py`
  (kanály mezi jazyky, interference, čtení, škola, liturgie),
  `src/cee/v2/changes/lexicon.py` (`LexicalBorrowing`),
  `src/cee/v2/background.py` (`ForeignElite`, `TradeShift`),
  `src/cee/v2/events.py` (`Contact`, `Conquest`, `ReligiousChange`),
  `src/cee/v2/concept_data.py` (`domain`, `borrowed`) a
  `src/cee/v2/vocabulary.py` (domény a půjčitelnost vlastních pojmů autora).

## Proč

Slova procházejí přes hranici jazyka dnes stejně bez ohledu na to, co
znamenají a odkud přicházejí:
- mezi jazyky s váhou `0,5 × (1 − frekvence)`;
- liturgie s `1 − frekvence`;
- čtení s `1 − reading_core_resistance · frekvence`.

Ve skutečnosti se výpůjčky řídí oblastí významu a kontaktní situací:
- nová elita přinese slova moci a správy (normanská *duke, count, baron*;
  *earl* přežil);
- liturgie přinese slova víry;
- obchod přinese věci a zboží;
- čtení a škola přinesou učená slova.

WOLD (Haspelmath & Tadmor 2009, CC BY 4.0) to měří: oblasti se půjčují
od 0,08 (funkční slova) přes 0,15 (tělo) po 0,42 (náboženství) a 0,63
(moderní svět). U jednotlivých slov uvádí i kontaktní situaci a účinek
(`forms.csv`: `contact_situation`, `effect`).

## Cíl

1. **Půjčitelnost z dat**: místo `1 − frekvence` použij v kanálech mezi
   jazyky půjčitelnost pojmu z WOLD (`concept_data.borrowed`, u vlastních
   pojmů hodnotu autora nebo výchozí). Navrhni převod z půjčitelnosti na
   váhu kanálu a parametr pro jeho sílu. Frekvence může zůstat jako
   doplněk, pokud to data podpoří. WOLD skóre už frekvenci zčásti obsahuje.
2. **Domény podle kanálu**: každý kanál dostane váhy domén (`core`,
   `learned`, `culture`, `religion`, `power`):
   - cizí elita (`ForeignElite`, `Conquest`) zvýhodní `power`;
   - liturgie (`ReligiousChange`) `religion`;
   - čtení a škola `learned`;
   - obchod (`TradeShift`, `Contact`) `culture`;
   - obecný kontakt sousedů bez zvláštní váhy.

   Zjisti, jak kanál v přenosu poznat (kanály `transmission.prepare`,
   skupiny elity, vazby obchodu) a navrhni nejčistší řešení. Váhy budou
   parametry světa (`Parameters`, přes `parameters` ve specifikaci), aby
   je autor mohl ladit.
3. **Kalibrace proti WOLD**:
   - v kontaktním světě (např. `scripts/v2_calibrate_retention.py
     --contact`, případně s pozadím dějin) změř podíl přejatých slov po
     oblastech WOLD a porovnej ho s průměrnou půjčitelností oblastí
     ve WOLD; cíl je co nejvyšší pořadová korelace;
   - ve světě s elitou ověř, že slova `power` jsou mezi výpůjčkami
     výrazně nadreprezentovaná proti světu bez elity; s liturgií totéž pro
     `religion`;
   - kalibrační skript dej do `scripts/` a popiš ho.
4. **Brány a retence**: celá sada; audit bran (`scripts/v2_gate_rates.py`,
   seedy 101–120, porovnání před a po); retence izolovaná i s kontaktem
   (`v2_calibrate_retention.py --seeds 1-8`, s `--contact` i bez). Pozor
   hlavně na brány výpůjček (M5), superstrátu, liturgie, Fergusonovy
   diglosie a jazyka trhu (M6b). Brány ani seedy neupravuj tak, aby
   prošly. Když brána padá oprávněně (data ukážou, že tvrdí něco, co neplatí),
   zastav se a popiš to.
5. **Dokumentace**: oddíl v `docs/engine-v2/19-pojmy.md`, parametry
   v docstringu `Parameters`, aktualizace `05-specifikace.md` (známé mezery).

## Prostředí

- Pracuješ výhradně ve worktree `/Users/janvrzal/Documents/CEE-domains` na
  větvi `engine-v2-domains`. Jiné adresáře **neměň**. Fonologie v Rustu
  (`phonology.py`, `language/bank.py`, `rust/`) ani tlaky výměny slov
  (`pressures/lexical.py`, `Entrenchment`, `Motivation`) nejsou předmětem;
  když na ně narazíš, popiš to.
- Python spouštěj z kořene worktree:
  `PYTHONPATH=src:. /Users/janvrzal/Documents/CEE/.venv/bin/python`.
  Lint: `/Users/janvrzal/Documents/CEE/.venv/bin/ruff check src/cee/v2 tests/v2 scripts`.
- Stroj má 16 GB RAM. Pouštěj jeden těžký běh najednou a nejvýš 3 procesy.
  Žádný paralelní pytest. Skripty s `multiprocessing` vždy ze souboru
  (spawn), nikdy přes stdin. Pomocné soubory ukládej do `scripts/` nebo do
  worktree, ne do scratchpadu: ten stroj průběžně čistí.
- Nic neinstaluj. Data jsou v `~/.cee/data` (WOLD v `~/.cee/data/wold`).
- Commituj na `engine-v2-domains` po malých krocích. Zpráva anglicky, na
  konci `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
  Soubory přidávej jménem. Nic nepushuj, nemerguj, nepoužívej `git stash`.
  Když ti systém něco zamítne, neobcházej to a napiš to do zprávy.

## Invarianty

- Je to **vědomá změna modelu**, takže otisky se změní. Nové otisky zapiš
  do `scripts/v2_digests.py` (nový blok referencí s popisem) a do
  připnutého otisku v `tests/v2/test_v2_vocabulary.py` (`DEFAULT_DIGEST`),
  a to jen pokud se mění kvůli modelu.
- S novými váhami nastavenými neutrálně (všechny domény 1, půjčitelnost
  vypnutá) by měl model dát přesně dnešní otisky. Pokud to jde, udělej to
  tak a ověř to testem. Pokud to nejde, napiš proč.
- **Determinismus**: žádné `hash()` ani `uuid4` a žádná iterace přes `set`,
  na jejímž pořadí záleží.
- Checkpointy a pickle fungují (`tests/v2/test_v2_checkpoints.py`).
- Komentáře a docstringy piš česky ve stylu okolního kódu, identifikátory
  anglicky. `ruff` musí být čistý.

## Výstup

Závěrečnou zprávu napiš česky a nic nepřikrášluj. Má obsahovat:

- commity a co každý dělá,
- nové parametry (název, význam, výchozí hodnota, jak autor ladí),
- kalibrace: podíly výpůjček po oblastech proti WOLD (tabulka, korelace),
  efekt elity a liturgie (tabulka),
- audit bran před a po, retence před a po,
- otisky staré a nové, celá sada,
- co nešlo a proč.

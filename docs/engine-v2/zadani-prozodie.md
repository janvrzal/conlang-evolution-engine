# Zadání: prozódie a eroze koncovek (část D)

Datum: 30. 10. 2026. Navazuje na části A–C ve worktree `../CEE-typologie`,
větev `engine-v2-typologie`, od commitu `6f687b2`. Deník pokračuje
v `10-typologie.md`, oddíl „Část D“. Platí všechna společná pravidla
ze `zadani-typologie.md` (soubory uživatele, determinismus, licence,
pravidlo stochastických bran, sériové měření, commit po krocích jen po
potvrzení, nic nepushovat).

## Výchozí stav (ověřeno v kódu)

Engine přízvuk zná, ale jen v nejjednodušší podobě:

- `StressRule = Literal["initial", "penult", "final"]` a `stressed_nucleus`
  v `language/processes.py`. `Code.stress_rule` má výchozí `"penult"`
  a v `src/cee/v2` ho nikde nic nenastavuje ani nemění: **všechny jazyky
  mají přízvuk na předposlední slabice navždy.**
- `VowelReduction`, `Syncope` a `Apocope` už zasahují jen nepřízvučné
  slabiky (`stress="unstressed"`), `Diphthongization` jen přízvučné.
- Redukční změny mají `ease` +0,15 a `clarity` −0,15 až −0,2, takže
  `Articulation` a `Clarity` se zhruba vyruší. Navíc `FunctionalLoad`
  (`FUNCTIONAL_LOAD_SCALE = 5.0`) trestá splynutí tvarů, a eroze koncovky
  je přesně takové splynutí. `Clarity` trestá i podíl zkrácených slov.
- Dlouhé vokály (`aː` …) v tabulce hlásek jsou, ale žádná změna délku
  nevytváří ani nepoužívá. Tón není.

Z části C: `weakness` gramatických buněk zůstává ≤ 0,15, takže
`CategoryLoss` se nespustí a flexivní kategorie se nasytí (cíl C4
nesplněn). Proč koncovky neerodují, zatím **nevíme**. Kandidáti jsou
pevný přízvuk na předposlední slabice, slabá výhoda redukce v nepřízvučných
slabikách a ochrana koncovek tlakem `FunctionalLoad`.

## Cíl

1. Zjistit, proč koncovky neerodují.
2. Přidat prozodické mechanismy, které ve skutečných jazycích erozi řídí:
   různé pravidlo přízvuku, jeho změnu a sílu přízvuku.
3. Ověřit, zda se tím velký cyklus a zánik kategorií rozběhnou samy, bez
   kontrolovaných pokusů. Na čísla WALS se neladí, to je M7.

## Kroky

### D0: diagnóza eroze koncovek (bez změny modelu)

Skript `scripts/v2_ending_erosion.py`. Pro scénář části A (`village_grid(6,
…)`, `FULL_GRAMMAR`, seedy 1..20, 3 000 let) zaznamenej pro každý zvukový
proces, který zasahuje koncovku gramatické buňky (`OBJ`, `PL`, `PAST`, …):

- kolikrát byl navržen, jaký měl rozpad fitness podle tlaků (`Articulation`,
  `Clarity`, `FunctionalLoad`, `Phonotactics`, `Dispersion`, sociální)
  a jak skončil (zanikl, ustálil se, fonologizoval);
- totéž pro stejné procesy v kořenech, pro srovnání;
- rozložení `weakness` podle funkce a času.

Pak tři **diagnostické** pokusy, jen pro deník, bez změny výchozích hodnot:

1. `stress_rule` = `initial` / `penult` / `final` pro celý svět;
2. `FUNCTIONAL_LOAD_SCALE` ∈ {0; 2,5; 5};
3. kombinace `initial` × scale 2,5.

Výstup: tabulka `weakness` a podílu zaniklých či ustálených erozí koncovek
pro každou variantu a rozbor, který faktor erozi brzdí nejvíc. **Zastav se
a ukaž výsledky.** Podle nich se rozhodne, které z kroků D1–D3 dávají smysl.

Ke `FunctionalLoad`: Wedel, Kaplan & Jackson (2013) doložili, že funkční
zátěž splynutí brzdí, ale nezastavuje. Pokud diagnóza ukáže, že hlavní
brzdou je `FUNCTIONAL_LOAD_SCALE`, hodnotu v D neměň: zapiš to jako
kalibrační otázku pro M7 s odkazem na velikost efektu v literatuře.

### D1: pravidlo přízvuku jako vlastnost jazyka

- Rozšířit `StressRule` o hodnoty, které WALS 14A rozlišuje a dají se
  vyjádřit nad posloupností jader: `initial`, `second`, `antepenult`,
  `penult`, `final`. Přízvuk podle váhy slabiky (WALS 15A) až v D3.
- Pravidlo přízvuku protojazyka: v pokusu „wals“ losovat z genusově
  váženého rozložení WALS 14A, přidat do `v2_typology.json` stejným
  buildem jako ostatní rysy. Výchozí scénáře a jejich otisky zůstávají na
  `penult`.
- Přidat 14A do měřidla typologie.

### D2: změna přízvuku a síla přízvuku

- **Posun přízvuku** jako proměnná se šířením mezi skupinami, stejně jako
  konstrukce (navrhne se, šíří, ustálí). Varianty jsou pravidla z D1;
  dominantní varianta určuje `code.stress_rule`. Zkontroluj, že keše
  tvarů a tabulky procesů (`bank.process_table(process, rule)`) se při
  změně pravidla správně zneplatní. Doložené směry s priory z literatury
  (např. posun k počátečnímu přízvuku v germánských jazycích a češtině).
  Přízvuk na poslední slabice ve francouzštině nevznikl změnou pravidla,
  ale ztrátou slabik po přízvuku; to má vzniknout samo z apokopy, ne
  zkratkou.
- **Síla přízvuku** (přízvukově vs. slabičně časované jazyky): vlastnost
  jazyka (např. `weak` / `strong`), která násobí výhodu redukčních změn
  v nepřízvučných slabikách. Jazyky se silným přízvukem redukují a srůstají
  víc (Dauer 1983; Bybee, Chakraborti, Jung & Scheibman 1998; Schiering
  2010). Přechod mezi hodnotami jako změna se zpětnou cestou. Velikost
  násobku zdůvodni, neladit.

### D3: délka a kompenzační prodloužení (volitelné, po potvrzení)

Kompenzační prodloužení (`CodaLoss` u vokálu v uzavřené slabice → dlouhý
vokál; Kavitskaya 2002), krácení dlouhých vokálů v nepřízvučných slabikách
a přízvuk podle váhy slabiky (WALS 15A). Začni jen po potvrzení po D2.
Tón a tonogeneze nejsou v rozsahu; zůstávají ve Známých mezerách.

### D4: ověření

1. Měřidlo z části A, pokusy `same_full` a `wals`, seedy 1..20, 5 000 let,
   obě čtení z C0. Navíc rozložení `weakness` a 14A.
2. Kvalitativní otázky (bez ladění na čísla):
   - Roste `weakness` koncovek v jazycích s počátečním nebo silným
     přízvukem výrazně víc než v jazycích s předposledním a slabým?
   - Spustí se `CategoryLoss` a velký cyklus (`Periphrasis` po erozi)
     aspoň v části seedů samy, bez kontrolovaných pokusů?
   - Má po 5 000 letech některý z rysů PL, DEFINITE, PAST a FUTURE
     entropii nad 0?

   Pokud ne, nahlas mechanismus. Žádné ladění konstant do shody.
3. Brány podle pravidla stochastických bran; při selhání míra průchodu
   před a po, nic neměnit bez mého rozhodnutí. Otisky se změní jen tam,
   kde se změní chování; zapiš nové. `valley-50` nejvýš +10 % proti
   `6f687b2` ze sériového páru; výjimku schvaluji jen já.
4. `05-specifikace.md`: Známé mezery (přízvuk, délka, tón) aktualizovat
   podle výsledku.

Brána D: D0–D2 a D4 hotové (D3 jen po potvrzení), `ruff` a `mypy` čisté
v dotčeném rozsahu, celá sada `pytest -q` prochází, deník s tabulkami.

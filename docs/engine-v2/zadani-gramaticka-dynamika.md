# Zadání: gramatická dynamika (část C)

Datum: 30. 10. 2026. Navazuje na části A a B ze zadání
[`zadani-typologie.md`](zadani-typologie.md), ve stejném worktree
`../CEE-typologie` a na stejné větvi `engine-v2-typologie`. **Začni až po
potvrzení a commitu části B.** Deník pokračuje v `10-typologie.md`, oddíl
„Část C“.

Platí všechna společná pravidla ze `zadani-typologie.md`: necommitnuté
soubory uživatele ve sdíleném checkoutu, determinismus, licence dat,
pravidlo stochastických bran z `AGENT.md`, sériové měření, commit po krocích
jen po potvrzení.

## Co ukázala část A

1. **Při stejném startu se gramatika 5 000 let nehne.** Všech 20 jazyků
   skončí s tím, s čím začalo. Gramatika se pohne jen po erozi koncovky a ta
   je vzácná (Známé mezery). Člen a budoucí čas navíc nemohou vzniknout, protože
   ve `SYNTAX_GRAMMAR` vůbec nejsou, a funkce mimo profil nemá místo pro inovaci.
2. **Při startu z WALS kategorie jen přibývají.** Člen, minulý čas, plurál
   i inflexní budoucnost mají do 2 000–3 000 let všechny jazyky. Ve WALS
   (genusově váženě) chybí člen 39 % a minulý čas 45 % jazyků.
3. **Vznikají příliš rychle.** Člen se objeví v 18/20 jazyků do 1 000 let.

### Příčina v kódu

- Žádná změna v `changes/syntax.py` nevede do `zero`. Cesta je jen
  `zero → opis → přiklonka → koncovka`.
- `Expressivity` = `need × strength`. `strength` opisu je vždy 1, `zero`
  vždy 0 (`syntax.strength`). Jediná protiváha je `Economy` = −0,15 za slovo.
  U členu (`need` 0,25) tedy opis vyhrává o +0,10, u plurálu o +0,45, vždy
  a ve všech jazycích. Model nezná jiný způsob, jak funkci splnit, než
  gramatickou kategorii. Skutečné jazyky bez minulého času nekomunikují hůř:
  nesou čas videm, příslovci a kontextem.
- Mechanismus náhradní strategie v katalogu existuje (`compensates`:
  pevný slovosled nese roli pádu), ale používá ho jen `ORDER → OBJ`.
- `Fusion` tlačí jen dopředu (to je správně, gramatikalizace je
  jednosměrná). Cyklus se ale uzavírá jen tehdy, když koncovka eroduje
  a nastoupí *nový* opis. Zánik bez obnovy neexistuje.

## Cíl

Model má mít oba stabilní stavy: jazyk s kategorií i jazyk bez ní, a cesty
mezi nimi oběma směry. Nejde o kalibraci tempa na WALS, to je M7. Cílem je,
aby kalibrace měla co ladit.

## Kroky

### C0: měřidlo podle povrchového kontrastu (bez změny modelu)

`metrics.typology_profile` dnes počítá `synthetic` jako „přítomné“ i tehdy,
když koncovky splynuly. Doplň druhé čtení: syntetická konstrukce je přítomná,
jen když `syntax.weakness` funkce je pod prahem. Práh odvoď z významu
`weakness` (podíl splynulých tvarů), zdůvodni ho v deníku a nevolej ho podle
výsledků. Report ukazuje obě čtení vedle sebe.

Přeměř části A (oba pokusy, seedy 1..20) s novým čtením. **Pokud se obraz
podstatně změní (např. velká část „přítomných“ kategorií je ve skutečnosti
splynulá), zastav se a nahlas to.** Pak by problém byl jinde, než si myslíme.

Otisky beze změny.

### C1: úplná gramatika pro pokusy

Přidej `FULL_GRAMMAR`: `SYNTAX_GRAMMAR` plus všechny funkce katalogu, které
v něm chybí, jako `zero`. **Výchozí `SYNTAX_GRAMMAR` neměň**, závisí na ní
brány a otisky. Pokus „same“ z části A opakuj i s `FULL_GRAMMAR`. Zda se
má stát výchozí, rozhodne uživatel.

### C2: náhradní strategie přes `compensates`

Funkce, kterou jazyk gramaticky nevyjadřuje, nemusí být nevyjádřená. Navrhni
a implementuj, jak náhradní strategie sníží tlak k vytvoření kategorie.
Možnosti (vyber a zdůvodni, případně navrhni lepší):

1. **Nové funkce v katalogu**, které jiné funkce zastoupí, stejným
   mechanismem jako `ORDER → OBJ`. Například vid (`ASPECT`) zastoupí `PAST`.
   Pro člen zvaž ukazovací zájmeno bez gramatikalizace nebo pozici tématu.
   Nové funkce musí mít vlastní cesty a doložené zdroje.
2. **Kontextová síla `zero`.** `strength(zero)` nebude 0, ale bude odpovídat
   tomu, jak dobře funkci nese kontext. Hodnota je vlastnost funkce
   v katalogu (`context` vedle `need`), ne konstanta pro všechny.

Rozhodující je, aby `Expressivity` u kompenzované nebo kontextem nesené
funkce netlačila k nové kategorii stejně silně jako u funkce, která nemá
žádné vyjádření. Hodnoty z literatury (Bybee, Perkins & Pagliuca 1994;
Dahl 1985; Heine & Kuteva 2002; Dryer 2013 k 37A), citace v katalogu
a docstringu.

### C3: zánik kategorie

Nová změna (např. `CategoryLoss`, šablona `inflection`): syntetická nebo opisná
konstrukce přejde do `zero`. Zánik se nesmí spouštět jen vysokou `weakness`
(která podle měření C0 v modelu samovolně téměř nenastává), ale primárně
nízkou potřebou po odečtu kompenzace z C2 (funkce saturovaná kontextem nebo
náhradní strategií, kde `effective_need` klesne k nule a převáží `Economy`).
Vysoká `weakness` (pokud koncovky splynou a nic je neobnovuje) zůstává doplňkovým
spouštěčem. Pravděpodobnost úměrná poklesu efektivní potřeby a slabosti vyjádření.
Konstanty zdůvodnit v docstringu analogií s ostatními změnami (`base_rate` ~ 0,01–0,03),
neladit na shodu s WALS.

- Doložené typy zániku uveď v docstringu: ztráta pádů v angličtině
  a románských jazycích (zastoupena slovosledem), ztráta rodu v angličtině,
  ztráta préterita v jihoněmeckých nářečích (nahrazena perfektem, tedy
  obnovou, ne zánikem; uveď to jako protipříklad).
- Kontakt: v M5/M6b už klesá složitost s podílem L2 mluvčích. Ověř, zda tento
  mechanismus zasahuje i konstrukce. Pokud ne, navrhni napojení, ale
  neimplementuj ho bez potvrzení.
- `Fusion` zůstává jednosměrný. Zánik není zpětná gramatikalizace, je to
  konec cyklu.

### C4: ověření

1. Pokusy části A (oba) a „same“ s `FULL_GRAMMAR`, seedy 1..20, 5 000 let,
   obě čtení z C0. Do deníku tabulky před a po.
2. Kvalitativní cíl, bez ladění na čísla:
   - při startu z WALS nemá žádný z rysů PL, DEFINITE, PAST a FUTURE po
     5 000 letech entropii 0;
   - při stejném startu s `FULL_GRAMMAR` vznikne pestrost aspoň u dvou rysů.

   Pokud cíl nevyjde, nahlas mechanismus, nelaď konstanty do shody.
   Kvantitativní shoda s WALS je práce M7.
3. Konstanty nových změn a tlaků mají řádovou hodnotu z literatury nebo
   z analogie se stávajícími (`base_rate` syntaktických změn je 0,01–0,05),
   zdůvodněnou v docstringu. Žádný průzkum konstant, který maximalizuje
   shodu s WALS.
4. Brány: všechny musí projít podle pravidla stochastických bran. Pozor
   na `test_v2_m4b_gate.py::test_clen_vznikne_z_ukazovaciho_zajmena` (člen
   ve 2 ze 3 jazyků) a velký cyklus v M4. Pokud brána padne, protože model
   je teď realističtější (člen nevznikne všude), **neměň ji**. Změř míru
   průchodu před a po, nahlas a navrhni úpravu. Rozhodne uživatel.
5. Otisky se změní jen u scénářů se syntaxí; nové zapsat. `valley-50`
   nejvýš o 5 % pomalejší (sériový pár).
6. Ve `05-specifikace.md` aktualizovat Známé mezery: řádek „Člen vznikne ve
   všech jazycích“ podle výsledku, nové mezery doplnit.

Brána C: C0–C4 hotové, `ruff` a `mypy` čisté v dotčeném rozsahu, celá sada
`pytest -q` prochází, deník s tabulkami a rozborem.

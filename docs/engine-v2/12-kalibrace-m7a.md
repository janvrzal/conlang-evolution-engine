# Kalibrace M7a: stacionarita gramatické typologie

Datum: 31. 10. 2026. Větev `engine-v2-dynamika`, harness
`scripts/v2_calibrate.py` (commit `6d4d676`). Navazuje na test dosažitelnosti
v [`11-gramaticka-dynamika.md`](11-gramaticka-dynamika.md).

## Protokol

Každé nastavení parametrů se hodnotí dvěma pokusy na stejných seedech
(společná náhoda): `village_grid(6)`, 5 000 let, odečty v roce 0, 2 000
a 5 000.

- **`wals`**: gramatika i přízvuk protojazyka losované z WALS. Stacionarita =
  průměrná Hellingerova vzdálenost rozložení 33A, 37A, 66A a 67A od WALS
  v letech 2 000 a 5 000.
- **`family`**: všechny seedy začínají stejnou `FULL_GRAMMAR` (člen a budoucí
  čas chybí). Obrat uvnitř rodiny = normovaná entropie 37A a 67A po 5 000
  letech; trest `max(0; 0,5 − E)`. Bez tohoto členu by vyhrál model, který se
  nemění vůbec.
- **Kontakt** (předpoklad o prostředí, nekalibruje se): stálý podíl L2
  mluvčích 0 / 0,1 / 0,3 podle `seed % 3`.
- Ztráta = stacionarita + 0,5 × trest obratu.

Prostor (7 rozměrů, výchozí hodnoty uvnitř): `context` členu (0,10–0,50),
budoucího času (0,20–0,60), plurálu a minulého času (0,10–0,50),
`learnability_strength` (0,25–1,5), `category_loss_l2_boost` (1–8),
`change_rates["periphrasis"]` (0,25–2; tempo vzniku opisu, nový parametr
`Parameters.change_rates`).

Hledání: výchozí bod + 32 bodů latinské hyperkrychle (seedy 1..8), zjemnění
kolem čtyř nejlepších (24 bodů), ověření tří nejlepších a výchozího bodu na
odložených seedech 101..112. Čtyři paralelní procesy, 46 minut.

## Výsledky

Odložené seedy 101..112 (H = průměr let 2 000 a 5 000; E = entropie v rodině):

| Nastavení | Ztráta | H 33A | H 37A | H 66A | H 67A | E člen | E bud. čas |
|---|---:|---:|---:|---:|---:|---:|---:|
| výchozí | 0,482 | 0,25 | 0,37 | 0,51 | 0,30 | 0,00 | 0,92 |
| nejlepší z hledání (č. 1) | 0,250 | 0,25 | 0,18 | 0,51 | 0,06 | 1,00 | 0,95 |
| nejlepší z hledání (č. 2) | 0,217 | 0,25 | 0,04 | 0,51 | 0,07 | 0,81 | 0,95 |
| nejlepší z hledání (č. 3) | 0,203 | 0,15 | 0,11 | 0,51 | 0,04 | 0,98 | 0,92 |
| **úsporný: jen `context` členu 0,40 a bud. času 0,45** | **0,238** | 0,25 | 0,10 | 0,51 | 0,09 | 1,00 | 0,85 |
| jen `context` členu 0,40 | 0,289 | 0,25 | 0,10 | 0,51 | 0,30 | 0,98 | 0,92 |
| úsporný + `context` plurálu a min. času 0,50 | 0,233 | 0,25 | 0,11 | 0,51 | 0,06 | 1,00 | 0,85 |

### Co je určené a co ne

- **Určené: kontext členu a budoucího času.** Všechny dobré body mají
  `context` členu 0,33–0,48 a budoucího času 0,29–0,55; výchozí 0,22 a 0,35
  jsou mimo. Úsporný kandidát, který mění jen tyto dva parametry, má na
  odložených seedech skoro celé zlepšení (0,238 proti 0,482; nejlepší bod
  0,203). Člen pak nevzniká všude a v rodině se jazyky liší (E 1,0 místo 0).
- **Neurčené: síla kontaktu a tempo opisu.** `learnability_strength`,
  `category_loss_l2_boost` i tempo opisu leží u dobrých bodů napříč celým
  rozsahem; ztráta na ně v tomto protokolu skoro nereaguje. Výchozí hodnoty
  nechat, dokud je neurčí jiný cíl (zpětný test latiny).

### Strukturální nález: minulý čas a plurál

**Minulý čas (66A, H 0,51) a plurál (33A, H 0,25) se nehnou v žádném bodě
prostoru.** Po 5 000 letech je mají všechny jazyky, i když WALS má 45 %
jazyků bez minulého času a 12 % bez plurálu. Ani `context` 0,5 nepomůže:
nula vyhraje nad volným opisem jen tehdy, když `need × (1 − context) ≤ 0,15`
(cena slova), tedy u minulého času (`need` 1,0) až při kontextu 0,85
a u plurálu (`need` 0,6) při 0,75. To nejsou věrohodné hodnoty „kontextu“.

Jazyky bez minulého času ve skutečnosti nevyjadřují čas kontextem, ale
**videm** (perfektivum, imperfektivum) a příslovci (Dahl 1985; Bybee, Perkins
& Pagliuca 1994). Jazyky bez povinného plurálu mají **obecné číslo
a klasifikátory** (Corbett 2000). Obojí v katalogu chybí. Mechanismus
náhrady (`compensates`) existuje, ale funkci, která by minulý čas nebo plurál
zastoupila, katalog nemá. Doplnit vid (s `compensates: [PAST]`)
a klasifikátory nebo obecné číslo (s `compensates: [PL]`) je rozšíření
gramatiky na úrovni b), ne kalibrace.

## Dopad na brány

Měřeno ve worktree `../CEE-m7a` (větev `engine-v2-m7a-candidate`) s úsporným
kandidátem jako výchozími hodnotami katalogu.
Kandidát je commit `f7237d9` na větvi `engine-v2-m7a-candidate` (jen
`v2_grammar.yaml`: `context` členu 0,40, budoucího času 0,45).

- **Otisky** všech sedmi scénářů beze změny (výchozí scénáře člen ani budoucí
  čas v gramatice nemají).
- **Rychlá sada**: 675 prošlo.
- **Brány**: 80 prošlo, 1 neprošla:
  `test_v2_m4b_gate.py::test_clen_vznikne_z_ukazovaciho_zajmena`
  (člen ve 2 ze 3 jazyků bez pádu za 3 000 let).
- **Míra průchodu této brány** s kandidátem (`v2_gate_rates.py`, seedy
  101..120): člen vznikne v **6/20** běhů (Wilson 95 % [0,145; 0,519]).
  Dříve 20/20.

Brána vynucuje přesně to, co kalibrace opravuje: člen vznikal všude. Za
3 000 let bez kontaktu vznikne nyní asi ve třetině jazyků; ve WALS má určitý
člen asi 61 % jazyků (genusově váženě), ale ty k němu měly i desetitisíce
let a kontakt.

## Doporučení

1. **Přijmout úsporného kandidáta** (kontext členu 0,40, budoucího času
   0,45) jako výchozí hodnoty. Ostatní parametry nechat, nejsou určené.
2. **Revidovat bránu `M4b::clen_vznikne`**: tvrdit vznik členu „aspoň
   v některých jazycích, ne ve všech“ místo „ve 2 ze 3“. Návrh: seedy 1..30,
   prochází, když člen vznikne aspoň v jednom a ne ve všech běhech;
   negativní kontrola bez zdrojových slov (`this`, `that`) musí dát 0.
   Při naměřené míře 30 % je pravděpodobnost falešného selhání pod 1 %
   (k = 1 z 30 při dolní mezi Wilsona 0,145). Mění se tím tvrzení brány,
   proto o tom rozhoduje uživatel.
3. **Rozšířit katalog o vid a obecné číslo nebo klasifikátory**, jinak
   minulý čas a plurál zůstanou nestacionární (H 0,51 a 0,25) za všech
   hodnot. Spolu s pády a předložkami jde o rozšíření gramatiky před latinským
   zpětným testem.

## Druhé kolo: vznik oddělený od obnovy a vid

Po prvním kole uživatel schválil přepracování mechanismů (commit `1da6ad7`):

1. **Vznik vs. obnova.** `Expressivity` uplatní u nevyjádřené funkce
   (`zero`) jen `emergence_need_scale` × potřeba. Tlak podle potřeby je
   doložený pro obnovu zeslabeného výrazu (Hopper & Traugott 2003); nová
   kategorie vzniká hlavně z častého užívání a expresivních inovací (Bybee
   2003; Haspelmath 1999). Výchozí 1,0 = dosavadní model.
2. **Obecná kompenzace.** Zastoupit funkci může kterákoli funkce katalogu
   s `compensates`; nese `coverage` její role (pevný slovosled pád 0,9 jako
   dosud). `syntax.carries_role` a `Ambiguity` platí obecně.
3. **Vid** (`ASPECT`, dokonavost ze slovesa „dokončit“, Bybee, Perkins
   & Pagliuca 1994) s `compensates: [PAST]`, `coverage` 0,7 (odhad). Je
   v `FULL_GRAMMAR` jako `zero`; výchozí scénáře ho nemají, otisky beze změny.

Prostor druhého kola: `emergence_need_scale` (0–1), `context` členu,
budoucího času, plurálu a minulého času, `coverage` vidu (0,4–0,9). Síla
kontaktu a tempo opisu na výchozích hodnotách (první kolo je neurčilo).
Stejný protokol a seedy, 44 minut.

| Nastavení (odložené seedy 101..112) | Ztráta | H 33A | H 37A | H 66A | H 67A | E člen | E bud. čas |
|---|---:|---:|---:|---:|---:|---:|---:|
| výchozí (s videm v gramatice) | 0,350 | 0,25 | 0,37 | 0,51 | 0,18 | 0,41 | 0,85 |
| nejlepší bod hledání | 0,143 | 0,25 | 0,23 | 0,06 | 0,04 | 1,00 | 0,68 |

Nejlepší bod: `emergence_need_scale` 0,59, `context` členu 0,16, budoucího
času 0,44, plurálu 0,10, minulého času 0,50, `coverage` vidu 0,90.

- **Minulý čas se pohnul.** H 66A klesla z 0,51 na 0,03–0,07; po 5 000 letech
  ho nemá 50–58 % jazyků (WALS 45 %). Jazyky bez minulého času nesou čas
  videm a nejsou tlačeny k vytvoření minulého času. Strukturální nález
  prvního kola tím je vyřešen mechanismem, ne číslem.
- **Plurál zůstává** (H 0,25, všechny jazyky ho mají) kromě bodů s nízkou
  škálou vzniku (0,27–0,33), kde se plurál drží v 12 % jazyků (H 0), ale
  člen pak vzniká málo. Globální škála vzniku nestačí; plurál potřebuje
  vlastní náhradu (obecné číslo, klasifikátory; Corbett 2000).
- **Určené:** `coverage` vidu vysoko (0,85–0,90, horní mez prostoru),
  `emergence_need_scale` 0,58–0,82. Ostatní slabě (korelace se ztrátou
  |r| ≤ 0,18).

### Ověření na 24 nových seedech (201..224)

| Kandidát | Ztráta | H 37A | H 66A | Jazyky bez min. času po 5 000 letech |
|---|---:|---:|---:|---:|
| výchozí | 0,267 | 0,23 | 0,51 | 0 % |
| nejlepší bod 2. kola | 0,126 | 0,09 | 0,14 | 67 % |
| **A**: `emergence_need_scale` 0,6, `context` členu 0,16, bud. času 0,44, `coverage` vidu 0,9 | **0,126** | 0,09 | 0,14 | 67 % |
| A + `context` min. času 0,5 | 0,126 | 0,09 | 0,14 | 67 % |
| C: škála vzniku 0,8, člen výchozí | 0,169 | 0,18 | 0,16 | 71 % |

Kandidát A mění jen určené parametry a je stejně dobrý jako nejlepší bod.
Kontext plurálu a minulého času nemá vliv. Minulý čas mírně přestřelí
(67 % proti 45 % ve WALS).

## Třetí kolo: obrat podle skutečných rodin z WALS

Commit `d637db9`. Build typologie zapisuje rozložení rysů uvnitř 11 rodin
a podrodin se stářím z literatury (`families` ve `v2_typology.json`).
Mladé (≈ 2 000 let: románské, slovanské, germánské, turkické) se srovnávají
s modelovou rodinou v roce 2 000, staré (≈ 4 000–8 500 let) v roce 5 000:

| | 33A | 37A | 66A | 67A |
|---|---:|---:|---:|---:|
| mladé rodiny, průměrná entropie | 0,00 | 0,22 | 0,00 | 0,00 |
| staré rodiny | 0,22 | 0,77 | 0,25 | 0,89 |

Hledání (4 parametry, odložené seedy 101..112):

| Kandidát | Ztráta | stacionarita | rodiny | E staré rodiny v r. 5 000 (37A / 66A / 67A) |
|---|---:|---:|---:|---|
| výchozí | 0,453 | 0,328 | 0,25 | 0,41 / 0,00 / 0,85 |
| nejlepší bod 3. kola (škála vzniku 0,26) | 0,157 | 0,052 | 0,21 | 0,65 / 0,00 / 0,00 |
| A (2. kolo) | 0,234 | 0,129 | 0,21 | 0,98 / 0,65 / 0,47 |

Mladé rodiny tlačí k velmi pomalé dynamice (škála vzniku ≈ 0,25): model pak
skoro stojí, je výborně stacionární, ale staré rodiny se v něm nerozrůzní
(budoucí čas E 0 proti 0,89). Kandidát A má stejný trest za rodiny a staré
rodiny pestré jako skutečné. **Tempo tedy zůstává neurčené.**

**Cíl podle rodin z WALS je nespolehlivý** (upozornil uživatel): tři ze
čtyř mladých jednotek jsou indoevropské a evropské, a WALS má 66A a 67A jen
ve vzorku asi 220 jazyků, takže mladý cíl pro minulý a budoucí čas stojí na
pěti germánských jazycích. Další krok: kalibrace „prajazyk → dcery“
(rekonstruovaná gramatika prajazyka, simulace po dobu stáří rodiny,
srovnání s rozložením u dcer) nad hustším Grambankem (CC BY 4.0) a s mladými
jednotkami z více rodin.

## Rozhodnutí

Uživatel schválil přijmout lepšího kandidáta jako výchozí stav s poznámkou
o předpokladech. Přijímá se **A**: výrazně lepší než dosavadní stav ve všech
třech protokolech a dynamika rodin realistická. Tempo (`emergence_need_scale`)
je jen předběžné, dokud ho neurčí kalibrace z prajazyků.

## Přijetí (commit `9c1cb95`)

- Výchozí `emergence_need_scale` 0,6 (`Parameters`), `context` členu 0,16,
  budoucího času 0,44, `coverage` vidu 0,9 (`v2_grammar.yaml`).
- Otisky všech sedmi scénářů beze změny: výchozí scénáře nemají nevyjádřené
  funkce, kterých se škála vzniku týká.
- Brány: 80 z 81 beze změny; `M4b::clen_vznikne` revidována. Audit
  s novými hodnotami: člen vznikne v 6/30 bězích (Wilson 95 % [0,095; 0,373]),
  negativní kontrola bez opisu a exaptace 0/10. Nové tvrzení: na seedech
  1..50 vznikne člen aspoň v jednom jazyce a ne ve všech (N ≥ 46 dá riziko
  falešného selhání pod 1 %); nová negativní kontrola
  `test_bez_opisu_a_exaptace_clen_nevznikne` (deterministická, v seznamu
  vyloučených z auditu). Brána M4b stojí asi 2 minuty navíc.
- Celá sada: 749 prošlo a test úplnosti registru bran po doplnění nové
  kontroly.

## Další krok (dohodnuto s uživatelem)

1. Scénář `region_world`: regiony zadané hustotou osídlení (ne počty) a
   sousedstvím, uvnitř síť vesnic, mezi regiony spoje přes pohraniční vesnice.
   Převod hustoty na efektivní velikost je kalibrační parametr.
2. Kalibrace prajazyk → dcery nad Grambankem a tabulkou rekonstrukcí.
3. Kalibrace M7 na `region_world` (prajazyky, stacionarita WALS, nářeční
   atlasy); tempo a měřítko.

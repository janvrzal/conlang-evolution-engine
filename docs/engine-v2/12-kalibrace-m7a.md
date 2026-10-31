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

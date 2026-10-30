# Gramatická dynamika a příprava M7 (část E)

Datum: 30. 10. 2026. Větev `engine-v2-dynamika` z `9321360` (konec části D),
worktree `../CEE-dynamika`. Práci dělá přímo Claude (bez Antigravity).

Sloučení `engine-v2-typologie` do `engine-v2` je připravené jako rychlé
převinutí (`engine-v2` je předkem), ale čeká na schválení uživatelem.

## Proč

Části C a D ukázaly, že flexivní kategorie (plurál, člen, minulý a budoucí
čas) se v modelu jen sčítají: po 5 000 letech je mají všechny jazyky
(entropie 0 ve všech pokusech). Stav funkce má čtyři hodnoty: `zero`, volný
opis, přiklonka a koncovka. Hrany před částí E:

| Z | Do | Změna | Podmínka |
|---|---|---|---|
| zero | opis | `Periphrasis` | zdroj ve slovníku |
| zero | koncovka | `Exaptation` | zbytková koncovka dárce |
| opis | přiklonka | `Cliticization` | vždy |
| přiklonka | koncovka | `Affixation` | vždy |
| oslabená koncovka | opis | `Periphrasis` | `weakness > 0` (obnova) |
| opis | zero | `CategoryLoss` | efektivní potřeba ≤ 0,15 (nikdy nenastalo) |
| koncovka | zero | `CategoryLoss` | `weakness ≥ 0,5` (nikdy nenastalo) |
| přiklonka | zero | — | chybí |

Jednosměrnost gramatikalizace platí pro *výraz* (slovo → přiklonka →
koncovka, zpět ne). *Kategorie* ale cyklí: koncovka nakonec zmizí a otevře
místo novému opisu (Hopper & Traugott 2003). Doložené cesty k `zero` jsou
tři: eroze bez obnovy, převzetí funkce (pevný slovosled místo pádu)
a kontakt, kdy dospělí L2 mluvčí vázané výrazy vypouštějí (Bentz & Winter
2013: jazyky s více L2 mluvčími mají méně pádů; afrikánština, kreoly).
Model měl jen první dvě, a i ty s prahem, který se nikdy nedosáhl.

## E1 a E2: zánik bez prahu a napojení kontaktu

- **`Construction.bound`**: koncovka nebo přiklonka.
- **`CategoryLoss`** bez prahu. Míra návrhu na místo je
  `base_rate × (weakness + l2_boost × l2_share)` pro vázaný výraz
  a `base_rate` pro volný opis. Nespolehlivější výraz se navrhuje
  k vypuštění častěji; o osudu rozhoduje selekce. Přibyla tak hrana
  přiklonka → zero (jen přes L2 mluvčí; přiklonka nemá vlastní `weakness`).
  `l2_boost = 4` jako u analogie (autorský odhad).
- **Tlak `Learnability`** (syntaktický): vázaný výraz má skóre
  `−LEARNABILITY_STRENGTH × l2_share`, volné slovo a `zero` nula. Síla 1,0
  jako `Teachability` u tvarů (autorský odhad; literatura podporuje směr).
  Ve skupině samých L2 mluvčích tak `zero` porazí neporušenou koncovku
  plurálu (Expressivity 0,6 − 1,0 proti 0,6 × 0,3).

Bez L2 mluvčích a bez eroze se nic nemění: výchozí scénáře bez kontaktu
mají stejné otisky.

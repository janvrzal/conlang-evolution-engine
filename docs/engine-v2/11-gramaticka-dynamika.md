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
  `−learnability_strength × l2_share` (`world.params`), volné slovo a `zero` nula. Síla 1,0
  jako `Teachability` u tvarů (autorský odhad; literatura podporuje směr).
  Ve skupině samých L2 mluvčích tak `zero` porazí neporušenou koncovku
  plurálu (Expressivity 0,6 − 1,0 proti 0,6 × 0,3).

Bez L2 mluvčích a bez eroze se nic nemění: výchozí scénáře bez kontaktu
mají stejné otisky.

Brány M3, M4, M4b, M5, M6a a M6b po E1/E2: 43 prošlo (6 min 7 s). Otisky:
změnily se jen scénáře s L2 mluvčími (`shift`, `island-city`), viz
`scripts/v2_digests.py`.

## Parametry jako data

Commit `b5aabec` (větev `engine-v2-params`, převinuto sem). Kalibrační
konstanty dynamiky jsou pole `Parameters` (`src/cee/v2/parameters.py`)
a patří světu (`world.params`): `functional_load_scale`,
`stress_strength_multiplier`, `coda_tolerance_scale`, `learnability_strength`,
`economy_word_cost`, `fusion_bonus`, `order_rigidity`,
`category_loss_l2_boost` a přepisy katalogu `grammar` (`need`, `context`
podle funkce). `catalog_for(world)` vrací katalog s přepisy a nikdy nemění
sdílený `catalog()`. Dva světy v jednom procesu tak mohou mít různé hodnoty;
hlídá to `tests/v2/test_v2_parameters.py`. Tuto chybu měla citlivostní
analýza C2.

Otisky všech sedmi scénářů beze změny, `valley-50` bez zpomalení.

Zbývají modulové konstanty mimo rozsah tohoto kroku: priory zvukových změn
a `CLARITY_DELETE_*` (`changes/sound.py`), konstanty kontaktu
(`contact.py`, `institutions.py`), prahy (`GRAMMAR_THRESHOLD`,
`ANALOGY_THRESHOLD`, `RESTRUCTURE_THRESHOLD`), `l2_boost` analogie, tabulky
vah tlaků (`SOUND_PRESSURES`, `SYNTAX_PRESSURES`, …), literály v `Clarity`
(1,5) a `Dispersion` (4,0), konstanty pozorovatele. Převést je před
kalibrací těchto oblastí.

## Oprava nestabilního testu

`test_v2_site_rate_index.py::test_sound_support_index_inventory_transition_and_mutations`
padal jen při `PYTHONHASHSEED=3`. Krok s přímou mutací `state.vocabulary`
bez logu porovnával průběžný index s referencí, která má keš podle
`state.version`; mutace bez logu verzi nezvýší. Pro 13 ze 149 slov (jediná
opora nějakého místa) se zastaralá reference lišila. **Index byl správně**:
produkční cesta (`leave_vocabulary` s logem) sedí pro všech 149 slov a po
zahození keší reference sedí i přímá mutace. Test teď keše zahazuje a slova
vybírá pevně (`d646583`).

Celá sada po E, parametrech a opravě testu: **740 prošlo** (8 min 22 s).

## Test dosažitelnosti cyklu kategorií

`scripts/v2_reachability.py`: start z WALS (gramatika i pravidlo přízvuku),
`village_grid(6)`, seedy 1..10, 5 000 let. Rohy prostoru po jednom
faktoru; kontakt jako stálý podíl L2 mluvčích ve všech skupinách.
Sloupce: přítomno v roce 0 → 2 000 → 5 000 (z jazyků), normovaná entropie
v roce 5 000, přechody přítomno → chybí / chybí → přítomno mezi odečty.

| Nastavení | Ustálené zániky | PL (33A) | člen (37A) | min. čas (66A) | bud. čas (67A) | max. weakness PL / PAST |
|---|---:|---|---|---|---|---|
| výchozí | 0 | 8→10→10, E 0, 0/2 | 2→9→10, E 0, 0/8 | 7→10→10, E 0, 0/3 | 7→8→10, E 0, 0/3 | 0,08 / 0,00 |
| silný přízvuk ×1,5 | 0 | 8→10→11, E 0 | 2→9→11, E 0 | 7→10→11, E 0 | 7→8→11, E 0 | 0,15 / 0,04 |
| silný přízvuk ×2,0 | 0 | 8→10→11, E 0 | 2→9→11, E 0 | 7→10→11, E 0 | 7→8→11, E 0 | 0,11 / 0,22 |
| ×2,0 + FL 1,0 | 0 | 8→10→11, E 0 | 2→9→11, E 0 | 7→10→11, E 0 | 7→8→11, E 0 | 0,13 / 0,22 |
| ×2,0 + FL 1,0 + tolerance kody 1,0 | 0 | 8→10→10, E 0 | 2→9→10, E 0 | 7→10→10, E 0 | 7→8→10, E 0 | 0,43 / 0,07 |
| L2 0,2 | 82 | 8→10→10, E 0 | 2→5→10, E 0, 0/8 | 7→10→10, E 0 | 7→8→8, **E 0,72**, 2/3 | 0,12 / 0,00 |
| L2 0,5 | 228 | 8→10→10, E 0 | 2→6→10, E 0, 1/9 | 7→10→10, E 0 | 7→0→0, E 0, 7/0 | 1,00 / 1,00 |
| L2 0,5, learnability 0,5 | 139 | 8→10→10, E 0 | 2→5→9, **E 0,47**, 1/8 | 7→10→10, E 0 | 7→6→7, **E 0,88**, 3/3 | 0,15 / 0,04 |

(Počet jazyků je 10, v některých bězích 11: jeden svět se rozpadl na dva
jazyky. U 67A je „chybí“ i volný opis; měřidlo počítá jen inflexní budoucnost.)

### Co z toho plyne

1. **Bez kontaktu cyklus nedosažitelný.** V žádném rohu prostoru (silný
   přízvuk ×2, slabá ochrana proti splynutí, plná tolerance kody) se
   neustálil jediný zánik. Nejvyšší `weakness` 0,43 (PL) nedosáhne hranice,
   kdy nula selekčně porazí koncovku (`1 − context`, 0,58–0,78). Eroze sama
   kategorii v 5 000 letech nezruší. To není číslo k doladění: koncovka
   s nulovou cenou prohraje jen tehdy, když se většina tvarů slije. Literatura
   (Trudgill 2011) skutečně spojuje ztrátu morfologie hlavně s kontaktem,
   takže izolované jazyky, které kategorie drží, nejsou nerealistické. Chybí
   ale ještě **kompenzace pádu předložkami**: latinské pády zanikly zároveň
   s nástupem předložek, model zná jako náhradu pádu jen pevný slovosled.
2. **S kontaktem se cyklus rozběhne.** Zániky se ustalují (82–228 za běh na
   10 seedů), budoucí čas a člen mají obousměrné přechody a entropii 0,47–0,88
   po 5 000 letech. Mechanismus části E tedy funguje.
3. **Plurál a minulý čas jsou odolné**: zanikly jen při L2 0,5, a to hned
   s `weakness` 1,0 (po zániku kategorie). Vysoká potřeba (1,0 a 0,6) je drží;
   45 % jazyků bez minulého času ve WALS jsou spíš jazyky, které ho nikdy
   nevyvinuly. To je otázka **tempa vzniku**, ne zániku.
4. **Tempo vzniku je druhá páka M7.** Člen v roce 2 000 má 9 z 10 jazyků ve
   všech nastaveních bez kontaktu (z výchozích 2). Ve skutečnosti
   člen vzniká staletí až tisíciletí a mnoho jazyků ho nikdy nevyvine. Citlivost
   C2 ukázala, že tempo vzniku řídí `context` (u členu nad 0,4 už nevzniká).
5. **L2 0,5 s plnou `Learnability` je extrém**: budoucí čas zmizí všude
   a nevrátí se (7 → 0). Síla 0,5 dává realističtější obraz (obousměrné
   přechody). Velikost patří do M7.

### Závěr pro M7

Cyklus kategorií je dosažitelný přes kontakt; erozí samotnou ne. Kalibrace
M7 má dvě páky: **tempo vzniku** (`context`, `need`, míry gramatikalizace)
a **sílu kontaktu** (`learnability_strength`, `category_loss_l2_boost`).
Cílem je stacionarita rozložení WALS. Před kalibrací doplnit kompenzaci pádu
předložkami (katalog: funkce s `compensates: [OBJ]` a vlastní cestou
gramatikalizace), protože bez ní nelze zpětně testovat latinu → románské
jazyky.

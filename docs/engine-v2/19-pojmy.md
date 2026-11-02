# Pojmy: oblasti, domény a půjčitelnost

Sepsáno 2026-11-02. Rozhodnutí s uživatelem: rovnováhu mezi lidovou řečí,
psanou normou a kontaktem engine nemá hledat jednou provždy, ale dát ji
autorovi světa do ruky jako parametry. K tomu musí engine vědět, k čemu
jsou slova vázaná: slova moci vymění nová elita, náboženská slova přijdou
s liturgií, věci obchodem a základní slovní zásoba zůstává.

## Data (krok 2, hotovo)

`cee.v2.concept_data` čte výřez z World Loanword Database
(Haspelmath & Tadmor 2009; CLDF lexibank/wold, commit `1df62b9`, CC BY 4.0)
v `cee/data/v2_concepts.json`, který staví `scripts/build_v2_concepts.py`:

- **pojmy enginu**: všech 149 pojmů `DEFAULT_CONCEPTS` má význam WOLD (přes
  glos Concepticonu; 15 ručně: `child` CHILD (YOUNG HUMAN), `god` DEITY,
  `hair` HAIR (HEAD), `know`, `lie` LIE DOWN, `louse` HEAD LOUSE, `mountain`
  MOUNTAIN OR HILL, `old`, `river` FLOWING BODY OF WATER, `spirit` SOUL,
  `stone` STONE OR ROCK, `war` BATTLE, `trade` TRADE OR BARTER, `close` SHUT,
  `ritual` WORSHIP);
- **katalog**: 1 458 významů WOLD doložených aspoň v 10 jazycích, tedy
  zásobník pro větší slovník; význam z jednoho slovníku (ID `…-999xx`, 1–2
  tvary, často skóre 1,0) se nebere;
- u každého významu: sémantická oblast (24), doména enginu, podíl jazyků
  s přejatým slovem (`borrowed`), skóre stáří a jednoduchosti, počet jazyků,
  zda patří do základního seznamu WOLD.

Půjčitelnost oblastí (průměr významů aspoň v 10 jazycích):

| oblast | doména | půjčitelnost |
|---|---|---|
| Modern world | culture | 0,63 |
| Religion and belief | religion | 0,42 |
| Clothing and grooming | culture | 0,38 |
| The house | culture | 0,37 |
| Law | power | 0,34 |
| Social and political relations | power | 0,32 |
| Food and drink, Agriculture | culture | 0,31 |
| Warfare and hunting | power | 0,29 |
| Animals | core | 0,28 |
| Possession, Basic actions and technology | culture | 0,26–0,27 |
| Cognition, Speech and language, Time | learned | 0,24 |
| Quantity, The physical world | culture, core | 0,22 |
| Emotions and values | learned | 0,21 |
| Motion | core | 0,19 |
| Kinship, The body, Spatial relations | core | 0,14–0,15 |
| Sense perception | core | 0,12 |
| Miscellaneous function words | core | 0,08 |

Z pojmů enginu se nejvíc půjčují *law* 0,63, *horse* 0,57, *boat* 0,54,
*king* 0,53 a *town* 0,47; nejméně *this* a *we* 0, *lie*, *stand*, *nose*
a *say* pod 0,03.

Oblasti moci se v průměru půjčují jen zhruba dvakrát víc než domácí jádro
a zhruba jako kultura. Že slova moci vymění nová elita (normanská *duke,
count, baron* proti přeživšímu *earl*), tedy není obecná vlastnost slov, ale
kontaktní situace: proto domény a ne jen půjčitelnost.

Přiřazení oblastí k doménám je náš úsudek (`DOMAINS` v build skriptu):

- `power`: společnost a politika, právo, válka a lov; působí na ně nová
  elita;
- `religion`: náboženství a víra; liturgie;
- `culture`: moderní svět, zemědělství, jídlo, oblečení, dům, vlastnictví,
  technika, kvantita; obchod a kontakt;
- `learned`: řeč a jazyk, myšlení, emoce a hodnoty, čas; čtení a škola;
- `core`: tělo, prostor, vnímání, pohyb, příroda, příbuzenství, zvířata,
  funkční slova.

Pojem mimo data (vlastní pojem autora) má doménu `core` a průměrnou
půjčitelnost katalogu, dokud je autor nezadá.

## Další kroky

3. **Domény v mechanismech**: cizí elita (`Conquest`, `ForeignElite`)
   přenáší hlavně slova `power`, liturgie hlavně `religion` (dnes váží
   jen vzácností), obchod (`TradeShift`) hlavně `culture`, čtení a škola
   hlavně `learned`, a všude podle půjčitelnosti. Váhy domén pro každý
   kanál budou parametry světa. Kalibrovat proti WOLD: podíl přejatých
   slov podle oblasti a kontaktní situace (WOLD má u slov i typ kontaktu
   a účinek: koexistence, náhrada, vložení).
4. **Nástroje pro autora**:
   - vlastní pojmy ve specifikaci světa (vymyšlené i reálné: název,
     doména, frekvence, volitelně příbuzné pojmy a půjčitelnost);
   - volba velikosti slovníku z katalogu (100, 200, 1 000 slov)
     s varováním, že jiný slovník dá jiné výsledky; tahy náhody jsou vázané
     na ID pojmu, takže stávající slova se nepřelosují, ale slova spolu
     soutěží;
   - parametry rovnováhy v UI.

   Pro velký slovník chybí:
   - **sémantické vztahy**: posuny významu z DatSemShift a kolexifikace
     z CLICS, CC BY 4.0. Výřez `build_v2_core_semantics.py` je jen pro
     149 pojmů a pro katalog se přegeneruje;
   - **frekvence pojmů**: data jsou hotová (viz níže); zbývá je použít
     v enginu místo generovaných.

## Frekvence pojmů (data hotová 2026-11-02)

`cee.v2.concept_data.log_frequency` a `frequency` čtou
`cee/data/v2_concept_frequencies.json` (`scripts/build_v2_concept_frequencies.py`):

- **Calude & Pagel (2011)**, seznam `Calude-2011-200` v Concepticonu
  (CC BY 4.0): log10 výskytů na milion slov pro 200 pojmů Swadeshova
  seznamu v 17 jazycích, průměr jazyků;
- **Leipzig Corpora Collection** (korpusy ke stažení pod CC BY; Goldhahn,
  Eckart & Quasthoff 2012) se slovy WOLD: angličtina, nizozemština,
  rumunština, indonéština, vietnamština (zprávy a Wikipedie, 300 tisíc
  vět), svahilština a malgaština (Wikipedie, 100 tisíc vět). Slovo
  sdílené více významy se dělí, víceslovná slova se vynechají. Každý jazyk
  se posune na stupnici Calude & Pagel a jazyky se zprůměrují. Na 182
  společných pojmech je korelace s Calude & Pagel 0,92.
- Odmítnuté zdroje: `wordfreq` (CC BY-SA), NoRaRe (CC BY-NC), Google Books
  Ngram (CC BY 3.0, ale jen angličtina a 7 GB dat).

Pokrytí: pojmy enginu 95 z Calude & Pagel a 54 z korpusů. Katalog 182
z Calude & Pagel, 1 271 z korpusů a 5 odhadem z vlastností WOLD. Nejčastější
pojmy enginu jsou *not, one, this, I, all, what, say*, nejvzácnější *bark,
thunder, fingernail, louse*; *war* vychází vysoko (2,99), protože polovina
korpusů jsou zprávy.

Převod na stupnici enginu: log10 0,5 → 0,05 a 3,5 → 0,9, mezi nimi
log-lineárně, mimo oříznuto (`LOG_FREQUENCY_ANCHORS`, `FREQUENCY_RANGE`).
Pojmy enginu pak mají medián 0,25 a kvartily 0,18 a 0,37; 0,9 mají
čtyři. Generované frekvence měly dvacet pojmů s 0,9 a ostatní
log-rovnoměrně 0,05–0,8.

## Frekvence v enginu (nasazeno 2026-11-02)

`protolanguage` bere frekvenci pojmu z dat, pokud ji data znají; pojem
mimo data (vlastní pojem autora) dostane generovanou jako dřív. Náhoda se
na generované frekvence spotřebuje vždy, takže tvary slov protojazyka se
nezměnily. Hranice košů souběžné variability jsou kvartily frekvencí
výchozí sady pojmů z dat (0,182 / 0,254 / 0,368, dříve 0,12 / 0,25 / 0,56)
a variabilita je podle nich přeměřená.

Frekvence z dat jsou užší než generované: aspoň 0,5 má 24 pojmů ze 149
(dříve 45). Dopady:

- **Brána výpůjček M5** měřila poměr průměrné frekvence přejatých pojmů
  k průměru všech (pod 0,7); s užšími frekvencemi vycházel 0,61–0,78 (9/20
  seedů), ačkoli výpůjčky jsou dál ze vzácnější části slovní zásoby.
  Nově (schváleno uživatelem) měří průměrné pořadí přejatých pojmů podle
  frekvence (0 = nejvzácnější), pod 0,5 = náhodný výběr; 0,29–0,41,
  20/20 seedů (s generovanými frekvencemi 0,25–0,35).
- **Metrika 2 M3b** (časté pojmy, frekvence aspoň 0,5, se nahrazují
  aspoň dvakrát pomaleji než ostatní): 20/20 → 16/20 seedů (p 0,11).
  Nahrazena cílem z dat, viz níže.
- Audit ostatních bran (seedy 101–120) v šumu, jazyk trhu M6b 15/20 →
  20/20; celá sada prošla.
- **Retence** (8 seedů, jádro, po tisíciletích): izolovaný jazyk 0,825 /
  0,913 / 0,968 (dříve 0,868 / 0,938 / 0,952), kontakt 0,830 / 0,901 /
  0,944. Základní slova byla dřív chráněná vysokou generovanou frekvencí
  (dvacet pojmů 0,9), teď mají frekvenci podle dat. Pro srovnání:
  glotochronologie udává pro stoslovný Swadeshův seznam asi 86 % za
  tisíciletí.

## Frekvence a rychlost výměny slov (kalibrace 2026-11-02)

Pagel, Atkinson & Meade (2007; Concepticon `Pagel-2007-200`, CC BY 4.0)
změřili rychlost výměny slov pro 200 pojmů Swadeshova seznamu. Rychlost
s frekvencí klesá jen mírně (sklon −0,18 v log10, r = −0,36 s frekvencemi
z dat; −0,17 a −0,38 s frekvencemi Pagel a kol.): horních 30 % pojmů podle
frekvence se vyměňuje rychlostí **0,70** ostatních (0,70–0,73 pro horních
10–50 %). Dřívější brána metriky 2 („aspoň dvakrát pomaleji“) tedy data
nepodporuje. Nově (schváleno uživatelem): horních 30 % pojmů podle pořadí
frekvence se nahrazuje pomaleji, poměr pod 0,85 (rezerva na šum dvou
seedů); 20/20 seedů 101–120.

Engine (`scripts/v2_calibrate_frequency.py`, kalibrační svět retence,
8 seedů, 2 000 let) chrání častá slova mnohem silněji:

| nastavení | poměr horních 30 % / ostatních | podíl nahrazených | pojmů bez výměny |
|---|---|---|---|
| převod šířky 3 (dnes), `entrenchment_strength` 0,3 | 0,26 | 0,24 | 77 ze 149 |
| převod šířky 4,5 | 0,68 | 0,26 | 72 |
| převod šířky 6 | 0,86 | 0,26 | 69 |
| šířka 3, síla 0,1 | 0,88 | 0,30 | 37 |
| šířka 3, síla 0 | 1,03 | 0,37 | 20 |
| šířka 3, exponent frekvence 0,5 | 0,03 | 0,14 | 103 |
| šířka 3, exponent 0,25 | 0,24 | 0,02 | 115 |

- Širší převod (4,5) odpovídá Pagel a kol., ale nejvyšší frekvence pojmu
  klesne na 0,66 a prahy morfologie (`conserved_frequency` 0,7) přestanou
  fungovat: padaly brány „častá slova si drží nepravidelnost“ (M3, S2)
  a liturgie (M6b). Převod proto zůstal šířky 3.
- Exponent frekvence (`Parameters.entrenchment_frequency_exponent`,
  výchozí 1 = beze změny) ochranu nesrovná: zvýší ji vzácným pojmům
  a výměna skoro ustane.
- **Strukturální rozdíl**: v enginu se ochrana zažitého slova chová jako
  práh. Polovina pojmů se za 2 000 let nevymění v žádné vesnici ani
  v jednom seedu, zbytek se mění hodně. U Pagel a kol. se rychlosti liší
  plynule (0,09–9,27 na 10 000 let) a nejstabilnější pojem by za 2 000 let
  vypadl asi ve 2 % případů. Jedním parametrem to nenaladit; souvisí to
  i s tím, u kterých pojmů jde nějakou změnu vůbec navrhnout. Otevřené pro
  kalibraci výměny slov (M7).

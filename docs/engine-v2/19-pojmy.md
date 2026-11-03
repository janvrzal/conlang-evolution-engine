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

   Pro velký slovník chybělo (hotovo, viz „Nástroje pro autora: slovník
   a vlastní pojmy“ níže):
   - **sémantické vztahy**: posuny významu z DatSemShift a kolexifikace
     z CLICS, CC BY 4.0. Výřez `build_v2_core_semantics.py` byl jen pro
     149 pojmů; pro katalog je samostatný soubor;
   - **frekvence pojmů**: data jsou hotová (viz níže) a engine je používá
     i pro pojmy katalogu.

   Zbývají parametry rovnováhy v UI a domény v mechanismech (krok 3).

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

## Plynulá výměna slov (2026-11-03)

Příčina prahové výměny: nové slovo mělo proti zažitému pevnou výhodu podle
druhu (`Motivation`: odvozenina a složenina +0,15, posun významu +0,05,
nový kořen −0,15), zažité slovo ochranu 0,3 × frekvence (`Entrenchment`).
Odvozenina tak vyhrála vždy u pojmů s frekvencí pod 0,5 a nikdy nad ní.

Nově každá lexikální inovace ve světě s tvary dostane náhodnou přitažlivost
~ N(0, `Parameters.lexical_appeal_sd`), stálou pro variantu: počítá se
z vlastního proudu náhody podle ID varianty (`changes.lexicon.with_appeal`),
takže je stejná ve všech skupinách a losy změn nemění. `Motivation` ji
přičte k výhodě podle druhu. Přibyly i parametry `entrenchment_base`
(ochrana nezávislá na frekvenci, výchozí 0) a
`entrenchment_frequency_exponent` (výchozí 1).

Kalibrace (síla ochrany 0,3; poměr = rychlost výměny horních 30 % pojmů
podle frekvence proti ostatním, Pagel a kol. 2007: 0,70):

| přitažlivost | poměr | retence jádra po tisíciletích | pojmy beze změny za 2 000 let |
|---|---|---|---|
| 0 (dříve) | 0,26 | 0,825 / 0,913 / 0,968 | 77 ze 149 |
| **0,03 (výchozí)** | **0,44** | **0,793 / 0,865 / 0,888** | **45** |
| 0,04 | 0,63 | 0,757 / 0,794 | 37 |
| 0,05 | 0,68 | 0,723 / 0,760 | 31 |

Glotochronologie udává 0,81–0,86 za tisíciletí. Širší přitažlivost se blíží
poměru z dat, ale slova se mění rychleji: každé nové slovo má šanci na
dobrý los, takže výměna roste s počtem inovací. Základní ochrana 0,6
s přitažlivostí 0,2 dala poměr 0,59 a retenci 0,82, ale v menších světech
se slovník zastavil a nepřekonaly ji výpůjčky. Padalo 9 bran (dělení
jazyků M6c, vzdálenost a zeměpis a liturgie M6b), proto základní ochrana
zůstala 0.

Výsledky s výchozí 0,03: celá sada prošla (1 069). Audit bran (seedy
101–120) proti stavu po nasazení frekvencí je v šumu: substrát M5 S3
7 → 2 z 20 (p 0,13), liturgie M6b 18 → 14 (p 0,24), migrace 13 → 10.
Kontakt: retence jádra 0,798 / 0,833 / 0,862, výpůjčky v jádru 5 %, 13 %,
18 % po 1 000, 2 000 a 3 000 letech.

Zbývá: 45 pojmů se nemění, protože u nich engine nemá z čeho tvořit nové
slovo. Pomůže větší výřez sémantických vztahů (katalog), pak kalibraci
zopakovat.

## Nástroje pro autora: slovník a vlastní pojmy (nasazeno 2026-11-02)

Krok 4 plánu. Specifikace světa (`WorldSpec`, viz
[`16-rozhrani-ui.md`](16-rozhrani-ui.md)) má dvě nová pole: `vocabulary`
(kolik pojmů) a `concepts` (vlastní pojmy). Kód je v `cee.v2.vocabulary`,
data o katalogu v `cee.v2.concept_data`. **Výchozí svět je bitově beze
změny**: bez těchto polí vychází stejný slovník (149 pojmů a šest zdrojů
gramatikalizace), stejný graf `core_graph()` a stejné otisky
`scripts/v2_digests.py` i světů ze specifikace.

### Velikost slovníku

`vocabulary` je celé číslo od 149 (výchozí) do 1 453 (149 pojmů enginu +
všech 1 304 pojmů katalogu mimo ně). UI nabízí předvolby 149, 200, 500
a 1 000. Menší slovník než 149 se nepřipouští: gramatikalizace potřebuje
zdroje a výchozí pojmy jsou jádro, na kterém stojí kalibrace.

**Pořadí pojmů** (jedno pro každou velikost; slovník o *n* pojmech je
začátkem slovníku o *n* + 1):

1. 149 pojmů `DEFAULT_CONCEPTS` v dnešním pořadí;
2. šest zdrojů gramatikalizace (*have, finish, go, want, thing, step*),
   které engine přidává vždy; stojí hned za výchozími pojmy, takže jejich
   tvary jsou stejné ve slovníku 149 i 1 453;
3. pojmy katalogu WOLD v pořadí `concept_data.catalog_order()`:
   - nejdřív 87 pojmů Swadeshova seznamu (to jsou pojmy s frekvencí z Calude
     & Pagel 2011: základní slovní zásoba, kterou má každý jazyk),
   - pak ostatní, v obou skupinách sestupně podle frekvence z dat, při shodě
     podle ID WOLD;
4. vlastní pojmy podle ID (pořadí ve specifikaci nerozhoduje).

Proč frekvence: nejčastější pojmy jsou ty, které slovník skutečného
jazyka obsahuje jako první a které nejvíc ovlivňují dynamiku (ochrana
zažitých slov, souběžná variabilita). Pořadí podle ID WOLD by dalo celé
tematické bloky po sobě (nejdřív celý svět přírody a pak zvířata) a skládání
slovníku by záviselo na tom, jak WOLD číslovala oblasti. Pole `core_list`
WOLD pořadí nerozliší: je pravdivé u všech 1 458 významů katalogu.
Nevýhoda: frekvence pojmů mimo Swadeshův seznam jsou z korpusů zpráv
a Wikipedie (viz výše), takže řada časově vázaných pojmů vychází výš, než
by v mluvené řeči.

Složení (domény včetně zdrojů gramatikalizace, který je `core`):

| slovník | pojmů | core | culture | learned | power | religion | ohebných | neohebných |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 149 | 155 | 102 | 23 | 20 | 8 | 2 | 122 | 33 |
| 200 | 206 | 128 | 36 | 31 | 9 | 2 | 144 | 62 |
| 500 | 506 | 245 | 120 | 108 | 28 | 5 | 360 | 146 |
| 1 000 | 1 006 | 436 | 302 | 171 | 78 | 19 | 801 | 205 |

**ID pojmů katalogu** (`concept_data.catalog_ids`) jsou odvozená z názvu
významu WOLD: bez členu *the* a *to*, malými písmeny, nealfanumerické znaky
na `-` (`the stone or rock` → `stone-or-rock`), číslo homonyma `(2)` jako
`-2`. Shoduje-li se ID s pojmem enginu nebo s dřívějším významem, přidá se
ID WOLD: hmyz *the fly* je `fly-3-83`, sloveso `fly` je pojem enginu.
Významy *to go, to have, to want, to finish, the thing* tu chybí: engine je
má jako zdroje gramatikalizace bez dat o frekvenci (výchozí svět se nesmí
změnit) a druhý pojem se stejným významem by jen zdvojil slova.

**Slovní druh** pojmu katalogu je podle kategorie WOLD: *Noun* → podstatné
jméno, *Verb* → sloveso, *Adjective, Function word, Adverb* → neohebné
(jako u výchozích pojmů, kde jsou přídavná jména v `UNINFLECTED`). Výchozí
pojmy si zatřídění ponechají z ručních množin `VERBS` a `UNINFLECTED`.

**Frekvence** pojmů katalogu se bere z dat jako u výchozích pojmů
(`concept_data.frequency`, převod na stupnici enginu beze změny).

**Varování**: jiný slovník než výchozí dá jiné výsledky. Slova nových
pojmů soutěží se stávajícími a kalibrace bran (frekvence, retence,
variabilita) platí jen pro výchozí slovník. `spec.check` proto vrátí
varování na cestě `vocabulary` (a `concepts` pro vlastní pojmy), které
svět nezastaví.

Co se při větším slovníku **nemění**: pořadí a tvary slov výchozích pojmů
a zdrojů gramatikalizace (losy tvarů jdou po pojmech v tomto pořadí),
frekvence výchozích pojmů, vztahy mezi nimi. Co se mění: generované
frekvence zdrojů gramatikalizace (losuje se po tvarech všech pojmů,
takže se posunou) a vše, co závisí na počtu slov (variabilita, výsledek
dynamiky).

### Vlastní pojmy

`concepts` je seznam objektů (`ConceptSpec`):

| pole | povinné | význam |
|---|---|---|
| `id` | ano | písmena, číslice, `_ . -`, začíná písmenem nebo číslicí |
| `gloss` | ne | anglický glos; shoduje-li se s glosem Concepticonu nebo názvem významu WOLD, převezmou se data jako při vazbě, jinak je to popisek |
| `wold` | ne | vazba na význam WOLD (`"4-35"`) |
| `concepticon` | ne | vazba na ID Concepticonu; jen jedna z vazeb `wold`, `concepticon` |
| `domain` | ne | `core, learned, culture, religion, power` |
| `frequency` | ne | 0,05 až 0,9 (stupnice enginu) |
| `word_class` | ne | `noun`, `verb`, `uninflected` |
| `borrowed` | ne | půjčitelnost 0 až 1 |
| `related` | ne | příbuzné pojmy pro posuny významu |

Pořadí hodnot: co autor zadal, má přednost; jinak se vezme z vazby
(WOLD, Concepticon, glos, nebo ID, které je ID pojmu katalogu); jinak engine
doplní výchozí hodnotu a zapíše, které pole doplnil (`Concept.defaulted`,
`Vocabulary.describe()` pro UI):

| pole | výchozí hodnota bez vazby |
|---|---|
| `domain` | `core` |
| `borrowed` | průměr půjčitelnosti katalogu: celého (0,254), je-li doména zadaná, domény pojmu (core 0,181, learned 0,234, culture 0,341, religion 0,424, power 0,312) |
| `frequency` | průměr frekvencí katalogu na stupnici enginu: celého (0,176), je-li doména zadaná, domény pojmu (core 0,173, learned 0,256, culture 0,152, religion 0,134, power 0,166) |
| `word_class` | podstatné jméno |

S vazbou se doména, půjčitelnost a frekvence vezmou z významu WOLD
a slovní druh z jeho kategorie. Vlastní pojem se stejným významem WOLD,
jaký už slovník má, dostane varování (slova obou pojmů budou soutěžit); není
to chyba.

`related`: příbuzné pojmy, každý s druhem vztahu, směrem a váhou:

- `concept`: ID pojmu světa (výchozího, z katalogu v rámci zvolené velikosti
  slovníku, nebo jiného vlastního); pojem katalogu mimo slovník je chyba
  s nápovědou, že je ve větším slovníku;
- `kind`: `polysemy` (posun významu: slovo jednoho pojmu se začne užívat
  i pro druhý), `derivation` (odvození: slovo jednoho pojmu je základ pro
  slovo druhého), `colexification` (kolexifikace, vždy oboustranná);
- `direction`: `to` (od vlastního pojmu k druhému), `from` (opačně), `both`.
  Bez zadání `both` u posunu významu, `from` u odvození (druhý pojem je
  základ vlastního);
- `weight`: síla dokladu v jednotkách dat (počet rodin, resp. jazyků).
  Bez zadání 2 u posunu a odvození (medián dat je 1, průměr 1,8 a 1,5)
  a 9 u kolexifikace (medián dat 9).

Váha je doklad, ne příkaz: `shift_weight = ln(1 + polysemy) + ln(1 +
colexification) / 3`, `derivation_weight = ln(1 + derivation)` jako u dat,
takže vlastní vztah soutěží s datovými stejnými vahami. Zadaný vztah
nahradí u dvojice a druhu vztahu hodnotu z dat.

Ověření (`spec.check`) zamítá: neznámou doménu, frekvenci mimo 0,05–0,9,
půjčitelnost mimo 0–1, neznámý slovní druh, duplicitní ID, ID, které už
má výchozí pojem, zdroj gramatikalizace nebo vybraný pojem katalogu, neznámou
vazbu (WOLD, Concepticon), obě vazby najednou, příbuzný pojem, který ve
světě není, vztah pojmu k sobě, zdvojený vztah a váhu pod 1. Slova
(`languages[].words`, `endonym`) smějí používat i vlastní a rozšiřující
pojmy.

### Sémantické vztahy pro katalog

Graf pojmů pro slovník větší než výchozí se skládá ze tří zdrojů:

1. `v2_core_semantics.json` (výchozí výřez, beze změny): vztahy mezi
   výchozími pojmy zůstávají přesně takové, jaké jsou, aby se pojmy
   výchozího slovníku nechovaly jinak jen proto, že přibyly další;
2. `v2_catalog_semantics.json` (nový, jen pro dvojice, kde je aspoň jeden
   pojem z katalogu nebo vlastní s vazbou): vztahy všech významů katalogu
   s glosem Concepticonu;
3. vlastní vztahy autora.

Nový výřez staví `scripts/build_v2_catalog_semantics.py` ze stejných dat
jako výchozí (DatSemShift, Zalizniak a kol. 2024, a CLICS⁴, Tjuka a kol.
2024; obojí CC BY 4.0; slabší kolexifikace než 5 jazyků se nebere):

- **6 772 vztahů** mezi 1 270 významy (1 145 s posunem významu, 496
  s odvozením, 5 351 s kolexifikací; jeden vztah může mít víc druhů);
- **194 kB**, jeden vztah na řádek: `[zdroj, cíl, polysemy, derivation,
  colexification]`; bez komprese;
- významy jsou spojené přes **ID Concepticonu** (DatSemShift ze sloupce
  `Concepticon_ID`, uzly CLICS podle glosu), takže soubor nezávisí na ID
  pojmů enginu; dvanáct výchozích pojmů, jejichž glos výřezu se liší od
  glosu významu WOLD (*mountain*: MOUNTAIN proti MOUNTAIN OR HILL), má
  v `aliases` druhé ID, aby nepřišly o doklady, které už mají;
- soubor nese citace, licence a SHA-256 vstupů (`parameters.csv`
  DatSemShift, `graph.graphml` a `clics4-graph.gml` CLICS, katalog WOLD
  a výchozí výřez);
- všech 425 dvojic výchozího výřezu je v novém také (u deseti je hodnota
  o něco jiná; ve slovníku se stejně berou z výchozího výřezu);
  1 457 z 1 458 významů katalogu má glos Concepticonu (chybí *to turn*),
  dva sdílejí glos *DINNER (SUPPER)*, takže jich je 1 456 různých.

Pokrytí ve slovníku (pojmy, které jsou cílem aspoň jednoho vztahu, tedy mají
z čeho posun, odvození nebo kolexifikaci vzít):

| slovník | pojmů | s příchozím vztahem | vztahů v grafu | cílů posunu | cílů odvození |
|---:|---:|---:|---:|---:|---:|
| 149 | 155 | 130 | 425 | 129 | 26 |
| 200 | 206 | 186 | 755 | 185 | 40 |
| 500 | 506 | 458 | 2 492 | 455 | 113 |
| 1 000 | 1 006 | 877 | 4 895 | 866 | 216 |
| 1 453 | 1 459 | 1 245 | 6 609 | 1 226 | 288 |

Recepty složenin (`compounds`) zůstávají jen pro výchozí pojmy (kurátorované
z legacy, `docs/SWADESH_COMPOUNDS.md`); pro pojmy katalogu se složeniny
netvoří.

### Výkon

`scripts/v2_spec_timing.py --rows 2 --columns 3 --years 1000 --vocabulary N`
(6 regionů po 4 vesnicích = 24 vesnic, tři protojazyky, stát s politikou
`promoted`, od poloviny norma a škola, 1 000 let, sémantika zapnutá;
výsledek v 33 skupinách; jeden proces, MacBook, jedno měření na velikost):

| slovník | pojmů ve světě | stavba | celkem | špičková paměť | export |
|---:|---:|---:|---:|---:|---:|
| 149 | 155 | 3,2 s | 23–25 s | 340–380 MB | 0,87 MB |
| 500 | 506 | 4,0 s | 41 s | 710 MB | 2,7 MB |
| 1 000 | 1 006 | 3,5 s | 77 s | 1 180 MB | 5,3 MB |

Čas je zhruba pevný základ 16 s plus 0,05–0,07 s na pojem, paměť asi
200 MB plus 1 MB na pojem: 6,5× víc pojmů dá 3,2× delší běh a 3,3× víc
paměti. Výsledky jsou pro 33 skupin; s počtem skupin paměť i čas rostou
dál. 149 pojmů se měřilo dvakrát (23 a 25 s), takže rozdíly pod 10 %
nejsou průkazné; ostatní velikosti jsou jedno měření.

### Co to neumí

- Příbuzné pojmy a vazby jdou jen na pojmy ve slovníku. Vlastní pojem se
  nedá navázat na významy mimo katalog WOLD (Concepticon, který WOLD nemá,
  je chyba).
- Domény a půjčitelnost vlastních pojmů zatím nic neovládají: mechanismy
  (cizí elita, liturgie, obchod, škola) je použijí až v kroku 3. Engine je
  uchová (`World.vocabulary`) a UI je může zobrazit.
- Pojmy katalogu nemají recepty složenin a jejich slovní druh je hrubý
  (jen tři třídy); ručně zatříděné jsou jen výchozí pojmy.


# Iterace 3 — katalog změn a tlaků

Cíl: vyjmenovat všechny způsoby, jak se jazyk mění, a rozhodnout, co z toho
je samostatná podtřída `Změna`, co je `Tlak` a co má vzniknout samo.

## Tři druhy jevů

1. **Změna** (podtřída rodiče): mechanismus, který vyrobí novou variantu.
2. **Tlak** (komponenta): ohodnotí variantu; sám nic nevyrábí.
3. **Emergentní jev**: nemá vlastní kód. Vznikne souhrou změn, tlaků a
   šíření. Je to test, že model funguje: pokud by se musel programovat
   zvlášť, je model špatně.

## Rozhraní podtřídy

Každá podtřída `Změna` deklaruje:

| Část | Otázka |
|---|---|
| `cíl` | Na jaký typ proměnné míří (iterace 2: procesní, lexikální, formová, konstrukční)? |
| `místa` | Kde v repertoáru může vzniknout (které morfémy, prostředí, konstrukce)? |
| `míra` | Jak často vzniká inovace na jednom místě za generaci? |
| `navrhni` | Jakou variantu vyrobí? |
| `tlaky` | Které tlaky ji hodnotí a s jakou vahou? |
| `po_ustálení` | Co se stane, když varianta vyhraje (např. fonologizace)? |

## A. Zvuk

Všechny tyto změny vyrábějí **procesní proměnnou**. Místo 29 pevných
šablon je každá rodina **parametrický prostor** (třída cíle × výstup ×
prostředí) s typologickými vahami. Váhy se vezmou z katalogu doložených
změn (viz `DIRECTIONAL_SOURCES.md`).

| Změna | Co dělá | Typické prostředí | Hlavní tlaky |
|---|---|---|---|
| `Asimilace` | soused přebírá rys (místo, znělost, nazalitu) | shluk, hranice morfémů | artikulace |
| `Palatalizace` | souhláska se posune k tvrdému patru | před předními vokály, /j/ | artikulace |
| `Lenice` | oslabení: okluziva → frikativa → aproximanta → nic | mezi samohláskami, v kodě | artikulace, frekvence |
| `Fortice` | zesílení: aproximanta → frikativa → okluziva | začátek slova, po nosovce | zřetelnost |
| `Redukce vokálu` | nepřízvučný vokál → ə → nic (synkopa, apokopa, afereze) | nepřízvučná slabika | artikulace, frekvence |
| `Vložení` | epenteze, proteze, paragoge | neplatný shluk | fonotaktika |
| `Změna kvality vokálu` | zvýšení, snížení, posun dopředu/dozadu, zaokrouhlení | přízvuk, okolní souhlásky | disperze, zřetelnost |
| `Diftongizace` / `Monoftongizace` | rozdělení dlouhého vokálu / splývání dvojhlásky | přízvučná / nepřízvučná slabika | zřetelnost / artikulace |
| `Řešení hiátu` | vokál + vokál → polosamohláska, splynutí, vložená souhláska | hranice slabik | fonotaktika |
| `Délka` | kompenzační prodloužení, zkrácení, vznik délky | ztráta segmentu, otevřená slabika | — |
| `Disimilace` | jeden ze dvou podobných segmentů se změní (r…r → r…l) | sporadicky, slovo po slově | zřetelnost |
| `Metateze` | prohození sousedů | sporadicky, slovo po slově | fonotaktika |
| `Přízvuk` | změna pravidla přízvuku | celý systém | — |
| `Tónová perturbace` | výška tónu se přizpůsobí okolní souhlásce | po znělé/neznělé souhlásce | (stopa pro tonogenezi) |
| `Nepravidelná redukce` | velmi častá slova se zkracují jednorázově (*God be with you* → *goodbye*) | jen nejčastější slova | frekvence |

Poslední tři skupiny (disimilace, metateze, nepravidelná redukce) jsou
**sporadické**: nevytvářejí procesní proměnnou pro celé prostředí, ale
formovou proměnnou pro jeden morfém.

## B. Morfologie

| Změna | Co dělá | Cíl | Hlavní tlaky |
|---|---|---|---|
| `Vyrovnání` | odstraní alternaci uvnitř paradigmatu (*mohu → můžu*) | formová | uniformita, učitelnost, frekvence (vzácné první) |
| `Rozšíření vzoru` | produktivní vzor se přenese na další slova (*-s* v angl. plurálu) | formová | uniformita, typová frekvence vzoru |
| `Kontaminace` | splynutí dvou příbuzných tvarů | formová | uniformita |
| `Reanalýza hranice` | posun hranice morfémů (*a napron → an apron*) | formová | zřetelnost |
| `Zpětné tvoření` | odvození „základu“ z odvozeného slova | lexikální | uniformita |
| `Gramatikalizace` | jeden krok po škále: slovo → pomocné slovo → klitika → afix | konstrukční | expresivita (začátek), frekvence (dál) |
| `Exaptace` | zbytkový morfém dostane novou funkci | konstrukční | — |
| `Odvozování` | nové slovo z kořene a produktivního afixu | lexikální | potřeba, transparentnost |
| `Skládání` | nové slovo ze dvou kořenů (recepty sémantiky převezmeme) | lexikální | potřeba, transparentnost |

## C. Syntax

| Změna | Co dělá | Cíl | Hlavní tlaky |
|---|---|---|---|
| `Změna slovosledu` | nové pořadí slotů jako varianta (SOV → SVO) | konstrukční | zřetelnost (když slábnou pády), kontakt |
| `Reanalýza struktury` | konstrukce se přeinterpretuje (*mám to napsané* → perfektum) | konstrukční | frekvence, expresivita |
| `Změna zarovnání` | pasivum nebo posesivum se stane základní větou (vznik ergativu) | konstrukční | — |
| `Obnova` | zeslabený výraz se posílí přidaným slovem (*ne* → *ne … pas*) | konstrukční | expresivita |
| `Vznik shody` | zájmeno se přilepí ke slovesu jako shoda | konstrukční | frekvence |
| `Kalk` | konstrukce se přeloží z kontaktního jazyka | konstrukční | prestiž, bilingvismus |

## D. Lexikon a význam

| Změna | Co dělá | Cíl | Hlavní tlaky |
|---|---|---|---|
| `Sémantický posun` | morfém začne vyjadřovat další pojem: metafora, metonymie, rozšíření, zúžení (graf CLICS + DatSemShift) | lexikální | potřeba, frekvence |
| `Hodnotový posun` | zlepšení nebo zhoršení konotace | lexikální | sociální |
| `Vyblednutí` | ztráta konkrétního významu, příprava gramatikalizace | lexikální → konstrukční | frekvence |
| `Expresivní tvoření` | zvukomalebné a expresivní nové kořeny podle fonotaktiky jazyka | lexikální | expresivita, identita |
| `Tabuová náhrada` | opis místo tabuizovaného slova | lexikální | tabu |
| `Náhrada erodovaného slova` | příliš krátké slovo nahradí delší (lat. *os* → *bucca* „ústa“) | lexikální | zřetelnost, homofonie |
| `Zkracování` | zkrácení dlouhého slova (*automobil → auto*) | formová | artikulace, frekvence |
| `Ztráta s věcí` | pojem přestane být potřeba | lexikální | potřeba |

## E. Kontakt

V modelu variant se kontakt z velké části děje přímo v `Šíření`: sousední
skupina mluví jiným kódem, ale její varianta pro pojem `WATER` může vstoupit
do naší lexikální proměnné `WATER`. Tím **se mění iterace 1**: `Výpůjčka`
není jediná cesta kontaktu. Šíření přes hranici kódu má filtr
přenositelnosti (Thomasonova a Kaufmanova škála) a krok adaptace.

| Mechanismus | Kde žije | Co dělá |
|---|---|---|
| Lexikální výpůjčka | `Šíření` + adaptace | varianta pojmu z cizího kódu, upravená fonologií příjemce |
| Šíření procesu | `Šíření` | stejná procesní proměnná přeskočí mezi kódy (areální rys, např. uvulární *r* v Evropě) |
| Strukturní výpůjčka | `Šíření`, jen při vysoké dvojjazyčnosti | afix, konstrukce, nový foném |
| `Výpůjčka` (Změna) | podtřída | vnese cizí prvek do místa, kde dosud nesoutěžil (nový pojem, nová kategorie) |
| `Kalk` | podtřída (C) | překlad cizí konstrukce domácími morfémy |
| Interference při přechodu | iterace 4 | populace přechází na jiný kód a nese do něj své varianty |

## Tlaky

Každý tlak vrací číslo v intervalu [−1, 1] pro variantu v konkrétní
skupině. Fitness varianty = vážený součet tlaků, které má její změna
připojené. Váhy se kalibrují (iterace 5).

| Tlak | Co měří | Zdroj |
|---|---|---|
| `Artikulace` | úspora gest: kratší, asimilovaný, méně napjatý tvar; silnější v nepřízvučné pozici a u častých slov | zákon nejmenšího úsilí, Bybee |
| `Zřetelnost` | zachování akustických vodítek kontrastu; penalizuje varianty, které je stírají | Ohala |
| `Funkční zátěž` | kolik frekvenčně vážených dvojic slov by varianta slila; zvlášť buňky téhož paradigmatu | Martinet; Wedel a kol. 2013 |
| `Disperze` | rozložení vokálů a souhlásek v prostoru: odměna za zaplnění mezery, trest za přeplnění | Martinet, Liljencrants & Lindblom |
| `Fonotaktika` | shoda se slabičnou stavbou jazyka a s typologickým priorem (PHOIBLE) | — |
| `Frekvence` | modulátor: častá slova vedou v redukci, ale odolávají analogii a náhradě | Bybee; Pagel a kol. 2007 |
| `Uniformita` | jeden tvar pro jeden význam; síla podle typové frekvence vzoru | analogie, Sturtevantův paradox |
| `Expresivita` | odměna za nový, delší, průhledný výraz tam, kde starý zeslábl | Haspelmath, Jespersen |
| `Učitelnost` | trest za nepravidelnost úměrný podílu dospělých nerodilých mluvčích; děti zesilují většinovou variantu | Trudgill; Hudson Kam & Newport 2005 |
| `Prestiž` | varianta zdroje s vyšší prestiží má výhodu | Labov |
| `Identita` | odměna za variantu, která odlišuje skupinu od soupeřícího souseda | Labov (Martha's Vineyard) |
| `Konformita` | výhoda většinové varianty ve skupině (zrychluje dokončení S-křivky) | — |
| `Norma` | brzda změny a výhoda kodifikované varianty; působí jen přes gramotnost a školu | instituce (iterace 4) |
| `Potřeba` | nové věci a pojmy zvyšují poptávku po výrazu; zaniklé ji snižují | — |
| `Tabu` | trest pro variantu s tabuizovaným významem | — |

Tlaky se dělí na dvě skupiny, jak bylo vysvětleno dříve: **jazykové**
(artikulace až expresivita) určují, které inovace vznikají a jak jsou
výhodné samy o sobě. **Sociální** (učitelnost až tabu) určují, které z nich
se uchytí v konkrétní skupině.

## Emergentní jevy

Tyto jevy se nesmí programovat zvlášť. Jsou to testy modelu.

| Jev | Jak má vzniknout |
|---|---|
| Řetězový posun | změna kvality vokálu + `Disperze` + `Funkční zátěž`: pohyb jednoho vokálu zvýhodní pohyb souseda do uvolněného místa |
| Splynutí a rozštěpení fonémů | fonologizace procesu: splynutí, když výstup existuje; rozštěpení, když podmínka později zmizí |
| Synkretismus | zvuková redukce slije koncovky různých buněk paradigmatu |
| Morfologizace (umlaut) | fonologizace přes hranici + pozdější ztráta podmínky (iterace 2) |
| Tonogeneze | `Tónová perturbace` + ztráta souhlásky, která ji podmiňovala |
| Analytizace | eroze koncovek + `Funkční zátěž` + `Expresivita` → předložky a pevný slovosled |
| Gramatikalizační cyklus | `Gramatikalizace` → eroze → `Obnova` → znovu |
| Koineizace | míšení skupin při migraci do města + `Učitelnost` + `Konformita` → vítězí méně značkované varianty |
| Konvergence (jazykový svaz) | dlouhodobé šíření procesů a konstrukcí mezi kódy s vysokou dvojjazyčností |
| Dialektové kontinuum a izoglosy | šíření po síti s různou silou vazeb |

## Matice interakcí

Jak výsledek jedné změny vytváří tlak nebo příležitost pro jinou:

| Když vyhraje… | …vznikne | …a to otevře |
|---|---|---|
| zvuková redukce | kratší slova, splynuté koncovky | náhradu erodovaných slov, analytizaci, obnovu |
| asimilace přes hranici | alomorfy | vyrovnání, rozšíření vzoru |
| splynutí fonémů | homofonie | náhradu slova, sémantický posun |
| ztráta souhlásky | delší vokál, tónová stopa | tonogenezi, kompenzační délku |
| gramatikalizace | nový afix | zvukovou erozi afixu (cyklus) |
| obnova | delší konstrukci | gramatikalizaci nového výrazu |
| analogie | pravidelnější paradigma | opětovný prostor pro zvukové změny |
| výpůjčka | nové fonémy a shluky | změny fonotaktiky, adaptaci dalších výpůjček |
| ztráta pádů | nejednoznačnost rolí | pevný slovosled, předložky |

### Velký cyklus

Nejdůležitější zpětná vazba celé gramatiky:

```mermaid
flowchart LR
    A[Zvuková eroze koncovek] --> B[Synkretismus]
    B --> C[Nejednoznačnost]
    C --> D[Opis a pevný slovosled]
    D --> E[Gramatikalizace opisu]
    E --> F[Nový afix]
    F -->|znovu| A
```

## Co se mění oproti iteraci 1 a 2

- `Výpůjčka` přestává být hlavní cestou kontaktu; většinu kontaktu nese
  `Šíření` přes hranici kódu s filtrem přenositelnosti.
- Zvukové změny nejsou pevné šablony, ale parametrické rodiny s vahami z
  dat.
- Sporadické změny (metateze, disimilace, nepravidelná redukce) míří na
  formové proměnné jednoho morfému, ne na procesní.

# Conlang Evolution Engine (CEE)

## Návrh výzkumného a vývojového projektu

**Verze 3.0** · srpen 2026 · Jan Vrzal

---

## 0. Shrnutí

**Conlang Evolution Engine (CEE)** je generativní simulátor jazykové změny. Z jednoho protojazyka a sítě historických událostí — štěpení populací, obchodních kontaktů, dobývání, vzniku písemnictví — odvozuje rodinu příbuzných jazyků, u nichž je každé slovo zpětně trasovatelné až ke svému kořeni.

Projekt stojí na jedné technické tezi a jedné z ní odvozené obchodní:

> **Technická teze.** Věrohodnost simulované jazykové rodiny lze měřit objektivně, a tedy i kalibrovat. Konkrétně: pokud standardní nástroje výpočetní historické lingvistiky (detekce kognátů, fylogenetická rekonstrukce) pracují na simulované rodině se srovnatelnou úspěšností jako na reálné rodině stejné časové hloubky, je simulace v relevantním smyslu realistická.

> **Obchodní teze.** Tentýž kalibrovaný model má dva odběratele s velmi odlišnou ochotou platit a velmi odlišným časovým horizontem. Worldbuildeři chtějí hotové jazyky a zaplatí hned; výpočetní historická lingvistika potřebuje **syntetická data se známou pravdou** pro benchmarkování vlastních metod a je ochotná spolufinancovat jejich vznik. Wedge je první skupina, dlouhodobě obranyschopné aktivum vzniká pro obě.

Klíčové rozhodnutí projektu je v tom, **co se generuje**. Existující nástroje (Lexurgy, Brassica, Zompistova SCA) jsou *aplikátory*: uživatel napíše uspořádaný seznam zvukových změn a nástroj ho spustí na slovník. To předpokládá uživatele, který ta pravidla umí napsat — tedy zkušeného conlangera. CEE naopak staví na *generátoru* pravidel: sadu věrohodných, vzájemně konzistentních zvukových změn navrhne engine sám, na základě typologických priorů z doložených jazykových dějin a s ohledem na aktuální fonologický inventář daného uzlu. Aplikátor je infrastruktura a dá se převzít. **Generátor je vlastní přínos i vlastní obranyschopnost.**

Dokument slouží zároveň jako zadání výzkumné práce (sekce 2, 3, 5, 9) a jako investiční podklad (sekce 0, 1, 3.2, 6, 7, 8). Sekce 4 je společná technická specifikace.

---

## 1. Problém

### 1.1 Worldbuilding: jazyky jako nekonzistentní ozdoba

Autoři fikčních světů — od tvůrců stolních RPG přes spisovatele fantasy po herní studia — potřebují jména míst, postav a věcí, která působí, že pocházejí z nějakého jazyka. V praxi vznikají třemi způsoby: náhodným generátorem slabik, ručním vymýšlením, nebo v poslední době promptováním jazykového modelu.

Všechny tři sdílejí stejnou vadu: **nemají historii.** Vygenerovaná slova spolu nesouvisejí. Když autor potřebuje, aby dvě sousední země mluvily příbuznými jazyky, musí tu příbuznost buď předstírat (podobně znějící slabiky), nebo ručně udržovat, což se v rozsahu stovek jmen rozpadne. Reálné jazyky mají vnitřní strukturu — v češtině je *ruka*, *rukáv*, *rukojmí* a *náruč* propojeno historií, kterou mluvčí neuvědoměle cítí. Tuhle vlastnost žádný z existujících postupů neposkytuje.

Zkušený conlanger to řeší ručně: napíše protojazyk, napíše uspořádaný seznam zvukových změn, spustí ho aplikátorem. Výsledek je vynikající. Cena je několik desítek až stovek hodin práce a znalost historické fonologie na úrovni magisterského studia lingvistiky. To je bariéra, která drtivou většinu poptávky nechává neobslouženou.

### 1.2 Výpočetní historická lingvistika: metody bez ground truth

Nezávisle na tom má obor, z jehož dat by CEE čerpal, vlastní strukturální problém. Metody pro **automatickou detekci kognátů** a **fylogenetickou rekonstrukci** jazykových stromů se validují na reálných rodinách — nejčastěji na indoevropské, austronéské a několika dalších dobře popsaných. Těch je málo, jsou vzájemně nezávislé jen omezeně a — zásadně — **pravda o nich není známá, je také rekonstruovaná.** Když algoritmus najde jiný strom než konsensus komparativní metody, není jednoznačně rozhodnutelné, kdo se mýlí.

Standardní odpovědí v jiných oborech je simulace: vygeneruj data z modelu, u kterého pravdu znáš, protože jsi ji sám zadal, a změř, jak dobře ji metoda najde zpět. Ve výpočetní historické lingvistice takový generátor v použitelné podobě chybí. Existující simulační práce bývají ad hoc skripty vázané na konkrétní článek, bez kalibrace vůči reálným rychlostem změny a bez modelování kontaktu, který je přitom hlavním zdrojem chyb fylogenetických metod.

### 1.3 Průnik

Obě mezery vyžadují tutéž věc: **generativní model jazykové změny, kalibrovaný tak, aby jeho výstupy byly statisticky nerozlišitelné od reálných jazykových rodin.** Pro worldbuildera je výstupem hotový jazyk; pro lingvistu je výstupem datová sada s anotovanou pravdou. Je to stejný engine, jen se z něj exportuje něco jiného.

Tenhle průnik je celá logika projektu. Není to dodatečné ospravedlnění hobby nástroje — je to důvod, proč se do něj vyplatí investovat víc práce než do dalšího generátoru slabik.

---

## 2. Teze, výzkumné otázky a přínos

### 2.1 Hlavní teze

Věrohodnost simulované jazykové rodiny je **měřitelná veličina**, nikoli věc vkusu. Operacionalizace: rodina je věrohodná v míře, v jaké se na ní standardní metody komparativní lingvistiky chovají stejně jako na reálné rodině srovnatelné časové hloubky a kontaktní historie.

Z toho plyne, že generátor lze **kalibrovat uzavřenou smyčkou**: generuj rodinu → změř ji nástroji oboru → porovnej profil s reálnou referenční rodinou → uprav váhy generátoru. Tenhle cyklus je jádro výzkumné části projektu a zároveň jediná obrana proti tomu, co postihuje všechny existující nástroje — vývojář ladí generátor podle toho, co mu subjektivně „zní dobře".

### 2.2 Výzkumné otázky

**VO1 — Aplikátor.** Reprodukuje stavový derivační model (rysové svazky, inventář jako stav) doložené vývoje správně? *Testovatelné:* zadej latinský lexikon a publikované sady zvukových zákonů pro francouzštinu, španělštinu a italštinu; změř shodu odvozených forem s doloženými.

**VO2 — Generátor.** Lze z typologických priorů generovat sady zvukových změn, jejichž statistický profil (typ změny, počet, pořadí, výsledná fonetická vzdálenost) je nerozlišitelný od profilu doložených sad? *Testovatelné:* porovnej distribuce generovaných a doložených sad; slepý test s hodnotiteli z oboru.

**VO3 — Rodina.** Chovají se metody detekce kognátů a fylogenetické rekonstrukce na simulovaných rodinách stejně jako na reálných? *Testovatelné:* spusť `LingPy` a standardní bayesovské fylogenetické postupy na obojím a porovnej křivky úspěšnosti proti časové hloubce.

**VO4 — Kontakt.** Reprodukuje model kontaktu (datované výpůjčky, substrát, lingua franca) známé signatury kontaktních situací — zejména to, že výpůjčky vykazují nižší fonetickou erozi než zděděný lexikon a že narušují fylogenetický signál způsobem popsaným v literatuře?

VO1 je nutná podmínka a je nízkorizikový. **VO2 je vlastní vědecké riziko projektu.** VO3 je podmínka pro druhý trh. VO4 je rozšíření.

### 2.3 Přínos

*Vědecký:* otevřený, kalibrovaný forward-simulátor jazykové změny a z něj odvozený **benchmarkový korpus syntetických jazykových rodin s anotovanou pravdou** (kognátní třídy, strom, výpůjčky, časová razítka) ve formátu CLDF, tedy přímo použitelný v existující infrastruktuře oboru.

*Produktový:* nástroj, který worldbuilderovi vygeneruje rodinu vnitřně konzistentních jazyků za odpoledne místo za měsíce, s exportem do formátů, které skutečně používá.

*Metodický:* protokol pro měření věrohodnosti simulovaných jazyků, který je použitelný i mimo CEE.

---

## 3. Stav poznání a konkurence

### 3.1 Datová a metodická základna

Projekt je postavitelný **až teď**, a to je podstatné pro časování. Ekosystém CLDF (Cross-Linguistic Data Formats) dozrál do stavu, kdy jsou všechny potřebné datové zdroje dostupné v jednotném, strojově čitelném a verzovaném formátu:

| Zdroj | Co poskytuje | Role v CEE |
|---|---|---|
| **Concepticon** | univerzální ID konceptů, propojení stovek wordlistů, sémantická pole, ontologické kategorie | osa významů; proxy bazálnosti; sémantická pole místo ručního tagování |
| **CLICS** | kolexifikace — které koncepty sdílejí slovo, v kolika jazycích | *neorientované* sdružování významů při tvorbě protojazyka |
| **DatSemShift** | katalog doložených diachronních sémantických posunů | *orientované* posuny v čase |
| **PHOIBLE** | fonologické inventáře reálných jazyků | sanity check generovaných inventářů |
| **Index Diachronica** (a jeho moderní přepracování) | kompilace doložených zvukových změn z historických gramatik | **priory pro generátor pravidel** |
| **LingPy** | zarovnání, detekce kognátů, fonetické vzdálenosti | měřicí přístroje, nikoli generování |

Poslední řádek je klíčový: Index Diachronica je zdroj, který dělá generátor vůbec možným. Bez něj by váhy typů zvukových změn byly čistě autorský odhad.

### 3.2 Konkurence

**Aplikátory zvukových změn** — Lexurgy, Brassica, Zompistova SCA². Zralé, kvalitní, zdarma. Neřeší generování, neřeší graf jazykové rodiny, neřeší sémantiku, neřeší kontakt. *Vztah k CEE: nikoli konkurenti, ale infrastruktura a výměnný formát.* Podpora importu i exportu Lexurgy souborů je pro CEE strategická — dává existující komunitě cestu dovnitř i ven a odstraňuje obavu z uzamčení.

**Generátory jazyků** — Vulgarlang je hlavní komerční hráč, prodává se jako jednorázová licence. Vygeneruje jeden jazyk s gramatikou a slovníkem. *Rozdíl:* generuje jazyk, ne **rodinu s historií**. Neumí odvodit dva sesterské jazyky ze společného předka tak, aby jejich příbuznost byla skutečná a trasovatelná. To je přesně ta funkce, kvůli které lidé tráví měsíce ruční prací.

**Generátory slov** — Awkwords, Lexifer a desítky dalších. Řeší nejmenší dílčí problém, zdarma.

**Jazykové modely.** Reálná a rostoucí konkurence pro nenáročný segment: LLM vygeneruje sadu jmen, která na první pohled působí konzistentně. Selhává na dvou věcech, které jsou pro seriózního uživatele podstatné: **nekonzistence v rozsahu** (u pěti set slov se struktura rozpadne, protože není odvozená, jen imitovaná) a **netrasovatelnost** (nelze se zeptat, proč zrovna tohle slovo vypadá takhle). CEE proti tomu nesoutěží kvalitou prvního dojmu, ale reprodukovatelností a auditovatelností. To je zároveň důvod, proč je architektonicky správně držet engine plně procedurální a AI mít jen jako volitelný vstupní pomocník (sekce 4.7).

### 3.3 Mezera

Nikdo nespojuje: (a) generování pravidel místo jejich aplikace, (b) graf celé rodiny s kontaktem, (c) vědecká sémantická data, (d) měřitelnou kalibraci. Body (a) a (d) neexistují nikde, ani v akademických pracích, ani v komerčních nástrojích.

---

## 4. Architektura

### 4.1 Datový model: graf a verzování po vzoru Gitu

Jádrem je graf uzlů (jazyk v čase) s dvěma typy hran: **vertikálními** (dědičnost) a **horizontálními** (kontakt).

**Pravidla jsou pravda, slovníky jsou cache.** Každá vertikální hrana drží uspořádaný, neměnný seznam pravidel, kterými z rodiče vznikl potomek. Slovník uzlu je odvozený artefakt vypočtený přehráním pravidel od protoformy. Nejtěžší část historické fonologie je *pořadí* pravidel (feeding, bleeding) a tento model ho činí explicitním a auditovatelným.

**Verzování je Git, ne zamykání.** Uzel je adresován hashem `H(hash rodiče ‖ serializovaný seznam pravidel ‖ seed)`. Z toho plyne:

- *Invalidace* je triviální — hash nesedí, přepočítej.
- *Reroll* je vytvoření **paralelní větve**, ne destruktivní přepis. Uživatel neztrácí předchozí variantu a nemusí nic „odmrazovat".
- *Freeze* je v tomto slovníku prostě **tag** na konkrétním commitu: pojmenovaný, stabilní odkaz, ze kterého se dá dál větvit.

**Cache se persistuje.** Formulace „slovník se fyzicky neukládá" je zavádějící: cache je content-addressed a **musí přežít zavření projektu**. Bez toho se při každém otevření přepočítává celý strom. Řádový odhad: list ve hloubce 30 kroků při ~40 pravidlech na hranu a 2 000 lexémech znamená kolem 2,4 milionu aplikací pravidla, tedy v Pythonu desítky sekund; s memoizací po uzlech jde o poslední hranu, ~80 tisíc aplikací, tedy podsekundový čas. Rozdíl mezi nepoužitelným a interaktivním nástrojem je zde výhradně v klíčování a persistenci cache.

**Mapa je aktivní.** Uživatel nahraje obrázek mapy a nad ním ve druhé vrstvě štětcem nakreslí **biomovou masku** (les, step, poušť, hory, pobřeží). Engine čte biom uzlu z jeho XY pozice. Mapa tedy není pasivní plátno — je to vstup do sémantického modulu (4.7).

**Tvar dat.** Minimální schéma uzlu a hran; vše ostatní je odvozené.

```jsonc
{
  "node": {
    "id": "sha256:a3f1…",              // H(parent ‖ rules ‖ seed)
    "parent": "sha256:9c22…",
    "year": 1200,                       // absolutní, ne index kroku
    "seed": 48210,
    "tags": ["frozen:klasicka-forma"],  // freeze = tag na commitu
    "state": {
      "inventory": ["p","t","k","s","m","n","a","i","u"],
      "phonotactics": "CV(C)",
      "morphosyntax": { "cases": 6, "tam": ["PRS","PST","FUT"] },
      "params": { "affixation": "suffix", "compound_head": "final" },
      "map": { "x": 412, "y": 233, "biome": "steppe" },
      "literacy": 0.2
    },
    "frequency_table": "sha256:…"      // per-uzlová, driftuje (4.7)
  },
  "vertical_edge": {
    "from": "sha256:9c22…", "to": "sha256:a3f1…",
    "rules": [                           // uspořádaný, neměnný
      { "schema": "lenition", "target": "[-son,+voice,-cont]",
        "env": "V_V", "result": "[+cont]", "year": 1150 }
    ]
  },
  "contact_edge": {
    "from": "sha256:7b0e…", "to": "sha256:a3f1…",
    "year": 1200,
    "type": "religion",                // viz tabulka v 4.6
    "prestige": 0.8,
    "volume": 120,
    "fields": ["Religion and belief", "Emotions and values"]
  }
}
```

### 4.2 Čas: absolutní rok a globální lockstep

Horizontální hrany dělají z grafu strukturu s cykly (jazyk A půjčuje B v roce 1200, B půjčuje A v roce 1300). Model „lokálních epoch" na tom selhává, protože „epocha 3" nemá napříč grafem definovaný význam.

**Časovou osou je absolutní rok.** Derivace běží jako globální lockstep: engine posune všechny uzly k nejbližšímu časovému bodu, tam vyhodnotí naráz všechny aktivní kontaktní hrany, provede commit a pokračuje. Cyklus se tím rozpadá na sled acyklických kroků.

**Délka kroku je vlastnost osy, ne uzlu.** Tím zůstává zachována flexibilní granularita, která je pro worldbuilding cenná — v pravěku krok 1 000 let, blíž k současnosti 100 nebo 50 let. Podmínkou konzistence je jen to, že krok je v daném okamžiku globální.

**Diglosie.** Vznik písemnictví uzel rozštěpí na dvě paralelní větve. Psaná forma se nezmrazí na nulu — klasická latina driftovala do středověké, církevní slovanština má recenze — ale mutuje řádově pomaleji (výchozí hodnota 5 % rychlosti mluvené větve, uživatelsky nastavitelná).

### 4.3 Fonologie: aplikátor

Derivace je **stavový fold**, který nese a průběžně aktualizuje stav uzlu (fonologický inventář, fonotaktika, frekvenční tabulka).

Substrátem **nejsou znakové regexy**. Ty neumí rozlišit afrikátu `ts` od shluku `t`+`s` a hlavně neumí vyjádřit přirozenou třídu, která se v čase mění: pravidlo „znělé okluzivy lenují intervokalicky" zapsané jako `[bdg]` má množinu zamrzlou v textu a nedozví se, že `/g/` mezitím zaniklo.

Místo toho: slovo se tokenizuje na **segmenty jako svazky distinktivních rysů** (integrace `panphon` pro IPA), pravidlo je transformace rysové matice a jeho cílová třída je **dotaz do aktuálního inventáře**. Pravidlo cílící na třídu, která je prázdná, se prostě nespustí — feeding a bleeding tak vyplývají ze stavu, nikoli z ručního ošetření.

*Poznámka k rozsahu:* podpora importu Lexurgy souborů není úspora práce na implementaci, jen na návrhu syntaxe. Lexurgy má vlastní systém rysů a vlastní sémantiku vyhodnocení; mapování na `panphon` není 1:1 a import bude v první iteraci vědomě ztrátový s explicitním hlášením nepřevoditelných konstrukcí.

### 4.4 Fonologie: generátor pravidel

**Toto je jádro projektu.** Pokud má cílový uživatel dostat pět jazyků za odpoledne, nemůže sady pravidel psát — musí je engine navrhnout.

Generátor pracuje ve třech vrstvách:

1. **Inventář schémat.** Typované, parametrizované třídy zvukových změn: lenice, fortice, palatalizace, asimilace (progresivní/regresivní, dle rysu), epenteze, elize, apokopa/synkopa, monoftongizace, diftongizace, posuny samohlásek, metateze, tonogeneze. Schéma není konkrétní pravidlo, je to šablona s rysovými podmínkami.

2. **Priory.** Váhy schémat a jejich typických prostředí jsou odvozeny z **Index Diachronica** — kompilace zvukových změn doložených v publikovaných historických gramatikách. Váha odpovídá tomu, jak často se daný typ změny v reálných dějinách jazyků vyskytuje a v jakém kontextu. Kde data nestačí, jsou priory explicitně autorské a jako takové označené (viz 5.5, reprodukovatelnost).

3. **Filtr věrohodnosti.** Vzorkovaná sekvence prochází kontrolami: prostředí musí být v aktuálním inventáři neprázdné; sekvence nesmí obsahovat okamžité zvrácení předchozí změny; výsledný inventář musí projít typologickou kontrolou proti PHOIBLE (např. jazyk se znělými okluzivami bez neznělých je krajně vzácný); výsledná fonotaktika nesmí kolabovat do neudržitelné podoby.

Generátor je řízen několika uživatelskými **makro-parametry** — rychlost změny, náchylnost k erozi konců slov, konzervativnost — které se propisují do vah. To je ta „black-box" vrstva pro worldbuildera. Vygenerovaná sada je zároveň exportovatelná jako Lexurgy soubor, což je únikový poklop pro uživatele, který chce zasahovat ručně.

### 4.5 Morfologie

**Morfosyntaktický inventář jako součást protosemene.** Bez něj nemá gramatikalizace co lepit a kreolizace co zahazovat. Protojazyk tedy nese nejen fonologický inventář, ale i: počet a inventář pádů, TAM kategorie, jmenné třídy/rody, inventář pomocných slov a adpozic.

**Dva nezávislé typologické parametry.** Sloučení do jednoho by bylo empiricky vadné:

1. *Afixační strategie* — preference sufixace či prefixace při gramatikalizaci degradujících pomocných slov. Napříč jazyky světa je doložena výrazná **obecná preference sufixace** nezávisle na slovosledu; korelace se syntaktickou hlavovostí je slabá tendence, ne pravidlo.
2. *Pořadí složenin* — zda hlava stojí v složenině vpravo, či vlevo. **Nezávisle** na předchozím parametru. Angličtina je učebnicová ukázka disociace: syntakticky head-initial (*kill the man*), ale ve složeninách striktně head-final — `houseboat` je *loď*, nikoli dům; `seahorse` je *kůň*. Model, který obojí řídí jedním přepínačem, vyrábí systematickou typologickou chybu.

**Analogie a vyrovnávání paradigmat.** Přehrávání samotných zvukových zákonů po deseti krocích vyrobí paradigmata, jaká by žádná populace mluvčích neudržela — reálné jazyky je průběžně uklízejí. Systém proto po každé fonologické vrstvě spouští analogické vyrovnávání, řízené frekvencí: vysokofrekvenční položky analogii odolávají a zůstávají nepravidelné (*být*, *jít*, angl. *be*, *go*), nízkofrekvenční se vyrovnávají do pravidelných tvarů (*holpen* → *helped*).

### 4.6 Kontakt: výpůjčky, prestiž, substrát

**Datované výpůjčky.** Slovo přejaté v roce *T* projde v přejímajícím jazyce pouze pravidly s datem pozdějším než *T*. Výpůjčky proto přirozeně vypadají méně obroušeně než zděděný lexikon — bez jakéhokoli zvláštního ošetření. Tuhle vlastnost je vhodné použít i jako validační test (VO4).

**Typy hran mají definovanou mechaniku.** Nestačí je pojmenovat; každý typ je trojice *(distribuce přes sémantická pole, objem, prestižní asymetrie)*:

| Typ vazby | Zasažená sémantická pole | Asymetrie | Zvláštnost |
|---|---|---|---|
| Obchod | materiální kultura, jídlo, míry, čísla | nízká, obousměrná | nejnižší objem |
| Dobytí / válka | správa, právo, vojenství, tituly | vysoká, jednosměrná | spouští substrátový efekt |
| Náboženství | abstrakta, rituál, morálka, kalendář | vysoká, jednosměrná | **učené výpůjčky** — nižší fonologická nativizace |
| Lingua franca | plošně, s důrazem na abstrakta | vysoká, jednosměrná | působí i na nesousedící uzly, dle % vlivu |

Poslední sloupec u náboženství je podstatný detail: liturgické a učené výpůjčky se historicky nativizují méně než lidové, protože procházejí písemným kanálem. Model to zachycuje sníženou průchodností fonotaktického filtru.

**Prostupný filtr výpůjček.** Historický inventář filtruje přejímky, ale **není tvrdý**. Při dostatečné prestiži a intenzitě kontaktu může výpůjčka do jazyka zavést dříve neexistující foném — angličtina si přes francouzštinu pořídila `/ʒ/`. Tvrdý filtr by vyráběl nerealisticky uzavřené fonologie právě u kultur pod nejsilnějším vlivem.

**Kotvy nejsou imunní.** Bazální lexikon je vůči výpůjčce odolný, nikoli neprostupný. Anglická zájmena *they/them/their* jsou ze staré severštiny, finské *äiti* („matka") je germanismus. Odolnost je proto spojitá váha, ne boolean — a její extrémní překročení při intenzivním kontaktu je jeden z nejzajímavějších výstupů, které simulace může dát.

**Substrát působí střídmě.** Vítězný lexikon protéká fonotaktickým filtrem poražené populace, ale substrátové vlivy jsou historicky proslule nepravidelné a rozsahem omezené — z galského vlivu na francouzštinu zbylo velmi málo a i to je sporné. Model proto substrát neaplikuje plošně; jinak vznikají přeplácané, nerealisticky hybridní jazyky.

### 4.7 Sémantika bez závislosti na AI

Engine musí být samostatný. Sémantika proto stojí na vědeckých datech, nikoli na běžícím jazykovém modelu.

**Tvorba protojazyka — CLICS (neorientovaně).** Kořen se nepřiřazuje k anglickému slovu, ale k **uzlům Concepticonu**. Engine vyhledá v CLICS pravděpodobné kolexifikace a přiřadí jeden kořen na skupinu konceptů — protojazyk A může mít jedno slovo pro `[STROM]` i `[DŘEVO]`, protojazyk B pro `[VODA]` i `[ŘEKA]`. Tím jazyky od začátku *dělí svět jinak*. Hrany CLICS jsou **vážené** počtem jazyků, v nichž je kolexifikace doložena.

**Posun v čase — DatSemShift (orientovaně).** CLICS je synchronní a neorientovaný: říká, že dva koncepty sdílejí slovo, neříká, kterým směrem posun proběhl. Pro diachronní posun se proto používá **DatSemShift**, katalog doložených orientovaných posunů, dostupný rovněž v CLDF.

**Biom bez ručního tagování 2 000 konceptů.** Prostředí ovlivňuje, které koncepty jsou v daném uzlu relevantní. Ruční klasifikace jednotlivých konceptů by byla neúnosná — ale není potřeba: Concepticon nese **sémantická pole** (~22 kategorií zděděných z IDS, například *The physical world*, *Animals*, *Agriculture and vegetation*) a šest ontologických kategorií. Biomová relevance se mapuje **na tato pole**, tedy řádově dvacítkou autorských rozhodnutí místo dvou tisíc. Granularita je hrubší, pro modelovaný jev dostatečná.

**Dvojí determinismus je nutné rozbít.** Skóre bazálnosti odvozené z Concepticonu (na kolika wordlistech se koncept objevuje) je vlastností *konceptu*, tedy identické pro všechny jazyky simulace a konstantní v čase. Kdyby řídilo zánik přímo, ztratily by všechny sesterské jazyky přesně tytéž koncepty a rodina by vyšla nerealisticky homogenní — což by zároveň znehodnotilo kalibrační metriku z 5.1. Stejně tak výběr cíle posunu podle *nejsilnější* hrany je argmax a vede každý jazyk k témuž výsledku.

Model to řeší dvěma opravami:

- Concepticonové skóre slouží jako **prior**. Každý uzel si nese vlastní frekvenční tabulku, která tímto priorem startuje a pak se v čase **náhodně prochází**. Linie se tak rozcházejí.
- Cíl sémantického posunu se **vzorkuje úměrně váze hrany**, nikoli vybírá maximem.

**Role LLM: volitelný inicializátor mimo aplikaci.** Engine neobsahuje běžící AI. Jazykový model může uživatel použít mimo CEE, chce-li si vytvořit vlastní kategorii fantastických konceptů (například *magie krve*) a nahrát ji jako JSON; engine ji napojí na existující uzly a dál s ní pracuje procedurálně. Tím zůstává celý běh reprodukovatelný a auditovatelný.

### 4.8 Explicitně mimo rozsah

Uvedeno proto, že rozsah je hlavní realizační riziko:

- **Syntax celých vět.** Engine modeluje fonologii, morfologii a lexikon. Slovosled vstupuje jen jako parametr ovlivňující morfologii.
- **Plně modelovaná kreolizace.** Zjednodušení morfologie kontaktem je v modelu jako parametrizovaný efekt, nikoli jako simulace pidginizace. Ta je samostatný výzkumný program.
- **Písmo a ortografie** nad rámec transliterace.
- **Plug-in ekosystém.** Odloženo do doby, kdy jádro bude stabilní a bude mít uživatele; navrhovat plug-in API dřív je klasická past.

---

## 5. Kalibrace a validace

Tato sekce je páteří vědecké části a zároveň hlavním nástrojem odrizikování pro investora. Platí, že projekt, jehož ústřední tvrzení nelze vyvrátit, nemá co nabídnout ani jednomu z obou publik.

### 5.1 Dvojí metrika

Zásadní je, že **jedna metrika nestačí**, protože jazyková změna má dvě nezávislé osy.

**(A) Lexikální retence.** Měří *náhradu* — zda význam ve slotu obsadil nový kořen. Toto je veličina, kterou měří glottochronologie. Retence **neslouží jako tvrdý cíl**: Swadeshova konstanta není konstanta a Bergsland s Vogtem to ukázali už v roce 1962 na islandštině versus kontinentální skandinávštině, kde se míry za stejné období z téhož výchozího bodu výrazně rozešly. Slouží proto jako **volné pásmo** (řádově 75–95 % za tisíciletí), uvnitř kterého uzel posouvá gramotnost, prestiž a intenzita kontaktu.

**(B) Fonetická vzdálenost kognátů.** Měří *erozi* — jak moc se tvar téhož kořene rozešel. Počítá se odděleně, například jako průměrná normalizovaná editační vzdálenost nad zarovnáními z `LingPy`.

Rozlišení není formalita. Lze aplikovat drastické zvukové změny a mít přitom stoprocentní lexikální retenci — `*kʷetwores` → *čtyři* je fonologicky brutální a lexikálně nulová změna. **Kalibrovat sílu zvukových změn podle Swadeshovy retence znamená ladit jeden parametr podle měřidla, které měří jiný.**

**Diagnostický list je fixní.** Swadeshův seznam je *měřicí přístroj*, nikoli vlastnost jazyka. Musí být pro všechny měřené uzly identický a neměnný, jinak jsou hodnoty nesrovnatelné. Je proto oddělen od uživatelsky viditelné **odolnosti slova** (spojité skóre dle 4.7), která se naopak vyvíjí.

### 5.2 Validace V1 — aplikátor (VO1)

Nejjednodušší a nejpřísnější test, protože latina je **doložená, nikoli rekonstruovaná** — na rozdíl od praindoevropštiny zde známe vstup s jistotou.

*Postup:* zadej klasickolatinský lexikon a publikované sady zvukových zákonů pro cestu k francouzštině, španělštině a italštině. Přehraj. Změř podíl odvozených forem, které se shodují s doloženými, a analyzuj systematické odchylky.

*Kritérium úspěchu:* shoda na úrovni srovnatelné s existujícími aplikátory. Neúspěch znamená chybu v derivačním jádru, nikoli v modelu — a je opravitelný.

### 5.3 Validace V2 — generátor (VO2, VO3)

Zde leží skutečné riziko projektu, a proto má dvě nezávislé části.

**V2a — profilové srovnání.** Nech generátor vyrobit *N* sad pravidel pro zadanou časovou hloubku a výchozí inventář. Porovnej distribuce s doloženými sadami z Index Diachronica: zastoupení typů změn, jejich počet na tisíciletí, typická prostředí, výsledná fonetická vzdálenost. Statisticky odlišné distribuce znamenají špatně nastavené priory.

**V2b — nerozlišitelnost pro nástroje oboru (klíčový test).** Toto je operacionalizace hlavní teze a zároveň důvod, proč má výstup hodnotu i pro lingvisty:

> Spusť standardní automatickou detekci kognátů a fylogenetickou rekonstrukci na (i) simulovaných rodinách a (ii) reálných rodinách srovnatelné časové hloubky a kontaktní historie. Porovnej **křivky úspěšnosti proti časové hloubce**.

Pokud se metody na syntetických datech chovají jinak než na reálných, simulace je v nějakém měřitelném smyslu nerealistická — a tvar odchylky navíc ukazuje, kde. Pokud se chovají stejně, jsou syntetická data použitelná jako benchmark s anotovanou pravdou, což je přesně produkt pro druhý trh.

Elegance téhle konstrukce je v tom, že **validační kritérium a vědecký deliverable jsou tatáž věc.**

**V2c — slepé hodnocení.** Doplňkově: předlož hodnotitelům se vzděláním v historické lingvistice směs generovaných a reálných sad zvukových změn a změř, zda je rozliší nad úrovní náhody.

### 5.4 Falzifikační kritéria

Projekt považuji za vyvrácený v příslušné části, pokud:

- **F1:** V1 nedosáhne shody srovnatelné s existujícími aplikátory ani po odladění → chyba derivačního jádra.
- **F2:** Distribuce v V2a zůstanou statisticky odlišné i po kalibraci priorů → typologické priory z dostupných dat nestačí; generátor vyžaduje jiný zdroj znalosti.
- **F3:** Metody v V2b se na syntetických datech chovají systematicky odlišně (typicky: kognáty se detekují *příliš snadno*, protože simulace nevyrábí dost šumu) → model postrádá podstatný zdroj variability, pravděpodobně lexikální difuzi, nepravidelnost a analogii.
- **F4:** Hodnotitelé v V2c rozliší generované od reálných výrazně nad náhodou a shodnou se na důvodu → identifikovatelná systematická vada.

F3 pokládám za nejpravděpodobnější způsob selhání a zároveň za nejinformativnější.

### 5.5 Reprodukovatelnost

Vlastnost, která je pro vědecké použití nutná, pro produkt je konkurenční výhodou a přitom skoro nic nestojí, je-li zabudována od začátku:

- **Seed** je součástí hashe uzlu. Táž konfigurace dává týž výsledek.
- **Verze dat.** Projekt si ukládá verze všech použitých datasetů (Concepticon, CLICS, DatSemShift, priory). Simulace z roku 2026 je spustitelná v roce 2030 se stejným výsledkem.
- **Autorské priory jsou označené.** Kde váha nepochází z dat, je to v souboru priorů explicitně vyznačeno — jinak by nebylo možné oddělit empirický základ od autorského odhadu.
- **Celá historie je exportovatelná** jako lidsky čitelný soubor pravidel (viz Lexurgy export). Uživatel není uzamčen.

---

## 6. Etapizace

**Etapa 1 — jádro (MVP).** CLI, žádné GUI, jedna linie bez kontaktu. Rysový derivační engine, ruční sady pravidel, trasovatelnost jednoho slova, obě metriky z 5.1. **Výstupní brána: validace V1.** Dokud aplikátor neprojde latinou, nemá smysl stavět nic nad ním.

**Etapa 2 — generátor.** Inventář schémat, priory z Index Diachronica, filtr věrohodnosti, makro-parametry. **Výstupní brána: validace V2a.**

**Etapa 3 — rodina a kontakt.** Graf, lockstep, horizontální hrany s definovanou mechanikou, git-like verzování. **Výstupní brána: validace V2b** — tedy okamžik, kdy vzniká i druhý produkt.

**Etapa 4 — sémantika.** Concepticon, CLICS, DatSemShift, biomová pole, morfologie a analogie.

**Etapa 5 — produkt.** Mapové GUI s biomovou maskou, exporty (gramatický náčrt v PDF/Markdown, dvojjazyčný slovník v CSV/JSON, balíček do Anki), onboarding, defaulty.

Pořadí je záměrně opačné, než by odpovídalo atraktivitě. GUI a exporty jsou to, co uživatel vidí, a zároveň to, co je nejsnazší postavit až nakonec — kdežto obrácené pořadí je nejčastější způsob, jak podobné projekty umřou s hezkým rozhraním nad nefunkčním jádrem.

---

## 7. Rizika

| Riziko | Závažnost | Zmírnění |
|---|---|---|
| **Generátor nevyrobí věrohodné sady** (F2/F3) | vysoká — jde o jádro | Etapa 2 je oddělená brána; při selhání zůstává použitelný produkt s ručními a předpřipravenými sadami pravidel, byť s užší cílovou skupinou |
| **Priory z Index Diachronica jsou zkreslené** — kompilace odráží to, co bylo popsáno, tedy převážně indoevropské jazyky | střední | explicitní označení autorských priorů; vážení podle rodin; korekce dle PHOIBLE |
| **Morfologie je těžší než fonologie** | střední | ostré omezení rozsahu (4.8); morfologie až v etapě 4 |
| **Trh je malý** | vysoká pro čistě komerční čtení | otevřené jádro + druhý (výzkumný) odběratel; nízká nákladová základna |
| **Licenční nesoulad dat** | střední | audit po jednotlivých datasetech před distribucí (sekce 9) |
| **Zdlouhavost výpočtu u velkých grafů** | nízká | content-addressed persistovaná cache (4.1) |
| **Rozsahová eroze** | vysoká, systémová | brány mezi etapami, explicitní seznam vyloučeného |

Riziko trhu je uvedeno záměrně bez příkras. CEE není nástroj s venture-scale trhem sám o sobě; smysl dává jako projekt s nízkou nákladovou základnou, otevřeným jádrem a dvěma odběrateli.

---

## 8. Obchodní model: otevřené jádro

### 8.1 Hranice

**Otevřené (permisivní licence):** derivační engine, generátor pravidel, datové konektory, formát projektu, CLI, exporty do otevřených formátů. Důvod je věcný, nikoli ideologický: vědecký nástroj, jehož jádro nelze zkontrolovat, není vědecký nástroj, a validační protokol z kapitoly 5 by byl bezcenný, kdyby ho nešlo zopakovat.

**Placené:** hostovaná verze se sdílením a spoluprací na projektech, knihovna kurátorovaných a kalibrovaných prosemen a stylových balíčků, prémiové exporty (sazba gramatiky, hromadné generování jmen pro herní obsah), týmové funkce a integrace do produkčních pipeline.

### 8.2 Kdo platí

*Jednotlivci* — autoři, tvůrci stolních RPG, kutilové. Nízká cena, vysoký objem, jednorázová nebo levná roční licence. Referenčním bodem je jednorázová licence Vulgarlangu.

*Malá studia a nakladatelství* — tvůrci herního a knižního obsahu s dlouhodobě udržovaným světem. Platí za konzistenci a auditovatelnost napříč lety a napříč lidmi; ruční alternativou je najatý konzultant.

*Akademie a výuka* — licence pro katedry, výuka historické lingvistiky, generování cvičných dat. Nízká marže, vysoká legitimizační hodnota.

*Výzkum* — benchmarkové korpusy a zakázkové generování datových sad. Menší objem, ale financovatelné z grantů, což je pro tenhle typ projektu realističtější zdroj než čistě rizikový kapitál.

### 8.3 Obranyschopnost

Kód není obranyschopný — je otevřený a schopný vývojář ho zreplikuje. Obranyschopné je následující, v tomto pořadí:

1. **Kalibrovaná knihovna priorů.** Vzniká prací, kterou nikdo jiný neudělal, a zpřesňuje se s používáním. To je skutečné aktivum.
2. **Validovanost.** Tvrzení „naše výstupy prošly V2b" je ověřitelné, citovatelné a nekopírovatelné bez zopakování celé práce.
3. **Ekosystém a data uživatelů.** Projekty, sdílená prosemena, komunitní balíčky pravidel. Uzamčení nikoli bariérou, ale hodnotou uvnitř.
4. **Postavení v akademickém ekosystému.** Nástroj citovaný v pracích oboru se nahrazuje obtížně.

### 8.4 Proč teď

Dvě věci se změnily nedávno a obě jsou nutné:

- **Datový substrát dozrál.** Concepticon, CLICS a nově i DatSemShift jsou dostupné v jednotném CLDF formátu s verzováním. Ještě před několika lety by podstatnou část rozpočtu spolykalo sjednocování dat.
- **Poptávka po worldbuildingu vzrostla** s rozšířením stolních RPG a nezávislé tvorby, a zároveň jazykové modely zvedly laťku očekávání — uživatelé dnes očekávají, že nástroj něco *vygeneruje*, ne že jim nabídne prázdný formulář.

---

## 9. Právní a datové aspekty

**Licence zdrojových dat nejsou jednotné.** Ekosystém CLLD/lexibank je převážně otevřený, ale jednotlivé zdrojové datasety se licenčně liší a některé jsou restriktivnější, než odpovídá zastřešující formulaci. Před jakoukoli distribucí, která data přibaluje, je nutný **audit po jednotlivých datasetech**. U komerční složky open-core modelu to není formalita.

**Atribuce a verzování.** Každý použitý dataset musí být v projektu i ve výstupech citován s verzí. To je zároveň požadavek licencí a požadavek reprodukovatelnosti (5.5).

**Uživatelský obsah.** Vygenerované jazyky vznikají z uživatelských vstupů a otevřených dat; podmínky musí explicitně přiznat práva k výstupu uživateli, jinak je nástroj pro komerční tvorbu nepoužitelný.

---

## 10. Pojmový slovník

Uveden proto, že v předchozích verzích dokumentu se čtyři pojmy vyskytovaly ve dvou různých významech naráz. Tento seznam je závazný.

| Pojem | Význam v tomto dokumentu | Co to **není** |
|---|---|---|
| **Rok** | absolutní bod na globální časové ose | nikoli lokální „epocha"; ta se v dokumentu nevyskytuje |
| **Krok** | interval mezi dvěma lockstep vyhodnoceními; vlastnost osy | nikoli vlastnost uzlu |
| **Freeze** | pojmenovaný tag na commitu | nikoli zamykání předků ani zákaz změn |
| **Reroll** | nová paralelní větev | nikoli destruktivní přepis |
| **Cache** | content-addressed persistovaný odvozený slovník | nikoli „neukládá se" |
| **CLICS** | *neorientovaná* synchronní síť kolexifikací | nikoli zdroj směru posunu |
| **DatSemShift** | *orientovaný* katalog diachronních posunů | nikoli zdroj kolexifikací |
| **Skóre zakotvenosti** | per-uzlová frekvence, startující z Concepticonového prioru a driftující v čase | nikoli konstanta sdílená všemi jazyky |
| **Diagnostický list** | fixní Swadeshův seznam, měřicí přístroj | nikoli uživatelská vlastnost jazyka; nemění se biomem |
| **Biom** | vlastnost uzlu čtená z masky mapy, mapovaná na sémantická pole Concepticonu | nikoli ruční tag na jednotlivých konceptech |
| **Aplikátor** | spouští zadaná pravidla (Lexurgy, Brassica) | nikoli generátor |
| **Generátor** | navrhuje sady pravidel z priorů | vlastní jádro CEE |

---

## 11. Zdroje

**Datové zdroje a nástroje**

- Concepticon — <https://concepticon.clld.org/>
- CLICS (Database of Cross-Linguistic Colexifications) — <https://clics.clld.org/>
- DatSemShift (Zaliznjak a kol.) — <https://datsemshift.ru/> ; CLDF verze: <https://github.com/lexibank/datsemshift>
- lexibank — <https://lexibank.clld.org/>
- Index Diachronica (prohledávatelná verze) — <https://chridd.nfshost.com/diachronica/> ; moderní přepracování: <https://github.com/bradrn/index-diachronica-redux>
- LingPy — <https://lingpy.org/>
- Lexurgy — <https://github.com/def-gthill/lexurgy>
- Brassica — <https://github.com/bradrn/brassica>

**Metodická literatura (výběr, k doplnění při zpracování)**

- Bergsland, K. & Vogt, H. (1962): *On the Validity of Glottochronology.* Current Anthropology — základ kritiky Swadeshovy konstanty.
- Hawkins, J. & Gilligan, G. (1988): *Prefixing and suffixing universals in relation to basic word order* — asymetrie sufixační preference.
- Williams, E. (1981): *On the notions "lexically related" and "head of a word"* — pravidlo pravé hlavy ve složeninách.
- List, J.-M. a kol.: publikace k CLICS, Concepticon a CLDF.


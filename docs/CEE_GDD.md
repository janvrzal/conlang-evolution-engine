# Conlang Evolution Engine (CEE): Master Document (GDD)

Tento dokument slouží jako hlavní návrhová specifikace (GDD - Game Design Document) pro vývoj univerzálního nástroje **Conlang Evolution Engine (CEE)**. Nástroj je navržen k simulaci evoluce jazyků a jejich štěpení napříč flexibilními časovými epochami.

## 0. Základní Vize a Filozofie (MVP Scope)
*   **Univerzalita:** Cílem je vytvořit nástroj, který si může každý uživatel přizpůsobit. Zda budou jazyky vizuálně "čitelné pro Evropana", nebo naopak zcela mimozemské, závisí čistě na **uživatelském nastavení** u proto-semen, ne na pevném kódu (hardcoding).
*   **Technologický Stack:** Jádro poběží v **Pythonu**. Pro grafy lze využít `networkx`. Pro zvukové změny CEE nebude psát vlastní pravidlový DSL od nuly, ale podpoří import **Lexurgy** souborů (zralá syntax pro zvukové změny se silnou komunitou).
*   **Cílová skupina a Výstup (Meta-Vize):** Nástroj je primárně určen pro **worldbuildery**, kteří chtějí k mapě za odpoledne vygenerovat pět věrohodně příbuzných jazyků. CEE disponuje dobrými defaulty (funguje jako "black-box generátor"), ale umožňuje plný zásah. **Výstupem** pro uživatele není vnitřní elegance simulace, ale konkrétní artefakty: Gramatický náčrt (PDF/Markdown), dvojjazyčný slovník (CSV/JSON) a balíček do Anki pro učení.
*   **Rozsah MVP:** Nástroj se v první iteraci nezaměří na plug-in ekosystém (Obsidian model), ale na stabilní jádro generující věrohodné rodiny jazyků.

---

## 1. Architektura Dat: Grafová Síť
Jádrem CEE je graf (Directed Acyclic Graph s horizontálními vazbami), který mapuje vývoj jazyků v čase a prostoru.
*   **Trasovatelnost (Traceability):** Graf umožňuje přesně zpětně trasovat, odkud slovo přišlo, a vykreslit nejpříbuznější jazyky. Měření příbuznosti probíhá skrz trasování v grafu, ale i přes vektorovou podobnost moderních slovníků.
*   **Pravidla jsou pravda, slovníky jsou cache:** Nejtěžší částí fonologie je *pořadí* pravidel (feeding, bleeding). Každá hrana v grafu drží uspořádaný, neměnný seznam pravidel (mutací), kterými vznikl potomek z rodiče. Slovník samotného uzlu se fyzicky neukládá, je to jen "cache" (odvozený artefakt vypočítaný přehráním pravidel od proto-formy).
    *   *Trasovatelnost:* Zcela automatická. Libovolné slovo lze odvodit přehráním historie.
    *   *Reroll a Freeze (Git Model):* Mechanika rerollu nevyužívá destruktivní přepisování a nakažlivé mrazení předků. Engine funguje jako Git (commits, branches). Uzel je adresován hashem (hash rodiče + serializovaný seznam pravidel). Reroll je pouze vytvoření nové větve vedle té staré. Invalidace je triviální (hash nesedí -> přepočítej), cache je content-addressed a bezpečná.
*   **Vizuální GUI (Aktivní Biomová Maska):** Uživatel nahraje obrázek své mapy světa. Na něj v druhé vrstvě ručně štětcem nakreslí "biomovou masku" (les, poušť, hory). Engine pak při pohybu uzlů po plátně sám čte aktuální biom z XY pozice na mapě.

---

## 2. Horizontální vazby (Kontakt a Konflikt)
Křížení a půjčování slov mezi uzly probíhá primárně přes horizontální hrany.
*   **Role a Typy konfliktů:** Pokaždé, když uživatel spojí dva uzly, zvolí "Typ vazby" (Obchod, Válka, Náboženství). Každá strana v konfliktu má svou roli.
*   **Datované výpůjčky (Loanwords):** Protože uzly drží *časově seřazená pravidla*, výpůjčky fungují automaticky. Když jazyk A přejme slovo z jazyka B v epoše 3, toto slovo projde v jazyce A pouze těmi mutačními pravidly, která nastanou *po* epoše 3. Loanwordy tak přirozeně vypadají "méně obroušeně" než domácí slova.
*   **Lingua Franca:** Jazyk lze na úrovni epochy označit jako *Lingua Franca* (např. latina nebo angličtina v reálném světě) a nastavit mu % plošného vlivu. Takový jazyk vyzařuje vliv a nabízí svá slova i kmenům, se kterými přímo na mapě nesousedí.

---

## 3. Řízení času (Globální Lockstep) a Modifikátory
Model času musí zvládat horizontální hrany (výpůjčky), které z DAGu dělají graf s cykly (jazyk A půjčuje jazyku B v roce 1200, B půjčuje A v roce 1300).
*   **Absolutní rok a Lockstep Derivace:** Časová osa nefunguje na lokálních flexibilních epochách, ale na **absolutním roce**. Derivace běží jako globální lockstep: Engine vezme všechny uzly v grafu, posune je k nejbližšímu časovému bodu, tam vyřeší naráz všechny kontaktní hrany (výpůjčky), provede commit (uloží stav) a pokračuje dál.
*   **Git-like Tahování:** (Viz bod 1) Čas nepoškozuje uzly napříč větvemi, rerolly vytvářejí paralelní časové timeline-větve.
*   **Gramotnost a Diglosie:** Vznik písemnictví rozštěpí jazyk vedví (Diglosie). Psaná forma se *nezmrazí na nulu* (klasická latina driftovala do středověké), ale drasticky zpomalí (např. mutuje rychlostí 5 % mluvené větve).
*   **Fixní diagnostika vs. Váhy:** Systém striktně odděluje **diagnostický Swadeshův list** (neměnný, uživatel ho nevidí, slouží jen jako kalibrační metr pro retenci) a **Spojité skóre zakotvenosti** (odolnost slova vůči zániku). Skóre zakotvenosti není ruční boolean, ale získá se zdarma z Concepticonu: koncept linkovaný na 200 wordlistech má obří váhu (nevyhnutně přežije), koncept na 1 listu má váhu marginální. V extrémních případech kontaktu (např. angličtina+severština) lze půjčovat i těžká kotevní slova (zájmena).

---

## 4. Generátor a Lingvistické Mutace
Engine (Python) zajišťuje, že příbuzná slova a složeniny (compounds) mají stejné historické základy, protože pracuje přímo na kořenech slov. Generování se opírá o následující pilíře:

### A. Fonologie (Tvar zvuku)
Mutace nepůsobí magicky jako bezhlavé mapování. Derivace je **stavový fold**, který s sebou neustále nese a updatuje stav, přičemž nevyužívá znakové regexy (ty neumí rozlišit afrikáty od shluků), ale **rysové svazky**.
*   **Fonémový inventář (Rysové matice):** Slovo se tokenizuje na segmenty a pravidlo je transformace rysové matice. K reprezentaci vlastností IPA využijeme integraci nástrojů jako `panphon`. (Pravidlo typu "znělé okluzivy lenují" se ptá rysové matice aktuálního inventáře, ne fixního textového regexu).
*   **Prostupný filtr výpůjček:** Historický inventář filtruje loanwords, ale filtr je prostupný na základě *prestiže a intenzity kontaktu*. Při dostatečném vlivu může loanword zavést do jazyka dříve neexistující foném (jako anglické /ʒ/ z francouzštiny).

### B. Morfologie a Analogie (Úklid paradigmat)
CEE bude mít vysoce modulární morfologický systém. Proto-semeno si nese nejen zvukový inventář, ale i **morfosyntaktický inventář** (počet pádů, TAM kategorie, inventář pomocných slov), bez kterého by gramatikalizace neměla co lepit (kreolizace musí mít pády, které může zahodit).
*   **Nezávislé syntaktické parametry:** Parametry se nedrží v jednom globálním nastavení, ale jsou typologicky nezávislé:
    1.  *Afixační strategie:* Určuje preferenci degradujících slov lepit se jako sufixy (univerzální lidská preference) nebo prefixy.
    2.  *Pořadí složenin (Compounds):* Určuje nezávisle na afixech, zda se hlava klade na začátek (DůmLoď = houseboat) nebo na konec.
*   **Analogie a Vyrovnávání:** Přehrávání pouze zvukových zákonů by po 10 epochách vytvořilo neudržitelná paradigmata. Systém používá **spojité skóre zakotvenosti (frekvence)**: Vysokofrekvenční slova (být, jít) analogii odolávají a zůstávají nepravidelná. Nízkofrekvenční slova se analogicky "vyrovnávají" do pravidelných tvarů (např. *holpen -> helped*).

### C. Substráty a Vnucení (Modelování válek)
Pokud Říše (Superstrát) dobude území a vnutí mu svůj jazyk, není to náhoda.
*   *Místní Akcent:* Vítězný slovník "proteče" přes fonotaktický filtr (akcent) poraženého národa (Substrátu). Tyto vlivy jsou ale historicky proslule **nepravidelné a omezené** (z galského vlivu na francouzštinu zbylo minimum). Substrát proto nepůsobí genericky masivně, aby nevznikaly přeplácané, nerealisticky hybridní jazyky.

### D. Kalibrace a Dvojí Metrika (LingPy)
Aby vývojář netestoval generátor "poslepu", engine na pozadí měří věrohodnost rodin:
1.  **Lexikální retence (Swadeshův list):** Měří lexikální náhradu (zda význam obsadil nový kořen). Glottochronologická retence neslouží jako tvrdý target (není to konstanta), ale jako volné pásmo (cca 75–95 % za tisíciletí). Literárnost a kontaktní hrany posouvají uzel uvnitř tohoto pásma.
2.  **Fonetická vzdálenost kognátů:** Kognáty se měří odděleně od lexikální retence. Slouží ke kalibraci *síly* zvukových změn (např. přes průměrnou normalizovanou editační vzdálenost za využití algoritmů z `LingPy`). Obě tyto metriky zároveň slouží k vykreslení "příbuznosti" v mapovém GUI.

---

## 5. Sémantika BEZ závislosti na AI (Vědecké Offline Ontologie)
Ačkoliv LLM může ušetřit spoustu práce při počáteční přípravě, **Engine nesmí být na AI závislý**. Aby byl CEE skutečně samostatný, musí mít vlastní procedurální řešení pro sémantiku postavené na tvrdých datech.

### A. Jádro: Jazykově agnostická síť (Concepticon, CLICS a DatSemShift)
Abychom zabránili uvěznění v anglickém vnímání světa, nevyužijeme WordNet, ale **skutečné lingvistické databáze (CLLD projekt pod CC-BY)**:
*   **Concepticon & CLICS:** CLICS ukazuje, jak se koncepty z Concepticonu "slévají" do stejných slov napříč tisíci světovými jazyky. Toto je synchronní, *neorientovaná* síť ideální pro sdružování významů při tvorbě protojazyka.
*   **DatSemShift (Zaliznjak a kol.):** Katalog doložených diachronních posunů. Narozdíl od CLICS je *orientovaný* (definuje, že směr posunu jde od konceptu A ke konceptu B, nikoliv naopak). Použije se pro počítání přesných sémantických posunů v čase. (Obě databáze lze načíst stejným pipeline v rámci `lexibank`).
*   *(Upozornění: Engine nebude nativně podporovat komplexní biomové tagování konceptů z důvodu nutnosti masivní manuální klasifikace 2000+ uzlů nad rámec originálních datasetů.)*

### B. Procedurální sémantický posun přes CLICS (Bez AI)
Pokud kmen migruje od moře na step, Engine nepotřebuje AI. Podívá se do vědeckých dat:
1.  **Lexical Attrition (Ztráta):** Engine najde konceptuální uzly vázané na tag `[voda]`. Během epoch na stepi je vysoká šance jejich zániku.
2.  **Sémantické klouzání pomocí CLICS:** Pokud slovo nezanikne, engine se podívá do databáze CLICS a vyhledá, s jakými jinými koncepty se dané slovo napříč tisíci reálných jazyků nejčastěji spojuje. Pokud databáze ukáže, že se slovo pro *Moře* ve 150 jazycích světa sémanticky posunulo na slovo *Duna* (nebo *Země*), engine tento posun procedurálně provede. Získáme tak realistické sémantické posuny bez použití AI.

### C. Role LLM: Striktně volitelný "Inicializátor"
AI už v enginu nefiguruje jako běžící proces. Uživatel si stáhne CEE, který obsahuje data z Concepticonu a CLICS. LLM se využije pouze jako pre-promptový generátor mimo aplikaci, pokud by si chtěl uživatel vytvořit vlastní, zcela novou kategorii fantastických konceptů (např. *Magie krve*), kterou pak jen ve formátu JSON nahraje do CEE. Engine si ji propojí s existujícími uzly a dál s ní pracuje procedurálně.

---

## 6. Příloha: UCN Architektura (Detailní proces sémantiky)

Tato sekce detailně vysvětluje, jak bude CEE offline simulovat chápání významu a sémantické posuny beze slov, čistě pomocí abstraktních uzlů, na konkrétním příkladu.

### 6.1. Jak probíhá integrace (CLICS + DatSemShift)
Místo generování přes LLM využije CEE vědecká data z `lexibank`:
1.  **Concepticon:** Poskytuje univerzální sémantické ID (např. `1227-TREE`).
2.  **CLICS:** Určuje neorientované shluky (colexification) použité pro iniciální generování proto-kořenů.
3.  **DatSemShift:** Určuje orientované vektory pro posun v čase.

### 6.2. Jak to funguje uvnitř Enginu

**Krok 1: Tvorba Proto-Jazyka (CLICS Sdružování)**
Když vytváříš kořenová slova pro "Semínko A", Engine nevygeneruje anglické slovo "River". Namísto toho vygeneruje zvuk, např. **"Moru"**. Následně vyhledá v síti CLICS nejpravděpodobnější ko-lexifikace a přiřadí "Moru" na uzly `CONCEPT_RIVER` a `CONCEPT_SEA`. Tento kmen tedy používá stejné slovo pro řeku i moře.

**Krok 2: Krize a Posun (DatSemShift Klouzání)**
Kmen migruje do jiného prostředí a slovo ztrácí využití.
1.  **Krize slova (Skóre z Concepticonu):** Zánik slova je řízen proxy frekvencí vytaženou z Concepticonu (na kolika listech se koncept celosvětově objevuje). Nízkofrekvenční slova mizí bez náhrady. U vysokofrekvenčních se spouští pravděpodobnost na posun.
2.  **Klouzání po váženém grafu:** Pokud se posouvá, Engine se podívá do orientované sítě DatSemShift (diachronní posuny v historii) a na hrany sítě CLICS, které jsou **vážené** (podle toho, v kolika jazycích se posun stal). Engine procedurálně posune význam slova **"Moru"** na "Písek". Míří tam, kde je nejsilnější hrana.

**Krok 3: Tvorba nových slov (Složeniny)**
Když kmen objeví nový koncept (Velbloud), Engine vyhledá v grafu nejbližší příbuzné (Zvíře) a spojí ho se stávajícím slovem. Podle nezávislého parametru *pořadí složenin* spojí Zvíře a Písek a vznikne logická, typologicky konzistentní složenina. Vše plně matematické, plně offline.

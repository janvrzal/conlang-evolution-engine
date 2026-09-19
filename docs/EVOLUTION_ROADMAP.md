# Evoluční roadmapa

Živý seznam práce na jádru CEE. Za položku se dává `[x]` až tehdy, když je
mechanismus součástí běžné simulace, má auditovatelnou historii a regresní
test. `[~]` znamená použitelný základ, který ještě nesplňuje celý popis.

Pořadí bloků je záměrné: zvukové změny tvoří podklad pro morfologii; variace
mezi mluvčími je pak podkladem pro lexikon i kontakt.

## 1. Zvuková historie — aktuální priorita

- [x] Řetězové posuny jako propojené série kontrastů: tři až čtyři kroky se
  aplikují simultánně, bez self-feeding mezitvarů. Pravidlo rozlišuje tažný
  řetězec, který se pohybuje do volného okraje řady, a strkovou rotaci, která
  zachová terminální kontrast.
- [x] Tonogeneze a tónová historie: ztracená znělá/neznělá koda vytváří L/H;
  tónové řady pracují s H/L/M a stoupavou i klesavou konturou R/F a sandhi má
  parametrizované dvojice. Priorita tónové inovace navíc bere v úvahu hustotu
  a vícecentrovost nastavené populace.
- [x] Vokálová harmonie jako systémový proces: generátor volí progresivní či
  regresivní směr, doménu slova nebo morfému a harmonii zadnosti, případně
  zadnosti i zaokrouhlení. Cílová samohláska se vždy vybírá z reálného
  inventáře jazyka a zachovává co nejvíce své výšky.
- [x] Postupné lexikální šíření podle frekvence, sociální skupiny a
  morfologické třídy: každá změna má seedované ohnisko, časové fáze a pro
  jednotlivé lexémy práh ovlivněný frekvencí, morfémovou hranicí, kohortou a
  městskou/izolovanou vrstvou. Síť komunit zůstává lehká, nikoli simulace osob.
- [x] Tlak na zachování kontrastů a funkční zátěž fonémů: hodnocení kandidáta
  měří nejen podíl zachovaných forem, ale i frekvenčně vážené nové kolize a
  zvlášť kontrasty uvnitř téhož paradigmatu; tyto hodnoty jdou do auditu.
- [x] Oprava fonotaktiky podle naučené gramatiky jazyka: profil se učí limity
  onsetu/kody, produktivní a jednorázově doložené vzory, sonoritní vzestup a
  pokles a vrací vážené porušení. Nový neplatný tvar opraví minimální domácí
  epentezí, reliktní výjimky nepřepisuje.

## 2. Význam a užívání

- [x] Tlak biomu, ekonomiky, technologie či institucí na konkrétní význam.
  Doložená hrana zůstává nutnou podmínkou; kontext ji pouze zvýhodňuje a do
  auditu zapisuje svůj důvod.
- [x] Životní cyklus registrů: neutrální → formální, tabu → opis, rituální →
  běžný. Tabu spouští legitimní lexikální náhradu, která je označena jako opis;
  registrální přechod i náhrada jsou samostatné auditní události.
- [x] Metafora, metonymie, specializace a generalizace jako samostatné,
  podmíněné mechanismy.
- [x] Konkurence synonym podle významu: tlak z překryvu kontextů, frekvence a
  stability, včetně postupného šíření a vítězství varianty.
- [x] Sociální a kontaktní rozšíření významu: významová inovace má ohnisko v
  konkrétní komunitě a šíří se po jejích vazbách a bilingvismu. Živá,
  rozběhnutá varianta se při kalkovém či obchodním kontaktu přenese jako nová
  časovaná varianta nad lexémem cílového jazyka; obchodní trasa je tak skutečný
  kanál difuze, ne jen dekorace.
- [x] Autorské potvrzení jednotlivého sémantického návrhu před aplikací:
  režim „ke schválení“ zapisuje návrh do auditu a detail jazyka jej může
  potvrdit pro příští běh bez skryté automatické mutace.
- [~] Sémantické presety a kalibrace: UI nabízí konzervativní, vyvážené a
  dynamické tempo sémantických příležitostí; chybí samostatné metriky
  polysémie, retence a velikosti skoků mezi větvemi.

## 3. Morfologická historie a tvorba slov

- [x] Automatický vznik produktivního afixu z frekventované konstrukce:
  opakované doložené formy se stejným afixem přejdou přes minimální počet
  typů a frekvenční expozici na produktivní gramatický morfém.
- [x] Eroze afixu a vznik nepravidelností napříč paradigmatem: časté formy
  produktivního paradigmatu mohou ztratit okraj afixu; analogie je později
  může, ale nemusí srovnat.
- [x] Produktivita slovotvorných vzorů podle frekvence a analogie: produktivita
  se odvozuje z užití, zatímco analogie pracuje pouze uvnitř paradigmatu.
- [x] Volba složeniny ze sémantického receptu bez ruční specifikace: volitelný
  režim `morphology.recipe_compounds` použije kurátorovaný recept jen tehdy,
  když cílový koncept chybí a oba živé zdroje existují; událost se zapisuje do
  historie jako `semantic_compound`.
- [x] UI fronta „čeká na rozhodnutí o homofonii“: položka obsahuje oba lexémy,
  tlak a rok a lze ji ponechat, odložit nebo otevřít v časové ose konkrétního
  jazyka. Editor nabídne pouze kolexifikaci, sémantický posun, derivaci či
  složeninu nad dostupným lexikonem; potvrzení uloží strategii pro příští běh
  i auditní autorskou událost, aniž by zpětně měnilo historický běh.

## 4. Lexikální životní cyklus

- [x] Motivovaný vznik nových kořenů: volitelná inovace skládá nový kořen z
  vlastního inventáře a označí auditovatelný zdroj — expresivitu, dětskou řeč,
  obchodní slang nebo lokální substrát. Nová forma pak soutěží se starou.
- [~] Stabilita podle Concepticonu: Concepticon dodává identitu, doménu a
  ontologii konceptu, nikoli empirickou míru retenční stability. Engine nyní
  umí načíst autorův CSV/TSV retenční korpus podle Concepticon ID či glosu,
  otisknout jeho SHA-256 provenance ke každému lexému a jinak transparentně
  spadnout na heuristiku. Výchozí lokální prior se skládá z otevřených
  Concepticonových seznamů Swadesh 1955 a Peust 2013; chybí jeho nezávislá
  kalibrace a širší globální evidence.
- [x] Synonymní konkurence: inovace vstoupí jako varianta, šíří se podle
  mobility a standardizace a až při převaze může vytlačit starší lexém.
- [x] Homofonie přes paradigmatické tvary: rozhodovací vrstva vyhodnocuje
  všechny aktivní lexémy, včetně časovaných flektivních tvarů.
- [x] Automatický výběr legitimní reakce z historie jazyka: explicitní
  strategie mají přednost; bez nich engine použije jen kurátorovaný recept
  složeniny se dvěma dostupnými kořeny nebo už produktivní gramatický afix.
  Kontakt může při výslovném zapnutí dodat nativizovanou výpůjčku. Ostatní
  případy zůstávají auditovatelné pro autora, neřeší se náhodným segmentem.
- [x] Autorova fronta nevyřešených kolizí: položky s rokem, tlakem a oběma
  lexémy se ukládají do projektu; lze je ponechat nebo otevřít v časové ose
  správce konkrétního jazyka.

## 5. Sociální vrstvy, variety a potřeby

- [x] Populační profil: řád velikosti, rozloha, koncentrace a počet center;
  používá se jako tlak na vznik a divergenci variet, nikoli jako nepodložená
  simulace jednotlivých obyvatel.
- [x] Komunity uvnitř jazyka: podíl, prestiž, mobilita, domény a typ skupiny.
  Mohou být sociální, městské nebo regionální a poskytují ohnisko inovace.
- [x] Lehké dialektní variety: drží jen vlastní divergenci, ne kopii lexikonu;
  při dlouhodobé regionální divergenci vznikne auditní kandidát na odštěpení.
- [x] Povýšení dialektové variety na samostatný jazyk v UI bez přerušení
  historie. Autor v detailu variety vytvoří od zvoleného roku nový uzel a
  dědičnou hranu; simulátor strom sám nikdy nemění.
- [x] Společenské potřeby jako zdroj návrhů: editor jazyka spravuje sílu
  ekonomiky, technologie, institucí a náboženství. Tyto tlaky zvýhodní pouze
  doložené sémantické vztahy v odpovídající doméně a lze je zapsat jako
  časovanou autorskou událost.
- [x] Registry a domény: editor spravuje formalizaci, šíření rituálního užití
  do běžné řeči a seznam tabuizovaných konceptů. Engine nad nimi vede
  neutrální/formální/rituální/tabu/Opisné přechody jako auditní události.
- [x] Síť šíření mezi varietami: editor spravuje komunity, jejich podíly,
  kohorty, mobilitu, městskost, vážené vazby a bilingvismus. Síť nyní váží
  konkrétní fonologickou difuzi i šíření soutěžících lexikálních variant a
  současně řídí sbližování variet.

## 5a. Prostor, státy a historické události — navazující návrh

- [x] Stát jako politická jednotka: jméno, území, instituce a skupina jazyků.
  Stát neznamená automaticky jeden jazyk: v každé epoše vytváří oboustranný
  vnitřní kontakt a instituce mohou nastavovat standardizační tlak.
- [x] Jazyky vznikají z existujícího jazyka nebo z potvrzené variety v zadaném
  roce; odštěpení uloží původní varietu i dědičnou hranu.
- [x] Obchodní trasy jsou samostatné časované objekty s typem
  námořní/pozemní/říční, intenzitou a pořadím jazyků. Autor je kreslí pomocí
  waypointů přímo do plátna a simulátor vytváří kontakt jen mezi jazyky v
  koridoru trasy; staré projekty bez geometrie zůstávají kompatibilní.
- [~] Historické události mají typ, začátek, trvání, cílové jazyky či stát a
  auditní stopu. Přednastavené účinky existují pro migraci, válku, kolaps,
  urbanizaci, standardizaci, náboženskou reformu a obchodní rozkvět. Trvání se
  skládá jako vratný intervalový stav pro základní sociální parametry; chybí
  průběžně proměnlivý účinek a samostatný model trvalých následků.
- [x] Větev uchovává endonymum, exonymum, míru autonomie a kurátorovaný seznam
  jmen; při odštěpení se jméno odvodí z nich. Autorská politická událost může
  časovaně změnit endonymum i exonymum a zanechá samostatnou auditní stopu.

## 5b. Správa jazyka a autorská časová osa

- [x] Samostatná stránka jazyka s řezem v konkrétním roce, auditními
  událostmi, varietami a katalogem jazyků projektu.
- [x] Konceptově i tvarově orientovaný slovník s filtry registru, komunity a
  lexikální třídy; homonyma a synonyma se nezakrývají, ale označují.
- [x] Autorské události jsou uložené v časové ose a auditovatelné. Změny
  metadata zůstávají záměrně autorské; migrace, institucionální tlaky a
  typované historické události mají mechanický sociální účinek.
- [x] Potvrzené operace nad varietou: **odštěpení** vytvoří nový uzel,
  dědičnou hranu a převezme pouze výchozí komunitu. **Asimilace** v simulaci
  vynuluje divergenci variety a označí její komunitu jako asimilovanou;
  **podpora dialektu** jí zachová minimální divergenci a ochranný stav.

## 6. Kontakt a výpůjčky

- [x] Výběr výpůjček podle sémantické domény kontaktu: obchod, náboženství a
  válka upřednostní Concepticonem anotovaná pole jednotlivých lexémů a při
  absenci anotace bezpečně spadnou na celý aktivní lexikon; je krytý regresí.
- [x] Nativizace podle fonotaktiky: výpůjčka se mapuje do cílového inventáře a
  při samotném přejímání projde opravou naučeného fonotaktického profilu.
- [x] Přejímání afixů, konstrukcí a produktivních vzorů: kontakt může přenést
  gramatické morfémy i autorem vybrané ID konstrukcí. Recept pro derivaci či
  složeninu se uloží jako vypůjčený vzor, případně si vypůjčí afix a vytvoří
  první doložený tvar; původ zůstává v genealogii i auditu.
- [x] Zavedení nového fonému výpůjčkami: při vypnuté nativizaci si výpůjčka
  ponechá segment, vstoupí do živého inventáře cíle a může ovlivnit další
  výběr zvukových změn; při zapnuté nativizaci se naopak mapuje do cíle.
- [x] Kontaktní vrstvy: editor a engine rozlišují obchod, náboženství, válku a
  sousedství, směr, prestiž, intenzitu, kalky i lidovou, elitní, písemnou a
  rituální vrstvu; vrstva označí registr přejatého lexému.
- [x] Kontakt jako zdroj konkrétní homofonní náhrady: výslovně zapnutý kontakt
  smí nahradit pouze poražený lexém funkčně zatížené kolize výpůjčkou pro
  stejný koncept. Tvar se nativizuje, nesmí znovu kolidovat a má vlastní
  auditní i genealogickou stopu.

## 7. Sociální a historické síly

- [x] Dialekty a jejich vzájemné šíření: komunity drží explicitní vážené vazby
  a mobilitu; jejich variety se nad nimi částečně sbližují a každá difuze je
  auditní událost. Lexikon se stále nekopíruje.
- [x] Věkové kohorty, město/venkov a síť šíření: agregované kohorty se
  obnovují v auditovatelných krocích a jejich generační profil, městskost a
  mobilita mění receptivitu k difuzi. Síť zůstává záměrně sítí komunit, ne
  nepodloženou simulací jednotlivých mluvčích.
- [x] Standardizace jako změna konkrétních variant: při silné standardizaci
  lexikální soutěž označí a frekvenčně zvýhodní konkrétní nejrozšířenější tvar
  jako standardní variantu.
- [x] Demografie a migrace s vlastním mechanismem: populace, rozloha,
  koncentrace a centra ovlivňují divergenční tlak. Časovaná migrace může
  přesunout podíl do existující komunity nebo založit novou varietu a zároveň
  vytvoří oboustrannou síťovou i bilingvní vazbu k původu.

## Hotový základ, na který roadmapa navazuje

- [x] Časová osa událostí, větvení a dědění rozehraných změn.
- [x] Audit změn a verzování slovních forem.
- [x] Výběr zvukové změny podle toho, zda má oporu v aktuálním lexikonu.
- [x] Základní výpůjčky, kalky, segmentová adaptace a sociální parametry.
- [x] Složeniny, derivace, paradigmata, gramatikalizace, reanalýza a analogie
  jako explicitně konfigurované operace.

## 8. Zbývající produktová a technická práce

Toto je úplný aktuální backlog. Položky výše označené `[~]` nejsou zapomenuté:
jsou zde rozepsané jako konkrétní dokončovací práce.

### Historický prostor a autorská kontrola

- [~] Intervalové účinky historických událostí: základní sociální účinek se
  po konci korektně uvolní a překrývající se účinky se skládají po vrstvách,
  takže konec jedné události nezruší druhou. Chybí průběžně proměnlivá křivka
  účinku a trvalé následky jako samostatný stav.

### Jazykové jádro a validace

- [~] Kurátorovaný globální retenční korpus pro Concepticonové koncepty a jeho
  nezávislá kalibrace. CEE už automaticky sestaví otevřený globální prior z
  Concepticonových seznamů Swadesh 1955 a Peust 2013 (229 namapovaných
  konceptů) a umí importovat jinou lokální tabulku s provenance. Chybí širší
  empirická evidence a nezávislé vyhodnocení tohoto prioru.
- [x] E2E regrese: UI payload → API → simulace → časový řez jazyka → export,
  včetně sémantické inovace, kalkového kontaktu a auditní stopy přenesené
  varianty.

### Datový model, výkon a provoz

- [ ] Typovaná schémata projektových dat a verzované migrace místo volných
  slovníků v uloženém projektu.
- [ ] Výkonnostní benchmark nad 2 000+ lexémy a profilování kopírování stavů,
  paginace lexikonu i čtení genealogie.
- [ ] Rozdělení velkých editorů mapy a správy jazyka na menší komponenty a
  rozhraní simulátoru na plánování událostí, aplikaci a audit.
- [ ] Backendová statická kontrola, lint a minimální coverage gate v CI.
- [ ] Dokončit čtecí Neo4j adaptér, nebo jej formálně odstranit z podporovaných
  rozhraní; souborové úložiště zůstává referenčním během bez Neo4j.

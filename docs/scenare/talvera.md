# Talvera

Talvera je subkontinent mezi severní vrchovinou a dvěma moři. Řeka Eren teče ze severu k jihu a v rovinách se větví do splavných ramen. Západ má chráněné přístavy a Solné ostrovy, jih deště a sezónní plavbu, východ široký úval za deštnými horami. Mezi řekou a západem leží odtoková jezera a staré průsmyky. Východní oceán uzavírají Vnější ostrovy. Dlouhodobě soupeří tři cesty pro dopravu lidí a zboží. Říční cesta zvýhodňuje deltu, souš horská sedla, moře pobřežní uzly.

## Měřítko prvního běhu

- Období od roku −700 do roku 1950. Čtyři výchozí jazykové rodiny, každý prajazyk vznikne z vlastního inventáře a slovníku. Příbuznost uvnitř rodin vzniká během simulace.
- **96 regionů**, v každém z dvanácti pásů osm. Výchozí síť má dvě vesnice na region a městská centra pouze ve vybraných uzlech. Region je jednotka mapy, vesnice a jejich skupiny jsou jednotky simulace.
- **Cíl 45–55 pozorovaných domácích jazyků** kolem roku 1950. Pro ilustraci měřítka odpovídá 96 regionům třeba 24 jazyků v jednom regionu, 16 ve dvou, osm ve třech a dva v osmi. Tohle je rozpočet mapy. Skutečné hranice i počet vzniknou v běhu.
- Rozsah 1–10 regionů posuzujeme podle jazyka, který má v regionu nejvíc domácích mluvčích. Domácí menšiny sledujeme zvlášť, včetně těch, které nikde nepřevažují. Veřejné druhé jazyky mají vlastní přehled.

## Geografie a osídlení

ID `m01-01` až `m12-08` jsou pracovní označení jednotlivých regionů. Tabulka udává, odkud začínají rodiny. Pomezí uvnitř každého pásu se v mapě střídají s přirozenými překážkami.

| Pás | Krajina | Výchozí rodina | Hlavní spojení |
|---|---|---|---|
| M01 · Delta Erenu | Říční ramena, hráze, mokřadní kapsy | serenská | M02, M07, M09 |
| M02 · Dolní Eren | Úrodná niva, zavlažování, říční města | serenská | M01, M03, M07 |
| M03 · Střední Eren | Kotlina, říční brody, říční ostrovy | serenská | M02, M04, M05, M10 |
| M04 · Severní předpolí | Suché pastviny a otevřená brána k horám | serenská / talmurská | M03, M05, M06 |
| M05 · Vnitřní jezera | Dvě jezera s odtokem k Erenu, rudné svahy | talmurská / serenská | M03, M04, M06, M07 |
| M06 · Sedlová vrchovina | Průsmyky, horní pastviny, slepá údolí | talmurská | M04, M05, M11 |
| M07 · Západní zátoky | Hluboké přístavy a sráz k vnitrozemí | veretská | M01, M02, M05, M08 |
| M08 · Solné ostrovy | Laguny, soliska, jeden nízký horský ostrov | veretská | M07, M09 |
| M09 · Jižní monzun | Nábřeží, dvě řeky a vnitřní mokřady | veretská / idarská | M01, M08, M10, M12 |
| M10 · Východní úval | Údolní osy a široká východní zátoka | idarská | M03, M09, M11, M12 |
| M11 · Deštné hory | Izolovaná údolí, horní hřebeny a prameny | idarská | M06, M10 |
| M12 · Vnější ostrovy | Oceánské ostrovy s rozptýlenými kotvišti | idarská / veretská | M09, M10 |

### Vlastní jména jazyků

Prajazyky nesou vlastní jména z generátoru jmen ([dok. 34](../engine-v2/34-jmena-s-historii.md)). Složil je z tehdejších slov receptu v roce −700. Ve [world.json](talvera.world.json) jsou uzamčená v poli `endonym_form`, takže je další běh nevylosuje znovu. Hláskový vývoj jména pokračuje se změnami jeho mluvčích. České názvy (Serenština, serenská rodina…) zůstávají jako popisky pro čtenáře. Přepis do latinky je stejný jako u ostatních jmen (`onomastics::romanize`).

| Popisek | ID | Vlastní jméno | IPA | Složení | Hlavní linie v roce 1950 (seed 1) |
|---|---|---|---|---|---|
| Serenština | `seren` | **Lanokum** | lanokum | „člověk“ + „řeč“ | Lenvogem (lenwoɡəm) |
| Talmurština | `talmur` | **Ngasimon** | ŋasimon | „hora“ + „řeč“ | Ngeze (ŋəzə) |
| Veretština | `veret` | **Omo** | omo | „moře“ + „řeč“ | Vu (wu) |
| Idarština | `idar` | **Anejin** | anəjin | „voda“ + „řeč“ | Anajyn (anajɨn) |

Každá rodina má také zadanou **tradici osobních jmen** (`person_names`) podle tabulky „Výchozí tradice Talvery“ v [návrhu jmen](generovani-jmen.md):

| Rodina | `person_names` | Jméno osoby | Příklad ze seedu 1 |
|---|---|---|---|
| serenská | `house_surety` | jméno při narození + dům, který za člověka ručí | Janbaja Ame („slunce-přítel“, ručí dům „hora“) |
| talmurská | `journey_name` | rodinné jméno + jméno po první samostatné cestě | Korming, Qiatngim („hvězda“, po cestě „žár-slunce“) |
| veretská | `crew_byname` | domácí jméno + palubní přezdívka | Akonole „Neke“ (domácí jméno „sláva“ • na palubě „dlouhý loď“) |
| idarská | `birth_rite` | jméno podle události při narození + obřadní jméno | Usa / Tiahi (narozen při „brod“, obřadní jméno „zákon-člověk“) |

Tradice se mohou měnit: dceřiné jazyky je dědí, liturgie, spisovná norma a dlouhá vláda cizího jazyka je mohou nahradit. Osadníci si tradici nesou s sebou.

Dceřiné jazyky jméno zdědí, nebo se pojmenují po kraji, státu, dřívějším národě či zakladateli. Mohou převzít i jméno, kterým jim říkají sousedé. Celý přehled jmen jazyků, míst a států s časovými osami je v exportu běhu pod `names`. Jméno celého subkontinentu (*Talvera*) je zatím autorské, generátor ho nevyrábí.

Serenové vycházejí z hustě osídlených niv a dělby práce kolem vody. Talmurové z pasteveckých a průsmykových obcí s větším sezónním pohybem. Veretové z pobřežních sítí rybářů, loďařů a překupníků soli. Idaři mají úvalová zemědělská sídla i horské komunity s vlastními pravidly užívání lesů. Časem vzniknou města, vrstvy i smíšené kultury napříč rodinami. Jazyk a politická příslušnost se mohou rozejít.

## Společná časová osa

| Éra | Roky | Kulturní těžiště | Dějinná změna |
|---|---:|---|---|
| I · Antika | −700 až 400 | **Varad** v deltě (`m01-04`) | Správa hrází a obilí vytvoří říční stát. Vnitřní kolonizace, posádky a archivní norma. Povodeň, fiskální krize a válka o brody říši rozlomí. |
| II · Raný středověk | 400–950 | **Tarem** v sedlech (`m06-03`) | Po úpadku říční správy nese dálkovou dopravu pás průsmyků. Talmurské osidlování, útěk z niv a klášterní síť posunou kulturu do hor. |
| III · Vrcholný středověk | 950–1450 | **Selva** v západních zátokách (`m07-04`) | Přístavní liga získá převahu díky úvěru, soli a pravidelným plavbám. Válka o průliv rozdělí ostrovy. Přístavy sdílejí obchodní veretštinu, vnitrozemí má více norem. |
| IV · Věk objevování | 1450–1750 | **Naret** na monzunovém pobřeží (`m09-05`) | Objeví se zámořská trasa, kterou lze zásobovat z jihu. Nové hlízy a luštěniny umožní osídlení některých okrajů. Námořní monopoly, návraty osadníků a přístavní karantény mění kontakty. |
| V · Industrializace | 1750–1950 | **Istren** u jezer (`m05-04`) | Ruda, palivo a průplav zvednou jezera. Pracovní migrace a školství vytvoří městské normy, příhraniční válka a přesuny obyvatel změní mapu. V některých kapsách začne obrození. |

### Pravidla pro rozpracování

- Centrum každé éry má konkrétní výhodu a musí převzít část funkcí předchozího centra. Starší normy a sítě přitom mohou přežít v užších doménách.
- Historické přesuny tvoří územní, ekonomické a sociální podmínky pro jazykovou změnu. Výsledný počet jazyků ani konkrétní hláskové změny se do událostí nezapisují.
- Sledujeme čtyři dlouhé linie malých komunit. Serenské hrázové osady v M01, talmurská slepá údolí v M06, veretské ostrůvky v M08 a idarské pramenné obce v M11. Některé se udrží, jiné mohou přejít na větší kód.
- Každá éra předá další éře změněnou síť, nejméně jeden neuzavřený konflikt a jasný stav psané či veřejné řeči.
- U každé události rozlišujeme přímý zápis do dnešního schématu CEE, aproximaci několika událostmi a historický kontext. Pro první běh držíme výchozí kalibraci enginu.

## I · Antika, −700 až 400

**Varad** leží u rozdělení Erenu na splavná ramena. Obce, které společně udržují hráze, mu postupně svěří výběr obilních dávek. Varad může zásobovat posádky proti proudu a z původního překladiště se stane sídlo říše a písařského vzdělání.

| Rok | Dění v Talveře | Zápis pro CEE |
|---:|---|---|
| −700 | Hrázové osady v `m01-07` a `m01-08` leží mimo hlavní rameno a spravují vlastní rybolov i vodní práva. | Výchozí slabší vazby na Varad, místní vazby a `identity: distinct`. |
| −475 | Po špatných sklizních svěří část obcí Varadu správu zásob výměnou za údržbu hrází. Říše zavádí společné obilní míry a výroční trhy. | `state` **Varadská říše** (`varad`), sídlo `m01-04`, území `m01-01` až `06` a `m02-01` až `04`, politika `tolerant`. |
| −225 až −175 | Říše potřebuje dřevo a brody. Zabere střední Eren a zřídí přístavní celnici v Západních zátokách. Osazuje překladiště rodinami z nivy. Veretští obchodníci si v přístavu udrží vlastní soudy. | `annexation` pro `m03-02`, `m03-04`, `m03-06` a `m07-02`. `settlement` z `m02-03` do `m03-04` a z `m01-05` do `m07-02`. Malá `elite` z `m01-04` v `m07-02`. |
| 25 | Varadská archivní norma sjednotí zápis pozemkových převodů a celních dohod. Část veretských lodníků se učí serensky pro jednání s říčními úřady. | `standard` pro `varad`, gramotnost `elite`. `lingua_franca` z `m01-04` v `m07-01` a `m07-03` bez zdomácnění. |
| 275–325 | Povodeň přeloží hlavní rameno. Příjmy klesnou, Varad zvýší dávky a brodská města v ozbrojeném sporu odmítnou odvádět clo. Rolníci opouštějí poškozenou nivu a přístavní rodiny hledají bezpečnější kotviště. | Povodeň a boje jsou kontext. `settlement` z `m02-02` do `m05-07` a z `m07-02` do `m08-02`. |
| 400 | Říše se rozpadne. Delta si ponechá Varad, dolní niva své sýpky a brodská města vlastní celnice. Sporný brod `m03-06` zůstane bez stálého pána. | `collapse` pro `varad`, následně `state` pro **Varadskou obec** (`varadska_obec`, `m01-01` až `06`, sídlo `m01-04`), **Dolní Eren** (`dolni_eren`, `m02-01` až `04`, sídlo `m02-03`) a **Brodská města** (`brodska_mesta`, `m03-02` a `m03-04`, sídlo `m03-04`). |

**Předání.** Varadská norma zůstává v archivech. Spor o cla zvyšuje hodnotu horské objížďky přes dosud nezávislý Tarem, který zaměstnává uprchlé písaře a přebírá jejich míry a smluvní zvyklosti.

**Co měřit.** Porovnat, zda po rozpadu roste vzdálenost domácích serenských kódů přes nové hranice rychleji než mezi podobně vzdálenými obcemi uvnitř nástupnického státu. Na západě sledovat serenské výpůjčky a zachování domácích veretských skupin odděleně.

## II · Raný středověk, 400–950

**Tarem** nabízí jeden sazebník mýta a ručí za náklad mezi sedly. Přes jezera a hory se proto vyplatí vozit drahé lehké zboží, přestože hromadný náklad dál závisí na Erenu. Klášterní domy vah se stanou zároveň sklady, archivy a školami.

| Rok | Dění v Talveře | Zápis pro CEE |
|---:|---|---|
| 450 | Serenské rodiny od sporného brodu zakládají osadu na jezerních terasách. Přinášejí zkušenost s říční dopravou i příbuzenské kontakty proti proudu. | `settlement` z `m03-06` do `m05-02`, jedna osada, podíl 0,12. |
| 525 | Po několika suchých zimách zakládají talmurské rodiny dvory na dřívějších sezónních trasách. Část se živí povoznictvím. | `settlement` z `m06-04` do `m04-05` a z `m06-05` do `m05-03`, podíly 0,15 a 0,12. |
| 600–650 | Sedlový svaz sjednotí ochranu cesty. Taremští písaři vedle starých varadských listin začnou vyhotovovat vlastní talmurské smlouvy. Slepé údolí `m06-08` zůstane mimo svaz. | `state` **Sedlový svaz** (`tarem`), sídlo `m06-03`, členové `m06-02` až `05`, `m05-02`, `m05-03`, `m04-05`, politika `tolerant`. Poté `standard` a `schools` s `coverage: towns` a `diglossic: true`. |
| 750 | Tarem obsadí sporný brod, aby vybíral mýto z obou stran. Brodská města zavřou přechody. Horské obce dodají stráže, místní rodiny drží převozy. | `annexation` `m03-06` státem `tarem` a dočasná `border_policy: closed` u `brodska_mesta`. |
| 750 | Do brodu přijde talmurská posádka a správa mýta. Velitelé se usadí, berou si místní ženy a jejich řeč nese prestiž sedel. | `elite` z `m06-03` do `m03-06`, 60 lidí, prestiž 1,4 (study case **Posádka na brodu**). |
| 850 | Brod připadne Brodským městům výměnou za otevření průjezdu. Spor o sazby trvá. Kupci zkoušejí západní přístavy, kde jedna smlouva pokrývá převoz i ručení. | `annexation` `m03-06` státem `brodska_mesta` a jeho `border_policy: normal`. |
| 925 | Selva zakládá kupecké kanceláře u jezer a v deltě. Obchodní veretština se používá při sjednávání přepravy. Hrázové osady dál projednávají svá vodní práva domácí řečí. | `lingua_franca` z `m07-04` pro `m05-07`, `m05-08` a `m01-02`, `spread: common`, `nativize: false`. |

**Předání.** Tarem drží sedla a vlastní školní normu. Brodská města ovládají přechod a Selva nabírá zákazníky i v zázemí Taremu. Spor o mýta a záruky dává západním přístavům důvod jednat společně.

**Co měřit.** U přesídlenců z let 450 a 525 sledovat přežití domácího kódu a přibližování k sousedům. U kupeckých kanceláří porovnat růst veřejné veretštiny se změnami domácí jazykové skladby.

## III · Vrcholný středověk, 950–1450

**Selva** získá převahu díky pravidelným konvojům a uznávání dluhopisů mezi přístavy. Kupci překládají na lodě stále větší díl soli, obilí a kovů. Za nimi se do zátok stěhují písaři, učni a řemeslníci.

| Rok | Dění v Talveře | Zápis pro CEE |
|---:|---|---|
| 975 | Rodiny z jezerních dílen dostanou na pobřeží úlevy za výrobu kování a opravy lodí. Udržují spojení s příbuznými a dodavateli u jezer. | `settlement` z `m05-03` do `m07-02`, podíl 0,10. |
| 1050 | Selva, dva přístavy a Solná brána sjednotí clo a řešení obchodních sporů. Každý člen si ponechá vlastní radu. | `state` **Přístavní liga** (`selva`), sídlo `m07-04`, členové `m07-02`, `m07-04`, `m07-06` a `m08-03`, `centralization: weak`, `policy: tolerant`, `border: open`. |
| 1125–1150 | Selva ustálí zápis kupních smluv. Učni se učí vysokou veretskou varietu. Kupci z Dolního Erenu a Naretu se učí obchodní veretštinu kvůli smlouvám a konvojům. | `standard` a `schools` pro `selva`, gramotnost `elite`, pokrytí `towns`, diglosie zapnutá. `lingua_franca` z `m07-04` pro `m02-02`, `m02-04`, `m09-05` a `m10-02`, bez zdomácnění. |
| 1225–1300 | Liga zabere druhý břeh průlivu, aby zabránila dvojímu clu. Její posádky začnou zadržovat i lodě členských měst. Část ostrovanů prchá do přístavů. Solná brána si nakonec vynutí samostatnost a udrží lodivody. | V roce 1225 `annexation` `m08-04` státem `selva`. V roce 1275 `settlement` z `m08-03` do `m07-06`, podíl 0,15. V roce 1300 `secession` **Solné brány** (`pruliv`, území i sídlo `m08-03`). |
| 1350 | Na ostrově `m08-08` vzniká rada společných studní a sezónních lovišť. Obyvatelé obchodují přes prostředníky a děti vyrůstají převážně na ostrově. | `identity: strong` v `m08-08`. |
| 1425 | Naretské rady dají místo loďařským rodinám ze západu. Zimní sklady a výměna posádek umožní čekat na správnou sezónu přímo na jihu. | `settlement` z `m07-06` do `m09-06`, podíl 0,12. Loděnice a sklady jsou kontext. |

**Předání.** Selva drží západní úvěr a konvoje, Tarem horské mýto. Nezávislý Naret má lodě, veřejnou veretštinu a loďařskou osadu v sousedství. Průliv zůstává rozdělený a celní spor trvá.

**Co měřit.** Srovnat domácí idarskou řeč v Naretu a ve vnitrozemském `m10-06`, zejména podíl veretských výpůjček. U ostrovní kapsy `m08-08` porovnat vzdálenost domácích kódů od Selvy se vzdáleností ligového přístavu `m08-04`.

## IV · Věk objevování, 1450–1750

**Naret** leží u dvou říčních ústí. Z jihu lze využít letní vítr k vyplutí a zimní k návratu. Když se oceánské plavby stanou pravidelné, pojistitelé a zásobovatelé potřebují stálé kanceláře v Naretu. Selva si ponechá západní úvěr a sůl, ale organizaci výprav přebírá jih.

| Rok | Dění v Talveře | Zápis pro CEE |
|---:|---|---|
| 1475 | Idařští lodivodi a veretští rejdaři zavedou plavební kalendář. Výpravy míří přes dvě stanice na Vnějších ostrovech dál za mapu. Na jedné zůstávají lodnické rodiny i přes zimu. | `settlement` z veretského `m09-04` do idarského `m12-03`. Průzkum a cesta za mapu jsou kontext. |
| 1525–1550 | Námořníci přivezou **stříbrnou hlízu**, kterou lze pěstovat na vlhkých svazích, a **přílivovou čočku** pro mírně zasolené nížiny. Nové zdroje potravy živí přístavy i dříve řídce obydlené svahy a mokřady. | `settlement` z `m10-04` do `m09-07` a z `m09-05` do `m09-08`. Každý přesun má podíl 0,12 a dvě osady. Plodiny vysvětlují přesuny v příběhu. |
| 1575–1600 | Naret spojí jižní přístavy s ostrovními stanicemi. Selva začne zadržovat lodě na svém břehu průlivu. Nezávislá Solná brána zkusí omezit přejezdy, po ztrátě příjmů znovu otevře překládku. | `state` **Naretský svaz** (`naret`), sídlo `m09-05`, území `m09-05` až `08`, `m12-02` a `m12-03`, politika `tolerant`. `border_policy` pro `pruliv` nejprve `closed`, pak `open`. Selva si ponechá `m08-04`. |
| 1600 | Na ostrovních stanicích se obchodní veretština stane řečí přístavních rodin: sezónní posádky, překupníci a jejich děti spolu mluví jen jí. | `lingua_franca` z veretské osady `m12-03+m09-04-0` pro `m12-03` a `m12-04`, `spread: universal`, `nativize: true` (study case **Přístavní kreol**). |
| 1625–1650 | Po zavlečené horečce zavede Naret sezónní karanténu. Část rodin se přestěhuje z ostrovů na jih za prací a příbuznými. Jiné dál udržují živnost na druhém břehu. | `settlement` z veretského `m12-02` do `m09-08` zachytí přesun obyvatel původních ostrovních vesnic. Karanténa a návraty konkrétních lodnických rodin jsou kontext. |
| 1675–1700 | Naret zavede idarskou kancelářskou normu pro berní knihy a výuku úředníků. Obchodní veretština zůstává užitečná na palubě, v přístavních smlouvách a při jednání se Selvou. | `standard` a `schools` pro `naret` s `towns`, `diglossic: true` a `printing: false`. Veřejná veretština pokračuje z éry III. |
| 1725–1750 | Naretští rejdaři financují sklady u Erenu a vyměřování cesty k Istrenu. Chtějí pravidelné dodávky jezerní rudy, dřeva a paliva. Selva brání výnosy ze západních překladišť. | Kontext. Územní držba M05 se zatím nemění. Pracovní migrace přijde v další éře. |

**Předání.** Naret drží jižní přístavy a dvě ostrovní stanice. Solná brána je samostatná, protější břeh má Selva. Tarem drží sedla. Spor o přístup k jezerní rudě a překladištím dostane nový význam, jakmile se u jezer rozběhnou hutě.

**Co měřit.** Po vzniku osad sledovat jejich velikost, domácí jazyky a kontakt s původními obcemi. V Naretu vykázat zvlášť veřejnou obchodní veretštinu, idarskou školní varietu a skutečné domácí kódy.

## V · Industrializace, 1750–1950

**Istren** má v dosahu rudu, palivo a vodu. Zpočátku vyrábí součásti na naretské objednávky, později sám vyváží stroje. Jeho školy a tiskárny získají dosah díky příchozím dělníkům a technikům, kteří se tu setkávají s místními talmurskými rodinami.

| Rok | Dění v Talveře | Zápis pro CEE |
|---:|---|---|
| 1775 | Istren spojí hutní osady a nákladní překladiště do jezerního svazu. Tarem dál vybírá poplatky na cestě přes sedla. | `state` **Jezerní svaz** (`istren`), sídlo `m05-04`, území `m05-04`, `m05-05` a `m05-06`, politika `tolerant`. Hutě a průplav jsou kontext. |
| 1800 | Serenští povozníci a skladníci zakládají osadu u hutí, veretští loďaři další u překladiště. Příbuzní z obou oblastí hledají práci i přímo ve městě. | `settlement` z `m03-07` do `m05-05` a z `m07-03` do `m05-06`, po jedné osadě, podíly 0,10 a 0,08. `immigration` 0,18 v `m05-04`. |
| 1825 | Istren sjednotí zápis měr a technických příruček podle městské řeči. Taremské školy a kláštery dál používají starší normu. | `standard` pro `istren`, gramotnost `towns`. |
| 1850 | Selva hájí přístup ke skladům u západní výpusti. Istren v ozbrojeném sporu obsadí dosud samostatné území a zavře hranici. Část rodin z výpusti odejde k Dolnímu Erenu. | `annexation` `m05-07` státem `istren`, `border_policy: closed` pro Istren a `settlement` z `m05-07` do `m02-06`, podíl 0,12. Uzávěra v CEE zasahuje celou hranici státu. |
| 1875 | Mír obnoví tranzit se společným ceníkem, výpust však zůstane Istrenu. Svaz vydává pracovní předpisy, financuje obecné školy a levné tisky i mimo městské jádro. | `border_policy: normal`, `schools` s `coverage: mass`, `printing: true` a `diglossic: false`. |
| 1875 | Po válce Istren prosazuje talmurštinu v úřadech i školách nových území. | `language_policy` `istren` `enforced` (study case **Tvrdá politika a obrození**). |
| 1925 | Ve výpusti `m05-07` vznikne serenské obrozenecké hnutí. | `revival` `m05-07`, jazyk `seren`, `strength: movement`. |
| 1925 | Učitelé pramenné obce `m11-08` vydají místní idarské čítanky a dvojjazyčné návody pro sezónní dělníky. Domácí řeč získá vlastní psaný registr. | `standard` pro `m11-08`. Místní obrození lze zkoušet s `identity` a případně s `revival` pro `idar`, pokud se zde mezitím rozšířila jiná rodina. `revival` pracuje s rodinou, takže schopnost oživit konkrétní dceřinou varietu je omezená. |

**Stav roku 1950.** Istren je kulturní a průmyslové těžiště. Tarem si drží sedla a starší normu, Selva pobřežní úvěr a Naret oceánské plavby. Ve škole, na trhu a v rodinách působí různé kódy. Rozsah menšin, jazykového obrození a nových městských variet ukáže běh.

**Co měřit.** V domácích skupinách u hutí a překladiště sledovat podíl kořenů od pracovních migrantů proti stejnému běhu bez obou osad. V talmurském jezerním jádře měřit výslovnost sdílených kořenů proti Istrenu ve variantách s masovým školstvím a bez něj. Mimo školní síť sledovat slepé údolí `m06-08`.

## Podklady pro převod do CEE

### Výchozí mapa

| Rodina | Regiony při startu | Počet |
|---|---|---:|
| serenská (`seren`) | M01–M03, M04-01 až 05, M05-06 až 08 | 32 |
| talmurská (`talmur`) | M04-06 až 08, M05-01 až 05, M06 | 16 |
| veretská (`veret`) | M07–M08, M09-01 až 04 a 07, M12-01 a 02 | 23 |
| idarská (`idar`) | M09-05, 06 a 08, M10–M11, M12-03 až 08 | 25 |

- Naret začíná idarský. Veretské osídlení a veřejná veretština kolem něj mají vzniknout až během dějin.
- Pět hlavních center má výchozí městský uzel. Varad je už na začátku dominantní. Tarem, Selva, Naret a Istren začínají jako menší sídla a postavení získávají událostmi. Ve venkovských regionech nastavíme `city: 0`, protože při vynechání pole by engine přidal město téměř všude. Výchozí měřítko je 192 sídelních skupin. U městského regionu je jedna z nich město.
- Podél hlavních tras budou sousední regiony propojené. Mezi pásy povedou jen konkrétní hrany, například přes brody, průsmyky, přístavy a ostrovní přejezdy. Zápis ve sloupci „Hlavní spojení“ je seznam možných koridorů. Hřeben ani moře z něj automaticky nedělají otevřenou hranici.
- Kotvy menšin jsou `m01-08`, `m06-08`, `m08-08` a `m11-08`. Izolaci založí terén a malé množství vazeb. Kulturní ochranu přidáme jen tam, kde má oporu v události, aby přežití nebylo zadaným výsledkem.
- Výchozí čtyři prajazyky dostanou odlišnou slabičnou stavbu a přízvuk. Seren má středně složitou stavbu s pěti samohláskami, Talmur větší počet souhláskových shluků, Veret převážně otevřené slabiky a Idar střídmější inventář s výrazně odlišným rytmem. Konkrétní inventáře i přepisy ověříme při stavbě světa.

### Překlad historie do událostí

- `settlement` zakládá osady z obyvatel výchozích vesnic daného regionu. Použijeme ho pro konkrétní přesídlení s jasným zdrojem a cílem. `immigration` slouží pro vyšší podíl dospělých přistěhovalců v cílovém regionu. Sama nepřičítá obyvatelstvo ani nevytváří osadu.
- Válku zachytíme změnou hranic, územní příslušnosti, přesídlením nebo příchodem elity. Vynálezy, plodiny, karanténa či průplav mají v modelu konkrétní následky jen tehdy, když je přeložíme do podporovaných událostí. Námořní spojení, která se mají otevřít až v určité éře, nahradíme pozdějšími kontakty vytvořenými osídlením, státem nebo veřejným kódem.
- `standard` a `schools` zakládají psanou normu a její dosah. `lingua_franca` ve výchozím případě rozšiřuje veřejný druhý jazyk. `nativize=true` použijeme jen tam, kde příběh počítá s předáváním veřejného jazyka v rodinách. Událost cílí na skupiny jiné výchozí rodiny, než je zdroj.
- První běh použije explicitní události a `background: none`, aby šlo pozorované přechody přiřadit k dějinám scénáře. V dalších bězích lze samostatně ověřit vliv náhodného pozadí. Vyhodnocení nepodmiňujeme výběrem šťastného seedu.

### Co číst ve výsledcích

1. V každém snímku přiřadit skupinu k pozorované jazykové linii a domácí skupiny sečíst po regionech. Počty podle výchozí rodiny samy o sobě nerozliší dceřiné jazyky. U posledního snímku zaznamenat celkový počet, velikosti oblastí v regionech, menšiny a poměr jednoosadních jazyků.
2. Srovnat vždy dvě podobná místa s rozdílnou historií, například přístavní obec s veřejnou veretštinou a blízkou obec mimo její dosah. Sledovat rozšíření veřejného kódu, změny domácí řeči, výpůjčky a případné zdomácnění zvlášť.
3. Pro conlang sledovat, zda se souběžně vyvíjí tvary zděděných slov, slovní zásoba a gramatika. Porovnat několik slov po časových řezech mezi dceřinými větvemi, mezi městem a venkovem i v izolovaných kapsách. Posuzovat opakovatelné vzorce na několika předem zvolených seedech.
4. Při výchozím kroku 25 let a pozorování každý čtvrtý krok připadne poslední běžný snímek před koncem na rok 1900. Pro jazykovou mapu roku 1950 je potřeba při běhu pořídit snímek i v koncovém roce, nebo jasně vykázat 1900 jako rok posledního snímku.

## První běh

Spustitelný scénář je v [talvera.world.json](talvera.world.json). Převod má 96 regionů, 127 sousedských vazeb a 59 datovaných událostí (od 8. 11. 2026 i čtyři události study cases). Pět center má vlastní jméno a ostatní regiony mají pracovní popisky podle pásu a čísla. Čtyři rodiny používají různé recepty pro vlastní jméno jazyka.

Seed 1, Rust M11 z commitu `05e27e5`, výchozí dynamika a vypnuté náhodné historické pozadí. Běh došel do roku 1950. V posledním pravidelném snímku z roku 1900 měl **123 domácích jazyků** a **211 nářečních shluků**. Padesát jazyků tvořila jediná skupina. Pouze šest jazyků mělo domácí skupiny ve více než jednom regionu. Výsledek se proti cíli 45–55 rozpadá hlavně na malé místní kódy. Tento běh sám neurčuje, nakolik se na výsledku podílí síť, výchozí rozložení center a pravidla pozorování.

Na konci běhu měl Naret 2 033 domácích mluvčích idarského kódu a 690 veřejných uživatelů veretštiny. Veřejní uživatelé jsou podmnožina obyvatel. Vlastní jména domácí řeči z exportu zahrnují `ŋɛ̃nʃem` v Taremu, `t͡somwu` v Selvě a `mɪ` v Naretu. Poslední příklad je zároveň aktuální slovo pro „řeč“ v Naretu a pochází z veretštiny. [Návrh generování jmen](generovani-jmen.md) rozlišuje tento způsob sestavování názvu a historicky uložené vlastní jméno. Od 9. 11. 2026 vede jména modul jmen ([dok. 34](../engine-v2/34-jmena-s-historii.md)). Jméno vznikne jednou, dál se vyvíjí hláskově a výměna obecného slova ho nezmění.

## Rozbor na M12 a study cases (8. 11. 2026)

Engine `a4fb8f2` (M12), semínka 1–3, měření skriptem `scripts/talvera_measure.py`.
Kontrafaktuály mění jen jednu událost, rozsahy jsou přes semínka.

### Mapa

65–70 domácích jazyků (cíl 45–55), 18–22 z jedné skupiny, 24–25 ve více regionech. Bez čtyř
událostí study cases 57–62 jazyků a 12–14 jednoskupinových. Přírůstek dělají hlavně skupiny,
které přešly na talmurštinu pod tvrdou politikou Istrenu (viz níže): pozorování je počítá jako
samostatné jazyky.

### Co měřit podle ér

| Éra | Otázka | Výsledek |
|---|---|---|
| I | serenské obce do 25 km přes nové hranice proti obcím uvnitř nástupce (hlásková vzdálenost) | 0,47–0,52 proti 0,17–0,19; **kontrafaktuál s jedním nástupcem 0,22 přes bývalou hranici** |
| II | přesídlenci 450 a 525 | všichni drží vlastní kód (seren v `m05-02` 549 lidí, talmur v `m04-05` 424); lexikálně 0,44 a 0,57 od starousedlíků |
| III | veretské výpůjčky v Naretu a v `m10-06` | 21–27 % proti 7–9 %; **bez veřejné veretštiny z roku 1150 v `m10-06` 0,6 %** |
| III | ostrovní kapsa `m08-08` a ligový `m08-04` od Selvy (lexikálně) | 0,51–0,57 proti 0,24–0,30 |
| IV | osady 1475–1650 od mateřské obce (hláskově) | 0,20–0,56: zakladatelský efekt, viz níže |
| V | kořeny od dělníků v talmurském jádru | 6–7 %, **bez dělnických osad stejně**: 150 let nestačí |
| V | jezerní obce od Istrenu s masovým školstvím a bez něj | 0,29 proti 0,31 |
| V | slepé údolí `m06-08` | talmurské, 0,53–0,58 od Istrenu |

### Study cases

**Posádka na brodu (750).** Talmurská elita v `m03-06` zanechá v serenštině 15–25 %
talmurských slov, v sousedním `m03-07` jsou 2–5 %. Elita (60 lidí) ale na serenštinu
nepřejde ani za 1 200 let (franská elita v Galii přešla za ~300 let).

**Přístavní kreol (1600).** Nevznikne. V Naretském svazu je úředním jazykem idarština
(prestiž domácích skupin 0,72, veřejné veretštiny 0,58), veretsky se domluví 12 % lidí a tah ke
zdomácnění je 0,02. Model tvoří nový domácí jazyk z lingua franky jen s prestiží nebo nutností.
Pro skutečný kreol by stanice potřebovala smíšené obyvatelstvo bez společného domácího jazyka.

**Tvrdá politika a obrození (1875, 1925).** V anektované výpusti `m05-07` přejde za 75 let na
talmurštinu 57–83 % lidí (kontrola `m05-08`: všech 1 100 serensky). Obrození z roku 1925 do
roku 1950 nic nezvrátí. Přešlé skupiny mají talmurský slovník (lexikálně 0,006 od Istrenu), ale
serenskou výslovnost (hláskově 0,40: odpadají koncové slabiky, *hjæsaneh* → *hjanə*), a proto
je pozorování počítá jako šest nových jazyků.

**Zakladatelský efekt (pokus, ne událost scénáře).** Osada ze 12 % obyvatel regionu (~150 lidí)
se od mateřské obce odchýlí o 0,08 už v první generaci i ve vlastním jazykovém regionu, ve
veretském regionu o 0,13–0,16; osada z poloviny obyvatel (~500 lidí) jen o 0,045, tolik jako dvě
vesnice mateřského regionu. Malá komunita v modelu rychle dokončí nebo zahodí rozjeté změny
(tlak populace podle Trudgilla, unášení). Vazba na mateřskou obec ani sdílené ocenění změn
s mateřským regionem to nezměnily.

### Pro engine

- Varieta po přechodu jazyka (stejný slovník, cizí výslovnost) se počítá jako samostatný jazyk:
  pozorování by mělo vážit slovník víc než výslovnost.
- Zakladatelský efekt malých osad je silný; měřítko pro novou osadu (Trudgill 2004, koiné za 2–3
  generace) by mělo zpomalit první generace.
- Elita se v Talveře nepřizpůsobí jazyku poddaných.

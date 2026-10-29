# M6e: průběžné indexy podle změněných slov

Nové zadání uživatele nahrazuje po neúspěšném experimentu plán s Numbou.
Profil údolí za 1 000 let: 92 milionů volání, žádná funkce nad přibližně
5 % vlastního času, aplikace procesů mimo prvních 45 míst. Podle měření
uživatele se na skupinu a krok mění průměrně 4,8 z 364 slov (1,3 %).
Problémem je opakované odvozování nezměněných hodnot, nikoli aplikátor.

## Postup a brána

1. Vrátit produkční integraci Numby i číselné zrcadlo `FormStore`, odstranit
   závislost a kód bez spotřebitelů. Zachovat `scripts/v2_timing.py`.
2. Zapsat závislosti všech níže uvedených výpočtů a doplnit chybějící
   deníky. Neměnit při tom původní `version` / `lexicon_version`, náhodu
   ani okamžiky záměrně zastaralého hodnocení (`STALE_TICKS`).
3. Převést **první dva výpočty**: lexikální jasnost a hodnocení zvukových
   procesů včetně přípravy jeho vzorku. Změna několika tvarů oběma dosud
   zneplatňovala velkou část odvozených dat. Sémantická místa už naproti
   tomu používají `lexicon_version` a samotné přepisy tvarů je neobnovují.
4. Po těchto dvou výpočtech vyhodnotit **údolí ≤ 25 s**. Používá se stejný
   `valley-50` jako v `scripts/v2_digests.py`: 50 skupin, syntax a význam,
   2 000 let. Pokud brána neprojde, další výpočty nepřevádět a plán znovu
   přehodnotit s uživatelem. Všech sedm otisků musí zůstat přesně shodných,
   pokračování z checkpointu musí odpovídat nepřerušenému běhu.

## Audit závislostí

„Procesy“ v tabulce rozlišují existenci kandidáta od skutečně zapsané
změny tvaru. Podkladový tvar se nepřepočítává proto, že se jen změnila
frekvence právě aktivního zvukového procesu.

| Výpočet | Tvar slova | Koncepty a frekvence | Procesy a další stav | Gramatika | Pořadí a invalidace |
|---|---|---|---|---|---|
| `LexicalClarity.scores` / `_clarity_map` | Tvar kandidáta, původní délka a homofonní tvary dominantních kořenů | Koncept → dominantní kořen; příbuznost v grafu, nikoli tokenová frekvence | Dosažené sloty z `freqs`/`heard`; aktivní proces jen přes zapsaný tvar | Přímá závislost není | Skóre nejprve −0,5 za erozi, potom nejvýše −0,4 za kolizi; dosud cache podle `state.version` |
| `Entrenchment.scores` | Ne | Konceptová frekvence, aktuální `batch.freqs >= 0.5` | Payload slotu s morfémem | Ne | Vektorový bodový výpočet; není to přestavba celého lexikonu |
| `Motivation.scores`, `Taboo.scores`, `LexicalActuation.scores` | Ne přímo | Payload/původ varianty, tabu skupiny, čas a délka generace; sociální parametry | Batch a seed podle původních stabilních ID | Ne | Konkrétní tlak zachovává původní vzorec a pořadí; neměnný payload není třeba znovu odvozovat ze slovníku |
| `_process_scores` | Přes `ProcessAssessment` | Frekvenčně vážený vzorek a jeho výběr | Konkrétní proces, dosažené sloupce a slot „změna“; `batch.memo` sdílené tlaky | Přes assessment | Obal sám neprochází lexikon; drahé jsou podklady a opakovaná obsluha skupin/variant |
| `_vocabulary`, `_assess_batch` | Form ID, délky, výsledek procesu, příznakovost, vokály, skupiny homofonů | Seřazený výběr nejčastějších slov, `usage_frequency`, konceptové frekvence a váhy buněk | Neměnný konkrétní proces a pravidlo přízvuku; ostatní procesy přes zapsané tvary | Kompenzované buňky ovlivňují váhu homofonních dvojic | Zachovat `STALE_TICKS`, původní vzorek a jeho pořadí, NumPy `sum(axis=1)` i šířku dávky; dvojice podle seřazeného výsledného form ID a původních pozic |
| `_form_scores` / `morphology.assess` | Cílová jednotka, citační kořen, kmen, hranice a koncovka; podoby produktivních koncovek | Frekvence lexému; počty koncovek dané třídy/buňky | Analogická změna a dosažené sloty, podíl L2 u Teachability; jiné procesy přes zapsané tvary | Jen případné změny forem a inventáře buněk; samotné skóre čte hlavně morfologii | `ClassStats.share` a odečtení dvou podílů v původním pořadí; dosud `state.version` |
| Lexikální `SemanticChange._sites` | Ne: dnešní podoby se používají až při `build` varianty | Dominantní kořeny, jejich třídy a etymologie, graf vztahů a recepty, odvozovací přípona, tabu, lexikální proměnné repertoáru | Typ změny a jeho možnosti | Třída slova z metadat | Dosud `lexicon_version`; zachovat pořadí možností i `sum(weight for ...)`, protože pořadí řídí RNG |
| Morfologické `Leveling._sites` | Tvar buňky a citační kořen | Členství jednotky ve slovní zásobě | Druh analogie | Inventář buněk paradigmatu | Příspěvek závislý i na kořenu; seřazená ID míst |
| Morfologické `Extension._sites` | Buňka, citační kořen a produktivní koncovka | Členství, globální celočíselné počty koncovek třídy/buňky | Druh analogie | Inventář buněk | Změna produktivity musí zneplatnit všechny závislé jednotky dané třídy/buňky, ne jen přepsané slovo |
| Morfologické `Rebracketing._sites` | Slovesný kořen, tvar částice | Dominantní slovesa a zdroj částice | Druh analogie | Dominantní záporová konstrukce a její zdroj | Původní `state.version` dnes nezachycuje každou samostatnou změnu konstrukce; deník musí existovat před jemnější invalidací |

## Deníky a hranice mutací

| Vstup | Deník / signál | Konzument a bezpečnost |
|---|---|---|
| Zapsané tvary | Dosavadní `FormStore.token` a `log` | Kurzor indexu; změna identity nebo neplatný kurzor znamená plnou obnovu; čte se konečný tvar každého změněného slova |
| Dominantní koncepty | `PhonologyState.dominant_log`: koncept, starý a nový kořen | Zaznamenat i přechodný odchod na `None` a následný příchod; sdílený kořen se nesmí předčasně odstranit |
| Užívání kořene | `usage_log`: kořen a původní/nový počet užití | Změna konceptu může změnit váhu všech buněk stejného lexému, i když tvar zůstal stejný |
| Členství ve slovní zásobě | `vocabulary_log`: příchod/odchod a ID jednotky | Neměnit původní počty inkrementů `lexicon_version`; inicializace má také svůj záznam |
| Konceptové frekvence | Verze a deník mapy frekvencí | Běžný dotaz kontroluje verzi v O(1); při přímém nahrazení mapy konzervativní obnova, bez nového řazení vzorku mimo původní podmínky |
| Aktivace/uzavírání | `lifecycle_log`: proces/analogie, akce, stabilní ID | Nový proces a změny živých množin se nesmějí zaměnit za přepis všech slov |
| Konstrukční distribuce | `grammar_log`: konstrukční proměnná při skutečné změně distribuce | Zápis po přenosu před konzumenty; aktuální distribuci číst přes `World.distribution` |
| Zapsaná gramatika | `grammar_applied_log`: ID zapsané varianty | Případný přepis slov současně patří do `FormStore.log` |

Deníky obsahují data, nikoli closure nebo odkazy na svět. Checkpoint je
kopíruje včetně kurzorů indexů. Graf vztahů (`ConceptGraph`, neměnná
n-tice relací), procesy a morfémy mají neměnná metadata; jejich výměnu lze
detekovat identitou. Přímá editace soukromých odvozených struktur grafu
není podporovaná mutační cesta. Při zjištěné veřejné mutaci mimo deník se
použije konzervativní obnova, nikoli úplný scan všech vstupů při každé
běžné změně tvaru.

## Zachování součtů a ověření

Příspěvky lze uchovávat po slovech a integer indexy aktualizovat
odebráním/přidáním. Float agregát se **nesmí** udržovat opakovaným
odečítáním/přičítáním: jeho zaokrouhlení by záviselo na historii změn.
U výsledku se znovu provede původní agregace ve stejném pořadí; v hodnocení
procesů zůstává NumPy redukce nad původně uspořádanými sloupci.

Každý nový index má test „průběžně = od nuly“: změny více slov a více
konceptů, návrat původního tvaru, změny frekvencí a členství, homofonie,
gramatická kompenzace a checkpoint. Vedle shody výsledků se kontroluje,
že změna jednoho slova skutečně nevyvolala přepočet nezměněných slov.

## Výchozí měření pro nový plán

Referenční commit `3d1016c`, stejný Python 3.11.9 a NumPy 2.4.6:
všech sedm očekávaných otisků souhlasí; mřížka 3,8 s, údolí 38,2 s.
Nové jádro se před bránou porovná v jednom sledu s touto výchozí kopií,
bez souběžného testování či simulací.

## Výsledek brány po prvních dvou výpočtech

**Brána neprošla; další výpočty se nepřevádějí.** Sériové porovnání
výchozího commitu a inkrementálního prototypu stejným interpretem:

| Scénář | Výchozí commit (s) | Dva indexy (s) |
|---|---:|---:|
| phonology | 0,2 | 0,2 |
| morphology | 0,4 | 0,4 |
| syntax | 0,6 | 0,6 |
| grid-5x5 | 3,5 | 3,7 |
| shift | 1,1 | 1,2 |
| island-city | 0,9 | 0,9 |
| valley-50 | **37,3** | **39,0** |

Požadavek ≤ 25 s nebyl splněn. Údolí je v tomto páru přibližně o 4,6 %
pomalejší. Všech sedm otisků obou běhů přesně odpovídá původnímu zadání.
Rychlá sada: **540 prošlo, 72 vynecháno, 18,59 s**. Ruff i mypy čisté.
Celá sada včetně milníkových bran a checkpointů: **612 prošlo za
279,75 s (4 min 39 s)**. Větší počet testů a rozdílná povaha celé sady
neumožňují tento čas zaměnit za splnění brány údolí.
Rollback Numby a nepoužívaných sloupců je uložen samostatně v `f626f1f`;
měřič zůstal a jeho volba `--helpers` rozlišuje sledované výpočty.

### Rozpad času

Další dvojice běžela se stopkovým měřičem, opět sériově. Časy jsou
inkluzivní, proto se řádky nesmějí sčítat: například assessment je uvnitř
`_process_scores`, ten je uvnitř přenosu. Totéž platí pro mapu jasnosti.
V obou instrumentovaných bězích souhlasí otisk údolí.

| Oblast | Původní (s) | Inkrementální (s) |
|---|---:|---:|
| Celý běh s měřičem | 36,721 | 38,824 |
| Inovace | 14,066 | 14,342 |
| Přenos | 20,301 | 21,801 |
| `_assess_batch` | **4,469** | **6,375** |
| `LexicalClarity.scores` | **3,154** | **1,761** |
| `_clarity_map` | 0,287 | 0,226 |
| `_process_scores` | 6,762 | 8,434 |
| `_form_scores` | 1,988 | 2,087 |
| Fonologizace | 2,675 | 3,079 |
| Pozorování | 2,352 | 2,679 |

První index v tomto páru snížil cenu lexikální jasnosti přibližně o 44 %
(1,393 s), ale druhý index zdražil assessment přibližně o 43 % (1,906 s).
Nelze tvrdit, že inkrementální přístup obecně nepomáhá: pomohl prvnímu
výpočtu. **Konkrétní druhá implementace však neprokázala výkonový přínos.**

Assessment stále připravuje celé matice skupiny × vzorek, kopíruje do
nich pět uložených polí, redukuje je v původním pořadí a znovu vyhledává
homofonní dvojice; vokálové změny znovu procházejí všechna zasažená slova.
Přidaná cache přitom částečně nahrazuje už levná vektorová čtení z
`ProcessTable` a `FormBank` novou správou kurzorů a polí. Časový rozpad
lokalizuje regresi v assessment, ale neizoluje cenu každé jeho operace.

Lexikální jasnost dál vytváří celý výstup a dosaženou masku a prochází
všechny dosažené kombinace proměnných, slotů a skupin. Index odstranil
opakované odvozování nezměněných slov, ne toto procházení výsledných buněk.

Nové indexy jsou zatím experiment na pracovní větvi; brána je nepřijala
jako úspěšnou výkonovou etapu. Do `engine-v2` se nic neslučuje. K dalšímu
rozhodnutí patří oddělené ponechání první optimalizace a vrácení druhé;
bez přehodnocení plánu se neprovádějí další optimalizace.

## Druhá iterace: uživatelem autorizované pokračování

Po oznámení první neúspěšné brány uživatel výslovně zadal „Pokračuj“.
Pokračování zůstává u průběžných indexů; odmítnutá Numba ani číselná
fasáda se nevracejí.

- Odstraněna regresní `ProcessWordIndex` a produkční `_assess_batch`
  vrácen na původní vektorový výpočet. Inkrementální příprava vzorku
  zůstává, včetně původní viditelnosti frekvencí a výběru slov.
- `LexicalClarity.scores` připravuje metadata kandidátů jednou pro dávku
  a vybírá dosažené buňky jednou na skupinu. Zachovává všechny cache,
  masky, duplicity a pořadí; hodnoty zapisuje hromadným indexováním.
- Sémantická místa používají společný přehled závislostí pro všech sedm
  rodin. Přepočítávají pouze cíle ovlivněné změněnými dominantními
  koncepty, vztahy, složeninami a odvozeninami. Konfigurace a záloha
  přímých mutací se kontrolují jednou na kód a `lexicon_version`, nikoli
  sedmkrát. `_derivations` zatím stále provádí jeden úplný průchod na
  `lexicon_version`; není vydáván za inkrementální.
- Vyrovnání a rozšíření morfologických vzorů sdílejí index jednotek,
  citačních kořenů a buněk. Změna citačního kořene zasáhne jeho buňky;
  změna produktivního exponentu nebo dostupnosti koncovky celou příslušnou
  buňku. Stávající `ExponentIndex` se neduplikuje. Rebracketing zatím
  zůstává referenčním úplným výpočtem.

Samostatný kontrolní běh po vrácení procesní cache trval 43,9 s pro
údolí, všechny otisky souhlasily. Není to párové srovnání ani důkaz
zrychlení či zpomalení této dílčí změny; rozhodující je následné měření
ustálené kombinace změn proti původní kopii.

### Další dokončené části a odmítnutý pokus

`morphology.assess` nově drží výsledky včetně `None` a ruší pouze závislé
varianty podle změněné jednotky, citačního kořene, frekvence, počtů
koncovek a podoby cílového exponentu. Záloha přímých změn dominant se
provádí jen při `lexicon_version`, nikoli při každé změně tvaru.

`_process_scores` a `_form_scores` sdílejí layout a výsledky assessmentů
jen po dobu `PressureBatch`. Vestavěné tlaky používají bodovou aritmetiku
nad poli místo opakovaného skalárního volání NumPy. Zachováno je pořadí
assessmentů i `None`, NaN, nekonečna a znaménka nul; nulový podíl L2 stále
ukončí Teachability před assessmenty.

Slabost gramatických buněk (`syntax.weakness`) drží celočíselné počty
všech a splynulých tvarů. S morfologickými kandidáty sdílí členství a
vazby citačních kořenů, ale konzumenti mají nezávislé kurzory. Samotná
slabost nevynucuje výpočet kandidátů ani `class_stats`.

Vyzkoušen byl také deník celočíselných delt podpory zvukových kandidátů.
Izolované běhy standardní sady otisků:

| Konfigurace stejné průběžné verze | Údolí (s) |
|---|---:|
| Se všemi prototypy | 33,3 |
| S původní podporou kandidátů | 31,9 |
| S původními sémantickými místy | 36,7 |

Všechny otisky souhlasily. Delta index opory byl **odmítnut a celý vrácen**,
včetně nových deníků/testů bez dalšího spotřebitele. Opakoval zpracování
stejných delt pro každou rodinu nadále vedle sestavení celé statistiky;
zůstává původní efektivní maticový výpočet. Sémantický index naopak
prokázal přínos a zůstal zachovaný. Tyto izolační běhy jsou jiné měření
než závěrečný pár níže.

### Závěrečné ověření druhé iterace

Sériový pár proti `3d1016c`, bez souběžných simulací/testů:

| Scénář | Výchozí commit (s) | Druhá iterace (s) |
|---|---:|---:|
| phonology | 0,2 | 0,2 |
| morphology | 0,4 | 0,4 |
| syntax | 0,6 | 0,5 |
| grid-5x5 | **3,5** | **2,7** |
| shift | 1,2 | 1,0 |
| island-city | 0,9 | 0,7 |
| valley-50 | **37,6** | **31,0** |

Údolí zrychlilo v tomto páru asi o 18 %, mřížka asi o 23 %.
**Limit 25 s stále není splněn.** Všech sedm původních otisků přesně
souhlasí. Rychlá sada: **570 prošlo, 72 vynecháno, 31,49 s**. Celá sada
včetně bran a checkpointů: **642 prošlo za 241,75 s (4 min 1 s)**. Ruff
i mypy čisté. Počet testů se změnil; čas celé sady není náhrada měření
samotné simulace.

Jádro `_innovate` a způsob náhodného losování v této iteraci zůstaly
beze změny. V pracovním souboru zadání mezitím přibyl dodatek fáze 5,
který povoluje jednorázovou změnu otisků. Protože předchozí přímá zpráva
uživatele požadovala bitovou shodu, potvrzení tohoto rozdílu je otevřené;
nové losování zde není implementováno. Uživatelská úprava zadání zůstává
mimo commity této iterace.

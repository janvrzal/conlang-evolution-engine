# 23. Evropa (M8, návrh)

Stav: **návrh k potvrzení uživatelem** (6. 11. 2026). Navazuje na Romanii (dokument 22, M7.3).

Cíl stejný jako u Romanie: ne kopie dějin, ale svět, který s podmínkami podobnými evropským
(*nudge*) vyprodukuje **rodiny podobné** románské, germánské, keltské a slovanské, včetně jejich
vzájemného kontaktu. Hodnotí se profil rodinné podobnosti (pořadí a směr změn, rozdíly mezi
větvemi a rodinami, k z N běhů), ne letopočty.

## Co model už umí a co chybí

Engine má události po skupinách: `migration` (lidé jazyka X se usadí v regionu), `conquest`
(cizí elita nad poddanými), `religious_change` (liturgický jazyk), `war`, `contact`, `epidemic`,
`state_collapse` (`events.rs`). **Popis světa (`WorldSpec`) je ale nezná** (dokument 16: „událostí po
skupinách zatím ve WorldSpec nejsou“) a `spec.py` přijímá jen události států a regionů. Potřeba:

1. **Události v popisu světa po regionech**: `migration` (jazyk, zdrojový region, cílový region,
   podíl), `conquest` (jazyk elity, region sídla, poddané regiony, síla), `religious_change`
   (liturgický jazyk, regiony). Engine si skupiny dohledá podle regionu a jazyka.
2. **Protojazyky bez slovníku z dat**: kromě latiny (dokument 22) se slovník generuje, jako
   u substrátů v Romanii. Pro rodinnou podobnost rozhoduje gramatika, inventář a podmínky, ne
   konkrétní slova; slovník z dat (IE-CoR) lze doplnit později.

## Scénář (návrh)

Start kolem roku 500 př. n. l., konec 1900; 25 let na generaci.

| region | jazyk na startu | podmínky |
|---|---|---|
| Itálie | latina (dokument 22) | jádro Říma |
| Galie, Hispánie | galština, iberština | romanizace (jako Romania), od 400 franská a vizigótská elita (dobytí, germánská) |
| Dácie | dáčtina | krátká romanizace, od 600 slovanská migrace |
| Británie | britonština | římská správa bez romanizace venkova, od 450 anglosaská migrace na východ, od 1066 normanská (románská) elita |
| Bretaň (Armorika) | britonština | přistěhovalci z Británie (keltský okraj) |
| Germánie, Skandinávie | pragermánština | bez Říma; od 800 seveřané do Británie (kontakt) |
| Slovanská pravlast | praslovanština | od 500 migrace na Balkán a do Dácie |
| Balkán | ilyrština nebo řečtina | Řím, pak slovanská migrace; kontakt s latinou a řečtinou (balkánský svaz) |

Gramatika protojazyků: pragermánština a praslovanština s bohatými pády (předmět, plurál, minulý čas
synteticky), bez členu; keltština s mutacemi zjednodušeně jako syntetický předmět. Liturgická latina
v západní církvi, církevní slovanština na Balkáně a východě (`religious_change`).

## Profil podobnosti (návrh cílů, `k` z `N`)

| cíl | tvrzení | opora |
|---|---|---|
| Romania | profil z dokumentu 22 (10 cílů) platí i v evropském světě | dokument 22 |
| keltský ústup | galština a iberština zaniknou (přechod na latinu); keltština přežije aspoň v jednom okrajovém regionu | historie (velština, bretonština) |
| angličtina | germánská větev v Británii ztratí víc pádů než germánština na kontinentu | angličtina proti němčině a islandštině |
| franská stopa | franská elita v Galii přejde na latinu a zanechá v ní jen málo slov | stovky franských slov ve francouzštině |
| slovanské pády | většina slovanských větví si pád předmětu udrží | slovanské jazyky mimo bulharštinu a makedonštinu |
| balkánský svaz | slovanská větev na Balkáně ztratí pád nebo získá člen častěji než ostatní slovanské | bulharština, makedonština (Joseph 1983, *The Synchrony and Diachrony of the Balkan Infinitive*) |
| rodiny | jazyková vzdálenost uvnitř rodiny je menší než mezi rodinami | samozřejmost, kontrola modelu |
| počet jazyků | v roce 1900 desítky jazyků, ne jeden a ne stovky | evropská mapa |

## Postup

1. Události po regionech v `WorldSpec` (Rust, `spec.py`, kontrola popisu světa).
2. Scénář `src/cee/data/scenarios/evropa.json` a měřidlo `cee calibrate --only evropa`
   (po rodinách a regionech).
3. Cíle jako profil podobnosti; nudge jen podmínkami scénáře.
4. Výkon: odhad 9 regionů × 4 až 6 vesnic × 96 generací, desítky sekund na běh.

## M8a: postaveno (6. 11. 2026)

Schválil uživatel („Ano, stavět“). Zapsáno:

- **Události po regionech v popisu světa** (Rust `spec::region_event`, `spec.py`): `settlement`
  (`from`, `to`, `share`, `settlements`, `prestige`) se přeloží na migraci do nových osad v cílovém
  regionu (`migration` nově umí `region`, kam osada patří); `elite` (`from`, `seat`, `subjects`,
  `language`, `population`, `prestige`, `strength`) na dobytí. Elita i poddaní se dohledají **až v roce
  události** (`region:jazyk` = největší skupina toho jazyka v regionu, `@region` = všechny mluvené
  skupiny regionu), protože romanizace mezitím vesnice přestaví.
- **Scénář** `src/cee/data/scenarios/evropa.json`: 10 regionů, 7 prajazyků (latina z dokumentu 22;
  galština, iberština, dáčtina, pragermánština s pevným silným přízvukem na první slabice,
  praslovanština, řečtina se členem; generované slovníky), −500 až 1900. Řím (romanizace), anexe
  Británie (43) a Dácie (106), odtržení Dácie (271) a Británie (410), Vizigóti v Hispánii (418),
  Anglosasové do Británie (450), Frankové v Galii (486), nástupnické státy s úřední latinou, Slované
  na Balkán (550) a do Dácie (600), seveřané (870) a Normané (1066) jako elita v Británii.
- **Měřidlo** `cee calibrate --only evropa` (12 semínek, 31 s): podíly jazyků v regionech, pád a člen
  po rodinách, vzdálenost uvnitř rodin a mezi nimi, počet jazyků; zatím cíl `m8::evropa_info`
  (informace).

### První běh bez ladění

| bod profilu | medián 12 semínek |
|---|---|
| románské větve bez pádu | 4 ze 4 |
| galština a iberština zaniknou (podíl < 0,1) | ano |
| keltština přežije na okraji | ano (Armorika 1,00, Británie 0,56) |
| franská elita přejde na latinu | ano |
| slovanská pravlast drží pád | ano |
| počet jazyků v roce 1900 | 25 |
| vzdálenost uvnitř rodin / mezi rodinami | 0,58 |
| germánština v Británii převládne | **ne** (podíl 0,10) |
| angličtina ztratí pád a pevninská germánština ne | **ne** |
| balkánská slovanština ztratí pád nebo získá člen | **ne** (Slované na Balkáně 0,16) |
| latina v Dácii | 0,07 |

Selhání mají jednu příčinu: **přistěhovalci se usadí, ale jejich jazyk se nešíří**. Historicky přešli
Britové na angličtinu a Balkán na slovanštinu díky anglosaským královstvím a bulharské říši, tedy
přes státy s úředním jazykem přistěhovalců. Další krok: tyto státy jako podmínky scénáře.

## M8b: profil podobnosti splněn (6. 11. 2026)

Tři podmínky scénáře a jedna úprava enginu:

1. **Státy přistěhovalců**: anglosaské království v Británii (600, úřední germánština, po zániku
   subrímské Británie v roce 599) a bulharská říše na Balkáně (681, úřední slovanština), obě s politikou
   `romanization`. Bez nich se přistěhovalci usadí, ale jejich jazyk se nešíří (Británie 0,10 germánštiny,
   Balkán 0,16 slovanštiny); s nimi Británie 0,82 a Balkán 1,00.
2. **Moře**: Británie sousedí jen s Galií a Armorikou. Přímé vazby do Germánie a Skandinávie přenášely
   ztrátu pádu z angličtiny na pevninu; kontakt se seveřany obstará jejich elita (870).
3. **Elity se od domoviny odtrhnou** (`homeland` 0 u událostí `elite`): dobytí dřív spojilo elitu
   s domovinou poloviční silou. Franská, vizigótská a seveřanská elita mezi poddanými jiného jazyka
   ztratila pád a jako skupina stejné linie ho poslala zpět do Germánie a Skandinávie (pád tam zanikl
   kolem 1500, aniž by se tam ztráta navrhla). Engine: nové pole `homeland` (síla vazby k domovině;
   bez něj polovina `strength` jako dřív, 0 = bez vazby), Rust i `spec.py`.
4. Pragermánština má přízvuk na první slabice se **slabou** silou (silný mazal koncovky i na pevnině).

### Cíle `m8::*` (12 semínek, `k` z `N`)

| cíl | tvrzení | výsledek |
|---|---|---|
| `romanske_pady` | románské větve ztratí pád (≥ 3 ze 4, `p_min` 0,8) | 12/12 |
| `keltsky_ustup` | galština a iberština ustoupí latině (`p_min` 0,8) | 12/12 |
| `keltsky_okraj` | keltština přežije na okraji (`p_min` 0,5) | 12/12 |
| `anglosasove` | germánština v Británii převládne (`p_min` 0,5) | 12/12 |
| `anglicke_pady` | germánská větev v Británii ztratí pád, pevninská ho udrží (`p_min` 0,5) | 12/12 |
| `franska_elita` | franská elita v Galii přejde na latinu (`p_min` 0,8) | 12/12 |
| `slovanske_pady` | slovanská pravlast si pád udrží (`p_min` 0,8) | 12/12 |
| `balkansky_svaz` | balkánská slovanština ztratí pád nebo získá člen (`p_min` 0,2) | 3/12 |
| `pocet_jazyku` | v roce 1900 desítky jazyků [10; 60] | 21,5 |
| `rodiny` | vzdálenost uvnitř rodin / mezi rodinami ≤ 0,8 | 0,56 |

**Evropa 10 z 10, kalibrace celkem 32 z 32, brány 47 z 47, testy prošly.** Celý běh Evropy trvá
asi 8 s, měření 12 semínek 31 s.

**Slabá místa:** balkánský svaz jen ve 3 z 12 běhů (pád ztracen, člen nevznikne nikdy: řečtina
přejde na slovanštinu a člen se nepřenese); latina v Dácii jen 7 % (rumunština nevznikne, Dácie
mluví dáčtinou a slovanštinou); slovník prajazyků kromě latiny je generovaný (od M8e z IE-CoR).

## M8c: vesnice regionu se liší (6. 11. 2026)

Podnět uživatele: „jazyky se až příliš snadno nahrazují a malé, lokální jazyky těžko přežívají; nejde
o 1:1 repliku, ale něco uvěřitelného.“ Rozbor:

- **Malé jazyky přežít umějí, když mají důvod.** Zkouška s Vaskonií (hory, silná identita, uvnitř
  římské Hispánie) dala 92 % baskičtiny, Řecko s vlastním státem (395) 100 % řečtiny. Velkou část
  nahrazování způsobil scénář, který takové regiony neměl.
- **Přechod jazyka byl deterministický.** Za generaci přejde očekávaný podíl (Abrams a Strogatz 2003)
  bez náhody a vesnice regionu byly totožné kopie (stejná loajalita i velikost), takže podíly jazyků
  vyšly ve všech semínkách stejně; semínko řídilo jen hláskové, slovní a gramatické změny.
- **Víc vesnic samo nepomůže** (3× víc při stejné populaci regionu: téměř beze změny), kopie dají totéž.
  Rozptyl loajality se 4 vesnicemi také ne. Teprve obojí dá první ostrůvky.

Zapsáno (schválil uživatel: „loajalita by měla být nějaká distribuce okolo střední hodnoty“,
„Ano, zapsat“, „Oříznutí, retence zvlášť“):

1. **`loyalty_spread` 0,25** (nový parametr, skupina `society`): loajalita vesnice = hodnota regionu
   (`identity_loyalty`) + odchylka z N(0; 0,25) podle semínka a jména vesnice, oříznutá do [0; 0,95]
   (`scenarios::village_loyalty`). Totéž platí při události `identity` (stejná vesnice dostane stejnou
   odchylku). Oříznutí zvedne průměr regionu se sdílenou identitou (0) asi na 0,1: i v takovém regionu
   se vesnice liší a některé drží jazyk déle.
2. **Evropa má 3× víc vesnic** (12 na region, Armorika a Skandinávie 9) i osad přistěhovalců; velikost
   vesnice zůstala.
3. **Měřidlo přežití původních jazyků**: podíl původního jazyka regionu v roce 1900, počet ostrůvků
   (původní jazyk drží 2 až 50 %) a přeživších původních jazyků; cíl `m8::ostruvky` (aspoň jeden
   ostrůvek, `p_min` 0,2).

### Výsledek (12 semínek)

| veličina | M8b | M8c |
|---|---|---|
| podíly jazyků mezi semínky | totožné | liší se |
| ostrůvky původních jazyků | 0 | 3 z 12 běhů (keltština v Británii 2–4 %, iberština v Hispánii 8 %) |
| přechod Galie na latinu (vesnice) | 350–475 | 375–575 |
| počet jazyků v roce 1900 | 21,5 | 44,5 |
| románské větve bez pádu ≥ 3 | 12/12 | 8/12 (cíl splněn) |
| balkánský svaz | 3/12 | 7/12 |
| měření Evropy | 31 s | asi 7 min |

**Evropa 11 z 11, brány 47 z 47, testy prošly, kalibrace 31 z 33.** Neprošly dva cíle Romanie, které
byly na hraně už předtím: retence vůči latině 0,557 → **0,536** (pásmo od 0,55) a obnova futura
5 → **4 z 20** (potřeba 5). S `loyalty_spread` 0 se obě vrátí přesně. Příčina: vesnice provincií
s vyšší loajalitou přecházejí na latinu později, latina má déle dvojjazyčné mluvčí a přejme víc
ze substrátu. Skutečná retence je 0,68–0,73 (IE-CoR), model byl nízko už bez rozptylu; řeší se
samostatně (uživatel: „retence zvlášť“).

**Mez mechanismu:** v modelu Abramse a Strogatze slabší jazyk zanikne vždy, loajalita přechod jen
zpomalí. Ostrůvky jsou proto malé (pod 10 %). Přežití po tisíciletí (velština, bretonština,
baskičtina) potřebuje stabilizaci: odlehlost (málo kontaktů s jazykem většiny) nebo identitu, která
sílí s menšinovostí (Mira a Paredes 2005, dvojjazyční mluvčí a koexistence). Další krok.

## M8e: skutečné slovníky prajazyků z IE-CoR (6. 11. 2026)

Uživatel: „Reálné slovníky“. Dosud měla skutečný slovník jen latina (dok. 22). IE-CoR (Heggarty,
Anderson a Scarborough 2024, verze 1.1, CC BY 4.0) obsahuje i staré doložené jazyky ve fonemickém
zápisu: starořečtinu (170 významů), staroslověnštinu (168), staroirštinu (169), staroislandštinu
a staroangličtinu (170), gótštinu (123) a galštinu (71, jen pravopis).

**Zapsáno:** skript `scripts/build_v2_iecor_words.py` (data v `~/.cee/data/iecor`) vybere pro pojmy
enginu (párování přes Concepticon) první slovo významu a uloží `src/cee/data/v2_iecor_words.json`;
scénář Evropy z něj bere slova a inventář hlásek (seřazený podle četnosti, z něj engine dogeneruje
pojmy, které IE-CoR nemá).

| jazyk scénáře | zdroj | pojmů z IE-CoR |
|---|---|---|
| `germanic` | gótština (nejstarší doložená germánština, 4. st.) | 70 |
| `slavic` | staroslověnština (9. st., blízko pozdní praslovanštině) | 89 |
| `greek` | starořečtina (attická) | 89 |
| `gaulish` (Galie, Británie, Armorika) | galština, pravopis převedený pravidly | 58 |
| `iberian`, `dacian` | zůstávají generované (iberštině nerozumíme, dáčtina má jen pár slov) | 0 |
| `latin` | beze změny (dok. 22) | 100 |

Převod: přízvuk, délka a melodický přízvuk se zahodí (jako u latiny; čárka by se četla jako tón,
řecký cirkumflex je v IE-CoR vlnovka, ne nosovost), afrikáty dostanou spojovací oblouček tabulky
hlásek (NFD), u jmen a sloves se odstraní koncovka slovníkového tvaru (gótské `-s`, `-an`; staroslověnský
koncový jer a `-ti`; řecké `-os`, `-on`, `-ō`, `-mi`, `-omai`; galské `-os`, `-on`), protože engine
přidává koncovky sám. Seznam koncovek je náš úsudek. Gótština tak dá *hund*, *wato*, *naht͡s*,
staroslověnština *voda*, *rõka*, *sr̩dɪt͡se*, starořečtina *kardia*, *hydor*, galština *kuno*, *derko*.

**Výsledek:** Evropa 11 z 11, testy prošly (brány ani Romanii scénář Evropy neovlivňuje). Profil
podobnosti řídí gramatika a podmínky, takže se čísla skoro nemění (balkánská slovanština ztratí pád
v 8 z 12 běhů místo 4 z 12).

Potomci v roce 1900 (semínko 1, `*` = nové slovo):

| pojem | gótština → Germánie / Skandinávie | staroslověnština → pravlast / Balkán | galština → Armorika |
|---|---|---|---|
| voda | *wato* → wato / waðo | *voda* → voda / voðə | *dubr* → duβør |
| ruka | *handu* → hadu / haðu | *rõka* → rõɡa / rõɣə | *lama* → lama |
| pes | *hund* → hunød / hunød | *pɪs* → pɪs / silɛ̃n | *kuno* → kuno |
| dva | *twɛ* → twæ / twæ | *dʊva* → dʊva / dʊvə | *wodui* → wowe |
| srdce | *hɛrto* → jækurka\* / maxa\* | *sr̩dɪt͡se* → jẽrɪd͡zəɡa\* / jəɣʷurkə\* | *kridio* → jɨɣuɣa\* |

Hláskové změny působí věrohodně (oslabení souhlásek mezi samohláskami v Balkánu a Skandinávii). **Slabé
místo, které skutečný slovník ukázal:** nová slova vznikají napříč rodinami podobně. Všechny rodiny
tvoří „srdce“ odvozeninou se stejnou příponou (engine má jednu odvozovací příponu `-ka` pro všechny
jazyky, `scenarios::DERIVATIONAL_SUFFIX`) a některé posuny a složeniny jsou nepravděpodobné (lat.
„noc“ ze „slunce“, „pes“ ze složeniny „noc + slunce“). Řešení je samostatný úkol: přípony podle jazyka
a věrohodnost zdrojů posunů a složenin.

**Další možnost:** se skutečným výchozím slovníkem jde měřit retenci i mimo latinu, například
staroslověnština → slovanské jazyky nebo starořečtina → novořečtina proti IE-CoR.

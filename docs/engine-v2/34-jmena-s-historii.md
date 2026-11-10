# 34. Jména jako slova s vlastní historií

Stav: **zapsáno na větvi `jmena-historie`** (9.–10. 11. 2026), nesloučeno.

Podnět uživatele: „Jak přesně fungují ta jména? Možná by měla fungovat jako slova? Endonyma
a exonyma. Někdy mohou převzít název exonyma jako endonymum? Odkazovat na minulý národ, co tam
žil, osobnost atd.“ Později: „Ideálně bych si představoval mít pak v appce generátor jmen měst,
z různých regionů a z různých časových epoch (město, co vzniklo před 100 lety, bude mít jiné
paradigma než to staré 1000 let).“ A dál: „A co systém vlastních/místních jmen? Neměl by se
taky ještě flashoutnout?“ Návrh je v [`docs/scenare/generovani-jmen.md`](../scenare/generovani-jmen.md).

## Co bylo špatně

`naming::endonym` skládalo vlastní jméno jazyka při každém exportu znovu z *dnešních* převládajících
slov receptu (`person` + `language`). Když se slovo nahradilo, změnilo se i jméno. `onomastics`
stavělo toponyma, exonyma a jména států stejně, z dnešních tvarů. Žádné jméno nemělo vlastní
historii: nevědělo, kdy vzniklo, jak znělo dřív a od koho ho kdo převzal.

## Model

Modul `names` (`rust/cee_engine/src/names/`) vede jména jako samostatné záznamy (`NameRecord`):

| Pole | Obsah |
|---|---|
| objekt | `world`, `language:<id>` (prajazyk), `lineage:<id>`, `territory:<id>`, `state:<id>`, `person:<klíč>`, `house:<klíč>` |
| role | **endonymum** (jméno, které objekt užívá pro sebe), nebo **exonymum** (jméno v řeči sousedů) |
| uživatelé | jazyk kódu, linie a *nositel*, tj. skupina, jejíž výslovnost jméno sleduje |
| vznik | tik a rok, motivace, příčina, tradice (u míst), význam česky, recept (pojmy a jejich tehdejší tvary) |
| zdroj | u přejatého jména záznam dárce a jeho tvar v okamžiku přejetí |
| časová osa | všechny podoby: rok, IPA, příčina (`founded`, `borrowed`, `inherited`, `sound: <změna>`) |
| konec | rok, kdy jméno přestalo být v užívání (objekt zanikl, dostal jiné jméno) |

1. **Vznik.** Jméno se složí jednou, z tehdejších povrchových tvarů slov komunity (stejné tvary
   jako `phonology::surface`), a uloží se jako hotový tvar. Recept zůstává jako výklad.
2. **Hláskový vývoj.** Proces, který v kódu skupiny převládne (podíl změny ≥ 0,5, stejný práh jako
   u povrchového tvaru), se zapíše do deníku skupiny (`SoundLog`) s tikem. Jména, která skupina
   nese, jím projdou v pořadí deníku, každým procesem nejvýš jednou (`cee_core::process::apply`
   přes `surface::apply_local`). Jméno je tak slovo s nízkou frekvencí: nemá náskok frekvence
   ani vlastní sklon. Je to první aproximace podle návrhu. Fronty fonologizace jména neznají.
3. **Ustrnutí.** Jméno nečte dnešní slovník. Výměna obecného slova jméno nezmění a původní
   rozklad zůstane v receptu (test `zmena_obecneho_slova_jmeno_nezmeni`).
4. **Přejetí.** Nová podoba jména v jiné řeči začíná tvarem dárce v tom roce, adaptovaným na
   hlásky příjemce (`contact::adapt`), a dál se vyvíjí v řeči příjemce.

Modul svět jen čte. Nic nezapisuje do `World` ani do historie, takže otisk běhu, slovník
i vzdálenosti jsou s jmény i bez nich stejné (test `jmena_nemeni_otisk_slovnik_ani_vzdalenosti`).
Zapíná ho `SimulationConfig::names`. Výchozí je vypnuto, takže brány a kalibrace běží beze změny.
`cee run`, `cee scenario`, `cee export-tick0`, `cee names` a vazba `cee_py` ho zapínají.
Volby padají z `rng::stable_int` nad semínkem světa a ID objektu, takže stejné semínko dává
stejná jména, na libovolném počtu vláken i po pokračování z kontrolního bodu (verze kontrolního
bodu 2 ukládá stav jmen).

## Jak jména vznikají

### Jazyky a lidé

- **Prajazyk** dostane na začátku běhu složeninu slov receptu (`LanguageSpec.endonym`), nebo
  autorem uzamčený tvar (`LanguageSpec.endonym_form`, motivace `authored`). Uzamčený tvar se
  nevylosuje znovu, hláskový vývoj pokračuje („Uzamknout návrh“ v návrhu).
- **První linie** z pozorování převezme jméno prajazyka.
- **Odštěpená linie** si vybere podle podmínek. Váhy jsou v `NameState::name_lineage`.
  - `inherited` (4): zdědí jméno rodiče, které se pak ve větvích vyvíjí samostatně.
  - `place` (1,5): jméno podle kraje, kde vznikla (z toponyma kraje).
  - `state` (1,5): jméno podle státu, ve kterém leží většina jejích skupin, když stát trvá aspoň 100 let.
  - `substrate` (1): jméno podle dřívějšího národa, když je původní jazyk kraje (`native_language`) jiný.
  - `eponym` (0,7): jméno podle zakladatele (dvoučlenné osobní jméno z tehdejších slov).
- **Po přechodu jazyka** (`exonym_adopted`, příčina `language_shift`): když většina skupin nové
  linie od minulého pozorování změnila jazyk, převezmou jméno, kterým jim říkal nový jazyk.
  Příklad je *Irish* místo *Gaeil*.
- **Z prestiže státu** (`exonym_adopted`, příčina `state_prestige`): linie, jejíž většina skupin
  (≥ 0,6) leží aspoň 200 let ve státě s jiným úředním jazykem, převezme s pravděpodobností 0,3
  jméno, kterým ji jmenuje vládnoucí jazyk. Rozhoduje se jednou za dvojici linie–stát. Příklad
  jsou Řekové, kteří si říkali *Rhōmaioi*.

### Místa

Jméno místa vznikne se sídlem: na začátku běhu, nebo když sídlo přibude (zjemnění, osídlení).
Vzor vybere **tradice podle podmínek v roce vzniku**, ne podle letopočtu (`compose::Tradition`).

| Tradice | Kdy | Převažující vzory |
|---|---|---|
| `archaic` | bez státu a písma | podle krajiny (`descriptive_terrain`), vody a brodu (`hydro_crossing`) |
| `state` | kraj ve státě | sídelní formant, zakladatel (`eponymous_founder`), posvátné a vladařské (`sacred_civic`) |
| `literate` | stát se spisovnou normou, nebo gramotnost či škola > 0,2 | posvátná a úřední, upomínka na stát (`commemorative`) |
| (každá) | osada založená migrací | přenesené jméno mateřského sídla, případně „Nový …“ (`transfer`) |

Když hlavní skupina místa začne mluvit jiným jazykem než uživatelé jména, noví obyvatelé
jméno s pravděpodobností 0,75 převezmou ve své podobě (`substrate`, „převzetí staršího místního
jména“). Jinak místo pojmenují znovu podle své tradice. Staré jméno končí rokem převzetí.

### Státy

Nový stát se pojmenuje podle předchůdce (`predecessor`, když v posledních 100 letech zanikl
stát, který držel jeho hlavní kraj), podle hlavního města a slova pro vládce, zákon nebo trh
podle centralizace (`capital`), podle lidí („země X“, `people`) nebo podle zakladatelova rodu
(`eponym`). Zánik státu ukončí jeho endonymum. Exonyma žijí dál, jako žije *Řím* v jiných jazycích.

### Osoby, rody a tradice osobních jmen

**Tradice osobních jmen** je vlastnost komunity (prajazyka a linie) s datovanou historií
(`NameState::traditions`, `TraditionStep`: rok, paradigma, příčina, zdroj). Paradigmata jsou
v katalogu `v2_onomastics.json` (`anthroponym_paradigms`): osm obecných (dvoučlenné, *tria nomina*,
genealogické s nisbou, klanově-generační, kalendářní z liturgie, cechovní, jméno činu, dvorská
diglosie) a čtyři talverské z tabulky „Výchozí tradice Talvery“ v návrhu:

| Paradigma | Komunita | Části jména |
|---|---|---|
| `house_surety` | hrázové obce dolního Erenu | jméno při narození + dům, který za člověka ručí |
| `journey_name` | pastevecké obce v sedlech | rodinné jméno + jméno po první samostatné cestě |
| `crew_byname` | lodnické obce západních zátok | domácí jméno + palubní přezdívka |
| `birth_rite` | pramenné obce Deštných hor | jméno podle události při narození + obřadní jméno |

- **Vznik:** tradici prajazyka zadá autor (`LanguageSpec.person_names`, `authored`), jinak se
  vylosuje z pěti tradic bez institucí (`initial`). První linie převezme tradici prajazyka,
  odštěpená ji zdědí (`inherited`).
- **Instituce:** když má většina skupin linie liturgický jazyk, linie přejde na kalendářní jména
  (`liturgy`). Když linii aspoň 50 let vládne stát se spisovnou normou v cizím jazyce
  a norma i škola zasáhly většinu jejích skupin, přejde s pravděpodobností 0,35 na dvorská jména
  (`state_standard`, vysoké jméno ve slovech úředního jazyka, přejatých do domácích hlásek).
- **Prestiž:** po 150 letech pod cizím úředním jazykem, a jen když se tradice linie 150 let neměnila,
  převezme s pravděpodobností 0,3 tradici vládnoucí linie (`state_prestige`). Obě rozhodnutí
  padají jednou za dvojici linie–stát.
- **Migrace:** osadníci si tradici nesou. Zakladatel osady založené migrací dostane jméno podle
  tradice komunity, ze které přišli (`settlement_founder_migration`), ne podle nových sousedů.

**Osoby a rody** jsou záznamy jako ostatní jména. `person:<klíč>` nese rodné jméno (tvar) a celé
jméno latinkou (`full_name`). `house:<klíč>` nese jméno rodu, má-li ho tradice. Osoby vznikají jako
zakladatelé: sídla pojmenovaného po zakladateli (místo odkazuje v receptu na záznam osoby), každého
státu (jeho rod je dynastie) a linie pojmenované po zakladateli. Stát se pojmenuje po zakladateli
jako *Osman → osmanský*: rodné jméno a slovo „dům“, recept odkazuje na osobu. Jména osob
se dál vyvíjejí v řeči komunity, která si je pamatuje (zakladatel v pověsti). Vzorník osobních
jmen v `onomastics` (`standards_personal_names`, `paradigm_catalog`) teď skládá stejná
paradigmata (`names::persons::person_name`) z dnešních slov.

### Svět

Jméno světa (objekt `world`) vznikne jako **exonymum nejstarší říše**, jako *Asie* nebo *Řecko*
z cizího jména. Rozhoduje první pozorování, kdy má nejstarší stát (podle roku vzniku) jméno
v cizí řeči. Ze všech jazyků, které ho tak jmenují, vyhraje ten s nejvíc skupinami. Jeho tvar
přejde na celou zemi (motivace `oldest_empire_exonym`). Ostatní jazyky ho převezmou stykem jako
jiná jména. Když linie, která jméno nese, zanikne, jméno dál nese nejrozšířenější linie, která ho
převzala. Autor může tvar uzamknout (`WorldSpec.name_form`, IPA). `name` zůstává popiskem.
Export má `world_name`. Tento způsob zvolil uživatel 10. 11. 2026 z dvou návrhů. Druhým bylo jméno
jednoho kraje rozšířené na celek.

### Exonyma

Při pozorování si linie, které spojuje vazba o síle aspoň 0,05, pojmenují jazyky, města
a státy svých sousedů. Exonymum vzniká jen v **cizí řeči**: sesterské linie téhož jazyka jméno
zdědily. Exonymum je samostatný záznam, který sleduje řeč pojmenovávající linie (*Wien* →
*Vídeň*).

## Generátor jmen sídel a osob podle kraje a epochy

Pro aplikaci: `NameState::generate(world, Query { region, year, count, until, urban, attempt, kind })`,
v příkazové řádce `cee names <scénář|spec.json> --until <rok> --region R --year Y[,Y2…] [--people]`,
ve vazbě `Run.names(query_json)`. `kind` je `place` (sídla, výchozí), nebo `person` (osoby
narozené v kraji v roce *Y*: tradice komunity v tom roce, tehdejší slova, u dvorských
a kalendářních jmen slova úředního jazyka státu převzatá do domácích hlásek).

1. Při každém pozorování se uloží dobový snímek (`Epoch`). U každé linie, která v některém kraji
   převládá, jde o povrchové tvary pojmů zásob katalogu, hláskový inventář, slovosled a přízvuk.
   U každého kraje jde o převládající linii, stát, písmo, město a terén.
2. Jméno založené v roce *Y* se složí ze slov posledního snímku před *Y* podle tradice, kterou určí
   tehdejší podmínky kraje.
3. Pak se vede do roku `until`. Projde hláskovými změnami z deníku nositele. Když kraj přejde na
   jiný jazyk, noví obyvatelé jméno převezmou ve své podobě.

Sídlo založené před tisíci lety je proto kratší a méně průhledné a obvykle má i jiný vzor.
Příklad v Talveře, kraj Varadu (`m01-04`), města, výsledky v roce 1950:

| Založeno | Tradice | Návrhy (tvar při založení → 1950) | Hláskových změn |
|---:|---|---|---:|
| −600 | `archaic` | Avika → Ävegä („dlouhý kámen“), Kagosi → Käbvuže („daleký vládce“) | 12–15 |
| 0 | `state` | Džegvo → Džjubve („mír vládce“), Lämenje → Lämunje („velký dvůr“) | 8–11 |
| 900 | `state` | Vekvonan → Väkvvonan („slunce kámen“), Mjusangji → Mjesangje („boj brod“) | 3–4 |
| 1850 | `state` | Pvubvu („slunce vládce“), Mantono („zelený kámen“) | 0–1 |

## Výsledek v Talveře

Talvera, seed 1, −700 až 1950, `cee names docs/scenare/talvera.world.json --until 1950`.
Otisk historie je stejný jako bez modulu jmen.

- **788 záznamů**: 486 endonym a 302 exonym. Podle objektů jde o 399 míst, 254 záznamů linií jazyků
  (včetně exonym), 48 států, 63 osob, 20 rodů a 4 prajazyky.
- **Prajazyky** (uzamčené tvary ze zadání) se vyvíjejí. Seren *lanokum* → *lenwoɡəm* (Lenvogem),
  talmur *ŋasimon* → *ŋəzə* (Ngeze), veret *omo* → *wu* (Vu), idar *anəjin* → *anajɨn* (Anajyn).
  Místa založená v roce −700 prošla mediánem 10 hláskových změn (nejvíc 24).
- **74 jmen linií:**
  - 38 zděděných;
  - 18 podle kraje;
  - 8 podle zakladatele;
  - 5 podle dřívějšího národa;
  - 3 podle státu;
  - 1 exonymum přijaté z prestiže státu: veretská linie si od 1800 říká *Vü*, tvarem, kterým ji
    jmenoval úřední jazyk Naretu.
- **Místa** (316 endonym): 301 vzniklo v archaické tradici na začátku, pozdější osady podle
  podmínek. Osadníci z jihu po roce 1425 dali osadě jméno „Nový Udž“ (*Üdžven*). Pod Istrenem
  vznikla upomínková jména podle státu *Hjeśye*. Po přechodu obyvatel na talmurštinu v roce 1925
  noví obyvatelé převzali staré serenské jméno sedmi míst (`substrate`).
- **Státy:**
  - Varadská říše se jmenuje po zakladateli *Ela Ame* (*emeni* → *Emjenö*).
  - Dolní Eren převzal jméno zaniklé říše (`predecessor`).
  - Brodská města, Varadská obec, Tarem, Selva a Istren mají jméno podle hlavního města.
  - Sousedé Varad jmenují po svém: talmursky *Jamen*, veretsky *Eju*, idarsky *Ymny*.
- **Svět** se jmenuje *Imini*. Je to idarské exonymum Varadské říše z roku −400; v roce 1950
  idarsky *Ymny*, serensky *Imi*, veretsky *Umi*.
- **Tradice osobních jmen** podle zadání: hrázové obce mají dům ručitele (*Janbaja Ame*), pastevci
  jméno po cestě (*Korming, Qiatngim*). Šest linií tradici změnilo. Talmurské linie pod istrenskou
  normou přešly v roce 1900 na dvorská jména. Jedna veretská linie převzala idarské jméno podle
  narození.

Generátor osob (`--people`) v Talveře, tři jména na kraj a rok:

| Kraj | Rok | Tradice | Návrhy |
|---|---:|---|---|
| Varad `m01-04` | −600 | `house_surety` | Janbaja Djame, Salaze Kime, Goera Vame |
| Varad `m01-04` | 1900 | `house_surety` | Pvuna Kume, Tapvuna Ljime, Saljige Pvume |
| Tarem `m06-03` | −600 | `journey_name` | Nak, Qivang („pták“, po první cestě „žár-hrom“); Julama, Iatang |
| Tarem `m06-03` | 1900 | `journey_name` | Kum, Qvuevü; Ňjöne, Jönvöch |
| pramenná obec `m11-08` | −600 | `birth_rite` | Usa / Tiahi („brod“ / „zákon-člověk“), Kasa / Haimam |
| pramenná obec `m11-08` | 1900 | `birth_rite` | Napej / Eehi, Enpej / Džemenje |

Stejná tradice dává v roce 1900 jiná jména než v roce −600, protože se mezitím změnila slova
i jejich výslovnost (*Janbaja* → *Pvuna* pro „slunce-…“).

## Výkon

Celý běh Talvery (2650 let, 106 kroků) s modulem jmen: jména zaberou asi 3 % času fází. Nejdražší
je dobový snímek pro generátor (povrchové tvary asi 110 pojmů u každé linie, které převládají
v některém kraji). Ten běží souběžně po liniích a součty četností pojmů skupiny počítá jednou
(`surface::surface_many`). Deník hláskových změn prochází každý krok pořadí procesů všech domácích
skupin.

## Zjednodušení a co dál

- Jména sledují jen procesy, které v kódu převládly. Fronty fonologizace, náskok frekvence ani
  relikty je nezasahují. Napojení na fronty přepisů je další krok podle návrhu.
- Exonyma vznikají jen mezi linie s různým jazykem kódu. Rozrůznění jména v sesterských liniích
  (*Deutsch* / *Dutch*) zachycuje dědění při rozštěpení.
- Elita, která se asimiluje, zatím své jméno místním nepředává (bulharský případ). Mechanismus
  by šel přidat k události `elite_assimilation`.
- Tradice jmen míst jsou tři úrovně podle podmínek, nemají vlastní historii po komunitách jako
  tradice osobních jmen. Přenos tradice mezi komunitami jen institucí a prestiží, ne obchodním
  stykem ani autorskou událostí převzetí (editor).
- Osoby vznikají jen jako zakladatelé. Vladaři, svatí ani rodokmeny se zatím nevedou, generátor
  osob dává jména pro autora.
- Řeky a jiné přírodní objekty engine nemá (jen terén kraje), proto zatím nemají jména (hydronyma).
- České glosy ve významu se neskloňují („volný ústí“).
- Exonyma států a měst vznikají při prvním styku. Zápis (písmo, úřední přejmenování) zatím
  nemá vlastní pole.

## Export

`names` v exportu `cee-v2/1` obsahuje:
- `records`: všechny záznamy s romanizací (`onomastics::romanize`) i u každé podoby na časové ose;
- `objects`: pro každý objekt současné endonymum, všechny jeho záznamy a exonyma podle linií.

`lineages[].endonym` (IPA) a nové `lineages[].name` (romanizace), `frame.endonyms`, `territories[].name`,
`territories[].toponym` a `onomastics.states` berou jméno ze záznamů, když modul běží. Bez něj
platí dřívější výpočet z dnešních slov.

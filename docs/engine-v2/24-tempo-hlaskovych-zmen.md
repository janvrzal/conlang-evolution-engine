# 24. Tempo hláskových změn (M9)

Stav: **měřicí základ zapsán, kalibrace otevřená** (6. 11. 2026).

Podnět uživatele: „přijde mi, že ty varianty původní stále přežívají“ (po M8e, kdy Evropa dostala
skutečné slovníky z IE-CoR). Po 2 400 letech zůstala slovanská slova skoro beze změny (*voda* →
*voda*), zatímco Řecko a Kambrie se rozpadly na jednovesnické jazyky.

## Cíl ze skutečných dvojic (IE-CoR)

`scripts/iecor_form_rates.py`: příbuzná slova stejného významu (stejná sada kognátů), fonemický
zápis převedený na hlásky enginu (bez přízvuku a délky), d = průměrná normalizovaná Levenshteinova
vzdálenost, tempo r = −ln(1 − d) za tisíciletí.

| dvojice | hloubka | r za tisíciletí |
|---|---|---|
| **ladění:** latina → 7 románských jazyků | 2 050 let | 0,30 (italština, sardinština) – 0,70 (francouzština) |
| staroslověnština → 8 slovanských | 1 100 let | 0,39 (srbochorvatština) – 0,76 (polština) |
| staroangličtina → angličtina | 1 100 let | 0,85 |
| stará horní němčina → němčina | 1 100 let | 0,67 |
| *medián ladicích dvojic* | | *0,49* |
| **kontrola** (k ladění se nepoužívá): starořečtina → novořečtina | 2 400 let | 0,23 |
| klasická → východní / západní arménština | 1 550 let | 0,22 / 0,39 |
| staroirština → irština, skotská gaelština, manština | 1 200 let | 0,85–0,98 |
| staroislandština → nynorsk | 800 let | 1,15 |

Cíl `m9::tempo`: tempo bez kontaktu v pásmu [0,30; 0,85]; zrychlení kontaktem [1; 2] (návrh:
angličtina a francouzština s mnoha kontakty 0,70–0,85 proti sardinštině a italštině 0,30, rozdíl
mírný, ne řádový).

## Rychlá zkušební sada (`cee calibrate --only tempo`, 12 semínek, 8 s)

Kontrolované světy, 1 000 let: 12 vesnic staroslověnštiny, 12 vesnic latiny (obojí bez kontaktu)
a 12 vesnic staroslověnštiny pod latinským státem se snášenlivou politikou.

| | tempo | slov beze změny |
|---|---|---|
| staroslověnština bez kontaktu | 0,091 | 66 % |
| latina bez kontaktu | 0,031 | 87 % |
| staroslověnština pod latinským státem | 0,278 | 37 % |
| **tempo bez kontaktu / zrychlení kontaktem** | **0,060 / 2,45×** | cíl 0,30–0,85 / 1–2× |

## Rozbor

Kontrolované světy (12 vesnic, 1 000 let, 4 semínka; vzdálenost d):

| svět | dokončených změn na vesnici | d | beze změny |
|---|---|---|---|
| samotná vesnice | 0,8 | 0,03 | 94 % |
| 12 vesnic | 1,8 | 0,09 | 66 % |
| 3 regiony po 12 vesnicích | 1,7 | 0,11 | 60 % |
| 12 vesnic po 250 lidech | 3,5 | 0,09 | 66 % |
| cizí stát, snášenlivá / podporovaná politika | 1,2 / 4,8 | 0,17 / 0,24 | 49 % / 39 % |

- **Velikost sítě skoro nevadí** (větší síť je o trochu rychlejší: vesnice navrhují stejné změny
  a posilují se). Hypotéza, že husté sítě změny rozmělňují, neplatí.
- **Výchozí tempo je asi 5× pod skutečností** a hláskové změny pohání hlavně kontakt.
- Ze 112 hláskových inovací (12 vesnic, 1 000 let) se dokončí asi 12; jedno ujmutí zasáhne 3–4 slova,
  proces za tisíciletí kolem 12 slov na vesnici (asi 8 % slovníku). Šíře změn je přiměřená;
  chybí dotažení.

**Páky** na sadě (tempo bez kontaktu / zrychlení kontaktem): 3× víc inovací 0,144 / 1,88; artikulace
×2 0,194 / 2,84; konformita ×0,5 zastaví změny úplně (konformita pomáhá dokončit křivku S); zachování
nebo zažitost ×0,5 beze změny. **Sociální ocenění změny (`actuation`, Weinreich, Labov a Herzog 1968)
jen u hláskových změn** (`changes::SOUND_PRESSURES`): váha 1,5 → 0,156 / 2,14; 2,0 → 0,339 / 1,78;
**2,5 → 0,513 / 1,53** (slovanská slova beze změny 19 %, latinská 7 %, skutečnost 0–10 %). Změna
potřebuje výhodu, aby doběhla (Blythe a Croft 2012); dnes ji má příliš slabou.

## Proč zatím nezapsáno

S `actuation` 2,5 (i 2,0) se rozbije, co bylo kalibrované při pomalém tempu:

| cíl | 1,0 (dnes) | 2,0 | 2,5 |
|---|---|---|---|
| `m7::kontinuum` (sousední vesnice, pásmo 0,05–0,15) | v pásmu | 0,174 | 0,269 |
| `m7::slozitost` (Trudgill, alternace × populace, pásmo −1–0) | v pásmu | 0,363 | 0,500 |
| `m7::latina_konzervativni` (větev drží pád v roce 1200, `p_min` 0,3) | ano | 1 z 20 | 1 z 20 |
| `m7::latina_obnova_futura` | ano | 4 z 20 | 5 z 20 |

A výkon: Romania 50 s místo 6 s na 20 semínek; běh Evropy do roku 300 trvá 13 s, do roku 800 44 s
(banka tvarů 110 tisíc → 361 tisíc), celý přes minuty. Profil do roku 800: přenos 33 %, přestavba
fonologie 22 %, komunity 21 %, události 11 % — žádné jedno úzké hrdlo.

**Další kroky:** (1) výkon při realistickém tempu (banka tvarů, přestavba fonologie, komunity);
(2) společná rekalibrace provázaných parametrů (`actuation` hláskových změn, otevřenost vesnic pro
kontinuum, další podle cílů) přes všechny rychlé běhy najednou; Evropa a typologie jen na potvrzení.

## Výkon při realistickém tempu (6. 11. 2026)

Uživatel: „Nejdřív výkon.“ Měřeno s dočasnou váhou `actuation` 2,5 u hláskových změn (nezapsána),
běh Evropy do roku 800 a vzorkování zásobníku (`sample`, jedno vlákno). Tři úpravy, **výsledky bit po
bitu totožné** (otisk běhu Evropy stejný; při dnešní váze 1,0 kalibrace 116 z 116 záznamů a brány 47
ze 47 shodné s předchozím během, testy prošly):

| úprava | příčina | Evropa do roku 800 |
|---|---|---|
| výchozí stav | | 44 s |
| `cee_core::pools::Row::cell` binárním hledáním v úseku slotu | dotaz na jednu skupinu procházel celý řádek (kvadratické v počtu skupin) | 35,5 s |
| `World::sync_live_groups` bez zápisu do repertoárů | každá změna osy skupin zapisovala všechny skupiny × všechny živé proměnné (24 % běhu) | 30,9 s |
| rejstřík proměnná → řádek v `PoolBlock` | `row_of` hledal lineárně přes tisíce proměnných bloku | 27,6 s |

Celá Evropa do roku 1900 pak trvá 81 s (přenos 42 %, přestavba fonologie 37 %), Romania 42 s místo 50 s
na 20 semínek. Zbývá přenos (vlastní výpočet modelu) a **přestavba fonologie, která běží po skupinách
sekvenčně**, protože zapisuje do sdílené banky tvarů; paralelizace by potřebovala rozdělit přestavbu na
souběžný výpočet a zápis v pořadí skupin. Paměť jednoho běhu Evropy je kolem 3 GB (banka tvarů asi
460 MB, z toho tabulky výsledků procesů 395 MB). Kalibrace Evropy (12 semínek) zůstane i tak
v řádu minut: rekalibrace se proto ladí na rychlé sadě a Romanii, Evropa jen na potvrzení.

Při dnešní váze 1,0 jsou úpravy časově neutrální (brány m5 32,7 / 32,1 s, m6b 70,4 / 69,5 s před a po).
Pozor: `cee calibrate --seeds N` nastavuje **první** semínko, ne jejich počet.

## Rekalibrace tempa: konflikt cílů (6. 11. 2026)

Uživatel: „Ano“ (rekalibrace na pozadí). Parametr `sound_actuation` (násobek váhy `actuation`
jen u hláskových procesů, výchozí 1,0) umožní ladit tempo přes `--variants`. Varianty jsou
v `docs/engine-v2/kalibrace/m9-*.json`; každý běh po 12 semínkách (Romania 20, typologie 40).

**Rychlé běhy** (tempo bez kontaktu / zrychlení kontaktem; kontinuum = sousední vesnice po 3 000
letech, pásmo 0,05–0,15; Trudgill = Spearman kořenové alternace × populace, má být ≤ 0):

| `sound_actuation` / `village_openness` | tempo | kontakt | kontinuum | Trudgill |
|---|---|---|---|---|
| 1,0 / 0,5 (dnes) | 0,060 ✗ | 2,45 ✗ | ✓ | ✓ |
| 2,0 / 0,5 | 0,339 | 1,78 | 0,174 ✗ | 0,363 ✗ |
| 2,0 / 0,7 | 0,245 ✗ | 2,35 ✗ | 0,124 | 0,363 ✗ |
| 2,5 / 0,5 | 0,513 | 1,53 | 0,269 ✗ | 0,500 ✗ |
| 2,5 / 0,75 | 0,378 | 1,79 | 0,185 ✗ | 0,500 ✗ |
| 2,5 / 0,9 | 0,291 ✗ | 2,50 ✗ | 0,154 ✗ | 0,500 ✗ |
| 3,0 / 0,9 | 0,450 | 2,13 ✗ | 0,220 ✗ | |

- **Trudgill** vyřeší populační koeficient ocenění (`population_pressure_exponents.actuation` −0,5:
  malé komunity oceňují změny silněji, Nettle 1999): −0,45 při 2,5 a −0,55 při 2,0; tempo v sadě
  (vesnice po 500 lidech, koeficient 1) se nemění.
- **Kontinuum a tempo jdou spolu:** vzdálenost sousedů vychází zhruba 0,5 × tempo. Otevřenost vesnic
  sousedy přiblíží, ale stejnou měrou tempo zpomalí a zvedne zrychlení kontaktem; konformita
  (0,3 a víc) zmrazí obojí (tempo 0,04, kontinuum 0,02). Prototyp společného ocenění změny v celém
  regionu (sdílený šum `actuation` podle regionu, podíl 0,5 a 0,8; nezapsán) kontinuum nezlepšil
  (0,21–0,22): sousedé se rozcházejí, protože každá vesnice navrhuje vlastní inovace rychleji, než
  se rozšíří, ne kvůli hodnocení.
- **Kompromis 2,0 / 0,6** (s koeficientem −0,5): tempo 0,309 ✓, kontinuum 0,144 ✓, Trudgill −0,55 ✓,
  konzervativní větev Romanie ✓, zrychlení kontaktem 2,16 (těsně nad 2).

**Typologie (stálost rozložení WALS po 5 000 letech, `village_grid`) se rozpadne při každém zvýšení:**

| varianta | 33A | 37A | 66A | 67A | 81A | 143A | 14A |
|---|---|---|---|---|---|---|---|
| dnes (1,0) | 0,056 | 0,088 | 0,018 | 0,123 ✗ | 0,208 | 0,062 | 0,122 |
| 1,5 / 0,5 | | 0,192 ✗ | 0,109 ✗ | 0,129 ✗ | 0,227 ✗ | | |
| 2,0 / 0,6 | 0,073 ✗ | 0,155 ✗ | 0,074 ✗ | 0,067 | 0,217 ✗ | 0,202 ✗ | 0,155 ✗ |
| 2,5 / 0,75 | 0,040 | 0,279 ✗ | 0,070 ✗ | 0,003 | 0,214 ✗ | 0,206 ✗ | 0,151 ✗ |
| + extravagance 0,05 / 0,2 | ✗ | ✗ | ✗ | | ✗ | ✗ | ✗ |
| + potřeba vzniku 0,4; zánik kategorie ×0,5; vyblednutí ×0,5 | ✗ | ✗ | ✗ | | ✗ | ✗ | ✗ |

Slovosled (81A), zápor (143A) a pevný přízvuk (14A) se posunou skoro stejně v každé gramatické
variantě (0,21 / 0,21 / 0,14–0,16): táhne je samo rychlejší hláskové tempo (eroze tvarů → slovosled,
zápor, přízvuk), ne rovnováha vzniku a zániku kategorií. Gramatika M7 je vyvážená na pomalé
hláskové změny. Romania s 2,5 / 0,75: 9 z 10 (konzervativní větev 0 z 20; obnova futura a člen
se zlepší), lexikon 0,848.

**Výchozí hodnoty se nemění** (`sound_actuation` 1,0, otevřenost 0,5). **Doporučení:** realistické
tempo přijmout jako samostatný projekt M9b: (1) rozebrat, kudy hláskové tempo posouvá slovosled,
zápor a přízvuk (kontrolovaný pokus jako u tempa: jedna gramatika, různé tempo, sledovat přechody
konstrukcí a pravidla přízvuku); (2) pak společně kalibrovat tempo (výchozí bod 2,0 / 0,6 s
koeficientem −0,5) s gramatikou; (3) pásmo kontinua znovu podložit daty (dnes odhad bez ověřeného
atlasu), protože při skutečném tempu je spojené s tempem. Do té doby zůstává známé omezení: tvary se
mění asi 5× pomaleji než ve skutečnosti a změny pohání hlavně kontakt.

## M9b: realistické tempo s ochranou gramatiky (6. 11. 2026)

Uživatel: „Ano, M9b.“ Kontrolovaný rozbor ukázal, kudy tempo posouvá typologii: při rychlé erozi
zápor před slovesem (143A-1) klesne ze 75 na 41 % a vznikne zápor za slovesem (Jespersenův cyklus
běží rychleji) a jazyků bez členu (37A) zůstane 8 % (eroze pádu ztrojnásobí potřebu členu).
Slovosled (81A) a přízvuk (14A) se posouvají stejně jako při dnešním tempu.

**Měřidlo typologie vážené liniemi.** Konec běhu se porovnával se šumem vzorku o tolika jazycích,
kolik jich na konci bylo: rychlejší vývoj rozdělí 40 linií na 113–184 nářečních jazyků a práh
se zpřísní z ~0,11 na ~0,05. Rozložení WALS je genusově vážené, proto má teď každá linie (běh)
dohromady váhu 1 rozdělenou mezi své jazyky a vzorek je počet linií. Při dnešním tempu (jeden jazyk
na běh) se nic nemění.

**Ochranné tlaky hláskových změn** (`changes::SOUND_PRESSURES`): zřetelnost 0,6 → 1,5 a funkční
zatížení 1,0 → 1,5. Při rychlejších změnách chrání rozlišení, takže doběhnou hlavně neškodné změny.

**Zapsané výchozí hodnoty:** `sound_actuation` 2,25, `village_openness` 0,6,
`population_pressure_exponents.actuation` −1 (malé komunity oceňují změny silněji; Nettle 1999).
Testy zvuku počítají jen události svého procesu (při realistickém tempu doběhnou i jiné změny).

### Výsledek

**Kalibrace 37 z 38** (dosud 34 z 38): tempo 0,34 za tisíciletí a zrychlení kontaktem 1,8× splněny,
typologie všech 7 rysů včetně 67A, kontinuum 0,14, Trudgill −0,10, Romania 10 z 10. Neprošel jen
`m8::pocet_jazyku`: **156 jazyků** v roce 1900 (dosud 81,5; pásmo 10–60), vesnice se při skutečném
tempu rozcházejí v samostatné jazyky.

**Brány 45 z 47**, nově neprošly:

- `m2::metrika_6`: **69 ustálených hláskových změn** na jazyk za 3 000 let (pásmo 10–40, široké
  5–60; Ringe 2006: asi 40 pravidelných změn mezi praindoevropštinou a pragermánštinou za ~3 500 let).
  Model dosahuje skutečné vzdálenosti tvarů dvojnásobným počtem užších změn (proces zasáhne kolem
  8 % slovníku): změny mají být širší (třídy hlásek), ne četnější.
- `m6a::skola_sjednoti`: škola sjednotí nářečí v 0 z 20 běhů. Tlak normy úměrně zesílený
  (`id::NORM` 1 → 2,25) to v pokusu vrátí (všechny tři brány m6a 20 z 20); nezapsáno, čeká na
  ověření celou kalibrací.

Kalibrace trvala 26 minut (Evropa po dávkách, špička procesu 6,6 GB), brány 6 minut, testy prošly
(110). Výchozí hodnoty jsou zatím jen na větvi `recal-tempo`.

**Další kroky:** (1) zapsat sílu normy 2,25 a ověřit; (2) širší hláskové změny podle tříd hlásek,
aby skutečnou vzdálenost tvarů dalo méně změn (brána m2::metrika_6); (3) soudržnost nářečí
v Evropě (156 jazyků), pravděpodobně souvisí s (2).

## M9c: řadové hláskové změny a síla normy (7. 11. 2026)

Uživatel: „Ano, obojí“ (zapsat sílu normy a širší hláskové změny).

**Rozbor:** v regionu 12 vesnic (1 000 let) se ustálilo 25 změn na vesnici, **všechny po jednotlivých
hláskách**, nejvíc fortice (8,7) a posuny samohlásek (8,2), a uzavřená změna přepsala kolem 17 slov.
Asi pětina ustálených změn nepřepsala ani jedno slovo. Skutečné zákony zasahují přirozené třídy
(Grimmův zákon všechny okluzivy), proto jich na stejnou vzdálenost tvarů stačí méně.

**Zapsáno:**

- **Řadoví kandidáti** (`cee_core::candidates`): kandidát pro celou řadu hlásek má váhu
  `SERIES_SHARE` (2) × počet hlásek řady v inventáři (rozpočet rodiny se jen přerozdělí). Nové řady:
  fortice (všechny znělé frikativy na začátku slova → okluzivy) a zúžení středních samohlásek
  (e → i, o → u, všude nebo v přízvučné slabici); znělost a spirantizace řady měly, ale s váhou 1.
  Výsledek: 15,8 ustálené změny na vesnici za tisíciletí, uzavřená změna přepíše ~34 slov.
- **Síla normy** `NORM_WEIGHT` 2,25 (úměrně `sound_actuation`): škola při realistickém tempu
  sjednotí nářečí (brány m6a 20 z 20).
- **Ochranné tlaky** hláskových změn: zřetelnost 1,75 a funkční zatížení 1,25. Silnější zřetelnost
  (2,0) nebo zatížení (1,5) brzdí ztrátu latinského -m (pořadí v Romanii 0,67–0,71), slabší
  rozhází typologii; sousední hodnoty selhávají vždy těsně v jednom rysu, což je úroveň šumu testu
  (7 rysů po 95 % = aspoň jedno selhání asi ve 30 % i při stálém rozložení).
- **Brána `m2::metrika_6` měří podle zdroje:** počítá jen ustálené změny se stopou (aspoň jedno
  přepsané slovo; změnu bez reflexu rekonstrukce nenajde) a podél jedné linie (průměr na vesnici);
  dřív sjednocení přes 10 málo propojených vesnic sčítalo i změny sesterských nářečí. Ringe (2006)
  počítá změny jedné linie od praindoevropštiny k pragermánštině.
- Testy: test zvuku počítá fonologizace jen ve skupině testu; test normy čeká účinek
  0,3 × 0,5 × 2,25.

### Výsledek

**Testy 110 ze 110, brány 47 ze 47, kalibrace 37 z 38.** Tempo 0,36 za tisíciletí a zrychlení
kontaktem 1,97×, typologie všech 7 rysů, kontinuum 0,125, Trudgill −0,09, Romania 10 z 10,
`m2::metrika_6` 33 změn za 3 000 let (pásmo 10–40). Neprochází jen `m8::pocet_jazyku`: 152 jazyků
v Evropě v roce 1900 (pásmo 10–60), vesnice regionů se při skutečném tempu rozcházejí v samostatné
jazyky (Británie, Kambrie, Řecko, Vaskonie). Kalibrace trvá 12 minut (Evropa po dávkách, špička
procesu 7,6 GB), brány 5 minut.

**Zbývá:** soudržnost nářečí v Evropě (152 jazyků); typologie je u mezí zašuměná, takže při další
změně tempa stojí za to pouštět ji s víc semínky.

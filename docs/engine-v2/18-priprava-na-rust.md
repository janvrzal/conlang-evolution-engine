# Příprava na Rust (fáze A) a přepis (fáze B)

Sepsáno 2026-11-01. Rozhodnutí s uživatelem: engine v2 nejdřív v Pythonu
připravit do podoby, jakou bude mít v Rustu (fáze A), a pak ho modul po
modulu přepsat (fáze B). Načasování fáze B má sedět s ustálením modelu (M7).

## Proč ne rovnou jádra v Rustu

Měření (údolí 10 × 5, syntax a význam, 1 000 let, 25 s): čas nejde do
několika výpočtů, ale do milionů drobných volání nad slovníky s textovými
klíči (`World.usage_frequency` 1 mil., `unit_of`/`form_of` 1,7 mil.,
`lexical_index.score` 2,9 mil., synchronizace indexů). Samotná aplikace
zvukových změn a fonologizace je asi 1 s. Rust jádro volané po jednom slově
by režií hranice Python–Rust zisk spotřebovalo; Rust pomůže, až budou data
v polích a jádra budou zpracovávat celou skupinu nebo celý krok najednou.

## Fáze A: kroky

Každý krok je malý commit, po každém `scripts/v2_digests.py` beze změny
(bitová shoda), checkpointy dál fungují, veřejné API (`Simulation`,
`World.form_of/unit_of/distribution`, `export`, `scenarios`) zůstává.

| Krok | Obsah | Stav |
|---|---|---|
| A1 | horké cesty: hromadné četnosti užití, ploché pole hlásek a bitové předfiltry v bance tvarů, hromadná lexikální jasnost, fronta fonologizace naráz (`zadani-datovy-model.md`, test shody `test_v2_datamodel.py`) | hotovo 2026-11-01: otisky beze změny, valley-50 42,7 s → 34 s (−19 %), grid-5x5 v šumu; profil je teď plochý (podpora zvukových změn ~17 %, artikulace ~14 %, fronta fonologizace ~12 %, lexikální jasnost ~8 %) |
| A2 | registry číselných ID pro morfémy, varianty, proměnné, skupiny, procesy, pojmy. Pořadí zpracování se nemění: kde dnes kód řadí podle řetězců, registr drží pořadí řetězců (pořadové číslo = pozice v seřazení) | hotovo 2026-11-02 (`zadani-registry.md`): `cee.v2.registry`, číslo = pořadí vzniku, registr patří světu a kopíruje se s ním; slovníky entit světa zapisují do registru samy (`RegisteredDict`); `Numbering.ranks()` pro řazení čísel v pořadí řetězců |
| A3 | stav kódu v polích: tvary (`FormStore` → čísla tvarů do `FormBank`), slovní zásoba a převládající kořeny (`PhonologyState`), fronty fonologizace | hotovo 2026-11-02: `FormStore` = tři pole `int32` podle čísla morfému (tvar v bance, hranice koncovky, koncovka; −1 = výchozí/žádná), `PhonologyState` v `language/columns.py` (slovní zásoba a fronty jako pole příznaků, počty užití a kořeny pojmů `int32`, fronta = `float64` potřebných logitů + `int32` morfémů), sklony slov jako sloupec světa; `World.form_id_of` místo hašování tvarů. Otisky beze změny i s jiným `PYTHONHASHSEED`, celá sada 1026 prošlo; čas a paměť v šumu (valley-50 32,7 → 33,5 s, špička ~1,44 GB). Na řetězcích zůstává: shoda v řazení fronty (logit, jméno morfému; pro Rust přes `ranks()`), deníky a klíče procesů, tvary v `UnitForm`, `ContextIndex`. `DominantMap` drží pořadí vložení pojmů: Rust ho musí udržet, nebo na něm nesmí záviset |
| A4 | tabulky světa jako sloupce: morfémy (tvar, frekvence, druh, jazyk, třída slova), varianty (proměnná, payload podle typu), proměnné, vazby (matice/CSR místo slovníku dvojic) | hotovo 2026-11-02 (`zadani-sloupce.md`): `cee.v2.tables` (`MorphemeTable`, `VariantTable`, `VariableTable` plněné při uložení entity do slovníku světa; `LinkDict` + `LinkTable` = CSR po číslech skupin, přepočet jen po změně vazeb); slovníky objektů zůstávají zdrojem pravdy. Na sloupce převedeno: `mixing_matrix`, `word_bias`, tlaky nad variantami (aktuace, motivace, přítomnost morfému, přitažlivost), milníky; hlavní hot cesty zbývají na objektech (viz závěrečná zpráva). Otisky beze změny, čas a paměť v šumu, celá sada 1032 prošla |
| A5 | fáze kroku jako funkce nad poli (inovace, tlaky, přenos, fonologizace, morfologie, syntax, prozódie, kontakt); třídy zůstanou tenkou fasádou. Součástí jsou **řídké fondy podle variant** (rozhodnuto s uživatelem 2026-11-02): živé fondy (`pools.py`) dnes drží každou proměnnou jako husté pole skupiny × sloty, takže varianta ve 3 vesnicích z 50 má řádek přes všech 50, a sloty jsou řetězcová ID variant, která tlaky a přenos při každé dávce překládají na čísla (zjištění z A4). Nově: sloty jako čísla variant z registru a výskyt varianty jako řídký seznam (skupina, podíl) uložený po variantách, tedy mapa rozšíření slova přímo v datech (pro atlas v UI). Přenos potřebuje „co je u mě a u sousedů“, proto zvážit dvojí index (po variantách i po skupinách) nebo husté bloky jen pro proměnné rozšířené skoro všude. Paměť a čas pak rostou s počtem skutečných výskytů, ne se součinem vesnic a variant; rozhoduje to u velkých map. Bitová shoda jen při zachovaném pořadí sčítání (jinak vědomá změna otisků s ověřením branami)  | část hotova 2026-11-03 (`zadani-faze.md`, modul `cee.v2.phases`): inovace (klíče, tempo, míry a váhy míst, výběr místa), milníky a ustálení, přechody přes práh, aktivace, analogie, nové koncovky a pravidlo přízvuku jsou čisté funkce nad poli, třídy je jen volají. Otisky beze změny. **Přenos a řídké fondy hotovo 2026-11-03** (`zadani-prenos.md`): (1) přenos je ve funkcích nad poli v `cee.v2.phases_transmission` (matice vazeb z tabulky vazeb, komponenty sítě, podíly kanálů elita/obchod, bloky komponent pro `CrossFlow`, faktory kontaktu a institucí po proměnných bloku jako pole, `mix`, `hear` = co skupiny slyší od sousedů, jiných jazyků a z kanálů, `settle` = výběr, trend, drift, ustálení, `normalized`); `transmission.prepare`, `transmit`, `StepInputs` a `CrossFlow` jsou tenká fasáda. Na objektech zůstává sbírání vlastností skupin a proměnných, mocnina přenositelnosti a prestiže (`**` v Pythonu, `numpy.power` se může lišit v posledním bitu), klíče driftu (`stable_int`) a tlaky (`Pressure.scores`) mezi `hear` a `settle`. (2) sloty živých fondů jsou čísla variant z registru (`PoolBlock.slot_variants`, −1 = prázdný slot), řetězcová ID jsou odvozený pohled `PoolBlock.slots` pro tlaky, testy a deníky; milníky a aktivace už nepřekládají řetězce. (3) fondy se drží **řídce po variantách**: pro řádek (proměnnou) a slot (variantu) seřazený seznam (skupina, podíl, základna), takže mapa rozšíření slova je přímo v datech (`LivePools.range_of`); co je u skupiny, dá hledání v seznamech slotů řádku nebo hustý pohled, který se při čtení sestaví a po kroku zahodí (`LivePools.compact`). Přenos se počítá dál nad hustými bloky sestavenými z řídkého uložení: BLAS sčítá v pořadí závislém na tvaru matice a řídké sčítání by změnilo poslední bity, takže bitová shoda (`CrossFlow`, `mix`) jinak nejde; otisky tedy zůstaly beze změny, bez vědomé změny modelu. Blok nad 2^20 buněk se počítá po kusech řádků (řádky jsou nezávislé), `Simulation._transmit` hned po bloku vezme z hustého výsledku události a nový stav uloží řídce (`stage_state`, zápis `commit_state` po všech blocích ve stejném pořadí jako dřív). Měření (Rust, vytížený stroj, rozdíly pod ~5 % jsou v šumu): paměť fondů v klidu valley-50 3,7 → 2,3 MB, 12×12 vesnic 17,5 → 5,5 MB, 20×20 vesnic 121 → 15 MB (obsazeno 5 až 36 % přidělených buněk); čas valley-50 asi +4 %, grid-5x5 +5 %, 12×12 +4 %, 20×20 +2 %; špička paměti procesu se nezměnila (valley-50 1,5 GB, 20×20 2,1 až 2,5 GB, běh od běhu kolísá o 10 až 20 %), protože ji tvoří indexy nad řetězci (`lexical_index` kolem 285 MB při 20×20), ne fondy. Přechodná paměť přenosu (`tracemalloc`, 20×20, 150 let) 723 → 533 MB. **Čas přenosu nejsou čísla ani fondy**: z 41 % času valley-50 jsou tlaky (`fitness_of`) 36 % (Articulation 12 %, LexicalClarity 11 %, Conservation 8 %), míšení 0,3 %, výběr a drift 3,7 %, převody slotů a milníky asi 2 %, příprava kroku 0,1 %, filtry kontaktu a institucí v kontaktních světech pod 1 %. Tlaky počítají jen dosažené buňky (podíl nebo slyšený podíl > 0), a těch je 5 slotů na buňku, protože proměnné jsou promíchané variabilitou po celé síti; buněk bez změny (jediná varianta u skupiny i jejích zdrojů) je jen 3 až 14 % a z práce tlaků 3 až 5 %, takže přeskakování nehybných buněk nic nepřinese. Zisk dá až přepis hodnocení za tlaky (`ContextIndex`, `LexicalClarityIndex`, hodnocení procesů a tvarů), ne přenosu. |
| A6 | přenositelná náhoda: model dnes vedle hashovaného šumu (`rng.stable_int`, `hash_normal`, `hash_poisson`; blake2b a splitmix64, v Rustu snadno stejné) používá i `numpy.random.Generator` (PCG64 a algoritmy `poisson`, `choice`, `uniform`, `normal` numpy). Ty v Rustu bitově zopakovat nejde rozumně; nahradit je hashovanými losy (asi 27 míst: tvorba protojazyka 11, pozadí dějin 6, lexikální změny 3, variabilita 2, syntax 2, výběr místa inovace a prozódie po 1). **Vědomá změna otisků**, ověřená branami | hotovo 2026-11-02 (`zadani-nahoda.md`): `rng.Stream` (klíč z `stable_int`, jádro SplitMix64, `random` 53 bitů, `integers` Lemire, `choice` postupné kumulativní součty + `bisect_right`, `normal` Box–Muller přes libm, `poisson` inverzí po kusech λ ≤ 30; algoritmy v docstringu, referenční tahy v `test_v2_stream.py`) nahradil numpy ve výběru místa inovace, návrzích změn, sklonech slov a velkých λ v `hash_poisson`. Tvorba světa (protojazyk, pozadí dějin, rozdání variability) zůstala na numpy, svět po `build()` je beze změny; při přechodu desktopu na čistý Rust ji bude třeba převést (jednorázová změna slov protojazyka). Nové otisky v `scripts/v2_digests.py`. Ověření: audit bran na seedech 101..120 bez významného rozdílu (nejmenší p = 0,24, Jespersenův cyklus 6/20 → 2/20), statistika inovací na 8 seedech v limitu u všech 39 typů změn, retence za 1 000 let izolovaná 0,900 → 0,899 a kontakt 0,915 → 0,913; valley-50 v šumu. Brána Fergusonovy diglosie (pevné seedy 1, 2) s novou náhodou neprošla; podíl na 20 seedech je ale 10/20 už před A6 (11/20 po) |
| A7 | zlatá data: záznam vstupů a výstupů každé funkce z A5 ze skutečných běhů pro ověření Rust implementace kus po kusu  | pro funkce z `cee.v2.phases` hotovo 2026-11-03: `scripts/v2_golden_phases.py` (grid-5x5, shift, valley-50 zkráceně a čtyři světy pro vzácné cesty), `tests/v2/data/golden_{innovation,vocabulary,grammar}.json.gz` (asi 200, 410 a 90 kB), test `test_v2_golden_phases.py`. Profil (s Rustem z B2): inovace 34 % času valley-50 a 30 % grid-5x5, z toho skoro vše ve hledání míst (`total_rate`), u valley-50 z dvou třetin ve zvukových změnách (`changes/sound.py`, 22 % celku); morfologie 2 %, syntax a prozódie pod 0,2 %, sledování slovní zásoby 5 %, čisté funkce nad poli dohromady asi 1,5 %. **Zlatá data přenosu hotova 2026-11-03**: `scripts/v2_golden_transmission.py` (grid-5x5, shift, shift s neutrálními vahami domén, valley-50 zkráceně, svět s cizí elitou a obchodem, svět s písmem, církví a školou; plus jedno pevně semínkované volání `settle` se skupinami bez proměnné, které se ve skutečných bězích nestane), `tests/v2/data/golden_transmission.json.gz` (asi 550 kB, 19 funkcí), test `test_v2_golden_transmission.py` (shoda bit po bitu, pokrytí větví, shoda polí faktorů se skalárními funkcemi, přenos po kusech dá tentýž otisk). **Zlatá data tlaků a hledání míst hotova 2026-11-03** (`zadani-zlata-data.md`). Hranice, která se nemění při předělání indexů na čísla z registru: u tlaků dávka (`PressureBatch`) a stav světa v ticku → `scores`, u hledání míst stav světa na začátku inovační fáze ticku a skupina → `sites`, `rates`, `total_rate`, `weighted_sites` každého druhu změny. (1) **Stav světa se neukládá**: snímek (pickle checkpointu) má 1 až 3 MB i stlačený (grid-5x5 0,9 až 2,7 MB, shift 0,7 až 1,5 MB, tj. 0,7 až 2,7 MB), limit je 1 MB na soubor. Svět v ticku záznamu vyrobí běh scénáře (`tests/v2/golden_worlds.py`, bitově shodný s otisky `scripts/v2_digests.py`); testy jsou `slow`, ověření trvá kolem 14 s každé (`CEE_NATIVE=0`). Pro ladění Rustu uloží skripty s `--snapshots ADRESÁŘ` pickle světa v tickách záznamů (nepatří do repozitáře). (2) **Scénáře**: grid-5x5, shift, valley-50 zkráceně (400 let), svět s cizí elitou a obchodem (`trade-elite`), svět s písmem, církví, liturgií a školou (`church-school`), a dva malé světy pro vzácné cesty: `rare-grammar` (gramatika s opisem, přiklonkou, exaptací, zkrácením záporu a tabuizovaným pojmem) a `rare-sounds` (počáteční `sC`, palatalizované souhlásky, nosová samohláska, tóny). Ticky a skupiny vzorku vybírá deterministicky `rng.Stream`, k nim se přidají záznamy, které doplní pokrytí (první nalezený stav, kde druh změny má místa a nenulovou míru). (3) **Hledání míst** (`scripts/v2_golden_sites.py`, `tests/v2/data/golden_sites.json.gz`, 205 kB, 5 015 záznamů): místa jako čísla do tabulky řetězců, `rates` (u druhů s jednotnou mírou `rate` a `rate_scale`), `total_rate`, `weighted` a `weights`; všech 57 druhů změn má neprázdný záznam s nenulovou mírou. Jen v malých světech jsou taboo_replacement, periphrasis, cliticization, affixation, exaptation, negation_reduction, prothesis, palatal_affrication, tone_merger, tone_loss a tone_dissimilation; delabialization a labial_shift jen v `church-school` (3 záznamy). Test `test_v2_golden_sites.py`. (4) **Tlaky** (`scripts/v2_golden_pressures.py`, `tests/v2/data/golden_pressures.json.gz`, 513 kB, 254 dávek všech pěti druhů proměnných): vstup dávky jako pole bez světa (`freqs`, `heard`, `numbers`, `slots`, ID proměnných a skupin; výřez několika řádků a skupin, kde se něco děje, protože tlaky jsou po řádcích i po skupinách nezávislé), výstup `scores` bit po bitu včetně tvaru (např. `appeal` má (proměnné, 1, sloty)) a `reads`: vstupy, které jsou čisté hodnoty (sloupce variant ve slotech, frekvence pojmů, hodnocení procesů a tvarů v dosažených buňkách, rysy skupin, váhy z `Parameters`). Co z toho tlaky čtou, je popsáno v dokumentaci skriptu; `Norm`, `Taboo`, `LexicalClarity` a syntaktické tlaky čtou index nebo objekt světa a mají jen stav z běhu. Všech 23 tlaků má záznam s nenulovým výstupem (`norm`, `fusion`, `taboo` jen v jednom světě, `learnability` ve dvou). Test `test_v2_golden_pressures.py` sestaví dávku ze záznamu nad světem z běhu, ověří také, že se rovná výřezu dávky z běhu, a porovná `scores` a `reads`. Sondy se napojují za běhu bez zásahu do zdroje modelu (`Simulation._innovate` na instanci, `transmission.fitness_of` a `Pressure.scores` na modulu a třídách); běh se sondou má stejný otisk jako bez ní. Soubory jsou při opakovaném běhu skriptů bajt po bajtu stejné. |
| A8 | hranice pro události a státy (`events`, `polity`, `background`, `contact`): jsou vzácné a nejsou horké, zůstanou nejdéle v Pythonu a budou svět měnit přes API | hotovo 2026-11-03 (`zadani-hranice-udalosti.md`) pro `events`, `polity` a `background`: modul `cee.v2.edits` (18 operací, deník `World.edit_log`, přehrání `events.ReplayEdits`); popis pod tabulkou fáze A. Otisky beze změny. **`contact.community_step` na API změn hotovo 2026-11-03** (`zadani-zlata-data.md`): přechod komunit, migrace, pronikání veřejného kódu domů i zánik skupin jsou operace `set_group`, `set_code`, `add_group`, `remove_group`, `connect`, `set_border_factor` a `set_prestige_mirror` (fáze `community`, viz níže); `Edit` nese fázi kroku, takže jde deník přehrát ve správném místě kroku. Otisky beze změny (7 světů a svět s komunitami `community` i před převodem), hlídač rozboru zdrojového kódu hlídá i `community_step` a jeho pomocníky v `contact.py` |

## A8: API změn světa

Události (`events`), státy (`polity`) a pozadí dějin (`background`) mění svět
**jen** přes `cee.v2.edits.Edits(world, tick)`. Test
`test_udalosti_staty_a_pozadi_nesahaji_na_svet_mimo_edits` to hlídá rozborem
zdrojového kódu (žádný zápis do atributu, žádný zápis do slovníků světa,
žádné volání mutátorů světa).

**Operace** mají jméno a pojmenované argumenty z čísel, řetězců, bool a `None`
(seznam jen pro polohu a oblasti státu). Pořadí provedení je pořadí volání, nic
se neřadí. Operace, která nic nezměnila, se nezapíše.

| Operace | Účinek | Rust převezme jako |
|---|---|---|
| `add_territory` | nové území, zařadí se k potomkům rodiče | zápis do stromu území |
| `add_group` | nová skupina s kódem (`main`) nebo všemi kódy (`all`) skupiny `code_from` (`branch()`; předtím se živé proměnné dárce zapíšou do repertoáru) | nový řádek sloupců skupin a kopie stavu kódu dárce |
| `remove_group` | skupina zmizí i s vazbami a obchodním podílem | smazání řádku a vazeb |
| `set_group` | jedno skalární pole skupiny (`GROUP_FIELDS`) | zápis do sloupce |
| `set_code` | `acquisition`, `l1_source`, `l2_share` hlavního kódu | zápis do sloupců kódu |
| `fix_code` | nestálé proměnné hlavního kódu na dominantní variantu (shodu rozhoduje první podle ID) | složená operace nad repertoárem |
| `connect`, `set_link`, `drop_link` | oboustranná vazba (ořez na 0 až 1), jednosměrná vazba, zrušení vazby | zápis do CSR vazeb |
| `set_trade` | obchodní podíl dvojice (abecedně seřazené), `None` zruší | zápis do mapy obchodu |
| `set_border_factor` | násobek oslabení vazby hranicí | zápis do mapy hranic |
| `set_base_prestige`, `set_prestige_mirror` | základní prestiž a předloha prestiže | zápis do map prestiže |
| `add_state`, `set_state`, `set_state_link`, `remove_state` | stát (`Polity`), jeho `regions`/`policy`/`border` a vazby na sídlo | zápis do tabulky států |
| `set_standard` | spisovný jazyk státu či regionu | zápis do mapy norem |

Složené změny se rozloží na operace i s vypočtenými hodnotami (gravitační
vazby: `Edits.connect_gravity` zapíše každou vazbu s vypočtenou silou;
`refresh` zapíše jen vazby, hranice a prestiže, které se opravdu změnily), takže
Rust nepotřebuje znát vzorce. Rozhodování, *kdy a jaké* operace volat, zůstává
v Pythonu.

**Deník změn** `World.edit_log` (`Edit`: tik, operace, argumenty) patří světu,
kopíruje se s ním (checkpointy, `deepcopy`, pickle) a jde uložit jako řádky JSON
(`journal_lines`, `load_journal`). `events.replay_events(deník, start_year=,
dt=)` vyrobí události `ReplayEdits`, které v týchž ticích provedou tytéž
operace: běh bez událostí, do kterého se vloží deník, dá stejný stav světa,
stejný deník a stejnou historii kromě záznamů, které zapisují samy události.
Test `test_v2_edits.py` to ověřuje na sedmi světech, které dohromady použijí
všech 18 operací a všechny druhy událostí (dobytí a elita, obchod, liturgie,
přesun jazyka, kodifikace, škola, tisk, zjemnění, migrace, státy, spisovné
jazyky, odtržení, obrození, pozadí dějin).

**Krok komunit** `contact.community_step` (migrace, přechod jazyka, pronikání
veřejného kódu domů, vznik a zánik skupin) mění svět také jen přes `Edits`,
ve fázi `community`: provádí se na konci ticku po přenosu, kdežto události,
státy a pozadí dějin (fáze `event`) na jeho začátku. `Edit` proto nese fázi
(`event` je výchozí a do řádku JSON se nezapisuje) a `Edits(world, tick, phase)`
ji zapisuje. Operace jsou `set_group` (`population`, `immigration`, `transmitted`,
`openness`), `set_code` (`l2_share`, `l1_source`, `acquisition`), `add_group`
(domácí skupina vzniklá pronikáním veřejného kódu, kód je větev kódu veřejné
skupiny), `remove_group`, `connect`, `set_border_factor` a `set_prestige_mirror`.
`World.materialize` před odebráním skupiny odpadlo: repertoár odebrané skupiny
nikdo nečte. Zápisy se nemění v pořadí ani v hodnotách (otisky beze změny).
Deník roste: ve světě, kde se podíl L2 mluvčích blíží k limitu, přibývá zápis
`set_code` za každou skupinu a tik, dokud se hodnota mění.
`edits.community_replay(deník)` je náhrada `community_step`, která místo výpočtu
provede zapsané operace fáze `community`; test přehrání v `test_v2_edits.py` s ní
přehraje celé deníky (události v ticích plus komunity na konci ticku) a dá stejný
svět, stejný deník a stejnou historii kromě záznamů, které píšou události
a `community_step` vedle změn světa (přechod, pronikání, obrození). Svět
`community` (`tests/v2/edit_worlds.py`) k tomu přidává migraci, nativizaci přes
uzavřenou hranici (nová domácí skupina s vazbami, násobky hranice a prestiží vzoru)
a přechody jazyka; jeho zápisy fáze `community` zahrnují všech sedm operací.
Cesta obrození (`transmission_resumed`, `revival`) v testovaných světech nenastane,
její zápisy jsou stejné operace.

**Mimo API zůstává** živé fondy (`world.live`: synchronizace po událostech v
`Simulation._apply_events` a po kroku komunit), `World.materialize` (součást
`add_group`) a tvorba světa (`scenarios`, `spec`, `variation`).

## Fáze B: pořadí přepisu

Podle závislostí, každý modul za stávajícím rozhraním (PyO3, maturin),
s testem shody proti zlatým datům:

1. tabulka hlásek (s vytvářením hlásek až při prvním zápisu, viz Známé mezery), banka tvarů, tabulky procesů.
   **Banka tvarů a tabulky procesů hotovo 2026-11-02** (`zadani-rust-b1.md`):
   - crate `rust/cee_core` (PyO3 0.30, maturin, modul `cee_core`, verze
     rozhraní 1): plochá aréna tvarů, bitové předfiltry, tabulky výsledků
     a aplikace procesu se všemi sedmi operacemi;
   - `cee.v2.native` rozšíření načte. Bez něj, s `CEE_NATIVE=0` nebo při
     jiné verzi rozhraní počítá Python;
   - otisky jsou bitově stejné v obou režimech, celé sady s Rustem 1 070
     prošlo a bez něj 1 065 prošlo a 5 přeskočeno;
   - zlatá data `tests/v2/data/golden_bank.json.gz` (21 093 aplikací);
   - zisk je malý: valley-50 asi −5 % (31 proti 34 s), grid-5x5 v šumu,
     protože zbývající cena je Python obal kolem 4 milionů jednotlivých
     volání `may_apply` z `phonology.restructure`. Velký zisk přijde
     s dávkovými voláními v kroku 2;
   - operace `change` a `tone` (nejbližší hláska) počítá dál Python
     a Rustu je doplňuje mapou, o kterou si sám řekne. Tabulka hlásek
     zůstala v Pythonu;
   - překlad: čistý release asi 10 s, po drobné změně asi 2,4 s;
   - sestavení: `maturin build --release`. Do sdíleného venv se
     rozšíření neinstaluje; agent ho dal do
     `rust/cee_core/target/py` a ten přidal do `PYTHONPATH`.
2. aplikace zvukových změn a fonologizace.
   **Hotovo 2026-11-03** (`zadani-rust-b2.md`):
   - `NativeBank` umí krok fonologizace kódu po dávkách
     (`restructure_step`, `queue_morpheme`, `activate`, verze rozhraní 2).
     Vstupy jsou pole `FormStore`, sloupce světa, příznaky front a sloupce
     sklonů slov předané bez kopírování. Rust nic nezapisuje, vrací
     rozhodnutí a Python je zapíše ve stejném pořadí jako dřív;
   - logity a sklony slov počítá Python, takže bitová shoda nezávisí na
     libm. Chybějící hodnoty si Rust vyžádá (`needs`) a Python je doplní;
   - otisky jsou stejné s Rustem i bez něj. Zlatá data kontrolují 18 015
     přepisů a 9 937 zařazení do fronty bit po bitu;
   - fonologie ve valley-50 trvá 3,7 s místo 7–8 s a celek je asi
     o 8 % rychlejší (valley-50 asi 30 s). Zbytek času je v tlacích,
     přenosu a hodnocení (krok 3 a 4 až po A5);
   - zbývá: sestavování seznamů front (`_targets`, asi 2 s) a četnosti
     užití (asi 1 s) v Pythonu;
3. hodnocení (artikulace, funkční zátěž, lexikální jasnost) a tlaky.
   **Část hotova 2026-11-03** (`zadani-rust-b3.md`):
   - v Rustu je maticová část hodnocení zvukového procesu
     (`NativeBank.assess_rows`, zasažená hmota, zkrácení, příznakovost,
     noví homofoni, samohlásky) a opora zvukových změn
     (`cee_core.sound_supports`). Verze rozhraní je 3;
   - součty plovoucích čísel jsou párové jako `np.sum`
     (`cee_core.pairwise_sum`). `native.sums_match()` jednou ověří, že
     numpy na stroji sčítá stejně, jinak se počítá v Pythonu. Bezstavová
     jádra se volají přes `native.kernel(...)`;
   - otisky jsou stejné s Rustem i bez něj, prošly obě celé sady (1 124
     s Rustem; 1 102 bez něj a 22 přeskočeno). Zlatá data jsou
     v `tests/v2/data/golden_assessment.json.gz`;
   - zisk je malý: valley-50 asi −10 % (v šumu −4 až −18 % na vytíženém
     stroji), grid-5x5 asi −9 %. Čísla v hodnocení jsou levná, čas jde do
     indexů nad řetězcovými slovníky (`ContextIndex`,
     `LexicalClarityIndex`, `AssessmentVocabularyIndex`,
     `FormAssessmentIndex`) a do Python obalů. Lexikální jasnost,
     synchronizace indexů a tlaky jako pole zůstaly v Pythonu. Tlaky stojí
     každý pod 0,3 % času, takže jejich přepis nic nepřinese, a testy
     (`test_v2_lexical_matrix`, `test_v2_process_scores`,
     `test_v2_form_scores`) fixují jejich objektové rozhraní;
   - plyne z toho, že další zisk nepřinesou další jádra, ale převedení
     stavu indexů na čísla z registru. Indexy pak přejdou do Rustu celé
     i s testy (tyto testy se pak vědomě přepíšou na nové rozhraní);
4. přenos (míšení, výběr, drift) a živé fondy. **Příprava hotova 2026-11-03** (řádky A5 a A7): rozhraní pro Rust jsou funkce `cee.v2.phases_transmission` se zlatými daty; živé fondy jsou řídké, přenos se počítá nad hustými bloky kvůli pořadí sčítání. Čas přenosu je ale z 36 % ve tlacích, ne v číslech přenosu, takže zisk Rustu v tomto kroku bude malý, dokud tlaky a hodnocení nepřejdou na čísla z registru;
5. hledání míst inovací a změny;
6. hlavní smyčka `Simulation`; Python zůstane pro popis světa, export,
   kalibrační skripty a API; desktopová aplikace (Tauri) může engine volat
   přímo z Rustu bez Pythonu.

Rozdělení na více crate (tabulka hlásek, změny, přenos, události) zkrátí
překlad po malé změně; konstanty a katalogy zůstanou daty
(`Parameters`, YAML/JSON), takže kalibrace nepotřebuje překlad.

## Bitová shoda při přechodu do Rustu

Transcendentní funkce (`exp`, `log`, `sqrt` je v pořádku) počítá numpy jinou
implementací než standardní knihovna Rustu a v posledním bitu se mohou
lišit. Postup: jednotlivé funkce porovnávat s tolerancí v řádu posledního
bitu, otisky při přechodu jednou vědomě vyměnit a nový stav ověřit celou
sadou bran a statistickým srovnáním na seedech. Od té chvíle jsou
referencí otisky z Rustu.

## Nevýhody, se kterými počítat

- pomalejší experimentování s modelem (překlad, typy); proto načasovat
  fázi B s ustálením M7;
- překlad: ladicí po malé změně jednotky sekund, optimalizovaný desítky
  sekund, čistý 1–3 minuty (odhad pro ~16 tisíc řádků);
- přechodné období dvou jazyků (vazby, sestavení přes maturin);
- binárky pro každou platformu (u Tauri spíš výhoda: engine bez Pythonu).

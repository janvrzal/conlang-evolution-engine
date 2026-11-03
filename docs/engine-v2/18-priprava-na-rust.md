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
   - **Dokončeno 2026-11-03 (B3b, `zadani-rust-tlaky.md`, verze rozhraní 7)**:
     vzorek slov pro hodnocení procesů a uložená hodnocení jsou na číslech
     a v Rustu (`assess_index.rs`), 23 tlaků jsou jádra v Rustu
     (`pressures.rs`) volaná uvnitř `NativeCells.transmit` bez zpětného
     volání; podrobně oddíl „B3b“ níže;
4. přenos (míšení, výběr, drift) a živé fondy. **Příprava hotova 2026-11-03** (řádky A5 a A7): rozhraní pro Rust jsou funkce `cee.v2.phases_transmission` se zlatými daty; živé fondy jsou řídké, přenos se počítá nad hustými bloky kvůli pořadí sčítání. Čas přenosu je ale z 36 % ve tlacích, ne v číslech přenosu, takže zisk Rustu v tomto kroku bude malý, dokud tlaky a hodnocení nepřejdou na čísla z registru;
   **Hotovo 2026-11-03** (`zadani-rust-b4.md`, verze rozhraní 4):
   - **Krok 1, pevné pořadí míšení** (samostatný commit): `phases_transmission.mix`
     sčítá místo BLAS postupně přes zdroje (pro cílovou skupinu součiny
     `váha × podíl` zleva doprava podle vzestupného čísla zdroje, nulové váhy se
     přeskočí; viz kapitola Pořadí sčítání v míšení níže). Na zlatých vstupech se
     staré a nové míšení liší jen v posledních bitech (nejvyšší relativní rozdíl
     `2,2e-16` u `mix`, `4,6e-16` u `hear`). **Otisky historie všech sedmi světů
     z `scripts/v2_digests.py` zůstaly stejné**, změnily se jen otisky *stavu*
     světa připnuté v `tests/v2/test_v2_edits.py` (sedm světů) a zlatá data
     přenosu. Audit bran a retenci po změně jsme nespouštěli (stroj byl přetížený,
     koordinátor je zrušil); běžel jen audit před změnou. Důvod, proč to neškodí:
     historie, tedy to, co brány měří, je bitově stejná ve všech sedmi světech;
     rozdíl je ve stavu frekvencí v řádu `1e-16`;
   - **Fondy v Rustu**: `cee_core.NativeCells` drží řídké buňky bloku (řádek =
     proměnná, buňky seřazené podle slotu a skupiny, `pools.rs`) po celý běh; Python
     (`PoolBlock`) drží rukojeť a veřejné rozhraní `LivePools` je beze změny. Stejné
     rozhraní má Python `PyCells` (bez rozšíření nebo s `CEE_NATIVE=0`); uložení
     (pickle, checkpointy) je neutrální pole, takže stav jde obnovit v obou režimech.
     Hustý pohled `block.freqs` a `previous` a výsledky přenosu jsou pole `Slab`
     sdílená s `numpy` bez kopie; Rust je přepíše, jen když na ně nikdo
     neodkazuje, takže starý pohled zůstane, jaký byl. Malá pole (čísla variant ve
     slotech, klíče, „kdo proměnnou má“) zůstala v Pythonu a do přenosu jdou jako pohledy;
   - **Přenos v Rustu** (`transmission.rs`): `hear` a `settle` jsou funkce nad poli a
     tentýž kód běží v `NativeCells.transmit`. Jedno volání na blok a krok: Rust
     zamíchá, po kusech řádků zavolá Python pro tlaky (`fitness(od, do, podíly,
     slyšené)`, jediné zpětné volání) a vybere, přičte drift a ustálí; vstupy kroku
     (síť po komponentách, kanály, kohorty, klíče driftu) se předají jednou za krok
     (`NativeStep`). Do Pythonu se vrací nové podíly a základny jako pohledy; `stage`
     a `commit` je převezmou bez kopie. Až tlaky přejdou do Rustu, zpětné volání
     nahradí jejich výpočet nad stejnými poli (`heard`, `current`, výstup `fitness`
     tvaru kusu) a řetězec míšení, tlaky, výběr poběží celý v Rustu bez Pythonu (B6);
   - **`exp`, `log`, `cos`**: Rust je počítá knihovnou systému a `settle` v Rustu
     se používá jen tehdy, když zkouška `native.libm_matches()` (20 000 náhodných
     vstupů, včetně celého `hash_normal`) ukáže bitovou shodu s `numpy`. Jinak počítá
     `settle` Python (míšení a fondy zůstanou v Rustu). Na tomto stroji shodují;
   - **vlákna**: `CEE_THREADS` (výchozí 1) dělí míšení, výběr a přípravu řádků po
     souvislých úsecích proměnných; každý úsek zapisuje do vlastního výstupu a nic se
     mezi vlákny nesčítá (`std::thread::scope`, bez nové závislosti). Test ověřuje
     stejné bity pro 1, 2, 3, 5, 7 a 20 vláken i celý běh s `CEE_THREADS=3`;
   - **ověření**: zlatá data přenosu (`golden_transmission.json.gz`, přegenerovaná
     v kroku 1) projdou přes Rust (`test_v2_native_transmission.py`), dále náhodné sítě
     o 1 až 300 skupinách a 1 až 16 slotech, shoda `NativeCells` s `PyCells` při náhodných
     operacích a celý běh s Rustem, bez něj i při neshodě knihovny;
   - **zůstalo v Pythonu**: příprava kroku (`mixing_from_links`, komponenty, podíly kanálů),
     faktory kanálů po proměnných bloku, klíče driftu (`stable_int`), tlaky
     (`Pressure.scores`) a vše za přenosem (události, slovní zásoba, aktivace); `mix`
     jako samostatná funkce má jen Python (Rust ho má uvnitř `hear`). Fondy, které by
     měly přejít spolu s tlaky: malá pole slotů a `LivePools` (`load`, `innovate`, `release`);
5. hledání míst inovací a změny (indexy na čísla z registru a do Rustu celé; návrh a stav v oddílu „B5“ níže). **Hotovo 2026-11-03 (`zadani-rust-b5.md` a `zadani-rust-mista.md`, verze rozhraní 8)** pro zvukové, lexikální, sémantické, morfologické a syntaktické změny a výpůjčky slov; v Pythonu zůstala reanalýza hranice a prozodie (viz „Zbylé indexy míst (B5b)“);
6. hlavní smyčka `Simulation`; Python zůstane pro popis světa, export,
   kalibrační skripty a API; desktopová aplikace (Tauri) může engine volat
   přímo z Rustu bez Pythonu.
   **Pozorování (B6a) hotovo 2026-11-03** (`zadani-rust-b6a.md`, verze rozhraní 10): `observe.observe` je
   jedno volání Rustu za pozorování (oddíl „B6a“ níže); zbytek B6 (B6b až B6e) dělají jiné části.

Rozdělení na více crate (tabulka hlásek, změny, přenos, události) zkrátí
překlad po malé změně; konstanty a katalogy zůstanou daty
(`Parameters`, YAML/JSON), takže kalibrace nepotřebuje překlad.

## B5: indexy na čísla a hledání míst inovací v Rustu (návrh)

Zadání `zadani-rust-b5.md`. Čas dnes nejde do aritmetiky, ale do indexů nad
řetězcovými slovníky a do Python obalů. Cíl: stav indexů v plochých sloupcích
podle čísel z registru, žijící v Rustu; Python posílá jen pohledy na pole a
bere pole zpět. Inventura je bez nového profilu (podíly z A7 a B3 výše).

### Inventura

| Index | Stav dnes | Aktualizace | Čtenáři | Návrh |
|---|---|---|---|---|
| `ContextIndex` | `Counter` pětic (předchozí, hláska, další, přízvuk, druhá další), `Counter` hlásek, `_counted: dict[str, tuple]`, `deltas` | deník `FormStore.log` (řetězce), `vocabulary_log`, token úložiště; po slovech | `SoundSupportIndex`, `context_stats` (legacy), `contact.inventory` | **hotovo**, viz „Zvukové změny“ |
| `SoundSupportIndex` | opory kandidátů (`int64`), efektivní opory, po rodinách seznam míst (řetězce ID proměnných), míry, součet, `supported_map` | rozdíly počtů prostředí → `eval_supports` (Rust z B3) | `SoundChange.sites/rates/total_rate/weighted_sites/propose` | **hotovo**, viz níže |
| `LexicalClarityIndex` | `dominant`, `root_concepts`, `root_forms`, `owners` (tvar → množina dvojic), `scores`, `by_form`, `by_root` | `forms.log`, `dominant_log`, verze, podpis grafu | `Clarity` (`pressures/lexical.py`), `lexicon.py` | druhý krok, **hotovo**: bez stavu; skóre je funkce polí (dominantní kořeny podle čísla pojmu, tvary kódu, výchozí tvary, banka, seřazené příbuzné dvojice), tabulka vlastníků tvaru se staví z dominantních kořenů při každé dávce (stovka položek na skupinu je levnější než dorovnávání), jedno volání `cee_core.clarity_scores` na dávku tlaků pro všechny skupiny |
| `AssessmentVocabularyIndex` | vzorek nejčastějších tvarů (jména, tvary n-ticemi, `owners`, `vowels`), pozice změněných | `forms.log`, frekvence pojmů (`FrequencyMap.log`) | `assessment._vocabulary`, `NativeBank.assess_rows` | třetí krok: vzorek jako pole čísel morfémů a tvarů, vlastníci tvaru CSR |
| `FormAssessmentIndex` | `values: dict[proměnná, FormAssessment]`, závislosti `unit_vars/root_vars/exponent_vars/cell_vars` | deníky tvarů, užití, dominantních kořenů, frekvencí | `Articulation`/morfologické tlaky | třetí krok: špinavé příznaky podle čísla proměnné, závislosti CSR |
| `MorphologyCandidateIndex`, `WordMembershipIndex`, `ExponentIndex` | množiny a slovníky podle řetězců (jednotka, kořen, buňka, třída) | `vocabulary_log`, `forms.log` | `changes/morphology.py`, analogie | **hotovo (B5b)**: sloupce podle čísla morfému jako `MorphemeTable`, stav v Rustu (`morphology_index.rs`) |
| `SemanticDependencies`, `SemanticSitesIndex` | `dominant`, `relations`, `compounds`, `sites` jako řetězce | `dominant_log`, `usage_log`, `vocabulary_log` | `changes/lexicon.py` | **hotovo (B5b)**: graf v CSR, součty vah podle pojmu, stav v Rustu (`semantic_index.rs`) |

Pořadí práce řídí cena: zvukové změny (prostředí a opory), pak lexikální
jasnost, pak ostatní. Pozn.: jazyky a skupiny mají vlastní stav; svět sdílí
banku tvarů, takže i čísla tvarů a prostředí.

### Zvukové změny: číselná podoba a hranice volání

Stav jednoho kódu (skupiny) je ve **světovém objektu** `SoundIndex` (patří
bance tvarů, protože číslo tvaru platí jen s ní; ve světě `FormBank.sound_index`,
v Rustu `cee_core.SoundIndex`). Skupiny v něm mají řádek podle čísla úložiště
tvarů (`FormStore.token`).

- **Tvary a slovní zásoba bez deníků.** Pro každý morfém (číslo z registru)
  drží kód pole `counted_form` (číslo tvaru, který index započítal, −2 =
  nezapočítáno) a `counted_rule` (pravidlo přízvuku při započtení). Při volání
  Python předá bez kopírování tři pohledy: pole tvarů kódu (`FormStore.raw()[0]`),
  výchozí tvary světa (`columns.morphemes.form`) a příznaky slovní zásoby
  (`MorphemeSet.flags`). Rust jedním hustým průchodem po morfémech (desítky tisíc
  bajtů, výrazně levnější než jedno volání z Pythonu) najde změněné položky a
  dorovná jen je. Deník řetězců se tak nečte vůbec a index se při kopii světa
  nemůže rozejít s deníkem. Zůstalo se starým chováním: po změně pravidla
  přízvuku se prostředí nepřepočítají, dokud se tvar slova nezmění (existující
  zvláštnost; `counted_rule` ji drží, ať se otisky nezmění), a změna úložiště
  (jiný token) index celý přepočte.
- **Prostředí jako čísla.** Pětice (předchozí, hláska, další, přízvuk, druhá
  další) je v Rustu zabalená do dvou `u64` a pamatovaná jen pro tvar
  (mapa tvar × pravidlo → seznam prostředí v CSR). Žádný `Counter`: opory se
  přičítají přímo, `segment_occurrences[hláska]` (počet výskytů) určuje inventář.
- **Opory kandidátů** (`Vec<i64>` podle řádku kandidáta v sjednocení rodin pro
  inventář). Sada kandidátů (masky cíl, vlevo, vpravo, druhý vpravo, přízvuk,
  hranice rodin) zůstává v Pythonu, protože ji vyrábí `candidates()` rodin;
  Rustu se předá jednou pro inventář (`register_candidates`) a on ji přepíše na
  **transponované bitové sady** (pro každý sloupec hlásky bity kandidátů).
  Shoda jednoho výskytu s kandidáty je AND čtyř řádků po 64 kandidátech;
  přírůstek opory je celočíselný, takže výsledek nezávisí na pořadí sčítání.
  Změny tvarů přičtou a odečtou jen svá prostředí (čistý rozdíl po
  seřazení), změna inventáře přepočte opory z tvarů celé slovní zásoby.
- **Rodiny.** Pro každou rodinu Rust drží seznam míst (kandidáti s oporou ≥ 2),
  míry `(scale · min(1, opora / 8)) / n` a součet `pairwise_sum` (jako
  `np.sum`); přepočítá jen rodiny, kterým se změnily efektivní opory.
  Váhy `rates / total` počítá Python jen pro skupiny s nenulovým počtem inovací.
- **Hranice.** `Change.total_rates(contexts)` je dávkové: jedno volání
  `sync` pro všechny skupiny tiku vrací matici součtů (skupina × rodina);
  místa, míry a opory pro (skupinu, rodinu) s inovací se čtou zvlášť po jedné
  (vzácné). Chybí-li Rustu sada kandidátů pro nový inventář, vrátí `needs`
  (inventář) a Python ji zaregistruje a zavolá znovu (jako ve smyčce B2).
  `propose` zůstává v Pythonu (A5).
- **Python reference** má tutéž podobu (pole `counted_form`, `counted_rule`,
  prostředí jako čísla, opory v `numpy`), je fallbackem (`CEE_NATIVE=0`) a
  referencí testu Rust proti Pythonu. Celé je přírůstkové: změna jednoho tvaru
  stojí řádově její prostředí, ne celou slovní zásobu; změna inventáře je
  jediný případ plného přepočtu (v Pythonu hustý maticový součin jako dosud).
- **Vlákna.** Skupiny se zapisují do vlastního stavu a vlastních výstupů,
  takže jsou nezávislé; paralelizace po skupinách (`rayon`) je možná bez
  změny výsledku. Nezavedeno, dokud se nepotvrdí na celé sadě.
- **Checkpointy a pickle.** Python drží jen číselná pole; stav v Rustu se
  exportuje a obnovuje (`counted_form`, `counted_rule`, token) a podle něj se
  opory přepočítají, takže zůstane i zachovaná zvláštnost s pravidlem přízvuku.

### Stav práce (B5)

Hotovo (verze rozhraní 5): `ContextIndex` a `SoundSupportIndex` v číselné podobě
(`cee.v2.language.sound_index`, Python reference `SoundIndex`, Rust `cee_core.SoundIndex`,
`rust/cee_core/src/index.rs`; `ContextIndex` zůstal jako průčelí pro `contact.inventory`),
dávkové `Change.total_rates` volané z `Simulation._innovate`, a lexikální jasnost
(`lexical_index.clarity_scores`, `rust/cee_core/src/clarity.rs`).
Odchylky od návrhu výše: (1) jazykový stav indexu je na **světě** (`World.sound`), ne na
bance tvarů, protože banka se mezi kopiemi světa (checkpoint) sdílí a stav kódů ne;
(2) sada kandidátů zůstala v Pythonu (vyrábí ji `candidates()` rodin), Rust ji dostane
jednou pro inventář; (3) vlákna nejsou zavedena. Zachovaná zvláštnost: změna pravidla
přízvuku nepřepočítá prostředí slov, dokud se slovo nezmění (`counted_rule`).

`AssessmentVocabularyIndex` a `FormAssessmentIndex` jsou hotové v B3b (oddíl „B3b“ níže),
místa inovací všech druhů změn v oddílu níže.

### Zbylé indexy míst (B5b)

Zadání `zadani-rust-mista.md`. Cíl: celé hledání míst inovací pro všechny druhy změn jako
jedna dávka v Rustu nad čísly; hlavní smyčka (B6) pak nepotřebuje Python až do návrhu
varianty (`propose`).

**Číselná podoba.** Stav patří světu (`World.sites`, `cee.v2.language.site_index`) a žije v Rustu
(`cee_core.SiteIndex`: `morphology_index.rs`, `semantic_index.rs`, `sites.rs`, vazba
`sites_python.rs`). Python reference ve stejné podobě (`PythonSites`, `MorphIndex`,
`SemanticDependencies`) je fallback (`CEE_NATIVE=0`) a reference testu Rust proti Pythonu.

- *Morfologie* (klíč `FormStore.token`, sloupce podle čísla morfému z `MorphemeTable`: druh, třída,
  buňka, lexém, koncovka, hranice). Členové jsou tvary slov ve slovní zásobě; hustý průchod po
  členech porovnává syrová čísla úložiště kódu (tvar, hranice, koncovka, tvar kořene) s tím, co index
  započítal, takže se nečte žádný deník. Příspěvek člena (koncovka, podoba koncovky, splynutí s citačním
  tvarem, místo vyrovnání, místo rozšíření) je čistá funkce jeho tvaru, tvaru kořene a popisu buňky
  (produktivní koncovka), proto je přírůstkový stav vždy stejný jako výpočet od nuly. Počty koncovek
  jsou malé tabulky podle (třída, buňka) a podle koncovky; podoby koncovek jsou číslované (jedna
  podoba, jedno číslo). Remízy (produktivní koncovka, podoba koncovky) a pořadí míst (`form:level|tvar|`,
  `form:extend|tvar|koncovka`) rozhodují řetězcová ID, jako dřív; index proto drží jména morfémů jako
  bajty UTF-8 (řadí se stejně jako body Unicode v Pythonu) a seřazená místa dá až na požádání.
  Výchozí tvary morfémů, které kód nepřepsal, drží index ve vlastní aréně (Python je doplní na
  požádání), takže do banky tvarů světa nic nezařazuje. `ExponentIndex` zůstal jako pohled
  (`.exponents`, `.shapes`) pro `morphology.class_stats`, který se nezměnil.
- *Sémantika.* Graf pojmů je CSR podle cíle (vztahy seřazené podle jména zdroje jako
  `ConceptGraph.into`), recepty složenin také; váhy vztahů, které by potřebovaly `log1p`
  (posun, konverze, odvození), a shodnost slovních druhů předpočítá Python, takže v Rustu není
  žádná transcendentní funkce. Pro kód: dominantní kořeny podle čísla pojmu, příznaky míst
  (lexikální proměnné) a tabu, pro každý druh změny součet vah cest podle pojmu (0 = bez místa),
  vlastnosti kořenů (odvozenina z jediného pojmu, základ) a pro zpětné tvoření obrácený index
  „pojem → pojmy, jejichž kořen z něj vznikl“. Změna dominantního kořene dotkne sám pojem, cíle jeho
  vztahů a složenin a pojem, z něhož je odvozen starý či nový kořen; ty se přepočítají pro všech
  sedm druhů. Míry se čtou jako `base × součet` v pořadí jmen pojmů a sčítají se párově (`pairwise_sum`).
- *Syntax* („konstrukce jako čísla“). Katalog funkcí (šablona, slovní druh, třída a buňka podle
  číslování morfémů, zdroje, dárci a zástupci v CSR) a druh a stupeň konstrukce podle čísla varianty.
  Každý tik předá Python číslo dominantní varianty pro každou dvojici (skupina, funkce) a Rust z něj
  vyhodnotí `applies` všech deseti změn včetně `CategoryLoss` (míra místa z slabosti koncovky a podílu
  druhojazyčných mluvčích, celek párově). Slabost buňky a „zbytková koncovka“ čte z morfologického stavu
  téhož kódu.
- *Výpůjčky slov.* Python spočítá dárce a podíly vstupu podle kanálů (`contact`) a filtr výpůjček
  podle kanálu a pojmu; Rust sečte míry míst (`základ × podíl × filtr`, u více kanálů součet přes
  kanály) přes lexikální proměnné kódu.

**Hranice volání.** `Simulation._innovate` volá `changes.sites.rate_sums`: zvukové změny jeden
dotaz na index prostředí pro všechny rodiny (`batch_total_rates`, dřív jeden dotaz na rodinu), ostatní
jednu dávku `SiteIndex.batch` (matice skupina × 21 sloupců: expresivní tvoření, 7 sémantických změn,
vyrovnání, rozšíření, 10 syntaktických změn, výpůjčky; součty a počty míst). Místa a míry se čtou zvlášť
jen pro (skupinu, změnu) s inovací (`weighted_sites`); `propose` zůstal v Pythonu. Stav se dorovnává jen
u kódů, jejichž klíč (verze stavu, délka deníku tvarů a slovní zásoby, verze slovníku) se změnil.
Hledání celkových měr tak stojí dvě dávková volání za tik (zvukový index a index míst, každé s případným
doplněním výchozích tvarů či sady kandidátů) místo jednoho volání na skupinu a druh změny; jedno volání pro
oba indexy najednou by vyžadovalo, aby si je Rust předával mezi sebou (zůstalo na B6).

**Pořadí a bity.** Míry a součty jsou stejné jako dřív (`base × počet × násobek`, součty
`np.sum`), ověřeno zlatými daty míst z A7 přes Rust, porovnáním dávky se `total_rate` po jedné změně
a Rustu s referencí v Pythonu (`tests/v2/test_v2_site_index.py`). Stav indexu se při kopii světa a
uložení nepřenáší (`__getstate__` nese jen volbu Rust/Python) a při dalším použití se deterministicky
postaví znovu.

**Zbytečné tvary v bance.** Po B5 měla banka ve světě `shift` v ticku 4 o polovinu víc tvarů
(1 170 místo 792). Příčina: index prostředí zvukových změn zařazoval do banky výchozí tvar každého
člena slovní zásoby, který kód nepřepsal (728 tvarů), aby měl jeho číslo. Oprava je hotová na větvi
`engine-v2-rust-sites-bank-forms` (index drží výchozí tvary ve vlastní aréně a banka má opět 792 tvarů),
**ale není sloučená**: jediný rozdíl, který se našel, je poslední bit jedné dávky zlatých dat tlaků
(shift, tik 4, rozdíl 4e-19) přes pořadí ceny homofonů; otisky historie a připnuté otisky stavu jsou
stejné. Sloučí se po opravě pořadí od agenta na tlaky.

**Zůstalo v Pythonu.** Reanalýza hranice (`Rebracketing`, kandidáti podle verze stavu), prozodické
změny (jedno místo), návrh variant (`propose`), čtení dominantních konstrukcí z živých fondů
(`world.dominant`, jednou na skupinu a funkci za tik), dárci a podíly vstupu u výpůjček (`contact`),
sestavení grafu a katalogu (jednou za změnu) a registrace konstrukcí. Vlákna nejsou zavedena (stav
kódů je nezávislý, takže paralelizace po kódech by výsledek nezměnila; sdílená je jen tabulka
podob koncovek).

## B3b: tlaky a hodnocení v Rustu, napojené do přenosu

Zadání `zadani-rust-tlaky.md`. Řetězec míšení → tlaky → výběr běží v Rustu bez
přechodu do Pythonu; Python se ptá jen na to, co v Rustu ještě není (viz „Dodávky“).

### Číselná podoba

- **Vzorek slov kódu** (`language/assessment_index.py`, Rust `assess_index::Sample`): čísla
  morfémů v pořadí jmen (na tom stojí pořadí součtů), `int64` čísla tvarů v bance, `float64`
  váhy a jejich součet, počty samohlásek podle čísla hlásky. Výběr a váhy (frekvence užití)
  počítá Python (`SampleKeeper`, stejná pravidla zneplatnění jako dřív: výběr při změně verze
  slovní zásoby, váhy při změně slovní zásoby či frekvencí pojmů, jinak zůstávají); čísla tvarů a
  samohlásky Rust dorovnává hustým průchodem po vzorku (120 čtení z polí `FormStore` a výchozích
  tvarů), když se změní verze kódu. Deník tvarů se v Rustu nečte.
- **Uložená hodnocení procesů**: seřazený vektor podle čísla proměnné (verze kódu, tik, pět hodnot),
  tatáž pravidla platnosti (`STALE_TICKS`) a tatáž šířka matice párových součtů (nejdelší vzorek mezi
  zastaralými skupinami téhož pravidla přízvuku a téhož volání; je to součást bitové shody).
  Zisk rozptylu vokálů se počítá v Rustu z polí souřadnic samohlásek (`__pow__(2)` je tam součin;
  `native.dispersion_matches()` to ověří na všech rozdílech souřadnic), ostatní součty `pairwise_sum`
  (`native.sums_match()`).
- **Hodnocení tvarů** (`FormAssessmentIndex`): klíče jsou čísla (proměnná, morfém, koncovka),
  dominantní kořeny pole podle čísla pojmu. Hodnoty (`gain`, frekvence, dva příznaky splynutí) drží
  Rust jako zrcadlo podle (token kódu, číslo proměnné); každé zrušení hodnoty v Pythonu se do zrcadla
  hned zapíše (`mirror`), chybějící hodnotu dodá Python na požádání.
- Stav obou indexů je **na světě** (`World.assessment`, odvozený stav), po tokenu úložiště tvarů
  kódu (jako `World.sound`). Uložení a kopie světa nesou `SampleKeeper` a uložená hodnocení jako
  pole; `index_of(world)` při změně režimu stav přenese. Python reference (`AssessmentIndex`) má
  stejnou podobu a je fallbackem (`CEE_NATIVE=0`) i referencí testů.

### Rozhraní tlaků v Rustu

`NativeCells.transmit(..., pressures=(step, rows))`:

- `PressureStep` (jednou za krok, sdílí ho každý blok): banka a index, dodavatel, plán tlaků
  (pro každý druh proměnných seznam (číslo tlaku, váha) v pořadí sčítání z `pressures_by_kind`),
  konstanty z `Parameters`, pole podle skupin (token, verze kódu, pravidlo přízvuku, silný přízvuk,
  podíl L2, klíč ocenění změn v epoše, pole tvarů a dominantních kořenů kódu), sloupce tabulky
  variant (změna, morfém, původ, přitažlivost, klíč ocenění) a morfémů (výchozí tvar, lexém, buňka).
- popis řádků bloku (13 polí, drží se u bloku podle `PoolBlock.layout`): druh, pojem, číslo proměnné,
  slot varianty „změna“, řádek procesu v bance, úspora a zřetelnost procesu, příznaky, ochrana
  zažitého slova (z frekvencí pojmů), čísla variant ve slotech a řídké položky
  (číslo tlaku, buňka bloku, hodnota).
- Výpočet kusu bloku má dvě fáze: **podklady** (jedno vlákno, mění stav: hodnocení procesů a tvarů
  v dosažených buňkách, podíl koncových souhlásek, tabulky vlastníků tvarů) a **skóre** (jen čtení,
  řádky jsou nezávislé a dělí se na vlákna `CEE_THREADS`). Součet vážených tlaků má stejné pořadí
  jako `fitness_of` (`fitness += síla * skóre` po tlacích druhu proměnných); nulové členy se
  nepřičítají (`x + 0 = x`, fitness nikdy není −0). Výběr čte tlak slotu jen tam, kde kohorta slot
  slyší (`slyšený × exp(…)` je jinak nula), proto přenos ocenění změn (`Actuation`, jediný tlak
  počítaný ve všech buňkách) v neslyšených slotech vynechává; zlatá data a zkoušky
  (`scores_of_batch`) počítají celé pole (`exhaustive`).
- `transmit` vrací pohledy na výsledky jako dřív; zpětné volání `fitness` zůstává pro tlaky, které
  Rust nezná (vlastní třídy), pro paralelní běh (`fitness_hook`), svět bez tabulky hlásek a režim
  bez Rustu.

### Dodávky (co dnes dodává Python, v B6 přejde do Rustu)

Co kód nezná, zapíše do `Needs` a výpočet té položky vynechá; po průchodu zavolá dodavatele
(`pressures_native.Supplier`) a kus se spočítá znovu (v ustáleném stavu se nevolá nic):
přepočet vzorku (výběr a váhy), výchozí tvary morfémů, které ještě nejsou v bance, mapy hlásek
procesů `change` a `tone`, nahraditelnost buňky paradigmatu jinou konstrukcí (cena dvojic téhož
lexému), podíl slov se souhláskovou koncovkou (fonotaktika apokopy) a hodnocení tvarů
(`morphology._assess_reference`, `class_stats`: počítá je dál Python při zrušení hodnoty, protože
čtou `ExponentIndex` a tvoří nové tvary; hledání jejich dotčení je číselné). Tvary, které při
hodnocení vznikly v Rustu, Python převezme po přenosu (`adopt_created`).

### Co zůstává v Pythonu

Konstrukční tlaky (`Expressivity`, `Economy`, `Fusion`, `Learnability`, `Ambiguity`; čtou katalog
funkcí, repertoár a paradigmata přes objekty v `syntax.py`), `Norm` (škola a spisovný jazyk) a `Taboo`
(tabuizované pojmy, původ slova): Python je spočítá ze stavu na začátku kroku a předá jako řídké
položky (`Overlay`); Rust je přičte na správné místo v pořadí tlaků. Škola a tabu jsou řídké (jen
některé skupiny), konstrukční řádky jsou vzácné, takže nic z toho není horké místo. Bitová
shoda drží i s nimi (zlatá data i otisky).

### Pořadí sčítání ceny nových homofonů (vědomá změna posledních bitů)

`merge_mass` sčítal ceny dvojic nových homofonů v pořadí čísel tvarů v bance, takže ho měnilo, že
banka držela jiné tvary (stalo se v B5). Dvojice se teď sčítají vzestupně podle pozic ve vzorku
(Python `assessment._new_pairs`, Rust `RowAssessment::pairs`). Rozdíl v zlatých datech: 15 ze 307
řádků s dvojicemi, nejvýš 7e-18 absolutně (2,5e-16 relativně). Otisky historie všech sedmi světů
i otisky stavu světů v `test_v2_edits.py` zůstaly stejné; přegenerovala se zlatá data hodnocení
a tlaků (`golden_assessment.json.gz`, `golden_pressures.json.gz`).

### Výsledek

Otisky všech sedmi světů beze změny (s Rustem, s `CEE_THREADS=3` i s `CEE_NATIVE=0 --quick`), obě
celé sady prošly (s Rustem 1 355, bez něj 1 252 a 103 přeskočeno). Jediné měření na konci (sdílený
stroj, tři střídavé běhy po sobě): valley-50 z 30,6 až 31,7 s (stav před B3b) na 26,7 až 27,4 s.
Zbytek je převážně mimo tlaky v Rustu: z přenosu (profil valley-50 s `cProfile`, zhruba
polovina běhu) zabírá asi polovinu Python hodnocení tvarů při dodávce (`FormAssessmentIndex`,
`_assess_reference`, `class_stats`, závisí na `ExponentIndex` z B5b), další čas jsou hledání míst
inovací, sledování slovní zásoby a pozorování.

### Zlatá data

Zlatá data tlaků (`test_v2_golden_pressures.py`, reference v Pythonu s `CEE_NATIVE=0`) procházejí
i přes Rust: `test_v2_native_pressures.py` zopakuje scénáře s Rustem, po přenosu bloku v ticích
záznamů spočítá každý tlak záznamu v Rustu nad dávkou ze záznamu (`pressures_native.scores_of_batch`)
a porovná ho s výstupem Pythonu bit po bitu; dále součet vážených tlaků pro 1 a 3 vlákna.

## B6a: pozorování (dialekty a jazyky) v Rustu

Zadání `zadani-rust-b6a.md`, verze rozhraní 10. `Simulation._observe` → `observe.observe` je jedno volání
`cee_core.observe_step` za pozorování (`rust/cee_core/src/observe.rs`, vazba `observe_python.rs`); Python
skládá vstup z polí (`observe._gather`) a zapisuje výsledek. Bez rozšíření, s `CEE_NATIVE=0` nebo bez bitové
shody knihoven (`native.observe_matches`) počítá Python reference nad týmiž poli.

### Číselná podoba a hranice volání

- **Vstup jednoho volání** (nic se nekopíruje, kromě malých polí): pro každý blok živých fondů hustý pohled
  `freqs (řádky, skupiny, sloty)` a `present (řádky, skupiny)` (sdílená paměť s Rustem), vybrané řádky
  (proměnné slov a konstrukcí) a pořadí proměnných při výběru vzorku sloupců (`stable_int("observe", jméno)`,
  hašuje se jednou za běh); čísla mluvených skupin mezi živými; **dominantní kořeny všech živých skupin
  jako CSR** (`ptr`, číslo pojmu, číslo kořene, číslo tvaru) ve vkládacím pořadí `DominantMap`; **tabulka
  různých tvarů** jako CSR hlásek; pořadí pojmů podle názvu (`Numbering.ranks`) a `SegmentTable.vectors`
  (int8); vazby jako dvojice pozic mluvených skupin (`LinkTable`), polohy, čísla dosavadních linií, prahy.
- **Tvar jako číslo.** Číslo tvaru v tabulce je podle *obsahu*: stejný obsah, stejné číslo. Tvar uložený
  v `FormStore` má číslo z banky; výchozí tvar morfému, který v bance ještě není, se předá podle obsahu
  a do banky se **nezařazuje** (test `test_vyber_tvaru_nic_nezarazuje_do_banky...`). Čísla tvarů v bance
  se mezi Rustem a Pythonem liší, proto zlatá data vybírají tvary podle obsahu.
- **Co dělá Rust** (jedno volání, bez zpětného volání): rysy (proměnlivé sloupce, vzorek proměnných nad
  2 000 sloupců, vložení podílů do 13 intervalů v `f32`, čtverce skupin párovým součtem), kategorie tvarů
  a vzdálenosti mezi tvary téhož kořene pojmu (editační vzdálenost z vektorů rysů; číslování kategorií
  řazením, ne hašováním, jako pořadí prvního výskytu), kandidáti sloučení (vazby a čtyři nejbližší
  sousedé na mřížce), **obě průměrné vazby** (dialekty a jazyky s hysterezí; kandidáti se počítají jednou)
  a s `keep_distances` matice vzdáleností kódů (`distance_matrix` po blocích proměnných jako `np.sum(axis=(0, 3))`
  a `cognate_matrix`; horní trojúhelník po souvislých úsecích řádků na `CEE_THREADS` vláknech, spodní se zrcadlí).
  Rysy se na vláknech dělí po skupinách. Vrací shluky jako seznamy pozic, matici a pro testy volitelně rysy.
- **Vzdálenost tvarů v dávce.** Editační vzdálenost je jen součty, podíl a minimum, takže stačí stejný
  postup tabulky; cena záměny hlásek je podíl odlišných rysů (`FEATURE_SCALE`, předává se při volání)
  s hustou pamětí cen v rámci volání. Dvojice tvarů téhož kořene pojmu se počítají jednou na dvojici
  (vzdálenost je přesně symetrická). Paměť vzdáleností mezi pozorováními (`_DISTANCES`) Rust nemá: dvojice
  jsou levnější přepočítat, než hledat, a výsledek by neměnila.
- **Slovníky v pořadí vkládání** (`Sparse`): `forms`, `spread` a četnosti linií jsou vektory sloupců a hodnot
  v pořadí vkládání s binárním hledáním; na pořadí stojí `sum(weight * large.get(...))` a sloučení shluků jako
  v `dict`. Hašovací mapy v Rustu nejsou.

### Bitová shoda: co není čistá aritmetika

- **Skalární součin `f32` řádků `shares[a] @ shares[b]`** volá BLAS, jehož pořadí sčítání neznáme (na tomto
  stroji Accelerate; vlastní pokusy s pevným počtem pruhů, FMA a stromy součtu se s ním neshodly ani na
  malých délkách). Rust proto na macOS volá **tutéž funkci `cblas_sdot` z Accelerate** (`#[link(name =
  "Accelerate", kind = "framework")]`, bez nové crate). Jinde (jiný BLAS) žádná shoda zaručena není:
  `native.observe_matches()` jednou ověří shodu na maticích šířek násobků 13 a bez shody pozorování počítá
  Python (jako `libm_matches` u přenosu).
- Dále se ověřují `hypot` (vzdálenost sousedů; `np.hypot` a `f64::hypot` volají libm), celočíselné dělení
  `x // size` s opravou zaokrouhlení (`numpy` a Python používají `divmod` s opravou, Rust ji opakuje) a
  součet `float32` přes osy `(0, 3)` matice vzdáleností (po řádcích párový součet přes sloty, mezi řádky
  postupně; tak to dělá `numpy` pro souvislé pole). `sums_match` hlídá párové součty čtverců.
- Pořadí a remízy: halda nad `(hodnota, a, b, verze a, verze b)` (pořadí výběru je dané úplným
  uspořádáním, ne implementací haldy), součty `sum(...)` z `dict` v pořadí vkládání, `max(0.0, value)`
  vrací +0, četnosti tvarů a linií jsou celá čísla v `f64`, takže jejich součty na pořadí nezávisejí.

### Zlatá data a testy

- `scripts/v2_golden_observe.py` (Python reference), `tests/v2/golden_observe.py`, `tests/v2/data/golden_observe.json.gz`
  (asi 29 kB), `test_v2_golden_observe.py`: ve všech sedmi scénářích z `golden_worlds.py` po 3 až 4 tickách
  rysy mluvených skupin (otisky matice vložení, slovníků tvarů a rozptylu, čtverce), kandidáti sloučení,
  dialekty, jazyky a události `LineageTracker` pro dvě dvojice prahů (tracker se mezi ticky předává), matice
  vzdáleností kódů a 276 editačních vzdáleností vybraných tvarů. Test běh zopakuje a porovná bit po bitu
  v Pythonu i v Rustu. Stav světa se neukládá (viz A7).
- `test_v2_native_observe.py`: Rust proti Pythonu na skutečném světě (rysy, kandidáti, shluky, 1 až 7 vláken,
  matice vzdáleností a `cognate_matrix`, celé `observe` včetně psaných skupin a veřejné domény), na syntetických
  blocích se vzorkem proměnných, na stovkách náhodných rysů se slovníky ve zvoleném pořadí vkládání (vazba, hystereze),
  na náhodných polohách (mřížka s remízami, shodné polohy), editační vzdálenosti pro dva dělitele a běh s pozorováním
  v obou režimech (otisk historie a matice).

### Přepsané testy (viz „Přepis existujících testů“ v zadání)

`test_v2_observe.py`: `_features(world, ids)` a `constrained_average_linkage(world, ids, threshold, features=...)`
fixovaly objektové rozhraní (svět a ID řetězce); nahradily je pomocné funkce `_features(world, ids)` nad poli
(`_gather`) a `_linkage(...)` s kandidáty z `_geometry`/`_candidates` a čísly linií místo řetězců. Testované chování
a hodnoty (vložení blízké vzdálenosti všech dvojic, vazba shluku jako průměr dvojic, hystereze) jsou stejné.

### Co zůstává v Pythonu a pro B6e

`LineageTracker` a sestavení snímku (malé), skládání vstupu z polí (smyčka po skupinách pro dominantní kořeny,
`ranks` a polohy; vše lineární v počtu skupin), hustý pohled na bloky fondů (`pool.freqs`; po kroku se zahazuje
a při pozorování znovu staví z řídkého uložení: B6e by měl číst řídké buňky z `NativeCells` přímo a hustou
matici nestavět), `world.links` a polohy. Pro hlavní smyčku v Rustu bez Pythonu zbývá: dominantní kořeny a tvary
přímo z polí kódu v Rustu (dnes přes `DominantMap.order`), tabulka tvarů z arény banky místo kopie obsahu, vazby
a polohy z tabulek světa, a stav dosavadních linií. Výkon se v B6a neměřil (měří hlavní agent najednou).

## Bitová shoda při přechodu do Rustu

Transcendentní funkce (`exp`, `log`, `sqrt` je v pořádku) počítá numpy jinou
implementací než standardní knihovna Rustu a v posledním bitu se mohou
lišit. Postup: jednotlivé funkce porovnávat s tolerancí v řádu posledního
bitu, otisky při přechodu jednou vědomě vyměnit a nový stav ověřit celou
sadou bran a statistickým srovnáním na seedech. Od té chvíle jsou
referencí otisky z Rustu.

### Pořadí sčítání v míšení

`phases_transmission.mix` násobila matici vazeb s hodnotami přes BLAS (`matrix @ flat`).
Pořadí sčítání v BLAS závisí na knihovně, její verzi a tvaru matice (proto se
dřív násobila každá propojená komponenta zvlášť); Rust ho bitově nezopakuje.
Nové pořadí je **postupně přes zdroje**: pro cílovou skupinu `i` je výsledek
`((0 + w[i,j₁] × x[j₁]) + w[i,j₂] × x[j₂]) + …`, kde `j₁ < j₂ < …` jsou zdroje s
nenulovou vahou. Součin se zaokrouhlí zvlášť a pak se přičte (žádné FMA; Rust ho
sám nikdy nesloučí), nulové váhy se přeskočí (nulový součin součet nezmění, takže
výsledek nezávisí na počtu nulových sloupců matice ani na rozdělení na komponenty).
V numpy se to počítá po „pořadí v řádku“ (`_by_rank`): k-tá nenulová buňka každého
řádku najednou, tedy tolik kroků, kolik má nejhustší řádek sousedů, a práce
úměrná počtu vazeb, ne čtverci počtu skupin.

Vědomá změna otisků, kterou nese jen pořadí sčítání: nic jiného (konstanty,
`Parameters`, brány) se neměnilo. Ověřeno tím, že staré a nové míšení se na
stejném vstupu liší jen v posledních bitech (relativně do `5e-16`). Otisky
historie se nezměnily vůbec (všech sedm světů z `scripts/v2_digests.py`), otisky
stavu světa v `tests/v2/test_v2_edits.py` ano.

Zbývající součty přenosu: `normalized` sčítá seřazené podíly slotů zleva doprava
(v Rustu totéž), `mixing_from_links` sčítá řádky `numpy.sum` a zůstává v Pythonu
(příprava kroku, ne horká cesta; kdyby přešla do Rustu, platí `pairwise_sum` a
hlídač `sums_match`), `settle` jinak sčítá jen po prvcích (přesné součty a
součiny).

## Nevýhody, se kterými počítat

- pomalejší experimentování s modelem (překlad, typy); proto načasovat
  fázi B s ustálením M7;
- překlad: ladicí po malé změně jednotky sekund, optimalizovaný desítky
  sekund, čistý 1–3 minuty (odhad pro ~16 tisíc řádků);
- přechodné období dvou jazyků (vazby, sestavení přes maturin);
- binárky pro každou platformu (u Tauri spíš výhoda: engine bez Pythonu).

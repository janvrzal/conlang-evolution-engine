# 20. Audit výkonu enginu v Rustu

Audit náročných a neefektivních algoritmů v `rust/cee_engine` a `rust/cee_core` (stav větve
`engine-v2-perf-audit`, odvozené z `engine-v2-numba`). Kód enginu se neopravoval; všechny
číselné údaje jsou měření nebo dočasné sondy, které byly po měření vráceny (`git checkout`).
Keše klíčované verzí kódu (`class_stats`, `cell_weakness`, `ViewCache`, četnosti užití), které
předělává jiný agent, se tu nehlásí.

## Jak se měřilo

- `cargo build --release` s `CARGO_PROFILE_RELEASE_DEBUG=true` (symboly), `cee … --phase-times`,
  profil macOS `sample` (1 ms) nad `target/release/cee`; inkluzivní časy funkcí jsou součty uzlů
  stromu volání. Počty (velikost tabulek, hustota buněk, počet sad kandidátů) dodaly dočasné
  čítače vložené do `bank.rs`, `block.rs`, `transmission.rs`, `candidates.rs`, `index.rs`
  a `bin/cee.rs`; po měření vráceno.
- Scénáře: `valley-50` (do 1000, 1500, 2000, 4000), `village-400` (do 200, 400, 800), `grid-5x5`,
  příklad `src/cee/data/v2_example_world.json`; 1 a 8 vláken. Krok je 25 let (valley do 4000 = 160 kroků).
- **Upozornění k šumu:** na stroji běžel souběžně jiný agent (load average 7 až 10 z 8 jader).
  Absolutní časy kolísají až o desítky procent (valley-50 do 4000 na 1 vlákně: 15 s v klidnější chvíli,
  26 s při zátěži). Podíly fází a poměry jsou spolehlivější než sekundy; použité hodnoty jsou z klidnějších
  běhů, pokud není uvedeno jinak. Otisky historie (`digest`) všech ověřených úprav byly beze změny.

## Souhrn nálezů (seřazeno podle odhadovaného zisku)

| # | místo | co je špatně | dnes → po opravě | naměřeno | návrh | riziko pro determinismus |
|---|---|---|---|---|---|---|
| 1 | `cee_core/src/bank.rs:65,388` (`Table.results`, `grow_results`) | tabulka výsledků procesu je **hustá přes čísla všech tvarů** a zdvojuje se; téměř celá je prázdná | paměť O(procesy × pravidla × tvary), tvary rostou přes 6× na zdvojnásobení běhu → O(počet skutečně dotázaných dvojic) | valley-50 do 4000: **553 M buněk = 4,4 GB, 99,0 % `UNKNOWN`** (do 2000: 485 MB, do 1000: 19 MB); špičková paměť běhu 3,2 GB; `grow_results` (memset + realloc) ≈ 3,5 % času a `missing` filtr v `Bank::results` (`bank.rs:431`) dalších ~3 % | řídké úložiště: stránky po 4096 tvarech alokované líně, nebo `HashMap` tvar→výsledek na tabulku; `missing` počítat jen přes dotázané tvary | žádné: čistá keš, stejné hodnoty |
| 2 | `cee_engine/src/transfer/block.rs:148-230` (`transmit_rows`), `cee_core/src/transmission.rs:422-570` (`settle_range`, `settle_cell`), `pressures.rs:298` (`fitness`) | blok se přenáší jako **hustý** `řádky × všechny skupiny × kapacita slotů`; šest polí (`current`, `previous`, `heard`, `fitness`, `updated`, `baseline`), všechny buňky se počítají včetně exp, driftu (`hash_normal`: log, cos) a třech řazení | O(řádky × G × kapacita) → O(živé buňky); u village-400 jsou živé buňky 4,3 % | village-400 do 400: hustých hodnot 118 M, nenulových 5,1 M (4,3 %); valley-50 do 4000: 33,6 M / 12,1 M (36 %). `transmit_rows` je 78 % času village-400 (z toho `settle_range` 54 %, `fitness` 34 %) | řídké kusy: v každém řádku pracovat jen se sloty a skupinami, kde je `current`, `previous` nebo `heard` nenulové (a u tlaků jen v nich); viz také #3 | nulová buňka dává přesně nulu (viz #3), takže pořadí a výsledky zůstanou; pozor na `hash_normal`, ten se volá jen při `spread > 0`, tj. jen pro slyšené varianty |
| 3 | `cee_core/src/transmission.rs:335` (`normalize_cell`) | třikrát na buňku se **řadí celé pole slotů** (až 512), ač je většina nul; sčítání nul na součet nemá vliv | O(k log k) s k = kapacita → k = počet nenulových | village-400: řazení ≈ 20–25 % času běhu (`driftsort`+`quicksort` 1,4–1,8 s ze 7 s). **Ověřeno experimentem:** řadit jen nenulové hodnoty → blocks 6,55 s → 4,98 s (−24 %), celý běh 9,26 → 7,73 s (−16 %), otisk historie **beze změny** (village-400 do 400 i valley-50 do 1500) | v `normalize_cell` vybrat nenulové do pracovního pole, seřadit prefix, sečíst; hotová 10řádková změna | žádné (součet seřazených nezáporných čísel s nulami = součet bez nul; experiment bit po bitu stejný) |
| 4 | `cee_core/src/index.rs:482-540` (`SoundIndex::sync`, `prebuild_sets`), `candidates.rs:1581-1609` (`build`) | při každém novém inventáři skupiny se staví celá sada kandidátů (řetězcová ID `format!("process:{}", key)`, **lineární hledání duplicit** `keyed.iter().all(..)` na kandidát, řazení řetězců) | O(K²) řetězcových porovnání na sadu → O(K log K) nebo bez řetězců | valley-50 do 4000: **3 814 staveb** (1,0 M kandidátů, ~270 na sadu); opakování stejného inventáře jen 83×, takže keš nepomůže; `make_set` ≈ 929 ms ze 14 s (6–7 %), `sync_groups` celkem 16 % času běhu (62 % fáze inovací) | duplicitu hlídat `HashSet` (nebo řadit a `dedup`), ID nepočítat jako `String`, klíč kandidáta jako číselnou n-tici; případně inkrementálně přidávat/odebírat hlásky | žádné, pokud se zachová pořadí „první vyhrává, v rodině podle ID“ |
| 5 | `cee_core/src/phonology.rs:227-270` (`queue_into`), `bank.rs:568` (`lookup`) | zařazení slova do front **projde všechny živé procesy** a pro každý volá `may_apply` + `lookup`; procesů přibývá v čase | O(M × P), P roste lineárně v čase → O(M × počet procesů, které na tvar sedí) | valley-50 do 4000: P = 273 (do 1000: 114); `queue_into` ≈ 9 % času; fáze `rebuild` roste **t^2,2** (95 → 369 → 1 870 ms pro 1000/2000/4000 let) | projít jen nastavené bity `rows_of(form_id)` (banka je už má předfiltrované), a ne všechny cíle | žádné, pokud se iteruje ve vzestupném pořadí řádků jako dnes |
| 6 | `cee_engine/src/transfer/assess.rs:389` (`refresh`), `Bank::results` | hodnocení procesu × skupina se po vypršení (8 ticků) počítá znovu nad vzorkem 120 slov a **nové tvary se trvale zařazují do banky** i pro hypotetické výsledky | O(procesy × skupiny × 120) za 8 ticků; banka roste s každým hypotetickým tvarem | `refresh` 13–15 % času valley-50 do 4000 (z toho `Bank::results` 669 ms, `assess_group` 300 ms); počet tvarů v bance roste 14 k → 95 k → 361 k (1000/2000/4000) a žádný se nikdy neuvolní | (a) hypotetické výsledky nezařazovat do banky (dočasné tvary), (b) hodnocení nepřepočítávat, když se nezměnila verze kódu **a** vzorek (dnes se přepočítá po 8 tick bez ohledu na změny); (c) uvolňovat nikdy nepoužité tvary | (a) čísla tvarů v bance se mění, ale otisky ne (ověřeno); (b) nevyplatí se, viz Stav oprav |
| 7 | `cee_engine/src/phonology/index.rs:49-88` (`stamp_of`, `group_vectors`) a `index.rs` `sync_group_diff` | razítko skupiny obsahuje **`world.morphemes.len()`**, takže každý nový morfém kdekoliv zneplatní **všechny** skupiny; pak se pro každou skupinu staví `flags`/`forms` délky M a diff běží přes celé M | O(G × M) za krok místo O(změny) | valley-50: M = 6 934 (do 4000), village-400: M = 17 483 už po 400 letech; podíl samotného průchodu je v profilu zakrytý stavbou sad (#4), ale roste s G a M (village-400: `sync` 154 ms ze 7 000 při M 17 k, bude kvadratické v G při větším světě) | razítko bez délky morfémů (nové morfémy se do slovní zásoby skupiny dostanou přes `vocabulary_log`, který razítko už obsahuje), diff jen přes zápis deníku | žádné |
| 8 | `cee_engine/src/history.rs:54` (`events: Vec<Map<String, Value>>`) | historie drží **každý záznam jako objekt `BTreeMap<String, Value>`** (klíče jako alokované řetězce); roste lineárně s počtem záznamů a ty rostou kvadraticky v čase | ~0,6–1 KB na záznam; typované záznamy ~100 B | valley-50 do 4000: **430 k záznamů** (do 1000: 46 k; do 2000: 141 k; `milestone` 236 k, `established` 99 k); JSON log 68 MB; v paměti odhadem 250–450 MB (odhad, neměřeno zvlášť); sestavení objektů `History::event` ≈ 1 % času | typovaná enum + serializace až při exportu; `milestone`/`established` ukládat po tiku jako sloupce (varianta, skupina, úroveň) | žádné pro otisk, pokud se zachová text řádků |
| 9 | `cee_engine/src/simulation.rs:199` (`checkpoint`) | kontrolní bod **klonuje celý `World` a `History`** (včetně banky: `FormBank::clone` znovu zařazuje všech 361 k tvarů a zahazuje tabulky) | O(velikost světa) na kontrolní bod | neměřeno (výchozí `checkpoint_every = None`); při zapnutí je cena úměrná paměti z #1 a #8 | ukládat jen rozdíl od posledního bodu nebo klonovat s `Arc` sdílenou historií | žádné |
| 10 | `cee_engine/src/transfer/assess.rs:127` (`select`) | při změně klíče (verze lexikonu, počtu morfémů, **celosvětová `morphemes.len()`**) se pro skupinu **řadí celá slovní zásoba** s porovnáním jmen (`names.name(a).cmp(..)`) a pak znovu | O(V log V) na skupinu a tik | `select` ≈ 1 % času; zbytečně často kvůli klíči s globálním `morphemes.len()` (stejný zdroj jako #7) | klíč jen z verze lexikonu skupiny; částečné řazení (`select_nth_unstable`) na 120 nejčastějších | žádné |
| 11 | `cee_engine/src/transfer/pressures.rs` `lexical_clarity` | `world.semantics.clone()` (Arc) **v každé buňce**; atomické počítadlo sdílené vlákny | 1 atomická operace na buňku | zanedbatelné samo, ale zbytečný kontakt mezi vlákny při 8 vláknech | vzít odkaz mimo smyčku | žádné |
| 12 | `cee_engine/src/world.rs:786` (`gravity_pairs`), `Links` | gravitační vazby **všech dvojic skupin**, vazby v `BTreeMap<(GroupId,GroupId),Link>` | O(G²) | stavba světa: valley-50 0,15 s, **village-400 1,1 s** (u 1 600 skupin by to bylo desítky sekund) | omezit sousedy prostorovým indexem (mřížka) a `max_distance` použít už při průchodu; plnit CSR přímo | žádné, pokud se zachová pořadí vzniku vazeb |

Poznámka k pořadí: zisky #1–#3 jsou měřitelné přímo (#3 experimentem), #2 je největší strukturální
položka pro velké světy; #4–#6 jsou odhady z profilu (podíl času, ne experiment).

## Profil po fázích

### valley-50, 4 000 let, 1 vlákno (celkem 14 574 ms v klidnějším běhu; podíly podfází z druhého, zatíženého běhu)

| fáze | ms | podíl |
|---|---|---|
| transmission | 8 433 | 57,9 % |
| – blocks (tlaky, výběr, drift) | podíl 43 % fáze | |
| – assess (hodnocení procesů) | podíl 27 % fáze | |
| – write (w/vocab, w/activate, w/release, záznamy) | podíl 30 % fáze | |
| innovation | 3 529 | 24,2 % |
| – sync (index zvukových změn) | ~1 340 (16 % hlavního vlákna) | |
| – rates (míry) | ~680 | |
| rebuild | 1 870 | 12,8 % |
| observe | 742 | 5,1 % |

Rozpis fází při 8 vláknech (běh pod zátěží, 10,4 s): transmission 55 % (assess 20 %, write 21 %,
blocks 14 %), rebuild 22 %, innovation 18 %, observe 5 %. **S vlákny se nejméně zrychluje sériový
zápis (`write`, `rebuild`)**, který drží právě tabulky z nálezů #1 a #5.

### valley-50, 4 000 let, hlavní funkce (inkluzivně, vzorky `sample`, hlavní vlákno 8 191 ms)

| funkce | ms | podíl |
|---|---|---|
| `phases::transmission::run` | 4 515 | 55 % |
| – `transmit_rows` | 2 323 | 28 % |
| – – `Pressures::fitness` | 1 280 | 16 % |
| – `assess::refresh` | 1 108 | 13,5 % |
| – `follow_vocabulary` (`units_of`, `enter_units`) | 468 | 5,7 % |
| `phases::innovation::run` | 2 168 | 26 % |
| – `SoundChange::prepare` → `sync_groups` → `SoundIndex::sync` | 1 339 | 16 % |
| – míry změn (`rate_sum`) | 683 | 8 % |
| `phases::rebuild::run` | 1 063 | 13 % |
| – `restructure_groups` → `queue_into` / `Bank::lookup` | 896 | 11 % |
| `phases::observe::run` (`categories`: editační vzdálenosti) | 446 | 5,4 % |

Vlastní čas (self) v celém běhu: `_platform_memmove` 445 (zejména `grow_results`),
`Pressures::fitness` 328, `settle_range` 320, malloc 280, `memcmp` 264, filtr v `Bank::results` 241,
`form_distance` 208, `queue_into` 208, `Pat::contains` 190, `mix_component` 186, řazení v `normalize_cell` 250.

### village-400, 400 let, 1 vlákno (ms z 12 451 při měření fází, 7 004 ms hlavního vlákna při vzorkování)

| funkce | podíl hlavního vlákna |
|---|---|
| `transmit_rows` | 78 % |
| – `settle_range` | 54 % (z toho `normalize_cell` řazení ≈ 20–25 % celého běhu) |
| – `Pressures::fitness` | 34 % |
| – `hear`/`mix_component` | 4,6 % |
| `innovation` | 11 % |
| `observe` (`linkage`, `categories`) | 5 % |
| `release` (`LivePools::release`) | 4,6 % |

## Škálování

### S délkou běhu (valley-50, 1 vlákno, 50 skupin)

| rok | součet fází (ms) | ms na krok | paměť (RSS) | tvary v bance | tabulky procesů | záznamů |
|---|---|---|---|---|---|---|
| 1 000 | 1 466 | 37 | 284 MB | 14 215 | 19 MB | 45 692 |
| 1 500 | 2 649 | 44 | 495 MB | – | – | 86 599 |
| 2 000 | 4 273 | 53 | 1,0 GB | 95 275 | 485 MB | 140 897 |
| 4 000 | 14 574 | 91 | 3,2 GB | 360 699 | **4,4 GB** | 429 997 |

Celkový čas roste jako **~t^1,9** (4× delší běh = 9,9× čas), paměť jako **~t^1,8** a tvary jako **~t^2,3**.
Ze zdvojení 2 000 → 4 000 vzrostla fáze `rebuild` 5,1×, `innovation` 3,1×, `transmission` 3,3×,
`observe` 3,3×. Příčiny: (a) banka tvarů, která se nikdy nezmenšuje, a hustě indexované tabulky (#1, #6),
(b) počet procesů a variant roste lineárně v čase a množství práce na slovo je úměrné jim (#5), (c) historie (#8)
s ~3 700 záznamy na tik na konci běhu oproti ~1 100 na začátku.

Řádky bloků přenosu: 12 453 (do 1000) → 31 351 (do 2000) → 88 750 (do 4000) součet přes tiky, tj. ~78 řádků
na tik na začátku vs ~555 na konci; proměnných ve světě přitom přibývá z 395 na 917.

### S velikostí světa (1 vlákno)

| scénář | skupin | rok | součet fází | tvary | RSS |
|---|---|---|---|---|---|
| valley-50 | 50 | 1 000 | 1,47 s | 14 215 | 284 MB |
| village-400 | 400 | 200 | 4,75 s | – | 704 MB |
| village-400 | 400 | 400 | 12,45 s | 9 309 | 997 MB |
| village-400 | 400 | 800 | 23,13 s | – | 1,86 GB |

Na krok vychází valley-50 37 ms (do 1000 let) a village-400 778 ms (12 451 ms / 16 kroků, do 400 let), tedy ~21× při 8× více
skupinách (věk světa je jiný, takže jde o hrubý řád): **roste to rychleji než lineárně s G**. Hlavní příčina je hustota přenosu (#2): čas `transmission/blocks`
je úměrný `řádky × G × kapacita`, přitom živé buňky tvoří u village-400 jen 4,3 % (u valley-50 36 %).
Stavba světa je O(G²) (#12): 0,15 s vs 1,1 s.
Podíl `transmission` v celku je u village-400 80 %, u valley-50 58–62 %.

Paměť village-400 do 800 let je 1,86 GB při pouhých 17 k morfémech; tabulky procesů tam ještě nejsou dominantní
(11 MB po 400 letech), roste hlavně hustota přenosu a historie (295 k záznamů do 800 let).

### Vlákna

Při 1 → 8 vláknech valley-50 do 1500 běží 3,39 → 1,73 s (1,96×); village-400 se na 8 vláknech zrychluje
zhruba 2,2× (dřívější měření v dokumentu 19: 10,25 → 4,6 s). Podstatná část času zůstává v sériových částech
(`write` 17–21 % a `rebuild` 12–22 %) a při delších během v rostoucích tabulkách (#1, #5).

## Doporučené pořadí oprav

1. **#3** (řazení jen nenulových): 10 řádků, ověřeno bit po bitu, −16 až −24 % času village-400.
2. **#1** (řídké tabulky procesů): odstraní 4,4 GB a velkou část paměťového tlaku při dlouhých bězích; čistě keš.
3. **#2** (řídký přenos): největší zisk pro velké světy (rádově desítky procent až násobky u village-400), vyžaduje
   přepis `transmit_rows` a `settle` na seznamy živých buněk; vynechání nulových buněk a slotů je přesné.
4. **#5, #4, #7** (fronty procesů, sady kandidátů, razítko skupiny): mění růst z kvadratického na přibližně lineární
   v délce běhu.
5. **#6, #8** (hypotetické tvary v bance, historie): odstraní růst paměti, ale #6a mění čísla tvarů a tedy otisky.

## Co se nenašlo / hranice auditu

- Řazení nebo `format!` v horkých cestách mimo uvedené (např. `History::event`, `stable_id`) tvoří dohromady
  jednotky procent.
- `observe::linkage` je řízené haldou nad sousedními shluky (O(E log E)), nikoli kvadratické; `categories`
  (editační vzdálenosti) je 3–5 % času a už se počítá souběžně.
- Nebylo měřeno `grid-5x5` do hloubky ani příklad `WorldSpec` (oba jsou menší než valley-50; profil po fázích
  se podobá valley-50) a kontrolní body v běhu (výchozí vypnuté).

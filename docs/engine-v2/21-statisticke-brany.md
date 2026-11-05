# 21. Statistické brány milníků

Stav: **zamčeno** (5. 11. 2026, schválil uživatel). Cílová pásma v `src/cee/data/v2_gate_targets.json`
platí jako brány milníků a nahradila staré jednorázové brány: `cee gates` i testy `tests/gates/`
(`statisticke_brany` v každém milníku) vyhodnocují všech 52 bran na N semínkách od 201 proti pásmům.
Starý audit s prahy z Pythonu zmizel. Změna pásma chce zdůvodnění ze zdroje a záznam v tomto dokumentu.
Engine ani parametry se kvůli branám nezměnily; 5. 11. 2026 se změnil scénář S1 (nepravidelná krajina)
a obě korelace se zeměpisem se měří s logaritmem vzdálenosti, viz níže.

## Proč

Prahy a počty semínek `k` starých bran vznikly podle toho, jak často jev nastával v tehdejším enginu,
ne podle reality. Když kalibrace model zrealističtí (člen vzniká jen v části jazyků), stará brána to
vyhodnotí jako zhoršení. Většina je navíc jednorázová (1 až 3 semínka), tedy křehká. Běhy jsou vzorek
z rozdělení, ne populace, a brána má dovolit rozumný rozptyl.

## Tři druhy bran

| druh | otázka | vyhodnocení | počet |
|---|---|---|---:|
| **invariant** | musí platit v každém běhu (psaný kód bez tisku stojí, bez kontaktu nejsou výpůjčky) | přesná podmínka na všech `N` semínkách (`N` = 3, u trojic 3 trojice) | 6 |
| **možnost jevu** | jev musí jít nastat (Jespersenův cyklus, vznik členu, exaptace) nebo je to obvyklý směr účinku | jev nastal na aspoň `k` z `N` semínek | 23 |
| **míra nebo pásmo** | jak často a jak moc (retence, délka slov, vzdálenost nářečí) | medián a 95% bootstrapový interval na `N` semínkách; brána projde, když se interval překrývá s cílovým pásmem, nebo když medián leží v širším pásmu | 23 |

Registr 52 bran se nemění; každá brána má právě jeden druh. Druh, `N`, `p_min`, pásma a zdroje jsou
data v `src/cee/data/v2_gate_targets.json` (pole `status: "návrh"`), vložená do binárky.

### Volba `N` a `k`

- **Možnost jevu.** Zvolí se `p_min`, nejnižší skutečná míra jevu, při které brána ještě nemá
  selhat. `k` je největší číslo, pro které `P(Bin(N, p_min) < k) <= 0,01` (pravidlo z dokumentu 09), ale
  aspoň 1: brána nikdy neprojde bez jediného výskytu jevu. Falešné selhání má tedy pravděpodobnost
  nejvýš 1 %. Příklady: člen `p_min` 0,1, `N` 50, `k` 1 (0,9^50 = 0,5 %); Jespersen a exaptace
  `p_min` 0,15, `N` 30, `k` 1; směr účinku `p_min` 0,8, `N` 20, `k` 12. Výpis uvádí i Wilsonův
  interval pozorovaného podílu. `p_min` je nejslabší místo návrhu: literatura míru jevu za
  3 000 let prakticky neuvádí, hodnoty jsou odhady z věrohodnosti.
- **Míra nebo pásmo.** `N` = 30 (míra se počítá z reportů starých bran, takže je každé semínko stejně
  levné, asi 10 s na všech 52 bran); u trojic semínek (M2) 12 trojic, u pomalých map 20. Interval je
  percentilový bootstrap mediánu (4 000 vzorků, deterministická náhoda podle jména brány a veličiny).
  Nepovažuji ho za přesný; u celých čísel a malého `N` bývá úzký.
- **Invariant.** Tři semínka (u trojic tři trojice); musí platit vše.

Veličiny berou hodnoty z `Report` starých bran (přepočet `hodnota × scale`), takže se nespouští nic
nového. Prahy starých bran se v nových nepoužívají, kromě případů, kde se starý práh shoduje
s přirozenou podmínkou (u „možnosti“ bez zvláštní podmínky platí „prošla stará brána“).

## Příkazy

```
cargo run --release --bin cee -- gates --list                           # druh, N a p_min 52 bran
cargo run --release --bin cee -- gates --seeds 201 -o values.jsonl      # všechno, asi 9 minut
cargo run --release --bin cee -- gates --only m4b,m6b::metrika_9        # výběr
cargo test --release --test gates -- --ignored --test-threads=1         # totéž jako testy, po milnících
```

`--seeds 201` je první semínko; vzorky používají `201, 202, …` (trojice po třech). Výpis má sloupce brána,
druh, veličina, N, medián (u možnosti podíl), interval, cílové pásmo, podpora, prošla. `-o` zapíše
hodnoty všech metrik po semínkách.

## Výsledek na dnešním enginu (semínka 201 a dál)

**52 z 52 bran prošlo** (po ověření zdrojů, opravě pásma `m2::zvukove_zmeny_se_siri` a úpravě S1; před nimi 50 z 52).

| brána | veličina | engine (medián, interval) | cílové pásmo | o kolik |
|---|---|---|---|---|
| `m1::s1_kontinuum` (do 5. 11.; po úpravě 0,837 [0,814; 0,856] a prošla) | korelace jazykové a zeměpisné vzdálenosti | 0,961 [0,956; 0,966] | [0,6; 0,9] | nad horní mezí o 0,056 |
| `m2::zvukove_zmeny_se_siri` (původní pásmo; po opravě [2; 20] a prošla) | medián počtu skupin na změnu | 14 [10,5; 18,5] | [2; 10] | interval celý nad pásmem |

Obě jsou informace, ne důvod ladit:

- Korelace 0,96 vznikla ze dvou věcí. Brána měřila korelaci s přímou vzdáleností, Heeringa a Nerbonne (2001)
  ale uvádějí asi 0,9 s logaritmem vzdálenosti. A scénář byl dokonalá řada 20 stejných vesnic se stejně
  silnými vazbami, takže jazyk mohl sledovat jen zeměpis. Samotné sjednocení měření nepomohlo (s logaritmem
  0,953 [0,927; 0,967] na 30 semínkách). Proto má S1 nepravidelnou krajinu (`Landscape::rural` ve
  `scenarios.rs`), hodnoty zvolené z věrohodnosti předem, ne laděním na bránu: posun vesnic až o 0,3 rozestupu
  v obou osách, populace log-normálně kolem 500 (σ = 0,7, oříznutí 100 až 3000), činitel terénu u každé vazby
  log-rovnoměrně 0,3 až 1,5 a dvě dálková spojení (aspoň 4 rozestupy, poloviční síla typické vazby). Výsledek:
  s logaritmem 0,837 [0,814; 0,856] (jednotlivá semínka 0,69 až 0,94), s přímou vzdáleností 0,747; brána prošla.
  Ostatní brány S1 (`m1::metrika_7`, `m1::metrika_8`) prošly i se šumem; `m1::s1_hranice` používá řadu bez
  šumu jako dřív. Stejně se teď měří i `m6b::metrika_9` (mapa 5 × 5): s logaritmem 0,809 [0,763; 0,830], dříve
  s přímou vzdáleností 0,778.
- Horní mez 10 pásma vznikla chybou převodu: metrika počítá události „ustálila se“ na proces, ne skupiny,
  takže přesáhne počet skupin (10). Opraveno na [2; 20] (`návrh`), brána prošla.

Dojem z „50 z 52“ je třeba číst s rezervou. Pásmo se širokým překryvem (CI s pásmem, nebo medián
v širším pásmu) je mírné; několik veličin leží těsně u meze (nejdelší průměrná délka slova 4,59 proti dolní
mezi 4,5; samohlásky 7,5 a 11 proti pásmu do 7 a do 10 projdou jen díky přesahu intervalu a širšímu
pásmu). Slabé brány ze starého auditu (exaptace, substrát S3, Jespersen, tabu, člen) prošly: exaptace 14/30
(47 %), Jespersen 11/30 (37 %), člen 5/50 (10 %), tabu 13/30 (43 %), protože se ptají, zda jev nastane
(`k` 1 až 2), ne jak často. Člen vznikl v 10 % běhů (Wilson [4 %; 21 %]), takže bodový odhad leží přesně na `p_min` 0,1 a brána prošla jen s malou rezervou (`k` = 1 z 50). Slovní stopa substrátu S3 (7 % slov
jazyka x proti pásmu 0 až 0,05) prošla jen díky širšímu pásmu do 0,08.

## Tabulka 52 bran

Podpora: **literatura** = číslo nebo rozsah nalezen v citovaném zdroji; **návrh** = literatura číslo nedává
nebo ho nešlo ověřit, pásmo je z věrohodnosti. Ověření zdroje: ověřeno, opraveno, nahrazeno, neověřitelné
(viz oddíl Ověření zdrojů). Úplné citace, převody na metriku
a vypuštěná tvrzení jsou v poli `source`, `conversion` a `note` souboru cílů.

| brána | druh | N | metrika a cílové pásmo (nebo `p_min`) | podpora | ověření zdroje | výsledek | poznámka |
|---|---|---:|---|---|---|---|---|
| `m1::metrika_7` | pásmo | 30 | medián R² logistické křivky ustálených změn 0.9–1.0 | návrh | neověřitelné | prošla | Vypuštěno „více než 50 drah“ (velikost vzorku, ne vlastnost jazyka). |
| `m1::metrika_8` | pásmo | 30 | podíl inovací, které se ustálí 0.01–0.2 | návrh | – | prošla |  |
| `m1::s1_hranice` | možnost | 20 | p_min 0.8 | návrh | – | prošla | Jev: vzdálenost přes hranici je větší než kterýkoli jiný skok mezi sousedy (stará brána chtěla dvojnásobek). |
| `m1::s1_kontinuum` | pásmo | 30 | korelace jazykové vzdálenosti a logaritmu zeměpisné 0.6–0.9; největší skok mezi sousedy / medián sousedů 1.0–4.0 | literatura/návrh | opraveno | prošla | Vypuštěna tvrzení „krajní vesnice dál než sousedé“ a „víc než jedno nářečí“ (platí triviálně). |
| `m1::velka_skupina_drift` | invariant | 3 | každý běh | literatura | ověřeno | prošla | Matematická vlastnost modelu, ne měření jazyka. |
| `m2::metrika_3` | pásmo | 30 | nejkratší průměrná délka slova (skupiny) 3.5–5.5; nejdelší průměrná délka slova (skupiny) 4.5–7.0 | návrh | neověřitelné | prošla |  |
| `m2::metrika_4` | pásmo | 30 | nejmenší inventář souhlásek 15.0–25.0; největší inventář souhlásek 19.0–33.0; nejmenší inventář samohlásek 4.0–7.0; největší inventář samohlásek 5.0–10.0 | literatura | opraveno/ověřeno | prošla |  |
| `m2::metrika_5` | pásmo | 30 | nejvyšší podíl homofonních slov 0.0–0.05 | návrh | – | prošla |  |
| `m2::metrika_6` | pásmo | 12 | ustálených zvukových změn na jazyk za 3 000 let 10.0–40.0; podíl souhláskových změn 0.25–0.75 | literatura/návrh | ověřeno | prošla | Dávka bere trojice semínek, N je počet trojic. |
| `m2::ruznost_seedu` | invariant | 3 | každý běh | návrh | – | prošla | Dávka bere trojice semínek, N je počet trojic. |
| `m2::zvukove_zmeny_se_siri` | pásmo | 30 | medián počtu skupin na změnu 2.0–20.0; podíl reliktů mezi zasaženými slovy 0.01–0.15 | návrh | opraveno | prošla |  |
| `m3::analogie` | pásmo | 30 | frekvence slov s analogií / průměr slovní zásoby 0.3–0.95 | návrh | – | prošla |  |
| `m3::morfologizace` | možnost | 20 | p_min 0.3 | návrh | nahrazeno | prošla |  |
| `m3::produktivni_vzor` | pásmo | 30 | podíl produktivní koncovky (nejnižší přes běh) 0.8–1.0; nepravidelnost častých − vzácných slov 0.02–1.0 | návrh/literatura | opraveno/ověřeno | prošla |  |
| `m3::sturtevantuv_paradox` | možnost | 20 | p_min 0.8 | návrh | – | prošla |  |
| `m3::zvukove_metriky` | pásmo | 30 | nejkratší průměrná délka slova 3.5–5.5; nejdelší průměrná délka slova 4.5–7.0; nejvyšší homofonie 0.0–0.05 | návrh | neověřitelné | prošla | Zdvojuje m2::metrika_3 a metrika_5 s paradigmaty; kandidát na sloučení. |
| `m3b::erodovana_slova` | možnost | 20 | p_min 0.8 | návrh | – | prošla | Jev: zkrácená slova se nahrazují častěji než ostatní (stará brána chtěla dvojnásobek). |
| `m3b::metrika_1` | pásmo | 30 | retence základní slovní zásoby za tisíciletí 0.8–0.87 | literatura | opraveno | prošla |  |
| `m3b::metrika_2` | pásmo | 30 | podíl nahrazených častých / vzácných pojmů 0.3–0.9 | návrh | opraveno | prošla |  |
| `m3b::nova_slova` | pásmo | 30 | podíl motivovaných původů nových slov 0.6–1.0; podíl slov vymyšlených od nuly 0.0–0.1 | návrh | – | prošla | Invariantní část (každé nové slovo má doložitelný původ) platí v každém běhu. |
| `m3b::tabu` | možnost | 30 | p_min 0.25 | návrh | opraveno | prošla |  |
| `m3b::zvukove_metriky` | pásmo | 30 | nejkratší průměrná délka slova 3.5–5.5; nejdelší průměrná délka slova 4.5–7.0; nejvyšší homofonie 0.0–0.05 | návrh | neověřitelné | prošla | Zdvojuje m2::metrika_3 a metrika_5 s lexikální změnou; kandidát na sloučení. |
| `m4::analytizace` | pásmo | 30 | podíl skupin s pevným slovosledem po ztrátě pádu 0.5–1.0; podíl skupin s volným slovosledem v kontrole 0.5–1.0 | návrh | opraveno | prošla |  |
| `m4::bez_eroze` | pásmo | 30 | podíl skupin se syntetickým minulým časem 0.5–1.0; podíl skupin se záporkou před slovesem 0.5–1.0 | návrh | – | prošla | Zvukové metriky v této bráně zdvojují m2::metrika_3 a metrika_5; kandidát na sloučení. |
| `m4::jespersen` | možnost | 30 | p_min 0.15 | návrh | ověřeno | prošla | Stará brána chtěla navíc aspoň 4 z 6 skupin s koncovou záporkou; to je míra šíření, ne možnost. |
| `m4::velky_cyklus` | možnost | 20 | p_min 0.3 | návrh | ověřeno | prošla | Jev: opis srostl v koncovku aspoň ve dvou skupinách; zdroj musí být z katalogu v každém případě. |
| `m4b::bez_padu` | pásmo | 30 | podíl skupin s pevným slovosledem bez pádu 0.5–1.0 | návrh | opraveno | prošla | Zdvojuje m4::analytizace; kandidát na sloučení. |
| `m4b::clen_vznikne` | možnost | 50 | p_min 0.1 | literatura | ověřeno | prošla | Člen smí vznikat jen v části jazyků; invariant: zdroj členu je v katalogu. |
| `m4b::exaptace` | možnost | 30 | p_min 0.15 | návrh | opraveno | prošla | Jev: exaptace aspoň ve dvou skupinách; invarianty (jen DEFINITE z OBJ, kontrola bez exaptace) musí platit tam, kde jev nastal. |
| `m4b::jazyk_bez_kategorie` | invariant | 3 | každý běh | návrh | – | prošla | Vypuštěno „nejvýš jedna skupina s nulovým minulým časem po vývoji“ (míra vývoje, kryje ji m4b::clen_vznikne) a podmíněné tvrzení o buňce PAST po gramatikalizaci (metrika není v každém běhu). |
| `m5::bez_dvojjazycnosti` | invariant | 3 | každý běh | návrh | ověřeno | prošla |  |
| `m5::metrika_11` | možnost | 20 | p_min 0.8 | návrh | neověřitelné | prošla |  |
| `m5::s2_l2` | možnost | 20 | p_min 0.8 | návrh | ověřeno | prošla |  |
| `m5::s2_mesto` | možnost | 20 | p_min 0.8 | návrh | ověřeno | prošla |  |
| `m5::s3_prechod` | invariant | 3 | každý běh | návrh | – | prošla |  |
| `m5::s3_substrat` | pásmo | 30 | x0>y: podíl slov jazyka x 0.0–0.05; x1>y: podíl slov jazyka x 0.0–0.05; stavba substrátu (menší z x0>y a x1>y) 0.2–1.0 | návrh | neověřitelné | prošla | Stará brána je slabá; většina jejích tvrzení (slovní stopa, zapsané změny) byla měřítka jednoho semínka. |
| `m5::vypujcky` | pásmo | 30 | a2: podíl výpůjček ve slovní zásobě 0.05–0.25; b0: podíl výpůjček ve slovní zásobě 0.05–0.25 | literatura | opraveno | prošla | Invariant: výpůjčka obsahuje jen hlásky inventáře příjemce. |
| `m6a::psany_kod_stoji` | invariant | 3 | každý běh | návrh | ověřeno | prošla |  |
| `m6a::s4_bez_skoly` | možnost | 20 | p_min 0.8 | návrh | ověřeno | prošla |  |
| `m6a::s4_skola` | možnost | 20 | p_min 0.8 | návrh | ověřeno | prošla |  |
| `m6a::skola_sjednoti` | možnost | 20 | p_min 0.8 | návrh | opraveno | prošla |  |
| `m6a::skola_zmrazena` | možnost | 20 | p_min 0.8 | návrh | – | prošla |  |
| `m6b::elita_prejde` | pásmo | 20 | doba do přechodu elity (roky) 100.0–400.0 | návrh | neověřitelné | prošla |  |
| `m6b::ferguson` | možnost | 20 | p_min 0.8 | literatura | ověřeno | prošla |  |
| `m6b::jazyk_trhu` | možnost | 20 | p_min 0.8 | návrh | neověřitelné | prošla |  |
| `m6b::loajalita` | možnost | 20 | p_min 0.8 | návrh | ověřeno | prošla |  |
| `m6b::metrika_9` | pásmo | 20 | korelace jazykové vzdálenosti a logaritmu zeměpisné (2D) 0.5–0.9; R² logaritmického − R² lineárního proložení 0.0–0.3 | literatura | opraveno | prošla |  |
| `m6b::migrace` | možnost | 20 | p_min 0.7 | návrh | ověřeno | prošla |  |
| `m6b::nabozenstvi` | možnost | 20 | p_min 0.8 | návrh | neověřitelné | prošla |  |
| `m6b::superstrat` | pásmo | 20 | l0: stavba elity 0.0–0.1; l3: stavba elity 0.0–0.1 | návrh | opraveno | prošla | Vypuštěno „aspoň 2 slova z jazyka dobyvatelů“ (velikost vzorku slovníku). |
| `m6c::strom_odpovida` | možnost | 20 | p_min 0.85 | návrh | – | prošla |  |
| `m6c::strom_stabilni` | možnost | 20 | p_min 0.85 | návrh | – | prošla |  |

## Pásma s oporou v literatuře a bez ní

- **Bez opory (14 bran, pásmo nebo `p_min` z věrohodnosti):** `m1::s1_hranice`, `m1::metrika_8`,
  `m2::metrika_5`, `m2::ruznost_seedu`, `m3::sturtevantuv_paradox`, `m3::analogie`, `m3b::nova_slova`,
  `m3b::erodovana_slova`, `m4::bez_eroze`, `m4b::jazyk_bez_kategorie`, `m5::s3_prechod`,
  `m6a::skola_zmrazena`, `m6c::strom_odpovida`, `m6c::strom_stabilni`. U bran druhu „možnost“ literatura
  dokládá nejvýš **směr** účinku; `p_min` je vždy návrh. Neznámá je četnost vzniku členu, exaptace,
  Jespersenova cyklu a tabu za 3 000 let.
- Po ověření mají číslo ze zdroje jen WALS kap. 1, 2 a 37, Lieberman et al. (2007), Swadesh, Lees a Bergsland
  a Vogt (retence), Heeringa a Nerbonne (2001), Ringe (počet změn přes recenzi) a WOLD (průměr přes sekundární
  citaci). Ostatní pásma (délka slova, doba přechodu elity, podíl nahrazených častých a vzácných pojmů, slovosled
  a pád, slovní stopa substrátu) jsou z věrohodnosti.
- Zvukové změny za 3 000 let (`m2::metrika_6`, 10 až 40 na jazyk): dnešní engine dává asi 25 na jazyk; horní mez
  40 odpovídá Ringemu (2006).

## Ověření zdrojů (listopad 2026)

Každý zdroj a číslo, které byly dříve označeny `literatura*` (a čtyři dříve potvrzené jen rychle), jsem
zkontroloval webem: CrossRef (bibliografické údaje a DOI), stránky WALS Online a WOLD, abstrakty a přehledové
články. Texty jsem nekopíroval. U většiny knih a starších článků jsem ověřil existenci, vydání a téma, ne
konkrétní stránku; to je v poli `source` řečeno. Stav má pole `verification` v souboru cílů:

- **ověřeno**: zdroj existuje a číslo nebo tvrzení sedí (nebo jde o směr účinku, kde p_min zůstává návrh);
- **opraveno**: zdroj existuje, číslo, jednotky nebo citace byly špatně; opraveno, případně upraveno pásmo;
- **nahrazeno**: zdroj nahrazen lepším;
- **neověřitelné**: zdroj nebo číslo nešlo dohledat; pásmo přesunuto do `support: "návrh"` (věrohodnost).

Počty (položka = jedna veličina brány „pásmo“ nebo jedna brána druhu „možnost“ a „invariant“, celkem 49):
**ověřeno 17, opraveno 18, nahrazeno 1, neověřitelné 13.** Žádná položka nezůstala označená `literatura*`.
`support: "literatura"` zůstává jen tam, kde jsem číslo nebo rozsah našel ve zdroji (WALS, Lieberman et al.,
Swadesh a Lees, Heeringa a Nerbonne, Maddieson, Ringe přes recenzi, WOLD přes sekundární citaci, Ferguson).

### Nejdůležitější opravy

- **`m2::zvukove_zmeny_se_siri`** (chyba jednotek): metrika počítá události „ustálila se“ na proces, ne skupiny;
  může přesáhnout 10 (pozorováno 14). Pásmo [2; 10] byl převod předchozího agenta, literatura číslo nedává
  (areálové šíření je jen kvalitativní poznatek). Nové pásmo [2; 20], široké [2; 30], `support: "návrh"`;
  dolní mez 2 (změna zasáhne víc skupin) zůstává, horní je jen strop věrohodnosti.
- **Korelace jazykové a zeměpisné vzdálenosti** (`m1::s1_kontinuum`, `m6b::metrika_9`): Heeringa a Nerbonne jsou
  z roku 2001, ne 2002. Mají 27 nizozemských obcí, zeměpis vysvětluje 65 až 81 % rozptylu a korelace s logaritmem
  vzdálenosti je asi 0,9. Rozsah „0,6 až 0,8“ jsem v Nerbonne (2010) nenašel. Pásma [0,6; 0,9] a [0,5; 0,9]
  zůstala, horní mez má oporu, dolní je z věrohodnosti. Obě brány od 5. 11. 2026 měří korelaci s logaritmem
  vzdálenosti jako zdroj (dříve s přímou vzdáleností, což se se zdrojem nedalo srovnat).
- **Retence slovní zásoby** (`m3b::metrika_1`): Swadesh (1955) 86 % pro seznam 100, Lees (1953) 0,8048 pro seznam
  200; Bergsland a Vogt (1962): islandština asi 4 % ztráty za tisíciletí, tj. retence 0,96. Široké pásmo
  rozšířeno shora z 0,95 na 0,97.
- **Maddieson (WALS kap. 1)**: 563 jazyků, třídy 6–14 / 15–18 / 19–25 / 26–33 / 34 a více, průměr 22,7, medián 21,
  rozsah 6 až 122. Samohlásky (kap. 2) sedí přesně (2–4, 5–6, 7–14; 564 jazyků).
- **Délka slova** (ASJP): Wichmann (2023) uvádí jen rozsah 1,93 až 7,73 segmentu; průměr ani kvantily ne.
  Pásma 3,5–5,5 a 4,5–7,0 přesunuta do věrohodnosti (`neověřitelné`), původní Wichmann et al. (2013) nahrazen.
- **Počet zvukových změn** (`m2::metrika_6`): Ringe (2006) podle recenze „some forty regular sound changes“;
  horní mez 40 sedí. Pope (1934) „řádově víc“ nepotvrzen, odstraněn.
- **WOLD**: 41 jazyků, průměr asi 24,2 % celé slovní zásoby (sekundární citace); tvrzení „1 až 70 %“ nepotvrzeno,
  předběžné údaje mají 1 až 60 %. Procento se týká celé slovní zásoby, ne základního seznamu 149 slov.
- **Doba přechodu normanské elity**: Short (2007) nenalezen; Ingham (2012) tvrdí, že anglonormanština byla
  v pozdní době učený druhý jazyk. Údaje o Francích, Langobardech a Prabulharech nepotvrzeny. Pásmo [100; 400]
  je z věrohodnosti.
- **Slovosled a pád** (`m4::analytizace`, `m4b::bez_padu`): typologická souvislost je doložena, ale historická
  souvislost ztráty pádů a pevného slovosledu je v literatuře zpochybněna (Detges 2009, Pintzuk 2002 podle
  Fedzechkina et al. 2017). Pásmo je tendence z věrohodnosti.
- **Citace**: Milroy a Milroy (1985) pro standardizaci je kniha *Authority in Language*, ne článek o šíření
  inovací; Norde (2001) pojednává o deflexi, ne o exaptaci; Meillet (1906) a Hyman (1975) nepotvrzeny.

### Zdroje

Ověřené citace (odkazy jsou DOI nebo stránky, kde jsem zdroj kontroloval):

- Allan, K., Burridge, K. (2006). *Forbidden Words: Taboo and the Censoring of Language*. Cambridge University Press. https://doi.org/10.1017/CBO9780511617881
- Baugh, A. C. (1951). *A History of the English Language*, 2. vyd., s. 215 (údaj „přes 10 000 francouzských slov“ podle LINGUIST List; vydání s Cablem nezkoumáno).
- Bentz, C., Winter, B. (2013). Languages with more second language learners tend to lose nominal case. *Language Dynamics and Change* 3(1), 1–27. https://doi.org/10.1163/22105832-13030105
- Bergsland, K., Vogt, H. (1962). On the validity of glottochronology. *Current Anthropology* 3, 115–153. https://doi.org/10.1086/200264
- Blythe, R. A., Croft, W. (2012). S-curves and the mechanisms of propagation in language change. *Language* 88(2), 269–304. https://doi.org/10.1353/lan.2012.0027
- Chambers, J. K., Trudgill, P. (1998). *Dialectology*, 2. vyd. Cambridge University Press.
- Croft, W. (2000). *Explaining Language Change: An Evolutionary Approach*. Longman.
- Dahl, Ö. (1979). Typology of sentence negation. *Linguistics* 17, 79–106. https://doi.org/10.1515/ling.1979.17.1-2.79
- Dautriche, I., Fibla, L., Fievet, A.-C., Christophe, A. (2018). Learning homophones in context: Easy cases are favored in the lexicon of natural languages. *Cognitive Psychology* 104, 83–105.
- Dryer, M. S. (2013). Definite Articles. In Dryer, Haspelmath (eds.), *WALS Online*, kap. 37. https://wals.info/chapter/37
- Ferguson, C. A. (1959). Diglossia. *Word* 15(2), 325–340. https://doi.org/10.1080/00437956.1959.11659702
- Fedzechkina, M., Newport, E. L., Jaeger, T. F. (2017). Balancing effort and information transmission during language acquisition: Evidence from word order and case marking. *Cognitive Science* 41, 416–446. https://doi.org/10.1111/cogs.12346
- Fishman, J. A. (1991). *Reversing Language Shift*. Multilingual Matters. https://doi.org/10.21832/9781800418097
- Gal, S. (1979). *Language Shift: Social Determinants of Linguistic Change in Bilingual Austria*. Academic Press.
- Givón, T. (1971). Historical syntax and synchronic morphology: an archaeologist’s field trip. *Chicago Linguistic Society* 7 (přetisk: https://doi.org/10.1075/z.192.c1).
- Haspelmath, M., Tadmor, U. (eds., 2009). *Loanwords in the World’s Languages*. De Gruyter Mouton. https://doi.org/10.1515/9783110218442; World Loanword Database, https://wold.clld.org
- Haugen, E. (1966). Dialect, language, nation. *American Anthropologist* 68, 922–935. https://doi.org/10.1525/aa.1966.68.4.02a00040
- Heeringa, W., Nerbonne, J. (2001). Dialect areas and dialect continua. *Language Variation and Change* 13(3), 375–400. https://doi.org/10.1017/S0954394501133041
- Heine, B., Kuteva, T. (2006). *The Changing Languages of Europe*. Oxford University Press. https://doi.org/10.1093/acprof:oso/9780199297337.001.0001
- Hopper, P. J., Traugott, E. C. (2003). *Grammaticalization*, 2. vyd. Cambridge University Press.
- Ingham, R. (2012). *The Transmission of Anglo-Norman*. John Benjamins. https://www.benjamins.com/catalog/lfab.9
- Kimura, M. (1964). Diffusion models in population genetics. *Journal of Applied Probability* 1, 177–232. https://doi.org/10.2307/3211856
- Kroch, A. S. (1989). Reflexes of grammar in patterns of language change. *Language Variation and Change* 1, 199–244. https://doi.org/10.1017/S0954394500000168
- Labov, W. (1994). *Principles of Linguistic Change, Volume 1: Internal Factors*. Blackwell.
- Lass, R. (1990). How to do things with junk: exaptation in language evolution. *Journal of Linguistics* 26, 79–102. https://doi.org/10.1017/S0022226700014432
- Lees, R. B. (1953). The basis of glottochronology. *Language* 29, 113–127. https://doi.org/10.2307/410164
- Lieberman, E., Michel, J.-B., Jackson, J., Tang, T., Nowak, M. A. (2007). Quantifying the evolutionary dynamics of language. *Nature* 449, 713–716. https://doi.org/10.1038/nature06137
- Lupyan, G., Dale, R. (2010). Language structure is partly determined by social structure. *PLoS ONE* 5(1), e8559. https://doi.org/10.1371/journal.pone.0008559
- Maddieson, I. (2013). Consonant Inventories (kap. 1) a Vowel Quality Inventories (kap. 2). *WALS Online*. https://wals.info/chapter/1, https://wals.info/chapter/2
- Milroy, J., Milroy, L. (1985). *Authority in Language: Investigating Standard English*. Routledge. https://doi.org/10.4324/9780203267424; týž (1985). Linguistic change, social network and speaker innovation. *Journal of Linguistics* 21, 339–384. https://doi.org/10.1017/S0022226700010306
- Nerbonne, J. (2010). Measuring the diffusion of linguistic change. *Philosophical Transactions of the Royal Society B* 365, 3821–3828. https://doi.org/10.1098/rstb.2010.0048
- Pagel, M., Atkinson, Q. D., Meade, A. (2007). Frequency of word-use predicts rates of lexical evolution throughout Indo-European history. *Nature* 449, 717–720. https://doi.org/10.1038/nature06176
- Pinker, S. (1999). *Words and Rules: The Ingredients of Language*. Basic Books.
- Ringe, D. (2006). *From Proto-Indo-European to Proto-Germanic* (A Linguistic History of English 1). Oxford University Press; počet změn podle recenze https://linguistlist.org/issues/20/2558/
- Sorensen, A. P. (1967). Multilingualism in the Northwest Amazon. *American Anthropologist* 69, 670–684. https://doi.org/10.1525/aa.1967.69.6.02a00030
- Swadesh, M. (1955). Towards greater accuracy in lexicostatistic dating. *International Journal of American Linguistics* 21, 121–137. https://doi.org/10.1086/464321
- Thomason, S. G., Kaufman, T. (1988). *Language Contact, Creolization, and Genetic Linguistics*. University of California Press. https://doi.org/10.1525/9780520912793
- Trudgill, P. (2011). *Sociolinguistic Typology: Social Determinants of Linguistic Complexity*. Oxford University Press.
- Wang, W. S.-Y. (1969). Competing changes as a cause of residue. *Language* 45, 9–25. https://doi.org/10.2307/411748
- Wichmann, S. (2023). Tone and word length across languages. *Frontiers in Psychology* 14, 1128461. https://doi.org/10.3389/fpsyg.2023.1128461
- Willis, D., Lucas, C., Breitbarth, A. (eds., 2013). *The History of Negation in the Languages of Europe and the Mediterranean*. Oxford University Press. https://doi.org/10.1093/acprof:oso/9780199602537.001.0001

Nenalezeno nebo nepotvrzeno (v souboru cílů označeno): Hyman (1975), Meillet (1906), Pope (1934), Short (2007),
Gumperz a Wilson (1971), Séguy (1971, původní článek; cituji podle Nerbonne 2010), Siewierska (1998),
Dryer (WALS kap. 81–87), Jespersen (1917), Kümmel (2007), Sapir (1921), Sturtevant (1947, existence jen z recenze),
čísla o galských slovech ve francouzštině a o korelacích Lupyan–Dale (|r| 0,1 až 0,3).

## Brány ke sloučení nebo zrušení

Při zamčení (5. 11. 2026) se nic nesloučilo ani nezrušilo; registr má dál 52 bran. Body níže jsou
otevřený návrh.

- `m3::zvukove_metriky`, `m3b::zvukove_metriky` a zvukové metriky v `m4::bez_eroze` zdvojují
  `m2::metrika_3` a `m2::metrika_5` (délka slova, homofonie) s přidanou vrstvou. Navrhuji jednu bránu
  „zvukové metriky“ vyhodnocenou v každé dávce jako vedlejší kontrola, ne tři brány.
- `m4b::bez_padu` zdvojuje `m4::analytizace` (pevný slovosled bez pádu). Sloučit.
- `m4::bez_eroze` a `m4b::bez_padu`: stabilita bez zásahu je kontrola scénáře, ne tvrzení o jazyce; po
  sloučení stačí jedna kontrola bez eroze.
- `m3b::erodovana_slova`, `m1::s1_hranice`, `m3::sturtevantuv_paradox`, `m6a::skola_zmrazena`: pokusy
  s vloženým zásahem bez literární míry; ponechat jako „možnost“ se `k`, nebo zrušit, pokud uživatel
  nepotřebuje potvrzení, že mechanismus funguje.
- `m6c::strom_odpovida` a `m6c::strom_stabilni` měří týž jev (strom odpovídá vloženému rozpadu); sloučit.
- `m5::s3_prechod`, `m5::bez_dvojjazycnosti`, `m6a::psany_kod_stoji`, `m4b::jazyk_bez_kategorie`,
  `m1::velka_skupina_drift`: invarianty, které platí z konstrukce scénáře (jednotkové testy by stačily).
  Ponechány, protože jsou levné.
- `m3b::tabu` má negativní kontrolu „bez tabu žádná náhrada“, která stejně jako dříve míchá
  dva jevy (drift může slovo nahradit); její přepsání na rozdíl četností je možné vylepšení.

## Co nešlo

- Texty knih a řady starších článků jsem nečetl, ověřena je bibliografie a téma (viz Zdroje); Pope, Short,
  Hyman, Meillet, Gumperz a Wilson, Siewierska a další zůstaly nepotvrzeny.
- Stará brána není pouze stochastická: u `m2::metrika_6` a `m2::ruznost_seedu` je vzorek trojice semínek,
  takže `N` = 12 trojic znamená 36 běhů.
- Od zamčení jsou brány v `cargo test` (test `statisticke_brany` v každém milníku, `#[ignore]` kvůli délce);
  `cee gates` skončí chybou, když některá veličina neprojde.

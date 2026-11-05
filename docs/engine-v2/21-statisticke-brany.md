# 21. Statistické brány milníků

Stav: **návrh**. Cílová pásma čekají na kontrolu uživatelem; do té doby jsou staré brány
(`tests/gates/`, `cee gates`) beze změny vedle nových. Engine ani parametry se nezměnily.

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
cargo run --release --bin cee -- gates --report --list                  # druh, N a p_min 52 bran
cargo run --release --bin cee -- gates --report --seeds 201 -o values.jsonl   # všechno, asi 9 minut
cargo run --release --bin cee -- gates --report --only m4b,m6b::metrika_9     # výběr
```

`--seeds 201` je první semínko; vzorky používají `201, 202, …` (trojice po třech). Výpis má sloupce brána,
druh, veličina, N, medián (u možnosti podíl), interval, cílové pásmo, podpora, prošla. `-o` zapíše
hodnoty všech metrik po semínkách.

## Výsledek na dnešním enginu (semínka 201 a dál)

**50 z 52 bran prošlo, 2 neprošly.**

| brána | veličina | engine (medián, interval) | cílové pásmo | o kolik |
|---|---|---|---|---|
| `m1::s1_kontinuum` | korelace jazykové a zeměpisné vzdálenosti | 0,961 [0,956; 0,966] | [0,6; 0,9] | nad horní mezí o 0,056 |
| `m2::zvukove_zmeny_se_siri` | medián počtu skupin na změnu | 14 [10,5; 18,5] | [2; 10] | interval celý nad pásmem |

Obě jsou informace, ne důvod ladit:

- Korelace 0,96 je u přímé řady 20 vesnic bez šumu ideální; reálná nářečí mají 0,6 až 0,8. Pásmo je
  z paměti (literatura\*) a platí pro dvojrozměrná data; u jednorozměrného řetězce může být přísné.
- Horní mez 10 pásma vznikla chybou převodu: metrika počítá události „ustálila se“ na proces, ne skupiny,
  takže přesáhne počet skupin (10). Pásmo je třeba opravit v jednotkách, než se zamkne.

Dojem z „50 z 52“ je třeba číst s rezervou. Pásmo se širokým překryvem (CI s pásmem, nebo medián
v širším pásmu) je mírné; několik veličin leží těsně u meze (nejdelší průměrná délka slova 4,59 proti dolní
mezi 4,5; samohlásky 7,5 a 11 proti pásmu do 7 a do 10 projdou jen díky přesahu intervalu a širšímu
pásmu). Slabé brány ze starého auditu (exaptace, substrát S3, Jespersen, tabu, člen) prošly: exaptace 14/30
(47 %), Jespersen 11/30 (37 %), člen 5/50 (10 %), tabu 13/30 (43 %), protože se ptají, zda jev nastane
(`k` 1 až 2), ne jak často. Člen vznikl v 10 % běhů (Wilson [4 %; 21 %]), takže bodový odhad leží přesně na `p_min` 0,1 a brána prošla jen s malou rezervou (`k` = 1 z 50). Slovní stopa substrátu S3 (7 % slov
jazyka x proti pásmu 0 až 0,05) prošla jen díky širšímu pásmu do 0,08.

## Tabulka 52 bran

Podpora: **literatura** = zdroj a číslo ověřené při psaní (WALS kap. 37 se 620 jazyky, Lieberman et al. 2007,
Séguyova křivka, Swadesh a Lees); **literatura\*** = zdroj z paměti, před zamčením
ověřit v originále; **návrh** = literatura nic nedává, pásmo je z věrohodnosti. Úplné citace, převody na metriku
a vypuštěná tvrzení jsou v poli `source`, `conversion` a `note` souboru cílů.

| brána | druh | N | metrika a cílové pásmo (nebo `p_min`) | podpora | výsledek | poznámka |
|---|---|---:|---|---|---|---|
| `m1::metrika_7` | pásmo | 30 | medián R² logistické křivky ustálených změn 0.9–1.0 | literatura* | prošla | Vypuštěno „více než 50 drah“ (velikost vzorku, ne vlastnost jazyka). |
| `m1::metrika_8` | pásmo | 30 | podíl inovací, které se ustálí 0.01–0.2 | návrh | prošla |  |
| `m1::s1_hranice` | možnost | 20 | p_min 0.8 | návrh | prošla | Jev: vzdálenost přes hranici je větší než kterýkoli jiný skok mezi sousedy (stará brána chtěla dvojnásobek). |
| `m1::s1_kontinuum` | pásmo | 30 | korelace jazykové a zeměpisné vzdálenosti 0.6–0.9; největší skok mezi sousedy / medián sousedů 1.0–4.0 | literatura*/návrh | neprošla | Vypuštěna tvrzení „krajní vesnice dál než sousedé“ a „víc než jedno nářečí“ (platí triviálně). |
| `m1::velka_skupina_drift` | invariant | 3 | každý běh | literatura | prošla | Matematická vlastnost modelu, ne měření jazyka. |
| `m2::metrika_3` | pásmo | 30 | nejkratší průměrná délka slova (skupiny) 3.5–5.5; nejdelší průměrná délka slova (skupiny) 4.5–7.0 | literatura* | prošla |  |
| `m2::metrika_4` | pásmo | 30 | nejmenší inventář souhlásek 15.0–25.0; největší inventář souhlásek 19.0–33.0; nejmenší inventář samohlásek 4.0–7.0; největší inventář samohlásek 5.0–10.0 | literatura* | prošla |  |
| `m2::metrika_5` | pásmo | 30 | nejvyšší podíl homofonních slov 0.0–0.05 | návrh | prošla |  |
| `m2::metrika_6` | pásmo | 12 | ustálených zvukových změn na jazyk za 3 000 let 10.0–40.0; podíl souhláskových změn 0.25–0.75 | literatura*/návrh | prošla | Dávka bere trojice semínek, N je počet trojic. |
| `m2::ruznost_seedu` | invariant | 3 | každý běh | návrh | prošla | Dávka bere trojice semínek, N je počet trojic. |
| `m2::zvukove_zmeny_se_siri` | pásmo | 30 | medián počtu skupin na změnu 2.0–10.0; podíl reliktů mezi zasaženými slovy 0.01–0.15 | literatura*/návrh | neprošla |  |
| `m3::analogie` | pásmo | 30 | frekvence slov s analogií / průměr slovní zásoby 0.3–0.95 | návrh | prošla |  |
| `m3::morfologizace` | možnost | 20 | p_min 0.3 | literatura* | prošla |  |
| `m3::produktivni_vzor` | pásmo | 30 | podíl produktivní koncovky (nejnižší přes běh) 0.8–1.0; nepravidelnost častých − vzácných slov 0.02–1.0 | literatura/literatura* | prošla |  |
| `m3::sturtevantuv_paradox` | možnost | 20 | p_min 0.8 | návrh | prošla |  |
| `m3::zvukove_metriky` | pásmo | 30 | nejkratší průměrná délka slova 3.5–5.5; nejdelší průměrná délka slova 4.5–7.0; nejvyšší homofonie 0.0–0.05 | literatura*/návrh | prošla | Zdvojuje m2::metrika_3 a metrika_5 s paradigmaty; kandidát na sloučení. |
| `m3b::erodovana_slova` | možnost | 20 | p_min 0.8 | návrh | prošla | Jev: zkrácená slova se nahrazují častěji než ostatní (stará brána chtěla dvojnásobek). |
| `m3b::metrika_1` | pásmo | 30 | retence základní slovní zásoby za tisíciletí 0.8–0.87 | literatura | prošla |  |
| `m3b::metrika_2` | pásmo | 30 | podíl nahrazených častých / vzácných pojmů 0.3–0.9 | literatura* | prošla |  |
| `m3b::nova_slova` | pásmo | 30 | podíl motivovaných původů nových slov 0.6–1.0; podíl slov vymyšlených od nuly 0.0–0.1 | návrh | prošla | Invariantní část (každé nové slovo má doložitelný původ) platí v každém běhu. |
| `m3b::tabu` | možnost | 30 | p_min 0.25 | literatura* | prošla |  |
| `m3b::zvukove_metriky` | pásmo | 30 | nejkratší průměrná délka slova 3.5–5.5; nejdelší průměrná délka slova 4.5–7.0; nejvyšší homofonie 0.0–0.05 | literatura*/návrh | prošla | Zdvojuje m2::metrika_3 a metrika_5 s lexikální změnou; kandidát na sloučení. |
| `m4::analytizace` | pásmo | 30 | podíl skupin s pevným slovosledem po ztrátě pádu 0.5–1.0; podíl skupin s volným slovosledem v kontrole 0.5–1.0 | literatura*/návrh | prošla |  |
| `m4::bez_eroze` | pásmo | 30 | podíl skupin se syntetickým minulým časem 0.5–1.0; podíl skupin se záporkou před slovesem 0.5–1.0 | návrh | prošla | Zvukové metriky v této bráně zdvojují m2::metrika_3 a metrika_5; kandidát na sloučení. |
| `m4::jespersen` | možnost | 30 | p_min 0.15 | literatura* | prošla | Stará brána chtěla navíc aspoň 4 z 6 skupin s koncovou záporkou; to je míra šíření, ne možnost. |
| `m4::velky_cyklus` | možnost | 20 | p_min 0.3 | literatura* | prošla | Jev: opis srostl v koncovku aspoň ve dvou skupinách; zdroj musí být z katalogu v každém případě. |
| `m4b::bez_padu` | pásmo | 30 | podíl skupin s pevným slovosledem bez pádu 0.5–1.0 | literatura* | prošla | Zdvojuje m4::analytizace; kandidát na sloučení. |
| `m4b::clen_vznikne` | možnost | 50 | p_min 0.1 | literatura | prošla | Člen smí vznikat jen v části jazyků; invariant: zdroj členu je v katalogu. |
| `m4b::exaptace` | možnost | 30 | p_min 0.15 | literatura* | prošla | Jev: exaptace aspoň ve dvou skupinách; invarianty (jen DEFINITE z OBJ, kontrola bez exaptace) musí platit tam, kde jev nastal. |
| `m4b::jazyk_bez_kategorie` | invariant | 3 | každý běh | návrh | prošla | Vypuštěno „nejvýš jedna skupina s nulovým minulým časem po vývoji“ (míra vývoje, kryje ji m4b::clen_vznikne) a podmíněné tvrzení o buňce PAST po gramatikalizaci (metrika není v každém běhu). |
| `m5::bez_dvojjazycnosti` | invariant | 3 | každý běh | literatura* | prošla |  |
| `m5::metrika_11` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m5::s2_l2` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m5::s2_mesto` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m5::s3_prechod` | invariant | 3 | každý běh | návrh | prošla |  |
| `m5::s3_substrat` | pásmo | 30 | x0>y: podíl slov jazyka x 0.0–0.05; x1>y: podíl slov jazyka x 0.0–0.05; stavba substrátu (menší z x0>y a x1>y) 0.2–1.0 | literatura*/návrh | prošla | Stará brána je slabá; většina jejích tvrzení (slovní stopa, zapsané změny) byla měřítka jednoho semínka. |
| `m5::vypujcky` | pásmo | 30 | a2: podíl výpůjček ve slovní zásobě 0.05–0.25; b0: podíl výpůjček ve slovní zásobě 0.05–0.25 | literatura* | prošla | Invariant: výpůjčka obsahuje jen hlásky inventáře příjemce. |
| `m6a::psany_kod_stoji` | invariant | 3 | každý běh | literatura* | prošla |  |
| `m6a::s4_bez_skoly` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6a::s4_skola` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6a::skola_sjednoti` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6a::skola_zmrazena` | možnost | 20 | p_min 0.8 | návrh | prošla |  |
| `m6b::elita_prejde` | pásmo | 20 | doba do přechodu elity (roky) 100.0–400.0 | literatura* | prošla |  |
| `m6b::ferguson` | možnost | 20 | p_min 0.8 | literatura | prošla |  |
| `m6b::jazyk_trhu` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6b::loajalita` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6b::metrika_9` | pásmo | 20 | korelace jazykové a zeměpisné vzdálenosti (2D) 0.5–0.9; R² logaritmického − R² lineárního proložení 0.0–0.3 | literatura/literatura* | prošla |  |
| `m6b::migrace` | možnost | 20 | p_min 0.7 | literatura* | prošla |  |
| `m6b::nabozenstvi` | možnost | 20 | p_min 0.8 | literatura* | prošla |  |
| `m6b::superstrat` | pásmo | 20 | l0: stavba elity 0.0–0.1; l3: stavba elity 0.0–0.1 | literatura* | prošla | Vypuštěno „aspoň 2 slova z jazyka dobyvatelů“ (velikost vzorku slovníku). |
| `m6c::strom_odpovida` | možnost | 20 | p_min 0.85 | návrh | prošla |  |
| `m6c::strom_stabilni` | možnost | 20 | p_min 0.85 | návrh | prošla |  |

## Pásma s oporou v literatuře a bez ní

- **S oporou (aspoň jedna veličina nebo zdroj druhu): 38 bran**. Webem jsem potvrdil čtyři zdroje: retence 0,80 až 0,87 (`m3b::metrika_1`; Swadesh 81 a 86 %, Lees 80,5 %, bez jistoty, který údaj patří ke kterému seznamu), Séguyova křivka (`m6b::metrika_9`, podlineární růst), závislost nepravidelnosti na frekvenci (`m3::produktivni_vzor`, Lieberman et al. 2007, sklon 0,50) a podíl jazyků se členem z WALS kap. 37 (377 ze 620, 61 %) u `m4b::clen_vznikne`. U ostatních jsem zdroj a řádovou hodnotu uvedl z paměti (literatura\*) a webové hledání je
  nepotvrdilo (Maddieson, WALS kap. 1 a 2, rozdělení do tříd; Tadmor 2009, průměrný podíl výpůjček;
  Pagel et al. 2007, tvar √ frekvence; Kroch 1989 a Blythe a Croft 2012 pro S-křivky; Ingham a Short pro
  přechod normanské elity).
- **Bez opory (14 bran, pásmo nebo `p_min` z věrohodnosti):** `m1::s1_hranice`, `m1::metrika_8`,
  `m2::metrika_5`, `m2::ruznost_seedu`, `m3::sturtevantuv_paradox`, `m3::analogie`, `m3b::nova_slova`,
  `m3b::erodovana_slova`, `m4::bez_eroze`, `m4b::jazyk_bez_kategorie`, `m5::s3_prechod`,
  `m6a::skola_zmrazena`, `m6c::strom_odpovida`, `m6c::strom_stabilni`. K tomu u mnoha bran druhu
  „možnost“ s oporou pro **směr** účinku (Ferguson, Lupyan a Dale, Haugen) literatura **míru** nedává:
  `p_min` 0,8 je u nich návrh. Zvlášť je neznámá četnost vzniku členu, exaptace, Jespersenova cyklu a tabu
  za 3 000 let.
- Zvukové změny za 3 000 let (`m2::metrika_6`, 10 až 40 na jazyk): dnešní engine dává asi 25 na jazyk; stará
  brána chtěla ≥ 10 na tři semínka a v Rustu dříve selhávala (13). Pásmo je z Ringeho (2006) a Popea (1934)
  z paměti.

## Brány ke sloučení nebo zrušení

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

- Webové hledání (US, standardní režim) potvrdilo jen část čísel (viz výše); zbytek je z paměti a výslovně
  označen. Před zamčením je třeba ověřit hlavně WALS kap. 1 a 2 (hranice tříd), WOLD (podíl výpůjček),
  Pagel et al. (tvar funkce), dobu přechodu elit a počty zvukových změn.
- Stará brána není pouze stochastická: u `m2::metrika_6` a `m2::ruznost_seedu` je vzorek trojice semínek,
  takže `N` = 12 trojic znamená 36 běhů.
- Nové brány se nenapojily na `cargo test`; jsou jen v `cee gates --report` (nespouštějí se v CI) a mají
  jednotkové testy statistiky a úplnosti registru.

# 22. Kalibrace M7

Stav: **M7.0 hotovo** (5. 11. 2026): měřidla cílů v Rustu a běh variant parametrů. Cíle jsou ve stavu
**návrh** a čekají na kontrolu uživatelem. Model ani parametry se zatím nezměnily.

## Proč

Brány milníků ([dokument 21](21-statisticke-brany.md)) říkají, zda model jev umí a drží ho ve
věrohodném rozsahu. Kalibrace se ptá jemněji: jak daleko je model od cílové hodnoty z literatury a
která varianta metaparametrů ho přiblíží. Nástroje, které cíle M7 měřily v Pythonu (typologické
měřidlo části A, test dosažitelnosti), zmizely se smazáním Pythonu v2; tady jsou znovu v Rustu.

Pravidlo jako u bran: **cíl a pásmo se stanoví ze zdroje předem**, parametry se ladí k cíli, ne cíl
k parametrům. Kalibrace používá semínka od 1, brány od 201, takže kalibrovat a ověřovat se nedá na
stejném vzorku.

## Příkaz

```
cargo run --release --bin cee -- calibrate --list                       # cíle a běhy
cargo run --release --bin cee -- calibrate -o values.jsonl              # všechno, asi 15 s
cargo run --release --bin cee -- calibrate --only typologie,m7::retence # běh nebo cíl
cargo run --release --bin cee -- calibrate --set village_openness=0.5 --set border_link_scale=2.0
cargo run --release --bin cee -- calibrate --variants varianty.json     # {"jméno": {"parametr": hodnota}}
```

Výpis má vždy variantu `výchozí` a vedle ní `přepis` (z `--set`) nebo varianty ze souboru.
Hodnota `--set` je JSON (číslo, objekt tabulky), jinak text; přepisy se ověřují stejně jako
`WorldSpec.parameters` (meze z `v2_parameters.json`). `-o` zapíše všechny veličiny po semínkách.
Semínka jedné varianty běží souběžně na všech jádrech; výsledek semínka na počtu vláken nezávisí.

**Jak se varianta dostane do světa.** Scénáře berou `Parameters::default()` při stavbě světa.
`parameters::with_defaults` ho na vlákně, kde se svět staví, nahradí variantou a po návratu vrátí
původní stav (i při panice). Běh pak čte jen parametry světa, takže vnořená vlákna simulace přepis
nepotřebují. Ověřeno: výchozí varianta dává totéž co běh bez přepisu, `--set` mění výsledek
(otevřenost 0,5 a hranice 2,0: vzdálenost přes hranici regionu 0,172 → 0,125).

## Kód a data

| část | soubor |
|---|---|
| cíle (stav „návrh“) | `src/cee/data/v2_calibration_targets.json` |
| reference WALS | `src/cee/data/v2_typology.json` (`engine_distribution`, dokument 10) |
| měřidla, běhy, vyhodnocení | `rust/cee_engine/src/calibration.rs` |
| přepis výchozích parametrů | `parameters::with_defaults`, `Parameters::file_default` |
| příkaz | `cee calibrate` (`rust/cee_engine/src/bin/cee.rs`) |

## Druhy cílů

- **pásmo**: veličina na `N` semínkách; cíl je splněný, když **medián** leží v pásmu. Je to přísnější
  než brána (tam stačí překryv intervalu se pásmem), protože kalibrace míří na hodnotu, ne na
  věrohodnost. Výpis uvádí i 95% bootstrapový interval mediánu.
- **typologie**: rozložení stavů rysu WALS přes jazyky **všech semínek dohromady** (jednotkou je
  jazyk posledního snímku, stav jazyka je převládající stav jeho skupin vážený mluvčími; protokol
  části A v dokumentu 10). Start se losuje z WALS (`calibration::wals_start`, vlastní proud na rys).
  Cíl je splněný, když Hellingerova vzdálenost od WALS po 5 000 letech nepřekročí 95% kvantil
  vzdálenosti, kterou dá stejně velký náhodný vzorek přímo z WALS (4 000 losů). Tedy: rozložení se
  od reality nevzdálí víc, než by vysvětlil šum vzorku. Řádek „start“ ukazuje, jak věrně sampler
  start vylosoval (není posuzovaný).
- **informace**: veličina bez cíle, jen výpis.

## Kalibrační běhy

| běh | scénář | cíle |
|---|---|---|
| `typologie` | 6 vesnic v řadě, syntax, sémantika, fonologie, morfologie a prozódie; gramatika (PL, PAST, FUTURE, DEFINITE, NEG, ORDER) a přízvuk losované z WALS; 5 000 let; 40 semínek | 7 rysů WALS, tóny |
| `lexikon` | 8 vesnic se sémantikou (běh brány `m3b`), 3 000 let; 20 semínek | retence |
| `region` | čtyři regiony po pěti vesnicích (`region-square`, dokument 14), 3 000 let; 12 semínek | kontinuum |
| `slozitost` | 20 míst: populace 100 až 10 000 × podíl L2 0 až 45 % (běh metriky 11), 1 500 let; 12 semínek | L2, populace, Trudgill |

Převod stavů enginu na WALS je tabulka A1 v [dokumentu 10](10-typologie.md): přítomnost PL, členu
a minulého času (`synthetic` nebo `periphrastic` = přítomné, `zero` = nepřítomné), inflexní budoucí
čas (`synthetic` = 67A-1), pevný slovosled podle pořadí (volný je neznámý, ne kategorie), zápor
před, za a obemknutý (143A-1, -2, -14), pravidlo přízvuku (14A-2, -3, -5, -6, -7). Reference je
`engine_distribution`, tj. WALS podmíněný na stavy, které model vyjádří; sampler i nulové
rozdělení používají totéž, takže srovnání je férové.

## Cíle (návrh)

| cíl | veličina | cíl | zdroj | podpora |
|---|---|---|---|---|
| `m7::retence` | retence základní slovní zásoby za tisíciletí | medián v [0,80; 0,90] | Swadesh (1955) 86 %/100 slov, Lees (1953) 80,5 %/200 slov | literatura |
| `m7::kontinuum` | vzdálenost sousedních vesnic v regionu po 3 000 letech | [0,05; 0,15] | dokument 14 (nářeční atlasy, míra není přímo srovnatelná) | návrh |
| `m7::slozitost` | Spearman složitosti s podílem L2 | [−1; −0,2] | Bentz a Winter (2013), směr | literatura (směr) |
| | Spearman složitosti s populací | [−1; −0,2] | Lupyan a Dale (2010), směr | literatura (směr) |
| | Spearman kořenové alternace s populací | [−1; 0] | Trudgill (2011), směr | literatura (směr) |
| `m7::typologie_<rys>` | Hellinger od WALS po 5 000 letech (33A, 37A, 66A, 67A, 81A, 143A, 14A) | ≤ 95% kvantil šumu vzorku | WALS CLDF v2020.6 (CC BY 4.0) | literatura |
| `m7::tony` | podíl samohlásek s tónem po 5 000 letech | informace | Maddieson (2013), WALS 13A: 42 % jazyků s tónem | literatura |
| `m7::kontinuum_poradi` | vzdálenost přes hranici, vzdálené regiony, počet jazyků | informace | dokument 14 | návrh |

U korelací literatura dává **směr**, ne sílu na stejné škále, proto je pásmo jen „správným směrem a
ne zanedbatelně“ (−0,2). U tónů chybí definice tónového jazyka: tón je v modelu rys jednotlivé
samohlásky, takže 42 % z WALS nejde srovnat s ničím, co model měří. Start je navíc bez tónů, takže
veličina měří tempo tonogeneze, ne stacionaritu.

## Výchozí stav (semínka od 1)

**Splněno 8 z 12 posuzovaných veličin.** Celý běh trvá asi 14 s (8 vláken).

| cíl | veličina | výchozí | cíl | splněno |
|---|---|---|---|---|
| retence | za tisíciletí | 0,832 [0,827; 0,843] | [0,80; 0,90] | ano |
| kontinuum | sousedé v regionu | 0,066 [0,062; 0,068] | [0,05; 0,15] | ano |
| složitost | s podílem L2 | −0,84 | [−1; −0,2] | ano |
| | s populací | −1,00 | [−1; −0,2] | ano |
| | kořenová alternace s populací (Trudgill) | **+0,38** [0,19; 0,48] | [−1; 0] | **ne** |
| 33A plurál | Hellinger | **0,251** (všech 40 jazyků má plurál; start 35 : 5) | ≤ 0,098 | **ne** |
| 37A člen | Hellinger | **0,469** (všech 40 má člen; start 19 : 21) | ≤ 0,112 | **ne** |
| 66A minulý čas | Hellinger | 0,000 | ≤ 0,110 | ano |
| 67A budoucí čas | Hellinger | **0,184** (inflexní 31 : 9; start 26 : 14) | ≤ 0,111 | **ne** |
| 81A slovosled | Hellinger | 0,211 (24 jazyků s pevným pořadím) | ≤ 0,245 | ano |
| 143A zápor | Hellinger | 0,146 | ≤ 0,147 | ano (těsně) |
| 14A přízvuk | Hellinger | 0,122 | ≤ 0,205 | ano |
| tóny | podíl samohlásek s tónem | 0,045 [0,010; 0,250] | informace | – |

Kontinuum (pořadí): sousedé 0,066 < přes hranici 0,172 < vzdálené regiony 0,229, po 3 000 letech
jeden jazyk; vše podle dokumentu 14.

**Co to znamená.** Potvrdilo se, před čím varovala specifikace: **flexivní kategorie se jen
sčítají**. Za 5 000 let má plurál a člen každý z 40 jazyků a inflexní budoucí čas přibývá; zánik
kategorie bez kontaktu skoro nenastává (dokument 05, mezery: `CategoryLoss` je bez L2 mluvčích
neaktivní). Minulý čas, slovosled, zápor a přízvuk jsou stacionární v rámci šumu. Trudgillův vztah
je obrácený, jak uvádí specifikace: kořenová alternace roste s populací.

## Omezení

- 40 jazyků je malý vzorek: 95% kvantil šumu je 0,10 až 0,25, takže test zachytí jen velký posun.
  U 33A dá vzorek „všechny přítomné“ Hellinger 0,251 a k takovému vzorku dojde náhodou s
  pravděpodobností 0,88^40 ≈ 0,6 %, proto neprošel; při 20 semínkách (0,88^20 ≈ 8 %) by prošel.
- Start 81A vyšel 0,208 proti kvantilu 0,205: start z dokonalého sampleru překročí kvantil v 5 %
  případů; je to šum, ne chyba sampleru (jednotkový test ověřuje sampler na 400 losech).
- 81A se posuzuje jen u jazyků s pevným slovosledem (volný není kategorie WALS); jazyků je proto
  méně (24 ze 40).
- Stav „přítomný“ u 37A zahrnuje volné ukazovací zájmeno v roli členu (jako WALS), takže start
  s volným `this` je člen přítomný.
- Typologie se měří jen na startu a po 5 000 letech; průběh (1 000, 2 000 …) zatím ne.
- Chybí měřidla, která kalibrace M7 ještě potřebuje: apokopa a eroze koncovek (dokument 05: 0 z 281
  ustálených), prestižní asymetrie výpůjček, konstanty kontaktu a přechodu, zpětný test latina →
  románské jazyky. Patří do M7.1 a M7.2, kde se k nim postaví scénáře.

## Další krok: M7.1 test dosažitelnosti

U čtyř nesplněných cílů je první otázka, zda je vůbec jde splnit změnou čísel: projít krajní hodnoty
parametrů, které literatura připouští (zejména `category_loss_l2_boost`, `emergence_need_scale`,
`change_rates` gramatiky, `analogy_l2_boost`), přes `--variants`. Když se zánik kategorie nebo
Trudgillův vztah nerozběhne ani v rohu prostoru, chybí mechanismus a kalibrace ho nespraví.

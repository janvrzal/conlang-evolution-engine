# 22. Kalibrace M7

Stav: **M7.0 a M7.1 hotovo** (5. 11. 2026): měřidla cílů v Rustu, běh variant parametrů a test
dosažitelnosti. Cíle jsou ve stavu **návrh** a čekají na kontrolu uživatelem. Model ani parametry se
zatím nezměnily. Výsledek M7.1: čtyři nesplněné cíle **nejdou splnit změnou čísel**, chybí mechanismy
(viz [M7.1](#m71-test-dosažitelnosti)).

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
  start vylosoval (není posuzovaný). Řádek „přechody“ počítá jazyky, které od startu kategorii získaly,
  ztratily nebo změnily stav (informace; rozliší rovnováhu od zamrznutí).
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

## M7.1: test dosažitelnosti

Otázka: dají se nesplněné cíle (plurál, člen a budoucí čas se jen hromadí, Trudgill obráceně) splnit
změnou metaparametrů v mezích, které jsou ještě věrohodné? Když ne ani v krajních variantách, chybí
mechanismus. Varianty jsou v `docs/engine-v2/kalibrace/m71-gramatika.json` a `m71-trudgill.json`:

```
cargo run --release --bin cee -- calibrate --only typologie --variants docs/engine-v2/kalibrace/m71-gramatika.json
cargo run --release --bin cee -- calibrate --only slozitost --variants docs/engine-v2/kalibrace/m71-trudgill.json
```

Literatura meze těchto konstant nedává (autorské odhady, `v2_parameters.json`), proto jsou rohy
násobky výchozích hodnot: tempo zániku ×10 a ×30, potřeba nové kategorie 0,2 a 0, tolerance kod 1
a funkční zátěž 1 (víc eroze), váha expresivity 0,3, ekonomie ×3, opis a exaptace ×0,25, a dva
kombinované rohy. Měřidlo k tomu dostalo **počty přechodů**: kolik jazyků od startu kategorii
získalo a ztratilo. Stacionární rozložení totiž může vzniknout rovnováhou vzniku a zániku, nebo tím,
že se nic neděje, a Hellingerova vzdálenost to nerozliší.

### Gramatické kategorie (40 jazyků, 5 000 let)

Vznik / zánik kategorie (počet jazyků):

| varianta | plurál 33A | člen 37A | minulý 66A | budoucí 67A |
|---|---|---|---|---|
| výchozí | +5 / −0 | +21 / −0 | +3 / −0 | +5 / −0 |
| zánik ×10 | +5 / −0 | +20 / −0 | +3 / −0 | +5 / −0 |
| zánik ×30 | +5 / −0 | +20 / −0 | +3 / −0 | +5 / −0 |
| víc eroze (kody 1, funkční zátěž 1) | +5 / −0 | +21 / −0 | +3 / −0 | +5 / −0 |
| potřeba 0,2 | +1 / −0 | +13 / −0 | +1 / −0 | +1 / −0 |
| potřeba 0 | +0 / −0 | +8 / −0 | +0 / −0 | +0 / −0 |
| expresivita 0,3 | +1 / −0 | +9 / −0 | +0 / −0 | +0 / −0 |
| ekonomie ×3 | +0 / −0 | +19 / −0 | +0 / −0 | +0 / −0 |
| opis a exaptace ×0,25 | +5 / −0 | +17 / −0 | +5 / −0 | +1 / −0 |
| roh „zánik“ | +0 / −0 | +4 / −0 | +0 / −0 | +0 / −0 |
| roh „extrémní“ | +0 / **−3** | +1 / **−5** | +0 / −0 | +0 / −0 |

**Zánik kategorie bez kontaktu nenastává.** Ve 40 jazycích za 5 000 let nezanikla ve výchozím stavu
ani jedna kategorie a desetinásobné ani třicetinásobné tempo zániku nic nezmění. Jediné zániky dal
extrémní roh (potřeba 0, expresivita 0,2, ekonomie ×3 a další), a to 3 plurály a 5 členů.
Varianty, které testem stacionarity projdou (potřeba 0, expresivita 0,3), projdou tím, že **zamrznou**
(nevzniká nic), ne rovnováhou.

Proč: `CategoryLoss` navrhne vypuštění syntetické koncovky jen úměrně její slabosti (`weakness`,
eroze tvaru) a podílu L2 mluvčích. Bez kontaktu je L2 nula a slabost zůstává nulová: varianta
„víc eroze“ dává přesně totéž co výchozí stav, takže zvukové změny koncovky neoslabí ani
s plnou tolerancí kod. Volný opis (`this` jako člen) zánik navrhnout může, ale výběr ho odmítne,
dokud expresivita nevyjádřenou funkci tolik trestá. To odpovídá dokumentu 05 (D0: apokopa 0 z 281
ustálených; D4: samovolná eroze nedosáhne slabosti 0,5).

**Chybějící mechanismus:** samovolná eroze vázané morfologie. V reálných jazycích koncovky slábnou
zvukovou změnou (latinské *-m*, koncové samohlásky) a kategorie pak zaniká nebo se obnoví opisem
(Jespersenův a velký cyklus). V modelu se cyklus rozběhne jen v kontrolovaném pokusu se vloženou
erozí (brány M4). Patří do M7.2 „zvuk“ (apokopa, tlak fonotaktiky a funkční zátěže na koncovkách),
ne do kalibrace čísel.

Stálé rysy (minulý čas, slovosled, zápor, přízvuk) se mezi variantami skoro nemění; přízvuk se ve
výchozím stavu změní ve 13 ze 40 jazyků, zápor v 5, slovosled ve 3, takže tam dynamika běží.

### Trudgill (12 semínek)

Spearman kořenové alternace s populací při pevném podílu L2 (cíl ≤ 0):

| varianta | korelace |
|---|---|
| výchozí | +0,38 |
| analogie ×4 | +0,22 |
| analogie ×0,25 | +0,41 |
| práh analogie 0,6 | +0,36 |
| konformita ×0,2 | +0,10 |
| konformita ×5 | 0,00 (všechno zamrzne, i korelace s L2 a populací jsou 0) |
| učitelnost ×3 | +0,32 |
| artikulace ×3 | +0,61 |

Žádná varianta vztah neotočí; slabší konformita ho jen zmenší. Velká skupina v modelu přijímá
přirozené zvukové změny účinněji, a tím získá víc alternací kmene. Trudgillův mechanismus (malá
izolovaná komunita s hustou sítí silných vazeb udrží i neobvyklé změny a složitost, velká s mnoha
slabými vazbami a dospělými učícími se ji ztrácí) model nemá: chybí vliv **hustoty sítě a podílu
slabých vazeb** na přijetí nepřirozených změn a na jejich zjednodušení. Patří do M7.2 „společnost“.

### Shrnutí M7.1

| cíl | dosažitelný čísly? | co chybí |
|---|---|---|
| plurál, člen, budoucí čas (stacionarita) | ne | samovolná eroze koncovek, která spustí zánik a cyklus |
| Trudgill | ne | vliv hustoty sítě a slabých vazeb na přijetí a zjednodušení změn |
| retence, kontinuum, L2, populace, minulý čas, slovosled, zápor, přízvuk | už splněno | – |

Další krok je tedy práce na modelu (M7.2), ne ladění: nejdřív eroze koncovek, protože na ní stojí
tři ze čtyř nesplněných cílů.

## M7.2a: diagnostika eroze koncovek

Typologický běh dostal diagnostiku (`eroze …` v `-o values.jsonl`): kolik změn konce slova
(`coda_loss`, `apocope`) se navrhlo, ustálilo a zfonologizovalo, a průměrná slabost syntetických
koncovek po 5 000 letech (podíl tvarů buňky splynulých s citačním tvarem). Varianty jsou
v `docs/engine-v2/kalibrace/m72-diagnostika.json`.

**Eroze nastává, ale koncovky skoro nezeslábnou.** Ve výchozím stavu se za 5 000 let ve 40 jazycích
ustálilo 665 ztrát kody a 13 apokop (990 a 68 zfonologizovaných slov), slabost plurálu je přesto
0,05, předmětu 0,005 a minulého času 0. Proč, ukázaly tvary protojazyka (semínko 3):

| slovo | citace | plurál | předmět (start → 1 000 let) |
|---|---|---|---|
| ‚bit‘ | bit | bit-i | bit-ne |
| ‚su‘ | su | su-i | su-ne → su-m |
| ‚kasepe‘ | kasepe | kasepe-i | kasepe-m |
| ‚la‘ | la | la-i | la-ne → la-m |

1. **Koncovka plurálu `-i` stojí většinou za samohláskou.** Apokopa maže samohlásku jen za
   souhláskou (`/C_#`) a ztráta kody jen souhlásku, takže na `-i` za samohláskou nedosáhne žádná
   změna. Reálné jazyky takový hiát řeší elizí jedné ze samohlásek (Casali 1997: nejčastěji první);
   rodina pro elizi v hiátu v katalogu chybí.
2. **Srozumitelnost brzdí změny konce slova nejvíc.** Se sníženou váhou `clarity` (0,3) se ustálí
   4× víc ztrát kody a 25× víc apokop; s vypnutou funkční zátěží slabost předmětu stoupne
   z 0,005 na 0,07, s obojím na 0,22 (plurál 0,11).
3. **Ani zeslabená koncovka kategorii nezruší.** I ve variantě se slabostí předmětu 0,22 nezanikla
   v žádném jazyce žádná kategorie. Zánik navrhuje `CategoryLoss` úměrně slabosti, ale výběr ho
   odmítne, protože nevyjádřená funkce (`zero`) platí plnou cenu expresivity; analogie mezitím
   zeslabené tvary opravuje rozšířením znějící koncovky (`-ne` → `-m` výše).

| varianta | ustálené ztráty kody | ustálené apokopy | slabost PL | slabost OBJ | zániky kategorií |
|---|---|---|---|---|---|
| výchozí | 665 | 13 | 0,052 | 0,005 | 0 |
| funkční zátěž 0 | 774 | 13 | 0,077 | 0,069 | 0 |
| funkční zátěž 1 | 732 | 25 | 0,065 | 0,020 | 0 |
| srozumitelnost 0,3 | 2 702 | 324 | 0,084 | 0,035 | 0 |
| funkční zátěž 0 a srozumitelnost 0,3 | 3 526 | 440 | 0,109 | 0,222 | 0 |
| tempo změn konce ×5 | 2 072 | 279 | 0,056 | 0,018 | 0 |

**Člen (37A) je zvláštní případ.** Hromadí se ne kvůli chybějící erozi, ale protože vzniká
rychle (všech 21 jazyků bez členu ho získalo) a zaniká jen tak, že se volné ukazovací zájmeno
vypustí, což výběr odmítá. Ve skutečnosti se člen „ztrácí“ hlavně tím, že se dál
gramatikalizuje na pouhý jmenný ukazatel bez určitosti (Greenberg 1978, stadium III), a WALS ho
pak za člen nepočítá. Stacionarita 37A potřebuje vyvážit tempo vzniku a ztráty (Maslova 2000:
stacionární rozložení = rovnováha přechodů), ne jen erozi.

## M7.2b: mechanismy eroze a cyklu členu

Na základě M7.2a (5. 11. 2026, schválil uživatel). Výchozí hodnoty parametrů se **nezměnily**; nové
jsou dvě změny modelu.

1. **Eliza v hiátu** (`hiatus_elision`, `cee_core::candidates`, prior 0,5 jako apokopa a synkopa):
   nepřízvučná samohláska zmizí před jinou samohláskou (`V → ∅ /_V`) nebo za ní na konci slova
   (`V → ∅ /V_#`). Hiát řeší většina jazyků, nejčastěji elizí (Casali 1997, Vowel elision in hiatus
   contexts, Language 73, 493–533). Dosáhne na koncovky za samohláskou (`la-i` → `la`), na které
   apokopa (`/C_#`) ani ztráta kody nedosáhnou. Rodina je v rozpočtu netónových zvukových inovací,
   takže tempo ostatních rodin kleslo asi o 3,5 % (součet priorů 13,7 → 14,2).
2. **Vyblednutí členu** (`bleaching`, `changes::syntax::Step::Bleaching`, základní míra 0,01 jako
   obnova záporu): vázaný člen (klitika nebo koncovka) ztratí určitost a stane se ukazatelem jména
   (Greenberg 1978, How does a language acquire gender markers?, v Universals of Human Language 3,
   stadium III). Konstrukce je `zero` se stadiem `marker`: funkce je nevyjádřená (WALS 37A ji počítá
   jako bez členu) a může se znovu obnovit opisem z ukazovacího zájmena, takže cyklus je uzavřený.
   Na škále gramatikalizace je o stupeň za koncovkou (`rank` 4), takže tlak `Fusion` vyblednutí mírně
   podporuje (jednosměrnost gramatikalizace). Jen u funkcí s `bleaches: true` v katalogu
   (`v2_grammar.yaml` a `.json`): dnes `DEFINITE`.

**Třetí navržený mechanismus už v modelu byl.** Expresivita syntetické koncovky je `1 − slabost`
a nevyjádřená funkce dostává `context`, takže zánik vyhraje, jakmile slabost přesáhne `1 − context`
(plurál 0,7, předmět 0,9, minulý čas 0,75). Návrh v M7.2a („cena podle spolehlivosti“) vycházel
z chybného předpokladu; nic se neměnilo.

### Výsledek (typologie, 40 jazyků, 5 000 let)

| | dřív | eliza a vyblednutí |
|---|---|---|
| ustálené elize v hiátu | – | 2 599 (4 967 zfonologizovaných slov) |
| slabost plurálu po 5 000 letech | 0,05 | 0,13 |
| člen: vznik / zánik | +21 / −0 | +19 / −2 |
| člen: Hellinger od WALS | 0,469 | 0,250 |
| plurál, minulý a budoucí čas | beze změny | beze změny (zánik 0) |
| brány milníků | 47 z 47 | **47 z 47** (délka slova, homofonie a inventáře beze změny) |

Varianty tempa vzniku s novými mechanismy (`docs/engine-v2/kalibrace/m72-vznik.json`):

| varianta | 33A plurál | 37A člen | 66A minulý | 67A budoucí |
|---|---|---|---|---|
| výchozí (potřeba 0,6) | +5 / −0, H 0,251 ne | +19 / −2, H 0,250 ne | +3 / −0 ano | +5 / −0, H 0,184 ne |
| potřeba 0,4 | +5 / −0 ne | +18 / −3, H 0,197 ne | +2 / −0 ano | +2 / −0, H 0,123 ne |
| potřeba 0,3 | +5 / −0 ne | +17 / −3, H 0,173 ne | +1 / −0 ano | +1 / −0 ano |
| potřeba 0,2 | +1 / −0 ano | **+13 / −5, H 0,050 ano** | +0 / −0 ano | +1 / −0 ano |
| vyblednutí ×3 | +5 / −0 ne | +18 / −4, H 0,173 ne | +3 / −0 ano | +5 / −0 ne |
| potřeba 0,3 a vyblednutí ×3 | +5 / −0 ne | **+13 / −5, H 0,050 ano** | +1 / −0 ano | +1 / −0 ano |

**Člen má skutečný cyklus**: při potřebě 0,2 (nebo 0,3 s rychlejším vyblednutím) člen ve 13 jazycích
vznikne a v 5 zanikne a rozložení drží u WALS v rámci šumu. To je stacionarita z rovnováhy
přechodů (Maslova 2000), ne ze zamrznutí.

**Plurál, minulý a budoucí čas projdou jen zamrznutím.** Při nižší potřebě vznikají vzácněji, ale
nezaniká žádný: slabost plurálu 0,13 je daleko od prahu 0,7, protože analogie zeslabené tvary
opravuje. Pro skutečný cyklus u nich chybí silnější eroze: tempo a srozumitelnost změn konce slova.
Literatura pro ně dává cíl až ve zpětném testu latina → románské jazyky (M7.3: ztráta koncového
*-m* a koncových samohlásek, zánik pádů), proto se váha `clarity` zatím neladí.

**Rozhodnutí pro uživatele**: tempo vzniku (`emergence_need_scale`) je od M7a jen předběžné (0,6).
Hodnota 0,2 až 0,3 dává stacionární typologii všech čtyř rysů, u členu skutečným cyklem. Změna
výchozí hodnoty zatím neproběhla.

### Tempo vzniku 0,2 naráží na bránu členu (5. 11. 2026)

Uživatel schválil snížit `emergence_need_scale` na 0,2. Kalibrace pak splní 11 z 12 cílů (chybí jen
Trudgill), ale **brána `m4b::clen_vznikne` neprojde**: ve scénáři M4b (jazyk bez pádu, 3 000 let)
člen nevznikne v žádném z 50 běhů (brána chce aspoň 1, `p_min` 0,1). Změna proto zatím **není
zapsaná**; výchozí hodnota zůstává 0,6. Měření (vyblednutí se základní mírou 0,03 u 0,3 až 0,5,
jinak 0,01):

| potřeba | člen v M4b (běhy z 50) | 33A plurál | 37A člen | 66A minulý | 67A budoucí |
|---|---|---|---|---|---|
| 0,6 | 5, prošla | ne (+5 / −0) | ne (+19 / −2) | ano | ne |
| 0,5 | 1, prošla | ne | ne (+16 / −4) | ano | ne |
| 0,4 | 1, prošla | ne (+5 / −0) | **ano (+15 / −5)** | ano | ne (+2 / −0) |
| 0,3 | 0, neprošla | ne | ano | ano | ano |
| 0,2 | 0, neprošla | ano (+1 / −0) | ano (+13 / −5) | ano (+0 / −0) | ano (+1 / −0) |

Žádná hodnota nesplní obojí. Plurál a budoucí čas projdou jen tam, kde skoro nevznikají
(zamrznutí), protože zatím nezanikají; tentýž nízký vznik pak nedovolí člen v brány M4b. Pravým
řešením je zánik plurálu a budoucího času erozí (M7.3), ne tempo vzniku.

Při té příležitosti se našla chyba v kontrole invariantu `m4b::jazyk_bez_kategorie`: „zdroj minulého
času je z katalogu“ počítala jako cizí zdroj i skupinu, která minulý čas nevyvinula. Opraveno
(4aa34bc); brána prochází při všech hodnotách.

## M7.2c: tempo vzniku 0,4, cyklus futura a kontext plurálu

Schválil uživatel 5. 11. 2026 („Zapiš 0,4 a pokračuj v kalibraci, vyřeš ten plurál a budoucí čas“).
Zapsané změny:

| změna | dřív | nyní | zdůvodnění |
|---|---|---|---|
| `emergence_need_scale` | 0,6 | **0,4** | nejnižší hodnota, při níž brána `m4b::clen_vznikne` projde a člen má cyklus (tabulka výše) |
| základní míra `bleaching` | 0,01 | **0,03** | jako připojení koncovky; s 0,01 je vyblednutí vzácnější než vznik a člen se hromadí |
| `FUTURE.bleaches` | – | **ano** | futurum vybledne do modálního nebo epistémického významu a obnoví se opisem (Bybee, Perkins a Pagliuca 1994, *The Evolution of Grammar*, University of Chicago Press; lat. *cantabo* → *cantare habeo*) |
| bonus `Fusion` ze zděděné koncovky | stupeň 0 | **stupeň 3** | zděděná syntetická konstrukce nemá zapsaný exponent, ale je to koncovka; bez opravy se vyblednutí futura nikdy neprosadilo (`transfer::pressures::current_rank`) |
| `PL.context` | 0,3 | **0,5** | plurál je povinný u všech jmen jen asi u 46 % jazyků (WALS 34A, Haspelmath 2013, Occurrence of Nominal Plurality); jinde plurálnost často nese kontext |

`PL.context` určuje oba směry cyklu: jak silně se plurál prosazuje do jazyka, který ho nemá, a od
jaké slabosti koncovky zaniká (`1 − context`, nyní 0,5). Varianty: `kalibrace/m72-plural.json`
(kontext 0,45 dal +5 / −1 a neprošel, 0,6 dal +1 / −1).

### Výsledek

**Kalibrace 10 z 12, brány 47 z 47, testy prošly.**

| rys | vznik / zánik | Hellinger | cíl | splněno |
|---|---|---|---|---|
| 33A plurál | +4 / −1 | 0,092 | ≤ 0,098 | ano (těsně) |
| 37A člen | +14 / −4 | 0,088 | ≤ 0,112 | ano |
| 66A minulý čas | +2 / −0 | 0,018 | ≤ 0,110 | ano |
| 67A budoucí čas | +2 / −3 | 0,067 | ≤ 0,111 | ano |
| 81A slovosled | ~3 změny | 0,211 | ≤ 0,245 | ano |
| **143A zápor** | ~4 změny | **0,256** | ≤ 0,147 | **ne** |
| 14A přízvuk | ~13 změn | 0,122 | ≤ 0,205 | ano |

Plurál, člen a futurum mají skutečný cyklus vzniku i zániku. Minulý čas jen vzniká; ve 40 jazycích
nezanikl, ale je stacionární v rámci šumu (zánik minulého času bez náhrady je i ve skutečnosti
vzácný, Präteritumschwund nahrazuje minulý čas perfektem, který 66A počítá jako přítomný).

**Zbývá:**

- **Zápor 143A.** Obemknutý zápor (Jespersenovo stadium II, `embraced`, ve WALS 13 %) ve 40
  jazycích zmizí (start 3, konec 0; při 0,6 jeden). Stadium II je v modelu příliš krátké: tlak
  `Economy` trestá dvě slova záporu a výraznost je u obou podob stejná. Ve skutečnosti obemknutý
  zápor vydrží staletí (francouzské *ne … pas*, afrikánština). Brána byla na hraně už ve výchozím
  stavu (0,146 proti 0,147).
- **Trudgill** (alternace kmene s populací +0,39): chybí vliv hustoty sítě (M7.1).

## M7.2d: zápor a Trudgill

Schválil uživatel 5. 11. 2026 („Udělej oba“).

### Zápor 143A: stadium II trvá, dokud nezeslábne první část

Obemknutý zápor (`embraced`, Jespersenovo stadium II) se zkracoval na samotnou druhou část
(`NegationReduction`) stálým tempem a výběr to vždy přijal, protože `Economy` trestá dvě slova
záporu a výraznost obou podob je stejná. Stadium II tak bylo jen přechodné a ve 40 jazycích
zmizelo. Ve skutečnosti obemknutý zápor trvá staletí a zkracuje se, až první část fonologicky
zeslábne (francouzské *ne* → *n'*, pak vypadne; Jespersen 1917, *Negation in English and Other
Languages*; Breitbarth 2009). Zkrácení se proto navrhuje jen tehdy, když je zdroj první části
erodovaný (`syntax::eroded`), stejně jako posílení prvního stadia stojí na slabosti částice.

| | dřív | nyní |
|---|---|---|
| 143A Hellinger (limit 0,147) | 0,256, neprošla | **0,063, prošla** |
| obemknutý zápor po 5 000 letech | 0 ze 40 | zachovaný |
| brána `m4::jespersen` | prošla | prošla (30 % běhů, `k` = 1 z 30) |

Dynamika záporu je ale pomalá: za 5 000 let změnil zápor stadium jen v 1 ze 40 jazyků (dřív ve 4).
Jespersenův cyklus má podle literatury stadia trvající staletí, takže za 5 000 let by změn mělo být
víc; tempo zeslabení částic je úkol pro M7.3 (zvukové tempo podle latiny).

### Trudgill: tři pokusy, žádný nevyšel, nic se nezapsalo

Cíl: alternace kmene má klesat s velikostí komunity (Trudgill 2011); dnes +0,39. Zkoušel jsem
parametr, kterým velikost komunity (`(populace / 500) ** exponent`) zesiluje vyrovnávání paradigmat:

| podoba | Trudgill | brány |
|---|---|---|
| tempo návrhů analogie i tlak `uniformity`, exponent 0,75 | **−0,19** (cíl splněn) | **44 ze 47**: neprošly `m5::s2_mesto`, `m5::s2_l2`, `m5::metrika_11` |
| jen tlak `uniformity`, exponent 0,75 | +0,23 | `m5::s2_mesto` neprošla |
| `uniformity` jen u řídce užívaných slov (frekvenčně vážená), exponent 1 | +0,21 | `m5::s2_mesto` neprošla |

Proč to nejde: obrátit vztah umí jen tak silné vyrovnávání ve velkých komunitách, že město
vyrovná i častá nepravidelná slova. Brána `m5::s2_mesto` ale hlídá doložený vliv frekvence
(častá slova si nepravidelnost drží, Bybee 2006; angl. *went*, *was*). Navíc násobit tempo návrhů
analogie velikostí je dvojí započtení, protože počet inovací už roste s počtem mluvčích
(`innovation_scale`, Kimura). Alternace v modelu roste s velikostí hlavně proto, že velká skupina
účinněji vybere snadno vyslovitelné zvukové změny (váha `articulation` 0,3 vztah oslabí na +0,16):
to je populační genetika výběru (Bromham, Hua, Fitzpatrick a Greenhill 2015, Rate of language evolution is affected by population size, PNAS 112, 2097–2102: větší
populace mění slovní zásobu rychleji), ne chyba.

Trudgillův mechanismus podle něj stojí na **vnitřní struktuře komunity** (hustá síť silných vazeb,
děti jako jediní učící se, málo dospělých nováčků), kterou model nemá: skupina je jeden uzel
s velikostí a podílem L2, bez vnitřní sítě. Mechanismus jsem proto nezapsal (parametr by jen
přidal neúčinnou složitost) a cíl zůstává nesplněný. Patří k vnitřní síti skupin (M7.2 společnost
nebo pozdější), ne ke kalibraci čísel. Varianty pokusů: `kalibrace/m72-trudgill.json`.

**Stav kalibrace: 11 z 12 cílů, brány 47 z 47.** Nesplněný zůstává jen Trudgill.

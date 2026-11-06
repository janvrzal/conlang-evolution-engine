# 25. Generátor protojazyka

Stav: **hotovo** (6. 11. 2026, větev `protojazyk`).

Podnět: vygenerovaný jazyk je první, co uživatel aplikace uvidí (iberština, dáčtina, baskičtina
v Evropě a protojazyky ve hrách). Dosavadní generátor skládal 1–3 slabiky CV z inventáře, 15 % slov
začínalo samohláskou, 25 % končilo souhláskou a hlásky měly váhy podle pořadí v seznamu (Zipf).
Výsledek vypadal jako náhodné slabiky: „dva“ *tikokub*, „ty“ *bebata*, „matka“ *liradu*.

Generátor (`rust/cee_engine/src/protoform.rs`) teď skládá slova podle dat o skutečných jazycích.
Slova zadaná autorem (`words`, např. z IE-CoR) mají vždy přednost; stejné semínko dá stejný jazyk.

## Zdroje a licence

| zdroj | k čemu | licence |
|---|---|---|
| ASJP (Wichmann, Holman a Brown, eds.; `lexibank/asjp` commit `cf4bf0d`, ~9 600 doculectů, 40–100 pojmů) | četnost hlásek podle pozice, slabiky, délka slov, Zipf | CC BY 4.0 |
| WALS 12A Syllable Structure (Maddieson 2013; `cldf-datasets/wals` commit `81298aa`) | slabičné typy a jejich podíly (61 / 274 / 151 jazyků) | CC BY 4.0 |
| Blasi, Wichmann, Hammarström, Stadler a Christiansen 2016, PNAS 113: 10818, tab. S2–S3 | 74 asociací pojem–hláska s poměrem rizik (RR) | převzatá čísla s citací (data ASJP CC BY 4.0) |
| Murdock 1959, Anthropological Linguistics 1(9); Jakobson 1962, *Why „mama“ and „papa“?* | dětská slova pro rodiče | převzatá čísla s citací |
| WOLD (Haspelmath a Tadmor 2009), 41 jazyků | kontrola dětských slov | CC BY 4.0 |

**PHOIBLE** zadání navrhovalo. Licenci jsem ověřil: web phoible.org (verze 2.0) uvádí CC BY-SA 3.0,
repozitář `phoible/dev` dnes uvádí data pod CC BY 4.0 (kód MIT). Nakonec jsem PHOIBLE nepoužil,
a to z věcného důvodu, ne kvůli licenci: měří, *zda* jazyk hlásku má (inventář), kdežto generátor
potřebuje, *jak často* se hláska ve slovech jazyka, který ji má, vyskytuje. To dává ASJP přímo
a na stejných datech pracovali Blasi a kol., takže je všechno na jedné stupnici. Inventář si
zatím volí autor nebo výchozí `p t k b d ɡ m n s l r w j h` / `a e i o u`. Pro budoucí
generování inventářů je vhodný PHOIBLE z GitHubu (CC BY 4.0).

Data: `src/cee/data/v2_protoform.json`, vyrábí ho `scripts/build_v2_protoform.py` (data v
`~/.cee/data/{asjp,wals,wold}`, otisky SHA-256 v souboru). Výpůjčky (`Loan`) a vymřelé jazyky
skript vynechává; průměr se počítá doculect → jazyk (Glottocode) → rodina → přes rodiny, aby
velké rodiny (bantuské, austronéské) nepřevážily.

## Co generátor dělá

### 1. Četnost hlásek podle skutečných jazyků

Každá hláska inventáře se převede na třídu ASJP (`ipa_to_asjp`, Brown a kol. 2008; diakritika,
délka a sekundární artikulace se odstraní, `t͡s` → `c`, `tʃ` → `C`). Váha hlásky v pozici je
podíl třídy mezi souhláskami (samohláskami) téže pozice **v jazycích, které třídu mají**:

| pozice | nejčastější souhlásky (podíl) |
|---|---|
| začátek slova | k 0,13 · m 0,11 · t 0,11 · n 0,10 · h 0,07 · s 0,06 · b 0,06 · p 0,06 · d 0,06 |
| vnitřek | r 0,12 · n 0,11 · k 0,10 · l 0,09 · t 0,08 · m 0,08 · ɡ 0,06 · d 0,06 · b 0,06 |
| konec slova | n 0,17 · ʔ 0,16 · ŋ 0,12 · r 0,10 · l 0,09 · k 0,08 · m 0,08 · t 0,07 · s 0,06 |

Samohlásky: *a* 0,31–0,37, *i* 0,20–0,26, *u*, *o*, *e* 0,10–0,15. Proto *r* a *l* zřídka začínají
slovo, ale často stojí uvnitř, a nosovky převažují na konci. Sdílí-li třídu víc hlásek inventáře
(*r* a *ɾ*), dělí se o její váhu. Hláska mimo třídy ASJP dostane průměrnou váhu pozice.

**Příchuť jazyka.** Jazyky se v četnostech liší: každá hláska jazyka dostane násobek
`exp(N(0; 0,5))`. ASJP dává mezi jazyky směrodatnou odchylku log podílu 0,72, jenže včetně šumu
krátkých seznamů (40–100 slov), proto bereme menší část (`LANGUAGE_SPREAD`).

**OCP.** Souhláska, která by zopakovala předchozí souhlásku slova, má váhu × 0,3 (Frisch,
Pierrehumbert a Broe 2004: sousední stejné souhlásky jsou v lexikonech vzácné). Dětská slova
(*mama*) tím omezená nejsou.

### 2. Slabičná stavba (WALS 12A) a fonotaktika kód

Jazyk má jednu ze tří staveb, zadanou ve spec (`LanguageSpec.syllables`: `simple`, `moderate`,
`complex`) nebo vylosovanou podle podílů ve WALS (13 / 56 / 31 %). Hodnoty typu změřené na slovech
ASJP jazyků, které WALS 12A zařazuje:

| typ (WALS) | jazyků WALS / doculectů ASJP | 1 / 2 / 3 / 4+ slabik | na samohlásku | na souhlásku | skupina na začátku | uvnitř | na konci | hlásek |
|---|---|---|---|---|---|---|---|---|
| jednoduchá (C)V | 61 / 153 | 0,22 / 0,50 / 0,21 / 0,07 | 0,30 | 0,05 | 0,05 | 0,05 | 0,00 | 4,41 |
| středně složitá | 274 / 913 | 0,30 / 0,48 / 0,17 / 0,05 | 0,19 | 0,36 | 0,04 | 0,16 | 0,02 | 4,45 |
| složitá | 151 / 301 | 0,38 / 0,46 / 0,12 / 0,03 | 0,19 | 0,54 | 0,08 | 0,19 | 0,07 | 4,40 |

Hezky je vidět vyrovnávání (Menzerath, Fenk-Oczlon a Fenk 1999): jazyky se složitou slabikou mají
méně slabik, takže délka slova v hláskách je u všech typů skoro stejná (~4,4).

Generátor bere tato čísla přímo:

- počet slabik podle rozdělení typu (posunutý Zipfem, bod 3);
- první slabika bez začáteční souhlásky s pravděpodobností „na samohlásku“;
- poslední slabika zavřená s pravděpodobností „na souhlásku“; uvnitř slova zavřená slabika
  s pravděpodobností dopočtenou tak, aby podíl slov se skupinou souhlásek uvnitř seděl;
- **jednoduchá**: bez kód a bez skupin (podle definice WALS; zbytek v ASJP jsou výpůjčky a zápis);
- **středně složitá**: na začátku slova ražená/třená + likvida či polosamohláska (*pr-*, *kw-*),
  na konci slabiky jedna souhláska;
- **složitá**: navíc *s* + neznělá ražená (*st-*, *sk-*, 30 % začátečních skupin) a koncové
  skupiny sonora + neznělá souhláska (*-nt*, *-rk*, *-ls*); *h* a *ʔ* ve skupinách nejsou.

**Fonotaktika kód** sleduje implikační hierarchii (Zec 1995; Blevins 2004): jazyk, který na konci
slabiky dovolí raženou, dovolí i sonory, a ten, který dovolí likvidy, dovolí i nosovky.
Středně složitý jazyk vylosuje jednu ze tří úrovní (jen nosovky — jako japonština či
mandarínština; sonory; všechny souhlásky), složitý dovoluje všechny. Konkrétní hláska na konci
se pak volí podle koncových vah ASJP.

### 3. Zipfův zákon zkracování

Časté pojmy mají kratší slova (Zipf 1935; Bentz a Ferrer-i-Cancho 2016). Cíl jsem změřil v ASJP:
Spearmanovo ρ mezi frekvencí pojmu (`v2_concept_frequencies.json`, Calude a Pagel 2011) a délkou
slova v hláskách uvnitř jazyka je v průměru přes rodiny **−0,135** (kvartily rodin −0,25 / −0,13 /
−0,04; záporné u 83 % z 508 rodin; −0,27 hlásky na řád frekvence). Efekt je u základní slovní
zásoby slabý, protože všechny pojmy jsou časté.

Generátor posune rozdělení počtu slabik: `P(k) ∝ P_typ(k) · exp(−β · z · k)`, kde `z` je
standardizovaný logaritmus frekvence pojmu v jazyce a β = 0,2 (`ABBREVIATION_BETA`), nastavené
tak, aby generované ρ sedělo na cíl.

### 4. Dětská slova pro rodiče

Murdock (1959; čísla z druhotného zdroje, článek jsem neměl v ruce) našel slabiku typu *ma*
ve slově „matka“ u 52 % jazyků (u otce 15 %) a *pa*/*ta* ve slově „otec“ u 55 % (u matky 7 %).
Jakobson (1962) to vysvětluje prvními slabikami dětského žvatlání: optimální souhláska + *a*,
nosovka souvisí s kojením. Kontrola na WOLD (41 jazyků, první tvar): nosovka ve slově „matka“ 71 %,
„otec“ 15 %; retná nebo zubná ražená (*p b t d*) ve slově „otec“ 73 %, „matka“ 22 %.

S pravděpodobností 0,55 (`NURSERY_SHARE`) dostane pojem `mother` dětské slovo z nosovky inventáře
(*m* 3 : *n* 2 : *ɲ* 1 : *ŋ* 0,5) a nejotevřenější samohlásky (*a*, jinak *ɛ*, *o*, *ə*), pojem
`father` z *p*, *b*, *t*, *d* (2 : 2 : 2 : 1). Tvar zhruba podle WOLD: zdvojený (*mama*, *baba*)
50 %, CV (*ma*) 25 %, VCV (*ama*, *apa*) 25 %. Jazyk bez nosovek dětské slovo pro matku nedostane.
Rodičovská slova se vybírají první, aby jim krátký tvar nevzalo jiné slovo.

### 5. Zvuková symbolika

Blasi a kol. (2016) našli v ASJP po kontrole příbuznosti a areálu 74 asociací (tab. S2–S3, převzaté
všechny). Kladné, např. „jazyk“–*l* (RR 2,77), „malý“–*i*
(1,58) a *tʃ* (5,12), „nos“–*n* (1,47), „plný“–*p* (2,11), „písek“–*s* (2,58), „kulatý“/„červený“–*r*;
záporné, např. „já“ a „ty“ se vyhýbají *l*, *r*, *p*, *t*, *s* (RR 0,18–0,44), „voda“–*t* (0,36).

U pojmu s asociací se váha hlásky dané třídy násobí `RR^γ`, γ = 1 (`SYMBOLISM_EXPONENT`). Protože
hláska stojí ve slově jen na některých místech, generované RR vychází slabší než publikované
(medián 0,75 log RR). To je záměr: preference má být slabá a jazyky se mají lišit.

### Ostatní

- Každý pojem má vlastní proud náhody (`protolanguage / word / pojem`), přidaný nebo autorem zadaný
  pojem tedy nezmění slova ostatních (kromě vzácné kolize stejných tvarů, kdy se slovo losuje znovu).
- Frekvence pojmů bez dat se losují ve vlastním proudu (`protolanguage / frequency`), jinak beze změny.
- Tóny tónových jazyků se připojují za samohlásku jako dosud (zipfovsky podle pořadí).
- Generátor už nezrcadlí Python (bitová shoda byla zrušena 3. 11.); proto zmizel test
  `vectors.rs::protojazyk` a vektor `tests/fixtures/protolanguage.json`.

## Ověření

`cargo run --release --example protojazyk -- mereni 300`: 300 semínek, výchozí pojmy, bohatší inventář
(`p t k b d ɡ m n ŋ s z ʃ tʃ l r w j h`, `a e i o u ɛ`):

| veličina | generováno | cíl (zdroj) |
|---|---|---|
| podíl typů jednoduchá / středně složitá / složitá | 0,10 / 0,57 / 0,33 | 0,13 / 0,56 / 0,31 (WALS) |
| na souhlásku končí (středně složitá / složitá) | 0,38 / 0,56 | 0,36 / 0,54 (ASJP) |
| na samohlásku začíná (jednoduchá / ostatní) | 0,25 / 0,17 | 0,30 / 0,19 (ASJP) |
| délka slova v hláskách | 4,3–4,5 | 4,4 (ASJP) |
| ρ(frekvence, délka), průměr; podíl záporných | −0,139; 97 % jazyků | −0,135; 83 % rodin (ASJP) |
| „matka“ s nosovkou / „otec“ s nosovkou | 0,81 / 0,19 | 0,71 / 0,15 (WOLD) |
| „otec“ s *p b t d* / „matka“ s *p b t d* | 0,76 / 0,20 | 0,73 / 0,22 (WOLD) |
| zvuková symbolika: směr RR | 71 z 71 shodně (3 asociace s *ɲ* a *q* inventář nemá) | Blasi a kol. 2016 |
| „jazyk“–*l*, „malý“–*tʃ*, „já“–*l*, „voda“–*t* | 2,36 · 3,14 · 0,29 · 0,38 | 2,77 · 5,12 · 0,19 · 0,36 |

Slov na samohlásku je o něco méně než v ASJP, protože jednohláskové slovo (*a*) generátor odmítá.
Záporné ρ má víc jazyků než v ASJP, protože generovaná slova nemají šum citačních tvarů (afixy).

Testy: `rust/cee_engine/tests/protoform.rs` (determinismus, jedinečnost a inventář, přednost
zadaných slov, nezávislost na přidaném pojmu, slabičná stavba, losování typů podle WALS, Zipf,
dětská slova, jazyk bez nosovek, zvuková symbolika) a `spec_check.rs::slabicna_stavba_se_overi`.

## Ukázky

`cargo run --release --example protojazyk -- ukazky 1 2 3 4` (výchozí pojmy, výchozí inventář;
vylosovaná slabičná stavba):

| semínko | stavba | já | ty | dva | matka | otec | voda | oheň | kámen | pes | nos | jazyk | malý | hora |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | složitá | twe | ɡona | tolo | bapo | bjitohams | pa | rahɡir | laku | sarurle | miribu | lorna | solnu | kim |
| 2 | jednoduchá | we | he | abu | ma | da | hine | olera | tata | waɡa | ejuhi | marera | tame | saba |
| 3 | jednoduchá | ni | mawi | pi | mama | tata | isu | jiditi | juhi | mino | jurako | irehe | ɡile | biki |
| 4 | středně složitá | manu | tu | bipwi | na | ik | nile | numme | mukone | hate | kiru | loɡulolril | tiwtorpi | te |

Generované jazyky Evropy (`src/cee/data/scenarios/evropa.json`, vlastní inventáře, tik 0):

| jazyk | | já | ty | dva | matka | otec | voda | oheň | slunce | pes | nos | jazyk | hora |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| iberština | dříve | liʃu | badem | tebom | noɾa | ɡela | naɾebat | datu | bo | beɾeme | bite | ɡabeta | kaba |
| | **nyní** | sel | sa | meɡan | mama | tata | osloʃ | ila | min | lana | bontuʃes | ɡe | boʃa |
| dáčtina | dříve | zopab | bebata | mi | liradu | ɡemema | ɡapemi | pa | kaz | dapipa | dureba | ko | de |
| | **nyní** | mana | eka | kuti | ama | papa | wilimi | lano | ti | uso | tajateji | taja | tanuke |
| baskičtina | dříve | deɡere | niʃe | tikokub | uko | boba | ʃeɾiɡe | seked | ɡadaku | tiʃobud | adeda | dotah | li |
| | **nyní** | daɾ | kon | ɡalɡoɾe | ha | liɾi | un | baʃe | naɡant͡s | t͡sis | biɾen | lunɡi | skade |

Baskický inventář ve scénáři nemá *m* ani *p* a matka tu dětské slovo nedostala (losovalo se
obecné slovo). Kdo chce určitou stavbu, zadá ji: `{"id": "basque", "syllables": "complex"}`.

## Dopad na brány a kalibraci

Nový generátor mění slova všech generovaných jazyků, i výchozího jazyka scénářů bran. `cee gates`
(semínka od 201): **47 z 47 před změnou i po ní**, prahy beze změny. Největší posuny:

| brána | před | po | práh | výklad |
|---|---|---|---|---|
| `m3::morfologizace` (podíl běhů) | 0,95 | 0,70 | ≥ 2 z 20 | závisí na tvaru koncovek; víc zavřených slabik a kratší častá slova mění, kde zvuková změna zasáhne hranici kmene |
| `m3::sturtevantuv_paradox` | 0,85 | 1,00 | ≥ 12 z 20 | |
| `m2::metrika_4` nejmenší / největší inventář samohlásek | 7,5 / 11 | 9 / 12 | pásmo [4; 7] / [5; 10], široké [2; 14] | nad úzkým pásmem byl už předtím; nová slova mají víc kód (hlavně nosovek, které ASJP dává na konec slova nejčastěji), a tedy pravděpodobně víc prostředí pro nosové a dloužené samohlásky (neověřeno) |
| `m2::metrika_6` podíl souhláskových změn | 0,63 | 0,57 | [0,25; 0,75] | |
| homofonní slova (m4, kontrola) | 0,013 | 0,000 | [0; 0,05] | |

Ostatní brány se pohnuly o méně než 5 %. Růst inventáře samohlásek nad běžné pásmo je
samostatný jev simulace (ne generátoru) a stojí za vlastní rozbor.

Test `sound.rs::proces_pod_prahem_nepise_a_neuzavre_se` počítal události `phonologized`
v celém světě; s novými slovy se v 6 krocích fonologizovala jiná, přirozeně vzniklá změna
(spirantizace *b* ve vesnici v01-03). Test teď počítá jen události svého procesu a skupiny,
jak zamýšlel.

**Kalibrace** (`cee calibrate`, semínka od 1; Evropa s `RAYON_NUM_THREADS=3`, jinak se plný běh
nevejde do 16 GB): **stejný souhrn před změnou i po ní**, 21 z 24 (bez Evropy) a 13 z 14 (Evropa).
Romanie a Evropa s generovanými substráty (iberština, dáčtina, baskičtina) zůstaly beze změny
splněných cílů; retence latiny 0,619 → 0,614, počet jazyků v roce 1900 81,5 → 79,5 (cíl 10–60
nesplněný už předtím).

| cíl | před | po | práh | |
|---|---|---|---|---|
| `m9::tempo` zrychlení kontaktem | 2,45 | 1,92 | [1; 2] | nově splněno |
| `m9::tempo` bez kontaktu | 0,060 | 0,077 | [0,30; 0,85] | nesplněno (dok. 24) |
| `m7::typologie_37A` konec (Hellinger) | 0,088 | 0,150 | ≤ 0,112 | nově nesplněno, viz níže |
| `m7::typologie_33A` konec | 0,056 | 0,092 | ≤ 0,098 | |
| `m7::typologie_67A` konec | 0,123 | 0,123 | ≤ 0,111 | nesplněno už předtím |

37A je na hraně i se starým generátorem: na dalších semínkách (`--seeds 101/201/301`) vychází
před změnou 0,173 / 0,173 / 0,129 a po ní 0,129 / 0,222 / 0,150, tedy nad prahem v obou verzích.
Splnění na semínkách od 1 bylo předtím štěstí; rozdíl je v šumu a stálost členu (37A) je otevřená
nezávisle na generátoru.

## Omezení a další kroky

- Inventář se negeneruje; výchozí inventář je pořád stejný pro všechny vygenerované jazyky
  (kromě příchuti vah). Generování inventáře podle PHOIBLE (CC BY 4.0 na GitHubu) by byl další krok.
- Váhy jsou podmíněné přítomností třídy v krátkém seznamu ASJP, takže vzácné třídy (mlaskavky,
  ʔ na konci) vycházejí v jazycích, které je mají, vysoké; s běžnými inventáři to nevadí.
- Odvozovací přípony (`generated_suffixes`) se pořád losují z prvních hlásek seznamu.
- Tvary jsou kořeny bez morfologie; ASJP obsahuje citační tvary (někdy s afixy), proto je cíl
  délky jen orientační.
- Tóny a délka samohlásek nemají data (tóny zipfovsky podle pořadí jako dřív).

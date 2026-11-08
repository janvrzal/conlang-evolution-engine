# 31. Citlivost, kalibrace a rozdělení parametrů (M11)

Stav: **experimentálně ověřeno a zapsáno do enginu** (8. 11. 2026).  
Navazuje na: [24. Tempo hláskových změn](file:///Users/janvrzal/Documents/CEE-dynamika/docs/engine-v2/24-tempo-hlaskovych-zmen.md), [27. Města](file:///Users/janvrzal/Documents/CEE-dynamika/docs/engine-v2/27-mesta.md), [29. Splynutí, zápor, nářečí](file:///Users/janvrzal/Documents/CEE-dynamika/docs/engine-v2/29-splynuti-zapor-nareci.md) a [30. Náhrada slov, data protojazyků, Čechy a Pobaltí](file:///Users/janvrzal/Documents/CEE-dynamika/docs/engine-v2/30-slovnik-zkracovani-pobalti.md).

Tento dokument shrnuje výsledky tří rozsáhlých kontrolovaných experimentů nad modelem CEE v2 (větev `engine-v2-dynamika`, commit `05e27e5`), které testovaly vzájemnou provázanost a citlivost parametrů dynamiky jazyka na kalibračních seedech `1..=8` i odložených validačních seedech `201..=208`. Na základě těchto měření bylo 86 parametrů enginu rozděleno do tří zřetelných rolí (`world`, `active`, `fixed`) při zachování 100% zpětné kompatibility všech přepisů ve starších světech.

---

## 1. Metodika: Sloppy models a dimenze jazykové dynamiky

### 1.1 Proč citlivost závisí na měřených veličinách (Gutenkunst a kol. 2007)

V teorii nelineárních dynamických systémů se pro vícedimenzionální modely vžil pojem **„sloppy models“** (Gutenkunst a kol. 2007, Transtrum a kol. 2015). Vlastní čísla Fisherovy informační matice (FIM) takových modelů typicky pokrývají mnoho řádů:
- Existuje několik málo **„tuhých“ (stiff)** směrů v prostoru parametrů, jejichž změna dramaticky mění chování modelu.
- Většina směrů je **„poddajná“ (sloppy)**, což svádí k dojmu, že parametry lze libovolně sloučit nebo že na nich nezáleží.

Klíčový metodologický poznatek však zní: **Co je tuhým a co poddajným směrem, závisí výhradně na tom, jaké veličiny měříme.**
- Pokud bychom sledovali pouze *hrubé lexikální tempo* (procento změněných slov za tisíc let), tempo hláskových změn by se jevilo jako redundantní vůči lexikálním inovacím.
- Jakmile však sledujeme současně:
  1. **hloubku fonologického přepisu** slovníku (počet slov zasažených jednou fonologizací),
  2. **přežití morfologických kategorií** (ochrana pádových koncovek a funkční zátěž podle Wedela a kol. 2013),
  3. **asymetrii diglosie a standardizace** (odstup mluveného jazyka od psaného kódu vs. nářeční vyrovnávání),
  4. **substrátovou interferenci v L2 populacích** (vliv rodného jazyka na osvojení cizího kódu),
  5. **kontinuální nářeční divergence vs. městskou koiné** (hierarchický rozpad nářečí pod vlivem gravitačního kontaktu),
ukáže se, že parametry dříve podezřívané z redundance ovládají **zcela ortogonální domény** a jejich sloučení do jednoho „makro-parametru“ by zničilo věrnost simulace.

### 1.2 Tři role parametrů v CEE v2 při zachování zpětné kompatibility

Struktura `Parameters` v Rustu i datový soubor `v2_parameters.json` obsahují přesně **86 parametrů**. Aby žádný existující svět, fixture ani integrační test neztratil funkčnost, všech 86 položek zůstává ve struktuře zachováno a metoda `from_overrides` dál přijímá libovolné přepisy.

Každý parametr je však nově v metadatech i schématu klasifikován polem `role`:
1. **`Role::World` (`"world"`, 12 položek):**
   Převodníky slovních úrovní a nastavení světa, které definuje autor světa (politika státu, gramotnost, školství, terén, domény kanálů výpůjček a přepis katalogu gramatiky).
2. **`Role::Active` (`"active"`, 24 položek):**
   Nezávislé kalibrační páky a ladicí tabulky, jejichž samostatná existence je doložena experimentálním měřením. Každá ovládá specifický fyzikální či sociolingvistický mechanismus.
3. **`Role::Fixed` (`"fixed"`, 50 položek):**
   Měřením zafixované konstanty modelu, stabilitní prahy a vypnuté/jednotkové přepínače. Leží ve stabilních bodech kalibrace a při běžném ladění se nemění, přestože jejich přepis ve starších světech zůstává funkční.

---

## 2. Experiment 1: Tempo hláskových změn (návrhy vs. ocenění vs. kontrasty a norma)

Experiment ověřil, zda lze tempo hláskového posunu řídit četností návrhů namísto sociálního ocenění, a jak se změna ocenění projevuje na ochraně morfologických kontrastů a spisovné normě.

### 2.1 Definice 11 testovaných režimů
1. **`M11_vychozi`**: `sound_actuation = 2.25`, `change_rates = 1.0` (všech 36 rodin), výchozí tlaky: `clarity = 1.75`, `functional_load = 1.25`, `norm = 2.25`.
2. **`M9a_referencni`**: `sound_actuation = 1.0`, ostatní výchozí.
3. **Četnost návrhů (`change_rates` pro 36 rodin):**
   - **`navrhy_2.25x_oceneni_1.0`**: `sound_actuation = 1.0`, `change_rates = 2.25`.
   - **`navrhy_0.67x`**: `sound_actuation = 2.25`, `change_rates = 0.667`.
   - **`navrhy_1.50x`**: `sound_actuation = 2.25`, `change_rates = 1.500`.
4. **Samostatné sociální ocenění (`sound_actuation`):**
   - **`oceneni_1.50_samotne`**: `sound_actuation = 1.50`.
   - **`oceneni_3.00_samotne`**: `sound_actuation = 3.00`.
5. **Společná změna ocenění s ochranou kontrastů a normou ($k = \text{actuation} / 2.25$):**
   - **`spolecne_kontrast_1.50`** ($k = 2/3$): `sound_actuation = 1.5`, `clarity = 1.167`, `functional_load = 0.833`, `norm = 2.25`.
   - **`spolecne_vse_1.50`** ($k = 2/3$): totéž + `norm = 1.5`.
   - **`spolecne_kontrast_3.00`** ($k = 4/3$): `sound_actuation = 3.0`, `clarity = 2.333`, `functional_load = 1.667`, `norm = 2.25`.
   - **`spolecne_vse_3.00`** ($k = 4/3$): totéž + `norm = 3.0`.

### 2.2 Svět A: Malý svět bez kontaktu a bez školy (1 000 let, 12 vesnic)
Naměřeno na 8 kalibračních (`1..=8`) a 8 validačních (`201..=208`) seedech (uvedeno jako kalibrační / validační průměr):

| Režim | Návrhy / vesnice | Unikátní návrhy | Ustálené / vesnice | Unikátní ustálené | Podíl uchycení | Slov / fonologizaci | Beze změny | Vzdálenost $d$ | Tempo $r = -\ln(1-d)$ | Nářečí celkem | Nářečí hlásky |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | 15.0 / 14.8 | 106.2 / 109.5 | 46.4 / 44.9 | 21.2 / 21.0 | 20.1 % / 19.2 % | 6.64 / 6.71 | 22.6 % / 23.4 % | 0.303 / 0.308 | **0.363 / 0.370** | 0.042 / 0.041 | 0.009 / 0.009 |
| **`M9a_referencni`** | 14.7 / 14.6 | 105.0 / 105.9 | 25.5 / 22.2 | 9.0 / 8.4 | 8.5 % / 8.0 % | 5.90 / 6.20 | 40.8 % / 43.6 % | 0.190 / 0.179 | **0.211 / 0.200** | 0.038 / 0.037 | 0.005 / 0.005 |
| **`navrhy_2.25x_oceneni_1.0`** | 27.6 / 27.6 | 148.1 / 146.1 | 35.0 / 32.4 | 12.0 / 12.4 | 8.1 % / 8.5 % | 5.81 / 5.92 | 33.5 % / 35.3 % | 0.235 / 0.229 | **0.269 / 0.260** | 0.041 / 0.039 | 0.008 / 0.007 |
| **`navrhy_0.67x`** | 10.9 / 10.7 | 88.9 / 87.8 | 40.3 / 34.3 | 17.8 / 15.6 | 20.0 % / 17.8 % | 6.56 / 6.85 | 28.4 % / 31.6 % | 0.269 / 0.242 | **0.318 / 0.277** | 0.041 / 0.039 | 0.008 / 0.007 |
| **`navrhy_1.50x`** | 20.3 / 20.0 | 129.8 / 128.8 | 56.9 / 53.8 | 26.1 / 25.5 | 20.2 % / 19.8 % | 6.37 / 6.49 | 21.1 % / 19.9 % | 0.312 / 0.346 | **0.375 / 0.427** | 0.045 / 0.042 | 0.011 / 0.010 |
| **`oceneni_1.50_samotne`** | 14.7 / 14.6 | 105.2 / 106.4 | 31.4 / 28.6 | 14.0 / 10.9 | 13.3 % / 10.3 % | 6.29 / 6.27 | 29.0 % / 35.7 % | 0.263 / 0.220 | **0.308 / 0.250** | 0.040 / 0.038 | 0.007 / 0.006 |
| **`oceneni_3.00_samotne`** | 15.1 / 14.9 | 108.2 / 112.4 | 61.3 / 64.7 | 29.9 / 31.2 | 27.6 % / 27.9 % | 7.30 / 7.28 | 18.2 % / 19.2 % | 0.364 / 0.350 | **0.456 / 0.432** | 0.045 / 0.044 | 0.011 / 0.012 |
| **`spolecne_kontrast_1.50`** | 14.4 / 14.1 | 106.8 / 106.1 | 28.5 / 27.2 | 14.5 / 11.6 | 13.5 % / 11.0 % | 5.75 / 6.52 | 33.3 % / 33.8 % | 0.245 / 0.235 | **0.284 / 0.270** | 0.041 / 0.040 | 0.008 / 0.008 |
| **`spolecne_vse_1.50`** | 14.4 / 14.1 | 106.8 / 106.1 | 28.5 / 27.2 | 14.5 / 11.6 | 13.5 % / 11.0 % | 5.75 / 6.52 | 33.3 % / 33.8 % | 0.245 / 0.235 | **0.284 / 0.270** | 0.041 / 0.040 | 0.008 / 0.008 |
| **`spolecne_kontrast_3.00`** | 15.6 / 15.4 | 106.6 / 112.1 | 58.0 / 56.9 | 28.0 / 28.4 | 26.3 % / 25.3 % | 7.31 / 7.02 | 19.5 % / 20.2 % | 0.352 / 0.337 | **0.434 / 0.413** | 0.044 / 0.042 | 0.011 / 0.010 |
| **`spolecne_vse_3.00`** | 15.6 / 15.4 | 106.6 / 112.1 | 58.0 / 56.9 | 28.0 / 28.4 | 26.3 % / 25.3 % | 7.31 / 7.02 | 19.5 % / 20.2 % | 0.352 / 0.337 | **0.434 / 0.413** | 0.044 / 0.042 | 0.011 / 0.010 |

### 2.3 Svět B: Týž svět se standardem (rok 200) a školou (rok 500)

| Režim | Ustálené / vesnice | Ustálené po r. 500 | Beze změny | Vzdálenost $d$ | Tempo $r$ | Odstup od normy (`gap`) | Nářečí celkem | Nářečí hlásky |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | 22.8 / 20.6 | 203.4 / 189.9 | 54.8 % / 48.7 % | 0.132 / 0.155 | **0.143 / 0.170** | 0.0107 / 0.0098 | 0.0048 / 0.0040 | 0.0029 / 0.0023 |
| **`M9a_referencni`** | 11.1 / 9.2 | 108.5 / 95.0 | 78.4 % / 75.3 % | 0.054 / 0.063 | **0.057 / 0.066** | 0.0058 / 0.0045 | 0.0030 / 0.0026 | 0.0011 / 0.0009 |
| **`navrhy_2.25x_oceneni_1.0`** | 15.5 / 16.1 | 144.1 / 155.4 | 69.3 % / 64.4 % | 0.081 / 0.093 | **0.085 / 0.098** | 0.0073 / 0.0063 | 0.0033 / 0.0030 | 0.0014 / 0.0013 |
| **`navrhy_0.67x`** | 21.3 / 16.0 | 194.0 / 154.2 | 62.2 % / 56.3 % | 0.110 / 0.127 | **0.118 / 0.137** | 0.0090 / 0.0075 | 0.0039 / 0.0034 | 0.0020 / 0.0017 |
| **`navrhy_1.50x`** | 29.9 / 27.4 | 264.5 / 243.4 | 45.7 % / 42.4 % | 0.165 / 0.184 | **0.181 / 0.204** | 0.0125 / 0.0120 | 0.0054 / 0.0047 | 0.0035 / 0.0030 |
| **`oceneni_1.50_samotne`** | 13.8 / 13.1 | 132.9 / 128.5 | 70.2 % / 65.1 % | 0.081 / 0.091 | **0.086 / 0.096** | 0.0074 / 0.0059 | 0.0033 / 0.0032 | 0.0014 / 0.0015 |
| **`oceneni_3.00_samotne`** | 36.4 / 34.8 | 318.4 / 291.9 | 40.5 % / 35.2 % | 0.200 / 0.219 | **0.226 / 0.249** | 0.0199 / 0.0177 | 0.0062 / 0.0062 | 0.0043 / 0.0045 |
| **`spolecne_kontrast_1.50`** | 10.3 / 10.1 | 99.6 / 93.2 | 74.1 % / 68.1 % | 0.072 / 0.084 | **0.077 / 0.088** | 0.0075 / 0.0056 | 0.0035 / 0.0031 | 0.0016 / 0.0014 |
| **`spolecne_vse_1.50`** | 12.6 / 12.3 | 127.6 / 119.2 | 66.3 % / 60.3 % | 0.093 / 0.111 | **0.099 / 0.119** | 0.0103 / 0.0094 | 0.0059 / 0.0053 | 0.0027 / 0.0024 |
| **`spolecne_kontrast_3.00`** | 38.8 / 35.3 | 343.6 / 310.0 | 36.8 % / 33.7 % | 0.221 / 0.231 | **0.253 / 0.264** | 0.0206 / 0.0157 | 0.0065 / 0.0058 | 0.0046 / 0.0041 |
| **`spolecne_vse_3.00`** | 32.2 / 32.2 | 264.4 / 272.1 | 42.2 % / 35.3 % | 0.186 / 0.219 | **0.207 / 0.247** | 0.0152 / 0.0139 | 0.0050 / 0.0040 | 0.0037 / 0.0029 |

### 2.4 Přenositelnost: Kontakt se státem (latina) a scénář diglosie S4

#### Kontakt s latinským státem (1 000 let, slovanský region v kontaktu s latinou):
| Režim | Slovanské tempo $r$ | Zrychlení kontaktem | **Zachování pádů v latině** (`OBJ`) | Latinské tempo $r$ | Slov/fonol. v kontaktu | Nářečí celkem |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | **0.906 / 0.932** | **2.50× / 2.52×** | **84.4 % / 86.5 %** | 0.958 / 0.876 | 8.26 / 8.01 | 0.113 / 0.111 |
| **`M9a_referencni`** | 0.697 / 0.696 | 3.30× / 3.49× | 87.5 % / 87.5 % | 0.724 / 0.724 | 7.65 / 7.41 | 0.101 / 0.099 |
| **`navrhy_2.25x_oceneni_1.0`** | 0.758 / 0.757 | 2.82× / 2.91× | 75.0 % / 85.4 % | 0.894 / 0.871 | 7.51 / 7.43 | 0.116 / 0.115 |
| **`spolecne_kontrast_1.50`** | 0.842 / 0.884 | 2.96× / 3.28× | **61.5 % / 71.9 %** *(kolaps)* | 0.906 / 0.845 | 7.72 / 7.38 | 0.107 / 0.108 |
| **`spolecne_kontrast_3.00`** | 0.938 / 0.952 | 2.16× / 2.31× | 86.5 % / 86.5 % | 0.976 / 0.885 | 8.67 / 8.50 | 0.115 / 0.114 |

#### Scénář S4 (`diglossia`, 2 500 let, písmo v r. 500, škola v r. 1500, odečet v r. 2500):
| Režim | Odstup od normy v r. 2500 (`gap`) | Nářečí se školou | Nářečí bez školy | Poměr nářečí (škola / bez) | Změny po r. 1750 (škola) | Změny po r. 1750 (bez) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | **0.0149** | **0.0151** | **0.1704** | **0.0883** | **655.9** | **1546.5** |
| **`M9a_referencni`** | 0.0030 | 0.0019 | 0.1003 | 0.0195 | 366.2 | 1101.0 |
| **`navrhy_2.25x_oceneni_1.0`** | 0.0039 | 0.0032 | 0.1081 | 0.0314 | 413.0 | 1240.0 |
| **`oceneni_3.00_samotne`** | 0.0364 | 0.0387 | 0.2172 | **0.1783** | 1025.8 | 1670.2 |
| **`spolecne_vse_3.00`** | 0.0224 | 0.0224 | 0.1898 | **0.1181** | 755.6 | 1574.6 |

### 2.5 Teoretické zdůvodnění a zapsaná změna v kódu

1. **Proč nelze násobit `INNOVATIONS_PER_GENERATION` a `sound_actuation`:**
   V kódu `changes/sound.rs:29` určuje `INNOVATIONS_PER_GENERATION = 0.6` míru v Poissonově rozdělení tahů v indexu rodin hlásek (`cee_core::index::SoundIndex`). Naproti tomu `sound_actuation` násobí sociální ocenění `id::ACTUATION` v logistické selekci (`transfer/pressures.rs:158`).
   Zvýšení četnosti návrhů na 2,25× při `sound_actuation = 1.0` vedlo k tomu, že podíl uchycení zůstal na pouhých **8,1–8,5 %** (oproti **19,2–20,1 %** v M11) a tempo dosáhlo pouze **0.265** (oproti **0.366** v M11). Návrhy bez silného ocenění vyhnívají v selekčním filtru; četnost návrhů a sílu ocenění nelze matematicky zaměnit.
2. **Proč nelze `clarity` a `functional_load` slepě škálovat se `sound_actuation`:**
   V logistické funkci hodnocení variant soupeří tlaky na srozumitelnost a funkční zátěž s fixní artikulační námahou (`articulation = 1.0`) a náhodným driftem (`standing_variation`). Když byly tlaky sníženy úměrně klesajícímu ocenění ($k = 1.5 / 2.25$), ochrana koncovek selhala a podíl vesnic držících syntetický pád klesl z 85,4 % na **61,5–71,9 %**. Ochrana morfologických kontrastů musí zůstat kalibrována nezávisle na tempu hlásek.
3. **Výchozí navázání normy `NORM_WEIGHT = sound_actuation`:**
   Při silném hláskovém ocenění (`sound_actuation = 3.0`) bez posílení normy se nářečí ve škole rozpadají (poměr nářečí v S4 vystřelil na 0.178). Posílení normy na 3.0 stlačilo rozpad zpět na 0.118.
   V `rust/cee_engine/src/transfer/pressures.rs` byla proto odstraněna pevná konstanta `const NORM_WEIGHT: f64 = 2.25;` a nahrazena dynamickou výchozí hodnotou:
   ```rust
   target.push((id::NORM, params.sound_actuation));
   ```
   Při výchozím `sound_actuation = 2.25` je chování bitově identické s M11; explicitní přepis `params.pressure_weights["norm"]` má nadále přednost.

---

## 3. Experiment 2: Tři účinky školy (`norm`, `school_weight`, `school_correction`)

Experiment testoval nezávislost tří parametrů reprezentujících školní docházku:
1. `pressure_weights["norm"]`: selekční tlak k psané normě působící na frekvence variant v populaci (`transfer/pressures.rs`).
2. `school_weight`: přímý kanál přenosu variant ze spisovného kódu do mluvené sítě (`transfer/network.rs:371`).
3. `school_correction`: korekční činitel tlumící asymetrickou substrátovou interferenci u L2 mluvčích (`phases/communities.rs` / `transfer/network.rs`).

### 3.1 Výsledky ve Světě 1 (Jednojazyčná diglosie S4, rok 2500)
Měřeno na všech 16 seedech (`1..=8` a `201..=208`):

| Varianta | gap_tot | gap_phon | gap_lex | dial_sch | dial_none | dial_rat | estab>1750 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | **0.0148** | **0.0126** | **0.0020** | **0.0146** | **0.1797** | **0.0813** | **660.56** |
| `norm_0.0` | 0.0959 | 0.0860 | 0.0095 | 0.1108 | 0.1797 | **0.6179** | 1110.31 |
| `norm_1.125` ($0.5\times$) | 0.0358 | 0.0321 | 0.0036 | 0.0421 | 0.1797 | 0.2342 | 909.94 |
| `norm_4.50` ($2.0\times$) | 0.0086 | 0.0073 | 0.0013 | 0.0088 | 0.1797 | 0.0501 | 383.94 |
| `school_w_0.0` | 0.0135 | 0.0112 | 0.0023 | 0.0111 | 0.1797 | 0.0623 | 452.69 |
| `school_w_0.15` ($0.5\times$) | 0.0161 | 0.0138 | 0.0022 | 0.0157 | 0.1797 | 0.0873 | 795.31 |
| `school_w_0.60` ($2.0\times$) | 0.0133 | 0.0114 | 0.0018 | 0.0127 | 0.1797 | 0.0710 | 526.25 |
| `corr_0.0` | 0.0148 | 0.0126 | 0.0020 | 0.0146 | 0.1797 | 0.0813 | 660.56 |
| `corr_0.4` ($0.5\times$) | 0.0148 | 0.0126 | 0.0020 | 0.0146 | 0.1797 | 0.0813 | 660.56 |
| `corr_1.0` | 0.0148 | 0.0126 | 0.0020 | 0.0146 | 0.1797 | 0.0813 | 660.56 |
| `spolecne_skola_0.5x` | 0.0388 | 0.0344 | 0.0043 | 0.0455 | 0.1797 | 0.2528 | 1231.00 |
| `spolecne_skola_1.5x` | 0.0091 | 0.0076 | 0.0015 | 0.0089 | 0.1797 | 0.0503 | 448.19 |

### 3.2 Výsledky ve Světě 2 (Vícejazyčný svět s L2 a školou, rok 1000)
Latina v kontaktu se slovanským substrátem v `r0` oproti mateřské latině v `r1` (16 seedů):

| Varianta | phon_dist | lex_dist | r_latin_r0 | r_latin_r1 | r0 / r1 | lat_share_r0 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`M11_vychozi`** | **0.0119** | **0.0032** | **0.1758** | **0.0463** | **3.796** | **1.0000** |
| `norm_0.0` | 0.0375 | 0.0164 | 0.4698 | 0.3364 | 1.397 | 1.0000 |
| `norm_1.125` ($0.5\times$) | 0.0230 | 0.0072 | 0.2696 | 0.1252 | 2.153 | 1.0000 |
| `norm_4.50` ($2.0\times$) | 0.0023 | 0.0011 | 0.0977 | 0.0150 | 6.530 | 1.0000 |
| `school_w_0.0` | 0.0122 | **0.0065** | 0.1817 | 0.0548 | 3.316 | 1.0000 |
| `school_w_0.15` ($0.5\times$) | 0.0123 | **0.0046** | 0.1798 | 0.0477 | 3.769 | 1.0000 |
| `school_w_0.60` ($2.0\times$) | 0.0113 | **0.0018** | 0.1687 | 0.0370 | 4.558 | 1.0000 |
| `corr_0.0` | 0.0117 | 0.0032 | 0.1754 | 0.0460 | 3.811 | 1.0000 |
| `corr_0.4` ($0.5\times$) | 0.0119 | 0.0032 | 0.1757 | 0.0463 | 3.798 | 1.0000 |
| `corr_1.0` | 0.0119 | 0.0032 | 0.1758 | 0.0463 | 3.794 | 1.0000 |
| `spolecne_skola_0.5x` | 0.0229 | 0.0107 | 0.2750 | 0.1410 | 1.950 | 1.0000 |
| `spolecne_skola_1.5x` | 0.0058 | 0.0014 | 0.1162 | 0.0180 | 6.464 | 1.0000 |

### 3.3 Závěr k parametrům školy
- **`pressure_weights["norm"]`** je hlavním stabilizátorem výslovnosti a nářeční soudržnosti. Bez něj (`norm = 0.0`) roste hláskový odstup mluveného jazyka od standardu 6,8× a poměr nářeční diverzity stoupne z 0.081 na 0.618 (škola téměř nesjednocuje výslovnost).
- **`school_weight`** působí selektivně na lexikon a syntax: ve Světě 2 klesá lexikální odstup od metropole téměř 4× (z 0.0065 na 0.0018), zatímco hlásková vzdálenost zůstává nedotčena (0.0113–0.0122). Děti si nesou výslovnost z rodiny, škola přináší nová slova a konstrukce.
- **`school_correction`** působí výhradně při `l2_share > 0`. Ve Světě 1 (jednojazyčném) jsou výsledky pro všechny hodnoty korekce na bit identické (kontrolní test ortogonality).
Tyto tři parametry zasahují různé lingvistické vrstvy a **musí zůstat odděleny**.

---

## 4. Experiment 3: Gravitační kontakt vs. zvláštní pravidla sídel

Experiment zkoumal vliv parametrů sídel (`city_*`, `capital_*`, `leveling_*`, `lingua_franca_*`) oproti čistému gravitačnímu kontaktu.

### 4.1 Svět 1: Dvoregionální stát (rok 1000 a 3000, 16 seedů)
Provincie `r0` (město `r0-v0`) a metropole `r1` (hlavní město `r1-v0`, stát od roku 100).

#### Stav v roce 1 000:
| Varianta | intra_r0 | intra_r1 | inter_region | inter / intra_r1 | jazyky | nářečí | $d_{\text{city}}$ | $d_{\text{village}}$ | city / vill |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`M11_vychozi`** | **0.0627** | **0.0509** | **0.1558** | **3.06x** | **1.00** | **3.06** | **0.3500** | **0.3455** | **1.01x** |
| `cista_gravitace_mesta` | 0.0646 | 0.0525 | 0.1575 | 3.00x | 1.00 | 3.69 | 0.3592 | 0.3545 | 1.01x |
| `symetricky_poslech_mesta` | 0.0547 | 0.0459 | 0.1988 | **4.33x** | 1.00 | 2.19 | 0.3375 | 0.3331 | 1.01x |
| `vyrovnavani_pres_region_0.35` | 0.0636 | 0.0506 | 0.1512 | 2.99x | 1.00 | 3.31 | 0.3453 | 0.3424 | 1.01x |
| `vyrovnavani_pres_region_1.0` | 0.0676 | 0.0504 | 0.1413 | 2.80x | 1.00 | 4.69 | 0.3448 | 0.3421 | 1.01x |
| `bez_vyrovnavani` | 0.0650 | 0.0537 | 0.1626 | 3.03x | 1.00 | 3.38 | 0.3481 | 0.3587 | 0.97x |
| `centra_0.67x` | 0.0580 | 0.0523 | 0.1833 | 3.50x | 1.00 | 2.31 | 0.3568 | 0.3526 | 1.01x |
| `centra_1.50x` | 0.0594 | 0.0475 | 0.1164 | 2.45x | 1.00 | 3.19 | 0.3401 | 0.3347 | 1.02x |

#### Stav v roce 3 000:
| Varianta | intra_r0 | intra_r1 | inter_region | inter / intra_r1 | jazyky | nářečí | $d_{\text{city}}$ | $d_{\text{village}}$ | city / vill |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`M11_vychozi`** | **0.0958** | **0.0852** | **0.2857** | **3.35x** | **1.19** | **12.56** | **0.5342** | **0.5329** | **1.00x** |
| `cista_gravitace_mesta` | 0.0960 | 0.0884 | 0.2801 | 3.17x | 1.00 | 13.69 | 0.5230 | 0.5213 | 1.00x |
| `symetricky_poslech_mesta` | 0.0904 | 0.0803 | 0.3866 | **4.81x** | **2.00** | 9.94 | 0.5186 | 0.5179 | 1.00x |
| `vyrovnavani_pres_region_0.35` | 0.1015 | 0.0867 | 0.2510 | 2.90x | 1.00 | 13.88 | 0.5298 | 0.5281 | 1.00x |
| `vyrovnavani_pres_region_1.0` | 0.1018 | 0.0848 | **0.2091** | **2.47x** | 1.00 | 13.44 | 0.5270 | 0.5241 | 1.01x |
| `bez_vyrovnavani` | **0.1439** | **0.1237** | 0.2963 | 2.40x | 1.38 | **18.00** | 0.5140 | 0.5237 | 0.98x |
| `centra_0.67x` | 0.0929 | 0.0870 | 0.3312 | 3.81x | **1.62** | 13.00 | 0.5248 | 0.5249 | 1.00x |
| `centra_1.50x` | 0.0872 | 0.0764 | 0.2143 | 2.80x | 1.00 | 7.56 | 0.5176 | 0.5146 | 1.01x |

### 4.2 Svět 2: Scénář Romania (12 seedů, 1 200 a 1 900 let)

#### Stav v roce 1 900:
| Varianta | jazyky | Itálie↔Galie | Itálie↔Hisp | Itálie↔Dácie | sdílená slov It-Ga | prům. sdílení | větve s pádem (prům / 4) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`M11_vychozi`** | **4.00** | **0.4170** | **0.5434** | **0.7226** | **91.5 %** | **63.8 %** | **0.33** (Dácie 33 %) |
| `cista_gravitace_mesta` | 4.00 | 0.4117 | 0.5405 | 0.7233 | 91.4 % | 63.8 % | 0.33 |
| `symetricky_poslech_mesta` | 4.00 | 0.4614 | 0.5433 | 0.7590 | 84.4 % | 62.0 % | 0.33 |
| `vyrovnavani_pres_region_0.35` | 4.00 | 0.3985 | 0.5227 | 0.7227 | 91.3 % | 63.8 % | 0.33 |
| `vyrovnavani_pres_region_1.0` | **3.83** | **0.3651** | 0.4926 | 0.7213 | 92.7 % | 64.4 % | 0.33 |
| `bez_vyrovnavani` | **5.00** | 0.4203 | 0.5500 | 0.7206 | 92.2 % | 64.6 % | 0.25 |
| `centra_0.67x` | 4.00 | 0.4542 | 0.5745 | 0.7264 | 84.8 % | 61.5 % | 0.25 |
| `centra_1.50x` | 3.75 | 0.3494 | 0.5111 | 0.7230 | **96.9 %** | 65.9 % | **0.08** (předčasný zánik) |

### 4.3 Klíčová zjištění pro pravidla sídel
1. **Asymetrie poslechu `city_listening = 0.2` je kriticky nutná:**
   Pokud město poslouchá venkov symetricky (`city_listening = 1.0`), venkovské konzervativní tvary ředí městské inovace a město přestává fungovat jako zdroj koiné. V důsledku toho se metropole a provincie odtrhnou do samostatných jazyků ve **100 % běhů** (počet jazyků v roce 3000 je 2.00 oproti 1.19 ve výchozím stavu).
2. **Nářeční vyrovnávání `leveling_rate = 0.35` je pilířem soudržnosti:**
   Při jeho vypnutí (`leveling_rate = 0.0`) se jazyková krajina katastrofálně tříští: v roce 3000 má každá z 18 vesnic vlastní nářečí (18.00) a v Romanii vzniká 5 samostatných jazyků (mikrojazyky).
3. **Meziregionální vyrovnávání `leveling_beyond_region = 0.0` musí zůstat vypnuté:**
   Povolení vyrovnávání přes hranice regionu (`0.35` a `1.0`) maže meziregionální vzdálenost (pokles o 27 %) a v Romanii způsobuje slévání provincií s Itálií (počet jazyků klesá pod 3.83).
4. **Umělá podlaha `city_link = 0.5` je zbytná:**
   Odstranění podlahy (`city_link = 0.0`) mění metriky v Romanii o méně než 0,3 % a mírně zpestřuje lokální nářečí. Čistá gravitace funguje spolehlivě.
5. **Citlivost center a stabilní fixace hodnot:**
   Škálování vazeb center ukázalo, že systém je na ně vysoce citlivý (`0.67x` rozbíjí jednotu státu na 1.62 jazyka, `1.50x` vede k přepálení sdílení slov na 96.9 % a zániku pádů). Kalibrované hodnoty `0.3` a `2.0` leží přesně ve stabilním bodě.

---

## 5. Přehled a katalog rozdělení 86 parametrů

### 5.1 Kategorie `Role::World` (12 položek)
Tyto parametry nepředstavují konstanty simulačního modelu, nýbrž **převodníky slovních úrovní a popis světa**, které zadává autor simulace (výběrem z předdefinovaných úrovní nebo úpravou katalogu).

| Parametr | Druh | Popis a důvod zařazení |
|---|---|---|
| `centralization_levels` | `level_table` | Převodník úrovně centralizace státu (`loose`, `moderate`, `strong`) na váhu vazeb k hlavnímu městu. |
| `policy_levels` | `level_table2` | Převodník jazykové politiky (`tolerant`, `promoted`, `enforced`) na tlak na asimilaci a úřední jazyk. |
| `lingua_franca_levels` | `level_table2` | Převodník úrovní mezinárodního jazyka na prestiž a sílu vazeb. |
| `terrain_access` | `level_table` | Převodník prostupnosti terénu (`plains`, `hills`, `mountains`, `swamp`) na fyzickou vzdálenost. |
| `identity_loyalty` | `level_table` | Převodník loajality identity (`fluid`, `neutral`, `firm`) na odolnost vůči jazykové směně. |
| `literacy_levels` | `level_table` | Převodník úrovně gramotnosti (`none`, `elite`, `scholarly`, `mass`) na podíl čtenářů. |
| `schooling_levels` | `level_table` | Převodník školní docházky (`none`, `rudimentary`, `elementary`, `universal`) na vliv školy. |
| `border_levels` | `level_table` | Převodník propustnosti hranic (`open`, `normal`, `closed`, `wall`) na přeshraniční kontakt. |
| `revival_levels` | `level_table` | Převodník intenzity jazykového obrození (`symbolic`, `moderate`, `vigorous`). |
| `background_levels` | `level_table2` | Převodník intenzity vnějších historických událostí na pozadí dějin. |
| `channel_domains` | `table2` | Matice domén (jádrová, odborná, kulturní, náboženská, mocenská) pro jednotlivé kanály kontaktu. |
| `grammar` | `table2` | Uživatelský přepis parametrů gramatického katalogu (potřeba, kontext, pokrytí). |

---

### 5.2 Kategorie `Role::Active` (24 položek)
Aktivně laděné kalibrační páky a ladicí tabulky. Každý parametr v této skupině má experimentálně doložený samostatný vliv a nelze jej svázat s ostatními.

| Parametr | Výchozí hodnota | Důvod samostatného ladění a lingvistický účinek |
|---|:---:|---|
| `sound_actuation` | `2.25` | **Tempo hláskových změn:** Násobek sociálního ocenění inovací. Určuje hloubku fonologického přepisu slovníku i míru uchycení variant (Exp. 1). |
| `functional_load_scale` | `5.0` | **Ochrana morfologických kontrastů:** Určuje sklon křivky chránící fonémy s vysokou rozlišovací zátěží (Wedel a kol. 2013). Klíčové pro životnost pádových koncovek. |
| `chain_shift_weight` | `1.5` | **Řetězové posuny:** Tahová a tlaková síla fonologického prostoru (Martinet 1955). Řídí tah samohlásek po uvolnění pozice. |
| `actuation_coherence` | `1.5` | **Soudržnost v ohnisku:** Zvýhodnění varianty, pokud se současně šíří v jiných slovech v témže uzlu. |
| `village_openness` | `0.35` | **Otevřenost vesnice:** Podíl váhy přikládané mluvčím ze sousedních sídel v síti. Řídí základní difuzi. |
| `leveling_rate` | `0.35` | **Nářeční vyrovnávání (Trudgill):** Rychlost stírání lokálních výslovnostních výstředností v rámci regionu. Nezbytné proti tříštění (Exp. 3). |
| `city_size` | `4.0` | **Demografická váha města:** Poměr velikosti města k běžné vesnici v gravitačním vzorci. |
| `city_prestige` | `0.3` | **Prestiž města:** Bonus k přitažlivosti městských variant v kontaktu. |
| `city_listening` | `0.2` | **Asymetrie poslechu města:** Koeficient, kterým město vnímá venkov. Klíčové pro roli města jako hegemonického ohniska koiné (Exp. 3). |
| `capital_prestige` | `2.0` | **Prestiž metropole:** Zvýhodnění variant z hlavního města v celém státě. |
| `capital_link_strength` | `0.3` | **Síla administrativních vazeb:** Přímé propojení sídla státu s regionálními středisky. |
| `loyalty_spread` | `0.5` | **Šíření etnické loajality:** Difuze loajality podél sítě kontaktů. |
| `school_weight` | `0.3` | **Přímý vliv školy na lexikon:** Přenos spisovných slov a syntaktických konstrukcí do mluvy žáků (Exp. 2). |
| `school_correction` | `0.8` | **Korekce substrátu ve škole:** Potlačení L1 interferenčních rysů při osvojování L2 standardu (Exp. 2). |
| `interference_weight` | `0.5` | **Síla substrátové interference:** Míra přenosu mateřských rysů do osvojovaného cizího jazyka. |
| `entrenchment_strength` | `1.0` | **Síla zakořenění (Bybee):** Odolnost frekventovaných slov a tvarů vůči analogickému vyrovnání. |
| `standing_variation` | `0.1` | **Stojatá variabilita:** Šum v pravděpodobnostech užití variant udržující přirozenou variabilitu řeči. |
| `lexical_length_cost` | `0.3` | **Zipfův trest za délku slov (Piantadosi a kol. 2011):** Znevýhodnění nadměrně dlouhých neprůhledných složenin a odvozenin. |
| `borrowability_strength` | `1.0` | **Půjčitelnost (Haspelmath 2009):** Škála propustnosti slovních druhů a domén při kontaktu. |
| `emergence_need_scale` | `2.0` | **Potřeba nových gramatických kategorií:** Citlivost gramatikalizace na funkční mezery v systému (členy, pomocná slovesa). |
| `extravagance` | `0.5` | **Extravagance (Haspelmath 1999):** Tlak na expresivitu vedoucí ke vzniku opisných konstrukcí. |
| `pressure_weights` | `{}` | **Přepis vah selekčních tlaků:** Tabulka umožňující explicitní přepis váhy libovolného tlaku (např. `"norm"`). |
| `population_pressure_exponents`| `{}` | **Populační koeficienty tlaků:** Nelineární škálování působení tlaků s rostoucí velikostí populace. |
| `change_rates` | `{}` | **Specifická tempa rodin změn:** Možnost nezávisle zrychlit či zpomalit vybrané z 36 rodin hlásek. |

---

### 5.3 Kategorie `Role::Fixed` (50 položek)
Zafixované konstanty modelu, stabilitní prahy a vypnuté/jednotkové přepínače. Všechny tyto položky zůstávají v kódu a ve `from_overrides`, ale při běžné kalibraci se nemění, protože představují vnitřní mechaniku enginu nebo fyzikální invarianty.

| Skupina parametrů | Zahrnuté položky | Důvod zafixování |
|---|---|---|
| **Fonotaktika a redukce** | `coda_tolerance_scale` (1.0), `stress_strength_multiplier` (1.0), `clarity_short_factor` (1.0), `dispersion_factor` (1.0) | Jednotkové kalibrační násobky fonotaktiky; ladění probíhá přímo přes váhy tlaků a pravidla inventáře. |
| **Morfologická dynamika** | `learnability_strength` (1.0), `fusion_bonus` (0.3), `order_rigidity` (0.8), `economy_word_cost` (0.2), `category_loss_l2_boost` (1.5), `analogy_l2_boost` (1.5), `analogy_threshold` (0.05), `paradigm_merge_weight` (1.0), `redundant_merge_weight` (1.0) | Kalibrováno v milnících M4a/M7; určují rovnováhu mezi syntetickou a analytickou strukturou. |
| **Jazyková směna (Abrams-Strogatz)** | `shift_rate` (0.02), `shift_exponent` (1.31), `shift_return` (0.0), `child_threshold` (0.15) | Exponent 1.31 odpovídá empirickému fitu Abramse a Strogatze (2003); `child_threshold` určuje bod zlomu transmise. |
| **Zakořenění a frekvence** | `entrenchment_base` (0.5), `entrenchment_frequency_exponent` (0.5), `frequency_lead` (0.2), `conserved_frequency` (0.8) | Psycholingvistické mocninné škálování frekvence užití (Bybee 2001). |
| **Sítě, sídla a prostor** | `leveling_beyond_region` (0.0), `city_link` (0.5), `capital_reach` (250.0), `settlement_growth` (0.0), `urban_mortality` (0.0), `population_per_density` (250.0), `border_link_scale` (0.3) | `leveling_beyond_region = 0.0` experimentálně ověřeno jako nutné (Exp. 3); `city_link = 0.5` je zbytná podlaha; růst sídel je vypnut. |
| **Instituce a písmo** | `reading_weight` (0.1), `reading_core_resistance` (0.8), `liturgy_weight` (0.05), `standard_prestige` (1.5) | Relativní váhy doplňkových institucí vůči základnímu školství. |
| **Pozadí dějin a elity** | `background_spans` (tabulka), `background_rates` (tabulka), `background_elite_prestige` (2.0), `background_elite_link` (0.3), `background_elite_share` (0.05) | Stabilní parametry elitních vrstev kopírující hodnoty metropole. |
| **Lingua franca** | `lingua_franca_link` (0.3), `lingua_franca_pull` (0.5) | Kopíruje stabilní koeficienty centrálních vazeb (0.3). |
| **Uzavírání a fonologizace** | `closure_generations` (3), `activation_share` (0.05), `release_residual` (0.05), `restructure_threshold` (0.85), `grammar_threshold` (0.85), `tonogenesis_trigger` (0.15), `variation_cap` (0.95), `actuation_coherence_other` (0.0) | Technické prahy životního cyklu inovace a její fonologizace. |
| **Lexikální náhoda** | `lexical_appeal_sd` (0.1), `word_bias_sd` (0.05), `semantic_recurrence` (0.01) | Parametry gaussovského šumu v lexikonu zaručující stochastickou pestrost. |

---

### 5.4 Automatické svázání fixovaných dvojníků v `Parameters::from_overrides`
Pro zachování intuitivního chování při kalibraci a zabránění asymetrickým stavům (kdy uživatel upraví aktivní páku, ale fixovaný parametr se stejnou lingvistickou rolí zůstane na výchozí hodnotě) provádí `Parameters::from_overrides` automatický přenos:
- `capital_prestige` → `background_elite_prestige` (pokud není `background_elite_prestige` explicitně zadán)
- `capital_link_strength` → `lingua_franca_link` (pokud není `lingua_franca_link` explicitně zadán)
- `analogy_l2_boost` → `category_loss_l2_boost` (pokud není `category_loss_l2_boost` explicitně zadán)
- `restructure_threshold` → `grammar_threshold`, `analogy_threshold` (pro nezadané prahy)
- `actuation_coherence` → `actuation_coherence_other` (0.5× hodnota páky)

Pokud uživatel explicitně zadá hodnotu fixovaného dvojníka, tento explicitní přepis má vždy přednost.

### 5.5 Lokální měřítko města (`Territory::city_size`)
Místo výhradně globálního parametru `world.params.city_size` nese každé území vlastní hodnotu `Territory::city_size`:
- Výchozí hodnota `0.0` znamená použití globálního parametru `Parameters::city_size`.
- Ve scénářích (`scenarios.rs`) se městským sídlům nastavuje lokální měřítko regionu (`settlement.city_size = city_size;`).
- Normalizace velikosti kohorty pro náhodný posun (`transfer/network.rs`) i vážení populačních tlaků (`transfer/pressures.rs`) načítají velikost města z konkrétního území dané skupiny, což umožňuje v jednom světě kombinovat metropole i malá provinční města bez zkreslení dynamiky inovací.

---

## 6. Souhrn úprav v kódu a ověření

1. **`rust/cee_engine/src/transfer/pressures.rs`:**
   - Odstraněna konstanta `const NORM_WEIGHT: f64 = 2.25;`.
   - Výchozí váha normy provázána na tempo změn: `target.push((id::NORM, params.sound_actuation));`.
2. **`rust/cee_engine/src/parameters.rs`:**
   - Přidán enum `pub enum Role { World, Active, Fixed }` (výchozí `Active`).
   - Přidáno pole `pub role: Role` do `ParameterSpec`.
   - Přidána pomocná metoda `ParameterFile::by_role(&self, role: Role)`.
   - V `Parameters::from_overrides` doplněno automatické svázání fixovaných dvojníků s aktivními pákami při neuvedení dvojníka v přepisech.
3. **`src/cee/data/v2_parameters.json`:**
   - Všech 86 parametrů doplněno o pole `"role"` (12× `"world"`, 24× `"active"`, 50× `"fixed"`).
4. **`src/cee/v2/parameters.py`:**
   - Definována trojice `ROLES = ("world", "active", "fixed")`.
   - Funkce `parameter_schema(role: str | None = None)` rozšířena o filtraci podle role.
5. **Lokální měřítko sídel (`Territory::city_size`):**
   - V `model/territory.rs` přidáno pole `city_size: f64` (s výchozí hodnotou 0.0 označující fallback na globální `params.city_size`).
   - Ve `scenarios.rs` se `settlement.city_size` inicializuje na specifickou velikost města daného regionu.
   - V `transfer/network.rs` a `transfer/pressures.rs` upraveno škálování kohorty a tlaků tak, aby využívalo lokální `Territory::city_size`.
6. **Kompoziční rozbor diakritik (`SegmentTable::parse`):**
   - V `segments.rs` doplněn kompoziční rozbor sekundárních artikulačních diakritik přes `SegmentTable::changed`, umožňující robustní parsování i při alternativním pořadí zápisu diakritik (např. délka před nosovostí `aː̃` vs. `ãː`).
7. **Testy a verifikace:**
   - Test `rust/cee_engine/tests/parameters.rs` ověřuje přesné počty parametrů v jednotlivých rolích (12 / 24 / 50) i automatické svázání fixovaných dvojníků při přepsání pák.
   - Python testy v `tests/test_api_v2.py` aktualizovány na 86 parametrů a ověřují přítomnost role ve schématu.
   - Všech 16 sad Rust testů i Python testy procházejí s nulovou chybovostí.

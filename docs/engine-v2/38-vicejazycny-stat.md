# 38. Vícejazyčný stát: normy národů a tempo vynucené politiky (M17)

Stav: **zapsáno na větvi `rozchazeni`** (10. 11. 2026).

Podnět uživatele: „mi chceme, aby se rozcházeli, když tam není stát (vytvoří kontinuum mezi
jazyky), ale aby se sjednotili do jednotného jazyku, když se stát vytvoří“, pak „Co státy, které
mají vícero jazyků (po vzoru R-U)“ a „Oboje udělej“ (norma pro víc krajů i tempo vynucené
politiky).

## Rozcházení bez státu a sjednocení pod státem

Dokument 37 nechal otevřené, proč se sousední vesnice Talvery rozcházejí bez ustálení. Pokusy:

- **Dva izolované kraje** (2 650 let): vesnice uvnitř kraje zůstávají 0,004–0,015 od sebe při
  každé kombinaci rodiny Talvery, jejích parametrů, dvou vesnic, malé hustoty a krajů bez města.
  Uvnitř kraje se tedy vesnice ustálí; rozcházení v Talveře plyne z napojení na síť (každou ves
  táhnou jiní sousedé), tedy z kontinua.
- **Řetěz 8 krajů** (seren, 4 vsi, −700 až 1950):

  | varianta | sousední kraje | jazyků | nářečí |
  |---|---|---|---|
  | bez státu, rok 500 | 0,10–0,15 | 1 | 8 |
  | bez státu, rok 1950 | 0,18–0,26 | 1 (vlna) | 32 |
  | stát od roku 500 | 0,07–0,11 | 1 | 32 |
  | stát, norma a hromadné školy | 0,00–0,01 | 1 | 1 |

  Bez státu vzniká vlna (každá ves nářečím, řetěz je drží jako jeden jazyk), stát kraje přitáhne
  a norma se školou je srovná. To uživatel chce.
- **Hustota sítě** (Talvera s 2, 4 a 6 vesnicemi na kraj): 27, 25 a 17 jazyků, jednoregionových
  37 %, 52 % a 29 %. Víc vesnic dává víc cest, kudy se řetěz spojí, vzdálenost sousedních krajů se
  ale nemění (0,22). Šest vesnic běží 3,7× déle a potřebuje asi 4× víc paměti.

Bez státu vzdálenost sousedních krajů stále roste (0,12 v roce 500, 0,22 v roce 1950), takže se
za tisíciletí vlna trhá ve slabých místech. Zda ji na rovině ustálit pod prahem, zůstává otevřené.

## Pokus R-U

16 krajů po 4 vsích, rok 0–1950: Rakousko (serenština jako němčina), české země, Halič a jižní
Slované (veretština, jedna rodina) a Uhry (talmurština). Monarchie 1526 se snášenlivou
politikou, státní norma 1600, hromadná škola 1870.

| varianta | jazyky 1950 |
|---|---|
| bez státu | němčina · Čechy až Halič · Kraňsko a Chorvatsko · maďarština |
| monarchie s normou jen pro kraj Čechy | stejné |
| monarchie s vynucenou politikou 1870 (tah 1,0) | jediný jazyk: všech 48 jinojazyčných skupin přešlo na němčinu za 80 let |

Chyběly dvě věci: norma mohla patřit jen státu nebo jedinému kraji (česká norma pro Čechy,
Moravu a Slezsko nešla, normy po krajích by češtinu rozdělily na tři střechy) a vynucená
politika převáděla celé kraje za dvě generace.

## Zapsáno

1. **Norma národa** (`standard` s `regions`): `{"kind": "standard", "of": "cestina", "regions":
   ["b1", "b2", "b3"], "literacy": "towns"}`. Jméno `of` nesmí patřit státu, kraji ani jinému
   národu; svět si rozsah pamatuje (`SocietyState::nations`), takže na něj odkáže i
   `{"kind": "schools", "of": "cestina"}`. Sídlem normy je největší ves prvního kraje, dosah
   slábne se vzdáleností jako u státu. Skupina jiného jazyka si cizí normu jen čte, skupina
   s normou vlastního jazyka zůstává u ní a do státní školy nechodí (jako dosud).
2. **Tempo vynucené politiky**: `policy_levels.enforced.pull` 1,0 → 0,15, kalibrováno novým
   během `politika` (cíl `m10::politika`). Germánský stát se slovanskou menšinou ve třech krajích,
   v roce 1 000 vynucená politika a hromadná škola ve státním jazyce:

   | tah | menšina po 80 letech | po 200 letech |
   |---|---:|---:|
   | 1,0 (dříve) | 0 | 0 |
   | 0,3 | 0,33 | 0 |
   | 0,2 | 0,55 | 0,05 |
   | **0,15** | **0,67** | **0,24** |
   | 0,12 | 0,74 | 0,37 |
   | cíl | 0,4–0,9 | 0,05–0,35 |

   Opora: velština 54 % (1891) → 21 % (1971), irština 29 % (1851) → 18 % (1911), bretonština
   ztratila mezigenerační předávání 60–80 let po Ferryho zákonech; maďarizace a germanizace
   Poláků v Prusku venkovské menšiny z velké části nepřevedly. Tah je stejný jako u
   `romanization`; rychlejší přechod dělá škola ve státním jazyce (`(1 + škola cíle)` v tempu).
3. **Pád exportu jmen osob** (`onomastics::export_world_onomastics`): mluvčí skupina sídla normy
   se hledala jménem a po přechodu jazyka už nežila (prázdné kódy). Teď se bere jen živá.

## Výsledek v pokusu R-U

S normami národů (polština 1550, maďarština 1780, čeština 1800, chorvatština 1830, vždy pro
všechny kraje národa) a národními školami 1870:

| varianta | jazyky 1950 | nářečí | Čechy–Morava | Slezsko–Halič | uvnitř Čech |
|---|---|---:|---:|---:|---:|
| normy národů | 5: němčina, čeština, polština, chorvatština, maďarština | 53 | 0,23 | 0,16 | 0,07 |
| + národní školy | stejných 5 | 18 | 0,18 | 0,26 | 0,02 |

Školy sjednotí nářečí kolem vlastní normy a zostří hranici dvou norem (Slezsko–Halič 0,16 →
0,26); rozdíl mezi kraji národa zůstává (Čechy a Morava). Vynucená politika 1870 s tahem 0,15:
bez národních norem mluví roku 1950 doma německy 26–37 % menšin, s národními normami a školami
4–6 % (vlastní škola přechod brzdí, jako u Čechů).

## Ověření

**Kalibrace 38 ze 40, brány 47 ze 47.** Nový cíl `m10::politika` prošel (0,664 po 80 letech,
0,238 po 200 letech); neprošly tytéž dva starší cíle jako v M15 a M16 se stejnými hodnotami
(`m7::typologie_37A` 0,129, `m8::romanske_pady` 0,417). Evropa a Romania vynucenou politiku
nepoužívají, jejich výsledky se nemění. Testy: nový `norma_naroda_pres_vic_kraju`, test
výchozích hodnot upraven na tah 0,15; selhává jen starší `spec_check::scenare_evropa_a_romania_nemaji_chyby`.
Desktop 11 testů ze schématu prošlo.

Talvera (semínko 1) má 29 jazyků, z toho 12 v jediném regionu (41 %), medián 2 regiony. Proti
M16 (27 a 10) je to v šumu semínek; Jezerní svaz (vynucená politika 1875) teď převádí pomaleji,
takže v jeho krajích přežije víc posunutých skupin.

## Otevřené

- Politika a „vlastní norma“ se dál řídí rodinou (prajazykem), ne pozorovaným jazykem. Norma
  národa to obchází rozsahem krajů; slovanský stát se slovanskými menšinami (Jugoslávie) by je
  dál bral jako vlastní jazyk.
- Úplné smazání nářečí pod hromadnou státní školou (řetěz krajů: 1 nářečí ze 32) je nejspíš
  příliš silné; skutečné státy nářečí obvykle zachovaly.
- Ustálení vzdálenosti sousedů bez státu (viz výše).

# 37. Jazyky jako vlny: prostupnost, kontinuum a cizí vrstvy (M16)

Stav: **zapsáno na větvi `kontinuum`** (9. 11. 2026).

Podnět uživatele: „Stále máme příliš jednoregionových jazyků … region by mělo být větší město + jeho
okolí.“ Dál: „abstrahovat od hor a kopců ke konkrétnímu číslu – prostupnost. 1 jsou krajiny hodně
prostupné, 0 absolutně izolované“; „Regiony by měli spolu mít soudržnost, když jsou spolu spjaté
a když mají společný kontext – obchod, stát, náboženství“; „jazyky byli spíše vlny, než homogenní
skupiny (němčina se přelévala v češtinu, těžko šlo označit to, kde co začínalo a končilo, to přišlo
až s centrálním státem, školstvím a tiskem).“

## Nález

Talvera (96 regionů po dvou vesnicích, −700 až 1950, M15): 54 jazyků, 25 z nich (46 %) v jediném
regionu, medián 2 regiony na jazyk. Talvera.md čeká 45–55 jazyků, ale uživatel chce jazyky
přes víc regionů.

## Zapsáno

1. **Prostupnost 0–1** místo tříd terénu (commit 4c49918): region má `permeability`, bez ní
   platí výchozí podle terénu (`terrain_access`: rovina 1, kopce 0,6, hory 0,3, ostrov 0,2).
   Vazbu přes hranici dvou regionů násobí **geometrický průměr** prostupností obou: cesta vede
   napůl přes každý region. Dřív se násobil součin, takže dva kopcovité regiony měly 0,36 a dva
   ostrovy 0,04 (krajina se započítala dvakrát). Dosah státu (`polity::reach`) čte prostupnost
   regionu dál přímo.
2. **Rozsah vesnic** v regionu (`villages: [min, max]`, commity 4c49918 a 86a6af6): počet se
   losuje ze semínka světa a jména regionu.
3. **Jazyky jako kontinuum** (`cee_core::observe::continua`). Jazyky už neurčuje průměrná vazba
   shluků, ale dvě Klossova kritéria (Kloss 1967):
   - **Abstand (vlna):** sousední skupiny (kandidátní dvojice z vazeb a polohy) se spojí, když je
     jejich vzdálenost pod prahem jazyka (0,25, s hysterezí a branou tvarů jako dřív). Spojení
     je řetězové: dialekty A–B–C jsou jeden jazyk, i když A a C jsou od sebe dál než práh.
     Hranici jazyka dělá až místo, kde se řetěz přeruší.
   - **Ausbau (střecha):** skupiny, které čtou spisovnou normu vlastního jazyka (gramotnost > 0),
     jsou jeden jazyk, ať jsou od sebe jakkoli daleko. Řetěz nesmí spojit dvě různé střechy:
     na hranici dvou norem vznikne ostrá hranice jazyků i uprostřed kontinua (čeština a slovenština,
     nizozemština a němčina). Bez normy zůstane vlna.
4. **`state_cohesion`** (role `active`, výchozí 0): vazby přes hranici regionů uvnitř státu se
   násobí 1 + `state_cohesion`. Páka pro scénáře, výchozí hodnota stav nemění.
5. **Cizí vrstvy nevytlačují příbuzné sousedy** (`transfer::network::mixing`, viz rozbor). Sousedé
   vlastního jazyka si otevřenost skupiny dělí mezi sebou; cizí zdroje mají svůj podíl ze všech
   vazeb navíc a `hear` řádek normalizuje podle vah. Skupina bez cizích vazeb se nemění.
6. **Kalibrační běh `prah`** (informační cíl `m10::prah`): dva regiony slovanštiny po čtyřech
   vesnicích bez kontaktu; po 250, 500, 750, 1 000 a 1 500 letech vzdálenost mezi regiony,
   uvnitř regionu, podíl společných slov a počet jazyků.

## Práh jazyka

Pokus `prah` (8 semínek):

| oddělení | vzdálenost regionů | společná slova |
|---|---:|---:|
| 500 let | 0,084 | 99 % |
| 1 000 let | 0,193 | 93 % |
| 1 500 let | 0,268 | 87 % |

Práh 0,25 odpovídá asi 1 300 letům úplného oddělení. To je uvěřitelné (románské jazyky se rozešly
za 1 000–1 500 let), takže práh zůstává.

## Rozbor: kde se ztrácí vliv sousedních regionů

Přes hranici regionu vesnice Talvery slyší v průměru 26 % vstupu, přenos tedy sousedy neodřezává.
Rozdělení podle velikosti jazyka ukazuje, kde chybí:

| jazyk vesnice | vstup od příbuzných z jiných regionů (medián) |
|---|---:|
| v jediném regionu | 1,7 % (9 z 22 vesnic nic) |
| ve 2–3 regionech | 6,8 % |
| ve 4 a více regionech | 26 % |

Vzdálenost sousedních vesnic na síle vazby opravdu závisí (bez vazby 0,32, se silnou 0,18).
Jednoregionové jazyky mají čtyři příčiny:

1. **Cizí vrstvy vytlačovaly příbuzné sousedy.** Váha zdroje v míšení je vazba × prestiž
   a nezávisí na velikosti. Vrstva 99 mluvčích veretštiny (lingua franca, prestiž 3,66) brala
   vesnici m05-08 (550 lidí) 52 % vstupu a na serenské sousedy zbylo 5 %. Cizí vstup filtr
   přenositelnosti v `hear` většinou zahodí a normalizace jeho váhu vrátí vlastní skupině: vesnice
   se uzavřela do sebe a odplula jako samostatný jazyk. Bez událostí `lingua_franca` kleslo
   jednoregionových jazyků ze 17 na 10. Opraveno (bod 5 výše).
2. **Osady** (`+` ve jménu) zůstávají jazykovými ostrůvky (4–5 jazyků). To je uvěřitelné.
3. **Ostrovy a hory** mají nízkou prostupnost a vlastní jazyk tam je uvěřitelný (faerština,
   horská údolí).
4. **Vesnice se rozcházejí i při silném propojení a nikde se neustálí** (otevřené, níže).

Bez vlivu na strukturu zůstaly (jednoregionových 15–22 jazyků, šum semínek asi ±5):
`state_cohesion` 0,5 a 1, kopce s prostupností 0,8, propojení všech dvojic vesnic přes hranici
(místo nejbližší dvojice; prototyp zahozen), `actuation_coherence` 0,4 a 0, `city_listening` 0,6,
`leveling_rate` 0,15, `border_link_scale` 5 a 12, geometrický průměr prostupnosti sám o sobě.
Pomohla jen otevřenost vesnic 0,8 (14 jednoregionových), ta ale mění celou kalibraci.

## Výsledek v Talveře

| stav | jazyků | jednoregionových | medián regionů |
|---|---:|---:|---:|
| M15 (stará pozorování) | 54 | 25 (46 %) | 2 |
| kontinuum a střechy | 31 | 16 (52 %) | 1 |
| + cizí vrstvy nevytlačují (semínko 1) | 27 | 10 (37 %) | 2 |

Semínka 2–4, staré a nové míšení:

| semínko | staré míšení | nové míšení |
|---|---|---|
| 2 | 32 jazyků, 16 jednoregionových | 26 jazyků, 11 jednoregionových |
| 3 | 34, 19 | 29, 13 |
| 4 | 32, 18 | 27, 12 |

## Kalibrace

**Kalibrace 36 z 38, brány 47 z 47.** Neprošly stejné dva cíle jako v M15 se stejnými hodnotami:
`m7::typologie_37A` 0,129 a `m8::romanske_pady` 0,417. Staré míšení na téže větvi dává také
36 z 38. Proti němu se nové míšení pohnulo takto:

| veličina | staré | nové |
|---|---:|---:|
| zrychlení kontaktem (`m9::tempo`, pásmo 1–2,8) | 2,78 | 2,31 |
| jazyků v Evropě 1900 (`m8::pocet_jazyku`) | 45,5 | 41,5 |
| slovanská pravlast drží pád | 0,83 | 0,92 |
| zápor před slovesem v Romanii | 0,70 | 0,75 |
| retence vůči latině | 0,737 | 0,722 |
| obnova futura | 1,00 | 0,90 |

Zrychlení kontaktem kleslo dál od horní meze: vesnice s cizí vrstvou dřív slyšela relativně víc
cizího a míň vlastního jazyka, než odpovídá jejím vazbám.

## Otevřené: stálé rozcházení

Vesnice téhož regionu (vazba kolem 0,85, 30–40 % vstupu od sebe) se v Talveře rozcházejí bez
ustálení: vzdálenost 0,04 v roce 300, 0,10 v roce 1950 bez událostí, 0,13 s událostmi; přes
hranici regionu 0,08, 0,18 a 0,25. V roce 300 má Talvera strukturu vln, jakou chce uživatel
(11 jazyků, medián 3 regiony, 18 % jednoregionových); za 2 650 let i dobře propojení sousedé
dojdou k prahu. Skutečné kontinuum drží sousedy srozumitelné trvale. Další krok: zjistit, která
složka vzdálenosti (slova, tvary, rozptyl variant) roste i pod silným míšením.

## Návrh pro talvera.md (nezapsáno, dokument je uživatelův)

- Cíl 45–55 jazyků nahradit strukturou: jazyk zabírá medián aspoň 2 regiony (po vyřešení
  stálého rozcházení 3), nejvýš asi pětina jazyků v jediném regionu mimo ostrovy, hory a osady;
  počet jazyků vyplyne (dnes 26–29).
- Ostrovům a horským údolím ponechat vlastní jazyky; prostupnost uvádět číslem tam, kde se
  krajina od výchozí hodnoty terénu liší.

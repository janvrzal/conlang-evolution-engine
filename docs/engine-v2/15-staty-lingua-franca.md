# Státy, jazyková politika a lingua franca (M6f)

Datum: 31. 10. 2026. Větev `engine-v2-dynamika`. Navazuje na
[`13-region-world.md`](13-region-world.md) a
[`14-kalibrace-kontinua.md`](14-kalibrace-kontinua.md).

Zadání uživatele:

- v rámci státu může převládnout jeden jazyk;
- nemusí to tak dopadnout vždy: regiony s vlastní historií nebo etnikem si
  jazyk udrží;
- lingua franca jako dorozumívací jazyk;
- autor světa to zadává uživatelsky přívětivě, stačí přiblížení.

## Princip

Stát svůj jazyk nešíří přímo. Mění tři věci a jazyk se pak šíří sám
mechanismy, které engine už měl:

| Páka | Co dělá | Mechanismus |
|---|---|---|
| prestiž | vesnice hlavního města mají `capital_prestige`× (2×) vyšší prestiž | děti se víc učí od prestižních sousedů (`mixing_matrix`), jazyk centra má vyšší status při přechodu |
| sítě | centralizace spojí vesnice státu se sídlem (úřady, trh, vojsko, cesty); síla klesá se vzdáleností (`capital_reach` 150 km) a v horách | nářečí se srovnávají k řeči centra |
| domény | regiony jiného jazyka užívají úřední jazyk mimo domov; politika určuje, jak silně se tlačí domů | veřejná doména (`LanguageShift(domain="public")`) a nově **pronikání domů** (`contact._nativize`) |

Jestli jazyk regionu přežije, rozhoduje to, co platí i ve skutečnosti:
blízkost centra, terén, demografie a loajalita. Autor to nezadává.
**Lingua franca** je týž mechanismus bez státu: komunity různých jazyků
se jedním kódem domlouvají mimo domov. Učí se ho dospělí (`l2_share` = 1),
takže na něj působí tlaky učení L2 (zjednodušení, část E) a v každém
regionu nese stopy místního jazyka (interference).

## Pronikání domů

Dosud byla veřejná dvojjazyčnost navždy stabilní. Nově má veřejná skupina
`home_pull` (tlak domů: škola v úředním jazyce, úřady, smíšená manželství).
Za generaci přejde do domácí skupiny cílového jazyka podíl

`home_pull × status × dvojjazyčnost^1,31 × (1 − loajalita)`

domácností (tvar jako u přechodu, Abrams & Strogatz 2003). Další průběh
vede dosavadní přechod (`_shift`: demografie ze sítě, loajalita, práh
předávání dětem) tempem politiky: uvolnění politiky přechod zastaví. Když
starý jazyk vymře, zanikne i veřejná dvojjazyčnost. Je to přiblížení,
model rodin to není. Výchozí `home_pull` = 0 nechává všechny dosavadní
scénáře beze změny (otisky stejné).

## Rozhraní pro autora

Regiony (`scenarios.Region`) dostaly tři slovní vlastnosti:

```python
Region("hory", (0, 60), density=0.5, neighbours=("stred",),
       language="c",          # protojazyk regionu (vlastní linie)
       terrain="mountains",   # plain | hills | mountains | island
       identity="strong")     # shared | distinct | strong
```

- `language` + `region_world(..., languages=(ProtoLanguage("a"), ...))`:
  regiony různých jazyků v jedné síti vesnic. Bez `languages` platí
  společný protojazyk jako dosud.
- `terrain` (`Parameters.terrain_access`: 1 / 0,6 / 0,3 / 0,2) násobí
  vazby přes hranici regionu (součin obou stran), dosah státu i rozšíření
  lingua franca.
- `identity` (`Parameters.identity_loyalty`: 0 / 0,5 / 0,8) nastaví
  loajalitu vesnic k jazyku: vlastní etnikum, náboženství nebo historie.

Události (`cee.v2.polity`), vše se zadává regiony a slovními úrovněmi:

```python
State(800, "kralovstvi", regions=("stred", "rovina", "hory"), capital="stred",
      centralization="moderate",   # none | weak | moderate | strong
      policy="promoted")           # tolerant | promoted | enforced
LanguagePolicy(1880, "kralovstvi", "enforced")   # povinná škola v úředním jazyce
Annexation(1200, "kralovstvi", ("jih",))
LinguaFranca(600, source="pristav", regions=("a", "b"), spread="common",  # rare | common | universal
             nativize=False)       # True = časem zdomácní (svahilština ve městech)
```

Úřední jazyk je řeč sídla (největší vesnice hlavního města). Výsledky čte
`polity.language_census(world)`: pro každý region podíl lidí podle jazyka
doma a mimo domov a stát, do kterého patří. Neznámou úroveň engine odmítne
s výčtem možností.

## Politiky

| Politika | Mimo domov (`share`) | Tlak domů (`pull`) | Typ |
|---|---:|---:|---|
| `tolerant` | 0,1 | 0 | stabilní diglosie (Fishman 1967), mnohonárodní říše |
| `promoted` | 0,3 | 0,1 | předmoderní stát: jazyk dvora, úřadů a měst |
| `enforced` | 0,6 | 1,0 | moderní stát: povinná škola, branná povinnost, železnice |

Obě čísla se násobí dosahem centra (terén × `exp(−d / 150 km)`). Hodnoty
jsou autorské odhady, nastavené podle řádů:

- vynucování prosadí jazyk na blízké rovině do 3–4 generací (Fishman);
- předmoderní stát asimiluje jen blízké roviny, a to během staletí;
- odlišné a odlehlé regiony vydrží (Baskicko, Bretaň do 19. století).

Kalibrace proti datům se zatím nedělala.

## Výsledky

`scripts/v2_kingdom.py`, scénář `scenarios.kingdom`. Hlavní město je
hustá rovina s jazykem `a`; k ní tři regiony 60 km daleko: rovina `b`
(shared), jih `d` (distinct) a hory `c` (mountains, strong). Stát vzniká
v roce 100. Tabulka ukazuje podíl obyvatel, kteří doma mluví původním
jazykem:

| varianta | region | 300 | 600 | 700 | 900 | 1 500 |
|---|---|---:|---:|---:|---:|---:|
| tolerantní | všechny | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| podporovaný jazyk | rovina | 0,87 | 0,65 | 0,58 | 0,42 | 0,00 |
| podporovaný jazyk | jih (odlišný) | 0,94 | 0,85 | 0,81 | 0,74 | 0,52 |
| podporovaný jazyk | hory (silná identita) | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| podporovaný, od 600 vynucovaný | rovina | 0,87 | 0,44 | 0,00 | 0,00 | 0,00 |
| podporovaný, od 600 vynucovaný | jih | 0,94 | 0,73 | 0,18 | 0,00 | 0,00 |
| podporovaný, od 600 vynucovaný | hory | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| lingua franca + tolerantní stát | všechny | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |

S lingua francou v tolerantním státě zůstávají domácí jazyky. Lingua
franca žije jen mimo domov: 30 % dospělých na rovinách a 9 % v horách.

Dvouregionové pokusy (rovina, 60 km, pokud není řečeno jinak). Čísla jsou
podíl původního jazyka doma po 100 / 300 / 600 / 1 000 letech:

| region | promoted | enforced |
|---|---|---|
| rovina, shared | 0,93 / 0,80 / 0,58 / 0,28 | 0 po 100 letech |
| rovina, distinct | 0,97 / 0,92 / 0,82 / 0,68 | 0,36 / 0 |
| rovina, strong | 1,00 trvale | 0,75 / 0,29 / 0 |
| pahorkatina | 1,00 trvale | 0,51 / 0 |
| hory | 1,00 trvale | 0,90 / 0,63 / 0,04 / 0 |
| ostrov | 1,00 trvale | 0,96 / 0,86 / 0,64 / 0,26 |
| rovina 200 km | 1,00 trvale | 0,81 / 0,33 / 0 |

Centralizace v jednojazyčném světě (čtverec čtyř regionů, otevřenost 0,1,
3 000 let, seed 1) zmenší vzdálenost přes hranici z 0,119 na 0,079
(`moderate`) a 0,074 (`strong`). Nářečí se k centru srovnávají, kontinuum
uvnitř regionu zůstává.

## Spisovný jazyk

Vrstvy písma, tisku a školy z M6a (`Codification`, `Printing`,
`Schooling`) se dají zadat i po regionech:

```python
Standard(1400, "kralovstvi", literacy="elite")   # elite | towns | mass
Standard(1850, "jih")                            # vlastní norma menšinového jazyka
Schools(1880, "kralovstvi", coverage="mass", printing=True, diglossic=False)  # towns | mass
Schools(1880, "jih")
```

- `of` je ID státu (řeč jeho sídla, úřední jazyk) nebo regionu (řeč jeho
  největší rodilé vesnice).
- Gramotnost a škola se násobí dosahem centra; u regionu jen terénem.
- Skupina čte normu svého jazyka. Normu cizího jazyka čte jen tehdy, když
  vlastní nemá, a pak z ní přejímá učená slova.
- **Školou prochází jen řeč jazyka normy.** U něj nastává standardizace
  a nářečí ustupují. Regiony jiného jazyka spisovný jazyk státu jen čtou;
  ve škole se ho učí jejich mluvčí mimo domov (veřejná doména) a ti, kdo
  na něj přešli. Školy kanály institucí nefiltrují podle linie, takže
  škola v cizím jazyce nesmí vlévat jeho konstrukce do mateřštiny. Asimilaci
  školou proto zadává `LanguagePolicy("enforced")`.
- Mluvčí kodifikovaného jazyka dostanou `standard_prestige`× (1,5×)
  vyšší prestiž. Spisovný jazyk státu tak přechod mírně urychlí a vlastní
  norma regionu jeho status vyrovná.
- **Škola ve vlastním jazyce chrání.** Tlak úředního jazyka domů
  i tempo přechodu se násobí `1 − docházka do školy ve vlastním jazyce`
  (`contact.own_schooling`), jako u češtiny, finštiny nebo katalánštiny.

Stejné království jako výše, spisovný jazyk státu od roku 300 (podíl
původního jazyka doma):

| varianta | region | 300 | 600 | 700 | 900 | 1 500 |
|---|---|---:|---:|---:|---:|---:|
| spisovný jazyk státu | rovina | 0,87 | 0,62 | 0,53 | 0,36 | 0,00 |
| spisovný jazyk státu | jih | 0,94 | 0,82 | 0,78 | 0,70 | 0,42 |
| + vlastní norma jihu | jih | 0,94 | 0,85 | 0,81 | 0,74 | 0,52 |
| od 600 vynucování a masová škola | rovina | 0,87 | 0,30 | 0,00 | 0,00 | 0,00 |
| od 600 vynucování a masová škola | jih | 0,94 | 0,64 | 0,00 | 0,00 | 0,00 |
| + vlastní norma a škola jihu | jih | 0,94 | 0,84 | 0,80 | 0,74 | 0,63 |

Čísla jsou po zavedení obrození, kdy škola působí na obě strany (viz
Obrození). Škola ve státním jazyce asimilaci urychlí: jih bez vlastní školy
ztratí jazyk do 100 let. Vlastní škola ho drží i po 900 letech vynucování
na 0,63, protože část rodin se k jazyku vrací.

## Hranice, prestiž a konzervace jazyka

Rozhodnutí uživatele: hranice jsou **implicitní**, tedy tam, kam stát
sahá, a působí **hned v plné síle**. Autor smí jazyk výslovně
zakonzervovat.

**Hranice.** Engine je odvodí z `world.states` po každé události státu
(`polity.refresh`). Vazba mezi regiony různých států, nebo státu a regionu
mimo státy, má sílu základ × propustnost. Platí méně propustná hranice
z obou stran (`Parameters.border_levels`: `open` 1,0, `normal` 0,5,
`closed` 0,1). Základ si vazba pamatuje (`world.border_factors`), takže
připojení regionu nebo rozpad státu hranici zase zruší. Hranice jen
oslabí kontakt. Rozcházení podél ní dělá to, že každá strana tíhne
k jinému sídlu a k jiné normě.

`scripts/v2_state_border.py`: jednojazyčný čtverec, sever a jih jako dva
státy, 2 000 let, průměr seedů 1 a 2 (vzdálenost kódů spojených vesnic
z různých regionů):

| hranice | uvnitř státu | přes hranici států |
|---|---:|---:|
| bez států | 0,124 | 0,111 |
| `open` | 0,053 | 0,115 |
| `normal` | 0,053 | 0,133 |
| `closed` | 0,054 | 0,168 |

Stát sjednotí své regiony (vazby k sídlu) a sousední státy se rozejdou
i při otevřené hranici. Zavřená hranice rozdíl zhruba zdvojnásobí. Engine
tak dává typ nizozemština a němčina nebo čeština a slovenština, aniž by
někdo zadal, kde mají být.

**Prestiž** se počítá ze stavu světa, nenásobí se jednou. Prestiž domácí
skupiny je:
- základ regionu;
- × `capital_prestige`, je-li skupina v hlavním městě existujícího státu;
- × `standard_prestige`, čte-li normu svého jazyka.

Mluvčí úředního jazyka mimo domov a rodiny, které na něj přešly, přebírají
**aktuální** prestiž jeho sídla (`world.prestige_mirror`).

**Události moci:**

```python
Secession(1500, "nezavisly", regions=("jih",), capital="jih", policy="promoted")
Collapse(1700, "kralovstvi")
BorderPolicy(1950, "kralovstvi", "closed")
Annexation(1300, "kralovstvi", ("sever",))   # kdo přijde o hlavní město, zanikne
```

- **Rozpad státu:** hlavní město ztratí status, hranice zmizí, zmizí
  i vazby vesnic k sídlu a tlak domů. Spisovná norma zůstane (jako latina
  po Římu) a lidé úřední jazyk umějí dál; rozběhnutý přechod se zastaví.
- **Odtržení:** regiony odejdou ze starého státu a jeho politika tam
  skončí. Jazyk nového hlavního města dostane status úředního jazyka.
  Hlavní město odtrhnout nejde (to je `Collapse`).

**Konzervace jazyka:** autor vypne vymírání tam, kde ho nechce.

```python
Region("ostrov", ..., preserve=True)                  # od začátku
Preserve(1200, ("hory",))                             # od roku 1200 (původní jazyk regionu)
Preserve(1800, ("hory",), preserved=False)            # zrušení
```

Ze zakonzervované skupiny nikdo nepřejde na jiný jazyk (`SpeechGroup.preserved`).
Jazyk se dál vyvíjí, přejímá slova a mluvčí ho mohou užívat mimo domov,
jen nevymře.

**Vlastnosti regionu v čase** (doplněno podle návrhu UI, `docs/ui-navrh`).
Identita a přistěhovalectví regionu se dají měnit i během dějin, editor
světa je zadává jako úseky „odtud potud“:

```python
Identity(900, ("teth",), "distinct")      # odlišnost regionu od roku 900
Immigration(1100, ("vardun",), 0.1)       # obchodní město: přicházejí cizinci
Immigration(1500, ("vardun",), 0.0)       # příchod skončí
```

`Identity` nastaví loajalitu domácích skupin regionu stejně jako
`Region.identity` na začátku (`Parameters.identity_loyalty`). Skupiny, které
vzniknou později přechodem nebo obrozením, ji zdědí. `Immigration` nastaví
podíl přistěhovalců za generaci jako `Region.immigration`; přistěhovalci se
místní řeč učí v dospělosti, takže drží podíl L2 mluvčích. Při zapnuté
gravitační migraci (`world.migration`) podíl každý krok přepíše migrace.

**Jména států:** `State` a `Secession` mají nepovinné `name`. Na dynamiku
nemá vliv; engine ho nese do historie a do exportu států.

## Obrození

Přechod, který rozběhl stát nebo obrození (`home_pull` > 0), je nově
**obousměrný**, jako v původním modelu Abramse a Strogatze. Rodiny se
vracejí ke starému jazyku podílem

`tempo hnutí × (1 − status cílového jazyka) × podíl mluvčích starého jazyka^1,31`.

Tempo hnutí je součet `SpeechGroup.revival` a školy ve vlastním jazyce.
Jazyk s takovou oporou si děti předávají dál i pod prahem užívání
(`transmission_resumed`). Když se vrátí všichni, skupina, která na jiný
jazyk přešla, zanikne (`revival`).

Přechody, které nerozběhl stát ani obrození (dosavadní scénáře), zůstávají
jednosměrné. Otisky se nemění.

Škola nově působí na obě strany. Škola ve vlastním jazyce přechod brzdí,
škola v cílovém jazyce ho urychlí. Proto se po této změně zrychlily
varianty království s masovou školou: jih bez vlastní školy ztratí jazyk
do roku 700 místo 900. Jih s vlastní školou drží v roce 1 500 podíl 0,63
místo 0.

```python
Revival(1850, ("jih",), strength="movement")   # movement | national
```

- Mluvčím jazyka v regionu dá tempo hnutí: `movement` 0,3, `national` 1,0
  (`Parameters.revival_levels`).
- Obce, kde jazyk už nikdo nemluví, ho dostanou zpět jako **noví mluvčí**
  (2 % nebo 5 % obyvatel): od sousedů, kteří ho ještě mluví, jinak z písma.
  Učí se ho jako druhý jazyk, s interferencí z dosavadního jazyka. Bez
  mluvčích i bez písma jazyk oživit nejde.
- Loajalita brzdí odchod od jazyka, ne návrat k němu.
- Původní jazyk regionu si pamatuje území (`Territory.native_language`),
  takže stačí zadat region.

Jestli se obrození ujme, rozhoduje dál status a demografie.
`scripts/v2_revival.py`: hlavní město jazyka `a` a region `x` jazyka `b`
s vlastní identitou, od roku 0 vynucování. Čísla jsou podíl obyvatel
regionu, kteří doma mluví jazykem `b`:

| varianta | 75 | 150 | 300 | 400 | 500 | 700 | 1 000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| bez obrození | 0,65 | 0,23 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| hnutí od 75, stát trvá | 0,66 | 0,26 | 0,02 | 0,00 | 0,00 | 0,00 | 0,00 |
| národní hnutí, norma a škola od 75 | 0,81 | 0,84 | 0,87 | 0,88 | 0,89 | 0,89 | 0,89 |
| odtržení a národní obrození od 75 | 0,85 | 0,95 | 1,00 | 1,00 | 1,00 | 1,00 | 1,00 |
| vymřelý jazyk z písma: odtržení a obrození od 400 | 0,70 | 0,32 | 0,00 | 0,06 | 0,17 | 1,00 | 1,00 |
| totéž se školou v obrozeném jazyce | 0,70 | 0,32 | 0,00 | 0,07 | 0,48 | 1,00 | 1,00 |

Samotné hnutí proti vynucujícímu státu nestačí (typ Bretaň). S vlastní
normou a školou jazyk vydrží (typ Wales a Katalánsko). Vlastní stát
přechod obrátí. Vymřelý jazyk s písmem oživí vlastní stát za 200–300 let
(typ hebrejština).

Úspěch je až příliš spolehlivý. Irsko mělo vlastní stát i školu, a přesto
obrození selhalo, protože angličtina měla celosvětovou prestiž, kterou
model nezná. Autor může sílu obrození zvolit slabší.

## Omezení

- **Práh prvního mluvčího.** Přechod začne, až když by za generaci přešel
  aspoň jeden člověk. Slabý tlak v odlehlém nebo velmi loajálním regionu
  proto nezačne nikdy. Hory se silnou identitou tak drží jazyk i při
  vynucování, což u Baskicka sedí, ale je to práh, ne rozložení.
- **Obousměrný je jen přechod rozběhnutý státem nebo obrozením.**
  Přechody z dosavadních scénářů (dobytí, trh) zůstávají jednosměrné.
  Prestiž mimo svět (světový jazyk) model nezná.
- **Demografie je deterministická.** Podíly nezávisí na seedu, náhoda
  působí jen na jazyk samotný.
- **Mezi dialekty téže linie přechod nefunguje.** Přechod funguje jen mezi
  liniemi (`Code.language`). Regiony společného protojazyka, které se
  rozešly v různé pozorované jazyky, se jen srovnávají sítí, k přechodu
  mezi nimi nedojde.
- **Norma se nezmění.** Spisovný jazyk se zapíše jednou. Revize normy
  podle jiného nářečí a jiné písmo přirozeně nejsou.
- Lingua franca se zadává, sama nevzniká (výběr podle dosahu obchodní
  sítě je další krok).
- Všechny úrovně jsou autorské odhady. Kalibraci zbývá udělat proti tempu
  přechodu (Fishman: tři generace), proti francouzštině 1794–1950 a
  proti přežití jazyků v Baskicku a Walesu.

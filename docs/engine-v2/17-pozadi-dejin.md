# Pozadí dějin

Sepsáno 2026-11-01. Modul `cee.v2.background`, pole `WorldSpec.background`.

## Proč

Kalibrace retence (M7) ukázala, že izolovaný svět mění slovní zásobu
pomaleji než skutečné jazyky a že tempo nehýbe ani tempo lexikálních změn,
ani velikost vesnic. V modelovém světě se mezi událostmi autora nic neděje,
kdežto ve skutečnosti se pořád něco děje. Pozadí dějin doplní drobné
události, které svět generuje sám.

## Události

Všechny pracují s kraji (`region`). Vesnice si najdou až při provedení
(`polity.groups_in`, `polity.seat_of`), takže fungují i po přechodu
k jinému jazyku nebo po migraci. Do historie se zapisují s
`background=True` a export je má na časové ose.

| Událost | Co udělá | Druh v historii |
|---|---|---|
| `Plague(year, regions, mortality)` | domácí skupiny kraje ztratí 15–40 % lidí (silnější drift) | `plague` |
| `Recovery(year, regions, factor)` | o 2–4 generace později populace doroste (populace jinak nerostou) | `recovery` |
| `Resettlement(year, source, target, share)` | 5–15 % lidí kraje se přestěhuje do sídla sousedního kraje a učí se tam jeho řeč (`events.Migration`) | `resettlement` |
| `TradeShift(year, (a, b), factor)` | vazby mezi vesnicemi dvou sousedních krajů zesílí ×1,5–3; po 100–300 letech zase upadnou | `trade` |
| `PrestigeShift(year, region, factor)` | základní prestiž skupin kraje ×0,7–1,4, pak `polity.refresh` | `prestige` |
| `ForeignElite(year, conqueror, region)` | soused jiného jazyka dosadí v sídle kraje elitu (`events.Conquest`, síla vazby a prestiž z `Parameters.background_elite_*`); jen jednou na dvojici | `foreign_elite` |
| `EliteAssimilation(year, conqueror, region)` | o 100–300 let později elita splyne s místními a zanikne; výpůjčky zůstanou | `elite_assimilation` |

## Generátor

`background.generate(regions, start, end, level_name, seed, params)`: po
krocích 25 let, v každém kraji a pro každý druh jeden Poissonův los
s očekáváním `background_rates[druh] × background_levels[míra] × 25/100`.
Vlastní proud náhody `generator(seed, "background")` na ostatní náhodu
enginu nesahá. Sousedství se bere oboustranně z `RegionSpec.neighbours`.
Události pozadí se řadí za události autora; ve stejném roce jde autor
první (`Simulation` řadí podle roku a pořadí).

| `Parameters` | Výchozí |
|---|---|
| `background_levels` | `none` 0, `calm` 0,3, `normal` 1, `turbulent` 2,5 |
| `background_rates` (na kraj a století) | mor 0,08, přesídlení 0,12, obchod 0,12, prestiž 0,08, cizí elita 0,02 |
| `background_spans` (rovnoměrně mezi `low` a `high`) | úmrtnost moru 0,15–0,4, obnova 2–4 kroky, přesídlení 0,05–0,15, obchod ×1,5–3 na 4–12 kroků, prestiž ×0,7–1,4, splynutí elity za 4–12 kroků |
| `background_elite_prestige`, `_link`, `_share` | 2, **0,1** (kalibrováno níže), 0,1 obyvatel sídla |

Při `normal` vychází asi 4 události na kraj za tisíciletí (plus obnovy a
úpadky obchodu). Výchozí míra popisu světa je `none`, takže stávající světy
i otisky (`scripts/v2_digests.py`) zůstaly beze změny.

## Kalibrace retence

`scripts/v2_calibrate_retention.py --backgrounds none normal turbulent [--contact] [--set …] --seeds 1-8`.
Šest krajů 3 × 2 po třech vesnicích, populace 500 na hustotu. S
`--contact` mluví spodní řada jazykem `b`. Zděděné slovo je jen to, které
měl jazyk skupiny na počátku. Výpůjčka je každé slovo s morfémem druhého
jazyka, ať je v dárci zděděné, nebo nové. Cizí elity se nepočítají. Číslo
je podíl Swadeshova jádra (100 pojmů) se zděděným slovem, průměr 8 seedů.
`--set` přidá varianty přepisů `Parameters` (`w.tlak=váha` pro
`pressure_weights`, `r.změna=násobek` pro `change_rates`).

| Svět | Pozadí | 1 000 let | 2 000 let | 3 000 let | za tisíciletí (3 000) | výpůjčky v jádru / ve zbytku (3 000) |
|---|---|---|---|---|---|---|
| izolovaný | none | 0,982 | 0,876 | 0,815 | 0,934 | 0 |
| izolovaný | normal | 0,980 | 0,877 | 0,814 | 0,934 | 0 |
| izolovaný | turbulent | 0,982 | 0,874 | 0,794 | 0,926 | 0 |
| dva jazyky | none | 0,982 | 0,885 | 0,810 | 0,932 | 0,071 / 0,072 |
| dva jazyky | normal | 0,851 | 0,703 | 0,577 | 0,832 | 0,253 / 0,306 |

Cíle: izolovaný jazyk asi 95–97 % za tisíciletí (islandština; Bergsland
& Vogt 1962), jazyk v kontaktu asi 85–88 %.

Rozklad podle druhu (dva jazyky, `normal`, vždy jen jeden druh, 4 seedy,
1 000 let): mor, přesídlení, obchod i prestiž nechají jádro na 0,978,
cizí elita ho sníží na 0,856.

### Zahřívání: proč je první tisíciletí pomalé

Protojazyk startuje bez jakékoli variability: každá vesnice má pro každý
pojem jediné slovo. Souběžné varianty (rozpracované inovace a synonyma)
se teprve hromadí. Podíl menšinových variant (izolovaný svět, seed 1):

| rok | 250 | 500 | 1 000 | 1 500 | 2 000 | 2 500 | 3 000 |
|---|---|---|---|---|---|---|---|
| zděděné jádro i zbytek | 1,000 | 1,000 | 0,989 | 0,947 | 0,885 | 0,858 | 0,840 |
| menšinový podíl variant | 0,004 | 0,008 | 0,027 | 0,041 | 0,056 | 0,055 | 0,064 |

Variabilita se ustálí kolem roku 2 000. Mezi lety 2 000 a 3 000 vychází
retence asi 95 % za tisíciletí, tedy uvnitř cíle pro izolovaný jazyk.
Průměr 93,4 % kazí první tisíciletí, které je téměř bez změn, a hned po
něm druhé, které je rychlé, protože se nahromaděné varianty právě
prosazují. Zažitost (`entrenchment`) a konformita tempo brzdí, ale tvar
křivky zůstává i bez nich. Jasnost slova (`lexical_clarity`) na retenci
skoro nepůsobí.

### Souběžná variabilita protojazyka (`cee.v2.variation`)

Náprava zpoždění. Předběh (síť vesnic žije před začátkem 2 000 let jen
s lexikálními změnami) zpoždění odstranil, ale stál víc než celý běh
(`valley-50` 38 s → 143 s) a pokaždé dal statisticky totéž. Engine proto
používá jen jeho statistiku: `scripts/v2_measure_variation.py` ji jednou
změří (sítě 3 × 2 a 4 × 3 kraje po třech vesnicích, seedy 1–8, 13 s) do
`cee/data/v2_standing_variation.json` a `variation.seed` ji rozdá při
startu simulace bez simulování (0,1 s):

- pro každý pojem, vesnici a druh změny, který u pojmu jde v protojazyce
  navrhnout, Poissonův počet variant podle naměřené hustoty přeživších
  variant toho druhu (koše podle frekvence pojmu; varianty vzniklé až
  řetězením se připočtou k pojmům, kde druh jde);
- skutečná změna navrhne skutečné slovo (posun významu, odvozenina,
  složenina…);
- vrcholový podíl z naměřených kvantilů, o 1, 2, 3 vazby dál naměřený
  násobek (asi 0,3; 0,1; 0,08), jen ve vesnicích stejného jazyka;
- slovo autora zůstane převládající: součet menšin u pojmu je nanejvýš
  `Parameters.variation_cap` (0,4). Varianta, která slovo autora v předběhu
  vytlačila, se do statistiky nepočítá (jinak by ho hned zase vytlačila).

Hustotu násobí `Parameters.standing_variation` (výchozí 1, 0 vypne).
Naměřené hodnoty: odvozenina 0,32–0,62 varianty na vesnici a pojem,
složenina 0,22–0,31, převod mezi slovními druhy 0,13–0,18, posun významu
0,10–0,12, nové kořeny a kontaminace 0,01–0,02; medián vrcholu 2,8 %
u vzácných pojmů a 1,2 % u nejčastějších.

Izolovaný svět (8 seedů, jádro): bez variability 0,982, 0,892, 0,930 po
tisíciletích; s ní 0,900, 0,918, 0,949. Zpoždění zmizelo. Zbývá mírný
pokles tempa v čase, protože pojmy se mění různě rychle (slabá slova
padnou první, nová jsou pak dlouho stabilní; Pagel a kol. 2007). Tempo
lexikálních změn retenci skoro nemění (poloviční tempo: 0,904 za první
tisíciletí): o ní rozhoduje výběr a drift, ne přísun inovací.

Svět dvou jazyků (8 seedů, jádro / výpůjčky v jádru): bez pozadí 0,915,
0,834, 0,775 / 0,022, 0,057, 0,090; s pozadím `normal` 0,779, 0,654,
0,550 / 0,139, 0,203, 0,263. Cíl kontaktu 85–88 % za tisíciletí pozadí
`normal` přestřelí: výpůjčky přináší hlavně cizí elita, jejíž síla
(`events.Conquest`: prestiž 2, vazba 0,5 ke všem poddaným) je odhad.

### Kalibrace cizí elity

Pracovní cíl (odhad, ne naměřená data): výpůjčky v základním slovníku
nanejvýš asi 10 % za 3 000 let středně silného kontaktu a kulturní slova
víc než základní. WOLD (Haspelmath & Tadmor 2009; Tadmor, Haspelmath
& Taylor 2010) ukazuje, že nejodolnější jsou prostorové vztahy, části těla
a smyslové vnímání a že jména se půjčují snáz než slovesa; přesné podíly
pro Swadeshův seznam se nepodařilo ověřit. Retence kontaktu 85–88 % za
tisíciletí.

Dvě zjištění: (1) míšení závisí jen na součinu síla vazby × prestiž
elity (prestiž 1 s vazbou 0,3 dá totéž co 2 s 0,15); (2) elita bez konce
dodávala výpůjčky celé tisíciletí, proto přibylo splynutí
(`EliteAssimilation`). Samotné splynutí ale skoro nepomohlo, výpůjčky
vzniknou během prvních generací. Rozhoduje síla vazby (4 seedy, dva
jazyky, pozadí `normal`, jádro / výpůjčky v jádru):

| `background_elite_link` | 1 000 let | 3 000 let | za tisíciletí (3 000) |
|---|---|---|---|
| 0,5 (dřív) | 0,767 / 0,151 | 0,575 / 0,249 | 0,832 |
| 0,25 | 0,829 / 0,095 | 0,625 / 0,197 | 0,855 |
| 0,15 | 0,867 / 0,057 | 0,671 / 0,154 | 0,875 |
| **0,1** | 0,884 / 0,043 | 0,701 / 0,132 | 0,888 |
| bez pozadí | 0,913 / 0,023 | 0,778 / 0,087 | 0,920 |

Výchozí je 0,1: výpůjčky v jádru nejblíž pracovnímu cíli, retence na
horní hraně pásma kontaktu. Autorova událost `Conquest` má dál vlastní
výchozí hodnoty (prestiž 2, vazba 0,5): to je dobytí, ne drobná elita.

Tempo `LexicalBorrowing` na výsledek měřitelně nepůsobí (násobek 0, 1
i 10 dá v jádru po 3 000 letech 0,700 / 0,691 a výpůjčky 0,134 / 0,138).
Navržená výpůjčka se ujme vzácně, protože jako neprůhledné slovo nemá
výhodu motivace jako odvozenina (`Motivation`: odvozenina +0,15, výpůjčka
0). Výpůjčky tak vznikají hlavně šířením nových slov souseda přes hranici
a přes elity.

Zbývající rozpory: kulturní slova se půjčují méně než základní (0,102
proti 0,132), a izolovaný jazyk je s 90 % za první tisíciletí pod cílem
95–97 %; kontakt proto ubere jen asi 1,6 bodu místo zhruba deseti.

### Výpůjčky

Kontakt přes hranici výpůjčky dělá, ale jen ze slov, která v sousedním
jazyce nově vznikla: inovace má sociální ocenění (`LexicalActuation`)
v každé skupině, i v cizí. Zděděné slovo souseda přichází vazbou jako
varianta bez ocenění a nikdy nepřeváží. Proto vznikla změna
`LexicalBorrowing` (`changes/lexicon.py`): skupina převezme slovo souseda
jiného jazyka s mírou úměrnou podílu vstupu z cizího jazyka (otevřenost ×
síla vazby × prestiž dárce) a přenositelnosti slova
(`contact.borrowing_factor`, vzácná slova snáz). Dál se výpůjčka šíří
jako každá inovace.

Výpůjčka se ujme podobně jako domácí inovace: podílu 0,1 ve vesnici
dosáhne 3 % výpůjček, 10 % posunů významu a 13 % odvozenin (1 000 let,
seed 1). Nad 0,5 se v prvním tisíciletí nedostane skoro žádná inovace,
takže ani stonásobné tempo výpůjček retenci prvních 3 000 let skoro
nezmění (dva jazyky bez pozadí: výpůjčky v jádru 0,071 → 0,075).
Tempo `LexicalBorrowing.base_rate` (1e-3) proto zůstává nekalibrované:
kalibrovat jde až v ustáleném stavu, po vyřešení zahřívání.

Kulturní slova se v modelu půjčují jen o málo víc než základní (0,306
proti 0,253 při `normal`). Ve WOLD je rozdíl mnohem větší (Haspelmath
& Tadmor 2009); rozšíření slovníku v kalibraci ale není opravdová
kulturní slovní zásoba, takže srovnání je jen orientační.

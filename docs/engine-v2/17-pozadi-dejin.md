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
| `ForeignElite(year, conqueror, region)` | soused jiného jazyka dosadí v sídle kraje elitu (`events.Conquest`); jen jednou na dvojici | `foreign_elite` |

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
skoro nepůsobí. Náprava (počáteční variabilita protojazyka, nebo jeho
zahřátí před začátkem) je změna modelu, která pohne všemi otisky; zatím
nezavedena.

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

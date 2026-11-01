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

`scripts/v2_calibrate_retention.py --backgrounds none normal turbulent [--contact] --seeds 1-8`.
Šest krajů 3 × 2 po třech vesnicích, populace 500 na hustotu. S
`--contact` mluví spodní řada jazykem `b`. Zděděné slovo je jen to, které
měl jazyk skupiny na počátku; slovo druhého jazyka je výpůjčka. Cizí elity
se nepočítají. Číslo je podíl Swadeshova jádra (100 pojmů) se zděděným
slovem, průměr 8 seedů.

| Svět | Pozadí | 1 000 let | 2 000 let | 3 000 let | za tisíciletí (3 000) | výpůjčky v jádru (3 000) |
|---|---|---|---|---|---|---|
| izolovaný | none | 0,982 | 0,876 | 0,815 | 0,934 | 0 |
| izolovaný | normal | 0,980 | 0,877 | 0,814 | 0,934 | 0 |
| izolovaný | turbulent | 0,982 | 0,874 | 0,794 | 0,926 | 0 |
| dva jazyky | none | 0,982 | 0,885 | 0,810 | 0,932 | 0,001 |
| dva jazyky | normal | 0,851 | 0,703 | 0,577 | 0,832 | 0,108 |
| dva jazyky | turbulent | 0,822 | 0,563 | 0,424 | 0,751 | 0,174 |

Cíle: izolovaný jazyk asi 95–97 % za tisíciletí (islandština; Bergsland
& Vogt 1962), jazyk v kontaktu asi 85–88 %.

Rozklad podle druhu (dva jazyky, `normal`, vždy jen jeden druh, 4 seedy,
1 000 let): mor, přesídlení, obchod i prestiž dávají jádro 0,978 a nulové
výpůjčky, cizí elita jádro 0,856 a výpůjčky 0,105.

### Co z toho plyne

- **Izolovaný svět pozadí skoro nemění.** Mor zesílí drift jen na pár
  generací a přesídlení a obchod uvnitř jednoho jazyka nepřinesou nic
  nového. Retence 93,4 % za tisíciletí je o 2–3 body pod cílem. Hlavní
  vadou je tvar křivky: první tisíciletí 98 %, druhé 89 %, třetí 93 %
  (zpoždění prvního tisíciletí, zvlášť k diagnóze).
- **Kontakt přes hranici sám výpůjčky nedělá.** V `transmission` míchá
  vazba mezi jazyky cizí varianty jen přes filtr přenositelnosti
  (`contact.borrowing_factor`). Jedna slabá pohraniční vazba mezi několika
  domácími dá výpůjčce malý podíl, ale nikdy převahu. Proto nic
  nepřinese ani zesílený obchod, ani přesídlení k sousedům jiného jazyka.
- **Všechny výpůjčky přináší cizí elita** (silné vazby ke všem poddaným,
  prestiž 2). Kontaktní svět při `normal` sice padne do cíle (85,1 %
  v prvním tisíciletí), ale jen díky druhu s četností 0,02 na století.
  Je to křehké a neodpovídá to skutečnosti: většina výpůjček vzniká
  obchodem a dvojjazyčností, přičemž se nejdřív půjčují kulturní slova
  (Thomason & Kaufman 1988). V modelu se kulturní slova půjčují jen
  o málo víc než jádro (0,838 proti 0,851).
- Konstanty se kvůli cílům neladily. Další krok je změna modelu:
  výpůjčky z potřeby a od dvojjazyčných mluvčích v obchodním kontaktu.

# Regiony jako sítě vesnic (`region_world`)

Datum: 31. 10. 2026. Větev `engine-v2-dynamika`. Navazuje na rozhodnutí
uživatele po M7a ([`12-kalibrace-m7a.md`](12-kalibrace-m7a.md)):

- kalibrovat v měřítku, které použije aplikace (regiony), ne na řadě
  izolovaných vesnic;
- autor světa zadává **hustotu osídlení**, ne počty lidí: hustota je
  relativní a stálá (hustá místa zůstávají hustá), absolutní čísla autor
  nezná;
- region se simuluje přes **síť vesnic** a sousední regiony se spojují
  přes pohraniční vesnice.

## Scénář

`scenarios.region_world(regions, ...)` s `Region(id, position, density,
neighbours, villages, prestige, openness, immigration)`:

- region = území úrovně `region` s vesnicí v těžišti a ostatními na prstenci
  o poloměru `village_spacing` (výchozí 10 km);
- uvnitř regionu gravitační vazby (`gravity_links`, dosah 2 × rozestup);
- mezi sousedními regiony **jediná vazba** mezi nejbližší dvojicí vesnic;
  hranice regionu je tak místem, kde se šíření zpomalí a izoglosy hromadí;
- populace vesnice = hustota × `Parameters.population_per_density`
  (výchozí 500 = dosavadní vesnice). Převod hustoty na velikost populace,
  která řídí drift, je kalibrační parametr, ne údaj od autora;
- protojazyk a jeho přepínače (`phonology`, `syntax`, `grammar`, přízvuk…)
  jsou tytéž jako u `village_grid`; obě funkce sdílejí `_seed_language`
  (refaktoring otisky nezměnil).

Testy `tests/v2/test_v2_region_world.py`: vesnice, populace podle hustoty
a parametru, vazby přes hranici jen mezi pohraničními dvojicemi sousedních
regionů, odmítnutí neplatných regionů, determinismus a to, že vesnice téhož
regionu jsou si po 1 500 letech bližší než vesnice přes hranici.

## Měření kontinua

`scripts/v2_region_continuum.py`: čtyři regiony ve čtverci (40 km od sebe,
každý sousedí se dvěma), po pěti vesnicích, plný model, seedy 1..4.
Průměrná vzdálenost kódů (`observe.code_distances`, táž míra jako prahy
dialektu a jazyka):

| rok | jazyků (pozorovatel) | sousedé v regionu | přes hranici | vzdálené regiony |
|---:|---:|---:|---:|---:|
| 500 | 1,0 | 0,019 | 0,024 | 0,025 |
| 1 000 | 1,0 | 0,071 | 0,105 | 0,125 |
| 2 000 | 3,5 | 0,160 | 0,264 | 0,312 |
| 3 000 | 4,0 | 0,207 | 0,344 | 0,405 |

- **Hranice funguje**: sousedé v regionu < přes hranici < vzdálené regiony
  ve všech letech. Po 3 000 letech pozorovatel rozliší čtyři jazyky, právě
  podle regionů; nikdo je tak nezadal.
- **Kontinuum je stále moc roztříštěné**: sousedé v regionu přesáhnou
  pásmo nářečních atlasů (0,05–0,15) asi po 2 000 letech. Čtyři jazyky na
  80 km bez jakékoli normy jsou na 3 000 let nejspíš moc. Mísení je slabé
  proti tempu změn (známá mezera); ladí se v M7 (`gravity_links`, otevřenost,
  tempo změn) proti atlasům.
- **Výkon**: 20 vesnic, plný model, 3 000 let ≈ 16 s. Kalibrační svět
  s 10 regiony po 5 vesnicích na 5 000 let by trval odhadem přes minutu na
  běh; stovky běhů kalibrace jsou hodiny při čtyřech procesech.

## Další krok

1. Kalibrace M7 na `region_world`: nářeční kontinuum podle atlasů (síla
   vazeb, otevřenost), převod hustoty na populaci, tempo; stacionarita WALS
   a kalibrace prajazyk → dcery (Grambank, tabulka rekonstrukcí).
2. Ověření měřítka: tentýž jazyk jako jemnější a hrubší síť vesnic musí dát
   podobné výsledky.
3. Výkon, než se kalibrace rozběhne naplno.

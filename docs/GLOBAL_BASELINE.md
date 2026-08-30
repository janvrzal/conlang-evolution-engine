# Globální kalibrace změn

CEE rozlišuje tři typy empirických dat. PHOIBLE je synchronní kontrola
inventáře. Lexibank a podobné CLDF wordlisty poskytují formy, koncepty a často
kognátní sady; bez směrované rekonstrukce z nich ale nelze poctivě tvrdit
konkrétní změnu `a → b`. Globální kalibrace proto přijímá pouze anotovaná,
směrovaná pozorování.

## Vstupní kontrakt

Data jsou mimo Git a manifest zůstává vedle nich. Každý zdroj musí mít
komerčně slučitelnou licenci (`CC0-1.0`, `CC-BY-4.0`, `BSD-3-Clause` nebo
`MIT`), verzi a citaci. Licence s `NC` nebo `SA` jsou odmítnuty dřív, než z
nich vzniknou distribuované váhy.

`manifest.json`:

```json
{
  "schema_version": 1,
  "smoothing": 1.0,
  "sources": [{
    "id": "open-curation-v1",
    "path": "changes.csv",
    "license": "CC-BY-4.0",
    "version": "2026-09",
    "citation": "Úplná citace zdroje a anotace",
    "url": "https://example.org/source"
  }]
}
```

`changes.csv`:

```csv
schema_id,environment,family_id,language_id,area
lenition,conditioned,atla1278,language-id,South America
vowel_shift,unconditional,indo1319,language-id,Eurasia
```

`schema_id`, `environment` a `family_id` jsou povinné. `family_id` má být
stabilní identifikátor (typicky Glottocode), nikoli volný název rodiny.

## Fronta reflexů z historického CLDF

Historický CLDF, který propojuje protoformy a reflexy přes `Origin_ID`, lze
proměnit na deterministickou frontu pro kurátora. Příkaz **neodvozuje** z
dvojice forem zvukový zákon: k tomu chybí zarovnání, pravidelnost napříč
lexémy a odborné posouzení. Výslovné výpůjčky přeskočí.

```bash
cee calibrate candidates \
  --forms /data/family/forms.csv \
  --family-id drav1251 \
  --proto-language proto-dravidian \
  --out /data/family/reflex-candidates.csv
```

Kurátor z fronty vytváří až výsledné `changes.csv` a uchová identifikátory
obou forem i přesnou citaci ve zdrojovém pracovním souboru.

## Režimy profilů

CEE vždy uvádí původ vah. Vestavěné `heuristic-default`,
`heuristic-conservative` a `heuristic-dynamic` jsou transparentní autorské
presety; nejsou vydávány za empirickou kalibraci. Empirický profil vzniká jen
z `cee calibrate global` nad licenčně auditovaným manifestem a má přednost před
heuristickým profilem. Režim `user-local-research` je vyhrazen pro data
uživatele: CEE je nestahuje, neodesílá ani nedistribuuje jejich odvozené váhy.

Index Diachronica se kvůli CC BY-NC-SA 3.0 nedodává ani jako vestavěný profil,
ani jako automatický downloader. Případné použití je věcí samostatné licence a
odpovědnosti uživatele; nesmí se prezentovat jako profil distribuovaný CEE.

### Lokální výzkumný profil

Uživatel může dodat vlastní CSV se sloupci `source`, `target` a volitelným
`context`. CEE jej čte pouze lokálně a vytvoří profil označený
`user-local-research`; do projektu se neukládají vstupní data, jen SHA-256
otisk. Nejednoznačné řádky se nepřiřazují. Tento režim není náhradou licence
ani distribuovaný empirický profil.

```bash
cee calibrate research-profile \
  --changes /data/moje-zmeny.csv \
  --out /data/moj-vyzkumny-profil.json \
  --acknowledge-local-research
```

## Globální korespondence

GLED je vhodný otevřený doplněk (CC BY 4.0): obsahuje globálně pokryté
kognátní sady a fonologická zarovnání, ale ne směr vývoje. CEE z něj proto
vytváří samostatný referenční profil `identity`, `substitution` a `gap`,
vyvážený podle rodin; nekrmí jím přímo volbu směrovaného schématu.

```bash
cee calibrate correspondences --gled-tsv /data/gled.tsv --out /data/gled-correspondences.json
```

## Kalibrace makro-divergence

Příkaz níže vytvoří deterministický dvouvětvový benchmark nad syntetickým
protolexikonem, zarovná odpovídající potomky a vybere kombinaci rychlosti,
podílu deletivních zákonů a konzervativnosti nejbližší globálnímu GLED
profilu. Eroze kod se ladí až v navazujícím, podmíněném kroku, aby se
nepřekrývala s obecným podílem mazání. Příkaz neučí směr jednotlivých pravidel.

```bash
cee calibrate macro \
  --target /data/gled-correspondences.json \
  --preset src/cee/data/presets/fantasy_preset.yaml \
  --repeats 3 \
  --out /data/gled-macro-report.json
```

Hellingerova vzdálenost je 0 při shodě a 1 při krajně rozdílném profilu.
Report navíc vypisuje skutečně smazané segmenty podle schématu, takže lze
odlišit vysoký podíl mezer způsobený několika deletivními kaskádami od běžné
divergence. Slouží k hledání přespříliš konzervativní či erozivní oblasti
parametrů; nejde o univerzální výchozí preset, dokud neprojde více inventářů a
časových hloubek.

Každý kandidát se standardně opakuje třikrát s odlišným, ale deterministicky
odvozeným protolexikonem i seedem simulace; report obsahuje jejich průměr.
Tím se nemůže vybrat parametr jen proto, že jednomu náhodnému lexikonu sedl
neobvyklý sled pravidel.

Generátor navíc nepřipustí tutéž širokou inovaci v intervalu kratším než 500
let. Nejde o tvrzení, že se například synkopa nemůže v jazyce vrátit; je to
ochrana generativního modelu před artefaktem, kdy tentýž abstraktní mechanismus
v krátkém sledu vyrábí a zase maže stejný strukturální materiál.

## Referenční běh (2026-08-30)

Nad GLED `20221127/gled.tsv` (SHA-256
`3e3b093afb8a7479bcf403905c6ddbd2f8bf7984877f11afc83e58d717d5acfd`) měl
rodinně vyvážený cíl `identity=66,28 %`, `substitution=18,12 %`, `gap=15,60 %`.
Tříopakovaný dvouvětvový benchmark (200 lexémů, 1 500 let, seedy 42–44) našel
nejbližší kandidát `change_rate=1.5`, `deletion_rate=0.5`,
`conservatism=0.2`: `identity=56,0 %`, `substitution=23,1 %`, `gap=20,9 %`,
Hellinger `0,075`.

To je kontrolní bod, nikoli tvrzení o kalibraci „všech jazyků“: zejména mezery
jsou stále o 5,3 p. b. výše než referenční profil. Další krok je podmíněně
ladit typ kody a délku nad více časovými hloubkami, ne zpětně vybírat jeden
náhodný seed s lepším skóre.

## Odhad a metriky

1. V každé rodině se nejprve normalizují počty změn na distribuci.
2. Tyto distribuce se zprůměrují napříč rodinami. Rodina s 10 000 záznamy tak
   nemá větší váhu než rodina s 20 dobře anotovanými záznamy.
3. Dirichletovo vyhlazení ponechá nenalezeným schématům nenulovou šanci.
4. Výstup obsahuje podíl každého schématu a prostředí, počet pozorování,
   počet rodin, SHA-256 každého vstupu, licenci, verzi a citaci.

To jsou metriky *datového profilu*. V2a proti generátoru se měří odděleně
Hellingerovou vzdáleností typu změny a prostředí a rozdílem rychlosti za
tisíciletí. Než bude k dispozici dostatečně široký otevřený směrovaný korpus,
nesmí se z tohoto nástroje reportovat „globální skóre realismu“.

## Použití

```bash
cee calibrate global --manifest /data/global/manifest.json --out /data/global/baseline.json
cee calibrate measure --baseline /data/global/baseline.json --preset src/cee/data/presets/fantasy_preset.yaml
cee simulate ... --global-baseline /data/global/baseline.json
```

Baseline upraví pouze kladné váhy schémat povolené presetem; sama nemůže
zapnout schéma, které autor presetu zakázal. Simulace je i s baseline offline a
deterministická.

`cee calibrate measure` hlásí Hellingerovu vzdálenost (0 = stejná
distribuce, 1 = zcela odlišná) pro typ změny i prostředí a podíl schémat
baseline, která generátor umí vytvořit. Bez časových intervalů ve vstupním
korpusu záměrně nehlásí rychlost změn za tisíciletí.

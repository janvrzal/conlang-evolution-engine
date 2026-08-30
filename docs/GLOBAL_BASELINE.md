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

## Globální korespondence

GLED je vhodný otevřený doplněk (CC BY 4.0): obsahuje globálně pokryté
kognátní sady a fonologická zarovnání, ale ne směr vývoje. CEE z něj proto
vytváří samostatný referenční profil `identity`, `substitution` a `gap`,
vyvážený podle rodin; nekrmí jím přímo volbu směrovaného schématu.

```bash
cee calibrate correspondences --gled-tsv /data/gled.tsv --out /data/gled-correspondences.json
```

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

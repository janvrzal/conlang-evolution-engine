# Conlang Evolution Engine (CEE)

Generative simulator of language evolution based on feature matrices, absolute
chronologies, and historical phonology modeling.

Technický whitepaper: [`docs/CEE_master.md`](docs/CEE_master.md).
Konvence a pravidla pro práci v repu: [`AGENT.md`](AGENT.md).
Ověřený implementovaný rozsah a hranice: [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).

CEE není replikátor historické Země. Jeho výzkumná osa je reprodukovatelná
simulace důsledků explicitních zásahů — například jak vyšší synkopa, kontakt
nebo analogie promění rodinu jazyků v čase. Empirická data slouží jako volitelné
priory a diagnostiky, nikoli jako jediná definice správného výstupu; podrobnosti
jsou ve whitepaperu v [hlavní tezi](docs/CEE_master.md#21-hlavní-teze) a
[experimentálním protokolu](docs/CEE_master.md#511-experimentální-protokol-a-funkčnost).

## Instalace

```bash
python3.11 -m venv .venv && .venv/bin/pip install -e '.[dev,ui]'
```

Extra `ui` doinstaluje FastAPI a uvicorn pro `cee ui`; jádro enginu je nepotřebuje.
Výchozí ukládání výsledků je lokální (`~/.cee/runs`), takže Neo4j není pro
běžný běh potřeba. Pro volitelný Neo4j adaptér nainstalujte `.[neo4j]` a
nastavte `CEE_GENEALOGY_STORE=neo4j` spolu s `CEE_NEO4J_URI`,
`CEE_NEO4J_USERNAME` a `CEE_NEO4J_PASSWORD`.

## Použití

Aplikace ruční sady pravidel na proto-lexikon, s volitelnou validací proti
doloženým formám:

```bash
cee apply --proto-csv latin_v1.csv --rules-yaml latin_rules.yaml --out-csv out.csv --ground-truth-csv latin_v1.csv
```

Simulace celé rodiny (větvení + kontakty) v globálním lockstepu:

```bash
cee simulate --topology-yaml scenario_split.yaml --proto-csv fantasy_v1.csv
```

Generátor zvukových změn místo ručních pravidel — hrany bez pravidel si je
nechají vygenerovat podle biomu uzlu:

```bash
cee simulate --topology-yaml scenario_generator.yaml --proto-csv fantasy_v1.csv --preset-yaml src/cee/data/presets/fantasy_preset.yaml
```

Volitelná empirická fonologická cache se stahuje jen explicitně; simulace pak
neběží přes síť:

```bash
cee phonology update-data
cee simulate --topology-yaml scenario_generator.yaml --proto-csv fantasy_v1.csv \
  --preset-yaml src/cee/data/presets/fantasy_preset.yaml --empirical-phonology
```

Globální váhy změn se nevyrábějí z PHOIBLE (to obsahuje inventáře, ne směry
historických změn). Pro licenčně auditovaný korpus anotovaných změn viz
[`docs/GLOBAL_BASELINE.md`](docs/GLOBAL_BASELINE.md):

```bash
cee calibrate global --manifest /data/global/manifest.json --out /data/global/baseline.json
cee simulate ... --global-baseline /data/global/baseline.json
```

Bez `--out-dir` se výsledky ukládají do `runs/run_YYYYMMDD_HHMMSS/`.

## Testy

```bash
.venv/bin/python -m pytest
cd ui && npm run check && npm run lint && npm test && npm run build
```

Sada obsahuje validaci **V1** (výstupní brána Etapy 1 dle `docs/CEE_master.md`
5.2): derivace latinského lexikonu publikovanou sadou zvukových zákonů
a měření shody s doloženými formami.

## Stav projektu

CEE už obsahuje lokální projektový editor, časovou mapu, genealogický export,
CLICS4/DatSemShift, volitelná PHOIBLE cache a diachronní
historii slov. Kalibrační vědecké brány, content-addressed rerolly a produktové
exporty jako CLDF/PDF/Anki jsou zatím plánované; úplný přehled je v
[`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).

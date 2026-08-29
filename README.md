# Conlang Evolution Engine (CEE)

Generative simulator of language evolution based on feature matrices, absolute
chronologies, and historical phonology modeling.

Technický whitepaper: [`docs/CEE_master.md`](docs/CEE_master.md).
Konvence a pravidla pro práci v repu: [`AGENT.md`](AGENT.md).

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

Bez `--out-dir` se výsledky ukládají do `runs/run_YYYYMMDD_HHMMSS/`.

## Testy

```bash
.venv/bin/python -m pytest
```

Sada obsahuje validaci **V1** (výstupní brána Etapy 1 dle `docs/CEE_master.md`
5.2): derivace latinského lexikonu publikovanou sadou zvukových zákonů
a měření shody s doloženými formami.

# ADR-001: genealogické úložiště výsledků simulace

**Stav:** přijato · 2026-08-29

## Kontext

HTTP API bylo přímo spojeno s Neo4j, připojovalo se na pevnou lokální adresu a
před zápisem nové simulace mazalo celý graf. Základní uživatelská cesta proto
nefungovala bez externí databáze a jeden projekt mohl zničit data jiného.

## Rozhodnutí

API závisí pouze na portu `GenealogyStore`. Výchozím adaptérem je
`FileGenealogyStore`, který každý běh atomicky ukládá do
`~/.cee/runs/<run_id>.json`. Běh má stabilní náhodné ID uložené v projektu;
opakovaná simulace stejného projektu nahradí jen tento soubor.

Neo4j je volitelný adaptér (`CEE_GENEALOGY_STORE=neo4j`) s připojením přes
`CEE_NEO4J_URI`, `CEE_NEO4J_USERNAME` a `CEE_NEO4J_PASSWORD`. Všechny uzly
nesou `simulation_id` a jeho mazání je striktně omezené na jeden běh.

## Důsledky

- Nový klon může simulovat, prohlížet slovník i exportovat bez Neo4j.
- HTTP endpointy jsou adresované `run_id`; data se nemíchají mezi projekty.
- JSON export je stejný pro oba adaptéry a je auditovatelný.
- Pro rozsáhlé analýzy lze Neo4j zapnout instalací `cee[neo4j]`, aniž by se
  měnil engine nebo rozhraní UI.

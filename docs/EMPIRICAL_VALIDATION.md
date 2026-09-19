# Empirická validace lexika a sémantiky

`cee diagnostic report` je diagnostická a lokálně kalibrační vrstva nad hotovým během. Není součástí rozhodování enginu ani potvrzením obecného historického modelu.

## Reprodukovatelný vstup

Každý běh používá identický explicitní seznam konceptů, odvozený z protolexikonu před simulací. JSON uvádí tento seznam a jeho SHA-256, seed, verzi simulátoru, a hash topologie, protolexikonu, presetu, sémantického grafu a všech volitelných datových souborů.

Volitelný retenční korpus je samostatný CSV/TSV vstup, nikoliv „pravda“ vložená do enginu. Vyžaduje přesně tyto sloupce:

```csv
concepticon_id,gloss,source,value,method_note
1277,WATER,Swadesh 1955,0.91,normalizováno z původní škály
```

`value` je v intervalu 0–1 a dvojice Concepticon ID + glosa nesmí být duplicitní. Vedle dat přidejte JSON manifest:

```json
{"source_version":"Concepticon 3.3.0; Swadesh 1955; Peust 2013","license":"CC-BY-4.0","imported_at":"2026-09-19"}
```

Report uvádí hash, verzi zdroje, licenci, datum importu, pokrytí podle ID, pokrytí fallbackem podle glosy a počet konceptů, pro něž zůstala heuristika. Concepticon, Swadesh 1955 a Peust 2013 jsou otevřené výchozí priory; jejich konkrétní verze a licenci nese manifest importu.

## Spuštění

```bash
cee diagnostic report --topology-yaml scenario.yaml --proto-csv proto.csv --seed 3101 --retention-corpus retention.csv --retention-manifest retention.manifest.json --out-dir runs/diagnostic-isolated
```

Vzniknou `empirical-report.json`, `empirical-branches.csv` a `empirical-report.md`.

## Metriky a meze

- Lexikální retence počítá jen živý původní kořen bez `source_id`; kontakt, domácí náhrada a ztráta jsou samostatné kategorie.
- Sémantika uvádí ztracené a nově pokryté koncepty, rozdělení velikosti polysémie a dobu soužití mezi zahájením a dokončením časované změny.
- `contact-calque` a lexémy se `source_id` nejsou započteny jako dědičná změna. Rozsah retence napříč větvemi je větevová divergence.
- Fonetická divergence kognátů se do této metriky nemíchá.
- Skok je malý/velký pouze s explicitním `concept_distance`; bez něj je `unknown`, nikoliv skrytá heuristika.

## Referenční experimenty

Použijte stejný protolexikon, seznam konceptů a seedy `3101, 3102, 3103`; porovnávejte distribuce, ne magický cíl.

| Experiment | Konfigurace | Očekávaný rozsah |
| --- | --- | --- |
| Izolovaná větev | bez `contact_edges`, balanced sémantika | 0 kontaktních náhrad. |
| Obchodní kontakt | jedna `trade` hrana s explicitním objemem | nenulové kontaktní náhrady/varianty. |
| Vysoká standardizace | `map.social.standardization: 0.9` | menší nebo stejná intenzita inovací než kontrola. |
| Dynamic vs conservative | stejné vše, mění se jen `semantic.profile` | dynamic nabízí více příležitostí; vyhodnotit citlivost. |

Pokud pokrytí korpusu nebo `concept_distance` nestačí, závěr musí mezeru otevřeně uvést. Tato vrstva poskytuje diagnostiku a lokální kalibraci, ne univerzální historický model.

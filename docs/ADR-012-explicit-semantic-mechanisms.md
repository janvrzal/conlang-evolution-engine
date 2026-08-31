# ADR-012: Explicitní mechanismy významové změny

**Status:** Accepted  
**Date:** 2026-08-31  
**Deciders:** CEE project

## Kontext

Orientovaná hrana DatSemShift a kolexifikační hrana CLICS4 dokazují vztah
mezi koncepty, ale samy běžně neurčují, zda šlo o metaforu, metonymii,
generalizaci nebo specializaci. Odvozovat typ jen z anglických glos by byl
neauditovatelný odhad.

## Rozhodnutí

Mechanismus je volitelné metadata hrany. Přijímá se pouze z kurátorovaného
grafu/YAML nebo z přesného autorova přepisu `source->target` v konfiguraci.
Podporované hodnoty jsou `metaphor`, `metonymy`, `generalization` a
`specialization`. Samotný štítek nestačí: metafora vyžaduje dvě odlišné
anotované domény, metonymie strukturální most v téže doméně a změny rozsahu
explicitní směr `broader` či `narrower`.

První tři rozšíří užití a vytvářejí období polysémie. Specializace je úplný
posun: po tomto období nový, užší význam nahradí hlavní starší užití.
Neoznačená hrana zůstává obecnou kolexifikací nebo obecným posunem.

## Důsledky

- Historie i export mohou uvést mechanismus bez falešné jistoty.
- Worldbuilder může určit typ svého záměru dříve, než existuje UI editor.
- Kvalita mechanismů roste s kurátorovanými daty; CEE je nebude halucinovat.
- Autor může doplnit `bridge` či `scope` přes relation override, ale bez
  příslušné evidence se konkrétní mechanismus nevygeneruje.

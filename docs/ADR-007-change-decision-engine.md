# ADR-007: Rozhodovací jádro pro historické inovace

**Status:** Accepted
**Date:** 2026-08-31

## Kontext

Vážený výběr schématu s následnou lokální opravou vytvářel formy bez
historického vysvětlení. Nejviditelnějším případem bylo řešení homofonie
náhodným jednosegmentovým prefixem.

## Rozhodnutí

CEE odděluje vyhodnocení tlaku od provedení změny. `ChangeDecisionEngine`
produkuje auditovatelná rozhodnutí nad aktuálním stavem jazyka. První modul
měří funkční zátěž homofonie z frekvence a deterministicky sestaveného překryvu
komunikačních kontextů. Bez původu v sémantice, morfologii, kontaktu či jiné
výslovně modelované inovaci homofonie formu lexému nemění.

Kontexty nepoužívají univerzální slovní druhy. Vycházejí z komunikačních rolí
(`reference`, `event`, `property`, `relation`, `deixis`) a sémantických domén.
Importer má v budoucnu naplnit `semantic.roles` a `semantic.domains` z
Concepticonu; fallback je označen jako heuristický. Concepticon je lokální,
volitelná cache a poskytuje přesně `SEMANTICFIELD` a `ONTOLOGICAL_CATEGORY`;
CLICS4 a DatSemShift s ním sdílejí Concepticonovou identitu konceptu.

## Důsledky

- Neexistují automatické disambiguační prefixy ani jejich morfémové artefakty.
- Vysoká homofonie se objeví v genealogickém auditu jako tlak, nikoli jako
  falešně vyřešená změna.
- Stejný kontrakt lze rozšířit na fonologické spouštěče a samostatné trvání
  inovací místo jediného globálního tempa.

# ADR-010: Postupná sémantická změna

**Status:** Accepted  
**Date:** 2026-08-31  
**Deciders:** CEE project

## Kontext

Původní `SemanticEvaluator` jednou za století náhodně přidal, přepsal nebo
odstranil význam. Výsledek byl reprodukovatelný, ale neuměl vysvětlit, proč
změna vznikla, ani zachytit období konkurence starého a nového užití.

## Rozhodnutí

Nativní simulace nejprve sestaví kandidáty z hran sémantického grafu. Jejich
tlak spočítá z evidence hrany, frekvence lexému a lexikální potřeby. Vybraná
inovace má vlastní historickou událost a šíří se po společné časové ose.

Rozšíření přidá nový význam do polysémie. Úplný posun nejprve vytvoří stejný
polysemní mezistav a až na konci povýší nový význam na hlavní. Stabilní
`lineage_id` drží identitu lexému napříč verzemi a větvemi.

## Zvažované možnosti

### Okamžitá mutace jednou za století

Jednoduchá a zpětně kompatibilní, ale bez kauzálního vysvětlení a mezistavů.

### Pravděpodobnost významu přímo na objektu slova

Vyjadřuje postupnost jemněji, ale směšuje prevalenci mezi mluvčími s lexikální
historií a vyžaduje populační model, který CEE zatím nemá.

### Historická událost s polysemním mezistavem

Zvolená varianta. Odpovídá současnému rozlišení `concept_id` a `polysemy`, je
viditelná na časové ose a později ji lze rozšířit o populační prevalenci.

## Důsledky

- Sémantické změny jsou auditovatelné a dědí se při odštěpení.
- Staré vlastní evaluátory dál fungují přes `evaluate()`.
- `forget_prob` ještě není součástí kauzální cesty; ztráta významu potřebuje
  vlastní tlak a bude doplněna v následujícím řezu.
- UI může později zobrazit začátek, koexistenci a dokončení změny bez změny
  základního event modelu.

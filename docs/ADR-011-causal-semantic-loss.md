# ADR-011: Kauzální ztráta významu

**Status:** Accepted  
**Date:** 2026-08-31  
**Deciders:** CEE project

## Kontext

Původní `forget_prob` náhodně odstranil libovolný význam polysemního slova.
Vzácnost ale sama o sobě neznamená, že význam může bezpečně zaniknout: jazyk
musí mít jiný způsob, jak stejný obsah předat, a oba výrazy si musejí skutečně
konkurovat ve srovnatelných kontextech.

## Rozhodnutí

Kandidát ztráty vzniká pouze pro význam pokrytý alespoň dvěma aktivními
lexémy. Engine určí silnějšího konkurenta podle frekvence a lexémové stability.
Tlak dále násobí překryvem sémantických rolí, domén a registru.

`forget_prob` určuje počet historických příležitostí. Neurčuje, který význam
zmizí. Zvolená ztráta probíhá jako časová událost: význam nejprve ustupuje a
teprve na konci je odstraněn. Polysemní lexém přijde jen o daný význam;
monosemní lexém může zaniknout pouze proto, že koncept zůstává pokrytý vítězem.

## Zvažované možnosti

### Náhodná ztráta libovolného významu

Jednoduchá, ale může odstranit jediný dostupný výraz a nemá vysvětlitelnou
příčinu.

### Ztráta podle samotné frekvence

Lepší než čistá náhoda, ale zaměňuje vzácnost za nahraditelnost a ignoruje
specializované registry.

### Konkurence s dostupnou náhradou

Zvolená varianta. Je konzervativní, auditovatelná a nepoškozuje sémantické
pokrytí lexikonu.

## Důsledky

- Každá ztráta uvádí konkurenční lexém a vypočtený tlak.
- Rituální, formální nebo jinak kontextově oddělená synonyma mohou koexistovat.
- Model zatím používá frekvenci celého lexému, nikoli frekvenci jednotlivých
  významů; tu doplní budoucí model prevalence a kontextového užití.

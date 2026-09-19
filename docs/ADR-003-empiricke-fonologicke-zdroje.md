# ADR-003: Empirické fonologické zdroje jako lokální, verzovaná cache

**Stav:** nahrazeno (2026-08-30)
**Datum:** 2026-08-29

## Kontext

Původní experiment spojil částečný Index Diachronica Redux s PHOIBLE. Ukázalo
se, že Redux není globální vzorek a PHOIBLE obsahuje synchronní inventáře,
nikoli směrované historické změny. Tento ADR zůstává jako historický záznam;
nahrazuje ho auditovatelná globální baseline popsaná v `GLOBAL_BASELINE.md`.

## Rozhodnutí

1. Kalibrace přijímá jen licenčně slučitelná, směrovaná anotovaná pozorování
   s rodinou, verzí, citací a SHA-256 vstupního souboru. Rodiny mají při
   odhadu stejnou váhu.
2. `PHOIBLE` se načte z `data/phoible.csv` do kompaktního modelu inventářů.
   Slouží jako filtr kandidátních stavů (např. znělá okluziva bez neznělé
   protějškové hlásky se odmítne), ne jako tvrzení, že existuje jediný správný
   inventář.
3. Síťovou aktualizaci PHOIBLE provádí výhradně explicitní příkaz
   `cee phonology update-data`. Výsledky patří do `~/.cee/phonology/`:
   zdrojové checkouty, odvozené JSON cache, commit a SHA-256.
4. Běžná simulace výhradně čte existující cache. Je-li cache nepřítomná nebo
   uživatel empirickou vrstvu vypne, spustí se se stávajícími autorskými
   presety. Je-li cache poškozená, běh varuje a bezpečně přejde na fallback.

## Důsledky

- Stejný preset, seed a cache dávají stejný výsledek.
- Výsledky lze dohledat k obsahu, licenci, verzi a citaci každého zdroje.
- Baseline nezaměňuje kognátní podobnost za směrovanou změnu a nepoužije
  nekomerčně kompatibilní data pro distribuované váhy.

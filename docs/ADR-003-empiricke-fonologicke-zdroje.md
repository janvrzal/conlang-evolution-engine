# ADR-003: Empirické fonologické zdroje jako lokální, verzovaná cache

**Stav:** přijato
**Datum:** 2026-08-29

## Kontext

Etapa 3 potřebuje používat doložené diachronní změny z Index Diachronica a
typologické inventáře z PHOIBLE. Simulace ale musí zůstat deterministická,
funkční offline a nesmí stahovat ani verzovat velké externí datasety v tomto
repozitáři.

## Rozhodnutí

1. `Index Diachronica Redux` se načte z `data/changes/*.txt` a zredukuje na
   auditovatelné počty podporovaných schémat. Ty násobí autorovy váhy presetu;
   nevybírají pravidla přímo ani neschovávají uživatelovu konfiguraci.
2. `PHOIBLE` se načte z `data/phoible.csv` do kompaktního modelu inventářů.
   Slouží jako filtr kandidátních stavů (např. znělá okluziva bez neznělé
   protějškové hlásky se odmítne), ne jako tvrzení, že existuje jediný správný
   inventář.
3. Síťovou aktualizaci provádí výhradně explicitní příkaz
   `cee phonology update-data`. Výsledky patří do `~/.cee/phonology/`:
   zdrojové checkouty, odvozené JSON cache, commit a SHA-256.
4. Běžná simulace výhradně čte existující cache. Je-li cache nepřítomná nebo
   uživatel empirickou vrstvu vypne, spustí se se stávajícími autorskými
   presety. Je-li cache poškozená, běh varuje a bezpečně přejde na fallback.

## Důsledky

- Stejný preset, seed a cache dávají stejný výsledek.
- Výsledky lze dohledat ke konkrétním commitům i k obsahu zdrojů.
- Priory jsou záměrně hrubé mapování na současný registry schémat; jemné
  jazykové/familiární podmínění a plné Index Diachronica parsování zůstávají
  budoucí kalibrační prací, ne předstíranou přesností.

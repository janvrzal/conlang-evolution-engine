# ADR-006: Kalibrační profily a ovladače worldbuildera

**Status:** Accepted  
**Date:** 2026-08-31

## Rozhodnutí

Profil rodiny kombinuje tři vrstvy: násobky schémat, makrotempo a lexikální
ekologii. Vestavěné profily jsou záměrně heuristické, nikoli tvrzení o jedné
správné zemské historii.

Přímé ovladače projektu přebíjejí makro a lexikální prior profilu; konfigurace
konkrétní větve přebíjí obojí. V pořadí tedy platí:

    vestavěný preset -> rodinný profil -> ovladače projektu -> uzel větve

Kontaktová hrana ovlivňuje tempo inovací saturovanou intenzitou podle objemu a
prestiže. Izolace jej mírně tlumí; žádná z těchto proměnných však jazyk
nezastaví.

## Důsledky

- Worldbuilder nastavuje tempo, dobu šíření a izolovanost, ne desítky vah.
- Profily Konzervativní rodina, Earth-like neutrální a Dynamická rodina jsou
  reprodukovatelné výchozí body.
- Empirický profil z externích dat zůstává samostatný, auditovatelný import;
  vestavěné heuristiky se za empirická data nevydávají.

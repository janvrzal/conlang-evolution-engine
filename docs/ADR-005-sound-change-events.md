# ADR-005: Zvukové změny jako časově rozprostřené události

**Status:** Accepted  
**Date:** 2026-08-30

## Kontext

Generátor dříve vybíral příležitost ke změně každých 25 let a pravidlo v
jednom okamžiku aplikoval na celý slovník. Za 1 500 let tak běžně vznikalo
přibližně 50 plošných pravidel. Výsledek uměle zvyšoval počet mergerů a
homofonii, a současně neumožňoval modelovat šíření inovace napříč komunitou.

## Rozhodnutí

Generované pravidlo nyní vzniká jako událost s počátkem, délkou šíření a
intenzitou. V průběhu 40letých auditních fází se deterministicky rozšiřuje na
kumulativní podmnožiny lexikonu. Ručně zadané pravidlo zůstává okamžité, aby
se neměnil význam existujících scénářů.

Výchozí tempo je 8 velkých inovací za tisíc let před korekcemi. Parametry
rodinného či uzlového makra jsou:

- sound_changes_per_millennium — tempo inovací;
- change_spread_years — délka šíření;
- isolation — 0 až 1, mírně tlumí vznik nových inovací.

change_rate, konzervativnost a sociální mobilita zůstávají dalšími
modifikátory tohoto tempa.

## Důsledky

- Auditní graf nese change_id, začátek, konec, délku, fázi a počet zásahů.
- Dlouhá simulace má řádově jednotky až desítky velkých inovací, ne desítky
  pravidel za tisíciletí.
- Výsledek je stále deterministický pro stejný seed a konfiguraci.
- Nejde o model jednotlivých mluvčích ani o empiricky kalibrovaný model
  difuze; ten bude další vrstva nad tímto rozhraním.

# CEE engine v2 — návrh

Nový simulační engine vzniká od nuly. Současné jádro (`src/cee/engine/`)
zůstává jako legacy, dokud ho v2 nepřekoná v metrikách realističnosti.

Návrh se zpřesňuje v pěti iteracích. Každá navazuje na předchozí a smí ji
přepsat; platí vždy poslední verze.

| # | Iterace | Otázka, na kterou odpovídá | Stav |
|---|---|---|---|
| 1 | [Jádro](01-jadro.md) | Jaká je hlavní smyčka a z jakých stavebních kamenů se skládá? | hotovo |
| 2 | [Reprezentace jazyka](02-reprezentace.md) | Jak vypadá hláska, slovo, morfém a konstrukce a jak na ně změna dosáhne? | hotovo |
| 3 | [Katalog změn a tlaků](03-katalog.md) | Které podtřídy `Změna` a které `Tlak` existují a jak se navzájem ovlivňují? | hotovo |
| 4 | [Společnost a prostor](04-spolecnost-prostor.md) | Generace, sítě, kontakt a učení dospělých, instituce, migrace, vznik jazyků. | hotovo |
| 5 | [Specifikace](05-specifikace.md) | Datové struktury, výkonový rozpočet, determinismus, metriky a validační scénáře. | hotovo |

## Výchozí principy

- Jazyk není homogenní. Základní jednotkou je **komunita na místě**; dialekty
  a jazyky jsou emergentní shluky komunit, nikoli vstup.
- Každá změna je **variace + selekce + šíření**. Nic se neaplikuje plošně
  naráz; i „pravidelná“ zvuková změna je jen velmi rychle se šířící varianta.
- Mechanismy změny mají **jednoho rodiče** (`Změna`). Tlaky se ke změnám
  **skládají** jako komponenty, nedědí se. Šíření je **jedno, společné**.
- Standardizace je pozdní a silný institucionální tlak, ne výchozí stav.
- Determinismus: stejný svět + stejný seed = stejná historie.

## Revize mezi iteracemi

Pozdější iterace upravují dřívější. Platí:

- **Komunita → skupina mluvčích** (iterace 4). Skupina může mít víc kódů
  (variet), každý s vlastním repertoárem.
- **Výpůjčka** (iterace 3) už není hlavní cestou kontaktu. Kontakt nese
  hlavně `Šíření` přes hranici kódu s filtrem přenositelnosti.
- **Proměnná** má čtyři typy: procesní, lexikální, formová, konstrukční
  (iterace 2).
- **Víceúrovňový svět** (iterace 4): strom území od světa po sídlo,
  nerozepsaná území jsou souhrnné skupiny, autor se přibližuje (drill-down).
  UI nabízí režimy údolí, region, země, kontinent, svět.
- **Délka generace je vlastnost skupiny** (iterace 4), výchozí 25 let.
  Krok simulace obnoví podíl `Δt / G` populace.
- **Závazná pro kód je [specifikace](05-specifikace.md)**; iterace 1–4
  vysvětlují důvody.

## Přijatá rozhodnutí

| Otázka | Rozhodnutí |
|---|---|
| Velikost světa v UI | pět režimů od údolí po svět, stejný model, náčrt shora a přiblížení |
| Délka generace | nastavitelná pro každou skupinu, výchozí 25 let |
| Katalog zvukových změn | autorský prior + korekce z IE-CoR a ACD (CC BY 4.0); audit v [`DIRECTIONAL_SOURCES.md`](../DIRECTIONAL_SOURCES.md) |
| Latinská data pro S5 | 170 pojmů z IE-CoR + 30–40 ručně kurátorovaných morfémů |

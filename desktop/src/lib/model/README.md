# model

Data pro obrazovky: typy exportu enginu (`export.ts`), mapa světa pro `<WorldMap>` (`geography.ts`)
a jazyky výsledku (`languages.ts`: rodina, barva, jméno, jazyk doma ve vsi, mluvčí).

Obrazovka, která potřebuje vlastní výpočet, si ho dá do `model/<obrazovka>.ts` (např. `model/slova.ts`),
aby se agenti nepotkali ve stejném souboru. Sdílené soubory tady mění jen správce ds.

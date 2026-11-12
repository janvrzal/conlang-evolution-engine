# Design systém CEE (`$lib/ds`)

Zdroj vzhledu: plátno „CEE Talvera · obrazovky“ (Design canvas `Gxj1bv7Wb29iWytp5jSLUt`),
UX audit `docs/ui-navrh/UX_AUDIT.md`, změny `docs/ui-navrh/ZMENY_TALVERA.md`.

## Pravidla (hlídá `sentinel.test.ts`, spouští `npm test` i `npm run check:ds`)

Mimo `src/lib/ds/` se nesmí:

- importovat `.svelte` komponenty odjinud než z indexu `$lib/ds` (ani `$lib/ds/X.svelte`);
- psát `<button>`, `<input>`, `<select>`, `<textarea>`, `<canvas>`, `<svg>`, `<table>`, `<dialog>`, `<progress>`, `<meter>`;
- psát `<style>`, atribut `style=` / `style:x=`, direktivu `class:x` ani `{@html}`.

Obrazovka skládá komponenty z `$lib/ds` a strukturní HTML (`div`, `section`, `p`, `span`, `a`, `b`, `i`, `ul`, `li`, `h1`–`h3`).
Výjimky jsou jen v `allowlist.json` (soubor, pravidlo, důvod) a přidává je správce ds. Chybí-li komponenta,
obrazovka ji nepíše sama: řekne správci ds, co potřebuje.

## Komponenty

| Skupina | Komponenty |
|---|---|
| Kostra | `Shell`, `AppBar`, `Screen` (sloupce/řádky: číslo = px, `'fill'`), `Area`, `Card`, `Stack`, `Cluster`, `Spacer`, `Stage` (rohy `tl tr bl br`), `Floating`, `Footer` |
| Text | `Text` (`h1 h2 h3 body caps why small big strong`, `tone`, `num`), `Ipa`, `Term`, `Kbd`, `Swatch`, `Icon` |
| Ovládání | `Button` (`primary`, `quiet`, `href`, `icon`, `disabled` = aria-disabled), `Segmented`, `Tabs`, `Field`, `TextInput`, `Checkbox`, `Range`, `Select`, `FilePicker`, `Chip` |
| Data | `Ledger` + `LedgerRow`, `Bars`, `Table` + `Tr` + `Td`, `List` + `ListItem`, `Legend`, `Strata` (vrt), `MiniBars` |
| Hlášení | `IssueList`, `CheckBadge`, `Banner`, `Toast`, `Popover`, `Working` (čekání na běh) |
| Čas a mapy | `TimeAxis`, `EventLanes` (kronika zadání), `WorldMap` (kartografie), `LanguageRiver` (řeka jazyků) |
| Funkce | `languagePalette`, `familyColor`, `shadeOf`, `cssVar`, `formatYear` (−700) |

`WorldMap` dostane kraje a vsi (`model/geography.ts`) a obrazovka jí dodá jen funkce: `fill` (barva vsi),
`regionFill`, `hatch`, `regionHatch`, `edge` (styl hrany mezi sousedními vesmi: hranice kraje, státu, izoglosa,
rozdíl), `highlight`, `selected`, `labels` (bez překryvů), `markers` (města), `arrows`, `focus` (přiblížení).
Šipky a Enter mezi kraji umí sama.

## Pohyb

Pohyb je jen uvnitř ds (obrazovky styly psát nesmí). Tokeny `--e-*` a `--t-*` jsou v `tokens.css`, stejné hodnoty
a přechody pro Svelte (`unfold`, `narrow`, `sprout`, `rise`, akce `underline`) v `motion.ts`. Řeka jazyků roste po ose
času, mapa šíří změnu barvy vlnou od sousedních vsí, kronika nechá událost vyrašit, když přes ni přejde ukazatel,
přepínač a karty mají posuvnou značku, zaškrtnutí se dokreslí, `Disclosure`, `Banner` a `LedgerRow` se rozvinou
a zúží, `Popover` se rozevře od kotvy, `Toast` se odkryje zleva. `Working` je čekání na dosimulování.
Při `prefers-reduced-motion` je vše hned v konečném stavu.

## Barvy a text

Papír a inkoust; **červená jen pro změnu** (izoglosa, rozdíl větví, zastaralé, chyba, ruka autora).
Výběr a aktivní položka jsou inkoustem. Jazyky: odstín = rodina (protojazyk), světlost = jazyk (`lineagePalette`).
Každý text jde přes `t()`; texty obrazovky jsou v `src/lib/messages/screens/<obrazovka>.ts` (česky i anglicky, stejné klíče).
Roky vždy `formatYear` (typografický minus).

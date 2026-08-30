# ADR-002: Společná chronologická fronta pro diachronní vrstvy

**Status:** Accepted
**Date:** 2026-08-29

## Context

Dosavadní simulátor řadil štěpení, zvukové změny a kontakt v čase, ale
morfologii a část lexikální historie vyhodnocoval až po konci běhu. To
znemožňovalo, aby nově vzniklé slovo procházelo dalšími změnami, aby se
analogie opírala o skutečné nepravidelnosti nebo aby kontakt volil slova podle
tehdejší sociální situace.

## Decision

Rozšiřujeme jedinou stabilně seřazenou frontu událostí. Vedle existujících
událostí obsahuje prosodické opravy, lexikální obměnu, morfologii a kontakt.
Každý stav jazyka nese malé, serializovatelné diachronní metriky:

- slovo: frekvenci, aktivnost, morfémové hranice, přízvuk a délku;
- jazyk: sociální profil (populace, mobilita, prestiž, gramotnost a standard);
- kontakt: doménu, směr, asymetrii/prestiž a intenzitu.

Všechny náhodné volby se odvozují z globálního seedu, uzlu, roku a typu
události. Stejný vstup proto nadále vytváří stejný výsledek.

Zvukové změny se nepředpočítávají při vzniku větve. Fronta obsahuje pouze
časové sloty a konkrétní pravidlo se vybírá až v daném roce z tehdejšího
aktivního lexikonu a inventáře. Výpůjčka, novotvar nebo sociální změna tak může
ovlivnit i pozdější fonologii. Ručně zadané změny se přidávají do téže historie,
aby generátor u potomků nenavrhoval jejich bezprostřední reverzi.

## Consequences

- Slova vytvořená morfologií nebo přejatá kontaktem projdou pozdější fonologií.
- Zaniklé lexémy neovlivňují živý inventář ani další výběr pravidel.
- Náhodnost jedné větve je lokální; přidání nesouvisející větve nezmění její
  sémantickou ani lexikální historii.
- Základní slovní zásoba je stabilnější než okrajová, ale stav modelu zůstává
  malý a exportovatelný.
- Neimplementujeme plnohodnotný sociolingvistický agentový model; sociální
  proměnné jsou vysvětlitelné parametry vah a pravděpodobností.
- Staré YAML a UI payloady zůstávají platné díky výchozím hodnotám.

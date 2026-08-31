# ADR-008: Kauzální šíření zvukové inovace

**Status:** Accepted

## Kontext

CEE už rozepisoval změnu do fází, ale slova vybíral pouze kumulativním
náhodným prahem. Inventář navíc potvrzoval přítomnost hlásek, nikoli skutečné
slovní prostředí pravidla.

## Rozhodnutí

Při vzniku změny `ChangeDecisionEngine` změří počet skutečně zasažených slov,
typovou a frekvenční pokrytost. Z nich vznikne tlak, který upraví délku šíření
a zapíše se do historie události. Každý způsobilý lexém má stabilní okamžik
adopce: častější slova přijímají inovaci dříve, zásah na morfémové hranici ji
zpomaluje. Závěrečná fáze pravidlo aplikuje na všechny zbývající způsobilé
lexémy.

## Důsledky

- Zvuková změna není skok přes celý lexikon.
- Každá změna nese vysvětlitelnou oporu v konkrétním slovníku.
- Zatím jde o první model lexikální difuze; sociální skupiny, frekvenční
  nepravidelnosti a konkurence inovací zůstávají následnou etapou.

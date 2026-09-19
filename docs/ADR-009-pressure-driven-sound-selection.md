# ADR-009: Výběr zvukové inovace podle tlaku lexikonu

- **Stav:** přijaté
- **Datum:** 2026-08-31

## Kontext

Původní generátor losoval schéma zvukové změny především z vah presetu. Až
následně kontroloval, zda pravidlo zasáhne alespoň jedno slovo. To mohlo
preferovat typologicky časté schéma, i když v daném jazyce nemělo téměř žádnou
lexikální oporu.

## Rozhodnutí

V každém fonologickém slotu simulátor vytvoří jeden platný kandidát pro každé
zapnuté schéma. Kandidát dostane tlak jako geometrický průměr:

`sqrt(podíl zasažených slov × podíl jejich frekvence)`.

Vybere se kandidát s nejsilnějším tlakem. Jen pokud se kandidáti liší nejvýše
o dva procentní body, rozhodnou mezi nimi váhy presetu, biome a kalibrace.
Tyto váhy jsou tedy typologický prior pro nerozhodné případy, nikoli samostatná
příčina změny.

## Důsledky

- Výběr je auditovatelný: událost nese tlak, počet zasažených slov a frekvenční
  pokrytí.
- Worldbuilder stále ovládá povolená schémata a chování při nerozhodných
  případech.
- Model zatím měří pouze bezprostřední fonologickou oporu. Artikulace,
  funkční zatížení kontrastů, sociální prestiž a areálové šíření budou další
  samostatné zdroje tlaku, nikoli skryté náhodné korekce.

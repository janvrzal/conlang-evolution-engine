# ADR-013: Abstraktní politický prostor a časované historické události

**Stav:** částečně implementováno · 2026-09-01

## Kontext

CEE pracuje s uzly jazyků a jejich dědičnými či kontaktními vztahy. To je
správná míra abstrakce pro návrh jazykových rodin: pixelová mapa by nutila
worldbuildera kreslit každé území a simulátor by předstíral přesnost, kterou
vstupní data nemají. Přesto chybí společná vrstva pro státy, obchodní cesty a
události, jež vysvětlují, *proč* se některé jazyky více stýkají,
standardizují nebo štěpí.

## Rozhodnutí

První verze zavede **časované abstraktní objekty**, nikoli geografický raster:

- **State** je politická jednotka s identitou, názvem, institucemi, členy
  (jazykové uzly) a volitelnými mapovými metadaty. Členství nezruší genealogii
  ani nevytvoří automaticky jednotný jazyk.
- **TradeRoute** je ručně zakreslený vztah mezi dvěma body/uzly s typem
  `land`, `river` nebo `sea`, intenzitou a obdobím platnosti. Teprve aktivní
  trasa vytváří kandidáta kontaktu; sama nekopíruje žádná slova.
- **HistoricalEvent** je časový interval s typem (migrace, válka, kolaps,
  urbanizace, standardizace, reforma, obchodní rozkvět), cílem a malou sadou
  účinků. Účinek mění jen explicitní parametry (mobilita, prestiž,
  standardizace, izolace, kontaktní intenzita, registrální/institucionální
  tlak) a zapisuje se do existující chronologické fronty.
- **LanguageName** uchovává endonymum, exonymum, rok platnosti a zdroj změny.
  Názvy se mění pouze autorskou událostí nebo explicitně povolenou politikou
  pojmenování; model je nikdy nesmí samovolně přepsat.

Všechny objekty budou uloženy v datech projektu a při simulaci přeloženy do
současných uzlových konfigurací a kontaktových událostí. Výchozí projekty a
staré snapshoty zůstávají beze změny platné.

## Zvažované varianty

### A. Pixelová mapa a automatická územní simulace

| Rozměr | Hodnocení |
| --- | --- |
| Složitost | vysoká |
| UX | náročné na ruční kresbu |
| Vysvětlitelnost | zdánlivě přesná, ale vstupně slabá |

Přináší přirozenější difuzi, ale vyžaduje hranice, hustotu i pohyb populace,
které většina projektů nemá. Pro první produktovou cestu ji odmítáme.

### B. Abstraktní časované objekty nad uzlovou mapou

| Rozměr | Hodnocení |
| --- | --- |
| Složitost | střední |
| UX | odpovídá současné mapě |
| Vysvětlitelnost | vysoká |

Zachová dosavadní mapový editor, ale každé historické působení má autora,
trvání a audit. Toto přijímáme.

### C. Jen ruční kontaktní hrany bez států a událostí

Jednoduché, ale nevysvětluje asymetrii, obchod, standardizaci ani společný
politický tlak. Zůstane kompatibilním nízkoúrovňovým nástrojem, ne hlavním
modelem.

## Důsledky

- Worldbuilder může oddělit politickou příslušnost, kontaktní síť a původ
  jazyka.
- Simulace dostane kauzální vstupy bez předstírání detailní geografie.
- Převod dialektu na jazyk zůstane výslovně autorským krokem; formulář pouze
  nabídne variantu jako výchozí zdroj.
- Před pixelovou difuzí bude potřeba později doplnit geometrii a prostorový
  model jako samostatný, volitelný adaptér.

## Pořadí implementace

1. [~] Projektová data jsou zpětně kompatibilní volné záznamy; chybí typované
   schéma a migrace pro `polities`, `tradeRoutes`, `historicalEvents` a názvy.
2. [x] Správce států, tras a událostí je v levém globálním panelu; detail
   jazyka je samostatná stránka.
3. [~] Trasy mají typ, intenzitu a časovou platnost, ale ne ručně kreslenou
   geometrii ani validaci waypointů na mapě.
4. [x] Aktivní objekty se překládají do chronologické fronty simulátoru a mají
   auditní regresní testy.
5. [~] Odštěpení z variety ukládá původ, rok a komunitu; jazyk drží endonymum,
   exonymum a kurátorovaná jména. Chybí časované přejmenování navázané na
   konkrétní politickou událost.

# Stav evolučního enginu

Legenda: **funguje** = implementováno a regresně testováno; **základ** =
použitelné, ale bez plné kauzální či sociální vrstvy; **plán** = další řez.

| Vrstva | Co dnes umí | Stav | Nejbližší chybějící část |
|---|---|---|---|
| Zvuk | Výběr změn podle tlaku v lexikonu, postupné šíření, dědění do větví, audit událostí | základ | artikulační a kontrastní tlaky; audit všech schémat |
| Prosodie a fonotaktika | Přízvuk, délka, morfémové hranice, slabiky a základní opravy struktur | základ | úplný model shluků, otevřených/zavřených slabik a jejich historické motivace |
| Význam | Kolexifikace, obecný posun, polysémie, zúžení, ztráta s náhradou a konkurence synonym | funguje | prevalence významů mezi mluvčími |
| Typy významové změny | Metafora (mezidoménově), metonymie (strukturální most), generalizace/specializace (směr rozsahu) z kurátorované hrany nebo autorova přepisu | funguje | širší kurátorovaný soubor mechanismů a ovládání v UI |
| Morfologie | Složeniny, derivace, paradigmata, analogie, gramatikalizace a reanalýza | základ | kauzální tlak, eroze afixů a postupné šíření nepravidelností |
| Lexikon | Frekvence, náhrady, tabuový směr, homofonie, složeniny a lexikální zánik | základ | vznik nových kořenů a model doménové stability |
| Kontakt | Výpůjčky, adaptace, prestiž, doména a kalky | základ | dlouhodobá asymetrie, morfologické výpůjčky a areálové šíření |
| Společnost a prostor | Izolace, mobilita, standardizace, gramotnost a intenzita kontaktu | základ | populace, skupiny mluvčích, dialekty a izoglosy |
| Worldbuilder | Presety a konfigurační parametry | základ | UI pro návrhy, schvalování, mechanismy a rodinné profily |
| Validace | Regresní testy, distribuční metriky a audit eventů | základ | E2E UI → API → export a metriky sémantiky, morfologie a kontaktu |

Podrobný stav významové vrstvy je v
[SEMANTIC_EVOLUTION_TRACKER.md](SEMANTIC_EVOLUTION_TRACKER.md).

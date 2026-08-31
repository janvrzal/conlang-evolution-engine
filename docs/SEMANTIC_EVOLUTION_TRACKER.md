# Tracker sémantického vývoje

Tento tracker sleduje přechod od náhodných stoletých mutací významu ke
kauzálním, časově rozloženým a auditovatelným změnám. Stav **hotovo** znamená,
že funkce má implementaci i automatický test.

## Hotovo

- [x] Oddělit návrh změny od její aplikace.
- [x] Vyžadovat pro rozšíření či posun hranu v CLICS4/DatSemShift grafu.
- [x] Skórovat kandidáty podle lokální váhy evidence, frekvence lexému a
  lexikální potřeby cílového konceptu.
- [x] Použít `shift_prob` jako tempo historických příležitostí, nikoli jako
  náhodný výběr cílového významu.
- [x] Modelovat období koexistence starého a nového významu.
- [x] U úplného posunu povýšit nový význam až na konci změny.
- [x] Verzionovat mezistav i dokončený stav v genealogii.
- [x] Zapisovat tlak, evidenci, délku a průběh změny do event logu.
- [x] Udržet aktivní změnu přes mezilehlé verze lexému a odštěpení větve.
- [x] Zachovat kompatibilitu jednoduchých vlastních evaluátorů používajících
  původní metodu `evaluate()`.
- [x] Kauzální zúžení a zánik významu pouze při dostupnosti živého konkurenta.
- [x] Skórovat konkurenci synonym podle frekvence, stability a kontextového
  překryvu.
- [x] Tlumit konkurenci synonym používaných v odlišných registrech či rolích.
- [x] U polysemního lexému odstranit jen vytlačený význam; poslední užití smí
  zaniknout pouze tehdy, když je koncept dál pokrytý silnějším lexémem.
- [x] Zapojit `forget_prob` jako tempo příležitostí pro kauzální ztrátu.
- [x] Rozlišit metaforu, metonymii, generalizaci a specializaci jen z
  kurátorovaného metadata nebo přesného autorského přepisu.
- [x] Zapsat mechanismus do auditní události a zachovat neoznačené hrany jako
  obecný posun či kolexifikaci.
- [x] Vyžadovat vlastní tlak mechanismu: mezidoménový most pro metaforu,
  strukturální vztah pro metonymii a explicitní rozsah pro generalizaci či
  specializaci.
- [x] Přidat komunikační tlaky biomu, ekonomiky, technologie a institucí jako
  transparentní zvýhodnění už doloženého cílového významu.
- [x] Modelovat malé životní cykly registru: institucionální formalizaci,
  explicitně nastavené šíření rituálního výrazu a tabuovou náhradu označenou
  jako opis.
- [x] Zapsat kontextový tlak i registrální přechody do event logu.

## Následuje

- [ ] Jemnější tlak prestiže a komunikační potřeby podle řečových komunit.
- [ ] Sémantické změny vyvolané kontaktem, kalky a přejímáním konstrukcí.
- [ ] Šíření podle sociálních skupin a regionů, nejen po jedné jazykové větvi.
- [ ] Ruční schválení či odmítnutí navržené inovace worldbuilderem.
- [ ] Presety intenzity sémantických změn a jejich ovládání v UI.
- [ ] Kalibrační metriky: polysémie, retence významů, velikost sémantických
  skoků a rozdíly mezi větvemi.
- [ ] E2E test UI → API → simulace → časový detail významu → export.

## Aktuální omezení

První verze vybírá nejvýše jednu novou sémantickou inovaci na jazyk a století.
Binární `concept_id`/`polysemy` zatím neumějí vyjádřit procento mluvčích, kteří
nové užití přijali; postupnost je proto zachycena historickými fázemi a
mezistavem polysémie. Populační rozšíření bude vyžadovat explicitní model
variant či řečových komunit.

Stabilita je zatím lexémová hodnota z metadat (`semantic.stability` nebo
`lexical.stability`), nikoli samostatný empiricky kalibrovaný parametr každého
významu. Pokud hlavní význam polysemního slova zanikne, převezme jeho místo
deterministicky první zbývající význam; prominence jednotlivých významů bude
potřebovat vlastní model užití.

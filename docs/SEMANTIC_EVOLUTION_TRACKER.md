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

## Následuje

- [ ] Kauzální zúžení a zánik významu; současný `forget_prob` zůstává pouze
  v kompatibilním okamžitém evaluátoru, dokud nebude existovat tlak pro ztrátu.
- [ ] Konkurence synonym podle frekvence, kontextového překryvu a stability.
- [ ] Samostatné mechanismy metafory, metonymie, generalizace a specializace.
- [ ] Tlak tabu, registru, prestiže a komunikační potřeby.
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

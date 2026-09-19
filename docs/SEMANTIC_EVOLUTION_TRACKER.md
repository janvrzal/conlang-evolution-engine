# Tracker sémantického vývoje

> Detailní tracker pro sekci 2 hlavní [evoluční roadmapy](EVOLUTION_ROADMAP.md).
> Hlavní roadmapa je zdrojem priorit; tento soubor drží přesné omezení
> sémantického runtime.

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

## Zbývá

- [~] Šíření podle sociálních skupin a regionů: každá sémantická inovace má
  volitelné ohnisko komunity, uchovává podíl přijetí po komunitách a síť
  vazeb/bilingvismu určuje difuzi. Chybí samostatný lexikon a konkurence
  významových variant pro každou komunitu.
- [~] Jemnější tlak prestiže a komunikační potřeby podle řečových komunit.
  Prestiž, mobilita, městskost a domény nyní určují ohnisko a receptivitu;
  chybí kalibrace proti doloženému sociolingvistickému korpusu.
- [x] Sémantické změny vyvolané kontaktem: kalkový nebo obchodní kontakt
  přenese živou, rozběhnutou variantu jako vlastní časovanou změnu v cíli;
  audit uchová zdroj, sílu kontaktu i obě identity změny.
- [x] Ruční schválení navržené inovace worldbuilderem: režim „ke schválení“
  uloží návrh do auditu, autor jej v detailu jazyka schválí pro další běh a
  může jej ponechat nevyřízený. Zamítnutí je zatím konzervativní: návrh se
  jednoduše neschválí a nemění historii.
- [x] Presety intenzity sémantických změn a jejich ovládání v UI: konzervativní,
  vyvážený a dynamický profil řídí interval sémantických příležitostí.
- [ ] Kalibrační metriky: polysémie, retence významů, velikost sémantických
  skoků a rozdíly mezi větvemi.
- [x] E2E test UI payload → API → simulace → časový detail významu → export,
  včetně kontaktního přenosu živé sémantické varianty.

## Aktuální omezení

První verze vybírá nejvýše jednu novou sémantickou inovaci na jazyk a století.
Podíl přijetí už drží lehká síť komunit, ale `concept_id`/`polysemy` stále patří
celému jazyku: model neumí samostatné konkurenční lexikony komunit. Plošná
lexikální změna je proto jen hrubý agregát difuze, nikoli individuální simulace
mluvčích.

Stabilita je lexémová hodnota z metadat (`semantic.stability` nebo
`lexical.stability`). Lokální cache CEE ji standardně vyplní z otevřeného
Concepticonového prioru sestaveného ze seznamů Swadesh 1955 a Peust 2013;
nepokryté koncepty zůstávají na heuristice. Tento prior není nezávisle
kalibrovaným univerzálním měřením retence. Pokud hlavní význam polysemního
slova zanikne, převezme jeho místo deterministicky první zbývající význam;
prominence jednotlivých významů bude potřebovat vlastní model užití.

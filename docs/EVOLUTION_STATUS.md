# Stav evolučního enginu

Toto je stručný, produktový pohled. Úplné odškrtávací položky a jejich limity
jsou v [EVOLUTION_ROADMAP.md](EVOLUTION_ROADMAP.md); detail významové vrstvy
v [SEMANTIC_EVOLUTION_TRACKER.md](SEMANTIC_EVOLUTION_TRACKER.md).

Legenda: **funguje** = běžný mechanismus má audit a regresní test; **základ**
= použitelný model s vědomě omezeným rozlišením; **plán** = dosud chybějící
samostatná vrstva.

| Vrstva | Co dnes umí | Stav | Nejbližší skutečný limit |
|---|---|---|---|
| Zvuk | Řetězové posuny, tonogeneze/tónové sandhi, vokálová harmonie, postupné šíření, funkční zátěž a naučená fonotaktická oprava | funguje | Neexistuje artikulační simulace ani plně naučená pravděpodobnostní gramatika. |
| Prosodie a fonotaktika | Přízvuk, délka, morfémové hranice, slabiky, sonorita a oprava neplatných struktur | základ | Výjimky a produktivní vážená gramatika fonotaktiky. |
| Význam | Doložené posuny, polysémie, ztráta s náhradou, registry, sémantické tlaky, schvalování návrhů a difuze komunitami i kalkovým/obchodním kontaktem | základ | Komunity ještě nemají vlastní konkurenční lexikony a přenášejí se pouze živé, rozběhnuté varianty. |
| Morfologie | Složeniny z receptů, derivace, paradigmata, gramatikalizace, produktivita, eroze afixů a analogie | funguje | Automatická reakce na homofonii se omezuje na receptovou složeninu, produktivní afix nebo výslovný kontakt. |
| Lexikon | Frekvence, motivované nové kořeny, synonymní soutěž, tabu, homofonie, auditní fronta a retenční prior | základ | Prior Swadesh 1955 + Peust 2013 má 229 Concepticonových konceptů; chybí širší nezávisle kalibrovaná evidence. |
| Kontakt | Doménový výběr, nativizace, vrstvy kontaktu, kalky, přenos afixů/konstrukcí, nové fonémy, sémantické varianty a cílené řešení homofonie | funguje | Dlouhodobé areálové šíření hotových inovací. |
| Společnost a prostor | Populace, komunity, variety, kohorty, bilingvismus, státy, trasy, migrace a časované politické události | základ | Historické účinky jsou zatím konstantní vrstvy bez modelu trvalých následků. |
| Worldbuilder | Mapa, podklad, trasy, detail jazyka, časový řez, katalog, filtry lexikonu a autorská rozhodnutí | funguje | Typovaná projektová data, migrace formátu a E2E regrese. |
| Validace a provoz | Regrese enginu, audit událostí, globální outcome metriky, export a lokální souborové úložiště | základ | E2E UI → API → export, benchmark 2 000+ lexémů, backend lint/typing/coverage a rozhodnutí o Neo4j adaptéru. |

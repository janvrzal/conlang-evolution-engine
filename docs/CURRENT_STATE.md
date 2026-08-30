# CEE: ověřený stav implementace

Aktualizováno: 2026-08-30. Tento dokument je provozní doplněk k whitepaperu
`CEE_master.md`: whitepaper popisuje směr a výzkumné hypotézy, kdežto zde je
výhradně to, co je v repozitáři implementované a kryté testy.

## Funguje dnes

- Lokální projekt, metaeditor protojazyka, mapa časových snímků a simulace
  rodiny v absolutním časovém lockstepu.
- Vertikální dědičnost v okamžiku štěpení, datovaný obousměrný i jednosměrný
  kontakt, lexikální původ a načítání stavu jazyka pro konkrétní rok.
- Zvukové změny nad PanPhon rysy, prosodie, přízvuk, délka, morfémové hranice,
  lexikální a morfologické události. Historicky pojmenovaná schémata mají
  derivační kontrakty v `tests/test_diachronic_schema_contracts.py`.
- CLICS4 + DatSemShift se načítají z lokální cache s fallbackem na malý
  zabalený graf. CLICS slouží kolexifikaci a DatSemShift směrovaným posunům.
- Index Diachronica Redux a PHOIBLE se aktualizují explicitně příkazem
  `cee phonology update-data`; simulace je potom používá offline. Cache ukládá
  commit a SHA-256 zdrojů.
- Výsledky se ukládají ve výchozím nastavení do souborového genealogického
  úložiště. Neo4j je volitelný adaptér. JSON export obsahuje slova, původové
  hrany, události a prosodická data.
- Frontend podporuje češtinu/angličtinu, interakci s mapou, typ dědičnost nebo
  kontakt, izoglosu a export uložené simulace.

## Částečně implementováno

- Priory z Index Diachronica jsou zatím konzervativní mapování doložených
  změn na registry schémat; nejsou plnou statistikou rodin, prostředí a epoch.
- PHOIBLE je sanity filtr inventáře, nikoli úplný generativní model
  typologické pravděpodobnosti.
- Sociální, lexikální a morfologická historie je agregovaný model, ne
  agentová simulace mluvčích či izoglos.
- Projektový dokument UI je kompatibilní s dřívějšími tvary dat, ale zatím
  nemá explicitní verzované schéma a řetězec migrací.

## Záměrně neimplementováno / budoucí práce

- Kalibrační brány V2a/V2b, benchmark syntetických rodin proti reálným
  rodinám a vědecké vyhodnocení přes LingPy/fylogenetické nástroje.
- Content-addressed hash stavu, paralelní rerolly/freeze a cache podle tohoto
  hashe. Současné deterministické identifikátory slov nejsou náhradou této
  funkce.
- CLDF, Lexurgy, PDF, Anki a jiné produktové exporty; dnes je podporovaný
  Markdown/CSV v CLI a auditovatelný JSON export běhu.
- Plnohodnotná biomová maska, diglosie a detailní sociofonetické šíření.

## Zdroj pravdy pro dokumentaci

- `README.md`: instalace a běžný uživatelský tok.
- `AGENT.md`: závazné technické konvence pro vývoj.
- `CEE_master.md`: vize, výzkumné hypotézy a cílová architektura.
- Tento dokument: implementovaný rozsah a známé hranice.

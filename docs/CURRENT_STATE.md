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
- PHOIBLE se aktualizuje explicitně příkazem `cee phonology update-data` nebo
  tlačítkem v mapovém editoru; UI ukazuje dostupnost, počet inventářů a dovolí
  filtr pro daný projekt zapnout až po stažení cache. Slouží jako offline
  sanity filtr inventáře. Globální kalibrační baseline se
  trénuje jen z licenčně auditovaného manifestu anotovaných změn; výstup nese
  SHA-256, verze, licence a citace vstupů.
- Výsledky se ukládají ve výchozím nastavení do souborového genealogického
  úložiště. Neo4j je volitelný adaptér. JSON export obsahuje slova, původové
  hrany, události a prosodická data.
- Frontend podporuje češtinu/angličtinu, interakci s mapou, typ dědičnost nebo
  kontakt, izoglosu a export uložené simulace. Nabízí také vestavěné profily
  vah zvukových změn, per-run audit aplikovaných změn, seznam pravidel pro
  vybranou dědičnou hranu a uložený Markdownový gramatický náčrt větve.

## Částečně implementováno

- Infrastruktura globální baseline už rodinně vyvažuje anotovaná pozorování a
  předává vyhlazené váhy presetům. Zatím ale není připojen dostatečně široký
  otevřený směrovaný korpus, takže nelze tvrdit globální vědeckou kalibraci.
- UI zobrazuje profil konkrétního běhu (počet pravidel, tempo, schémata a
  deletivní zásahy); Hellingerovo srovnání s externí baseline a GLED grid-search
  zatím zůstávají výzkumné CLI workflow.
- GLED lze použít jako CC BY globální profil nesměrované kognátní divergence
  (identita, substituce, mezery) a jako cíl makro-kalibrace. Není a nesmí být
  zdrojem směrovaných vah jednotlivých zvukových schémat.
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

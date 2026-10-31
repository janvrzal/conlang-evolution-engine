# CEE: ověřený stav implementace

Aktualizováno: 2026-10-29. Tento dokument je provozní doplněk k whitepaperu
`CEE_master.md`: whitepaper popisuje směr a výzkumné hypotézy, kdežto zde je
výhradně to, co je v repozitáři implementované a kryté testy.

## Engine v2 (větev `engine-v2`)

Nové simulační jádro `src/cee/v2/` podle `docs/engine-v2/`. Zatím není
napojené na CLI, API ani UI; spouští se z testů a skriptů.

| Milník | Stav |
|---|---|
| M1 jádro: svět, území, skupiny, síť, přenos, dialekty | hotovo (sublinearita vzdálenosti odložena do M6) |
| M2 zvuk: hlásky, 20 rodin změn, fonologizace, reliktní výjimky | hotovo |
| M3 morfologie: paradigmata, morfologizace, analogie | hotovo |
| M3b lexikon a význam: graf pojmů, posun, odvození, složeniny, tabu | hotovo |
| M4 syntax: konstrukce, gramatikalizace, analytizace, Jespersenův cyklus | hotovo |
| M4b modulární gramatika: katalog funkcí, profil protojazyka, exaptace | hotovo |
| M5 kontakt: víc jazyků, výpůjčky, L2 mluvčí, přechod jazyka a substrát | hotovo |
| M6a instituce: písmo, škola, tisk, diglosie a standardizace | hotovo |
| M6b společnost: migrace, události, vitalita a domény jazyka, diglosie, náboženství, Séguyho zákon | hotovo |
| M6c linie jazyků a export pro UI | hotovo (výkon plného modelu nad rozpočtem) |
| M6d odezva: průběžné výsledky, checkpointy, přepočet od změny | hotovo (výpočet sám zůstává pomalý) |
| M6e průběžné indexy, dávková inovace a zpevnění bran | na větvi `engine-v2-numba` hotovo po fázi 5 a zpevnění bran (`07-prubezne-indexy.md`, `08-davkova-inovace.md`, `09-zpevneni-bran.md`): dávkové `hash_poisson` losování inovací s neutrálním klíčem `"innovation-change"`, přírůstkové indexy míst a měr (`valley-50` 23,6–25,4 s místo 37,6 s, inovace 2,12× rychlejší; `grid-5x5` 2,2–2,5 s místo 3,5 s) a zpevnění stochastických milníkových bran na `k` z `N` podle auditu `v2_gate_rates.py`; původní orientační rozpočet ≤ 5–8 s zůstává mimo dosah bez změny modelu (M7) či paralelismu |
| M7 kalibrace | plán |

Platné referenční otisky (`scripts/v2_digests.py`, doménový klíč `"innovation-change"`):
`phonology` `8d7971c1a6afe5f6b8ca9f33919b8b3e2e929d56832ae4e04c738efa18c53840`,
`morphology` `3567be70a272f42662ecd44838079d33abf953d090c59a9a2da4079467933a06`,
`syntax` `eefb5db5be7bfac8284c400b7a0ebc81fe4a65c04325aaafa9b1cdb39d50fc38`,
`grid-5x5` `a6aa9a33f1a416e33144a0235d19194c442bb27ede6f966c5092a7b7342b08c0`,
`shift` `47d69ad8a511366b2dedba0a9c30550c0c1d0045aa24ce3eafbdde03663da71a`,
`island-city` `a082c2463488378f975fc050a9265f62856e716d6b1dd0b4d813f7d5323ab2cf`,
`valley-50` `02ccc3819e155cff096d791466f3dcdab88142a4e31e9b1920f92fc9898b1272`.

Naměřené hodnoty a známé mezery jsou v `docs/engine-v2/05-specifikace.md`.

Na větvi `engine-v2-typologie` jsou hotové části A–D (`engine-v2/10-typologie.md`):
měřidlo typologické pestrosti proti WALS, sekundární artikulace (palatalizace,
nosové vokály, labializace), kontext a úplná gramatika pro pokusy, zánik
kategorie a prozódie (pět poloh přízvuku, posun a síla přízvuku). Na větvi
`engine-v2-dynamika` navazuje část E (`engine-v2/11-gramaticka-dynamika.md`):
zánik kategorie bez prahu, kontakt přes L2 mluvčí (`Learnability`),
kalibrační konstanty dynamiky jako `world.params` (`src/cee/v2/parameters.py`)
a test dosažitelnosti cyklu kategorií: bez kontaktu flexivní kategorie jen
přibývají, s kontaktem se cyklus rozběhne. První kalibrace M7a (`engine-v2/12-kalibrace-m7a.md`)
oddělila vznik kategorie od obnovy, přidala vid jako náhradu minulého času
a nastavila výchozí hodnoty podle stacionarity WALS; minulý čas a člen se
teď v rodinách liší jako ve skutečnosti, tempo je předběžné. Cíle kalibrace
M7 jsou ve specifikaci (oddíl „Cíle kalibrace M7“). Nic z toho zatím není v `engine-v2`;
sloučení čeká na uživatele. Tyto výsledky nejsou kalibrací M7.


## Legacy jádro

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

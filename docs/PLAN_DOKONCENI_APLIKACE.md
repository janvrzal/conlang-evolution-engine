# Plán dokončení aplikace CEE

Datum: 6. 11. 2026. Pracovní větev `app-dokonceni` (worktree
`~/Documents/CEE-worktrees/app`), založená z `engine-v2-dynamika` (1b063b4).
Rozpracované UI z `engine-v2-numba` je na ní jako první commit beze změny
(záloha i na větvi `ui-wip`).

Stav: **návrh ke schválení.** Nic z kroků 1–8 zatím není implementované.

## 1. Audit: co dnes v repozitáři je

### Dvě uživatelská rozhraní

| | `ui/` (SvelteKit, web) | `desktop/` (Tauri 2 + SvelteKit) |
|---|---|---|
| Engine | **v1** (Python): `/api/simulate_dynamic`, `/api/protolang/generate`, `/api/runs/{id}/…` | **v2** (Rust přes `cee_engine_py`): `/api/v2/*` |
| Data projektu | projekt V3 (`project_schema.py`): jazykové uzly, hrany dědění a kontaktu po časových řezech, polygony států, obchodní cesty, mapa (OpenLayers) | soubor `cee-v2-world/1` (`WorldSpec`): kraje jako body, jazyky, události |
| Ukládání | server, `/api/projects/{id}` (JSON na disku) | otevření souboru, uložení stažením; Tauri dialog chybí |
| Obrazovky | přehled projektů, svět/mapa (OpenLayers), rodokmen (Svelte Flow), časová osa, nastavení, detail jazyka (slovník, vrt slova, izoglosa, gramatika); WIP: Studio, Model vývoje, technický editor (`legacy`) | cesta práce Svět → Protojazyk → Dějiny → Výsledky → Větve; zatím jen **tabulky** (svět, jazyky, události, seznam jazyků s nářečími), Větve prázdné |
| Vizuál | shadcn/Tailwind, bez vlastního jazyka | „Poloostrov“ (Piazzolla, Charis 7, papír Břidlice, červený inkoust), i18n CS/EN |
| Testy | Vitest 41 ✔, svelte-check 0 chyb | Vitest 4 ✔ + 1 integrační (s běžícím enginem), svelte-check 0 chyb |

WIP v `ui/` (září–říjen 2026) patří do světa enginu v1: Studio spouští
`simulateDynamic`, Model vývoje edituje časové řezy uzlů a hran. Nic z toho
nevolá `/api/v2`.

Návrh UI pro engine v2 je v [`docs/ui-navrh`](ui-navrh/README.md): funkční
prototypy všech pěti kroků nad skutečnými běhy (HTML, celkem 1,6 MB),
vizuální jazyk a systém jmen (`zdroje/naming.js`, v desktopu už převedený do
`desktop/src/lib/naming.ts`). Podle dřívějších rozhodnutí (1. 11. 2026) je
cílem desktopová aplikace a struktura stránek `ui/` se nepřebírá.

### Server (`src/cee/api`)

- `/api/v2`: `schema`, `validate`, `runs` (start, stav se snímky, výsledek,
  zrušení). Revize API 10. Běhy jen **v paměti** (posledních 8), po
  restartu serveru zmizí.
- Zbytek serveru je v1 (projekty V3, protojazyk v1, běhy v1, PHOIBLE).
- Chybí pro v2: náhled protoslovníku bez běhu (obrazovka Protojazyk má
  „výchozí slova z enginu“), uložení a seznam běhů, srovnání dvou běhů.

### Engine v2 (Rust)

- `rust/cee_engine` (+ CLI `cee`), `rust/cee_py` (PyO3 vazba
  `cee_engine_py`), server ji najde v `rust/cee_py/target/py`.
- Export `cee-v2/1` obsahuje vše, co obrazovky Výsledky a Větve potřebují:
  `territories`, `groups`, `links`, `snapshots` (dialekty a jazyky po 100
  letech), `lineages`, `lexicon` a `grammar` po skupinách, `states`,
  `borders`, `standards`, `dialect_facts`, `census`, `events`. Snímek
  (`frame`) během běhu: populace, L2, jazyky, sčítání, státy, endonymy.
- **Zjištěno při auditu:** vazba v `CEE-dynamika` je zastaralá (sestavená
  4. 11. 20:31, `cee_py` změněn 22:05). `POST /api/v2/validate` s ní padá
  (`TypeError` v `runner.check`). S vazbou sestavenou v tomto worktree vše
  funguje (oddíl „Ověření“). Server dnes nepozná, že vazba neodpovídá zdroji.

### Drobné nesoulady v `desktop/`

- `API_REVISION = 9`, server má 10; `Issue` nemá `severity`, takže
  hlavička počítá varování jako chyby.
- Uložení v Tauri jen stažením (komentář „později dialog“).
- `WorldSpec` má `extra="forbid"`: do souboru světa nejde uložit nic, co
  potřebuje jen UI (podklad mapy, pevnina, rozložení, uložené běhy). Je
  potřeba obal projektu (viz krok 2).

## 2. Rozhodnutí, která potřebuji

1. **Cílová aplikace:** `desktop/` na enginu v2 (doporučuji; odpovídá
   rozhodnutím z 1. 11. a návrhu „Poloostrov“). `ui/` zůstane jako
   doplněk pro engine v1 beze změn, včetně tvého WIP. Alternativa: stavět
   dál v `ui/` a převést ho na v2 (víc práce, jiný vizuál než schválený
   návrh).
2. **Formát projektu:** obal `cee-project/1` = `{ world: WorldSpec, map:
   {podklad, pevnina, měřítko}, ui: {…}, runs: [odkazy] }`, uložený jako
   jeden `.cee` soubor (JSON); výsledky běhů vedle něj
   (`<jméno>.runs/<id>.json.gz`). Doporučuji. Alternativa: běhy jen
   v datech aplikace.
3. **E2E testy:** přidat Playwright pro `desktop/` v prohlížečovém režimu
   proti běžícímu serveru (kouřové testy každé obrazovky). Doporučuji;
   dnes projekt Playwright nemá.
4. **Balení desktopu:** zatím Python server jako pomocný proces (beze
   změny). Přímé volání Rustu z Tauri (bez Pythonu) je samostatný krok 8,
   až po obrazovkách.

## 3. Kroky

Odhady jsou v pracovních dnech jedné relace včetně testů a ladění.

| # | Krok | Obsah | Testy | Odhad |
|---|---|---|---|---|
| 1 | **Spojení s enginem v2** | sestavení vazby skriptem (`scripts/build_binding.sh`) a kontrola stáří vazby v `/api/health` (UI ukáže „engine potřebuje přestavět“); `API_REVISION` 10, `severity` v `Issue`, počítadlo chyb vs. varování; README desktopu | Vitest (engine.ts, state), integrační test zelený | 0,5 |
| 2 | **Projekt a uložené běhy** | obal `cee-project/1` (+ načtení starého `cee-v2-world/1`), Tauri dialogy otevřít/uložit (`plugin-dialog`, `plugin-fs`), nedávné soubory; server: uložení exportu běhu na disk, `GET /api/v2/runs` seznam, načtení po restartu | Vitest (převod formátu, stav), pytest jen se svolením | 1,5 |
| 3 | **Výsledky** | mapa vsí (Voronoi) obarvená jazykem, nářečí světlostí, kreslení průběžně ze snímků; řeka jazyků v čase s kurzorem roku; karta jazyka (endonym, původ, osud, mluvčí); srovnávací slovník s výpůjčkami a vrtem slova; Slovo v krajině (tvary na mapě, izoglosy) | Vitest (geometrie, odvození dat z exportu), Playwright kouř | 4 |
| 4 | **Editor světa** | mapa z prototypu: kraj = bod, území Voronoi ořezané pevninou, nástroje V/R/S, karta kraje přesně podle `RegionSpec` s větou o dopadu, podklad z obrázku (ztlumit/odbarvit/skrýt), živé ověření přes `/api/v2/validate`, zpět/znovu | Vitest (Voronoi, sousedství, převod do spec), Playwright | 3,5 |
| 5 | **Dějiny** | mapa států v roce pod kurzorem, kronika s pruhy států a přetahovatelnými událostmi, karta pro všech 13 druhů událostí, výběr krajů na mapě, kontrola pořadí | Vitest (přehrání dějin, převod událostí), Playwright | 3 |
| 6 | **Protojazyk** | tabulka IPA, lichoběžník samohlásek, četnost ve třech úrovních, přízvuk, mluvnice, slovník; server `POST /api/v2/proto` (protoslovník v ročníku 0 z vazby, bez běhu) | Vitest, Playwright; endpoint pytestem jen se svolením | 2,5 |
| 7 | **Větve** | dva běhy vedle sebe ve stejném roce, vsi s jiným jazykem červeně, řeky jazyků se společným měřítkem, slova vybrané vsi v obou větvích; větev = kopie světa s jinými událostmi | Vitest (srovnání exportů), Playwright | 2 |
| 8 | **Balení** | sestavení `.app` (Tauri bundle) s enginem: buď Python + vazba přes PyInstaller, nebo přímé volání `cee_engine` z Tauri (validace schématu by se musela přenést z pydanticu) — rozhodnutí před krokem | ruční ověření sestavené aplikace | 2–3 |

Celkem zhruba **19–20 dní** práce.

### Doporučené pořadí: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

- 1 a 2 jsou základ: bez platné vazby nejde nic ověřit, bez uložení
  projektu a běhů se nedá s aplikací pracovat.
- **Výsledky před editorem:** nad ukázkovým Poloostrovem dají nejrychleji
  něco, na co se dá dívat a co prověří export; editor pak staví na stejné
  mapové vrstvě (Voronoi, pevnina, popisky).
- **Protojazyk až po Dějinách:** souběžně běží relace, která mění generátor
  protojazyka v Rustu; obrazovka nad ním má smysl až po jejím sloučení.
- Větve potřebují uložené běhy (krok 2) a mapu výsledků (krok 3).
- Kroky 3–7 jsou na sobě nezávislé jen částečně (sdílí mapové komponenty),
  proto je doporučuji dělat postupně v jedné větvi, ne souběžně.

### Co v plánu není

- Změny enginu v Rustu a parametrů (běží rekalibrace tempa a protojazyk).
  Díry v enginu, které UI odhalí, zapíšu jako zadání.
- Události po skupinách (`Contact`, `Migration`, `Conquest`) ve `WorldSpec`.
- Úpravy `ui/` a enginu v1.
- Merge do `engine-v2-dynamika` nebo `main` a push: jen s tvým souhlasem.

## 4. Ověření

Audit ověřil v tomto worktree:

- `desktop/`: `vitest run` 4 ✔ (1 přeskočen), `svelte-check` 0 chyb.
- `ui/` s WIP: `vitest run` 41 ✔, `svelte-check` 0 chyb.
- Server + vazba z `CEE-dynamika`: `/api/health` OK (revize 10),
  `/api/v2/validate` padá na zastaralé vazbě (viz výše).
- Server + vazba sestavená v tomto worktree (`maturin build --release`,
  instalace do `rust/cee_py/target/py`, mimo git): integrační test desktopu
  projde (Poloostrov, 400 let: kontrola → běh → jména jazyků a nářečí
  česky i anglicky, 2,1 s). Cesta UI → `/api/v2` → Rust tedy funguje.

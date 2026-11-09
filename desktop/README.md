# CEE desktop

Desktopová aplikace CEE: Tauri 2, UI ve Svelte 5 (SvelteKit, statický výstup)
a engine v2 v Rustu přímo v procesu aplikace (crate `rust/cee_engine`, příkazy Tauri
v `src-tauri/src`). Python ani server za běhu nepotřebuje. Vizuální jazyk a návrh obrazovek
jsou v [`docs/ui-navrh`](../docs/ui-navrh/README.md).

## Stavba

- **Design systém** `src/lib/ds` (pravidla v `src/lib/ds/README.md`). Sentinel
  (`npm run check:ds`, součást `npm test`) hlídá, že obrazovky skládají jen jeho komponenty.
- **Obrazovky** `src/routes/<obrazovka>`: Projekty, Svět, Protojazyky, Pojmy, Dějiny, Model
  (Zadání) a Atlas, Jazyky, Slova, Kronika, Co kdyby (Výsledek). Kostra s lištou, ověřením
  zadání, Zpět/Znovu a časovou osou je v `src/routes/+layout.svelte`.
- **Data** `src/lib/model` (typy exportu `cee-v2/1`, mapa, jazyky, variety malých jazyků),
  stav `src/lib/state.svelte.ts`, texty `src/lib/messages/screens/<obrazovka>.ts` (cs i en).
- **Engine** `src-tauri/src/engine.rs`: ověření zadání, schéma pro UI, běhy na pozadí se
  snímky, export s událostmi časové osy a souhrnem všech událostí po stoletích (`event_summary`).
  Popis a ověření tvaru zadání: `src-tauri/src/spec_schema.rs`.

## Desktop (Tauri)

Potřebuje Rust (`rustup`). Engine se i ve vývoji překládá s optimalizacemi (první sestavení trvá):

```bash
cd desktop && npm install && npm run tauri dev
```

Testy enginu v aplikaci (ověření Talvery, schéma, krátký běh):

```bash
cd desktop/src-tauri && cargo test --lib
```

Popis zadání (pole, typy, meze, druhy událostí) je v Rustu v `src-tauri/src/spec_schema.rs`:
z něj je JSON schéma pro formuláře i ověření tvaru s českými hláškami a cestou k poli.
Test `shoda_s_pydanticem` ho porovnává s pydanticem (`src/cee/v2/spec.py`, který dál používá
Python server); po změně `spec.py` vygeneruj vzor `scripts/schema.py` a dorovnej `spec_schema.rs`.

## Sestavení aplikace (.app)

```bash
cd desktop && npm run tauri build -- --bundles app
```

Výsledek je v `src-tauri/target/release/bundle/macos/CEE.app`. Bez podpisu ji macOS při prvním
spuštění zablokuje (Gatekeeper); otevře se pravým tlačítkem → Otevřít.

**Podpis a notarizace** (až bude certifikát Developer ID Application). Konfigurace je připravená
v `src-tauri/tauri.conf.json` (`bundle.macOS`: hardened runtime, macOS 12+); identita a údaje
pro notarizaci se dávají proměnnými prostředí, ne do repozitáře:

```bash
export APPLE_SIGNING_IDENTITY="Developer ID Application: Jméno (TEAMID)"
export APPLE_ID="apple-id@example.com" APPLE_PASSWORD="heslo-pro-aplikaci" APPLE_TEAM_ID="TEAMID"
npm run tauri build -- --bundles app,dmg
```

Tauri pak aplikaci podepíše, odešle k notarizaci a výsledek připojí (staple).

## Vývoj UI v prohlížeči

```bash
cd desktop && npm run dev
```

Bez enginu se dá pracovat nad vzorkem skutečného běhu: `scripts/fixture.py` udělá ze
zkráceného exportu soubor do `static/fixtures/` (mimo git) a `?fixture=talvera` ho načte
(`&branch=…` druhou větev pro Co kdyby). Snímek obrazovky: `node scripts/shot.mjs URL soubor.png`.
UI v prohlížeči umí i Python server `/api/v2` na portech 8000–8019
(`PYTHONPATH=src python -m uvicorn cee.api.server:app --port 8001`).

## Písmo

UI je v Piazzolle (Fontsource), IPA v Charis 7 (SIL, OFL 1.1) přibaleném
v `static/fonts` v úplné, neupravené podobě s licencí `Charis-OFL.txt`.
Pokrývá všech 138 znaků, které engine umí zapsat, včetně kombinační
diakritiky a skládání znamének. Porovnání s Gentium Book Plus, Doulos SIL,
Andika, Noto Serif a Libertinus Serif (tomu chybí tónové značky) je
v historii projektu (1. 11. 2026). Charis se nesmí podmnožinovat pod svým
jménem (vyhrazené jméno v OFL), proto se přibaluje celé.

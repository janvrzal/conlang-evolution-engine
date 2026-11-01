# CEE desktop

Desktopová aplikace CEE: Tauri 2, UI ve Svelte 5 (SvelteKit, statický výstup)
a engine v2 jako pomocný proces s `/api/v2`. Vizuální jazyk a návrh obrazovek
jsou v [`docs/ui-navrh`](../docs/ui-navrh/README.md).

## Stav kostry

- Cesta práce Svět → Protojazyk → Dějiny → Výsledky → Větve, otevření a uložení
  popisu světa (`cee-v2-world/1`), ukázkový svět Poloostrov.
- Spojení s enginem: kontrola světa, běh s průběhem, výsledek. Výsledky
  ukazují jazyky a nářečí se jmény z vlastních jmen jazyků (`src/lib/naming.ts`).
- Všechny popisky česky i anglicky (`src/lib/messages/cs.ts`, `en.ts`,
  přepínač CS/EN). Hlášení enginu jsou zatím jen česky.
- Obrazovky z prototypů (mapa, editor, kronika, řeka jazyků, větve) přijdou
  postupně; teď jsou to tabulky nad stejnými daty.

## Vývoj v prohlížeči

Engine běží zvlášť a UI ho najde na portech 8000–8019:

```bash
PYTHONPATH=src python -m uvicorn cee.api.server:app --port 8001
```

```bash
cd desktop && npm install && npm run dev
```

Testy (`npm test`); s běžícím enginem i průchod světem:

```bash
CEE_ENGINE_URL=http://127.0.0.1:8001 npm test
```

## Desktop (Tauri)

Potřebuje Rust (`rustup`). Aplikace spustí engine sama na volném portu:

```bash
CEE_PYTHON=../../CEE/.venv/bin/python CEE_ENGINE_SRC=$(pwd)/../src npm run tauri dev
```

Zabalení enginu do aplikace (PyInstaller) a později přímé volání enginu
v Rustu přijde místo pomocného procesu.

## Písmo

UI je v Piazzolle (Fontsource), IPA v Charis 7 (SIL, OFL 1.1) přibaleném
v `static/fonts` v úplné, neupravené podobě s licencí `Charis-OFL.txt`.
Pokrývá všech 138 znaků, které engine umí zapsat, včetně kombinační
diakritiky a skládání znamének. Porovnání s Gentium Book Plus, Doulos SIL,
Andika, Noto Serif a Libertinus Serif (tomu chybí tónové značky) je
v historii projektu (1. 11. 2026). Charis se nesmí podmnožinovat pod svým
jménem (vyhrazené jméno v OFL), proto se přibaluje celé.

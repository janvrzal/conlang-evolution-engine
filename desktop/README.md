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

UI používá Piazzolla a pro IPA Charis (Fontsource). Fontsource z Charis
vynechává část kombinační diakritiky, proto `npm run fonts` zkopíruje úplné
Charis 7 do `static/fonts` (mimo git) z balíku, na jehož složku `web` ukazuje
`CEE_CHARIS`.

"""Sestaví ucelený návrh aplikace z pěti hotových prototypů.

Každá obrazovka zůstává svým prototypem (dokument v `srcdoc` rámu, takže se
skripty ani styly nepletou), ale hlavičku, cestu práce, stav běhu a sdílený
rok drží společná kostra. Prototypy se jen nepatrně upraví:

- skryje se jejich vlastní hlavička,
- Výsledkům se skryjí záložky a rok (kreslí je kostra, Slovo v krajině je třetí pohled),
- rok Výsledků a Větví ovládá kostra (posuvník, přehrávání),
- „Pokračovat“, „Zpět“ a „Spustit“ převezme kostra,
- vloží se háček, který posílá kostře rok a změny a přijímá rok a režim.

Spouští se v `docs/ui-navrh/zdroje`:

    python build_app.py VÝSTUP_ADRESÁŘ [CESTA_K_PÍSMŮM]

Do výstupu zapíše `index.html` a zkopíruje Charis (z `desktop/static/fonts`)
do `fonts/`. Kopie bez písma jde do `../prototypy/aplikace.html`.
"""

import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTO = HERE.parent / "prototypy"
FONTS = HERE.parents[2] / "desktop" / "static" / "fonts"

# klíč rámu, soubor prototypu, co kostra převezme z tlačítek, krok roku (None = bez roku)
FRAMES = {
    "svet": ("editor-sveta", {"next": "protojazyk"}, None),
    "proto": ("protojazyk", {"back": "svet", "next": "dejiny"}, None),
    "dejiny": ("dejiny", {"run": "@run"}, "UI.year = Math.round(y / STEP) * STEP; renderAll();"),
    "vysledky": ("vysledky", {}, "UI.year = Math.max(0, Math.min(END, Math.round(y / 50) * 50)); render();"),
    "slovo": ("slovo-v-krajine", {}, "S.year = Math.max(0, Math.min(D.end, Math.round(y / D.step) * D.step)); render(true);"),
    "vetve": ("vetve", {}, "UI.year = Math.max(0, Math.min(END, Math.round(y / 50) * 50)); render();"),
}
GET_YEAR = {"dejiny": "UI.year", "vysledky": "UI.year", "slovo": "S.year", "vetve": "UI.year"}

FONT_FACE = """
@font-face { font-family: "Charis CEE"; src: url("fonts/Charis-Regular.woff2") format("woff2"); font-weight: 400; font-style: normal; font-display: swap; }
@font-face { font-family: "Charis CEE"; src: url("fonts/Charis-Italic.woff2") format("woff2"); font-weight: 400; font-style: italic; font-display: swap; }
@font-face { font-family: "Charis CEE"; src: url("fonts/Charis-Bold.woff2") format("woff2"); font-weight: 700; font-style: normal; font-display: swap; }
"""

# Úpravy vzhledu rámu: bez vlastní hlavičky (rok Výsledků a Větví ovládá kostra), horní okraj dělá kostra.
FRAME_CSS = {
    "default": "header.top { display: none !important; } body { padding-top: 0 !important; }",
    "slovo": "body { padding-top: 10px !important; }",
    "vysledky": ("header.top { display: none !important; } body { padding-top: 0 !important; }"
                 " .tabs { display: none !important; }"),
}


def hook(key: str, actions: dict[str, str], set_year: str | None) -> str:
    """Háček vložený na konec skriptu prototypu (uvnitř jeho funkce, vidí jeho stav)."""
    get = GET_YEAR.get(key)
    return f"""
  // --- háček ucelené aplikace ---
  (() => {{
    const post = (m) => {{ try {{ parent.postMessage(Object.assign({{ cee: true, frame: {json.dumps(key)} }}, m), '*'); }} catch (_) {{}} }};
    const actions = {json.dumps(actions)};
    document.addEventListener('click', (e) => {{
      const b = e.target.closest && e.target.closest('button[id], a[id]');
      if (!b || !(b.id in actions)) return;
      e.preventDefault(); e.stopImmediatePropagation();
      const to = actions[b.id];
      post(to === '@run' ? {{ type: 'run' }} : {{ type: 'go', to }});
    }}, true);
    const born = Date.now();
    const saved = document.getElementById('saved');
    if (saved) new MutationObserver(() => {{ if (Date.now() - born > 2000) post({{ type: 'edited' }}); }})
      .observe(saved, {{ childList: true, characterData: true, subtree: true }});
    window.addEventListener('message', (e) => {{
      const m = e.data || {{}};
      if (!m.cee) return;
      if (m.type === 'theme') {{
        if (m.theme) document.documentElement.setAttribute('data-theme', m.theme);
        else document.documentElement.removeAttribute('data-theme');
      }}
      {"if (m.type === 'year' && typeof m.year === 'number') { const y = m.year; " + set_year + " }" if set_year else ""}
      {"if (m.type === 'view' && typeof setView === 'function') setView(m.view);" if key == "vysledky" else ""}
    }});
    {"let last = null; setInterval(() => { const y = " + get + "; if (y !== last) { last = y; post({ type: 'year', year: y }); } }, 300);" if get else ""}
    post({{ type: 'ready', year: {get or "null"} }});
  }})();
"""


def frame_doc(key: str) -> str:
    name, actions, set_year = FRAMES[key]
    s = (PROTO / f"{name}.html").read_text(encoding="utf-8")
    # Písmo: jedna sada Charis vedle stránky místo vložených podmnožin.
    s = re.sub(r'@font-face\s*\{[^}]*"Charis CEE"[^}]*\}', "", s)
    css = FONT_FACE + FRAME_CSS.get(key, FRAME_CSS["default"])
    # Za poslední styl prototypu, aby úpravy v kaskádě vyhrály (prototypy nemají <head>).
    cut = s.rfind("</style>") + len("</style>")
    s = s[:cut] + f"<style>{css}</style>" + s[cut:]
    # Háček na konec posledního skriptu, dovnitř jeho funkce.
    scripts = list(re.finditer(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>(.*?)</script>", s, re.S))
    last = scripts[-1]
    body = last.group(1)
    end = body.rstrip().rfind("})();")
    if end < 0:
        raise SystemExit(f"{name}: skript nekončí '}})();'")
    body = body[:end] + hook(key, actions, set_year) + body[end:]
    # Rám vložený skriptem se může začít číst dřív, než dostane rozměry; mapy by se
    # spočítaly pro plátno 0 × 0. Skript proto počká, až má okno velikost.
    body = ("\n(function ceeStart() {\n  if (!window.innerWidth || !window.innerHeight) { requestAnimationFrame(ceeStart); return; }\n"
            + body + "\n})();\n")
    return s[: last.start(1)] + body + s[last.end(1):]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "aplikace"
    fonts = Path(sys.argv[2]) if len(sys.argv) > 2 else FONTS
    out.mkdir(parents=True, exist_ok=True)
    shell = (HERE / "app.template.html").read_text(encoding="utf-8")
    def embed(key: str) -> str:
        data = json.dumps(frame_doc(key)).replace("</", "<\\/")
        return f'<script type="application/json" id="doc-{key}">{data}</script>'

    docs = "\n".join(embed(key) for key in FRAMES)
    page = shell.replace("<!-- FRAMES -->", docs)
    (out / "index.html").write_text(page, encoding="utf-8")
    (PROTO / "aplikace.html").write_text(page, encoding="utf-8")
    (out / "fonts").mkdir(exist_ok=True)
    for font in ("Charis-Regular.woff2", "Charis-Italic.woff2", "Charis-Bold.woff2", "Charis-OFL.txt"):
        shutil.copy(fonts / font, out / "fonts" / font)
    print(f"{out / 'index.html'}: {len(page) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()

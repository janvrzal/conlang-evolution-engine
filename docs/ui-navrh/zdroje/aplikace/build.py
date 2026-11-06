"""Sestaví stránku návrhu: šablona + jména (naming.js) + data z prep.py + písmo Charis.

    python build.py DATA.json VÝSTUP_ADRESÁŘ

Do výstupu zapíše index.html a fonts/ (Charis z desktop/static/fonts) a kopii
stránky do docs/ui-navrh/prototypy/aplikace.html (bez písma).
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main() -> None:
    data, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    page = (HERE / "template.html").read_text(encoding="utf-8")
    page = page.replace("/*NAMING*/", (HERE / "naming.js").read_text(encoding="utf-8"))
    page = page.replace("__DATA__", data.read_text(encoding="utf-8").replace("</", "<\\/"))
    (out / "index.html").write_text(page, encoding="utf-8")
    (HERE.parents[1] / "prototypy" / "aplikace.html").write_text(page, encoding="utf-8")
    (out / "fonts").mkdir(exist_ok=True)
    for font in ("Charis-Regular.woff2", "Charis-Italic.woff2", "Charis-Bold.woff2", "Charis-OFL.txt"):
        shutil.copy(ROOT / "desktop/static/fonts" / font, out / "fonts" / font)
    print(out / "index.html", f"{len(page.encode()) / 1e6:.2f} MB")


if __name__ == "__main__":
    main()

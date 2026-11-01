"""Sestaví obrazovku Dějiny: protoslovník (jména) + pojmenování + písmo."""

import json
import re
from pathlib import Path

from fonts import charis

HERE = Path(__file__).parent
concepts = json.loads(re.search(r"const CONCEPTS = (\[.*?\]);\n", (HERE / "protojazyk.html").read_text()).group(1))
out = ((HERE / "dejiny.template.html").read_text()
       .replace("__LEXICON__", json.dumps({c: f for c, _, f in concepts}, ensure_ascii=False))
       .replace("__NAMING__", (HERE / "naming.js").read_text())
       .replace("__CHARIS_REGULAR__", charis()))
(HERE / "dejiny.html").write_text(out)
print(len(out) // 1024, "kB")

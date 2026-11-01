"""Sestaví editor světa: protoslovník z enginu (pro jména) + písmo Charis."""

import json
import re
from pathlib import Path

from fonts import charis

HERE = Path(__file__).parent

page = (HERE / "protojazyk.html").read_text()
concepts = json.loads(re.search(r"const CONCEPTS = (\[.*?\]);\n", page).group(1))
lex = {concept: form for concept, _, form in concepts}
out = ((HERE / "editor.template.html").read_text()
       .replace("__LEXICON__", json.dumps(lex, ensure_ascii=False))
       .replace("__CHARIS_REGULAR__", charis()))
(HERE / "editor-sveta.html").write_text(out)
print(len(out) // 1024, "kB")

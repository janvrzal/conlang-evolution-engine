"""Vzor pro test shody: schéma zadání z pydanticu (src-tauri/tests/pydantic-schema.json).

    python scripts/schema.py        # z kořene desktop/, s PYTHONPATH=../src

Aplikace má popis zadání v Rustu (src-tauri/src/spec_schema.rs) a Python za běhu nepotřebuje.
Test `spec_schema::tests::shoda_s_pydanticem` porovnává rustové schéma s tímto výstupem
pydanticu (src/cee/v2/spec.py). Po změně spec.py spusť skript a dorovnej spec_schema.rs.
"""
import json
from pathlib import Path

from cee.v2 import spec

out = Path(__file__).resolve().parents[1] / "src-tauri" / "tests" / "pydantic-schema.json"
vocabulary = spec.vocabulary_options(0)
vocabulary.pop("max")
data = {
    "format": spec.FORMAT,
    "json_schema": spec.WorldSpec.model_json_schema(),
    "event_kinds": list(spec.EVENT_KINDS),
    "vocabulary": vocabulary,
}
out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(out, len(data["event_kinds"]), "druhů událostí")

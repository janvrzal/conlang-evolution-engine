"""Statická část schématu enginu pro desktop (src-tauri/data/schema.json).

    python scripts/schema.py        # z kořene desktop/, s PYTHONPATH=../src

Zadání světa popisuje pydantic (src/cee/v2/spec.py); jeho JSON schéma, druhy událostí a volby
slovníku se tu uloží do souboru, který si Tauri zabuduje do aplikace. Parametry, slovní úrovně
a největší slovník bere aplikace za běhu přímo z rustového enginu. Po změně spec.py spusť znovu;
test v src-tauri hlídá, že druhy událostí sedí se schématem.
"""
import json
from pathlib import Path

from cee.v2 import spec

out = Path(__file__).resolve().parents[1] / "src-tauri" / "data" / "schema.json"
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

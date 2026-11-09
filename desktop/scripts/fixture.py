"""Ze skutečného běhu udělá vzorek dat pro vývoj obrazovek (desktop/static/fixtures, mimo git).

    python scripts/fixture.py BĚH_ADRESÁŘ VÝSTUP.json

BĚH_ADRESÁŘ obsahuje world.json, frames.json a export.json (výstup run_talvera.py).
Export se zkrátí: z událostí zůstanou jen dějinné a jazykové (bez milníků zvukových změn),
ze snímků se vynechá slovník a mluvnice. Aplikace vzorek načte v režimu vývoje přes ?fixture=jméno.
"""
import json
import sys

KEEP = {
    "language_split", "language_emerged", "language_ended", "language_shift", "nativization", "bilingualism",
    "transmission_stopped", "transmission_resumed", "codification", "printing", "migration", "conquest",
    "revival_movement", "state", "annexation", "secession", "collapse", "border_policy", "lingua_franca", "schools",
    "standard", "identity", "schooling", "grammaticalized", "stress_rule_changed", "stress_strength_changed", "exapted",
}
FRAME_KEYS = ("year", "tick", "groups", "languages", "endonyms", "dialects", "dialect_facts", "states", "census")

src, out = sys.argv[1], sys.argv[2]
world = json.load(open(f"{src}/world.json"))
frames = [{k: f[k] for k in FRAME_KEYS if k in f} for f in json.load(open(f"{src}/frames.json"))]
export = json.load(open(f"{src}/export.json"))
counts = {}
summary = {}
for e in export["events"]:
    counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    century = str(int(e["year"] // 100 * 100))
    row = summary.setdefault(century, {})
    row[e["kind"]] = row.get(e["kind"], 0) + 1
export["events"] = [e for e in export["events"] if e["kind"] in KEEP]
export["event_counts"] = counts
# souhrn po stoletích (století → druh → počet); server by ho měl posílat místo milionů událostí
export["event_summary"] = summary
export.pop("links", None)
json.dump({"world": world, "frames": frames, "result": export}, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print(out, len(export["events"]), "událostí")

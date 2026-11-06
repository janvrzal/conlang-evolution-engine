"""Pustí Poloostrov (rozšířený o nové možnosti enginu) v Rustu a uloží tick 0, snímky a export."""
import json, sys, time
sys.path.insert(0, sys.argv[1] + "/rust/cee_py/target/py")
import cee_engine_py as c

w = json.load(open(sys.argv[1] + "/desktop/static/projects/poloostrov.cee.json"))
w["background"] = "normal"
w["events"] += [
    {"kind": "settlement", "year": 350, "from": "bal", "to": "lisk", "share": 0.25, "settlements": 1},
    {"kind": "elite", "year": 525, "from": "pelna", "seat": "kaar", "subjects": ["kaar", "dorn"], "population": 120, "prestige": 2.0, "strength": 0.6},
]
if len(sys.argv) > 3 and sys.argv[3] == "b":
    # Větev B: západ v roce 1300 nepřipojí Rowohe, Sawe a Rokwu.
    w["events"] = [e for e in w["events"] if e["kind"] != "annexation"]
w["events"].sort(key=lambda e: e["year"])
out = sys.argv[2]
json.dump(w, open(out + "/world.json", "w"), ensure_ascii=False)
issues = c.check_spec(json.dumps(w))
print("issues", issues)
run = c.Run(json.dumps(w))
open(out + "/tick0.json", "w").write(run.export(False))
frames, seen, t = [], 0, time.time()
while True:
    more = run.advance(1)
    if run.snapshots != seen:
        seen = run.snapshots
        frame = json.loads(run.frame())
        # Slovník, mluvnice a stav skupin v okamžiku snímku (export jde kdykoli).
        full = json.loads(run.export(False))
        frame["lexicon"] = {g: {c: [w["form"], w["origin"], w["language"], w["loan"]] for c, w in lex.items()} for g, lex in full["lexicon"].items()}
        frame["grammar"] = {g: {f: [x["kind"], x["stage"], x["exponent"], x["source"], x["donor"]] for f, x in gr.items()} for g, gr in full["grammar"].items()}
        frame["group_state"] = {x["id"]: [x["territory"], x["domain"], x["written"], round(x["literacy"], 3), round(x["schooling"], 3), round(x["loyalty"], 3), x["standard"], x["code_language"], round(x["prestige"], 3), x["preserved"], round(x["revival"], 3)] for x in full["groups"]}
        frame["borders"] = full["borders"]
        frames.append(frame)
        print("snapshot", frame["year"], round(time.time() - t, 1), flush=True)
    if not more:
        break
json.dump(frames, open(out + "/frames.json", "w"), ensure_ascii=False)
open(out + "/export.json", "w").write(run.export(False))
print("done", round(time.time() - t, 1), "s", len(frames), "frames")

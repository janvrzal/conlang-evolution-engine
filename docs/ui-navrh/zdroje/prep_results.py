"""Zhustí run2.json na data obrazovky Výsledky a sestaví stránku."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import build_proto  # noqa: E402  (české glosy)
import record2  # noqa: E402
from fonts import charis  # noqa: E402
from cee.v2 import export  # noqa: E402
from cee.v2.simulation import Simulation  # noqa: E402
from cee.v2.spec import build  # noqa: E402



def proto_lexicons() -> dict[str, dict[str, str]]:
    world, _, _ = build(record2.spec())
    simulation = Simulation(world)
    for _ in simulation.iterate(25.0):
        pass
    return {"pra": {c: e["form"] for c, e in export.lexicon(simulation.world, "vardun-v0").items()},
            "vych": {c: e["form"] for c, e in export.lexicon(simulation.world, "pelna-v0").items()}}


def main() -> None:
    run = json.loads((HERE / "run2.json").read_text())
    lex = proto_lexicons()
    places = sorted(g["id"] for g in run["groups"] if not g["written"] and g["domain"] == "home" and g["id"] in run["forms"])
    pos = {g["id"]: g["position"] for g in run["groups"]}
    lineages = sorted(run["lineages"], key=lambda l: (l["start_year"], l["id"]))
    lin_index = {l["id"]: i for i, l in enumerate(lineages)}
    code_of = {}
    first = run["frames"][2]["groups"]
    for l in lineages:
        members = l["groups_at_start"]
        code_of[l["id"]] = first[members[0]][1]
    strings, sidx = [], {}

    def s(v):
        if v not in sidx:
            sidx[v] = len(strings)
            strings.append(v)
        return sidx[v]

    origins = []
    forms = {}
    for concept in record2.CONCEPTS:
        rows = []
        for gid in places:
            out, last = [], object()
            for entry in run["forms"][gid][concept]:
                value = None if entry[1] is None else (entry[1], entry[3], entry[4])
                if value == last:
                    continue
                last = value
                if value is None:
                    out.append([entry[0], -1, 0, ""])
                else:
                    if value[1] not in origins:
                        origins.append(value[1])
                    out.append([entry[0], s(value[0]), origins.index(value[1]), value[2]])
            rows.append(out)
        forms[concept] = rows
    frames = []
    for f in run["frames"]:
        lineage_of = {g: lin_index[k] for k, gs in f["languages"].items() for g in gs if k in lin_index}
        dialect_of = {g: i for i, cluster in enumerate(f["dialects"]) for g in cluster}
        frames.append({
            "year": f["year"],
            "lin": [lineage_of.get(g, -1) for g in places],
            "dia": [dialect_of.get(g, -1) for g in places],
            "pop": [f["groups"][g][0] for g in places],
            "code": [f["groups"][g][1] for g in places],
            "census": {r: {"home": c["home"], "public": c["public"], "state": c["state"]} for r, c in f["census"].items()},
            "states": f["states"],
        })
    regions = [{"id": r["id"], "x": r["position"][0], "y": r["position"][1], "terrain": r["terrain"], "language": r["language"]}
               for r in record2.spec()["regions"]]
    data = {
        "end": 2000, "step": 50,
        "regions": regions,
        "places": [{"id": g, "region": g.rsplit("-v", 1)[0], "x": pos[g][0], "y": pos[g][1]} for g in places],
        "lineages": [{"id": l["id"], "parent": lin_index.get(l["parent"]), "start": l["start_year"], "end": l["end_year"],
                      "code": code_of[l["id"]], "at_start": [places.index(g) for g in l["groups_at_start"] if g in places]} for l in lineages],
        "gloss": {c: build_proto.CS[c] for c in record2.CONCEPTS},
        "strings": strings, "origins": origins, "forms": forms, "frames": frames, "lex": lex,
        "events": [e for e in run["events"] if e["kind"] in (
            "state", "standard", "lingua_franca", "annexation", "secession", "schools", "preserve", "language_policy",
            "revival_movement", "collapse", "language_split", "language_ended")],
    }
    page = ((HERE / "vysledky.template.html").read_text()
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            .replace("__NAMING__", (HERE / "naming.js").read_text())
            .replace("__CHARIS_REGULAR__", charis()))
    (HERE / "vysledky.html").write_text(page)
    print(len(page) // 1024, "kB;", len(strings), "tvarů; původy", origins,
          "; pra ruka", lex["pra"]["hand"], "; vych ruka", lex["vych"]["hand"], file=sys.stderr)


if __name__ == "__main__":
    main()

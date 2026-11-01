"""Data obrazovky Větve: dva běhy (A hlavní, B dobytí východu) ve společném tvaru."""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import build_proto  # noqa: E402
import prep_results  # noqa: E402
import record2  # noqa: E402
import record3  # noqa: E402,F401  (přepíše record2.spec na větev B)
from fonts import charis  # noqa: E402



def pack(run, places, strings, sidx, origins):
    """Jedna větev. Ves = vesnice; při přechodu k jinému jazyku má dvě domácí skupiny, bere se ta početnější."""
    def s(v):
        if v not in sidx:
            sidx[v] = len(strings)
            strings.append(v)
        return sidx[v]

    lineages = sorted(run["lineages"], key=lambda l: (l["start_year"], l["id"]))
    # Krátké linie o pár vsích (šum pozorování během přechodu) se počítají k rodiči.
    size = {l["id"]: 0 for l in lineages}
    for f in run["frames"]:
        for k, gs in f["languages"].items():
            if k in size:
                size[k] = max(size[k], len({g.split(">")[0] for g in gs}))
    keep = [l for l in lineages if not (l["parent"] and size[l["id"]] <= 3)]
    kept = {l["id"] for l in keep}
    parent = {l["id"]: l["parent"] for l in lineages}

    def resolve(k):
        while k is not None and k not in kept:
            k = parent.get(k)
        return k

    lin_index = {l["id"]: i for i, l in enumerate(keep)}

    def dominant(f, place):
        cands = [g for g, (pop, code, dom) in f["groups"].items() if dom == "home" and (g == place or g.startswith(place + ">"))]
        return max(cands, key=lambda g: (f["groups"][g][0], g == place)) if cands else None

    frames, dom_by_year = [], []
    for f in run["frames"]:
        lineage_of = {g: k for k, gs in f["languages"].items() for g in gs}
        dialect_of = {g: i for i, cluster in enumerate(f["dialects"]) for g in cluster}
        doms = [dominant(f, p) for p in places]
        dom_by_year.append((f["year"], doms))
        lin = []
        for g in doms:
            k = resolve(lineage_of.get(g))
            lin.append(lin_index[k] if k in lin_index else -1)
        frames.append({"year": f["year"], "lin": lin, "dia": [dialect_of.get(g, -1) for g in doms],
                       "pop": [sum(pop for gg, (pop, code, dom) in f["groups"].items() if dom == "home" and (gg == p or gg.startswith(p + ">"))) for p in places],
                       "code": [f["groups"][g][1] if g else "pra" for g in doms],
                       "census": {r: {"home": c["home"], "public": c["public"], "state": c["state"]} for r, c in f["census"].items()}})

    def at(history, year):
        value = None
        for e in history:
            if e[0] <= year:
                value = e
            else:
                break
        return value or history[0]

    forms = {}
    for concept in record2.CONCEPTS:
        rows = []
        for pi, place in enumerate(places):
            out, last = [], object()
            for year, doms in dom_by_year:
                g = doms[pi]
                if g is None or g not in run["forms"]:
                    continue
                e = at(run["forms"][g][concept], year)
                value = None if e[1] is None else (e[1], e[3], e[4])
                if value == last:
                    continue
                last = value
                if value is None:
                    out.append([year, -1, 0, ""])
                else:
                    if value[1] not in origins:
                        origins.append(value[1])
                    out.append([year, s(value[0]), origins.index(value[1]), value[2]])
            rows.append(out or [[0, -1, 0, ""]])
        forms[concept] = rows
    def code_at(l):
        g = l["groups_at_start"][0]
        for f in run["frames"]:
            if f["year"] >= l["start_year"] and g in f["groups"]:
                return f["groups"][g][1]
        return "pra"

    return {
        "lineages": [{"id": l["id"], "parent": lin_index.get(resolve(l["parent"])), "start": l["start_year"], "end": l["end_year"],
                      "code": code_at(l),
                      "at_start": [places.index(g.split(">")[0]) for g in l["groups_at_start"] if g.split(">")[0] in places]}
                     for l in keep],
        "forms": forms, "frames": frames,
        "events": [e for e in run["events"] if e["kind"] in ("state", "annexation", "secession", "collapse", "language_split", "language_ended", "schools", "standard", "lingua_franca", "revival_movement", "language_policy")],
        "spec_events": run["spec"]["events"],
    }


def main() -> None:
    run_a = json.loads((HERE / "run2.json").read_text())
    run_b = json.loads((HERE / "run3.json").read_text())
    lex = prep_results.proto_lexicons()
    places = sorted(g["id"] for g in run_a["groups"] if not g["written"] and g["domain"] == "home" and ">" not in g["id"] and g["id"] in run_a["forms"])
    pos = {g["id"]: g["position"] for g in run_a["groups"]}
    strings, sidx, origins = [], {}, []
    data = {
        "end": 2000,
        "regions": [{"id": r["id"], "x": r["position"][0], "y": r["position"][1], "terrain": r["terrain"], "language": r["language"]}
                    for r in run_a["spec"]["regions"]],
        "places": [{"id": g, "region": g.rsplit("-v", 1)[0], "x": pos[g][0], "y": pos[g][1]} for g in places],
        "gloss": {c: build_proto.CS[c] for c in record2.CONCEPTS},
        "lex": lex,
        "runs": [
            {"name": "Hlavní", "fork": None, **pack(run_a, places, strings, sidx, origins)},
            {"name": "Dobytí východu", "fork": 1300, **pack(run_b, places, strings, sidx, origins)},
        ],
    }
    data["strings"], data["origins"] = strings, origins
    page = ((HERE / "vetve.template.html").read_text()
            .replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
            .replace("__NAMING__", (HERE / "naming.js").read_text())
            .replace("__CHARIS_REGULAR__", charis()))
    (HERE / "vetve.html").write_text(page)
    print(len(page) // 1024, "kB", file=sys.stderr)


if __name__ == "__main__":
    main()

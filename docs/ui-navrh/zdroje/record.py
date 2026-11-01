"""Skutečný běh pro prototyp srdeční scény: tvary slov po skupinách v čase."""

from __future__ import annotations

import json
import math
import sys

from cee.v2 import export
from cee.v2.simulation import Simulation
from cee.v2.spec import build

# Poloostrov: pobřežní nížina na západě, hřbet hor uprostřed, náhorní východ,
# ostrov na jihu. Souřadnice v km.
REGIONS = [
    ("Vardun", 40, 120, "plain"), ("Selm", 85, 95, "plain"), ("Orra", 70, 150, "plain"),
    ("Kestrin", 120, 130, "plain"), ("Bal", 30, 175, "plain"), ("Tumar", 110, 180, "hills"),
    ("Hesk", 150, 90, "hills"), ("Ivel", 160, 160, "mountains"), ("Dorn", 185, 115, "mountains"),
    ("Kaar", 175, 210, "hills"), ("Mirost", 225, 145, "plain"), ("Pelna", 235, 95, "plain"),
    ("Sorrow", 270, 125, "plain"), ("Ulm", 255, 185, "hills"), ("Teth", 300, 165, "plain"),
    ("Varra", 310, 100, "plain"), ("Nask", 60, 225, "plain"), ("Ebb", 140, 240, "plain"),
    ("Lisk", 105, 300, "island"), ("Corrin", 210, 240, "plain"),
]
REACH = 62.0


def spec() -> dict:
    regions = []
    for name, x, y, terrain in REGIONS:
        neighbours = [
            other for other, ox, oy, _ in REGIONS
            if other != name and math.dist((x, y), (ox, oy)) <= REACH
        ]
        if name == "Lisk":
            neighbours = ["Ebb", "Nask"]
        if name in ("Ebb", "Nask"):
            neighbours.append("Lisk")
        regions.append({
            "id": name.lower(), "name": name, "position": [float(x), float(y)],
            "neighbours": sorted({n.lower() for n in neighbours}), "villages": 4, "terrain": terrain,
            "density": 2.0 if name == "Vardun" else 1.0, "language": "pra",
            "identity": "distinct" if name in ("Lisk", "Teth", "Varra") else "shared",
        })
    west = [r["id"] for r in regions if r["position"][0] < 170 and r["id"] != "lisk"]
    return {
        "name": "Poloostrov", "seed": 4417, "end_year": 2000.0,
        "languages": [{
            "id": "pra", "name": "pravardština",
            "consonants": ["p", "t", "k", "kʷ", "b", "d", "ɡ", "s", "h", "m", "n", "r", "l", "w", "j"],
            "vowels": ["a", "e", "i", "o", "u"], "stress": "initial",
        }],
        "regions": regions,
        "events": [
            {"kind": "state", "year": 700, "id": "vard", "regions": west,
             "capital": "vardun", "policy": "promoted", "border": "closed"},
            {"kind": "standard", "year": 1100, "of": "vard"},
            {"kind": "schools", "year": 1600, "of": "vard"},
        ],
    }


CONCEPTS = [
    "water", "fire", "stone", "sun", "moon", "night", "day", "mother", "father", "child", "dog", "fish",
    "bird", "tree", "eye", "ear", "hand", "heart", "blood", "bone", "eat", "drink", "die", "come",
    "big", "small", "black", "white", "cold", "far", "road", "boat", "field", "house", "name", "king",
]


def main(out: str) -> None:
    world, events, _ = build(spec())
    simulation = Simulation(world, events=events)
    forms: dict[str, dict[str, list]] = {}
    langs: list[dict] = []
    step = 0
    for state in simulation.iterate(2000.0):
        step += 1
        if step % 2:
            continue
        w = state.world
        year = round(state.year)
        for gid in w.group_ids():
            group = w.groups[gid]
            if group.written or group.domain != "home":
                continue
            lx = export.lexicon(w, gid)
            row = forms.setdefault(gid, {})
            for concept in CONCEPTS:
                entry = lx.get(concept)
                value = None if entry is None else [entry["form"], entry["loan"], entry["origin"]]
                history = row.setdefault(concept, [])
                if not history or history[-1][1:] != value:
                    history.append([year] + ([None] if value is None else value))
        snaps = state.history.snapshots
        if snaps and (not langs or langs[-1]["year"] != snaps[-1].year):
            langs.append({"year": round(snaps[-1].year),
                          "languages": {k: list(v) for k, v in snaps[-1].languages.items()},
                          "dialects": [list(c) for c in snaps[-1].dialects]})
        print(year, file=sys.stderr, flush=True)
    full = export.export(simulation)
    keep = {k: full[k] for k in ("territories", "groups", "links", "lineages", "states", "borders",
                                 "census", "events", "grammar", "start_year", "year")}
    keep["forms"] = forms
    keep["observed"] = langs
    keep["spec"] = spec()
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(keep, handle, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])

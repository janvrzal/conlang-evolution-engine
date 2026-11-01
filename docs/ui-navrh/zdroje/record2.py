"""Běh pro obrazovku Výsledky: svět z editoru a dějiny z prototypu Dějin.

Proti prototypům přibyl druhý protojazyk na východě, aby výsledky ukázaly
kontakt, přechod k jinému jazyku a obrození.
"""

from __future__ import annotations

import json
import sys

import record
from cee.v2 import export, polity
from cee.v2.simulation import Simulation
from cee.v2.spec import build

EAST = ["pelna", "sorrow", "mirost", "varra", "teth", "ulm"]
CONCEPTS = record.CONCEPTS + ["language", "person", "speak", "we", "good", "mountain", "river", "sea", "forest", "earth", "road", "village"]
WEST = ["vardun", "selm", "orra", "kestrin", "bal", "tumar", "hesk", "ivel", "nask", "ebb"]


def spec() -> dict:
    base = record.spec()
    for region in base["regions"]:
        region["language"] = "vych" if region["id"] in EAST else "pra"
        region["identity"] = "distinct" if region["id"] in ("teth", "varra", "lisk") else "shared"
    base["languages"] = [
        base["languages"][0],
        {"id": "vych", "consonants": ["t", "k", "n", "s", "m", "l", "r", "ʃ", "x", "d", "ɡ", "j", "θ", "z"],
         "vowels": ["a", "i", "u", "ə", "o"], "stress": "final", "grammar": "substrate"},
    ]
    base["events"] = [
        {"kind": "state", "year": 700, "id": "zapad", "regions": WEST, "capital": "vardun", "centralization": "moderate",
         "policy": "promoted", "border": "closed"},
        {"kind": "state", "year": 950, "id": "vychod", "regions": EAST, "capital": "pelna", "centralization": "weak",
         "policy": "tolerant", "border": "normal"},
        {"kind": "standard", "year": 1100, "of": "zapad", "literacy": "elite"},
        {"kind": "lingua_franca", "year": 1200, "source": "vardun", "regions": ["pelna", "sorrow", "mirost", "ulm", "kaar", "corrin"],
         "spread": "common", "nativize": False},
        {"kind": "annexation", "year": 1300, "state": "zapad", "regions": ["kaar", "corrin", "dorn"]},
        {"kind": "secession", "year": 1450, "id": "teth", "regions": ["teth", "varra"], "capital": "teth",
         "centralization": "moderate", "policy": "tolerant", "border": "normal"},
        {"kind": "schools", "year": 1600, "of": "zapad", "coverage": "mass", "printing": True, "diglossic": False},
        {"kind": "preserve", "year": 1600, "regions": ["lisk"], "preserved": True},
        {"kind": "language_policy", "year": 1650, "state": "zapad", "policy": "enforced"},
        {"kind": "revival", "year": 1800, "regions": ["teth", "varra"], "strength": "national"},
        {"kind": "collapse", "year": 1850, "state": "vychod"},
    ]
    return base


def main(out: str) -> None:
    world, events, _ = build(spec())
    simulation = Simulation(world, events=events)
    forms: dict[str, dict[str, list]] = {}
    written: dict[str, dict[str, list]] = {}
    frames: list[dict] = []
    step = 0
    for state in simulation.iterate(2000.0):
        step += 1
        if step % 2:
            continue
        w = state.world
        year = round(state.year)
        for gid in w.group_ids():
            group = w.groups[gid]
            target = written if group.written else forms
            if not group.written and group.domain != "home":
                continue
            lx = export.lexicon(w, gid)
            row = target.setdefault(gid, {})
            for concept in CONCEPTS:
                entry = lx.get(concept)
                value = None if entry is None else [entry["form"], entry["loan"], entry["origin"], entry["language"]]
                history = row.setdefault(concept, [])
                if not history or history[-1][1:] != ([None] if value is None else value):
                    history.append([year] + ([None] if value is None else value))
        snap = state.history.snapshots[-1] if state.history.snapshots else None
        frames.append({
            "year": year,
            "languages": {} if snap is None else {k: list(v) for k, v in snap.languages.items()},
            "dialects": [] if snap is None else [list(c) for c in snap.dialects],
            "census": polity.language_census(w),
            "states": [{"id": s["id"], "regions": s["regions"], "capital": s["capital"]} for s in polity.states(w)],
            "groups": {gid: [w.groups[gid].population, w.groups[gid].main_code.language, w.groups[gid].domain]
                       for gid in w.group_ids() if not w.groups[gid].written},
        })
        print(year, file=sys.stderr, flush=True)
    full = export.export(simulation)
    keep = {k: full[k] for k in ("territories", "groups", "links", "lineages", "events", "grammar", "standards")}
    keep.update(forms=forms, written=written, frames=frames, spec=spec())
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(keep, handle, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])

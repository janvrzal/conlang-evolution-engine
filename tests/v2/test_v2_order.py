"""Výsledek kroku nezávisí na pořadí, v jakém se zpracují skupiny.

Podmínka paralelního běhu po vlastnících skupin (``cee.v2.parallel``):
kroky po skupinách (uplatnění inovací, vstup slov do slovníku, přestavba)
projde ``Simulation.reverse_groups`` pozpátku a stav i množina záznamů
historie musí zůstat stejné.
"""

import json

from cee.v2 import export
from cee.v2.simulation import Simulation
from cee.v2.spec import build

SPEC = {
    "end_year": 400,
    "languages": [{"id": "a"}, {"id": "b", "grammar": "full"}],
    "regions": [
        {"id": "c", "position": [0, 0], "density": 2, "neighbours": ["x"], "language": "a", "villages": 3},
        {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3},
    ],
    "events": [
        {"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c", "policy": "enforced"},
        {"kind": "standard", "year": 100, "of": "k"},
        {"kind": "schools", "year": 150, "of": "k"},
    ],
}


def outcome(reverse):
    world, events, spec = build(SPEC)
    simulation = Simulation(world, events=events)
    simulation.reverse_groups = reverse
    simulation.run(spec.end_year)
    data = export.export(simulation, events=None)
    records = sorted(json.dumps(event, sort_keys=True) for event in data.pop("events"))
    return json.dumps(data, sort_keys=True), records


def test_poradi_skupin_nemeni_vysledek():
    forward, reverse = outcome(False), outcome(True)
    assert forward[1] == reverse[1]
    assert forward[0] == reverse[0]

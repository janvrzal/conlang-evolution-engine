"""Paralelní běh (``cee.v2.parallel``) dá bitově stejný výsledek jako jeden proces."""

import json

from cee.v2 import parallel, runner

SPEC = {
    "end_year": 250,
    "languages": [{"id": "a"}, {"id": "b"}],
    "regions": [
        {"id": "c", "position": [0, 0], "density": 2, "neighbours": ["x"], "language": "a", "villages": 3},
        {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3},
    ],
    "events": [{"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c", "policy": "enforced"}],
    "semantics": False,
}


def test_vlastnik_skupiny_je_stabilni_a_rozlozeny():
    owners = [parallel.owner(f"g{index}", 3) for index in range(300)]
    assert owners == [parallel.owner(f"g{index}", 3) for index in range(300)]
    assert {owners.count(shard) > 60 for shard in range(3)} == {True}


def test_paralelni_beh_je_bitove_stejny():
    run, simulation = runner.prepare("serial", SPEC)
    run.execute(simulation)
    digest, result = parallel.run(SPEC, 2)
    assert digest == simulation.history.digest()
    assert json.dumps(result, sort_keys=True) == json.dumps(run.result, sort_keys=True)

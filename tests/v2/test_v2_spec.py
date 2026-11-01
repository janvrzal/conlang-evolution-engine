"""Popis světa pro UI (``cee.v2.spec``) a běh na pozadí (``cee.v2.runner``)."""

import json
from importlib import resources

import pytest

from cee.v2 import runner
from cee.v2.polity import State
from cee.v2.spec import EVENT_KINDS, SpecError, WorldSpec, build, check, levels


def small(**extra):
    spec = {
        "end_year": 200,
        "languages": [{"id": "a"}, {"id": "b", "grammar": "substrate"}],
        "regions": [
            {"id": "c", "position": [0, 0], "density": 2, "neighbours": ["x"], "language": "a", "villages": 3},
            {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3,
             "terrain": "hills", "identity": "distinct"},
        ],
        "events": [{"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c"}],
        "semantics": False,
    }
    spec.update(extra)
    return spec


def example():
    return json.loads(resources.files("cee.data").joinpath("v2_example_world.json").read_text(encoding="utf-8"))


def test_priklad_sveta_je_platny_a_kazdy_druh_udalosti_ma_schema():
    assert check(example()) == []
    schema = json.dumps(WorldSpec.model_json_schema())
    assert all(f'"{kind}"' in schema for kind in EVENT_KINDS)
    assert levels()["policy_levels"] == ["enforced", "promoted", "tolerant"]


def test_stavba_sveta_z_popisu():
    world, events, spec = build(small())
    assert spec.end_year == 200
    assert world.territories["x"].terrain == "hills"
    assert world.territories["x"].native_language == "b"
    assert len([g for g in world.group_ids() if g.startswith("x-")]) == 3
    assert isinstance(events[0], State)


def test_chyby_maji_cestu_a_ceskou_zpravu():
    spec = small(events=[
        {"kind": "state", "year": 0, "id": "k", "regions": ["c", "x"], "capital": "c", "policy": "brutal"},
        {"kind": "collapse", "year": 50, "state": "nikdo"},
        {"kind": "standard", "year": 900, "of": "k"},
    ])
    issues = {issue.path: issue.message for issue in check(spec)}
    assert "jazyková politika" in issues["events.0"]
    assert "neexistuje" in issues["events.1"]
    assert "mimo" in issues["events.2.year"]
    issues = {issue.path: issue.message for issue in check({"end_year": 10, "languages": [],
                                                            "regions": [{"id": "r", "position": [0, 0], "x": 1}]})}
    assert issues["regions.0.x"] == "neznámé pole"
    assert "aspoň 1" in issues["languages"]
    assert check(small(events=[{"kind": "war", "year": 0}]))[0].message.startswith("neznámý druh události")
    assert check(small(parameters={"nic": 1}))[0].path == "parameters.nic"
    with pytest.raises(SpecError):
        build(small(end_year=-5))


def test_udalosti_se_overi_v_poradi_roku():
    late_state = small(events=[
        {"kind": "collapse", "year": 100, "state": "k"},
        {"kind": "state", "year": 50, "id": "k", "regions": ["c", "x"], "capital": "c"},
    ])
    assert check(late_state) == []


def test_prepis_parametru_se_projevi():
    world, _, _ = build(small(parameters={"capital_prestige": 3.0}))
    assert world.params.capital_prestige == 3.0


def test_beh_dava_snimky_a_export_a_je_deterministicky():
    results = []
    for _ in range(2):
        run, simulation = runner.prepare("test", small())
        run.execute(simulation)
        assert run.status == "done" and run.progress == 1.0
        view = run.status_view(since=1)
        assert view["frame_count"] >= 2 and len(view["frames"]) == view["frame_count"] - 1
        results.append(json.dumps(run.result, sort_keys=True))
    exported = json.loads(results[0])
    assert results[0] == results[1]
    assert exported["states"][0]["id"] == "k"
    assert set(exported["census"]) == {"c", "x"}


def test_zruseny_beh_skonci():
    run, simulation = runner.prepare("test", small(end_year=2000))
    run.cancel()
    run.execute(simulation)
    assert run.status == "cancelled" and run.result is None


def test_autor_muze_zadat_vlastni_slova_protojazyka():
    from cee.v2 import export
    from cee.v2.language.protoforms import protolanguage
    from cee.v2.scenarios import DEFAULT_CONCEPTS
    from cee.v2.simulation import Simulation

    plain, _ = protolanguage(DEFAULT_CONCEPTS, seed=7)
    fixed, _ = protolanguage(DEFAULT_CONCEPTS, seed=7, fixed={"hand": "ruka"})
    assert fixed["hand"] == "ruka"
    assert {c: f for c, f in fixed.items() if c != "hand" and f != "ruka"} == {
        c: f for c, f in plain.items() if c != "hand" and f != "ruka"}
    data = small(languages=[{"id": "a", "words": {"hand": "ruka", "water": "voda"}}, {"id": "b"}])
    world, events, _ = build(data)
    simulation = Simulation(world, events=events)
    simulation.run(25.0)
    lexicon = export.lexicon(simulation.world, "c-v0")
    assert (lexicon["hand"]["form"], lexicon["water"]["form"]) == ("ruka", "voda")


def test_vlastni_slova_se_overi():
    data = small(languages=[{"id": "a", "words": {"xyz": "ka", "fire": "q͡ǂ", "hand": " "}}, {"id": "b"}])
    issues = {issue.path: issue.message for issue in check(data)}
    assert "neznámý pojem" in issues["languages.0.words.xyz"]
    assert "hlásku" in issues["languages.0.words.fire"]
    assert "prázdné" in issues["languages.0.words.hand"]


def test_identita_prichod_cizincu_a_jmena_statu_v_popisu():
    data = small(events=[
        {"kind": "state", "year": 0, "id": "k", "name": "Království", "regions": ["c", "x"], "capital": "c"},
        {"kind": "identity", "year": 50, "regions": ["x"], "identity": "strong"},
        {"kind": "immigration", "year": 60, "regions": ["c"], "immigration": 0.2},
    ])
    assert check(data) == []
    world, events, _ = build(data)
    assert [type(e).__name__ for e in events] == ["State", "Identity", "Immigration"]
    bad = small(events=[{"kind": "immigration", "year": 0, "regions": ["c"], "immigration": 2}])
    assert any(issue.path.startswith("events.0") for issue in check(bad))

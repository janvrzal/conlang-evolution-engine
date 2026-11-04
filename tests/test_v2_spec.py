"""Popis světa pro UI (``cee.v2.spec``): schéma, validace polí, přepisy parametrů a ověření v Rustu.

Sémantiku (neznámé státy a regiony, slova, slovník) ověřuje Rust (``cee_engine_py.check_spec``,
testy též v ``rust/cee_engine/tests/spec_check.rs``); sestavená vazba je potřeba, bez ní se
modul přeskočí (``rust/README.md``).
"""

import json
from importlib import resources

import pytest

from cee.v2 import runner
from cee.v2.spec import (
    EVENT_KINDS,
    SpecError,
    WorldSpec,
    errors,
    levels,
    parse,
    vocabulary_options,
    warnings,
)

try:
    binding = runner.native()
except ImportError:
    pytest.skip("vazba cee_engine_py není sestavená (rust/README.md)", allow_module_level=True)

check = runner.check


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
    options = vocabulary_options(binding.vocabulary_max_size())
    assert options["default"] == 149 and options["max"] > 1000 and 200 in options["presets"]


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
    spec, issues = parse(small(end_year=-5))
    assert spec is None and issues


def test_prepisy_parametru_se_overi_podle_souboru():
    def issues(**parameters):
        return [(item.path, item.message) for item in check(small(parameters=parameters))]

    assert issues(capital_prestige=3.0, border_levels={"open": 1.0, "normal": 0.5, "closed": 0.1, "wall": 0.0}) == []
    assert issues(nic=1) == [("parameters.nic", "neznámý parametr")]
    assert issues(capital_prestige="x") == [("parameters.capital_prestige", "očekáváno číslo")]
    assert issues(border_levels=2)[0][0] == "parameters.border_levels"
    assert issues(channel_domains={"trade": {"power": -1}})[0][0] == "parameters.channel_domains.trade.power"
    assert issues(channel_domains={"trade": {"nic": 1}})[0][0] == "parameters.channel_domains.trade.nic"


def test_udalosti_se_overi_v_poradi_roku():
    late_state = small(events=[
        {"kind": "collapse", "year": 100, "state": "k"},
        {"kind": "state", "year": 50, "id": "k", "regions": ["c", "x"], "capital": "c"},
    ])
    assert check(late_state) == []


def test_vlastni_slova_se_overi():
    data = small(languages=[{"id": "a", "words": {"xyz": "ka", "fire": "ʬ", "hand": " ", "eye": "kʷá",
                                                   "ear": "ɐɾʡ"}}, {"id": "b"}])
    issues = {issue.path: issue.message for issue in check(data)}
    assert "neznámý pojem" in issues["languages.0.words.xyz"]
    assert "hlásku" in issues["languages.0.words.fire"]
    assert "prázdné" in issues["languages.0.words.hand"]
    # tón diakritikou a hlásky, které PanPhon slévá, projdou
    assert "languages.0.words.eye" not in issues and "languages.0.words.ear" not in issues


def test_varovani_nezastavi_beh():
    found = check(small(vocabulary=200))
    assert not errors(found) and [issue.path for issue in warnings(found)] == ["vocabulary"]
    assert [issue.path for issue in errors(check(small(vocabulary=200, background="zzz")))] == ["background"]


def test_identita_prichod_cizincu_a_jmena_statu_v_popisu():
    data = small(events=[
        {"kind": "state", "year": 0, "id": "k", "name": "Království", "regions": ["c", "x"], "capital": "c"},
        {"kind": "identity", "year": 50, "regions": ["x"], "identity": "strong"},
        {"kind": "immigration", "year": 60, "regions": ["c"], "immigration": 0.2},
    ])
    assert check(data) == []
    bad = small(events=[{"kind": "immigration", "year": 0, "regions": ["c"], "immigration": 2}])
    assert any(issue.path.startswith("events.0") for issue in check(bad))


def test_beh_dava_snimky_a_export_a_je_deterministicky():
    results = []
    for _ in range(2):
        run = runner.prepare("test", small())
        run.execute()
        assert run.status == "done" and run.progress == 1.0
        view = run.status_view(since=1)
        assert view["frame_count"] >= 2 and len(view["frames"]) == view["frame_count"] - 1
        results.append(json.dumps(run.result, sort_keys=True))
    exported = json.loads(results[0])
    assert results[0] == results[1]
    assert exported["states"][0]["id"] == "k"
    assert set(exported["census"]) == {"c", "x"}


def test_zruseny_beh_skonci_a_neplatny_popis_vyhodi_chybu():
    run = runner.prepare("test", small(end_year=2000))
    run.cancel()
    run.execute()
    assert run.status == "cancelled" and run.result is None
    with pytest.raises(SpecError) as error:
        runner.prepare("test", small(regions=[]))
    assert error.value.issues[0].path == "regions"

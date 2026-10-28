"""Pozorování a export enginu v2 (milník M6c)."""

import json

import numpy as np

from cee.v2.events import Contact
from cee.v2.export import FORMAT, TIMELINE, export, lineages
from cee.v2.observe import (
    LineageTracker,
    _with_hysteresis,
    code_distances,
    cognate_matrix,
    distance_matrix,
    form_distance,
)
from cee.v2.scenarios import Language, Place, contact_world, village_grid
from cee.v2.simulation import Simulation


def test_vzdalenost_tvaru_je_vazena_rysy():
    world = village_grid(1, seed=1, phonology=True)
    parse = world.table.parse
    assert form_distance(world, parse("kata"), parse("kata")) == 0.0
    voiced = form_distance(world, parse("kata"), parse("kada"))
    vowel = form_distance(world, parse("kata"), parse("kaaa"))
    assert 0 < voiced < vowel <= 1.0
    assert form_distance(world, parse("ka"), ()) == 1.0


def test_pribuzna_slova_pridaji_vzdalenost_jen_podle_tvaru():
    world = village_grid(2, seed=1, phonology=True)
    Simulation(world)
    first, second = (world.groups[group].main_code for group in world.group_ids())
    assert not cognate_matrix(world, world.group_ids()).any()
    root = first.phonology.dominant["water"]
    from cee.v2.language.lexicon import UnitForm

    second.forms.set(root, UnitForm(world.form_of(first, root) + (world.table.id_of("s"),), None, None))
    matrix = cognate_matrix(world, world.group_ids())
    assert matrix[0, 1] == matrix[1, 0] > 0


def test_svet_bez_tvaru_ma_vzdalenost_jen_ze_slov():
    world = village_grid(3, seed=1)
    Simulation(world).run(500)
    assert np.array_equal(code_distances(world), distance_matrix(world))


def test_hystereze_drzi_spojene_a_oddelene_skupiny():
    tracker = LineageTracker()
    tracker.update([["a", "b"], ["c"]], 0)
    distances = np.full((3, 3), 0.3)
    np.fill_diagonal(distances, 0.0)
    adjusted = _with_hysteresis(distances, ["a", "b", "c"], tracker, 0.05)
    assert adjusted[0, 1] == 0.25 and adjusted[0, 2] == 0.35 and adjusted[0, 0] == 0.0


def test_export_je_json_se_slovnikem_puvodem_a_stromem():
    world = contact_world([
        Language("a", (Place("a0", (0.0, 0.0)),)),
        Language("b", (Place("b0", (10.0, 0.0)),)),
    ], seed=1)
    simulation = Simulation(world, events=[Contact(100.0, (("a0", "b0"),), 0.8)])
    simulation.run(1500)
    data = json.loads(json.dumps(export(simulation), ensure_ascii=False))
    assert data["format"] == FORMAT and data["year"] == 1500.0
    assert {group["id"] for group in data["groups"]} == {"a0", "b0"}
    assert data["groups"][0]["code_language"] == "a"
    entry = data["lexicon"]["a0"]["water"]
    assert entry["form"] and entry["origin"] and entry["language"] in ("a", "b")
    assert any(item["loan"] for item in data["lexicon"]["a0"].values())
    assert data["grammar"]["a0"]["NEG"]["kind"]
    assert {event["kind"] for event in data["events"]} <= TIMELINE
    assert {item["id"] for item in data["lineages"]} >= set(data["snapshots"][-1]["languages"])
    assert lineages(simulation) == data["lineages"]

"""Pozorování a export enginu v2 (milník M6c)."""

import json

import numpy as np

from cee.v2.events import Contact
from cee.v2.export import FORMAT, TIMELINE, export, lineages
from cee.v2 import observe as observation
from cee.v2.observe import (
    _candidates,
    _gather,
    _geometry,
    code_distances,
    cognate_matrix,
    constrained_average_linkage,
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


def _features(world, group_ids):
    """Rysy mluvených skupin ``group_ids`` (Python reference nad poli, která dostává i Rust)."""
    columns = np.array([world.live.group_index[group_id] for group_id in group_ids], dtype=np.int64)
    return observation._features(_gather(world, columns))


def _linkage(world, group_ids, threshold, features, labels=None, margin=0.0):
    """Průměrná vazba mluvených skupin s kandidáty z vazeb a map."""
    pairs = _candidates(*_geometry(world, group_ids))
    return constrained_average_linkage(features, pairs, threshold, labels=labels, margin=margin)


def _pairwise(features, first, second):
    """Vzdálenost dvou skupin z vložení (jako ve shlukování), počítaná přímo."""
    shares = features.shares
    categorical = 0.5 * float(((shares[first] - shares[second]) ** 2).sum())
    forms = sum(weight * features.forms[second].get(column, 0.0) for column, weight in features.spread[first].items())
    return (categorical + forms) / features.lexical


def _diverged(columns=4, years=1500):
    world = village_grid(columns, 2, seed=1, syntax=True, semantics=True)
    Simulation(world).run(years)
    return world


def test_vlozeni_dava_temer_stejnou_vzdalenost_jako_vsechny_dvojice():
    world = _diverged()
    ids = list(world.live.group_ids)
    exact = code_distances(world)
    features = _features(world, ids)
    upper = np.triu_indices(len(ids), 1)
    approx = np.array([[_pairwise(features, a, b) for b in range(len(ids))] for a in range(len(ids))])
    assert np.corrcoef(exact[upper], approx[upper])[0, 1] > 0.99
    assert 0.85 < approx[upper].mean() / exact[upper].mean() <= 1.0


def test_vazba_shluku_ze_souctu_je_prumer_vsech_dvojic():
    world = _diverged()
    ids = list(world.live.group_ids)
    features = _features(world, ids)
    first, second = list(range(0, len(ids), 2)), list(range(1, len(ids), 2))
    brute = np.mean([_pairwise(features, a, b) for a in first for b in second])
    shares, squares = features.shares, features.squares
    na, nb = len(first), len(second)
    total = (0.5 * (squares[first].sum() / na + squares[second].sum() / nb)
             - float(shares[first].sum(axis=0) @ shares[second].sum(axis=0)) / (na * nb))
    spread = {}
    for a in first:
        for column, weight in features.spread[a].items():
            spread[column] = spread.get(column, 0.0) + weight
    forms = {}
    for b in second:
        for column, weight in features.forms[b].items():
            forms[column] = forms.get(column, 0.0) + weight
    total += sum(weight * forms.get(column, 0.0) for column, weight in spread.items()) / (na * nb)
    assert abs(total / features.lexical - brute) < 1e-6  # vložení je ve float32
    assert _linkage(world, ids, 0.0, features) == [[index] for index in range(len(ids))]
    assert _linkage(world, ids, 10.0, features) == [list(range(len(ids)))]


def test_hystereze_drzi_spojene_a_oddelene_skupiny():
    world = _diverged(columns=2, years=1000)
    ids = list(world.live.group_ids)
    features = _features(world, ids)
    distance = _pairwise(features, 0, 1)
    together = _linkage(world, ids[:2], distance - 0.01, _features(world, ids[:2]), labels=[0, 0], margin=0.02)
    apart = _linkage(world, ids[:2], distance + 0.01, _features(world, ids[:2]), labels=[0, 1], margin=0.02)
    assert together == [[0, 1]] and apart == [[0], [1]]


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

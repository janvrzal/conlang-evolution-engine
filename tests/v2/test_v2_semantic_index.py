"""Sémantická místa odpovídají úplnému sestavení včetně pořadí."""

import copy
import struct
from dataclasses import replace
from unittest.mock import patch

import numpy as np

from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import LEXICAL_CHANGES, SemanticChange
from cee.v2.scenarios import village_grid
from cee.v2.semantics import ConceptGraph, Relation
from cee.v2.simulation import Simulation


def _context(world):
    group = world.groups[world.group_ids()[0]]
    return InnovationContext(world, group, group.main_code, 0, 0.0)


def _compare(context):
    for change in LEXICAL_CHANGES:
        if not isinstance(change, SemanticChange):
            continue
        actual = change._sites(context)
        expected = change._sites_reference(context)
        assert actual == expected
        sites = sorted(expected)
        assert list(change.sites(context)) == sites
        expected_rates = [change.base_rate * sum(weight for weight, _ in expected[site]) for site in sites]
        assert [struct.pack("d", rate) for rate in change.rates(context, sites)] == [
            struct.pack("d", rate) for rate in expected_rates
        ]
        for site in sites:
            weights = np.array([weight for weight, _ in expected[site]])
            a = np.random.default_rng(17)
            b = np.random.default_rng(17)
            assert a.choice(len(actual[site]), p=weights / weights.sum()) == b.choice(
                len(expected[site]), p=weights / weights.sum()
            )
        if sites:
            left, right = copy.deepcopy(context.world), copy.deepcopy(context.world)
            candidate = change.propose(_context(left), sites[0], np.random.default_rng(23), 0)
            with patch.object(type(change), "_sites", SemanticChange._sites_reference):
                reference = change.propose(_context(right), sites[0], np.random.default_rng(23), 0)
            assert candidate == reference


def test_shoda_po_zmenach_dominance_a_checkpointu():
    world = village_grid(1, seed=6, semantics=True, taboo=("fire",))
    simulation = Simulation(world)
    context = _context(world)
    _compare(context)
    state = context.code.phonology
    concepts = list(state.dominant)[:4]
    root = state.dominant[concepts[0]]
    state.set_dominant(concepts[1], root)
    state.lexicon_version += 1
    _compare(context)
    state.set_dominant(concepts[0], None)
    state.lexicon_version += 1
    _compare(context)
    resumed = Simulation.resume(simulation.checkpoint()).world
    _compare(_context(resumed))
    resumed_state = _context(resumed).code.phonology
    resumed_state.set_dominant(concepts[2], root)
    resumed_state.lexicon_version += 1
    _compare(_context(resumed))
    _compare(context)


def test_zmena_konfigurace_se_projevi_az_po_zmene_verze():
    world = village_grid(1, seed=7, semantics=True)
    Simulation(world)
    context = _context(world)
    _compare(context)
    before = {change.kind: copy.deepcopy(change._sites(context)) for change in LEXICAL_CHANGES
              if isinstance(change, SemanticChange)}
    world.derivational_suffix = ()
    world.concept_classes[next(iter(world.concept_classes))] = "different"
    assert all(change._sites(context) == before[change.kind] for change in LEXICAL_CHANGES
               if isinstance(change, SemanticChange))
    context.code.phonology.lexicon_version += 1
    _compare(context)


def test_duplicitni_vztahy_slozenina_a_vymena_odvozenin():
    world = village_grid(1, seed=3, semantics=True)
    Simulation(world)
    context = _context(world)
    state = context.code.phonology
    source, target, base_a, base_b = list(state.dominant)[:4]
    old_root, new_root = state.dominant[source], state.dominant[target]
    world.morphemes[old_root] = replace(world.morphemes[old_root], etymology="derivation",
                                        sources=(base_a,), base=state.dominant[base_a])
    world.morphemes[new_root] = replace(world.morphemes[new_root], etymology="derivation",
                                        sources=(base_b,), base=state.dominant[base_b])
    world.semantics = ConceptGraph(
        (Relation(source, target, polysemy=2), Relation(source, target, polysemy=3)),
        {base_a: ((source, source), (source, target))},
    )
    _compare(context)
    shift = next(change for change in LEXICAL_CHANGES if change.kind == "semantic_shift")
    assert len(shift._sites(context).get("lexical:" + target, ())) == 2
    state.set_dominant(source, new_root)
    state.lexicon_version += 1
    _compare(context)

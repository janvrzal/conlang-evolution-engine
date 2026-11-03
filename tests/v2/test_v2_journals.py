from __future__ import annotations

from copy import deepcopy

import pytest

import cee.v2.simulation as simulation_module
from cee.v2 import morphology, phonology, syntax
from cee.v2.history import History
from cee.v2.language.constructions import Construction
from cee.v2.language.journal import FrequencyMap
from cee.v2.language.lexicon import PhonologyState
from cee.v2.language.morphology import FormChange
from cee.v2.language.processes import Process
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from cee.v2.world import World


def test_state_journals_record_dominance_polysemy_and_usage_changes() -> None:
    state = PhonologyState()

    state.set_dominant("water", "root-shared")
    state.adjust_uses("root-shared", 1)
    state.set_dominant("fire", "root-shared")
    state.adjust_uses("root-shared", 1)
    state.set_dominant("water", None)
    state.adjust_uses("root-shared", -1)
    state.set_dominant("water", "root-new")
    state.adjust_uses("root-new", 1)

    assert state.dominant_log == [
        ("water", None, "root-shared"),
        ("fire", None, "root-shared"),
        ("water", "root-shared", None),
        ("water", None, "root-new"),
    ]
    assert state.usage_log == [
        ("root-shared", 0, 1),
        ("root-shared", 1, 2),
        ("root-shared", 2, 1),
        ("root-new", 0, 1),
    ]
    assert state.uses == {"root-shared": 1, "root-new": 1}


def test_seed_vocabulary_logs_match_seeded_state() -> None:
    world = village_grid(1, seed=11, concepts=("water", "fire"), phonology=True)
    simulation = Simulation(world)
    state = world.groups["v00-00"].main_code.phonology

    assert len(state.dominant_log) == 2
    assert all(old is None for _, old, _ in state.dominant_log)
    assert {concept for concept, _, _ in state.dominant_log} == {"water", "fire"}
    assert {root for _, _, root in state.dominant_log} == set(state.uses)
    assert {unit for action, unit in state.vocabulary_log if action == "enter"} == state.vocabulary
    assert all(action == "enter" for action, _ in state.vocabulary_log)
    last_root, _, last_count = state.usage_log[-1]
    assert state.uses[last_root] == last_count
    assert simulation.world is world


def test_vocabulary_enter_leave_are_logged_once() -> None:
    world = village_grid(1, seed=3, concepts=("water",), phonology=True)
    code = world.groups["v00-00"].main_code
    unit = next(iter(world.morphemes))
    code.phonology = PhonologyState()

    phonology.enter_vocabulary(world, code, unit)
    phonology.enter_vocabulary(world, code, unit)
    phonology.leave_vocabulary(code, unit)
    phonology.leave_vocabulary(code, unit)

    assert code.phonology.vocabulary_log == [("enter", unit), ("leave", unit)]
    assert unit not in code.phonology.vocabulary


def test_lifecycle_and_grammar_journals_branch_as_independent_prefixes() -> None:
    state = PhonologyState()
    state.record_lifecycle("process", "activate", "process:x")
    state.record_lifecycle("form", "remove", "form:y")
    state.record_grammar("construction:PAST")
    assert state.mark_grammar_applied("variant:past")
    assert not state.mark_grammar_applied("variant:past")

    branch = state.branch()
    assert branch.lifecycle_log == state.lifecycle_log
    assert branch.grammar_log == state.grammar_log
    assert branch.grammar_applied_log == state.grammar_applied_log
    assert branch.lifecycle_log is not state.lifecycle_log
    assert branch.grammar_log is not state.grammar_log
    branch.record_lifecycle("process", "close", "process:x")
    branch.record_grammar("construction:PL")
    assert len(branch.lifecycle_log) == len(state.lifecycle_log) + 1
    assert len(branch.grammar_log) == len(state.grammar_log) + 1


def test_frequency_map_tracks_mutations_and_deepcopy_without_fake_entries() -> None:
    defaults = FrequencyMap()
    assert defaults.setdefault("unspecified") is None
    assert defaults.log == ["unspecified"]

    frequencies = FrequencyMap({"water": 0.8, "fire": 0.4})
    assert frequencies.version == 0
    assert frequencies.log == []

    frequencies["water"] = 0.8  # stejná hodnota není změna
    frequencies["water"] = 0.7
    frequencies.update({"fire": 0.4, "earth": 0.2})
    frequencies.setdefault("earth", 1.0)
    frequencies.setdefault("air", 0.3)
    frequencies.pop("missing", None)
    frequencies.pop("air")
    frequencies |= {"water": 0.6}
    frequencies.popitem()  # earth, poslední vložený klíč

    assert frequencies.log == ["water", "earth", "air", "air", "water", "earth"]
    assert frequencies.version == len(frequencies.log)
    copied = deepcopy(frequencies)
    assert copied == frequencies
    assert copied.version == frequencies.version
    assert copied.log == frequencies.log
    assert copied.log is not frequencies.log
    copied["water"] = 0.5
    assert frequencies["water"] == 0.6
    assert len(copied.log) == len(frequencies.log) + 1

    frequencies.clear()
    assert frequencies.log[-1] == "fire"
    assert frequencies.version == len(frequencies.log)


def test_world_wraps_initial_plain_frequency_mapping() -> None:
    supplied = {"water": 0.8, "fire": 0.4}
    world = World(seed=1, concept_frequencies=supplied)
    assert isinstance(world.concept_frequencies, FrequencyMap)
    assert list(world.concept_frequencies.items()) == list(supplied.items())
    assert world.concept_frequencies.version == 0
    assert world.concept_frequencies.log == []


def test_process_and_form_lifecycle_transitions_are_journaled() -> None:
    world = village_grid(1, seed=7, concepts=("water",), phonology=True)
    simulation = Simulation(world)
    group_id = "v00-00"
    code = world.groups[group_id].main_code
    state = code.phonology
    assert world.table is not None

    process = Process("test", world.table.VOWEL, "replace", segment=world.table.id_of("a"))
    process_id, _ = phonology.register(world, process, Origin("test", 0, 0.0, group_id))
    phonology.activate(world, code, process_id)
    code.repertoire.set(process_id, Distribution.fixed(phonology.changed_id(process_id)))
    state.set_fixed_since(process_id, 0)
    phonology.restructure(world, group_id, 3, 25.0, History(), 75.0)
    assert ("process", "activate", process_id) in state.lifecycle_log
    assert ("process", "close", process_id) in state.lifecycle_log

    root = next(iter(world.morphemes))
    change = FormChange("level", root)
    form_id, _ = morphology.register(world, change, Origin("analogy", 0, 0.0, group_id))
    morphology.activate(world, code, form_id)
    morphology.restructure(world, group_id, 4, History(), 100.0)
    morphology.activate(world, code, form_id)
    code.repertoire.set(form_id, Distribution.fixed(phonology.changed_id(form_id)))
    morphology.restructure(world, group_id, 5, History(), 125.0)
    assert ("form", "activate", form_id) in state.lifecycle_log
    assert ("form", "remove", form_id) in state.lifecycle_log
    assert ("form", "close", form_id) in state.lifecycle_log
    assert simulation.world is world


def test_syntax_restructure_journals_the_applied_construction_variant() -> None:
    world = village_grid(1, seed=5, syntax=True)
    Simulation(world)
    state = world.groups["v00-00"].main_code.phonology
    code = world.groups["v00-00"].main_code
    exponent = next(iter(world.morphemes))
    variable, applied_variant = syntax.register(
        world, Construction("PAST", "synthetic", "finish", exponent=exponent),
        Origin("test", 0, 0.0, "v00-00"),
    )
    code.repertoire.set(variable, Distribution.fixed(applied_variant.id))
    state.grammar_applied.clear()
    history = History()

    syntax.restructure(world, "v00-00", 1, history, 25.0)

    expected = set()
    for entry in syntax.functions(world, "inflection"):
        distribution = world.distribution("v00-00", syntax.variable_id(entry.id))
        if distribution is None:
            continue
        dominant_variant, share = distribution.dominant()
        construction = syntax.construction_of(world, dominant_variant)
        if (share >= world.params.grammar_threshold and construction.kind == "synthetic"
                and construction.exponent is not None):
            expected.add(dominant_variant)
    assert state.grammar_applied_log
    assert set(state.grammar_applied_log) <= expected


def test_transmit_journals_only_changed_construction_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = village_grid(2, seed=13, syntax=True)
    variable_id = "construction:test-journal"
    world.variables[variable_id] = Variable("construction", "test-journal")
    variants = (
        Variant("variant:test-a", variable_id, {}, Origin(None, 0, 0.0, None)),
        Variant("variant:test-b", variable_id, {}, Origin(None, 0, 0.0, None)),
    )
    for variant in variants:
        world.variants[variant.id] = variant
    groups = world.group_ids()
    world.groups[groups[0]].main_code.repertoire.set(
        variable_id, Distribution.fixed(variants[0].id)
    )
    world.groups[groups[1]].main_code.repertoire.set(
        variable_id, Distribution.fixed(variants[1].id)
    )
    simulation = Simulation(world)
    assert variable_id in world.live

    def fake_transmit(world_arg, block, inputs, pressures, params):
        updated = block.freqs.copy()
        if variable_id not in block.variable_ids:
            return updated, block.previous.copy()
        row = block.row_of(variable_id)
        first_slot = block.slots[row].index(variants[0].id)
        second_slot = block.slots[row].index(variants[1].id)
        updated[row, 0] = 0.0
        updated[row, 0, first_slot] = 0.7
        updated[row, 0, second_slot] = 0.3
        return updated, block.previous.copy()

    monkeypatch.setattr(simulation_module, "transmit", fake_transmit)
    simulation._transmit(25.0)

    assert world.groups[groups[0]].main_code.phonology.grammar_log == [variable_id]
    assert world.groups[groups[1]].main_code.phonology.grammar_log == []

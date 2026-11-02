"""Číselné struktury stavu kódu (krok A3) proti dřívějším množinám a slovníkům."""

import bisect
import random

from cee.v2.language.columns import DominantMap, MorphemeCounts, MorphemeSet, ProcessQueue
from cee.v2.language.lexicon import PhonologyState
from cee.v2.registry import Registry
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_mnozina_morfemu_se_chova_jako_set():
    rng = random.Random(1)
    registry = Registry()
    names = [f"m{i}" for i in range(30)]
    flags, reference = MorphemeSet(registry.morphemes), set()
    for _ in range(500):
        name = rng.choice(names)
        if rng.random() < 0.55:
            flags.add(name)
            reference.add(name)
        else:
            flags.discard(name)
            reference.discard(name)
        assert (name in flags) == (name in reference)
        assert len(flags) == len(reference) and bool(flags) == bool(reference)
    assert sorted(flags) == sorted(reference) and flags == reference
    other = set(rng.sample(names, 10))
    assert flags - other == reference - other and flags & other == reference & other
    assert other - flags == other - reference and flags | other == reference | other
    assert "neznamy" not in flags and "neznamy" not in registry.morphemes


def test_dominantni_mapa_se_chova_jako_slovnik_vcetne_poradi():
    rng = random.Random(2)
    registry = Registry()
    concepts, roots = [f"c{i}" for i in range(12)], [f"r{i}" for i in range(7)]
    mapping, reference = DominantMap(registry.concepts, registry.morphemes), {}
    for _ in range(600):
        concept = rng.choice(concepts)
        action = rng.random()
        if action < 0.5:
            root = rng.choice(roots)
            mapping[concept] = root
            reference[concept] = root
        elif action < 0.8:
            assert mapping.pop(concept, None) == reference.pop(concept, None)
        elif action < 0.9 and concept in reference:
            del mapping[concept]
            del reference[concept]
        assert mapping.get(concept) == reference.get(concept)
        assert (concept in mapping) == (concept in reference)
        assert list(mapping.items()) == list(reference.items())
        assert list(mapping) == list(reference) and list(mapping.values()) == list(reference.values())
        assert len(mapping) == len(reference)
    assert mapping == reference and mapping.copy() == reference
    assert mapping.keys() - {"c1"} == reference.keys() - {"c1"}


def test_pocty_uziti_se_chovaji_jako_slovnik_s_kladnymi_hodnotami():
    rng = random.Random(3)
    registry = Registry()
    counts, reference = MorphemeCounts(registry.morphemes), {}
    for _ in range(400):
        name, value = f"m{rng.randrange(9)}", rng.randrange(-1, 4)
        counts[name] = value
        if value > 0:
            reference[name] = value
        else:
            reference.pop(name, None)
        assert counts.get(name) == reference.get(name) and len(counts) == len(reference)
    assert counts == reference


def test_fronta_seradi_stejne_jako_vkladani_dvojic_vcetne_shodnych_logitu():
    rng = random.Random(4)
    registry = Registry()
    queue, reference = ProcessQueue(registry.morphemes), []
    names = [f"morpheme:{rng.randrange(10**6):06d}" for _ in range(200)]
    for name in names:
        # Málo různých logitů, aby se často řadilo podle řetězce.
        needed = rng.choice([-1.5, -0.5, 0.0, 0.5, 2.0])
        queue.insert(needed, name)
        bisect.insort(reference, (needed, name))
        if rng.random() < 0.2:
            assert registry.morphemes.name(queue.pop_first()) == reference.pop(0)[1]
    assert queue == reference and queue.pairs() == reference
    rebuilt = ProcessQueue(registry.morphemes, reversed(reference))
    assert rebuilt == queue and rebuilt.names() == [name for _, name in reference]


def test_vetev_stavu_sdili_registr_ale_ne_pole():
    state = PhonologyState()
    state.set_dominant("water", "root-1")
    state.adjust_uses("root-1", 1)
    state.enter_vocabulary("root-1")
    state.pending["p"] = [(0.5, "root-1")]
    child = state.branch()
    assert child.registry is state.registry
    child.set_dominant("fire", "root-2")
    child.adjust_uses("root-1", 1)
    child.vocabulary.add("root-2")
    child.pending["p"].insert(0.1, "root-2")
    assert "fire" not in state.dominant and state.uses_of("root-1") == 1
    assert "root-2" not in state.vocabulary and len(state.pending["p"]) == 1
    assert child.dominant["water"] == "root-1" and child.uses_of("root-1") == 2


def test_pripojeni_stavu_ke_svetu_prenese_obsah_podle_jmen():
    state = PhonologyState()
    state.set_dominant("water", "root-1")
    state.adjust_uses("root-1", 2)
    state.enter_vocabulary("root-1")
    state.pending["p"] = [(0.5, "root-1"), (0.7, "root-0")]
    state.queued["p"] = state.morpheme_set(["root-1", "root-0"])
    world = village_grid(1, seed=1, phonology=True)
    state.bind(world.registry)
    assert state.registry is world.registry and dict(state.dominant) == {"water": "root-1"}
    assert state.uses_of("root-1") == 2 and "root-1" in state.vocabulary
    assert state.pending["p"] == [(0.5, "root-1"), (0.7, "root-0")]
    assert state.queued["p"] == {"root-1", "root-0"}
    assert "root-1" in world.registry.morphemes


def test_stav_kodu_ve_svete_odpovida_dominantnim_variantam():
    world = village_grid(3, seed=2, morphology=True, semantics=True)
    Simulation(world).run(600)
    code = world.groups[world.group_ids()[0]].main_code
    state = code.phonology
    assert state.registry is world.registry
    from collections import Counter

    assert Counter(state.dominant.values()) == Counter(dict(state.uses.items()))
    assert all(root in state.vocabulary for root in state.dominant.values())
    for process, queue in state.pending.items():
        assert set(queue.names()) == set(state.queued[process])

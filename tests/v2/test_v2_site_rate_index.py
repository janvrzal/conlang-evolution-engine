"""Testy indexu míst s mírami a součty (fáze 5, krok 2)."""

from __future__ import annotations

from typing import cast

import numpy as np

from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import (
    BackFormation,
    Compounding,
    Contamination,
    Conversion,
    Derivation,
    LexicalCoinage,
    SemanticChange,
    SemanticShift,
    TabooReplacement,
)
from cee.v2.changes.morphology import Extension, Leveling
from cee.v2.language.morphology_index import MorphologyCandidateIndex
from cee.v2.language.semantic_index import SemanticSitesIndex
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def test_continuous_equals_from_scratch_each_step() -> None:
    """Průběžně = od nuly po každém kroku delšího běhu.

    Ověřuje, že sites, rates i total_rate indexovaných rodin přesně odpovídají
    referenčnímu výpočtu z čistého stavu bez keše.
    """
    world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
    sim = Simulation(world)

    indexed_changes = [
        LexicalCoinage(),
        SemanticShift(),
        Conversion(),
        Derivation(),
        Compounding(),
        TabooReplacement(),
        Contamination(),
        BackFormation(),
        Extension(),
        Leveling(),
    ]

    # Běžíme 500 let (20 kroků) a kontrolujeme každý krok pro všechny skupiny
    for _ in sim.iterate(500):
        for group in sim.world.groups.values():
            if group.written:
                continue
            context = InnovationContext(sim.world, group, group.main_code, sim.tick, sim.year)
            for change in indexed_changes:
                total_rate = change.total_rate(context)
                sites = change.sites(context)
                rates = change.rates(context, sites)

                if isinstance(change, SemanticChange):
                    ref_dict = change._sites_reference(context)
                    ref_sites = sorted(ref_dict)
                    ref_rates = [
                        change.base_rate * sum(weight for weight, _ in ref_dict[s])
                        for s in ref_sites
                    ]
                    assert list(sites) == ref_sites
                    if ref_rates:
                        assert np.allclose(rates, ref_rates, rtol=0.0, atol=1e-12)
                        assert abs(total_rate - sum(ref_rates)) <= 1e-12
                    else:
                        assert list(rates) == []
                        assert total_rate == 0.0

                    # weighted_sites ověření
                    ws_sites, ws_weights = change.weighted_sites(context)
                    assert list(ws_sites) == list(sites)
                    if ref_rates and total_rate > 0.0:
                        assert ws_weights is not None
                        np.testing.assert_allclose(ws_weights, np.array(rates) / total_rate)
                    else:
                        assert ws_weights is None
                elif isinstance(change, (Extension, Leveling)):
                    ref_dict = change.candidates(context)
                    ref_sites = sorted(ref_dict)
                    assert list(sites) == ref_sites
                    ref_total = float(
                        change.base_rate * len(ref_sites) * change.rate_scale(context)
                    ) if ref_sites else 0.0
                    assert abs(total_rate - ref_total) <= 1e-12
                    ws_sites, ws_weights = change.weighted_sites(context)
                    assert list(ws_sites) == list(sites)
                    assert ws_weights is None  # uniform rate
                elif isinstance(change, LexicalCoinage):
                    ref_sites = list(context.code.repertoire.variable_ids_of("lexical"))
                    assert list(sites) == ref_sites
                    ref_total = float(
                        change.base_rate * len(ref_sites) * change.rate_scale(context)
                    ) if ref_sites else 0.0
                    assert abs(total_rate - ref_total) <= 1e-12
                    ws_sites, ws_weights = change.weighted_sites(context)
                    assert list(ws_sites) == ref_sites
                    assert ws_weights is None  # uniform rate


def test_incremental_dirty_concept_update() -> None:
    """Inkrementálnost: změna jednoho dominantního kořene přepočítá jen dotčené pojmy."""
    world = village_grid(2, seed=1, phonology=True, semantics=True)
    sim = Simulation(world)
    group = world.groups[world.group_ids()[0]]
    context = InnovationContext(world, group, group.main_code, sim.tick, sim.year)

    shift = SemanticShift()
    # První volání naplní index
    initial_total = shift.total_rate(context)
    assert initial_total > 0.0

    # Počítadlo volání options
    options_calls: list[str] = []
    real_options = shift.options

    def counting_options(ctx: InnovationContext, concept: str) -> list[tuple[float, dict[str, object]]]:
        options_calls.append(concept)
        return real_options(ctx, concept)

    shift.options = counting_options  # type: ignore[method-assign]

    # Dotaz při nezměněné verzi nesmí options vůbec volat (O(1))
    same_total = shift.total_rate(context)
    assert same_total == initial_total
    assert len(options_calls) == 0

    # Změna dominantního kořene jednoho pojmu
    state = group.main_code.phonology
    concept_to_change = "water" if "water" in state.dominant else next(iter(state.dominant))
    old_root = state.dominant[concept_to_change]
    state.dominant[concept_to_change] = "morpheme:dummy_test_root"
    state.dominant_log.append(("change", concept_to_change, old_root, "morpheme:dummy_test_root"))
    state.lexicon_version += 1

    # Dotaz po změně jednoho pojmu
    new_total = shift.total_rate(context)
    assert new_total >= 0.0
    # Muselo dojít k přepočtu dotčených pojmů, ale rozhodně ne všech ~150
    assert 0 < len(options_calls) < 25

    # Další dotaz se stejnou verzí opět nevolá nic
    options_calls.clear()
    assert shift.total_rate(context) == new_total
    assert len(options_calls) == 0


def test_checkpoint_isolation_and_resume_digest() -> None:
    """Izolace a bitová shoda checkpointů: žádná sdílená měnitelná pole a identický digest."""
    world = village_grid(3, 2, seed=7, syntax=True, semantics=True)
    sim = Simulation(world)
    sim.run(100)

    cp = sim.checkpoint()
    cp_world = cp.state[0]

    # Ověříme, že indexy v živém světě a checkpointu nesdílejí žádné instance polí/slovníků
    for gid in sim.world.group_ids():
        live_cache = sim.world.groups[gid].main_code.phonology.cache
        cp_cache = cp_world.groups[gid].main_code.phonology.cache

        # Sémantické indexy
        for key in list(live_cache.keys()):
            if isinstance(key, tuple) and key[0] == "semantic-index":
                live_idx = cast(SemanticSitesIndex, live_cache[key][1])
                cp_idx = cast(SemanticSitesIndex, cp_cache[key][1])
                assert live_idx is not cp_idx
                assert live_idx.found is not cp_idx.found
                assert live_idx.site_rates is not cp_idx.site_rates
                assert live_idx.sorted_sites is not cp_idx.sorted_sites
                assert live_idx.rates_array is not cp_idx.rates_array

        # Morfologický index
        if "morphology-candidate-index" in live_cache:
            live_m = cast(MorphologyCandidateIndex, live_cache["morphology-candidate-index"][1])
            cp_m = cast(MorphologyCandidateIndex, cp_cache["morphology-candidate-index"][1])
            assert live_m is not cp_m
            assert live_m.results is not cp_m.results
            assert live_m.contributions is not cp_m.contributions
            assert live_m.sorted_sites is not cp_m.sorted_sites

    # Nepřerušený běh
    sim.run(200)
    digest_straight = sim.history.digest()

    # Pokračování z checkpointu
    resumed = Simulation.resume(cp)
    resumed.run(200)
    digest_resumed = resumed.history.digest()

    assert digest_resumed == digest_straight

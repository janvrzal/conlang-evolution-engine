"""Testy indexu míst s mírami a součty (fáze 5, kroky 2 a 3)."""

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
from cee.v2.changes.morphology import Extension, Leveling, Rebracketing
from cee.v2.changes.sound import (
    FULL_SUPPORT,
    SOUND_CHANGES,
    SOUND_INNOVATIONS_PER_GENERATION,
    SoundChange,
    SoundSupportIndex,
    _total_prior,
)
from cee.v2.language.index import ContextIndex
from cee.v2.language.morphology_index import MorphologyCandidateIndex
from cee.v2.language.semantic_index import SemanticSitesIndex
from cee.v2.phonology import enter_vocabulary, leave_vocabulary
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
        Rebracketing(),
        *SOUND_CHANGES,
    ]

    # Běžíme 500 let (20 kroků) a kontrolujeme každý krok pro všechny skupiny
    for _ in sim.iterate(500):
        for group in sim.world.groups.values():
            if group.written:
                continue
            context = InnovationContext(sim.world, group, group.main_code, sim.tick, sim.year)
            state = group.main_code.phonology
            # Nejprve sebereme všechny průběžné výsledky s živou keší
            live_results = []
            for change in indexed_changes:
                total_rate = change.total_rate(context)
                sites = list(change.sites(context))
                rates = list(change.rates(context, sites))
                ws_sites, ws_weights = change.weighted_sites(context)
                live_results.append(
                    (
                        change,
                        total_rate,
                        sites,
                        rates,
                        list(ws_sites),
                        None if ws_weights is None else ws_weights.copy(),
                    )
                )

            # Poté nad dočasně vyprázdněnou keší spočteme referenci úplně od nuly
            saved_cache = dict(state.cache)
            state.cache.clear()
            try:
                for change, total_rate, sites, rates, ws_sites, ws_weights in live_results:
                    if isinstance(change, SoundChange):
                        sound_ref_dict = change._supported_legacy(context)
                        sound_ref_sites = sorted(sound_ref_dict)
                        scale = SOUND_INNOVATIONS_PER_GENERATION * (change.prior / _total_prior())
                        ref_rates = [
                            scale * min(1.0, sound_ref_dict[s][1] / FULL_SUPPORT) / len(sound_ref_sites)
                            for s in sound_ref_sites
                        ] if sound_ref_sites else []
                        ref_total = float(np.sum(np.asarray(ref_rates, dtype=np.float64))) if ref_rates else 0.0

                        assert sites == sound_ref_sites
                        if ref_rates:
                            assert np.allclose(rates, ref_rates, rtol=0.0, atol=1e-12)
                            assert abs(total_rate - ref_total) <= 1e-12
                        else:
                            assert rates == []
                            assert total_rate == 0.0

                        assert ws_sites == sites
                        if ref_rates and total_rate > 0.0:
                            assert ws_weights is not None
                            np.testing.assert_allclose(ws_weights, np.array(rates) / total_rate)
                        else:
                            assert ws_weights is None
                    elif isinstance(change, SemanticChange):
                        sem_ref_dict = change._sites_reference(context)
                        sem_ref_sites = sorted(sem_ref_dict)
                        ref_rates = [
                            change.base_rate * sum(weight for weight, _ in sem_ref_dict[s])
                            for s in sem_ref_sites
                        ]
                        assert sites == sem_ref_sites
                        if ref_rates:
                            assert np.allclose(rates, ref_rates, rtol=0.0, atol=1e-12)
                            assert abs(total_rate - sum(ref_rates)) <= 1e-12
                        else:
                            assert rates == []
                            assert total_rate == 0.0

                        assert ws_sites == sites
                        if ref_rates and total_rate > 0.0:
                            assert ws_weights is not None
                            np.testing.assert_allclose(ws_weights, np.array(rates) / total_rate)
                        else:
                            assert ws_weights is None
                    elif isinstance(change, (Extension, Leveling, Rebracketing)):
                        morph_ref_dict = change.candidates(context)
                        morph_ref_sites = sorted(morph_ref_dict)
                        assert sites == morph_ref_sites
                        ref_total = float(
                            change.base_rate * len(morph_ref_sites) * change.rate_scale(context)
                        ) if morph_ref_sites else 0.0
                        assert abs(total_rate - ref_total) <= 1e-12
                        assert ws_sites == sites
                        assert ws_weights is None  # uniform rate
                    elif isinstance(change, LexicalCoinage):
                        ref_sites = list(context.code.repertoire.variable_ids_of("lexical"))
                        assert sites == ref_sites
                        ref_total = float(
                            change.base_rate * len(ref_sites) * change.rate_scale(context)
                        ) if ref_sites else 0.0
                        assert abs(total_rate - ref_total) <= 1e-12
                        assert ws_sites == ref_sites
                        assert ws_weights is None  # uniform rate
            finally:
                state.cache.clear()
                state.cache.update(saved_cache)


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

    shift.options = counting_options

    # Dotaz při nezměněné verzi nesmí options vůbec volat (O(1))
    same_total = shift.total_rate(context)
    assert same_total == initial_total
    assert len(options_calls) == 0

    # Změna dominantního kořene jednoho pojmu
    state = group.main_code.phonology
    concept_to_change = "water" if "water" in state.dominant else next(iter(state.dominant))
    old_root = state.dominant[concept_to_change]
    state.dominant[concept_to_change] = "morpheme:dummy_test_root"
    state.dominant_log.append((concept_to_change, old_root, "morpheme:dummy_test_root"))
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


def test_sound_support_index_inventory_transition_and_mutations() -> None:
    """Ověření změn slovníku, mutací i přechodů inventáře v SoundSupportIndex."""
    world = village_grid(2, seed=5, phonology=True)
    sim = Simulation(world)
    group = next(iter(world.groups.values()))
    code = group.main_code
    context = InnovationContext(world, group, code, sim.tick, sim.year)

    # 1. Výchozí stav: shoda s legacy referencí
    for change in SOUND_CHANGES:
        assert list(change.sites(context)) == sorted(change._supported_legacy(context))

    # 2. Odchod slova ze slovníku
    state = code.phonology
    sample_root = next(iter(state.vocabulary))
    leave_vocabulary(code, sample_root)
    for change in SOUND_CHANGES:
        assert list(change.sites(context)) == sorted(change._supported_legacy(context))

    # 3. Návrat slova do slovníku
    enter_vocabulary(world, code, sample_root)
    for change in SOUND_CHANGES:
        assert list(change.sites(context)) == sorted(change._supported_legacy(context))

    # 4. Přímá mutace state.vocabulary.remove bez logu
    word_to_remove = next(iter(state.vocabulary))
    state.vocabulary.remove(word_to_remove)
    for change in SOUND_CHANGES:
        assert list(change.sites(context)) == sorted(change._supported_legacy(context))

    # 5. Přechod inventáře: odebrání všech slov obsahujících vybranou hlásku
    ci = cast(ContextIndex, state.cache["context-index"][1])
    inv_before = ci.inventory()
    # Najdeme hlásku s nejmenším výskytem
    target_seg = min(ci.segment_counts, key=lambda s: ci.segment_counts[s])
    for unit in list(state.vocabulary):
        form = world.form_of(code, unit)
        if target_seg in form:
            state.vocabulary.remove(unit)
    ci.sync(world, code)
    inv_after = ci.inventory()
    assert target_seg not in inv_after
    assert len(inv_after) < len(inv_before)

    # SoundSupportIndex musí detekovat změnu inventáře a provést full rebuild
    for change in SOUND_CHANGES:
        sites = change.sites(context)
        ref = change._supported_legacy(context)
        assert list(sites) == sorted(ref)


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

        # Zvukový index opor
        if "sound-support-index" in live_cache:
            live_ss = cast(SoundSupportIndex, live_cache["sound-support-index"][1])
            cp_ss = cast(SoundSupportIndex, cp_cache["sound-support-index"][1])
            assert live_ss is not cp_ss
            assert live_ss.supports is not cp_ss.supports
            assert live_ss.effective_supports is not cp_ss.effective_supports
            assert live_ss.families is not cp_ss.families

        # Index prostředí
        if "context-index" in live_cache:
            live_ci = cast(ContextIndex, live_cache["context-index"][1])
            cp_ci = cast(ContextIndex, cp_cache["context-index"][1])
            assert live_ci is not cp_ci
            assert live_ci.counts is not cp_ci.counts
            assert live_ci.segment_counts is not cp_ci.segment_counts
            assert live_ci.deltas is not cp_ci.deltas

    # Nepřerušený běh
    sim.run(200)
    digest_straight = sim.history.digest()

    # Pokračování z checkpointu
    resumed = Simulation.resume(cp)
    resumed.run(200)
    digest_resumed = resumed.history.digest()

    assert digest_resumed == digest_straight

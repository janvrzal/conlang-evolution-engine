"""Index míst světa na číslech (B5b): Rust proti referenci v Pythonu a proti původnímu úplnému výpočtu.

Index (``cee.v2.language.site_index``) drží morfologii (členství, koncovky, kandidáty vyrovnání a rozšíření,
slabost buněk), sémantická místa a syntaktická místa jako čísla; Rust (``cee_core.SiteIndex``) a reference
v Pythonu (``PythonSites``) mají stejné rozhraní a musí dávat bit po bitu totéž, a to totéž, co původní
výpočty od nuly (``candidates``, ``_sites_reference``, ``_weakness_reference``).
"""

from __future__ import annotations

import copy
import pickle
from typing import Any

import numpy as np
import pytest

from cee.v2 import native, syntax
from cee.v2.changes import DEFAULT_CHANGES
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.lexicon import SemanticChange
from cee.v2.changes.morphology import Extension, Leveling
from cee.v2.changes.sites import native_column, rate_sums
from cee.v2.changes.syntax import SyntacticChange
from cee.v2.language import semantic_index
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.morphology_index import ExponentIndex, _count_reference
from cee.v2.language.site_index import COL_SEMANTIC, SiteIndex, site_index
from cee.v2.morphology import class_stats
from cee.v2.scenarios import language_shift, village_grid
from cee.v2.simulation import Simulation

RUST = native.available() and native.sums_match()


def contexts_of(simulation: Simulation) -> list[InnovationContext]:
    world = simulation.world
    return [
        InnovationContext(world, world.groups[group_id], world.groups[group_id].main_code, simulation.tick, simulation.year)
        for group_id in world.group_ids() if not world.groups[group_id].written
    ]


def worlds() -> list[tuple[str, Any]]:
    return [
        ("grid", lambda: (village_grid(3, 2, seed=4, syntax=True, semantics=True), [])),
        ("shift", lambda: language_shift(2, start=300.0)),
    ]


def bases_of(changes: Any) -> tuple[dict[int, float], float]:
    bases = {native_column(change): change.base_rate for change in changes if native_column(change) is not None}
    return bases, 1.0


def hexes(values: Any) -> list[str]:
    return [float(value).hex() for value in np.asarray(values, dtype=np.float64).ravel()]


@pytest.mark.parametrize("name", [name for name, _ in worlds()])
def test_davka_je_stejna_jako_celkove_miry_po_jedne_zmene(name):
    """``rate_sums`` (jedna dávka) = ``total_rate`` každé změny po skupinách, bit po bitu (včetně zvukových změn)."""
    build = dict(worlds())[name]
    world, events = build()
    simulation = Simulation(world, events=events)
    checked = 0
    for _ in range(14):
        simulation.step()
        contexts = contexts_of(simulation)
        sums = rate_sums(DEFAULT_CHANGES, contexts)
        for column, change in enumerate(DEFAULT_CHANGES):
            expected = [change.total_rate(context) for context in contexts]
            expected = [value if value > 0.0 else 0.0 for value in expected]
            assert hexes(sums[:, column]) == hexes(expected), f"{name}: tik {simulation.tick}, {change.kind}"
            checked += int(any(expected))
    assert checked > 40


@pytest.mark.skipif(not RUST, reason="rozšíření cee_core není k dispozici")
@pytest.mark.parametrize("name", [name for name, _ in worlds()])
def test_rust_a_reference_v_pythonu_davaji_totez(name):
    """Dvě nezávislé indexy nad týmž světem (Rust a Python) mají po každém tiku stejné míry, počty a místa."""
    world, events = dict(worlds())[name]()
    simulation = Simulation(world, events=events)
    rust, python = SiteIndex(native.new_site_index()), SiteIndex()
    assert rust.native and not python.native
    changes = [change for change in DEFAULT_CHANGES if native_column(change) is not None]
    bases, scale = bases_of(changes)
    compared = 0
    for _ in range(16):
        simulation.step()
        contexts = contexts_of(simulation)
        a, b = rust.batch(world, contexts, bases, scale), python.batch(world, contexts, bases, scale)
        assert hexes(a[0]) == hexes(b[0]) and a[1].tolist() == b[1].tolist(), f"tik {simulation.tick}"
        for context in contexts:
            code = context.code
            for kind in range(len(semantic_index.KINDS)):
                assert rust.semantic_sites(world, code, kind) == python.semantic_sites(world, code, kind)
                base = bases[COL_SEMANTIC + kind]
                assert hexes(rust.semantic_rates(code, kind, base)) == hexes(python.semantic_rates(code, kind, base))
            for extension in (False, True):
                assert rust.candidates(world, code, extension) == python.candidates(world, code, extension)
            assert rust.stats(world, code) == python.stats(world, code)
            for kind in range(10):
                (sites_a, rates_a), (sites_b, rates_b) = rust.syntax_sites(code, kind), python.syntax_sites(code, kind)
                assert sites_a == sites_b and hexes(rates_a) == hexes(rates_b)
            compared += len(rust.candidates(world, code, False)) + len(rust.candidates(world, code, True))
    assert compared > 0


@pytest.mark.parametrize("backend", ["python", "rust"])
def test_prubezny_index_je_stejny_jako_nove_postaveny(backend):
    """Index udržovaný po tikách = index postavený od nuly nad stejným stavem světa."""
    if backend == "rust" and not RUST:
        pytest.skip("rozšíření cee_core není k dispozici")
    world, events = dict(worlds())["grid"]()
    simulation = Simulation(world, events=events)

    def make() -> SiteIndex:
        return SiteIndex(native.new_site_index() if backend == "rust" else None)

    kept = make()
    changes = [change for change in DEFAULT_CHANGES if native_column(change) is not None]
    bases, scale = bases_of(changes)
    for step in range(12):
        simulation.step()
        contexts = contexts_of(simulation)
        a = kept.batch(world, contexts, bases, scale)
        if step % 3 == 0:
            b = make().batch(world, contexts, bases, scale)
            assert hexes(a[0]) == hexes(b[0]) and a[1].tolist() == b[1].tolist(), f"tik {simulation.tick}"


def test_miry_a_mista_odpovidaji_puvodnimu_uplnemu_vypoctu():
    """Místa vyrovnání a rozšíření, slabost buněk, počty koncovek a místa změn jako při výpočtu od nuly."""
    world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
    simulation = Simulation(world)
    seen = {"leveling": 0, "extension": 0, "weak": 0}
    for step in range(16):
        simulation.step()
        if step == 7:
            # Tvar buňky splyne s citačním tvarem (koncovka zanikla): buňka je slabá.
            first = contexts_of(simulation)[0]
            unit = next(u for u in sorted(first.code.phonology.vocabulary) if world.morphemes[u].kind == "word")
            citation = world.form_of(first.code, world.morphemes[unit].lexeme_id)
            first.code.forms.set(unit, UnitForm(citation, None, None))
            first.code.phonology.version += 1
        for context in contexts_of(simulation):
            code = context.code
            for change in (Leveling(), Extension()):
                reference = change.candidates(context)
                assert change._sites(context) == reference
                assert list(change.sites(context)) == sorted(reference)
                seen[change.kind] += len(reference)
            for function in syntax.functions(world):
                value = syntax.weakness(world, code, function.id)
                assert value == syntax._weakness_reference(world, code, function.id)
                seen["weak"] += int(value > 0.0)
            expected = _count_reference(world, code)
            held = ExponentIndex()
            held.sync(world, code)
            assert (held.exponents, held.shapes) == expected
            stats = class_stats(world, code)
            assert {key: dict(value) for key, value in stats.exponents.items()} == {
                key: dict(value) for key, value in sorted(expected[0].items())
            }
            for change in DEFAULT_CHANGES:
                if isinstance(change, SemanticChange):
                    reference = change._sites_reference(context)
                    assert list(change.sites(context)) == sorted(reference)
                    assert change._sites(context) == reference
                    expected_rates = [change.base_rate * sum(w for w, _ in reference[s]) for s in sorted(reference)]
                    assert hexes(change.rates(context, change.sites(context))) == hexes(expected_rates)
                elif isinstance(change, SyntacticChange):
                    assert list(change.sites(context)) == change._sites_reference(context)
    assert seen["leveling"] > 0 and seen["extension"] > 0 and seen["weak"] > 0


@pytest.mark.parametrize("copying", ["deepcopy", "pickle"])
def test_stav_indexu_se_po_kopii_a_ulozeni_znovu_postavi(copying):
    """Kopie světa (checkpoint) i uložení nese jen volbu Rust/Python; stav se při dalším použití postaví znovu."""
    world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
    simulation = Simulation(world)
    for _ in range(8):
        simulation.step()
    index = site_index(world)
    contexts = contexts_of(simulation)
    changes = [change for change in DEFAULT_CHANGES if native_column(change) is not None]
    bases, scale = bases_of(changes)
    expected = index.batch(world, contexts, bases, scale)
    copied = copy.deepcopy(world) if copying == "deepcopy" else pickle.loads(pickle.dumps(world))
    assert copied.sites is not index and copied.sites.native == index.native
    group_contexts = [
        InnovationContext(copied, copied.groups[c.group.id], copied.groups[c.group.id].main_code, c.tick, c.year)
        for c in contexts
    ]
    actual = site_index(copied).batch(copied, group_contexts, bases, scale)
    assert hexes(actual[0]) == hexes(expected[0]) and actual[1].tolist() == expected[1].tolist()


def test_index_nezarazuje_do_banky_tvary_ktere_model_nepouziva():
    """Výchozí tvary morfémů drží index ve vlastní aréně; banka tvarů světa jimi neroste."""
    world = village_grid(3, 2, seed=4, syntax=True, semantics=True)
    simulation = Simulation(world)
    simulation.step()
    before = len(world.form_bank())
    fresh = SiteIndex(native.new_site_index() if RUST else None)
    changes = [change for change in DEFAULT_CHANGES if native_column(change) is not None]
    bases, scale = bases_of(changes)
    fresh.batch(world, contexts_of(simulation), bases, scale)
    assert len(world.form_bank()) == before

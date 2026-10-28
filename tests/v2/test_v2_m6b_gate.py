"""Brána milníku M6b (specifikace, oddíl Milníky): společnost.

Metrika 9 (Séguyho zákon) v plném modelu na mapě, superstrát po přechodu
elity, stabilní dvojjazyčnost, loajalita, podíl L2 mluvčích z migrace,
Fergusonova diglosie a učená slova z liturgického jazyka.
"""

import statistics

import pytest

from cee.v2 import contact
from cee.v2.events import ReligiousChange
from cee.v2.metrics import (
    code_distance,
    distinctive_variants,
    isolation_by_distance,
    morphological_complexity,
    spearman,
    trace_shares,
)
from cee.v2.scenarios import (
    conquest,
    conversion,
    diglossia,
    language_shift,
    market_town,
    migration_region,
    village_grid,
)
from cee.v2.simulation import Simulation

SEEDS = (1, 2)


def _loans(world, group, language):
    code = world.groups[group].main_code
    return sum(world.morphemes[root].language == language for root in code.phonology.dominant.values())


# --- metrika 9 ------------------------------------------------------------------


@pytest.mark.parametrize("seed", (2, 3))
def test_metrika_9_vzdalenost_roste_se_zemepisnou_zpomalene(seed):
    """Séguyho zákon: na mapě (2D) roste vzdálenost nářečí jako logaritmus.

    V řadě vesnic (1D) a ve světě M1 se stejnou výhodou inovace všude je
    průběh lineární; ve 2D a s místním oceněním změn (od M3b) vzniká sám.
    """
    world = village_grid(5, 5, seed=seed, morphology=True, semantics=True)
    simulation = Simulation(world)
    simulation.run(2500)
    snapshot = simulation.history.snapshots[-1]
    fit = isolation_by_distance(snapshot.distances, [world.position_of(group) for group in snapshot.group_ids])
    assert fit.correlation > 0.7
    assert fit.sublinear


# --- superstrát -----------------------------------------------------------------


@pytest.fixture(scope="module")
def conquered():
    result = []
    for seed in SEEDS:
        world, events = conquest(seed)
        simulation = Simulation(world, events=events)
        simulation.run(1100)
        elite = distinctive_variants(world, "l0+e0", "l3")
        simulation.run(2000)
        result.append((world, simulation.history, elite))
    return result


def test_elita_v_mensine_prejde_na_jazyk_poddanych(conquered):
    for world, history, _ in conquered:
        shifts = history.of_kind("language_shift")
        assert [event["group"] for event in shifts] == ["l0+e0"]
        assert 150 <= shifts[0]["year"] - 1100 <= 500
        # V poddaném území se mluví jen jazykem poddaných; domovina dobyvatelů zůstává.
        assert all(group.main_code.language == "l" for group in world.groups.values()
                   if group.territory != "e0")


def test_superstrat_je_hlavne_slovni(conquered):
    for world, _, elite in conquered:
        for group in ("l0", "l1", "l2", "l3"):
            assert _loans(world, group, "e") >= 2
            # Stavba elity se v jazyce poddaných neuchytí (na rozdíl od substrátu v S3).
            assert trace_shares(world, group, elite)["construction"] < 0.1


# --- stabilní dvojjazyčnost a loajalita -------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_jazyk_trhu_jen_mimo_domov_je_stabilni_dvojjazycnost(seed):
    world, events = market_town(seed)
    simulation = Simulation(world, events=events)
    simulation.run(2000)
    assert not simulation.history.of_kind("language_shift")
    assert world.groups["a1"].transmitted and world.groups["a1"].population == 500
    bilingual = world.groups["a1>b"]
    assert bilingual.domain == "public" and bilingual.main_code.l2_share == 1.0
    native = world.groups["a1"].main_code.phonology.dominant
    assert sum(world.morphemes[root].language == "a" for root in native.values()) / len(native) > 0.8
    assert _loans(world, "a1", "b") > 0


def test_loajalita_prechod_zpomali_nebo_zastavi():
    def shifted(loyalty):
        world, events = language_shift(1)
        for group in ("x0", "x1", "x2"):
            world.groups[group].loyalty = loyalty
        simulation = Simulation(world, events=events)
        simulation.run(2500)
        return {event["group"]: event["year"] for event in simulation.history.of_kind("language_shift")}

    free, loyal, steadfast = shifted(0.0), shifted(0.6), shifted(0.9)
    assert set(free) == set(loyal) == {"x0", "x1", "x2"}
    assert all(loyal[group] > free[group] for group in free)
    assert {"x0", "x1"}.isdisjoint(steadfast)


# --- migrace ----------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_podil_l2_mluvcich_vyplyne_z_migrace_a_slozitost_klesa(seed):
    world = migration_region(seed)
    Simulation(world).run(1500)
    groups = world.group_ids()
    populations = [world.groups[group].population for group in groups]
    shares = [world.groups[group].main_code.l2_share for group in groups]
    complexity = [morphological_complexity(world, group) for group in groups]
    assert spearman(populations, shares) > 0.6  # města přitahují přistěhovalce
    assert world.groups["city"].main_code.l2_share == max(shares)
    assert spearman(populations, complexity) < 0.0
    assert spearman(shares, complexity) < 0.0


# --- Fergusonova diglosie a náboženská změna ------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_fergusonova_diglosie_vysoka_varieta_stoji_lidova_rec_se_vzdaluje(seed):
    world, events = diglossia(seed, diglossic=True)
    simulation = Simulation(world, events=events)
    written = "written:v00-02"

    def distance(first, second):
        return sum(code_distance(world, first, second).values())

    simulation.run(1475)
    before = statistics.mean(distance(group, written) for group in world.group_ids() if group != written)
    simulation.run(3000)
    vernacular = [group for group in world.group_ids()
                  if not world.groups[group].written and world.groups[group].domain == "home"]
    high = [f"{group}>H" for group in vernacular]
    assert all(world.groups[group].domain == "public" for group in high)
    low_gap = statistics.mean(distance(group, written) for group in vernacular)
    high_gap = statistics.mean(distance(group, written) for group in high)
    assert low_gap >= before  # lidová řeč se psané nepřibližuje (na rozdíl od S4)
    assert high_gap < low_gap / 2  # vysoká varieta drží normu
    assert statistics.mean(distance(group, f"{group}>H") for group in vernacular) > 0.05
    # Vysoká varieta je druhý kód: do dialektů a jazyků se nepočítá.
    assert set(simulation.history.snapshots[-1].group_ids) == set(vernacular)


@pytest.mark.parametrize("seed", SEEDS)
def test_nabozenstvi_prinese_ucena_slova_z_liturgickeho_jazyka(seed):
    def loans(events_filter):
        world, events = conversion(seed)
        simulation = Simulation(world, events=[event for event in events if events_filter(event)])
        simulation.run(2000)
        return world, {group: _loans(world, group, "r") for group in ("v0", "v1", "v2", "v3")}

    world, converted = loans(lambda event: True)
    _, control = loans(lambda event: not isinstance(event, ReligiousChange))
    assert all(count >= 1 for count in converted.values()) and sum(converted.values()) >= 6
    assert not any(control.values())
    learned = [concept for group in ("v0", "v1", "v2", "v3")
               for concept, root in world.groups[group].main_code.phonology.dominant.items()
               if world.morphemes[root].language == "r"]
    assert statistics.mean(world.concept_frequency(concept) for concept in learned) < 0.7 * statistics.mean(
        world.concept_frequencies.values()
    )
    for group in ("v0", "v1", "v2", "v3"):
        code = world.groups[group].main_code
        inventory = set(contact.inventory(world, code))
        assert all(set(world.form_of(code, root)) <= inventory
                   for root in code.phonology.dominant.values() if world.morphemes[root].language == "r")

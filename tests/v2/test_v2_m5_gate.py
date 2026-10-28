"""Brána milníku M5 (specifikace, oddíl Milníky): kontakt jazyků.

S2 (ostrov a obchodní město), S3 (přechod regionu na prestižní jazyk),
výpůjčky mezi jazyky v trvalém kontaktu a metrika 11 (morfologická
složitost klesá s podílem L2 mluvčích a s velikostí populace).
"""

import statistics

import pytest

from cee.v2 import contact, syntax
from cee.v2.events import Contact
from cee.v2.metrics import (
    distinctive_variants,
    morphological_complexity,
    morphology_profile,
    spearman,
    trace_shares,
)
from cee.v2.scenarios import Language, Place, contact_world, island_and_city, language_shift
from cee.v2.simulation import Simulation

SEEDS = (1, 2)


def _run(world, until, events=()):
    simulation = Simulation(world, events=events)
    simulation.run(until)
    return world, simulation.history


# --- S2: ostrov a obchodní město ------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_s2_mesto_s_pristehovalci_zjednodusuje_ostrov_drzi(seed):
    world, _ = _run(island_and_city(seed), 2000)
    island, city = morphology_profile(world, "island"), morphology_profile(world, "city")
    assert city.irregular_rare < island.irregular_rare / 2
    assert city.productive_share > island.productive_share + 0.1
    # Častá slova si nepravidelnost drží i ve městě (Sturtevantův paradox).
    assert city.irregular_frequent > city.irregular_rare


@pytest.mark.parametrize("seed", SEEDS)
def test_s2_zjednoduseni_pusobi_l2_mluvci(seed):
    """Kontrolovaný pokus: totéž město bez přistěhovalců a s nimi."""
    native, _ = _run(island_and_city(seed, immigration=0.0), 2000)
    mixed, _ = _run(island_and_city(seed, immigration=0.6), 2000)
    assert morphological_complexity(mixed, "city") < morphological_complexity(native, "city") / 2


# --- S3: přechod na jiný jazyk ---------------------------------------------


@pytest.fixture(scope="module")
def shifted():
    result = []
    for seed in SEEDS:
        world, events = language_shift(seed)
        simulation = Simulation(world, events=events)
        simulation.run(1500)
        substrate = distinctive_variants(world, "x1", "y2")
        simulation.run(2500)
        result.append((world, simulation.history, substrate))
    return result


def test_s3_region_prejde_na_prestizni_jazyk(shifted):
    for world, history, _ in shifted:
        assert {event["group"] for event in history.of_kind("language_shift")} == {"x0", "x1", "x2"}
        assert all(group.main_code.language == "y" for group in world.groups.values())


def test_s3_v_novem_jazyce_zustane_stavba_a_vyslovnost_ale_malo_slov(shifted):
    for world, _, substrate in shifted:
        processes = [variable for variable, (kind, _) in substrate.items() if kind == "process"]
        constructions = {group: trace_shares(world, group, substrate)["construction"]
                         for group in ("x0>y", "x1>y", "x2>y", "y0", "y2")}
        # Substrát je nejsilnější daleko od kontaktu; pohraniční vesnice se
        # většinovému jazyku vyrovnává a jádro většinového jazyka ho skoro nemá.
        assert min(constructions["x0>y"], constructions["x1>y"]) > 0.5
        assert constructions["x1>y"] > constructions["x2>y"] > constructions["y2"]
        for group in ("x0>y", "x1>y", "x2>y"):
            traces = trace_shares(world, group, substrate)
            # Thomason & Kaufman: interference při přechodu je hlavně stavební.
            assert traces["lexical"] < 0.05
            assert traces["construction"] > 10 * traces["lexical"]
            # Zvukové změny prvního jazyka jsou zapsané v tvarech nového.
            code = world.groups[group].main_code
            written = sum(bool(code.phonology.restructured.get(variable)) for variable in processes)
            assert written >= 0.8 * len(processes)
            native = [concept for concept, root in code.phonology.dominant.items()
                      if world.morphemes[root].language == "x"]
            # Zůstane jen pár slov, a to vzácných (místní a odvozená slova).
            assert len(native) / len(code.phonology.dominant) < 0.08
            if native:
                assert statistics.mean(world.concept_frequency(concept) for concept in native) < (
                    statistics.mean(world.concept_frequencies.values())
                )
        # Jádro většinového jazyka si svou stavbu drží.
        assert syntax.dominant(world, "y2", "NEG").kind == "pre"
        assert trace_shares(world, "y2", substrate)["construction"] < 0.1


# --- výpůjčky ------------------------------------------------------------------


@pytest.fixture(scope="module")
def borrowing():
    result = []
    for seed in SEEDS:
        world = contact_world([
            Language("a", tuple(Place(f"a{index}", (index * 10.0, 0.0)) for index in range(3))),
            Language("b", tuple(Place(f"b{index}", (40.0 + index * 10.0, 0.0)) for index in range(3)),
                     consonants=("t", "k", "s", "n", "m", "l", "ʃ", "f", "x", "v", "r", "j", "ts")),
        ], seed=seed)
        result.append(_run(world, 2000, [Contact(500.0, (("a2", "b0"),), 0.5)])[0])
    return result


def _loans(world, group):
    code = world.groups[group].main_code
    return {
        concept: root for concept, root in sorted(code.phonology.dominant.items())
        if world.morphemes[root].language != code.language
    }


def test_vypujcky_jsou_vzacne_pojmy_adaptovane_hlaskami_prijemce(borrowing):
    for world in borrowing:
        for group in ("a2", "b0"):
            loans = _loans(world, group)
            assert 3 <= len(loans) <= 40
            code = world.groups[group].main_code
            assert all(set(world.form_of(code, root)) <= set(contact.inventory(world, code))
                       for root in loans.values())
        loans = [concept for group in world.group_ids() for concept in _loans(world, group)]
        assert statistics.mean(world.concept_frequency(concept) for concept in loans) < 0.7 * statistics.mean(
            world.concept_frequencies.values()
        )


def test_bez_dvojjazycnosti_se_stavba_nepujcuje(borrowing):
    for world in borrowing:
        for group in ("a0", "a1", "a2"):
            # Konstrukce jazyka b se v jazyce a neprosadí (oba mají výchozí
            # gramatiku, ale jiné koncovky: nová koncovka b by byla výpůjčkou afixu).
            for function in ("PAST", "PL", "OBJ"):
                exponent = syntax.dominant(world, group, function).exponent
                assert exponent is None or world.morphemes[exponent].language == "a"


# --- metrika 11 ---------------------------------------------------------------


POPULATIONS = (100, 300, 1000, 3000, 10000)
L2_SHARES = (0.0, 0.15, 0.3, 0.45)


@pytest.mark.parametrize("seed", SEEDS)
def test_metrika_11_slozitost_klesa_s_l2_mluvcimi_a_populaci(seed):
    places = tuple(
        Place(f"g{population}-{int(share * 100)}", (column * 1000.0, row * 1000.0),
              population=population, immigration=share)
        for column, population in enumerate(POPULATIONS) for row, share in enumerate(L2_SHARES)
    )
    world, _ = _run(contact_world([Language("proto", places)], seed=seed), 1500)
    complexity = {place.id: morphological_complexity(world, place.id) for place in places}

    def within(fixed, varied):
        """Průměrná korelace s ``varied`` při pevné hodnotě ``fixed``."""
        levels = sorted({getattr(place, fixed) for place in places})
        return statistics.mean(
            spearman([getattr(place, varied) for place in places if getattr(place, fixed) == level],
                     [complexity[place.id] for place in places if getattr(place, fixed) == level])
            for level in levels
        )

    assert within("population", "immigration") < -0.6
    assert within("immigration", "population") < -0.6

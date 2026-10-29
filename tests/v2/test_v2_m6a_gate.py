"""Brána milníku M6a (specifikace, oddíl Milníky): instituce a diglosie.

Scénář S4: písmo v roce 500, škola a tisk v roce 1500. Rozdíl mluvené a
psané řeči roste do zavedení školy, pak se zmenšuje.
"""

import statistics

import pytest

from cee.v2.events import Codification
from cee.v2.metrics import code_distance
from cee.v2.scenarios import diglossia, village_grid
from cee.v2.simulation import Simulation

SEEDS = (1, 2)
WRITTEN = "written:v00-02"


def _spoken(world):
    return [group for group in world.group_ids() if not world.groups[group].written]


def _gap(world):
    """Průměrná vzdálenost mluvené řeči vesnic od psaného kódu."""
    return statistics.mean(sum(code_distance(world, group, WRITTEN).values()) for group in _spoken(world))


def _dialects(world):
    groups = _spoken(world)
    return statistics.mean(
        sum(code_distance(world, first, second).values())
        for index, first in enumerate(groups) for second in groups[index + 1 :]
    )


def _course(seed, **options):
    world, events = diglossia(seed, **options)
    simulation = Simulation(world, events=events)
    course = {}
    for year in (1000, 1475, 2000, 2500):
        simulation.run(year)
        course[year] = (_gap(world), _dialects(world))
    established = [event for event in simulation.history.of_kind("established") if event["year"] > 1750]
    return world, course, len(established)


def run_diglossia_courses(seed: int):
    return {
        "school": _course(seed),
        "none": _course(seed, school=None),
        "frozen": _course(seed, printing=False),
    }


def check_s4_skola(courses):
    _, course, _ = courses["school"]
    assert course[1000][0] < course[1475][0]  # diglosie: psaný kód stojí, řeč ne
    assert course[2000][0] < course[1475][0] / 3
    assert course[2500][0] < course[1475][0] / 3


def check_s4_bez_skoly(courses):
    _, course, _ = courses["none"]
    assert course[1000][0] < course[1475][0] < course[2000][0] < course[2500][0]


def check_skola_sjednoti(courses):
    _, school, changes = courses["school"]
    _, none, control = courses["none"]
    assert school[2500][1] < none[2500][1] / 5  # dialekty splynou se standardem
    assert changes > control / 5  # norma se obnovuje podle řeči elity


def check_skola_zmrazena(courses):
    _, _, frozen = courses["frozen"]
    _, _, printed = courses["school"]
    assert frozen < printed / 3


def run_codification(seed: int = 4):
    world = village_grid(3, seed=seed, syntax=True, semantics=True)
    simulation = Simulation(world, events=[Codification(100.0, "v00-01", tuple(world.group_ids()))])
    simulation.run(100.0)
    written = WRITTEN.replace("v00-02", "v00-01")
    before = {variable: world.distribution(written, variable)
              for variable in sorted(world.variables)}
    simulation.run(800.0)
    return world, simulation, before, written


def check_psany_kod_bez_tisku_stoji(world, simulation, before, written):
    for variable, distribution in before.items():
        if distribution is not None:
            assert world.distribution(written, variable).variants == distribution.variants
    assert all(len(snapshot.group_ids) == 3 for snapshot in simulation.history.snapshots)


@pytest.fixture(scope="module")
def runs():
    return {seed: run_diglossia_courses(seed) for seed in SEEDS}


def test_s4_rozdil_roste_do_skoly_pak_se_zmensuje(runs):
    for seed in SEEDS:
        check_s4_skola(runs[seed])


def test_s4_bez_skoly_rozdil_roste_dal(runs):
    for seed in SEEDS:
        check_s4_bez_skoly(runs[seed])


def test_skola_sjednoti_dialekty_ale_jazyk_se_meni_dal(runs):
    for seed in SEEDS:
        check_skola_sjednoti(runs[seed])


def test_skola_se_zmrazenou_normou_zmenu_zastavi(runs):
    """Kontrafaktuál: masová škola bez tisku drží řeč u jazyka z doby kodifikace."""
    for seed in SEEDS:
        check_skola_zmrazena(runs[seed])


def test_psany_kod_bez_tisku_stoji():
    world, simulation, before, written = run_codification(4)
    check_psany_kod_bez_tisku_stoji(world, simulation, before, written)


def test_determinismus_s_pismem():
    def run():
        world, events = diglossia(3, writing=200.0, school=500.0)
        simulation = Simulation(world, events=events)
        simulation.run(800.0)
        return simulation.history.digest()

    assert run() == run()

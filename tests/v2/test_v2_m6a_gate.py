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


@pytest.fixture(scope="module")
def runs():
    return {
        seed: {
            "school": _course(seed),
            "none": _course(seed, school=None),
            "frozen": _course(seed, printing=False),
        }
        for seed in SEEDS
    }


def test_s4_rozdil_roste_do_skoly_pak_se_zmensuje(runs):
    for seed in SEEDS:
        _, course, _ = runs[seed]["school"]
        assert course[1000][0] < course[1475][0]  # diglosie: psaný kód stojí, řeč ne
        assert course[2000][0] < course[1475][0] / 3
        assert course[2500][0] < course[1475][0] / 3


def test_s4_bez_skoly_rozdil_roste_dal(runs):
    for seed in SEEDS:
        _, course, _ = runs[seed]["none"]
        assert course[1000][0] < course[1475][0] < course[2000][0] < course[2500][0]


def test_skola_sjednoti_dialekty_ale_jazyk_se_meni_dal(runs):
    for seed in SEEDS:
        _, school, changes = runs[seed]["school"]
        _, none, control = runs[seed]["none"]
        assert school[2500][1] < none[2500][1] / 5  # dialekty splynou se standardem
        assert changes > control / 5  # norma se obnovuje podle řeči elity


def test_skola_se_zmrazenou_normou_zmenu_zastavi(runs):
    """Kontrafaktuál: masová škola bez tisku drží řeč u jazyka z doby kodifikace."""
    for seed in SEEDS:
        _, _, frozen = runs[seed]["frozen"]
        _, _, printed = runs[seed]["school"]
        assert frozen < printed / 3


def test_psany_kod_bez_tisku_stoji():
    world = village_grid(3, seed=4, syntax=True, semantics=True)
    simulation = Simulation(world, events=[Codification(100.0, "v00-01", tuple(world.group_ids()))])
    simulation.run(100.0)
    before = {variable: world.distribution(WRITTEN.replace("v00-02", "v00-01"), variable)
              for variable in sorted(world.variables)}
    simulation.run(800.0)
    written = WRITTEN.replace("v00-02", "v00-01")
    for variable, distribution in before.items():
        if distribution is not None:
            assert world.distribution(written, variable).variants == distribution.variants
    assert all(len(snapshot.group_ids) == 3 for snapshot in simulation.history.snapshots)


def test_determinismus_s_pismem():
    def run():
        world, events = diglossia(3, writing=200.0, school=500.0)
        simulation = Simulation(world, events=events)
        simulation.run(800.0)
        return simulation.history.digest()

    assert run() == run()

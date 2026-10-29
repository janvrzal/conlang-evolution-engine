"""Brána milníku M2 (specifikace, oddíl Milníky): metriky 3–6 nad zvukem.

Tři seedy kontinua deseti vesnic s vygenerovaným protojazykem, 3 000 let.
"""

import statistics
from collections import Counter

import pytest

from cee.v2 import phonology
from cee.v2.changes.sound import SOUND_CHANGES
from cee.v2.language.protoforms import protolanguage
from cee.v2.metrics import (
    CONSONANT_BAND,
    VOWEL_BAND,
    established_processes,
    hellinger,
    lexicon_profile,
)
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from cee.v2.world import Code, SpeechGroup, Territory, World

SEEDS = (1, 2, 3)
DOMAIN = {change.kind: change.domain for change in SOUND_CHANGES}


def run_phonology(seed: int):
    """Pro daný seed svět, historii a profily slovní zásoby po 1 000 letech."""
    world = village_grid(10, seed=seed, phonology=True)
    simulation = Simulation(world)
    profiles = []
    for year in (1000, 2000, 3000):
        simulation.run(year)
        profiles.append([lexicon_profile(world, group) for group in world.group_ids()])
    return world, simulation.history, profiles


def check_metrika_3(profiles):
    for snapshot in profiles:
        for profile in snapshot:
            assert 3.0 <= profile.mean_length <= 8.0


def check_metrika_4(profiles):
    for profile in profiles[-1]:
        assert CONSONANT_BAND[0] <= profile.consonants <= CONSONANT_BAND[1]
        assert VOWEL_BAND[0] <= profile.vowels <= VOWEL_BAND[1]


def check_metrika_5(profiles):
    for profile in profiles[-1]:
        assert profile.homophony < 0.05


def check_metrika_6(runs):
    """Legacy jádro ustálilo jen samohláskové změny; tady nesmí převážit žádná doména."""
    domains: Counter[str] = Counter()
    families: Counter[str] = Counter()
    for world, history, _ in runs:
        for variable in established_processes(history):
            family = world.processes[variable].family
            families[family] += 1
            domains[DOMAIN[family]] += 1
    total = sum(domains.values())
    assert total >= 30
    assert domains["consonant"] / total >= 0.2
    assert domains["vowel"] / total >= 0.2
    assert len(families) >= 6
    prior: Counter[str] = Counter()
    for change in SOUND_CHANGES:
        prior[change.domain] += change.prior
    assert hellinger(dict(domains), dict(prior)) < 0.25


def check_jazyky_z_ruznych_seedu_se_lisi(runs):
    """Bez nahodilosti spuštění by každý jazyk prošel stejnými změnami."""
    histories = [
        {world.processes[variable].key for variable in established_processes(history)}
        for world, history, _ in runs
    ]
    for index, first in enumerate(histories):
        for second in histories[index + 1 :]:
            overlap = len(first & second) / len(first | second)
            assert overlap < 0.6


def check_zvukove_zmeny_se_siri(world, history):
    groups_per_change = Counter(
        event["variable"] for event in history.of_kind("established")
        if str(event["variable"]).startswith("process:")
    )
    assert groups_per_change and statistics.median(groups_per_change.values()) >= 2
    closed = history.of_kind("process_closed")
    relics = sum(event["relics"] for event in closed)
    rewritten = sum(event["restructured"] for event in closed)
    assert relics + rewritten > 0 and 0.01 < relics / (relics + rewritten) < 0.15


@pytest.fixture(scope="module")
def runs():
    """Pro každý seed svět, historii a profily slovní zásoby po 1 000 letech."""
    return [run_phonology(seed) for seed in SEEDS]


def test_metrika_3_delka_slov_zustava_v_pasmu(runs):
    for _, _, profiles in runs:
        check_metrika_3(profiles)


def test_metrika_4_inventare_lezi_v_pasmu_realnych_jazyku(runs):
    for _, _, profiles in runs:
        check_metrika_4(profiles)


def test_metrika_5_homofonie_zustava_nizka(runs):
    for _, _, profiles in runs:
        check_metrika_5(profiles)


def test_metrika_6_ustalene_zmeny_odpovidaji_prioru_a_nejsou_jednostranne(runs):
    check_metrika_6(runs)


def test_jazyky_z_ruznych_seedu_se_lisi(runs):
    check_jazyky_z_ruznych_seedu_se_lisi(runs)


def test_zvukove_zmeny_se_siri_arealne_a_maji_male_vyjimky(runs):
    for world, history, _ in runs:
        check_zvukove_zmeny_se_siri(world, history)


def test_determinismus_s_fonologii():
    def digest():
        world = village_grid(4, seed=8, phonology=True)
        simulation = Simulation(world)
        simulation.run(1000)
        forms = phonology.lexicon(world, world.group_ids()[0])
        return simulation.history.digest(), forms

    assert digest() == digest()


def _two_regions(refine_west: bool) -> World:
    world = World(seed=9)
    world.add_territory(Territory("world", "world"))
    concepts = [f"c{index}" for index in range(60)]
    forms, frequencies = protolanguage(concepts, seed=9)
    base = world.seed_lexicon(concepts, forms, frequencies)
    world.add_territory(Territory("west", "region", parent="world", position=(0.0, 0.0)))
    world.add_territory(Territory("east", "region", parent="world", position=(100.0, 0.0)))
    if refine_west:
        for index in range(2):
            village = f"west-{index}"
            world.add_territory(Territory(village, "settlement", parent="west", position=(index * 10.0, 0)))
            world.add_group(SpeechGroup(village, village, 1_500, [Code("main", base.branch())]))
        world.connect("west-0", "west-1", 0.8, "strong")
    else:
        world.add_group(SpeechGroup("west", "west", 3_000, [Code("main", base.branch())], aggregate=True))
    for index in range(3):
        village = f"east-{index}"
        world.add_territory(Territory(village, "settlement", parent="east", position=(100.0 + index * 10, 0)))
        world.add_group(SpeechGroup(village, village, 500, [Code("main", base.branch())]))
    world.connect("east-0", "east-1", 0.6)
    world.connect("east-1", "east-2", 0.6)
    return world


def test_priblizeni_nezmeni_zvukovou_historii_nepropojene_oblasti():
    def east(refine_west):
        world = _two_regions(refine_west)
        simulation = Simulation(world)
        simulation.run(2000)
        groups = {group for group in world.groups if group.startswith("east")}
        events = [
            event for event in simulation.history.events
            if event.get("group") in groups and event["kind"] != "language_emerged"
        ]
        forms = {group: phonology.lexicon(world, group) for group in sorted(groups)}
        return events, forms

    coarse = east(False)
    fine = east(True)
    assert any(event["kind"] == "phonologized" for event in coarse[0])
    assert coarse == fine

"""Sloupcové tabulky světa (krok A4): shoda se slovníky objektů po skutečném běhu, izolace kopií."""

import copy
import math

import numpy as np

from cee.v2.events import Border, Contact
from cee.v2.scenarios import kingdom, language_shift, village_grid
from cee.v2.simulation import Simulation
from cee.v2.tables import LINK_KINDS, MORPHEME_KINDS, UNSET, VARIABLE_KINDS


def check_morphemes(world):
    table, registry = world.columns.morphemes, world.registry
    names = registry.morphemes.names
    assert table.version >= len(world.morphemes)
    for number, name in enumerate(names):
        stored = name in world.morphemes
        assert (number < len(table.present) and table.present[number] == 1) == stored
        if not stored:
            continue
        morpheme = world.morphemes[name]
        assert table.frequency[number] == morpheme.frequency
        assert MORPHEME_KINDS[table.kind[number]] == morpheme.kind
        assert table.languages.name(table.language[number]) == morpheme.language
        word_class = table.word_class[number]
        assert (None if word_class == UNSET else table.word_classes.name(word_class)) == morpheme.word_class
        cell = table.cell[number]
        assert (None if cell == UNSET else table.cells.name(cell)) == morpheme.cell
        assert names[table.lexeme[number]] == morpheme.lexeme_id
        exponent = table.exponent[number]
        assert (None if exponent == UNSET else names[exponent]) == morpheme.exponent
        boundary = table.boundary[number]
        assert (None if boundary == UNSET else boundary) == morpheme.boundary
        form = table.form[number]
        if form != UNSET:  # doplněno při prvním použití tvaru
            assert world.form_bank().forms[form] == morpheme.form
    # Python čte int a float, ne numpy skaláry.
    if len(table.present):
        assert type(table.frequency[0]) is float and type(table.lexeme[0]) is int


def check_variants_and_variables(world):
    registry = world.registry
    variants, variables = world.columns.variants, world.columns.variables
    for number, name in enumerate(registry.variants.names):
        assert (number < len(variants.present) and variants.present[number] == 1) == (name in world.variants)
        if name not in world.variants:
            continue
        variant = world.variants[name]
        assert registry.variables.names[variants.variable[number]] == variant.variable
        code = variants.change[number]
        assert (None if code == UNSET else variants.changes.name(code)) == variant.origin.change
        assert variants.tick[number] == variant.origin.tick and variants.year[number] == variant.origin.year
        group = variants.group[number]
        assert (None if group == UNSET else registry.groups.name(group)) == variant.origin.group
        morpheme = variants.morpheme[number]
        payload_morpheme = variant.payload.get("morpheme")
        assert (None if morpheme == UNSET else registry.morphemes.name(morpheme)) == payload_morpheme
        origin = variants.origin[number]
        assert (None if origin == UNSET else variants.payload_origins.name(origin)) == variant.payload.get("origin")
        appeal = variants.appeal[number]
        expected = variant.payload.get("appeal")
        assert (math.isnan(appeal) if expected is None else appeal == expected)
    for number, name in enumerate(registry.variables.names):
        assert (number < len(variables.present) and variables.present[number] == 1) == (name in world.variables)
        if name not in world.variables:
            continue
        variable = world.variables[name]
        assert VARIABLE_KINDS[variables.kind[number]] == variable.kind
        key = variables.key[number]
        assert (registry.concepts.name(key) if key != UNSET else None) == (
            variable.key if variable.kind == "lexical" else None
        )
        default = variables.default[number]
        assert (None if default == UNSET else registry.variants.name(default)) == variable.default


def check_links(world):
    table = world.link_table()
    groups = world.registry.groups
    assert len(table) == len(world.links) and table.groups == len(groups)
    assert table.indptr[0] == 0 and table.indptr[-1] == len(table)
    keys = list(world.links)
    found = {}
    for source in range(table.groups):
        row = table.row(source)
        targets = table.indices[row]
        assert list(targets) == sorted(targets)
        for target, strength, kind, position in zip(
            targets, table.strength[row], table.kind[row], table.position[row]
        ):
            key = (groups.name(source), groups.name(int(target)))
            link = world.links[key]
            assert link.strength == strength and LINK_KINDS[kind] == link.kind
            assert keys[position] == key  # pořadí vkládání se dá obnovit
            found[key] = True
    assert len(found) == len(world.links)


def check_all(world):
    check_morphemes(world)
    check_variants_and_variables(world)
    check_links(world)


def test_sloupce_odpovidaji_objektum_po_behu_s_udalostmi():
    events = (Border(300.0, ("v00-00", "v00-01"), ("v00-02", "v00-03"), 0.2), Contact(500.0, (("v00-00", "v00-03"),), 0.3))
    world = village_grid(4, seed=3, syntax=True, semantics=True)
    check_all(world)
    simulation = Simulation(world, events=events)
    simulation.run(800)
    check_all(simulation.world)
    assert len(simulation.world.morphemes) > 0 and len(simulation.world.links) > 0


def test_sloupce_odpovidaji_objektum_u_morfologie_a_prechodu_jazyka():
    world, events = language_shift(2, start=100.0)
    simulation = Simulation(world, events=events)
    simulation.run(400)
    check_all(simulation.world)
    morphology = Simulation(village_grid(3, seed=2, morphology=True, semantics=True))
    morphology.run(400)
    check_all(morphology.world)
    assert 2 in set(morphology.world.columns.morphemes.kind)  # tvary slov


def test_sloupce_odpovidaji_objektum_u_statu():
    world, events = kingdom(1, founded=50.0, modern=100.0)
    simulation = Simulation(world, events=events)
    simulation.run(300)
    check_all(simulation.world)


def test_vazby_po_zmene_se_prepocitaji_a_nezastaraji():
    world = village_grid(3, seed=2)
    first = world.link_table()
    assert world.link_table() is first  # beze změny se nestaví znovu
    key = next(iter(world.links))
    link = world.links[key]
    world.links[key] = type(link)(link.source, link.target, 0.123, "strong")
    check_links(world)
    world.remove_group("v00-00")
    check_links(world)
    world.links.clear()
    assert len(world.link_table()) == 0


def test_kopie_sveta_nesdili_sloupce_a_zustavaji_shodne():
    world = village_grid(3, seed=2, morphology=True, semantics=True)
    simulation = Simulation(world)
    simulation.run(200)
    copied = copy.deepcopy(simulation.world)
    check_all(copied)
    assert copied.columns.morphemes is not simulation.world.columns.morphemes
    assert copied.morphemes._table is copied.columns.morphemes
    assert copied.columns.morphemes.frequency is not simulation.world.columns.morphemes.frequency
    before = len(copied.columns.morphemes)
    arrays_before = {name: column.copy() for name, column in copied.columns.morphemes.arrays().items()}
    simulation.run(400)
    # Další běh zdroje kopii nezměnil a naopak.
    assert len(copied.columns.morphemes) == before
    for name, column in copied.columns.morphemes.arrays().items():
        assert np.array_equal(column, arrays_before[name], equal_nan=True)
    check_all(simulation.world)
    link = next(iter(copied.links.values()))
    copied.links[(link.source, link.target)] = type(link)(link.source, link.target, 0.5, link.kind)
    check_links(copied)
    check_links(simulation.world)


def test_pokracovani_z_checkpointu_dava_stejne_sloupce():
    world = village_grid(3, seed=2, morphology=True, semantics=True)
    straight = Simulation(world)
    straight.run(300)
    stopped = Simulation(village_grid(3, seed=2, morphology=True, semantics=True))
    stopped.run(150)
    resumed = Simulation.resume(stopped.checkpoint())
    resumed.run(300)
    check_all(resumed.world)
    one, two = straight.world.columns.morphemes.arrays(), resumed.world.columns.morphemes.arrays()
    assert one.keys() == two.keys()
    for name in one:
        assert np.array_equal(one[name], two[name], equal_nan=True), name
    assert straight.world.registry.morphemes.names == resumed.world.registry.morphemes.names

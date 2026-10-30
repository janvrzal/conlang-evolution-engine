"""Typologické měřidlo: agregace mluvených skupin a neznámé hodnoty."""

import math

import numpy as np
import pytest

from cee.v2 import metrics, syntax
from cee.v2.language.constructions import Construction
from cee.v2.repertoire import Distribution, Origin
from cee.v2.scenarios import village_grid


def test_normalizovana_entropie():
    assert metrics.normalized_entropy({"a": 3, "b": 3}, ("a", "b")) == pytest.approx(1)
    assert metrics.normalized_entropy({"a": 5}, ("a", "b")) == 0
    assert metrics.normalized_entropy({"a": 1, "b": 1}, ("a", "b", "c")) == pytest.approx(math.log(2) / math.log(3))
    with pytest.raises(ValueError):
        metrics.normalized_entropy({}, ("a", "b"))


def test_profil_agreguje_frekvence_a_ignoruje_psany_kod():
    world = village_grid(3, seed=1, syntax=True)
    groups = sorted(world.groups.values(), key=lambda group: group.id)
    variable, svo = syntax.register(world, Construction("ORDER", "fixed", order="SVO"), Origin(None, 0, 0, None))
    _, sov = syntax.register(world, Construction("ORDER", "fixed", order="SOV"), Origin(None, 0, 0, None))
    for group in groups:
        group.population = 100
        group.main_code.repertoire.set(variable, Distribution.fixed(sov.id))
    variants = tuple(sorted((svo.id, sov.id)))
    freqs = np.array([0.6 if variant == svo.id else 0.4 for variant in variants])
    for group in groups[:2]:
        group.main_code.repertoire.set(variable, Distribution(variants, freqs))
    groups[2].written = True
    assert metrics.typology_profile(world, [group.id for group in groups])["81A"] == "81A-2"
    groups[2].written = False
    assert metrics.typology_profile(world, [group.id for group in groups])["81A"] == "81A-1"


def test_volny_slovosled_a_chybejici_funkce_jsou_nezname():
    world = village_grid(1, seed=1, syntax=True)
    profile = metrics.typology_profile(world, list(world.groups))
    assert profile["81A"] is None
    assert profile["37A"] == "definite_absent"
    assert profile["67A"] == "67A-2"
    assert profile["66A"] == "past_present"


def test_zivy_sklad_ma_prednost_pred_repertoarem():
    from cee.v2.pools import LivePools

    world = village_grid(1, seed=1, syntax=True)
    group = next(iter(world.groups.values()))
    variable, svo = syntax.register(world, Construction("ORDER", "fixed", order="SVO"), Origin(None, 0, 0, None))
    world.live = LivePools([group.id])
    world.live.load(variable, [Distribution.fixed(svo.id)])
    assert metrics.typology_profile(world, [group.id])["81A"] == "81A-2"


def test_podkladovy_inventar_je_proxy_nikoli_wals_kategorie():
    world = village_grid(1, seed=1, syntax=True)
    group = next(iter(world.groups.values()))
    # Slovník se osídluje až při inicializaci simulace; prázdný proxy je neznámý.
    assert metrics.underlying_inventory_proxy(world, [group.id]) is None


@pytest.mark.parametrize("kind,stage,expected", [
    ("synthetic", None, "67A-1"),
    ("zero", None, "67A-2"),
    ("periphrastic", "free", "67A-2"),
    ("periphrastic", "clitic", None),
])
def test_budouci_cas_zachovava_nejednoznacnou_klitiku(kind, stage, expected):
    grammar = {"FUTURE": Construction("FUTURE", kind, "go", stage)}
    world = village_grid(1, seed=1, grammar=grammar)
    assert metrics.typology_profile(world, list(world.groups))["67A"] == expected


def test_proxy_pocita_nosovy_podkladovy_vokal():
    from types import SimpleNamespace

    table = SimpleNamespace(index={"nas": 0}, vectors=np.array([[-1], [1], [-1]]),
                            is_vowel=lambda segment: segment < 2)
    code = SimpleNamespace(phonology=SimpleNamespace(vocabulary={"root"}))
    group = SimpleNamespace(written=False, domain="home", population=10, main_code=code)
    world = SimpleNamespace(table=table, groups={"g": group},
                            unit_of=lambda _code, _unit: SimpleNamespace(form=(0, 1, 2)))
    result = metrics.underlying_inventory_proxy(world, ["g"])
    assert result == {"consonants": 1, "vowels": 2, "nasal_vowels": 1, "nasal_vowel": True}


def test_proxy_podkladove_tvary_a_psana_skupina():
    from cee.v2.language.lexicon import UnitForm
    from cee.v2.simulation import Simulation

    world = village_grid(2, seed=1, syntax=True)
    Simulation(world)  # naplní slovník bez spuštění evoluce
    spoken, written = sorted(world.groups.values(), key=lambda group: group.id)
    assert world.table is not None
    oral = world.table.parse("a")
    nasal = world.table.parse("ã")
    for group in (spoken, written):
        for unit in group.main_code.phonology.vocabulary:
            old = world.unit_of(group.main_code, unit)
            group.main_code.forms.set(unit, UnitForm(oral, len(oral), old.exponent))
    first = next(iter(sorted(spoken.main_code.phonology.vocabulary)))
    old = world.unit_of(spoken.main_code, first)
    spoken.main_code.forms.set(first, UnitForm(nasal, len(nasal), old.exponent))
    written.written = True
    result = metrics.underlying_inventory_proxy(world, [spoken.id, written.id])
    assert result is not None and result["nasal_vowels"] == 1
    spoken.main_code.forms.set(first, UnitForm(oral, len(oral), old.exponent))
    first_written = next(iter(sorted(written.main_code.phonology.vocabulary)))
    old = world.unit_of(written.main_code, first_written)
    written.main_code.forms.set(first_written, UnitForm(nasal, len(nasal), old.exponent))
    result = metrics.underlying_inventory_proxy(world, [spoken.id, written.id])
    assert result is not None and result["nasal_vowels"] == 0

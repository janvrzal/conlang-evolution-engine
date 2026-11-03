"""Instituce enginu v2 (milník M6a): psaný kód, čtení, škola a norma."""

import dataclasses

import numpy as np

from cee.v2 import institutions, syntax
from cee.v2.events import Codification, Schooling
from cee.v2.history import History
from cee.v2.language.constructions import Construction
from cee.v2.parameters import NEUTRAL_CHANNEL_DOMAINS
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.social import Norm
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid


def _world():
    world = village_grid(2, seed=1, syntax=True, semantics=True)
    Codification(0.0, "v00-00", tuple(world.group_ids())).apply(world, History(), 0)
    world.live.sync_groups(world)
    return world


def test_kodifikace_zmrazi_prevladajici_variantu_a_skupiny_ji_znaji():
    world = _world()
    written = world.groups["written:v00-00"]
    assert written.written and written.openness == 0.0
    assert world.renewal(written.id, 25.0) == 0.0
    assert all(world.groups[group].standard == written.id for group in ("v00-00", "v00-01"))
    assert all(
        distribution.is_fixed
        for variable in world.variables
        if (distribution := written.main_code.repertoire.get(variable)) is not None
    )


def test_cteni_prenasi_jen_slova_skola_hlavne_stavbu():
    world = _world()
    # Bez vah domén (s nimi čtení zvýhodní ``learned``, viz ``test_v2_domains``).
    world.params = dataclasses.replace(world.params, channel_domains=NEUTRAL_CHANNEL_DOMAINS)
    # Čtení šetří častá slova (``reading_core_resistance``), vzácná přináší skoro plně.
    lexical = [v for v, variable in world.variables.items() if variable.kind == "lexical"]
    assert institutions.reading_factor(world, "lexical:water") == 1.0 - world.concept_frequency("water")
    assert max(institutions.reading_factor(world, v) for v in lexical) == 1.0 - min(
        world.concept_frequency(v.split(":", 1)[1]) for v in lexical)
    world.params = dataclasses.replace(world.params, reading_core_resistance=0.0)
    assert institutions.reading_factor(world, "lexical:water") == 1.0
    assert institutions.reading_factor(world, "construction:NEG") == 0.0
    assert institutions.school_factor(world, "construction:NEG") == 1.0
    assert institutions.school_factor(world, "lexical:water") > 0
    assert institutions.SCHOOL["process"] < institutions.SCHOOL["construction"]


def _negation_batch(world):
    pre = syntax.construction_of(world, world.distribution("v00-01", "construction:NEG").dominant()[0])
    _, post = syntax.register(world, Construction("NEG", "post", "step"), Origin("test", 1, 25.0, "v00-01"))
    codified = syntax.register(world, pre, Origin(None, 0, 0.0, None))[1]
    return PressureBatch(
        world=world, variable_ids=["construction:NEG"], group_ids=["v00-01"],
        freqs=np.array([[[0.5, 0.5]]]), slots=[[codified.id, post.id]], tick=1,
        heard=np.array([[[0.5, 0.5]]]),
    )


def test_norma_bez_skoly_nepusobi_se_skolou_zvyhodni_kodifikovanou_variantu():
    world = _world()
    batch = _negation_batch(world)
    assert not Norm().scores(batch).any()
    Schooling(0.0, ("v00-01",), schooling=0.5).apply(world, History(), 0)
    scores = Norm().scores(_negation_batch(world))[0, 0]
    assert scores[0] == Norm.strength * 0.5 and scores[1] == 0.0

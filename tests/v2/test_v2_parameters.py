"""Kalibrační konstanty jako data světa: dva světy v jednom procesu se neovlivňují."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from cee.v2 import contact, syntax
from cee.v2.changes import DEFAULT_CHANGES, pressures_by_kind
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.morphology import Leveling, Rebracketing
from cee.v2.changes.syntax import CategoryLoss
from cee.v2.history import History
from cee.v2.language.constructions import Construction, catalog, catalog_for
from cee.v2.parameters import Parameters
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.syntactic import Ambiguity, Economy, Expressivity, Fusion, Learnability
from cee.v2.repertoire import Origin
from cee.v2.scenarios import Language, Place, contact_world, village_grid
from cee.v2.simulation import Simulation


def _world(params: Parameters | None = None):
    world = village_grid(1, seed=42, syntax=True, semantics=True, params=params)
    Simulation(world)
    group = world.groups[world.group_ids()[0]]
    return world, group, group.main_code


def _batch(world, group, function, constructions):
    variants = [syntax.register(world, item, Origin("test", 0, 0, None))[1] for item in constructions]
    share = 1.0 / len(variants)
    return PressureBatch(
        world=world,
        variable_ids=[f"construction:{function}"],
        group_ids=[group.id],
        freqs=np.full((1, 1, len(variants)), share),
        slots=[[variant.id for variant in variants]],
        tick=0,
        heard=np.full((1, 1, len(variants)), share),
    )


def test_vychozi_hodnoty_jsou_dosavadni_konstanty():
    params = Parameters()
    assert params.functional_load_scale == 5.0
    assert params.stress_strength_multiplier == 1.5
    assert params.coda_tolerance_scale == 0.0
    assert params.learnability_strength == 1.0
    assert params.economy_word_cost == 0.15
    assert params.fusion_bonus == 0.25
    assert params.order_rigidity == 0.05
    assert params.category_loss_l2_boost == 4.0
    assert len(params.grammar) == 0
    assert len(params.pressure_weights) == 0
    defaults = {
        "analogy_l2_boost": 4.0, "clarity_short_factor": 1.5, "dispersion_factor": 4.0,
        "interference_weight": 0.5, "school_correction": 0.8, "shift_rate": 1.0,
        "shift_exponent": 1.31, "child_threshold": 0.2, "reading_weight": 0.1,
        "school_weight": 0.3, "liturgy_weight": 0.1, "grammar_threshold": 0.85,
        "conserved_frequency": 0.7, "analogy_threshold": 0.85, "restructure_threshold": 0.85,
        "word_bias_sd": 1.5, "frequency_lead": 1.0, "closure_generations": 2.0,
        "activation_share": 0.05, "paradigm_merge_weight": 1.0, "redundant_merge_weight": 0.3,
    }
    for name, value in defaults.items():
        assert getattr(params, name) == value, name
    world, _, _ = _world()
    assert world.params == Parameters()


def test_parametry_jsou_nemenne_a_hashovatelne():
    params = Parameters(grammar={"DEFINITE": {"context": 0.4}})
    assert hash(params) == hash(Parameters(grammar={"DEFINITE": {"context": 0.4}}))
    assert params != Parameters()
    assert params.grammar["DEFINITE"]["context"] == 0.4
    with pytest.raises(FrozenInstanceError):
        params.fusion_bonus = 1.0  # type: ignore[misc]
    with pytest.raises(AttributeError):
        params.grammar["DEFINITE"]._items = ()  # type: ignore[index, attr-defined]
    assert copy.deepcopy(params) == params


def test_neznamy_prepis_gramatiky_je_chyba():
    with pytest.raises(ValueError):
        Parameters(grammar={"DEFINITE": {"weight": 0.4}})
    with pytest.raises(ValueError):
        catalog_for(Parameters(grammar={"NEEXISTUJE": {"need": 0.4}}))


def test_catalog_for_nemeni_globalni_katalog():
    before = copy.deepcopy(catalog())
    shared = catalog()
    world, _, _ = _world(Parameters(grammar={"DEFINITE": {"context": 0.4, "need": 0.9}}))
    local = catalog_for(world)
    assert local is not shared
    assert local["DEFINITE"].context == 0.4 and local["DEFINITE"].need == 0.9
    assert catalog() is shared and shared == before
    assert catalog()["DEFINITE"].context == before["DEFINITE"].context
    # Nepřepsané funkce zůstávají beze změny; bez přepisů je to sdílený katalog.
    assert local["PAST"] == before["PAST"]
    assert catalog_for(_world()[0]) is shared
    # Stejná hodnota parametrů sdílí katalog, jiná ne.
    assert catalog_for(Parameters(grammar={"DEFINITE": {"context": 0.4, "need": 0.9}})) is local
    assert catalog_for(Parameters(grammar={"DEFINITE": {"context": 0.5}})) is not local


def test_dva_svety_s_ruznym_katalogem_se_neovlivnuji():
    first, first_group, _ = _world()
    second, second_group, _ = _world(Parameters(grammar={"DEFINITE": {"context": 0.4}}))
    default_context = catalog()["DEFINITE"].context
    assert catalog_for(first)["DEFINITE"].context == default_context
    assert catalog_for(second)["DEFINITE"].context == 0.4
    zero = Construction("DEFINITE", "zero")
    # Síla nevyjádřené funkce je dána jejím kontextem (bez kompenzace).
    assert syntax.strength(first, first_group.main_code, zero, group_id=first_group.id) == default_context
    assert syntax.strength(second, second_group.main_code, zero, group_id=second_group.id) == 0.4
    # Pořadí nehraje roli: první svět je nedotčen i po vytvoření druhého.
    assert syntax.strength(first, first_group.main_code, zero, group_id=first_group.id) == default_context


def test_tlaky_ctou_parametry_sveho_sveta():
    first, first_group, first_code = _world()
    second, second_group, second_code = _world(Parameters(
        learnability_strength=2.0,
        economy_word_cost=0.3,
        fusion_bonus=0.5,
        order_rigidity=0.2,
        grammar={"DEFINITE": {"context": 0.4}},
    ))
    first_code.l2_share = second_code.l2_share = 0.5
    free = Construction("DEFINITE", "periphrastic", "that", "free")
    clitic = Construction("DEFINITE", "periphrastic", "that", "clitic")
    zero = Construction("DEFINITE", "zero")
    batches = {
        key: _batch(world, group, "DEFINITE", [zero, free, clitic])
        for key, (world, group) in {"first": (first, first_group), "second": (second, second_group)}.items()
    }

    learn = {key: Learnability().scores(batch)[0, 0] for key, batch in batches.items()}
    assert list(learn["first"]) == [0.0, 0.0, -0.5]
    assert list(learn["second"]) == [0.0, 0.0, -1.0]

    economy = {key: Economy().scores(batch)[0, 0] for key, batch in batches.items()}
    assert economy["first"][1] == pytest.approx(-0.15)
    assert economy["second"][1] == pytest.approx(-0.3)

    # Expressivity zero = need × context funkce.
    expressivity = {key: Expressivity().scores(batch)[0, 0] for key, batch in batches.items()}
    need = catalog()["DEFINITE"].need
    assert expressivity["first"][0] == pytest.approx(need * catalog()["DEFINITE"].context)
    assert expressivity["second"][0] == pytest.approx(need * 0.4)


def test_fusion_a_ambiguity_ctou_parametry(monkeypatch):
    first, first_group, _ = _world()
    second, second_group, _ = _world(Parameters(fusion_bonus=0.5, order_rigidity=0.2))
    free = Construction("DEFINITE", "periphrastic", "that", "free")
    clitic = Construction("DEFINITE", "periphrastic", "that", "clitic")
    # Ve skupině převažuje volný opis, takže o stupeň dál je přiklonka.
    monkeypatch.setattr(syntax, "dominant", lambda *_: free)
    fusion = []
    for world, group in ((first, first_group), (second, second_group)):
        fusion.append(Fusion().scores(_batch(world, group, "DEFINITE", [free, clitic]))[0, 0])
    assert list(fusion[0]) == [0.0, 0.25]
    assert list(fusion[1]) == [0.0, 0.5]

    # Ambiguity: pevný slovosled stojí `order_rigidity` × (1 - ztráta pádu).
    fixed = Construction("ORDER", "fixed", order="SOV")
    monkeypatch.setattr(syntax, "weakness", lambda *_: 0.0)
    ambiguity = []
    for world, group in ((first, first_group), (second, second_group)):
        ambiguity.append(Ambiguity().scores(_batch(world, group, "ORDER", [fixed]))[0, 0, 0])
    assert ambiguity[0] == pytest.approx(-0.05 * len(syntax.catalog_for(first)["ORDER"].compensates))
    assert ambiguity[1] == pytest.approx(-0.2 * len(syntax.catalog_for(second)["ORDER"].compensates))


def test_category_loss_cte_l2_boost_sveta():
    first, first_group, first_code = _world()
    second, second_group, second_code = _world(Parameters(category_loss_l2_boost=10.0))
    first_code.l2_share = second_code.l2_share = 0.5
    loss = CategoryLoss()
    construction = Construction("PL", "synthetic")
    pressure = []
    for world, group in ((first, first_group), (second, second_group)):
        context = InnovationContext(world, group, group.main_code, 1, 25.0)
        pressure.append(loss._pressure(context, construction))
    assert pressure == [pytest.approx(4.0 * 0.5), pytest.approx(10.0 * 0.5)]


def test_kopie_stavu_a_vetev_zachovavaji_parametry():
    params = Parameters(learnability_strength=2.0, grammar={"DEFINITE": {"context": 0.4}})
    world, _, _ = _world(params)
    clone = copy.deepcopy(world)
    assert clone.params == params
    assert catalog_for(clone)["DEFINITE"].context == 0.4


def test_contact_world_nese_parametry():
    params = Parameters(grammar={"DEFINITE": {"context": 0.4}})
    world = contact_world([Language("proto", (Place("a", (0.0, 0.0)),))], seed=1, params=params)
    assert world.params is params
    assert contact_world([Language("proto", (Place("a", (0.0, 0.0)),))], seed=1).params == Parameters()


def test_prechod_cte_parametry_sveho_sveta():
    def moved(params: Parameters) -> tuple[int, bool]:
        place = (Place("a", (0.0, 0.0), population=500, prestige=1.0),
                 Place("b", (10.0, 0.0), population=500, prestige=0.3))
        world = contact_world([Language("proto", place)], seed=1, params=params)
        contact._shift(world, "a", "b", 0.04, 1, 25.0, History())
        return world.groups["a"].population, world.groups["b"].transmitted

    fast = Parameters(shift_rate=3.0, child_threshold=0.9)
    first, second, third = moved(Parameters()), moved(fast), moved(Parameters())
    assert first == third and first != second
    # Práh předávání dětem platí jen ve světě, který ho změnil.
    assert first[1] is True and second[1] is False


def test_prah_zapisu_a_vahy_vstupu_jsou_na_svete():
    first, _, _ = _world()
    second, _, _ = _world(Parameters(grammar_threshold=0.5, word_bias_sd=0.1, interference_weight=0.9))
    assert first.params.grammar_threshold == 0.85 and second.params.grammar_threshold == 0.5
    assert first.params.interference_weight == 0.5 and second.params.interference_weight == 0.9


def test_analogie_cte_l2_boost_sveta():
    first, first_group, first_code = _world()
    second, second_group, second_code = _world(Parameters(analogy_l2_boost=10.0))
    first_code.l2_share = second_code.l2_share = 0.5
    change = Leveling()
    scales = [
        change.rate_scale(InnovationContext(world, group, group.main_code, 1, 25.0))
        for world, group in ((first, first_group), (second, second_group))
    ]
    assert scales == [pytest.approx(1.0 + 4.0 * 0.5), pytest.approx(1.0 + 10.0 * 0.5)]
    context = InnovationContext(second, second_group, second_group.main_code, 1, 25.0)
    assert Rebracketing().rate_scale(context) == 1.0


def test_pressure_weights_prepisuji_vahy_tlaku_jen_ve_svem_svete():
    def weights(table):
        return {kind: {p.name: w for p, w in items} for kind, items in table.items()}

    before = weights(pressures_by_kind(DEFAULT_CHANGES, Parameters()))
    assert before == weights(pressures_by_kind(DEFAULT_CHANGES))
    after = weights(pressures_by_kind(DEFAULT_CHANGES, Parameters(pressure_weights={"clarity": 0.25, "norm": 2.0})))
    assert after != before
    for kind, items in after.items():
        assert items["norm"] == 2.0
        if "clarity" in items:
            assert items["clarity"] == 0.25
        assert {name: w for name, w in items.items() if name not in ("clarity", "norm")} == {
            name: w for name, w in before[kind].items() if name not in ("clarity", "norm")
        }
    with pytest.raises(ValueError, match="Neznámé tlaky"):
        pressures_by_kind(DEFAULT_CHANGES, Parameters(pressure_weights={"neexistuje": 1.0}))


def test_change_rates_meni_tempo_jen_vybrane_zmeny():
    """Násobek tempa 0 vypne inovace jedné změny, ostatní zůstanou; neznámá změna se odmítne."""

    def innovations(params):
        simulation = Simulation(village_grid(3, seed=4, phonology=True, params=params))
        simulation.run(500)
        return [event["change"] for event in simulation.history.of_kind("innovation")]

    default = innovations(Parameters())
    assert "voicing" in default
    silenced = innovations(Parameters(change_rates={"voicing": 0.0}))
    assert "voicing" not in silenced
    assert set(silenced) - {"voicing"}
    assert Parameters().change_rates == {}
    with pytest.raises(ValueError, match="neznámých změn"):
        Simulation(village_grid(2, seed=4, phonology=True, params=Parameters(change_rates={"neexistuje": 2.0})))

"""Jednotkové testy pro zánik kategorie (CategoryLoss, krok C3).

Ověřuje:
1. CategoryLoss je s výchozím katalogem neaktivní (efektivní potřeba > 0,15, slabost <= 0,15).
2. Spuštění větve (a): syntetická konstrukce s vysokou slabostí (weakness >= 0,5).
3. Spuštění větve (b): volný opis (words = 1) s nízkou efektivní potřebou (<= 0,15).
4. Selekce rozhoduje ve prospěch zero při nízké efektivní potřebě (Economy -0,15 převáží).
5. Selekce rozhoduje ve prospěch zero při vysoké erozní slabosti (weakness > 1 - context).
"""

from dataclasses import replace

import numpy as np

from cee.v2 import morphology, syntax
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.syntax import CategoryLoss
from cee.v2.language.constructions import Construction, catalog
from cee.v2.language.lexicon import UnitForm
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.syntactic import Economy, Expressivity
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation


def _world():
    world = village_grid(1, seed=42, syntax=True, semantics=True)
    Simulation(world)
    group = world.groups[world.group_ids()[0]]
    return world, group, group.main_code


def _context(world, group):
    return InnovationContext(world, group, group.main_code, 1, 25.0)


def test_category_loss_neaktivni_ve_vychozim_stavu():
    """S dnešním katalogem a neporušenou gramatikou je CategoryLoss zcela neaktivní."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()

    # 1. Syntetické kategorie (PAST, PL): slabost je <= 0,15 (< 0,5)
    for func in ("PAST", "PL"):
        current = Construction(func, "synthetic")
        assert not cat_loss.applies(context, current)

    # 2. Volné opisy (DEFINITE, FUTURE, PAST, PL): efektivní potřeba je vždy > 0,15
    # DEF: 0,25 * (1 - 0,22) = 0,195 > 0,15
    # FUT: 0,40 * (1 - 0,35) = 0,260 > 0,15
    # PL:  0,60 * (1 - 0,30) = 0,420 > 0,15
    # PAST: 1,0 * (1 - 0,25) = 0,750 > 0,15
    for func, src in (("DEFINITE", "that"), ("FUTURE", "go"), ("PAST", "have"), ("PL", "thing")):
        free = Construction(func, "periphrastic", src, "free")
        assert not cat_loss.applies(context, free)

    # 3. Přiklonky a nulový tvar: CategoryLoss se na ně nevztahuje
    clitic = Construction("DEFINITE", "periphrastic", "that", "clitic")
    assert not cat_loss.applies(context, clitic)
    zero = Construction("DEFINITE", "zero")
    assert not cat_loss.applies(context, zero)

    # V žádné skupině nenajde místo
    assert not cat_loss.sites(context)


def test_category_loss_vetev_synteticka_pri_vysoke_slabosti():
    """Větev (a): syntetická koncovka se slabostí >= 0,5 navrhne zánik do zero."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()
    rng = np.random.default_rng(123)

    # Erodujeme koncovky minulého času (nahradíme citačním tvarem)
    for unit in sorted(code.phonology.vocabulary):
        if world.morphemes[unit].cell == "PAST":
            citation = morphology.citation_form(world, code, unit)
            code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
    code.phonology.version += 1

    assert syntax.weakness(world, code, "PAST") >= 0.5
    current = Construction("PAST", "synthetic")
    assert cat_loss.applies(context, current)

    proposed = cat_loss.next(context, current, rng)
    assert proposed == Construction("PAST", "zero")


def test_category_loss_vetev_volny_opis_pri_nizke_potrebe():
    """Větev (b): volný opis s efektivní potřebou <= 0,15 navrhne zánik do zero."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()
    rng = np.random.default_rng(456)

    cat = catalog()
    orig_def = cat["DEFINITE"]
    try:
        # Simulujeme situaci s vysokým kontextem (context = 0.45 -> eff_need = 0.25 * 0.55 = 0.1375 <= 0.15)
        cat["DEFINITE"] = replace(orig_def, context=0.45)
        current = Construction("DEFINITE", "periphrastic", "that", "free")
        assert cat_loss.applies(context, current)

        proposed = cat_loss.next(context, current, rng)
        assert proposed == Construction("DEFINITE", "zero")
    finally:
        cat["DEFINITE"] = orig_def


def test_selekce_rozhoduje_ve_prospech_zero_pri_nizke_potrebe():
    """Při efektivní potřebě <= 0,15 penalizace Economy (-0,15) způsobí, že zero má vyšší fitness."""
    world, group, code = _world()
    cat = catalog()
    orig_def = cat["DEFINITE"]
    try:
        # Nastavíme context = 0.50 (need 0.25 -> eff_need = 0.125 < 0.15)
        cat["DEFINITE"] = replace(orig_def, context=0.50)

        zero_var = syntax.register(world, Construction("DEFINITE", "zero"), Origin("test", 0, 0, None))[1]
        free_var = syntax.register(world, Construction("DEFINITE", "periphrastic", "that", "free"), Origin("test", 0, 0, None))[1]

        batch = PressureBatch(
            world=world,
            variable_ids=["construction:DEFINITE"],
            group_ids=[group.id],
            freqs=np.array([[[0.5, 0.5]]]),
            slots=[[zero_var.id, free_var.id]],
            tick=0,
            heard=np.array([[[0.5, 0.5]]]),
        )

        exp_scores = Expressivity().scores(batch)[0, 0]
        eco_scores = Economy().scores(batch)[0, 0]

        # zero: Expressivity = 0.25 * 0.50 = 0.125, Economy = 0.0 -> celkem 0.125
        # free: Expressivity = 0.25 * 1.00 = 0.250, Economy = -0.15 -> celkem 0.100
        total_zero = exp_scores[0] + eco_scores[0]
        total_free = exp_scores[1] + eco_scores[1]

        assert total_zero > total_free, f"Zero ({total_zero}) musí mít vyšší fitness než volný opis ({total_free})"
    finally:
        cat["DEFINITE"] = orig_def


def test_selekce_rozhoduje_ve_prospech_zero_pri_erodovane_synteze():
    """Když slabost koncovky překročí 1 - context, syntéza ztrácí expressivity a zero vítězí."""
    world, group, code = _world()
    cat = catalog()
    orig_past = cat["PAST"]
    try:
        # PAST má need = 1.0, context = 0.25. Hranice je 1 - 0.25 = 0.75.
        # Simulujeme extrémní erozi (weakness = 0.90).
        for unit in sorted(code.phonology.vocabulary):
            if world.morphemes[unit].cell == "PAST":
                citation = morphology.citation_form(world, code, unit)
                code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
        code.phonology.version += 1

        assert syntax.weakness(world, code, "PAST") >= 0.75

        zero_var = syntax.register(world, Construction("PAST", "zero"), Origin("test", 0, 0, None))[1]
        syn_var = syntax.register(world, Construction("PAST", "synthetic"), Origin("test", 0, 0, None))[1]

        batch = PressureBatch(
            world=world,
            variable_ids=["construction:PAST"],
            group_ids=[group.id],
            freqs=np.array([[[0.5, 0.5]]]),
            slots=[[zero_var.id, syn_var.id]],
            tick=0,
            heard=np.array([[[0.5, 0.5]]]),
        )

        exp_scores = Expressivity().scores(batch)[0, 0]

        # Obě mají words = 0 -> Economy = 0.
        # zero: Expressivity = 1.0 * 0.25 = 0.25
        # syn:  Expressivity = 1.0 * (1 - 1.0) = 0.0
        assert exp_scores[0] > exp_scores[1], f"Zero ({exp_scores[0]}) musí mít vyšší Expressivity než erodovaná syntéza ({exp_scores[1]})"
    finally:
        cat["PAST"] = orig_past

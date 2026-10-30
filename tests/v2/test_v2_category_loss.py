"""Jednotkové testy pro zánik kategorie (CategoryLoss, kroky C3 a E).

Ověřuje:
1. Neporušená koncovka bez L2 mluvčích nemá důvod zaniknout; volný opis ano.
2. Míra návrhu roste se slabostí koncovky (žádný práh).
3. L2 mluvčí navrhují vypuštění vázaného výrazu i bez eroze.
4. Selekce rozhoduje ve prospěch zero při nízké potřebě (Economy -0,15 převáží).
5. Selekce rozhoduje ve prospěch zero při vysoké erozní slabosti (weakness > 1 - context).
6. Learnability znevýhodní vázané výrazy úměrně podílu L2 mluvčích.
"""

from dataclasses import replace

import numpy as np

from cee.v2 import morphology, syntax
from cee.v2.changes.base import InnovationContext
from cee.v2.changes.syntax import CategoryLoss
from cee.v2.language.constructions import Construction, catalog
from cee.v2.language.lexicon import UnitForm
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.syntactic import LEARNABILITY_STRENGTH, Economy, Expressivity, Learnability
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


def _erode_past(world, code):
    for unit in sorted(code.phonology.vocabulary):
        if world.morphemes[unit].cell == "PAST":
            citation = morphology.citation_form(world, code, unit)
            code.forms.set(unit, UnitForm(citation, len(citation), world.unit_of(code, unit).exponent))
    code.phonology.version += 1


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


def test_neporusena_koncovka_bez_l2_nema_duvod_zaniknout():
    """Bez eroze a bez L2 mluvčích se vázaný výraz nenavrhuje k vypuštění; volný opis ano."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()

    for func in ("PAST", "PL"):
        assert syntax.weakness(world, code, func) == 0.0
        assert not cat_loss.applies(context, Construction(func, "synthetic"))
    assert not cat_loss.applies(context, Construction("DEFINITE", "periphrastic", "that", "clitic"))
    assert not cat_loss.applies(context, Construction("DEFINITE", "zero"))
    assert cat_loss.applies(context, Construction("DEFINITE", "periphrastic", "that", "free"))
    # Výchozí gramatika má jen neporušené koncovky: žádné místo.
    assert not cat_loss.sites(context)


def test_mira_navrhu_roste_se_slabosti_koncovky():
    """Míra návrhu je úměrná slabosti koncovky; návrh je zero."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()
    _erode_past(world, code)

    weakness = syntax.weakness(world, code, "PAST")
    assert weakness > 0.0
    assert cat_loss.sites(context) == ["construction:PAST"]
    assert cat_loss.rate(context, "construction:PAST") == cat_loss.base_rate * weakness
    proposed = cat_loss.next(context, Construction("PAST", "synthetic"), np.random.default_rng(123))
    assert proposed == Construction("PAST", "zero")


def test_l2_mluvci_navrhuji_vypusteni_vazaneho_vyrazu():
    """L2 mluvčí navrhují vypuštění koncovky i přiklonky bez eroze."""
    world, group, code = _world()
    context = _context(world, group)
    cat_loss = CategoryLoss()
    code.l2_share = 0.5

    clitic = Construction("DEFINITE", "periphrastic", "that", "clitic")
    assert cat_loss.applies(context, clitic)
    assert cat_loss.applies(context, Construction("PL", "synthetic"))
    assert cat_loss.rate(context, "construction:PL") == cat_loss.base_rate * cat_loss.l2_boost * 0.5


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


def test_learnability_znevyhodni_vazane_vyrazy_podle_podilu_l2():
    """Koncovka a přiklonka ztrácejí úměrně podílu L2 mluvčích; volné slovo a zero ne."""
    world, group, code = _world()
    constructions = [
        Construction("DEFINITE", "zero"),
        Construction("DEFINITE", "periphrastic", "that", "free"),
        Construction("DEFINITE", "periphrastic", "that", "clitic"),
    ]
    batch = _batch(world, group, "DEFINITE", constructions)
    assert not Learnability().scores(batch).any()

    code.l2_share = 0.5
    scores = Learnability().scores(batch)[0, 0]
    assert list(scores) == [0.0, 0.0, -LEARNABILITY_STRENGTH * 0.5]


def test_pri_plne_l2_skupine_vyhraje_zero_nad_neporusenou_koncovkou():
    """Ve skupině samých L2 mluvčích převáží Learnability výhodu koncovky plurálu."""
    world, group, code = _world()
    code.l2_share = 1.0
    batch = _batch(world, group, "PL", [Construction("PL", "zero"), Construction("PL", "synthetic")])
    total = Expressivity().scores(batch)[0, 0] + Learnability().scores(batch)[0, 0]
    assert total[0] > total[1]

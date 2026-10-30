"""Testy prozódie: pravidla přízvuku a typologické měření (krok D1)."""

import pytest

from cee.v2 import metrics
from cee.v2.language.processes import stressed_nucleus
from cee.v2.language.segments import SegmentTable
from cee.v2.scenarios import village_grid


@pytest.fixture
def table() -> SegmentTable:
    return SegmentTable()


def test_stressed_nucleus_vsechna_pravidla(table: SegmentTable) -> None:
    # 4 slabiky: a.ba.ka.da
    # Jádra jsou na indexech 0, 2, 4, 6
    w4 = table.parse("abakada")
    assert stressed_nucleus(w4, table, "initial") == 0
    assert stressed_nucleus(w4, table, "second") == 2
    assert stressed_nucleus(w4, table, "antepenult") == 2  # -3 z 4 je druhá slabika (index 2)
    assert stressed_nucleus(w4, table, "penult") == 4     # -2 z 4 je třetí slabika (index 4)
    assert stressed_nucleus(w4, table, "final") == 6

    # 3 slabiky: ba.ka.da
    # Jádra: 1, 3, 5
    w3 = table.parse("bakada")
    assert stressed_nucleus(w3, table, "initial") == 1
    assert stressed_nucleus(w3, table, "second") == 3
    assert stressed_nucleus(w3, table, "antepenult") == 1  # -3 z 3 je první slabika
    assert stressed_nucleus(w3, table, "penult") == 3     # -2 z 3 je druhá slabika
    assert stressed_nucleus(w3, table, "final") == 5

    # 2 slabiky: ba.ka
    # Jádra: 1, 3
    w2 = table.parse("baka")
    assert stressed_nucleus(w2, table, "initial") == 1
    assert stressed_nucleus(w2, table, "second") == 3
    assert stressed_nucleus(w2, table, "antepenult") == 1  # méně než 3 slabiky -> fallback na první
    assert stressed_nucleus(w2, table, "penult") == 1     # předposlední ze dvou je první
    assert stressed_nucleus(w2, table, "final") == 3

    # 1 slabika: ba
    w1 = table.parse("ba")
    for rule in ("initial", "second", "antepenult", "penult", "final"):
        assert stressed_nucleus(w1, table, rule) == 1  # jediná slabika nese přízvuk vždy


def test_typologicke_meridlo_14a() -> None:
    world = village_grid(3, seed=1, syntax=True)
    groups = sorted(world.groups.values(), key=lambda g: g.id)

    # Výchozí stav: penult -> 14A-6
    profile = metrics.typology_profile(world, [g.id for g in groups])
    assert profile["14A"] == "14A-6"

    # Změna u 2 ze 3 vesnic na initial -> 14A-2
    groups[0].main_code.stress_rule = "initial"
    groups[1].main_code.stress_rule = "initial"
    profile = metrics.typology_profile(world, [g.id for g in groups])
    assert profile["14A"] == "14A-2"

    # Změna na final -> 14A-7
    for g in groups:
        g.main_code.stress_rule = "final"
    profile = metrics.typology_profile(world, [g.id for g in groups])
    assert profile["14A"] == "14A-7"


def test_stress_shift_and_strength_propose_and_restructure() -> None:
    import numpy as np

    from cee.v2 import prosody
    from cee.v2.changes.base import InnovationContext
    from cee.v2.changes.prosody import StressShift, StressStrengthChange
    from cee.v2.history import History
    from cee.v2.repertoire import Distribution

    world = village_grid(2, seed=42, syntax=True)
    group = world.groups["v00-00"]
    code = group.main_code
    assert code.stress_rule == "penult"
    assert code.stress_strength == "weak"

    ctx = InnovationContext(world, group, code, tick=1, year=25.0)
    rng = np.random.default_rng(123)

    # 1. StressShift propose
    shift = StressShift()
    assert shift.sites(ctx) == ("prosody:stress_rule",)
    var = shift.propose(ctx, "prosody:stress_rule", rng, 0)
    assert var is not None
    proposed_rule = var.payload["rule"]
    assert proposed_rule in ("initial", "antepenult")

    # Restructure without dominance change: no change
    history = History()
    prosody.restructure(world, group.id, 1, history, 25.0)
    assert code.stress_rule == "penult"
    assert len(history.events) == 0

    # Dominance change: distribution sets proposed rule to 100%
    group.main_code.repertoire.set("prosody:stress_rule", Distribution.fixed(var.id))
    old_version = code.phonology.version
    prosody.restructure(world, group.id, 2, history, 50.0)
    assert code.stress_rule == proposed_rule
    assert code.phonology.version > old_version
    assert len(history.events) == 1
    assert history.events[0]["kind"] == "stress_rule_changed"
    assert history.events[0]["old"] == "penult"
    assert history.events[0]["new"] == proposed_rule

    # 2. StressStrengthChange propose
    strength_change = StressStrengthChange()
    assert strength_change.sites(ctx) == ("prosody:stress_strength",)
    var_strength = strength_change.propose(ctx, "prosody:stress_strength", rng, 0)
    assert var_strength is not None
    assert var_strength.payload["strength"] == "strong"

    # Dominance change to strong
    group.main_code.repertoire.set("prosody:stress_strength", Distribution.fixed(var_strength.id))
    prosody.restructure(world, group.id, 3, history, 75.0)
    assert code.stress_strength == "strong"
    assert len(history.events) == 2
    assert history.events[1]["kind"] == "stress_strength_changed"
    assert history.events[1]["old"] == "weak"
    assert history.events[1]["new"] == "strong"


def test_articulation_stress_strength_multiplier() -> None:
    from types import SimpleNamespace

    import numpy as np

    from cee.v2.language.processes import Process
    from cee.v2.language.segments import default_table
    from cee.v2.pressures import linguistic
    from cee.v2.pressures.base import PressureBatch
    from cee.v2.pressures.linguistic import Articulation

    table = default_table()
    # Reductive unstressed process (e.g. Apocope / VowelReduction)
    p_reductive = Process(
        family="vowel_reduction",
        target=table.VOWEL,
        operation="replace",
        segment=table.parse("ə")[0],
        stress="unstressed",
        ease=0.15,
        clarity=-0.2,
        reductive=True,
    )
    # Non-reductive or stressed process
    p_normal = Process(
        family="palatalization",
        target=table.CONSONANT,
        operation="replace",
        segment=table.parse("t")[0],
        stress=None,
        ease=0.10,
        clarity=-0.05,
        reductive=False,
    )

    var_reductive = "process:" + p_reductive.key
    var_normal = "process:" + p_normal.key
    processes = {var_reductive: p_reductive, var_normal: p_normal}

    group_weak = SimpleNamespace(main_code=SimpleNamespace(stress_strength="weak"))
    group_strong = SimpleNamespace(main_code=SimpleNamespace(stress_strength="strong"))
    groups = {"g_weak": group_weak, "g_strong": group_strong}
    world = SimpleNamespace(processes=processes, groups=groups)

    freqs = np.zeros((2, 2, 2))
    freqs[0, :, 1] = 0.5  # variable 0 (reductive) reached by g_weak and g_strong
    freqs[1, :, 1] = 0.5  # variable 1 (normal) reached by g_weak and g_strong

    from cee.v2.phonology import changed_id
    batch = PressureBatch(
        world=world,  # type: ignore[arg-type]
        variable_ids=(var_reductive, var_normal),
        group_ids=("g_weak", "g_strong"),
        freqs=freqs,
        slots=((None, changed_id(var_reductive)), (None, changed_id(var_normal))),
        tick=1,
        heard=np.zeros_like(freqs),
        memo={
            (var_reductive, 0): SimpleNamespace(),
            (var_reductive, 1): SimpleNamespace(),
            (var_normal, 0): SimpleNamespace(),
            (var_normal, 1): SimpleNamespace(),
        },
    )

    art = Articulation()
    # Test with STRESS_STRENGTH_MULTIPLIER = 1.5
    linguistic.STRESS_STRENGTH_MULTIPLIER = 1.5
    scores = art.scores(batch)

    # Reductive unstressed process:
    # g_weak gets 0.15 * 1.0 = 0.15
    # g_strong gets 0.15 * 1.5 = 0.225
    assert np.isclose(scores[0, 0, 1], 0.15)
    assert np.isclose(scores[0, 1, 1], 0.225)

    # Normal process: both get 0.10
    assert np.isclose(scores[1, 0, 1], 0.10)
    assert np.isclose(scores[1, 1, 1], 0.10)

    # Test sensitivity propagation: change STRESS_STRENGTH_MULTIPLIER to 2.0
    linguistic.STRESS_STRENGTH_MULTIPLIER = 2.0
    batch.memo.pop(linguistic._PROCESS_SCORE_LAYOUT_KEY, None)
    scores2 = art.scores(batch)
    assert np.isclose(scores2[0, 1, 1], 0.30)  # 0.15 * 2.0 = 0.30

    # Restore default
    linguistic.STRESS_STRENGTH_MULTIPLIER = 1.5

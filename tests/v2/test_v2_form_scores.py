"""Hromadné morfologické tlaky proti původní skalární cestě."""

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import cee.v2.pressures.morphological as morphological
from cee.v2.language.morphology import FormChange
from cee.v2.morphology import FormAssessment
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import PressureBatch

PRESSURES = (
    morphological.Uniformity(),
    morphological.Conservation(),
    morphological.Teachability(),
    morphological.Distinctiveness(),
)


def _assessment(
    gain: float,
    frequency: float,
    before: bool = False,
    after: bool = False,
) -> FormAssessment:
    return FormAssessment(gain, frequency, before, after)


def _make_batch(*, l2_shares: tuple[float, ...] = (0.5, 0.0, 1.0)) -> PressureBatch:
    variables = ("form:v0", "form:v1", "form:v2")
    changes = {
        variables[0]: FormChange("level", "unit0"),
        variables[1]: FormChange("extend", "unit1", exponent="exp"),
        variables[2]: FormChange("prepend", "unit2", segment=3),
    }
    groups = {
        f"g{index}": SimpleNamespace(main_code=SimpleNamespace(l2_share=share))
        for index, share in enumerate(l2_shares)
    }
    world = SimpleNamespace(form_changes=changes, groups=groups)
    freqs = np.zeros((3, 3, 4))
    heard = np.zeros_like(freqs)
    freqs[0, 0, 1] = 0.2
    heard[0, 2, 1] = 0.3
    freqs[1, 1, 2] = 0.4
    heard[1, 2, 2] = 0.5
    freqs[2, 0, 0] = 0.6
    heard[2, 1, 0] = 0.7
    freqs[2, 2, 2] = 0.8  # Dosažený nesprávný slot se ignoruje.
    memo = {("form", variables[0], 0): None}
    return PressureBatch(
        world=world,  # type: ignore[arg-type]
        variable_ids=variables,
        group_ids=("g0", "g1", "g2"),
        freqs=freqs,
        slots=(
            ("other", changed_id(variables[0]), changed_id(variables[0]), None),
            ("other", None, changed_id(variables[1]), changed_id(variables[1])),
            (changed_id(variables[2]), None, "other", None),
        ),
        tick=10,
        heard=heard,
        memo=memo,
    )


def _assessment_for(variable_id: str, group_id: str) -> FormAssessment | None:
    values = {
        ("form:v0", "g2"): _assessment(-0.0, float("nan"), True, False),
        ("form:v1", "g1"): _assessment(float("inf"), -0.0, False, True),
        ("form:v1", "g2"): _assessment(float("nan"), float("inf"), True, False),
        ("form:v2", "g0"): _assessment(-0.0, 0.75, False, False),
        ("form:v2", "g1"): None,
    }
    return values[(variable_id, group_id)]


def _scalar_value(pressure: Any, change: FormChange, assessment: FormAssessment) -> float:
    if isinstance(pressure, morphological.Uniformity):
        return 0.4 if change.operation == "level" else 0.35 * assessment.gain
    if isinstance(pressure, morphological.Conservation):
        return 0.0 if change.lexeme_wide else -0.6 * (2.0 * assessment.frequency - 1.0)
    if isinstance(pressure, morphological.Teachability):
        return 0.0 if change.lexeme_wide else pressure.strength
    if assessment.syncretic_after and not assessment.syncretic_before:
        return -0.8
    if assessment.syncretic_before and not assessment.syncretic_after:
        return 0.6
    return 0.0


EXPECTED_ASSESS_CALLS = [
    ("form:v0", "g2"),
    ("form:v1", "g1"),
    ("form:v1", "g2"),
    ("form:v2", "g0"),
    ("form:v2", "g1"),
]


@pytest.mark.parametrize("pressure", PRESSURES)
def test_hromadny_tlak_shodny_se_scalarni_referenci_a_poradim(monkeypatch, pressure) -> None:
    calls: list[tuple[str, str]] = []

    def assess(_world, group_id, variable_id):
        calls.append((variable_id, group_id))
        return _assessment_for(variable_id, group_id)

    monkeypatch.setattr(morphological, "assess", assess)
    actual_batch = _make_batch()
    seeded = actual_batch.memo[("form", "form:v0", 0)]
    actual = pressure.scores(actual_batch)
    assert calls == EXPECTED_ASSESS_CALLS

    reference_batch = _make_batch()
    expected = morphological._form_scores_reference(
        reference_batch,
        lambda change, assessment: _scalar_value(pressure, change, assessment),
    )
    if isinstance(pressure, morphological.Teachability):
        shares = np.array([0.5, 0.0, 1.0])
        expected *= shares[None, :, None]
    assert calls[-len(EXPECTED_ASSESS_CALLS):] == EXPECTED_ASSESS_CALLS
    assert np.array_equal(actual, expected, equal_nan=True)
    np.testing.assert_array_equal(np.signbit(actual), np.signbit(expected))
    assert actual_batch.memo[("form", "form:v0", 0)] is seeded
    assert ("_cee_form_score_layout_v1",) in actual_batch.memo
    assert actual[0, 0, 1] == 0.0 and not np.signbit(actual[0, 0, 1])
    assert actual[2, 1, 0] == 0.0 and not np.signbit(actual[2, 1, 0])
    if isinstance(pressure, morphological.Uniformity):
        assert actual[2, 0, 0] == 0.0 and np.signbit(actual[2, 0, 0])


def test_sdileny_layout_assessmenty_opakuji_jen_jednou(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def assess(_world, group_id, variable_id):
        calls.append((variable_id, group_id))
        return _assessment_for(variable_id, group_id)

    monkeypatch.setattr(morphological, "assess", assess)
    batch = _make_batch()
    for pressure in PRESSURES:
        pressure.scores(batch)
    assert calls == EXPECTED_ASSESS_CALLS


def test_teachability_l2_nula_vraci_zeros_bez_assessmentu(monkeypatch) -> None:
    def unexpected_assess(*_args):
        raise AssertionError("při nulovém podílu L2 se assessment nevolá")

    monkeypatch.setattr(morphological, "assess", unexpected_assess)
    batch = _make_batch(l2_shares=(0.0, -0.0, 0.0))
    actual = morphological.Teachability().scores(batch)
    np.testing.assert_array_equal(actual, np.zeros_like(batch.freqs))
    assert ("_cee_form_score_layout_v1",) not in batch.memo

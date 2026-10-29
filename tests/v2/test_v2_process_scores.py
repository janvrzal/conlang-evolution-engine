"""Hromadné jazykové tlaky proti původní skalární cestě."""

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

import cee.v2.pressures.linguistic as linguistic
from cee.v2.assessment import ProcessAssessment
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import PressureBatch

PRESSURES = (
    linguistic.Articulation(),
    linguistic.Clarity(),
    linguistic.FunctionalLoad(),
    linguistic.Dispersion(),
    linguistic.Phonotactics(),
)


def _assessment(
    *, short: float = 0.0, merge: float = 0.0, dispersion: float = 0.0, marked: float = 0.0
) -> ProcessAssessment:
    return ProcessAssessment(0.1, merge, short, marked, dispersion)


def _make_batch() -> PressureBatch:
    variable0, variable1 = "process:p0", "process:p1"
    processes = {
        variable0: SimpleNamespace(ease=-0.0, clarity=float("nan")),
        variable1: SimpleNamespace(ease=float("inf"), clarity=0.5),
    }
    freqs = np.zeros((2, 3, 4))
    heard = np.zeros_like(freqs)
    freqs[0, 0, 1] = 0.2  # Jiż existuje memo; nový layout ho nesmí přepočítat.
    heard[0, 2, 1] = 0.3
    freqs[1, 0, 2] = 0.4
    heard[1, 1, 2] = 0.5
    freqs[1, 2, 0] = 0.6  # dosažený jiný slot nesmí být hodnocen.
    memo = {(variable0, 0): _assessment(short=float("nan"), merge=float("nan"), marked=-0.0)}
    return PressureBatch(
        world=SimpleNamespace(processes=processes),  # type: ignore[arg-type]
        variable_ids=(variable0, variable1),
        group_ids=("g0", "g1", "g2"),
        freqs=freqs,
        slots=(("other", changed_id(variable0), changed_id(variable0), None),
               (None, "other", changed_id(variable1), changed_id(variable1))),
        tick=16,
        heard=heard,
        memo=memo,
    )


def _assessment_for(variable_id: str, group_id: str) -> ProcessAssessment:
    values = {
        ("process:p0", "g2"): _assessment(
            short=float("inf"), merge=float("inf"), dispersion=float("-inf"), marked=float("inf")
        ),
        ("process:p1", "g0"): _assessment(
            short=float("-inf"), merge=-0.0, dispersion=0.0, marked=-0.0
        ),
        ("process:p1", "g1"): _assessment(
            short=0.25, merge=float("nan"), dispersion=float("nan"), marked=float("-inf")
        ),
    }
    return values[(variable_id, group_id)]


def _scalar_value(pressure: Any, process: Any, assessment: ProcessAssessment) -> float:
    if isinstance(pressure, linguistic.Articulation):
        return process.ease
    if isinstance(pressure, linguistic.Clarity):
        return float(np.clip(process.clarity - 1.5 * assessment.short_share, -1.0, 1.0))
    if isinstance(pressure, linguistic.FunctionalLoad):
        return -float(min(1.0, linguistic.FUNCTIONAL_LOAD_SCALE * assessment.merge_mass))
    if isinstance(pressure, linguistic.Dispersion):
        return float(np.clip(4.0 * assessment.dispersion_delta, -1.0, 1.0))
    assert isinstance(pressure, linguistic.Phonotactics)
    return -float(np.clip(assessment.markedness_delta, -1.0, 1.0))


@pytest.mark.parametrize("pressure", PRESSURES)
def test_vectorovy_tlak_shodny_se_scalarni_referenci_a_poradim(monkeypatch, pressure) -> None:
    calls: list[tuple[str, list[str], int]] = []

    def assess_many(world, group_ids, variable_id, tick):
        calls.append((variable_id, list(group_ids), tick))
        return [_assessment_for(variable_id, group_id) for group_id in group_ids]

    monkeypatch.setattr(linguistic, "assess_many", assess_many)
    actual_batch = _make_batch()
    seeded = actual_batch.memo[("process:p0", 0)]
    actual = pressure.scores(actual_batch)
    expected_calls = [
        ("process:p0", ["g2"], 16),
        ("process:p1", ["g0", "g1"], 16),
    ]
    assert calls == expected_calls

    reference_batch = _make_batch()
    expected = linguistic._process_scores_reference(
        reference_batch,
        lambda process, assessment: _scalar_value(pressure, process, assessment),
    )
    assert calls[-2:] == expected_calls
    assert np.array_equal(actual, expected, equal_nan=True)
    np.testing.assert_array_equal(np.signbit(actual), np.signbit(expected))
    assert actual_batch.memo[("process:p0", 0)] is seeded
    assert ("_cee_process_score_layout_v1",) in actual_batch.memo


def test_sdilene_memo_layout_znovu_nevola_assess_many(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def assess_many(_world, group_ids, variable_id, _tick):
        calls.append((variable_id, list(group_ids)))
        return [_assessment_for(variable_id, group_id) for group_id in group_ids]

    monkeypatch.setattr(linguistic, "assess_many", assess_many)
    batch = _make_batch()
    for pressure in PRESSURES:
        pressure.scores(batch)
    assert calls == [("process:p0", ["g2"]), ("process:p1", ["g0", "g1"])]


def test_scalar_callback_zustava_dostupny(monkeypatch) -> None:
    monkeypatch.setattr(
        linguistic,
        "assess_many",
        lambda _world, group_ids, variable_id, _tick: [
            _assessment_for(variable_id, group_id) for group_id in group_ids
        ],
    )
    batch = _make_batch()
    result = linguistic._process_scores(batch, lambda process, _: process.ease)
    assert result[0, 0, 1] == -0.0
    assert np.signbit(result[0, 0, 1])

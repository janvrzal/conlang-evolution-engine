"""Morfologické tlaky (iterace 3): na analogické tvary slov."""

from __future__ import annotations

from typing import Callable, cast

import numpy as np

from cee.v2.language.morphology import FormChange
from cee.v2.morphology import FormAssessment, assess
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


def _form_scores(
    batch: PressureBatch,
    value: Callable[[FormChange, FormAssessment], float],
    values_many: Callable[[FormChange, list[FormAssessment | None]], np.ndarray] | None = None,
) -> FloatArray:
    """Skóre analogického tvaru v každé skupině, ke které dolehl."""
    result = np.zeros_like(batch.freqs)
    for row, change, slot, columns, assessments in _form_score_layout(batch):
        if not len(columns):
            continue
        values: list[float] | np.ndarray
        if values_many is None:
            values = [
                0.0 if assessment is None else value(change, assessment)
                for assessment in assessments
            ]
        else:
            values = values_many(change, assessments)
        result[row, columns, slot] = values
    return result


def _form_scores_reference(
    batch: PressureBatch, value: Callable[[FormChange, FormAssessment], float]
) -> FloatArray:
    """Původní skalární cesta, ponechaná pro testy parity."""
    result = np.zeros_like(batch.freqs)
    world = batch.world
    for row, variable_id in enumerate(batch.variable_ids):
        change = world.form_changes.get(variable_id)
        if change is None:
            continue
        changed = changed_id(variable_id)
        if changed not in batch.slots[row]:
            continue
        slot = list(batch.slots[row]).index(changed)
        reached = (batch.freqs[row, :, slot] > 0) | (batch.heard[row, :, slot] > 0)
        for column in (int(index) for index in np.flatnonzero(reached)):
            key = ("form", variable_id, column)
            if key not in batch.memo:
                batch.memo[key] = assess(world, batch.group_ids[column], variable_id)
            assessment = batch.memo[key]
            # Ve skupině, kde by změna nic nezměnila, nemá výhodu ani nevýhodu.
            result[row, column, slot] = 0.0 if assessment is None else value(change, assessment)
    return result


_FORM_SCORE_LAYOUT_KEY = ("_cee_form_score_layout_v1",)


def _form_score_layout(
    batch: PressureBatch,
) -> list[tuple[int, FormChange, int, np.ndarray, list[FormAssessment | None]]]:
    """Jednou připraví dosažené buňky a jejich assessmenty pro všechny tlaky."""
    cached = batch.memo.get(_FORM_SCORE_LAYOUT_KEY)
    if cached is not None:
        return cast(list[tuple[int, FormChange, int, np.ndarray, list[FormAssessment | None]]], cached)

    layout: list[tuple[int, FormChange, int, np.ndarray, list[FormAssessment | None]]] = []
    world = batch.world
    for row, variable_id in enumerate(batch.variable_ids):
        change = world.form_changes.get(variable_id)
        if change is None:
            continue
        changed = changed_id(variable_id)
        if changed not in batch.slots[row]:
            continue
        slot = list(batch.slots[row]).index(changed)
        reached = (batch.freqs[row, :, slot] > 0) | (batch.heard[row, :, slot] > 0)
        columns = np.flatnonzero(reached)
        assessments: list[FormAssessment | None] = []
        for index in columns:
            column = int(index)
            key = ("form", variable_id, column)
            if key not in batch.memo:
                batch.memo[key] = assess(world, batch.group_ids[column], variable_id)
            assessments.append(batch.memo[key])
        layout.append((row, change, slot, columns, assessments))

    batch.memo[_FORM_SCORE_LAYOUT_KEY] = layout
    return layout


def _assessment_values(
    assessments: list[FormAssessment | None], attribute: str
) -> tuple[np.ndarray, np.ndarray]:
    """Vrátí masku existujících výsledků a jejich číselné pole."""
    present = np.fromiter((item is not None for item in assessments), dtype=np.bool_)
    values = np.fromiter(
        (0.0 if item is None else getattr(item, attribute) for item in assessments),
        dtype=np.float64,
    )
    return present, values


def _uniformity_values(
    change: FormChange, assessments: list[FormAssessment | None]
) -> np.ndarray:
    present, gains = _assessment_values(assessments, "gain")
    result = np.zeros(len(assessments), dtype=np.float64)
    if change.operation == "level":
        result[present] = 0.4
    else:
        result[present] = 0.35 * gains[present]
    return result


def _conservation_values(
    change: FormChange, assessments: list[FormAssessment | None]
) -> np.ndarray:
    present, frequencies = _assessment_values(assessments, "frequency")
    result = np.zeros(len(assessments), dtype=np.float64)
    if not change.lexeme_wide:
        result[present] = -0.6 * (2.0 * frequencies[present] - 1.0)
    return result


def _teachability_values(
    change: FormChange, assessments: list[FormAssessment | None], strength: float
) -> np.ndarray:
    present = np.fromiter((item is not None for item in assessments), dtype=np.bool_)
    result = np.zeros(len(assessments), dtype=np.float64)
    if not change.lexeme_wide:
        result[present] = strength
    return result


def _distinctiveness_values(
    _: FormChange, assessments: list[FormAssessment | None]
) -> np.ndarray:
    present = np.fromiter((item is not None for item in assessments), dtype=np.bool_)
    before = np.fromiter(
        (False if item is None else item.syncretic_before for item in assessments), dtype=np.bool_
    )
    after = np.fromiter(
        (False if item is None else item.syncretic_after for item in assessments), dtype=np.bool_
    )
    result = np.zeros(len(assessments), dtype=np.float64)
    result[present & after & ~before] = -0.8
    result[present & before & ~after] = 0.6
    return result


class Uniformity(Pressure):
    """Jeden tvar pro jeden význam; síla podle typové frekvence vzoru."""

    name = "uniformity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _form_scores(
            batch,
            lambda change, assessment: 0.4 if change.operation == "level" else 0.35 * assessment.gain,
            _uniformity_values,
        )


class Conservation(Pressure):
    """Častá slova si drží nepravidelnost, vzácná podléhají analogii (Bybee).

    Proto jsou nepravidelná právě *být, mít, jít*: jejich tvary se učí z
    tolika výskytů, že je analogie nepřepíše. Reanalýza hranice není
    analogie k pravidelnosti, proto na ni tento tlak nepůsobí.
    """

    name = "conservation"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _form_scores(
            batch,
            lambda change, assessment: 0.0 if change.lexeme_wide
            else -0.6 * (2.0 * assessment.frequency - 1.0),
            _conservation_values,
        )


class Teachability(Pressure):
    """Dospělí, kteří se jazyk učí jako druhý, nepravidelnosti neudrží.

    Pravidelný tvar (vyrovnání, rozšíření vzoru) má výhodu úměrnou podílu
    L2 mluvčích ve skupině (Trudgill 2011; Lupyan & Dale 2010). Bez nich je
    tlak nulový. Reanalýza hranice regularizace není.
    """

    name = "teachability"
    strength = 1.0

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        shares = np.array([world.groups[group_id].main_code.l2_share for group_id in batch.group_ids])
        if not shares.any():
            return np.zeros_like(batch.freqs)
        return _form_scores(
            batch,
            lambda change, _: 0.0 if change.lexeme_wide else self.strength,
            lambda change, assessments: _teachability_values(change, assessments, self.strength),
        ) * shares[None, :, None]


class Distinctiveness(Pressure):
    """Tvar buňky má zůstat odlišný od citačního tvaru.

    Analogie, která by plurál slila se singulárem, je nevýhodná; analogie,
    která po erozi koncovky rozdíl obnoví, je výhodná. Tak se šíří nové
    koncovky na místa, kde staré zvukovými změnami zmizely.
    """

    name = "distinctiveness"

    def scores(self, batch: PressureBatch) -> FloatArray:
        def value(_: FormChange, assessment: FormAssessment) -> float:
            if assessment.syncretic_after and not assessment.syncretic_before:
                return -0.8
            if assessment.syncretic_before and not assessment.syncretic_after:
                return 0.6
            return 0.0

        return _form_scores(batch, value, _distinctiveness_values)

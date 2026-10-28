"""Morfologické tlaky (iterace 3): na analogické tvary slov."""

from __future__ import annotations

from typing import Callable

import numpy as np

from cee.v2.language.morphology import FormChange
from cee.v2.morphology import FormAssessment, assess
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


def _form_scores(
    batch: PressureBatch, value: Callable[[FormChange, FormAssessment], float]
) -> FloatArray:
    """Skóre analogického tvaru v každé skupině, ke které dolehl."""
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


class Uniformity(Pressure):
    """Jeden tvar pro jeden význam; síla podle typové frekvence vzoru."""

    name = "uniformity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _form_scores(
            batch,
            lambda change, assessment: 0.4 if change.operation == "level" else 0.35 * assessment.gain,
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
        )


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

        return _form_scores(batch, value)

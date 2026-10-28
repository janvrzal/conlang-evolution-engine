"""Jazykové tlaky: jak výhodná je varianta sama o sobě (iterace 3)."""

from __future__ import annotations

from typing import Callable

import numpy as np

from cee.v2.assessment import ProcessAssessment, assess
from cee.v2.language.processes import Process
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


class Appeal(Pressure):
    """Dočasný zástupce jazykových tlaků u slov (milník M1).

    Dokud lexém nemá hodnocení podle tvaru a významu (M3+), varianta při
    vzniku dostane číslo ``appeal``, které souhrnně zastupuje její výhodu.
    """

    name = "appeal"

    def scores(self, batch: PressureBatch) -> FloatArray:
        result: FloatArray = np.clip(batch.payload("appeal"), -1.0, 1.0)
        return result


def _process_scores(
    batch: PressureBatch, value: Callable[[Process, ProcessAssessment], float]
) -> FloatArray:
    """Skóre varianty „změna“ každého procesu v každé skupině, která ji slyší.

    Varianta „žádná změna“ má skóre 0; selekce pracuje jen s rozdílem.
    Skupiny, ke kterým změna vůbec nedolehla, se nehodnotí — nic by to
    nezměnilo a hodnocení není zadarmo.
    """
    result = np.zeros_like(batch.freqs)
    world = batch.world
    for row, variable_id in enumerate(batch.variable_ids):
        process = world.processes.get(variable_id)
        if process is None:
            continue
        changed = changed_id(variable_id)
        if changed not in batch.slots[row]:
            continue
        slot = list(batch.slots[row]).index(changed)
        reached = (batch.freqs[row, :, slot] > 0) | (batch.heard[row, :, slot] > 0)
        for column in (int(index) for index in np.flatnonzero(reached)):
            key = (variable_id, column)
            assessment = batch.memo.get(key)
            if assessment is None:
                assessment = batch.memo[key] = assess(
                    world, batch.group_ids[column], variable_id, batch.tick
                )
            result[row, column, slot] = value(process, assessment)
    return result


class Articulation(Pressure):
    """Úspora artikulačních gest: oslabení, asimilace, redukce."""

    name = "articulation"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(batch, lambda process, _: process.ease)


class Clarity(Pressure):
    """Zachování akustických vodítek (Ohala); trest za slova zkrácená pod mez."""

    name = "clarity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch,
            lambda process, assessment: float(
                np.clip(process.clarity - 1.5 * assessment.short_share, -1.0, 1.0)
            ),
        )


#: Jak silně zvýhodňuje funkční zátěž zachování kontrastu. Je to sklon, ne
#: zákaz (Wedel a kol. 2013): eroze pádových koncovek se v reálných jazycích
#: děje i přes splynutí tvarů (latinské koncové -m).
FUNCTIONAL_LOAD_SCALE = 5.0


class FunctionalLoad(Pressure):
    """Splynutí, které vyrobí mnoho častých homofonů, je nevýhodné (Martinet)."""

    name = "functional_load"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch, lambda _, assessment: -float(min(1.0, FUNCTIONAL_LOAD_SCALE * assessment.merge_mass))
        )


class Dispersion(Pressure):
    """Rozložení vokálů: odměna za zaplnění mezery, trest za natlačení."""

    name = "dispersion"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch, lambda _, assessment: float(np.clip(4.0 * assessment.dispersion_delta, -1.0, 1.0))
        )


class Phonotactics(Pressure):
    """Slabičná stavba: změna, která přidá shluky či hiát, je nevýhodná."""

    name = "phonotactics"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch, lambda _, assessment: -float(np.clip(assessment.markedness_delta, -1.0, 1.0))
        )

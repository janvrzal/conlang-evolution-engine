"""Jazykové tlaky: jak výhodná je varianta sama o sobě (iterace 3)."""

from __future__ import annotations

from typing import Callable, cast

import numpy as np

from cee.v2.assessment import ProcessAssessment, assess_many
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
    batch: PressureBatch,
    value: Callable[[Process, ProcessAssessment], float],
    values_many: Callable[[Process, list[ProcessAssessment]], np.ndarray] | None = None,
) -> FloatArray:
    """Skóre varianty „změna“ každého procesu v každé skupině, která ji slyší.

    Varianta „žádná změna“ má skóre 0; selekce pracuje jen s rozdílem.
    Skupiny, ke kterým změna vůbec nedolehla, se nehodnotí — nic by to
    nezměnilo a hodnocení není zadarmo.
    """
    result = np.zeros_like(batch.freqs)
    for row, process, slot, columns, assessments in _process_score_layout(batch):
        if not len(columns):
            continue
        values: list[float] | np.ndarray
        if values_many is None:
            values = [value(process, assessment) for assessment in assessments]
        else:
            values = values_many(process, assessments)
        result[row, columns, slot] = values
    return result


def _process_scores_reference(
    batch: PressureBatch, value: Callable[[Process, ProcessAssessment], float]
) -> FloatArray:
    """Původní skalární cesta, ponechaná pro testy parity."""
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
        columns = np.flatnonzero(reached).tolist()
        missing = [column for column in columns if (variable_id, column) not in batch.memo]
        if missing:
            # Všechny skupiny, kam změna dolehla, se hodnotí naráz.
            fresh = assess_many(world, [batch.group_ids[column] for column in missing], variable_id, batch.tick)
            for column, assessment in zip(missing, fresh):
                batch.memo[(variable_id, column)] = assessment
        for column in columns:
            result[row, column, slot] = value(process, batch.memo[(variable_id, column)])
    return result


_PROCESS_SCORE_LAYOUT_KEY = ("_cee_process_score_layout_v1",)


def _process_score_layout(
    batch: PressureBatch,
) -> list[tuple[int, Process, int, np.ndarray, list[ProcessAssessment]]]:
    """Sdílené řádky, změnové sloty a dosažené sloupce pro všechny jazykové tlaky."""
    cached = batch.memo.get(_PROCESS_SCORE_LAYOUT_KEY)
    if cached is not None:
        return cast(list[tuple[int, Process, int, np.ndarray, list[ProcessAssessment]]], cached)

    layout: list[tuple[int, Process, int, np.ndarray, list[ProcessAssessment]]] = []
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
        columns = np.flatnonzero(reached)
        missing = [int(column) for column in columns if (variable_id, int(column)) not in batch.memo]
        if missing:
            # Zachovává se pořadí řádků a vzestupné pořadí sloupců původní cesty.
            fresh = assess_many(
                world, [batch.group_ids[column] for column in missing], variable_id, batch.tick
            )
            for column, assessment in zip(missing, fresh):
                batch.memo[(variable_id, column)] = assessment
        assessments = [batch.memo[(variable_id, int(column))] for column in columns]
        layout.append((row, process, slot, columns, assessments))

    batch.memo[_PROCESS_SCORE_LAYOUT_KEY] = layout
    return layout


def _functional_load_values(
    _: Process, assessments: list[ProcessAssessment]
) -> np.ndarray:
    scaled = FUNCTIONAL_LOAD_SCALE * np.fromiter(
        (item.merge_mass for item in assessments), dtype=np.float64
    )
    # Python min(1.0, NaN) vrací první argument; porovnání zachová totéž.
    return -np.where(scaled < 1.0, scaled, 1.0)


#: Násobek úspory artikulace pro redukční procesy v nepřízvučných slabikách
#: u jazyků se silným přízvukem (stress-timed).
#:
#: Literatura podporuje směr (silnější redukce a afixální komprese v nepřízvučné
#: pozici: Dauer 1983; Bybee, Chakraborti, Jung & Scheibman 1998 „Prosody and
#: segmental effect: Some paths of evolution for word stress“, Studies in
#: Language 22; Schiering 2010), hodnota 1,5 je autorský odhad (neladěno na WALS).
STRESS_STRENGTH_MULTIPLIER: float = 1.5


class Articulation(Pressure):
    """Úspora artikulačních gest: oslabení, asimilace, redukce."""

    name = "articulation"

    def scores(self, batch: PressureBatch) -> FloatArray:
        result = np.zeros_like(batch.freqs)
        groups = getattr(batch.world, "groups", None)
        if groups is not None:
            strong_groups = np.array(
                [
                    getattr(groups[gid].main_code, "stress_strength", "weak") == "strong"
                    for gid in batch.group_ids
                ],
                dtype=bool,
            )
        else:
            strong_groups = np.zeros(len(batch.group_ids), dtype=bool)

        for row, process, slot, columns, _ in _process_score_layout(batch):
            if not len(columns):
                continue
            ease = process.ease
            if getattr(process, "reductive", False) and getattr(process, "stress", None) == "unstressed":
                multipliers = np.where(strong_groups[columns], STRESS_STRENGTH_MULTIPLIER, 1.0)
                result[row, columns, slot] = ease * multipliers
            else:
                result[row, columns, slot] = ease
        return result


class Clarity(Pressure):
    """Zachování akustických vodítek (Ohala); trest za slova zkrácená pod mez."""

    name = "clarity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch,
            lambda process, assessment: float(
                np.clip(process.clarity - 1.5 * assessment.short_share, -1.0, 1.0)
            ),
            lambda process, assessments: np.clip(
                process.clarity
                - 1.5 * np.fromiter((item.short_share for item in assessments), dtype=np.float64),
                -1.0,
                1.0,
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
            batch,
            lambda _, assessment: -float(min(1.0, FUNCTIONAL_LOAD_SCALE * assessment.merge_mass)),
            _functional_load_values,
        )


class Dispersion(Pressure):
    """Rozložení vokálů: odměna za zaplnění mezery, trest za natlačení."""

    name = "dispersion"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch,
            lambda _, assessment: float(np.clip(4.0 * assessment.dispersion_delta, -1.0, 1.0)),
            lambda _, assessments: np.clip(
                4.0 * np.fromiter((item.dispersion_delta for item in assessments), dtype=np.float64),
                -1.0,
                1.0,
            ),
        )


class Phonotactics(Pressure):
    """Slabičná stavba: změna, která přidá shluky či hiát, je nevýhodná."""

    name = "phonotactics"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _process_scores(
            batch,
            lambda _, assessment: -float(np.clip(assessment.markedness_delta, -1.0, 1.0)),
            lambda _, assessments: -np.clip(
                np.fromiter((item.markedness_delta for item in assessments), dtype=np.float64),
                -1.0,
                1.0,
            ),
        )

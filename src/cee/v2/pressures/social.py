"""Sociální tlaky: rozhodují, které varianty se v konkrétní skupině uchytí."""

from __future__ import annotations

from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


class Conformity(Pressure):
    """Výhoda většinové varianty ve skupině.

    Menšinová varianta je znevýhodněná, většinová zvýhodněná. Inovace se proto
    musí nejdřív prosadit vlastní výhodou, driftem nebo přílivem od sousedů;
    jakmile překročí polovinu, konformita dokončení S-křivky naopak urychlí.
    """

    name = "conformity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        result: FloatArray = 2.0 * batch.freqs - 1.0
        return result

"""Jazykové tlaky: jak výhodná je varianta sama o sobě."""

from __future__ import annotations

import numpy as np

from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


class Appeal(Pressure):
    """Dočasný zástupce jazykových tlaků v milníku M1.

    Dokud lexém nemá hláskovou podobu (M2), nelze spočítat artikulaci,
    zřetelnost ani homofonii. Varianta proto při vzniku dostane číslo
    ``appeal``, které souhrnně zastupuje její jazykovou výhodu. Až přijdou
    skutečné tlaky z katalogu, tento tlak zanikne.
    """

    name = "appeal"

    def scores(self, batch: PressureBatch) -> FloatArray:
        result: FloatArray = np.clip(batch.payload("appeal"), -1.0, 1.0)
        return result

"""Sociální tlaky: rozhodují, které varianty se v konkrétní skupině uchytí."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch
from cee.v2.rng import hash_normal, stable_int


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


class Actuation(Pressure):
    """Sociální ocenění změny: proč tady a teď, a jinde ne (Labov).

    Stejná výslovnostní inovace se v jedné komunitě stane znakem identity a
    v sousední zůstane nepovšimnuta. Simulace nemá mluvčí, kteří by tohle
    rozhodovali, proto každá skupina dostane pro každou změnu a každou epochu
    (8 generací) vlastní seedované ocenění. Bez něj by všechny jazyky
    prošly stejnými, typologicky nejvýhodnějšími změnami.
    """

    name = "actuation"
    spread = 0.25
    epoch_ticks = 8

    def scores(self, batch: PressureBatch) -> FloatArray:
        result = np.zeros_like(batch.freqs)
        variants = batch.world.variants
        cells = [
            (row, slot, variant)
            for row, slots in enumerate(batch.slots)
            for slot, variant in enumerate(slots)
            if variant is not None and variants[variant].origin.change is not None
            and self.applies(variants[variant].payload)
        ]
        if not cells:
            return result
        epoch = batch.tick // self.epoch_ticks
        seed = batch.world.seed
        groups = np.array(
            [stable_int(seed, "actuation", epoch, group) for group in batch.group_ids], dtype=np.uint64
        )
        keys = np.array([stable_int("actuation", variant) for _, _, variant in cells], dtype=np.uint64)
        values = np.clip(self.spread * hash_normal(groups, keys), -1.0, 1.0)
        rows = np.array([row for row, _, _ in cells])
        slots = np.array([slot for _, slot, _ in cells])
        result[rows, :, slots] = values.T
        return result

    def applies(self, payload: Mapping[str, object]) -> bool:
        return True

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
        # Buňky (řádek, slot) s inovací (varianta nese změnu) z tabulky variant,
        # v pořadí řádků a slotů jako dřív.
        numbers = batch.slot_numbers()
        mask = batch.slot_column("change", -1.0) >= 0
        if self.requires_morpheme:
            mask &= batch.slot_column("morpheme", -1.0) >= 0
        found_rows, found_slots = np.nonzero(mask & (numbers >= 0))
        cells = [
            (int(row), int(slot), batch.slots[row][slot]) for row, slot in zip(found_rows, found_slots)
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

    #: Působí jen na varianty s morfémem (lexikální ocenění); jinak na každou inovaci.
    requires_morpheme = False

    def applies(self, payload: Mapping[str, object]) -> bool:
        return True


class Norm(Pressure):
    """Škola zvýhodní variantu, kterou má psaný kód (kodifikovanou).

    Působí jen tam, kde děti chodí do školy, a úměrně docházce; bez písma a
    školy je nulový (standardizace je pozdní, iterace 4). Zvukovou změnu,
    kterou už si kód uzavřel do podkladových tvarů, škola nevrátí: tvary
    slov se nepřepisují zpět.
    """

    name = "norm"
    #: Spisovné jazyky se mění dál, jen pomaleji: norma inovaci brzdí, ale
    #: nepřebije každý jiný tlak.
    strength = 0.3

    def scores(self, batch: PressureBatch) -> FloatArray:
        from cee.v2.institutions import standard_of

        world = batch.world
        result = np.zeros_like(batch.freqs)
        for column, group_id in enumerate(batch.group_ids):
            group = world.groups[group_id]
            standard = standard_of(world, group_id) if group.schooling > 0 else None
            if standard is None:
                continue
            closed = group.main_code.phonology.closed
            for row, variable_id in enumerate(batch.variable_ids):
                key = ("codified", standard, variable_id)
                if key not in batch.memo:
                    distribution = world.distribution(standard, variable_id)
                    batch.memo[key] = None if distribution is None else distribution.dominant()[0]
                codified = batch.memo[key]
                if codified is None or codified not in batch.slots[row] or variable_id in closed:
                    continue
                result[row, column, list(batch.slots[row]).index(codified)] = self.strength * group.schooling
        return result

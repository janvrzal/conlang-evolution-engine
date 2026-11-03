"""Lexikální tlaky (iterace 3, milník M3b): proč se jedno slovo ujme a jiné ne.

Všechny tlaky hodnotí jen varianty s morfémem (svět s hláskovými tvary).
Ve světě M1 vracejí nulu a jeho kalibrace zůstává beze změny.
"""

from __future__ import annotations

from typing import Mapping

import numpy as np

from cee.v2.language.lexical_index import clarity_scores
from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch
from cee.v2.pressures.social import Actuation

#: Kolik generací musí slovo být v užívání, než ho tabu „opotřebuje“. Kratší
#: lhůta než doba šíření nového opisu by nedovolila žádnému opisu převážit.
TABOO_GENERATIONS = 10

_MOTIVATION = {
    "derivation": 0.15, "compound": 0.15, "circumlocution": 0.1, "shift": 0.05, "conversion": 0.05,
    "back_formation": 0.0, "contamination": -0.05, "coinage": -0.15,
}


def _has_morpheme(batch: PressureBatch) -> FloatArray:
    """1 pro slot s variantou, která nese morfém (sloupec ``morpheme`` tabulky variant), jinak 0."""
    found = (batch.slot_column("morpheme", -1.0) >= 0).astype(np.float64)
    return found.reshape(len(batch.slots), 1, -1)  # type: ignore[no-any-return]


class LexicalClarity(Pressure):
    """Slovo, které zvukové změny zkrátily na dvě hlásky nebo slily s jiným, je nevýhodné.

    Náhrada erodovaného slova (lat. *os* „ústa“ → *bucca*) a homofonního
    slova je běžná cesta lexikální změny. Polysémie příbuzných pojmů
    (posun významu) se za homofonii nepočítá.
    """

    name = "lexical_clarity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        result = np.zeros_like(batch.freqs)
        if world.table is None:
            return result
        return _clarity_scores(batch, result)


def _clarity_scores(batch: PressureBatch, result: FloatArray) -> FloatArray:
    """Skóre jasnosti buněk (proměnná, skupina, slot) jednou dávkou pro všechny skupiny.

    Skupiny, ke kterým varianta nedolehla, se nehodnotí: s nulovým vstupem ji
    selekce stejně nevybere. Morfém varianty je sloupec tabulky variant, pojem
    proměnné číslo z registru; nic se nepřekládá přes řetězce varianty.
    """
    world = batch.world
    reached = (batch.freqs > 0) | (batch.heard > 0)
    morphemes = batch.slot_column("morpheme", -1.0).astype(np.int64)
    concepts = np.array(
        [world.registry.concepts.intern(variable_id.split(":", 1)[1]) for variable_id in batch.variable_ids],
        dtype=np.int64,
    )
    rows, columns, slots = np.nonzero((morphemes >= 0)[:, None, :] & reached)
    if not len(rows):
        return result
    codes = [world.groups[group_id].main_code for group_id in batch.group_ids]
    result[rows, columns, slots] = clarity_scores(
        world, codes, columns.astype(np.int64), morphemes[rows, slots], concepts[rows]
    )
    return result


class Entrenchment(Pressure):
    """Zažité slovo se nahrazuje pomalu, slovo pro častý pojem ještě pomaleji (Pagel a kol. 2007).

    Dominantní varianta dostane výhodu ``Parameters.entrenchment_base``
    (slovo zná celá komunita) plus ``entrenchment_strength`` × frekvence
    pojmu: čím častější pojem, tím víc výskytů staré slovo každou generaci
    upevní. Nové slovo ji přebije jen s dost velkou přitažlivostí
    (``Motivation``), takže výměna je plynulá a s frekvencí klesá mírně.
    """

    name = "entrenchment"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        if world.table is None:
            return np.zeros_like(batch.freqs)
        frequency = np.array(
            [world.concept_frequency(variable_id.split(":", 1)[1]) for variable_id in batch.variable_ids]
        )
        dominant = (batch.freqs >= 0.5).astype(np.float64)
        strength = world.params.entrenchment_strength
        exponent = world.params.entrenchment_frequency_exponent
        if exponent != 1.0:
            frequency = frequency**exponent
        protection = strength * frequency
        base = world.params.entrenchment_base
        if base != 0.0:
            protection = base + protection
        result: FloatArray = protection[:, None, None] * dominant * _has_morpheme(batch)
        return result


class Motivation(Pressure):
    """Průhledné nové slovo (odvozenina, složenina) se ujme snáz než nový kořen.

    K výhodě podle druhu se přičte náhodná přitažlivost slova
    (``Parameters.lexical_appeal_sd``, ``changes.lexicon.with_appeal``).
    """

    name = "motivation"

    def scores(self, batch: PressureBatch) -> FloatArray:
        if batch.world.table is None:
            return np.zeros_like(batch.freqs)
        # Kód původu slova (sloupec ``origin``) → váha; −1 (chybí) ukazuje na poslední prvek, nulu.
        names = batch.world.columns.variants.payload_origins.names
        weights = np.array([_MOTIVATION.get(name, 0.0) for name in names] + [0.0])
        codes = batch.slot_column("origin", -1.0).astype(np.intp)
        # Náhodná přitažlivost nového slova (``Parameters.lexical_appeal_sd``);
        # varianta bez ní (zděděné slovo) má nulu.
        appeal = np.nan_to_num(batch.slot_column("appeal", 0.0), nan=0.0)
        result: FloatArray = np.broadcast_to(
            (weights[codes] + appeal).reshape(len(batch.slots), 1, -1), batch.freqs.shape
        ).copy()
        return result


class Taboo(Pressure):
    """Slovo pro tabuizovaný pojem se časem „opotřebuje“ a nahradí opisem.

    Opis je zprvu přijatelný; po několika generacích užívání se stane stejně
    nevhodným jako slovo, které nahradil (eufemistický koloběh).
    """

    name = "taboo"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        result = np.zeros_like(batch.freqs)
        groups = [world.groups[group_id] for group_id in batch.group_ids]
        if not any(group.taboo for group in groups):
            return result
        for row, variable_id in enumerate(batch.variable_ids):
            concept = variable_id.split(":", 1)[1]
            columns = [column for column, group in enumerate(groups) if concept in group.taboo]
            if not columns:
                continue
            for slot, variant in enumerate(batch.slots[row]):
                if variant is None or "morpheme" not in world.variants[variant].payload:
                    continue
                origin = world.variants[variant].origin
                for column in columns:
                    generation = groups[column].generation_years / 25.0
                    age = batch.tick - origin.tick if origin.change is not None else 10**9
                    if age >= TABOO_GENERATIONS * generation:
                        result[row, column, slot] = -0.6
        return result


class LexicalActuation(Actuation):
    """Sociální ocenění nového slova; jen ve světě s hláskovými tvary."""

    name = "lexical_actuation"

    requires_morpheme = True

    def applies(self, payload: Mapping[str, object]) -> bool:
        return "morpheme" in payload

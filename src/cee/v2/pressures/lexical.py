"""Lexikální tlaky (iterace 3, milník M3b): proč se jedno slovo ujme a jiné ne.

Všechny tlaky hodnotí jen varianty s morfémem (svět s hláskovými tvary).
Ve světě M1 vracejí nulu a jeho kalibrace zůstává beze změny.
"""

from __future__ import annotations

from typing import Callable, Mapping, cast

import numpy as np

from cee.v2.language.lexical_index import LexicalClarityIndex
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
    return batch.slot_values(lambda variant: 1.0 if "morpheme" in variant.payload else 0.0)


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
        per_group: dict[int, Callable[[str, str], float]] = {}
        # Skupiny, ke kterým varianta nedolehla, se nehodnotí: s nulovým
        # vstupem ji selekce stejně nevybere.
        reached = (batch.freqs > 0) | (batch.heard > 0)
        for row, variable_id in enumerate(batch.variable_ids):
            concept = variable_id.split(":", 1)[1]
            for slot, variant in enumerate(batch.slots[row]):
                if variant is None:
                    continue
                morpheme = world.variants[variant].payload.get("morpheme")
                if not isinstance(morpheme, str):
                    continue
                for column in np.flatnonzero(reached[row, :, slot]).tolist():
                    scores = per_group.get(column)
                    if scores is None:
                        scores = per_group[column] = _clarity_map(batch, batch.group_ids[column])
                    result[row, column, slot] = scores(morpheme, concept)
        return result


def _clarity_map(batch: PressureBatch, group_id: str) -> Callable[[str, str], float]:
    """Průběžná mapa jasnosti pro jednu skupinu."""
    world = batch.world
    code = world.groups[group_id].main_code
    state = code.phonology
    stored = state.cache.get("lexical-clarity-index")
    if stored is None:
        index = LexicalClarityIndex()
        state.cache["lexical-clarity-index"] = (0, index)
    else:
        index = cast(LexicalClarityIndex, stored[1])
    index.sync(world, code)
    return lambda morpheme, concept: index.score(world, code, morpheme, concept)


def _clarity_map_reference(batch: PressureBatch, group_id: str) -> Callable[[str, str], float]:
    """Funkce (morfém, pojem) → skóre jasnosti pro jednu skupinu, s cache."""
    world = batch.world
    code = world.groups[group_id].main_code
    state = code.phonology
    # Mapa homofonů závisí jen na tvarech a slovní zásobě skupiny: drží se
    # napříč dávkami i kroky, dokud se verze kódu nezmění.
    stored = state.cache.get("lexical-clarity-reference")
    if stored is not None and stored[0] == state.version:
        memo = cast(tuple[dict[tuple[str, str], float], dict[tuple[int, ...], set[tuple[str, str]]]], stored[1])
    else:
        built: dict[tuple[int, ...], set[tuple[str, str]]] = {}
        for concept, root in state.dominant.items():
            built.setdefault(world.form_of(code, root), set()).add((root, concept))
        memo = ({}, built)
        state.cache["lexical-clarity-reference"] = (state.version, memo)
    cache: dict[tuple[str, str], float] = memo[0]
    owners: dict[tuple[int, ...], set[tuple[str, str]]] = memo[1]

    def score(morpheme: str, concept: str) -> float:
        found = cache.get((morpheme, concept))
        if found is not None:
            return float(found)
        form = world.form_of(code, morpheme)
        # Trestá se eroze, ne krátkost: slovo, které bylo krátké odjakživa
        # (zájmena, CV kořeny), je stabilní.
        eroded = len(form) <= 2 and len(form) < len(world.morphemes[morpheme].form)
        value = -0.5 if eroded else 0.0
        semantics = world.semantics
        for root, other in owners.get(form, ()):
            if root != morpheme and other != concept and not (
                semantics is not None and semantics.related(concept, other)
            ):
                value -= 0.4
                break
        cache[(morpheme, concept)] = value
        return value

    return score


class Entrenchment(Pressure):
    """Zažité slovo pro častý pojem se nahrazuje pomalu (Pagel a kol. 2007).

    Dominantní varianta dostane výhodu úměrnou tomu, jak často se o pojmu
    mluví. Čím častější pojem, tím víc výskytů staré slovo každou generaci
    upevní a tím těžší je ho vytlačit.
    """

    name = "entrenchment"
    strength = 0.3

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        if world.table is None:
            return np.zeros_like(batch.freqs)
        frequency = np.array(
            [world.concept_frequency(variable_id.split(":", 1)[1]) for variable_id in batch.variable_ids]
        )
        dominant = (batch.freqs >= 0.5).astype(np.float64)
        result: FloatArray = self.strength * frequency[:, None, None] * dominant * _has_morpheme(batch)
        return result


class Motivation(Pressure):
    """Průhledné nové slovo (odvozenina, složenina) se ujme snáz než nový kořen."""

    name = "motivation"

    def scores(self, batch: PressureBatch) -> FloatArray:
        if batch.world.table is None:
            return np.zeros_like(batch.freqs)
        result: FloatArray = np.broadcast_to(
            batch.slot_values(lambda variant: _MOTIVATION.get(str(variant.payload.get("origin")), 0.0)),
            batch.freqs.shape,
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

    def applies(self, payload: Mapping[str, object]) -> bool:
        return "morpheme" in payload

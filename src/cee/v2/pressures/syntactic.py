"""Syntaktické tlaky (iterace 3; milníky M4 a M4b).

Žádný tlak nezná konkrétní funkci; co funkce potřebuje (``need``) a čí roli
může převzít (``compensates``), říká katalog gramatických funkcí.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from cee.v2 import syntax
from cee.v2.language.constructions import Construction, catalog_for
from cee.v2.pressures.base import FloatArray, Pressure, PressureBatch


def _scores(
    batch: PressureBatch, value: Callable[[Construction, Construction | None, str], float]
) -> FloatArray:
    """Skóre každé konstrukce v každé skupině vzhledem k té, která tam převažuje."""
    world = batch.world
    result = np.zeros_like(batch.freqs)
    for row, variable_id in enumerate(batch.variable_ids):
        function = variable_id.split(":", 1)[1]
        for column, group_id in enumerate(batch.group_ids):
            current = syntax.dominant(world, group_id, function)
            for slot, variant in enumerate(batch.slots[row]):
                if variant is not None:
                    result[row, column, slot] = value(
                        syntax.construction_of(world, variant), current, group_id
                    )
    return result


class Expressivity(Pressure):
    """Zeslabené vyjádření funkce se obnovuje novým, silnějším výrazem.

    Skóre je potřeba funkce × síla vyjádření. Když koncovka minulého času
    zvukovými změnami splynula s citačním tvarem, má opis (*mít* + sloveso)
    výhodu úměrnou tomu, kolik tvarů splynulo. Funkce, kterou jazyk vůbec
    nevyjadřuje (``zero``), tlačí k novému výrazu tím víc, čím víc ji
    komunikace potřebuje (minulý čas víc než určenost), ale tato potřeba
    je tlumena kontextem a náhradními strategiemi (C2; Bybee et al. 1994,
    Dahl 1985, Dryer 2013).
    """

    name = "expressivity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        functions = catalog_for(world)

        def value(construction: Construction, current: Construction | None, group_id: str) -> float:
            need = functions[construction.function].need
            if need == 0.0:
                return 0.0
            return need * syntax.strength(
                world, world.groups[group_id].main_code, construction, group_id=group_id
            )

        return _scores(batch, value)


class Economy(Pressure):
    """Každé slovo navíc stojí úsilí; víceslovná konstrukce je nevýhodná."""

    name = "economy"

    def scores(self, batch: PressureBatch) -> FloatArray:
        cost = batch.world.params.economy_word_cost
        return _scores(batch, lambda construction, _, __: -cost * construction.words)


class Fusion(Pressure):
    """Častá konstrukce srůstá: krok dál na škále gramatikalizace má výhodu.

    Tlak působí jen jedním směrem (jednosměrnost gramatikalizace): zpět
    k volnějšímu tvaru nic netlačí.
    """

    name = "fusion"

    def scores(self, batch: PressureBatch) -> FloatArray:
        bonus = batch.world.params.fusion_bonus

        def value(construction: Construction, current: Construction | None, _: str) -> float:
            if current is None or current.rank == 0:
                return 0.0
            return bonus if construction.rank == current.rank + 1 else 0.0

        return _scores(batch, value)


class Learnability(Pressure):
    """Dospělí, kteří se jazyk učí jako druhý, vázané výrazy neudrží.

    Koncovka a přiklonka jsou nevýhodné úměrně podílu L2 mluvčích ve
    skupině; volné slovo ani nevyjádřená funkce nic nestojí. Jazyky s více
    L2 mluvčími mají méně pádů (Bentz & Winter 2013) a kontaktní variety
    dávají přednost volným výrazům (Trudgill 2011; McWhorter 2007). Bez L2
    mluvčích je tlak nulový.
    """

    name = "learnability"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        shares = np.array([world.groups[group_id].main_code.l2_share for group_id in batch.group_ids])
        if not shares.any():
            return np.zeros_like(batch.freqs)
        strength = world.params.learnability_strength
        bound = _scores(batch, lambda construction, _, __: -strength * construction.bound)
        return bound * shares[None, :, None]


class Ambiguity(Pressure):
    """Funkce, kterou jazyk přestal vyjadřovat, se musí poznat jinak.

    Když pádová koncovka předmětu splynula s citačním tvarem, volný
    slovosled nerozliší, kdo je podmět a kdo předmět: je nevýhodný úměrně
    tomu, kolik tvarů splynulo, a pevný slovosled nese role místo pádu
    (analytizace). Dokud pád drží, je pevný slovosled jen nepatrnou
    zbytečnou rigiditou. Které funkce lze takto nahradit, říká katalog
    (``compensates``).
    """

    name = "ambiguity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        functions = catalog_for(world)
        rigidity = world.params.order_rigidity

        def value(construction: Construction, current: Construction | None, group_id: str) -> float:
            code = world.groups[group_id].main_code
            score = 0.0
            for compensated in functions[construction.function].compensates:
                lost = syntax.weakness(world, code, compensated)
                if construction.carries_order:
                    score -= rigidity * (1.0 - lost)
                else:
                    score -= functions[compensated].need * lost
            return score

        return _scores(batch, value)

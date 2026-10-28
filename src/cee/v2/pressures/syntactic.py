"""Syntaktické tlaky (iterace 3; milníky M4 a M4b).

Žádný tlak nezná konkrétní funkci; co funkce potřebuje (``need``) a čí roli
může převzít (``compensates``), říká katalog gramatických funkcí.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from cee.v2 import syntax
from cee.v2.language.constructions import Construction, catalog
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
    komunikace potřebuje (minulý čas víc než určenost).
    """

    name = "expressivity"

    def scores(self, batch: PressureBatch) -> FloatArray:
        world = batch.world
        functions = catalog()

        def value(construction: Construction, current: Construction | None, group_id: str) -> float:
            need = functions[construction.function].need
            if need == 0.0:
                return 0.0
            return need * syntax.strength(world, world.groups[group_id].main_code, construction)

        return _scores(batch, value)


class Economy(Pressure):
    """Každé slovo navíc stojí úsilí; víceslovná konstrukce je nevýhodná."""

    name = "economy"

    def scores(self, batch: PressureBatch) -> FloatArray:
        return _scores(batch, lambda construction, _, __: -0.15 * construction.words)


class Fusion(Pressure):
    """Častá konstrukce srůstá: krok dál na škále gramatikalizace má výhodu.

    Tlak působí jen jedním směrem (jednosměrnost gramatikalizace): zpět
    k volnějšímu tvaru nic netlačí.
    """

    name = "fusion"

    def scores(self, batch: PressureBatch) -> FloatArray:
        def value(construction: Construction, current: Construction | None, _: str) -> float:
            if current is None or current.rank == 0:
                return 0.0
            return 0.25 if construction.rank == current.rank + 1 else 0.0

        return _scores(batch, value)


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
        functions = catalog()

        def value(construction: Construction, current: Construction | None, group_id: str) -> float:
            code = world.groups[group_id].main_code
            score = 0.0
            for compensated in functions[construction.function].compensates:
                lost = syntax.weakness(world, code, compensated)
                if construction.carries_order:
                    score -= 0.05 * (1.0 - lost)
                else:
                    score -= functions[compensated].need * lost
            return score

        return _scores(batch, value)

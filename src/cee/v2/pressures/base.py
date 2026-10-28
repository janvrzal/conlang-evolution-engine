"""Rodič všech tlaků."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.repertoire import Variant

if TYPE_CHECKING:
    from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class PressureBatch:
    """Výřez živých proměnných jednoho typu, které se hodnotí najednou.

    ``freqs`` má tvar (proměnné, skupiny, sloty). ``slots[b][k]`` je ID
    varianty v daném slotu, nebo ``None`` pro prázdný slot.
    """

    world: World
    variable_ids: Sequence[str]
    group_ids: Sequence[str]
    freqs: FloatArray
    slots: Sequence[Sequence[str | None]]
    tick: int

    def slot_values(self, value: Callable[[Variant], float], empty: float = 0.0) -> FloatArray:
        """Vlastnost varianty v každém slotu, tvar (proměnné, 1, sloty)."""
        variants = self.world.variants
        table = np.array(
            [[empty if variant is None else value(variants[variant]) for variant in row]
             for row in self.slots],
            dtype=np.float64,
        ).reshape(len(self.slots), 1, -1)
        return table

    def payload(self, key: str, default: Any = 0.0) -> FloatArray:
        return self.slot_values(lambda variant: float(variant.payload.get(key, default)))


class Pressure(ABC):
    """Ohodnotí varianty: jak výhodná je varianta v dané skupině.

    Tlak sám nic nevyrábí. Hodnotí celý výřez naráz (proměnné × skupiny ×
    sloty), protože po jednotlivých variantách by to bylo řádově pomalejší.
    Výsledek leží v intervalu [−1, 1]; váhu tlaku určuje změna, která ho
    připojila.
    """

    name: ClassVar[str]

    @abstractmethod
    def scores(self, batch: PressureBatch) -> FloatArray:
        """Výsledek má tvar ``batch.freqs`` nebo se na něj dá rozšířit."""

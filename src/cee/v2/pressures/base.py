"""Rodič všech tlaků."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    varianty v daném slotu, nebo ``None`` pro prázdný slot. ``numbers`` jsou
    tytéž sloty jako čísla variant z registru světa (−1 = prázdný slot), když
    je zná fond (:attr:`cee.v2.pools.PoolBlock.slot_variants`); jinak se
    dopočtou z ``slots``.
    """

    world: World
    variable_ids: Sequence[str]
    group_ids: Sequence[str]
    freqs: FloatArray
    slots: Sequence[Sequence[str | None]]
    tick: int
    #: Co skupiny slyší od sebe i sousedů (stejný tvar jako ``freqs``).
    heard: FloatArray
    #: Mezivýsledky sdílené tlaky v rámci jednoho kroku.
    memo: dict[Any, Any] = field(default_factory=dict)
    numbers: npt.NDArray[np.intp] | None = None

    def slot_values(self, value: Callable[[Variant], float], empty: float = 0.0) -> FloatArray:
        """Vlastnost varianty v každém slotu, tvar (proměnné, 1, sloty)."""
        variants = self.world.variants
        table = np.array(
            [[empty if variant is None else value(variants[variant]) for variant in row]
             for row in self.slots],
            dtype=np.float64,
        ).reshape(len(self.slots), 1, -1)
        return table

    def slot_numbers(self) -> npt.NDArray[np.intp]:
        """Čísla variant ze registru ve slotech, tvar (proměnné, sloty); −1 = prázdný slot."""
        if self.numbers is not None:
            return self.numbers
        found = self.memo.get("slot-numbers")
        if found is None:
            numbers = self.world.registry.variants.numbers
            found = np.array(
                [[-1 if variant is None else numbers[variant] for variant in row] for row in self.slots],
                dtype=np.intp,
            ).reshape(len(self.slots), -1)
            self.memo["slot-numbers"] = found
        return found  # type: ignore[no-any-return]

    def slot_column(self, name: str, empty: float) -> npt.NDArray[Any]:
        """Sloupec tabulky variant (:class:`cee.v2.tables.VariantTable`) ve slotech, tvar (proměnné, sloty).

        Prázdný slot dostane ``empty``. Totéž co ``slot_values`` nad vlastností
        varianty, jen z pole místo z objektů; hodnoty sloupce vzniknou při uložení
        varianty, takže jsou stejné jako atributy objektu.
        """
        numbers = self.slot_numbers()
        column = self.world.columns.variants.arrays()[name]
        if not len(column):
            return np.full(numbers.shape, empty, dtype=np.float64)
        return np.where(numbers >= 0, column[numbers], empty)

    def payload(self, key: str, default: Any = 0.0) -> FloatArray:
        if key == "appeal":
            # Přitažlivost ze sloupce (NaN = varianta ji v payloadu nemá).
            appeal = self.slot_column("appeal", 0.0)
            numbers = self.slot_numbers()
            found = np.where(np.isnan(appeal) & (numbers >= 0), float(default), appeal)
            return found.reshape(len(self.slots), 1, -1)  # type: ignore[no-any-return]
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

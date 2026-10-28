"""Živé proměnné uložené po sloupcích pro vektorový přenos.

Repertoáry skupin jsou výhodné pro ukládání (copy-on-write), ale přenos
potřebuje opak: jednu proměnnou přes všechny skupiny naráz. Proměnné, ve
kterých se skupiny liší, proto leží v polích ``freqs`` o tvaru
(proměnné, skupiny, sloty). Slot je místo pro jednu variantu dané proměnné.

Proměnné se dělí do bloků podle počtu potřebných slotů (2, 4, 8, …). Jediná
proměnná s mnoha soutěžícími variantami tak nezvětší pole všem ostatním.
Proměnná, která je ve všech skupinách stejná a ustálená, se vrátí do
repertoárů a ze skladu zmizí. Jediné čtení stavu je
:meth:`cee.v2.world.World.distribution`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.repertoire import Distribution
from cee.v2.rng import stable_int

if TYPE_CHECKING:
    from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
KeyArray = npt.NDArray[np.uint64]
Row = tuple[str, FloatArray, FloatArray, BoolArray, list[str | None], KeyArray]

_MIN_CAPACITY = 2


class PoolBlock:
    """Proměnné se stejnou kapacitou slotů.

    Řádky leží v předalokovaném zásobníku, takže přidání i odebrání proměnné
    je amortizovaně konstantní. Odebraný řádek nahradí poslední; pořadí řádků
    tím nemá vliv na výsledek, protože každý řádek se počítá samostatně a log
    se řadí kanonicky.
    """

    def __init__(self, groups: int, capacity: int):
        self.capacity = capacity
        self.variable_ids: list[str] = []
        self.slots: list[list[str | None]] = []
        self._rows: dict[str, int] = {}
        self._freqs = np.zeros((4, groups, capacity))
        self._previous = np.zeros_like(self._freqs)
        self._present = np.zeros((4, groups), dtype=bool)
        self._keys = np.zeros((4, capacity), dtype=np.uint64)

    def __len__(self) -> int:
        return len(self.variable_ids)

    @property
    def freqs(self) -> FloatArray:
        return self._freqs[: len(self)]

    @freqs.setter
    def freqs(self, value: FloatArray) -> None:
        self._freqs[: len(self)] = value

    @property
    def previous(self) -> FloatArray:
        return self._previous[: len(self)]

    @previous.setter
    def previous(self, value: FloatArray) -> None:
        self._previous[: len(self)] = value

    @property
    def present(self) -> BoolArray:
        return self._present[: len(self)]

    @property
    def slot_keys(self) -> KeyArray:
        return self._keys[: len(self)]

    def row_of(self, variable_id: str) -> int:
        return self._rows[variable_id]

    def append(self, row: Row) -> None:
        """Přidá řádek; jeho pole mají tvar (skupiny, sloty ≤ kapacita)."""
        variable_id, freqs, previous, present, slots, keys = row
        index = len(self)
        if index == len(self._freqs):
            grow = len(self._freqs)
            self._freqs = np.concatenate([self._freqs, np.zeros_like(self._freqs[:grow])])
            self._previous = np.concatenate([self._previous, np.zeros_like(self._previous[:grow])])
            self._present = np.concatenate([self._present, np.zeros_like(self._present[:grow])])
            self._keys = np.concatenate([self._keys, np.zeros_like(self._keys[:grow])])
        width = freqs.shape[1]
        self._freqs[index] = 0.0
        self._previous[index] = 0.0
        self._keys[index] = 0
        self._freqs[index, :, :width] = freqs
        self._previous[index, :, :width] = previous
        self._present[index] = present
        self._keys[index, :width] = keys
        self.variable_ids.append(variable_id)
        self.slots.append([*slots, *([None] * (self.capacity - width))])
        self._rows[variable_id] = index

    def extract(self, rows: Sequence[int]) -> list[Row]:
        """Vyjme řádky z bloku a vrátí jejich obsah (kopie)."""
        taken: list[Row] = [
            (self.variable_ids[row], self._freqs[row].copy(), self._previous[row].copy(),
             self._present[row].copy(), list(self.slots[row]), self._keys[row].copy())
            for row in rows
        ]
        for row in sorted(rows, reverse=True):
            last = len(self) - 1
            del self._rows[self.variable_ids[row]]
            if row != last:
                self._freqs[row] = self._freqs[last]
                self._previous[row] = self._previous[last]
                self._present[row] = self._present[last]
                self._keys[row] = self._keys[last]
                self.variable_ids[row] = self.variable_ids[last]
                self.slots[row] = self.slots[last]
                self._rows[self.variable_ids[row]] = row
            self.variable_ids.pop()
            self.slots.pop()
        return taken


class LivePools:
    def __init__(self, group_ids: Sequence[str] = ()):
        self.group_ids: list[str] = list(group_ids)
        self.group_index = {group_id: index for index, group_id in enumerate(self.group_ids)}
        self.blocks: dict[int, PoolBlock] = {}
        self._block_of: dict[str, int] = {}
        self._keys: dict[str, int] = {}

    # --- čtení --------------------------------------------------------

    def __contains__(self, variable_id: object) -> bool:
        return variable_id in self._block_of

    def __len__(self) -> int:
        return len(self._block_of)

    @property
    def variable_ids(self) -> list[str]:
        return sorted(self._block_of)

    def iter_blocks(self) -> Iterator[PoolBlock]:
        for capacity in sorted(self.blocks):
            if len(self.blocks[capacity]):
                yield self.blocks[capacity]

    def holds(self, group_id: str, variable_id: str) -> bool:
        """Má skupina tuto živou proměnnou? Levnější než :meth:`get`."""
        block = self.blocks[self._block_of[variable_id]]
        return bool(block.present[block.row_of(variable_id), self.group_index[group_id]])

    def get(self, group_id: str, variable_id: str) -> Distribution | None:
        block = self.blocks[self._block_of[variable_id]]
        row = block.row_of(variable_id)
        column = self.group_index[group_id]
        if not block.present[row, column]:
            return None
        used = sorted(
            (variant, slot) for slot, variant in enumerate(block.slots[row])
            if variant is not None and block.freqs[row, column, slot] > 0
        )
        slots = [slot for _, slot in used]
        return Distribution(
            tuple(variant for variant, _ in used),
            block.freqs[row, column, slots].copy(),
            block.previous[row, column, slots].copy(),
        )

    # --- zápis --------------------------------------------------------

    def load(self, variable_id: str, distributions: Sequence[Distribution | None]) -> None:
        """Převezme proměnnou z repertoárů všech skupin (v pořadí ``group_ids``)."""
        if variable_id in self._block_of:
            raise ValueError(f"Proměnná {variable_id} už je živá.")
        variants = sorted({v for item in distributions if item is not None for v in item.variants})
        slot_of = {variant: slot for slot, variant in enumerate(variants)}
        groups = len(self.group_ids)
        freqs, previous = np.zeros((groups, len(variants))), np.zeros((groups, len(variants)))
        present = np.zeros(groups, dtype=bool)
        for column, item in enumerate(distributions):
            if item is None:
                continue
            present[column] = True
            for variant, freq, before in zip(item.variants, item.freqs, item.previous):
                freqs[column, slot_of[variant]] = freq
                previous[column, slot_of[variant]] = before
        keys = np.array([self._key(variant) for variant in variants], dtype=np.uint64)
        slots: list[str | None] = list(variants)
        # Rezerva jednoho slotu: proměnná se načítá kvůli nové inovaci.
        self._place(_capacity_for(len(variants) + 1),
                    (variable_id, freqs, previous, present, slots, keys))

    def innovate(self, variable_id: str, group_id: str, variant_id: str, share: float) -> None:
        """Nová varianta v jedné skupině s podílem ``share``, bez trendu."""
        block = self.blocks[self._block_of[variable_id]]
        row = block.row_of(variable_id)
        if None not in block.slots[row]:
            self._move(variable_id, block.capacity * 2)
            block = self.blocks[self._block_of[variable_id]]
            row = block.row_of(variable_id)
        slot = block.slots[row].index(None)
        column = self.group_index[group_id]
        block.slots[row][slot] = variant_id
        block.slot_keys[row, slot] = self._key(variant_id)
        block.freqs[row, column] *= 1.0 - share
        block.freqs[row, column, slot] = share
        block.previous[row, column] = block.freqs[row, column]

    def release(self) -> list[tuple[str, list[Distribution | None]]]:
        """Vyjme proměnné, které jsou všude stejné a ustálené.

        Uvolní také sloty variant, které už nežije žádná skupina, a proměnné
        využívající jen čtvrtinu kapacity přesune do menšího bloku.
        """
        released: list[tuple[str, list[Distribution | None]]] = []
        for block in list(self.iter_blocks()):
            alive = (block.freqs > 0).any(axis=1)
            for row, slot in zip(*np.nonzero(~alive)):
                if block.slots[row][slot] is not None:
                    block.slots[row][slot] = None
                    block.slot_keys[row, slot] = 0
                    block.previous[row, :, slot] = 0.0
            held = np.where(block.present[:, :, None], block.freqs, 0.0)
            single = ((held > 0).sum(axis=2) <= 1) | ~block.present
            leader = np.where(block.present, held.argmax(axis=2), -1)
            first = leader.max(axis=1, keepdims=True)
            same = ((leader == first) | (leader == -1)).all(axis=1)
            uniform = [int(row) for row in np.flatnonzero(single.all(axis=1) & same)]
            for row in uniform:
                variable_id = block.variable_ids[row]
                released.append(
                    (variable_id, [self.get(group_id, variable_id) for group_id in self.group_ids])
                )
            for variable_id, *_ in block.extract(uniform):
                del self._block_of[variable_id]
            if block.capacity > _MIN_CAPACITY and len(block):
                used = np.array([[slot is not None for slot in row] for row in block.slots])
                sparse = np.flatnonzero(used.sum(axis=1) <= block.capacity // 4)
                for variable_id in [block.variable_ids[row] for row in sparse]:
                    self._move(variable_id, block.capacity // 2)
        return sorted(released, key=lambda item: item[0])

    def sync_groups(self, world: World) -> None:
        """Přizpůsobí osu skupin světu po události, která skupiny přidala či ubrala.

        Nová skupina převezme živé proměnné ze svého repertoáru; zjemnění
        proto musí souhrnnou skupinu před odebráním zhmotnit
        (:meth:`cee.v2.world.World.materialize`).
        """
        group_ids = world.group_ids()
        if group_ids == self.group_ids:
            return
        # Málo častá operace: živé proměnné se zhmotní a znovu načtou.
        for group_id in self.group_ids:
            if group_id in world.groups:
                world.materialize(group_id)
        variable_ids = self.variable_ids
        self.group_ids = list(group_ids)
        self.group_index = {group_id: index for index, group_id in enumerate(group_ids)}
        self.blocks, self._block_of = {}, {}
        for variable_id in variable_ids:
            self.load(variable_id, [
                world.groups[group_id].main_code.repertoire.get(variable_id) for group_id in group_ids
            ])

    # --- pomocné ------------------------------------------------------

    def _place(self, capacity: int, row: Row) -> None:
        variable_id, freqs, previous, present, slots, keys = row
        used = [index for index, slot in enumerate(slots) if slot is not None]
        capacity = max(capacity, _capacity_for(len(used)))
        block = self.blocks.get(capacity)
        if block is None:
            block = self.blocks[capacity] = PoolBlock(len(self.group_ids), capacity)
        block.append((variable_id, freqs[:, used], previous[:, used], present,
                      [slots[index] for index in used], keys[used]))
        self._block_of[variable_id] = capacity

    def _move(self, variable_id: str, capacity: int) -> None:
        block = self.blocks[self._block_of[variable_id]]
        (row,) = block.extract([block.row_of(variable_id)])
        self._place(max(_MIN_CAPACITY, capacity), row)

    def _key(self, variant_id: str) -> int:
        """Klíč varianty pro hashovaný drift; nezávisí na slotu ani na bloku."""
        key = self._keys.get(variant_id)
        if key is None:
            key = self._keys[variant_id] = stable_int("variant-key", variant_id)
        return key


def _capacity_for(slots: int) -> int:
    capacity = _MIN_CAPACITY
    while capacity < slots:
        capacity *= 2
    return capacity

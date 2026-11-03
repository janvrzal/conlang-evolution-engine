"""Živé proměnné: řídké uložení po variantách a husté bloky pro vektorový přenos.

Repertoáry skupin jsou výhodné pro ukládání (copy-on-write), ale přenos
potřebuje opak: jednu proměnnou přes všechny skupiny naráz. Proměnné, ve
kterých se skupiny liší, proto tvoří bloky o tvaru (proměnné, skupiny, sloty).
Slot je místo pro jednu variantu dané proměnné.

**Uložení je řídké a po variantách.** Hustá pole ``freqs`` a ``previous`` jsou
jen pohled, který se podle potřeby sestaví z řídkého uložení (a zahodí v
:meth:`LivePools.compact`). Skutečně se drží jen výskyty: pro každý řádek
(proměnnou) a slot (variantu) seřazený seznam skupin, které variantu mají, s
podílem a trendovou základnou (:class:`RowCells`). Seznam jedné varianty je
tedy její mapa rozšíření přímo v datech (:meth:`LivePools.range_of`), a co je u
skupiny, dá hledání skupiny v seznamech slotů řádku (:meth:`PoolBlock.cell`),
nebo hustý pohled, je-li právě sestavený. Paměť roste s počtem výskytů, ne se
součinem skupin a slotů. Skupiny, které proměnnou vůbec nemají, drží hustá
bool pole ``present`` (jeden bajt na skupinu a proměnnou).

Uložení buněk má dvě podoby se stejným rozhraním: ``cee_core.NativeCells`` v Rustu
(stav bloku žije v Rustu po celý běh, Python drží rukojeť; hustý pohled a výsledky
přenosu jsou pole Rustu sdílená s ``numpy`` bez kopie) a :class:`PyCells` v Pythonu
(bez rozšíření nebo s ``CEE_NATIVE=0``). Oba dávají stejné bity. Pohled ``freqs`` a
``previous`` je jen pro čtení a po změně bloku zůstane, jaký byl (Rust pole nepřepíše,
dokud na ně někdo odkazuje).

Přenos (:mod:`cee.v2.transmission`) bere hustý pohled jen na dobu jednoho kroku:
míšení sčítá postupně přes zdroje (viz :mod:`cee.v2.phases_transmission`), takže
pořadí součtů nezávisí na tvaru matice a Rust ho zopakuje bit po bitu. Hustý blok
vzniká na dobu jednoho kroku a po zápisu výsledku se zahodí (velké bloky) nebo
se ponechá jako pohled.

Slot drží **číslo varianty z registru** světa (:mod:`cee.v2.registry`, −1 =
prázdný slot), ne řetězec: ``PoolBlock.slot_variants``. Řetězcová ID variant
v ``PoolBlock.slots`` jsou odvozený pohled pro tlaky, testy a deníky; pole a
převody pracují s čísly. Číslo neurčuje pořadí (to dál rozhoduje řetězec ID,
viz :meth:`LivePools.get`).

Proměnné se dělí do bloků podle počtu potřebných slotů (2, 4, 8, …). Jediná
proměnná s mnoha soutěžícími variantami tak nezvětší pole všem ostatním.
Proměnná, která je ve všech skupinách stejná a ustálená, se vrátí do
repertoárů a ze skladu zmizí. Jediné čtení stavu je
:meth:`cee.v2.world.World.distribution`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.registry import Numbering
from cee.v2.repertoire import Distribution
from cee.v2.rng import stable_int

if TYPE_CHECKING:
    from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]
KeyArray = npt.NDArray[np.uint64]
IntArray = npt.NDArray[np.intp]
Row = tuple[str, FloatArray, FloatArray, BoolArray, list[str | None], KeyArray]

_MIN_CAPACITY = 2
#: Blok s víc buňkami (proměnné × skupiny × sloty) si po kroku hustý pohled nenechává.
DENSE_KEEP_CELLS = 1 << 18


class RowCells:
    """Výskyty variant jedné proměnné: buňky (slot, skupina) seřazené podle slotu a skupiny.

    ``slot[k]`` je slot, ``group[k]`` sloupec skupiny, ``freq[k]`` její podíl
    varianty a ``prev[k]`` trendová základna. Buňka tu je, má-li kladný podíl
    nebo nenulovou základnu; chybějící buňka je nula. Úsek jednoho slotu je
    souvislý (``starts[slot]:starts[slot + 1]``) a v něm skupiny rostou, takže
    skupina ve variantě se hledá půlením.
    """

    __slots__ = ("slot", "group", "freq", "prev", "starts")

    def __init__(self, slot: Any, group: Any, freq: FloatArray, prev: FloatArray, starts: Any):
        self.slot, self.group, self.freq, self.prev, self.starts = slot, group, freq, prev, starts

    @classmethod
    def build(cls, slot: Any, group: Any, freq: FloatArray, prev: FloatArray, capacity: int) -> RowCells:
        """Buňky seřazené podle slotu a skupiny; začátky úseků slotů se dopočtou."""
        return cls(slot, group, freq, prev, np.searchsorted(slot, np.arange(capacity + 1)))

    @classmethod
    def from_dense(cls, freqs: FloatArray, previous: FloatArray, capacity: int) -> RowCells:
        """Buňky z husté matice (skupiny, sloty ≤ ``capacity``) jedné proměnné."""
        slots, groups = np.nonzero(((freqs > 0) | (previous != 0)).T)
        return cls.build(slots.astype(np.int16), groups.astype(np.int32), freqs[groups, slots],
                         previous[groups, slots], capacity)

    def __len__(self) -> int:
        return len(self.slot)

    def span(self, slot: int) -> tuple[int, int]:
        """Úsek buněk jednoho slotu: ``[od, do)``."""
        starts = self.starts
        if slot + 1 >= len(starts):
            return len(self.slot), len(self.slot)
        return int(starts[slot]), int(starts[slot + 1])

    def to_dense(self, groups: int, capacity: int) -> tuple[FloatArray, FloatArray]:
        freqs, previous = np.zeros((groups, capacity)), np.zeros((groups, capacity))
        freqs[self.group, self.slot] = self.freq
        previous[self.group, self.slot] = self.prev
        return freqs, previous


class _Base:
    """Buňky všech řádků bloku v jednom poli po řádcích (výsledek posledního zápisu celého bloku)."""

    __slots__ = ("pointer", "bounds", "slot", "group", "freq", "prev")

    def __init__(self, pointer: Any, bounds: Any, slot: Any, group: Any, freq: FloatArray, prev: FloatArray):
        #: ``pointer[r]:pointer[r + 1]`` jsou buňky řádku r; ``bounds[r, s]`` začátek slotu s v řádku (relativně).
        self.pointer, self.bounds = pointer, bounds
        self.slot, self.group, self.freq, self.prev = slot, group, freq, prev

    @property
    def rows(self) -> int:
        return len(self.pointer) - 1

    def row(self, index: int) -> RowCells:
        low, high = int(self.pointer[index]), int(self.pointer[index + 1])
        return RowCells(self.slot[low:high], self.group[low:high], self.freq[low:high], self.prev[low:high],
                        self.bounds[index])


class PyCells:
    """Buňky bloku v Pythonu (referenční uložení; bez Rustu nebo s ``CEE_NATIVE=0``).

    Buňky všech řádků drží ``_base`` (celý blok najednou po posledním zápisu) a
    ``_edited`` (řádky změněné nebo přidané od té doby). Rozhraní je totéž co
    ``cee_core.NativeCells`` (viz :mod:`cee.v2.native`), takže :class:`PoolBlock`
    nepozná, které uložení drží.
    """

    def __init__(self, groups: int, capacity: int):
        self.groups = groups
        self.capacity = capacity
        self.size = 0
        self._base: _Base | None = None
        self._edited: dict[int, RowCells] = {}
        self._staged: _Base | None = None

    def __len__(self) -> int:
        return self.size

    @classmethod
    def from_flat(cls, groups: int, capacity: int, pointer: Any, slot: Any, group: Any, freq: Any,
                  prev: Any, threads: int = 1) -> PyCells:
        """Uložený stav (viz :meth:`flat`)."""
        store = cls(groups, capacity)
        store.size = len(pointer) - 1
        bounds = np.zeros((store.size, capacity + 1), dtype=np.int64)
        for row in range(store.size):
            low, high = int(pointer[row]), int(pointer[row + 1])
            bounds[row] = np.searchsorted(slot[low:high], np.arange(capacity + 1))
        store._base = _Base(np.asarray(pointer, dtype=np.int64), bounds, np.asarray(slot, dtype=np.int16),
                            np.asarray(group, dtype=np.int32), np.asarray(freq, dtype=np.float64),
                            np.asarray(prev, dtype=np.float64))
        return store

    def flat(self) -> tuple[Any, Any, Any, Any, Any]:
        """Stav po řádcích za sebou: ukazatele řádků, sloty, skupiny, podíly, základny."""
        rows = [self.cells(row) for row in range(self.size)]
        pointer = np.zeros(self.size + 1, dtype=np.int64)
        np.cumsum([len(cells) for cells in rows], out=pointer[1:])
        if not rows:
            return pointer, np.zeros(0, np.int16), np.zeros(0, np.int32), np.zeros(0), np.zeros(0)
        return (pointer, np.concatenate([cells.slot for cells in rows]).astype(np.int16),
                np.concatenate([cells.group for cells in rows]).astype(np.int32),
                np.concatenate([cells.freq for cells in rows]), np.concatenate([cells.prev for cells in rows]))

    def set_threads(self, threads: int) -> None:
        """Python uložení vlákna nepoužívá."""

    # --- čtení --------------------------------------------------------

    def cells(self, row: int) -> RowCells:
        """Výskyty variant proměnné v řádku (pohled do uložení, neměnit)."""
        edited = self._edited.get(row)
        if edited is not None:
            return edited
        assert self._base is not None
        return self._base.row(row)

    def dense(self) -> tuple[FloatArray, FloatArray]:
        """Hustý tvar celého bloku (proměnné, skupiny, sloty); nová pole."""
        size = self.size
        freqs = np.zeros((size, self.groups, self.capacity))
        previous = np.zeros_like(freqs)
        base = self._base
        if base is not None and len(base.slot):
            owner = np.repeat(np.arange(base.rows), np.diff(base.pointer))
            stale = np.zeros(base.rows, dtype=bool)
            stale[size:] = True
            stale[np.array([row for row in self._edited if row < base.rows], dtype=np.intp)] = True
            keep = ~stale[owner]
            freqs[owner[keep], base.group[keep], base.slot[keep]] = base.freq[keep]
            previous[owner[keep], base.group[keep], base.slot[keep]] = base.prev[keep]
        for row, cells in self._edited.items():
            freqs[row, cells.group, cells.slot] = cells.freq
            previous[row, cells.group, cells.slot] = cells.prev
        return freqs, previous

    def row_dense(self, row: int) -> tuple[FloatArray, FloatArray]:
        return self.cells(row).to_dense(self.groups, self.capacity)

    def cell(self, row: int, column: int) -> tuple[IntArray, FloatArray, FloatArray]:
        """Sloty s kladným podílem u jedné skupiny: (sloty vzestupně, podíly, základny)."""
        cells = self.cells(row)
        found = np.flatnonzero((cells.group == column) & (cells.freq > 0))
        return cells.slot[found].astype(np.intp), cells.freq[found], cells.prev[found]

    def value(self, row: int, column: int, slot: int) -> float:
        """Podíl varianty ve slotu u jedné skupiny (0, když tam není)."""
        edited = self._edited.get(row)
        if edited is None:
            base = self._base
            assert base is not None
            first = int(base.pointer[row])
            start, stop = first + int(base.bounds[row, slot]), first + int(base.bounds[row, slot + 1])
            groups, freqs = base.group, base.freq
        else:
            start, stop = edited.span(slot)
            groups, freqs = edited.group, edited.freq
        index = start + int(groups[start:stop].searchsorted(column))
        if index < stop and groups[index] == column:
            return float(freqs[index])
        return 0.0

    def range_of(self, row: int, slot: int) -> tuple[IntArray, FloatArray]:
        """Mapa rozšíření varianty: sloupce skupin, které ji mají, a její podíly u nich."""
        cells = self.cells(row)
        low, high = cells.span(slot)
        shares = cells.freq[low:high]
        kept = shares > 0
        return cells.group[low:high][kept].astype(np.intp), shares[kept]

    def entries(self) -> int:
        """Počet uložených buněk (výskytů variant) celého bloku."""
        base = self._base
        total = 0
        if base is not None:
            limit = min(self.size, base.rows)
            total = int(base.pointer[limit]) - sum(
                int(base.pointer[row + 1] - base.pointer[row]) for row in self._edited if row < limit
            )
        return total + sum(len(cells) for row, cells in self._edited.items() if row < self.size)

    def nbytes(self) -> int:
        """Paměť řídkého uložení v bajtech."""
        total = 0
        if self._base is not None:
            base = self._base
            total += (base.pointer.nbytes + base.bounds.nbytes + base.slot.nbytes + base.group.nbytes
                      + base.freq.nbytes + base.prev.nbytes)
        for cells in self._edited.values():
            total += (cells.slot.nbytes + cells.group.nbytes + cells.freq.nbytes + cells.prev.nbytes
                      + cells.starts.nbytes)
        return total

    # --- zápis --------------------------------------------------------

    def stage(self, freqs: FloatArray, previous: FloatArray) -> None:
        """Připraví nový stav celého bloku z hustých polí; zapíše ho až :meth:`commit`."""
        size = self.size
        if freqs.shape != (size, self.groups, self.capacity) or previous.shape != freqs.shape:
            raise ValueError("Pole musí mít tvar (proměnné, skupiny, sloty) bloku.")
        rows, slots, groups = np.nonzero(((freqs > 0) | (previous != 0)).transpose(0, 2, 1))
        pointer = np.zeros(size + 1, dtype=np.int64)
        np.cumsum(np.bincount(rows, minlength=size), out=pointer[1:])
        bounds = np.zeros((size, self.capacity + 1), dtype=np.int64)
        np.cumsum(np.bincount(rows * self.capacity + slots, minlength=size * self.capacity)
                  .reshape(size, self.capacity), axis=1, out=bounds[:, 1:])
        self._staged = _Base(pointer, bounds, slots.astype(np.int16), groups.astype(np.int32),
                             freqs[rows, groups, slots], previous[rows, groups, slots])

    def commit(self, keep_dense: bool = True) -> None:
        """Zapíše stav připravený :meth:`stage` (řádky bloku se mezitím nesměly změnit)."""
        assert self._staged is not None
        base, self._staged = self._staged, None
        if base.rows != self.size:
            raise ValueError("Řádky bloku se mezi přípravou a zápisem stavu změnily.")
        self._base, self._edited = base, {}

    def append(self, freqs: FloatArray, previous: FloatArray) -> None:
        """Přidá řádek; pole mají tvar (skupiny, sloty ≤ kapacita)."""
        self._edited[self.size] = RowCells.from_dense(freqs, previous, self.capacity)
        self.size += 1

    def swap_remove(self, row: int) -> None:
        """Odebere řádek; na jeho místo přijde poslední."""
        last = self.size - 1
        if row != last:
            self._edited[row] = self.cells(last)
        self._edited.pop(last, None)
        self.size -= 1

    def add_share(self, row: int, column: int, slot: int, share: float) -> None:
        """Nová varianta ve slotu u jedné skupiny: ostatní podíly skupiny se zmenší, základna se vyrovná.

        Totéž co ``freqs[row, column] *= 1 − share; freqs[row, column, slot] += share;
        previous[row, column] = freqs[row, column]`` nad hustým polem.
        """
        cells = self.cells(row)
        mine = np.flatnonzero(cells.group == column)
        scaled = cells.freq[mine] * (1.0 - share)
        here = np.flatnonzero(cells.slot[mine] == slot)
        if len(here):
            scaled[here[0]] = scaled[here[0]] + share
        if len(scaled) and not (scaled > 0).all():
            self._add_share_general(row, column, slot, share)
            return
        freq, prev = cells.freq.copy(), cells.prev.copy()
        freq[mine] = prev[mine] = scaled
        if len(here):
            self._edited[row] = RowCells(cells.slot, cells.group, freq, prev, cells.starts)
        else:
            # Skupina varianty ještě nemá: nová buňka se vloží na své místo v úseku slotu.
            start, stop = cells.span(slot)
            at = start + int(cells.group[start:stop].searchsorted(column))
            starts = cells.starts.copy()
            starts[slot + 1:] += 1
            self._edited[row] = RowCells(
                _inserted(cells.slot, at, slot), _inserted(cells.group, at, column),
                _inserted(freq, at, 0.0 + share), _inserted(prev, at, 0.0 + share), starts,
            )

    def _add_share_general(self, row: int, column: int, slot: int, share: float) -> None:
        """Totéž pro skupinu, jejíž buňka by zanikla (podíl 0 se základnou ≠ 0); buňky se přeskládají."""
        cells = self.cells(row)
        mine = cells.group == column
        slots, shares = cells.slot[mine], cells.freq[mine] * (1.0 - share)
        found = np.flatnonzero(slots == slot)
        if len(found):
            shares[found[0]] = shares[found[0]] + share
        else:
            slots, shares = np.append(slots, np.int16(slot)), np.append(shares, 0.0 + share)
        positive = shares > 0
        slots, shares = slots[positive], shares[positive]
        merged_slot = np.concatenate([cells.slot[~mine], slots])
        merged_group = np.concatenate([cells.group[~mine], np.full(len(slots), column, dtype=np.int32)])
        merged_freq = np.concatenate([cells.freq[~mine], shares])
        merged_prev = np.concatenate([cells.prev[~mine], shares])
        order = np.lexsort((merged_group, merged_slot))
        self._edited[row] = RowCells.build(
            merged_slot[order], merged_group[order], merged_freq[order], merged_prev[order], self.capacity
        )

    def free_slots(self, row: int, slots: Sequence[int]) -> None:
        """Odebere buňky uvolněných slotů řádku."""
        cells = self.cells(row)
        kept = ~np.isin(cells.slot, slots)
        self._edited[row] = RowCells.build(
            cells.slot[kept], cells.group[kept], cells.freq[kept], cells.prev[kept], self.capacity
        )


def new_cells(groups: int, capacity: int) -> Any:
    """Prázdné uložení buněk: ``NativeCells`` v Rustu, jinak :class:`PyCells`."""
    found = native.new_cells(groups, capacity)
    return PyCells(groups, capacity) if found is None else found


def cells_from_flat(groups: int, capacity: int, state: tuple[Any, ...]) -> Any:
    """Uložení buněk z uloženého stavu (``flat``); backend podle toho, zda je Rust k dispozici."""
    found = native.cells_from_flat(groups, capacity, *state)
    return PyCells.from_flat(groups, capacity, *state) if found is None else found


class PoolBlock:
    """Proměnné se stejnou kapacitou slotů.

    Řádky leží v předalokovaných zásobnících, takže přidání i odebrání
    proměnné je amortizovaně konstantní. Odebraný řádek nahradí poslední;
    pořadí řádků tím nemá vliv na výsledek, protože každý řádek se počítá
    samostatně a log se řadí kanonicky.

    Buňky (výskyty variant) drží uložení ``_cells``: v Rustu (``NativeCells``,
    stav žije tam po celý běh), nebo v Pythonu (:class:`PyCells`). Hustý pohled
    ``freqs`` a ``previous`` se sestaví při prvním čtení a drží, dokud se blok
    nezmění nebo ho :meth:`drop_dense` nezahodí. Malá pole (čísla variant ve
    slotech, klíče, kdo proměnnou má) zůstávají v Pythonu a do přenosu se předávají
    jako pohledy.
    """

    def __init__(self, groups: int, capacity: int, numbering: Numbering | None = None):
        self.capacity = capacity
        self.groups = groups
        #: Číslování variant, podle kterého jsou ``slot_variants`` (registr světa).
        self.numbering = Numbering("variant") if numbering is None else numbering
        self.variable_ids: list[str] = []
        #: Řetězcová ID variant ve slotech (odvozený pohled na ``slot_variants``).
        self.slots: list[list[str | None]] = []
        self._rows: dict[str, int] = {}
        self._variants = np.full((4, capacity), -1, dtype=np.int32)
        self._present = np.zeros((4, groups), dtype=bool)
        self._keys = np.zeros((4, capacity), dtype=np.uint64)
        self._cells = new_cells(groups, capacity)
        self._dense: tuple[FloatArray, FloatArray] | None = None
        self._staged_dense: tuple[FloatArray, FloatArray] | None = None
        #: Roste s každou změnou řádků a slotů (proměnné, varianty ve slotech); podle něj se
        #: zneplatňuje popis řádků pro tlaky v Rustu (``pressures_native``), který držíme u bloku.
        self.layout = 0
        self.pressure_rows: Any = None

    def __len__(self) -> int:
        return len(self.variable_ids)

    def __getstate__(self) -> dict[str, Any]:
        # Hustý pohled se do kopií a checkpointů nebere; sestaví se znovu. Buňky se ukládají
        # jako pole, nezávisle na tom, zda je držel Rust nebo Python.
        state = dict(self.__dict__)
        state["_dense"] = None
        state["_staged_dense"] = None
        state["pressure_rows"] = None
        state["_cells"] = self._cells.flat()
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._cells = cells_from_flat(self.groups, self.capacity, state["_cells"])

    @property
    def native(self) -> Any | None:
        """Uložení v Rustu (``NativeCells``), nebo ``None``, když buňky drží Python."""
        return None if isinstance(self._cells, PyCells) else self._cells

    # --- hustý pohled -------------------------------------------------

    def _dense_arrays(self) -> tuple[FloatArray, FloatArray]:
        found = self._dense
        if found is None:
            freqs, previous = self._cells.dense()
            freqs.setflags(write=False)
            previous.setflags(write=False)
            found = self._dense = (freqs, previous)
        return found

    def drop_dense(self, free: bool = True) -> None:
        """Zahodí hustý pohled (zůstane jen řídké uložení).

        Rust si u malých bloků paměť pohledu a výsledků přenosu ponechá pro další krok
        (``free=False``, platný pohled se pak nemusí sestavovat znovu); ``free`` ji uvolní.
        """
        self._dense = None
        if free and self.native is not None:
            self._cells.drop_dense()

    @property
    def large(self) -> bool:
        """Je hustý pohled bloku velký (nad ``DENSE_KEEP_CELLS`` buněk)?"""
        return len(self) * self.groups * self.capacity > DENSE_KEEP_CELLS

    @property
    def has_dense(self) -> bool:
        return self._dense is not None

    @property
    def freqs(self) -> FloatArray:
        """Podíly variant, tvar (proměnné, skupiny, sloty); hustý pohled jen pro čtení."""
        return self._dense_arrays()[0]

    @freqs.setter
    def freqs(self, value: FloatArray) -> None:
        self.set_state(value, self.previous)

    @property
    def previous(self) -> FloatArray:
        """Trendová základna, tvar jako ``freqs``; hustý pohled jen pro čtení."""
        return self._dense_arrays()[1]

    @previous.setter
    def previous(self, value: FloatArray) -> None:
        self.set_state(self.freqs, value)

    @property
    def present(self) -> BoolArray:
        return self._present[: len(self)]

    @property
    def slot_keys(self) -> KeyArray:
        return self._keys[: len(self)]

    @property
    def slot_variants(self) -> npt.NDArray[np.int32]:
        """Čísla variant ze registru ve slotech, tvar (proměnné, sloty); −1 = prázdný slot."""
        return self._variants[: len(self)]

    def numbers_in(self, numbering: Numbering, rows: Sequence[int] | slice = slice(None)) -> npt.NDArray[np.intp]:
        """Čísla variant ve slotech podle ``numbering`` (registr světa), tvar (proměnné, sloty).

        Má-li fond číslování světa, je to jen pole; jinak (samostatný sklad v
        testech) se čísla dopočtou z řetězcových ID.
        """
        if self.numbering is numbering:
            return self.slot_variants[rows].astype(np.intp)
        chosen = self.slots[rows] if isinstance(rows, slice) else [self.slots[row] for row in rows]
        return np.array(
            [[-1 if variant is None else numbering.numbers[variant] for variant in row] for row in chosen],
            dtype=np.intp,
        ).reshape(len(chosen), self.capacity)

    def set_slot(self, row: int, slot: int, variant_id: str | None) -> None:
        """Zapíše variantu do slotu (číslo i řetězec); ``None`` slot uvolní."""
        self.slots[row][slot] = variant_id
        self._variants[row, slot] = -1 if variant_id is None else self.numbering.intern(variant_id)
        self.layout += 1

    def row_of(self, variable_id: str) -> int:
        return self._rows[variable_id]

    # --- buňky: čtení -------------------------------------------------

    def cell(self, row: int, column: int) -> tuple[IntArray, FloatArray, FloatArray]:
        """Sloty s kladným podílem u jedné skupiny: (sloty vzestupně, podíly, základny)."""
        if self._dense is not None:
            freqs, previous = self._dense
            found = np.flatnonzero(freqs[row, column] > 0)
            return found, freqs[row, column, found], previous[row, column, found]
        slots, freqs, previous = self._cells.cell(row, column)
        return np.asarray(slots, dtype=np.intp), freqs, previous

    def value(self, row: int, column: int, slot: int) -> float:
        """Podíl varianty ve slotu u jedné skupiny (0, když tam není)."""
        if self._dense is not None:
            return float(self._dense[0][row, column, slot])
        return float(self._cells.value(row, column, slot))

    def range_of(self, row: int, slot: int) -> tuple[IntArray, FloatArray]:
        """Mapa rozšíření varianty: sloupce skupin, které ji mají, a její podíly u nich."""
        columns, shares = self._cells.range_of(row, slot)
        return np.asarray(columns, dtype=np.intp), shares

    def entries(self) -> int:
        """Počet uložených buněk (výskytů variant) celého bloku."""
        return int(self._cells.entries())

    def nbytes(self) -> int:
        """Paměť řídkého uložení a malých polí bloku (bez hustého pohledu), v bajtech."""
        return int(self._cells.nbytes()) + self._variants.nbytes + self._present.nbytes + self._keys.nbytes

    # --- zápis --------------------------------------------------------

    def set_state(self, freqs: FloatArray, previous: FloatArray) -> None:
        """Nahradí podíly a základny celého bloku (husté pole tvaru proměnné × skupiny × sloty).

        Uloží se jen buňky s kladným podílem nebo nenulovou základnou. Předaná
        pole blok převezme jako hustý pohled (jen pro čtení): volající je po
        zápisu nemá měnit.
        """
        self.stage_state(freqs, previous)
        self.commit_state()

    def stage_state(self, freqs: FloatArray, previous: FloatArray, keep_dense: bool = True) -> None:
        """Připraví nový stav celého bloku, ale nezapíše ho (:meth:`commit_state`); čtení vidí dál starý.

        Přenos tak spočítá všechny bloky ze starého stavu a husté výsledky
        hned zahodí: ``keep_dense`` říká, zda je blok po zápisu ponechá jako
        hustý pohled (malé bloky ano, velké ne).
        """
        size = len(self)
        if freqs.shape != (size, self.groups, self.capacity) or previous.shape != freqs.shape:
            raise ValueError("Pole musí mít tvar (proměnné, skupiny, sloty) bloku.")
        if self.native is not None:
            self._cells.stage(np.ascontiguousarray(freqs), np.ascontiguousarray(previous))
        else:
            self._cells.stage(freqs, previous)
        self._staged_dense = (freqs, previous) if keep_dense else None

    def commit_state(self) -> None:
        """Zapíše stav připravený :meth:`stage_state` (řádky bloku se mezitím nesměly změnit)."""
        dense, self._staged_dense = self._staged_dense, None
        self._cells.commit(dense is not None)
        if dense is not None:
            dense[0].setflags(write=False)
            dense[1].setflags(write=False)
        self._dense = dense

    def append(self, row: Row) -> None:
        """Přidá řádek; jeho pole mají tvar (skupiny, sloty ≤ kapacita)."""
        variable_id, freqs, previous, present, slots, keys = row
        index = len(self)
        if index == len(self._variants):
            grow = len(self._variants)
            self._present = np.concatenate([self._present, np.zeros_like(self._present[:grow])])
            self._keys = np.concatenate([self._keys, np.zeros_like(self._keys[:grow])])
            self._variants = np.concatenate([self._variants, np.full_like(self._variants[:grow], -1)])
        width = freqs.shape[1]
        self._keys[index] = 0
        self._variants[index] = -1
        self._present[index] = present
        self._keys[index, :width] = keys
        self.variable_ids.append(variable_id)
        self.slots.append([*slots, *([None] * (self.capacity - width))])
        self._variants[index, :width] = [-1 if slot is None else self.numbering.intern(slot) for slot in slots]
        self._rows[variable_id] = index
        self._cells.append(np.ascontiguousarray(freqs), np.ascontiguousarray(previous))
        self._dense = None
        self.layout += 1

    def extract(self, rows: Sequence[int]) -> list[Row]:
        """Vyjme řádky z bloku a vrátí jejich obsah (kopie)."""
        taken: list[Row] = []
        for row in rows:
            freqs, previous = self._cells.row_dense(row)
            taken.append((self.variable_ids[row], freqs, previous, self._present[row].copy(),
                          list(self.slots[row]), self._keys[row].copy()))
        for row in sorted(rows, reverse=True):
            last = len(self) - 1
            del self._rows[self.variable_ids[row]]
            if row != last:
                self._present[row] = self._present[last]
                self._keys[row] = self._keys[last]
                self._variants[row] = self._variants[last]
                self.variable_ids[row] = self.variable_ids[last]
                self.slots[row] = self.slots[last]
                self._rows[self.variable_ids[row]] = row
            self._cells.swap_remove(row)
            self.variable_ids.pop()
            self.slots.pop()
        self._dense = None
        self.layout += 1
        return taken

    def add_share(self, row: int, column: int, slot: int, share: float) -> None:
        """Nová varianta ve slotu u jedné skupiny: ostatní podíly skupiny se zmenší, základna se vyrovná.

        Totéž co ``freqs[row, column] *= 1 − share; freqs[row, column, slot] += share;
        previous[row, column] = freqs[row, column]`` nad hustým polem.
        """
        self._cells.add_share(row, column, slot, share)
        self._dense = None

    def free_slots(self, freed: Sequence[tuple[int, int]]) -> None:
        """Uvolní sloty bez výskytu (řádek, slot): číslo varianty, klíč i zbylé základny."""
        by_row: dict[int, list[int]] = {}
        for row, slot in freed:
            by_row.setdefault(row, []).append(slot)
            self.set_slot(row, slot, None)
            self._keys[row, slot] = 0
        for row, slots in by_row.items():
            self._cells.free_slots(row, slots)
        self._dense = None


class LivePools:
    def __init__(self, group_ids: Sequence[str] = (), variants: Numbering | None = None):
        self.group_ids: list[str] = list(group_ids)
        #: Číslování variant ve slotech; ve světě je to registr světa (:meth:`bind`).
        self.variants: Numbering = Numbering("variant") if variants is None else variants
        self.group_index = {group_id: index for index, group_id in enumerate(self.group_ids)}
        self.blocks: dict[int, PoolBlock] = {}
        self._block_of: dict[str, int] = {}
        self._keys: dict[str, int] = {}

    def bind(self, variants: Numbering) -> None:
        """Přepne na číslování variant světa (volá ``World``; sklad musí být prázdný)."""
        if self.blocks:
            raise ValueError("Číslování variant lze přepnout jen v prázdném skladu.")
        self.variants = variants

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

    def compact(self) -> None:
        """Zahodí husté pohledy všech bloků; zůstane jen řídké uložení."""
        for block in self.blocks.values():
            block.drop_dense(free=block.large)

    def stats(self) -> dict[str, int]:
        """Rozsah skladu: proměnné, skupiny, buňky husté a řídké, paměť řídkého uložení a hustého ekvivalentu."""
        blocks = list(self.iter_blocks())
        dense_cells = sum(len(block) * len(self.group_ids) * block.capacity for block in blocks)
        return {
            "variables": sum(len(block) for block in blocks),
            "groups": len(self.group_ids),
            "dense_cells": dense_cells,
            "entries": sum(block.entries() for block in blocks),
            "sparse_bytes": sum(block.nbytes() for block in blocks),
            # Hustý ekvivalent: podíly a základny po 8 bajtech a stejná malá pole.
            "dense_bytes": 16 * dense_cells + sum(
                block._variants.nbytes + block._present.nbytes + block._keys.nbytes for block in blocks
            ),
        }

    def holds(self, group_id: str, variable_id: str) -> bool:
        """Má skupina tuto živou proměnnou? Levnější než :meth:`get`."""
        block = self.blocks[self._block_of[variable_id]]
        return bool(block._present[block.row_of(variable_id), self.group_index[group_id]])

    def frequency(self, group_id: str, variable_id: str, variant_id: str) -> float | None:
        """Podíl varianty, jako ``get(...).frequency(variant_id)``; ``None`` = skupina proměnnou nemá."""
        block = self.blocks[self._block_of[variable_id]]
        row = block.row_of(variable_id)
        column = self.group_index[group_id]
        if not block._present[row, column]:
            return None
        slots = block.slots[row]
        if variant_id not in slots:
            return 0.0
        freq = block.value(row, column, slots.index(variant_id))
        return freq if freq > 0 else 0.0

    def dominant(self, group_id: str, variable_id: str) -> tuple[str, float] | None:
        """Nejčastější varianta a její podíl, jako ``get(...).dominant()``.

        Shodu rozhodne menší ID varianty (``get`` řadí varianty podle ID a
        ``argmax`` vrátí první maximum); nestaví ``Distribution``.
        """
        block = self.blocks[self._block_of[variable_id]]
        row = block.row_of(variable_id)
        column = self.group_index[group_id]
        if not block._present[row, column]:
            return None
        names = block.slots[row]
        best: tuple[str, float] | None = None
        slots, freqs, _ = block.cell(row, column)
        for slot, freq in zip(slots.tolist(), freqs.tolist()):
            variant = names[slot]
            if variant is None:
                continue
            if best is None or freq > best[1] or (freq == best[1] and variant < best[0]):
                best = (variant, freq)
        return best

    def get(self, group_id: str, variable_id: str) -> Distribution | None:
        block = self.blocks[self._block_of[variable_id]]
        row = block.row_of(variable_id)
        column = self.group_index[group_id]
        if not block._present[row, column]:
            return None
        names = block.slots[row]
        slots, freqs, previous = block.cell(row, column)
        used = sorted((names[slot], position) for position, slot in enumerate(slots.tolist())
                      if names[slot] is not None)
        positions = [position for _, position in used]
        return Distribution(
            tuple(variant for variant, _ in used),
            freqs[positions].copy(),
            previous[positions].copy(),
        )

    def range_of(self, variable_id: str, variant_id: str) -> tuple[list[str], FloatArray]:
        """Mapa rozšíření varianty: skupiny, které ji mají (seřazené podle sloupce), a její podíly u nich.

        Čte přímo seznam výskytů varianty z řídkého uložení, bez hustého pole.
        Varianta, kterou proměnná nemá, nebo neživá proměnná dá prázdný výsledek.
        """
        capacity = self._block_of.get(variable_id)
        if capacity is None:
            return [], np.zeros(0)
        block = self.blocks[capacity]
        row = block.row_of(variable_id)
        if variant_id not in block.slots[row]:
            return [], np.zeros(0)
        columns, shares = block.range_of(row, block.slots[row].index(variant_id))
        keep = block.present[row, columns]
        return [self.group_ids[column] for column in columns[keep]], shares[keep]

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
        # Stejnou variantu už může mít jiná skupina (paralelní inovace téže
        # zvukové změny); pak sdílí její slot, jinak dostane volný.
        if variant_id not in block.slots[row] and None not in block.slots[row]:
            self._move(variable_id, block.capacity * 2)
            block = self.blocks[self._block_of[variable_id]]
            row = block.row_of(variable_id)
        if variant_id in block.slots[row]:
            slot = block.slots[row].index(variant_id)
        else:
            slot = block.slots[row].index(None)
            block.set_slot(row, slot, variant_id)
            block.slot_keys[row, slot] = self._key(variant_id)
        block.add_share(row, self.group_index[group_id], slot, share)

    def release(self) -> list[tuple[str, list[Distribution | None]]]:
        """Vyjme proměnné, které jsou všude stejné a ustálené.

        Uvolní také sloty variant, které už nežije žádná skupina, a proměnné
        využívající jen čtvrtinu kapacity přesune do menšího bloku.
        """
        released: list[tuple[str, list[Distribution | None]]] = []
        for block in list(self.iter_blocks()):
            freqs = block.freqs
            alive = (freqs > 0).any(axis=1)
            dead = [(int(row), int(slot)) for row, slot in zip(*np.nonzero(~alive))
                    if block.slots[row][slot] is not None]
            if dead:
                block.free_slots(dead)
            held = np.where(block.present[:, :, None], freqs, 0.0)
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
                sparse = np.flatnonzero((block.slot_variants >= 0).sum(axis=1) <= block.capacity // 4)
                for variable_id in [block.variable_ids[row] for row in sparse]:
                    self._move(variable_id, block.capacity // 2)
            if block.large:
                block.drop_dense()
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
            self.load(variable_id, [world.stored(group_id, variable_id) for group_id in group_ids])

    def load_differing(self, world: World) -> list[str]:
        """Načte proměnné, ve kterých se repertoáry skupin liší, ač nejsou živé.

        V jednom protojazyce se skupiny začnou lišit jen inovací, a ta
        proměnnou načte sama. Svět s víc jazyky (M5) se liší od začátku a
        jazyky po navázání kontaktu: bez načtení by se jejich slova nikdy
        nesetkala. Vrací seřazená ID načtených proměnných.
        """
        loaded = []
        for variable_id in sorted(world.variables):
            if variable_id in self._block_of:
                continue
            distributions = [world.stored(group_id, variable_id) for group_id in self.group_ids]
            held = {item.variants for item in distributions if item is not None}
            if len(held) <= 1 and all(item is None or item.is_fixed for item in distributions):
                continue
            self.load(variable_id, distributions)
            loaded.append(variable_id)
        return loaded

    # --- pomocné ------------------------------------------------------

    def _place(self, capacity: int, row: Row) -> None:
        variable_id, freqs, previous, present, slots, keys = row
        used = [index for index, slot in enumerate(slots) if slot is not None]
        capacity = max(capacity, _capacity_for(len(used)))
        block = self.blocks.get(capacity)
        if block is None:
            block = self.blocks[capacity] = PoolBlock(len(self.group_ids), capacity, self.variants)
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


def _inserted(array: Any, at: int, value: float) -> Any:
    """Kopie pole s hodnotou vloženou na pozici ``at`` (rychlejší než ``numpy.insert``)."""
    out = np.empty(len(array) + 1, dtype=array.dtype)
    out[:at] = array[:at]
    out[at] = value
    out[at + 1:] = array[at:]
    return out


def _capacity_for(slots: int) -> int:
    capacity = _MIN_CAPACITY
    while capacity < slots:
        capacity *= 2
    return capacity

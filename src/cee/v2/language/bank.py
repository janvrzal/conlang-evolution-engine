"""Banka tvarů a tabulky procesů: výpočet nad různými tvary, ne nad vesnicemi.

Vesnice v kontinuu mají většinu tvarů slov shodných (v údolí po 500 letech
jsou různé jen asi 3 % tvarů). Co se o tvaru zjišťuje opakovaně, se proto
počítá jednou pro každý *různý* tvar:

- :class:`FormBank` dá každému různému tvaru číslo a drží jeho odvozené
  vlastnosti (příznakovost slabik, samohlásky).
- :class:`ProcessTable` je pro jeden zvukový proces pole „tvar č. X →
  výsledný tvar č. Y“ (−1 = proces tvar nemění). Plní se postupně, takže se
  proces na každý různý tvar aplikuje jednou za celý běh, ať ho potkají
  kolikrát chtějí.

Čísla tvarů jsou interní: záleží na pořadí, ve kterém se tvary objevily,
proto se podle nich nikdy neřadí ani nic nevypisuje.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import numpy.typing as npt

from cee.v2.language.processes import Process, StressRule
from cee.v2.language.segments import Form, SegmentTable

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

#: V tabulce procesu: tvar se zatím nezkoumal.
UNKNOWN = -2
#: V tabulce procesu: proces tvar nemění.
UNCHANGED = -1


class FormBank:
    """Různé tvary slov a jejich odvozené vlastnosti, každý jednou."""

    def __init__(self, table: SegmentTable):
        self.table = table
        self.forms: list[Form] = []
        self._ids: dict[Form, int] = {}
        self._derived: dict[str, list[float | None]] = {}
        self._arrays: dict[str, FloatArray] = {}
        self._lengths = np.zeros(64, dtype=np.int64)
        #: Hlásky všech tvarů za sebou (``_flat``), kde tvar začíná (``_starts``)
        #: a hlásky, které se do pole ještě nepřepsaly (``_pending``).
        self._starts = np.zeros(64, dtype=np.int64)
        self._flat = np.zeros(1024, dtype=np.int64)
        self._flat_size = 0
        self._pending: list[int] = []
        self._tables: dict[tuple[str, StressRule], ProcessTable] = {}
        #: Tabulky v pořadí vzniku a jejich masky (cíl, levý a pravý soused)
        #: složené do matic pro hromadný předfiltr.
        self._order: list[ProcessTable] = []
        self._masks: tuple[npt.NDArray[np.bool_], ...] | None = None
        #: Pro kolik tabulek (od začátku ``_order``) už byl tvar předfiltrován
        #: a které z nich v něm mohou mít místo.
        self._screened: list[int] = []
        self._rows: dict[int, set[int]] = {}
        self._possible: dict[tuple[int, StressRule], tuple[int, set[str]]] = {}

    def __len__(self) -> int:
        return len(self.forms)

    def id_of(self, form: Form) -> int:
        found = self._ids.get(form)
        if found is None:
            found = self._ids[form] = len(self.forms)
            self.forms.append(form)
            if found >= len(self._lengths):
                self._lengths = np.concatenate([self._lengths, np.zeros(len(self._lengths), dtype=np.int64)])
                self._starts = np.concatenate([self._starts, np.zeros(len(self._starts), dtype=np.int64)])
            self._lengths[found] = len(form)
            self._starts[found] = self._flat_size + len(self._pending)
            self._pending.extend(form)
        return found

    def _segments(self) -> npt.NDArray[np.int64]:
        """Hlásky všech tvarů za sebou; doplní, co se od posledního čtení přidalo."""
        if self._pending:
            top = self._flat_size + len(self._pending)
            if top > len(self._flat):
                grown = np.zeros(max(top, 2 * len(self._flat)), dtype=np.int64)
                grown[: self._flat_size] = self._flat[: self._flat_size]
                self._flat = grown
            self._flat[self._flat_size : top] = self._pending
            self._flat_size = top
            self._pending.clear()
        return self._flat

    def has_site(self, masks: tuple[npt.NDArray[np.bool_], ...], form_ids: IntArray) -> npt.NDArray[np.bool_]:
        """Pro každý tvar: má v něm změna s maskami (cíl, levý, pravý soused) vůbec místo?

        Stejná podmínka jako v :meth:`screen`, ale pro jednu změnu a mnoho tvarů
        najednou. Podmínky přízvuku a pozice místa jen dál zužují, takže „ne“
        je jisté a „ano“ se ověří aplikací změny.
        """
        flat = self._segments()
        lengths = self._lengths[form_ids]
        result = np.zeros(len(form_ids), dtype=bool)
        filled = np.flatnonzero(lengths > 0)
        if not len(filled):
            return result
        lengths = lengths[filled]
        ends = np.cumsum(lengths)
        begins = ends - lengths
        total = int(ends[-1])
        # Pozice hlásek vybraných tvarů v poli ``flat``.
        positions = np.arange(total) + np.repeat(self._starts[form_ids[filled]] - begins, lengths)
        segments = flat[positions]
        boundary = self.table.boundary
        previous = np.empty_like(segments)
        previous[1:] = segments[:-1]
        previous[begins] = boundary
        following = np.empty_like(segments)
        following[:-1] = segments[1:]
        following[ends - 1] = boundary
        target, left, right = masks
        hit = target[segments] & left[previous] & right[following]
        result[filled] = np.add.reduceat(hit.astype(np.int64), begins) > 0
        return result

    def lengths(self, form_ids: IntArray) -> IntArray:
        return self._lengths[form_ids]

    def values(self, name: str, form_ids: IntArray, compute: Callable[[Form], float]) -> FloatArray:
        """Vlastnost tvarů jako pole; chybějící hodnoty se dopočítají jednou za běh."""
        array = self._arrays.get(name)
        if array is None or len(array) < len(self.forms):
            grown = np.full(max(64, 2 * len(self.forms)), np.nan)
            if array is not None:
                grown[: len(array)] = array
            array = self._arrays[name] = grown
        found = array[form_ids]
        missing = np.isnan(found)
        if missing.any():
            for form_id in np.unique(form_ids[missing]).tolist():
                array[form_id] = compute(self.forms[form_id])
            found = array[form_ids]
        return found

    def ids_of(self, forms: list[Form]) -> IntArray:
        return np.array([self.id_of(form) for form in forms], dtype=np.int64)

    def derived(self, name: str, form_id: int, compute: Callable[[Form], float]) -> float:
        """Vlastnost tvaru (např. příznakovost), spočítaná jednou za běh."""
        values = self._derived.setdefault(name, [])
        if len(values) <= form_id:
            values.extend([None] * (form_id + 1 - len(values)))
        value = values[form_id]
        if value is None:
            value = values[form_id] = compute(self.forms[form_id])
        return value

    def process_table(self, process: Process, rule: StressRule) -> ProcessTable:
        key = (process.key, rule)
        table = self._tables.get(key)
        if table is None:
            table = self._tables[key] = ProcessTable(self, process, rule, len(self._order))
            self._order.append(table)
            self._masks = None
        return table

    def possible(self, form_id: int, rule: StressRule) -> set[str]:
        """Klíče změn (s pravidlem přízvuku ``rule``), které v tvaru mohou mít místo."""
        self.screen(form_id)
        cached = self._possible.get((form_id, rule))
        if cached is not None and cached[0] == len(self._order):
            return cached[1]
        found = {
            self._order[row].process.key for row in self._rows.get(form_id, ())
            if self._order[row].rule == rule
        }
        self._possible[(form_id, rule)] = (len(self._order), found)
        return found

    def screen(self, form_id: int) -> None:
        """Hromadný předfiltr: které změny v tvaru nemají žádné místo.

        Změna může tvar zasáhnout jen tam, kde je její cílová hláska se
        správným levým a pravým sousedem. Pro všechny tabulky najednou se to
        ověří jednou operací nad maticemi masek (tabulky × hlásky tvaru);
        změnám bez místa se nezapisuje nic: tabulka procesu si při dotazu na
        tvar ověří, zda její řádek mezi možnými je (``ProcessTable.result``).
        Podmínky přízvuku a pozice místa jen dál zužují, takže předfiltr nic
        neodmítne neprávem.
        """
        if len(self._screened) <= form_id:
            self._screened.extend([0] * (form_id + 1 - len(self._screened)))
        start = self._screened[form_id]
        if start >= len(self._order):
            return
        if self._masks is None:
            size = len(self.table.vowel_mask)
            everything = np.ones(size, dtype=bool)
            self._masks = tuple(
                np.stack([
                    (getattr(table.process, side).mask if getattr(table.process, side) is not None else everything)
                    for table in self._order
                ])
                for side in ("target", "left", "right")
            )
        target, left, right = (matrix[start:] for matrix in self._masks)
        form = np.array(self.forms[form_id], dtype=np.int64)
        boundary = np.array([self.table.boundary], dtype=np.int64)
        previous = np.concatenate([boundary, form[:-1]])
        following = np.concatenate([form[1:], boundary])
        possible = (target[:, form] & left[:, previous] & right[:, following]).any(axis=1)
        self._rows.setdefault(form_id, set()).update((start + np.flatnonzero(possible)).tolist())
        self._screened[form_id] = len(self._order)


class ProcessTable:
    """Výsledek jednoho procesu pro každý tvar banky, plněný postupně."""

    def __init__(self, bank: FormBank, process: Process, rule: StressRule, index: int = -1):
        self.bank = bank
        self.process = process
        self.rule = rule
        #: Řádek tabulky v pořadí vzniku banky (viz ``FormBank.screen``).
        self.index = index
        everything = np.ones(len(bank.table.vowel_mask), dtype=bool)
        #: Masky hlásek, které mohou být cílem změny a jejími sousedy.
        self._masks = tuple(
            everything if getattr(process, side) is None else getattr(process, side).mask
            for side in ("target", "left", "right")
        )
        self._results = np.full(max(64, len(bank)), UNKNOWN, dtype=np.int64)

    def _grow(self, top: int) -> None:
        if top >= len(self._results):
            grown = np.full(max(top + 1, 2 * len(self._results)), UNKNOWN, dtype=np.int64)
            grown[: len(self._results)] = self._results
            self._results = grown

    def result(self, form_id: int) -> int:
        """Totéž co :meth:`results` pro jeden tvar (bez režie polí)."""
        self._grow(form_id)
        found = int(self._results[form_id])
        if found == UNKNOWN:
            self.bank.screen(form_id)
            if self.index not in self.bank._rows.get(form_id, ()):
                self._results[form_id] = UNCHANGED
                return UNCHANGED
            changed = self.process.apply(self.bank.forms[form_id], self.bank.table, self.rule)
            found = UNCHANGED if changed is None else self.bank.id_of(changed)
            self._results[form_id] = found
        return found

    def results(self, form_ids: IntArray) -> IntArray:
        """Číslo výsledného tvaru pro každý tvar (``UNCHANGED``, když se nemění)."""
        if len(form_ids) == 0:
            return form_ids
        top = int(form_ids.max())
        if top >= len(self._results):
            grown = np.full(max(top + 1, 2 * len(self._results)), UNKNOWN, dtype=np.int64)
            grown[: len(self._results)] = self._results
            self._results = grown
        found = self._results[form_ids]
        missing = np.unique(form_ids[found == UNKNOWN])
        missing_before = missing
        if len(missing):
            # Tvary bez místa pro změnu se hromadně označí, aplikuje se jen na zbytek.
            possible = self.bank.has_site(self._masks, missing)
            self._results[missing[~possible]] = UNCHANGED
            missing = missing[possible]
        for form_id in missing.tolist():
            changed = self.process.apply(self.bank.forms[form_id], self.bank.table, self.rule)
            self._results[form_id] = UNCHANGED if changed is None else self.bank.id_of(changed)
        if len(missing_before):
            found = self._results[form_ids]
        return found

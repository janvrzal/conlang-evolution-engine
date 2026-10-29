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
        self._tables: dict[tuple[str, StressRule], ProcessTable] = {}

    def __len__(self) -> int:
        return len(self.forms)

    def id_of(self, form: Form) -> int:
        found = self._ids.get(form)
        if found is None:
            found = self._ids[form] = len(self.forms)
            self.forms.append(form)
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
            table = self._tables[key] = ProcessTable(self, process, rule)
        return table


class ProcessTable:
    """Výsledek jednoho procesu pro každý tvar banky, plněný postupně."""

    def __init__(self, bank: FormBank, process: Process, rule: StressRule):
        self.bank = bank
        self.process = process
        self.rule = rule
        self._results = np.full(max(64, len(bank)), UNKNOWN, dtype=np.int64)

    def result(self, form_id: int) -> int:
        """Totéž co :meth:`results` pro jeden tvar (bez režie polí)."""
        if form_id >= len(self._results):
            grown = np.full(max(form_id + 1, 2 * len(self._results)), UNKNOWN, dtype=np.int64)
            grown[: len(self._results)] = self._results
            self._results = grown
        found = int(self._results[form_id])
        if found == UNKNOWN:
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
        for form_id in missing.tolist():
            changed = self.process.apply(self.bank.forms[form_id], self.bank.table, self.rule)
            self._results[form_id] = UNCHANGED if changed is None else self.bank.id_of(changed)
        if len(missing):
            found = self._results[form_ids]
        return found

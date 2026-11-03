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

**Jádro v Rustu.** Je-li k dispozici rozšíření ``cee_core`` (viz
:mod:`cee.v2.native`), počítá dávkové výpočty (předfiltry, tabulky procesů,
aplikace procesu na nové tvary) ono; Python dál drží seznam tvarů a slovník
tvar → číslo jako zdroj pravdy, každý nový tvar posílá do Rustu a tvary
vzniklé v Rustu si hned převezme (:meth:`FormBank._adopt`), takže čísla zůstávají
stejná. Výsledky jsou bitově stejné s Rustem i bez něj. Kopie a pickle banky
Rust nenesou, po obnově se postaví znovu z tvarů a změn.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
import numpy.typing as npt

from cee.v2 import native
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
        #: Tabulky v pořadí vzniku. Předfiltr nezávisí na pravidle přízvuku, proto
        #: pracuje s různými změnami (``_procs``, bez ohledu na počet pravidel).
        self._order: list[ProcessTable] = []
        self._procs: list[Process] = []
        self._proc_index: dict[str, int] = {}
        #: Pro každou změnu masky hlásek (cíl, levý a pravý soused) a pro každou
        #: hlásku bity změn (bit = řádek v ``_procs``), kterým může být cílem,
        #: levým či pravým sousedem; ``_bits_known`` je počet změn, které už
        #: bity hlásky zahrnují.
        self._masks: list[tuple[npt.NDArray[np.bool_], ...]] = []
        self._bits: tuple[dict[int, int], dict[int, int], dict[int, int]] = ({}, {}, {})
        self._bits_known: dict[int, int] = {}
        #: Tvar → bity změn, které v něm mohou mít místo, a pro kolik změn (od
        #: začátku ``_procs``) už byl tvar předfiltrován.
        self._screened: list[int] = []
        self._rows: dict[int, int] = {}
        self._rule_bits: dict[StressRule, int] = {}
        #: Pravidlo přízvuku → klíč změny → její řádek, jen pro změny, které mají
        #: tabulku s tímto pravidlem (rychlá odpověď ``may_apply`` bez složených klíčů).
        self._rule_rows: dict[StressRule, dict[str, int]] = {}
        self._possible: dict[tuple[int, StressRule], tuple[int, set[str]]] = {}
        #: Zrcadlo v Rustu (``None`` = počítá Python); viz :mod:`cee.v2.native`.
        self._native: Any = native.new_bank(table)

    def __len__(self) -> int:
        return len(self.forms)

    def __getstate__(self) -> dict[str, Any]:
        # Rust nelze zkopírovat ani uložit; po obnově se postaví znovu.
        state = self.__dict__.copy()
        state["_native"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._rule_rows = {}
        for key, rule in self._tables:
            self._rule_rows.setdefault(rule, {})[key] = self._proc_index[key]
        self._native = native.new_bank(self.table)
        if self._native is not None:
            self._restore_native()

    def _restore_native(self) -> None:
        """Naplní novou banku v Rustu stávajícími tvary a změnami."""
        count = len(self.forms)
        flat = self._segments()[: self._flat_size]
        self._native.push_many(np.ascontiguousarray(flat, dtype=np.int64), self._lengths[:count].copy())
        for row, process in enumerate(self._procs):
            self._register_native(row, process)

    def _register_native(self, row: int, process: Process) -> None:
        """Předá Rustu změnu: operaci, masky hlásek a parametry."""
        everything = np.ones(len(self.table.vowel_mask), dtype=bool)
        masks = [
            everything if pattern is None else pattern.mask
            for pattern in (process.target, process.left, process.right, process.right2)
        ]
        self._native.register_proc(
            row, native.OPERATIONS.index(process.operation),
            {None: 0, "stressed": 1, "unstressed": 2}[process.stress], process.medial,
            -1 if process.segment is None else process.segment, *masks,
        )

    def _add(self, form: Form) -> int:
        """Zapíše nový tvar do seznamu, slovníku a polí hlásek (bez Rustu)."""
        found = self._ids[form] = len(self.forms)
        self.forms.append(form)
        if found >= len(self._lengths):
            self._lengths = np.concatenate([self._lengths, np.zeros(len(self._lengths), dtype=np.int64)])
            self._starts = np.concatenate([self._starts, np.zeros(len(self._starts), dtype=np.int64)])
        self._lengths[found] = len(form)
        self._starts[found] = self._flat_size + len(self._pending)
        self._pending.extend(form)
        return found

    def id_of(self, form: Form) -> int:
        found = self._ids.get(form)
        if found is None:
            found = self._add(form)
            if self._native is not None:
                self._native.push(form)
        return found

    def _adopt(self, first: int, flat: IntArray | list[int], lengths: IntArray | list[int]) -> None:
        """Převezme tvary, které vznikly v Rustu (výsledky procesů), pod stejnými čísly.

        Pole hlásek a délek přijde buď jako pole numpy, nebo jako seznamy (krok fonologizace).
        """
        if not len(lengths):
            return
        assert first == len(self.forms), "banka v Rustu se rozešla s Pythonem"
        values = flat if isinstance(flat, list) else flat.tolist()
        begin = 0
        for length in (lengths if isinstance(lengths, list) else lengths.tolist()):
            self._add(tuple(values[begin : begin + length]))
            begin += length

    def _resolve(self, row: int, segments: list[int]) -> None:
        """Doplní Rustu výstupy operace ``change`` či ``tone`` pro hlásky, které si vyžádal.

        Nejbližší hlásku hledá tabulka hlásek (``SegmentTable.changed``), ne Rust;
        výstup je čistá funkce hlásky, takže se spočítá jednou.
        """
        process, table = self._procs[row], self.table
        if process.operation == "tone":
            assert process.tone is not None
            outputs = [table.with_tone(segment, process.tone) for segment in segments]
        else:
            outputs = [table.changed(segment, process.changes, process.allow) for segment in segments]
        self._native.set_map(
            row, np.array(segments, dtype=np.int64),
            np.array([-1 if output is None else output for output in outputs], dtype=np.int64),
        )

    def _native_results(self, row: int, rule: StressRule, form_ids: IntArray) -> IntArray:
        """``ProcessTable.results`` v Rustu, včetně doplnění map a převzetí nových tvarů."""
        ids = np.ascontiguousarray(form_ids, dtype=np.int64)
        code = native.RULES.index(rule)
        while True:
            needs, found, first, flat, lengths = self._native.results(row, code, ids)
            self._adopt(first, flat, lengths)
            if found is not None:
                return found
            self._resolve(row, needs)

    def assess_rows(
        self, process: Process, rule: StressRule, ids: IntArray, weights: FloatArray, offsets: IntArray,
        width: int, want_vowels: bool,
    ) -> tuple[Any, ...]:
        """Hodnocení procesu nad maticí slovních zásob v Rustu (``assess.rs``).

        Vstupy a výstupy viz ``NativeBank.assess_rows``; mapy hlásek, které si
        Rust vyžádá, doplní banka stejně jako u ``results``. Nové tvary, které
        při tom vzniknou, si převezme. Vrací pole bez ``needs`` a bez nových tvarů.
        """
        assert self._native is not None
        row = self.process_table(process, rule).index
        code = native.RULES.index(rule)
        arrays = (
            np.ascontiguousarray(ids, dtype=np.int64), np.ascontiguousarray(weights, dtype=np.float64),
            np.ascontiguousarray(offsets, dtype=np.int64),
        )
        while True:
            answer = self._native.assess_rows(row, code, *arrays, width, want_vowels)
            self._adopt(*answer[-3:])
            if not answer[0]:
                return tuple(answer[1:-3])
            self._resolve(row, answer[0])

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
            row = self._proc_index.get(process.key)
            if row is None:
                row = self._proc_index[process.key] = len(self._procs)
                self._procs.append(process)
                everything = np.ones(len(self.table.vowel_mask), dtype=bool)
                self._masks.append(tuple(
                    everything if getattr(process, side) is None else getattr(process, side).mask
                    for side in ("target", "left", "right")
                ))
                if self._native is not None:
                    self._register_native(row, process)
            table = self._tables[key] = ProcessTable(self, process, rule, row)
            self._order.append(table)
            self._rule_rows.setdefault(rule, {})[process.key] = row
            self._rule_bits[rule] = self._rule_bits.get(rule, 0) | (1 << row)
        return table

    def possible(self, form_id: int, rule: StressRule) -> set[str]:
        """Klíče změn (s pravidlem přízvuku ``rule``), které v tvaru mohou mít místo."""
        cached = self._possible.get((form_id, rule))
        if cached is not None and cached[0] == len(self._order):
            return cached[1]
        bits = self._row_bits(form_id) & self._rule_bits.get(rule, 0)
        found: set[str] = set()
        while bits:
            low = bits & -bits
            found.add(self._procs[low.bit_length() - 1].key)
            bits ^= low
        self._possible[(form_id, rule)] = (len(self._order), found)
        return found

    def may_apply(self, form_id: int, rule: StressRule, key: str) -> bool:
        """Totéž co ``key in possible(form_id, rule)`` bez sestavování množiny."""
        rows = self._rule_rows.get(rule)
        row = None if rows is None else rows.get(key)
        if self._native is not None:
            return row is not None and self._native.may_apply(form_id, row)
        self.screen(form_id)
        return row is not None and bool((self._rows.get(form_id, 0) >> row) & 1)

    def _row_bits(self, form_id: int) -> int:
        """Bity změn, které v tvaru mohou mít místo (bit = řádek v ``_procs``)."""
        if self._native is not None:
            return sum(word << (64 * position) for position, word in enumerate(self._native.rows_of(form_id)))
        self.screen(form_id)
        return self._rows.get(form_id, 0)

    def _site_bits(self, segment: int) -> tuple[int, int, int]:
        """Bity změn, kterým hláska může být cílem, levým a pravým sousedem."""
        known = self._bits_known.get(segment, 0)
        count = len(self._procs)
        target, left, right = self._bits
        if known < count:
            bits_target, bits_left, bits_right = target.get(segment, 0), left.get(segment, 0), right.get(segment, 0)
            for row in range(known, count):
                masks = self._masks[row]
                if masks[0][segment]:
                    bits_target |= 1 << row
                if masks[1][segment]:
                    bits_left |= 1 << row
                if masks[2][segment]:
                    bits_right |= 1 << row
            target[segment], left[segment], right[segment] = bits_target, bits_left, bits_right
            self._bits_known[segment] = count
        return target[segment], left[segment], right[segment]

    def screen(self, form_id: int) -> None:
        """Hromadný předfiltr: které změny v tvaru nemají žádné místo.

        Změna může tvar zasáhnout jen tam, kde je její cílová hláska se
        správným levým a pravým sousedem. Každá hláska má bity změn, kterým
        může být cílem, levým a pravým sousedem; místa ve tvaru se pak najdou
        součtem (OR) přes jeho hlásky pro všechny změny najednou. Změnám bez
        místa se nezapisuje nic: tabulka procesu si při dotazu na tvar ověří,
        zda její řádek mezi možnými je (``ProcessTable.result``). Podmínky
        přízvuku a pozice místa jen dál zužují, takže předfiltr nic neodmítne
        neprávem.
        """
        if self._native is not None:
            self._native.screen(form_id)
            return
        if len(self._screened) <= form_id:
            self._screened.extend([0] * (form_id + 1 - len(self._screened)))
        if self._screened[form_id] >= len(self._procs):
            return
        form = self.forms[form_id]
        boundary = self.table.boundary
        bits = 0
        previous = boundary
        last = len(form) - 1
        for index, segment in enumerate(form):
            following = form[index + 1] if index < last else boundary
            target = self._site_bits(segment)[0]
            if target:
                bits |= target & self._site_bits(previous)[1] & self._site_bits(following)[2]
            previous = segment
        self._rows[form_id] = bits
        self._screened[form_id] = len(self._procs)


class ProcessTable:
    """Výsledek jednoho procesu pro každý tvar banky, plněný postupně."""

    def __init__(self, bank: FormBank, process: Process, rule: StressRule, index: int = -1):
        self.bank = bank
        self.process = process
        self.rule = rule
        #: Řádek změny v předfiltru banky (viz ``FormBank.screen``).
        self.index = index
        everything = np.ones(len(bank.table.vowel_mask), dtype=bool)
        #: Masky hlásek, které mohou být cílem změny a jejími sousedy.
        self._masks = tuple(
            everything if getattr(process, side) is None else getattr(process, side).mask
            for side in ("target", "left", "right")
        )
        #: V Rustu se výsledky drží v jeho tabulce a tohle pole zůstává prázdné.
        self._results = np.full(max(64, len(bank)), UNKNOWN, dtype=np.int64)
        self._rule_code = native.RULES.index(rule)

    def _grow(self, top: int) -> None:
        if top >= len(self._results):
            grown = np.full(max(top + 1, 2 * len(self._results)), UNKNOWN, dtype=np.int64)
            grown[: len(self._results)] = self._results
            self._results = grown

    def result(self, form_id: int) -> int:
        """Totéž co :meth:`results` pro jeden tvar (bez režie polí)."""
        handle = self.bank._native
        if handle is not None and self.index >= 0:
            answer: int = handle.result(self.index, self._rule_code, form_id)
            if answer > -3:
                return answer
            # Rust potřebuje doplnit mapu hlásek nebo vznikl nový tvar.
            return int(self.bank._native_results(self.index, self.rule, np.array([form_id], dtype=np.int64))[0])
        if form_id >= len(self._results):
            self._grow(form_id)
        found: int = self._results.item(form_id)
        if found == UNKNOWN:
            self.bank.screen(form_id)
            if not (self.bank._rows.get(form_id, 0) >> self.index) & 1:
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
        if self.bank._native is not None and self.index >= 0:
            return self.bank._native_results(self.index, self.rule, form_ids)
        top = int(form_ids.max())
        if top >= len(self._results):
            grown = np.full(max(top + 1, 2 * len(self._results)), UNKNOWN, dtype=np.int64)
            grown[: len(self._results)] = self._results
            self._results = grown
        found = self._results[form_ids]
        unknown = form_ids[found == UNKNOWN]
        missing = np.unique(unknown) if len(unknown) else unknown
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

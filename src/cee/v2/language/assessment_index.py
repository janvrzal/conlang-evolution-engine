"""Vzorek slov pro hodnocení zvukových procesů jako pole čísel (krok B3b, Python reference).

Hodnocení procesu (:mod:`cee.v2.assessment`) se dívá na ``SAMPLE_WORDS`` nejčastějších
slov kódu. Vzorek je v plochých polích podle čísel z registru:

- ``morphemes`` (``int32``): čísla morfémů ve vzorku, **v pořadí jmen morfémů** (řazení podle
  řetězců, na kterém stojí pořadí součtů hodnocení; číslo pořadí neurčuje);
- ``ids`` (``int64``): číslo aktuálního tvaru každého slova v bance tvarů;
- ``weights`` (``float64``): frekvence užití, nejméně 0,01, a ``total`` jejich součet (1, když je 0);
- ``vowels`` (``int64`` podle čísla hlásky): kolikrát se která samohláska ve vzorku vyskytuje.

Co se kdy přepočítá, určuje :class:`SampleKeeper` (výběr, váhy a jejich klíče) a
:class:`AssessmentVocabularyIndex` (čísla tvarů a samohlásky podle deníku tvarů). Pravidla
(přepočet jen při změně verze kódu, váhy jen při změně slovní zásoby či frekvencí pojmů)
jsou stejná jako dřív; Rust (``cee_core.AssessIndex``) drží totéž a výběr a váhy
od :class:`SampleKeeper` dostává jako pole.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, cast

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.language.journal import FrequencyMap

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Čísla pravidel přízvuku, jak je zná Rust (``cee.v2.native.RULES``).
RULES = native.RULES
#: Čísla operací analogických změn tvarů, jak je zná Rust (``form_assess.rs``).
_FORM_OPERATIONS = {"level": 0, "extend": 1, "prepend": 2, "drop_initial": 3}


def top_words(world: World, code: Code, count: int) -> list[str]:
    """``count`` nejčastějších tvarů slovní zásoby; shodní se řadí podle ID.

    Řazení je podle dvojice (−frekvence, ID), tedy úplné: pořadí, ve kterém
    množina slovní zásoby vydává tvary, na výsledku nic nemění.
    """
    units = list(code.phonology.vocabulary)
    keyed = sorted(zip([-value for value in world.usage_frequencies(code, units)], units))
    return [unit for _, unit in keyed[:count]]


def clipped_frequencies(world: World, code: Code, units: Iterable[str]) -> dict[str, float]:
    """Tvar → frekvence užití, nejméně 0,01 (ve stejném pořadí jako ``units``)."""
    units = list(units)
    return {unit: max(0.01, value) for unit, value in zip(units, world.usage_frequencies(code, units))}


@dataclass(slots=True)
class Vocabulary:
    """Vzorek slov jednoho kódu v polích (viz popis modulu)."""

    morphemes: npt.NDArray[np.int32]
    ids: npt.NDArray[np.int64]
    weights: npt.NDArray[np.float64]
    total: float
    vowels: npt.NDArray[np.int64]

    def names(self, world: World) -> list[str]:
        """Jména morfémů vzorku (pozice jako v polích)."""
        names = world.registry.morphemes.names
        return [names[number] for number in self.morphemes.tolist()]


def frequency_key(world: World) -> object:
    """Klíč frekvencí pojmů: když se nezmění, váhy vzorku se nepřepočítávají."""
    frequencies = world.concept_frequencies
    if isinstance(frequencies, FrequencyMap):
        return (id(frequencies), frequencies.version)
    return tuple(sorted(frequencies.items()))


def selection(world: World, code: Code, size: int) -> list[str]:
    """Výběr vzorku podle slovní zásoby, zapamatovaný pro verzi slovní zásoby kódu."""
    state = code.phonology
    picked = state.cache.get("vocabulary-sample")
    if picked is not None and picked[0] == state.lexicon_version:
        return cast(list[str], picked[1])
    chosen = top_words(world, code, size)
    state.cache["vocabulary-sample"] = (state.lexicon_version, chosen)
    return chosen


class SampleKeeper:
    """Které slovo je ve vzorku a s jakou váhou: výběr (v pořadí jmen) a frekvence užití.

    ``refresh`` se volá při změně verze kódu a vrátí, zda se výběr nebo váhy změnily.
    Výběr se přepočítává, když se změní verze slovní zásoby, váhy když se změní slovní zásoba
    nebo frekvence pojmů (nebo je úložiště tvarů jiné); jinak zůstávají, jaké byly.
    """

    __slots__ = ("token", "cursor", "lexicon_version", "size", "frequency", "morphemes", "weights", "total")

    def __init__(self) -> None:
        self.token: int | None = None
        self.cursor = 0
        self.lexicon_version = -1
        self.size = -1
        self.frequency: object = None
        self.morphemes = np.zeros(0, dtype=np.int32)
        self.weights = np.zeros(0, dtype=np.float64)
        self.total = 1.0

    def refresh(self, world: World, code: Code, size: int, dirty: bool = False) -> bool:
        """Dorovná výběr a váhy; ``True``, když se výběr změnil (``dirty`` ho vynutí)."""
        state, store = code.phonology, code.forms
        key = frequency_key(world)
        reset = dirty or self.token != store.token or self.cursor > len(store.log) or self.size != size
        lexical = self.lexicon_version != state.lexicon_version
        selected: list[str] | None = None
        numbering = world.registry.morphemes
        if lexical:
            selected = selection(world, code, size)
            # Změna slovníku, která nezmění vybraný vzorek (výpůjčka okrajového slova), stačí dorovnat
            # tvary a frekvence; stavět vzorek znovu ne.
            if not reset and sorted(selected) != [numbering.names[number] for number in self.morphemes.tolist()]:
                reset = True
        if reset:
            if selected is None:
                selected = selection(world, code, size)
            chosen = sorted(selected)
            self.morphemes = np.array([numbering.intern(unit) for unit in chosen], dtype=np.int32)
            self._weights(world, code, chosen)
        elif key != self.frequency or lexical:
            # Výběr se nemění (frekvence pojmů, nebo změna slovníku mimo vzorek).
            self._weights(world, code, [numbering.names[number] for number in self.morphemes.tolist()])
        self.token, self.cursor = store.token, len(store.log)
        self.lexicon_version, self.size, self.frequency = state.lexicon_version, size, key
        return reset

    def _weights(self, world: World, code: Code, chosen: list[str]) -> None:
        frequency = clipped_frequencies(world, code, chosen)
        self.weights = np.array([frequency[unit] for unit in chosen], dtype=np.float64)
        self.total = sum(frequency.values()) or 1.0


class AssessmentVocabularyIndex:
    """Vzorek jednoho kódu (reference v Pythonu): :class:`SampleKeeper` a čísla tvarů se samohláskami.

    Čísla tvarů a samohlásky se dorovnávají podle deníku přepsaných tvarů (``FormStore.log``):
    mění se jen slova, která se změnila. ``changes`` jsou pozice slov změněných od posledního
    přestavění vzorku (pro testy).
    """

    def __init__(self) -> None:
        self.keeper = SampleKeeper()
        self.vocabulary: Vocabulary | None = None
        self.token: int | None = None
        self.cursor = 0
        self.positions: dict[int, int] = {}
        self.changes: list[int] = []
        self.generation = 0

    def sync(self, world: World, code: Code) -> Vocabulary:
        from cee.v2.assessment import SAMPLE_WORDS

        table = world.table
        assert table is not None
        store, keeper = code.forms, self.keeper
        stale = self.vocabulary is None or self.token != store.token or self.cursor > len(store.log)
        rebuilt = keeper.refresh(world, code, SAMPLE_WORDS, dirty=stale)
        names = world.registry.morphemes.names
        bank = world.form_bank()
        if rebuilt or self.vocabulary is None:
            ids = np.array([world.form_id_of(code, names[number]) for number in keeper.morphemes.tolist()],
                           dtype=np.int64)
            vowels = np.zeros(len(table.vowel_mask), dtype=np.int64)
            for form_id in ids.tolist():
                _count_vowels(vowels, bank.forms[form_id], table.vowel_mask, 1)
            self.vocabulary = Vocabulary(keeper.morphemes, ids, keeper.weights, keeper.total, vowels)
            self.positions = {number: position for position, number in enumerate(keeper.morphemes.tolist())}
            self.generation += 1
            self.changes = []
        else:
            vocabulary = self.vocabulary
            vocabulary.weights, vocabulary.total = keeper.weights, keeper.total
            numbers = world.registry.morphemes.numbers
            dirty = sorted({numbers[unit] for unit in store.log[self.cursor:]} & self.positions.keys())
            for number in dirty:
                position = self.positions[number]
                new = world.form_id_of(code, names[number])
                old = int(vocabulary.ids[position])
                if old == new:
                    continue
                _count_vowels(vocabulary.vowels, bank.forms[old], table.vowel_mask, -1)
                _count_vowels(vocabulary.vowels, bank.forms[new], table.vowel_mask, 1)
                vocabulary.ids[position] = new
                self.changes.append(position)
        self.token, self.cursor = store.token, len(store.log)
        assert self.vocabulary is not None
        return self.vocabulary


def _count_vowels(
    counts: npt.NDArray[np.int64], form: tuple[int, ...], vowel_mask: npt.NDArray[np.bool_], sign: int
) -> None:
    """Přičte (``sign`` = 1) či odečte (−1) samohlásky tvaru k počtům podle čísla hlásky."""
    for segment in form:
        if vowel_mask[segment]:
            counts[segment] += sign


# --- index světa: vzorky, uložená hodnocení a zrcadlo hodnocení tvarů --------------------------------


def _entries_arrays(
    entries: list[tuple[int, int, int, tuple[float, ...]]]
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    variables = np.array([entry[0] for entry in entries], dtype=np.int64)
    versions = np.array([entry[1] for entry in entries], dtype=np.int64)
    ticks = np.array([entry[2] for entry in entries], dtype=np.int64)
    values = np.array([value for entry in entries for value in entry[3]], dtype=np.float64)
    return variables, versions, ticks, values


class AssessmentIndex:
    """Vzorky kódů a uložená hodnocení procesů (reference v Pythonu); stav podle ``FormStore.token``.

    Hodnocení zůstává platné, dokud se nezmění verze kódu, nejvýš ``STALE_TICKS`` ticků. Stav se
    ukládá ve tvaru, který čte i :class:`NativeAssessmentIndex` (``snapshot``, ``restore``), takže
    kontrolní bod z jednoho režimu jde obnovit v druhém.
    """

    native = False

    def __init__(self) -> None:
        self.groups: dict[int, _GroupState] = {}

    def _group(self, token: int) -> _GroupState:
        found = self.groups.get(token)
        if found is None:
            found = self.groups[token] = _GroupState()
        return found

    def vocabulary(self, world: World, code: Code) -> Vocabulary:
        """Vzorek kódu dorovnaný na jeho aktuální verzi."""
        group = self._group(code.forms.token)
        version = code.phonology.version
        if group.vocabulary is None or group.synced != version:
            group.vocabulary = group.vocab.sync(world, code)
            group.synced = version
        return group.vocabulary

    def assess_many(self, world: World, group_ids: list[str], variable_id: str, tick: int) -> list[object]:
        """Hodnocení jednoho procesu ve více skupinách; zastaralá se spočítají naráz."""
        from cee.v2.assessment import STALE_TICKS, ProcessAssessment, _assess_batch

        number = world.registry.variables.intern(variable_id)
        found: list[ProcessAssessment | None] = []
        stale: list[int] = []
        for position, group_id in enumerate(group_ids):
            code = world.groups[group_id].main_code
            entry = self._group(code.forms.token).cache.get(number)
            if entry is not None:
                version, stored_tick, stored = entry
                if version == code.phonology.version or tick - stored_tick < STALE_TICKS:
                    found.append(stored)
                    continue
            found.append(None)
            stale.append(position)
        if stale:
            fresh = _assess_batch(
                world, [group_ids[position] for position in stale], variable_id,
                lambda w, group_id: self.vocabulary(w, w.groups[group_id].main_code),
            )
            for position, result in zip(stale, fresh):
                found[position] = result
                code = world.groups[group_ids[position]].main_code
                self._group(code.forms.token).cache[number] = (code.phonology.version, tick, result)
        return cast("list[object]", found)

    # --- uložení --------------------------------------------------------------------------------------

    def snapshot(self) -> dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]:
        out = {}
        for token, group in self.groups.items():
            entries = [
                (variable, version, tick, (a.coverage, a.merge_mass, a.short_share, a.markedness_delta,
                                           a.dispersion_delta))
                for variable, (version, tick, a) in sorted(group.cache.items())
            ]
            out[token] = (group.vocab.keeper, entries)
        return out

    def restore(self, saved: dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]) -> None:
        from cee.v2.assessment import ProcessAssessment

        for token, (keeper, entries) in saved.items():
            group = self._group(token)
            group.vocab.keeper = keeper
            group.cache = {
                variable: (version, tick, ProcessAssessment(*values)) for variable, version, tick, values in entries
            }

    def __getstate__(self) -> dict[str, object]:
        return {"saved": self.snapshot()}

    def __setstate__(self, state: dict[str, object]) -> None:
        self.groups = {}
        self.restore(cast("dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]",
                          state["saved"]))


class _GroupState:
    """Stav jednoho kódu v :class:`AssessmentIndex`: vzorek a uložená hodnocení (číslo proměnné → verze, tik, hodnocení)."""

    __slots__ = ("vocab", "vocabulary", "synced", "cache")

    def __init__(self) -> None:
        self.vocab = AssessmentVocabularyIndex()
        self.vocabulary: Vocabulary | None = None
        self.synced = -1
        self.cache: dict[int, tuple[int, int, Any]] = {}


class NativeAssessmentIndex:
    """Tentýž index v Rustu (``cee_core.AssessIndex``); rozhraní jako :class:`AssessmentIndex`.

    Uložená hodnocení, čísla tvarů a samohlásky vzorků a zrcadlo hodnocení tvarů jsou v Rustu;
    Python drží jen :class:`SampleKeeper` každého kódu (výběr a váhy, které počítá on) a odpovídá
    na to, co si Rust vyžádá (viz :class:`cee.v2.pressures_native.Supplier`). Rust nelze zkopírovat
    ani uložit, proto se při kopii světa a ukládání exportují uložená hodnocení a po obnově se
    vrátí do nového rukojeti (zrcadlo tvarů a čísla tvarů vzorku se podle stavu kódu doplní samy).
    """

    native = True

    def __init__(self, handle: Any) -> None:
        self.handle = handle
        self.keepers: dict[int, SampleKeeper] = {}
        self.prepared = False
        #: Odvozené pole pro přenos (klíče ocenění), neukládá se.
        self.scratch: dict[str, Any] = {}
        #: Uložený stav, pokud rozšíření chybí (obnova v jiném režimu).
        self._saved: dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]] | None = None

    def keeper(self, token: int) -> SampleKeeper:
        found = self.keepers.get(token)
        if found is None:
            found = self.keepers[token] = SampleKeeper()
        return found

    def prepare(self, world: World) -> None:
        """Jednou předá Rustu souřadnice samohlásek tabulky hlásek."""
        if self.prepared:
            return
        table = world.table
        assert table is not None
        coordinates = np.zeros((len(table.vowel_mask), 3), dtype=np.float64)
        for segment in np.flatnonzero(table.vowel_mask[:-1]).tolist():
            coordinates[segment] = table.vowel_coordinates(segment)
        self.handle.set_coordinates(coordinates)
        self.prepared = True

    def ensure_process(self, world: World, variable_id: str, rule: str) -> tuple[int, int]:
        """Číslo proměnné procesu a jeho řádek v bance; při prvním použití proces zaregistruje v Rustu."""
        from cee.v2.assessment import _shapes_vowels

        process = world.processes[variable_id]
        number = world.registry.variables.intern(variable_id)
        row = world.form_bank().process_table(process, rule).index  # type: ignore[arg-type]
        if not self.handle.has_process(number):
            table = world.table
            assert table is not None
            shapes = _shapes_vowels(process, table)
            segment = process.segment
            self.handle.register_process(
                number, shapes, -1 if segment is None else int(segment),
                np.ascontiguousarray(process.target.mask, dtype=bool),
            )
        return number, int(row)

    def ensure_form(self, world: World, variable_id: str) -> None:
        """Při prvním použití zaregistruje v Rustu analogickou změnu tvaru (čísla morfémů, operace, hláska)."""
        number = world.registry.variables.intern(variable_id)
        if self.handle.has_form(number):
            return
        change = world.form_changes[variable_id]
        morphemes = world.registry.morphemes
        self.handle.register_form(
            number, _FORM_OPERATIONS[change.operation], morphemes.intern(change.unit),
            -1 if change.exponent is None else morphemes.intern(change.exponent),
            -1 if change.segment is None else change.segment,
        )

    def assess_many(self, world: World, group_ids: list[str], variable_id: str, tick: int) -> list[object]:
        """Hodnocení jednoho procesu ve více skupinách (stejně jako :class:`AssessmentIndex`)."""
        from cee.v2.assessment import ProcessAssessment
        from cee.v2.pressures_native import Supplier

        if not group_ids:
            return []
        self.prepare(world)
        codes = [world.groups[group_id].main_code for group_id in group_ids]
        number, row = self.ensure_process(world, variable_id, codes[0].stress_rule)
        supplier = Supplier(world, codes, list(group_ids), self)
        bank = world.form_bank()._native
        assert bank is not None
        tokens = [code.forms.token for code in codes]
        versions = [code.phonology.version for code in codes]
        rules = [RULES.index(code.stress_rule) for code in codes]
        forms = [code.forms.raw()[0] for code in codes]
        params = world.params
        known: list[tuple[int, int, bool]] = []
        for _ in range(64):
            needs, values = self.handle.assess(
                bank, tokens, versions, rules, forms, world.columns.morphemes.form,
                world.columns.morphemes.lexeme, world.columns.morphemes.cell,
                (params.paradigm_merge_weight, params.redundant_merge_weight), known, number, row,
                list(range(len(codes))), tick,
            )
            if not any(needs):
                break
            known.extend(supplier.supply(needs))
        else:
            raise RuntimeError("hodnocení procesu se nepodařilo dopočítat")
        supplier.adopt()
        return [ProcessAssessment(*row.tolist()) for row in values.reshape(len(codes), 5)]

    # --- uložení --------------------------------------------------------------------------------------

    def snapshot(self) -> dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]:
        if self.handle is None:
            return dict(self._saved or {})
        out = {}
        for token, keeper in self.keepers.items():
            variables, versions, ticks, values = self.handle.export(token)
            entries = [
                (int(variable), int(version), int(tick), tuple(values[5 * at: 5 * at + 5].tolist()))
                for at, (variable, version, tick) in enumerate(zip(variables, versions, ticks))
            ]
            out[token] = (keeper, entries)
        return out

    def restore(self, saved: dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]) -> None:
        for token, (keeper, entries) in saved.items():
            self.keepers[token] = keeper
            if entries:
                self.handle.import_cache(token, *_entries_arrays(entries))

    def __getstate__(self) -> dict[str, object]:
        return {"saved": self.snapshot()}

    def __setstate__(self, state: dict[str, object]) -> None:
        saved = cast("dict[int, tuple[SampleKeeper, list[tuple[int, int, int, tuple[float, ...]]]]]", state["saved"])
        self.keepers = {}
        self.prepared = False
        self.scratch = {}
        handle = native.new_assess_index()
        self.handle = handle
        self._saved = saved
        if handle is not None:
            self.restore(saved)


def index_of(world: World) -> AssessmentIndex | NativeAssessmentIndex:
    """Index hodnocení světa; Rust, je-li k dispozici (a svět má banku tvarů v Rustu), jinak Python.

    Při změně režimu (obnova kontrolního bodu s jiným nastavením) se uložený stav přenese.
    """
    want = native.assess_enabled() and world.table is not None and world.form_bank()._native is not None
    found = world.assessment
    if found is not None and found.native == want and (not want or found.handle is not None):
        return cast("AssessmentIndex | NativeAssessmentIndex", found)
    fresh: AssessmentIndex | NativeAssessmentIndex
    if want:
        fresh = NativeAssessmentIndex(native.new_assess_index())
    else:
        fresh = AssessmentIndex()
    if found is not None:
        fresh.restore(found.snapshot())
    world.assessment = fresh
    return fresh

"""Zvukové změny (iterace 3, oblast A).

Každá rodina je parametrický prostor: z aktuálního inventáře kódu vyrobí
konkrétní procesy (třída cíle × výstup × prostředí). Kandidát, který ve
slovní zásobě nemá aspoň pár výskytů, se nenabízí. O tom, jestli se změna
prosadí, nerozhoduje počet zasažených slov (to byla chyba legacy jádra, kde
vždy vyhrála nejširší změna samohlásek), ale tlaky a šíření.

Váhy ``prior`` jsou autorský typologický prior podle obecné literatury o
směrech zvukové změny (např. lenice je častější než fortice). Nepřebírají
žádnou databázi; viz ``docs/DIRECTIONAL_SOURCES.md``.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Mapping, Sequence, cast
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from cee.v2.world import Code, World

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.processes import Process, StressRule, stressed_nucleus
from cee.v2.language.segments import TONE_CODES, TONES, Pattern, SegmentTable
from cee.v2.language.sound_index import NativeSoundIndex, SoundIndex
from cee.v2.phonology import register
from cee.v2.pressures import (
    Actuation,
    Articulation,
    Clarity,
    Conformity,
    Dispersion,
    FunctionalLoad,
    Phonotactics,
    Pressure,
)
from cee.v2.repertoire import Origin, Variable, Variant
from cee.v2.rng import RandomSource

Domain = Literal["consonant", "vowel", "structure"]

#: Očekávaný počet zvukových inovací na skupinu a generaci (všechny rodiny
#: dohromady). Většina z nich zanikne; kalibruje se v M7.
SOUND_INNOVATIONS_PER_GENERATION = 0.6
#: Kolik výskytů prostředí ve slovní zásobě dá kandidátovi plnou šanci.
FULL_SUPPORT = 8
MIN_SUPPORT = 2

SOUND_PRESSURES: Mapping[type[Pressure], float] = {
    Articulation: 1.0,
    Clarity: 0.6,
    FunctionalLoad: 1.0,
    Dispersion: 0.5,
    Phonotactics: 0.4,
    Conformity: 0.1,
    Actuation: 1.0,
}


@dataclass(frozen=True)
class ContextStats:
    """Výskyty (předchozí, hláska, následující, přízvuk) ve slovní zásobě."""

    previous: npt.NDArray[np.intp]
    segment: npt.NDArray[np.intp]
    following: npt.NDArray[np.intp]
    stressed: npt.NDArray[np.bool_]
    following2: npt.NDArray[np.intp]
    count: npt.NDArray[np.float64]
    inventory: tuple[int, ...]

    def support(self, process: Process, table: SegmentTable) -> float:
        mask = process.target.mask[self.segment]
        if process.left is not None:
            mask &= process.left.mask[self.previous]
        if process.right is not None:
            mask &= process.right.mask[self.following]
        if process.right2 is not None:
            mask &= process.right2.mask[self.following2]
        if process.stress == "stressed":
            mask &= self.stressed
        elif process.stress == "unstressed":
            mask &= ~self.stressed & table.vowel_mask[self.segment]
        return float(self.count[mask].sum())


_CONTEXTS: dict[tuple[object, ...], tuple[tuple[int, int, int, bool, int], ...]] = {}
_CONTEXTS_LIMIT = 1 << 17


def form_contexts(
    form: tuple[int, ...], table: SegmentTable, rule: StressRule
) -> tuple[tuple[int, int, int, bool, int], ...]:
    """Prostředí všech hlásek tvaru; čistá funkce tvaru, proto zapamatovaná."""
    key = (form, rule, id(table))
    found = _CONTEXTS.get(key)
    if found is None:
        if len(_CONTEXTS) >= _CONTEXTS_LIMIT:
            _CONTEXTS.clear()
        stress = stressed_nucleus(form, table, rule)
        found = _CONTEXTS[key] = tuple(
            (
                form[index - 1] if index else table.boundary,
                segment,
                form[index + 1] if index + 1 < len(form) else table.boundary,
                index == stress,
                form[index + 2] if index + 2 < len(form) else table.boundary,
            )
            for index, segment in enumerate(form)
        )
    return found


def context_stats(context: InnovationContext) -> ContextStats | None:
    """Statistika prostředí kódu; drží se, dokud se slovní zásoba nezmění."""
    world, code = context.world, context.code
    table = world.table
    state = code.phonology
    if table is None or not state.vocabulary:
        return None
    cached = state.cache.get("context-stats")
    if cached is not None and cached[0] == state.version:
        return cast(ContextStats, cached[1])
    # Počty prostředí drží průběžný index světa; dorovná jen změněná slova.
    index = sound_index(world)
    index.sync(world, [code], CATALOG)
    previous, segment, following, stressed, following2, count = index.context_counts(code, world)
    stats = ContextStats(
        previous=previous,
        segment=segment,
        following=following,
        stressed=stressed,
        following2=following2,
        count=count.astype(np.float64),
        inventory=tuple(sorted({int(value) for value in np.unique(segment)})),
    )
    state.cache["context-stats"] = (state.version, stats)
    return stats


class _Columns:
    """Masky kandidátů jen ve sloupcích hlásek inventáře (a hranice slova).

    Tabulka hlásek má desítky tisíc řádků (celé IPA, tóny), inventář jazyka
    desítky hlásek; matice přes celou tabulku by v paměti kandidátů zabraly
    gigabajty. Hláska mimo inventář (prostředí slova, které už zmizelo) se
    dopočítá z úplných masek procesů, takže výsledek je stejný.
    """

    def __init__(self, processes: list[Process], table: SegmentTable, inventory: Sequence[int]):
        self.processes = processes
        self.cols = np.array(sorted({*inventory, table.boundary}), dtype=np.intp)
        cols = self.cols
        width = len(cols)

        def stack(rows: list[npt.NDArray[np.bool_]]) -> npt.NDArray[np.bool_]:
            return np.array(rows, dtype=bool).reshape(len(rows), width)

        everything = np.ones(width, dtype=bool)
        self.target = stack([p.target.mask[cols] for p in processes])
        self.left = stack([everything if p.left is None else p.left.mask[cols] for p in processes])
        self.right = stack([everything if p.right is None else p.right.mask[cols] for p in processes])
        self.right2_rows = np.array([i for i, p in enumerate(processes) if p.right2 is not None], dtype=np.intp)
        self.right2 = stack([cast(Pattern, processes[i].right2).mask[cols] for i in self.right2_rows])

    def gather(self, name: str, ids: npt.NDArray[np.intp]) -> npt.NDArray[np.bool_]:
        """Sloupce masky ``name`` pro hlásky ``ids`` (řádky procesů)."""
        matrix = getattr(self, name)
        cols = self.cols
        position = np.minimum(np.searchsorted(cols, ids), len(cols) - 1)
        out = matrix[:, position]
        missing = np.nonzero(cols[position] != ids)[0]
        if len(missing):
            processes = self.processes if name != "right2" else [self.processes[i] for i in self.right2_rows]
            for column in missing:
                segment = int(ids[column])
                for row, process in enumerate(processes):
                    pattern = getattr(process, name)
                    out[row, column] = True if pattern is None else bool(pattern.mask[segment])
        return out


class _Candidates:
    """Kandidáti rodiny pro jeden inventář a jejich masky složené do matic."""

    def __init__(self, processes: list[Process], table: SegmentTable, inventory: Sequence[int] = ()):
        # Bez inventáře se sloupce dopočítají z úplných masek (pomalejší, stejný výsledek).
        self.processes = processes
        self.masks = _Columns(processes, table, inventory)
        self.right2_rows = self.masks.right2_rows
        # Identifikátor proměnné a jen první kandidát se stejnou změnou.
        self.variable_ids = [_variable_id(process) for process in processes]
        seen: set[str] = set()
        self.first = []
        for index, variable_id in enumerate(self.variable_ids):
            if variable_id not in seen:
                seen.add(variable_id)
                self.first.append(index)
        self.stressed = np.array([process.stress == "stressed" for process in processes], dtype=bool)
        self.unstressed = np.array([process.stress == "unstressed" for process in processes], dtype=bool)

    def supports(self, stats: ContextStats, table: SegmentTable) -> npt.NDArray[np.float64]:
        """Totéž co :meth:`ContextStats.support` pro všechny kandidáty naráz."""
        if not self.processes:
            return np.zeros(0)
        masks = self.masks
        mask = masks.gather("target", stats.segment) & masks.gather("left", stats.previous) \
            & masks.gather("right", stats.following)
        if len(self.right2_rows):
            mask[self.right2_rows] &= masks.gather("right2", stats.following2)
        mask &= np.where(self.stressed[:, None], stats.stressed[None, :], True)
        unstressed = ~stats.stressed & table.vowel_mask[stats.segment]
        mask &= np.where(self.unstressed[:, None], unstressed[None, :], True)
        result: npt.NDArray[np.float64] = mask.astype(np.float64) @ stats.count
        return result


_CANDIDATES: dict[tuple[str, int, tuple[int, ...]], _Candidates] = {}
_CANDIDATES_LIMIT = 1 << 12


class _CombinedSoundCandidates:
    """Sjednocení kandidátů všech rodin zvukových změn pro jeden inventář.

    Python reference a fallback (``CEE_NATIVE=0``). S rozšířením sady staví Rust
    (``rust/cee_core/src/candidates.rs``) z rysů tabulky hlásek, v témže pořadí a se stejnými
    klíči; Python pak postaví jen ``Process`` místa, které se skutečně použije
    (:func:`process_from_spec`). Test ``test_v2_native_candidates`` obě sady porovnává.
    """

    def __init__(self, table: SegmentTable, inventory: tuple[int, ...]):
        self.inventory = inventory
        self.family_slices: dict[str, slice] = {}
        self.family_candidates: dict[str, list[tuple[str, Process]]] = {}
        all_processes: list[Process] = []

        for change in SOUND_CHANGES:
            procs = change.candidates(table, inventory)
            seen: set[str] = set()
            uniq: list[tuple[str, Process]] = []
            for proc in procs:
                var_id = _variable_id(proc)
                if var_id not in seen:
                    seen.add(var_id)
                    uniq.append((var_id, proc))
            uniq.sort(key=lambda item: item[0])
            start = len(all_processes)
            all_processes.extend([proc for _, proc in uniq])
            self.family_slices[change.kind] = slice(start, len(all_processes))
            self.family_candidates[change.kind] = uniq

        self.all_processes = all_processes
        #: Konec každé rodiny (v pořadí ``SOUND_CHANGES``) v řádcích kandidátů.
        self.family_ends = [self.family_slices[change.kind].stop for change in SOUND_CHANGES]
        self.masks = _Columns(all_processes, table, inventory)
        self.right2_rows = self.masks.right2_rows
        self.stressed_rows = np.array([i for i, p in enumerate(all_processes) if p.stress == "stressed"],
                                      dtype=np.intp)
        self.unstressed_rows = np.array([i for i, p in enumerate(all_processes) if p.stress == "unstressed"],
                                        dtype=np.intp)
        #: Pole předaná jádru v Rustu (sestaví se při prvním použití).
        self._kernel_arguments: tuple[npt.NDArray[np.int64], ...] | None = None

    def eval_supports(
        self,
        prev: npt.NDArray[np.intp],
        seg: npt.NDArray[np.intp],
        foll: npt.NDArray[np.intp],
        str_arr: npt.NDArray[np.bool_],
        foll2: npt.NDArray[np.intp],
        counts_int64: npt.NDArray[np.int64],
        table: SegmentTable,
    ) -> npt.NDArray[np.int64]:
        """Opory všech kandidátů nad počty (rozdíly počtů) prostředí; Rust, nebo Python."""
        if not self.all_processes or len(counts_int64) == 0:
            return np.zeros(len(self.all_processes), dtype=np.int64)
        kernel = native.kernel("sound_supports")
        if kernel is not None:
            masks = self.masks
            arguments = self._kernel_arguments
            if arguments is None:
                arguments = self._kernel_arguments = (
                    masks.cols.astype(np.int64), masks.target, masks.left, masks.right, masks.right2,
                    masks.right2_rows.astype(np.int64), self.stressed_rows.astype(np.int64),
                    self.unstressed_rows.astype(np.int64),
                )
            # Hláska mimo inventář (prostředí slova, které zmizelo) nemá sloupec v maskách:
            # Rust pak vrátí ``None`` a tu dopočítá Python z úplných masek procesů.
            found = kernel(
                *arguments, np.ascontiguousarray(seg, dtype=np.int64), np.ascontiguousarray(prev, dtype=np.int64),
                np.ascontiguousarray(foll, dtype=np.int64), np.ascontiguousarray(foll2, dtype=np.int64),
                np.ascontiguousarray(str_arr, dtype=bool), table.vowel_mask, np.ascontiguousarray(counts_int64, dtype=np.int64),
            )
            if found is not None:
                result: npt.NDArray[np.int64] = found
                return result
        return self.eval_supports_python(prev, seg, foll, str_arr, foll2, counts_int64, table)

    def eval_supports_python(
        self,
        prev: npt.NDArray[np.intp],
        seg: npt.NDArray[np.intp],
        foll: npt.NDArray[np.intp],
        str_arr: npt.NDArray[np.bool_],
        foll2: npt.NDArray[np.intp],
        counts_int64: npt.NDArray[np.int64],
        table: SegmentTable,
    ) -> npt.NDArray[np.int64]:
        masks = self.masks
        mask = masks.gather("target", seg) & masks.gather("left", prev) & masks.gather("right", foll)
        if len(self.right2_rows):
            mask[self.right2_rows] &= masks.gather("right2", foll2)
        if len(self.stressed_rows):
            mask[self.stressed_rows] &= str_arr
        if len(self.unstressed_rows):
            unstressed = ~str_arr & table.vowel_mask[seg]
            mask[self.unstressed_rows] &= unstressed
        result: npt.NDArray[np.int64] = mask @ counts_int64
        return result


_COMBINED_CANDIDATES: dict[tuple[int, tuple[int, ...]], _CombinedSoundCandidates] = {}
_COMBINED_CANDIDATES_LIMIT = 1 << 10


def _combined_candidates(table: SegmentTable, inventory: tuple[int, ...]) -> _CombinedSoundCandidates:
    memo_key = (id(table), inventory)
    found = _COMBINED_CANDIDATES.get(memo_key)
    if found is None:
        if len(_COMBINED_CANDIDATES) >= _COMBINED_CANDIDATES_LIMIT:
            _COMBINED_CANDIDATES.clear()
        found = _COMBINED_CANDIDATES[memo_key] = _CombinedSoundCandidates(table, inventory)
    return found


class _SoundCatalog:
    """Sady kandidátů a míry rodin, jak je potřebuje index světa (``language.sound_index``)."""

    #: Míra rodiny na jednotku opory: ``SOUND_INNOVATIONS_PER_GENERATION · prior / součet priorů``.
    scales: list[float]

    def __init__(self) -> None:
        self.scales = []

    @staticmethod
    def candidates(table: SegmentTable, inventory: tuple[int, ...]) -> _CombinedSoundCandidates:
        return _combined_candidates(table, inventory)


class _FamilyView:
    """Místa jedné rodiny u jednoho kódu: názvy proměnných, míry, součet a váhy.

    S indexem v Rustu drží sadu kandidátů Rust (názvy míst a popisy procesů čte z něj; ``Process``
    se postaví jen pro místo, které se skutečně použije); bez něj ji sestaví Python (``_combined_candidates``).
    """

    def __init__(self, index: SoundIndex | NativeSoundIndex, code: Code, table: SegmentTable, family: int, kind: str) -> None:
        self.index, self.code, self.table, self.kind = index, code, table, kind
        self.positions, self.rates, self.total = index.family(code, family)
        self._family = family
        self.combined: _CombinedSoundCandidates | None
        if isinstance(index, NativeSoundIndex):
            self.combined = None
            self.names: list[str] = index.family_names(code, family)
        else:
            self.combined = _combined_candidates(table, index.inventory(code))
            candidates = self.combined.family_candidates[kind]
            self.names = [candidates[position][0] for position in self.positions.tolist()]

    @property
    def weights(self) -> npt.NDArray[np.float64] | None:
        return (self.rates / self.total) if self.total > 0.0 else None

    def position_of(self, site: str) -> int | None:
        try:
            return self.names.index(site)
        except ValueError:
            return None

    def process_of(self, site: str) -> Process:
        found = self.position_of(site)
        if found is None:
            raise KeyError(site)
        return self._process_at(found)

    def _process_at(self, found: int) -> Process:
        if self.combined is None:
            index = cast(NativeSoundIndex, self.index)
            return process_from_spec(self.table, index.family_spec(self.code, self._family, found))
        return self.combined.family_candidates[self.kind][int(self.positions[found])][1]

    def supported(self) -> dict[str, tuple[Process, float]]:
        if self.combined is None:
            index = cast(NativeSoundIndex, self.index)
            supports = index.family_supports(self.code, self._family)
            return {name: (self._process_at(at), float(supports[at])) for at, name in enumerate(self.names)}
        candidates = self.combined.family_candidates[self.kind]
        supports = self.index.supports(self.code)
        start = self.combined.family_slices[self.kind].start
        return {
            candidates[position][0]: (candidates[position][1], float(supports[start + position]))
            for position in self.positions.tolist()
        }


def process_from_spec(table: SegmentTable, spec: Any) -> Process:
    """``Process`` z popisu kandidáta, který postavil Rust (:func:`cee.v2.language.sound_index`).

    Vzory se berou z tabulky hlásek (``pattern``, ``segments``), takže jsou tytéž (pamatované) objekty
    jako ve vzorech, které stavěl Python; pole ve výchozí hodnotě se nepředávají, jako v ``_make``.
    """
    (family, label, operation, changes, segment, stress, medial), (ease, ease_is_int, clarity, reductive, allow, tone), \
        (target, left, right, right2) = spec
    fields: dict[str, object] = {"target": _pattern_of(table, target), "operation": operation}
    if changes:
        fields["changes"] = tuple((name, value) for name, value in changes)
    if segment is not None:
        fields["segment"] = segment
    if left is not None:
        fields["left"] = _pattern_of(table, left)
    if right is not None:
        fields["right"] = _pattern_of(table, right)
    if stress is not None:
        fields["stress"] = stress
    if medial:
        fields["medial"] = True
    fields["ease"] = 0 if ease_is_int else ease
    fields["clarity"] = clarity
    if reductive:
        fields["reductive"] = True
    if allow:
        fields["allow"] = tuple(allow)
    if right2 is not None:
        fields["right2"] = _pattern_of(table, right2)
    if tone is not None:
        fields["tone"] = tone
    return _make(FAMILY_KINDS[family], label, **fields)


_CONSONANT_OR_BOUNDARY: WeakKeyDictionary[SegmentTable, Pattern] = WeakKeyDictionary()


def _pattern_of(table: SegmentTable, recipe: Any) -> Pattern:
    """Vzor podle předpisu z Rustu (druh, dvojice rys-hodnota, zápis hlásek výčtu)."""
    kind, items, symbols = recipe
    if kind == "features":
        return table.pattern(dict(items))
    if kind == "segments":
        return table.segments(symbols)
    if kind == "vowel":
        return table.VOWEL
    if kind == "consonant":
        return table.CONSONANT
    if kind == "boundary":
        return table.BOUNDARY
    found = _CONSONANT_OR_BOUNDARY.get(table)
    if found is None:
        found = _CONSONANT_OR_BOUNDARY[table] = Pattern("C|#", table.CONSONANT.mask | table.BOUNDARY.mask)
    return found


def sound_index(world: World) -> SoundIndex | NativeSoundIndex:
    """Index prostředí a opor světa; kopie světa (checkpoint) dostane vlastní kopii stavu."""
    index = world.sound
    if index is None:
        handle = native.new_sound_index(CATALOG.scales) if world.form_bank()._native is not None else None
        index = world.sound = SoundIndex() if handle is None else NativeSoundIndex(handle, CATALOG.scales)
    return cast("SoundIndex | NativeSoundIndex", index)


CATALOG = _SoundCatalog()


class SoundChange(Change):
    """Rodina zvukových změn. Podtřída říká jen, jaké procesy umí vyrobit."""

    target = "process"
    rate_basis = "generation"
    pressures = SOUND_PRESSURES
    base_rate = 0.0  # míra se počítá z ``prior`` a opory kandidáta

    prior: ClassVar[float]
    domain: ClassVar[Domain]
    #: Tónové rodiny mají vlastní rozpočet inovací: do ``_TOTAL_PRIOR`` se
    #: nepočítají, takže tempo ostatních rodin nezmění.
    tonal: ClassVar[bool] = False

    @abstractmethod
    def candidates(self, table: SegmentTable, inventory: Sequence[int]) -> list[Process]:
        """Procesy, které rodina umí v daném inventáři vyrobit."""

    def _family_view(self, context: InnovationContext) -> _FamilyView | None:
        """Místa a míry rodiny z indexu světa; ``None`` pro vlastní váhy priorů nebo prázdný inventář."""
        if _STANDARD_SOUND_PRIORS.get(type(self)) != self.prior:
            return None
        world, code = context.world, context.code
        table = world.table
        if table is None or not code.phonology.vocabulary:
            return None
        index = sound_index(world)
        index.sync(world, [code], CATALOG)
        if not index.has_families(code):
            return None
        return _FamilyView(index, code, table, FAMILY_INDEX[self.kind], self.kind)

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return ()  # svět bez hláskových tvarů (M1) nebo prázdná slovní zásoba
        view = self._family_view(context)
        if view is not None:
            return view.names
        self._supported_legacy(context)
        return cast(list[str], context.code.phonology.cache[("sound-sites-sorted", self.kind)][1])

    def total_rate(self, context: InnovationContext) -> float:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return 0.0
        view = self._family_view(context)
        if view is not None:
            return view.total
        return super().total_rate(context)

    def total_rates(self, contexts: Sequence[InnovationContext]) -> list[float]:
        """Součty měr všech skupin naráz: jedno dorovnání indexu světa na tik místo jednoho na skupinu."""
        if not contexts or _STANDARD_SOUND_PRIORS.get(type(self)) != self.prior:
            return super().total_rates(contexts)
        world = contexts[0].world
        live = [
            position for position, context in enumerate(contexts)
            if context.world.table is not None and context.code.phonology.vocabulary
        ]
        totals = [0.0] * len(contexts)
        if not live:
            return totals
        index = sound_index(world)
        codes = [contexts[position].code for position in live]
        index.sync(world, codes, CATALOG)
        column = index.totals(codes, len(SOUND_CHANGES))[:, FAMILY_INDEX[self.kind]]
        for position, code, value in zip(live, codes, column.tolist()):
            if index.has_families(code):
                totals[position] = value
            else:
                totals[position] = super().total_rate(contexts[position])
        return totals

    def weighted_sites(
        self, context: InnovationContext
    ) -> tuple[Sequence[str], npt.NDArray[np.float64] | None]:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return (), None
        view = self._family_view(context)
        if view is not None:
            return view.names, view.weights
        return super().weighted_sites(context)

    def rate(self, context: InnovationContext, site: str) -> float:
        view = self._family_view(context)
        if view is not None:
            found = view.position_of(site)
            if found is None:
                raise KeyError(site)
            return float(view.rates[found])
        supported = self._supported_legacy(context)
        share = self.prior / _total_prior()
        _, support = supported[site]
        return SOUND_INNOVATIONS_PER_GENERATION * share * min(1.0, support / FULL_SUPPORT) / len(supported)

    def rates(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        view = self._family_view(context)
        if view is not None:
            if sites is view.names or sites == view.names:
                return view.rates.tolist()
            rates = view.rates
            return [float(rates[cast(int, view.position_of(site))]) for site in sites]
        supported = self._supported_legacy(context)
        scale = SOUND_INNOVATIONS_PER_GENERATION * (self.prior / _total_prior())
        return [scale * min(1.0, supported[site][1] / FULL_SUPPORT) / len(supported) for site in sites]

    def _supported(self, context: InnovationContext) -> dict[str, tuple[Process, float]]:
        view = self._family_view(context)
        if view is not None:
            return view.supported()
        return self._supported_legacy(context)

    def _supported_legacy(self, context: InnovationContext) -> dict[str, tuple[Process, float]]:
        state = context.code.phonology
        cache_key = ("sound-sites", self.kind)
        cached = state.cache.get(cache_key)
        if cached is not None and cached[0] == state.version:
            return cast(dict[str, tuple[Process, float]], cached[1])
        stats = context_stats(context)
        table = context.world.table
        found: dict[str, tuple[Process, float]] = {}
        if stats is not None and table is not None:
            # Kandidáti závisí jen na inventáři, a ten mají vesnice většinou
            # společný a mění se zřídka: sestaví se jednou pro každý inventář.
            memo_key = (self.kind, id(table), stats.inventory)
            prepared = _CANDIDATES.get(memo_key)
            if prepared is None:
                if len(_CANDIDATES) >= _CANDIDATES_LIMIT:
                    _CANDIDATES.clear()
                prepared = _CANDIDATES[memo_key] = _Candidates(self.candidates(table, stats.inventory), table,
                                                               stats.inventory)
            # Opory všech kandidátů jedním maticovým násobením nad počty
            # prostředí (počty jsou celá čísla, součet je přesný).
            supports = prepared.supports(stats, table)
            for index in prepared.first:
                support = float(supports[index])
                if support >= MIN_SUPPORT:
                    found[prepared.variable_ids[index]] = (prepared.processes[index], support)
        state.cache[cache_key] = (state.version, found)
        state.cache[("sound-sites-sorted", self.kind)] = (state.version, sorted(found))
        return found

    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        view = self._family_view(context)
        process = self._supported_legacy(context)[site][0] if view is None else view.process_of(site)
        _, variant = register(
            context.world, process,
            Origin(self.kind, context.tick, context.year, context.group.id),
        )
        return variant


def _present(table: SegmentTable, inventory: Sequence[int], pattern: Pattern) -> list[int]:
    return [segment for segment in inventory if segment in pattern]


#: Čisté funkce tabulky hlásek, které sestavování kandidátů volá pro každý inventář znovu
#: se stejnými argumenty; pamatují se po tabulce (slabě, tabulka s nimi nezmizí z paměti).
_SINGLES: WeakKeyDictionary[SegmentTable, dict[int, Pattern]] = WeakKeyDictionary()
_DELTAS: WeakKeyDictionary[SegmentTable, dict[tuple[int, int], tuple[tuple[str, str], ...]]] = WeakKeyDictionary()


def _single(table: SegmentTable, segment: int) -> Pattern:
    found = _SINGLES.setdefault(table, {})
    pattern = found.get(segment)
    if pattern is None:
        pattern = found[segment] = table.segments([table.ipa[segment]])
    return pattern


#: Hotové procesy podle všech argumentů (včetně typů hodnot). Vzory hlásek jsou v tabulce
#: pamatované, takže stejný proces z jiného inventáře má stejné argumenty a sdílí instanci:
#: ``Process`` je neměnný, klíč se počítá jednou. Při zaplnění se paměť vyprázdní.
_MADE: dict[tuple[object, ...], Process] = {}
_MADE_LIMIT = 1 << 17
_PROCESS_IDS: dict[str, str] = {}


def _make(family: str, label: str, **fields: object) -> Process:
    key = (family, label, *fields.items(), *map(type, fields.values()))
    try:
        found = _MADE.get(key)
    except TypeError:  # nehašovatelný argument: bez paměti
        return Process(family=family, label=label, **fields)  # type: ignore[arg-type]
    if found is None:
        if len(_MADE) >= _MADE_LIMIT:
            _MADE.clear()
        found = _MADE[key] = Process(family=family, label=label, **fields)  # type: ignore[arg-type]
    return found


def _variable_id(process: Process) -> str:
    """Identifikátor proměnné procesu (``Variable("process", key).id``), pamatovaný po klíči."""
    key = process.key
    found = _PROCESS_IDS.get(key)
    if found is None:
        found = _PROCESS_IDS[key] = Variable("process", key).id
    return found


class Voicing(SoundChange):
    """Lenice 1: znělost neznělých obstruentů mezi samohláskami (p → b)."""

    kind, prior, domain = "voicing", 1.0, "consonant"

    def candidates(self, table, inventory):
        stops = table.pattern({"syl": "-", "son": "-", "voi": "-"})
        found = [
            _make(self.kind, f"{table.ipa[s]} → zněle /V_V", target=_single(table, s),
                  operation="change", changes=(("voi", "+"),), left=table.VOWEL, right=table.VOWEL,
                  ease=0.15, clarity=-0.1, reductive=True)
            for s in _present(table, inventory, stops)
        ]
        if len(_present(table, inventory, table.pattern({"syl": "-", "son": "-", "voi": "-", "cont": "-"}))) >= 2:
            found.append(_make(
                self.kind, "řada neznělých okluziv → zněle /V_V",
                target=table.pattern({"syl": "-", "son": "-", "voi": "-", "cont": "-"}),
                operation="change", changes=(("voi", "+"),), left=table.VOWEL, right=table.VOWEL,
                ease=0.15, clarity=-0.1, reductive=True,
            ))
        return found


class Spirantization(SoundChange):
    """Lenice 2: okluziva mezi samohláskami se stane frikativou (b → β)."""

    kind, prior, domain = "spirantization", 0.8, "consonant"

    def candidates(self, table, inventory):
        stops = table.pattern({"syl": "-", "son": "-", "cont": "-", "delrel": "-"})
        found = []
        for s in _present(table, inventory, stops):
            found.append(_make(
                self.kind, f"{table.ipa[s]} → frikativa /V_V", target=_single(table, s),
                operation="change", changes=(("cont", "+"), ("strid", "-")),
                left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.15, reductive=True,
            ))
        voiced = table.pattern({"syl": "-", "son": "-", "cont": "-", "delrel": "-", "voi": "+"})
        if len(_present(table, inventory, voiced)) >= 2:
            found.append(_make(
                self.kind, "řada znělých okluziv → frikativy /V_V", target=voiced,
                operation="change", changes=(("cont", "+"), ("strid", "-")),
                left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.15, reductive=True,
            ))
        return found


class Debuccalization(SoundChange):
    """Ztráta ústního místa: s, f, x → h mezi samohláskami nebo na konci."""

    kind, prior, domain = "debuccalization", 0.4, "consonant"

    def candidates(self, table, inventory):
        h = table.id_of("h")
        fricatives = table.pattern({"syl": "-", "son": "-", "cont": "+", "voi": "-"})
        found = []
        for s in _present(table, inventory, fricatives):
            if s == h:
                continue
            for left, right, where in ((table.VOWEL, table.VOWEL, "V_V"), (table.VOWEL, table.BOUNDARY, "V_#")):
                found.append(_make(
                    self.kind, f"{table.ipa[s]} → h /{where}", target=_single(table, s),
                    operation="replace", segment=h, left=left, right=right,
                    ease=0.125, clarity=-0.2, reductive=True,
                ))
        return found


class IntervocalicLoss(SoundChange):
    """Lenice 3: znělá frikativa, h nebo polosamohláska mezi samohláskami zmizí."""

    kind, prior, domain = "intervocalic_loss", 0.4, "consonant"

    def candidates(self, table, inventory):
        weak = sorted(
            s for s in inventory
            if not table.is_vowel(s) and (
                table.ipa[s] in ("h", "j", "w")
                or (table.feature(s, "cont") == 1 and table.feature(s, "voi") == 1
                    and table.feature(s, "son") != 1 and table.feature(s, "strid") != 1)
            )
        )
        return [
            _make(self.kind, f"{table.ipa[s]} → ∅ /V_V", target=_single(table, s), operation="delete",
                  left=table.VOWEL, right=table.VOWEL, ease=0.15, clarity=-0.4, reductive=True)
            for s in weak
        ]


class Fortition(SoundChange):
    """Zesílení na začátku slova: frikativa → okluziva, j → d͡ʒ."""

    kind, prior, domain = "fortition", 0.3, "consonant"

    def candidates(self, table, inventory):
        found = []
        fricatives = table.pattern({"syl": "-", "son": "-", "cont": "+", "voi": "+"})
        for s in _present(table, inventory, fricatives):
            found.append(_make(
                self.kind, f"{table.ipa[s]} → okluziva /#_", target=_single(table, s),
                operation="change", changes=(("cont", "-"), ("strid", "-"), ("delrel", "-")),
                left=table.BOUNDARY, ease=-0.1, clarity=0.3,
            ))
        if table.id_of("j") in inventory:
            found.append(_make(
                self.kind, "j → d͡ʒ /#_", target=table.segments(["j"]), operation="replace",
                segment=table.id_of("d͡ʒ"), left=table.BOUNDARY, ease=-0.1, clarity=0.3,
            ))
        return found


class Palatalization(SoundChange):
    """Velára, dentála nebo s před předním vokálem či j se posune k patru."""

    kind, prior, domain = "palatalization", 0.8, "consonant"

    def candidates(self, table, inventory):
        place = ["cor", "ant", "distr", "hi", "lo", "back", "delrel", "strid", "lab"]
        front = table.pattern({"hi": "+", "back": "-"})
        outputs = {
            "k": table.features_of("t͡ʃ", place), "ɡ": table.features_of("d͡ʒ", place),
            "t": table.features_of("t͡s", place), "d": table.features_of("d͡z", place),
            "s": table.features_of("ʃ", ["ant", "distr", "cor"]),
        }
        found = []
        for symbol, changes in outputs.items():
            segment = table.id_of(symbol)
            if segment in inventory:
                found.append(_make(
                    self.kind, f"{symbol} → palatála /_i", target=_single(table, segment),
                    operation="change", changes=changes, right=front, ease=0.15, clarity=0.0,
                    reductive=True,
                ))
        return found


class NasalAssimilation(SoundChange):
    """Nazála převezme místo následující okluzivy (n → m /_p)."""

    kind, prior, domain = "nasal_assimilation", 0.8, "consonant"

    def candidates(self, table, inventory):
        nasals = _present(table, inventory, table.pattern({"nas": "+", "syl": "-"}))
        places = (
            ("m", table.pattern({"syl": "-", "son": "-", "lab": "+"})),
            ("n", table.pattern({"syl": "-", "son": "-", "cor": "+"})),
            ("ŋ", table.pattern({"syl": "-", "son": "-", "hi": "+", "back": "+"})),
        )
        found = []
        for nasal in nasals:
            for symbol, before in places:
                output = table.id_of(symbol)
                if output != nasal:
                    found.append(_make(
                        self.kind, f"{table.ipa[nasal]} → {symbol} před homorganní okluzivou",
                        target=_single(table, nasal), operation="replace", segment=output,
                        right=before, ease=0.2, clarity=-0.05,
                    ))
        return found


class VoicingAssimilation(SoundChange):
    """Obstruent převezme znělost následujícího obstruentu."""

    kind, prior, domain = "voicing_assimilation", 0.6, "consonant"

    def candidates(self, table, inventory):
        found = []
        for value, opposite in (("+", "-"), ("-", "+")):
            target = table.pattern({"syl": "-", "son": "-", "voi": opposite})
            if _present(table, inventory, target):
                found.append(_make(
                    self.kind, f"obstruent → {value}zněle před {value}znělým",
                    target=target, operation="change", changes=(("voi", value),),
                    right=table.pattern({"syl": "-", "son": "-", "voi": value}),
                    ease=0.15, clarity=-0.05,
                ))
        return found


class FinalDevoicing(SoundChange):
    kind, prior, domain = "final_devoicing", 0.5, "consonant"

    def candidates(self, table, inventory):
        target = table.pattern({"syl": "-", "son": "-", "voi": "+"})
        if not _present(table, inventory, target):
            return []
        return [_make(self.kind, "znělý obstruent → nezněle /_#", target=target, operation="change",
                      changes=(("voi", "-"),), right=table.BOUNDARY, ease=0.1, clarity=-0.1)]


_CONSONANT_CLASSES = {
    "okluzivy": {"syl": "-", "son": "-", "cont": "-"},
    "nazály": {"syl": "-", "nas": "+"},
    "frikativy": {"syl": "-", "son": "-", "cont": "+"},
    "likvidy": {"syl": "-", "son": "+", "cons": "+", "nas": "-"},
}


class CodaLoss(SoundChange):
    """Koncová souhláska (třída nebo jedna hláska) zmizí."""

    kind, prior, domain = "coda_loss", 0.5, "consonant"

    def candidates(self, table, inventory):
        found = []
        for name, features in _CONSONANT_CLASSES.items():
            pattern = table.pattern(features)
            present = _present(table, inventory, pattern)
            if present:
                found.append(_make(self.kind, f"{name} → ∅ /V_#", target=pattern, operation="delete",
                                   left=table.VOWEL, right=table.BOUNDARY, ease=0.15, clarity=-0.3,
                                   reductive=True))
            for segment in present:
                found.append(_make(self.kind, f"{table.ipa[segment]} → ∅ /V_#",
                                   target=_single(table, segment), operation="delete",
                                   left=table.VOWEL, right=table.BOUNDARY, ease=0.15, clarity=-0.3,
                                   reductive=True))
        return found


class ClusterSimplification(SoundChange):
    """První souhláska vnitřního shluku zmizí (VCCV → VCV)."""

    kind, prior, domain = "cluster_simplification", 0.6, "consonant"

    def candidates(self, table, inventory):
        found = []
        for name, features in _CONSONANT_CLASSES.items():
            pattern = table.pattern(features)
            if _present(table, inventory, pattern):
                found.append(_make(self.kind, f"{name} → ∅ /V_C", target=pattern, operation="delete",
                                   left=table.VOWEL, right=table.CONSONANT, ease=0.15, clarity=-0.2,
                                   reductive=True))
        return found


def _vowels(table: SegmentTable, inventory: Sequence[int]) -> list[int]:
    return [segment for segment in inventory if table.is_vowel(segment)]


class VowelReduction(SoundChange):
    """Nepřízvučný vokál se oslabí na ə."""

    kind, prior, domain = "vowel_reduction", 0.8, "vowel"

    def candidates(self, table, inventory):
        schwa = table.id_of("ə")
        found = [
            _make(self.kind, f"{table.ipa[v]} → ə v nepřízvučné slabice", target=_single(table, v),
                  operation="replace", segment=schwa, stress="unstressed", ease=0.15, clarity=-0.2,
                  reductive=True)
            for v in _vowels(table, inventory) if v != schwa
        ]
        found.append(_make(self.kind, "nevysoké vokály → ə v nepřízvučné slabice",
                           target=table.pattern({"syl": "+", "hi": "-"}), operation="replace",
                           segment=schwa, stress="unstressed", ease=0.15, clarity=-0.2, reductive=True))
        return found


#: Ztráta akustických vodítek při smazání nepřízvučného plného vokálu.
CLARITY_DELETE_FULL: float = -0.15

#: Ztráta akustických vodítek při smazání redukovaného vokálu [ə] (šva).
#: Redukovaný vokál nese minimální percepční kontrast (Ohala 1993; Blevins 2004),
#: proto je trest za jeho zánik výrazně nižší než u plných samohlásek.
CLARITY_DELETE_SCHWA: float = -0.05


class Syncope(SoundChange):
    """Nepřízvučný vokál mezi souhláskami zmizí."""

    kind, prior, domain = "syncope", 0.5, "vowel"

    def candidates(self, table, inventory):
        schwa = table.id_of("ə")
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_C nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.CONSONANT,
                  stress="unstressed", medial=True, ease=0.15,
                  clarity=CLARITY_DELETE_SCHWA if v == schwa else CLARITY_DELETE_FULL,
                  reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vysoké vokály → ∅ /C_C nepřízvučně",
                           target=table.pattern({"syl": "+", "hi": "+"}), operation="delete",
                           left=table.CONSONANT, right=table.CONSONANT, stress="unstressed",
                           medial=True, ease=0.15, clarity=CLARITY_DELETE_FULL, reductive=True))
        return found


class Apocope(SoundChange):
    """Koncový nepřízvučný vokál zmizí."""

    kind, prior, domain = "apocope", 0.5, "vowel"

    def candidates(self, table, inventory):
        schwa = table.id_of("ə")
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_# nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.BOUNDARY,
                  stress="unstressed", ease=0.15,
                  clarity=CLARITY_DELETE_SCHWA if v == schwa else CLARITY_DELETE_FULL,
                  reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vokály → ∅ /C_# nepřízvučně",
                           target=table.VOWEL, operation="delete", left=table.CONSONANT,
                           right=table.BOUNDARY, stress="unstressed", ease=0.15,
                           clarity=CLARITY_DELETE_FULL, reductive=True))
        return found


#: Obyčejné vokály, mezi kterými se posouvá kvalita.
_VOWEL_SPACE = ("i", "y", "ɨ", "u", "e", "ø", "ə", "o", "ɛ", "ɔ", "a", "ɑ", "æ")


class VowelShift(SoundChange):
    """Posun kvality jednoho vokálu o krok v prostoru (zvýšení, snížení, …).

    Řetězové posuny se tu neprogramují: vzniknou, když uvolněné místo
    zvýhodní tlak disperze a funkční zátěž brání splynutí (iterace 3).
    """

    kind, prior, domain = "vowel_shift", 1.2, "vowel"

    def candidates(self, table, inventory):
        space = [table.id_of(symbol) for symbol in _VOWEL_SPACE]
        found = []
        for vowel in _vowels(table, inventory):
            if vowel not in space:
                continue
            origin = table.vowel_coordinates(vowel)
            for other in space:
                if other == vowel:
                    continue
                target = table.vowel_coordinates(other)
                steps = [abs(a - b) for a, b in zip(origin, target)]
                # Jeden krok v jediném rozměru: sousední vokál, ne skok přes systém.
                if sum(1 for step in steps if step > 0) != 1 or max(steps) > 1.0:
                    continue
                for stress, where in ((None, "všude"), ("stressed", "v přízvučné slabice")):
                    found.append(_make(
                        self.kind, f"{table.ipa[vowel]} → {table.ipa[other]} {where}",
                        target=_single(table, vowel), operation="replace", segment=other,
                        stress=stress, ease=0, clarity=0.0,
                    ))
        return found


class Diphthongization(SoundChange):
    """Přízvučné středové e, o získá polosamohlásku (e → je, o → wo)."""

    kind, prior, domain = "diphthongization", 0.4, "vowel"

    def candidates(self, table, inventory):
        found = []
        for symbol, glide in (("e", "j"), ("ɛ", "j"), ("o", "w"), ("ɔ", "w")):
            segment = table.id_of(symbol)
            if segment in inventory:
                found.append(_make(self.kind, f"{symbol} → {glide}{symbol} v přízvučné slabice",
                                   target=_single(table, segment), operation="insert_before",
                                   segment=table.id_of(glide), stress="stressed",
                                   ease=-0.05, clarity=0.2))
        return found


class Monophthongization(SoundChange):
    """Dvojice vokálů splyne v jeden (ai → e, au → o)."""

    kind, prior, domain = "monophthongization", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = []
        for first, second, output in (("a", "i", "e"), ("a", "u", "o"), ("e", "i", "i"),
                                      ("o", "u", "u"), ("o", "i", "ø"), ("a", "e", "ɛ")):
            a, b = table.id_of(first), table.id_of(second)
            if a in inventory and b in inventory:
                found.append(_make(self.kind, f"{first}{second} → {output}", target=_single(table, a),
                                   operation="merge_next", segment=table.id_of(output),
                                   right=_single(table, b), ease=0.15, clarity=-0.1))
        return found


class GlideFormation(SoundChange):
    """Vysoký vokál před jiným vokálem se stane polosamohláskou (ia → ja)."""

    kind, prior, domain = "glide_formation", 0.5, "structure"

    def candidates(self, table, inventory):
        found = []
        for vowel, glide in (("i", "j"), ("u", "w")):
            segment = table.id_of(vowel)
            if segment in inventory:
                found.append(_make(self.kind, f"{vowel} → {glide} /_V", target=_single(table, segment),
                                   operation="replace", segment=table.id_of(glide), right=table.VOWEL,
                                   ease=0.1, clarity=-0.05))
        return found


def _epenthetic_vowel(table: SegmentTable, inventory: Sequence[int]) -> int:
    for symbol in ("ə", "e", "i", "a"):
        segment = table.id_of(symbol)
        if segment in inventory:
            return segment
    return table.id_of("e")


class Epenthesis(SoundChange):
    """Vložený vokál rozbije koncový shluk souhlásek (-CC → -CVC)."""

    kind, prior, domain = "epenthesis", 0.4, "structure"

    def candidates(self, table, inventory):
        vowel = _epenthetic_vowel(table, inventory)
        return [_make(self.kind, f"∅ → {table.ipa[vowel]} /C_C#", target=table.CONSONANT,
                      operation="insert_before", segment=vowel, left=table.CONSONANT,
                      right=table.BOUNDARY, ease=-0.1, clarity=0.2)]


class Prothesis(SoundChange):
    """Vokál před počátečním s + souhláska (sp- → esp-)."""

    kind, prior, domain = "prothesis", 0.15, "structure"

    def candidates(self, table, inventory):
        s = table.id_of("s")
        if s not in inventory:
            return []
        vowel = table.id_of("e") if table.id_of("e") in inventory else _epenthetic_vowel(table, inventory)
        return [_make(self.kind, f"∅ → {table.ipa[vowel]} /#_sC", target=table.segments(["s"]),
                      operation="insert_before", segment=vowel, left=table.BOUNDARY,
                      right=table.CONSONANT, ease=-0.05, clarity=0.1)]




def _feature_delta(table: SegmentTable, source: int, target: int) -> tuple[tuple[str, str], ...]:
    found = _DELTAS.setdefault(table, {})
    delta = found.get((source, target))
    if delta is None:
        symbols = {1: "+", -1: "-", 0: "0"}
        delta = found[(source, target)] = tuple(sorted(
            (name, symbols[table.feature(target, name)]) for name in table.names
            if table.feature(source, name) != table.feature(target, name)))
    return delta


class SecondaryPalatalization(SoundChange):
    """C → Cʲ / _i,j. The numerical prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    The original direct Palatalization remains a parallel historical pathway.
    """
    kind, prior, domain = "secondary_palatalization", 0.35, "consonant"

    def candidates(self, table, inventory):
        front = table.segments(("i", "j"))
        found = []
        for symbol in ("p", "t", "k", "b", "d", "ɡ", "s", "m", "n", "l", "r"):
            src, dst = table.id_of(symbol), table.id_of(symbol + "ʲ")
            if src in inventory and src != dst:
                found.append(_make(self.kind, f"{symbol} → {symbol}ʲ /_i,j", target=_single(table, src),
                                   operation="change", changes=_feature_delta(table, src, dst),
                                   allow=("ʲ",), right=front, ease=0.1))
        return found


class Depalatalization(SoundChange):
    """Loss of secondary palatalization; numerical prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    """
    kind, prior, domain = "depalatalization", 0.2, "consonant"

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{symbol}ʲ → {symbol}", target=_single(table, table.id_of(symbol + "ʲ")),
                      operation="replace", segment=table.id_of(symbol), ease=0.1)
                for symbol in ("p", "t", "k", "b", "d", "ɡ", "s", "m", "n", "l", "r")
                if table.id_of(symbol + "ʲ") in inventory]


class PalatalAffrication(SoundChange):
    """Palatalized velars develop affricates; prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    """
    kind, prior, domain = "palatal_affrication", 0.25, "consonant"

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{src} → {dst}", target=_single(table, table.id_of(src)),
                      operation="replace", segment=table.id_of(dst), ease=0.05)
                for src, dst in (("kʲ", "t͡ʃ"), ("ɡʲ", "d͡ʒ")) if table.id_of(src) in inventory]


class VowelNasalization(SoundChange):
    """V → Ṽ / _N(C|#); numerical prior is an authored heuristic.

    Ohala & Ohala (1993), “The phonetics of nasal phonology: theorems and
    data”, in Huffman & Krakow (eds.), *Nasals, Nasalization, and the Velum*,
    Academic Press, pp. 225–249; doi:10.1016/B978-0-12-360380-7.50013-2.
    """
    kind, prior, domain = "vowel_nasalization", 0.35, "vowel"

    def candidates(self, table, inventory):
        nasal = table.pattern({"nas": "+", "syl": "-"})
        c_or_boundary = Pattern("C|#", table.CONSONANT.mask | table.BOUNDARY.mask)
        found = []
        for symbol in ("a", "e", "i", "o", "u", "ɛ", "ɔ", "ə"):
            src, dst = table.id_of(symbol), table.id_of(symbol + "\u0303")
            if src in inventory and src != dst:
                found.append(_make(self.kind, f"{symbol} → {symbol}̃ /_N(C|#)", target=_single(table, src),
                                   operation="change", changes=_feature_delta(table, src, dst),
                                   allow=("\u0303",), right=nasal, right2=c_or_boundary,
                                   ease=0.1, reductive=True))
        return found


class VowelDenazalization(SoundChange):
    """Nasal vowels lose nasality; numerical prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press. Ohala & Ohala (1993), “The phonetics of nasal
    phonology: theorems and data”, in Huffman & Krakow (eds.), *Nasals,
    Nasalization, and the Velum*, Academic Press, pp. 225–249.
    """
    kind, prior, domain = "vowel_denazalization", 0.2, "vowel"

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{symbol}̃ → {symbol}", target=_single(table, table.id_of(symbol + "\u0303")),
                      operation="replace", segment=table.id_of(symbol), ease=0.1)
                for symbol in ("a", "e", "i", "o", "u", "ɛ", "ɔ", "ə")
                if table.id_of(symbol + "\u0303") in inventory]


class Labialization(SoundChange):
    """Velar → labialized velar / _u,w; prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    """
    kind, prior, domain = "labialization", 0.3, "consonant"

    def candidates(self, table, inventory):
        found = []
        for symbol in ("k", "ɡ"):
            src, dst = table.id_of(symbol), table.id_of(symbol + "ʷ")
            if src in inventory and src != dst:
                found.append(_make(self.kind, f"{symbol} → {symbol}ʷ /_u,w", target=_single(table, src),
                                   operation="change", changes=_feature_delta(table, src, dst),
                                   allow=("ʷ",), right=table.segments(("u", "w")), ease=0.1))
        return found


class Delabialization(SoundChange):
    """Loss of secondary labialization; numerical prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    """
    kind, prior, domain = "delabialization", 0.2, "consonant"

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{symbol}ʷ → {symbol}", target=_single(table, table.id_of(symbol + "ʷ")),
                      operation="replace", segment=table.id_of(symbol), ease=0.1)
                for symbol in ("k", "ɡ") if table.id_of(symbol + "ʷ") in inventory]


class LabialShift(SoundChange):
    """Labiovelar → labial stop; numerical prior is an authored heuristic.

    Blevins (2004), *Evolutionary Phonology: The Emergence of Sound Patterns*,
    Cambridge University Press; Kümmel (2007), *Konsonantenwandel*, Reichert.
    """
    kind, prior, domain = "labial_shift", 0.2, "consonant"

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{src} → {dst}", target=_single(table, table.id_of(src)),
                      operation="replace", segment=table.id_of(dst), ease=0.05)
                for src, dst in (("kʷ", "p"), ("ɡʷ", "b")) if table.id_of(src) in inventory]


# --- tóny ---------------------------------------------------------------------
#
# Tón je rys samohlásky (``x_tone``). Vzniká fonologizací výšky hlasu, kterou
# sousední souhláska samohlásce vtiskne (Haudricourt 1954; Matisoff 1973;
# Hombert, Ohala & Ewan 1979): po neznělé souhlásce je samohláska výš, po
# znělé níž, před rázem stoupá, před /h/ (a /s/) klesá. Když pak rozdíl
# souhlásek zmizí (ztráta znělosti, ztráta kody), zůstane tón jediným
# rozlišením. Tóny pak splývají, mizí a v sousedství stejného tónu se
# rozrůzňují (sandhi; Yip 2002, *Tone*). Priory jsou autorský odhad.


def _pitch(code: int) -> tuple[int, int]:
    """Začátek a konec tónu na škále 1 (˩) až 5 (˥)."""
    letters = TONES[code - 1]
    return _LEVEL_PITCH[letters[0]], _LEVEL_PITCH[letters[-1]]


_LEVEL_PITCH = {"˩": 1, "˨": 2, "˧": 3, "˦": 4, "˥": 5}


def _tone_distance(first: int, second: int) -> int:
    a, b = _pitch(first), _pitch(second)
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _tones_present(table: SegmentTable, inventory: Sequence[int]) -> list[int]:
    return sorted({table.tone_of(segment) for segment in inventory if table.is_vowel(segment)} - {0})


def _toneless(table: SegmentTable) -> Pattern:
    return table.pattern({"syl": "+", "x_tone": "0"})


def _with_tone(table: SegmentTable, code: int) -> Pattern:
    return table.pattern({"syl": "+", "x_tone": str(code)})


class ToneFromOnset(SoundChange):
    """Tonogeneze z počáteční souhlásky: V → V˦ /T_, V → V˨ /D_."""

    kind, prior, domain, tonal = "tonogenesis_onset", 0.12, "vowel", True

    def candidates(self, table, inventory):
        if not _present(table, inventory, _toneless(table)):
            return []
        found = []
        for voice, tone, name in (("-", "˦", "T"), ("+", "˨", "D")):
            onset = table.pattern({"syl": "-", "son": "-", "voi": voice})
            if _present(table, inventory, onset):
                found.append(_make(self.kind, f"V → V{tone} /{name}_", target=_toneless(table), operation="tone",
                                   tone=TONE_CODES[tone], left=onset, ease=0.0, clarity=0.1))
        return found


class ToneFromCoda(SoundChange):
    """Tonogeneze ze zakončení: V → V˧˥ /_ʔ#, V → V˥˩ /_h#, _s#."""

    kind, prior, domain, tonal = "tonogenesis_coda", 0.08, "vowel", True

    def candidates(self, table, inventory):
        if not _present(table, inventory, _toneless(table)):
            return []
        found = []
        for coda, tone in (("ʔ", "˧˥"), ("h", "˥˩"), ("s", "˥˩")):
            segment = table.id_of(coda)
            if segment in inventory:
                found.append(_make(self.kind, f"V → V{tone} /_{coda}#", target=_toneless(table), operation="tone",
                                   tone=TONE_CODES[tone], right=_single(table, segment), right2=table.BOUNDARY,
                                   ease=0.0, clarity=0.1))
        return found


class ToneMerger(SoundChange):
    """Splynutí dvou blízkých tónů (˦ → ˥, ˧˥ → ˨˥…)."""

    kind, prior, domain, tonal = "tone_merger", 0.08, "vowel", True

    def candidates(self, table, inventory):
        present = _tones_present(table, inventory)
        return [_make(self.kind, f"{TONES[a - 1]} → {TONES[b - 1]}", target=_with_tone(table, a), operation="tone",
                      tone=b, ease=0.1, clarity=-0.15)
                for a in present for b in present if a != b and _tone_distance(a, b) <= 2]


class ToneLoss(SoundChange):
    """Ztráta tónu: V˦ → V (detonalizace, typicky v kontaktu)."""

    kind, prior, domain, tonal = "tone_loss", 0.04, "vowel", True

    def candidates(self, table, inventory):
        return [_make(self.kind, f"{TONES[a - 1]} → ∅", target=_with_tone(table, a), operation="tone", tone=0,
                      ease=0.1, clarity=-0.2)
                for a in _tones_present(table, inventory)]


class ToneDissimilation(SoundChange):
    """Sandhi: ze dvou stejných tónů za sebou se první změní (˨˩˦ ˨˩˦ → ˧˥ ˨˩˦)."""

    kind, prior, domain, tonal = "tone_dissimilation", 0.04, "vowel", True

    def candidates(self, table, inventory):
        present = _tones_present(table, inventory)
        found = []
        for tone in present:
            others = [other for other in present if other != tone]
            if not others:
                continue
            nearest = min(others, key=lambda other: (_tone_distance(tone, other), other))
            found.append(_make(self.kind, f"{TONES[tone - 1]} → {TONES[nearest - 1]} /_C{TONES[tone - 1]}",
                               target=_with_tone(table, tone), operation="tone", tone=nearest,
                               right=table.CONSONANT, right2=_with_tone(table, tone), ease=0.05, clarity=0.05))
        return found


SOUND_CHANGES: tuple[SoundChange, ...] = (
    Voicing(), Spirantization(), Debuccalization(), IntervocalicLoss(), Fortition(),
    Palatalization(), NasalAssimilation(), VoicingAssimilation(), FinalDevoicing(), CodaLoss(),
    ClusterSimplification(), VowelReduction(), Syncope(), Apocope(), VowelShift(),
    Diphthongization(), Monophthongization(), GlideFormation(), Epenthesis(), Prothesis(),
    SecondaryPalatalization(), Depalatalization(), PalatalAffrication(), VowelNasalization(),
    VowelDenazalization(), Labialization(), Delabialization(), LabialShift(),
    ToneFromOnset(), ToneFromCoda(), ToneMerger(), ToneLoss(), ToneDissimilation(),
)

_STANDARD_SOUND_PRIORS: dict[type[SoundChange], float] = {
    type(change): change.prior for change in SOUND_CHANGES
}
_TOTAL_PRIOR: float = sum(change.prior for change in SOUND_CHANGES if not change.tonal)


def _total_prior() -> float:
    return _TOTAL_PRIOR


def standard_sound_changes(changes: Sequence[Change]) -> list[tuple[int, SoundChange]]:
    """Zvukové změny (pozice v ``changes``), které mají standardní váhy priorů a počítá je index světa."""
    return [
        (at, change) for at, change in enumerate(changes)
        if isinstance(change, SoundChange) and _STANDARD_SOUND_PRIORS.get(type(change)) == change.prior
    ]


def live_positions(contexts: Sequence[InnovationContext]) -> list[int]:
    """Pozice skupin, které mají hláskové tvary a neprázdnou slovní zásobu (ostatní zvukové změny nemají)."""
    return [
        position for position, context in enumerate(contexts)
        if context.world.table is not None and context.code.phonology.vocabulary
    ]


def family_totals(
    standard: Sequence[tuple[int, SoundChange]], contexts: Sequence[InnovationContext], live: Sequence[int],
    matrix: npt.NDArray[np.float64], has: Sequence[bool],
) -> dict[int, list[float]]:
    """Součty měr zvukových změn všech skupin z matice (kód × rodina) indexu; klíč je pozice změny.

    Kód bez rodin (index pro něj nic nespočítal) vyřídí výchozí ``Change.total_rate``.
    """
    found: dict[int, list[float]] = {at: [0.0] * len(contexts) for at, _ in standard}
    for at, change in standard:
        column = matrix[:, FAMILY_INDEX[change.kind]].tolist()
        totals = found[at]
        for position, indexed, value in zip(live, has, column):
            totals[position] = value if indexed else Change.total_rate(change, contexts[position])
    return found


def batch_total_rates(
    changes: Sequence[Change], contexts: Sequence[InnovationContext]
) -> dict[int, list[float]]:
    """Součty měr zvukových změn všech skupin: jedno dorovnání a jeden dotaz na index světa pro všechny rodiny.

    Klíč je pozice změny v ``changes``; změny s vlastními váhami priorů (jiná podtřída či ``prior``)
    se tu nepočítají a volající je vyřídí po jedné (``total_rates``).
    """
    standard = standard_sound_changes(changes)
    if not standard or not contexts:
        return {}
    world = contexts[0].world
    live = live_positions(contexts)
    if not live:
        return {at: [0.0] * len(contexts) for at, _ in standard}
    index = sound_index(world)
    codes = [contexts[position].code for position in live]
    index.sync(world, codes, CATALOG)
    matrix = index.totals(codes, len(SOUND_CHANGES))
    return family_totals(standard, contexts, live, matrix, [index.has_families(code) for code in codes])

#: Druh změny podle čísla rodiny (pořadí ``SOUND_CHANGES``, shodné s ``cee_core.candidate_families``).
FAMILY_KINDS: tuple[str, ...] = tuple(change.kind for change in SOUND_CHANGES)
#: Číslo rodiny podle druhu změny (pořadí ``SOUND_CHANGES``).
FAMILY_INDEX: dict[str, int] = {change.kind: number for number, change in enumerate(SOUND_CHANGES)}
CATALOG.scales = [SOUND_INNOVATIONS_PER_GENERATION * (change.prior / _TOTAL_PRIOR) for change in SOUND_CHANGES]

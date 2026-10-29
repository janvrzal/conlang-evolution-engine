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
from typing import TYPE_CHECKING, ClassVar, Literal, Mapping, Sequence, cast

if TYPE_CHECKING:
    from cee.v2.world import Code, World

import numpy as np
import numpy.typing as npt

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.index import ContextIndex
from cee.v2.language.processes import Process, StressRule, stressed_nucleus
from cee.v2.language.segments import Pattern, SegmentTable
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
    count: npt.NDArray[np.float64]
    inventory: tuple[int, ...]

    def support(self, process: Process, table: SegmentTable) -> float:
        mask = process.target.mask[self.segment]
        if process.left is not None:
            mask &= process.left.mask[self.previous]
        if process.right is not None:
            mask &= process.right.mask[self.following]
        if process.stress == "stressed":
            mask &= self.stressed
        elif process.stress == "unstressed":
            mask &= ~self.stressed & table.vowel_mask[self.segment]
        return float(self.count[mask].sum())


_CONTEXTS: dict[tuple[object, ...], tuple[tuple[int, int, int, bool], ...]] = {}
_CONTEXTS_LIMIT = 1 << 17


def form_contexts(
    form: tuple[int, ...], table: SegmentTable, rule: StressRule
) -> tuple[tuple[int, int, int, bool], ...]:
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
    # Počty prostředí drží průběžný index; dorovná jen změněná slova.
    index = state.cache.get("context-index")
    if index is None:
        index = state.cache["context-index"] = (0, ContextIndex())
    contexts = cast(ContextIndex, index[1])
    contexts.sync(world, code)
    counts = contexts.counts
    keys = sorted(counts)
    stats = ContextStats(
        previous=np.array([key[0] for key in keys], dtype=np.intp),
        segment=np.array([key[1] for key in keys], dtype=np.intp),
        following=np.array([key[2] for key in keys], dtype=np.intp),
        stressed=np.array([key[3] for key in keys], dtype=bool),
        count=np.array([counts[key] for key in keys], dtype=np.float64),
        inventory=tuple(sorted({key[1] for key in keys})),
    )
    state.cache["context-stats"] = (state.version, stats)
    return stats


class _Candidates:
    """Kandidáti rodiny pro jeden inventář a jejich masky složené do matic."""

    def __init__(self, processes: list[Process], table: SegmentTable):
        self.processes = processes
        size = len(table.vowel_mask)
        everything = np.ones(size, dtype=bool)
        self.target = np.array([process.target.mask for process in processes]).reshape(-1, size)
        self.left = np.array([
            everything if process.left is None else process.left.mask for process in processes
        ]).reshape(-1, size)
        self.right = np.array([
            everything if process.right is None else process.right.mask for process in processes
        ]).reshape(-1, size)
        # Identifikátor proměnné a jen první kandidát se stejnou změnou.
        self.variable_ids = [Variable("process", process.key).id for process in processes]
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
        mask = self.target[:, stats.segment] & self.left[:, stats.previous] & self.right[:, stats.following]
        mask &= np.where(self.stressed[:, None], stats.stressed[None, :], True)
        unstressed = ~stats.stressed & table.vowel_mask[stats.segment]
        mask &= np.where(self.unstressed[:, None], unstressed[None, :], True)
        result: npt.NDArray[np.float64] = mask.astype(np.float64) @ stats.count
        return result


_CANDIDATES: dict[tuple[str, int, tuple[int, ...]], _Candidates] = {}
_CANDIDATES_LIMIT = 1 << 12


@dataclass
class _FamilyRateState:
    sites: list[str]
    rates_array: npt.NDArray[np.float64]
    total: float
    weights: npt.NDArray[np.float64] | None
    supported_map: dict[str, tuple[Process, float]] | None
    site_indices: dict[str, int]


class _CombinedSoundCandidates:
    """Sjednocení kandidátů všech rodin zvukových změn pro jeden inventář."""

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
                var_id = Variable("process", proc.key).id
                if var_id not in seen:
                    seen.add(var_id)
                    uniq.append((var_id, proc))
            uniq.sort(key=lambda item: item[0])
            start = len(all_processes)
            all_processes.extend([proc for _, proc in uniq])
            self.family_slices[change.kind] = slice(start, len(all_processes))
            self.family_candidates[change.kind] = uniq

        self.all_processes = all_processes
        size = len(table.vowel_mask)
        everything = np.ones(size, dtype=bool)
        if all_processes:
            self.target = np.array([p.target.mask for p in all_processes], dtype=bool).reshape(-1, size)
            self.left = np.array([
                everything if p.left is None else p.left.mask for p in all_processes
            ], dtype=bool).reshape(-1, size)
            self.right = np.array([
                everything if p.right is None else p.right.mask for p in all_processes
            ], dtype=bool).reshape(-1, size)
            self.stressed = np.array([p.stress == "stressed" for p in all_processes], dtype=bool)
            self.unstressed = np.array([p.stress == "unstressed" for p in all_processes], dtype=bool)
            self.has_stressed = bool(np.any(self.stressed))
            self.has_unstressed = bool(np.any(self.unstressed))
        else:
            self.target = np.zeros((0, size), dtype=bool)
            self.left = np.zeros((0, size), dtype=bool)
            self.right = np.zeros((0, size), dtype=bool)
            self.stressed = np.zeros(0, dtype=bool)
            self.unstressed = np.zeros(0, dtype=bool)
            self.has_stressed = False
            self.has_unstressed = False

    def eval_supports(
        self,
        prev: npt.NDArray[np.intp],
        seg: npt.NDArray[np.intp],
        foll: npt.NDArray[np.intp],
        str_arr: npt.NDArray[np.bool_],
        counts_int64: npt.NDArray[np.int64],
        table: SegmentTable,
    ) -> npt.NDArray[np.int64]:
        if not self.all_processes or len(counts_int64) == 0:
            return np.zeros(len(self.all_processes), dtype=np.int64)
        mask = self.target[:, seg] & self.left[:, prev] & self.right[:, foll]
        if self.has_stressed:
            mask &= np.where(self.stressed[:, None], str_arr[None, :], True)
        if self.has_unstressed:
            unstressed = ~str_arr & table.vowel_mask[seg]
            mask &= np.where(self.unstressed[:, None], unstressed[None, :], True)
        result: npt.NDArray[np.int64] = mask.astype(np.int64) @ counts_int64
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


class SoundSupportIndex:
    """Společný průběžný index opor pro všech 20 rodin zvukových změn."""

    def __init__(self) -> None:
        self.version: int = -1
        self.table_id: int | None = None
        self.inventory: tuple[int, ...] = ()
        self.context_generation: int = -1
        self.delta_cursor: int = 0
        self.supports: npt.NDArray[np.int64] = np.zeros(0, dtype=np.int64)
        self.effective_supports: npt.NDArray[np.int64] = np.zeros(0, dtype=np.int64)
        self.families: dict[str, _FamilyRateState] = {}

    def sync(self, world: World, code: Code) -> None:
        state = code.phonology
        table = world.table
        if table is None or not state.vocabulary:
            self.version = state.version
            self.table_id = id(table) if table is not None else None
            self.inventory = ()
            self.supports = np.zeros(0, dtype=np.int64)
            self.effective_supports = np.zeros(0, dtype=np.int64)
            self.families.clear()
            return

        index_holder = state.cache.get("context-index")
        if index_holder is None:
            index_holder = state.cache["context-index"] = (0, ContextIndex())
        contexts = cast(ContextIndex, index_holder[1])

        if (
            self.version == state.version
            and self.table_id == id(table)
            and len(contexts._counted) == len(state.vocabulary)
        ):
            return

        touched = contexts.sync(world, code)
        if (
            not touched
            and self.table_id == id(table)
            and self.context_generation == contexts.generation
            and self.delta_cursor == len(contexts.deltas)
            and len(self.supports) > 0
        ):
            self.version = state.version
            return

        inventory = contexts.inventory()
        if not inventory:
            self.version = state.version
            self.table_id = id(table)
            self.inventory = ()
            self.supports = np.zeros(0, dtype=np.int64)
            self.effective_supports = np.zeros(0, dtype=np.int64)
            self.families.clear()
            return

        full_rebuild = (
            self.table_id != id(table)
            or self.inventory != inventory
            or self.context_generation != contexts.generation
            or self.delta_cursor > len(contexts.deltas)
            or len(self.supports) == 0
        )
        combined = _combined_candidates(table, inventory)
        if full_rebuild:
            if not contexts.counts:
                self.supports = np.zeros(len(combined.all_processes), dtype=np.int64)
            else:
                keys = list(contexts.counts.keys())
                counts_arr = np.array([contexts.counts[k] for k in keys], dtype=np.int64)
                prev = np.array([k[0] for k in keys], dtype=np.intp)
                seg = np.array([k[1] for k in keys], dtype=np.intp)
                foll = np.array([k[2] for k in keys], dtype=np.intp)
                str_arr = np.array([k[3] for k in keys], dtype=bool)
                self.supports = combined.eval_supports(prev, seg, foll, str_arr, counts_arr, table)
            self.table_id = id(table)
            self.inventory = inventory
            self.context_generation = contexts.generation
            self.delta_cursor = len(contexts.deltas)
            self.effective_supports = np.zeros(0, dtype=np.int64)
        else:
            new_deltas = contexts.deltas[self.delta_cursor :]
            self.delta_cursor = len(contexts.deltas)
            if new_deltas:
                agg: dict[tuple[int, int, int, bool], int] = {}
                for ctx, diff in new_deltas:
                    agg[ctx] = agg.get(ctx, 0) + diff
                non_zero = [(ctx, diff) for ctx, diff in agg.items() if diff != 0]
                if non_zero:
                    diffs_arr = np.array([diff for _, diff in non_zero], dtype=np.int64)
                    prev = np.array([k[0] for k, _ in non_zero], dtype=np.intp)
                    seg = np.array([k[1] for k, _ in non_zero], dtype=np.intp)
                    foll = np.array([k[2] for k, _ in non_zero], dtype=np.intp)
                    str_arr = np.array([k[3] for k, _ in non_zero], dtype=bool)
                    delta_supps = combined.eval_supports(prev, seg, foll, str_arr, diffs_arr, table)
                    self.supports = self.supports + delta_supps

        new_effective = np.where(self.supports < 2, np.int64(0), np.minimum(np.int64(8), self.supports))
        total_prior = _total_prior()

        for ch in SOUND_CHANGES:
            kind = ch.kind
            sl = combined.family_slices[kind]
            old_eff = (
                self.effective_supports[sl]
                if len(self.effective_supports) == len(self.supports)
                else None
            )
            new_eff_slice = new_effective[sl]
            if old_eff is not None and kind in self.families and np.array_equal(new_eff_slice, old_eff):
                fam_state = self.families[kind]
                fam_state.supported_map = None
                continue

            cands = combined.family_candidates[kind]
            fam_supps = self.supports[sl]
            sites: list[str] = []
            fam_active_supps: list[float] = []
            site_indices: dict[str, int] = {}
            for i in range(len(cands)):
                s = fam_supps[i]
                if s >= MIN_SUPPORT:
                    var_id = cands[i][0]
                    site_indices[var_id] = len(sites)
                    sites.append(var_id)
                    fam_active_supps.append(float(s))

            n_sites = len(sites)
            if n_sites == 0:
                self.families[kind] = _FamilyRateState(
                    sites=[],
                    rates_array=np.zeros(0, dtype=np.float64),
                    total=0.0,
                    weights=None,
                    supported_map=None,
                    site_indices={},
                )
            else:
                scale = SOUND_INNOVATIONS_PER_GENERATION * (ch.prior / total_prior)
                rates_list = [
                    (scale * min(1.0, supp / FULL_SUPPORT)) / n_sites
                    for supp in fam_active_supps
                ]
                rates_array = np.array(rates_list, dtype=np.float64)
                total = float(np.sum(rates_array))
                weights = (rates_array / total) if total > 0.0 else None
                self.families[kind] = _FamilyRateState(
                    sites=sites,
                    rates_array=rates_array,
                    total=total,
                    weights=weights,
                    supported_map=None,
                    site_indices=site_indices,
                )

        self.effective_supports = new_effective
        self.version = state.version

    def get_supported_map(
        self, fam_state: _FamilyRateState, combined: _CombinedSoundCandidates, kind: str
    ) -> dict[str, tuple[Process, float]]:
        if fam_state.supported_map is not None:
            return fam_state.supported_map
        sl = combined.family_slices[kind]
        cands = combined.family_candidates[kind]
        fam_supps = self.supports[sl]
        found: dict[str, tuple[Process, float]] = {}
        for i in range(len(cands)):
            s = fam_supps[i]
            if s >= MIN_SUPPORT:
                found[cands[i][0]] = (cands[i][1], float(s))
        fam_state.supported_map = found
        return found


class SoundChange(Change):
    """Rodina zvukových změn. Podtřída říká jen, jaké procesy umí vyrobit."""

    target = "process"
    rate_basis = "generation"
    pressures = SOUND_PRESSURES
    base_rate = 0.0  # míra se počítá z ``prior`` a opory kandidáta

    prior: ClassVar[float]
    domain: ClassVar[Domain]

    @abstractmethod
    def candidates(self, table: SegmentTable, inventory: Sequence[int]) -> list[Process]:
        """Procesy, které rodina umí v daném inventáři vyrobit."""

    def _get_support_index(self, context: InnovationContext) -> SoundSupportIndex | None:
        if _STANDARD_SOUND_PRIORS.get(type(self)) != self.prior:
            return None
        world, code = context.world, context.code
        table = world.table
        state = code.phonology
        if table is None or not state.vocabulary:
            return None
        index_holder = state.cache.get("sound-support-index")
        if index_holder is None:
            support_idx = SoundSupportIndex()
            state.cache["sound-support-index"] = (0, support_idx)
        else:
            support_idx = cast(SoundSupportIndex, index_holder[1])
        support_idx.sync(world, code)
        return support_idx

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return ()  # svět bez hláskových tvarů (M1) nebo prázdná slovní zásoba
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            return idx.families[self.kind].sites
        self._supported_legacy(context)
        return cast(list[str], context.code.phonology.cache[("sound-sites-sorted", self.kind)][1])

    def total_rate(self, context: InnovationContext) -> float:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return 0.0
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            return idx.families[self.kind].total
        return super().total_rate(context)

    def weighted_sites(
        self, context: InnovationContext
    ) -> tuple[Sequence[str], npt.NDArray[np.float64] | None]:
        if context.world.table is None or not context.code.phonology.vocabulary:
            return (), None
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            fam = idx.families[self.kind]
            return fam.sites, fam.weights
        return super().weighted_sites(context)

    def rate(self, context: InnovationContext, site: str) -> float:
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            fam = idx.families[self.kind]
            i = fam.site_indices.get(site)
            if i is not None:
                return float(fam.rates_array[i])
            raise KeyError(site)
        supported = self._supported_legacy(context)
        share = self.prior / _total_prior()
        _, support = supported[site]
        return SOUND_INNOVATIONS_PER_GENERATION * share * min(1.0, support / FULL_SUPPORT) / len(supported)

    def rates(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            fam = idx.families[self.kind]
            if sites is fam.sites or sites == fam.sites:
                return fam.rates_array.tolist()
            return [float(fam.rates_array[fam.site_indices[s]]) for s in sites]
        supported = self._supported_legacy(context)
        scale = SOUND_INNOVATIONS_PER_GENERATION * (self.prior / _total_prior())
        return [scale * min(1.0, supported[site][1] / FULL_SUPPORT) / len(supported) for site in sites]

    def _supported(self, context: InnovationContext) -> dict[str, tuple[Process, float]]:
        idx = self._get_support_index(context)
        if idx is not None and self.kind in idx.families:
            assert context.world.table is not None
            combined = _combined_candidates(context.world.table, idx.inventory)
            return idx.get_supported_map(idx.families[self.kind], combined, self.kind)
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
                prepared = _CANDIDATES[memo_key] = _Candidates(self.candidates(table, stats.inventory), table)
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
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        process, _ = self._supported(context)[site]
        _, variant = register(
            context.world, process,
            Origin(self.kind, context.tick, context.year, context.group.id),
        )
        return variant


def _present(table: SegmentTable, inventory: Sequence[int], pattern: Pattern) -> list[int]:
    return [segment for segment in inventory if segment in pattern]


def _single(table: SegmentTable, segment: int) -> Pattern:
    return table.segments([table.ipa[segment]])


def _make(family: str, label: str, **fields: object) -> Process:
    return Process(family=family, label=label, **fields)  # type: ignore[arg-type]


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


class Syncope(SoundChange):
    """Nepřízvučný vokál mezi souhláskami zmizí."""

    kind, prior, domain = "syncope", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_C nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.CONSONANT,
                  stress="unstressed", medial=True, ease=0.15, clarity=-0.15, reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vysoké vokály → ∅ /C_C nepřízvučně",
                           target=table.pattern({"syl": "+", "hi": "+"}), operation="delete",
                           left=table.CONSONANT, right=table.CONSONANT, stress="unstressed",
                           medial=True, ease=0.15, clarity=-0.15, reductive=True))
        return found


class Apocope(SoundChange):
    """Koncový nepřízvučný vokál zmizí."""

    kind, prior, domain = "apocope", 0.5, "vowel"

    def candidates(self, table, inventory):
        found = [
            _make(self.kind, f"{table.ipa[v]} → ∅ /C_# nepřízvučně", target=_single(table, v),
                  operation="delete", left=table.CONSONANT, right=table.BOUNDARY,
                  stress="unstressed", ease=0.15, clarity=-0.15, reductive=True)
            for v in _vowels(table, inventory)
        ]
        found.append(_make(self.kind, "vokály → ∅ /C_# nepřízvučně",
                           target=table.VOWEL, operation="delete", left=table.CONSONANT,
                           right=table.BOUNDARY, stress="unstressed", ease=0.15, clarity=-0.15,
                           reductive=True))
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


SOUND_CHANGES: tuple[SoundChange, ...] = (
    Voicing(), Spirantization(), Debuccalization(), IntervocalicLoss(), Fortition(),
    Palatalization(), NasalAssimilation(), VoicingAssimilation(), FinalDevoicing(), CodaLoss(),
    ClusterSimplification(), VowelReduction(), Syncope(), Apocope(), VowelShift(),
    Diphthongization(), Monophthongization(), GlideFormation(), Epenthesis(), Prothesis(),
)

_STANDARD_SOUND_PRIORS: dict[type[SoundChange], float] = {
    type(change): change.prior for change in SOUND_CHANGES
}
_TOTAL_PRIOR: float = sum(change.prior for change in SOUND_CHANGES)


def _total_prior() -> float:
    return _TOTAL_PRIOR

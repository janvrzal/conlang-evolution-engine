"""Pozorování: vzdálenosti kódů, dialekty, jazyky a jejich linie (iterace 4).

Jazyky ani strom jazyků nejsou vstupem simulace. Počítají se zde ze
skutečného stavu repertoárů.

**Jádro v Rustu.** Je-li k dispozici rozšíření ``cee_core`` (viz :mod:`cee.v2.native`),
počítá celé pozorování jedno volání ``observe_step`` (``rust/cee_core/src/observe.rs``):
rysy skupin (vložení podílů, čtverce, kategorie tvarů příbuzných slov a editační
vzdálenosti tvarů), kandidáty sloučení, obě průměrné vazby a na přání matici vzdáleností
kódů. Python skládá jen vstup z polí (:func:`_gather`: pohledy na bloky živých fondů,
dominantní kořeny a tvary skupin jako CSR, polohy a vazby) a zapisuje výsledek.
Bez rozšíření, s ``CEE_NATIVE=0`` nebo bez bitové shody knihovny (``native.observe_matches``)
počítá totéž Python nad týmiž poli; výsledky jsou bit po bitu stejné.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.language.segments import SegmentTable
from cee.v2.rng import stable_id, stable_int
from cee.v2.world import World

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]


#: Blok fondů pro pozorování: podíly ``(řádky, skupiny, sloty)``, kdo proměnnou má
#: ``(řádky, skupiny)``, vybrané řádky (podle druhu proměnné) a pořadí proměnných při
#: výběru vzorku (nižší číslo je dřív).
Pool = tuple[FloatArray, npt.NDArray[np.bool_], IntArray, IntArray]

#: Klíč výběru vzorku proměnných (stabilní hash jména): jméno se hašuje jednou za běh.
_SAMPLING_KEYS: dict[str, int] = {}


def _ranks(names: Sequence[str]) -> IntArray:
    """Pořadí proměnných při výběru vzorku sloupců: podle stabilního hashe, při shodě podle jména."""
    keys = np.empty(len(names), dtype=np.uint64)
    for position, name in enumerate(names):
        key = _SAMPLING_KEYS.get(name)
        if key is None:
            key = _SAMPLING_KEYS[name] = stable_int("observe", name)
        keys[position] = key
    order = np.argsort(keys, kind="stable")
    if len(order) > 1 and (keys[order][1:] == keys[order][:-1]).any():
        order = np.array(sorted(range(len(names)), key=lambda at: (int(keys[at]), names[at])), dtype=np.int64)
    ranks = np.empty(len(names), dtype=np.int64)
    ranks[order] = np.arange(len(names), dtype=np.int64)
    return ranks


def _pools(world: World, kinds: Sequence[str], ranked: bool = True) -> list[Pool]:
    """Bloky živých fondů s řádky proměnných daných druhů; hustý pohled se nekopíruje."""
    chosen = []
    names: list[str] = []
    for pool in world.live.iter_blocks():
        rows = [row for row, variable_id in enumerate(pool.variable_ids)
                if world.variables[variable_id].kind in kinds]
        if rows:
            chosen.append((pool, rows))
            if ranked:
                names += [pool.variable_ids[row] for row in rows]
    ranks = _ranks(names) if ranked else np.zeros(sum(len(rows) for _, rows in chosen), dtype=np.int64)
    result: list[Pool] = []
    start = 0
    for pool, rows in chosen:
        result.append((
            np.ascontiguousarray(pool.freqs), np.ascontiguousarray(pool.present),
            np.asarray(rows, dtype=np.int64), ranks[start : start + len(rows)],
        ))
        start += len(rows)
    return result


def _distance_totals(pools: Sequence[Pool], live: int, chunk: int = 4_000_000) -> FloatArray:
    """Součet variačních vzdáleností kódů přes vybrané proměnné (bez dělení jejich počtem).

    Pro jednu proměnnou je vzdálenost ½ Σ |p − q|: 0 pro shodné rozdělení, 1 pro zcela odlišné
    varianty. Výpočet běží po blocích proměnných, aby paměť nerostla se čtvercem počtu skupin
    krát počet proměnných. Součet ``float32`` přes řádky a sloty je ``np.sum(axis=(0, 3))``:
    po řádcích párový součet přes sloty; ``float64`` se sčítá až mezi bloky.
    """
    total = np.zeros((live, live))
    for freqs, present, rows, _ in pools:
        capacity = freqs.shape[2]
        # float32 stačí: vzdálenost slouží ke shlukování, ne k dalšímu výpočtu.
        values = np.where(present[rows, :, None], freqs[rows], 0.0).astype(np.float32)
        step = max(1, chunk // max(1, live * live * capacity))
        for start in range(0, len(rows), step):
            part = values[start : start + step]
            total += 0.5 * np.abs(part[:, :, None, :] - part[:, None, :, :]).sum(axis=(0, 3))
    return total


def distance_matrix(
    world: World, chunk: int = 4_000_000, kinds: Sequence[str] = ("lexical",)
) -> FloatArray:
    """Průměrná variační vzdálenost hlavních kódů přes všechny proměnné.

    Pro jednu proměnnou je vzdálenost ½ Σ |p − q|: 0 pro shodné rozdělení,
    1 pro zcela odlišné varianty. Proměnné, které jsou všude stejné, by
    přispěly nulou, proto se počítá jen nad živými proměnnými. Průměr se bere
    přes všechny lexikální proměnné, aby vzdálenost nezávisela na tom, kolik
    jich je zrovna živých. Zvukové procesy se nezapočítávají: mrtvé inovace
    by vzdálenost ředily a jejich výsledek zachycuje srovnání tvarů
    (:func:`cognate_matrix`). Výpočet běží po blocích proměnných, aby
    paměť nerostla se čtvercem počtu skupin krát počet proměnných.
    """
    live = len(world.live.group_ids)
    lexical = sum(variable.kind == "lexical" for variable in world.variables.values())
    result: FloatArray = _distance_totals(_pools(world, kinds, ranked=False), live, chunk) / max(1, lexical)
    return result


#: Kolik váží rozdíl tvaru příbuzného slova proti rozdílu slova samého.
FORM_WEIGHT = 1.0
#: Záměna hlásky stojí podíl odlišných rysů, nejvýš 1; odlišných rysů je u
#: běžných záměn (znělost, místo) jen pár, proto se dělí tímto počtem.
FEATURE_SCALE = 6.0


def segment_cost(world: World, first: int, second: int) -> float:
    """Cena záměny dvou hlásek podle počtu odlišných rysů (PanPhon)."""
    if first == second:
        return 0.0
    assert world.table is not None
    return _segment_cost_cached(world.table, first, second, FEATURE_SCALE)


@lru_cache(maxsize=65536)
def _segment_cost_cached(table: SegmentTable, first: int, second: int, scale: float) -> float:
    # A strong table reference in the key avoids accidental reuse of object IDs.
    vectors = table.vectors
    return min(1.0, float((vectors[first] != vectors[second]).sum()) / scale)


_DISTANCES: dict[tuple[tuple[int, ...], tuple[int, ...], int], float] = {}
_DISTANCES_LIMIT = 1 << 19


def form_distance(world: World, first: tuple[int, ...], second: tuple[int, ...]) -> float:
    """Normalizovaná editační vzdálenost dvou tvarů (0 shodné, 1 zcela jiné).

    Dvojice tvarů se mezi pozorováními skoro nemění, proto se pamatuje.
    """
    if first == second:
        return 0.0
    if not first or not second:
        return 1.0
    key = (first, second, id(world.table))
    found = _DISTANCES.get(key)
    if found is None:
        if len(_DISTANCES) >= _DISTANCES_LIMIT:
            _DISTANCES.clear()
        found = _DISTANCES[key] = _edit_distance(world, first, second)
    return found


def _edit_distance(world: World, first: tuple[int, ...], second: tuple[int, ...]) -> float:
    previous = [float(index) for index in range(len(second) + 1)]
    for row, a in enumerate(first, 1):
        current = [float(row)]
        for column, b in enumerate(second, 1):
            current.append(min(
                previous[column] + 1.0, current[column - 1] + 1.0,
                previous[column - 1] + segment_cost(world, a, b),
            ))
        previous = current
    return min(1.0, previous[-1] / max(len(first), len(second)))


def cognate_matrix(world: World, group_ids: Sequence[str]) -> FloatArray:
    """Součet rozdílů tvarů příbuzných slov přes pojmy (jen převládající slova).

    Pojem, pro který mají dvě skupiny stejné převládající slovo (tentýž
    morfém), přispěje vzdáleností jejich dnešních tvarů. Rozdíl slova samého
    počítá :func:`distance_matrix`. Tvary se porovnávají jen mezi různými
    podobami téhož slova, kterých je v jednom pojmu málo.
    """
    total = np.zeros((len(group_ids), len(group_ids)))
    if world.table is None:
        return total
    codes = [world.groups[group_id].main_code for group_id in group_ids]
    concepts = sorted({concept for code in codes for concept in code.phonology.dominant})
    cache: dict[tuple[tuple[int, ...], tuple[int, ...]], float] = {}
    for concept in concepts:
        by_root: dict[str, dict[tuple[int, ...], list[int]]] = {}
        for index, code in enumerate(codes):
            root = code.phonology.dominant.get(concept)
            if root is not None:
                by_root.setdefault(root, {}).setdefault(world.form_of(code, root), []).append(index)
        for shapes in by_root.values():
            forms = sorted(shapes)
            for position, first in enumerate(forms):
                for second in forms[position + 1 :]:
                    key = (first, second)
                    if key not in cache:
                        cache[key] = form_distance(world, first, second)
                    a, b = np.array(shapes[first]), np.array(shapes[second])
                    total[np.ix_(a, b)] += cache[key]
                    total[np.ix_(b, a)] += cache[key]
    return total


def code_distances(world: World) -> FloatArray:
    """Vzdálenost kódů pro pozorování: slova, tvary příbuzných slov, konstrukce.

    Vše se dělí počtem lexikálních proměnných, takže svět bez hláskových
    tvarů (M1) má stejnou vzdálenost jako :func:`distance_matrix`.
    """
    lexical = sum(variable.kind == "lexical" for variable in world.variables.values())
    live = len(world.live.group_ids)
    if native.observe_enabled():
        inp = _gather(world, np.arange(live, dtype=np.int64), lexical=lexical, ranked=False)
        module = native.kernel("observe_distance_totals")
        assert module is not None
        distances: FloatArray = module(_native_pools(inp), live, 4_000_000, native.threads()) / max(1, lexical)
        if inp.forms is not None:
            cognate = native.kernel("observe_cognate_totals")
            assert cognate is not None
            distances = distances + FORM_WEIGHT * cognate(live, _native_forms(inp.forms)) / max(1, lexical)
        return distances
    distances = distance_matrix(world, kinds=("lexical", "construction"))
    if world.table is not None:
        distances = distances + FORM_WEIGHT * cognate_matrix(world, world.live.group_ids) / max(1, lexical)
    return distances


@dataclass(frozen=True)
class Snapshot:
    tick: int
    year: float
    group_ids: tuple[str, ...]
    #: Matice vzdáleností mluvených skupin (``code_distances``); jen s
    #: ``keep_distances``, protože roste se čtvercem počtu skupin.
    distances: FloatArray | None
    dialects: tuple[tuple[str, ...], ...]
    #: ID linie jazyka → skupiny, které ho právě mluví.
    languages: dict[str, tuple[str, ...]]


class LineageTracker:
    """Páruje shluky jazyků mezi snímky a zapisuje jejich rozštěpení.

    Nový shluk zdědí linii toho předchozího, s nímž sdílí nejvíc skupin. Když
    z jedné linie vzejde víc shluků, největší pokračuje a ostatní jsou nové
    linie odštěpené od ní. Z těchto záznamů vzniká emergentní strom jazyků.
    """

    def __init__(self) -> None:
        self.lineages: dict[str, frozenset[str]] = {}

    def update(
        self, clusters: Sequence[Sequence[str]], tick: int
    ) -> tuple[dict[str, tuple[str, ...]], list[dict[str, object]]]:
        events: list[dict[str, object]] = []
        claims: dict[str | None, list[frozenset[str]]] = {}
        for cluster in clusters:
            members = frozenset(cluster)
            overlaps = sorted(
                ((len(members & previous), lineage) for lineage, previous in self.lineages.items()),
                key=lambda item: (-item[0], item[1]),
            )
            parent = overlaps[0][1] if overlaps and overlaps[0][0] > 0 else None
            claims.setdefault(parent, []).append(members)

        assigned: dict[str, frozenset[str]] = {}
        for parent in sorted(claims, key=lambda item: (item is None, item or "")):
            successors = sorted(
                claims[parent],
                key=lambda members: (
                    -len(members & self.lineages.get(parent or "", frozenset())),
                    -len(members),
                    min(members),
                ),
            )
            for position, members in enumerate(successors):
                if parent is not None and position == 0:
                    assigned[parent] = members
                    continue
                lineage = stable_id("lineage", parent, tick, min(members))
                assigned[lineage] = members
                events.append(
                    {"kind": "language_split" if parent else "language_emerged",
                     "lineage": lineage, "parent": parent, "groups": sorted(members)}
                )
        for lineage in sorted(set(self.lineages) - set(assigned)):
            events.append({"kind": "language_ended", "lineage": lineage})
        self.lineages = assigned
        return {lineage: tuple(sorted(members)) for lineage, members in sorted(assigned.items())}, events


#: Hystereze rozpoznání jazyků jako podíl prahu: dvojice, která byla jedním
#: jazykem, se rozdělí až nad prahem + rezerva, oddělená se spojí až pod
#: prahem − rezerva. Bez ní strom kmitá, když se vzdálenost drží u prahu.
HYSTERESIS = 0.1


def observe(
    world: World,
    tick: int,
    year: float,
    tracker: LineageTracker,
    *,
    dialect_threshold: float,
    language_threshold: float,
    keep_distances: bool = False,
) -> tuple[Snapshot, list[dict[str, object]]]:
    """Dialekty a jazyky ze stavu světa (průměrná vazba mezi sousedícími shluky).

    Čas i paměť rostou s počtem skupin lineárně (:func:`constrained_average_linkage`).
    S ``keep_distances`` uloží snímek i celou matici vzdáleností (čtvercová,
    pro metriky a testy kontinua).
    """
    # Do dialektů a jazyků se počítá jen řeč z domova: psaný kód nemá
    # mluvčí a kód trhu, úřadu nebo školy (veřejná doména) je druhý jazyk.
    spoken = [index for index, group_id in enumerate(world.live.group_ids)
              if not world.groups[group_id].written and world.groups[group_id].domain == "home"]
    group_ids = [world.live.group_ids[index] for index in spoken]
    member_of = {group: lineage for lineage, members in tracker.lineages.items() for group in members}
    codes = {lineage: number for number, lineage in enumerate(sorted(tracker.lineages))}
    labels = np.array([codes[member_of[group_id]] if group_id in member_of else -1 for group_id in group_ids],
                      dtype=np.int64)
    margin = HYSTERESIS * language_threshold
    inp = _gather(world, np.array(spoken, dtype=np.int64))
    distances = None
    if native.observe_enabled():
        step = native.kernel("observe_step")
        assert step is not None
        links, places = _geometry(world, group_ids)
        dialect_clusters, language_clusters, distances, _ = step(
            _native_pools(inp), inp.live, inp.columns, None if inp.forms is None else _native_forms(inp.forms),
            inp.lexical, links, places, labels, (dialect_threshold, language_threshold, margin),
            keep_distances, native.threads(), False,
        )
    else:
        if keep_distances:
            distances = code_distances(world)
            if len(spoken) != len(world.live.group_ids):
                distances = distances[np.ix_(spoken, spoken)]
        features = _features(inp)
        pairs = _candidates(*_geometry(world, group_ids))
        dialect_clusters = constrained_average_linkage(features, pairs, dialect_threshold)
        language_clusters = constrained_average_linkage(
            features, pairs, language_threshold, labels=labels, margin=margin,
        )
    dialects = tuple(tuple(group_ids[index] for index in cluster) for cluster in dialect_clusters)
    languages, events = tracker.update([[group_ids[index] for index in cluster] for cluster in language_clusters], tick)
    return (
        Snapshot(tick, year, tuple(group_ids), distances, dialects, languages),
        events,
    )


# --- vstup pozorování z polí --------------------------------------------------
#
# Obě cesty (Rust i Python) čtou tatáž pole: pohledy na bloky živých fondů, dominantní
# kořeny a tvary skupin jako CSR (pojem, kořen a číslo tvaru v tabulce různých tvarů), polohy
# a vazby skupin jako čísla. Tvary patří bance světa; do banky se při pozorování nic
# nezařazuje (výchozí tvary morfémů, které v ní ještě nejsou, se předají podle obsahu).


@dataclass
class _Forms:
    """Dominantní kořeny a tvary všech živých skupin (pořadí pojmů je pořadí vložení do slovníku)."""

    ptr: IntArray             # (živé skupiny + 1)
    concept: npt.NDArray[np.int32]
    root: npt.NDArray[np.int32]
    form: npt.NDArray[np.int32]  # číslo do tabulky různých tvarů
    form_ptr: IntArray        # (tvary + 1)
    form_flat: npt.NDArray[np.int32]
    ranks: npt.NDArray[np.int32]  # pořadí pojmů podle názvu
    vectors: npt.NDArray[np.int8]

    def form_of(self, form: int) -> tuple[int, ...]:
        return tuple(self.form_flat[self.form_ptr[form] : self.form_ptr[form + 1]].tolist())


@dataclass
class _Input:
    world: World
    #: Počet živých skupin a čísla mluvených skupin mezi nimi.
    live: int
    columns: IntArray
    pools: list[Pool]
    forms: _Forms | None
    #: Počet lexikálních proměnných světa.
    lexical: int


def _view(buffer: Any, dtype: Any) -> npt.NDArray[Any]:
    """Pohled na pole ``array.array`` bez kopie (prázdné pole nelze mapovat)."""
    return np.frombuffer(buffer, dtype=dtype) if len(buffer) else np.zeros(0, dtype=dtype)


def _forms_input(world: World) -> _Forms | None:
    """Dominantní kořeny a tvary živých skupin jako pole; ``None`` ve světě bez tabulky hlásek."""
    if world.table is None:
        return None
    bank = world.form_bank()
    names = world.registry.morphemes.names
    defaults = _view(world.columns.morphemes.form, np.int32)  # type: ignore[attr-defined]
    bank_size = len(bank.forms)
    local: dict[tuple[int, ...], int] = {}

    def by_content(content: tuple[int, ...]) -> int:
        found = bank._ids.get(content)
        return found if found is not None else bank_size + local.setdefault(content, len(local))

    ptr, concepts, roots, forms = [0], [], [], []
    for group_id in world.live.group_ids:
        code = world.groups[group_id].main_code
        dominant = code.phonology.dominant
        count = len(dominant.order)
        if count:
            concept = np.fromiter(dominant.order, dtype=np.int32, count=count)
            root = _view(dominant.roots, np.int32)[concept]
            store = code.forms
            if store.context is world:
                stored = _view(store.raw()[0], np.int32)
                form = np.full(count, -1, dtype=np.int64)
                inside = root < len(stored)
                form[inside] = stored[root[inside]]
                # Výchozí tvar: číslo v bance, nebo (ještě nezařazený) záporné číslo podle kořene.
                missing = form < 0
                inside = missing & (root < len(defaults))
                form[inside] = defaults[root[inside]]
                form[form < 0] = -(root[form < 0].astype(np.int64) + 1)
            else:
                form = np.array([by_content(world.form_of(code, names[number])) for number in root.tolist()],
                                dtype=np.int64)
            concepts.append(concept)
            roots.append(root)
            forms.append(form)
        ptr.append(ptr[-1] + count)
    concept = np.concatenate(concepts) if concepts else np.zeros(0, dtype=np.int32)
    root = np.concatenate(roots) if roots else np.zeros(0, dtype=np.int32)
    form = np.concatenate(forms) if forms else np.zeros(0, dtype=np.int64)
    unresolved = form < 0
    if unresolved.any():
        pending = np.unique(-form[unresolved] - 1)
        found = np.array([by_content(world.morphemes[names[number]].form) for number in pending.tolist()],
                         dtype=np.int64)
        form[unresolved] = found[np.searchsorted(pending, -form[unresolved] - 1)]
    distinct, inverse = np.unique(form, return_inverse=True)
    banked = distinct[distinct < bank_size]
    lengths = bank._lengths[banked]
    starts = bank._starts[banked]
    offsets = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)
    gathered = np.repeat(starts - offsets[:-1], lengths) + np.arange(int(offsets[-1]), dtype=np.int64)
    flat = bank._segments()[gathered].astype(np.int32)
    extra = [content for content, _ in sorted(local.items(), key=lambda item: item[1])]
    extra = [extra[int(number) - bank_size] for number in distinct[distinct >= bank_size]]
    if extra:
        lengths = np.concatenate([lengths, [len(content) for content in extra]]).astype(np.int64)
        offsets = np.concatenate([[0], np.cumsum(lengths)]).astype(np.int64)
        flat = np.concatenate([flat, np.array([hlaska for content in extra for hlaska in content], dtype=np.int32)])
    return _Forms(
        np.asarray(ptr, dtype=np.int64), concept, root, inverse.reshape(-1).astype(np.int32), offsets, flat,
        world.registry.concepts.ranks(), np.ascontiguousarray(world.table.vectors),
    )


def _gather(world: World, columns: IntArray, *, lexical: int | None = None, ranked: bool = True) -> _Input:
    """Vstup pozorování pro mluvené skupiny ``columns`` (čísla mezi živými skupinami)."""
    if lexical is None:
        lexical = sum(variable.kind == "lexical" for variable in world.variables.values())
    return _Input(
        world, len(world.live.group_ids), columns, _pools(world, ("lexical", "construction"), ranked),
        _forms_input(world), lexical,
    )


def _geometry(
    world: World, group_ids: Sequence[str]
) -> tuple[tuple[IntArray, IntArray], tuple[IntArray, FloatArray, FloatArray]]:
    """Vazby mezi skupinami (dvojice pozic) a polohy skupin, které ji mají (pozice, x, y)."""
    numbers = world.registry.groups.numbers
    where = np.full(len(world.registry.groups.names), -1, dtype=np.int64)
    where[np.array([numbers[group_id] for group_id in group_ids], dtype=np.int64)] = np.arange(len(group_ids))
    table = world.link_table()
    source, target = where[table.source], where[table.indices]
    keep = (source >= 0) & (target >= 0) & (source != target)
    slots: list[int] = []
    xs: list[float] = []
    ys: list[float] = []
    for position, group_id in enumerate(group_ids):
        xy = world.position_of(group_id)
        if xy is not None:
            slots.append(position)
            xs.append(float(xy[0]))
            ys.append(float(xy[1]))
    return (
        (np.ascontiguousarray(source[keep]), np.ascontiguousarray(target[keep])),
        (np.array(slots, dtype=np.int64), np.array(xs, dtype=np.float64), np.array(ys, dtype=np.float64)),
    )


def _native_pools(inp: _Input) -> list[tuple[Any, ...]]:
    return [tuple(pool) for pool in inp.pools]


def _native_forms(forms: _Forms) -> tuple[Any, ...]:
    """Tvary skupin pro Rust (viz ``FormsIn`` v ``observe_python.rs``)."""
    return (
        forms.ptr, forms.concept, forms.root, forms.form, forms.form_ptr, forms.form_flat, forms.ranks,
        forms.vectors, FEATURE_SCALE,
    )


# --- pozorování bez matice všech dvojic (Python reference) ---------------------
#
# Vzdálenost dvou skupin je táž jako v ``code_distances``: rozdíl rozdělení
# variant (½ Σ |p − q| přes živé proměnné slov a konstrukcí) plus rozdíl
# tvarů příbuzných slov, děleno počtem lexikálních proměnných. Rozdíl
# rozdělení se počítá jako ½‖φ(p) − φ(q)‖² ve vložení ``_embedded`` (přesné až
# na chybu uvnitř jednoho intervalu ``EDGES``, v průměru asi −5 %). Díky tomu
# jde průměrná vzdálenost mezi dvěma shluky spočítat přesně ze součtů za
# shluk (počet, součet vložení, součet čtverců, četnosti tvarů), bez
# procházení dvojic členů. Shlukují se jen
# shluky, které spolu sousedí (vazbou nebo zeměpisně); průměr se ale bere
# přes všechny jejich členy, takže dlouhé kontinuum se rozpadne podle
# nahromaděného rozdílu jako dosud. Čas i paměť rostou s počtem skupin
# lineárně (krát počet živých proměnných), ne se čtvercem.

#: Kolik zeměpisně nejbližších skupin je kandidátem na sloučení (vedle vazeb).
NEAREST = 4


@dataclass
class _Features:
    shares: FloatArray            # (skupiny, kategorie variant)
    squares: FloatArray           # Σ‖p‖² za skupinu
    forms: list[dict[int, float]]  # skupina → {kategorie tvaru: 1}
    spread: list[dict[int, float]]  # skupina → {kategorie tvaru: Σ vzdálenost k tvarům téhož kořene}
    lexical: int


def _features(inp: _Input) -> _Features:
    """Rysy mluvených skupin ``inp.columns`` (Python reference téhož, co počítá Rust)."""
    columns = inp.columns
    parts, owners = [], []
    ranks: list[int] = []
    for freqs, present, rows, row_ranks in inp.pools:
        freq = np.where(present[np.ix_(rows, columns)][:, :, None], freqs[rows][:, columns], 0.0)
        parts.append(np.transpose(freq, (1, 0, 2)).reshape(len(columns), -1))
        owners += [len(ranks) + index for index in range(len(rows)) for _ in range(freqs.shape[2])]
        ranks += row_ranks.tolist()
    shares = np.concatenate(parts, axis=1) if parts else np.zeros((len(columns), 0))
    scale = 1.0
    if len(shares):
        # Sloupec, který mají všechny skupiny stejný, k žádné vzdálenosti nepřispívá.
        varying = (shares != shares[:1]).any(axis=0)
        total = int(varying.sum())
        if total > SAMPLED:
            # Nestranný odhad z pevného výběru proměnných (stabilní hash), aby
            # paměť rostla jen s počtem skupin: proměnné se berou v pořadí hashe,
            # dokud se nevyčerpá rozpočet sloupců.
            width: dict[int, int] = {}
            for column in np.flatnonzero(varying):
                width[owners[column]] = width.get(owners[column], 0) + 1
            kept, used = set(), 0
            for owner in sorted(width, key=ranks.__getitem__):
                if used + width[owner] > SAMPLED:
                    break
                kept.add(owner)
                used += width[owner]
            varying &= np.array([owner in kept for owner in owners])
            scale = total / max(1, used)
        shares = _embedded(shares[:, varying], np.sqrt(scale))
    forms: list[dict[int, float]] = [{} for _ in columns]
    spread: list[dict[int, float]] = [{} for _ in columns]
    if inp.forms is not None:
        forms, spread = _categories(inp.world, inp.forms, columns)
    squares = (shares.astype(np.float64) ** 2).sum(axis=1)
    return _Features(shares, squares, forms, spread, max(1, inp.lexical))


def _categories(
    world: World, source: _Forms, columns: IntArray
) -> tuple[list[dict[int, float]], list[dict[int, float]]]:
    """Kategorie tvarů dominantních kořenů skupin a vzdálenosti mezi tvary téhož kořene pojmu."""
    contents: dict[int, tuple[int, ...]] = {}

    def content(form: int) -> tuple[int, ...]:
        found = contents.get(form)
        if found is None:
            found = contents[form] = source.form_of(form)
        return found

    categories: dict[tuple[int, int, int], int] = {}
    members: dict[tuple[int, int], list[int]] = {}
    chosen: list[list[tuple[int, int, int]]] = [[] for _ in columns]
    ptr = source.ptr
    for index, group in enumerate(columns.tolist()):
        begin, end = int(ptr[group]), int(ptr[group + 1])
        entries = zip(source.concept[begin:end].tolist(), source.root[begin:end].tolist(),
                      source.form[begin:end].tolist())
        for key in entries:
            if key not in categories:
                categories[key] = len(categories)
                members.setdefault((key[0], key[1]), []).append(key[2])
            chosen[index].append(key)
    forms: list[dict[int, float]] = [{} for _ in columns]
    spread: list[dict[int, float]] = [{} for _ in columns]
    for index, keys in enumerate(chosen):
        for key in keys:
            forms[index][categories[key]] = 1.0
            for other in members[(key[0], key[1])]:
                if other != key[2]:
                    spread[index][categories[(key[0], key[1], other)]] = form_distance(
                        world, content(key[2]), content(other)
                    )
    return forms, spread


#: Hranice intervalů vložení podílů: jemné u 0 a u 1, kde žijí menšinové
#: varianty (malé rozdíly rozhodují o dialektech), hrubé uprostřed.
EDGES = (0.0, 1e-3, 0.01, 0.03, 0.08, 0.2, 0.4, 0.6, 0.8, 0.92, 0.97, 0.99, 0.999, 1.0)
#: Nejvýš tolik proměnlivých sloupců (proměnná × slot) vstupuje do shlukování;
#: víc se odhadne výběrem proměnných. Paměť je pak asi 100 kB na skupinu.
SAMPLED = 2000


def _embedded(shares: FloatArray, factor: float = 1.0) -> FloatArray:
    """Vložení podílů, ve kterém ½‖φ(p) − φ(q)‖² ≈ ½ Σ |p − q| (rozdíl rozdělení).

    |x − y| na [0, 1] je ∫ (1[t < x] − 1[t < y])² dt; prahy ``EDGES`` ho
    aproximují po částech: φⱼ(x) = clip((x − tⱼ) / Δⱼ, 0, 1) · √Δⱼ. Mimo jeden
    interval je výsledek přesný, uvnitř je chyba menší než šířka intervalu.
    """
    edges = np.asarray(EDGES, dtype=np.float32)
    starts, widths = edges[:-1], np.diff(edges)
    roots = np.sqrt(widths) * np.float32(factor)
    rows, columns = shares.shape
    result = np.empty((rows, columns * len(widths)), dtype=np.float32)
    step = max(1, (1 << 22) // max(1, columns * len(widths)))
    for start in range(0, rows, step):
        part = shares[start:start + step].astype(np.float32)[:, :, None]
        result[start:start + step] = (np.clip((part - starts) / widths, 0.0, 1.0) * roots).reshape(len(part), -1)
    return result


def _candidates(
    links: tuple[IntArray, IntArray], places: tuple[IntArray, FloatArray, FloatArray]
) -> list[tuple[int, int]]:
    """Dvojice, které se smějí přímo sloučit: vazby a nejbližší sousedé na mapě."""
    pairs = set()
    for first, second in zip(links[0].tolist(), links[1].tolist()):
        if first != second:
            pairs.add((min(first, second), max(first, second)))
    slots, xs, ys = places
    if len(slots) > 1:
        extent = max(float(xs.max() - xs.min()), float(ys.max() - ys.min()), 1e-9)
        size = extent / max(1.0, np.sqrt(len(slots) / 2.0))
        cells: dict[tuple[int, int], list[int]] = {}
        for slot, (x, y) in enumerate(zip(xs, ys)):
            cells.setdefault((int(x // size), int(y // size)), []).append(slot)
        reach = int(np.ceil(extent / size)) + 1
        for slot, (x, y) in enumerate(zip(xs, ys)):
            home = (int(x // size), int(y // size))
            found: list[tuple[float, int]] = []
            for radius in range(reach + 1):
                ring = [(home[0] + dx, home[1] + dy) for dx in range(-radius, radius + 1)
                        for dy in range(-radius, radius + 1) if max(abs(dx), abs(dy)) == radius]
                for cell in ring:
                    for other in cells.get(cell, ()):
                        if other != slot:
                            found.append((float(np.hypot(xs[other] - x, ys[other] - y)), other))
                # Kruh o poloměru r pokrývá jistě vše do vzdálenosti (r − 1) · size.
                if len(found) >= NEAREST and sorted(found)[NEAREST - 1][0] <= (radius) * size:
                    break
            for _, other in sorted(found)[:NEAREST]:
                first, second = int(slots[slot]), int(slots[other])
                pairs.add((min(first, second), max(first, second)))
    return sorted(pairs)


def constrained_average_linkage(
    features: _Features, pairs: Sequence[tuple[int, int]], threshold: float, *,
    labels: Sequence[int] | IntArray | None = None, margin: float = 0.0,
) -> list[list[int]]:
    """Průměrná vazba mezi sousedícími shluky až do prahu (lineární v počtu skupin).

    ``pairs`` jsou kandidáti sloučení (:func:`_candidates`). S ``labels`` (číslo dosavadní linie
    skupin, −1 žádná) a ``margin`` hystereze: dvojice téže linie je o ``margin`` blíž, dvojice
    dvou různých známých linií dál.
    """
    count = len(features.squares)
    clusters = [[index] for index in range(count)]
    if count < 2:
        return clusters
    size = np.ones(count)
    shares = features.shares.copy()
    squares = features.squares.copy()
    forms = [dict(item) for item in features.forms]
    spread = [dict(item) for item in features.spread]
    label_counts: list[dict[str, float]] = [
        {} if labels is None or labels[index] < 0 else {str(labels[index]): 1.0} for index in range(count)
    ]
    neighbours: list[set[int]] = [set() for _ in range(count)]
    for first, second in pairs:
        neighbours[first].add(second)
        neighbours[second].add(first)

    def linkage(a: int, b: int) -> float:
        na, nb = size[a], size[b]
        value = 0.5 * (squares[a] / na + squares[b] / nb) - float(shares[a] @ shares[b]) / (na * nb)
        small, large = (spread[a], forms[b]) if len(spread[a]) <= len(forms[b]) else (forms[b], spread[a])
        value += FORM_WEIGHT * sum(weight * large.get(column, 0.0) for column, weight in small.items()) / (na * nb)
        value /= features.lexical
        if margin:
            same = sum(weight * label_counts[b].get(label, 0.0) for label, weight in label_counts[a].items())
            known = sum(label_counts[a].values()) * sum(label_counts[b].values())
            value += margin * (known - 2.0 * same) / (na * nb)
        return max(0.0, value)

    import heapq

    version = [0] * count
    heap = [(linkage(a, b), a, b, 0, 0) for a in range(count) for b in neighbours[a] if a < b]
    heapq.heapify(heap)
    alive = [True] * count
    while heap:
        value, a, b, va, vb = heapq.heappop(heap)
        if not (alive[a] and alive[b]) or version[a] != va or version[b] != vb:
            continue
        if value > threshold:
            break
        keep, drop = (a, b) if a < b else (b, a)
        size[keep] += size[drop]
        shares[keep] += shares[drop]
        squares[keep] += squares[drop]
        for target, source in ((forms, forms), (spread, spread), (label_counts, label_counts)):
            merged = target[keep]
            for column, weight in source[drop].items():
                merged[column] = merged.get(column, 0.0) + weight
        clusters[keep].extend(clusters[drop])
        clusters[drop] = []
        alive[drop] = False
        version[keep] += 1
        neighbours[keep] = (neighbours[keep] | neighbours[drop]) - {keep, drop}
        for other in neighbours[drop]:
            neighbours[other].discard(drop)
            if other != keep:
                neighbours[other].add(keep)
        neighbours[drop] = set()
        for other in sorted(neighbours[keep]):
            first, second = (keep, other) if keep < other else (other, keep)
            heapq.heappush(heap, (linkage(first, second), first, second, version[first], version[second]))
    return sorted((sorted(cluster) for cluster in clusters if cluster), key=lambda c: c[0])

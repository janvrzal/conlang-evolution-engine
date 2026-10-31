"""Pozorování: vzdálenosti kódů, dialekty, jazyky a jejich linie (iterace 4).

Jazyky ani strom jazyků nejsou vstupem simulace. Počítají se zde ze
skutečného stavu repertoárů.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.language.segments import SegmentTable
from cee.v2.rng import stable_id, stable_int
from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]


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
    live = world.live
    count = len(live.group_ids)
    total = np.zeros((count, count))
    lexical = [variable_id for variable_id, variable in world.variables.items()
               if variable.kind == "lexical"]
    for pool in live.iter_blocks():
        rows = [row for row, variable_id in enumerate(pool.variable_ids)
                if world.variables[variable_id].kind in kinds]
        if not rows:
            continue
        # float32 stačí: vzdálenost slouží ke shlukování, ne k dalšímu výpočtu.
        freqs = np.where(pool.present[rows, :, None], pool.freqs[rows], 0.0).astype(np.float32)
        step = max(1, chunk // max(1, count * count * pool.capacity))
        for start in range(0, len(rows), step):
            part = freqs[start : start + step]
            total += 0.5 * np.abs(part[:, :, None, :] - part[:, None, :, :]).sum(axis=(0, 3))
    result: FloatArray = total / max(1, len(lexical))
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
    distances = None
    if keep_distances:
        distances = code_distances(world)
        if len(spoken) != len(world.live.group_ids):
            distances = distances[np.ix_(spoken, spoken)]
    features = _features(world, group_ids)
    dialects = tuple(
        tuple(group_ids[index] for index in cluster)
        for cluster in constrained_average_linkage(world, group_ids, dialect_threshold, features=features)
    )
    member_of = {group: lineage for lineage, members in tracker.lineages.items() for group in members}
    language_clusters = [
        [group_ids[index] for index in cluster]
        for cluster in constrained_average_linkage(
            world, group_ids, language_threshold, features=features,
            labels=[member_of.get(group_id) for group_id in group_ids],
            margin=HYSTERESIS * language_threshold,
        )
    ]
    languages, events = tracker.update(language_clusters, tick)
    return (
        Snapshot(tick, year, tuple(group_ids), distances, dialects, languages),
        events,
    )


# --- pozorování bez matice všech dvojic ---------------------------------------
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
    group_ids: list[str]
    shares: FloatArray            # (skupiny, kategorie variant)
    squares: FloatArray           # Σ‖p‖² za skupinu
    forms: list[dict[int, float]]  # skupina → {kategorie tvaru: 1}
    spread: list[dict[int, float]]  # skupina → {kategorie tvaru: Σ vzdálenost k tvarům téhož kořene}
    lexical: int


def _features(world: World, group_ids: Sequence[str]) -> _Features:
    live = world.live
    columns = [live.group_index[group_id] for group_id in group_ids]
    parts, owners = [], []
    for pool in live.iter_blocks():
        rows = [row for row, variable_id in enumerate(pool.variable_ids)
                if world.variables[variable_id].kind in ("lexical", "construction")]
        if not rows:
            continue
        freqs = np.where(pool.present[np.ix_(rows, columns)][:, :, None], pool.freqs[rows][:, columns], 0.0)
        parts.append(np.transpose(freqs, (1, 0, 2)).reshape(len(columns), -1))
        owners += [pool.variable_ids[row] for row in rows for _ in range(pool.capacity)]
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
            width: dict[str, int] = {}
            for column in np.flatnonzero(varying):
                width[owners[column]] = width.get(owners[column], 0) + 1
            kept, used = set(), 0
            for name in sorted(width, key=lambda name: (stable_int("observe", name), name)):
                if used + width[name] > SAMPLED:
                    break
                kept.add(name)
                used += width[name]
            varying &= np.array([name in kept for name in owners])
            scale = total / max(1, used)
        shares = _embedded(shares[:, varying], np.sqrt(scale))
    forms: list[dict[int, float]] = [{} for _ in group_ids]
    spread: list[dict[int, float]] = [{} for _ in group_ids]
    if world.table is not None:
        codes = [world.groups[group_id].main_code for group_id in group_ids]
        categories: dict[tuple[str, str, tuple[int, ...]], int] = {}
        members: dict[tuple[str, str], list[tuple[int, ...]]] = {}
        chosen: list[list[tuple[str, str, tuple[int, ...]]]] = [[] for _ in group_ids]
        for index, code in enumerate(codes):
            for concept, root in code.phonology.dominant.items():
                key = (concept, root, world.form_of(code, root))
                if key not in categories:
                    categories[key] = len(categories)
                    members.setdefault((concept, root), []).append(key[2])
                chosen[index].append(key)
        for index, keys in enumerate(chosen):
            for key in keys:
                column = categories[key]
                forms[index][column] = 1.0
                for other in members[(key[0], key[1])]:
                    if other != key[2]:
                        spread[index][categories[(key[0], key[1], other)]] = form_distance(world, key[2], other)
    lexical = sum(variable.kind == "lexical" for variable in world.variables.values())
    squares = (shares.astype(np.float64) ** 2).sum(axis=1)
    return _Features(list(group_ids), shares, squares, forms, spread, max(1, lexical))


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


def _candidates(world: World, group_ids: Sequence[str]) -> list[tuple[int, int]]:
    """Dvojice, které se smějí přímo sloučit: vazby a nejbližší sousedé na mapě."""
    index = {group_id: position for position, group_id in enumerate(group_ids)}
    pairs = set()
    for (source, target), _ in world.links.items():
        if source in index and target in index and source != target:
            first, second = index[source], index[target]
            pairs.add((min(first, second), max(first, second)))
    placed = [(position, world.position_of(group_id)) for position, group_id in enumerate(group_ids)]
    placed = [(position, xy) for position, xy in placed if xy is not None]
    if len(placed) > 1:
        xs = np.array([xy[0] for _, xy in placed])
        ys = np.array([xy[1] for _, xy in placed])
        extent = max(float(xs.max() - xs.min()), float(ys.max() - ys.min()), 1e-9)
        size = extent / max(1.0, np.sqrt(len(placed) / 2.0))
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
                first, second = placed[slot][0], placed[other][0]
                pairs.add((min(first, second), max(first, second)))
    return sorted(pairs)


def constrained_average_linkage(
    world: World, group_ids: Sequence[str], threshold: float, *,
    labels: Sequence[str | None] | None = None, margin: float = 0.0, features: _Features | None = None,
) -> list[list[int]]:
    """Průměrná vazba mezi sousedícími shluky až do prahu (lineární v počtu skupin).

    S ``labels`` (dosavadní linie skupin) a ``margin`` hystereze: dvojice téže
    linie je o ``margin`` blíž, dvojice dvou různých známých linií dál.
    """
    count = len(group_ids)
    clusters = [[index] for index in range(count)]
    if count < 2:
        return clusters
    feats = features if features is not None else _features(world, group_ids)
    size = np.ones(count)
    shares = feats.shares.copy()
    squares = feats.squares.copy()
    forms = [dict(item) for item in feats.forms]
    spread = [dict(item) for item in feats.spread]
    label_counts: list[dict[str, float]] = [
        {} if labels is None or labels[index] is None else {str(labels[index]): 1.0} for index in range(count)
    ]
    neighbours: list[set[int]] = [set() for _ in range(count)]
    for first, second in _candidates(world, group_ids):
        neighbours[first].add(second)
        neighbours[second].add(first)

    def linkage(a: int, b: int) -> float:
        na, nb = size[a], size[b]
        value = 0.5 * (squares[a] / na + squares[b] / nb) - float(shares[a] @ shares[b]) / (na * nb)
        small, large = (spread[a], forms[b]) if len(spread[a]) <= len(forms[b]) else (forms[b], spread[a])
        value += FORM_WEIGHT * sum(weight * large.get(column, 0.0) for column, weight in small.items()) / (na * nb)
        value /= feats.lexical
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

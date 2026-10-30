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
from cee.v2.rng import stable_id
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


def average_linkage(distances: FloatArray, threshold: float) -> list[list[int]]:
    """Hierarchické shlukování (průměrná vazba) až do dané vzdálenosti."""
    clusters = [[index] for index in range(len(distances))]
    if len(clusters) < 2:
        return clusters
    linkage = distances.astype(np.float64).copy()
    np.fill_diagonal(linkage, np.inf)
    sizes = np.ones(len(clusters))
    alive = np.ones(len(clusters), dtype=bool)
    while alive.sum() > 1:
        masked = np.where(alive[:, None] & alive[None, :], linkage, np.inf)
        first, second = np.unravel_index(int(np.argmin(masked)), masked.shape)
        if masked[first, second] > threshold:
            break
        keep, drop = (int(first), int(second)) if first < second else (int(second), int(first))
        merged = (sizes[keep] * linkage[keep] + sizes[drop] * linkage[drop]) / (
            sizes[keep] + sizes[drop]
        )
        linkage[keep, :] = merged
        linkage[:, keep] = merged
        linkage[keep, keep] = np.inf
        sizes[keep] += sizes[drop]
        alive[drop] = False
        clusters[keep].extend(clusters[drop])
        clusters[drop] = []
    return sorted((sorted(cluster) for cluster in clusters if cluster), key=lambda c: c[0])


@dataclass(frozen=True)
class Snapshot:
    tick: int
    year: float
    group_ids: tuple[str, ...]
    distances: FloatArray
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


def _with_hysteresis(
    distances: FloatArray, group_ids: Sequence[str], tracker: LineageTracker, margin: float
) -> FloatArray:
    if not tracker.lineages or margin == 0:
        return distances
    member_of = {group: lineage for lineage, members in tracker.lineages.items() for group in members}
    labels = [member_of.get(group_id) for group_id in group_ids]
    known = np.array([label is not None for label in labels])
    same = np.array([[a is not None and a == b for b in labels] for a in labels])
    shift = np.where(same, -margin, np.where(known[:, None] & known[None, :], margin, 0.0))
    adjusted: FloatArray = np.maximum(0.0, distances + shift)
    np.fill_diagonal(adjusted, 0.0)
    return adjusted


def observe(
    world: World,
    tick: int,
    year: float,
    tracker: LineageTracker,
    *,
    dialect_threshold: float,
    language_threshold: float,
) -> tuple[Snapshot, list[dict[str, object]]]:
    # Do dialektů a jazyků se počítá jen řeč z domova: psaný kód nemá
    # mluvčí a kód trhu, úřadu nebo školy (veřejná doména) je druhý jazyk.
    spoken = [index for index, group_id in enumerate(world.live.group_ids)
              if not world.groups[group_id].written and world.groups[group_id].domain == "home"]
    group_ids = [world.live.group_ids[index] for index in spoken]
    distances = code_distances(world)
    if len(spoken) != len(world.live.group_ids):
        distances = distances[np.ix_(spoken, spoken)]
    dialects = tuple(
        tuple(group_ids[index] for index in cluster)
        for cluster in average_linkage(distances, dialect_threshold)
    )
    language_clusters = [
        [group_ids[index] for index in cluster]
        for cluster in average_linkage(
            _with_hysteresis(distances, group_ids, tracker, HYSTERESIS * language_threshold),
            language_threshold,
        )
    ]
    languages, events = tracker.update(language_clusters, tick)
    return (
        Snapshot(tick, year, tuple(group_ids), distances, dialects, languages),
        events,
    )

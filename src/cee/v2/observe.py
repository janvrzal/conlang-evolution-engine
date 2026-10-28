"""Pozorování: vzdálenosti kódů, dialekty, jazyky a jejich linie (iterace 4).

Jazyky ani strom jazyků nejsou vstupem simulace. Počítají se zde ze
skutečného stavu repertoárů.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.rng import stable_id
from cee.v2.world import World

FloatArray = npt.NDArray[np.float64]


def distance_matrix(world: World, chunk: int = 4_000_000) -> FloatArray:
    """Průměrná variační vzdálenost hlavních kódů přes všechny proměnné.

    Pro jednu proměnnou je vzdálenost ½ Σ |p − q|: 0 pro shodné rozdělení,
    1 pro zcela odlišné varianty. Proměnné, které jsou všude stejné, by
    přispěly nulou, proto se počítá jen nad živými proměnnými. Průměr se bere
    přes všechny lexikální proměnné, aby vzdálenost nezávisela na tom, kolik
    jich je zrovna živých. Zvukové procesy se zatím nezapočítávají: mrtvé
    inovace by vzdálenost ředily (srovnání tvarů kognátů přijde v M6). Výpočet běží po blocích proměnných, aby
    paměť nerostla se čtvercem počtu skupin krát počet proměnných.
    """
    live = world.live
    count = len(live.group_ids)
    total = np.zeros((count, count))
    lexical = [variable_id for variable_id, variable in world.variables.items()
               if variable.kind == "lexical"]
    for pool in live.iter_blocks():
        rows = [row for row, variable_id in enumerate(pool.variable_ids)
                if world.variables[variable_id].kind == "lexical"]
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


def observe(
    world: World,
    tick: int,
    year: float,
    tracker: LineageTracker,
    *,
    dialect_threshold: float,
    language_threshold: float,
) -> tuple[Snapshot, list[dict[str, object]]]:
    group_ids = world.live.group_ids
    distances = distance_matrix(world)
    dialects = tuple(
        tuple(group_ids[index] for index in cluster)
        for cluster in average_linkage(distances, dialect_threshold)
    )
    language_clusters = [
        [group_ids[index] for index in cluster]
        for cluster in average_linkage(distances, language_threshold)
    ]
    languages, events = tracker.update(language_clusters, tick)
    return (
        Snapshot(tick, year, tuple(group_ids), distances, dialects, languages),
        events,
    )

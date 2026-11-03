"""Hledání míst inovací pro celou inovační fázi jako jedna dávka (krok B5b).

``Simulation._innovate`` potřebuje pro každou dvojici (skupina, druh změny) celkovou míru
míst. Zvukové změny (rodiny) počítá index prostředí světa jedním dotazem pro všechny rodiny;
expresivní tvoření slov, sémantické, morfologické (vyrovnání, rozšíření) a syntaktické změny
počítá index míst světa (:mod:`cee.v2.language.site_index`, v Rustu) jednou dávkou pro všechny
skupiny a všechny tyto druhy najednou. Zbylé druhy (výpůjčky slov, reanalýza hranice, přízvuk a
vlastní podtřídy změn) jedou výchozím ``total_rates`` po jedné změně.

Změna, kterou počítá index míst, má na své třídě (ne zděděný) atribut ``site_column``: číslo
sloupce výstupu dávky. Podtřída bez vlastního ``site_column`` (jiné chování) jede výchozí cestou.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.site_index import COL_COINAGE, site_index


def native_column(change: Change) -> int | None:
    """Sloupec dávky, kterou změna počítá index míst; ``None`` pro změny jiné cesty (viz modul)."""
    column = type(change).__dict__.get("site_column")
    return column if isinstance(column, int) else None


def column_totals(change: Change, contexts: Sequence[InnovationContext]) -> list[float]:
    """Celkové míry jedné změny pro všechny skupiny jednou dávkou (výchozí ``total_rates`` změn indexu míst)."""
    column = native_column(change)
    assert column is not None
    if not contexts:
        return []
    world = contexts[0].world
    scale = change.rate_scale(contexts[0]) if column == COL_COINAGE else 1.0
    totals, _ = site_index(world).batch(world, list(contexts), {column: change.base_rate}, scale)
    return [float(value) for value in totals[:, column]]


def rate_sums(
    changes: Sequence[Change], contexts: Sequence[InnovationContext]
) -> npt.NDArray[np.float64]:
    """Celkové míry míst (skupina × změna): nenulové jen tam, kde změna má místa.

    Zvukové změny počítá jeden dotaz na index prostředí, změny z indexu míst jedna dávka, zbytek
    výchozí ``total_rates``. Výsledek je stejný jako ``total_rates`` po jedné změně.
    """
    from cee.v2.changes.sound import batch_total_rates

    sums = np.zeros((len(contexts), len(changes)), dtype=np.float64)
    if not contexts:
        return sums
    world = contexts[0].world
    bases: dict[int, float] = {}
    positions: dict[int, int] = {}
    scale = 1.0
    for position, change in enumerate(changes):
        column = native_column(change)
        if column is not None:
            bases[column] = change.base_rate
            positions[position] = column
            if column == COL_COINAGE:
                scale = change.rate_scale(contexts[0])
    found: dict[int, list[float]] = {}
    if positions:
        totals, _ = site_index(world).batch(world, list(contexts), bases, scale)
        for position, column in positions.items():
            found[position] = totals[:, column].tolist()
    found.update(batch_total_rates(changes, contexts))
    for position, change in enumerate(changes):
        column_values = found.get(position)
        if column_values is None:
            column_values = [float(value) for value in change.total_rates(contexts)]
        values = np.array(column_values, dtype=np.float64)
        sums[:, position] = np.where(values > 0.0, values, 0.0)
    return sums

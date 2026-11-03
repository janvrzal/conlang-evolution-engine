"""Hledání míst inovací pro celou inovační fázi jako jedna dávka (kroky B5b a B6d).

``Simulation._innovate`` potřebuje pro každou dvojici (skupina, druh změny) celkovou míru
míst. Zvukové změny (rodiny) počítá index prostředí světa (:mod:`cee.v2.language.sound_index`);
expresivní tvoření slov, sémantické, morfologické (vyrovnání, rozšíření, reanalýza hranice), syntaktické
změny, výpůjčky slov a prozodické změny počítá index míst světa (:mod:`cee.v2.language.site_index`).
S Rustem je to **jediné volání za tik**: oba indexy si data předávají v Rustu a vrátí matici
skupina × druh změny. Vlastní podtřídy změn jedou výchozím ``total_rates`` po jedné změně.

Změna, kterou počítá index míst, má na své třídě (ne zděděný) atribut ``site_column``: číslo
sloupce výstupu dávky. Podtřída bez vlastního ``site_column`` (jiné chování) jede výchozí cestou.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import numpy.typing as npt

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.site_index import COL_BORROWING, COL_COINAGE, site_index


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
    borrowing = change.borrowing_inputs(contexts) if column == COL_BORROWING else None  # type: ignore[attr-defined]
    totals, _ = site_index(world).batch(world, list(contexts), {column: change.base_rate}, scale, borrowing)
    return [float(value) for value in totals[:, column]]


def rate_sums(
    changes: Sequence[Change], contexts: Sequence[InnovationContext]
) -> npt.NDArray[np.float64]:
    """Celkové míry míst (skupina × změna): nenulové jen tam, kde změna má místa.

    S indexy v Rustu je to **jedno volání** za tik: index prostředí zvukových změn a index míst ostatních
    změn (expresivní tvoření, sémantika, vyrovnání a rozšíření, syntax, výpůjčky, reanalýza hranice, prozodie)
    si předávají data v Rustu a vrátí součty pro všechny skupiny a druhy změn. Bez Rustu (``CEE_NATIVE=0``)
    počítá totéž Python po indexech. Zbytek (vlastní podtřídy změn) jede výchozím ``total_rates``.
    Výsledek je stejný jako ``total_rates`` po jedné změně.
    """
    from cee.v2.changes.sound import (
        batch_total_rates,
        family_totals,
        live_positions,
        sound_index,
        standard_sound_changes,
    )
    from cee.v2.language.sound_index import NativeSoundIndex

    sums = np.zeros((len(contexts), len(changes)), dtype=np.float64)
    if not contexts:
        return sums
    world = contexts[0].world
    bases: dict[int, float] = {}
    positions: dict[int, int] = {}
    scale = 1.0
    borrowing = None
    for position, change in enumerate(changes):
        column = native_column(change)
        if column is not None:
            bases[column] = change.base_rate
            positions[position] = column
            if column == COL_COINAGE:
                scale = change.rate_scale(contexts[0])
            if column == COL_BORROWING:
                borrowing = change.borrowing_inputs(contexts)  # type: ignore[attr-defined]
    found: dict[int, list[float]] = {}
    index = site_index(world) if positions else None
    standard = standard_sound_changes(changes)
    live = live_positions(contexts) if standard else []
    sound = sound_index(world) if live else None
    if index is not None and index.native and isinstance(sound, NativeSoundIndex):
        # Jediné volání Rustu pro oba indexy.
        codes = [contexts[position].code for position in live]
        (totals, _), (matrix, has) = index.batch_with_sound(  # type: ignore[misc]
            world, list(contexts), bases, scale, borrowing, (sound, codes)
        )
        found.update(family_totals(standard, contexts, live, matrix, has))
    else:
        if index is not None:
            totals, _ = index.batch(world, list(contexts), bases, scale, borrowing)
        found.update(batch_total_rates(changes, contexts))
    if index is not None:
        for position, column in positions.items():
            found[position] = totals[:, column].tolist()
    for position, change in enumerate(changes):
        column_values = found.get(position)
        if column_values is None:
            column_values = [float(value) for value in change.total_rates(contexts)]
        values = np.array(column_values, dtype=np.float64)
        sums[:, position] = np.where(values > 0.0, values, 0.0)
    return sums

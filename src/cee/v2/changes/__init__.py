"""Změny a jejich registr."""

from __future__ import annotations

from typing import Sequence

from cee.v2.changes.base import Change, InnovationContext, RateBasis
from cee.v2.changes.lexicon import LexicalCoinage
from cee.v2.changes.sound import SOUND_CHANGES, SoundChange
from cee.v2.pressures.base import Pressure

#: Pevné pořadí registru je součástí determinismu. Ve světě bez hláskových
#: tvarů (M1) zvukové změny nenajdou žádné místo a nic nestojí.
DEFAULT_CHANGES: tuple[Change, ...] = (LexicalCoinage(), *SOUND_CHANGES)


def pressures_by_kind(changes: Sequence[Change]) -> dict[str, tuple[tuple[Pressure, float], ...]]:
    """Tlaky pro každý typ proměnné.

    Všechny varianty jedné proměnné se musí hodnotit stejnými tlaky, i když
    je vyrobily různé změny. Tlaky se proto sdružují podle cílového typu;
    deklaruje-li tentýž tlak víc změn, platí nejvyšší váha.
    """
    weights: dict[str, dict[type[Pressure], float]] = {}
    for change in changes:
        target = weights.setdefault(change.target, {})
        for pressure, weight in change.pressures.items():
            target[pressure] = max(weight, target.get(pressure, weight))
    return {
        kind: tuple(
            (pressure(), weight)
            for pressure, weight in sorted(items.items(), key=lambda item: item[0].name)
        )
        for kind, items in weights.items()
    }


__all__ = [
    "DEFAULT_CHANGES",
    "Change",
    "InnovationContext",
    "LexicalCoinage",
    "SOUND_CHANGES",
    "SoundChange",
    "RateBasis",
    "pressures_by_kind",
]

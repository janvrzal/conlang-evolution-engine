"""Změny a jejich registr."""

from __future__ import annotations

from typing import Sequence

from cee.v2.changes.base import Change, InnovationContext, RateBasis
from cee.v2.changes.lexicon import LEXICAL_CHANGES, LexicalCoinage
from cee.v2.changes.morphology import MORPHOLOGICAL_CHANGES, AnalogicalChange
from cee.v2.changes.prosody import PROSODY_CHANGES, StressShift, StressStrengthChange
from cee.v2.changes.sound import SOUND_CHANGES, SoundChange
from cee.v2.changes.syntax import SYNTACTIC_CHANGES, SyntacticChange
from cee.v2.pressures.base import Pressure
from cee.v2.pressures.social import Norm

#: Pevné pořadí registru je součástí determinismu. Ve světě bez hláskových
#: tvarů (M1) zvukové změny nenajdou žádné místo a nic nestojí.
DEFAULT_CHANGES: tuple[Change, ...] = (
    *LEXICAL_CHANGES, *SOUND_CHANGES, *MORPHOLOGICAL_CHANGES, *SYNTACTIC_CHANGES, *PROSODY_CHANGES,
)


def pressures_by_kind(changes: Sequence[Change]) -> dict[str, tuple[tuple[Pressure, float], ...]]:
    """Tlaky pro každý typ proměnné.

    Všechny varianty jedné proměnné se musí hodnotit stejnými tlaky, i když
    je vyrobily různé změny. Tlaky se proto sdružují podle cílového typu;
    deklaruje-li tentýž tlak víc změn, platí nejvyšší váha. `Norm` (škola)
    působí na každý typ proměnné.
    """
    weights: dict[str, dict[type[Pressure], float]] = {}
    for change in changes:
        target = weights.setdefault(change.target, {})
        target.setdefault(Norm, 1.0)
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
    "LEXICAL_CHANGES",
    "MORPHOLOGICAL_CHANGES",
    "AnalogicalChange",
    "DEFAULT_CHANGES",
    "Change",
    "InnovationContext",
    "LexicalCoinage",
    "PROSODY_CHANGES",
    "SOUND_CHANGES",
    "SYNTACTIC_CHANGES",
    "StressShift",
    "StressStrengthChange",
    "SyntacticChange",
    "SoundChange",
    "RateBasis",
    "pressures_by_kind",
]

"""Deterministické vyhodnocení časovaných účinků historických událostí.

Tento modul neprovádí žádné jazykové změny. Pouze překládá autorský popis
události na průhledné, parametrické tlaky, které pak spotřebuje simulátor.
"""

from __future__ import annotations

import math
from typing import Any, Dict

SOCIAL_PARAMETERS = frozenset({
    "prestige", "mobility", "literacy", "standardization", "population",
    "isolation", "contact_intensity", "institutional_pressure",
    "register_pressure", "urbanity", "receptivity",
})
CURVES = frozenset({"step", "linear", "pulse", "persistent"})


def normalize_effect(parameter: str, raw: Any, duration: int) -> Dict[str, Any] | None:
    """Normalizuje starý číselný i nový objektový zápis efektu.

    ``{"value": .8, "curve": "linear", "mode": "target"}`` nastavuje
    cílovou intenzitu; ``mode: add`` přičítá příspěvek. Čísla z původního
    formátu zůstávají okamžitými cílovými efekty (``step``).
    """
    if parameter not in SOCIAL_PARAMETERS:
        return None
    if isinstance(raw, dict):
        if "value" not in raw:
            return None
        value = raw["value"]
        curve = str(raw.get("curve", "step"))
        mode = str(raw.get("mode", "target"))
    else:
        value, curve, mode = raw, "step", "target"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return {
        "parameter": parameter,
        "value": max(0.0, min(1.0, value)),
        "curve": curve if curve in CURVES else "step",
        "mode": mode if mode in {"target", "add"} else "target",
        "duration": max(0, int(duration)),
    }


def curve_strength(curve: str, start_year: int, duration: int, year: int) -> float:
    """Vrací sílu účinku v konkrétním roce, včetně následku persistent."""
    if year < start_year:
        return 0.0
    if duration <= 0:
        return 1.0
    end_year = start_year + duration
    if year >= end_year:
        return 1.0 if curve == "persistent" else 0.0
    progress = (year - start_year) / duration
    if curve == "linear" or curve == "persistent":
        return progress
    if curve == "pulse":
        return math.sin(math.pi * progress)
    return 1.0

"""Volitelné jádro v Rustu (rozšíření ``cee_core``).

Python zůstává referenční implementací: bez sestaveného rozšíření, s nastaveným
``CEE_NATIVE=0`` nebo při neshodě verze rozhraní poběží stávající kód beze
změny a výsledky jsou bitově stejné. Rozšíření se sestavuje z ``rust/cee_core``
(``maturin``); kdo ho nemá, o nic nepřichází.

Verze rozhraní chrání před rozjetím Pythonu a rozšíření: rozšíření se může
nainstalovat do sdíleného prostředí a vidět ho tak i jiná kopie kódu, která
čeká jiné rozhraní. Při neshodě se nepoužije.
"""

from __future__ import annotations

import os
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cee.v2.language.segments import SegmentTable

#: Verze rozhraní, kterou tento Python čeká (viz ``INTERFACE_VERSION`` v Rustu).
INTERFACE_VERSION = 3

#: Čísla operací a pravidel přízvuku, jak je zná Rust (``process.rs``).
OPERATIONS = ("change", "replace", "delete", "insert_before", "insert_after", "merge_next", "tone")
RULES = ("initial", "second", "antepenult", "penult", "final")

_UNLOADED: Any = object()
_module: ModuleType | None | Any = _UNLOADED


def _load() -> ModuleType | None:
    global _module
    if _module is _UNLOADED:
        try:
            import cee_core  # type: ignore[import-not-found, unused-ignore]
        except ImportError:
            _module = None
        else:
            _module = cee_core if getattr(cee_core, "INTERFACE_VERSION", None) == INTERFACE_VERSION else None
    return _module


def available() -> bool:
    """Je rozšíření sestavené, nainstalované a má správnou verzi rozhraní?"""
    return _load() is not None


def enabled() -> bool:
    """Použije se Rust? Ne, když je ``CEE_NATIVE=0`` nebo rozšíření chybí."""
    return os.environ.get("CEE_NATIVE", "") != "0" and available()


def status() -> str:
    """Čitelný popis pro výpisy skriptů: ``rust`` či ``python`` a důvod."""
    if os.environ.get("CEE_NATIVE", "") == "0":
        return "python (CEE_NATIVE=0)"
    if available():
        return "rust"
    return "python (rozšíření cee_core není k dispozici)"


def new_bank(table: SegmentTable) -> Any | None:
    """Prázdná banka v Rustu nad tabulkou hlásek, nebo ``None`` bez Rustu."""
    if not enabled():
        return None
    module = _load()
    assert module is not None
    return module.NativeBank(table.boundary, table.vowel_mask, glide_mask(table))


def glide_mask(table: SegmentTable) -> Any:
    """Maska polosamohlásek (``SegmentTable.sonority == 3``) s hranicí slova na konci.

    Vektorově to samé, co ``sonority``: ne slabičná, sonorantní a nesouhláskové.
    """
    import numpy as np

    vectors, index = table.vectors, table.index
    syllabic = vectors[:, index["syl"]] == 1
    sonorant = vectors[:, index["son"]] == 1
    consonantal = vectors[:, index["cons"]] == 1
    return np.append(~syllabic & sonorant & ~consonantal, False)

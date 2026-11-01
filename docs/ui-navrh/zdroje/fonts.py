"""Písmo Charis 7 (SIL, OFL) pro zápis IPA ve stránkách prototypů.

Do repozitáře se nevkládá. Stránka ho dostane jen tehdy, když proměnná
``CEE_CHARIS`` ukazuje na adresář ``web`` z balíku Charis 7
(https://software.sil.org/charis/); jinak se IPA vysází písmem systému.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path


def charis(style: str = "Regular") -> str:
    """Písmo jako base64 pro ``@font-face``, nebo prázdný řetězec."""
    folder = os.environ.get("CEE_CHARIS")
    path = Path(folder) / f"Charis-{style}.woff2" if folder else None
    return base64.b64encode(path.read_bytes()).decode() if path and path.exists() else ""

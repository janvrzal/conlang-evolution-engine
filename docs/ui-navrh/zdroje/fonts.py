"""Písmo Charis 7 (SIL, OFL) pro zápis IPA ve stránkách prototypů.

Bere se z ``desktop/static/fonts`` (úplné Charis 7 s licencí OFL), nebo
z adresáře v proměnné ``CEE_CHARIS``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path


def charis(style: str = "Regular") -> str:
    """Písmo jako base64 pro ``@font-face``, nebo prázdný řetězec."""
    folder = os.environ.get("CEE_CHARIS") or str(Path(__file__).resolve().parents[3] / "desktop" / "static" / "fonts")
    path = Path(folder) / f"Charis-{style}.woff2" if folder else None
    return base64.b64encode(path.read_bytes()).decode() if path and path.exists() else ""

"""Co víme o pojmech z dat: sémantická oblast, doména enginu a půjčitelnost.

Výřez z World Loanword Database (Haspelmath & Tadmor 2009, CC BY 4.0) je
v ``cee/data/v2_concepts.json`` (skript ``scripts/build_v2_concepts.py``).
U každého pojmu:

- ``field``: sémantická oblast WOLD (tělo, příbuzenství, společnost
  a politika, náboženství…),
- ``domain``: doména enginu, tedy mechanismus, který na slova působí nejvíc
  (``power``: nová elita, ``religion``: liturgie, ``culture``: obchod
  a kontakt, ``learned``: čtení a škola, ``core``: domácí jádro),
- ``borrowed``: podíl jazyků WOLD, kde je slovo pro pojem přejaté
  (0 = nikde, 1 = všude); ``age`` a ``simplicity`` podobně.

Pojem, který v datech není (vlastní pojem autora), dostane doménu ``core``
a půjčitelnost průměru WOLD, dokud ji autor nezadá.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

#: Domény enginu.
DOMAINS = ("core", "learned", "culture", "religion", "power")


@lru_cache(maxsize=1)
def data() -> dict[str, Any]:
    text = resources.files("cee.data").joinpath("v2_concepts.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def info(concept: str) -> dict[str, Any] | None:
    """Záznam pojmu enginu z WOLD, nebo ``None`` u pojmu mimo data."""
    found: dict[str, Any] | None = data()["concepts"].get(concept)
    return found


def domain(concept: str) -> str:
    """Doména enginu pojmu (``core`` u pojmu mimo data)."""
    found = info(concept)
    return "core" if found is None else str(found["domain"])


@lru_cache(maxsize=1)
def mean_borrowed() -> float:
    """Průměrná půjčitelnost významů katalogu WOLD."""
    scores = [item["borrowed"] for item in data()["catalog"] if item["borrowed"] is not None]
    return sum(scores) / len(scores)


def borrowed(concept: str) -> float:
    """Půjčitelnost pojmu (průměr WOLD u pojmu mimo data nebo bez skóre)."""
    found = info(concept)
    if found is None or found["borrowed"] is None:
        return mean_borrowed()
    return float(found["borrowed"])

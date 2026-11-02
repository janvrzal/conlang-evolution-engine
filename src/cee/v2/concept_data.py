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
  (0 = nikde, 1 = všude); ``age`` a ``simplicity`` podobně;
- ``log_frequency``: frekvence pojmu, ``log10`` výskytů na milion slov
  (``cee/data/v2_concept_frequencies.json``, skript
  ``scripts/build_v2_concept_frequencies.py``): Calude & Pagel 2011 pro
  pojmy Swadeshova seznamu (17 jazyků), jinak korpusy Leipzig v sedmi
  jazycích převedené na stejnou stupnici (korelace se Calude & Pagel 0,92).

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
#: Převod frekvence z dat na stupnici enginu: ``log10`` výskytů na milion
#: (asi 3 a 3 000) → frekvence enginu (rozpětí dřívějších generovaných
#: frekvencí), mezi nimi log-lineárně, mimo oříznuto.
LOG_FREQUENCY_ANCHORS = (0.5, 3.5)
FREQUENCY_RANGE = (0.05, 0.9)


@lru_cache(maxsize=1)
def data() -> dict[str, Any]:
    text = resources.files("cee.data").joinpath("v2_concepts.json").read_text(encoding="utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


@lru_cache(maxsize=1)
def frequencies() -> dict[str, Any]:
    text = resources.files("cee.data").joinpath("v2_concept_frequencies.json").read_text(encoding="utf-8")
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


def log_frequency(concept: str) -> float | None:
    """``log10`` výskytů pojmu na milion slov, nebo ``None`` u pojmu mimo data."""
    found = frequencies()["concepts"].get(concept)
    return None if found is None else float(found["log_frequency"])


def frequency(concept: str) -> float | None:
    """Frekvence pojmu na stupnici enginu (:data:`FREQUENCY_RANGE`), nebo ``None`` mimo data."""
    value = log_frequency(concept)
    if value is None:
        return None
    low, high = LOG_FREQUENCY_ANCHORS
    position = min(max((value - low) / (high - low), 0.0), 1.0)
    least, most = FREQUENCY_RANGE
    return float(least * (most / least) ** position)

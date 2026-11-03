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

**Katalog**: význam WOLD, který není pojmem ``DEFAULT_CONCEPTS``, má ID
pojmu odvozené z jeho názvu (:func:`catalog_ids`: bez členu *the* a *to*,
malými písmeny, ``mountain-or-hill``; číslo homonyma ``(2)`` jako ``-2``;
při shodě s jiným pojmem ``…-<ID WOLD>``). Funkce :func:`info`,
:func:`domain`, :func:`borrowed` a :func:`frequency` je znají stejně jako
pojmy enginu, takže větší slovník (``cee.v2.vocabulary``) má pro každý
pojem doménu, půjčitelnost i frekvenci z dat. Pořadí pojmů, ve kterém se
slovník rozšiřuje, dává :func:`catalog_order`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from importlib import resources
from typing import Any

#: Domény enginu.
DOMAINS = ("core", "learned", "culture", "religion", "power")
#: Převod frekvence z dat na stupnici enginu: ``log10`` výskytů na milion
#: v kotvách (asi 3 a 3 000) → frekvence enginu (rozpětí dřívějších
#: generovaných frekvencí), mezi nimi log-lineárně, mimo oříznuto. Na
#: absolutní frekvenci stojí prahy morfologie (``conserved_frequency`` 0,7),
#: proto se kotvy nemění; jak silně frekvence chrání slova před výměnou,
#: ladí ``Parameters.entrenchment_frequency_exponent``.
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


def _wold_key(wold_id: str) -> tuple[int, ...]:
    """Číselný klíč ID významu WOLD (``10-47`` → ``(10, 47)``), aby ``2-9`` přišlo před ``2-10``."""
    return tuple(int(part) for part in wold_id.split("-"))


def _slug(name: str) -> str:
    """ID pojmu z názvu významu WOLD: ``the mountain or hill`` → ``mountain-or-hill``."""
    text = re.sub(r"^(the|to|a|an) ", "", name.lower().strip())
    text = re.sub(r"\((\d+)\)$", r"-\1", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


@lru_cache(maxsize=1)
def catalog_ids() -> dict[str, dict[str, Any]]:
    """Významy katalogu mimo pojmy enginu podle ID pojmu (v pořadí ID WOLD).

    Významy, které engine už zná (pojmy ``DEFAULT_CONCEPTS``), tu nejsou. Chybí
    i významy, jejichž název dává ID zdroje gramatikalizace (*go, have, want,
    finish, thing*): ty engine má vždy a bez dat o frekvenci, aby se výchozí svět
    nezměnil. Při shodě ID s pojmem enginu nebo s dřívějším významem se k ID
    přidá ID WOLD (``fly-3-83`` je hmyz, ``fly`` sloveso).
    """
    from cee.v2.language.constructions import GRAMMATICAL_SOURCES

    engine = data()["concepts"]
    known = {entry["wold_id"] for entry in engine.values()}
    taken = {*engine, *GRAMMATICAL_SOURCES}
    found: dict[str, dict[str, Any]] = {}
    for item in sorted(data()["catalog"], key=lambda entry: _wold_key(entry["wold_id"])):
        if item["wold_id"] in known:
            continue
        base = _slug(item["name"])
        if base in GRAMMATICAL_SOURCES:
            continue
        concept = base if base not in taken else f"{base}-{item['wold_id']}"
        taken.add(concept)
        found[concept] = item
    return found


@lru_cache(maxsize=1)
def catalog_order() -> tuple[str, ...]:
    """Pořadí, ve kterém se slovník rozšiřuje o pojmy katalogu (ID pojmů).

    Nejdřív významy Swadeshova seznamu (frekvence z Calude & Pagel 2011, tedy
    základní slovní zásoba), pak ostatní; uvnitř skupiny sestupně podle
    frekvence z dat, při shodě podle ID WOLD. Pořadí nezávisí na ničem než na
    datech, takže slovník o ``n`` pojmech je vždy začátkem slovníku o ``n + 1``.
    ``core_list`` WOLD pořadí nerozliší: je pravdivé u všech významů katalogu.
    """
    table = frequencies()["catalog"]

    def key(concept: str) -> tuple[bool, float, tuple[int, ...]]:
        item = catalog_ids()[concept]
        value, source = table[item["wold_id"]][:2]
        return (source != "calude2011", -float(value), _wold_key(item["wold_id"]))

    return tuple(sorted(catalog_ids(), key=key))


def info(concept: str) -> dict[str, Any] | None:
    """Záznam pojmu z WOLD (pojem enginu nebo katalogu), nebo ``None`` u pojmu mimo data."""
    found: dict[str, Any] | None = data()["concepts"].get(concept)
    return found if found is not None else catalog_ids().get(concept)


def find(*, wold: str | None = None, concepticon: int | None = None, gloss: str | None = None) -> dict[str, Any] | None:
    """Význam katalogu podle ID WOLD, ID Concepticonu nebo anglického glosu.

    Glos se hledá jako glos Concepticonu (bez ohledu na velikost písmen) a pak
    jako název významu WOLD bez členu. Při více shodách vyhraje význam doložený
    ve víc jazycích, pak nižší ID WOLD. ``None``, když nic nevyhovuje.
    """
    catalog = data()["catalog"]
    if wold is not None:
        return next((item for item in catalog if item["wold_id"] == wold), None)
    if concepticon is not None:
        matches = [item for item in catalog if item["concepticon_id"] == concepticon]
    elif gloss is not None:
        wanted = gloss.strip().lower()
        matches = [item for item in catalog if (item["concepticon_gloss"] or "").lower() == wanted]
        if not matches:
            matches = [item for item in catalog if re.sub(r"^(the|to|a|an) ", "", item["name"].lower()) == wanted]
    else:
        return None
    if not matches:
        return None
    best: dict[str, Any] = min(matches, key=lambda item: (-item["languages"], _wold_key(item["wold_id"])))
    return best


def domain(concept: str) -> str:
    """Doména enginu pojmu (``core`` u pojmu mimo data)."""
    found = info(concept)
    return "core" if found is None else str(found["domain"])


@lru_cache(maxsize=None)
def mean_borrowed(domain: str | None = None) -> float:
    """Průměrná půjčitelnost významů katalogu WOLD (jen domény ``domain``, je-li zadaná)."""
    scores = [item["borrowed"] for item in data()["catalog"]
              if item["borrowed"] is not None and (domain is None or item["domain"] == domain)]
    return sum(scores) / len(scores)


@lru_cache(maxsize=None)
def mean_frequency(domain: str | None = None) -> float:
    """Průměrná frekvence (stupnice enginu) významů katalogu (jen domény ``domain``, je-li zadaná)."""
    table = frequencies()["catalog"]
    values = [_scaled(float(table[item["wold_id"]][0])) for item in data()["catalog"]
              if domain is None or item["domain"] == domain]
    return sum(values) / len(values)


def borrowed(concept: str) -> float:
    """Půjčitelnost pojmu (průměr WOLD u pojmu mimo data nebo bez skóre)."""
    found = info(concept)
    if found is None or found["borrowed"] is None:
        return mean_borrowed()
    return float(found["borrowed"])


def log_frequency(concept: str) -> float | None:
    """``log10`` výskytů pojmu na milion slov, nebo ``None`` u pojmu mimo data.

    Pojem enginu má frekvenci ze seznamu pojmů; pojem katalogu mimo engine
    (:func:`catalog_ids`) ze stejného zdroje po významech WOLD.
    """
    found = frequencies()["concepts"].get(concept)
    if found is not None:
        return float(found["log_frequency"])
    item = catalog_ids().get(concept)
    return None if item is None else float(frequencies()["catalog"][item["wold_id"]][0])


def _scaled(value: float) -> float:
    """``log10`` výskytů na milion → frekvence na stupnici enginu."""
    low, high = LOG_FREQUENCY_ANCHORS
    position = min(max((value - low) / (high - low), 0.0), 1.0)
    least, most = FREQUENCY_RANGE
    return float(least * (most / least) ** position)


def item_frequency(item: dict[str, Any]) -> float | None:
    """Frekvence významu katalogu na stupnici enginu (``None``, když ji data nemají)."""
    found = frequencies()["catalog"].get(item["wold_id"])
    return None if found is None else _scaled(float(found[0]))


def frequency(concept: str) -> float | None:
    """Frekvence pojmu na stupnici enginu (:data:`FREQUENCY_RANGE`), nebo ``None`` mimo data."""
    value = log_frequency(concept)
    return None if value is None else _scaled(value)

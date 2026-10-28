"""Gramatické funkce a konstrukce (iterace 2 a 3; milníky M4 a M4b).

Funkce (minulý čas, plurál, určenost, zápor, slovosled…) je řádek
katalogu ``cee/data/v2_grammar.yaml`` a v jazyce konstrukční proměnná.
Varianty jsou konstrukce, které spolu soutěží:

- šablona ``inflection``: ``zero`` (nevyjadřuje se), ``periphrastic``
  (pomocné slovo; ``stage`` ``free`` nebo ``clitic``) a ``synthetic``
  (koncovka; ``exponent`` je afix, ``None`` = koncovka z protojazyka;
  ``donor`` = koncovka převzatá exaptací z jiné funkce),
- šablona ``negation``: ``pre`` (částice před slovesem), ``embraced``
  (částice + zesilovač, *ne … pas*), ``post`` (jen zesilovač, *pas*),
- šablona ``order``: ``free`` (role nese pád) a ``fixed`` (``order``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

CATALOG = Path(__file__).resolve().parents[2] / "data" / "v2_grammar.yaml"

Template = Literal["inflection", "negation", "order"]


@dataclass(frozen=True)
class GrammaticalFunction:
    id: str
    template: Template
    domain: str
    need: float = 0.0
    cell: str | None = None
    weight: float = 0.5
    sources: tuple[str, ...] = ()
    compensates: tuple[str, ...] = ()
    orders: tuple[str, ...] = field(default=())
    donors: tuple[str, ...] = ()

    @property
    def word_class(self) -> str | None:
        return self.domain if self.domain in ("noun", "verb") else None


@lru_cache(maxsize=1)
def catalog() -> dict[str, GrammaticalFunction]:
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    return {
        name: GrammaticalFunction(
            id=name,
            template=entry["template"],
            domain=entry["domain"],
            need=float(entry.get("need", 0.0)),
            cell=entry.get("cell"),
            weight=float(entry.get("weight", 0.5)),
            sources=tuple(entry.get("sources", ())),
            compensates=tuple(entry.get("compensates", ())),
            orders=tuple(entry.get("orders", ())),
            donors=tuple(entry.get("donors", ())),
        )
        for name, entry in data["functions"].items()
    }


def function(name: str) -> GrammaticalFunction:
    return catalog()[name]


#: Zdroje gramatikalizace podle funkce (odvozeno z katalogu).
PATHWAYS: dict[str, tuple[str, ...]] = {name: entry.sources for name, entry in catalog().items()}
#: Pojmy, které protojazyk dostane navíc k základní slovní zásobě, aby cesty
#: existovaly (ostatní zdroje katalogu v ní už jsou).
GRAMMATICAL_SOURCES = ("have", "finish", "go", "want", "thing", "step")

#: Jak daleko je konstrukce na škále gramatikalizace (jednosměrnost).
STAGE_RANK = {"free": 0, "clitic": 1}


@dataclass(frozen=True)
class Construction:
    function: str
    kind: str
    source: str | None = None
    stage: str | None = None
    order: str | None = None
    exponent: str | None = None
    reinforcer: str | None = None
    donor: str | None = None

    @property
    def key(self) -> str:
        parts = (self.function, self.kind, self.source or "", self.stage or "",
                 self.order or "", self.exponent or "", self.reinforcer or "")
        key = "|".join(parts)
        return key if self.donor is None else f"{key}|{self.donor}"

    @property
    def words(self) -> int:
        """Kolik samostatných slov konstrukce přidává."""
        if self.kind == "periphrastic":
            return 1 if self.stage == "free" else 0
        if self.kind == "embraced":
            return 2
        if self.kind in ("pre", "post"):
            return 1
        return 0

    @property
    def rank(self) -> int:
        """Pořadí na škále gramatikalizace: nic/stará koncovka < opis < přiklonka < nová koncovka."""
        if self.kind == "periphrastic":
            return 1 + STAGE_RANK.get(self.stage or "free", 0)
        if self.kind == "synthetic" and self.exponent is not None:
            return 3
        return 0

    @property
    def carries_order(self) -> bool:
        """Nese tato konstrukce role argumentů pořadím slov?"""
        return self.kind == "fixed"

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

from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping, cast

import yaml

from cee.v2.parameters import Parameters

if TYPE_CHECKING:
    from cee.v2.world import World

CATALOG = Path(__file__).resolve().parents[2] / "data" / "v2_grammar.yaml"

Template = Literal["inflection", "negation", "order"]


@dataclass(frozen=True)
class GrammaticalFunction:
    id: str
    template: Template
    domain: str
    need: float = 0.0
    context: float = 0.0
    cell: str | None = None
    weight: float = 0.5
    sources: tuple[str, ...] = ()
    compensates: tuple[str, ...] = ()
    #: Jakou část role zastoupených funkcí (``compensates``) nese, když ji jazyk
    #: vyjadřuje (0 až 1).
    coverage: float = 0.0
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
            context=float(entry.get("context", 0.0)),
            cell=entry.get("cell"),
            weight=float(entry.get("weight", 0.5)),
            sources=tuple(entry.get("sources", ())),
            compensates=tuple(entry.get("compensates", ())),
            coverage=float(entry.get("coverage", 0.0)),
            orders=tuple(entry.get("orders", ())),
            donors=tuple(entry.get("donors", ())),
        )
        for name, entry in data["functions"].items()
    }


@lru_cache(maxsize=None)
def _with_overrides(grammar: Mapping[str, Mapping[str, float]]) -> dict[str, GrammaticalFunction]:
    """Katalog s přepsanými poli ``need`` a ``context``; globální katalog se nemění."""
    base = catalog()
    unknown = sorted(set(grammar) - set(base))
    if unknown:
        raise ValueError(f"Parametry přepisují neznámé gramatické funkce: {unknown}.")
    return {
        name: replace(entry, **cast(Any, {key: float(value) for key, value in grammar[name].items()}))
        if name in grammar else entry
        for name, entry in base.items()
    }


def catalog_for(world: World | Parameters) -> dict[str, GrammaticalFunction]:
    """Katalog funkcí s přepisy z ``params.grammar`` světa (nebo z přímo daných parametrů).

    Bez přepisů je to sdílený :func:`catalog`. Výsledek se nesmí měnit; cache
    je podle hodnoty přepisů, takže světy s týmiž parametry sdílejí katalog
    a světy s různými parametry se neovlivňují.
    """
    grammar = (world if isinstance(world, Parameters) else world.params).grammar
    return _with_overrides(grammar) if grammar else catalog()


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

    @property
    def bound(self) -> bool:
        """Je výraz vázaný na slovo (koncovka nebo přiklonka)?"""
        return self.kind == "synthetic" or (self.kind == "periphrastic" and self.stage == "clitic")

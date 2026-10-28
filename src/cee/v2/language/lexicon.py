"""Morfémy, jejich podkladové tvary a fonologický stav kódu (iterace 2)."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from cee.v2.language.segments import Form


@dataclass(frozen=True)
class Morpheme:
    """Morfém s tvarem, jaký měl při vzniku.

    Každý kód si tvar přepisuje sám (fonologizace), proto je tady jen výchozí
    podoba; aktuální podkladový tvar drží :class:`FormStore` kódu.
    """

    id: str
    meaning: str
    form: Form
    #: Tokenová frekvence užití, 0 až 1.
    frequency: float = 0.5
    kind: str = "root"
    origin_group: str | None = None
    origin_tick: int = 0


class FormStore:
    """Podkladové tvary kódu jako copy-on-write vrstvy nad výchozími tvary.

    Neznámý morfém (třeba slovo převzaté od sousedů) má výchozí tvar z
    registru světa; přesnější převzetí podle tvaru u zdroje přinese kontakt
    v M5.
    """

    __slots__ = ("_base", "_own", "_frozen")

    def __init__(self, base: FormStore | None = None):
        self._base = base
        self._own: dict[str, Form] = {}
        self._frozen = False

    def get(self, morpheme_id: str) -> Form | None:
        layer: FormStore | None = self
        while layer is not None:
            form = layer._own.get(morpheme_id)
            if form is not None:
                return form
            layer = layer._base
        return None

    def set(self, morpheme_id: str, form: Form) -> None:
        if self._frozen:
            raise RuntimeError("Zmrazené tvary nelze měnit; použij branch().")
        self._own[morpheme_id] = form

    def freeze(self) -> FormStore:
        self._frozen = True
        return self

    def branch(self) -> FormStore:
        if self._frozen:
            return FormStore(self)
        snapshot = FormStore(self._base)
        snapshot._own = self._own
        snapshot._frozen = True
        self._base = snapshot
        self._own = {}
        return FormStore(snapshot)


@dataclass
class PhonologyState:
    """Co kód udělal se zvukovými procesy.

    ``restructured`` jsou morfémy, které si proces už zapsaly do podkladového
    tvaru. ``closed`` jsou procesy, které po ustálení přestaly být živé: nové
    slovo jimi už neprojde a nepřepsané morfémy zůstanou reliktní výjimkou.
    """

    #: Morfémy, které kód právě užívá jako dominantní slova pro své pojmy.
    vocabulary: set[str] = field(default_factory=set)
    restructured: dict[str, set[str]] = field(default_factory=dict)
    #: Kdy dosáhl změněný tvar procesu 100 %.
    fixed_since: dict[str, int] = field(default_factory=dict)
    closed: set[str] = field(default_factory=set)
    #: Proces → seřazené (potřebný logit, morfém); viz ``restructure``.
    pending: dict[str, list[tuple[float, str]]] = field(default_factory=dict)
    #: Pořadí, ve kterém procesy kód zasáhly: chronologie změn tohoto kódu.
    #: Nezávisí na tom, kdy stejnou změnu vymyslel někdo jinde.
    order: dict[str, int] = field(default_factory=dict)
    #: Roste s každou změnou slovní zásoby nebo podkladových tvarů.
    version: int = 0
    #: Odvozené údaje (statistiky prostředí, hodnocení procesů) s verzí, ze
    #: které vznikly. Nejsou součástí stavu jazyka.
    cache: dict[object, tuple[int, object]] = field(default_factory=dict)

    def branch(self) -> PhonologyState:
        return copy.deepcopy(self)

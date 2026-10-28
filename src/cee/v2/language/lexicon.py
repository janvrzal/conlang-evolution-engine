"""Morfémy, tvary slov a fonologický stav kódu (iterace 2, milníky M2 a M3).

Od M3 je jednotkou slovní zásoby *tvar slova*: kořen v citačním tvaru, nebo
jedna buňka paradigmatu (kmen + koncovka). Tvary se ukládají celé a s
vyznačenou hranicí kmen | koncovka, jak je mluvčí slyší a pamatují si je
(model „slovo a paradigma“, Bybee). Alomorfie, synkretismus i eroze
koncovek pak nejsou zvláštní mechanismy, ale rozdíly mezi uloženými tvary.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from cee.v2.language.segments import Form

MorphemeKind = Literal["root", "affix", "word"]


@dataclass(frozen=True)
class Morpheme:
    """Morfém nebo tvar slova s podobou, jakou měl při vzniku.

    Každý kód si tvar přepisuje sám (fonologizace, analogie), proto je tady
    jen výchozí podoba; aktuální stav drží :class:`FormStore` kódu.
    """

    id: str
    meaning: str
    form: Form
    #: Tokenová frekvence užití, 0 až 1.
    frequency: float = 0.5
    kind: MorphemeKind = "root"
    origin_group: str | None = None
    origin_tick: int = 0
    #: Třída slova kořene (``noun``, ``verb``), ``None`` = neohebné.
    word_class: str | None = None
    #: U tvaru slova: lexém (kořen), buňka paradigmatu, koncovka a index,
    #: kde koncovka začíná.
    lexeme: str | None = None
    cell: str | None = None
    exponent: str | None = None
    boundary: int | None = None
    #: Původ kořene, který vznikl za běhu: změna, pojmy, ze kterých vzešel, a
    #: u odvozeniny kořen základu (pro zpětné tvoření).
    etymology: str | None = None
    sources: tuple[str, ...] = ()
    base: str | None = None

    @property
    def lexeme_id(self) -> str:
        """Lexém, ke kterému tvar patří; citační tvar je lexémem sám."""
        return self.lexeme or self.id


class UnitForm(NamedTuple):
    """Aktuální stav tvaru slova v jednom kódu."""

    form: Form
    #: Kde začíná koncovka (``None`` = bez koncovky).
    boundary: int | None
    exponent: str | None

    @property
    def stem(self) -> Form:
        return self.form if self.boundary is None else self.form[: self.boundary]

    @property
    def ending(self) -> Form:
        return () if self.boundary is None else self.form[self.boundary :]


class FormStore:
    """Podkladové tvary kódu jako copy-on-write vrstvy nad výchozími tvary.

    Neznámý morfém (třeba slovo převzaté od sousedů) má výchozí tvar z
    registru světa; přesnější převzetí podle tvaru u zdroje přinese kontakt
    v M5.
    """

    __slots__ = ("_base", "_own", "_frozen")

    def __init__(self, base: FormStore | None = None):
        self._base = base
        self._own: dict[str, UnitForm] = {}
        self._frozen = False

    def get(self, morpheme_id: str) -> UnitForm | None:
        layer: FormStore | None = self
        while layer is not None:
            unit = layer._own.get(morpheme_id)
            if unit is not None:
                return unit
            layer = layer._base
        return None

    def set(self, morpheme_id: str, unit: UnitForm) -> None:
        if self._frozen:
            raise RuntimeError("Zmrazené tvary nelze měnit; použij branch().")
        self._own[morpheme_id] = unit

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
    #: Pojem → jeho dominantní kořen; kořen → pro kolik pojmů je dominantní.
    #: Posun významu dá jednomu kořeni víc pojmů, a ten pak ze slovní zásoby
    #: nesmí vypadnout, dokud ho užívá aspoň jeden z nich.
    dominant: dict[str, str] = field(default_factory=dict)
    uses: dict[str, int] = field(default_factory=dict)
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
    #: Živé morfologické změny (proměnná → tvar slova, kterého se týká) a ty,
    #: které už si kód zapsal.
    morph_active: dict[str, str] = field(default_factory=dict)
    morph_closed: set[str] = field(default_factory=set)
    #: Odvozené údaje (statistiky prostředí, hodnocení procesů) s verzí, ze
    #: které vznikly. Nejsou součástí stavu jazyka.
    cache: dict[object, tuple[int, object]] = field(default_factory=dict)

    def branch(self) -> PhonologyState:
        return copy.deepcopy(self)

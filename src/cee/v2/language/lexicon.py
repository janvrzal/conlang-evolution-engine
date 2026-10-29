"""Morfémy, tvary slov a fonologický stav kódu (iterace 2, milníky M2 a M3).

Od M3 je jednotkou slovní zásoby *tvar slova*: kořen v citačním tvaru, nebo
jedna buňka paradigmatu (kmen + koncovka). Tvary se ukládají celé a s
vyznačenou hranicí kmen | koncovka, jak je mluvčí slyší a pamatují si je
(model „slovo a paradigma“, Bybee). Alomorfie, synkretismus i eroze
koncovek pak nejsou zvláštní mechanismy, ale rozdíly mezi uloženými tvary.
"""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NamedTuple

import numpy as np

from cee.v2.language.registry import IdRegistry

if TYPE_CHECKING:
    from cee.v2.language.bank import FormBank

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
    #: Linie jazyka, ve které morfém vznikl (protojazyk a jeho potomci).
    #: Morfém z jiné linie je v kódu výpůjčka a jeho tvar se adaptuje.
    language: str = "proto"

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


_TOKENS = itertools.count()


class FormStore:
    """Podkladové tvary kódu jako copy-on-write vrstvy nad výchozími tvary.

    Neznámý morfém (třeba slovo převzaté od sousedů) má výchozí tvar z
    registru světa; přesnější převzetí podle tvaru u zdroje přinese kontakt
    v M5.
    """

    __slots__ = ("_base", "_own", "_frozen", "token", "log", "_registry", "_bank",
                 "_exponents", "form_ids", "boundaries", "exponent_ids")

    def __init__(self, base: FormStore | None = None):
        self._base = base
        self._own: dict[str, UnitForm] = {}
        self._frozen = False
        #: Identita úložiště a deník přepsaných morfémů. Průběžné indexy
        #: (:mod:`cee.v2.language.index`) podle nich dorovnají jen změny.
        self.token = next(_TOKENS)
        self.log: list[str] = []
        self._registry: IdRegistry | None = None
        self._bank: FormBank | None = None
        self._exponents: IdRegistry | None = None
        self.form_ids = np.full(0, -1, dtype=np.int64)
        self.boundaries = np.full(0, -1, dtype=np.int64)
        self.exponent_ids = np.full(0, -1, dtype=np.int64)

    def bind(self, registry: IdRegistry, bank: FormBank, exponents: IdRegistry) -> None:
        """Naváže číselné sloupce na svět; existující zápisy převede beze změny deníku."""
        if self._registry is not None:
            if self._registry is not registry or self._bank is not bank or self._exponents is not exponents:
                raise ValueError("Úložiště je již navázáno na jiný registr nebo banku.")
            return
        if self._base is not None:
            self._base.bind(registry, bank, exponents)
        self._registry, self._bank, self._exponents = registry, bank, exponents
        for morpheme_id, unit in self._own.items():
            self._write_columns(morpheme_id, unit)
        if self._frozen:
            self._freeze_columns()

    def _freeze_columns(self) -> None:
        for array in (self.form_ids, self.boundaries, self.exponent_ids):
            array.flags.writeable = False

    def _write_columns(self, morpheme_id: str, unit: UnitForm) -> None:
        assert self._registry is not None and self._bank is not None and self._exponents is not None
        index = self._registry.register(morpheme_id)
        if index >= len(self.form_ids):
            size = max(index + 1, max(8, len(self.form_ids) * 2))
            for name in ("form_ids", "boundaries", "exponent_ids"):
                old = getattr(self, name)
                grown = np.full(size, -1, dtype=np.int64)
                grown[:len(old)] = old
                setattr(self, name, grown)
        self.form_ids[index] = self._bank.id_of(unit.form)
        self.boundaries[index] = -1 if unit.boundary is None else unit.boundary
        self.exponent_ids[index] = -1 if unit.exponent is None else self._exponents.register(unit.exponent)

    def form_id(self, index: int) -> int:
        """Číslo přepsaného tvaru, nebo −1 pro výchozí tvar."""
        if index < 0:
            raise IndexError(index)
        layer: FormStore | None = self
        while layer is not None:
            if index < len(layer.form_ids):
                found = int(layer.form_ids[index])
                if found >= 0:
                    return found
            layer = layer._base
        return -1

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
        if self._registry is not None:
            self._write_columns(morpheme_id, unit)
        self.log.append(morpheme_id)

    def freeze(self) -> FormStore:
        self._frozen = True
        self._freeze_columns()
        return self

    def branch(self) -> FormStore:
        if self._frozen:
            child = FormStore(self)
            if self._registry is not None:
                assert self._bank is not None and self._exponents is not None
                child.bind(self._registry, self._bank, self._exponents)
            return child
        snapshot = FormStore(self._base)
        snapshot._own = self._own
        snapshot._registry, snapshot._bank, snapshot._exponents = self._registry, self._bank, self._exponents
        snapshot.form_ids, snapshot.boundaries, snapshot.exponent_ids = (
            self.form_ids, self.boundaries, self.exponent_ids
        )
        snapshot._frozen = True
        snapshot._freeze_columns()
        self._base = snapshot
        self._own = {}
        self.form_ids = np.full(0, -1, dtype=np.int64)
        self.boundaries = np.full(0, -1, dtype=np.int64)
        self.exponent_ids = np.full(0, -1, dtype=np.int64)
        child = FormStore(snapshot)
        if self._registry is not None:
            assert self._bank is not None and self._exponents is not None
            child.bind(self._registry, self._bank, self._exponents)
        return child


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
    #: Morfémy, které ve frontě procesu právě čekají (pro rychlé „už tam je?“).
    queued: dict[str, set[str]] = field(default_factory=dict)
    #: Pořadí, ve kterém procesy kód zasáhly: chronologie změn tohoto kódu.
    #: Nezávisí na tom, kdy stejnou změnu vymyslel někdo jinde.
    order: dict[str, int] = field(default_factory=dict)
    #: Roste s každou změnou slovní zásoby nebo podkladových tvarů.
    version: int = 0
    #: Roste jen se změnou slovní zásoby (které slovo je pro který pojem
    #: dominantní), ne s přepisem tvarů. Keše, které na tvarech nezávisí, se
    #: tak nepřepočítávají při každé zvukové změně.
    lexicon_version: int = 0
    #: Živé morfologické změny (proměnná → tvar slova, kterého se týká) a ty,
    #: které už si kód zapsal.
    morph_active: dict[str, str] = field(default_factory=dict)
    morph_closed: set[str] = field(default_factory=set)
    #: Syntetické konstrukce (nové koncovky), které už kód zapsal do tvarů.
    grammar_applied: set[str] = field(default_factory=set)
    #: Odvozené údaje (statistiky prostředí, hodnocení procesů) s verzí, ze
    #: které vznikly. Nejsou součástí stavu jazyka.
    cache: dict[object, tuple[int, object]] = field(default_factory=dict)

    def branch(self) -> PhonologyState:
        return copy.deepcopy(self)

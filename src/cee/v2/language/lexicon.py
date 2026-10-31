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


def next_token() -> int:
    """Jedinečné ID verze tvarů pro zneplatnění indexů."""
    return next(_TOKENS)


#: Od kolika vrstev pod sebou se úložiště tvarů při větvení sloučí.
MAX_LAYERS = 4


class FormStore:
    """Podkladové tvary kódu jako copy-on-write vrstvy nad výchozími tvary.

    Neznámý morfém (třeba slovo převzaté od sousedů) má výchozí tvar z
    registru světa; přesnější převzetí podle tvaru u zdroje přinese kontakt
    v M5.
    """

    __slots__ = ("_base", "_own", "_frozen", "token", "log")

    def __init__(self, base: FormStore | None = None):
        self._base = base
        self._own: dict[str, UnitForm] = {}
        self._frozen = False
        #: Identita úložiště a deník přepsaných morfémů. Průběžné indexy
        #: (:mod:`cee.v2.language.index`) podle nich dorovnají jen změny.
        self.token = next(_TOKENS)
        self.log: list[str] = []

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
        self.log.append(morpheme_id)

    def freeze(self) -> FormStore:
        self._frozen = True
        return self

    def _depth(self) -> int:
        depth, layer = 0, self._base
        while layer is not None:
            depth, layer = depth + 1, layer._base
        return depth

    def _flattened(self) -> FormStore:
        """Zmrazená jediná vrstva se stejným obsahem jako celý řetěz pod ní."""
        chain = []
        layer: FormStore | None = self
        while layer is not None:
            chain.append(layer._own)
            layer = layer._base
        merged: dict[str, UnitForm] = {}
        for own in reversed(chain):
            merged.update(own)
        flat = FormStore()
        flat._own = merged
        flat._frozen = True
        return flat

    def branch(self) -> FormStore:
        # Každé větvení přidá vrstvu; kód větvený mnohokrát (sídlo státu, ze
        # kterého vzniká veřejná skupina v každé vesnici) by jinak při každém
        # čtení tvaru procházel desítky vrstev. Zmrazené vrstvy se nemění,
        # takže sloučení dá při čtení stejný výsledek.
        if self._frozen:
            return FormStore(self._flattened() if self._depth() >= MAX_LAYERS else self)
        snapshot = FormStore(self._base)
        snapshot._own = self._own
        snapshot._frozen = True
        if snapshot._depth() >= MAX_LAYERS:
            snapshot = snapshot._flattened()
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
    #: Append-only vstupy pro inkrementální konzumenty; obsahují jen stabilní ID.
    dominant_log: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    usage_log: list[tuple[str, int, int]] = field(default_factory=list)
    vocabulary_log: list[tuple[str, str]] = field(default_factory=list)
    lifecycle_log: list[tuple[str, str, str]] = field(default_factory=list)
    grammar_log: list[str] = field(default_factory=list)
    grammar_applied_log: list[str] = field(default_factory=list)
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

    def set_dominant(self, concept: str, root: str | None) -> bool:
        """Změní dominantní kořen a zaznamená i přechodný stav bez kořene."""
        old = self.dominant.get(concept)
        if old == root and (root is not None or concept not in self.dominant):
            return False
        if root is None:
            self.dominant.pop(concept, None)
        else:
            self.dominant[concept] = root
        self.dominant_log.append((concept, old, root))
        return True

    def adjust_uses(self, root: str, delta: int, *, missing: int = 0) -> int:
        """Upraví počet pojmů kořene a zaznamená změnu pro frekvenční indexy."""
        old = self.uses.get(root, missing)
        new = old + delta
        if new > 0:
            self.uses[root] = new
        else:
            self.uses.pop(root, None)
        if new != old:
            self.usage_log.append((root, old, new))
        return new

    def enter_vocabulary(self, unit: str) -> bool:
        if unit in self.vocabulary:
            return False
        self.vocabulary.add(unit)
        self.vocabulary_log.append(("enter", unit))
        return True

    def leave_vocabulary(self, unit: str) -> bool:
        if unit not in self.vocabulary:
            return False
        self.vocabulary.remove(unit)
        self.vocabulary_log.append(("leave", unit))
        return True

    def record_lifecycle(self, entity: str, action: str, entity_id: str) -> None:
        self.lifecycle_log.append((entity, action, entity_id))

    def record_grammar(self, variable_id: str) -> None:
        self.grammar_log.append(variable_id)

    def mark_grammar_applied(self, variant_id: str) -> bool:
        if variant_id in self.grammar_applied:
            return False
        self.grammar_applied.add(variant_id)
        self.grammar_applied_log.append(variant_id)
        return True

    def branch(self) -> PhonologyState:
        """Nezávislá kopie stavu pro nový kód (odštěpení, přechod, zjemnění).

        Hodnocení zvukových procesů (``("assessment", proces)`` v keši) se
        nedědí: smějí zastarat o několik kroků, a jejich obsah tak závisí na
        tom, kdy je kód předlohy naposledy spočítal. Nový kód si je spočítá
        sám, takže jeho historie nezávisí na tom, kdo předlohu hodnotil
        (paralelní běh, :mod:`cee.v2.parallel`).
        """
        cache = self.cache
        self.cache = {key: value for key, value in cache.items()
                      if not (isinstance(key, tuple) and key and key[0] == "assessment")}
        try:
            return copy.deepcopy(self)
        finally:
            self.cache = cache

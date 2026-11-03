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
from array import array
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, NamedTuple, Protocol

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.language.bank import FormBank
from cee.v2.language.columns import (
    DominantMap,
    MorphemeCounts,
    MorphemeSet,
    NativePending,
    NativeQueued,
    NativeRestructured,
    ProcessQueue,
    QueueMap,
)
from cee.v2.language.segments import Form
from cee.v2.registry import KINDS, Registry

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


class _FormContext(Protocol):
    """Co úložiště tvarů potřebuje od světa: číslování morfémů a banku tvarů."""

    registry: Registry

    def form_bank(self) -> FormBank: ...


class _PrivateContext:
    """Registr a banka úložiště, které (zatím) nepatří žádnému světu (testy, nový kód)."""

    def __init__(self) -> None:
        self.registry = Registry()
        self.bank: FormBank | None = None

    def form_bank(self) -> FormBank:
        if self.bank is None:
            from cee.v2.language.segments import default_table

            self.bank = FormBank(default_table())
        return self.bank


#: V polích úložiště tvarů: morfém nemá vlastní tvar (platí výchozí z registru světa).
UNSET = -1


class FormStore:
    """Podkladové tvary kódu v polích podle čísla morfému (krok A3).

    Pro každý morfém, jehož tvar se od výchozího liší, drží tři pole
    indexovaná číslem morfému z registru světa (:mod:`cee.v2.registry`):

    - ``form``: číslo tvaru v bance tvarů světa (:class:`FormBank`), −1 = výchozí;
    - ``boundary``: kde začíná koncovka, −1 = bez koncovky;
    - ``exponent``: číslo morfému koncovky, −1 = žádná.

    Metody ``get``/``set``/``branch`` a deník (``token``, ``log``) zůstávají
    jako dřív, jen s textovými ID na povrchu. Neznámý morfém (třeba slovo
    převzaté od sousedů) má výchozí tvar z registru světa; přesnější převzetí
    podle tvaru u zdroje přinese kontakt v M5.

    Úložiště je přibližně tak velké jako počet morfémů, které kód přepsal;
    ``branch`` kopíruje pole, takže potomek nesdílí se zdrojem nic měnitelného
    (banka tvarů jen přibývá a sdílet se smí).
    """

    __slots__ = (
        "_ctx", "_morphemes", "_bank", "_form", "_boundary", "_exponent", "_frozen", "token", "log",
    )

    def __init__(self, context: _FormContext | None = None):
        self._ctx: _FormContext = _PrivateContext() if context is None else context
        self._morphemes = self._ctx.registry.morphemes
        self._bank: FormBank | None = None
        self._form = array("i")
        self._boundary = array("i")
        self._exponent = array("i")
        self._frozen = False
        #: Identita úložiště a deník přepsaných morfémů. Průběžné indexy
        #: (:mod:`cee.v2.language.index`) podle nich dorovnají jen změny.
        self.token = next(_TOKENS)
        self.log: list[str] = []

    # --- napojení na svět ------------------------------------------------------

    @property
    def context(self) -> _FormContext:
        return self._ctx

    def bind(self, context: _FormContext) -> None:
        """Přepne číslování a banku na ty, které patří světu; obsah se přenese.

        Nový kód vzniká s vlastním (prázdným) číslováním a přidáním do světa
        se napojí na jeho registr. Má-li už nějaké tvary, zapíšou se znovu
        podle jmen morfémů.
        """
        if context is self._ctx:
            return
        names = self._morphemes.names
        old_bank = self.bank()
        kept = [
            (names[number], old_bank.forms[form], self._boundary[number],
             None if self._exponent[number] == UNSET else names[self._exponent[number]])
            for number, form in enumerate(self._form) if form != UNSET
        ]
        self._ctx, self._bank = context, None
        self._morphemes = context.registry.morphemes
        self._form, self._boundary, self._exponent = array("i"), array("i"), array("i")
        for name, form, boundary, exponent in kept:
            self._store(name, UnitForm(form, None if boundary == UNSET else boundary, exponent))

    def bank(self) -> FormBank:
        bank = self._bank
        if bank is None:
            bank = self._bank = self._ctx.form_bank()
        return bank

    # --- čtení a zápis -----------------------------------------------------------

    def get(self, morpheme_id: str) -> UnitForm | None:
        number = self._morphemes.numbers.get(morpheme_id)
        if number is None or number >= len(self._form):
            return None
        form = self._form[number]
        if form == UNSET:
            return None
        boundary, exponent = self._boundary[number], self._exponent[number]
        bank = self._bank
        return UnitForm(
            (self.bank() if bank is None else bank).forms[form], None if boundary == UNSET else boundary,
            None if exponent == UNSET else self._morphemes.names[exponent],
        )

    def form(self, morpheme_id: str) -> Form | None:
        """Jen tvar morfému (bez hranice a koncovky), nebo ``None`` při výchozím tvaru."""
        number = self._morphemes.numbers.get(morpheme_id)
        if number is None or number >= len(self._form):
            return None
        form = self._form[number]
        if form == UNSET:
            return None
        bank = self._bank
        return (self.bank() if bank is None else bank).forms[form]

    def form_id(self, morpheme_id: str) -> int:
        """Číslo tvaru v bance, nebo −1 (výchozí tvar); bez sestavení :class:`UnitForm`."""
        number = self._morphemes.numbers.get(morpheme_id)
        if number is None or number >= len(self._form):
            return UNSET
        return self._form[number]  # type: ignore[no-any-return]

    def set(self, morpheme_id: str, unit: UnitForm) -> None:
        if self._frozen:
            raise RuntimeError("Zmrazené tvary nelze měnit; použij branch().")
        self._store(morpheme_id, unit)
        self.log.append(morpheme_id)

    def _store(self, morpheme_id: str, unit: UnitForm) -> None:
        morphemes = self._morphemes
        number = morphemes.intern(morpheme_id)
        exponent = UNSET if unit.exponent is None else morphemes.intern(unit.exponent)
        missing = number + 1 - len(self._form)
        if missing > 0:
            filler = array("i", [UNSET]) * missing
            self._form.extend(filler)
            self._boundary.extend(filler)
            self._exponent.extend(filler)
        self._form[number] = self.bank().id_of(unit.form)
        self._boundary[number] = UNSET if unit.boundary is None else unit.boundary
        self._exponent[number] = exponent

    @property
    def frozen(self) -> bool:
        return self._frozen

    def raw(self) -> tuple[array, array, array]:  # type: ignore[type-arg]
        """Živá pole (tvar, hranice koncovky, koncovka) podle čísla morfému pro jádro v Rustu; nezapisovat."""
        return self._form, self._boundary, self._exponent

    def put(self, number: int, form_id: int, boundary: int, exponent: int) -> None:
        """Totéž co :meth:`set` z čísel: číslo tvaru v bance, hranice (−1 = žádná), číslo koncovky (−1 = žádná)."""
        if self._frozen:
            raise RuntimeError("Zmrazené tvary nelze měnit; použij branch().")
        missing = number + 1 - len(self._form)
        if missing > 0:
            filler = array("i", [UNSET]) * missing
            self._form.extend(filler)
            self._boundary.extend(filler)
            self._exponent.extend(filler)
        self._form[number] = form_id
        self._boundary[number] = boundary
        self._exponent[number] = exponent
        self.log.append(self._morphemes.names[number])

    def freeze(self) -> FormStore:
        self._frozen = True
        return self

    def arrays(self) -> tuple[npt.NDArray[np.int32], npt.NDArray[np.int32], npt.NDArray[np.int32]]:
        """Kopie polí (tvar, hranice koncovky, koncovka) podle čísla morfému; −1 = nenastaveno."""
        return tuple(  # type: ignore[return-value]
            np.array(field, dtype=np.int32) for field in (self._form, self._boundary, self._exponent)
        )

    def branch(self) -> FormStore:
        """Nezávislé úložiště se stejným obsahem; zdroj i potomek pak žijí zvlášť."""
        child = FormStore(self._ctx)
        child._bank = self._bank
        child._form = array("i", self._form)
        child._boundary = array("i", self._boundary)
        child._exponent = array("i", self._exponent)
        return child


@dataclass
class PhonologyState:
    """Co kód udělal se zvukovými procesy.

    ``restructured`` jsou morfémy, které si proces už zapsaly do podkladového
    tvaru. ``closed`` jsou procesy, které po ustálení přestaly být živé: nové
    slovo jimi už neprojde a nepřepsané morfémy zůstanou reliktní výjimkou.

    Slovní zásoba, počty užití, dominantní kořeny a fronty fonologizace jsou
    v polích podle čísel z registru světa (:mod:`cee.v2.language.columns`);
    textové rozhraní (``in``, ``add``, ``get``, ``items``) zůstává.
    Samostatný stav (bez světa) má vlastní registr, ke světu se připojí
    metodou :meth:`bind` při přidání skupiny.
    """

    registry: Registry = field(default_factory=Registry)
    #: Morfémy, které kód právě užívá jako dominantní slova pro své pojmy.
    vocabulary: MorphemeSet = field(init=False)
    #: Pojem → jeho dominantní kořen. Posun významu dá jednomu kořeni víc
    #: pojmů, a ten pak ze slovní zásoby nesmí vypadnout, dokud ho užívá aspoň
    #: jeden z nich (počet pojmů kořene drží ``uses``).
    dominant: DominantMap = field(init=False)
    #: Morfém → pro kolik pojmů je dominantní kořenem (pole podle čísla morfému; chybí = 0).
    uses: MorphemeCounts = field(init=False)
    #: Append-only vstupy pro inkrementální konzumenty; obsahují jen stabilní ID.
    dominant_log: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    usage_log: list[tuple[str, int, int]] = field(default_factory=list)
    vocabulary_log: list[tuple[str, str]] = field(default_factory=list)
    lifecycle_log: list[tuple[str, str, str]] = field(default_factory=list)
    grammar_log: list[str] = field(default_factory=list)
    grammar_applied_log: list[str] = field(default_factory=list)
    restructured: dict[str, MorphemeSet] = field(default_factory=dict)
    #: Kdy dosáhl změněný tvar procesu 100 %.
    fixed_since: dict[str, int] = field(default_factory=dict)
    closed: set[str] = field(default_factory=set)
    #: Proces → fronta fonologizace (potřebný logit a morfém, seřazeno; viz
    #: :class:`ProcessQueue`) a morfémy, které v ní právě čekají (pro rychlé
    #: „už tam je?“).
    pending: QueueMap = field(init=False)
    queued: dict[str, MorphemeSet] = field(default_factory=dict)
    #: Pořadí, ve kterém procesy kód zasáhly: chronologie změn tohoto kódu.
    #: Nezávisí na tom, kdy stejnou změnu vymyslel někdo jinde.
    order: dict[str, int] = field(default_factory=dict)
    #: Stav fronty a dominantních kořenů v Rustu (``cee_core.NativeCode``), nebo
    #: ``None`` (pak ho drží ``pending``, ``queued``, ``restructured`` a ``fixed_since``
    #: v Pythonu). S Rustem jsou ``pending``, ``queued`` a ``restructured`` pohledy
    #: jen ke čtení na tento stav.
    core: Any = field(default=None, init=False, repr=False)
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

    def __post_init__(self) -> None:
        morphemes = self.registry.morphemes
        self.vocabulary = MorphemeSet(morphemes)
        self.dominant = DominantMap(self.registry.concepts, morphemes)
        self.uses = MorphemeCounts(morphemes)
        self.pending = QueueMap(morphemes)
        self.core = native.new_code()
        if self.core is not None:
            self._use_core()

    def _use_core(self) -> None:
        """Pohledy ``pending``, ``queued`` a ``restructured`` na stav v Rustu."""
        self.pending = NativePending(self.core, self.registry)  # type: ignore[assignment]
        self.queued = NativeQueued(self.core, self.registry)  # type: ignore[assignment]
        self.restructured = NativeRestructured(self.core, self.registry)  # type: ignore[assignment]
        self.dominant.listener = self.core.set_root

    def processes_snapshot(self) -> list[dict[str, Any]]:
        """Procesy kódu (živé i uzavřené) v pořadí vzniku, podle jmen (neutrální podoba)."""
        names = self.registry.processes.names
        if self.core is not None:
            found = []
            for number in self.core.processes():
                needed, morphemes = self.core.queue(number) or ([], [])
                found.append({
                    "process": names[number], "live": self.core.status(number) == 1,
                    "queue": [(logit, self.registry.morphemes.names[item]) for logit, item in zip(needed, morphemes)],
                    "done": [self.registry.morphemes.names[item] for item in self.core.done(number)],
                    "fixed_since": self.core.fixed_since(number),
                })
            return found
        return [
            {
                "process": variable_id, "live": variable_id in self.pending,
                "queue": self.pending[variable_id].pairs() if variable_id in self.pending else [],
                "done": list(self.restructured.get(variable_id, ())),
                "fixed_since": self.fixed_since.get(variable_id),
            }
            for variable_id in self._known_processes()
        ]

    def _known_processes(self) -> list[str]:
        """Procesy Pythonového stavu: nejdřív podle pořadí vzniku, pak ostatní podle jména."""
        known = {*self.pending, *self.closed, *self.restructured}
        ordered = [variable_id for variable_id in sorted(self.order, key=self.order.__getitem__) if variable_id in known]
        return ordered + sorted(known.difference(ordered))

    def load_processes(self, procs: list[dict[str, Any]]) -> None:
        """Naplní fronty z neutrální podoby (``processes_snapshot``) do prázdného stavu."""
        registry = self.registry
        if self.core is None:
            for item in procs:
                process = item["process"]
                self.restructured[process] = self.morpheme_set(item["done"]) if item["done"] else self.morpheme_set()
                if item["fixed_since"] is not None:
                    self.fixed_since[process] = item["fixed_since"]
                if item["live"]:
                    self.pending[process] = ProcessQueue(registry.morphemes, item["queue"])
                    self.queued[process] = self.morpheme_set(name for _, name in item["queue"])
            self.restructured = {process: done for process, done in self.restructured.items() if done}
            return
        exported = []
        for item in procs:
            queued = bytearray()
            done = bytearray()
            numbers = [registry.morphemes.intern(name) for _, name in item["queue"]]
            for number in numbers:
                queued.extend(bytes(max(0, number + 1 - len(queued))))
                queued[number] = 1
            for name in item["done"]:
                number = registry.morphemes.intern(name)
                done.extend(bytes(max(0, number + 1 - len(done))))
                done[number] = 1
            exported.append((
                registry.processes.intern(item["process"]), item["live"], False, -1, -1, bytes(queued), bytes(done),
                [logit for logit, _ in item["queue"]], numbers, item["fixed_since"],
            ))
        self.core = native.restore_code((exported, self.core.roots()))
        self._use_core()

    def bind(self, registry: Registry) -> None:
        """Přepne číslování na registr světa; obsah se přenese podle jmen."""
        if registry is self.registry:
            return
        vocabulary = list(self.vocabulary)
        dominant = self.dominant.items()
        uses = list(self.uses.items())
        procs = self.processes_snapshot()
        self.registry = registry
        self.__post_init__()
        self.vocabulary.update(vocabulary)
        for concept, root in dominant:
            self.dominant[concept] = root
        self.uses.update(uses)
        self.load_processes(procs)

    def __getstate__(self) -> dict[str, Any]:
        # Stav v Rustu nelze uložit ani zkopírovat; nese se jako neutrální seznam procesů
        # a po obnově se postaví v tom režimu, ve kterém se obnovuje.
        state = self.__dict__.copy()
        state["_procs"] = self.processes_snapshot()
        if self.core is not None:
            for key in ("core", "pending", "queued", "restructured", "fixed_since"):
                state[key] = None
        else:
            for key in ("pending", "queued", "restructured", "fixed_since"):
                state[key] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        procs = state.pop("_procs")
        self.__dict__.update(state)
        morphemes = self.registry.morphemes
        self.pending = QueueMap(morphemes)
        self.queued, self.restructured, self.fixed_since = {}, {}, {}
        self.core = native.new_code()
        if self.core is not None:
            for concept, root in self.dominant.items():
                self.core.set_root(self.registry.concepts.numbers[concept], morphemes.numbers[root])
            self._use_core()
        self.load_processes(procs)

    def morpheme_set(self, items: Iterable[str] = ()) -> MorphemeSet:
        """Nová množina morfémů nad číslováním tohoto kódu."""
        return MorphemeSet(self.registry.morphemes, items)

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

    def set_fixed_since(self, variable_id: str, tick: int | None) -> None:
        """Kdy dosáhl změněný tvar procesu 100 % (``None`` = není na 100 %); jen pro testy a obnovu stavu."""
        if self.core is not None:
            self.core.set_fixed_since(self.registry.processes.intern(variable_id), tick)
        elif tick is None:
            self.fixed_since.pop(variable_id, None)
        else:
            self.fixed_since[variable_id] = tick

    def uses_of(self, root: str) -> int:
        """Pro kolik pojmů je kořen dominantní (0, když pro žádný)."""
        return self.uses.get(root, 0)  # type: ignore[no-any-return]

    def adjust_uses(self, root: str, delta: int, *, missing: int = 0) -> int:
        """Upraví počet pojmů kořene a zaznamená změnu pro frekvenční indexy."""
        old = self.uses.get(root, missing)
        new = old + delta
        self.uses[root] = new  # nekladný počet položku odebere
        if new != old:
            self.usage_log.append((root, old, new))
        return new  # type: ignore[no-any-return]

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

        Keš (odvozené údaje) se nedědí, nový kód si ji postaví sám. Většina
        keší je čistou funkcí stavu, takže na výsledku to nic nemění (otisky
        stejné); hodnocení zvukových procesů ale smí zastarat o několik kroků,
        a s děděnou keší by historie nového kódu závisela na tom, kdy předlohu
        kdo hodnotil (paralelní běh, :mod:`cee.v2.parallel`). Kopie je i levnější.

        Registr světa se nekopíruje: potomek patří do téhož světa a číslování
        sdílí; pole a fronty se kopírují.
        """
        cache = self.cache
        self.cache = {}
        registry = self.registry
        memo: dict[int, Any] = {id(registry): registry}
        for kind in KINDS:
            numbering = registry.of(kind)
            memo[id(numbering)] = numbering
        try:
            return copy.deepcopy(self, memo)
        finally:
            self.cache = cache

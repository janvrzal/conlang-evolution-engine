"""Tabulky světa jako sloupce (krok A4 přípravy na Rust).

Slovníky objektů světa (``world.morphemes``, ``variants``, ``variables``,
``links``) zůstávají zdrojem pravdy a veřejným API. Vedle nich se udržují
sloupce indexované čísly z registru (:mod:`cee.v2.registry`), nad kterými
budou pracovat číselná jádra:

- :class:`MorphemeTable`, :class:`VariantTable`, :class:`VariableTable` se
  plní při uložení entity do slovníku světa (``RegisteredDict.__setitem__``).
  Entity jsou neměnné, takže se sloupec mění jen přepsáním celé položky;
  přepsání zapíše řádek znovu na stejné číslo;
- :class:`LinkDict` je slovník vazeb, který počítá změny, a z něj se na
  požádání (a jen po změně) staví řídká matice :class:`LinkTable` ve tvaru CSR.

Pravidla jsou stejná jako v registru:

- **čísla nikdy neurčují pořadí**. Řádek č. N je jen místo v poli. Kde engine
  iteruje ve vkládacím pořadí nebo ``sorted``, iteruje dál po slovnících;
  sloupce pořadí vkládání (``position`` u vazeb) a řazení podle řetězců
  (``Numbering.ranks``) dodávají tam, kde by je jádro potřebovalo;
- pole jsou ``array.array`` (čtení z Pythonu vrací ``int`` a ``float``, ne
  numpy skaláry, takže se do historie a otisků nic nového nedostane);
  :meth:`arrays` vrací kopie jako numpy pole, vždy platné k aktuální verzi;
- kopie světa (checkpoint, větev) kopíruje i sloupce; se zdrojem nesdílí nic
  měnitelného (nesdílí se ani keš numpy kopií).

−1 v celočíselném sloupci znamená „není“ (``None``), v ``float64`` sloupci
NaN.
"""

from __future__ import annotations

import math
from array import array
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np
import numpy.typing as npt

from cee.v2.registry import Numbering, Registry

if TYPE_CHECKING:
    from cee.v2.language.lexicon import Morpheme
    from cee.v2.repertoire import Variable, Variant
    from cee.v2.world import Link, World

#: V celočíselných sloupcích: hodnota není (``None``, žádný odkaz).
UNSET = -1

#: Kódy ``Morpheme.kind``, ``Variable.kind`` a ``Link.kind`` (pořadí = kód).
MORPHEME_KINDS = ("root", "affix", "word")
VARIABLE_KINDS = ("process", "lexical", "form", "construction", "prosody")
LINK_KINDS = ("weak", "strong")

#: (jméno, typ pole, výplň) – pole jsou ``array.array`` typů ``i`` (int32), ``b`` (int8), ``d`` (float64).
_Spec = tuple[tuple[str, str, float], ...]

_MORPHEME_SPEC: _Spec = (
    ("present", "b", 0), ("form", "i", UNSET), ("frequency", "d", math.nan), ("kind", "b", -1),
    ("language", "i", UNSET), ("word_class", "i", UNSET), ("cell", "i", UNSET),
    ("lexeme", "i", UNSET), ("exponent", "i", UNSET), ("boundary", "i", UNSET),
)
_VARIANT_SPEC: _Spec = (
    ("present", "b", 0), ("variable", "i", UNSET), ("change", "i", UNSET), ("tick", "i", UNSET),
    ("year", "d", math.nan), ("group", "i", UNSET), ("morpheme", "i", UNSET),
    ("origin", "i", UNSET), ("appeal", "d", math.nan),
)
_VARIABLE_SPEC: _Spec = (
    ("present", "b", 0), ("kind", "b", -1), ("key", "i", UNSET), ("default", "i", UNSET),
)


class _Columns:
    """Společný základ: pojmenovaná pole stejné délky, růst podle čísla řádku, numpy kopie."""

    __slots__ = ("version", "_np")

    spec: ClassVar[_Spec] = ()

    def __init__(self) -> None:
        #: Roste s každým zápisem; numpy kopie a odvozené údaje se podle něj zneplatňují.
        self.version = 0
        self._np: tuple[int, dict[str, npt.NDArray[Any]]] | None = None
        for name, code, _ in self.spec:
            setattr(self, name, array(code))

    def __len__(self) -> int:
        """Počet řádků pole (nejvyšší uložené číslo + 1, včetně neobsazených)."""
        return len(getattr(self, "present"))

    def _grow(self, size: int) -> None:
        for name, code, fill in self.spec:
            column: array = getattr(self, name)  # type: ignore[type-arg]
            missing = size - len(column)
            if missing > 0:
                column.extend(array(code, [fill]) * missing)

    def arrays(self) -> dict[str, npt.NDArray[Any]]:
        """Kopie sloupců jako numpy pole (``int32``, ``int8``, ``float64``), platné k aktuální verzi."""
        cached = self._np
        if cached is None or cached[0] != self.version:
            dtypes = {"i": np.int32, "b": np.int8, "d": np.float64}
            fresh = {
                name: np.array(getattr(self, name), dtype=dtypes[code]) for name, code, _ in self.spec
            }
            cached = self._np = (self.version, fresh)
        return cached[1]

    def __getstate__(self) -> dict[str, Any]:
        # Kopie a pickle nesou jen pole; numpy keš si kopie postaví sama.
        state = {name: getattr(self, name) for name in self._state_names()}
        state["_np"] = None
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        for name, value in state.items():
            setattr(self, name, value)

    def _state_names(self) -> tuple[str, ...]:
        return ("version", *(name for name, _, _ in self.spec))


class MorphemeTable(_Columns):
    """Morfémy podle čísla morfému z registru (``world.registry.morphemes``).

    - ``present``: 1 = morfém je ve slovníku světa (číslo může být v registru
      obsazené i bez uloženého morfému, třeba jako koncovka v ``FormStore``);
    - ``form``: číslo výchozího tvaru v ``FormBank`` světa, −1 = tvar se zatím
      nezařadil do banky (svět bez hláskových tvarů); doplní ho
      ``World.form_id_of``;
    - ``frequency`` (``float64``): tokenová frekvence morfému;
    - ``kind``: kód ``MORPHEME_KINDS`` (0 kořen, 1 koncovka, 2 tvar slova);
    - ``language``: číslo linie jazyka (``languages``);
    - ``word_class``: číslo třídy slova (``word_classes``), −1 = neohebné;
    - ``cell``: číslo buňky paradigmatu (``cells``), −1 = žádná;
    - ``lexeme``: číslo morfému lexému (``Morpheme.lexeme_id``): u tvaru slova
      jeho kořen, u kořene a koncovky on sám, takže není nikdy −1;
    - ``exponent``: číslo morfému koncovky, −1 = žádná;
    - ``boundary``: kde začíná koncovka, −1 = bez koncovky.
    """

    __slots__ = (
        "_world", "present", "form", "frequency", "kind", "language", "word_class", "cell",
        "lexeme", "exponent", "boundary", "languages", "word_classes", "cells",
    )
    spec = _MORPHEME_SPEC

    def __init__(self, world: World) -> None:
        super().__init__()
        self._world = world
        self.languages = Numbering("language")
        self.word_classes = Numbering("word_class")
        self.cells = Numbering("cell")

    def store(self, number: int, morpheme: Morpheme) -> None:
        world = self._world
        numbering = world.registry.morphemes
        lexeme = numbering.intern(morpheme.lexeme_id)
        exponent = UNSET if morpheme.exponent is None else numbering.intern(morpheme.exponent)
        self._grow(max(number, lexeme, exponent) + 1)
        self.present[number] = 1
        self.form[number] = world.form_bank().id_of(morpheme.form) if world.table is not None else UNSET
        self.frequency[number] = morpheme.frequency
        self.kind[number] = MORPHEME_KINDS.index(morpheme.kind)
        self.language[number] = self.languages.intern(morpheme.language)
        self.word_class[number] = (
            UNSET if morpheme.word_class is None else self.word_classes.intern(morpheme.word_class)
        )
        self.cell[number] = UNSET if morpheme.cell is None else self.cells.intern(morpheme.cell)
        self.lexeme[number] = lexeme
        self.exponent[number] = exponent
        self.boundary[number] = UNSET if morpheme.boundary is None else morpheme.boundary
        self.version += 1

    def _state_names(self) -> tuple[str, ...]:
        return (*super()._state_names(), "_world", "languages", "word_classes", "cells")


class VariantTable(_Columns):
    """Varianty podle čísla varianty z registru (``world.registry.variants``).

    - ``variable``: číslo proměnné; ``change``: kód změny, která variantu
      vytvořila (``changes``), −1 = zděděná z protojazyka; ``tick``, ``year``
      (``float64``) a ``group`` (číslo skupiny, −1 = žádná) z ``Origin``;
    - payload lexikální varianty: ``morpheme`` je číslo morfému (−1, když
      varianta morfém nemá), ``origin`` kód ``payload["origin"]``
      (``payload_origins``, −1 = chybí), ``appeal`` (``float64``, NaN = chybí;
      jen svět bez hláskových tvarů).

    Na objektu zůstává zbytek payloadu (``lexeme``, ``process``, ``form``,
    ``rule``, ``strength``, ``construction``) a ``Origin.parent``.
    """

    __slots__ = (
        "_world", "present", "variable", "change", "tick", "year", "group", "morpheme",
        "origin", "appeal", "changes", "payload_origins",
    )
    spec = _VARIANT_SPEC

    def __init__(self, world: World) -> None:
        super().__init__()
        self._world = world
        self.changes = Numbering("change")
        self.payload_origins = Numbering("payload_origin")

    def store(self, number: int, variant: Variant) -> None:
        registry = self._world.registry
        variable = registry.variables.intern(variant.variable)
        origin = variant.origin
        group = UNSET if origin.group is None else registry.groups.intern(origin.group)
        payload = variant.payload
        morpheme = payload.get("morpheme")
        source = payload.get("origin")
        appeal = payload.get("appeal")
        self._grow(number + 1)
        self.present[number] = 1
        self.variable[number] = variable
        self.change[number] = UNSET if origin.change is None else self.changes.intern(origin.change)
        self.tick[number] = origin.tick
        self.year[number] = origin.year
        self.group[number] = group
        self.morpheme[number] = (
            registry.morphemes.intern(morpheme) if isinstance(morpheme, str) else UNSET
        )
        self.origin[number] = UNSET if source is None else self.payload_origins.intern(str(source))
        self.appeal[number] = math.nan if appeal is None else float(appeal)
        self.version += 1

    def _state_names(self) -> tuple[str, ...]:
        return (*super()._state_names(), "_world", "changes", "payload_origins")


class VariableTable(_Columns):
    """Proměnné podle čísla proměnné z registru (``world.registry.variables``).

    ``kind``: kód ``VARIABLE_KINDS``; ``key``: číslo pojmu (``registry.concepts``)
    u lexikálních proměnných, jinak −1; ``default``: číslo výchozí varianty,
    −1 = proměnná výchozí variantu nemá.
    """

    __slots__ = ("_world", "present", "kind", "key", "default")
    spec = _VARIABLE_SPEC

    def __init__(self, world: World) -> None:
        super().__init__()
        self._world = world

    def store(self, number: int, variable: Variable) -> None:
        registry = self._world.registry
        self._grow(number + 1)
        self.present[number] = 1
        self.kind[number] = VARIABLE_KINDS.index(variable.kind)
        self.key[number] = registry.concepts.intern(variable.key) if variable.kind == "lexical" else UNSET
        self.default[number] = UNSET if variable.default is None else registry.variants.intern(variable.default)
        self.version += 1

    def _state_names(self) -> tuple[str, ...]:
        return (*super()._state_names(), "_world")


class WorldColumns:
    """Sloupcové tabulky jednoho světa (morfémy, varianty, proměnné)."""

    __slots__ = ("morphemes", "variants", "variables")

    def __init__(self, world: World) -> None:
        self.morphemes = MorphemeTable(world)
        self.variants = VariantTable(world)
        self.variables = VariableTable(world)

    def table(self, kind: str) -> MorphemeTable | VariantTable | VariableTable | None:
        """Tabulka pro druh entity registru, nebo ``None`` (skupiny, pojmy a procesy tabulku nemají)."""
        return {"morpheme": self.morphemes, "variant": self.variants, "variable": self.variables}.get(kind)


# --- vazby --------------------------------------------------------------------


class LinkTable:
    """Vazby jako řídká matice CSR podle čísel skupin (``world.registry.groups``).

    Řádek *s* (zdroj, skupina se učí) obsahuje položky ``indptr[s]:indptr[s+1]``:

    - ``indices`` (``int32``): číslo cíle (od koho se učí), uvnitř řádku vzestupně;
    - ``strength`` (``float64``) a ``kind`` (``int8``, kód ``LINK_KINDS``);
    - ``source`` (``int32``): řádek každé položky (rozvinuté ``indptr``);
    - ``position`` (``int32``): pořadí položky ve slovníku ``world.links``
      (vkládací pořadí). Číslo skupiny pořadí nerozhoduje: kdo potřebuje
      sčítat či vybírat ve vkládacím pořadí, seřadí položky podle ``position``
      (``np.argsort``), podle řetězců pak přes ``Numbering.ranks``.

    Tabulka je snímek k ``version`` slovníku vazeb; mění-li se vazby, staví
    se znovu (:meth:`LinkDict.table`).
    """

    __slots__ = ("version", "groups", "indptr", "indices", "strength", "kind", "source", "position")

    def __init__(
        self, version: int, groups: int, source: npt.NDArray[np.int32], target: npt.NDArray[np.int32],
        strength: npt.NDArray[np.float64], kind: npt.NDArray[np.int8],
    ) -> None:
        order = np.lexsort((target, source))
        self.version = version
        self.groups = groups
        self.source = source[order]
        self.indices = target[order]
        self.strength = strength[order]
        self.kind = kind[order]
        self.position = order.astype(np.int32)
        counts = np.bincount(self.source, minlength=groups)
        self.indptr = np.concatenate([[0], np.cumsum(counts)]).astype(np.int32)

    def __len__(self) -> int:
        return len(self.indices)

    def row(self, source: int) -> slice:
        return slice(int(self.indptr[source]), int(self.indptr[source + 1]))


class LinkDict(dict):  # type: ignore[type-arg]
    """Slovník vazeb (zdroj, cíl) → ``Link``, který počítá změny a staví z nich CSR.

    Chová se jako obyčejný slovník včetně pořadí vkládání. Každá změna (zápis,
    odebrání, ``update``, ``clear``) zvýší ``version``; ``table()`` postaví
    :class:`LinkTable` znovu jen tehdy, když se verze nebo počet skupin od
    posledního stavění změnily. Kopie slovníku (deepcopy, pickle) se skládá
    z registru a obsahu, tabulku si postaví sama.
    """

    __slots__ = ("_registry", "version", "_table")

    def __init__(self, registry: Registry, items: Any = ()) -> None:
        dict.__init__(self, items)
        self._registry = registry
        self.version = 0
        self._table: LinkTable | None = None

    def __setitem__(self, key: tuple[str, str], value: Link) -> None:
        self.version += 1
        dict.__setitem__(self, key, value)

    def __delitem__(self, key: tuple[str, str]) -> None:
        self.version += 1
        dict.__delitem__(self, key)

    def pop(self, key: Any, *default: Any) -> Any:
        self.version += 1
        return dict.pop(self, key, *default)

    def popitem(self) -> tuple[tuple[str, str], Link]:
        self.version += 1
        return dict.popitem(self)

    def clear(self) -> None:
        self.version += 1
        dict.clear(self)

    def setdefault(self, key: tuple[str, str], default: Any = None) -> Any:
        if key not in self:
            self[key] = default
        return dict.__getitem__(self, key)

    def update(self, source: Any = (), /, **values: Any) -> None:
        self.version += 1
        dict.update(self, source, **values)

    def __ior__(self, source: Any) -> LinkDict:  # type: ignore[override,misc]
        self.update(source)
        return self

    def copy(self) -> dict:  # type: ignore[type-arg,override]
        """Obyčejný slovník (kopie nemá vlastní verzi)."""
        return dict(self)

    def table(self) -> LinkTable:
        """Vazby jako CSR podle čísel skupin; přepočítá se jen po změně vazeb či přibytku skupin."""
        built = self._table
        groups = self._registry.groups
        if built is not None and built.version == self.version and built.groups == len(groups):
            return built
        count = len(self)
        source = np.fromiter((groups.intern(key[0]) for key in self), np.int32, count)
        target = np.fromiter((groups.intern(key[1]) for key in self), np.int32, count)
        strength = np.fromiter((link.strength for link in self.values()), np.float64, count)
        kind = np.fromiter((LINK_KINDS.index(link.kind) for link in self.values()), np.int8, count)
        built = self._table = LinkTable(self.version, len(groups), source, target, strength, kind)
        return built

    def __reduce__(self) -> tuple[Any, ...]:
        return (_restore_links, (self._registry, dict(self)))


def _restore_links(registry: Registry, items: dict[tuple[str, str], Any]) -> LinkDict:
    return LinkDict(registry, items)

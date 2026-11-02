"""Tabulky světa jako sloupce (krok A4 přípravy na Rust).

Slovníky objektů světa (``world.morphemes``, ``variants``, ``variables``)
zůstávají zdrojem pravdy a veřejným API. Vedle nich se udržují
sloupce indexované čísly z registru (:mod:`cee.v2.registry`), nad kterými
budou pracovat číselná jádra:

- :class:`MorphemeTable`, :class:`VariantTable`, :class:`VariableTable` se
  plní při uložení entity do slovníku světa (``RegisteredDict.__setitem__``).
  Entity jsou neměnné, takže se sloupec mění jen přepsáním celé položky;
  přepsání zapíše řádek znovu na stejné číslo.

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

from cee.v2.registry import Numbering

if TYPE_CHECKING:
    from cee.v2.language.lexicon import Morpheme
    from cee.v2.repertoire import Variable, Variant
    from cee.v2.world import World

#: V celočíselných sloupcích: hodnota není (``None``, žádný odkaz).
UNSET = -1

#: Kódy ``Morpheme.kind`` a ``Variable.kind`` (pořadí = kód).
MORPHEME_KINDS = ("root", "affix", "word")
VARIABLE_KINDS = ("process", "lexical", "form", "construction", "prosody")

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

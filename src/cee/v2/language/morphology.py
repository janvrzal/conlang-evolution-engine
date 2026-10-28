"""Paradigmata a morfologické změny tvarů (iterace 3, oblast B; milník M3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cee.v2.language.lexicon import UnitForm
from cee.v2.language.segments import Form

FormOperation = Literal["level", "extend", "prepend", "drop_initial"]


@dataclass(frozen=True)
class Paradigm:
    """Buňky jedné třídy slov; první buňka je citační tvar bez koncovky."""

    word_class: str
    cells: tuple[str, ...]
    #: Váha buňky v užívání: frekvence tvaru = frekvence lexému × váha.
    weights: tuple[float, ...]

    @property
    def citation(self) -> str:
        return self.cells[0]

    def weight(self, cell: str) -> float:
        return self.weights[self.cells.index(cell)]


def unit_id(lexeme_id: str, cell: str, paradigm: Paradigm) -> str:
    """ID tvaru slova; citační tvar sdílí ID s lexémem."""
    return lexeme_id if cell == paradigm.citation else f"{lexeme_id}#{cell}"


@dataclass(frozen=True)
class FormChange:
    """Analogická změna jednoho tvaru slova (hodnota formové proměnné).

    - ``level`` (vyrovnání): kmen buňky se nahradí citačním tvarem lexému,
      koncovka zůstane (*mohu → můžu* je opačný směr, ale stejný princip).
    - ``extend`` (rozšíření vzoru): koncovka buňky se nahradí produktivní
      koncovkou třídy (*brethren → brothers*).
    - ``prepend`` / ``drop_initial`` (reanalýza hranice): hláska se přesune
      mezi přiklonkou a slovem (*a napron → an apron*); týká se všech tvarů
      lexému.
    """

    operation: FormOperation
    unit: str
    exponent: str | None = None
    segment: int | None = None

    @property
    def key(self) -> str:
        key = f"{self.operation}|{self.unit}|{self.exponent or ''}"
        return key if self.segment is None else f"{key}|{self.segment}"

    @property
    def lexeme_wide(self) -> bool:
        return self.operation in ("prepend", "drop_initial")


def level(citation: Form, unit: UnitForm) -> UnitForm:
    return UnitForm(citation + unit.ending, len(citation), unit.exponent)


def extend(unit: UnitForm, ending: Form, exponent: str) -> UnitForm:
    return UnitForm(unit.stem + ending, len(unit.stem), exponent)


def rebracket(unit: UnitForm, operation: FormOperation, segment: int) -> UnitForm | None:
    if operation == "prepend":
        boundary = None if unit.boundary is None else unit.boundary + 1
        return UnitForm((segment, *unit.form), boundary, unit.exponent)
    if unit.form[:1] != (segment,) or len(unit.form) < 3:
        return None
    boundary = None if unit.boundary is None else unit.boundary - 1
    return UnitForm(unit.form[1:], boundary, unit.exponent)

"""Paradigmata a morfologické změny tvarů (iterace 3, oblast B; milník M3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cee.v2.language.lexicon import UnitForm
from cee.v2.language.segments import Form

FormOperation = Literal["level", "extend"]


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
    """

    operation: FormOperation
    unit: str
    exponent: str | None = None

    @property
    def key(self) -> str:
        return f"{self.operation}|{self.unit}|{self.exponent or ''}"


def level(citation: Form, unit: UnitForm) -> UnitForm:
    return UnitForm(citation + unit.ending, len(citation), unit.exponent)


def extend(unit: UnitForm, ending: Form, exponent: str) -> UnitForm:
    return UnitForm(unit.stem + ending, len(unit.stem), exponent)

"""Morfologické změny (iterace 3, oblast B): analogie nad tvary slov."""

from __future__ import annotations

from typing import Mapping, Sequence, cast

import numpy as np

from cee.v2 import morphology
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.morphology import FormChange
from cee.v2.pressures import Actuation, Conformity, Pressure
from cee.v2.pressures.morphological import Conservation, Distinctiveness, Uniformity
from cee.v2.repertoire import Origin, Variable, Variant

MORPH_PRESSURES: Mapping[type[Pressure], float] = {
    Uniformity: 1.0,
    Conservation: 1.0,
    Distinctiveness: 1.0,
    Conformity: 0.1,
    Actuation: 1.0,
}


class AnalogicalChange(Change):
    """Rodič analogických změn: místem je jeden tvar slova."""

    target = "form"
    rate_basis = "generation"
    pressures = MORPH_PRESSURES

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        raise NotImplementedError

    def _sites(self, context: InnovationContext) -> dict[str, FormChange]:
        state = context.code.phonology
        key = ("form-sites", self.kind)
        cached = state.cache.get(key)
        if cached is not None and cached[0] == state.version:
            return cast(dict[str, FormChange], cached[1])
        found = self.candidates(context)
        state.cache[key] = (state.version, found)
        return found

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if context.world.table is None or not context.world.paradigms:
            return ()
        return sorted(self._sites(context))

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        change = self._sites(context)[site]
        _, variant = morphology.register(
            context.world, change, Origin(self.kind, context.tick, context.year, context.group.id)
        )
        return variant


def _word_units(context: InnovationContext) -> list[str]:
    world = context.world
    return [
        unit for unit in sorted(context.code.phonology.vocabulary)
        if world.morphemes[unit].kind == "word"
    ]


class Leveling(AnalogicalChange):
    """Vyrovnání: kmen buňky se srovná s citačním tvarem (alternace zmizí)."""

    kind = "leveling"
    base_rate = 0.004

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        world, code = context.world, context.code
        found = {}
        for unit in _word_units(context):
            if world.unit_of(code, unit).stem != morphology.citation_form(world, code, unit):
                change = FormChange("level", unit)
                found[Variable("form", change.key).id] = change
        return found


class Extension(AnalogicalChange):
    """Rozšíření vzoru: buňka převezme produktivní koncovku své třídy.

    Nabízí se, když buňka nese menšinovou koncovku, nebo když její koncovka
    zvukovými změnami zanikla a buňka splynula s citačním tvarem.
    """

    kind = "extension"
    base_rate = 0.004

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        world, code = context.world, context.code
        stats = morphology.class_stats(world, code)
        found = {}
        for unit in _word_units(context):
            morpheme = world.morphemes[unit]
            assert morpheme.word_class is not None and morpheme.cell is not None
            productive = stats.productive(morpheme.word_class, morpheme.cell)
            if productive is None or not stats.endings.get(productive):
                continue
            current = world.unit_of(code, unit)
            syncretic = current.form == morphology.citation_form(world, code, unit)
            if current.exponent != productive or syncretic:
                change = FormChange("extend", unit, productive)
                found[Variable("form", change.key).id] = change
        return found


MORPHOLOGICAL_CHANGES: tuple[AnalogicalChange, ...] = (Leveling(), Extension())

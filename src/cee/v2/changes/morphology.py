"""Morfologické změny (iterace 3, oblast B): analogie nad tvary slov."""

from __future__ import annotations

from typing import ClassVar, Mapping, Sequence, cast

from cee.v2 import morphology, phases
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.changes.sites import column_totals, native_column
from cee.v2.language.morphology import FormChange
from cee.v2.language.site_index import COL_EXTENSION, COL_LEVELING, site_index
from cee.v2.pressures import Actuation, Conformity, Pressure
from cee.v2.pressures.morphological import Conservation, Distinctiveness, Teachability, Uniformity
from cee.v2.repertoire import Origin, Variable, Variant
from cee.v2.rng import RandomSource

MORPH_PRESSURES: Mapping[type[Pressure], float] = {
    Uniformity: 1.0,
    Conservation: 1.0,
    Distinctiveness: 1.0,
    Teachability: 1.0,
    Conformity: 0.1,
    Actuation: 1.0,
}


class AnalogicalChange(Change):
    """Rodič analogických změn: místem je jeden tvar slova."""

    target = "form"
    rate_basis = "generation"
    pressures = MORPH_PRESSURES

    #: Zda změna je regularizace: násobí se jí ``params.analogy_l2_boost``
    #: (reanalýza hranice ji vypíná, není to přehnané zobecnění).
    regularizing: ClassVar[bool] = True

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        raise NotImplementedError

    def rate_scale(self, context: InnovationContext) -> float:
        if not self.regularizing:
            return 1.0
        return 1.0 + context.world.params.analogy_l2_boost * context.code.l2_share

    def _form_changes(self, context: InnovationContext) -> list[FormChange]:
        """Místa vyrovnání či rozšíření z indexu míst světa v pořadí řetězcových ID míst."""
        world, code = context.world, context.code
        index = site_index(world)
        index.refresh(world, [context])
        extension = self.kind == "extension"
        return [
            FormChange("extend", unit, exponent) if extension else FormChange("level", unit)
            for unit, exponent in index.candidates(world, code, extension)
        ]

    def _sites(self, context: InnovationContext) -> dict[str, FormChange]:
        if native_column(self) is not None:
            return {
                Variable("form", change.key).id: change
                for change in (self._form_changes(context) if self._active(context) else ())
            }
        state = context.code.phonology
        key = ("form-sites", self.kind)
        cached = state.cache.get(key)
        if cached is not None and cached[0] == state.version:
            return cast(dict[str, FormChange], cached[1])
        found = self.candidates(context)
        state.cache[key] = (state.version, found)
        return found

    def _active(self, context: InnovationContext) -> bool:
        return context.world.table is not None and bool(context.world.paradigms)

    def total_rate(self, context: InnovationContext) -> float:
        if native_column(self) is not None:
            return column_totals(self, [context])[0]
        if not self._active(context):
            return 0.0
        count = len(self._sites(context))
        if count == 0:
            return 0.0
        return float(phases.uniform_rate(self.base_rate, count, self.rate_scale(context)))

    def total_rates(self, contexts: Sequence[InnovationContext]) -> list[float]:
        if native_column(self) is None:
            return super().total_rates(contexts)
        return column_totals(self, contexts)

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if not self._active(context):
            return ()
        if native_column(self) is not None:
            return [Variable("form", change.key).id for change in self._form_changes(context)]
        state = context.code.phonology
        key = ("form-sites-sorted", self.kind)
        cached = state.cache.get(key)
        if cached is None or cached[0] != state.version:
            cached = state.cache[key] = (state.version, sorted(self._sites(context)))
        return cast(list[str], cached[1])

    def _site_change(self, context: InnovationContext, site: str) -> FormChange:
        """Změna místa: u vyrovnání a rozšíření ze jména místa (``form:level|tvar|``), jinak z kandidátů."""
        if native_column(self) is None:
            return self._sites(context)[site]
        prefix = f"form:{'extend' if self.kind == 'extension' else 'level'}|"
        if not site.startswith(prefix):
            raise KeyError(site)
        rest = site[len(prefix):]
        if self.kind == "extension":
            unit, _, exponent = rest.rpartition("|")
            return FormChange("extend", unit, exponent)
        return FormChange("level", rest[:-1])

    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        change = self._site_change(context, site)
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
    site_column = COL_LEVELING
    base_rate = 0.004

    def _candidate(self, context: InnovationContext, unit: str) -> FormChange | None:
        if context.world.unit_of(context.code, unit).stem != morphology.citation_form(
            context.world, context.code, unit
        ):
            return FormChange("level", unit)
        return None

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        found = {}
        for unit in _word_units(context):
            change = self._candidate(context, unit)
            if change is not None:
                found[Variable("form", change.key).id] = change
        return found


class Extension(AnalogicalChange):
    """Rozšíření vzoru: buňka převezme produktivní koncovku své třídy.

    Nabízí se, když buňka nese menšinovou koncovku, nebo když její koncovka
    zvukovými změnami zanikla a buňka splynula s citačním tvarem.
    """

    kind = "extension"
    site_column = COL_EXTENSION
    base_rate = 0.004

    def _candidate(
        self, context: InnovationContext, unit: str, stats: morphology.ClassStats
    ) -> FormChange | None:
        world, code = context.world, context.code
        morpheme = world.morphemes[unit]
        assert morpheme.word_class is not None and morpheme.cell is not None
        productive = stats.productive(morpheme.word_class, morpheme.cell)
        if productive is None or not stats.endings.get(productive):
            return None
        current = world.unit_of(code, unit)
        syncretic = current.form == morphology.citation_form(world, code, unit)
        if current.exponent != productive or syncretic:
            return FormChange("extend", unit, productive)
        return None

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        stats = morphology.class_stats(context.world, context.code)
        found = {}
        for unit in _word_units(context):
            change = self._candidate(context, unit, stats)
            if change is not None:
                found[Variable("form", change.key).id] = change
        return found


class Rebracketing(AnalogicalChange):
    """Reanalýza hranice mezi záporkou a slovesem (typ *a napron → an apron*).

    Záporka stojí před slovesem a vyslovuje se s ním dohromady. Končí-li na
    souhlásku a sloveso začíná samohláskou, může si generace souhlásku
    přiřadit ke slovesu; končí-li záporka samohláskou, může naopak počáteční
    souhlásku slovesa připsat záporce.
    """

    kind = "rebracketing"
    # Sporadický jev: jednotky případů na jazyk za tisíciletí.
    base_rate = 0.0002
    regularizing = False  # reanalýza hranice není regularizace

    def candidates(self, context: InnovationContext) -> dict[str, FormChange]:
        from cee.v2 import syntax

        world, code = context.world, context.code
        if world.table is None:
            return {}
        # Záporka před slovesem (šablona negation katalogu gramatických funkcí).
        negations = [
            current for entry in syntax.functions(world, "negation")
            if (current := syntax.dominant(world, context.group.id, entry.id)) is not None
            and current.kind == "pre"
        ]
        if not negations:
            return {}
        particle = syntax.particle_form(world, code, negations[0].source)
        if not particle:
            return {}
        state = code.phonology
        cached = state.cache.get("dominant-verb-roots")
        if cached is not None and cached[0] == state.lexicon_version:
            verb_roots = cast(tuple[str, ...], cached[1])
        else:
            verb_roots = tuple(
                root
                for root in sorted(set(state.dominant.values()))
                if world.morphemes[root].word_class == "verb"
            )
            state.cache["dominant-verb-roots"] = (state.lexicon_version, verb_roots)
        found = {}
        for root in verb_roots:
            form = world.form_of(code, root)
            if not form:
                continue
            if not world.table.is_vowel(particle[-1]) and world.table.is_vowel(form[0]):
                change = FormChange("prepend", root, segment=particle[-1])
            elif world.table.is_vowel(particle[-1]) and not world.table.is_vowel(form[0]) and len(form) >= 3:
                change = FormChange("drop_initial", root, segment=form[0])
            else:
                continue
            found[Variable("form", change.key).id] = change
        return found


MORPHOLOGICAL_CHANGES: tuple[AnalogicalChange, ...] = (Leveling(), Extension(), Rebracketing())

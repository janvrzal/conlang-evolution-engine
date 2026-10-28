"""Morfologie v běžící simulaci: tvary paradigmatu a analogie (milník M3).

Zvukové změny z M2 pracují s celými tvary slov, takže alomorfie, eroze
koncovek i synkretismus vznikají samy. Tady jsou jen dvě věci navíc:

- **Produktivita**: která koncovka je pro danou buňku třídy nejčastější
  (podle počtu lexémů, ne tokenů). Nové slovo dostane produktivní koncovku.
- **Analogie**: varianta tvaru jedné buňky (vyrovnání kmene, rozšíření
  koncovky) se šíří jako každá jiná. Když ve skupině převáží, nová generace
  si tvar zapíše a změna se uzavře.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cee.v2.history import History
from cee.v2.language.lexicon import Morpheme, UnitForm
from cee.v2.language.morphology import FormChange, extend, level, rebracket, unit_id
from cee.v2.language.segments import Form
from cee.v2.repertoire import Origin, Variable, Variant

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Nad tímto podílem si nová generace analogický tvar zapíše.
ANALOGY_THRESHOLD = 0.85


@dataclass(frozen=True)
class ClassStats:
    """Kolik lexémů nese kterou koncovku, a jak ta koncovka dnes zní."""

    #: (třída, buňka) → koncovka → počet lexémů
    exponents: dict[tuple[str, str], Counter[str]]
    #: koncovka → nejčastější dnešní podoba koncovky
    endings: dict[str, Form]

    def productive(self, word_class: str, cell: str) -> str | None:
        counts = self.exponents.get((word_class, cell))
        if not counts:
            return None
        return max(sorted(counts), key=lambda exponent: counts[exponent])

    def share(self, word_class: str, cell: str, exponent: str | None) -> float:
        counts = self.exponents.get((word_class, cell))
        if not counts or exponent is None:
            return 0.0
        return counts[exponent] / sum(counts.values())


def class_stats(world: World, code: Code) -> ClassStats:
    state = code.phonology
    cached = state.cache.get("class-stats")
    if cached is not None and cached[0] == state.version:
        return cast(ClassStats, cached[1])
    exponents: dict[tuple[str, str], Counter[str]] = {}
    shapes: dict[str, Counter[Form]] = {}
    for morpheme_id in sorted(state.vocabulary):
        morpheme = world.morphemes[morpheme_id]
        if morpheme.kind != "word" or morpheme.word_class is None or morpheme.cell is None:
            continue
        unit = world.unit_of(code, morpheme_id)
        if unit.exponent is None:
            continue
        exponents.setdefault((morpheme.word_class, morpheme.cell), Counter())[unit.exponent] += 1
        shapes.setdefault(unit.exponent, Counter())[unit.ending] += 1
    endings = {
        exponent: max(sorted(counter), key=lambda shape: counter[shape])
        for exponent, counter in shapes.items()
    }
    stats = ClassStats(exponents, endings)
    state.cache["class-stats"] = (state.version, stats)
    return stats


def units_of(world: World, code: Code, root_id: str) -> list[str]:
    """Tvary slova (citační tvar a buňky paradigmatu) pro lexém.

    Lexém, který vznikl až během simulace, dostane tvary buněk podle
    produktivní koncovky kódu, kde je poprvé potřeba.
    """
    root = world.morphemes[root_id]
    if root.word_class is None or root.word_class not in world.paradigms:
        return [root_id]
    paradigm = world.paradigms[root.word_class]
    result = [root_id]
    for cell in paradigm.cells[1:]:
        unit = unit_id(root_id, cell, paradigm)
        if unit not in world.morphemes:
            stats = class_stats(world, code)
            exponent = stats.productive(root.word_class, cell)
            if exponent is None:
                continue
            ending = stats.endings.get(exponent, world.morphemes[exponent].form)
            stem = world.form_of(code, root_id)
            world.morphemes[unit] = Morpheme(
                id=unit, meaning=root.meaning, form=stem + ending,
                frequency=root.frequency * paradigm.weight(cell), kind="word",
                word_class=root.word_class, lexeme=root_id, cell=cell, exponent=exponent,
                boundary=len(stem), origin_group=root.origin_group, origin_tick=root.origin_tick,
            )
        result.append(unit)
    return result


def register(world: World, change: FormChange, origin: Origin) -> tuple[str, Variant]:
    """Formová proměnná analogické změny; tatáž změna = tatáž proměnná."""
    from cee.v2.phonology import changed_id, none_id

    variable_id = Variable("form", change.key).id
    if variable_id not in world.variables:
        world.variables[variable_id] = Variable("form", change.key, default=none_id(variable_id))
        world.variants[none_id(variable_id)] = Variant(
            none_id(variable_id), variable_id, {"form": None}, Origin(None, origin.tick, origin.year, None)
        )
        world.variants[changed_id(variable_id)] = Variant(
            changed_id(variable_id), variable_id, {"form": variable_id}, origin
        )
        world.form_changes[variable_id] = change
    return variable_id, world.variants[changed_id(variable_id)]


def citation_form(world: World, code: Code, unit: str) -> Form:
    return world.form_of(code, world.morphemes[unit].lexeme_id)


def apply_form_change(world: World, code: Code, change: FormChange) -> UnitForm | None:
    """Analogický tvar podle dnešního stavu kódu, nebo ``None``, když nic nezmění."""
    unit = world.unit_of(code, change.unit)
    if change.lexeme_wide:
        assert change.segment is not None
        return rebracket(unit, change.operation, change.segment)
    if change.operation == "level":
        citation = citation_form(world, code, change.unit)
        return None if unit.stem == citation else level(citation, unit)
    assert change.exponent is not None
    ending = class_stats(world, code).endings.get(change.exponent)
    if ending is None or (unit.exponent == change.exponent and unit.ending == ending):
        return None
    return extend(unit, ending, change.exponent)


def activate(world: World, code: Code, variable_id: str) -> None:
    state = code.phonology
    if variable_id not in state.morph_closed:
        state.morph_active.setdefault(variable_id, world.form_changes[variable_id].unit)


def restructure(world: World, group_id: str, tick: int, history: History, year: float) -> None:
    """Analogie, která ve skupině převážila, se zapíše do tvaru slova."""
    from cee.v2.phonology import active_processes, changed_share, requeue

    code = world.groups[group_id].main_code
    state = code.phonology
    for variable_id, unit in sorted(state.morph_active.items()):
        share = changed_share(world, group_id, variable_id)
        if share <= 0:
            del state.morph_active[variable_id]
            continue
        if share < ANALOGY_THRESHOLD:
            continue
        change = world.form_changes[variable_id]
        del state.morph_active[variable_id]
        state.morph_closed.add(variable_id)
        targets = units_of(world, code, unit) if change.lexeme_wide else [unit]
        rewritten = False
        for target in targets:
            new = (
                rebracket(world.unit_of(code, target), change.operation, change.segment)
                if change.lexeme_wide and change.segment is not None
                else apply_form_change(world, code, change)
            )
            if new is None:
                continue
            code.forms.set(target, new)
            rewritten = True
            for process in active_processes(state, world):
                requeue(world, code, process, target)
        if not rewritten:
            continue
        state.version += 1
        morpheme = world.morphemes[unit]
        history.record(
            "analogy", tick, year, group=group_id, variable=variable_id,
            operation=change.operation, concept=morpheme.meaning, cell=morpheme.cell,
        )


@dataclass(frozen=True)
class FormAssessment:
    #: Jak moc změna sjednotí paradigma nebo posílí produktivní vzor (−1 až 1).
    gain: float
    #: Frekvence lexému.
    frequency: float
    #: Tvar buňky zní stejně jako citační tvar před změnou / po ní.
    syncretic_before: bool
    syncretic_after: bool


def assess(world: World, group_id: str, variable_id: str) -> FormAssessment | None:
    code = world.groups[group_id].main_code
    state = code.phonology
    key = ("form-assessment", variable_id)
    cached = state.cache.get(key)
    if cached is not None and cached[0] == state.version:
        return cast(FormAssessment | None, cached[1])
    change = world.form_changes[variable_id]
    result = None
    new = apply_form_change(world, code, change)
    if new is not None:
        morpheme = world.morphemes[change.unit]
        citation = citation_form(world, code, change.unit)
        current = world.unit_of(code, change.unit)
        if change.operation == "level":
            gain = 1.0
        elif change.lexeme_wide:
            gain = 0.0
        else:
            stats = class_stats(world, code)
            assert morpheme.word_class is not None and morpheme.cell is not None
            gain = stats.share(morpheme.word_class, morpheme.cell, change.exponent) - stats.share(
                morpheme.word_class, morpheme.cell, current.exponent
            )
        result = FormAssessment(
            gain=gain,
            frequency=world.usage_frequency(code, morpheme.lexeme_id),
            syncretic_before=current.form == citation,
            syncretic_after=new.form == citation,
        )
    state.cache[key] = (state.version, result)
    return result

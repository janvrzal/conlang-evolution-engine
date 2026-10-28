"""Kontakt jazyků (iterace 3, oblast E, a iterace 4; milník M5).

Kontakt nemá vlastní mechanismus šíření. Varianta jiného jazyka vstupuje do
proměnné stejně jako varianta sousedního dialektu, jen přes dva filtry
přenositelnosti (Thomason & Kaufman 1988):

- **Výpůjčka** (mluvčí si drží svůj jazyk a přejímají z cizího): nejsnáz
  slova, a to spíš vzácná než základní (Haspelmath & Tadmor 2009); stavba
  jazyka jen výjimečně.
- **Interference** (dospělí se učí cizí kód a nesou do něj svůj první
  jazyk): naopak hlavně výslovnost a konstrukce, slov málo.

Vícejazyčná komunita je v simulaci víc skupin (jedna na kód) se společným
``community``. Přechod na jiný jazyk je přesun mluvčích mezi nimi podle
modelu Abramse a Strogatze (2003); kód, kterému se přestanou učit děti,
vymře a v novém jazyce po něm zůstane substrát.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from cee.v2.history import History
from cee.v2.language.segments import Form

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Filtr výpůjček podle typu proměnné. U slov se násobí ``1 − frekvence
#: pojmu``: základní slovní zásoba se půjčuje nejméně.
BORROWING = {"lexical": 0.5, "process": 0.1, "construction": 0.1, "form": 0.0}
#: Filtr interference při osvojování druhého jazyka.
INTERFERENCE = {"lexical": 0.05, "process": 1.0, "construction": 1.0, "form": 0.0}
#: Jak velkou část vstupu L2 kódu tvoří první jazyk jeho mluvčích, když se
#: ho učí všichni až v dospělosti (``l2_share`` = 1).
INTERFERENCE_WEIGHT = 0.5

#: Abrams & Strogatz (2003): rychlost přechodu je úměrná statusu cílového
#: jazyka a podílu jeho mluvčích na ``SHIFT_EXPONENT``.
SHIFT_RATE = 1.0
SHIFT_EXPONENT = 1.31
#: Pod tímto podílem užívání v komunitě se kód nepředává dětem (iterace 4).
CHILD_THRESHOLD = 0.2
#: Skupina s menší populací zaniká (poslední mluvčí).
LAST_SPEAKERS = 1.0


def borrowing_factor(world: World, variable_id: str) -> float:
    variable = world.variables[variable_id]
    factor = BORROWING.get(variable.kind, 0.0)
    if variable.kind == "lexical":
        factor *= 1.0 - world.concept_frequency(variable.key)
    return factor


def interference_factor(world: World, variable_id: str) -> float:
    return INTERFERENCE.get(world.variables[variable_id].kind, 0.0)


def language_of(world: World, group_id: str) -> str:
    return world.groups[group_id].main_code.language


# --- adaptace výpůjček ----------------------------------------------------


def inventory(world: World, code: Code) -> tuple[int, ...]:
    """Hlásky, které kód ve slovní zásobě užívá (seřazené)."""
    state = code.phonology
    cached = state.cache.get("inventory")
    if cached is not None and cached[0] == state.version:
        return tuple(cached[1])  # type: ignore[arg-type]
    found = sorted({segment for unit in state.vocabulary for segment in world.form_of(code, unit)})
    state.cache["inventory"] = (state.version, found)
    return tuple(found)


def adapt(world: World, code: Code, form: Form) -> Form:
    """Cizí hlásky se nahradí nejbližší hláskou příjemce (podle rysů PanPhonu)."""
    assert world.table is not None
    native = inventory(world, code)
    if not native:
        return form
    vectors = world.table.vectors
    pool = np.array(native)
    result = []
    for segment in form:
        if segment in native:
            result.append(segment)
            continue
        distance = (vectors[pool] != vectors[segment]).sum(axis=1)
        # Samohláska zůstane samohláskou, souhláska souhláskou.
        same = np.array([world.table.is_vowel(int(other)) == world.table.is_vowel(segment) for other in pool])
        distance = np.where(same, distance, distance + 1000)
        result.append(int(pool[int(np.argmin(distance))]))
    return tuple(result)


def donor_form(world: World, group_id: str, morpheme_id: str) -> Form:
    """Tvar slova u nejbližšího mluvčího jeho jazyka, jak ho skupina slyší."""
    language = world.morphemes[morpheme_id].language
    group = world.groups[group_id]
    candidates = [(link.strength, link.target) for link in world.neighbors(group_id)]
    if group.main_code.l1_source in world.groups:
        candidates.append((1.0, group.main_code.l1_source))
    for _, donor in sorted(candidates, key=lambda item: (-item[0], item[1])):
        code = world.groups[donor].main_code
        if code.language == language and morpheme_id in code.phonology.vocabulary:
            return world.form_of(code, morpheme_id)
    return world.morphemes[morpheme_id].form


def adopt(world: World, group_id: str, morpheme_id: str) -> None:
    """Cizí kořen vstupuje do slovní zásoby: převezme a adaptuje jeho tvar.

    Tvary buněk paradigmatu pak dostane výpůjčka podle produktivních koncovek
    příjemce (:func:`cee.v2.morphology.units_of`), jak to dělají reálné
    jazyky (*pizza → pizzy*).
    """
    code = world.groups[group_id].main_code
    morpheme = world.morphemes[morpheme_id]
    if morpheme.language == code.language or code.forms.get(morpheme_id) is not None:
        return
    from cee.v2.language.lexicon import UnitForm

    code.forms.set(morpheme_id, UnitForm(adapt(world, code, donor_form(world, group_id, morpheme_id)), None, None))


# --- komunity: přistěhovalectví a přechod na jiný jazyk ------------------


def community_step(world: World, dt: float, tick: int, year: float, history: History) -> bool:
    """Jeden krok demografie kódů; vrací ``True``, když nějaká skupina zanikla."""
    removed = False
    for group_id in world.group_ids():
        group = world.groups[group_id]
        code = group.main_code
        renewal = min(1.0, dt / group.generation_years)
        source = code.l1_source if code.l1_source in world.groups else None
        if source is None:
            # Stárnoucí L2 mluvčí nahradí děti, které se kód učí od narození;
            # přistěhovalci podíl drží.
            code.l2_share += renewal * (group.immigration - code.l2_share)
            continue
        removed |= _shift(world, group_id, source, renewal, tick, year, history)
    return removed


def _shift(
    world: World, target_id: str, source_id: str, renewal: float, tick: int, year: float, history: History
) -> bool:
    """Mluvčí skupiny ``source`` přecházejí na kód skupiny ``target``."""
    source, target = world.groups[source_id], world.groups[target_id]
    total = source.population + target.population
    share = target.population / total
    status = target.prestige / (target.prestige + source.prestige)
    moving = source.population * renewal * SHIFT_RATE * status * share**SHIFT_EXPONENT
    births = 0.0
    if source.population / total < CHILD_THRESHOLD:
        # Děti se starý kód už neučí: rodí se do nového.
        if source.transmitted:
            source.transmitted = False
            history.record("transmission_stopped", tick, year, group=source_id, language=source.main_code.language)
        births = source.population * renewal
    moving = min(moving, source.population - births)
    learners = target.main_code.l2_share * target.population * (1.0 - renewal) + moving
    remaining = source.population - moving - births
    target_population = target.population + moving + births
    target.main_code.l2_share = min(1.0, learners / target_population)
    target.population = max(1, round(target_population))
    if remaining < LAST_SPEAKERS:
        world.materialize(source_id)
        world.remove_group(source_id)
        target.main_code.l1_source = None
        # Komunita už mluví novým kódem od dětství: je to zase obyčejná
        # skupina se svou dřívější otevřeností.
        target.openness = source.openness
        history.record(
            "language_shift", tick, year, group=source_id, into=target_id,
            language=source.main_code.language, target_language=target.main_code.language,
        )
        return True
    source.population = max(1, round(remaining))
    return False

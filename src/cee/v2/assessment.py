"""Hodnocení zvukového procesu nad slovní zásobou jednoho kódu.

Jazykové tlaky (iterace 3) potřebují vědět, co by změna se slovní zásobou
udělala: kolik slov zasáhne, kolik nových homofonů vytvoří, jestli slova
nezkrátí pod únosnou mez, jak změní slabičnou stavbu a rozložení vokálů.
Hodnocení se počítá z podkladových tvarů a drží se, dokud se slovní zásoba
kódu podstatně nezmění; je to přibližné, ale levné.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cee.v2.language.processes import Process
from cee.v2.language.segments import Form, SegmentTable

if TYPE_CHECKING:
    from cee.v2.world import World

#: Hodnocení se přepočítá nejdřív po tolika krocích, i když se slovní zásoba mění.
STALE_TICKS = 8
#: Hodnotí se nejčastější slova; funkční zátěž nesou hlavně ona a cena
#: hodnocení tak nezávisí na velikosti slovníku.
SAMPLE_WORDS = 120


@dataclass(frozen=True)
class ProcessAssessment:
    #: Podíl tokenové frekvence slovní zásoby, kterého se změna týká.
    coverage: float
    #: Frekvenčně vážené nové dvojice homofonů vůči celé slovní zásobě.
    merge_mass: float
    #: Podíl zasažených slov (váženě), která klesnou na dvě hlásky a méně.
    short_share: float
    #: Průměrná změna příznakovosti slabičné stavby zasažených slov.
    markedness_delta: float
    #: Změna průměrné vzdálenosti nejbližších vokálů v systému.
    dispersion_delta: float


NEUTRAL = ProcessAssessment(0.0, 0.0, 0.0, 0.0, 0.0)


def markedness(form: Form, table: SegmentTable) -> float:
    """Hrubá příznakovost slabičné stavby: shluky, koncové souhlásky, hiát.

    Polosamohláska vedle samohlásky patří k jádru slabiky (dvojhláska *je*,
    *aw*), ne do souhláskového shluku.
    """
    vocalic = [
        table.is_vowel(segment)
        or (
            table.sonority(segment) == 3
            and any(
                0 <= other < len(form) and table.is_vowel(form[other])
                for other in (index - 1, index + 1)
            )
        )
        for index, segment in enumerate(form)
    ]
    score = 0.0
    run = 0
    seen = False
    for index, is_vocalic in enumerate(vocalic):
        if is_vocalic:
            if run:
                score += max(0, run - 1) if not seen else max(0, run - 2)
            elif seen and table.is_vowel(form[index]) and index and table.is_vowel(form[index - 1]):
                score += 0.5  # hiát
            run = 0
            seen = True
        else:
            run += 1
    if run:
        score += 0.4 * run + max(0, run - 1)
    return score


def _nearest(vowel: int, others: set[int], table: SegmentTable) -> float:
    height, back, rounded = table.vowel_coordinates(vowel)
    distances = [
        math.sqrt((height - h) ** 2 + (back - b) ** 2 + 0.25 * (rounded - r) ** 2)
        for h, b, r in (table.vowel_coordinates(other) for other in sorted(others) if other != vowel)
    ]
    return min(distances, default=0.0)


def _dispersion_gain(
    process: Process, before: set[int], after: set[int], table: SegmentTable
) -> float:
    """O kolik se nový vokál vzdálí od sousedů oproti vokálu, ze kterého vznikl.

    Hodnotí se jen nový kontrast v přízvučné či neutrální pozici. Splynutí
    s existujícím vokálem tu není ani ziskem, ani ztrátou — jeho cenu nese
    funkční zátěž. V nepřízvučné slabice se kontrasty neutralizují samy a
    natlačení vokálů tam nevadí (redukce na ə).
    """
    if process.stress == "unstressed" or process.segment is None or not table.is_vowel(process.segment):
        return 0.0
    output = process.segment
    if output in before:
        return 0.0
    sources = [vowel for vowel in before if vowel in process.target]
    if not sources:
        return 0.0
    return _nearest(output, after, table) - max(_nearest(source, before, table) for source in sources)


@dataclass(frozen=True)
class _Vocabulary:
    forms: dict[str, Form]
    frequency: dict[str, float]
    owners: dict[Form, list[str]]
    total: float
    vowels: Counter[int]


def _vocabulary(world: World, group_id: str) -> _Vocabulary:
    code = world.groups[group_id].main_code
    state = code.phonology
    cached = state.cache.get("vocabulary")
    if cached is not None and cached[0] == state.version:
        return cast(_Vocabulary, cached[1])
    assert world.table is not None
    chosen = sorted(
        state.vocabulary, key=lambda morpheme: (-world.morphemes[morpheme].frequency, morpheme)
    )[:SAMPLE_WORDS]
    forms = {morpheme: world.form_of(code, morpheme) for morpheme in sorted(chosen)}
    owners: dict[Form, list[str]] = {}
    vowels: Counter[int] = Counter()
    for morpheme, form in forms.items():
        owners.setdefault(form, []).append(morpheme)
        vowels.update(segment for segment in form if world.table.is_vowel(segment))
    frequency = {morpheme: max(0.01, world.morphemes[morpheme].frequency) for morpheme in forms}
    vocabulary = _Vocabulary(forms, frequency, owners, sum(frequency.values()) or 1.0, vowels)
    state.cache["vocabulary"] = (state.version, vocabulary)
    return vocabulary


def assess(world: World, group_id: str, variable_id: str, tick: int) -> ProcessAssessment:
    code = world.groups[group_id].main_code
    state = code.phonology
    key = ("assessment", variable_id)
    cached = state.cache.get(key)
    if cached is not None:
        version, value = cached
        stored_tick, stored = cast(tuple[int, ProcessAssessment], value)
        if version == state.version or tick - stored_tick < STALE_TICKS:
            return stored
    result = _assess(world, group_id, variable_id)
    state.cache[key] = (state.version, (tick, result))
    return result


def _assess(world: World, group_id: str, variable_id: str) -> ProcessAssessment:
    table = world.table
    if table is None:
        return NEUTRAL
    code = world.groups[group_id].main_code
    process = world.processes[variable_id]
    vocabulary = _vocabulary(world, group_id)
    if not vocabulary.forms:
        return NEUTRAL
    affected: dict[str, Form] = {}
    for morpheme, form in vocabulary.forms.items():
        changed = process.apply(form, table, code.stress_rule)
        if changed is not None:
            affected[morpheme] = changed
    if not affected:
        return NEUTRAL
    frequency = vocabulary.frequency
    affected_mass = sum(frequency[morpheme] for morpheme in affected)

    merge = 0.0
    new_owners: dict[Form, list[str]] = {}
    for morpheme, form in affected.items():
        new_owners.setdefault(form, []).append(morpheme)
    for form, movers in new_owners.items():
        # Dvojice, která dřív zněla různě a teď splyne: se slovem, které změna
        # nezasáhla, nebo s jiným zasaženým slovem s jiným původním tvarem.
        stayers = [other for other in vocabulary.owners.get(form, []) if other not in affected]
        for morpheme in movers:
            merge += sum(math.sqrt(frequency[morpheme] * frequency[other]) for other in stayers)
        for index, first in enumerate(movers):
            for second in movers[index + 1 :]:
                if vocabulary.forms[first] != vocabulary.forms[second]:
                    merge += math.sqrt(frequency[first] * frequency[second])

    short = sum(
        frequency[morpheme] for morpheme, form in affected.items()
        if len(form) <= 2 and len(form) < len(vocabulary.forms[morpheme])
    )
    marked = sum(
        frequency[morpheme] * (markedness(form, table) - markedness(vocabulary.forms[morpheme], table))
        for morpheme, form in affected.items()
    )
    vowels_after = Counter(vocabulary.vowels)
    for morpheme, form in affected.items():
        vowels_after.subtract(segment for segment in vocabulary.forms[morpheme] if table.is_vowel(segment))
        vowels_after.update(segment for segment in form if table.is_vowel(segment))
    before = {vowel for vowel, count in vocabulary.vowels.items() if count > 0}
    after = {vowel for vowel, count in vowels_after.items() if count > 0}
    return ProcessAssessment(
        coverage=affected_mass / vocabulary.total,
        merge_mass=merge / vocabulary.total,
        short_share=short / affected_mass,
        markedness_delta=marked / affected_mass,
        dispersion_delta=_dispersion_gain(process, before, after, table),
    )

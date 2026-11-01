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

import numpy as np
import numpy.typing as npt

from cee.v2.language.assessment_index import clipped_frequencies, top_words
from cee.v2.language.processes import Process, StressRule
from cee.v2.language.segments import Form, SegmentTable

if TYPE_CHECKING:
    from cee.v2.language.lexicon import Morpheme
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


def _shapes_vowels(process: Process, table: SegmentTable) -> bool:
    """Může změna ovlivnit rozptyl vokálů? Stejné podmínky jako :func:`_dispersion_gain`."""
    return (
        process.stress != "unstressed" and process.segment is not None
        and table.is_vowel(process.segment)
    )


def _dispersion_gain(
    process: Process, before: set[int], after: set[int], table: SegmentTable
) -> float:
    """O kolik se nový vokál vzdálí od sousedů oproti vokálu, ze kterého vznikl.

    Hodnotí se jen nový kontrast v přízvučné či neutrální pozici. Splynutí
    s existujícím vokálem tu není ani ziskem, ani ztrátou — jeho cenu nese
    funkční zátěž. V nepřízvučné slabice se kontrasty neutralizují samy a
    natlačení vokálů tam nevadí (redukce na ə).
    """
    if not _shapes_vowels(process, table):
        return 0.0
    assert process.segment is not None
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
    #: Čísla tvarů v bance, morfémy a frekvence, ve stejném pořadí jako ``forms``.
    ids: npt.NDArray[np.int64]
    morphemes: list[str]
    weights: npt.NDArray[np.float64]


def _vocabulary_reference(world: World, group_id: str) -> _Vocabulary:
    code = world.groups[group_id].main_code
    state = code.phonology
    cached = state.cache.get("vocabulary-reference")
    if cached is not None and cached[0] == state.version:
        return cast(_Vocabulary, cached[1])
    assert world.table is not None
    # Výběr vzorku závisí jen na slovní zásobě, ne na tvarech.
    picked = state.cache.get("vocabulary-sample")
    if picked is not None and picked[0] == state.lexicon_version:
        chosen = cast(list[str], picked[1])
    else:
        chosen = top_words(world, code, SAMPLE_WORDS)
        state.cache["vocabulary-sample"] = (state.lexicon_version, chosen)
    forms = {morpheme: world.form_of(code, morpheme) for morpheme in sorted(chosen)}
    owners: dict[Form, list[str]] = {}
    vowels: Counter[int] = Counter()
    for morpheme, form in forms.items():
        owners.setdefault(form, []).append(morpheme)
        vowels.update(segment for segment in form if world.table.is_vowel(segment))
    frequency = clipped_frequencies(world, code, forms)
    ids = world.form_bank().ids_of(list(forms.values()))
    morphemes = list(forms)
    weights = np.array([frequency[morpheme] for morpheme in morphemes], dtype=np.float64)
    vocabulary = _Vocabulary(
        forms, frequency, owners, sum(frequency.values()) or 1.0, vowels, ids, morphemes, weights
    )
    state.cache["vocabulary-reference"] = (state.version, vocabulary)
    return vocabulary


def _vocabulary(world: World, group_id: str) -> _Vocabulary:
    """Vzorek s přírůstkovým dorovnáním změněných tvarů podle deníku."""
    code = world.groups[group_id].main_code
    state = code.phonology
    cached = state.cache.get("vocabulary")
    from cee.v2.language.assessment_index import AssessmentVocabularyIndex

    item = state.cache.get("assessment-vocabulary-index")
    index = (cast(AssessmentVocabularyIndex, item[1]) if item is not None
             else AssessmentVocabularyIndex())
    if cached is not None and cached[0] == state.version:
        return cast(_Vocabulary, cached[1])
    assert world.table is not None
    result = index.sync(world, code)
    state.cache["assessment-vocabulary-index"] = (state.version, index)
    state.cache["vocabulary"] = (state.version, result)
    return result

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


def assess_many(world: World, group_ids: list[str], variable_id: str, tick: int) -> list[ProcessAssessment]:
    """Hodnocení jednoho procesu ve více skupinách; zastaralá se spočítají naráz."""
    found: list[ProcessAssessment | None] = []
    stale: list[int] = []
    key = ("assessment", variable_id)
    for position, group_id in enumerate(group_ids):
        state = world.groups[group_id].main_code.phonology
        cached = state.cache.get(key)
        if cached is not None:
            version, value = cached
            stored_tick, stored = cast(tuple[int, ProcessAssessment], value)
            if version == state.version or tick - stored_tick < STALE_TICKS:
                found.append(stored)
                continue
        found.append(None)
        stale.append(position)
    if stale:
        fresh = _assess_batch(world, [group_ids[position] for position in stale], variable_id)
        for position, result in zip(stale, fresh):
            found[position] = result
            state = world.groups[group_ids[position]].main_code.phonology
            state.cache[key] = (state.version, (tick, result))
    return cast(list[ProcessAssessment], found)


def _assess_batch_reference(world: World, group_ids: list[str], variable_id: str) -> list[ProcessAssessment]:
    """Hodnocení procesu ve více skupinách jako operace nad maticí (skupiny × slova vzorku)."""
    table = world.table
    if table is None:
        return [NEUTRAL] * len(group_ids)
    process = world.processes[variable_id]
    bank = world.form_bank()
    results: list[ProcessAssessment] = [NEUTRAL] * len(group_ids)
    by_rule: dict[str, list[int]] = {}
    for position, group_id in enumerate(group_ids):
        by_rule.setdefault(world.groups[group_id].main_code.stress_rule, []).append(position)
    for rule, positions in sorted(by_rule.items()):
        vocabularies = [_vocabulary_reference(world, group_ids[position]) for position in positions]
        width = max((len(vocabulary.ids) for vocabulary in vocabularies), default=0)
        if width == 0:
            continue
        rows = len(positions)
        ids = np.full((rows, width), -1, dtype=np.int64)
        weights = np.zeros((rows, width))
        for row, vocabulary in enumerate(vocabularies):
            ids[row, : len(vocabulary.ids)] = vocabulary.ids
            weights[row, : len(vocabulary.ids)] = vocabulary.weights
        valid = ids >= 0
        changed = np.full((rows, width), -1, dtype=np.int64)
        changed[valid] = bank.process_table(process, cast(StressRule, rule)).results(ids[valid])
        hit = changed >= 0
        if not hit.any():
            continue
        mass = (weights * hit).sum(axis=1)
        safe_ids, safe_new = np.where(valid, ids, 0), np.where(hit, changed, 0)
        old_lengths, new_lengths = bank.lengths(safe_ids), bank.lengths(safe_new)
        short = (weights * (hit & (new_lengths <= 2) & (new_lengths < old_lengths))).sum(axis=1)

        def compute(form: Form) -> float:
            return markedness(form, table)

        marked_new = np.zeros((rows, width))
        marked_old = np.zeros((rows, width))
        marked_new[hit] = bank.values("markedness", changed[hit], compute)
        marked_old[hit] = bank.values("markedness", ids[hit], compute)
        marked = (weights * (marked_new - marked_old)).sum(axis=1)
        # Nový homofon: dvojice, která po změně zní stejně a předtím nezněla.
        # Výplň řádků dostane různá záporná čísla, aby se za homofony nepočítala.
        final = np.where(hit, changed, ids)
        final = np.where(valid, final, -1 - np.arange(width)[None, :])
        ordered = np.sort(final, axis=1)
        collides = (ordered[:, 1:] == ordered[:, :-1]).any(axis=1) & hit.any(axis=1)
        vowels = _shapes_vowels(process, table)
        for row, (position, vocabulary) in enumerate(zip(positions, vocabularies)):
            if mass[row] <= 0:
                continue
            group_id = group_ids[position]
            merge = 0.0
            if collides[row]:
                values, counts = np.unique(final[row], return_counts=True)
                for value in values[counts > 1].tolist():
                    members = np.flatnonzero(final[row] == value).tolist()
                    for index, first in enumerate(members):
                        for second in members[index + 1 :]:
                            if ids[row, first] != ids[row, second]:
                                merge += _pair(
                                    world, vocabulary.frequency, vocabulary.morphemes[first],
                                    vocabulary.morphemes[second], group_id,
                                )
            before = {vowel for vowel, count in vocabulary.vowels.items() if count > 0}
            after = before
            if vowels:
                vowels_after = Counter(vocabulary.vowels)
                for index in np.flatnonzero(hit[row]).tolist():
                    morpheme = vocabulary.morphemes[index]
                    vowels_after.subtract(
                        segment for segment in vocabulary.forms[morpheme] if table.is_vowel(segment)
                    )
                    vowels_after.update(
                        segment for segment in bank.forms[int(changed[row, index])] if table.is_vowel(segment)
                    )
                after = {vowel for vowel, count in vowels_after.items() if count > 0}
            results[position] = ProcessAssessment(
                coverage=float(mass[row]) / vocabulary.total,
                merge_mass=merge / vocabulary.total,
                short_share=float(short[row]) / float(mass[row]),
                markedness_delta=float(marked[row]) / float(mass[row]),
                dispersion_delta=_dispersion_gain(process, before, after, table),
            )
    return results


def _assess_batch(world: World, group_ids: list[str], variable_id: str) -> list[ProcessAssessment]:
    """Hodnocení procesu ve více skupinách jako operace nad maticí (skupiny × slova vzorku)."""
    table = world.table
    if table is None:
        return [NEUTRAL] * len(group_ids)
    process = world.processes[variable_id]
    bank = world.form_bank()
    results: list[ProcessAssessment] = [NEUTRAL] * len(group_ids)
    by_rule: dict[str, list[int]] = {}
    for position, group_id in enumerate(group_ids):
        by_rule.setdefault(world.groups[group_id].main_code.stress_rule, []).append(position)
    for rule, positions in sorted(by_rule.items()):
        vocabularies = [_vocabulary(world, group_ids[position]) for position in positions]
        width = max((len(vocabulary.ids) for vocabulary in vocabularies), default=0)
        if width == 0:
            continue
        rows = len(positions)
        ids = np.full((rows, width), -1, dtype=np.int64)
        weights = np.zeros((rows, width))
        for row, vocabulary in enumerate(vocabularies):
            ids[row, : len(vocabulary.ids)] = vocabulary.ids
            weights[row, : len(vocabulary.ids)] = vocabulary.weights
        valid = ids >= 0
        changed = np.full((rows, width), -1, dtype=np.int64)
        changed[valid] = bank.process_table(process, cast(StressRule, rule)).results(ids[valid])
        hit = changed >= 0
        if not hit.any():
            continue
        mass = (weights * hit).sum(axis=1)
        safe_ids, safe_new = np.where(valid, ids, 0), np.where(hit, changed, 0)
        old_lengths, new_lengths = bank.lengths(safe_ids), bank.lengths(safe_new)
        short = (weights * (hit & (new_lengths <= 2) & (new_lengths < old_lengths))).sum(axis=1)

        def compute(form: Form) -> float:
            return markedness(form, table)

        marked_new = np.zeros((rows, width))
        marked_old = np.zeros((rows, width))
        marked_new[hit] = bank.values("markedness", changed[hit], compute)
        marked_old[hit] = bank.values("markedness", ids[hit], compute)
        marked = (weights * (marked_new - marked_old)).sum(axis=1)
        # Nový homofon: dvojice, která po změně zní stejně a předtím nezněla.
        # Výplň řádků dostane různá záporná čísla, aby se za homofony nepočítala.
        final = np.where(hit, changed, ids)
        final = np.where(valid, final, -1 - np.arange(width)[None, :])
        ordered = np.sort(final, axis=1)
        collides = (ordered[:, 1:] == ordered[:, :-1]).any(axis=1) & hit.any(axis=1)
        vowels = _shapes_vowels(process, table)
        for row, (position, vocabulary) in enumerate(zip(positions, vocabularies)):
            if mass[row] <= 0:
                continue
            group_id = group_ids[position]
            merge = 0.0
            if collides[row]:
                values, counts = np.unique(final[row], return_counts=True)
                for value in values[counts > 1].tolist():
                    members = np.flatnonzero(final[row] == value).tolist()
                    for index, first in enumerate(members):
                        for second in members[index + 1 :]:
                            if ids[row, first] != ids[row, second]:
                                merge += _pair(
                                    world, vocabulary.frequency, vocabulary.morphemes[first],
                                    vocabulary.morphemes[second], group_id,
                                )
            before = {vowel for vowel, count in vocabulary.vowels.items() if count > 0}
            after = before
            if vowels:
                vowels_after = Counter(vocabulary.vowels)
                for index in np.flatnonzero(hit[row]).tolist():
                    morpheme = vocabulary.morphemes[index]
                    vowels_after.subtract(
                        segment for segment in vocabulary.forms[morpheme] if table.is_vowel(segment)
                    )
                    vowels_after.update(
                        segment for segment in bank.forms[int(changed[row, index])] if table.is_vowel(segment)
                    )
                after = {vowel for vowel, count in vowels_after.items() if count > 0}
            results[position] = ProcessAssessment(
                coverage=float(mass[row]) / vocabulary.total,
                merge_mass=merge / vocabulary.total,
                short_share=float(short[row]) / float(mass[row]),
                markedness_delta=float(marked[row]) / float(mass[row]),
                dispersion_delta=_dispersion_gain(process, before, after, table),
            )
    return results

# Váhy splynutí buněk paradigmatu jsou data světa (``world.params``:
# ``paradigm_merge_weight``, ``redundant_merge_weight``).


def _pair(world: World, frequency: dict[str, float], first: str, second: str, group_id: str) -> float:
    mass = math.sqrt(frequency[first] * frequency[second])
    a, b = world.morphemes[first], world.morphemes[second]
    if a.lexeme_id == b.lexeme_id:
        mass *= world.params.paradigm_merge_weight
        if _redundant_cell(world, group_id, a) or _redundant_cell(world, group_id, b):
            mass *= world.params.redundant_merge_weight
    return mass


def _redundant_cell(world: World, group_id: str, morpheme: Morpheme) -> bool:
    from cee.v2 import syntax

    if morpheme.cell is None:
        return False
    entry = syntax.function_of_cell(morpheme.word_class, morpheme.cell)
    return entry is not None and syntax.compensated(world, group_id, entry.id)


def _assess(world: World, group_id: str, variable_id: str) -> ProcessAssessment:
    table = world.table
    if table is None:
        return NEUTRAL
    code = world.groups[group_id].main_code
    process = world.processes[variable_id]
    vocabulary = _vocabulary(world, group_id)
    if not vocabulary.forms:
        return NEUTRAL
    # Celý vzorek naráz jako pole: výsledek procesu jedním vyhledáním v
    # tabulce procesu (proces se na každý různý tvar aplikuje jednou za běh),
    # součty jako operace nad poli.
    bank = world.form_bank()
    ids = vocabulary.ids
    results = bank.process_table(process, code.stress_rule).results(ids)
    hit = results >= 0
    if not hit.any():
        return NEUTRAL
    weights = vocabulary.weights[hit]
    old, new = ids[hit], results[hit]
    affected_mass = float(weights.sum())

    # Nový homofon je dvojice, která po změně zní stejně a předtím nezněla.
    final = ids.copy()
    final[hit] = new
    merge = 0.0
    values, counts = np.unique(final, return_counts=True)
    for value in values[counts > 1].tolist():
        members = np.flatnonzero(final == value).tolist()
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                if ids[first] != ids[second]:
                    merge += _pair(
                        world, vocabulary.frequency, vocabulary.morphemes[first],
                        vocabulary.morphemes[second], group_id,
                    )

    new_lengths, old_lengths = bank.lengths(new), bank.lengths(old)
    short = float(weights[(new_lengths <= 2) & (new_lengths < old_lengths)].sum())

    def compute(form: Form) -> float:
        return markedness(form, table)

    marked = float((weights * (bank.values("markedness", new, compute) - bank.values("markedness", old, compute))).sum())
    affected = {
        vocabulary.morphemes[index]: bank.forms[result]
        for index, result in zip(np.flatnonzero(hit).tolist(), new.tolist())
    } if _shapes_vowels(process, table) else {}
    before = {vowel for vowel, count in vocabulary.vowels.items() if count > 0}
    after = before
    if _shapes_vowels(process, table):
        # Rozložení vokálů po změně je potřeba jen pro změny, které tvoří
        # vokál; u ostatních je zisk rozptylu nulový bez ohledu na něj.
        vowels_after = Counter(vocabulary.vowels)
        for morpheme, form in affected.items():
            vowels_after.subtract(segment for segment in vocabulary.forms[morpheme] if table.is_vowel(segment))
            vowels_after.update(segment for segment in form if table.is_vowel(segment))
        after = {vowel for vowel, count in vowels_after.items() if count > 0}
    return ProcessAssessment(
        coverage=affected_mass / vocabulary.total,
        merge_mass=merge / vocabulary.total,
        short_share=short / affected_mass,
        markedness_delta=marked / affected_mass,
        dispersion_delta=_dispersion_gain(process, before, after, table),
    )

"""Hodnocení zvukového procesu nad slovní zásobou jednoho kódu.

Jazykové tlaky (iterace 3) potřebují vědět, co by změna se slovní zásobou
udělala: kolik slov zasáhne, kolik nových homofonů vytvoří, jestli slova
nezkrátí pod únosnou mez, jak změní slabičnou stavbu a rozložení vokálů.
Hodnocení se počítá z podkladových tvarů a drží se, dokud se slovní zásoba
kódu podstatně nezmění; je to přibližné, ale levné.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, cast

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.language.assessment_index import (
    AssessmentVocabularyIndex,
    Vocabulary,
    _count_vowels,
    clipped_frequencies,
    index_of,
    selection,
)
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


def _new_pairs(final: npt.NDArray[np.int64], ids: npt.NDArray[np.int64]) -> list[tuple[int, int]]:
    """Dvojice pozic vzorku (první < druhá), které po změně znějí stejně a předtím neznělo.

    ``final`` jsou tvary po změně, ``ids`` před ní (stejná pozice = stejný morfém). Pořadí je
    vzestupné podle (první, druhá), tedy podle pořadí slov ve vzorku (řazeném podle jména morfému),
    a na číslech tvarů v bance nezávisí. Součet cen dvojic (``merge_mass``) tak nezmění ani to,
    že banka drží víc tvarů nebo v jiném pořadí.
    """
    values, counts = np.unique(final, return_counts=True)
    pairs: list[tuple[int, int]] = []
    for value in values[counts > 1].tolist():
        members = np.flatnonzero(final == value).tolist()
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                if ids[first] != ids[second]:
                    pairs.append((first, second))
    pairs.sort()
    return pairs


def _vocabulary_reference(world: World, group_id: str) -> Vocabulary:
    """Vzorek od začátku, bez přírůstkového indexu (reference pro testy); pamatuje se podle verze kódu."""
    code = world.groups[group_id].main_code
    state = code.phonology
    cached = state.cache.get("vocabulary-reference")
    if cached is not None and cached[0] == state.version:
        return cast(Vocabulary, cached[1])
    table = world.table
    assert table is not None
    # Výběr vzorku závisí jen na slovní zásobě, ne na tvarech.
    chosen = sorted(selection(world, code, SAMPLE_WORDS))
    numbering = world.registry.morphemes
    numbers = np.array([numbering.intern(unit) for unit in chosen], dtype=np.int32)
    frequency = clipped_frequencies(world, code, chosen)
    ids = np.array([world.form_id_of(code, unit) for unit in chosen], dtype=np.int64)
    vowels = np.zeros(len(table.vowel_mask), dtype=np.int64)
    bank = world.form_bank()
    for form_id in ids.tolist():
        _count_vowels(vowels, bank.forms[form_id], table.vowel_mask, 1)
    weights = np.array([frequency[unit] for unit in chosen], dtype=np.float64)
    vocabulary = Vocabulary(numbers, ids, weights, sum(frequency.values()) or 1.0, vowels)
    state.cache["vocabulary-reference"] = (state.version, vocabulary)
    return vocabulary


def _vocabulary(world: World, group_id: str) -> Vocabulary:
    """Vzorek s přírůstkovým dorovnáním změněných tvarů podle deníku."""
    code = world.groups[group_id].main_code
    state = code.phonology
    cached = state.cache.get("vocabulary")
    if cached is not None and cached[0] == state.version:
        return cast(Vocabulary, cached[1])
    assert world.table is not None
    item = state.cache.get("assessment-vocabulary-index")
    index = cast(AssessmentVocabularyIndex, item[1]) if item is not None else AssessmentVocabularyIndex()
    result = index.sync(world, code)
    state.cache["assessment-vocabulary-index"] = (state.version, index)
    state.cache["vocabulary"] = (state.version, result)
    return result


def assess(world: World, group_id: str, variable_id: str, tick: int) -> ProcessAssessment:
    return assess_many(world, [group_id], variable_id, tick)[0]


def assess_many(world: World, group_ids: list[str], variable_id: str, tick: int) -> list[ProcessAssessment]:
    """Hodnocení jednoho procesu ve více skupinách; zastaralá se spočítají naráz.

    Uložená hodnocení a vzorky drží index světa (:func:`cee.v2.language.assessment_index.index_of`),
    s Rustem v Rustu: tlaky v přenosu (``pressures_native``) čtou tytéž hodnoty.
    """
    return cast(list[ProcessAssessment], index_of(world).assess_many(world, list(group_ids), variable_id, tick))


def _assess_batch_reference(world: World, group_ids: list[str], variable_id: str) -> list[ProcessAssessment]:
    """Hodnocení procesu ve více skupinách nad maticí (skupiny × slova vzorku), vzorek od začátku."""
    return _assess_matrix(world, group_ids, variable_id, _vocabulary_reference)


def _assess_batch(
    world: World, group_ids: list[str], variable_id: str,
    vocabulary_of: Callable[[World, str], Vocabulary] | None = None,
) -> list[ProcessAssessment]:
    """Hodnocení procesu ve více skupinách; s Rustem počítá matici jádro, jinak Python."""
    vocabulary_of = vocabulary_of or _vocabulary
    if world.table is not None and world.form_bank()._native is not None and native.sums_match():
        return _assess_batch_native(world, group_ids, variable_id, vocabulary_of)
    return _assess_matrix(world, group_ids, variable_id, vocabulary_of)


def _assess_batch_native(
    world: World, group_ids: list[str], variable_id: str,
    vocabulary_of: Callable[[World, str], Vocabulary] | None = None,
) -> list[ProcessAssessment]:
    """Totéž co :func:`_assess_batch_python`, matici (skupiny × slova vzorku) počítá Rust.

    Python zůstává zdrojem pravdy o vzorku slov a jejich frekvencích; Rust dostane
    čísla tvarů a váhy po řádcích a vrátí součty (sčítá párově jako ``numpy``, po
    celé šířce matice), dvojice nových homofonů vzestupně podle pozic a samohlásky před
    změnou a po ní. Cenu dvojic (:func:`_pair`) a zisk rozptylu vokálů
    (:func:`_dispersion_gain`) počítá dál Python.
    """
    table = world.table
    assert table is not None
    vocabulary_of = vocabulary_of or _vocabulary
    process = world.processes[variable_id]
    bank = world.form_bank()
    results: list[ProcessAssessment] = [NEUTRAL] * len(group_ids)
    by_rule: dict[str, list[int]] = {}
    for position, group_id in enumerate(group_ids):
        by_rule.setdefault(world.groups[group_id].main_code.stress_rule, []).append(position)
    for rule, positions in sorted(by_rule.items()):
        vocabularies = [vocabulary_of(world, group_ids[position]) for position in positions]
        sizes = [len(vocabulary.ids) for vocabulary in vocabularies]
        width = max(sizes, default=0)
        if width == 0:
            continue
        offsets = np.zeros(len(sizes) + 1, dtype=np.int64)
        np.cumsum(sizes, out=offsets[1:])
        raw = bank.assess_rows(
            process, cast(StressRule, rule),
            np.concatenate([vocabulary.ids for vocabulary in vocabularies]),
            np.concatenate([vocabulary.weights for vocabulary in vocabularies]),
            offsets, width, _shapes_vowels(process, table),
        )

        def pair_mass(row: int, first: int, second: int) -> float:
            return _pair(world, vocabularies[row], first, second, group_ids[positions[row]])

        found = assessments_from_rows(raw, [vocabulary.total for vocabulary in vocabularies], pair_mass, process, table)
        for position, assessment in zip(positions, found):
            results[position] = assessment
    return results


def assessments_from_rows(
    raw: tuple[Any, ...], totals: list[float], pair_mass: Callable[[int, int, int], float], process: Process,
    table: SegmentTable,
) -> list[ProcessAssessment]:
    """Hodnocení jednotlivých řádků matice ze součtů, které vrátil Rust (``assess_rows``).

    ``totals`` jsou úhrnné frekvence slovníků řádků, ``pair_mass(řádek, první,
    druhá)`` cena dvojice nových homofonů. Řádek, kterého se změna netýká,
    dostane :data:`NEUTRAL`.
    """
    (mass, short, marked, pair_counts, pair_first, pair_second,
     before_counts, before_flat, after_counts, after_flat) = raw
    pair_ends = np.cumsum(pair_counts).tolist()
    before_ends, after_ends = np.cumsum(before_counts).tolist(), np.cumsum(after_counts).tolist()
    first_list, second_list = pair_first.tolist(), pair_second.tolist()
    before_list, after_list = before_flat.tolist(), after_flat.tolist()
    vowels = _shapes_vowels(process, table)
    found: list[ProcessAssessment] = []
    for row, total in enumerate(totals):
        row_mass = float(mass[row])
        if row_mass <= 0:
            found.append(NEUTRAL)
            continue
        merge = 0.0
        for index in range(pair_ends[row] - pair_counts[row], pair_ends[row]):
            merge += pair_mass(row, first_list[index], second_list[index])
        before: set[int] = set()
        after: set[int] = set()
        if vowels:
            before = set(before_list[before_ends[row] - before_counts[row]:before_ends[row]])
            after = set(after_list[after_ends[row] - after_counts[row]:after_ends[row]])
        found.append(ProcessAssessment(
            coverage=row_mass / total,
            merge_mass=merge / total,
            short_share=float(short[row]) / row_mass,
            markedness_delta=float(marked[row]) / row_mass,
            dispersion_delta=_dispersion_gain(process, before, after, table),
        ))
    return found


def _assess_batch_python(world: World, group_ids: list[str], variable_id: str) -> list[ProcessAssessment]:
    """Hodnocení procesu ve více skupinách jako operace nad maticí (skupiny × slova vzorku)."""
    return _assess_matrix(world, group_ids, variable_id, _vocabulary)


def _assess_matrix(
    world: World, group_ids: list[str], variable_id: str, vocabulary_of: Callable[[World, str], Vocabulary]
) -> list[ProcessAssessment]:
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
        vocabularies = [vocabulary_of(world, group_ids[position]) for position in positions]
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
                for first, second in _new_pairs(final[row], ids[row]):
                    merge += _pair(world, vocabulary, first, second, group_id)
            before = set(np.flatnonzero(vocabulary.vowels > 0).tolist())
            after = before
            if vowels:
                counts = vocabulary.vowels.copy()
                for index in np.flatnonzero(hit[row]).tolist():
                    _count_vowels(counts, bank.forms[int(ids[row, index])], table.vowel_mask, -1)
                    _count_vowels(counts, bank.forms[int(changed[row, index])], table.vowel_mask, 1)
                after = set(np.flatnonzero(counts > 0).tolist())
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


def _pair(world: World, vocabulary: Vocabulary, first: int, second: int, group_id: str) -> float:
    """Cena dvojice nových homofonů (pozice ve vzorku): geometrický průměr frekvencí, s vahami buněk."""
    mass = math.sqrt(float(vocabulary.weights[first]) * float(vocabulary.weights[second]))
    names = world.registry.morphemes.names
    a, b = world.morphemes[names[int(vocabulary.morphemes[first])]], world.morphemes[names[int(vocabulary.morphemes[second])]]
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
    return _assess_matrix(world, [group_id], variable_id, _vocabulary)[0]

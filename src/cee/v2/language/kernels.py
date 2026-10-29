"""Číselná Numba implementace aplikace fonologického procesu.

``Process`` a banka tvarů používají skalární i dávkovou cestu. Pole obsahují
jen celočíselná ID a masky; původní Python aplikátor zůstává referencí.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from numba import njit

IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]

# Kódy operací: change, replace, delete, insert_before, insert_after, merge_next.
CHANGE = 0
REPLACE = 1
DELETE = 2
INSERT_BEFORE = 3
INSERT_AFTER = 4
MERGE_NEXT = 5

# Přízvuk: žádný, přízvučný cíl, nepřízvučný cíl.
NO_STRESS = 0
STRESSED = 1
UNSTRESSED = 2

# Pravidlo přízvuku: počáteční, předposlední, poslední slabika.
INITIAL = 0
PENULT = 1
FINAL = 2


@njit(cache=True)
def apply_process(
    form: IntArray,
    target_mask: BoolArray,
    left_mask: BoolArray,
    right_mask: BoolArray,
    vowel_mask: BoolArray,
    change_output: IntArray,
    operation: int,
    segment: int,
    stress: int,
    stress_rule: int,
    medial: bool,
    boundary: int,
) -> tuple[IntArray, int, bool]:
    """Aplikuje proces z masek a ID; ``boundary=-1`` znamená bez hranice."""
    length = len(form)
    first_nucleus = -1
    last_nucleus = -1
    nucleus_count = 0
    stressed_index = -1
    for index in range(length):
        if vowel_mask[form[index]]:
            if first_nucleus < 0:
                first_nucleus = index
            last_nucleus = index
            nucleus_count += 1
    if nucleus_count > 0:
        if stress_rule == INITIAL:
            for index in range(length):
                if vowel_mask[form[index]]:
                    stressed_index = index
                    break
        elif stress_rule == FINAL:
            stressed_index = last_nucleus
        elif nucleus_count == 1:
            stressed_index = first_nucleus
        else:
            seen = 0
            for index in range(length):
                if vowel_mask[form[index]]:
                    seen += 1
                    if seen == nucleus_count - 1:
                        stressed_index = index
                        break

    sites = np.zeros(length, dtype=np.bool_)
    last = length - 1
    for index in range(length):
        current = form[index]
        if not target_mask[current]:
            continue
        previous = form[index - 1] if index > 0 else len(vowel_mask) - 1
        following = form[index + 1] if index < last else len(vowel_mask) - 1
        if not left_mask[previous] or not right_mask[following]:
            continue
        if stress == STRESSED and index != stressed_index:
            continue
        if stress == UNSTRESSED and (index == stressed_index or not vowel_mask[current]):
            continue
        if operation == MERGE_NEXT and index == last:
            continue
        if medial and not (first_nucleus >= 0 and first_nucleus < index < last_nucleus):
            continue
        if operation == INSERT_BEFORE and index > 0 and form[index - 1] == segment:
            continue
        if operation == INSERT_AFTER and index < last and form[index + 1] == segment:
            continue
        sites[index] = True

    if not sites.any():
        return form.copy(), boundary, False

    result = np.empty(length * 2, dtype=np.int64)
    result_length = 0
    skip = -1
    new_boundary = boundary
    for index in range(length):
        if boundary >= 0 and index == boundary:
            new_boundary = result_length
        if index == skip:
            continue
        current = form[index]
        if not sites[index]:
            result[result_length] = current
            result_length += 1
            continue
        if operation == CHANGE:
            output = change_output[current]
            result[result_length] = current if output < 0 else output
            result_length += 1
        elif operation == REPLACE:
            result[result_length] = segment
            result_length += 1
        elif operation == DELETE:
            continue
        elif operation == INSERT_BEFORE:
            result[result_length] = segment
            result[result_length + 1] = current
            result_length += 2
        elif operation == INSERT_AFTER:
            result[result_length] = current
            result[result_length + 1] = segment
            result_length += 2
        else:
            result[result_length] = segment
            result_length += 1
            skip = index + 1

    if boundary >= length:
        new_boundary = result_length
    output_form = result[:result_length]
    if result_length == length:
        same = True
        for index in range(length):
            if output_form[index] != form[index]:
                same = False
                break
        if same:
            return form.copy(), boundary, False
    if result_length < 2:
        return form.copy(), boundary, False
    has_vowel = False
    for index in range(result_length):
        if vowel_mask[output_form[index]]:
            has_vowel = True
            break
    if not has_vowel:
        return form.copy(), boundary, False
    return output_form, new_boundary, True


@njit(cache=True)
def apply_process_batch(
    forms: IntArray,
    lengths: IntArray,
    boundaries: IntArray,
    target_mask: BoolArray,
    left_mask: BoolArray,
    right_mask: BoolArray,
    vowel_mask: BoolArray,
    change_output: IntArray,
    operation: int,
    segment: int,
    stress: int,
    stress_rule: int,
    medial: bool,
) -> tuple[IntArray, IntArray, IntArray, BoolArray]:
    """Zpracuje řádky matice forem; výstup má dvojnásobnou šířku pro inserty.

    Nevyužité buňky výstupu obsahují ``-1``. Řádky zůstávají ve vstupním
    pořadí a jejich délky a tracked hranice jsou vrácené v samostatných polích.
    """
    rows, width = forms.shape
    output = np.full((rows, width * 2), -1, dtype=np.int64)
    output_lengths = np.zeros(rows, dtype=np.int64)
    output_boundaries = np.empty(rows, dtype=np.int64)
    changed = np.zeros(rows, dtype=np.bool_)
    for row in range(rows):
        form, boundary, did_change = apply_process(
            forms[row, :lengths[row]], target_mask, left_mask, right_mask,
            vowel_mask, change_output, operation, segment, stress, stress_rule,
            medial, boundaries[row],
        )
        output_lengths[row] = len(form)
        output_boundaries[row] = boundary
        changed[row] = did_change
        for column in range(len(form)):
            output[row, column] = form[column]
    return output, output_lengths, output_boundaries, changed

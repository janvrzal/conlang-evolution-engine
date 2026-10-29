from __future__ import annotations

import random

import numpy as np
import pytest

from cee.v2.changes.sound import Voicing
from cee.v2.language.kernels import apply_process, apply_process_batch
from cee.v2.language.processes import Process
from cee.v2.language.segments import SegmentTable, default_table

_OPERATIONS = {
    "change": 0,
    "replace": 1,
    "delete": 2,
    "insert_before": 3,
    "insert_after": 4,
    "merge_next": 5,
}
_STRESSES = {None: 0, "stressed": 1, "unstressed": 2}
_RULES = {"initial": 0, "penult": 1, "final": 2}
_ALPHABET = "ptkbdmnsaeiuj"


def _numeric(process: Process, table: SegmentTable):
    size = table.boundary + 1
    target = np.asarray(process.target.mask, dtype=np.bool_)
    left = np.ones(size, dtype=np.bool_) if process.left is None else np.asarray(process.left.mask)
    right = np.ones(size, dtype=np.bool_) if process.right is None else np.asarray(process.right.mask)
    change_output = np.full(size, -1, dtype=np.int64)
    if process.operation == "change":
        # V produkčním převodu není třeba navštívit ID mimo cílovou masku.
        for segment in np.flatnonzero(target[:table.boundary]):
            output = table.changed(int(segment), process.changes)
            if output is not None:
                change_output[segment] = output
    return (
        target, left, right, np.asarray(table.vowel_mask, dtype=np.bool_), change_output,
        _OPERATIONS[process.operation], -1 if process.segment is None else process.segment,
        _STRESSES[process.stress], process.medial,
    )


def _kernel(process: Process, form: tuple[int, ...], table: SegmentTable,
            rule: str, boundary: int | None):
    target, left, right, vowels, change_output, operation, segment, stress, medial = _numeric(
        process, table
    )
    return apply_process(
        np.asarray(form, dtype=np.int64), target, left, right, vowels, change_output,
        operation, segment, stress, _RULES[rule], medial,
        -1 if boundary is None else boundary,
    )


def _compare(process: Process, form: tuple[int, ...], table: SegmentTable,
             rule: str = "penult", boundary: int | None = None) -> bool:
    result, new_boundary, changed = _kernel(process, form, table, rule, boundary)
    expected = process._apply(form, table, rule, boundary)
    if expected is None:
        assert not changed
        assert tuple(result.tolist()) == form
        assert new_boundary == (-1 if boundary is None else boundary)
    else:
        expected_form, expected_boundary = expected
        assert changed
        assert tuple(result.tolist()) == expected_form
        assert new_boundary == (-1 if expected_boundary is None else expected_boundary)
    return changed


def _compare_batch(process: Process, forms: list[tuple[int, ...]], table: SegmentTable,
                   rule: str, boundaries: list[int]) -> None:
    width = max(map(len, forms), default=0)
    padded = np.full((len(forms), width), -1, dtype=np.int64)
    lengths = np.asarray([len(form) for form in forms], dtype=np.int64)
    for row, form in enumerate(forms):
        padded[row, :len(form)] = form
    target, left, right, vowels, change_output, operation, segment, stress, medial = _numeric(
        process, table
    )
    output, output_lengths, output_boundaries, changed = apply_process_batch(
        padded, lengths, np.asarray(boundaries, dtype=np.int64), target, left, right,
        vowels, change_output, operation, segment, stress, _RULES[rule], medial,
    )
    for row, form in enumerate(forms):
        assert tuple(output[row, :output_lengths[row]].tolist()) == tuple(
            _kernel(process, form, table, rule, boundaries[row])[0].tolist()
        )
        expected = process._apply(form, table, rule, boundaries[row])
        if expected is None:
            assert not changed[row]
            assert output_boundaries[row] == boundaries[row]
        else:
            assert changed[row]
            assert tuple(output[row, :output_lengths[row]].tolist()) == expected[0]
            assert output_boundaries[row] == expected[1]


@pytest.mark.parametrize("operation", list(_OPERATIONS))
def test_seeded_random_common_ipa_forms_match_reference_and_batch(operation: str) -> None:
    table = default_table()
    rng = random.Random(4100 + _OPERATIONS[operation])
    form_symbols = [table.id_of(symbol) for symbol in _ALPHABET]
    target_id = table.id_of("p")
    process = Process(
        family="test", target=table.segments(["p"]), operation=operation,
        changes=(("voi", "+"),) if operation == "change" else (),
        segment=(table.id_of("b") if operation in ("replace", "merge_next")
                 else table.id_of("m")) if operation not in ("change", "delete") else None,
    )
    forms = []
    boundaries = []
    changed_count = 0
    for _ in range(100):
        length = rng.randint(3, 12)
        form = [rng.choice(form_symbols) for _ in range(length)]
        form[rng.randrange(length)] = table.id_of("a")
        form[rng.randrange(length)] = target_id
        word = tuple(form)
        boundary = rng.choice((0, len(word) // 2, len(word), len(word) + 1))
        forms.append(word)
        boundaries.append(boundary)
        changed_count += _compare(process, word, table, rng.choice(tuple(_RULES)), boundary)
    assert changed_count > 0
    _compare_batch(process, forms, table, "penult", boundaries)


@pytest.mark.parametrize("operation,word,target,segment,expected", [
    ("change", "pata", "p", None, "bata"),
    ("replace", "pata", "p", "b", "bata"),
    ("delete", "pata", "p", None, "ata"),
    ("insert_before", "pata", "p", "m", "mpata"),
    ("insert_after", "pata", "p", "m", "pmata"),
    ("merge_next", "pata", "p", "b", "bta"),
])
def test_explicit_operation_cases_match_reference(
    operation: str, word: str, target: str, segment: str | None, expected: str
) -> None:
    table = default_table()
    process = Process(
        "test", table.segments([target]), operation,
        changes=(("voi", "+"),) if operation == "change" else (),
        segment=None if segment is None else table.id_of(segment),
    )
    form = table.parse(word)
    result, _, did_change = _kernel(process, form, table, "initial", 0)
    assert did_change
    assert table.render(result.tolist()) == expected
    _compare(process, form, table, "initial", 0)
    _compare_batch(process, [form], table, "initial", [0])


@pytest.mark.parametrize("operation,word,target,segment", [
    ("delete", "pa", "a", None),  # ztráta poslední samohlásky
    ("delete", "pa", "p", None),  # jednopísmenné minimální slovo
])
def test_minimum_word_and_last_vowel_are_protected(
    operation: str, word: str, target: str, segment: str | None
) -> None:
    table = default_table()
    process = Process("test", table.segments([target]), operation,
                      segment=None if segment is None else table.id_of(segment))
    form = table.parse(word)
    assert not _compare(process, form, table)
    _compare_batch(process, [form], table, "penult", [1])


@pytest.mark.parametrize("operation,word,segment", [
    ("insert_before", "mpa", "m"),
    ("insert_after", "pma", "m"),
])
def test_insertion_does_not_duplicate_neighbor(operation: str, word: str, segment: str) -> None:
    table = default_table()
    process = Process("test", table.segments(["p"]), operation,
                      segment=table.id_of(segment))
    assert not _compare(process, table.parse(word), table)


def test_stressed_and_unstressed_vowel_targets_change() -> None:
    table = default_table()
    target = table.segments(list("aeiu"))
    for stress in ("stressed", "unstressed"):
        process = Process("test", target, "insert_after", segment=table.id_of("p"),
                          stress=stress)
        changed = _compare(process, table.parse("pata"), table, "penult")
        assert changed


def test_merge_skip_boundary_and_unchanged_boundary_are_preserved() -> None:
    table = default_table()
    merge = Process("test", table.segments(["p"]), "merge_next", segment=table.id_of("b"))
    result, boundary, changed = _kernel(merge, table.parse("pata"), table, "initial", 1)
    assert changed
    assert table.render(result.tolist()) == "bta"
    assert boundary == 1  # boundary leží na druhém segmentu, který merge přeskočil
    _compare_batch(merge, [table.parse("pata")], table, "initial", [1])

    no_op = Process("test", table.segments(["p"]), "replace", segment=table.id_of("p"))
    result, boundary, changed = _kernel(no_op, table.parse("pata"), table, "initial", 2)
    assert not changed
    assert tuple(result.tolist()) == table.parse("pata")
    assert boundary == 2


def test_real_sound_change_candidates_match_reference() -> None:
    table = default_table()
    inventory = [table.id_of(symbol) for symbol in "ptkbdgmnfszaiu"]
    candidates = Voicing().candidates(table, inventory)
    assert candidates
    forms = [table.parse(word) for word in ("apa", "ata", "ika", "pata", "aiba", "apta")]
    changed_total = 0
    for process in candidates:
        for form in forms:
            changed_total += _compare(process, form, table, "penult", len(form) // 2)
        _compare_batch(process, forms, table, "penult", [len(form) // 2 for form in forms])
    assert changed_total > 0

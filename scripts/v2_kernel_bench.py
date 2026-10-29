"""Porovnání Python a Numba aplikace zvukových procesů bez simulace.

Příklad: ``python scripts/v2_kernel_bench.py --batch-size 1000 --repeats 7``.
První volání JIT je vykázáno odděleně; následná měření obsahují warm-up.
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable, Sequence

import numpy as np

from cee.v2.changes.sound import SOUND_CHANGES
from cee.v2.language.kernels import apply_process, apply_process_batch
from cee.v2.language.processes import Process
from cee.v2.language.segments import SegmentTable
from cee.v2.scenarios import village_grid
from cee.v2.world import World

_RULE = "penult"


def _dataset() -> tuple[World, list[tuple[tuple[int, ...], int | None]]]:
    """Vezme protolexikon z hotového světa; žádný Simulation se nevytváří."""
    world = village_grid(4, seed=2, morphology=True)
    forms = [
        (morpheme.form, morpheme.boundary)
        for _, morpheme in sorted(world.morphemes.items())
        if morpheme.kind in ("root", "word")
    ]
    if not forms:
        raise RuntimeError("Scénář neobsahuje hláskové tvary.")
    return world, forms


def _prepare(
    process: Process,
    table: SegmentTable,
    forms: Sequence[tuple[tuple[int, ...], int | None]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[object, ...]]:
    width = max((len(form) for form, _ in forms), default=0)
    padded = np.full((len(forms), width), -1, dtype=np.int64)
    lengths = np.empty(len(forms), dtype=np.int64)
    boundaries = np.empty(len(forms), dtype=np.int64)
    flat_segments: list[int] = []
    for row, (form, boundary) in enumerate(forms):
        lengths[row] = len(form)
        padded[row, :len(form)] = form
        boundaries[row] = -1 if boundary is None else boundary
        flat_segments.extend(form)
    args = process.kernel_args(table, _RULE, np.asarray(flat_segments, dtype=np.int64))
    return padded, lengths, boundaries, args


def _scalar(rows: Sequence[tuple[np.ndarray, int]], args: tuple[object, ...]) -> None:
    for form, boundary in rows:
        apply_process(form, *args, boundary)


def _batch(padded: np.ndarray, lengths: np.ndarray, boundaries: np.ndarray,
           args: tuple[object, ...]) -> object:
    return apply_process_batch(padded, lengths, boundaries, *args)


def _end_to_end(process: Process, table: SegmentTable,
                forms: Sequence[tuple[tuple[int, ...], int | None]]) -> object:
    """Batch fasáda včetně převodu výstupních řádků na tuple/None."""
    padded, lengths, boundaries, args = _prepare(process, table, forms)
    output, output_lengths, output_boundaries, changed = _batch(
        padded, lengths, boundaries, args
    )
    converted = []
    for row in range(len(forms)):
        if changed[row]:
            boundary = int(output_boundaries[row])
            converted.append((tuple(output[row, :output_lengths[row]].tolist()),
                              None if boundary < 0 else boundary))
        else:
            converted.append(None)
    return converted


def _actual_candidates(
    world: World,
    forms: Sequence[tuple[tuple[int, ...], int | None]],
) -> list[tuple[Process, int, int]]:
    table = world.table
    assert table is not None
    inventory = sorted({segment for form, _ in forms for segment in form})
    best: dict[str, tuple[Process, int, int]] = {}
    for family in SOUND_CHANGES:
        for process in family.candidates(table, inventory):
            sites = 0
            changed = 0
            for form, boundary in forms:
                sites += len(process.sites(form, table, _RULE))
                if process._apply(form, table, _RULE, boundary) is not None:
                    changed += 1
            if changed == 0:
                continue
            previous = best.get(process.operation)
            if previous is None or (changed, sites) > (previous[1], previous[2]):
                best[process.operation] = (process, changed, sites)
    return [best[operation] for operation in sorted(best)]


def _assert_parity(process: Process, table: SegmentTable,
                   forms: Sequence[tuple[tuple[int, ...], int | None]]) -> tuple[int, int]:
    changed_rows = 0
    site_count = 0
    for form, boundary in forms:
        expected = process._apply(form, table, _RULE, boundary)
        compiled = process._apply_compiled(form, table, _RULE, boundary)
        assert compiled == expected
        site_count += len(process.sites(form, table, _RULE))
        array = np.asarray(form, dtype=np.int64)
        args = process.kernel_args(table, _RULE, array)
        actual, actual_boundary, did_change = apply_process(
            array, *args, -1 if boundary is None else boundary
        )
        if expected is None:
            assert not did_change
            assert tuple(actual.tolist()) == form
            assert actual_boundary == (-1 if boundary is None else boundary)
        else:
            expected_form, expected_boundary = expected
            assert did_change
            assert tuple(actual.tolist()) == expected_form
            assert actual_boundary == (-1 if expected_boundary is None else expected_boundary)
            changed_rows += 1
    return changed_rows, site_count


def _assert_batch_parity(
    process: Process,
    table: SegmentTable,
    forms: Sequence[tuple[tuple[int, ...], int | None]],
    batch_size: int,
) -> None:
    sample = [forms[index % len(forms)] for index in range(batch_size)]
    padded, lengths, boundaries, args = _prepare(process, table, sample)
    output, output_lengths, output_boundaries, changed = _batch(padded, lengths, boundaries, args)
    facade = _end_to_end(process, table, sample)
    for row, (form, boundary) in enumerate(sample):
        expected = process._apply(form, table, _RULE, boundary)
        assert facade[row] == expected
        actual = tuple(output[row, :output_lengths[row]].tolist())
        if expected is None:
            assert not changed[row]
            assert actual == form
            assert output_boundaries[row] == (-1 if boundary is None else boundary)
        else:
            assert changed[row]
            assert actual == expected[0]
            assert output_boundaries[row] == (-1 if expected[1] is None else expected[1])


def _samples(fn: Callable[[], object], repeats: int) -> list[float]:
    found = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        found.append(time.perf_counter() - started)
    return found


def _report(label: str, values: Sequence[float]) -> None:
    milliseconds = [value * 1000 for value in values]
    print(f"  {label:28s} min {min(milliseconds):9.3f} ms  median "
          f"{statistics.median(milliseconds):9.3f} ms")


def run(batch_size: int, repeats: int) -> None:
    world, source_forms = _dataset()
    table = world.table
    assert table is not None
    candidates = _actual_candidates(world, source_forms)
    if not candidates:
        raise RuntimeError("Žádný kandidát SOUND_CHANGES skutečně nezměnil protolexikon.")
    print(f"Tvary: {len(source_forms)} protolexikálních tvarů; běh simulace: ne.")
    print(f"Procesy: {len(candidates)} skutečných kandidátů, operace: "
          f"{', '.join(process.operation for process, _, _ in candidates)}")
    print(f"Měření: batch {batch_size} řádků, {repeats} opakování; pravidlo přízvuku: {_RULE}.")

    for process, discovered_changes, discovered_sites in candidates:
        print(f"\n{process.family} / {process.operation}: {process.label or process.key}")
        print(f"  pokrytí: {discovered_sites} míst, "
              f"{discovered_changes}/{len(source_forms)} změněných tvarů")

        repeated = [source_forms[index % len(source_forms)] for index in range(batch_size)]
        setup_started = time.perf_counter()
        padded, lengths, boundaries, args = _prepare(process, table, repeated)
        scalar_rows = [(np.asarray(form, dtype=np.int64), -1 if boundary is None else boundary)
                       for form, boundary in repeated]
        setup_seconds = time.perf_counter() - setup_started
        # První volání obou dispatchery vykázáno odděleně od zahřátých měření.
        first_started = time.perf_counter()
        apply_process(scalar_rows[0][0], *args, scalar_rows[0][1])
        scalar_first = time.perf_counter() - first_started
        first_started = time.perf_counter()
        _batch(padded, lengths, boundaries, args)
        batch_first = time.perf_counter() - first_started
        print(f"  první volání (kompilace/cache): scalar {scalar_first * 1000:.3f} ms; "
              f"batch {batch_first * 1000:.3f} ms")
        print(f"  příprava polí a masek: {setup_seconds * 1000:.3f} ms")

        changed_rows, site_count = _assert_parity(process, table, source_forms)
        assert changed_rows == discovered_changes and site_count == discovered_sites
        _assert_batch_parity(process, table, source_forms, batch_size)

        # Zahřátí není součástí opakovaných časů.
        _scalar(scalar_rows[:min(16, len(scalar_rows))], args)
        _batch(padded, lengths, boundaries, args)
        _end_to_end(process, table, repeated[:min(batch_size, 32)])
        process._apply_compiled(repeated[0][0], table, _RULE, repeated[0][1])

        production_scalar = _samples(
            lambda: [process._apply_compiled(form, table, _RULE, boundary)
                     for form, boundary in repeated], repeats
        )

        reference = _samples(
            lambda: [process._apply(form, table, _RULE, boundary) for form, boundary in repeated],
            repeats,
        )
        scalar = _samples(lambda: _scalar(scalar_rows, args), repeats)
        batch = _samples(lambda: _batch(padded, lengths, boundaries, args), repeats)
        end_to_end = _samples(lambda: _end_to_end(process, table, repeated), repeats)
        _report(f"Python reference ×{batch_size}", reference)
        _report(f"production _apply_compiled ×{batch_size}", production_scalar)
        _report(f"Numba scalar ×{batch_size}", scalar)
        _report(f"Numba batch ×{batch_size}", batch)
        _report(f"end-to-end batch ×{batch_size}", end_to_end)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()
    if args.batch_size < 1 or args.repeats < 1:
        parser.error("--batch-size a --repeats musí být kladná čísla")
    run(args.batch_size, args.repeats)


if __name__ == "__main__":
    main()

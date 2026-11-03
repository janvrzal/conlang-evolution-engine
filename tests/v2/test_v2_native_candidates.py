"""Sady kandidátů zvukových změn v Rustu proti Pythonu (krok B6d).

Rust (``rust/cee_core/src/candidates.rs``) staví kandidáty všech rodin z rysů tabulky hlásek a
inventáře: pořadí, ID proměnných, masky a popisy procesů musí být stejné jako
``_CombinedSoundCandidates`` (Python reference a fallback). Testuje se na inventářích z běžících
světů, na náhodných inventářích přes celou tabulku a na inventářích s tóny a sekundární artikulací.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from cee.v2 import native
from cee.v2.changes import sound
from cee.v2.language.segments import default_table
from cee.v2.language.sound_index import NativeSoundIndex

pytestmark = pytest.mark.skipif(not native.enabled(), reason="rozšíření cee_core není k dispozici")


@pytest.fixture(scope="module")
def table():
    return default_table()


@pytest.fixture(scope="module")
def handle(table):
    index = NativeSoundIndex(native.new_sound_index(sound.CATALOG.scales), sound.CATALOG.scales)
    index._send_table(table)
    return index._handle


def _inventories(table) -> list[tuple[int, ...]]:
    rng = np.random.default_rng(20261103)
    module = native._load()
    symbols = [table.id_of(symbol) for symbol in module.candidate_symbols()]
    toned = [table.with_tone(table.id_of(vowel), code) for vowel in "aeiou" for code in (1, 2, 4, 5, 9, 13, 20)]
    pool = sorted({*symbols, *(segment for segment in toned if segment is not None)})
    found: set[tuple[int, ...]] = {(), (symbols[0],)}
    # Celé inventáře: všechny symboly, jen souhlásky, jen samohlásky, jedna hláska z celé tabulky.
    found.add(tuple(sorted(pool)))
    found.add(tuple(sorted(s for s in pool if not table.is_vowel(s))))
    found.add(tuple(sorted(s for s in pool if table.is_vowel(s))))
    for segment in rng.integers(0, len(table.ipa), 40).tolist():
        found.add((segment,))
    for size in (3, 8, 15, 25, 40, 60):
        for _ in range(12):
            chosen = rng.choice(pool, size=min(size, len(pool)), replace=False).tolist()
            found.add(tuple(sorted(int(s) for s in chosen)))
    for _ in range(12):
        extra = rng.integers(0, len(table.ipa), 6).tolist()
        chosen = rng.choice(pool, size=20, replace=False).tolist() + extra
        found.add(tuple(sorted({int(s) for s in chosen})))
    return sorted(found)


def _fields(process) -> tuple[object, ...]:
    return tuple(
        (getattr(process, field.name), type(getattr(process, field.name)))
        for field in dataclasses.fields(process) if field.name not in ("target", "left", "right", "right2")
    ) + tuple(
        None if getattr(process, name) is None else getattr(process, name).key
        for name in ("target", "left", "right", "right2")
    )


def test_rodiny_maji_stejne_poradi_jako_python(handle):
    assert tuple(native._load().candidate_families()) == sound.FAMILY_KINDS


def test_symboly_hledane_rustem_zna_tabulka(table):
    assert all(table.id_of(symbol) >= 0 for symbol in native._load().candidate_symbols())


def test_sada_kandidatu_v_rustu_je_stejna_jako_v_pythonu(table, handle):
    checked = 0
    for inventory in _inventories(table):
        combined = sound._CombinedSoundCandidates(table, inventory)
        ids, ends, specs, columns, masks, rows = handle.describe_set(list(inventory))
        expected_ids = [item for change in sound.SOUND_CHANGES for item, _ in combined.family_candidates[change.kind]]
        assert ids == expected_ids, inventory
        assert ends == list(combined.family_ends), inventory
        python_masks = combined.masks
        assert columns.tolist() == python_masks.cols.tolist()
        assert np.array_equal(masks[0], python_masks.target.ravel())
        assert np.array_equal(masks[1], python_masks.left.ravel())
        assert np.array_equal(masks[2], python_masks.right.ravel())
        assert np.array_equal(masks[3], python_masks.right2.ravel())
        assert rows[0] == python_masks.right2_rows.tolist()
        assert rows[1] == combined.stressed_rows.tolist()
        assert rows[2] == combined.unstressed_rows.tolist()
        expected = [process for change in sound.SOUND_CHANGES for _, process in combined.family_candidates[change.kind]]
        assert len(specs) == len(expected)
        for spec, process in zip(specs, expected):
            built = sound.process_from_spec(table, spec)
            # Vzor „C|#“ Python staví pokaždé znovu (jiný objekt), proto se vzory porovnávají klíčem.
            assert _fields(built) == _fields(process)
            assert built.key == process.key
        checked += len(ids)
    assert checked > 5000

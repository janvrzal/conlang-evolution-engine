"""Hodnocení zvukových procesů v Rustu proti Pythonu: zlatá data a shoda součtů.

Zlatá data (``tests/v2/data/golden_assessment.json.gz``) zaznamenal
``scripts/v2_golden_assessment.py`` ze skutečných běhů v Pythonu: dávky
hodnocení procesu (tvary a váhy slov vzorku po skupinách, pořadí a cena
dvojic nových homofonů, výsledné ``ProcessAssessment``). Rust musí dát přesně
stejné součty (porovnává se bit po bitu; sčítá se párově jako ``numpy``)
i stejné dvojice ve stejném pořadí. Bez sestaveného rozšíření se testy s Rustem
přeskočí a celá sada běží nad Pythonem.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from test_v2_native_bank import _process

from cee.v2 import assessment, native
from cee.v2.language.bank import FormBank
from cee.v2.language.segments import default_table

GOLDEN = Path(__file__).parent / "data" / "golden_assessment.json.gz"
RULES = native.RULES

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.available(),
    reason="rozšíření cee_core není sestavené (nebo je vypnuté CEE_NATIVE=0)",
)


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    with gzip.open(GOLDEN, "rt") as handle:
        data: dict[str, Any] = json.load(handle)
    table = default_table()
    fingerprint = {"segments": len(table.ipa), "sha256": hashlib.sha256("\n".join(table.ipa).encode()).hexdigest()}
    assert data["table"] == fingerprint, "zlatá data jsou nad jinou tabulkou hlásek, nahraj je skriptem znovu"
    return data


def _bank(monkeypatch: pytest.MonkeyPatch) -> FormBank:
    monkeypatch.setattr(native, "enabled", lambda: True)
    bank = FormBank(default_table())
    assert bank._native is not None
    return bank


@needs_native
def test_hodnoceni_dava_na_zlatych_datech_stejne_soucty_dvojice_i_vysledek(golden, monkeypatch):
    table = default_table()
    processes = [_process(spec) for spec in golden["processes"]]
    forms = [tuple(form) for form in golden["forms"]]
    rows = merging = shaping = neutral = 0
    for case in golden["assess"]:
        process, rule = processes[case["process"]], RULES[case["rule"]]
        # Rust řadí nové homofony podle čísel tvarů, proto se banka plní v pořadí čísel ze záznamu.
        bank = _bank(monkeypatch)
        assert [bank.id_of(forms[form]) for form in case["order"]] == list(range(len(case["order"])))
        sizes = [len(row["ids"]) for row in case["rows"]]
        offsets = np.zeros(len(sizes) + 1, dtype=np.int64)
        np.cumsum(sizes, out=offsets[1:])
        ids = np.array([number for row in case["rows"] for number in row["ids"]], dtype=np.int64)
        weights = np.array([weight for row in case["rows"] for weight in row["weights"]], dtype=np.float64)
        raw = bank.assess_rows(process, rule, ids, weights, offsets, case["width"], assessment._shapes_vowels(process, table))
        pair_counts, first, second = raw[3], raw[4].tolist(), raw[5].tolist()
        found_pairs = [
            list(zip(first[end - count:end], second[end - count:end]))
            for count, end in zip(pair_counts.tolist(), np.cumsum(pair_counts).tolist())
        ]

        def pair_mass(row: int, one: int, two: int) -> float:
            for left, right, value in case["rows"][row]["pairs"]:
                if (left, right) == (one, two):
                    return float(value)
            raise AssertionError(("dvojice, kterou Python nezná", row, one, two))

        found = assessment.assessments_from_rows(raw, [row["total"] for row in case["rows"]], pair_mass, process, table)
        for row, (expected, pairs, result) in enumerate(zip(case["rows"], found_pairs, found)):
            rows += 1
            if expected["result"] is None:
                neutral += 1
                assert result == assessment.NEUTRAL
                continue
            # Dvojice ve stejném pořadí, v jakém je procházel Python (a tím i pořadí sčítání).
            assert pairs == [(left, right) for left, right, _ in expected["pairs"]]
            merging += bool(pairs)
            shaping += expected["result"][4] != 0.0
            values = [
                result.coverage, result.merge_mass, result.short_share, result.markedness_delta,
                result.dispersion_delta,
            ]
            assert [value.hex() for value in values] == [float(value).hex() for value in expected["result"]]
    assert rows > 1000 and neutral > 100 and merging > 30 and shaping > 10


@needs_native
def test_parovy_soucet_v_rustu_sedi_s_numpy_bit_po_bitu():
    import cee_core

    rng = np.random.default_rng(7)
    for rows in (1, 3, 50):
        for width in [*range(1, 40), 64, 100, 119, 120, 127, 128, 129, 200, 300, 513, 1025]:
            matrix = rng.random((rows, width)) * rng.choice([1.0, 100.0, 1e-3, 1e9], size=(rows, width))
            matrix *= rng.random((rows, width)) < 0.7
            matrix[:, ::5] *= -1.0
            for found, expected in zip(matrix.sum(axis=1).tolist(), range(rows)):
                assert cee_core.pairwise_sum(np.ascontiguousarray(matrix[expected])).hex() == found.hex()


@needs_native
def test_priznakovost_slabik_v_rustu_sedi_s_pythonem_na_nahodnych_tvarech(monkeypatch):
    bank = _bank(monkeypatch)
    table = default_table()
    rng = np.random.default_rng(11)
    vowels = np.flatnonzero(table.vowel_mask[:-1]).tolist()[:40]
    glides = [segment for segment in range(table.boundary) if table.sonority(segment) == 3][:10]
    consonants = [segment for segment in range(table.boundary) if table.sonority(segment) in (0, 1, 2)][:60]
    assert vowels and glides and consonants
    pool = vowels + glides + consonants
    forms = [tuple(int(item) for item in rng.choice(pool, size=int(rng.integers(1, 9)))) for _ in range(600)]
    forms += [(vowels[0], vowels[1]), (glides[0], vowels[0]), (vowels[0], glides[0], vowels[1]), (consonants[0],)]
    for form_id, form in zip(bank.ids_of(forms).tolist(), forms):
        assert bank._native.markedness(form_id).hex() == assessment.markedness(form, table).hex()


def test_vyhodnoceni_radku_bez_zasazeni_je_neutralni():
    raw = (np.zeros(2), np.zeros(2), np.zeros(2), np.zeros(2, dtype=np.int64), np.zeros(0, dtype=np.int64),
           np.zeros(0, dtype=np.int64), np.zeros(2, dtype=np.int64), np.zeros(0, dtype=np.int64),
           np.zeros(2, dtype=np.int64), np.zeros(0, dtype=np.int64))
    process = _process_stub()
    found = assessment.assessments_from_rows(raw, [3.0, 4.0], lambda *_: 1 / 0, process, default_table())
    assert found == [assessment.NEUTRAL, assessment.NEUTRAL]


def _process_stub() -> Any:
    from cee.v2.language.processes import Process

    table = default_table()
    return Process(family="stub", target=table.VOWEL, operation="delete")

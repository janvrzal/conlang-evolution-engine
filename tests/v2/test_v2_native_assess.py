"""Hodnocení zvukových procesů a opory změn v Rustu proti Pythonu: zlatá data a shoda součtů.

Zlatá data (``tests/v2/data/golden_assessment.json.gz``) zaznamenal
``scripts/v2_golden_assessment.py`` ze skutečných běhů v Pythonu: dávky
hodnocení procesu (tvary a váhy slov vzorku po skupinách, pořadí a cena
dvojic nových homofonů, výsledné ``ProcessAssessment``) a opory kandidátů
zvukových změn nad počty prostředí. Rust musí dát přesně stejné součty
(porovnává se bit po bitu; sčítá se párově jako ``numpy``), stejné dvojice ve
stejném pořadí a stejné opory. Bez sestaveného rozšíření se testy s Rustem
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
from cee.v2.changes import sound
from cee.v2.language.bank import FormBank
from cee.v2.language.processes import Process
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
        # Pořadí dvojic na číslech tvarů nezávisí; banka se přesto plní v pořadí čísel ze záznamu (stejné tvary).
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


def _support_inputs(case: dict[str, Any]) -> tuple[Any, ...]:
    return (
        np.array(case["previous"], dtype=np.intp), np.array(case["segment"], dtype=np.intp),
        np.array(case["following"], dtype=np.intp), np.array(case["stressed"], dtype=bool),
        np.array(case["following2"], dtype=np.intp), np.array(case["count"], dtype=np.int64),
    )


@needs_native
def test_opory_zmen_v_rustu_sedi_s_pythonem_na_zlatych_datech(golden):
    table = default_table()
    negative = 0
    assert len(golden["supports"]) > 100
    for case in golden["supports"]:
        combined = sound._combined_candidates(table, tuple(case["inventory"]))
        found = combined.eval_supports(*_support_inputs(case), table)
        assert found.tolist() == case["result"]
        assert found.tolist() == combined.eval_supports_python(*_support_inputs(case), table).tolist()
        negative += any(count < 0 for count in case["count"])
    assert negative > 20


@needs_native
def test_opory_s_hlaskou_mimo_inventar_pocita_python(golden, monkeypatch):
    table = default_table()
    case = next(item for item in golden["supports"] if len(item["count"]) > 5)
    combined = sound._combined_candidates(table, tuple(case["inventory"]))
    outside = next(segment for segment in range(table.boundary) if segment not in case["inventory"])
    previous, segment, following, stressed, following2, count = _support_inputs(case)
    segment[0] = outside
    answers = []
    kernel = native.kernel("sound_supports")
    monkeypatch.setattr(native, "kernel", lambda name: lambda *args: answers.append(kernel(*args)) or answers[-1])
    found = combined.eval_supports(previous, segment, following, stressed, following2, count, table)
    assert answers == [None]  # Rust hlásku bez sloupce pozná a neodpoví
    assert found.tolist() == combined.eval_supports_python(
        previous, segment, following, stressed, following2, count, table).tolist()


def test_opory_bez_rustu_pocita_python(golden, monkeypatch):
    table = default_table()
    monkeypatch.setattr(native, "kernel", lambda name: None)
    for case in golden["supports"][:20]:
        combined = sound._combined_candidates(table, tuple(case["inventory"]))
        assert combined.eval_supports(*_support_inputs(case), table).tolist() == case["result"]


def _world_with_processes() -> tuple[Any, list[str], list[str]]:
    from cee.v2.language.processes import Process
    from cee.v2.phonology import register
    from cee.v2.repertoire import Origin
    from cee.v2.scenarios import village_grid

    world = village_grid(3, seed=5, phonology=True, semantics=True)
    table = world.table
    for group in world.groups.values():
        group.main_code.phonology.vocabulary.update(world.morphemes)
    schwa = table.id_of("ə")
    processes = [
        # Všechny samohlásky splynou: spousta nových homofonů a změna rozptylu vokálů.
        Process("merge", table.VOWEL, "replace", segment=schwa, left=None, right=None),
        # Nový vokál jen v přízvuku, mizení souhlásky, vložení hlásky: ostatní operace a délky.
        Process("stressed", table.segments(["a"]), "replace", segment=table.id_of("o"), stress="stressed"),
        Process("loss", table.CONSONANT, "delete", right=table.BOUNDARY),
        Process("insert", table.VOWEL, "insert_after", segment=table.id_of("t")),
    ]
    variables = [register(world, process, Origin("test", 0, 0.0, "v"))[0] for process in processes]
    return world, sorted(world.groups), variables


@needs_native
def test_hodnoceni_dava_na_svete_stejne_vysledky_jako_python_i_reference():
    world, groups, variables = _world_with_processes()
    merged = 0
    for variable in variables:
        native_result = assessment._assess_batch_native(world, groups, variable)
        assert native_result == assessment._assess_batch_python(world, groups, variable)
        assert native_result == assessment._assess_batch_reference(world, groups, variable)
        merged += sum(item.merge_mass > 0 or item.dispersion_delta != 0 for item in native_result)
    assert merged >= 3


def test_poradi_novych_homofonu_nezavisi_na_cislech_tvaru():
    """Dvojice nových homofonů jdou podle pozic ve vzorku; čísla tvarů v bance je neovlivní."""
    ids = np.array([5, 9, 2, 7, 3, 8], dtype=np.int64)
    final = np.array([4, 1, 4, 1, 3, 1], dtype=np.int64)
    expected = [(0, 2), (1, 3), (1, 5), (3, 5)]
    assert assessment._new_pairs(final, ids) == expected
    # Přečíslování tvarů (jiné pořadí v bance) pořadí dvojic nezmění.
    relabel = {1: 90, 3: 10, 4: 50}
    assert assessment._new_pairs(np.array([relabel[item] for item in final.tolist()]), ids) == expected
    assert assessment._new_pairs(final, 100 - ids) == expected


@needs_native
def test_rust_radi_nove_homofony_podle_pozic_ne_podle_cisel_tvaru(monkeypatch):
    """Banka plněná v jiném pořadí (jiná čísla tvarů) dá stejné dvojice jako Python."""
    table = default_table()
    merge = Process("merge", table.VOWEL, "replace", segment=table.id_of("ə"), left=None, right=None)
    letters = [["t", "a"], ["t", "o"], ["k", "a"], ["k", "o"], ["p", "i"], ["p", "u"]]
    forms = [tuple(table.id_of(letter) for letter in form) for form in letters]
    found = []
    for order in (list(range(6)), [5, 3, 1, 4, 2, 0]):
        bank = _bank(monkeypatch)
        numbers = {position: bank.id_of(forms[position]) for position in order}
        ids = np.array([numbers[position] for position in range(6)], dtype=np.int64)
        offsets = np.array([0, 6], dtype=np.int64)
        raw = bank.assess_rows(merge, "initial", ids, np.ones(6), offsets, 6, False)
        count = int(raw[3][0])
        found.append(list(zip(raw[4].tolist()[:count], raw[5].tolist()[:count])))
    assert found[0] == found[1] and found[0] == sorted(found[0]) and len(found[0]) > 0


@needs_native
def test_hodnoceni_se_nepocita_v_rustu_kdyz_numpy_scita_jinak(monkeypatch):
    world, groups, variables = _world_with_processes()
    called = []
    monkeypatch.setattr(assessment, "_assess_batch_native", lambda *args: called.append(args))
    monkeypatch.setattr(native, "sums_match", lambda: False)
    assert assessment._assess_batch(world, groups, variables[0]) == assessment._assess_batch_python(
        world, groups, variables[0])
    assert not called


@needs_native
def test_overeni_souctu_projde_na_tomto_stroji():
    assert native.sums_match()

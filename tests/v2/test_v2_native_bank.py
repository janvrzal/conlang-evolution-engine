"""Jádro v Rustu (banka tvarů, tabulky procesů) proti Pythonu na zlatých datech.

Zlatá data (``tests/v2/data/golden_bank.json.gz``) zaznamenal
``scripts/v2_golden_bank.py`` ze skutečných běhů: každá různá aplikace
zvukového procesu na tvar, i s popisem procesu. Rust musí dát bitově stejné
výsledky a stejná čísla tvarů jako Python; bez sestaveného rozšíření se tyto
testy přeskočí a celá sada běží nad Pythonem jako dřív.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
import pickle
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from cee.v2 import native
from cee.v2.language.bank import UNCHANGED, FormBank
from cee.v2.language.processes import Process
from cee.v2.language.segments import Pattern, default_table

GOLDEN = Path(__file__).parent / "data" / "golden_bank.json.gz"
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


def _pattern(spec: dict[str, Any] | None) -> Pattern | None:
    if spec is None:
        return None
    mask = np.zeros(spec["size"], dtype=bool)
    for begin, end in spec["ranges"]:
        mask[begin:end] = True
    return Pattern(spec["key"], mask)


def _process(spec: dict[str, Any]) -> Process:
    target = _pattern(spec["target"])
    assert target is not None
    process = Process(
        family=spec["family"], target=target, operation=spec["operation"],
        changes=tuple(tuple(pair) for pair in spec["changes"]), segment=spec["segment"],
        left=_pattern(spec["left"]), right=_pattern(spec["right"]), stress=spec["stress"], medial=spec["medial"],
        allow=tuple(spec["allow"]), right2=_pattern(spec["right2"]), tone=spec["tone"],
    )
    assert process.key == spec["key"]
    return process


def _bank(monkeypatch: pytest.MonkeyPatch, use_native: bool) -> FormBank:
    monkeypatch.setattr(native, "enabled", lambda: use_native)
    bank = FormBank(default_table())
    assert (bank._native is not None) == use_native
    return bank


def _same(left: FormBank, right: FormBank) -> None:
    """Banky mají stejné tvary pod stejnými čísly."""
    assert left.forms == right.forms


@needs_native
def test_rust_dava_na_zlatych_datech_vysledky_ze_skutecnych_behu(golden, monkeypatch):
    banks = [_bank(monkeypatch, False), _bank(monkeypatch, True)]
    processes = [_process(spec) for spec in golden["processes"]]
    forms = [tuple(form) for form in golden["forms"]]
    grouped: dict[tuple[int, int], list[tuple[tuple[int, ...], tuple[int, ...] | None]]] = {}
    for index, rule, form, result in golden["records"]:
        grouped.setdefault((index, rule), []).append((forms[form], None if result < 0 else forms[result]))
    for (index, rule), items in grouped.items():
        for bank in banks:
            table = bank.process_table(processes[index], RULES[rule])
            ids = bank.ids_of([form for form, _ in items])
            found = table.results(ids)
            for (form, expected), result in zip(items, found.tolist()):
                assert (result == UNCHANGED) if expected is None else bank.forms[result] == expected, (
                    bank is banks[1], processes[index].key, form)
    _same(*banks)


@needs_native
def test_rust_a_python_se_shoduji_na_nahodnych_tvarech_a_cisla_tvaru_jsou_stejna(golden, monkeypatch):
    python, rust = _bank(monkeypatch, False), _bank(monkeypatch, True)
    table = default_table()
    processes = [_process(spec) for spec in golden["processes"]]
    seen = sorted({segment for form in golden["forms"] for segment in form})
    rng = random.Random(20261102)
    pool = seen + [rng.randrange(len(table.ipa)) for _ in range(40)]
    vowels = [segment for segment in pool if table.is_vowel(segment)]
    for round_ in range(6):
        forms = []
        for _ in range(400):
            size = rng.randint(1, 9)
            form = [rng.choice(pool) for _ in range(size)]
            if rng.random() < 0.8:  # většina tvarů má samohlásku, jinak by procesy nic nezkoumaly
                form[rng.randrange(size)] = rng.choice(vowels)
            forms.append(tuple(form))
        forms += [(), (rng.choice(pool),)]
        for process in rng.sample(processes, 40):
            rule = rng.choice(RULES)
            tables = [bank.process_table(process, rule) for bank in (python, rust)]
            ids = [bank.ids_of(forms) for bank in (python, rust)]
            assert ids[0].tolist() == ids[1].tolist()
            rng.shuffle(forms)  # příští dávka v jiném pořadí a s opakováním
            batch = ids[0][np.array([rng.randrange(len(forms)) for _ in range(300)])]
            found = [table_.results(batch) for table_ in tables]
            assert found[0].tolist() == found[1].tolist()
            for form_id in batch[:30].tolist():
                assert tables[0].result(form_id) == tables[1].result(form_id)
        _same(python, rust)
    for form_id in range(0, len(python), max(1, len(python) // 300)):
        for rule in RULES:
            assert python.possible(form_id, rule) == rust.possible(form_id, rule)
            for process in processes[:20]:
                assert python.may_apply(form_id, rule, process.key) == rust.may_apply(form_id, rule, process.key)


@needs_native
def test_banka_v_rustu_prezije_deepcopy_i_pickle_a_pokracuje_stejne(golden, monkeypatch):
    python, rust = _bank(monkeypatch, False), _bank(monkeypatch, True)
    processes = [_process(spec) for spec in golden["processes"]][:30]
    forms = [tuple(form) for form in golden["forms"][:600]]
    for bank in (python, rust):
        ids = bank.ids_of(forms[:300])
        for process in processes[:15]:
            bank.process_table(process, "penult").results(ids)
    copied = copy.deepcopy(rust)
    restored = pickle.loads(pickle.dumps(rust))
    assert copied._native is not None and restored._native is not None
    assert rust._native is not copied._native and copied._native is not restored._native
    _same(python, copied)
    _same(python, restored)
    # Kopie pokračují: nové tvary, nové změny, stejná čísla jako v Pythonu.
    for bank in (python, rust, copied, restored):
        ids = bank.ids_of(forms)
        for process in processes:
            bank.process_table(process, "penult").results(ids)
            bank.process_table(process, "initial").results(ids)
    for bank in (copied, restored):
        _same(python, bank)
    _same(python, rust)


@needs_native
def test_banka_sdilena_mezi_kopiemi_sveta_zustava_jedna(golden, monkeypatch):
    rust = _bank(monkeypatch, True)
    shared = copy.deepcopy({"bank": rust, "other": [1, 2]}, {id(rust): rust})
    assert shared["bank"] is rust


@needs_native
def test_pickle_banky_z_rustu_jde_nacist_i_bez_rustu(golden, monkeypatch):
    rust = _bank(monkeypatch, True)
    processes = [_process(spec) for spec in golden["processes"]][:20]
    ids = rust.ids_of([tuple(form) for form in golden["forms"][:200]])
    for process in processes:
        rust.process_table(process, "final").results(ids)
    saved = pickle.dumps(rust)
    monkeypatch.setattr(native, "enabled", lambda: False)
    restored = pickle.loads(saved)
    assert restored._native is None
    _same(rust, restored)
    reference = _bank(monkeypatch, False)
    reference_ids = reference.ids_of([tuple(form) for form in golden["forms"][:200]])
    for process in processes:
        expected = reference.process_table(process, "final").results(reference_ids).tolist()
        found = restored.process_table(process, "final").results(restored.ids_of(
            [tuple(form) for form in golden["forms"][:200]])).tolist()
        assert [reference.forms[value] if value >= 0 else None for value in expected] == [
            restored.forms[value] if value >= 0 else None for value in found]


def test_bez_rozsireni_nebo_s_vypnutim_bezi_python(monkeypatch):
    monkeypatch.setenv("CEE_NATIVE", "0")
    assert not native.enabled() and native.status().startswith("python")
    assert native.new_bank(default_table()) is None
    bank = FormBank(default_table())
    assert bank._native is None


def test_rozsireni_s_jinou_verzi_rozhrani_se_nepouzije(monkeypatch):
    monkeypatch.setattr(native, "_module", native._UNLOADED)
    monkeypatch.setitem(sys.modules, "cee_core", SimpleNamespace(INTERFACE_VERSION=native.INTERFACE_VERSION + 1))
    monkeypatch.delenv("CEE_NATIVE", raising=False)
    assert not native.available() and not native.enabled()
    assert FormBank(default_table())._native is None
    monkeypatch.setattr(native, "_module", native._UNLOADED)  # ať další testy načtou skutečné rozšíření


def test_chybejici_rozsireni_neni_chyba(monkeypatch):
    monkeypatch.setattr(native, "_module", native._UNLOADED)
    monkeypatch.setitem(sys.modules, "cee_core", None)  # import selže jako bez rozšíření
    assert not native.available()
    assert FormBank(default_table())._native is None
    monkeypatch.setattr(native, "_module", native._UNLOADED)

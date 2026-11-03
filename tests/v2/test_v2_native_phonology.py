"""Krok fonologizace v Rustu proti Pythonu: zlatá data a shoda celých běhů.

Zlatá data (``tests/v2/data/golden_phonology.json.gz``) zaznamenal
``scripts/v2_golden_phonology.py`` ze skutečných běhů v Pythonu: přepisy tvarů
včetně hranice kmen | koncovka, zařazení morfému do fronty a fronty nově
aktivovaných procesů. Rust musí dát přesně stejné tvary, pořadí i logity
(porovnává se bit po bitu, Rust logity nepočítá, jen odečítá). Druhá část
spouští svět s Rustem i bez něj a porovnává celý stav; bez sestaveného
rozšíření se testy s Rustem přeskočí a celá sada běží nad Pythonem.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from array import array
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from cee.v2 import native, phonology
from cee.v2.language.bank import FormBank
from cee.v2.language.processes import Process
from cee.v2.language.segments import Pattern, default_table
from cee.v2.scenarios import language_shift, village_grid
from cee.v2.simulation import Simulation

GOLDEN = Path(__file__).parent / "data" / "golden_phonology.json.gz"
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


class Kit:
    """Banka v Rustu s procesy ze zlatých dat a volání jádra bez světa."""

    def __init__(self, golden: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(native, "enabled", lambda: True)
        self.bank = FormBank(default_table())
        assert self.bank._native is not None
        self.handle = self.bank._native
        self.processes = [_process(spec) for spec in golden["processes"]]
        self.forms = [tuple(form) for form in golden["forms"]]
        self.base = golden["constants"]["base"]
        self.lead = golden["constants"]["lead"]

    def row(self, index: int, rule: int) -> int:
        return self.bank.process_table(self.processes[index], RULES[rule]).index

    def complete(self, call: Any) -> tuple[Any, ...]:
        """Volá Rust, dokud nemá vše: mapy hlásek mu doplní banka (jako ``phonology._resolve``)."""
        while True:
            answer = call()
            self.bank._adopt(*answer[-3:])
            needs = answer[0]
            if not any(needs):
                return answer  # type: ignore[no-any-return]
            assert not (needs[0] or needs[1] or needs[2] or needs[4]), needs
            for row, segments in needs[3]:
                self.bank._resolve(row, segments)

    def rewrite(self, index: int, rule: int, form: tuple[int, ...], cut: int) -> tuple[tuple[int, ...], int] | None:
        """Přepis jednoho tvaru: jediný morfém č. 0 ve frontě procesu, bez dalších front."""
        row = self.row(index, rule)
        form_id = self.bank.id_of(form)
        store = (array("i", [form_id]), array("i", [cut]), array("i", [-1]))
        columns = (array("i", [-1]), array("i", [-1]), array("i", [-1]), array("i", [0]))
        targets: tuple[list[Any], ...] = ([], [], [], [], [])
        answer = self.complete(lambda: self.handle.restructure_step(
            rule, self.base, self.lead, store, columns, targets, {}, row,
            (array("d", [-1e9]), array("i", [0])), 0.0, 0,
        ))
        _, popped, moved, forms, cuts = answer[:5]
        assert popped == 1
        if not moved:
            return None
        return self.bank.forms[forms[0]], cuts[0]

    def queue(
        self, index: int, rule: int, form: tuple[int, ...], restructured: bool, waiting: bool,
        bias: float, frequency: float | None,
    ) -> float | None:
        """Zařazení jednoho morfému (č. 0) do fronty procesu; vrací potřebný logit, nebo ``None``."""
        row = self.row(index, rule)
        store = (array("i", [self.bank.id_of(form)]), array("i", [-1]), array("i", [-1]))
        columns = (array("i", [-1]), array("i", [-1]), array("i", [-1]), array("i", [0]))
        targets = (
            [row], [bytearray([int(waiting)])], [bytearray([int(restructured)])],
            [array("d", [bias])], [frequency is not None],
        )
        known = {} if frequency is None else {0: frequency}
        answer = self.complete(lambda: self.handle.queue_morpheme(
            rule, self.base, self.lead, store, columns, targets, known, 0,
        ))
        _, queues, morphemes, logits = answer[:4]
        assert queues == morphemes == [0] * len(queues)
        assert len(logits) <= 1
        return logits[0] if logits else None


@needs_native
def test_prepis_tvaru_i_s_hranici_kmene_sedi_s_pythonem_na_zlatych_datech(golden, monkeypatch):
    kit = Kit(golden, monkeypatch)
    changed = 0
    for index, rule, form, cut, expected in golden["apply"]:
        found = kit.rewrite(index, rule, tuple(golden["forms"][form]), cut)
        if expected is None:
            assert found is None, (kit.processes[index].key, golden["forms"][form], cut)
        else:
            changed += 1
            assert found == (kit.forms[expected[0]], expected[1]), (
                kit.processes[index].key, golden["forms"][form], cut)
    assert changed > 1000 and len(golden["apply"]) > 5000


@needs_native
def test_zarazeni_do_fronty_sedi_s_pythonem_bit_po_bitu(golden, monkeypatch):
    kit = Kit(golden, monkeypatch)
    inserted = skipped = 0
    for index, rule, form, restructured, waiting, bias, frequency, expected in golden["queue"]:
        found = kit.queue(index, rule, kit.forms[form], restructured, waiting, bias, frequency)
        assert found == expected, (kit.processes[index].key, kit.forms[form], bias, frequency)
        if expected is None:
            skipped += 1
        else:
            inserted += 1
            assert found.hex() == expected.hex()
    assert inserted > 500 and skipped > 500


@needs_native
def test_aktivace_procesu_dava_stejnou_frontu_jako_python(golden, monkeypatch):
    kit = Kit(golden, monkeypatch)
    assert len(golden["activate"]) >= 10
    for case in golden["activate"]:
        words = case["words"]
        row = kit.row(case["process"], case["rule"])
        forms = [kit.bank.id_of(kit.forms[form]) for form, _, _ in words]
        store = (array("i", forms), array("i", [-1] * len(words)), array("i", [-1] * len(words)))
        # Slova jsou seřazená podle jména, takže číslo = pořadí jmen a shoda logitů se řeší stejně.
        columns = (
            array("i", [-1] * len(words)), array("i", [-1] * len(words)), array("i", [-1] * len(words)),
            array("i", [lexeme for _, _, lexeme in words]),
        )
        biases = array("d", [bias for bias, _ in case["lexemes"]])
        known = {number: frequency for number, (_, frequency) in enumerate(case["lexemes"]) if frequency is not None}
        reductive = bool(known)
        restructured = bytearray(int(flag) for _, flag, _ in words)
        targets = ([row], [bytearray()], [restructured], [biases], [reductive])
        answer = kit.complete(lambda: kit.handle.activate(
            case["rule"], kit.base, kit.lead, store, columns, targets, known, row, bytearray([1] * len(words)),
        ))
        _, morphemes, logits = answer[:3]
        assert [[number, needed] for number, needed in zip(morphemes, logits)] == case["queue"]


def test_shodne_logity_ve_fronte_se_radi_podle_jmena_ne_podle_cisla():
    names = ["b", "a", "d", "c", "e"]
    # Čísla 1 až 3 mají shodný logit (−0,0 a 0,0 jsou si rovny), jména a, d, c.
    assert phonology._by_name([0, 1, 2, 3, 4], [-1.0, 0.0, -0.0, 0.0, 2.0], names) == [0, 1, 3, 2, 4]
    assert phonology._by_name([0, 1, 2, 3, 4], [1.0, 1.0, 1.0, 1.0, 2.0], names) == [1, 0, 3, 2, 4]
    assert phonology._by_name([0, 1, 2, 3, 4], [1.0, 2.0, 2.0, 3.0, 3.0], names) == [0, 1, 2, 3, 4]
    assert phonology._by_name([4, 3, 2], [1.0, 1.0, 1.0], names) == [3, 2, 4]
    assert phonology._by_name([], [], names) == []


# --- celé běhy s Rustem a bez něj ------------------------------------------------------------


def _state(world: Any) -> dict[str, Any]:
    """Celý stav fonologizace světa v prostých datech: tvary, fronty, příznaky, verze a deníky."""
    names = world.registry.morphemes.names
    codes = {}
    for group_id, group in sorted(world.groups.items()):
        code = group.main_code
        state = code.phonology
        form_ids = [list(array_.tolist()) for array_ in code.forms.arrays()]
        bank = world.form_bank()
        codes[group_id] = {
            "forms": [[bank.forms[form] if form >= 0 else None for form in form_ids[0]], form_ids[1], form_ids[2]],
            "log": list(code.forms.log),
            "pending": {variable: queue.pairs() for variable, queue in sorted(state.pending.items())},
            "queued": {variable: sorted(waiting) for variable, waiting in sorted(state.queued.items())},
            "restructured": {variable: sorted(done) for variable, done in sorted(state.restructured.items())},
            "closed": sorted(state.closed), "order": sorted(state.order.items()),
            "version": state.version, "lexicon_version": state.lexicon_version,
            "fixed_since": sorted(state.fixed_since.items()), "lifecycle": list(state.lifecycle_log),
            "vocabulary": sorted(state.vocabulary), "stress_rule": code.stress_rule,
        }
    return {"morphemes": len(names), "codes": codes}


def _run(monkeypatch: pytest.MonkeyPatch, use_native: bool, build: Any, stages: list[float], flip: bool = False) -> Any:
    monkeypatch.setattr(native, "enabled", lambda: use_native)
    world, events = build()
    assert (world.form_bank()._native is not None) == use_native
    simulation = Simulation(world, events=events)
    result = []
    for stage in stages:
        simulation.run(stage)
        if flip and stage != stages[-1]:
            # Přízvuk se změnil uprostřed běhu (jako ``prosody.restructure``): tabulky procesů
            # s novým pravidlem v bance ještě nemusí být, a na tom závisí předfiltr.
            for group in world.groups.values():
                code = group.main_code
                code.stress_rule = "initial" if code.stress_rule != "initial" else "final"
                code.phonology.version += 1
                code.phonology.cache.clear()
        result.append((simulation.history.digest(), _state(world)))
    return result


SCENARIOS = {
    "fonologie": (lambda: (village_grid(4, seed=2, phonology=True), ()), [500.0, 1000.0], False),
    "morfologie": (lambda: (village_grid(4, seed=2, morphology=True, semantics=True), ()), [500.0, 1000.0], False),
    "syntax": (lambda: (village_grid(4, seed=2, syntax=True, semantics=True), ()), [500.0, 1000.0], False),
    "posun-jazyka": (lambda: language_shift(2, start=300.0), [400.0, 900.0], False),
    "zmena-prizvuku": (lambda: (village_grid(4, seed=2, morphology=True, semantics=True), ()), [300.0, 600.0, 1000.0], True),
}


@needs_native
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_beh_s_rustem_a_bez_nej_dava_stejny_stav(name, monkeypatch):
    build, stages, flip = SCENARIOS[name]
    python = _run(monkeypatch, False, build, stages, flip)
    rust = _run(monkeypatch, True, build, stages, flip)
    assert len(python) == len(rust)
    for (digest_python, state_python), (digest_rust, state_rust) in zip(python, rust):
        assert digest_python == digest_rust
        assert state_python == state_rust
    # Test má smysl, jen když ve světě opravdu běžely procesy (a aspoň někde se přepisovalo).
    last = rust[-1][1]["codes"]
    assert any(code["pending"] for code in last.values())
    if name != "fonologie":
        assert any(code["restructured"] and code["log"] for code in last.values())


@needs_native
def test_kopie_a_checkpoint_sveta_s_rustem_pokracuji_jako_python(monkeypatch):
    import copy

    def start(use_native: bool) -> Simulation:
        monkeypatch.setattr(native, "enabled", lambda: use_native)
        simulation = Simulation(village_grid(4, seed=2, morphology=True, semantics=True))
        simulation.run(400.0)
        return simulation

    python, rust = start(False), start(True)
    # Kopie světa má vlastní banku v Rustu; checkpoint banku sdílí (jen přibývá).
    clone = copy.deepcopy(rust.world)
    assert clone.form_bank()._native is not rust.world.form_bank()._native
    assert _state(clone) == _state(rust.world)
    resumed = Simulation.resume(rust.checkpoint())
    for simulation in (python, rust, resumed):
        simulation.run(800.0)
    assert python.history.digest() == rust.history.digest() == resumed.history.digest()
    assert _state(python.world) == _state(rust.world) == _state(resumed.world)


def test_bez_rozsireni_poctita_python(monkeypatch):
    """Rozšíření chybí nebo je vypnuté: svět vznikne bez banky v Rustu a běží beze změny."""
    monkeypatch.setattr(native, "enabled", lambda: False)
    world = village_grid(4, seed=2, phonology=True)
    assert world.form_bank()._native is None
    Simulation(world).run(120.0)
    assert phonology._kernel(world, next(iter(world.groups.values())).main_code) is None

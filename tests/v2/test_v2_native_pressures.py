"""Tlaky a hodnocení v Rustu (B3b): shoda s Pythonem bit po bitu.

- zlatá data tlaků (``golden_pressures.json.gz``) projdou přes Rust: scénář se zopakuje s Rustem,
  v ticích záznamů se po přenosu bloku spočítá každý tlak záznamu v Rustu nad dávkou ze záznamu
  a porovná se s výstupem, který zaznamenal Python; stejně součet vážených tlaků a výsledek
  pro 1 a víc vláken;
- hodnocení procesů v Rustu (stav v ``AssessIndex``) dá stejné hodnoty jako index v Pythonu i po
  změnách verze, zastarání a kopii světa;
- kontrolní bod z jednoho režimu jde obnovit v druhém a běh pak dá tentýž otisk.
"""

from __future__ import annotations

import copy
import os
import pickle
from typing import Any

import numpy as np
import pytest

import cee.v2.simulation as simulation_module
from cee.v2 import assessment, native, pressures_native
from cee.v2.assessment import STALE_TICKS
from cee.v2.language.assessment_index import AssessmentIndex, NativeAssessmentIndex, index_of
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.processes import Process
from cee.v2.phonology import register
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from tests.v2 import golden_worlds as worlds

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.assess_enabled() or not native.transmit_enabled(),
    reason="rozšíření cee_core není sestavené, je vypnuté, nebo se numpy a knihovna systému s Rustem rozcházejí",
)


def bits(array: np.ndarray) -> np.ndarray:
    """Pole jako bity; −0 je tu +0 (fitness nikdy není −0, Rust nulové členy nepřičítá)."""
    return (np.asarray(array, dtype=np.float64) + 0.0).view(np.uint64)


@pytest.fixture(scope="module")
def golden() -> dict[str, list[dict[str, Any]]]:
    data = worlds.read_gzip(worlds.DATA / "golden_pressures.json.gz")
    return {name: [worlds.decode(item) for item in scenario["records"]] for name, scenario in data["scenarios"].items()}


@needs_native
@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(worlds.SCENARIOS))
def test_tlaky_v_rustu_odpovidaji_zlatym_datum(golden, name, monkeypatch):
    """Každý tlak záznamu spočítaný v Rustu je bit po bitu stejný jako zaznamenaný výstup Pythonu."""
    expected: dict[int, list[dict[str, Any]]] = {}
    for record in golden[name]:
        expected.setdefault(record["tick"], []).append(record)
    simulation, ticks = worlds.new_simulation(name)
    checked: set[tuple[int, int]] = set()
    pressures = simulation.pressures
    original = simulation_module.transmit

    def probe(world, block, inputs, pressures_in, params, **hooks):
        result = original(world, block, inputs, pressures_in, params, **hooks)
        for number, record in enumerate(expected.get(inputs.tick, ())):
            if (inputs.tick, number) in checked or not set(record["batch"]["variable_ids"]) <= set(block.variable_ids):
                continue
            checked.add((inputs.tick, number))
            batch = worlds.batch_from_record(world, record["batch"])
            shape = batch.freqs.shape
            weighted = pressures[record["kind"]]
            where = f"{name}: tik {inputs.tick}, záznam {number}"
            for pressure, _ in weighted:
                found = pressures_native.scores_of_batch(world, batch, {record["kind"]: ((pressure, 1.0),)})
                assert found is not None, where
                golden_scores = worlds.full_scores(record["scores"][pressure.name], shape)
                assert np.array_equal(bits(found), bits(golden_scores)), f"{where}, tlak {pressure.name}"
            # Součet vážených tlaků v pořadí tlaků druhu proměnných, na 1 i na víc vláken.
            total = np.zeros(shape)
            for pressure, strength in weighted:
                total += strength * worlds.full_scores(record["scores"][pressure.name], shape)
            for threads in (1, 3):
                found = pressures_native.scores_of_batch(world, batch, {record["kind"]: weighted}, threads)
                assert found is not None and np.array_equal(bits(found), bits(total)), f"{where}, vlákna {threads}"
        return result

    monkeypatch.setattr(simulation_module, "transmit", probe)
    simulation.run(simulation.world.start_year + max(expected) * worlds.DT)
    assert checked == {(tick, number) for tick, records in expected.items() for number in range(len(records))}
    assert ticks >= max(expected)


def _world_with_processes():
    world = village_grid(3, seed=5, phonology=True, morphology=True, semantics=True)
    table = world.table
    for group in world.groups.values():
        group.main_code.phonology.vocabulary.update(world.morphemes)
    schwa = table.id_of("ə")
    processes = [
        Process("merge", table.VOWEL, "replace", segment=schwa, left=None, right=None),
        Process("stressed", table.segments(["a"]), "replace", segment=table.id_of("o"), stress="stressed"),
        Process("loss", table.CONSONANT, "delete", right=table.BOUNDARY),
        Process("insert", table.VOWEL, "insert_after", segment=table.id_of("t")),
        Process("change", table.segments(["t"]), "change", changes=(("voi", "+"),)),
    ]
    variables = [register(world, process, Origin("test", 0, 0.0, "v"))[0] for process in processes]
    return world, sorted(world.groups), variables


def _bumped(world, groups, step):
    """Změní tvar jednoho slova v každé skupině a zvedne verzi kódu."""
    for group_id in groups:
        code = world.groups[group_id].main_code
        words = sorted(code.phonology.vocabulary)
        word = words[step % len(words)]
        current = world.unit_of(code, word)
        code.forms.set(word, UnitForm(current.form[::-1], current.boundary, current.exponent))
        code.phonology.version += 1


@needs_native
def test_hodnoceni_v_rustu_sedi_s_pythonem_po_zmenach_a_zastarani(monkeypatch):
    """Stejné hodnoty a stejný okamžik přepočtu v Rustu i v Pythonu (včetně ``STALE_TICKS``)."""
    rust_world, groups, variables = _world_with_processes()
    python_world, _, _ = _world_with_processes()
    rust = index_of(rust_world)
    assert isinstance(rust, NativeAssessmentIndex)
    python = AssessmentIndex()
    python_world.assessment = python
    tick = 0
    merged = 0
    for step in range(6):
        for variable in variables:
            ours = rust.assess_many(rust_world, groups, variable, tick)
            theirs = python.assess_many(python_world, groups, variable, tick)
            assert ours == theirs, (step, variable)
            merged += sum(item.merge_mass > 0 or item.dispersion_delta != 0 for item in ours)
        if step % 2 == 0:
            _bumped(rust_world, groups, step)
            _bumped(python_world, groups, step)
        # Mezi ticky zastarávají hodnocení: po ``STALE_TICKS`` se přepočítají i bez změny verze.
        tick += STALE_TICKS // 2
    assert merged >= 3
    # Kopie světa nese uložená hodnocení i s okamžikem přepočtu.
    copied = copy.deepcopy(rust_world)
    again = pickle.loads(pickle.dumps(rust_world))
    for other in (copied, again):
        for variable in variables:
            assert index_of(other).assess_many(other, groups, variable, tick) == python.assess_many(
                python_world, groups, variable, tick)
    # Obnova v jiném režimu (bez Rustu) dá z uloženého stavu tytéž hodnoty.
    monkeypatch.setenv("CEE_NATIVE", "0")
    restored = pickle.loads(pickle.dumps(rust_world))
    index = index_of(restored)
    assert isinstance(index, AssessmentIndex)
    for variable in variables:
        assert index.assess_many(restored, groups, variable, tick) == python.assess_many(python_world, groups, variable, tick)


@needs_native
def test_hodnoceni_procesu_cte_stejny_vzorek_jako_reference():
    """Vzorek, váhy a součty indexu v Rustu jsou ty, které dá reference nad maticí od začátku."""
    world, groups, variables = _world_with_processes()
    for variable in variables:
        found = assessment.assess_many(world, groups, variable, 0)
        assert found == assessment._assess_batch_reference(world, groups, variable)


@needs_native
@pytest.mark.slow
def test_kontrolni_bod_jde_obnovit_v_rustu_i_z_pythonu_do_rustu(monkeypatch):
    """Běh z kontrolního bodu (Rust → Rust, Python → Rust, Python → Python) dá otisk nepřerušeného běhu.

    Z Rustu do Pythonu obnova nejde už od B5 (index zvukových změn ``World.sound`` je v Rustu); hodnocení
    ``language.assessment_index`` samo se při změně režimu přenáší (viz test níže).
    """
    def build():
        return village_grid(3, seed=11, phonology=True, morphology=True, semantics=True)

    straight = Simulation(build())
    straight.run(300.0)
    digest = straight.history.digest()
    for first, second in (("", ""), ("0", ""), ("0", "0")):
        monkeypatch.setenv("CEE_NATIVE", first)
        monkeypatch.setattr(native, "_SUMS", None)
        monkeypatch.setattr(native, "_LIBM", None)
        half = Simulation(build())
        half.run(150.0)
        saved = pickle.dumps(half.checkpoint())
        monkeypatch.setenv("CEE_NATIVE", second)
        resumed = Simulation.resume(pickle.loads(saved))
        resumed.run(300.0)
        assert resumed.history.digest() == digest, (first, second)


def _eroded_world():
    world = village_grid(3, seed=7, phonology=True, morphology=True, semantics=True)
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind != "lexical":
            continue
        root = world.stored(world.group_ids()[0], variable_id)
        morpheme = world.variants[root.variants[0]].payload["morpheme"]
        form = world.morphemes[morpheme].form
        if len(form) < 4:
            continue
        for group in world.groups.values():
            group.main_code.forms.set(morpheme, UnitForm(form[:2], None, None))
            group.main_code.phonology.version += 1
    return world


@needs_native
def test_vychozi_tvar_se_doplni_i_kdyz_kod_slovo_prepsal(monkeypatch):
    """Erodované slovo (kód má vlastní tvar, výchozí není v bance) dá s Rustem stejný běh jako bez něj."""
    rust = Simulation(_eroded_world())
    rust.run(200.0)
    monkeypatch.setenv("CEE_NATIVE", "0")
    python = Simulation(_eroded_world())
    python.run(200.0)
    assert rust.history.digest() == python.history.digest()

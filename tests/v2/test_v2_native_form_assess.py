"""Hodnocení analogických změn tvarů v Rustu (B6b): shoda s Pythonem bit po bitu.

Rust počítá hodnocení tvarů (zisk, frekvence, splynutí s citačním tvarem) sám ze stavu morfologického
indexu míst, úložiště tvarů kódů a dominantních kořenů. Zkouška porovná čtyři morfologické tlaky
(`Uniformity`, `Conservation`, `Teachability`, `Distinctiveness`; dohromady určují všech pět hodnot
hodnocení) spočítané v Rustu s tlaky v Pythonu (reference s `FormAssessmentIndex`) po změnách tvarů,
dominantních kořenů, slovní zásoby a frekvencí, a to ve všech čtyřech operacích analogické změny.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from cee.v2 import morphology, native, pressures_native
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.morphology import FormChange
from cee.v2.phonology import changed_id, leave_vocabulary, none_id
from cee.v2.pressures.base import PressureBatch
from cee.v2.pressures.morphological import Conservation, Distinctiveness, Teachability, Uniformity
from cee.v2.repertoire import Origin
from cee.v2.scenarios import village_grid

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.assess_enabled() or not native.transmit_enabled(),
    reason="rozšíření cee_core není sestavené, je vypnuté, nebo se numpy a knihovna systému s Rustem rozcházejí",
)

PRESSURES = (Uniformity(), Conservation(), Teachability(), Distinctiveness())


def bits(array: np.ndarray) -> np.ndarray:
    return (np.asarray(array, dtype=np.float64) + 0.0).view(np.uint64)


def _world():
    world = village_grid(3, seed=9, phonology=True, morphology=True, semantics=True)
    groups = sorted(world.groups)
    for group_id in groups:
        code = world.groups[group_id].main_code
        code.phonology.vocabulary.update(world.morphemes)
        code.l2_share = 0.25 if group_id == groups[1] else 0.0
    words = sorted(
        unit for unit in world.groups[groups[0]].main_code.phonology.vocabulary
        if world.morphemes[unit].kind == "word" and world.morphemes[unit].exponent is not None
    )
    changes: list[FormChange] = []
    for unit in words[:4]:
        value = world.unit_of(world.groups[groups[0]].main_code, unit)
        other = world.unit_of(world.groups[groups[0]].main_code, words[-1])
        changes += [
            FormChange("level", unit), FormChange("extend", unit, value.exponent),
            FormChange("extend", unit, other.exponent), FormChange("prepend", unit, segment=value.form[0]),
            FormChange("drop_initial", unit, segment=value.form[0]),
        ]
    variables = [
        morphology.register(world, change, Origin("test", 0, 0.0, groups[0]))[0] for change in changes
    ]
    # Dominantní kořeny: každý kořen nese víc pojmů, pořadí vložení se mezi kódy liší (na něm stojí součet).
    names = world.registry.concepts.names
    for index, group_id in enumerate(groups):
        state = world.groups[group_id].main_code.phonology
        for position, unit in enumerate(words[:4]):
            root = world.morphemes[unit].lexeme_id
            extra = [names[(37 * position + 11 * index + 29 * step) % len(names)] for step in range(3)]
            for concept in [world.morphemes[root].meaning, *extra]:
                state.set_dominant(concept, root)
        state.version += 1
        state.lexicon_version += 1
    return world, groups, words, variables


def _batch(world, groups, variables) -> PressureBatch:
    shape = (len(variables), len(groups), 2)
    freqs = np.full(shape, 0.5)
    heard = np.full(shape, 0.5)
    # Jedna buňka je nedosažená, ať se zkouší i vynechání.
    freqs[0, 0, 1] = heard[0, 0, 1] = 0.0
    return PressureBatch(
        world=world, variable_ids=list(variables), group_ids=list(groups), freqs=freqs,
        slots=[[none_id(variable), changed_id(variable)] for variable in variables], tick=1, heard=heard,
    )


def _compare(world, groups, variables, where):
    reached = 0
    for pressure in PRESSURES:
        python = pressure.scores(_batch(world, groups, variables))
        rust = pressures_native.scores_of_batch(
            world, _batch(world, groups, variables), {"form": ((pressure, 1.0),)}
        )
        assert rust is not None, where
        assert np.array_equal(bits(python), bits(rust)), f"{where}: {pressure.name}"
        reached += int(np.count_nonzero(python))
    return reached


def _rewrite(world, group_id, unit, reverse=True):
    code = world.groups[group_id].main_code
    current = world.unit_of(code, unit)
    form = current.form[::-1] if reverse else current.form[1:] + current.form[:1]
    code.forms.set(unit, UnitForm(form, current.boundary, current.exponent))
    code.phonology.version += 1


@needs_native
def test_hodnoceni_tvaru_v_rustu_sedi_s_pythonem_po_zmenach_stavu():
    world, groups, words, variables = _world()
    reached = _compare(world, groups, variables, "výchozí stav")
    # Přepsání tvaru slova, jeho kořene a cizího slova; po každé změně se verze kódu zvýší.
    for step, (group_id, unit) in enumerate(
        [(groups[0], words[0]), (groups[1], words[1]), (groups[2], words[0]),
         (groups[0], world.morphemes[words[0]].lexeme_id), (groups[1], words[-1])]
    ):
        _rewrite(world, group_id, unit, reverse=step % 2 == 0)
        reached += _compare(world, groups, variables, f"přepsaný tvar {step}")
    # Změna dominantního kořene a slovní zásoby.
    code = world.groups[groups[0]].main_code
    state = code.phonology
    concept, root = next(iter(state.dominant.items()))
    other = next(item for item in state.dominant.values() if item != root)
    state.set_dominant(concept, other)
    state.version += 1
    state.lexicon_version += 1
    reached += _compare(world, groups, variables, "změna dominantního kořene")
    leave_vocabulary(world.groups[groups[1]].main_code, words[2])
    leave_vocabulary(world.groups[groups[2]].main_code, words[0])
    reached += _compare(world, groups, variables, "slovo opustilo slovní zásobu")
    # Frekvence pojmů se mění bez změny verze kódu (obě podoby drží hodnotu do příští změny verze)
    # i s ní.
    world.concept_frequencies[concept] = 0.9
    _compare(world, groups, variables, "frekvence bez změny verze")
    for group_id in groups:
        world.groups[group_id].main_code.phonology.version += 1
    reached += _compare(world, groups, variables, "frekvence po změně verze")
    assert reached > 50


@needs_native
def test_hodnoceni_tvaru_se_nepocita_v_pythonu_pri_tlacich_v_rustu(monkeypatch):
    """Tlaky v Rustu nevolají `morphology._assess_reference` ani `class_stats`: hodnocení tvarů počítá Rust."""
    world, groups, words, variables = _world()
    for group_id in groups:
        _rewrite(world, group_id, words[0])
    calls: list[str] = []
    for name in ("_assess_reference", "class_stats"):
        original = getattr(morphology, name)
        monkeypatch.setattr(morphology, name, lambda *args, _name=name, _original=original: (
            calls.append(_name), _original(*args))[1])
    found = pressures_native.scores_of_batch(
        world, _batch(world, groups, variables), {"form": tuple((pressure, 1.0) for pressure in PRESSURES)}
    )
    assert found is not None and np.count_nonzero(found) > 0
    assert not calls

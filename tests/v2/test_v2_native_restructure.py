"""Přestavba tvarů po analogii v Rustu (B6b): stejný výsledek jako smyčka v Pythonu.

`morphology.restructure` zapisuje analogie, které ve skupině převážily. Nové stavy tvarů (vyrovnání, rozšíření)
počítá s Rustem jedno volání na kód (`_native_writes`), další analogie téhož kódu vidí stav po předchozím zápisu.
Zkouška zopakuje přestavbu na dvou stejných světech, jednou s Rustem a jednou s původní smyčkou v Pythonu,
a porovná tvary slov, banku tvarů, verze kódu, fronty fonologizace, deníky a historii.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from cee.v2 import morphology, native
from cee.v2.history import History
from cee.v2.language.lexicon import UnitForm
from cee.v2.language.morphology import FormChange
from cee.v2.phonology import changed_id
from cee.v2.repertoire import Distribution, Origin
from cee.v2.scenarios import village_grid

needs_native = pytest.mark.skipif(
    os.environ.get("CEE_NATIVE") == "0" or not native.assess_enabled(),
    reason="rozšíření cee_core není sestavené nebo je vypnuté",
)


def _world(seed: int):
    """Svět, kde má každá skupina několik živých analogií, které převážily, nad přepsanými tvary."""
    world = village_grid(2, seed=seed, phonology=True, morphology=True, semantics=True)
    groups = sorted(world.groups)
    rng = np.random.default_rng(seed)
    for group_id in groups:
        world.groups[group_id].main_code.phonology.vocabulary.update(world.morphemes)
    words = sorted(
        unit for unit in world.groups[groups[0]].main_code.phonology.vocabulary
        if world.morphemes[unit].kind == "word" and world.morphemes[unit].exponent is not None
    )
    exponents = sorted({world.morphemes[unit].exponent for unit in words})
    for group_id in groups:
        code = world.groups[group_id].main_code
        for unit in rng.choice(words, size=8, replace=False).tolist():
            current = world.unit_of(code, unit)
            form = current.form[1:] + current.form[:1] if len(current.form) > 1 else current.form[::-1]
            code.forms.set(unit, UnitForm(form, current.boundary, current.exponent))
        code.phonology.version += 1
    chosen = rng.choice(words, size=10, replace=False).tolist()
    variables = []
    for unit in chosen:
        for change in (FormChange("level", unit), FormChange("extend", unit, str(rng.choice(exponents))),
                       FormChange("extend", unit, str(rng.choice(exponents)))):
            variables.append(morphology.register(world, change, Origin("test", 0, 0.0, groups[0]))[0])
    for group_id in groups:
        code = world.groups[group_id].main_code
        for variable in rng.choice(variables, size=14, replace=False).tolist():
            morphology.activate(world, code, variable)
            code.repertoire.set(variable, Distribution.fixed(changed_id(variable)))
    return world, groups


def _state(world, groups):
    out = []
    for group_id in groups:
        code = world.groups[group_id].main_code
        state = code.phonology
        units = sorted(world.morphemes)
        out.append((
            group_id, state.version, state.lexicon_version, sorted(state.morph_active.items()),
            sorted(state.morph_closed), list(state.lifecycle_log),
            [(unit, world.unit_of(code, unit)) for unit in units],
            list(code.forms.log),
            {process: queue.pairs() for process, queue in state.pending.items()},
        ))
    return out


@needs_native
@pytest.mark.parametrize("seed", [3, 5, 8])
def test_prestavba_s_rustem_dava_stav_a_historii_stejne_jako_smycka_v_pythonu(seed, monkeypatch):
    rust_world, groups = _world(seed)
    python_world, _ = _world(seed)
    assert _state(rust_world, groups) == _state(python_world, groups)
    original = morphology._native_writes
    seen: list[list] = []
    monkeypatch.setattr(morphology, "_native_writes", lambda *args: seen.append(original(*args)) or seen[-1])
    rust_history = History()
    for tick, group_id in enumerate(groups, start=1):
        morphology.restructure(rust_world, group_id, tick, rust_history, 25.0 * tick)
    writes = [item for batch in seen if batch is not None for item in batch]
    assert writes and any(item is None for item in writes) and any(item is not None for item in writes)
    monkeypatch.setattr(morphology, "_native_writes", lambda *args: None)
    python_history = History()
    for tick, group_id in enumerate(groups, start=1):
        morphology.restructure(python_world, group_id, tick, python_history, 25.0 * tick)
    assert _state(rust_world, groups) == _state(python_world, groups)
    assert rust_history.digest() == python_history.digest()
    assert len(rust_history.digest()) > 0
    closed = sum(len(state[4]) for state in _state(rust_world, groups))
    assert closed > 0

"""Zvukové procesy v běžící simulaci: proměnné, fonologizace a povrch.

Životní cyklus změny (iterace 2):

1. **Inovace** vytvoří procesní proměnnou s variantami „žádná změna“ a
   „změna“. Varianta se šíří jako každá jiná.
2. **Fonetická fáze**: povrch slova se mění s pravděpodobností
   ``p_slovo = σ(logit p + β·frekvence + sklon_slova)``.
3. **Fonologizace**: když ``p_slovo`` překročí práh, nová generace si
   přepíše podkladový tvar. Slova se sklonem proti změně zůstanou
   reliktními výjimkami.
4. **Uzavření**: po dvou generacích na 100 % proces přestane být živý; nové
   slovo jím už neprojde.

Fonologizace jednoho slova může procesu, který ještě běží, připravit půdu
(feeding) nebo ji vzít (bleeding). Řeší se to tak, že se slovo po přepisu
znovu zařadí do front ostatních živých procesů.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cee.v2.history import History
from cee.v2.language.lexicon import PhonologyState, UnitForm
from cee.v2.language.processes import Process
from cee.v2.language.segments import Form
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.rng import generator, stable_id

if TYPE_CHECKING:
    from cee.v2.world import Code, World

#: Nad tímto p_slovo si nová generace slovo přepíše.
RESTRUCTURE_THRESHOLD = 0.85
#: Rozptyl sklonu jednotlivých slov; určuje podíl reliktních výjimek.
WORD_BIAS_SD = 1.5
#: Jak silně frekvence předbíhá u redukčních změn (Bybee).
FREQUENCY_LEAD = 1.0
#: Po kolika generacích na 100 % proces přestane být živý.
CLOSURE_GENERATIONS = 2.0
#: Od jakého podílu ve skupině začne proces působit na slova. Většina
#: inovací zanikne dřív, a nemusí se proto ani zařazovat do front.
ACTIVATION_SHARE = 0.05

_LOGIT_THRESHOLD = math.log(RESTRUCTURE_THRESHOLD / (1 - RESTRUCTURE_THRESHOLD))


def none_id(variable_id: str) -> str:
    return stable_id("variant", "none", variable_id)


def changed_id(variable_id: str) -> str:
    return stable_id("variant", "changed", variable_id)


def register(world: World, process: Process, origin: Origin) -> tuple[str, Variant]:
    """Procesní proměnná a její varianta „změna“; tatáž změna = tatáž proměnná.

    Když vznikne stejná změna nezávisle ve dvou skupinách, je to jedna
    proměnná a jedna varianta — paralelní inovace se tak sčítají.
    """
    variable_id = Variable("process", process.key).id
    if variable_id not in world.variables:
        world.variables[variable_id] = Variable("process", process.key, default=none_id(variable_id))
        world.variants[none_id(variable_id)] = Variant(
            none_id(variable_id), variable_id, {"process": None},
            Origin(None, origin.tick, origin.year, None),
        )
        world.variants[changed_id(variable_id)] = Variant(
            changed_id(variable_id), variable_id, {"process": variable_id}, origin,
        )
        world.processes[variable_id] = process
    return variable_id, world.variants[changed_id(variable_id)]


def changed_share(world: World, group_id: str, variable_id: str) -> float:
    distribution: Distribution | None = world.distribution(group_id, variable_id)
    return 0.0 if distribution is None else distribution.frequency(changed_id(variable_id))


def _logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return math.log(p / (1 - p))


_BIASES: dict[tuple[int, str, str], float] = {}


def word_bias(world: World, variable_id: str, morpheme_id: str) -> float:
    """Seedovaný sklon slova vůči změně; stejný ve všech skupinách.

    Patří lexému, ne jednotlivému tvaru: všechny buňky paradigmatu tak změnu
    přijmou (nebo odmítnou) společně a výjimka nevyrobí falešnou alternaci.
    """
    morpheme_id = world.morphemes[morpheme_id].lexeme_id
    key = (world.seed, variable_id, morpheme_id)
    bias = _BIASES.get(key)
    if bias is None:
        bias = _BIASES[key] = float(
            generator(world.seed, "word-bias", variable_id, morpheme_id).normal(0.0, WORD_BIAS_SD)
        )
    return bias


def _lead(world: World, process: Process, morpheme_id: str, code: Code | None = None) -> float:
    lexeme = world.morphemes[morpheme_id].lexeme_id
    frequency = world.usage_frequency(code, lexeme) if code is not None else world.morphemes[lexeme].frequency
    return FREQUENCY_LEAD * (2.0 * frequency - 1.0) if process.reductive else 0.0


def word_probability(
    world: World, variable_id: str, morpheme_id: str, share: float, code: Code | None = None
) -> float:
    process = world.processes[variable_id]
    value = _logit(share) + _lead(world, process, morpheme_id, code) + word_bias(world, variable_id, morpheme_id)
    return 1.0 / (1.0 + math.exp(-value))


def _needed(world: World, variable_id: str, morpheme_id: str, code: Code | None = None) -> float:
    """Logit sdíleného podílu, při kterém si slovo změnu zapíše."""
    process = world.processes[variable_id]
    return (
        _LOGIT_THRESHOLD - _lead(world, process, morpheme_id, code)
        - word_bias(world, variable_id, morpheme_id)
    )


def _applies(world: World, code: Code, variable_id: str, morpheme_id: str) -> bool:
    # Tabulka procesu v bance tvarů: každý různý tvar se posoudí jednou za běh.
    bank = world.form_bank()
    table = bank.process_table(world.processes[variable_id], code.stress_rule)
    return table.result(bank.id_of(world.form_of(code, morpheme_id))) >= 0


def _queue(world: World, code: Code, variable_id: str, morpheme_id: str) -> None:
    state = code.phonology
    queue = state.pending.setdefault(variable_id, [])
    waiting = state.queued.setdefault(variable_id, set())
    if morpheme_id in state.restructured.get(variable_id, ()):
        return
    if morpheme_id in waiting:
        return
    if _applies(world, code, variable_id, morpheme_id):
        bisect.insort(queue, (_needed(world, variable_id, morpheme_id, code), morpheme_id))
        waiting.add(morpheme_id)


def requeue(world: World, code: Code, variable_id: str, morpheme_id: str) -> None:
    """Tvar se změnil (analogie, jiný proces): ať ho živý proces znovu posoudí."""
    _queue(world, code, variable_id, morpheme_id)


def active_processes(state: PhonologyState, world: World) -> list[str]:
    """Živé procesy kódu v pořadí jejich vzniku (chronologie změn)."""
    return sorted(
        (variable_id for variable_id in state.pending if variable_id not in state.closed),
        key=lambda variable_id: (state.order[variable_id], variable_id),
    )


def activate(world: World, code: Code, variable_id: str) -> None:
    """Proces poprvé zasáhl kód: zařadí do fronty všechna slova, kterých se týká."""
    state = code.phonology
    if variable_id in state.pending or variable_id in state.closed:
        return
    state.pending[variable_id] = []
    state.queued[variable_id] = set()
    state.order[variable_id] = len(state.order)
    for morpheme_id in sorted(state.vocabulary):
        _queue(world, code, variable_id, morpheme_id)


def enter_vocabulary(world: World, code: Code, morpheme_id: str) -> None:
    """Slovo se stalo dominantním: projdou jím i změny, které právě běží."""
    state = code.phonology
    if morpheme_id in state.vocabulary:
        return
    state.vocabulary.add(morpheme_id)
    state.version += 1
    state.lexicon_version += 1
    for variable_id in active_processes(state, world):
        _queue(world, code, variable_id, morpheme_id)


def leave_vocabulary(code: Code, morpheme_id: str) -> None:
    if morpheme_id in code.phonology.vocabulary:
        code.phonology.vocabulary.discard(morpheme_id)
        code.phonology.version += 1
        code.phonology.lexicon_version += 1


@dataclass(frozen=True)
class Phonologized:
    group: str
    variable: str
    words: tuple[str, ...]


def restructure(world: World, group_id: str, tick: int, dt: float, history: History, year: float) -> None:
    """Fonologizace a uzavírání procesů v jedné skupině (krok 6 ticku)."""
    group = world.groups[group_id]
    code = group.main_code
    state = code.phonology
    assert world.table is not None
    for variable_id in active_processes(state, world):
        share = changed_share(world, group_id, variable_id)
        queue = state.pending[variable_id]
        level = _logit(share) if share > 0 else -math.inf
        rewritten: list[str] = []
        while queue and queue[0][0] < level:
            _, morpheme_id = queue.pop(0)
            state.queued[variable_id].discard(morpheme_id)
            process = world.processes[variable_id]
            unit = world.unit_of(code, morpheme_id)
            new = process.apply_tracked(unit.form, world.table, code.stress_rule, unit.boundary)
            if new is None:
                continue  # dřívější přepis jinou změnou mu vzal půdu
            code.forms.set(morpheme_id, UnitForm(new[0], new[1], unit.exponent))
            state.restructured.setdefault(variable_id, set()).add(morpheme_id)
            state.version += 1
            rewritten.append(morpheme_id)
            for other in active_processes(state, world):
                if other != variable_id:
                    _queue(world, code, other, morpheme_id)
        if rewritten:
            history.record(
                "phonologized", tick, year, group=group_id, variable=variable_id,
                words=len(rewritten),
            )
        if share >= 1.0:
            since = state.fixed_since.setdefault(variable_id, tick)
            if (tick - since) * dt >= CLOSURE_GENERATIONS * group.generation_years:
                relics = sorted(morpheme_id for _, morpheme_id in queue)
                state.closed.add(variable_id)
                del state.pending[variable_id]
                state.queued.pop(variable_id, None)
                state.version += 1
                history.record(
                    "process_closed", tick, year, group=group_id, variable=variable_id,
                    restructured=len(state.restructured.get(variable_id, ())), relics=len(relics),
                )
        else:
            state.fixed_since.pop(variable_id, None)


def surface(world: World, group_id: str, morpheme_id: str) -> Form:
    """Dominantní povrchový tvar: podkladový tvar prohnaný živými procesy."""
    assert world.table is not None
    code = world.groups[group_id].main_code
    state = code.phonology
    form = analogical(world, group_id, morpheme_id).form
    for variable_id in active_processes(state, world):
        if morpheme_id in state.restructured.get(variable_id, ()):
            continue
        share = changed_share(world, group_id, variable_id)
        if share <= 0 or word_probability(world, variable_id, morpheme_id, share, code) < 0.5:
            continue
        changed = world.processes[variable_id].apply(form, world.table, code.stress_rule)
        if changed is not None:
            form = changed
    return form


def analogical(world: World, group_id: str, morpheme_id: str) -> UnitForm:
    """Podkladový tvar, nebo analogický tvar, který ve skupině převažuje."""
    code = world.groups[group_id].main_code
    unit = world.unit_of(code, morpheme_id)
    for variable_id, target in sorted(code.phonology.morph_active.items()):
        if target == morpheme_id and changed_share(world, group_id, variable_id) >= 0.5:
            from cee.v2.morphology import apply_form_change

            changed = apply_form_change(world, code, world.form_changes[variable_id])
            if changed is not None:
                unit = changed
    return unit


def lexicon(world: World, group_id: str) -> dict[str, Form]:
    """Pojem → povrchový tvar dominantního slova skupiny."""
    result: dict[str, Form] = {}
    for variable_id, variable in sorted(world.variables.items()):
        if variable.kind != "lexical":
            continue
        distribution = world.distribution(group_id, variable_id)
        if distribution is None:
            continue
        morpheme_id = world.variants[distribution.dominant()[0]].payload.get("morpheme")
        if isinstance(morpheme_id, str):
            result[variable.key] = surface(world, group_id, morpheme_id)
    return result

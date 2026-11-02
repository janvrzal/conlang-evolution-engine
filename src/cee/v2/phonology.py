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

import math
from array import array
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from cee.v2.history import History
from cee.v2.language.columns import ProcessQueue
from cee.v2.language.lexicon import PhonologyState, UnitForm
from cee.v2.language.processes import Process
from cee.v2.language.segments import Form
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.rng import generator, stable_id

if TYPE_CHECKING:
    from cee.v2.world import Code, World

# Prahy a rozptyl přepisu slov jsou data světa (``world.params``:
# ``restructure_threshold``, ``word_bias_sd``, ``frequency_lead``,
# ``closure_generations``, ``activation_share``).


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
    if variable_id in world.live and group_id in world.live.group_index:
        found = world.live.frequency(group_id, variable_id, changed_id(variable_id))
        return 0.0 if found is None else found
    distribution: Distribution | None = world.stored(group_id, variable_id)
    return 0.0 if distribution is None else distribution.frequency(changed_id(variable_id))


def _logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return math.log(p / (1 - p))


def word_bias(world: World, variable_id: str, morpheme_id: str) -> float:
    """Seedovaný sklon slova vůči změně; stejný ve všech skupinách.

    Patří lexému, ne jednotlivému tvaru: všechny buňky paradigmatu tak změnu
    přijmou (nebo odmítnou) společně a výjimka nevyrobí falešnou alternaci.
    Hodnota je čistá funkce (seed, proces, lexém, ``word_bias_sd``); svět si ji
    pamatuje v poli podle čísla lexému (jedno pole na proces).
    """
    registry = world.registry
    # Lexém ze sloupce morfémů (číslo morfému lexému); bez řádku sloupce slovník.
    numbers = registry.morphemes.numbers
    lexemes = world.columns.morphemes.lexeme
    found = numbers.get(morpheme_id)
    lexeme_number = lexemes[found] if found is not None and found < len(lexemes) else -1
    if lexeme_number < 0:
        lexeme = world.morphemes[morpheme_id].lexeme_id
        lexeme_number = numbers[lexeme]
    else:
        lexeme = registry.morphemes.names[lexeme_number]
    process = registry.processes.numbers.get(variable_id)
    if process is None:
        return _draw_bias(world, variable_id, lexeme)
    number = lexeme_number
    column = world.word_biases.get(process)
    if column is None:
        column = world.word_biases[process] = array("d")
    if number >= len(column):
        column.extend(array("d", [math.nan]) * (len(registry.morphemes) - len(column)))
    bias = column[number]
    if bias != bias:
        bias = column[number] = _draw_bias(world, variable_id, lexeme)
    return bias  # type: ignore[no-any-return]


def _draw_bias(world: World, variable_id: str, lexeme: str) -> float:
    return float(generator(world.seed, "word-bias", variable_id, lexeme).normal(0.0, world.params.word_bias_sd))


def _lead(world: World, process: Process, morpheme_id: str, code: Code | None = None) -> float:
    lexeme = world.morphemes[morpheme_id].lexeme_id
    frequency = world.usage_frequency(code, lexeme) if code is not None else world.morphemes[lexeme].frequency
    return world.params.frequency_lead * (2.0 * frequency - 1.0) if process.reductive else 0.0


def _leads(world: World, process: Process, morpheme_ids: list[str], code: Code) -> list[float]:
    """:func:`_lead` pro víc morfémů najednou (stejné hodnoty, jedno ověření paměti frekvencí)."""
    if not process.reductive:
        return [0.0] * len(morpheme_ids)
    morphemes = world.morphemes
    lexemes = [morphemes[morpheme_id].lexeme_id for morpheme_id in morpheme_ids]
    lead = world.params.frequency_lead
    return [lead * (2.0 * frequency - 1.0) for frequency in world.usage_frequencies(code, lexemes)]


def word_probability(
    world: World, variable_id: str, morpheme_id: str, share: float, code: Code | None = None
) -> float:
    process = world.processes[variable_id]
    value = _logit(share) + _lead(world, process, morpheme_id, code) + word_bias(world, variable_id, morpheme_id)
    return 1.0 / (1.0 + math.exp(-value))


def _needed(world: World, variable_id: str, morpheme_id: str, code: Code | None = None) -> float:
    """Logit sdíleného podílu, při kterém si slovo změnu zapíše."""
    process = world.processes[variable_id]
    threshold = world.params.restructure_threshold
    return (
        math.log(threshold / (1 - threshold)) - _lead(world, process, morpheme_id, code)
        - word_bias(world, variable_id, morpheme_id)
    )


def _applies(world: World, code: Code, variable_id: str, morpheme_id: str) -> bool:
    # Tabulka procesu v bance tvarů: každý různý tvar se posoudí jednou za běh.
    table = world.form_bank().process_table(world.processes[variable_id], code.stress_rule)
    return table.result(world.form_id_of(code, morpheme_id)) >= 0


def _queue(world: World, code: Code, variable_id: str, morpheme_id: str) -> None:
    state = code.phonology
    queue = state.pending.get(variable_id)
    if queue is None:
        queue = state.pending[variable_id] = ProcessQueue(state.registry.morphemes)
    waiting = state.queued.get(variable_id)
    if waiting is None:
        waiting = state.queued[variable_id] = state.morpheme_set()
    if morpheme_id in state.restructured.get(variable_id, ()):
        return
    if morpheme_id in waiting:
        return
    if _applies(world, code, variable_id, morpheme_id):
        queue.insert(_needed(world, variable_id, morpheme_id, code), morpheme_id)
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
    state.order[variable_id] = len(state.order)
    state.record_lifecycle("process", "activate", variable_id)
    # Celá slovní zásoba se posoudí jedním vyhledáním v tabulce procesu;
    # do fronty jdou jen slova, která změna opravdu mění.
    words = sorted(state.vocabulary)
    bank = world.form_bank()
    results = bank.process_table(world.processes[variable_id], code.stress_rule).results(
        np.fromiter((world.form_id_of(code, morpheme_id) for morpheme_id in words), np.int64, len(words))
    )
    # Fronta vznikne naráz: tabulka už řekla, kterých slov se změna týká
    # (to, co by ``_queue`` ověřil znovu), a čekající jsou seřazena podle
    # dvojice (potřebný logit, morfém), tedy úplně, stejně jako po vkládání.
    restructured = state.restructured.get(variable_id, ())
    hits = [
        morpheme_id for morpheme_id, result in zip(words, results.tolist())
        if result >= 0 and morpheme_id not in restructured
    ]
    process = world.processes[variable_id]
    threshold = world.params.restructure_threshold
    base = math.log(threshold / (1 - threshold))
    leads = _leads(world, process, hits, code)
    state.pending[variable_id] = ProcessQueue(
        state.registry.morphemes,
        ((base - lead - word_bias(world, variable_id, morpheme_id), morpheme_id)
         for morpheme_id, lead in zip(hits, leads)),
    )
    state.queued[variable_id] = state.morpheme_set(hits)


def enter_vocabulary(world: World, code: Code, morpheme_id: str) -> None:
    """Slovo se stalo dominantním: projdou jím i změny, které právě běží."""
    state = code.phonology
    if not state.enter_vocabulary(morpheme_id):
        return
    state.version += 1
    state.lexicon_version += 1
    for variable_id in active_processes(state, world):
        _queue(world, code, variable_id, morpheme_id)


def leave_vocabulary(code: Code, morpheme_id: str) -> None:
    state = code.phonology
    if state.leave_vocabulary(morpheme_id):
        state.version += 1
        state.lexicon_version += 1


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
    morphemes = state.registry.morphemes.names
    for variable_id in active_processes(state, world):
        share = changed_share(world, group_id, variable_id)
        queue = state.pending[variable_id]
        level = _logit(share) if share > 0 else -math.inf
        rewritten: list[str] = []
        while queue and queue.needed[0] < level:
            morpheme_id = morphemes[queue.pop_first()]
            state.queued[variable_id].discard(morpheme_id)
            process = world.processes[variable_id]
            unit = world.unit_of(code, morpheme_id)
            new = process.apply_tracked(unit.form, world.table, code.stress_rule, unit.boundary)
            if new is None:
                continue  # dřívější přepis jinou změnou mu vzal půdu
            code.forms.set(morpheme_id, UnitForm(new[0], new[1], unit.exponent))
            state.restructured.setdefault(variable_id, state.morpheme_set()).add(morpheme_id)
            state.version += 1
            rewritten.append(morpheme_id)
            # Nový tvar posoudí jen změny, které v něm podle předfiltru banky
            # mohou mít místo; u ostatních by fronta nic neudělala.
            bank = world.form_bank()
            rewritten_id, rule = world.form_id_of(code, morpheme_id), code.stress_rule
            for other in active_processes(state, world):
                if other != variable_id and bank.may_apply(rewritten_id, rule, world.processes[other].key):
                    _queue(world, code, other, morpheme_id)
        if rewritten:
            history.record(
                "phonologized", tick, year, group=group_id, variable=variable_id,
                words=len(rewritten),
            )
        if share >= 1.0:
            since = state.fixed_since.setdefault(variable_id, tick)
            if (tick - since) * dt >= world.params.closure_generations * group.generation_years:
                relics = sorted(queue.names())
                state.closed.add(variable_id)
                state.record_lifecycle("process", "close", variable_id)
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

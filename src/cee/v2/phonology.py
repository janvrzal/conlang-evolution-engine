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
from array import array
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from cee.v2 import native
from cee.v2.history import History
from cee.v2.language.columns import MorphemeSet, ProcessQueue
from cee.v2.language.lexicon import PhonologyState, UnitForm
from cee.v2.language.processes import Process
from cee.v2.language.segments import Form
from cee.v2.repertoire import Distribution, Origin, Variable, Variant
from cee.v2.rng import Stream, stable_id

if TYPE_CHECKING:
    from cee.v2.language.processes import StressRule
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
    return Stream(world.seed, "word-bias", variable_id, lexeme).normal(0.0, world.params.word_bias_sd)


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


def requeue_all(world: World, code: Code, morpheme_id: str) -> None:
    """:func:`requeue` pro všechny živé procesy kódu v pořadí jejich vzniku (v Rustu naráz)."""
    _queue_all(world, code, morpheme_id)


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
    if _activate_native(world, code, variable_id):
        return
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
    _queue_all(world, code, morpheme_id)


def leave_vocabulary(code: Code, morpheme_id: str) -> None:
    state = code.phonology
    if state.leave_vocabulary(morpheme_id):
        state.version += 1
        state.lexicon_version += 1


# --- Krok fonologizace v Rustu --------------------------------------------------------
#
# Rozhraní (``cee_core.NativeBank``): ``restructure_step`` (cyklus odebírání z
# fronty jednoho procesu), ``queue_morpheme`` (zařazení morfému do front) a
# ``activate`` (fronta nového procesu). Rust dostane existující pole (tvary
# kódu, sloupce morfémů světa, příznaky front a přepsaných morfémů, sklony slov)
# a vrátí rozhodnutí; zapisuje Python, ve stejném pořadí jako dřív. Co Rust
# nemá (losované sklony slov, četnosti užití, výchozí tvary, mapy hlásek pro
# ``change`` a ``tone``), vyžádá jako ``needs`` a nic nezapíše; Python to
# doplní a volá znovu. Bez Rustu (``CEE_NATIVE=0``, jiná verze rozhraní, zmrazené
# tvary) běží původní kód níže beze změny.

_EMPTY_FLAGS = bytearray()


def _kernel(world: World, code: Code) -> Any | None:
    """Banka v Rustu pro krok fonologizace, nebo ``None`` (pak počítá Python).

    Rust se nepoužije bez rozšíření, s ``CEE_NATIVE=0``, u zmrazených tvarů a
    u kódu, jehož úložiště tvarů nepatří světu (číslování morfémů by nesedělo).
    """
    if not native.enabled() or world.table is None:
        return None
    store = code.forms
    if store.frozen or store.context is not world:
        return None
    return world.form_bank()._native


def _bias_column(world: World, variable_id: str) -> array | None:  # type: ignore[type-arg]
    """Sloupec sklonů slov procesu (NaN = ještě nelosováno), dorostlý na všechny morfémy."""
    number = world.registry.processes.numbers.get(variable_id)
    if number is None:
        return None
    column = world.word_biases.get(number)
    if column is None:
        column = world.word_biases[number] = array("d")
    missing = len(world.registry.morphemes) - len(column)
    if missing > 0:
        column.extend(array("d", [math.nan]) * missing)
    return column


def _targets(
    world: World, code: Code, actives: list[str], rule: StressRule, *, strict: bool
) -> tuple[list[Any], ...] | None:
    """Fronty živých procesů pro Rust: řádek změny, příznaky, sklony, redukčnost.

    ``strict`` je pravidlo ``restructure``: proces, jehož tabulka s pravidlem
    přízvuku kódu v bance ještě není, se přeskočí (řádek −1), stejně jako ho
    přeskočil ``FormBank.may_apply``. Jinak se tabulka založí (jako v ``_applies``).
    """
    state = code.phonology
    bank = world.form_bank()
    processes = world.processes
    known = bank._rule_rows.get(rule) if strict else None
    rows: list[int] = []
    queued: list[Any] = []
    restructured: list[Any] = []
    biases: list[Any] = []
    reductive: list[bool] = []
    for variable_id in actives:
        process = processes[variable_id]
        column = _bias_column(world, variable_id)
        if column is None:
            return None
        if strict:
            rows.append(-1 if known is None else known.get(process.key, -1))
        else:
            rows.append(bank.process_table(process, rule).index)
        waiting = state.queued.get(variable_id)
        if waiting is None:
            waiting = state.queued[variable_id] = state.morpheme_set()
        done = state.restructured.get(variable_id)
        queued.append(waiting.flags)
        restructured.append(_EMPTY_FLAGS if done is None else done.flags)
        biases.append(column)
        reductive.append(process.reductive)
    return rows, queued, restructured, biases, reductive


def _constants(world: World) -> tuple[float, float]:
    """Základ logitu prahu fonologizace a váha frekvence (součásti ``_needed``)."""
    threshold = world.params.restructure_threshold
    return math.log(threshold / (1 - threshold)), world.params.frequency_lead


def _columns(world: World) -> tuple[Any, Any, Any, Any]:
    """Výchozí tvar, hranice, koncovka a lexém každého morfému ze sloupců světa."""
    columns = world.columns.morphemes
    return columns.form, columns.boundary, columns.exponent, columns.lexeme


def _frequencies(world: World, code: Code, lexemes: Any, known: dict[int, float]) -> None:
    """Doplní do ``known`` četnosti užití lexémů (podle čísla), které tam ještě nejsou."""
    missing = [lexeme for lexeme in lexemes if lexeme not in known]
    if missing:
        names = world.registry.morphemes.names
        for lexeme, frequency in zip(missing, world.usage_frequencies(code, [names[n] for n in missing])):
            known[lexeme] = frequency


def _resolve(
    world: World, code: Code, needs: tuple[Any, Any, Any, Any], variable_ids: list[str],
    known: dict[int, float],
) -> None:
    """Doplní, co Rust vyžádal: sklony slov, četnosti, výchozí tvary a mapy hlásek."""
    biases, frequencies, forms, maps = needs
    names = world.registry.morphemes.names
    for target, morpheme in biases:
        word_bias(world, variable_ids[target], names[morpheme])
    if frequencies:
        _frequencies(world, code, frequencies, known)
    for morpheme in forms:
        world.form_id_of(code, names[morpheme])
    bank = world.form_bank()
    for row, segments in maps:
        bank._resolve(row, segments)


def _complete(
    world: World, code: Code, variable_ids: list[str], known: dict[int, float], call: Any,
) -> tuple[Any, ...]:
    """Zavolá Rust a dokud vyžaduje doplnění, doplňuje a volá znovu; vrací úplnou odpověď.

    Odpověď je úplná, když ``needs`` (její první položka) je prázdné. Nové tvary,
    které vznikly v Rustu (poslední tři položky odpovědi), banka převezme pokaždé.
    """
    bank = world.form_bank()
    previous = None
    while True:
        answer: tuple[Any, ...] = call()
        bank._adopt(*answer[-3:])
        needs = answer[0]
        if not any(needs):
            return answer
        if needs == previous:
            raise RuntimeError(f"Rust opakovaně vyžaduje totéž, bez pokroku: {needs!r}")
        previous = needs
        _resolve(world, code, needs, variable_ids, known)


def _queue_all(world: World, code: Code, morpheme_id: str) -> None:
    """``_queue`` pro všechny živé procesy kódu v pořadí jejich vzniku (v Rustu naráz)."""
    state = code.phonology
    actives = active_processes(state, world)
    handle = _kernel(world, code) if actives else None
    number = world.registry.morphemes.numbers.get(morpheme_id)
    rule = code.stress_rule
    targets = None if handle is None or number is None else _targets(world, code, actives, rule, strict=False)
    columns = _columns(world)
    if targets is None or number >= len(columns[3]) or columns[3][number] < 0:
        for variable_id in actives:
            _queue(world, code, variable_id, morpheme_id)
        return
    known: dict[int, float] = {}
    if any(targets[4]):
        _frequencies(world, code, [columns[3][number]], known)
    base, lead = _constants(world)
    store = code.forms.raw()
    code_rule = native.RULES.index(rule)
    answer = _complete(
        world, code, actives, known,
        lambda: handle.queue_morpheme(code_rule, base, lead, store, columns, targets, known, number),
    )
    _, queue_ids, morphemes, logits = answer[:4]
    names = world.registry.morphemes.names
    for target, found, needed in zip(queue_ids, morphemes, logits):
        variable_id = actives[target]
        state.pending[variable_id].insert(needed, names[found])
        state.queued[variable_id].add_number(found)


def _activate_native(world: World, code: Code, variable_id: str) -> bool:
    """:func:`activate` v Rustu; ``False``, když Rust není k dispozici (pak aktivuje Python)."""
    handle = _kernel(world, code)
    if handle is None:
        return False
    state = code.phonology
    rule = code.stress_rule
    process = world.processes[variable_id]
    column = _bias_column(world, variable_id)
    if column is None:
        return False
    row = world.form_bank().process_table(process, rule).index
    done = state.restructured.get(variable_id)
    targets = (
        [row], [_EMPTY_FLAGS], [_EMPTY_FLAGS if done is None else done.flags], [column], [process.reductive],
    )
    base, lead = _constants(world)
    store, columns, code_rule = code.forms.raw(), _columns(world), native.RULES.index(rule)
    known: dict[int, float] = {}
    answer = _complete(
        world, code, [variable_id], known,
        lambda: handle.activate(code_rule, base, lead, store, columns, targets, known, row, state.vocabulary.flags),
    )
    _, morphemes, logits = answer[:3]
    names = state.registry.morphemes.names
    # Rust řadí shodné logity podle čísla morfému, fronta podle jména: každý úsek shodných logitů se srovná.
    ordered = list(morphemes)
    values = np.array(logits, dtype=np.float64)
    tied = np.flatnonzero(values[1:] == values[:-1]).tolist()
    position = 0
    while position < len(tied):
        last = position
        while last + 1 < len(tied) and tied[last + 1] == tied[last] + 1:
            last += 1
        low, high = tied[position], tied[last] + 2
        ordered[low:high] = sorted(ordered[low:high], key=names.__getitem__)
        position = last + 1
    queue = ProcessQueue(state.registry.morphemes)
    queue.needed = array("d", logits)
    queue.morphemes = array("i", ordered)
    state.pending[variable_id] = queue
    state.queued[variable_id] = MorphemeSet.from_numbers(state.registry.morphemes, ordered)
    return True


@dataclass(frozen=True)
class Phonologized:
    group: str
    variable: str
    words: tuple[str, ...]


def _pop_python(
    world: World, code: Code, variable_id: str, queue: ProcessQueue, level: float
) -> list[str]:
    """Cyklus fonologizace jednoho procesu v Pythonu: přepíše slova, která došla na práh."""
    state = code.phonology
    morphemes = state.registry.morphemes.names
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
    return rewritten


class _Kit:
    """Fronty živých procesů kódu pro Rust, sestavené jednou za ``restructure``.

    Pole (příznaky front, sklony, ...) zůstávají po celý krok tytéž objekty, proto
    se nemusí sestavovat pro každý proces zvlášť. Uzavřený proces se přeskočí
    (řádek −1); příznaky přepsaných morfémů procesu, který je teprve založil,
    se doplní (``adopt_done``).
    """

    __slots__ = ("order", "rows", "queued", "restructured", "biases", "reductive", "queues", "known")

    def __init__(self, order: list[str], targets: tuple[list[Any], ...], queues: list[ProcessQueue]) -> None:
        self.order = order
        self.rows, self.queued, self.restructured, self.biases, self.reductive = targets
        self.queues = queues
        #: Četnosti užití lexémů spočítané v tomto kroku.
        self.known: dict[int, float] = {}

    def targets(self) -> tuple[list[Any], ...]:
        return self.rows, self.queued, self.restructured, self.biases, self.reductive


def _pop_native(
    world: World, code: Code, handle: Any, variable_id: str, kit: list[_Kit | None], live: list[str],
    queue: ProcessQueue, level: float,
) -> list[str] | None:
    """:func:`_pop_python` v Rustu; ``None``, když ho Rust převzít nemůže (pak jde Python).

    Rust odebírá z čela fronty a rozhoduje, kam se přepsané slovo zařadí; zápis
    (tvary, příznaky, fronty, verze) dělá Python po dávkách ve stejném pořadí
    jako dřív. Chybí-li Rustu sklon slova, zastaví se před dalším slovem, Python
    zapíše, co se stalo, doplní sklon a pokračuje.
    """
    count = bisect.bisect_left(queue.needed, level)
    if count == 0:
        return []
    state = code.phonology
    process = world.processes[variable_id]
    bank = world.form_bank()
    row = bank._proc_index.get(process.key)
    columns = _columns(world)
    lexemes = columns[3]
    heads = queue.morphemes[:count]
    if row is None or any(head >= len(lexemes) or lexemes[head] < 0 for head in heads):
        return None
    rule = code.stress_rule
    held = kit[0]
    if held is None:
        built = _targets(world, code, live, rule, strict=True)
        if built is None:
            return None
        held = kit[0] = _Kit(list(live), built, [state.pending[other] for other in live])
    order, rows = held.order, held.rows
    # Procesy uzavřené dřív v tomto kroku už cílem nejsou.
    for position, other in enumerate(order):
        if other not in state.pending:
            rows[position] = -1
    known = held.known
    if any(held.reductive):
        # Náskok z četnosti užití potřebuje každý přepsaný lexém; spočítá se předem.
        _frequencies(world, code, {lexemes[head] for head in heads}, known)
    base, lead = _constants(world)
    store, code_rule, skip = code.forms.raw(), native.RULES.index(rule), order.index(variable_id)
    names = state.registry.morphemes.names
    waiting = state.queued[variable_id]
    targets = held.targets()
    rewritten: list[str] = []
    previous = None
    while True:
        (needs, popped, moved, forms, cuts, exponents, targeted, queued, logits, first, flat, lengths) = (
            handle.restructure_step(
                code_rule, base, lead, store, columns, targets, known, row,
                (queue.needed, queue.morphemes), level, skip,
            )
        )
        bank._adopt(first, flat, lengths)
        if popped:
            for number in queue.morphemes[:popped]:
                waiting.discard_number(number)
            del queue.needed[:popped]
            del queue.morphemes[:popped]
        if moved:
            done = state.restructured.get(variable_id)
            if done is None:
                done = state.restructured[variable_id] = state.morpheme_set()
            held.restructured[skip] = done.flags
            for number, form_id, cut, exponent in zip(moved, forms, cuts, exponents):
                code.forms.put(number, form_id, cut, exponent)
                done.add_number(number)
                state.version += 1
                rewritten.append(names[number])
        for target, number, needed in zip(targeted, queued, logits):
            held.queues[target].insert(needed, names[number])
            state.queued[order[target]].add_number(number)
        if not any(needs):
            return rewritten
        if not popped and needs == previous:
            raise RuntimeError(f"Rust opakovaně vyžaduje totéž, bez pokroku: {needs!r}")
        previous = needs
        _resolve(world, code, needs, order, known)


def restructure(world: World, group_id: str, tick: int, dt: float, history: History, year: float) -> None:
    """Fonologizace a uzavírání procesů v jedné skupině (krok 6 ticku)."""
    group = world.groups[group_id]
    code = group.main_code
    state = code.phonology
    assert world.table is not None
    handle = _kernel(world, code)
    live = active_processes(state, world)
    kit: list[_Kit | None] = [None]
    for variable_id in list(live):
        share = changed_share(world, group_id, variable_id)
        queue = state.pending[variable_id]
        level = _logit(share) if share > 0 else -math.inf
        rewritten = None if handle is None else _pop_native(world, code, handle, variable_id, kit, live, queue, level)
        if rewritten is None:
            rewritten = _pop_python(world, code, variable_id, queue, level)
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
                live.remove(variable_id)
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

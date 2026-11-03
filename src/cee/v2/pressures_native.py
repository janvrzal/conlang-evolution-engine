"""Tlaky v Rustu: příprava vstupů pro ``NativeCells.transmit`` (krok B3b).

S Rustem počítá tlaky na varianty sám přenos bloku (``cee_core``, ``pressures.rs``): Python mu
jednou za krok dá :class:`PressureStep` (skupiny, sloupce variant, plán tlaků) a pro každý blok popis
řádků (druh proměnné, pojem, proces, slot změny; ten se drží u bloku, dokud se řádky a sloty nezmění)
a řídké položky tlaků, které se počítají z objektů světa (škola, tabu, konstrukce). Zpětné volání
do Pythonu pro tlaky odpadá. Rozhraní, které bude B6 (hlavní smyčka v Rustu) potřebovat, jsou tato
pole; co dnes dodává Python na požádání (:class:`Supplier`: výběr vzorku a jeho váhy, výchozí tvary
mimo banku a v aréně morfologického indexu, mapy hlásek procesů, nahraditelnost buněk, podíl koncových
souhlásek), se v B6 přesune do Rustu. Hodnocení analogických změn tvarů (B6b) počítá Rust sám ze
stavu morfologického indexu míst, úložiště tvarů kódů a dominantních kořenů (``form_assess.rs``).

Tlaky, které tento modul nezná (vlastní třídy), a režimy bez Rustu jdou dál cestou
``transmission.fitness_of``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import native
from cee.v2.assessment import SAMPLE_WORDS, _redundant_cell
from cee.v2.language.assessment_index import NativeAssessmentIndex, index_of
from cee.v2.language.lexical_index import _default_form, related_keys
from cee.v2.language.site_index import site_index
from cee.v2.phonology import changed_id
from cee.v2.pressures.base import Pressure, PressureBatch
from cee.v2.pressures.lexical import _MOTIVATION, Taboo
from cee.v2.pressures.linguistic import coda_share
from cee.v2.pressures.social import Actuation, Norm
from cee.v2.rng import stable_int
from cee.v2.tables import VARIABLE_KINDS

if TYPE_CHECKING:
    from cee.v2.pools import PoolBlock
    from cee.v2.transmission import StepInputs
    from cee.v2.world import Code, World

#: Čísla tlaků v Rustu (``pressures::id``), podle jména tlaku.
PRESSURE_IDS = {
    "actuation": 0, "ambiguity": 1, "appeal": 2, "articulation": 3, "clarity": 4, "conformity": 5,
    "conservation": 6, "dispersion": 7, "distinctiveness": 8, "economy": 9, "entrenchment": 10,
    "expressivity": 11, "functional_load": 12, "fusion": 13, "lexical_actuation": 14,
    "lexical_clarity": 15, "learnability": 16, "motivation": 17, "norm": 18, "phonotactics": 19,
    "taboo": 20, "teachability": 21, "uniformity": 22,
}
_NORM, _TABOO = PRESSURE_IDS["norm"], PRESSURE_IDS["taboo"]
_CONSTRUCTION = ("ambiguity", "economy", "expressivity", "fusion", "learnability")

#: Příznaky řádku (viz ``pressures.rs``).
REDUCTIVE_UNSTRESSED, APOCOPE, LEVEL, LEXEME_WIDE = 1, 2, 4, 8
_KIND = {kind: number for number, kind in enumerate(VARIABLE_KINDS)}
_PROCESS, _LEXICAL, _FORM, _CONSTRUCTION_KIND = (_KIND[name] for name in ("process", "lexical", "form", "construction"))


def adopt_created(world: World) -> None:
    """Převezme tvary, které Rust vytvořil při hodnocení (výsledky procesů), pod jejich čísly."""
    bank = world.form_bank()
    if bank._native is None:
        return
    module = native._load()
    assert module is not None
    first, flat, lengths = module.take_created(bank._native)
    bank._adopt(first, flat, lengths)


def plan_of(pressures: Mapping[str, Sequence[tuple[Pressure, float]]]) -> list[list[tuple[int, float]]] | None:
    """Plán tlaků pro Rust (pro každý druh proměnných dvojice číslo tlaku a váha), nebo ``None``, je-li některý neznámý."""
    plan: list[list[tuple[int, float]]] = [[] for _ in VARIABLE_KINDS]
    for kind, weighted in pressures.items():
        if kind not in _KIND:
            return None
        for pressure, strength in weighted:
            number = PRESSURE_IDS.get(pressure.name)
            if number is None or not type(pressure).__module__.startswith("cee.v2.pressures"):
                return None
            plan[_KIND[kind]].append((number, float(strength)))
    return plan


class Supplier:
    """Odpovídá na to, co si Rust při tlacích a hodnocení vyžádá (viz ``assess_index::Needs``).

    Jedna instance patří jednomu kroku: zná kódy skupin v pořadí, jak je Rust číslu je (pozice).
    Metody nic nevrací Rustu přímo, kromě ``redundant`` a ``coda`` (hodnoty, které si Rust uloží);
    ostatní zapisují do světa či do indexu a Rust při dalším průchodu čte aktualizovaný stav.
    Hodnocení analogických změn tvarů už Python nedodává: Rust si je spočítá sám.
    """

    def __init__(self, world: World, codes: Sequence[Code], group_ids: Sequence[str], index: NativeAssessmentIndex):
        self.world, self.codes, self.group_ids, self.index = world, codes, group_ids, index

    def adopt(self) -> None:
        adopt_created(self.world)

    def samples(self, groups: list[int]) -> None:
        """Přepočítá vzorek (výběr a váhy) kódů a předá ho Rustu."""
        self.adopt()
        for group in groups:
            code = self.codes[group]
            token = code.forms.token
            keeper = self.index.keeper(token)
            keeper.refresh(self.world, code, SAMPLE_WORDS)
            self.index.handle.set_sample(token, code.phonology.version, keeper.morphemes, keeper.weights, keeper.total)

    def defaults(self, items: list[tuple[int, int]]) -> None:
        """Zařadí do banky výchozí tvary morfémů (zapíše je do sloupce morfémů světa), i když je kód přepsal."""
        self.adopt()
        for _, morpheme in sorted({(0, morpheme) for _, morpheme in items}):
            _default_form(self.world, morpheme)

    def maps(self, items: list[tuple[int, list[int]]]) -> None:
        """Spočítá mapy hlásek operací ``change`` a ``tone`` pro řádky změn."""
        self.adopt()
        bank = self.world.form_bank()
        for row, segments in items:
            bank._resolve(row, segments)

    def redundant(self, items: list[tuple[int, int]]) -> list[bool]:
        """Je buňka paradigmatu morfému ve skupině nahrazena jinou konstrukcí?"""
        names = self.world.registry.morphemes.names
        morphemes = self.world.morphemes
        return [
            _redundant_cell(self.world, self.group_ids[group], morphemes[names[morpheme]])
            for group, morpheme in items
        ]

    def coda(self, groups: list[int]) -> list[float]:
        """Podíl slov se souhláskovou koncovkou ve slovní zásobě skupin."""
        return [coda_share(self.world, self.group_ids[group]) for group in groups]

    def morph_defaults(self, numbers: list[int]) -> None:
        """Doplní výchozí tvary morfémů do arény morfologického indexu míst (hodnocení tvarů je čte)."""
        site_index(self.world)._supply_defaults(self.world, sorted(numbers))

    def supply(self, needs: tuple[Any, ...]) -> list[tuple[int, int, bool]]:
        """Totéž, co dělá Rust při přenosu, pro volání z Pythonu; vrací odpovědi na ``redundant``."""
        samples, defaults, maps, redundant, _coda, morph_defaults = needs
        if samples:
            self.samples(list(samples))
        if defaults:
            self.defaults(list(defaults))
        if maps:
            self.maps([(row, list(segments)) for row, segments in maps])
        found: list[tuple[int, int, bool]] = []
        if redundant:
            items = [(int(group), int(morpheme)) for group, morpheme in redundant]
            found = [(group, morpheme, value) for (group, morpheme), value in zip(items, self.redundant(items))]
        if morph_defaults:
            self.morph_defaults(list(morph_defaults))
        return found


class RowsPack:
    """Popis řádků bloku pro Rust (druh, proměnná, pojem, proces a příznaky); drží se u bloku podle ``layout``."""

    __slots__ = ("kind", "variable", "concept", "changed", "proc_row", "ease", "clarity", "flags",
                 "lexical", "concepts", "protection_key", "protection")

    def __init__(self, world: World, block: PoolBlock, index: NativeAssessmentIndex, rule: str) -> None:
        count = len(block)
        self.kind = np.zeros(count, dtype=np.uint8)
        self.variable = np.zeros(count, dtype=np.int64)
        self.concept = np.full(count, -1, dtype=np.int64)
        self.changed = np.full(count, -1, dtype=np.int32)
        self.proc_row = np.full(count, -1, dtype=np.int32)
        self.ease = np.zeros(count, dtype=np.float64)
        self.clarity = np.zeros(count, dtype=np.float64)
        self.flags = np.zeros(count, dtype=np.uint8)
        lexical: list[int] = []
        concepts: list[str] = []
        registry = world.registry
        for row, variable_id in enumerate(block.variable_ids):
            variable = world.variables[variable_id]
            self.kind[row] = _KIND[variable.kind]
            self.variable[row] = registry.variables.intern(variable_id)
            if variable.kind == "lexical":
                concept = variable_id.split(":", 1)[1]
                self.concept[row] = registry.concepts.intern(concept)
                lexical.append(row)
                concepts.append(concept)
            elif variable.kind in ("process", "form"):
                slots = block.slots[row]
                changed = changed_id(variable_id)
                if variable.kind == "process":
                    process = world.processes.get(variable_id)
                    if process is None or changed not in slots:
                        continue
                    number, proc_row = index.ensure_process(world, variable_id, rule)
                    self.proc_row[row] = proc_row
                    self.ease[row], self.clarity[row] = process.ease, process.clarity
                    self.flags[row] = (
                        (REDUCTIVE_UNSTRESSED if getattr(process, "reductive", False)
                         and getattr(process, "stress", None) == "unstressed" else 0)
                        | (APOCOPE if getattr(process, "family", "") == "apocope" else 0)
                    )
                else:
                    change = world.form_changes.get(variable_id)
                    if change is None or changed not in slots:
                        continue
                    index.ensure_form(world, variable_id)
                    self.flags[row] = (LEVEL if change.operation == "level" else 0) | (
                        LEXEME_WIDE if change.lexeme_wide else 0)
                self.changed[row] = slots.index(changed)
        self.lexical = np.array(lexical, dtype=np.intp)
        self.concepts = concepts
        self.protection_key: object = None
        self.protection = np.zeros(count, dtype=np.float64)

    def protect(self, world: World) -> npt.NDArray[np.float64]:
        """Ochrana zažitého slova podle řádku (``Entrenchment``); přepočítá se při změně frekvencí pojmů."""
        frequencies = world.concept_frequencies
        version = getattr(frequencies, "version", None)
        key = None if version is None else (id(frequencies), version)
        if key is not None and key == self.protection_key:
            return self.protection
        if len(self.lexical):
            params = world.params
            frequency = np.array([world.concept_frequency(concept) for concept in self.concepts])
            if params.entrenchment_frequency_exponent != 1.0:
                frequency = frequency**params.entrenchment_frequency_exponent
            protection = params.entrenchment_strength * frequency
            if params.entrenchment_base != 0.0:
                protection = params.entrenchment_base + protection
            self.protection = np.zeros(len(self.kind), dtype=np.float64)
            self.protection[self.lexical] = protection
        self.protection_key = key
        return self.protection


def _padded(array: npt.NDArray[Any], size: int, fill: Any) -> npt.NDArray[Any]:
    """Pole nejméně ``size`` dlouhé (sloupec tabulky variant může být kratší než číslování)."""
    if len(array) >= size:
        return np.ascontiguousarray(array)
    out = np.full(size, fill, dtype=array.dtype)
    out[: len(array)] = array
    return out


def _actuation_keys(world: World, index: NativeAssessmentIndex, inputs: StepInputs) -> npt.NDArray[np.uint64]:
    """Klíče ocenění změn skupin v epoše (stejné jako ``Actuation.scores``); drží se po dobu epochy."""
    epoch = inputs.tick // Actuation.epoch_ticks
    key = (epoch, tuple(inputs.group_ids))
    held = index.scratch.get("actuation-keys")
    if held is not None and held[0] == key:
        return held[1]  # type: ignore[no-any-return]
    keys = np.array([stable_int(world.seed, "actuation", epoch, group) for group in inputs.group_ids], dtype=np.uint64)
    index.scratch["actuation-keys"] = (key, keys)
    return keys


def _variant_keys(world: World, index: NativeAssessmentIndex, size: int) -> npt.NDArray[np.uint64]:
    """Klíč ocenění každé varianty (``stable_int("actuation", id varianty)``) podle čísla varianty."""
    held = index.scratch.get("variant-keys")
    names = world.registry.variants.names
    have = 0 if held is None else len(held)
    if have < len(names):
        more = np.array([stable_int("actuation", names[number]) for number in range(have, len(names))],
                        dtype=np.uint64)
        held = more if held is None else np.concatenate([held, more])
        index.scratch["variant-keys"] = held
    assert held is not None
    return _padded(held, size, 0)


def _dominant_order(index: NativeAssessmentIndex, code: Code, stamp: int) -> Any:
    """Čísla pojmů s dominantním kořenem v pořadí vložení do mapy (``int32``); drží se, dokud se mapa nezmění.

    Na pořadí stojí pořadí sčítání frekvencí pojmů jednoho kořene, tedy bitová shoda ``usage_frequency``.
    """
    held = index.scratch.setdefault("dominant-order", {})
    found = held.get(code.forms.token)
    if found is not None and found[0] == stamp:
        return found[1]
    order = code.phonology.dominant.order
    array = np.fromiter(order, dtype=np.int32, count=len(order))
    held[code.forms.token] = (stamp, array)
    return array


def _concept_frequencies(world: World, index: NativeAssessmentIndex) -> npt.NDArray[np.float64]:
    """Frekvence pojmů podle čísla pojmu (chybějící 0,3 jako ``World.concept_frequency``); drží se po verzi."""
    frequencies = world.concept_frequencies
    concepts = world.registry.concepts
    version = getattr(frequencies, "version", None)
    key = (id(frequencies), version, len(concepts))
    held = index.scratch.get("concept-frequencies")
    if version is not None and held is not None and held[0] == key:
        return held[1]  # type: ignore[no-any-return]
    found = np.full(len(concepts), 0.3, dtype=np.float64)
    numbers = concepts.numbers
    for concept, value in frequencies.items():
        number = numbers.get(concept)
        if number is not None:
            found[number] = value
    index.scratch["concept-frequencies"] = (key, found)
    return found


def _paradigm_weights(world: World, index: NativeAssessmentIndex) -> tuple[npt.NDArray[np.float64], int]:
    """Váha buňky paradigmatu podle (třída slova, buňka) po řádcích a počet buněk; 1 tam, kde se neváží."""
    table = world.columns.morphemes
    classes, cells = table.word_classes, table.cells
    key = (len(classes), len(cells), len(world.paradigms))
    held = index.scratch.get("paradigm-weights")
    if held is not None and held[0] == key:
        return held[1], held[2]  # type: ignore[no-any-return]
    width = max(len(cells), 1)
    weights = np.ones(len(classes) * width, dtype=np.float64)
    for word_class, paradigm in world.paradigms.items():
        row = classes.numbers.get(word_class)
        if row is None:
            continue
        for cell, weight in zip(paradigm.cells, paradigm.weights):
            column = cells.numbers.get(cell)
            if column is not None:
                weights[row * width + column] = weight
    index.scratch["paradigm-weights"] = (key, weights, width)
    return weights, width


def _step(
    world: World, inputs: StepInputs, index: NativeAssessmentIndex, plan: list[list[tuple[int, float]]], sites: Any,
) -> Any:
    """Vstupy kroku pro Rust (jednou za krok, sdílí je všechny bloky)."""
    module = native._load()
    assert module is not None
    group_ids = list(inputs.group_ids)
    codes = [world.groups[group_id].main_code for group_id in group_ids]
    bank = world.form_bank()._native
    assert bank is not None
    index.prepare(world)
    # Morfologický stav kódů (koncovky a jejich podoby) čte hodnocení tvarů z indexu míst.
    sites.prepare(world, codes)
    params = world.params
    variants = len(world.registry.variants)
    columns = world.columns.variants.arrays()
    names = world.columns.variants.payload_origins.names
    weights = np.array([_MOTIVATION.get(name, 0.0) for name in names] + [0.0], dtype=np.float64)
    morphemes: Any = world.columns.morphemes
    related = related_keys(world)
    supplier = Supplier(world, codes, group_ids, index)
    stamps = np.array([(code.phonology.lexicon_version << 32) | len(code.phonology.dominant_log) for code in codes],
                      dtype=np.int64)
    stores = [code.forms.raw() for code in codes]
    paradigm, cells = _paradigm_weights(world, index)
    return module.PressureStep(
        bank, index.handle, sites.handle, supplier, plan,
        (inputs.tick, world.table is not None, params.clarity_short_factor, params.functional_load_scale,
         params.dispersion_factor, params.coda_tolerance_scale, params.stress_strength_multiplier,
         params.paradigm_merge_weight, params.redundant_merge_weight),
        (np.array([code.forms.token for code in codes], dtype=np.int64),
         np.array([code.phonology.version for code in codes], dtype=np.int64),
         np.array([native.RULES.index(code.stress_rule) for code in codes], dtype=np.uint8),
         np.array([getattr(code, "stress_strength", "weak") == "strong" for code in codes], dtype=bool),
         np.array([code.l2_share for code in codes], dtype=np.float64),
         _actuation_keys(world, index, inputs), stamps),
        ([store[0] for store in stores], [store[1] for store in stores], [store[2] for store in stores],
         [code.phonology.dominant.roots for code in codes],
         [_dominant_order(index, code, int(stamp)) for code, stamp in zip(codes, stamps.tolist())]),
        np.ascontiguousarray(related, dtype=np.int64), weights,
        [morphemes.form, morphemes.lexeme, morphemes.cell,
         _padded(columns["change"], variants, -1), _padded(columns["morpheme"], variants, -1),
         _padded(columns["origin"], variants, -1), _padded(columns["appeal"], variants, np.nan),
         _variant_keys(world, index, variants),
         morphemes.kind, morphemes.word_class, morphemes.exponent, morphemes.boundary, morphemes.frequency],
        (_concept_frequencies(world, index), paradigm, cells),
    )


def _overlay(
    world: World, block: PoolBlock, inputs: StepInputs, pack: RowsPack, plan: list[list[tuple[int, float]]],
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
) -> tuple[npt.NDArray[np.uint8], npt.NDArray[np.int64], npt.NDArray[np.float64]]:
    """Řídké položky tlaků, které čtou objekty světa (škola, tabu, konstrukce), podle buňky bloku."""
    groups = len(inputs.group_ids)
    stride = groups * block.capacity
    entries: list[tuple[int, int, float]] = []
    wanted = {number for kind in plan for number, _ in kind}
    cache = inputs.cache
    if _NORM in wanted:
        if "school" not in cache:
            cache["school"] = any(world.groups[group_id].schooling > 0 for group_id in inputs.group_ids)
        if cache["school"]:
            for row, column, slot, value in Norm().cells(
                world, inputs.group_ids, block.variable_ids, block.slots, {}
            ):
                entries.append((row * stride + column * block.capacity + slot, _NORM, value))
    if _TABOO in wanted and len(pack.lexical):
        if "taboo" not in cache:
            cache["taboo"] = any(world.groups[group_id].taboo for group_id in inputs.group_ids)
        if cache["taboo"]:
            lexical = pack.lexical.tolist()
            for row, column, slot, value in Taboo().cells(
                world, inputs.group_ids, [block.variable_ids[r] for r in lexical],
                [block.slots[r] for r in lexical], inputs.tick,
            ):
                entries.append((lexical[row] * stride + column * block.capacity + slot, _TABOO, value))
    construction = np.flatnonzero(pack.kind == _CONSTRUCTION_KIND)
    if len(construction):
        rows = construction.tolist()
        shape = (len(rows), groups, block.capacity)
        batch = PressureBatch(
            world=world, variable_ids=[block.variable_ids[r] for r in rows], group_ids=inputs.group_ids,
            freqs=np.zeros(shape), slots=[block.slots[r] for r in rows], tick=inputs.tick, heard=np.zeros(shape),
            numbers=block.numbers_in(world.registry.variants, rows),
        )
        for pressure, _ in pressures.get("construction", ()):
            if pressure.name not in _CONSTRUCTION:
                continue
            scores = np.broadcast_to(pressure.scores(batch), shape)
            number = PRESSURE_IDS[pressure.name]
            for local, column, slot in zip(*(axis.tolist() for axis in np.nonzero(scores))):
                entries.append((rows[local] * stride + column * block.capacity + slot, number,
                                float(scores[local, column, slot])))
    entries.sort(key=lambda item: item[0])
    return (np.array([item[1] for item in entries], dtype=np.uint8),
            np.array([item[0] for item in entries], dtype=np.int64),
            np.array([item[2] for item in entries], dtype=np.float64))


def prepare(
    world: World, block: PoolBlock, inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
) -> tuple[Any, tuple[Any, ...]] | None:
    """Vstupy pro tlaky v Rustu, nebo ``None``, když to nejde (bez Rustu, neznámý tlak, svět bez tabulky hlásek)."""
    if not (native.transmit_enabled() and native.assess_enabled()):
        return None
    if world.table is None or block.numbering is not world.registry.variants:
        return None
    if world.form_bank()._native is None:
        return None
    plan = plan_of(pressures)
    if plan is None:
        return None
    index = index_of(world)
    if not isinstance(index, NativeAssessmentIndex):
        return None
    sites = site_index(world)
    if not sites.native:
        # Odvozený stav z jiného režimu (třeba obnova kontrolního bodu): index míst se postaví znovu.
        world.sites = None
        sites = site_index(world)
        if not sites.native:
            return None
    step = inputs.cache.get("pressure-step")
    if step is None:
        step = inputs.cache["pressure-step"] = _step(world, inputs, index, plan, sites)
    held = block.pressure_rows
    if held is None or held[0] != block.layout or held[2] != len(inputs.group_ids):
        rule = world.groups[inputs.group_ids[0]].main_code.stress_rule
        held = block.pressure_rows = (block.layout, RowsPack(world, block, index, rule), len(inputs.group_ids))
    pack: RowsPack = held[1]
    pressure, cell, value = _overlay(world, block, inputs, pack, plan, pressures)
    rows = (pack.kind, pack.concept, pack.variable, pack.changed, pack.proc_row, pack.ease, pack.clarity,
            pack.flags, pack.protect(world), block.slot_variants, pressure, cell, value)
    return step, rows


class _BatchBlock:
    """Dávka tlaků (pole) v roli bloku, pro zkoušky Rustu nad zlatými daty; jen čtení."""

    def __init__(self, world: World, batch: PressureBatch) -> None:
        self.variable_ids = list(batch.variable_ids)
        self.slots = [list(row) for row in batch.slots]
        self.capacity = batch.freqs.shape[2]
        self.numbering = world.registry.variants
        self.slot_variants = np.ascontiguousarray(batch.slot_numbers(), dtype=np.int32)
        self.layout = 0
        self.pressure_rows: Any = None

    def __len__(self) -> int:
        return len(self.variable_ids)

    def numbers_in(self, numbering: Any, rows: Sequence[int] | slice = slice(None)) -> npt.NDArray[np.intp]:
        return self.slot_variants[rows].astype(np.intp)


def scores_of_batch(
    world: World, batch: PressureBatch, pressures: Mapping[str, Sequence[tuple[Pressure, float]]], threads: int = 1,
) -> npt.NDArray[np.float64] | None:
    """Součet vážených tlaků dávky (tvar ``batch.freqs``) spočítaný v Rustu, nebo ``None``, když to nejde.

    Stejný výpočet jako uvnitř ``NativeCells.transmit``, jen nad dávkou jako polem (zlatá data
    tlaků a zkoušky vláken). Hodnotí všechny řádky dávky pravidly daného druhu proměnných.
    """
    from types import SimpleNamespace

    block = _BatchBlock(world, batch)
    inputs = SimpleNamespace(group_ids=list(batch.group_ids), tick=batch.tick, cache={})
    prepared = prepare(world, block, inputs, pressures)  # type: ignore[arg-type]
    if prepared is None:
        return None
    step, rows = prepared
    module = native._load()
    assert module is not None
    found = module.pressure_scores(
        step, rows, np.ascontiguousarray(batch.freqs, dtype=np.float64),
        np.ascontiguousarray(batch.heard, dtype=np.float64), 0, threads,
    )
    adopt_created(world)
    return found.reshape(batch.freqs.shape)  # type: ignore[no-any-return]

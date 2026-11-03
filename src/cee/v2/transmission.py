"""Šíření: přenos repertoáru na další generaci a mezi skupinami.

Jeden mechanismus pro všechny změny (iterace 1). S-křivky, vlny a izoglosy
nejsou naprogramované: vyplývají z opakovaného přenosu s výhodou po síti.
Vzorec je ve specifikaci, oddíl Přenos — vzorec. Celý krok se počítá
vektorově nad :class:`cee.v2.pools.LivePools`.

Čísla počítají čisté funkce polí v :mod:`cee.v2.phases_transmission`
(matice vazeb, komponenty, kanály, míšení, výběr, drift). Tento modul je
tenká fasáda: z objektů světa (skupiny, vazby, proměnné, tlaky) složí vstupní
pole, zavolá je a výsledek předá dál. Na objektech zůstává sbírání vlastností
skupin a proměnných, tlaky na varianty a klíče driftu.

S Rustem (:func:`_transmit_native`) je přenos bloku jediné volání ``NativeCells.transmit``:
míšení, tlaky (zpětné volání Pythonu po kusech řádků) a výběr s driftem počítá Rust nad
stavem, který drží. Až tlaky přejdou do Rustu, zpětné volání zmizí a celý řetězec
míšení → tlaky → výběr poběží v Rustu bez přechodu přes Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import contact, institutions, native
from cee.v2 import phases_transmission as phases
from cee.v2.pools import PoolBlock
from cee.v2.pressures.base import Pressure, PressureBatch
from cee.v2.registry import Numbering
from cee.v2.rng import stable_int
from cee.v2.world import SpeechGroup, World

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class TransmissionParams:
    dt: float
    alpha: float
    selection: float
    kappa: float
    sigma: float
    adult_rate: float
    loss_threshold: float
    establish_threshold: float


def mixing_matrix(world: World, group_ids: Sequence[str], alpha: float) -> FloatArray:
    """Od koho se která skupina učí: řádek g je rozdělení vstupu skupiny g.

    Na diagonále je vlastní skupina s vahou ``1 − otevřenost``. Zbytek se
    rozdělí mezi sousedy úměrně síle vazby a prestiži zdroje (na ``alpha``).
    Skupina bez sousedů se učí jen sama od sebe.
    """
    # Vazby z CSR tabulky světa (obnoví se jen po změně vazeb). Každá dvojice
    # (zdroj, cíl) je v tabulce jednou, takže se buňky jen přiřazují a pořadí
    # položek na výsledku nezáleží. Mocninu prestiže počítáme po skupinách
    # v Pythonu (stejné ``**`` jako dřív), v poli už jen násobíme.
    table = world.link_table()
    numbers = world.registry.groups.numbers
    place = np.full(table.groups, -1, dtype=np.intp)
    place[np.array([numbers[group_id] for group_id in group_ids], dtype=np.intp)] = np.arange(len(group_ids))
    power = np.array([world.groups[group_id].prestige**alpha for group_id in group_ids])
    openness = np.array([world.groups[group_id].openness for group_id in group_ids])
    return phases.mixing_from_links(
        table.source.astype(np.intp), table.indices.astype(np.intp), table.strength, place, power, openness
    )


def _normalized(array: FloatArray, fallback: FloatArray) -> FloatArray:
    """Podíly slotů dělené součtem, viz :func:`cee.v2.phases_transmission.normalized`."""
    return phases.normalized(array, fallback)


@dataclass(frozen=True, slots=True)
class Channel:
    """Vstup, který skupina dostává mimo vazby sítě.

    Skupina ``learners[i]`` přebírá podíl ``weights[i] × faktor(proměnná)``
    svého vstupu od ``sources[i]``: interference prvního jazyka, čtení a
    škola z psaného kódu. ``factors(world, sloupce proměnných)`` dá filtr
    kanálu pro všechny proměnné bloku naráz.
    """

    learners: npt.NDArray[np.intp]
    sources: npt.NDArray[np.intp]
    weights: FloatArray
    factors: Callable[[World, contact.VariableColumns], FloatArray]


def _channel(
    mask: npt.NDArray[np.bool_], sources: npt.NDArray[np.intp], weights: FloatArray,
    factors: Callable[[World, contact.VariableColumns], FloatArray],
) -> Channel:
    learners = np.flatnonzero(mask).astype(np.intp)
    return Channel(learners=learners, sources=sources[learners], weights=weights[learners], factors=factors)


@dataclass(frozen=True, slots=True)
class CrossFlow:
    """Vazby mezi jazyky jednoho kanálu (po komponentách sítě, viz :func:`cee.v2.phases_transmission.mix`).

    Kanály ``elite`` a ``trade`` se oddělují od obecného kontaktu sousedů jen
    tehdy, mají-li v ``Parameters.channel_domains`` jiné váhy domén
    (:func:`cee.v2.contact.distinct_channels`); jinak je jediný kanál ``neighbor``.
    """

    channel: str
    blocks: Sequence[FloatArray]


@dataclass(frozen=True, slots=True)
class StepInputs:
    """Vstupy jednoho kroku sdílené všemi bloky živých proměnných."""

    group_ids: Sequence[str]
    #: Míšení po komponentách sítě, viz :func:`cee.v2.phases_transmission.mix`.
    #: ``blocks`` jsou vazby uvnitř jazyka (a vlastní skupina), ``cross`` vazby
    #: mezi jazyky podle kanálů; ty procházejí filtrem přenositelnosti (prázdné,
    #: když žádné nejsou).
    members: Sequence[npt.NDArray[np.intp]]
    blocks: Sequence[FloatArray]
    cross: Sequence[CrossFlow]
    alone: npt.NDArray[np.intp]
    alone_weight: FloatArray
    renewal: FloatArray
    drift_scale: FloatArray
    loss_floor: FloatArray
    row_keys: npt.NDArray[np.uint64]
    tick: int
    #: Interference, čtení, škola a liturgie, v tomto pořadí; jen neprázdné.
    channels: Sequence[Channel]
    #: Odvozené vstupy pro Rust (``NativeStep``), sestaví se při prvním přenosu bloku v kroku.
    cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def native_step(self) -> Any:
        """Vstupy kroku v Rustu, jednou za krok sdílené všemi bloky (sít, kanály, kohorty a klíče driftu)."""
        step = self.cache.get("step")
        if step is None:
            floats, ints = np.float64, np.int64
            step = self.cache["step"] = native.new_step(
                [np.ascontiguousarray(group, dtype=ints) for group in self.members],
                [np.ascontiguousarray(block, dtype=floats) for block in self.blocks],
                np.ascontiguousarray(self.alone, dtype=ints), np.ascontiguousarray(self.alone_weight, dtype=floats),
                [[np.ascontiguousarray(block, dtype=floats) for block in flow.blocks] for flow in self.cross],
                [(np.ascontiguousarray(channel.learners, dtype=ints), np.ascontiguousarray(channel.sources, dtype=ints),
                  np.ascontiguousarray(channel.weights, dtype=floats)) for channel in self.channels],
                np.ascontiguousarray(self.renewal, dtype=floats), np.ascontiguousarray(self.drift_scale, dtype=floats),
                np.ascontiguousarray(self.loss_floor, dtype=floats), np.ascontiguousarray(self.row_keys, dtype=np.uint64),
            )
        return step


def _components(mixing: FloatArray) -> list[npt.NDArray[np.intp]]:
    """Propojené komponenty sítě, viz :func:`cee.v2.phases_transmission.components`."""
    return phases.components(mixing)


def _mix(inputs: StepInputs, values: FloatArray, cross: Sequence[FloatArray] | None = None) -> FloatArray:
    """Vážený vstup od sousedů, viz :func:`cee.v2.phases_transmission.mix`."""
    if cross is None:
        return phases.mix(values, inputs.members, inputs.blocks, inputs.alone, inputs.alone_weight)
    return phases.mix(values, inputs.members, cross)


def prepare(world: World, group_ids: Sequence[str], params: TransmissionParams, tick: int) -> StepInputs:
    groups = [world.groups[group_id] for group_id in group_ids]
    renewal = np.array([world.renewal(group_id, params.dt) for group_id in group_ids])
    drift_scale, loss_floor = phases.cohort_scales(
        renewal, np.array([group.population for group in groups]), params.sigma, params.loss_threshold
    )
    mixing = mixing_matrix(world, group_ids, params.alpha)
    components = phases.components(mixing)
    linked = [members for members in components if len(members) > 1]
    alone = np.array([members[0] for members in components if len(members) == 1], dtype=np.intp)
    # Jazyky jako kódy, aby se vazby mezi jazyky počítaly z čísel, ne z řetězců.
    languages = np.unique(np.array([group.main_code.language for group in groups]), return_inverse=True)[1]
    foreign = phases.foreign_mask(languages.astype(np.intp))
    cross: list[CrossFlow] = []
    if foreign.any():
        distinct = contact.distinct_channels(world.params)
        shares = contact.channel_shares(world, group_ids, distinct) if distinct else {}
        # Obecný kontakt je to, co nepatří elitě ani obchodu; bez odlišných kanálů celá vazba.
        neighbor = phases.neighbor_fraction(list(shares.values())) if shares else None
        for channel, fraction in (("neighbor", neighbor), *shares.items()):
            blocks = phases.cross_blocks(mixing, linked, foreign, fraction)
            if any(block.any() for block in blocks):
                cross.append(CrossFlow(channel, blocks))
    channels = _channels(world, groups, group_ids)
    return StepInputs(
        group_ids=group_ids,
        members=linked,
        blocks=phases.internal_blocks(mixing, linked, foreign if cross else None),
        cross=cross,
        alone=alone,
        alone_weight=mixing[alone, alone],
        renewal=renewal,
        drift_scale=drift_scale,
        loss_floor=loss_floor,
        row_keys=np.array(
            [stable_int(world.seed, "drift", tick, group_id) for group_id in group_ids],
            dtype=np.uint64,
        ),
        tick=tick,
        channels=channels,
    )


def _channels(world: World, groups: Sequence[SpeechGroup], group_ids: Sequence[str]) -> list[Channel]:
    """Vstupy mimo vazby sítě: interference, čtení, škola a liturgie (jen neprázdné)."""
    params = world.params
    index = {group_id: position for position, group_id in enumerate(group_ids)}

    def column(attribute: Callable[[SpeechGroup], float]) -> FloatArray:
        return np.array([attribute(group) for group in groups], dtype=np.float64)

    def source(attribute: Callable[[SpeechGroup], str | None]) -> npt.NDArray[np.intp]:
        return np.array([index.get(attribute(group), -1) for group in groups], dtype=np.intp)  # type: ignore[arg-type]

    l1_sources = source(lambda group: group.main_code.l1_source)
    l2_share = column(lambda group: group.main_code.l2_share)
    standards = source(lambda group: group.standard)
    liturgies = source(lambda group: group.liturgy)
    literacy, schooling, devotion = (column(lambda group, name=name: getattr(group, name))
                                     for name in ("literacy", "schooling", "devotion"))
    specs = (
        ((l1_sources >= 0) & (l2_share > 0), l1_sources,
         phases.channel_weights(params.interference_weight, l2_share, params.school_correction * schooling),
         contact.interference_factors),
        ((standards >= 0) & (literacy > 0), standards,
         phases.channel_weights(params.reading_weight, literacy), institutions.reading_factors),
        ((standards >= 0) & (schooling > 0), standards,
         phases.channel_weights(params.school_weight, schooling), institutions.school_factors),
        ((liturgies >= 0) & (devotion > 0), liturgies,
         phases.channel_weights(params.liturgy_weight, devotion), institutions.liturgy_factors),
    )
    return [_channel(mask, sources, weights, factors) for mask, sources, weights, factors in specs if mask.any()]


def fitness_of(
    world: World,
    block: PoolBlock | RowSlice,
    inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
    heard: FloatArray,
    columns: Sequence[int] | None = None,
) -> FloatArray:
    """Součet vážených tlaků pro každou buňku bloku (proměnná, skupina, slot).

    S ``columns`` jen pro tyto sloupce (skupiny); tvar je pak (proměnné,
    ``len(columns)``, sloty). Tlak hodnotí každou skupinu zvlášť, takže výřez
    dá pro své sloupce stejná čísla jako celý blok (na tom stojí paralelní běh,
    :mod:`cee.v2.parallel`).
    """
    current = block.freqs
    group_ids: Sequence[str] = inputs.group_ids
    if columns is not None:
        picked = np.asarray(columns, dtype=np.intp)
        current, heard = current[:, picked], heard[:, picked]
        group_ids = [inputs.group_ids[column] for column in picked]
    fitness = np.zeros_like(current)
    kinds = np.array([world.variables[variable_id].kind for variable_id in block.variable_ids])
    for kind, weighted in pressures.items():
        rows = np.flatnonzero(kinds == kind)
        if not len(rows):
            continue
        batch = PressureBatch(
            world=world,
            variable_ids=[block.variable_ids[row] for row in rows],
            group_ids=group_ids,
            freqs=current[rows],
            slots=[block.slots[row] for row in rows],
            tick=inputs.tick,
            heard=heard[rows],
            numbers=block.numbers_in(world.registry.variants, rows),
        )
        for pressure, strength in weighted:
            fitness[rows] += strength * pressure.scores(batch)
    return fitness


#: Nejvíc buněk (proměnné × skupiny × sloty) jednoho kusu bloku při přenosu. Větší blok se
#: počítá po kusech řádků, aby přechodná pole (slyšené, tlaky, výběr, drift) nerostla s celým
#: blokem. Řádky jsou na sobě nezávislé, takže kusy dají tytéž bity.
CHUNK_CELLS = 1 << 20


class RowSlice:
    """Řádky ``[start, stop)`` bloku jako blok (pro přenos po kusech); jen čtení."""

    def __init__(self, block: PoolBlock, start: int, stop: int, freqs: FloatArray | None = None):
        self.block, self.start, self.stop = block, start, stop
        self._freqs = freqs
        self.capacity = block.capacity
        self.numbering = block.numbering
        self.variable_ids = block.variable_ids[start:stop]
        self.slots = block.slots[start:stop]

    def __len__(self) -> int:
        return self.stop - self.start

    @property
    def freqs(self) -> FloatArray:
        # Rust předá výřez hned, aby se hustý pohled bloku nestavěl znovu.
        return self.block.freqs[self.start : self.stop] if self._freqs is None else self._freqs

    @property
    def previous(self) -> FloatArray:
        return self.block.previous[self.start : self.stop]

    @property
    def present(self) -> npt.NDArray[np.bool_]:
        return self.block.present[self.start : self.stop]

    @property
    def slot_keys(self) -> npt.NDArray[np.uint64]:
        return self.block.slot_keys[self.start : self.stop]

    @property
    def slot_variants(self) -> npt.NDArray[np.int32]:
        return self.block.slot_variants[self.start : self.stop]

    def numbers_in(self, numbering: Numbering, rows: Sequence[int] | slice = slice(None)) -> npt.NDArray[np.intp]:
        chosen = range(self.start, self.stop)[rows] if isinstance(rows, slice) else [self.start + row for row in rows]
        return self.block.numbers_in(numbering, list(chosen))


def transmit(
    world: World,
    block: PoolBlock,
    inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
    params: TransmissionParams,
    fitness_hook: Callable[..., FloatArray] | None = None,
) -> tuple[FloatArray, FloatArray]:
    """Nové frekvence a trendová základna jednoho bloku živých proměnných.

    Počítá se výhradně ze starého stavu, takže pořadí proměnných ani skupin
    výsledek neovlivní. Šum závisí jen na (tick, skupina, varianta), proto
    skupina bez vazeb na zbytek světa dostane stejný výsledek, ať jinde
    existuje cokoli.

    Jen složí vstupy z objektů: faktory kanálů po proměnných bloku (jedním
    polem na kanál), potom :func:`cee.v2.phases_transmission.hear`, tlaky
    na varianty (:func:`fitness_of`) a :func:`cee.v2.phases_transmission.settle`.
    Velký blok (víc než ``CHUNK_CELLS`` buněk) se počítá po kusech řádků.
    """
    size, width = len(block), max(1, len(inputs.group_ids) * block.capacity)
    step = max(1, CHUNK_CELLS // width)
    if block.native is not None and native.transmit_enabled():
        return _transmit_native(world, block, inputs, pressures, params, fitness_hook, 0 if size <= step else step)
    if size <= step:
        return _transmit_rows(world, block, inputs, pressures, params, fitness_hook)
    updated, baseline = np.empty_like(block.freqs), np.empty_like(block.freqs)
    for start in range(0, size, step):
        stop = min(size, start + step)
        part = RowSlice(block, start, stop)
        updated[start:stop], baseline[start:stop] = _transmit_rows(
            world, part, inputs, pressures, params, fitness_hook
        )
    return updated, baseline


def _transmit_native(
    world: World,
    block: PoolBlock,
    inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
    params: TransmissionParams,
    fitness_hook: Callable[..., FloatArray] | None,
    chunk_rows: int,
) -> tuple[FloatArray, FloatArray]:
    """Přenos bloku v Rustu: jedno volání, v něm míšení, tlaky (zpětné volání) a výběr s driftem.

    Stav bloku, míšení a ustálení jsou v Rustu; Python dodá jen faktory kanálů po proměnných bloku
    a tlaky (:func:`fitness_of`), které Rust zavolá po kusech řádků mezi míšením a výběrem. Výsledek
    jsou pohledy na pole Rustu, platné do příštího přenosu bloku.
    """
    columns = contact.variable_columns(world, block.variable_ids) if inputs.cross or inputs.channels else None
    flow_factors = [np.ascontiguousarray(contact.borrowing_factors(world, columns, flow.channel), dtype=np.float64)
                    for flow in inputs.cross]
    channel_factors = [np.ascontiguousarray(channel.factors(world, columns), dtype=np.float64)
                       for channel in inputs.channels]
    callback: Callable[..., FloatArray] | None
    if not any(pressures.values()):
        callback = None
    elif fitness_hook is not None:
        chunk_rows = 0

        def callback(start: int, stop: int, current: FloatArray, heard: FloatArray) -> FloatArray:
            assert fitness_hook is not None
            return np.ascontiguousarray(fitness_hook(world, block, inputs, pressures, heard), dtype=np.float64)
    else:
        def callback(start: int, stop: int, current: FloatArray, heard: FloatArray) -> FloatArray:
            part = RowSlice(block, start, stop, current)
            return np.ascontiguousarray(fitness_of(world, part, inputs, pressures, heard), dtype=np.float64)
    assert block.native is not None
    return block.native.transmit(
        inputs.native_step(), flow_factors, channel_factors, block.present, block.slot_keys,
        (params.selection, params.kappa, params.adult_rate, params.establish_threshold), callback, chunk_rows,
    )


def _transmit_rows(
    world: World,
    block: PoolBlock | RowSlice,
    inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
    params: TransmissionParams,
    fitness_hook: Callable[..., FloatArray] | None,
) -> tuple[FloatArray, FloatArray]:
    current, previous, present = block.freqs, block.previous, block.present
    columns = contact.variable_columns(world, block.variable_ids) if inputs.cross or inputs.channels else None
    flows = [(contact.borrowing_factors(world, columns, flow.channel), flow.blocks) for flow in inputs.cross]
    channels = [(channel.factors(world, columns), channel.learners, channel.sources, channel.weights)
                for channel in inputs.channels]
    heard = phases.hear(current, present, inputs.members, inputs.blocks, inputs.alone, inputs.alone_weight,
                        flows, channels)
    fitness = (fitness_of(world, block, inputs, pressures, heard) if fitness_hook is None
               else fitness_hook(world, block, inputs, pressures, heard))
    return phases.settle(
        current, previous, present, heard, fitness, block.slot_keys, inputs.row_keys, inputs.drift_scale,
        inputs.renewal, inputs.loss_floor, params.selection, params.kappa, params.adult_rate,
        params.establish_threshold,
    )

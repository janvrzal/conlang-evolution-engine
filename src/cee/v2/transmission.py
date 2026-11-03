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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import contact, institutions
from cee.v2 import phases_transmission as phases
from cee.v2.pools import PoolBlock
from cee.v2.pressures.base import Pressure, PressureBatch
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
    block: PoolBlock,
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
    """
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

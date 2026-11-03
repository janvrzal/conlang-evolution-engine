"""Šíření: přenos repertoáru na další generaci a mezi skupinami.

Jeden mechanismus pro všechny změny (iterace 1). S-křivky, vlny a izoglosy
nejsou naprogramované: vyplývají z opakovaného přenosu s výhodou po síti.
Vzorec je ve specifikaci, oddíl Přenos — vzorec. Celý krok se počítá
vektorově nad :class:`cee.v2.pools.LivePools`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import contact, institutions
from cee.v2.pools import PoolBlock
from cee.v2.pressures.base import Pressure, PressureBatch
from cee.v2.rng import hash_normal, stable_int
from cee.v2.world import World

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
    size = len(group_ids)
    place = np.full(table.groups, -1, dtype=np.intp)
    place[np.array([numbers[group_id] for group_id in group_ids], dtype=np.intp)] = np.arange(size)
    power = np.array([world.groups[group_id].prestige**alpha for group_id in group_ids])
    rows, columns = place[table.source], place[table.indices]
    kept = (rows >= 0) & (columns >= 0)
    weights = np.zeros((size, size))
    weights[rows[kept], columns[kept]] = table.strength[kept] * power[columns[kept]]
    totals = weights.sum(axis=1)
    openness = np.array([world.groups[group_id].openness for group_id in group_ids])
    openness = np.where(totals > 0, openness, 0.0)
    safe = np.where(totals > 0, totals, 1.0)
    mixing: FloatArray = (1.0 - openness)[:, None] * np.eye(len(group_ids)) + openness[
        :, None
    ] * (weights / safe[:, None])
    return mixing


def _normalized(array: FloatArray, fallback: FloatArray) -> FloatArray:
    # Součet seřazených hodnot nezávisí na tom, ve kterých slotech varianty
    # leží. Pořadí slotů ovlivňují i inovace v nepropojených skupinách, a bez
    # toho by tak přes poslední bity zaokrouhlení měnily výsledek jinde.
    # Součet dvou čísel je komutativní i v plovoucí čárce, řadit stačí od tří.
    # Sčítání provádíme striktně sekvenčně zleva doprava po seřazených slotech:
    # vestavěný np.sum() používá pro různé délky (např. 4 vs. 8) odlišné
    # párové/SIMD redukce. V IEEE-754 platí +0.0 + x == x pro x >= 0, takže
    # sekvenční součet zleva doprava zajistí bitovou shodu bez ohledu na to,
    # kolika úvodními nulami je řádek doplněn v blocích různé kapacity.
    ordered = array if array.shape[-1] <= 2 else np.sort(array, axis=-1)
    totals = ordered[..., :1] + 0.0
    for slot in range(1, ordered.shape[-1]):
        totals = totals + ordered[..., slot : slot + 1]
    result: FloatArray = np.where(totals > 0, array / np.where(totals > 0, totals, 1.0), fallback)
    return result


@dataclass(frozen=True, slots=True)
class Channel:
    """Vstup, který skupina dostává mimo vazby sítě.

    Skupina ``learners[i]`` přebírá podíl ``weights[i] × factor(proměnná)``
    svého vstupu od ``sources[i]``: interference prvního jazyka, čtení a
    škola z psaného kódu.
    """

    learners: npt.NDArray[np.intp]
    sources: npt.NDArray[np.intp]
    weights: FloatArray
    factor: Callable[[World, str], float]


def _channel(items: Sequence[tuple[int, int, float]], factor: Callable[[World, str], float]) -> Channel:
    return Channel(
        learners=np.array([item[0] for item in items], dtype=np.intp),
        sources=np.array([item[1] for item in items], dtype=np.intp),
        weights=np.array([item[2] for item in items], dtype=np.float64),
        factor=factor,
    )


@dataclass(frozen=True, slots=True)
class CrossFlow:
    """Vazby mezi jazyky jednoho kanálu (po komponentách sítě, viz :func:`_mix`).

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
    #: Míšení po komponentách sítě, viz :func:`_mix`. ``blocks`` jsou vazby
    #: uvnitř jazyka (a vlastní skupina), ``cross`` vazby mezi jazyky podle
    #: kanálů; ty procházejí filtrem přenositelnosti (prázdné, když žádné nejsou).
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
    """Propojené komponenty sítě (kdo se od koho, i nepřímo, učí)."""
    parent = list(range(len(mixing)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first, second in zip(*np.nonzero(mixing)):
        a, b = root(int(first)), root(int(second))
        if a != b:
            parent[max(a, b)] = min(a, b)
    members: dict[int, list[int]] = {}
    for index in range(len(mixing)):
        members.setdefault(root(index), []).append(index)
    return [np.array(items, dtype=np.intp) for _, items in sorted(members.items())]


def _mix(inputs: StepInputs, values: FloatArray, cross: Sequence[FloatArray] | None = None) -> FloatArray:
    """Vážený vstup od sousedů: ``values`` má skupiny na ose 1.

    Násobí se zvlášť každá propojená komponenta. Knihovna BLAS totiž sčítá v
    pořadí, které závisí na velikosti matice; přidání skupin v nepropojené
    části světa by jinak změnilo poslední bity výsledku a časem i historii.
    Osamocené skupiny (učí se jen samy od sebe) se vyřídí najednou.
    """
    result = np.zeros_like(values)
    if len(inputs.alone) and cross is None:
        shape = (1, -1) + (1,) * (values.ndim - 2)
        result[:, inputs.alone] = inputs.alone_weight.reshape(shape) * values[:, inputs.alone]
    for members, matrix in zip(inputs.members, inputs.blocks if cross is None else cross):
        part = values[:, members]
        flat = np.moveaxis(part, 1, 0).reshape(len(members), -1)
        mixed = (matrix @ flat).reshape((len(members), part.shape[0], *part.shape[2:]))
        result[:, members] = np.moveaxis(mixed, 0, 1)
    return result


def prepare(world: World, group_ids: Sequence[str], params: TransmissionParams, tick: int) -> StepInputs:
    groups = [world.groups[group_id] for group_id in group_ids]
    renewal = np.array([world.renewal(group_id, params.dt) for group_id in group_ids])
    cohort = np.maximum(1.0, renewal * np.array([group.population for group in groups]))
    mixing = mixing_matrix(world, group_ids, params.alpha)
    components = _components(mixing)
    linked = [members for members in components if len(members) > 1]
    alone = np.array([members[0] for members in components if len(members) == 1], dtype=np.intp)
    languages = np.array([group.main_code.language for group in groups])
    foreign = languages[:, None] != languages[None, :]
    cross: list[CrossFlow] = []
    if foreign.any():
        distinct = contact.distinct_channels(world.params)
        shares = contact.channel_shares(world, group_ids, distinct) if distinct else {}
        # Obecný kontakt je to, co nepatří elitě ani obchodu; bez odlišných kanálů celá vazba.
        neighbor = 1.0 - sum(shares.values()) if shares else None
        for channel, fraction in (("neighbor", neighbor), *shares.items()):
            blocks = [
                np.where(foreign[np.ix_(members, members)],
                         mixing[np.ix_(members, members)] if fraction is None
                         else mixing[np.ix_(members, members)] * fraction[np.ix_(members, members)], 0.0)
                for members in linked
            ]
            if any(block.any() for block in blocks):
                cross.append(CrossFlow(channel, blocks))
    index = {group_id: position for position, group_id in enumerate(group_ids)}
    learners = [
        (index[group.id], index[group.main_code.l1_source],
         world.params.interference_weight * group.main_code.l2_share
         * (1.0 - world.params.school_correction * group.schooling))
        for group in groups
        if group.main_code.l1_source in index and group.main_code.l2_share > 0
    ]
    readers = [
        (index[group.id], index[group.standard], world.params.reading_weight * group.literacy)
        for group in groups if group.standard in index and group.literacy > 0
    ]
    pupils = [
        (index[group.id], index[group.standard], world.params.school_weight * group.schooling)
        for group in groups if group.standard in index and group.schooling > 0
    ]
    worshippers = [
        (index[group.id], index[group.liturgy], world.params.liturgy_weight * group.devotion)
        for group in groups if group.liturgy in index and group.devotion > 0
    ]
    channels = [
        _channel(items, factor)
        for items, factor in (
            (learners, contact.interference_factor),
            (readers, institutions.reading_factor),
            (pupils, institutions.school_factor),
            (worshippers, institutions.liturgy_factor),
        )
        if items
    ]
    return StepInputs(
        group_ids=group_ids,
        members=linked,
        blocks=[
            np.where(foreign[np.ix_(members, members)], 0.0, mixing[np.ix_(members, members)])
            if cross else mixing[np.ix_(members, members)]
            for members in linked
        ],
        cross=cross,
        alone=alone,
        alone_weight=mixing[alone, alone],
        renewal=renewal,
        drift_scale=params.sigma / np.sqrt(cohort),
        # Varianta, na kterou v učící se kohortě nepřipadá ani půl mluvčího,
        # zaniká. Pevná spodní mez drží výpočet u velkých souhrnných skupin
        # rozumně malý.
        loss_floor=np.maximum(params.loss_threshold, 0.5 / cohort),
        row_keys=np.array(
            [stable_int(world.seed, "drift", tick, group_id) for group_id in group_ids],
            dtype=np.uint64,
        ),
        tick=tick,
        channels=channels,
    )


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
    """
    current, previous, present = block.freqs, block.previous, block.present
    heard = _mix(inputs, current)
    weight = _mix(inputs, present.astype(np.float64))
    for flow in inputs.cross:
        # Vazby mezi jazyky: jen tolik, kolik filtr přenositelnosti propustí
        # (podle pojmu a kanálu: obecný kontakt, elita, obchod).
        factor = np.array([contact.borrowing_factor(world, variable_id, flow.channel)
                           for variable_id in block.variable_ids])
        heard = heard + factor[:, None, None] * _mix(inputs, current, cross=flow.blocks)
        weight = weight + factor[:, None] * _mix(inputs, present.astype(np.float64), cross=flow.blocks)
    # Skupiny bez této proměnné se z míšení vyřadí a zbytek vstupu se převáží.
    heard = np.where(weight[:, :, None] > 0, heard / np.where(weight > 0, weight, 1.0)[:, :, None], 0)
    for channel in inputs.channels:
        # Interference (L2 mluvčí nesou svůj první jazyk), čtení a škola.
        factor = np.array([channel.factor(world, variable_id) for variable_id in block.variable_ids])
        # Váha domény nad 1 smí podíl zvýšit nejvýš na celý vstup.
        share = np.minimum(factor[:, None] * channel.weights[None, :], 1.0)
        share = np.where(present[:, channel.sources], share, 0.0)[:, :, None]
        heard[:, channel.learners] = (
            (1.0 - share) * heard[:, channel.learners] + share * current[:, channel.sources]
        )

    fitness = (fitness_of(world, block, inputs, pressures, heard) if fitness_hook is None
               else fitness_hook(world, block, inputs, pressures, heard))

    selected = _normalized(heard * np.exp(params.selection * fitness), heard)
    trend = params.kappa * (current - previous)
    # Wright–Fisherův drift: rozptyl p(1 − p) / N učící se kohorty. Varianta,
    # kterou kohorta vůbec neslyší, nemůže driftem vzniknout. Šum se počítá
    # jen tam, kde opravdu soutěží varianty; jinde je nulový.
    spread = selected * (1.0 - selected)
    drift = np.zeros_like(selected)
    rows_i, columns, cells = np.nonzero(spread > 0)
    if len(rows_i):
        noise = hash_normal(inputs.row_keys[columns], block.slot_keys[rows_i, cells], pairwise=True)
        drift[rows_i, columns, cells] = (
            noise * inputs.drift_scale[columns] * np.sqrt(spread[rows_i, columns, cells])
        )
    children = _normalized(np.clip(selected + trend + drift, 0.0, None), selected)
    adults = current + params.adult_rate * (heard - current)
    renewal = inputs.renewal[None, :, None]
    updated = (1.0 - renewal) * adults + renewal * children

    updated[updated < inputs.loss_floor[None, :, None]] = 0.0
    updated = _normalized(updated, current)
    leaders = updated.argmax(axis=2)
    top = np.take_along_axis(updated, leaders[:, :, None], axis=2)[:, :, 0]
    established = (top >= params.establish_threshold) & (top < 1.0)
    if established.any():
        one_hot = np.zeros_like(updated)
        np.put_along_axis(one_hot, leaders[:, :, None], 1.0, axis=2)
        updated = np.where(established[:, :, None], one_hot, updated)
    if not present.all():
        updated = np.where(present[:, :, None], updated, 0.0)
    baseline = np.where(updated > 0, previous + renewal * (current - previous), 0.0)
    # Skupina s jedinou variantou nemá trend. Bez toho by základna závisela
    # na tom, zda proměnná mezitím ležela v repertoáru, nebo ve skladu, a to
    # mohou ovlivnit i inovace v nepropojené části světa.
    alone = (updated > 0).sum(axis=2, keepdims=True) == 1
    baseline = np.where(alone, updated, baseline)
    return updated, baseline

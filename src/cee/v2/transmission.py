"""Šíření: přenos repertoáru na další generaci a mezi skupinami.

Jeden mechanismus pro všechny změny (iterace 1). S-křivky, vlny a izoglosy
nejsou naprogramované: vyplývají z opakovaného přenosu s výhodou po síti.
Vzorec je ve specifikaci, oddíl Přenos — vzorec. Celý krok se počítá
vektorově nad :class:`cee.v2.pools.LivePools`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import numpy.typing as npt

from cee.v2 import contact
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
    index = {group_id: position for position, group_id in enumerate(group_ids)}
    weights = np.zeros((len(group_ids), len(group_ids)))
    for (source, target), link in world.links.items():
        if source in index and target in index:
            weights[index[source], index[target]] = (
                link.strength * world.groups[target].prestige**alpha
            )
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
    ordered = array if array.shape[-1] <= 2 else np.sort(array, axis=-1)
    totals = ordered.sum(axis=-1, keepdims=True)
    result: FloatArray = np.where(totals > 0, array / np.where(totals > 0, totals, 1.0), fallback)
    return result


@dataclass(frozen=True, slots=True)
class StepInputs:
    """Vstupy jednoho kroku sdílené všemi bloky živých proměnných."""

    group_ids: Sequence[str]
    #: Míšení po komponentách sítě, viz :func:`_mix`. ``blocks`` jsou vazby
    #: uvnitř jazyka (a vlastní skupina), ``cross`` vazby mezi jazyky; ty
    #: procházejí filtrem přenositelnosti (prázdné, když žádné nejsou).
    members: Sequence[npt.NDArray[np.intp]]
    blocks: Sequence[FloatArray]
    cross: Sequence[FloatArray]
    alone: npt.NDArray[np.intp]
    alone_weight: FloatArray
    renewal: FloatArray
    drift_scale: FloatArray
    loss_floor: FloatArray
    row_keys: npt.NDArray[np.uint64]
    tick: int
    #: Interference: L2 skupina (index), skupina jejího prvního jazyka a váha.
    learners: npt.NDArray[np.intp]
    sources: npt.NDArray[np.intp]
    interference: FloatArray


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


def _mix(inputs: StepInputs, values: FloatArray, cross: bool = False) -> FloatArray:
    """Vážený vstup od sousedů: ``values`` má skupiny na ose 1.

    Násobí se zvlášť každá propojená komponenta. Knihovna BLAS totiž sčítá v
    pořadí, které závisí na velikosti matice; přidání skupin v nepropojené
    části světa by jinak změnilo poslední bity výsledku a časem i historii.
    Osamocené skupiny (učí se jen samy od sebe) se vyřídí najednou.
    """
    result = np.zeros_like(values)
    if len(inputs.alone) and not cross:
        shape = (1, -1) + (1,) * (values.ndim - 2)
        result[:, inputs.alone] = inputs.alone_weight.reshape(shape) * values[:, inputs.alone]
    for members, matrix in zip(inputs.members, inputs.cross if cross else inputs.blocks):
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
    cross = [] if not foreign.any() else [
        np.where(foreign[np.ix_(members, members)], mixing[np.ix_(members, members)], 0.0)
        for members in linked
    ]
    if cross and not any(block.any() for block in cross):
        cross = []
    index = {group_id: position for position, group_id in enumerate(group_ids)}
    learners = [
        (index[group.id], index[group.main_code.l1_source],
         contact.INTERFERENCE_WEIGHT * group.main_code.l2_share)
        for group in groups
        if group.main_code.l1_source in index and group.main_code.l2_share > 0
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
        learners=np.array([item[0] for item in learners], dtype=np.intp),
        sources=np.array([item[1] for item in learners], dtype=np.intp),
        interference=np.array([item[2] for item in learners], dtype=np.float64),
    )


def transmit(
    world: World,
    block: PoolBlock,
    inputs: StepInputs,
    pressures: Mapping[str, Sequence[tuple[Pressure, float]]],
    params: TransmissionParams,
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
    if inputs.cross:
        # Vazby mezi jazyky: jen tolik, kolik filtr přenositelnosti propustí.
        factor = np.array([contact.borrowing_factor(world, variable_id) for variable_id in block.variable_ids])
        heard = heard + factor[:, None, None] * _mix(inputs, current, cross=True)
        weight = weight + factor[:, None] * _mix(inputs, present.astype(np.float64), cross=True)
    # Skupiny bez této proměnné se z míšení vyřadí a zbytek vstupu se převáží.
    heard = np.where(weight[:, :, None] > 0, heard / np.where(weight > 0, weight, 1.0)[:, :, None], 0)
    if len(inputs.learners):
        # Dospělí, kteří se kód naučili jako druhý, do něj nesou svůj první jazyk.
        factor = np.array([contact.interference_factor(world, variable_id) for variable_id in block.variable_ids])
        share = factor[:, None] * inputs.interference[None, :]
        share = np.where(present[:, inputs.sources], share, 0.0)[:, :, None]
        heard[:, inputs.learners] = (
            (1.0 - share) * heard[:, inputs.learners] + share * current[:, inputs.sources]
        )

    fitness = np.zeros_like(current)
    kinds = np.array([world.variables[variable_id].kind for variable_id in block.variable_ids])
    for kind, weighted in pressures.items():
        rows = np.flatnonzero(kinds == kind)
        if not len(rows):
            continue
        batch = PressureBatch(
            world=world,
            variable_ids=[block.variable_ids[row] for row in rows],
            group_ids=inputs.group_ids,
            freqs=current[rows],
            slots=[block.slots[row] for row in rows],
            tick=inputs.tick,
            heard=heard[rows],
        )
        for pressure, strength in weighted:
            fitness[rows] += strength * pressure.scores(batch)

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

"""Hlavní smyčka enginu v2 (specifikace, oddíl Jeden tick)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from cee.v2.changes import DEFAULT_CHANGES, Change, InnovationContext, pressures_by_kind
from cee.v2.events import WorldEvent
from cee.v2.history import History
from cee.v2.observe import LineageTracker, Snapshot, observe
from cee.v2.pools import PoolBlock
from cee.v2.rng import generator
from cee.v2.transmission import TransmissionParams, prepare, transmit
from cee.v2.world import World

_MILESTONES = (0.1, 0.5, 0.9)


@dataclass(frozen=True)
class SimulationConfig:
    """Konstanty běhu. Startovní hodnoty ze specifikace; kalibrují se v M7."""

    #: Délka kroku v letech; nesmí být delší než nejkratší generace ve světě.
    dt: float = 25.0
    alpha: float = 1.0
    selection: float = 1.0
    kappa: float = 0.3
    #: Síla driftu. Hodnota nad 1 vyjadřuje, že na jazyk nemají všichni mluvčí
    #: stejný vliv: efektivní populace je menší než skutečná (N / σ²).
    sigma: float = 2.0
    p0: float = 0.02
    adult_rate: float = 0.05
    #: Spodní mez frekvence; pod ní (nebo pod půl mluvčího kohorty) varianta zaniká.
    loss_threshold: float = 0.001
    #: Vedoucí varianta nad touto mezí se stane jedinou. Slouží jen k úklidu
    #: zbytků; ustálení samo vzniká tím, že ostatní varianty vymřou.
    establish_threshold: float = 0.999
    #: Po kolika krocích se počítají dialekty a jazyky.
    observe_every: int = 4
    #: Výchozí prahy průměrné variační vzdálenosti; nekalibrované.
    dialect_threshold: float = 0.05
    language_threshold: float = 0.25
    record_trajectories: bool = False


class Simulation:
    def __init__(
        self,
        world: World,
        config: SimulationConfig | None = None,
        *,
        changes: Sequence[Change] = DEFAULT_CHANGES,
        events: Sequence[WorldEvent] = (),
    ):
        self.world = world
        self.config = config or SimulationConfig()
        if not world.groups:
            raise ValueError("Svět potřebuje alespoň jednu skupinu mluvčích.")
        self._check_step()
        self.changes = tuple(changes)
        self.pressures = pressures_by_kind(self.changes)
        self.params = TransmissionParams(
            dt=self.config.dt,
            alpha=self.config.alpha,
            selection=self.config.selection,
            kappa=self.config.kappa,
            sigma=self.config.sigma,
            adult_rate=self.config.adult_rate,
            loss_threshold=self.config.loss_threshold,
            establish_threshold=self.config.establish_threshold,
        )
        # Stabilní řazení: rok, potom pořadí zadání.
        self._pending = sorted(enumerate(events), key=lambda item: (item[1].year, item[0]))
        self.history = History()
        self.tick = 0
        self.tracker = LineageTracker()
        self._total_variables = len(world.variables)
        world.live.sync_groups(world)

    @property
    def year(self) -> float:
        return self.world.start_year + self.tick * self.config.dt

    @property
    def snapshots(self) -> list[Snapshot]:
        return self.history.snapshots

    def run(self, until_year: float) -> History:
        while self.year + self.config.dt <= until_year + 1e-9:
            self.step()
        return self.history

    def step(self) -> None:
        self.tick += 1
        year = self.year
        self._apply_events(year)
        self._innovate(year)
        self._transmit(year)
        if self.tick % self.config.observe_every == 0:
            self._observe(year)

    # --- jednotlivé fáze -------------------------------------------------

    def _apply_events(self, until: float) -> None:
        applied = False
        while self._pending and self._pending[0][1].year <= until:
            _, event = self._pending.pop(0)
            event.apply(self.world, self.history, self.tick)
            applied = True
        if applied:
            self._check_step()
            self.world.live.sync_groups(self.world)

    def _innovate(self, year: float) -> None:
        for group_id in self.world.group_ids():
            group = self.world.groups[group_id]
            renewal = min(1.0, self.config.dt / group.generation_years)
            # Do M5 (vícejazyčnost) se simuluje jen hlavní kód skupiny.
            context = InnovationContext(self.world, group, group.main_code, self.tick, year)
            for change in self.changes:
                self._innovate_with(change, context, renewal)

    def _innovate_with(self, change: Change, context: InnovationContext, renewal: float) -> None:
        sites = change.sites(context)
        if not sites:
            return
        tempo = renewal if change.rate_basis == "generation" else self.config.dt
        rng = generator(self.world.seed, "innovation", self.tick, context.group.id,
                        context.code.id, change.kind)
        if change.uses_uniform_rate():
            weights = None
            expected = change.base_rate * tempo * len(sites)
        else:
            rates = [change.rate(context, site) for site in sites]
            expected = sum(rates) * tempo
            weights = [rate / sum(rates) for rate in rates] if expected > 0 else None
        count = int(rng.poisson(expected)) if expected > 0 else 0
        live = self.world.live
        for index in range(count):
            site = sites[int(rng.choice(len(sites), p=weights))]
            variant = change.propose(context, site, rng, index)
            if variant is None:
                continue
            if site in live:
                if not live.holds(context.group.id, site):
                    continue
            elif context.code.repertoire.get(site) is None:
                continue
            else:
                live.load(site, [self.world.groups[group_id].main_code.repertoire.get(site)
                                 for group_id in live.group_ids])
            self.world.variants[variant.id] = variant
            live.innovate(site, context.group.id, variant.id, self.config.p0)
            self.history.record(
                "innovation", self.tick, context.year,
                group=context.group.id, code=context.code.id, change=change.kind,
                variable=site, variant=variant.id,
            )

    def _transmit(self, year: float) -> None:
        live = self.world.live
        if len(live) == 0:
            return
        inputs = prepare(self.world, live.group_ids, self.params, self.tick)
        results = [
            (block, *transmit(self.world, block, inputs, self.pressures, self.params))
            for block in live.iter_blocks()
        ]
        records: list[tuple[Any, ...]] = []
        for block, updated, baseline in results:
            records.extend(self._changes(block, block.freqs, updated))
            if self.config.record_trajectories:
                self._trace(block, block.freqs, updated)
            block.freqs, block.previous = updated, baseline
        # Kanonické pořadí nezávisí na tom, ve kterém bloku proměnná leží.
        for kind, payload in sorted(records, key=lambda item: (item[0], sorted(item[1].items()))):
            self.history.record(kind, self.tick, year, **payload)
        for variable_id, distributions in live.release():
            for group_id, distribution in zip(live.group_ids, distributions):
                if distribution is not None:
                    self.world.groups[group_id].main_code.repertoire.set(variable_id, distribution)

    def _changes(
        self, block: PoolBlock, before: np.ndarray, after: np.ndarray
    ) -> list[tuple[str, dict[str, Any]]]:
        """Milníky, ustálení a zánik inovací v jednom bloku; vše vektorově."""
        variants = self.world.variants
        group_ids = self.world.live.group_ids
        innovation = np.array(
            [[slot is not None and variants[slot].origin.change is not None for slot in row]
             for row in block.slots],
            dtype=bool,
        ).reshape(len(block), 1, block.capacity)
        records: list[tuple[str, dict[str, Any]]] = []

        def describe(row: int, slot: int, **extra: Any) -> dict[str, Any]:
            return {"variable": block.variable_ids[row], "variant": block.slots[row][slot], **extra}

        levels = np.array(_MILESTONES)
        reached_before = np.searchsorted(levels, before, side="right")
        reached_after = np.searchsorted(levels, after, side="right")
        for row, column, slot in zip(*np.nonzero((reached_after > reached_before) & innovation)):
            for level in _MILESTONES[reached_before[row, column, slot] : reached_after[row, column, slot]]:
                records.append(("milestone", describe(row, slot, group=group_ids[column], level=level)))
        for row, column, slot in zip(*np.nonzero((after == 1.0) & (before < 1.0) & innovation)):
            records.append(("established", describe(row, slot, group=group_ids[column])))
        gone = (before > 0).any(axis=1) & ~(after > 0).any(axis=1) & innovation[:, 0, :]
        for row, slot in zip(*np.nonzero(gone)):
            records.append(("extinct", describe(row, slot)))
        return records

    def _trace(self, block: PoolBlock, before: np.ndarray, after: np.ndarray) -> None:
        variants = self.world.variants
        group_ids = self.world.live.group_ids
        for row, column, slot in zip(*np.nonzero((before > 0) | (after > 0))):
            variant = block.slots[row][slot]
            if variant is None or variants[variant].origin.change is None:
                continue
            self.history.trajectories.setdefault((variant, group_ids[column]), []).append(
                (self.tick, float(after[row, column, slot]))
            )

    def _observe(self, year: float) -> None:
        snapshot, events = observe(
            self.world, self.tick, year, self._total_variables, self.tracker,
            dialect_threshold=self.config.dialect_threshold,
            language_threshold=self.config.language_threshold,
        )
        self.history.snapshots.append(snapshot)
        for event in events:
            payload = dict(event)
            kind = str(payload.pop("kind"))
            self.history.record(kind, self.tick, year, **payload)

    def _check_step(self) -> None:
        if self.config.dt > self.world.generation_ceiling():
            raise ValueError(
                f"Krok {self.config.dt} let je delší než nejkratší generace "
                f"({self.world.generation_ceiling()} let)."
            )

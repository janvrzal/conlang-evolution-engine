"""Hlavní smyčka enginu v2 (specifikace, oddíl Jeden tick)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import numpy as np

from cee.v2 import contact, morphology, phonology, syntax
from cee.v2.changes import DEFAULT_CHANGES, Change, InnovationContext, pressures_by_kind
from cee.v2.events import WorldEvent
from cee.v2.history import History
from cee.v2.observe import LineageTracker, Snapshot, observe
from cee.v2.pools import PoolBlock
from cee.v2.repertoire import Distribution
from cee.v2.rng import generator
from cee.v2.transmission import TransmissionParams, prepare, transmit
from cee.v2.world import World

_MILESTONES = (0.1, 0.5, 0.9)
_EMPTY = Distribution((), np.zeros(0))


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
    #: Počáteční podíl inovace ve skupině o ``reference_population``
    #: obyvatelích. Inovace začíná u jednoho mluvčího, takže v menší skupině
    #: má větší podíl a ve větší menší (viz :meth:`Simulation.innovation_scale`).
    p0: float = 0.02
    reference_population: float = 500.0
    #: Meze počátečního podílu: pod spodní by inovaci hned smazal práh zániku,
    #: nad horní by jedna inovace přeskočila celé šíření.
    p0_min: float = 0.002
    p0_max: float = 0.2
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
    #: Po kolika letech se automaticky uloží checkpoint (``None`` = nikdy).
    #: Z checkpointu jde pokračovat se změněnými pozdějšími událostmi
    #: (:meth:`Simulation.branch`) bez přepočtu starší historie.
    checkpoint_every: float | None = None


@dataclass(frozen=True)
class Checkpoint:
    """Úplný stav běhu po kroku ``tick``; pokračování z něj je bitově stejné."""

    tick: int
    year: float
    state: tuple[World, History, LineageTracker]


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
        self._configure(changes, events)
        self.history = History()
        self.tick = 0
        self.tracker = LineageTracker()
        world.live.sync_groups(world)
        world.live.load_differing(world)
        self._grammar = any(variable.kind == "construction" for variable in world.variables.values())
        if world.table is not None:
            for group_id in world.group_ids():
                self._seed_vocabulary(group_id)

    def _configure(self, changes: Sequence[Change], events: Sequence[WorldEvent]) -> None:
        self.changes = tuple(changes)
        self.events = tuple(events)
        self.checkpoints: dict[int, Checkpoint] = {}
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

    @property
    def year(self) -> float:
        return self.world.start_year + self.tick * self.config.dt

    @property
    def snapshots(self) -> list[Snapshot]:
        return self.history.snapshots

    def run(self, until_year: float) -> History:
        for _ in self.iterate(until_year):
            pass
        return self.history

    def iterate(self, until_year: float) -> Iterator[Simulation]:
        """Krok po kroku až do roku ``until_year``; po každém kroku vrátí sebe.

        UI tak může kreslit mapu a časovou osu průběžně, ne až po celém běhu
        (lehký snímek pro každý krok dává :func:`cee.v2.export.frame`).
        """
        while self.year + self.config.dt <= until_year + 1e-9:
            self.step()
            yield self

    # --- checkpointy -------------------------------------------------------

    def checkpoint(self) -> Checkpoint:
        """Úplný stav běhu. Neměnná data (tabulka hlásek, graf pojmů) se sdílejí."""
        return Checkpoint(self.tick, self.year, _copied((self.world, self.history, self.tracker), self.world))

    @classmethod
    def resume(
        cls,
        checkpoint: Checkpoint,
        events: Sequence[WorldEvent] = (),
        config: SimulationConfig | None = None,
        *,
        changes: Sequence[Change] = DEFAULT_CHANGES,
    ) -> Simulation:
        """Pokračování z checkpointu s (případně jinými) událostmi.

        Události do roku checkpointu už se staly a jsou ve stavu; z ``events``
        se použijí jen pozdější. Výsledek je bitově stejný, jako kdyby běh
        s ``events`` šel od začátku (pokud se ty starší neliší).
        """
        world, history, tracker = _copied(checkpoint.state, checkpoint.state[0])
        simulation = cls.__new__(cls)
        simulation.world = world
        simulation.config = config or SimulationConfig()
        simulation._configure(changes, events)
        simulation._pending = [item for item in simulation._pending if item[1].year > checkpoint.year]
        simulation.history, simulation.tracker, simulation.tick = history, tracker, checkpoint.tick
        simulation._grammar = any(variable.kind == "construction" for variable in world.variables.values())
        return simulation

    def branch(self, events: Sequence[WorldEvent]) -> Simulation:
        """Nový běh s jinými událostmi, od posledního checkpointu před první změnou.

        Když se změní událost v roce 1500, stačí pokračovat z checkpointu před
        rokem 1500; starší historie se nepočítá znovu. Bez vhodného
        checkpointu vyhodí ``ValueError`` (pak je třeba běžet od začátku).
        """
        old = sorted(self.events, key=lambda event: event.year)
        new = sorted(events, key=lambda event: event.year)
        changed = min(
            [min(first.year, second.year) for first, second in zip(old, new) if first != second]
            + [event.year for event in (old[len(new):] + new[len(old):])]
            + [float("inf")]
        )
        usable = [tick for tick, point in self.checkpoints.items() if point.year < changed]
        if not usable:
            raise ValueError("Žádný checkpoint před první změněnou událostí; spusť běh od začátku.")
        return Simulation.resume(self.checkpoints[max(usable)], events, self.config, changes=self.changes)

    def step(self) -> None:
        self.tick += 1
        year = self.year
        self._apply_events(year)
        self._innovate(year)
        self._transmit(year)
        if contact.community_step(self.world, self.config.dt, self.tick, year, self.history):
            self.world.live.sync_groups(self.world)
        if self.tick % self.config.observe_every == 0:
            self._observe(year)
        every = self.config.checkpoint_every
        if every is not None and (year - self.world.start_year) % every < 1e-9:
            self.checkpoints[self.tick] = self.checkpoint()

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
            self.world.live.load_differing(self.world)
            if self.world.table is not None:
                for group_id in self.world.group_ids():
                    self._seed_vocabulary(group_id)

    def _innovate(self, year: float) -> None:
        for group_id in self.world.group_ids():
            group = self.world.groups[group_id]
            if group.written:
                continue  # psaný kód se nemění
            renewal = self.world.renewal(group_id, self.config.dt)
            # Do M5 (vícejazyčnost) se simuluje jen hlavní kód skupiny.
            context = InnovationContext(self.world, group, group.main_code, self.tick, year)
            for change in self.changes:
                self._innovate_with(change, context, renewal)

    def innovation_scale(self, group_id: str) -> tuple[float, float]:
        """Počáteční podíl inovace a násobek četnosti inovací ve skupině.

        Inovace vzniká u jednoho mluvčího: ve skupině s ``N`` lidmi má podíl
        úměrný ``1 / N`` a inovací je úměrně ``N``. Součin obou, tedy tempo
        neutrálních změn, na velikosti nezávisí (Kimura 1968); malá skupina
        ale víc podléhá driftu a velká víc selekci. Skupina o referenční
        velikosti dostane přesně ``p0`` a násobek 1.
        """
        config = self.config
        size = config.reference_population / self.world.groups[group_id].population
        share = min(config.p0_max, max(config.p0_min, config.p0 * size))
        return share, config.p0 / share

    def _innovate_with(self, change: Change, context: InnovationContext, renewal: float) -> None:
        sites = change.sites(context)
        if not sites:
            return
        share, frequency = self.innovation_scale(context.group.id)
        tempo = (renewal if change.rate_basis == "generation" else self.config.dt) * frequency
        rng = generator(self.world.seed, "innovation", self.tick, context.group.id,
                        context.code.id, change.kind)
        if change.uses_uniform_rate():
            weights = None
            expected = change.base_rate * tempo * len(sites) * change.rate_scale(context)
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
            elif self.world.stored(context.group.id, site) is None:
                continue
            else:
                live.load(site, [self.world.stored(group_id, site) for group_id in live.group_ids])
            if variant.id in (self.world.distribution(context.group.id, site) or _EMPTY).variants:
                continue  # tutéž změnu už skupina má (paralelní inovace jinde)
            self.world.variants[variant.id] = variant
            live.innovate(site, context.group.id, variant.id, share)
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
        activations: list[tuple[str, str]] = []
        for block, updated, baseline in results:
            records.extend(self._changes(block, block.freqs, updated))
            if self.config.record_trajectories:
                self._trace(block, block.freqs, updated)
            if self.world.table is not None:
                self._follow_vocabulary(block, block.freqs, updated)
                activations.extend(self._activations(block, updated))
            block.freqs, block.previous = updated, baseline
        # Kanonické pořadí: pořadí aktivací určuje chronologii změn kódu a
        # nesmí záviset na tom, ve kterém řádku skladu proměnná leží (to
        # ovlivňují i inovace v nepropojených oblastech).
        for group_id, variable_id in sorted(activations):
            code = self.world.groups[group_id].main_code
            if variable_id in self.world.processes:
                phonology.activate(self.world, code, variable_id)
            else:
                morphology.activate(self.world, code, variable_id)
        # Kanonické pořadí nezávisí na tom, ve kterém bloku proměnná leží.
        for kind, payload in sorted(records, key=lambda item: (item[0], sorted(item[1].items()))):
            self.history.record(kind, self.tick, year, **payload)
        for variable_id, distributions in live.release():
            for group_id, distribution in zip(live.group_ids, distributions):
                if distribution is not None:
                    self.world.groups[group_id].main_code.repertoire.set(variable_id, distribution)
        if self.world.table is not None:
            for group_id in live.group_ids:
                if self.world.groups[group_id].written:
                    continue
                state = self.world.groups[group_id].main_code.phonology
                if state.pending:
                    phonology.restructure(
                        self.world, group_id, self.tick, self.config.dt, self.history, year
                    )
                if state.morph_active:
                    morphology.restructure(self.world, group_id, self.tick, self.history, year)
                if self._grammar:
                    syntax.restructure(self.world, group_id, self.tick, self.history, year)

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

    def _seed_vocabulary(self, group_id: str) -> None:
        code = self.world.groups[group_id].main_code
        if code.phonology.vocabulary:
            return
        for variable_id, variable in sorted(self.world.variables.items()):
            if variable.kind != "lexical":
                continue
            distribution = self.world.distribution(group_id, variable_id)
            if distribution is None:
                continue
            morpheme = self.world.variants[distribution.dominant()[0]].payload.get("morpheme")
            if isinstance(morpheme, str):
                code.phonology.dominant[variable.key] = morpheme
                code.phonology.uses[morpheme] = code.phonology.uses.get(morpheme, 0) + 1
                code.phonology.vocabulary.update(morphology.units_of(self.world, code, morpheme))
                code.phonology.version += 1

    def _follow_vocabulary(self, block: PoolBlock, before: np.ndarray, after: np.ndarray) -> None:
        """Slovo, které se stane dominantním, vstoupí do fonologie kódu."""
        variants = self.world.variants
        group_ids = self.world.live.group_ids
        lexical = np.array(
            [self.world.variables[variable_id].kind == "lexical" for variable_id in block.variable_ids],
            dtype=bool,
        )[:, None, None]
        # Nejdřív odchody, potom příchody: kořen, který jeden pojem opouští a
        # druhý (posunem) přebírá, tak ze slovní zásoby na okamžik nevypadne.
        for direction, mask in (
            ("leave", (before >= 0.5) & (after < 0.5) & lexical),
            ("enter", (before < 0.5) & (after >= 0.5) & lexical),
        ):
            for row, column, slot in zip(*np.nonzero(mask)):
                variant = block.slots[row][slot]
                morpheme = variants[variant].payload.get("morpheme") if variant else None
                if not isinstance(morpheme, str):
                    continue
                concept = block.variable_ids[row].split(":", 1)[1]
                code = self.world.groups[group_ids[column]].main_code
                state = code.phonology
                state.version += 1
                if direction == "leave":
                    if state.dominant.get(concept) == morpheme:
                        del state.dominant[concept]
                    state.uses[morpheme] = state.uses.get(morpheme, 1) - 1
                    if state.uses[morpheme] > 0:
                        continue
                    del state.uses[morpheme]
                else:
                    state.dominant[concept] = morpheme
                    state.uses[morpheme] = state.uses.get(morpheme, 0) + 1
                    if state.uses[morpheme] > 1:
                        continue
                    contact.adopt(self.world, group_ids[column], morpheme)
                for unit in morphology.units_of(self.world, code, morpheme):
                    if direction == "enter":
                        phonology.enter_vocabulary(self.world, code, unit)
                    else:
                        phonology.leave_vocabulary(code, unit)

    def _activations(self, block: PoolBlock, after: np.ndarray) -> list[tuple[str, str]]:
        """Procesy a analogie, které ve skupině překročily malý podíl a začnou působit."""
        group_ids = self.world.live.group_ids
        found = []
        for row, variable_id in enumerate(block.variable_ids):
            if variable_id not in self.world.processes and variable_id not in self.world.form_changes:
                continue
            changed = phonology.changed_id(variable_id)
            if changed not in block.slots[row]:
                continue
            slot = block.slots[row].index(changed)
            for column in np.flatnonzero(after[row, :, slot] >= phonology.ACTIVATION_SHARE):
                found.append((group_ids[column], variable_id))
        return found

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
            self.world, self.tick, year, self.tracker,
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


def _copied(state: Any, world: World) -> Any:
    """Hluboká kopie stavu; neměnná sdílená data světa se nekopírují."""
    memo: dict[int, Any] = {}
    for shared in (world.table, world.semantics):
        if shared is not None:
            memo[id(shared)] = shared
    return copy.deepcopy(state, memo)

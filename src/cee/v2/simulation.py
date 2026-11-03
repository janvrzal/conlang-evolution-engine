"""Hlavní smyčka enginu v2 (specifikace, oddíl Jeden tick)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterator, Sequence

import numpy as np

from cee.v2 import contact, morphology, phases, phonology, prosody, syntax, variation
from cee.v2.changes import DEFAULT_CHANGES, Change, InnovationContext, pressures_by_kind
from cee.v2.changes.lexicon import with_appeal
from cee.v2.events import WorldEvent
from cee.v2.history import History
from cee.v2.observe import LineageTracker, Snapshot, observe
from cee.v2.pools import PoolBlock
from cee.v2.repertoire import Distribution
from cee.v2.rng import Stream, cumulative, hash_poisson, stable_int
from cee.v2.transmission import TransmissionParams, prepare, transmit
from cee.v2.world import World

_MILESTONES = (0.1, 0.5, 0.9)
_LEVELS = np.array(_MILESTONES)
_EMPTY = Distribution((), np.zeros(0))
_INNOVATION_CHANGE_DOMAIN = "innovation-change"


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
    #: Ukládat do snímků celou matici vzdáleností (čtvercová v počtu skupin);
    #: jen pro metriky a testy kontinua.
    keep_distances: bool = False
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
    #: Paralelní běh (:mod:`cee.v2.parallel`): drahé dotazy (tlaky, tempo
    #: inovací) počítá každý proces jen pro své skupiny a výsledky si procesy
    #: vymění. ``None`` = vše v tomto procesu (i po ``resume``).
    shards: Any = None
    #: Jen pro testy nezávislosti na pořadí skupin: kroky po skupinách se
    #: projdou pozpátku. Výsledný stav se nesmí změnit (podmínka paralelního
    #: běhu, kde skupiny zpracovávají různé procesy).
    reverse_groups: bool = False

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
        self._grammar = any(variable.kind == "construction" for variable in world.variables.values())
        if world.table is not None:
            for group_id in world.group_ids():
                self._seed_vocabulary(group_id)
        if not world.varied:
            # Až po slovníku (posun významu a odvozování hledají slova kódu)
            # a před načtením živých proměnných, které variabilitu převezmou.
            world.varied = True
            variation.seed(world)
        world.live.load_differing(world)

    def _configure(self, changes: Sequence[Change], events: Sequence[WorldEvent]) -> None:
        self.changes = tuple(changes)
        self._change_keys = np.array(
            [stable_int(_INNOVATION_CHANGE_DOMAIN, change.kind) for change in self.changes], dtype=np.uint64
        )
        rates = self.world.params.change_rates
        unknown = set(rates) - {change.kind for change in self.changes}
        if unknown:
            raise ValueError(f"Parametry mění tempo neznámých změn: {sorted(unknown)}.")
        self._rate_scales = {change.kind: float(rates[change.kind]) for change in self.changes if change.kind in rates}
        self.events = tuple(events)
        self.checkpoints: dict[int, Checkpoint] = {}
        self.pressures = pressures_by_kind(self.changes, self.world.params)
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
        entries: list[tuple[InnovationContext, float, float, float]] = []
        for group_id in self.world.group_ids():
            group = self.world.groups[group_id]
            if group.written:
                continue  # psaný kód se nemění
            renewal = self.world.renewal(group_id, self.config.dt)
            share, frequency = self.innovation_scale(group_id)
            # Do M5 (vícejazyčnost) se simuluje jen hlavní kód skupiny.
            context = InnovationContext(self.world, group, group.main_code, self.tick, year)
            entries.append((context, renewal, share, frequency))

        if not entries or not self.changes:
            return

        group_keys = phases.innovation_group_keys(
            self.world.seed, self.tick,
            [ctx.group.id for ctx, _, _, _ in entries], [ctx.code.id for ctx, _, _, _ in entries],
        )
        renewals = np.array([renewal for _, renewal, _, _ in entries], dtype=np.float64)
        frequencies = np.array([frequency for _, _, _, frequency in entries], dtype=np.float64)

        # Tempo se počítá ze stavu na začátku kroku pro všechny skupiny, než
        # se uplatní první inovace; v paralelním běhu jen pro vlastní skupiny.
        owned = [index for index, (ctx, _, _, _) in enumerate(entries)
                 if self.shards is None or self.shards.owns(ctx.group.id)]
        rate_sums = np.zeros((len(entries), len(self.changes)), dtype=np.float64)
        for change_idx, change in enumerate(self.changes):
            for group_idx in owned:
                rate_sum = change.total_rate(entries[group_idx][0])
                if rate_sum > 0.0:
                    rate_sums[group_idx, change_idx] = float(rate_sum)
        expected = phases.expected_counts(
            rate_sums, renewals, frequencies, self.config.dt,
            np.array([change.rate_basis == "generation" for change in self.changes], dtype=bool),
            np.array([self._rate_scales.get(change.kind, 1.0) for change in self.changes], dtype=np.float64),
        )
        if self.shards is not None:
            for rows, values in self.shards.gather("expected", (owned, expected[owned])):
                expected[rows] = values

        if not np.any(expected > 0.0):
            return

        counts = hash_poisson(group_keys, self._change_keys, expected)
        # Místa inovací (a jejich váhy) závisí jen na stavu na začátku kroku;
        # spočítají se předem, v paralelním běhu každý proces pro své skupiny.
        sites: dict[tuple[int, int], tuple[Sequence[str], np.ndarray | None]] = {}
        for group_idx, (context, _, _, _) in enumerate(entries):
            if self.shards is not None and not self.shards.owns(context.group.id):
                continue
            for change_idx, change in enumerate(self.changes):
                if int(counts[group_idx, change_idx]) > 0:
                    sites[(group_idx, change_idx)] = change.weighted_sites(context)
        if self.shards is not None:
            for part in self.shards.gather("sites", sites):
                sites.update(part)

        order = list(enumerate(entries))
        for group_idx, (context, _, share, _) in (reversed(order) if self.reverse_groups else order):
            for change_idx, change in enumerate(self.changes):
                count = int(counts[group_idx, change_idx])
                if count <= 0:
                    continue
                self._apply_innovations(change, context, share, count, sites[(group_idx, change_idx)])

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

    def _apply_innovations(
        self, change: Change, context: InnovationContext, share: float, count: int,
        weighted: tuple[Sequence[str], np.ndarray | None] | None = None,
    ) -> None:
        sites, weights = change.weighted_sites(context) if weighted is None else weighted
        if not sites:
            return
        rng = Stream(
            self.world.seed,
            "innovation",
            self.tick,
            context.group.id,
            context.code.id,
            change.kind,
        )
        cumulated = None if weights is None else cumulative(weights)
        live = self.world.live
        for index in range(count):
            # Výběr místa je funkce stavu proudu; návrh varianty pak čerpá z téhož proudu.
            picked, rng.state = phases.draw_site(rng.state, len(sites), cumulated)
            site = sites[picked]
            variant = change.propose(context, site, rng, index)
            if variant is None:
                continue
            variant = with_appeal(self.world, variant)
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
                "innovation",
                self.tick,
                context.year,
                group=context.group.id,
                code=context.code.id,
                change=change.kind,
                variable=site,
                variant=variant.id,
            )

    def _innovate_with(self, change: Change, context: InnovationContext, renewal: float) -> None:
        rate_sum = change.total_rate(context)
        if rate_sum <= 0.0:
            return
        share, frequency = self.innovation_scale(context.group.id)
        expected = phases.expected_counts(
            np.array([[rate_sum]], dtype=np.float64),
            np.array([renewal], dtype=np.float64),
            np.array([frequency], dtype=np.float64),
            self.config.dt,
            np.array([change.rate_basis == "generation"], dtype=bool),
            np.array([self._rate_scales.get(change.kind, 1.0)], dtype=np.float64),
        )
        group_keys = phases.innovation_group_keys(
            self.world.seed, self.tick, [context.group.id], [context.code.id]
        )
        change_key = np.array([stable_int(_INNOVATION_CHANGE_DOMAIN, change.kind)], dtype=np.uint64)
        count = int(hash_poisson(group_keys, change_key, expected[0], pairwise=True)[0])
        if count > 0:
            self._apply_innovations(change, context, share, count)

    def _transmit(self, year: float) -> None:
        live = self.world.live
        if len(live) == 0:
            return
        inputs = prepare(self.world, live.group_ids, self.params, self.tick)
        hooks = {} if self.shards is None else {"fitness_hook": self.shards.fitness}
        results = [
            (block, *transmit(self.world, block, inputs, self.pressures, self.params, **hooks))
            for block in live.iter_blocks()
        ]
        records: list[tuple[Any, ...]] = []
        activations: list[tuple[str, str]] = []
        for block, updated, baseline in results:
            records.extend(self._changes(block, block.freqs, updated))
            if self.config.record_trajectories:
                self._trace(block, block.freqs, updated)
            # Konstrukční rozdělení je vstupem syntaxového konzumenta.
            # Zapisujeme jen proměnné, jejichž řádek se v konkrétní skupině změnil.
            for row, variable_id in enumerate(block.variable_ids):
                if self.world.variables[variable_id].kind != "construction":
                    continue
                changed_columns = np.flatnonzero(
                    np.any(block.freqs[row] != updated[row], axis=1)
                )
                for column in changed_columns:
                    group_id = self.world.live.group_ids[int(column)]
                    self.world.groups[group_id].main_code.phonology.record_grammar(variable_id)
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
            groups = [
                group_id for group_id in (list(reversed(live.group_ids)) if self.reverse_groups else live.group_ids)
                if not self.world.groups[group_id].written
            ]
            # Rozhodnutí o analogiích, nových koncovkách a přízvuku čtou jen rozdělení
            # proměnných a stav vlastní skupiny, takže jdou spočítat pro všechny skupiny naráz.
            analogies = morphology.analogy_plan(
                self.world, [group_id for group_id in groups if self.world.groups[group_id].main_code.phonology.morph_active]
            )
            constructions = syntax.ready_constructions(self.world, groups) if self._grammar else {}
            stress = prosody.plan(self.world, groups)
            for group_id in groups:
                state = self.world.groups[group_id].main_code.phonology
                if state.pending:
                    phonology.restructure(
                        self.world, group_id, self.tick, self.config.dt, self.history, year
                    )
                if state.morph_active:
                    morphology.restructure(self.world, group_id, self.tick, self.history, year, analogies.get(group_id))
                if self._grammar:
                    syntax.restructure(self.world, group_id, self.tick, self.history, year, constructions[group_id])
                if group_id in stress:
                    prosody.restructure(self.world, group_id, self.tick, self.history, year, stress[group_id])

    def _changes(
        self, block: PoolBlock, before: np.ndarray, after: np.ndarray
    ) -> list[tuple[str, dict[str, Any]]]:
        """Milníky, ustálení a zánik inovací v jednom bloku; vše vektorově."""
        group_ids = self.world.live.group_ids
        # Inovace = varianta, kterou vytvořila změna (sloupec ``change`` tabulky variant).
        numbers = self.world.registry.variants.numbers
        slot_numbers = np.array(
            [[-1 if slot is None else numbers[slot] for slot in row] for row in block.slots], dtype=np.intp
        ).reshape(len(block), block.capacity)
        innovation = phases.innovation_mask(slot_numbers, self.world.columns.variants.arrays()["change"])
        records: list[tuple[str, dict[str, Any]]] = []

        def describe(row: int, slot: int, **extra: Any) -> dict[str, Any]:
            return {"variable": block.variable_ids[row], "variant": block.slots[row][slot], **extra}

        milestones, established, extinct = phases.change_events(before, after, innovation, _LEVELS)
        for row, column, slot, first, last in zip(*milestones):
            for level in _MILESTONES[first:last]:
                records.append(("milestone", describe(row, slot, group=group_ids[column], level=level)))
        for row, column, slot in zip(*established):
            records.append(("established", describe(row, slot, group=group_ids[column])))
        for row, slot in zip(*extinct):
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
                state = code.phonology
                state.set_dominant(variable.key, morpheme)
                state.adjust_uses(morpheme, 1)
                for unit in morphology.units_of(self.world, code, morpheme):
                    state.enter_vocabulary(unit)
                code.phonology.version += 1
                code.phonology.lexicon_version += 1

    def _follow_vocabulary(self, block: PoolBlock, before: np.ndarray, after: np.ndarray) -> None:
        """Slovo, které se stane dominantním, vstoupí do fonologie kódu."""
        variants = self.world.variants
        group_ids = self.world.live.group_ids
        lexical = np.array(
            [self.world.variables[variable_id].kind == "lexical" for variable_id in block.variable_ids],
            dtype=bool,
        )
        # Nejdřív odchody, potom příchody: kořen, který jeden pojem opouští a
        # druhý (posunem) přebírá, tak ze slovní zásoby na okamžik nevypadne.
        leave, enter = phases.threshold_crossings(before, after, lexical, 0.5)
        for direction, found in (("leave", leave), ("enter", enter)):
            cells = list(zip(*found))
            for row, column, slot in (sorted(cells, key=lambda cell: (-cell[1], cell[0], cell[2]))
                                      if self.reverse_groups else cells):
                variant = block.slots[row][slot]
                morpheme = variants[variant].payload.get("morpheme") if variant else None
                if not isinstance(morpheme, str):
                    continue
                concept = block.variable_ids[row].split(":", 1)[1]
                code = self.world.groups[group_ids[column]].main_code
                state = code.phonology
                state.version += 1
                state.lexicon_version += 1
                if direction == "leave":
                    if state.dominant.get(concept) == morpheme:
                        state.set_dominant(concept, None)
                    if state.adjust_uses(morpheme, -1, missing=1) > 0:
                        continue
                else:
                    state.set_dominant(concept, morpheme)
                    if state.adjust_uses(morpheme, 1) > 1:
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
        slots = np.full(len(block), -1, dtype=np.intp)
        for row, variable_id in enumerate(block.variable_ids):
            if variable_id not in self.world.processes and variable_id not in self.world.form_changes:
                continue
            changed = phonology.changed_id(variable_id)
            if changed in block.slots[row]:
                slots[row] = block.slots[row].index(changed)
        rows, columns = phases.activation_cells(after, slots, self.world.params.activation_share)
        return [(group_ids[column], block.variable_ids[row]) for row, column in zip(rows, columns)]

    def _trace(self, block: PoolBlock, before: np.ndarray, after: np.ndarray) -> None:
        variants = self.world.variants
        group_ids = self.world.live.group_ids
        for row, column, slot in zip(*phases.trace_cells(before, after)):
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
            keep_distances=self.config.keep_distances,
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
    # Banka tvarů jen přibývá a nemění význam čísel, proto ji kopie sdílejí.
    for shared in (world.table, world.semantics, world.bank):
        if shared is not None:
            memo[id(shared)] = shared
    return copy.deepcopy(state, memo)

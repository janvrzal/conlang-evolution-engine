"""Hledání míst inovací všech druhů změn jako jedna dávka nad čísly (krok B5b).

Stav indexů míst (morfologie, sémantika, konstrukce) patří **světu** (``World.sites``,
:func:`site_index`) a žije v Rustu (``cee_core.SiteIndex``, ``rust/cee_core/src/sites.rs``);
Python mu posílá jen pohledy na pole (příznaky slovní zásoby, tvary kódu, dominantní
kořeny, sloupce světa) a malé přírůstkové tabulky (jména, výchozí tvary, vlastnosti
kořenů, graf pojmů, katalog funkcí, druhy konstrukcí). Jedno volání :meth:`SiteIndex.batch`
vrátí pro všechny skupiny a druhy změn celkové míry a počty míst (matice skupina × sloupec);
místa a míry se čtou zvlášť jen tam, kde je inovace.

Bez rozšíření (``CEE_NATIVE=0``) počítá totéž :class:`PythonSites` v Pythonu, ve stejné
číselné podobě (reference testu Rust proti Pythonu). Obě podoby mají stejné rozhraní;
:class:`SiteIndex` je tenká vrstva, která z registru světa a stavu kódů sestavuje vstupy
a vyřizuje, co si index vyžádá (``needs``: výchozí tvary a vlastnosti kořenů).

Stav indexu je odvozený: po kopii světa (checkpoint) a po uložení (pickle) se nepřenáší
a deterministicky se postaví znovu při prvním použití.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from cee.v2 import native, phases
from cee.v2.language import semantic_index as semantic
from cee.v2.language.morphology_index import MorphIndex
from cee.v2.language.semantic_index import SemanticDependencies, SemanticSitesIndex

if TYPE_CHECKING:
    from cee.v2.changes.base import InnovationContext
    from cee.v2.world import Code, World

#: Sloupce výstupu dávky: expresivní tvoření, sedm sémantických změn, vyrovnání, rozšíření,
#: deset syntaktických změn a výpůjčky slov (stejné pořadí jako ``sites::COLUMNS`` v Rustu).
SYNTAX_KINDS = (
    "periphrasis", "cliticization", "affixation", "exaptation", "category_loss",
    "negation_reinforcement", "negation_reduction", "negation_renewal", "order_fixation", "order_relaxation",
)
COL_COINAGE = 0
COL_SEMANTIC = 1
COL_LEVELING = COL_SEMANTIC + len(semantic.KINDS)
COL_EXTENSION = COL_LEVELING + 1
COL_SYNTAX = COL_EXTENSION + 1
COL_BORROWING = COL_SYNTAX + len(SYNTAX_KINDS)
COLUMNS = COL_BORROWING + 1

#: Šablony funkcí, druhy konstrukcí a stupně opisu jako čísla (viz ``sites.rs``).
TEMPLATES = {"inflection": 0, "negation": 1, "order": 2}
CONSTRUCTION_KINDS = {"zero": 0, "periphrastic": 1, "synthetic": 2, "pre": 3, "embraced": 4, "post": 5,
                      "free": 6, "fixed": 7}
STAGES = {None: -1, "free": 0, "clitic": 1}
ZERO, PERIPHRASTIC, SYNTHETIC, PRE, EMBRACED, POST, FREE, FIXED = range(8)
INFLECTION, NEGATION, ORDER = 0, 1, 2
TEMPLATE_OF = (INFLECTION,) * 5 + (NEGATION,) * 3 + (ORDER,) * 2
(PERIPHRASIS, CLITICIZATION, AFFIXATION, EXAPTATION, CATEGORY_LOSS, NEGATION_REINFORCEMENT, NEGATION_REDUCTION,
 NEGATION_RENEWAL, ORDER_FIXATION, ORDER_RELAXATION) = range(10)

_ConstructionKey = tuple[int, int]


class PythonSites:
    """Reference v Pythonu: stejné rozhraní a stejná čísla jako ``cee_core.SiteIndex``."""

    native = False

    def __init__(self) -> None:
        self.morph = MorphIndex()
        self.semantic = SemanticDependencies()
        self.sem_sites = SemanticSitesIndex(self.semantic)
        self.catalog: dict[str, Any] = {}
        self.constructions: dict[int, _ConstructionKey] = {}
        self._results: dict[int, tuple[list[list[int]], list[float]]] = {}

    # --- tabulky ----------------------------------------------------------------

    def set_names(self, morphemes_from: int, morphemes: list[str], concepts_from: int, concepts: list[str]) -> None:
        if morphemes_from != len(self.morph.names) or concepts_from != len(self.semantic.concepts):
            raise ValueError("jména morfémů či pojmů na sebe nenavazují")
        self.morph.set_names(morphemes)
        self.semantic.set_names(concepts)

    def set_defaults(self, numbers: list[int], forms: list[Any]) -> None:
        self.morph.set_defaults(numbers, forms)

    def set_roots(self, numbers: list[int], sources: list[int], bases: list[int]) -> None:
        self.semantic.set_roots(numbers, sources, bases)

    def set_graph(self, concepts: int, *arrays: Any) -> None:
        self.semantic.set_graph(semantic.Graph(concepts, *arrays))

    def set_catalog(
        self, template: list[int], word_class: list[int], class_: list[int], cell: list[int], has_cell: list[bool],
        has_orders: list[bool], coverage: list[float], source_start: list[int], sources: list[int],
        donor_start: list[int], donors: list[int], deputy_start: list[int], deputies: list[int],
    ) -> None:
        self.catalog = {
            "template": template, "word_class": word_class, "class": class_, "cell": cell, "has_cell": has_cell,
            "has_orders": has_orders, "coverage": coverage, "source_start": source_start, "sources": sources,
            "donor_start": donor_start, "donors": donors, "deputy_start": deputy_start, "deputies": deputies,
            "count": len(template),
        }

    def set_constructions(self, variants: list[int], kinds: list[int], stages: list[int]) -> None:
        for variant, kind, stage in zip(variants, kinds, stages):
            self.constructions[int(variant)] = (int(kind), int(stage))

    # --- dorovnání --------------------------------------------------------------

    def sync_morphology(
        self, bank: Any, tokens: list[int], flags: list[Any], store: list[tuple[Any, Any, Any]], columns: Any,
    ) -> list[int]:
        return self.morph.sync(bank.forms, tuple(columns), tokens, flags, store)

    def sync_semantic(
        self, tokens: list[int], dominant: list[Any], sites: list[Any], taboo: list[Any], suffix: list[bool],
    ) -> list[int]:
        return self.semantic.sync(tokens, dominant, sites, taboo, suffix)

    # --- dávka ------------------------------------------------------------------

    def totals(
        self, tokens: list[int], variants: npt.NDArray[np.int32], l2_share: npt.NDArray[np.float64],
        lexical: npt.NDArray[np.int64], morph_on: list[bool], semantic_on: list[bool],
        bases: npt.NDArray[np.float64], scales: tuple[float, float, float], borrowing: Any = None,
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64]]:
        coinage_scale, analogy_boost, loss_boost = scales
        groups, functions = len(tokens), self.catalog.get("count", 0)
        totals = np.zeros((groups, COLUMNS), dtype=np.float64)
        counts = np.zeros((groups, COLUMNS), dtype=np.int64)

        def uniform(base: float, count: int, scale: float) -> float:
            return float(base * count * scale) if count > 0 else 0.0

        for group, token in enumerate(tokens):
            counts[group, COL_COINAGE] = int(lexical[group])
            totals[group, COL_COINAGE] = uniform(float(bases[COL_COINAGE]), int(lexical[group]), coinage_scale)
            if semantic_on[group]:
                for kind in range(len(semantic.KINDS)):
                    found, total = self.sem_sites.count_total(token, kind, float(bases[COL_SEMANTIC + kind]))
                    counts[group, COL_SEMANTIC + kind], totals[group, COL_SEMANTIC + kind] = found, total
            if morph_on[group]:
                leveling, extension = self.morph.counts(token)
                scale = 1.0 + analogy_boost * float(l2_share[group])
                counts[group, COL_LEVELING], counts[group, COL_EXTENSION] = leveling, extension
                totals[group, COL_LEVELING] = uniform(float(bases[COL_LEVELING]), leveling, scale)
                totals[group, COL_EXTENSION] = uniform(float(bases[COL_EXTENSION]), extension, scale)
            if borrowing is not None and borrowing[3][group]:
                found, total = self._borrowing(token, group, borrowing, float(bases[COL_BORROWING]))
                counts[group, COL_BORROWING], totals[group, COL_BORROWING] = found, total
            if functions:
                sites, rates = self._syntax(
                    token, variants[group * functions:(group + 1) * functions], bases, float(l2_share[group]), loss_boost,
                )
                self._results[token] = (sites, rates)
                for kind in range(len(SYNTAX_KINDS)):
                    found = len(sites[kind])
                    counts[group, COL_SYNTAX + kind] = found
                    if kind == CATEGORY_LOSS:
                        totals[group, COL_SYNTAX + kind] = phases.rate_total(rates) if found else 0.0
                    else:
                        totals[group, COL_SYNTAX + kind] = uniform(float(bases[COL_SYNTAX + kind]), found, 1.0)
        return totals, counts

    def _borrowing(self, token: int, group: int, borrowing: Any, base: float) -> tuple[int, float]:
        """Počet míst výpůjček a součet jejich měr (viz ``sites::SiteIndex::borrowing``)."""
        channels, distinct, exposure, _, factors = borrowing
        slot = self.semantic.slots.get(token)
        concepts = len(factors) // max(channels, 1)
        shares = [float(exposure[group * channels + channel]) for channel in range(channels)]
        rates = []
        for concept in self.semantic.by_name:
            if slot is None or concept >= len(slot.site) or not slot.site[concept]:
                continue
            if distinct:
                total = 0.0
                for channel, share in enumerate(shares):
                    total += share * float(factors[channel * concepts + concept])
                rates.append(base * total)
            else:
                rates.append(base * shares[0] * float(factors[concept]))
        return len(rates), (phases.rate_total(rates) if rates else 0.0)

    def syntax_sites(self, token: int, kind: int) -> tuple[npt.NDArray[np.uint32], npt.NDArray[np.float64]]:
        sites, rates = self._results.get(token, ([[] for _ in SYNTAX_KINDS], []))
        return (np.array(sites[kind], dtype=np.uint32),
                np.array(rates if kind == CATEGORY_LOSS else [], dtype=np.float64))

    def _syntax(
        self, token: int, variants: Any, bases: Any, l2_share: float, loss_boost: float,
    ) -> tuple[list[list[int]], list[float]]:
        catalog = self.catalog
        dominant = self.sem_sites.dominant(token)

        def present(concept: int) -> bool:
            return 0 <= concept < len(dominant) and dominant[concept] >= 0

        current = [self.constructions.get(int(variant)) if variant >= 0 else None for variant in variants]

        def weakness(function: int) -> float:
            if not catalog["has_cell"][function]:
                return 0.0
            if catalog["word_class"][function] == 0:
                return 1.0
            return self.morph.weakness(token, catalog["class"][function], catalog["cell"][function])

        def span(start: str, items: str, function: int) -> list[int]:
            return catalog[items][catalog[start][function]:catalog[start][function + 1]]

        def sourced(function: int) -> bool:
            return any(present(concept) for concept in span("source_start", "sources", function))

        def compensated(function: int) -> bool:
            found = 0.0
            for deputy in span("deputy_start", "deputies", function):
                found_deputy = current[deputy]
                if found_deputy is not None:
                    kind = found_deputy[0]
                    carries = kind == FIXED if catalog["template"][deputy] == ORDER else kind != ZERO
                    if carries:
                        found = max(found, catalog["coverage"][deputy])
            return found > 0.0

        def residual(donor: int) -> bool:
            return (catalog["word_class"][donor] != 0 and bool(catalog["has_cell"][donor])
                    and self.morph.residual(token, catalog["class"][donor], catalog["cell"][donor]) >= 0)

        def donors_found(function: int) -> bool:
            return any(
                catalog["word_class"][donor] == catalog["word_class"][function] and compensated(donor)
                and residual(donor) for donor in span("donor_start", "donors", function)
            )

        def pressure(function: int, kind: int, stage: int) -> float:
            if kind == PERIPHRASTIC and stage == 0:
                return 1.0
            bound = kind == SYNTHETIC or (kind == PERIPHRASTIC and stage == 1)
            if not bound:
                return 0.0
            unreliable = weakness(function) if kind == SYNTHETIC else 0.0
            return unreliable + loss_boost * l2_share

        sites: list[list[int]] = [[] for _ in SYNTAX_KINDS]
        rates: list[float] = []
        for function, found in enumerate(current):
            if found is None:
                continue
            kind, stage = found
            for change, template in enumerate(TEMPLATE_OF):
                if catalog["template"][function] != template:
                    continue
                if change == PERIPHRASIS:
                    applies = (weakness(function) != 0.0 if kind == SYNTHETIC else kind == ZERO) and sourced(function)
                elif change == CLITICIZATION:
                    applies = kind == PERIPHRASTIC and stage == 0
                elif change == AFFIXATION:
                    applies = kind == PERIPHRASTIC and stage == 1
                elif change == EXAPTATION:
                    applies = kind == ZERO and donors_found(function)
                elif change == CATEGORY_LOSS:
                    applies = pressure(function, kind, stage) > 0.0
                elif change == NEGATION_REINFORCEMENT:
                    applies = kind == PRE and sourced(function)
                elif change == NEGATION_REDUCTION:
                    applies = kind == EMBRACED
                elif change == NEGATION_RENEWAL:
                    applies = kind == POST
                elif change == ORDER_FIXATION:
                    applies = kind == FREE and bool(catalog["has_orders"][function])
                else:
                    applies = kind == FIXED
                if not applies:
                    continue
                sites[change].append(function)
                if change == CATEGORY_LOSS:
                    rates.append(float(bases[COL_SYNTAX + CATEGORY_LOSS]) * pressure(function, kind, stage))
        return sites, rates

    # --- čtení ------------------------------------------------------------------

    def semantic_sites(self, token: int, kind: int) -> npt.NDArray[np.uint32]:
        return np.array(self.sem_sites.sites(token, kind), dtype=np.uint32)

    def semantic_rates(self, token: int, kind: int, base: float) -> npt.NDArray[np.float64]:
        return self.sem_sites.rates(token, kind, base)

    def semantic_dominant(self, token: int) -> npt.NDArray[np.int32]:
        return np.array(self.sem_sites.dominant(token), dtype=np.int32)

    def morph_candidates(self, token: int, extension: bool) -> tuple[list[int], list[int]]:
        return self.morph.candidates.candidates(token, extension)

    def morph_stats(self, token: int) -> tuple[list[list[int]], list[tuple[int, list[int], int]]]:
        return self.morph.stats(token)

    def morph_members(self, token: int) -> list[int]:
        return self.morph.members(token)

    def morph_weakness(self, token: int, word_class: int, cell: int) -> float:
        return self.morph.weakness(token, word_class, cell)


class SiteIndex:
    """Index míst světa: sestavuje vstupy z registru a stavu kódů a vyřizuje, co si backend vyžádá."""

    def __init__(self, handle: Any = None) -> None:
        self._handle: Any = PythonSites() if handle is None else handle
        self.native = handle is not None
        self._reset_tracking()

    def _reset_tracking(self) -> None:
        self._morphemes_sent = 0
        self._concepts_sent = 0
        self._morph_keys: dict[int, tuple[int, ...]] = {}
        self._semantic_keys: dict[int, tuple[int, ...]] = {}
        self._graph_key: tuple[Any, ...] | None = None
        self._graph_object: Any = None
        self._graph_generation = 0
        self._catalog_key: tuple[Any, ...] | None = None
        self._functions: list[str] = []
        self._known_variants: set[int] = set()
        self._site_cache: dict[int, tuple[Any, Any]] = {}
        self._taboo_cache: dict[int, tuple[Any, Any]] = {}
        self._borrowing_key: tuple[Any, ...] | None = None
        self._borrowing_cache = np.zeros(0, dtype=np.float64)

    def __getstate__(self) -> dict[str, Any]:
        return {"native": self.native}

    def __setstate__(self, state: dict[str, Any]) -> None:
        handle = native.new_site_index() if state["native"] else None
        self._handle = PythonSites() if handle is None else handle
        self.native = handle is not None
        self._reset_tracking()

    @property
    def handle(self) -> Any:
        return self._handle

    # --- tabulky světa ----------------------------------------------------------

    def _names(self, world: World) -> None:
        morphemes, concepts = world.registry.morphemes.names, world.registry.concepts.names
        if len(morphemes) != self._morphemes_sent or len(concepts) != self._concepts_sent:
            self._handle.set_names(
                self._morphemes_sent, morphemes[self._morphemes_sent:], self._concepts_sent,
                concepts[self._concepts_sent:],
            )
            self._morphemes_sent, self._concepts_sent = len(morphemes), len(concepts)

    def _catalog(self, world: World) -> None:
        """Katalog gramatických funkcí v pořadí jmen; posílá se jen při změně."""
        from cee.v2.language.constructions import catalog_for

        entries = catalog_for(world)
        table = world.columns.morphemes
        key = (id(entries), len(table.word_classes), len(table.cells), len(world.registry.concepts))
        if key == self._catalog_key:
            return
        self._catalog_key = key
        names = sorted(entries)
        self._functions = names
        position = {name: at for at, name in enumerate(names)}
        concepts = world.registry.concepts
        template: list[int] = []
        word_class: list[int] = []
        class_: list[int] = []
        cell: list[int] = []
        has_cell: list[bool] = []
        has_orders: list[bool] = []
        coverage: list[float] = []
        source_start, donor_start, deputy_start = [0], [0], [0]
        sources: list[int] = []
        donors: list[int] = []
        deputies: list[int] = []
        for name in names:
            entry = entries[name]
            template.append(TEMPLATES[entry.template])
            kind = entry.word_class
            word_class.append(0 if kind is None else 1 if kind == "noun" else 2)
            class_.append(-1 if kind is None else table.word_classes.get(kind))
            cell.append(-1 if entry.cell is None else table.cells.get(entry.cell))
            has_cell.append(entry.cell is not None)
            has_orders.append(bool(entry.orders))
            coverage.append(float(entry.coverage))
            sources.extend(concepts.get(concept) for concept in entry.sources)
            source_start.append(len(sources))
            donors.extend(position[donor] for donor in entry.donors if donor in position)
            donor_start.append(len(donors))
            deputies.extend(at for at, other in enumerate(names) if name in entries[other].compensates)
            deputy_start.append(len(deputies))
        self._handle.set_catalog(
            template, word_class, class_, cell, has_cell, has_orders, coverage, source_start, sources, donor_start,
            donors, deputy_start, deputies,
        )

    def _graph(self, world: World) -> bool:
        """Graf pojmů pro rodiny sémantických změn; vrací, zda se od minula změnil."""
        graph = world.semantics
        concepts = world.registry.concepts
        classes = tuple(sorted(world.concept_classes.items()))
        if self._graph_key is not None and len(concepts) == self._graph_key[1] and classes == self._graph_key[2] and (
            graph is self._graph_object or (graph == self._graph_object)
        ):
            return False
        self._graph_key = (None, len(concepts), classes)
        self._graph_object = graph
        count = len(concepts)
        into_start, source, shift, conversion, derivation, flags = [0], [], [], [], [], []
        compound_start, left, right = [0], [], []
        class_of = world.concept_classes
        for target in range(count):
            name = concepts.names[target]
            if graph is not None:
                for relation in graph.into(name):
                    source.append(concepts.get(relation.source))
                    shift.append(relation.shift_weight)
                    conversion.append(math.log1p(relation.polysemy) if relation.polysemy >= 1 else 0.0)
                    derivation.append(relation.derivation_weight)
                    flags.append(
                        (semantic.COMPATIBLE if class_of.get(relation.source) == class_of.get(name) else 0)
                        | (semantic.POLYSEMOUS if relation.polysemy >= 1 else 0)
                        | (semantic.COLEXIFIED if relation.colexification >= 20 else 0)
                    )
                for first, second in graph.compounds.get(name, ()):
                    left.append(concepts.get(first))
                    right.append(concepts.get(second))
            into_start.append(len(source))
            compound_start.append(len(left))
        self._handle.set_graph(
            count, np.array(into_start, dtype=np.int64), np.array(source, dtype=np.int64),
            np.array(shift, dtype=np.float64), np.array(conversion, dtype=np.float64),
            np.array(derivation, dtype=np.float64), np.array(flags, dtype=np.uint8),
            np.array(compound_start, dtype=np.int64), np.array(left, dtype=np.int64), np.array(right, dtype=np.int64),
        )
        self._graph_generation += 1
        return True

    def _supply_defaults(self, world: World, numbers: list[int]) -> None:
        names = world.registry.morphemes.names
        self._handle.set_defaults(numbers, [world.morphemes[names[number]].form for number in numbers])

    def _supply_roots(self, world: World, numbers: list[int]) -> None:
        names = world.registry.morphemes.names
        morphemes, concepts = world.registry.morphemes, world.registry.concepts
        sources, bases = [], []
        for number in numbers:
            morpheme = world.morphemes.get(names[number])
            if morpheme is None:  # číslo kořene, který svět nezná: bez odvození
                sources.append(-1)
                bases.append(-1)
                continue
            derived = morpheme.etymology == "derivation" and len(morpheme.sources) == 1
            sources.append(concepts.get(morpheme.sources[0]) if derived else -1)
            bases.append(-1 if morpheme.base is None else morphemes.get(morpheme.base, -3))
        self._handle.set_roots(numbers, sources, bases)

    # --- dorovnání ------------------------------------------------------------

    def _bank(self, world: World) -> Any:
        bank = world.form_bank()
        if self.native:
            assert bank._native is not None, "index v Rustu potřebuje banku tvarů v Rustu"
            return bank._native
        return bank

    def sync_morphology(self, world: World, codes: list[Code]) -> None:
        """Dorovná morfologii kódů, jejichž stav se od minula změnil."""
        if world.table is None:
            return
        changed = []
        for code in codes:
            state = code.phonology
            key = (state.version, len(code.forms.log), len(state.vocabulary_log), len(state.vocabulary))
            if self._morph_keys.get(code.forms.token) != key:
                changed.append((code, key))
        if not changed:
            return
        table: Any = world.columns.morphemes
        columns = [table.kind, table.word_class, table.cell, table.lexeme, table.exponent, table.boundary]
        tokens = [code.forms.token for code, _ in changed]
        flags = [code.phonology.vocabulary.flags for code, _ in changed]
        store = [code.forms.raw() for code, _ in changed]
        bank = self._bank(world)
        for _ in range(64):
            needs = self._handle.sync_morphology(bank, tokens, flags, store, columns)
            if not len(needs):
                break
            self._supply_defaults(world, list(needs))
        else:
            raise RuntimeError("morfologický index se nepodařilo dorovnat")
        for code, key in changed:
            self._morph_keys[code.forms.token] = key

    def sync_semantics(self, world: World, contexts: list[InnovationContext]) -> None:
        """Dorovná sémantiku kódů, jejichž slovník (dominantní kořeny) se od minula změnil."""
        if world.table is None:
            return
        for _ in range(2):
            changed = [
                ctx for ctx in contexts
                if self._semantic_keys.get(ctx.code.forms.token)
                != (ctx.code.phonology.lexicon_version, self._graph_generation)
            ]
            if not changed:
                return
            if self._graph(world):
                continue  # graf se změnil: všechny kódy se dorovnají znovu
            break
        concepts = world.registry.concepts
        tokens, dominant, sites, taboo = [], [], [], []
        for ctx in changed:
            code = ctx.code
            tokens.append(code.forms.token)
            dominant.append(code.phonology.dominant.roots)
            sites.append(self._lexical_numbers(world, ctx))
            taboo.append(self._taboo_numbers(world, ctx, concepts))
        suffix = [bool(world.derivational_suffix)] * len(changed)
        for _ in range(64):
            needs = self._handle.sync_semantic(tokens, dominant, sites, taboo, suffix)
            if not len(needs):
                break
            self._supply_roots(world, list(needs))
        else:
            raise RuntimeError("sémantický index se nepodařilo dorovnat")
        for ctx in changed:
            self._semantic_keys[ctx.code.forms.token] = (ctx.code.phonology.lexicon_version, self._graph_generation)

    def _lexical_numbers(self, world: World, context: InnovationContext) -> npt.NDArray[np.int32]:
        """Čísla pojmů lexikálních proměnných kódu (seznam ID drží repertoár, dokud se nezmění)."""
        ids = context.code.repertoire.variable_ids_of("lexical")
        token = context.code.forms.token
        cached = self._site_cache.get(token)
        if cached is None or cached[0] is not ids:
            concepts = world.registry.concepts
            cached = self._site_cache[token] = (
                ids, np.array([concepts.get(item.split(":", 1)[1]) for item in ids], dtype=np.int32),
            )
        return cached[1]

    def _taboo_numbers(self, world: World, context: InnovationContext, concepts: Any) -> npt.NDArray[np.int32]:
        taboo = context.group.taboo
        token = context.code.forms.token
        cached = self._taboo_cache.get(token)
        if cached is None or cached[0] != taboo:
            cached = self._taboo_cache[token] = (
                taboo, np.array([concepts.get(concept) for concept in sorted(taboo)], dtype=np.int32),
            )
        return cached[1]

    def _constructions(self, world: World, variants: npt.NDArray[np.int32]) -> None:
        """Druh a stupeň konstrukcí, které se objevily mezi dominantními variantami."""
        fresh = [int(number) for number in np.unique(variants) if number >= 0 and int(number) not in self._known_variants]
        if not fresh:
            return
        names = world.registry.variants.names
        kinds, stages = [], []
        for number in fresh:
            construction = world.variants[names[number]].payload["construction"]
            kinds.append(CONSTRUCTION_KINDS[construction.kind])
            stages.append(STAGES[construction.stage])
        self._handle.set_constructions(fresh, kinds, stages)
        self._known_variants.update(fresh)

    # --- dávka ----------------------------------------------------------------

    def refresh(self, world: World, contexts: list[InnovationContext]) -> None:
        """Dorovná všechny indexy kódů na aktuální stav (jen kódy, které se změnily)."""
        self._names(world)
        self._catalog(world)
        codes = [ctx.code for ctx in contexts]
        self.sync_morphology(world, codes)
        self.sync_semantics(world, contexts)

    def prepare(self, world: World, codes: list[Code]) -> None:
        """Dorovná jen morfologii kódů (koncovky, slabost buněk), třeba pro ``class_stats``."""
        self._names(world)
        self.sync_morphology(world, codes)

    def batch(
        self, world: World, contexts: list[InnovationContext], bases: dict[int, float], coinage_scale: float,
        borrowing: tuple[int, bool, npt.NDArray[np.float64], list[bool], npt.NDArray[np.float64]] | None = None,
    ) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64]]:
        """Celkové míry a počty míst (skupina × sloupec) všech druhů změn v ``bases`` (sloupec → základní míra)."""
        self.refresh(world, contexts)
        groups = len(contexts)
        if not groups:
            return np.zeros((0, COLUMNS)), np.zeros((0, COLUMNS), dtype=np.int64)
        functions = self._functions
        variants = np.full(groups * len(functions), -1, dtype=np.int32)
        if functions:
            numbers = world.registry.variants.numbers
            tracked = [f"construction:{name}" in world.variables for name in functions]
            ids = [f"construction:{name}" for name in functions]
            dominant = world.dominant
            for group, context in enumerate(contexts):
                row = group * len(functions)
                group_id = context.group.id
                for at, variable in enumerate(ids):
                    if tracked[at]:
                        found = dominant(group_id, variable)
                        if found is not None:
                            variants[row + at] = numbers[found[0]]
            self._constructions(world, variants)
        base = np.zeros(COLUMNS, dtype=np.float64)
        for column, value in bases.items():
            base[column] = value
        params = world.params
        table_on = world.table is not None
        morph_on = [table_on and bool(world.paradigms)] * groups
        semantic_on = [table_on and world.semantics is not None] * groups
        totals, counts = self._handle.totals(
            [ctx.code.forms.token for ctx in contexts], variants,
            np.array([ctx.code.l2_share for ctx in contexts], dtype=np.float64),
            np.array([len(ctx.code.repertoire.variable_ids_of("lexical")) for ctx in contexts], dtype=np.int64),
            morph_on, semantic_on, base, (coinage_scale, params.analogy_l2_boost, params.category_loss_l2_boost),
            borrowing,
        )
        return np.asarray(totals).reshape(groups, COLUMNS), np.asarray(counts).reshape(groups, COLUMNS)

    def borrowing_factors(self, world: World, channels: tuple[str, ...]) -> npt.NDArray[np.float64]:
        """Filtr výpůjček slov podle kanálu a čísla pojmu (kanál × pojem, po řádcích); drží se, dokud se svět nezmění."""
        from cee.v2.contact import borrowing_factor

        names = world.registry.concepts.names
        key = (id(world.params), len(names), channels)
        if self._borrowing_key != key:
            variables = world.variables
            self._borrowing_key = key
            self._borrowing_cache = np.array(
                [
                    borrowing_factor(world, f"lexical:{name}", channel) if f"lexical:{name}" in variables else 0.0
                    for channel in channels for name in names
                ],
                dtype=np.float64,
            )
        return self._borrowing_cache

    # --- čtení míst -------------------------------------------------------------

    def semantic_sites(self, world: World, code: Code, kind: int) -> list[str]:
        """Názvy míst (``lexical:pojem``) sémantické změny v pořadí jmen; kód musí být dorovnaný."""
        names = world.registry.concepts.names
        found = np.asarray(self._handle.semantic_sites(code.forms.token, kind)).tolist()
        return ["lexical:" + names[number] for number in found]

    def semantic_rates(self, code: Code, kind: int, base: float) -> npt.NDArray[np.float64]:
        return np.asarray(self._handle.semantic_rates(code.forms.token, kind, base), dtype=np.float64)

    def candidates(self, world: World, code: Code, extension: bool) -> list[tuple[str, str | None]]:
        """Tvar a (u rozšíření) koncovka míst vyrovnání či rozšíření v pořadí řetězcových ID míst."""
        names = world.registry.morphemes.names
        units, exponents = self._handle.morph_candidates(code.forms.token, extension)
        return [(names[unit], names[exponent] if extension else None) for unit, exponent in zip(
            np.asarray(units).tolist(), np.asarray(exponents).tolist())]

    def stats(self, world: World, code: Code) -> tuple[Any, Any]:
        """Počty koncovek (třída, buňka, koncovka, počet) a podoby koncovek; kód musí být dorovnaný."""
        return self._handle.morph_stats(code.forms.token)

    def weakness(self, world: World, code: Code, word_class: str, cell: str) -> float:
        table = world.columns.morphemes
        return float(self._handle.morph_weakness(code.forms.token, table.word_classes.get(word_class),
                                                 table.cells.get(cell)))

    def syntax_sites(self, code: Code, kind: int) -> tuple[list[int], npt.NDArray[np.float64]]:
        """Funkce (čísla v katalogu) a míry zániku kategorie, které jsou místy změny; po :meth:`batch`."""
        found, rates = self._handle.syntax_sites(code.forms.token, kind)
        return np.asarray(found).tolist(), np.asarray(rates, dtype=np.float64)

    @property
    def functions(self) -> list[str]:
        return self._functions


def site_index(world: World) -> SiteIndex:
    """Index míst světa; vzniká při prvním použití (Rust, je-li k dispozici, jinak reference v Pythonu)."""
    index = world.sites
    if index is None:
        handle = native.new_site_index() if world.table is not None and world.form_bank()._native is not None else None
        index = world.sites = SiteIndex(handle)
    return index

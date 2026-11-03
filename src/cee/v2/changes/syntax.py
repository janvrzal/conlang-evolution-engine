"""Syntaktické změny (iterace 3, oblast C; milníky M4 a M4b).

Každá změna navrhuje *další krok* od konstrukce, která ve skupině právě
převažuje. Gramatikalizace tak jde jedním směrem (volné slovo → přiklonka →
koncovka) a cykly se uzavírají samy: nová koncovka eroduje a otevře místo
dalšímu opisu.

Změna nezná konkrétní funkci: místem je každá funkce katalogu se šablonou
změny (``inflection``, ``negation``, ``order``), kterou jazyk sleduje. Jazyk
bez určitého členu, bez času nebo bez pádu je proto jen jiný řádek profilu.
"""

from __future__ import annotations

from typing import ClassVar, Mapping, Sequence, cast

import numpy as np

from cee.v2 import phases, syntax
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.changes.sites import column_totals, native_column
from cee.v2.language.constructions import Construction, catalog_for
from cee.v2.language.site_index import COL_SYNTAX, site_index
from cee.v2.pressures import Actuation, Conformity, Pressure
from cee.v2.pressures.syntactic import Ambiguity, Economy, Expressivity, Fusion, Learnability
from cee.v2.repertoire import Origin, Variant
from cee.v2.rng import RandomSource

SYNTAX_PRESSURES: Mapping[type[Pressure], float] = {
    Expressivity: 1.0,
    Economy: 1.0,
    Fusion: 1.0,
    Ambiguity: 1.0,
    Learnability: 1.0,
    Conformity: 0.1,
    Actuation: 1.0,
}


class SyntacticChange(Change):
    """Rodič syntaktických změn; místem je jedna gramatická funkce skupiny."""

    target = "construction"
    rate_basis = "generation"
    pressures = SYNTAX_PRESSURES
    template: ClassVar[str]

    def next(
        self, context: InnovationContext, current: Construction, rng: RandomSource
    ) -> Construction | None:
        raise NotImplementedError

    def applies(self, context: InnovationContext, current: Construction) -> bool:
        raise NotImplementedError

    def _found(self, context: InnovationContext) -> tuple[list[str], list[float]]:
        """Místa změny (``construction:funkce`` v pořadí jmen) a míry zániku kategorie z indexu míst světa."""
        world = context.world
        index = site_index(world)
        column = cast(int, self.site_column)
        index.batch(world, [context], {column: self.base_rate}, 1.0)
        functions, rates = index.syntax_sites(context.code, column - COL_SYNTAX)
        names = index.functions
        return [syntax.variable_id(names[number]) for number in functions], rates.tolist()

    def _sites_reference(self, context: InnovationContext) -> list[str]:
        """Původní sestavení míst z dominantních konstrukcí, nezávislé na indexu míst."""
        found = []
        for entry in syntax.functions(context.world, self.template):
            current = syntax.dominant(context.world, context.group.id, entry.id)
            if current is not None and self.applies(context, current):
                found.append(syntax.variable_id(entry.id))
        return found

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if native_column(self) is None:
            return self._sites_reference(context)
        return self._found(context)[0]

    def total_rate(self, context: InnovationContext) -> float:
        if native_column(self) is None:
            return super().total_rate(context)
        return column_totals(self, [context])[0]

    def total_rates(self, contexts: Sequence[InnovationContext]) -> list[float]:
        if native_column(self) is None:
            return super().total_rates(contexts)
        return column_totals(self, contexts)

    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        current = syntax.dominant(context.world, context.group.id, site.split(":", 1)[1])
        if current is None or not self.applies(context, current):
            return None
        construction = self.next(context, current, rng)
        if construction is None:
            return None
        _, variant = syntax.register(
            context.world, construction, Origin(self.kind, context.tick, context.year, context.group.id)
        )
        return variant


def _sources(context: InnovationContext, function: str) -> list[str]:
    dominant = context.code.phonology.dominant
    return [concept for concept in catalog_for(context.world)[function].sources if concept in dominant]


def _pick(options: Sequence[str], rng: RandomSource) -> str:
    return options[int(rng.integers(len(options)))]


class Periphrasis(SyntacticChange):
    """Opis: pomocné slovo + citační tvar (*mám napsáno*, *I have written*).

    Vzniká tam, kde funkci jazyk dosud nevyjadřoval vůbec (ukazovací zájmeno
    jako člen, *ille → le*), a tam, kde koncovka zeslábla (obnova, Hopper &
    Traugott 2003). Opis vedle neporušené koncovky nemá čím uspět, a tak ho
    změna ani nenavrhuje.
    """

    site_column = COL_SYNTAX + 0
    kind, template, base_rate = "periphrasis", "inflection", 0.05

    def applies(self, context, current):
        if current.kind == "synthetic":
            if syntax.weakness(context.world, context.code, current.function) == 0.0:
                return False
        elif current.kind != "zero":
            return False
        return bool(_sources(context, current.function))

    def next(self, context, current, rng):
        sources = _sources(context, current.function)
        return Construction(current.function, "periphrastic", _pick(sources, rng), "free")


class Cliticization(SyntacticChange):
    """Pomocné slovo ztratí samostatnost a přiklonní se ke slovu."""

    site_column = COL_SYNTAX + 1
    kind, template, base_rate = "cliticization", "inflection", 0.04

    def applies(self, context, current):
        return current.kind == "periphrastic" and current.stage == "free"

    def next(self, context, current, rng):
        return Construction(current.function, "periphrastic", current.source, "clitic")


class Affixation(SyntacticChange):
    """Přiklonka sroste se slovem v novou koncovku (*cantare habeo → chanterai*)."""

    site_column = COL_SYNTAX + 2
    kind, template, base_rate = "affixation", "inflection", 0.03

    def applies(self, context, current):
        return current.kind == "periphrastic" and current.stage == "clitic"

    def next(self, context, current, rng):
        affix = syntax.new_affix(context.world, context.code, current, context.group.id, context.tick)
        if affix is None:
            return None
        return Construction(current.function, "synthetic", current.source, exponent=affix)


class Exaptation(SyntacticChange):
    """Zbytková koncovka dostane novou funkci (Lass 1990).

    Koncovka funkce, jejíž roli už nese něco jiného (pád vedle pevného
    slovosledu), ještě zní, ale nic neznamená. Mluvčí ji mohou přečíst jako
    vyjádření funkce téže třídy slov, kterou jazyk dosud nevyjadřoval.
    Které funkce si mohou koncovku vzít, říká katalog (``donors``).
    """

    site_column = COL_SYNTAX + 3
    kind, template, base_rate = "exaptation", "inflection", 0.02

    def _donors(self, context: InnovationContext, function: str) -> list[tuple[str, str]]:
        functions = catalog_for(context.world)
        found = []
        for donor in functions[function].donors:
            if functions[donor].word_class != functions[function].word_class:
                continue
            if not syntax.compensated(context.world, context.group.id, donor):
                continue
            exponent = syntax.residual_exponent(context.world, context.code, functions[donor])
            if exponent is not None:
                found.append((donor, exponent))
        return found

    def applies(self, context, current):
        return current.kind == "zero" and bool(self._donors(context, current.function))

    def next(self, context, current, rng):
        donors = self._donors(context, current.function)
        if not donors:
            return None
        donor, exponent = donors[int(rng.integers(len(donors)))]
        return Construction(current.function, "synthetic", exponent=exponent, donor=donor)


class NegationReinforcement(SyntacticChange):
    """Zeslabený zápor se posílí dalším slovem (*ne → ne … pas*), Jespersen."""

    site_column = COL_SYNTAX + 5
    kind, template, base_rate = "negation_reinforcement", "negation", 0.03

    def applies(self, context, current):
        return current.kind == "pre" and bool(_sources(context, current.function))

    def next(self, context, current, rng):
        sources = [concept for concept in _sources(context, current.function) if concept != current.source]
        if not sources:
            return None
        return Construction(current.function, "embraced", current.source, reinforcer=_pick(sources, rng))


class NegationReduction(SyntacticChange):
    """Původní záporka odpadne a zápor nese zesilovač (*ne … pas → pas*)."""

    site_column = COL_SYNTAX + 6
    kind, template, base_rate = "negation_reduction", "negation", 0.03

    def applies(self, context, current):
        return current.kind == "embraced"

    def next(self, context, current, rng):
        return Construction(current.function, "post", current.reinforcer)


class NegationRenewal(SyntacticChange):
    """Zesilovač se stane obyčejnou záporkou před slovesem: cyklus začíná znovu."""

    site_column = COL_SYNTAX + 7
    kind, template, base_rate = "negation_renewal", "negation", 0.01

    def applies(self, context, current):
        return current.kind == "post"

    def next(self, context, current, rng):
        return Construction(current.function, "pre", current.source)


class OrderFixation(SyntacticChange):
    """Volný slovosled se ustálí; SOV a SVO jsou v jazycích světa zhruba stejně časté."""

    site_column = COL_SYNTAX + 8
    kind, template, base_rate = "order_fixation", "order", 0.03

    def applies(self, context, current):
        return current.kind == "free" and bool(catalog_for(context.world)[current.function].orders)

    def next(self, context, current, rng):
        orders = catalog_for(context.world)[current.function].orders
        return Construction(current.function, "fixed", order=_pick(orders, rng))


class OrderRelaxation(SyntacticChange):
    """Pevný slovosled se uvolní (vzácné; jen když pád role spolehlivě nese)."""

    site_column = COL_SYNTAX + 9
    kind, template, base_rate = "order_relaxation", "order", 0.01

    def applies(self, context, current):
        return current.kind == "fixed"

    def next(self, context, current, rng):
        return Construction(current.function, "free")


class CategoryLoss(SyntacticChange):
    """Zánik kategorie: výraz funkce se přestane užívat a funkce je ``zero``.

    Gramatikalizace je jednosměrná pro výraz (slovo → přiklonka → koncovka),
    kategorie ale cyklí: koncovka nakonec zmizí a místo otevře novému opisu
    (Hopper & Traugott 2003). Doložené cesty k ``zero``:

    - eroze bez obnovy: koncovka splývá s citačním tvarem (ztráta pádů
      v angličtině a románských jménech);
    - převzetí funkce: roli nese pevný slovosled (``compensates``);
    - kontakt: dospělí L2 mluvčí vázané výrazy vypouštějí (Bentz & Winter
      2013; afrikánština, kreoly).

    Návrh nepotřebuje žádný práh. Vypuštění koncovky navrhují mluvčí tím
    častěji, čím je koncovka nespolehlivější (``weakness``) a čím víc je
    ve skupině L2 mluvčích; o osudu návrhu rozhoduje selekce
    (`Expressivity` proti `Learnability` a `Economy`). Volný opis lze
    vypustit vždy se základní mírou: slovo navíc stojí a funkci s nízkou
    potřebou nebo silným kontextem selekce nedrží.
    """

    site_column = COL_SYNTAX + 4
    kind, template, base_rate = "category_loss", "inflection", 0.02

    def _pressure(self, context: InnovationContext, current: Construction) -> float:
        """Kolik důvodů k vypuštění výrazu mluvčí mají (násobek ``base_rate``)."""
        if current.kind == "periphrastic" and current.stage == "free":
            return 1.0
        if not current.bound:
            return 0.0
        unreliable = 0.0
        if current.kind == "synthetic":
            unreliable = syntax.weakness(context.world, context.code, current.function)
        return unreliable + context.world.params.category_loss_l2_boost * context.code.l2_share

    def applies(self, context: InnovationContext, current: Construction) -> bool:
        return self._pressure(context, current) > 0.0

    def rate(self, context: InnovationContext, site: str) -> float:
        return self.rates(context, [site])[0]

    def rates(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        """Míry míst: z indexu míst světa pro místa změny, jinak z konstrukcí (:meth:`_rates_reference`)."""
        if native_column(self) is not None:
            found, rates = self._found(context)
            if sites is found or list(sites) == found:
                return rates
        return self._rates_reference(context, sites)

    def _rates_reference(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        """Míry míst naráz: z konstrukcí složí pole a spočte je ``phases.category_loss_rates``."""
        currents = [syntax.dominant(context.world, context.group.id, site.split(":", 1)[1]) for site in sites]
        present = np.array([current is not None for current in currents], dtype=bool)
        free = np.zeros(len(sites), dtype=bool)
        bound = np.zeros(len(sites), dtype=bool)
        synthetic = np.zeros(len(sites), dtype=bool)
        weakness = np.zeros(len(sites), dtype=np.float64)
        for index, current in enumerate(currents):
            if current is None:
                continue
            free[index] = current.kind == "periphrastic" and current.stage == "free"
            bound[index] = current.bound
            if current.kind == "synthetic" and not free[index] and bound[index]:
                synthetic[index] = True
                weakness[index] = syntax.weakness(context.world, context.code, current.function)
        rates = phases.category_loss_rates(
            self.base_rate, present, free, bound, synthetic, weakness,
            context.world.params.category_loss_l2_boost, context.code.l2_share,
        )
        return [float(rate) for rate in rates]

    def next(
        self, context: InnovationContext, current: Construction, rng: RandomSource
    ) -> Construction | None:
        return Construction(current.function, "zero")


SYNTACTIC_CHANGES: tuple[SyntacticChange, ...] = (
    Periphrasis(), Cliticization(), Affixation(), Exaptation(), CategoryLoss(),
    NegationReinforcement(), NegationReduction(), NegationRenewal(),
    OrderFixation(), OrderRelaxation(),
)

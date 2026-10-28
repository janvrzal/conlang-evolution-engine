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

from typing import ClassVar, Mapping, Sequence

import numpy as np

from cee.v2 import syntax
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.constructions import Construction, catalog
from cee.v2.pressures import Actuation, Conformity, Pressure
from cee.v2.pressures.syntactic import Ambiguity, Economy, Expressivity, Fusion
from cee.v2.repertoire import Origin, Variant

SYNTAX_PRESSURES: Mapping[type[Pressure], float] = {
    Expressivity: 1.0,
    Economy: 1.0,
    Fusion: 1.0,
    Ambiguity: 1.0,
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
        self, context: InnovationContext, current: Construction, rng: np.random.Generator
    ) -> Construction | None:
        raise NotImplementedError

    def applies(self, context: InnovationContext, current: Construction) -> bool:
        raise NotImplementedError

    def sites(self, context: InnovationContext) -> Sequence[str]:
        found = []
        for entry in syntax.functions(context.world, self.template):
            current = syntax.dominant(context.world, context.group.id, entry.id)
            if current is not None and self.applies(context, current):
                found.append(syntax.variable_id(entry.id))
        return found

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        current = syntax.dominant(context.world, context.group.id, site.split(":", 1)[1])
        if current is None:
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
    return [concept for concept in catalog()[function].sources if concept in dominant]


def _pick(options: Sequence[str], rng: np.random.Generator) -> str:
    return options[int(rng.integers(len(options)))]


class Periphrasis(SyntacticChange):
    """Opis: pomocné slovo + citační tvar (*mám napsáno*, *I have written*).

    Vzniká tam, kde funkci jazyk dosud nevyjadřoval vůbec (ukazovací zájmeno
    jako člen, *ille → le*), a tam, kde koncovka zeslábla (obnova, Hopper &
    Traugott 2003). Opis vedle neporušené koncovky nemá čím uspět, a tak ho
    změna ani nenavrhuje.
    """

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

    kind, template, base_rate = "cliticization", "inflection", 0.04

    def applies(self, context, current):
        return current.kind == "periphrastic" and current.stage == "free"

    def next(self, context, current, rng):
        return Construction(current.function, "periphrastic", current.source, "clitic")


class Affixation(SyntacticChange):
    """Přiklonka sroste se slovem v novou koncovku (*cantare habeo → chanterai*)."""

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

    kind, template, base_rate = "exaptation", "inflection", 0.02

    def _donors(self, context: InnovationContext, function: str) -> list[tuple[str, str]]:
        functions = catalog()
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

    kind, template, base_rate = "negation_reduction", "negation", 0.03

    def applies(self, context, current):
        return current.kind == "embraced"

    def next(self, context, current, rng):
        return Construction(current.function, "post", current.reinforcer)


class NegationRenewal(SyntacticChange):
    """Zesilovač se stane obyčejnou záporkou před slovesem: cyklus začíná znovu."""

    kind, template, base_rate = "negation_renewal", "negation", 0.01

    def applies(self, context, current):
        return current.kind == "post"

    def next(self, context, current, rng):
        return Construction(current.function, "pre", current.source)


class OrderFixation(SyntacticChange):
    """Volný slovosled se ustálí; SOV a SVO jsou v jazycích světa zhruba stejně časté."""

    kind, template, base_rate = "order_fixation", "order", 0.03

    def applies(self, context, current):
        return current.kind == "free" and bool(catalog()[current.function].orders)

    def next(self, context, current, rng):
        return Construction(current.function, "fixed", order=_pick(catalog()[current.function].orders, rng))


class OrderRelaxation(SyntacticChange):
    """Pevný slovosled se uvolní (vzácné; jen když pád role spolehlivě nese)."""

    kind, template, base_rate = "order_relaxation", "order", 0.01

    def applies(self, context, current):
        return current.kind == "fixed"

    def next(self, context, current, rng):
        return Construction(current.function, "free")


SYNTACTIC_CHANGES: tuple[SyntacticChange, ...] = (
    Periphrasis(), Cliticization(), Affixation(), Exaptation(), NegationReinforcement(),
    NegationReduction(), NegationRenewal(), OrderFixation(), OrderRelaxation(),
)

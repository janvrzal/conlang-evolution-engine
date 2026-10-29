"""Lexikální změny (iterace 3, oblast D; milník M3b).

Nové slovo pro pojem má vždy doložitelný původ:

- **posun významu**: slovo jiného pojmu se začne užívat i pro tento
  (*tongue → language*); dokladem jsou posuny a kolexifikace v grafu pojmů,
- **konverze**: totéž přes hranici slovního druhu (M4),
- **odvození**: kořen příbuzného pojmu + odvozovací přípona,
- **složenina**: dva kořeny podle receptu (*sky + water → rain*),
- **opis za tabu**: náhrada tabuizovaného slova příbuzným výrazem,
- **kontaminace**: smíšení tvarů dvou příbuzných slov,
- **zpětné tvoření**: z odvozeného slova se odtrhne přípona,
- **expresivní tvoření**: nový kořen podle fonotaktiky jazyka (vzácné).

O tom, které nové slovo se prosadí, rozhodují lexikální tlaky
(``pressures/lexical.py``), ne náhodné číslo jako v M1.
"""

from __future__ import annotations

import math
from abc import abstractmethod
from typing import Mapping, Sequence, cast

import numpy as np

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.lexicon import Morpheme
from cee.v2.language.protoforms import coin
from cee.v2.language.segments import Form
from cee.v2.language.semantic_index import SemanticSitesIndex
from cee.v2.pressures import Appeal, Conformity, Pressure
from cee.v2.pressures.lexical import (
    Entrenchment,
    LexicalActuation,
    LexicalClarity,
    Motivation,
    Taboo,
)
from cee.v2.repertoire import Origin, Variant
from cee.v2.rng import stable_id

LEXICAL_PRESSURES: Mapping[type[Pressure], float] = {
    LexicalClarity: 1.0,
    Entrenchment: 1.0,
    Motivation: 1.0,
    Taboo: 1.0,
    LexicalActuation: 1.0,
    Conformity: 0.1,
}


class LexicalCoinage(Change):
    """Nový kořen pro existující pojem.

    Ve světě bez hláskových tvarů (M1) zastupuje všechny cesty vzniku slova
    a jeho výhodu nese náhodné ``appeal``. S tvary (M3b) je to expresivní
    tvoření: kořen ze slabik jazyka, vzácný a bez náhodné výhody — jeho osud
    řeší lexikální tlaky.
    """

    kind = "lexical_coinage"
    target = "lexical"
    pressures = {Appeal: 1.0, Conformity: 0.1, **LEXICAL_PRESSURES}
    # Nová slova vymýšlejí dospělí, tempo se proto řídí kalendářním časem.
    base_rate = 4e-4
    rate_basis = "year"

    appeal_mean = -0.05
    appeal_sd = 0.15
    #: Ve světě s významy je expresivní tvoření jen malou částí obměny.
    expressive_share = 0.1

    def rate_scale(self, context: InnovationContext) -> float:
        return self.expressive_share if context.world.semantics is not None else 1.0

    def total_rate(self, context: InnovationContext) -> float:
        count = len(context.code.repertoire.variable_ids_of("lexical"))
        if count == 0:
            return 0.0
        return float(self.base_rate * count * self.rate_scale(context))

    def sites(self, context: InnovationContext) -> Sequence[str]:
        return context.code.repertoire.variable_ids_of("lexical")

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        parts = (context.group.id, context.code.id, site, context.tick, index)
        payload: dict[str, object] = {"lexeme": stable_id("lexeme", self.kind, *parts)}
        world = context.world
        if world.table is None:
            payload["appeal"] = float(rng.normal(self.appeal_mean, self.appeal_sd))
        else:
            form = _coin_form(context, rng)
            if form is None:
                return None
            payload.update(
                morpheme=_new_root(context, site, form, self.kind, parts), origin="coinage"
            )
        return Variant(
            id=stable_id("variant", self.kind, *parts),
            variable=site,
            payload=payload,
            origin=Origin(self.kind, context.tick, context.year, context.group.id),
        )


# --- pomocné ------------------------------------------------------------


def concept_of(site: str) -> str:
    return site.split(":", 1)[1]


def dominant_root(context: InnovationContext, concept: str) -> str | None:
    return context.code.phonology.dominant.get(concept)


def _roots(context: InnovationContext) -> dict[str, Form]:
    world, code = context.world, context.code
    return {
        root: world.form_of(code, root) for root in sorted(set(code.phonology.dominant.values()))
    }


def _coin_form(context: InnovationContext, rng: np.random.Generator) -> Form | None:
    assert context.world.table is not None
    roots = _roots(context)
    return coin(context.world.table, roots, rng, set(roots.values()))


def _new_root(
    context: InnovationContext, site: str, form: Form, kind: str, parts: tuple,
    sources: tuple[str, ...] = (), base: str | None = None,
) -> str:
    """Zaregistruje kořen nového slova; frekvenci a třídu má podle pojmu."""
    world = context.world
    concept = concept_of(site)
    morpheme = Morpheme(
        id=stable_id("morpheme", kind, *parts),
        meaning=concept,
        form=form,
        frequency=world.concept_frequency(concept),
        word_class=world.concept_classes.get(concept),
        origin_group=context.group.id,
        origin_tick=context.tick,
        language=context.code.language,
        etymology=kind,
        sources=sources,
        base=base,
    )
    world.morphemes[morpheme.id] = morpheme
    return morpheme.id


def _compatible(context: InnovationContext, first: str, second: str) -> bool:
    """Posun významu mezi slovními druhy (sloveso → jméno) by potřeboval konverzi."""
    classes = context.world.concept_classes
    return classes.get(first) == classes.get(second)


class SemanticChange(Change):
    """Rodič lexikálních změn řízených grafem pojmů."""

    target = "lexical"
    rate_basis = "year"
    pressures = LEXICAL_PRESSURES

    @abstractmethod
    def options(self, context: InnovationContext, concept: str) -> list[tuple[float, dict[str, object]]]:
        """(váha, podklad varianty) pro všechny doložené cesty k pojmu."""

    @abstractmethod
    def build(
        self, context: InnovationContext, site: str, option: dict[str, object], parts: tuple,
        rng: np.random.Generator,
    ) -> dict[str, object] | None:
        """Payload nové varianty, nebo ``None``, když cesta dnes nejde."""

    def _index(self, context: InnovationContext) -> SemanticSitesIndex:
        state = context.code.phonology
        key = ("semantic-index", self.kind)
        cached = state.cache.get(key)
        index = SemanticSitesIndex() if cached is None else cast(SemanticSitesIndex, cached[1])
        index.sync(context, self)
        state.cache[key] = (state.lexicon_version, index)
        return index

    def _sites(self, context: InnovationContext) -> dict[str, list[tuple[float, dict[str, object]]]]:
        return self._index(context).found

    def _sites_reference(self, context: InnovationContext) -> dict[str, list[tuple[float, dict[str, object]]]]:
        """Původní úplné sestavení, nezávislé na produkční keši míst."""
        state = context.code.phonology
        key = ("lexical-sites-reference", self.kind)
        cached = state.cache.get(key)
        # Možnosti závisí jen na slovní zásobě (dominantní kořeny), ne na tvarech.
        if cached is not None and cached[0] == state.lexicon_version:
            return cast(dict[str, list[tuple[float, dict[str, object]]]], cached[1])
        found = {}
        for site in context.code.repertoire.variable_ids_of("lexical"):
            options = self.options(context, concept_of(site))
            if options:
                found[site] = options
        state.cache[key] = (state.lexicon_version, found)
        return found

    def sites(self, context: InnovationContext) -> Sequence[str]:
        if context.world.semantics is None or context.world.table is None:
            return ()
        index = self._index(context)
        index.ensure_ready()
        return index.sorted_sites

    def rate(self, context: InnovationContext, site: str) -> float:
        return self._index(context).site_rates[site]

    def rates(self, context: InnovationContext, sites: Sequence[str]) -> list[float]:
        if context.world.semantics is None or context.world.table is None:
            return []
        index = self._index(context)
        index.ensure_ready()
        if sites is index.sorted_sites or sites == index.sorted_sites:
            return index.rates_array.tolist()
        return [self.rate(context, site) for site in sites]

    def total_rate(self, context: InnovationContext) -> float:
        if context.world.semantics is None or context.world.table is None:
            return 0.0
        index = self._index(context)
        index.ensure_ready()
        return index._total

    def weighted_sites(
        self, context: InnovationContext
    ) -> tuple[Sequence[str], np.ndarray | None]:
        if context.world.semantics is None or context.world.table is None:
            return (), None
        index = self._index(context)
        index.ensure_ready()
        if not index.sorted_sites or index._total <= 0.0:
            return (), None
        if index._weights is None:
            index._weights = index.rates_array / index._total
        return index.sorted_sites, index._weights

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        options = self._sites(context)[site]
        weights = np.array([weight for weight, _ in options])
        option = options[int(rng.choice(len(options), p=weights / weights.sum()))][1]
        parts = (context.group.id, site, context.tick, index)
        payload = self.build(context, site, option, parts, rng)
        if payload is None:
            return None
        return Variant(
            id=stable_id("variant", self.kind, *parts),
            variable=site,
            payload=payload,
            origin=Origin(self.kind, context.tick, context.year, context.group.id),
        )


class SemanticShift(SemanticChange):
    """Slovo příbuzného pojmu se začne užívat i pro tento pojem (polysémie)."""

    kind = "semantic_shift"
    base_rate = 4e-4

    def options(self, context, concept):
        assert context.world.semantics is not None
        current = dominant_root(context, concept)
        found = []
        for relation in context.world.semantics.into(concept):
            source = dominant_root(context, relation.source)
            if source is None or source == current or not _compatible(context, relation.source, concept):
                continue
            if relation.shift_weight > 0:
                found.append((relation.shift_weight, {"root": source, "from": relation.source}))
        return found

    def build(self, context, site, option, parts, rng):
        root = option["root"]
        # Stejný posun téhož kořene ve dvou skupinách je tatáž varianta.
        return {"morpheme": root, "origin": "shift", "from": [option["from"]],
                "lexeme": stable_id("lexeme", "shift", root, site)}

    def propose(self, context, site, rng, index):
        variant = super().propose(context, site, rng, index)
        if variant is None:
            return None
        shared = stable_id("variant", self.kind, site, variant.payload["morpheme"])
        return Variant(shared, variant.variable, variant.payload, variant.origin)


class Conversion(SemanticChange):
    """Slovo přejde do jiného slovního druhu beze změny tvaru (*a run → to run*).

    Posun významu mezi slovesem a jménem by jinak potřeboval odvození;
    konverze vezme tvar kořene a dá mu třídu cílového pojmu.
    """

    kind = "conversion"
    base_rate = 1.5e-4

    def options(self, context, concept):
        assert context.world.semantics is not None
        found = []
        for relation in context.world.semantics.into(concept):
            source = dominant_root(context, relation.source)
            if source is None or _compatible(context, relation.source, concept):
                continue
            if relation.polysemy >= 1:
                found.append((math.log1p(relation.polysemy), {"root": source, "from": relation.source}))
        return found

    def build(self, context, site, option, parts, rng):
        form = context.world.form_of(context.code, str(option["root"]))
        morpheme = _new_root(context, site, form, self.kind, parts, sources=(str(option["from"]),))
        return {"morpheme": morpheme, "origin": "conversion", "from": [option["from"]]}


class Derivation(SemanticChange):
    """Kořen příbuzného pojmu + odvozovací přípona (*péct → pekař*)."""

    kind = "derivation"
    base_rate = 4e-4

    def options(self, context, concept):
        assert context.world.semantics is not None
        if not context.world.derivational_suffix:
            return []
        found = []
        for relation in context.world.semantics.into(concept):
            source = dominant_root(context, relation.source)
            if source is not None and relation.derivation_weight > 0:
                found.append((relation.derivation_weight, {"root": source, "from": relation.source}))
        return found

    def build(self, context, site, option, parts, rng):
        base = context.world.form_of(context.code, str(option["root"]))
        form = base + context.world.derivational_suffix
        morpheme = _new_root(context, site, form, self.kind, parts,
                             sources=(str(option["from"]),), base=str(option["root"]))
        return {"morpheme": morpheme, "origin": "derivation", "from": [option["from"]]}


class Compounding(SemanticChange):
    """Složenina ze dvou kořenů podle receptu (*sky + water → rain*)."""

    kind = "compounding"
    base_rate = 3e-4

    def options(self, context, concept):
        assert context.world.semantics is not None
        found = []
        for left, right in context.world.semantics.compounds.get(concept, ()):
            first, second = dominant_root(context, left), dominant_root(context, right)
            if first is not None and second is not None:
                found.append((1.0, {"first": first, "second": second, "from": [left, right]}))
        return found

    def build(self, context, site, option, parts, rng):
        world, code = context.world, context.code
        # Pořadí složek podle receptu (např. sky + water pro „déšť“).
        form = world.form_of(code, str(option["first"])) + world.form_of(code, str(option["second"]))
        if len(form) > 10:
            return None  # příliš dlouhá složenina se v řeči neujme
        sources = tuple(str(item) for item in cast(list[str], option["from"]))
        return {"morpheme": _new_root(context, site, form, self.kind, parts, sources=sources),
                "origin": "compound", "from": list(sources)}


class TabooReplacement(SemanticChange):
    """Tabuizovaný pojem dostane opis: slovo příbuzného pojmu nebo složeninu."""

    kind = "taboo_replacement"
    base_rate = 1e-3

    def options(self, context, concept):
        if concept not in context.group.taboo:
            return []
        assert context.world.semantics is not None
        current = dominant_root(context, concept)
        found = []
        for relation in context.world.semantics.into(concept):
            source = dominant_root(context, relation.source)
            if source is not None and source != current:
                found.append((1.0, {"root": source, "from": relation.source}))
        if not found:
            found.append((1.0, {"root": None, "from": None}))
        return found

    def build(self, context, site, option, parts, rng):
        if option["root"] is not None:
            return {"morpheme": option["root"], "origin": "circumlocution", "from": [option["from"]]}
        form = _coin_form(context, rng)
        if form is None:
            return None
        return {"morpheme": _new_root(context, site, form, self.kind, parts), "origin": "circumlocution",
                "from": []}


class Contamination(SemanticChange):
    """Smíšení tvarů dvou příbuzných slov (začátek jednoho, konec druhého)."""

    kind = "contamination"
    base_rate = 2e-5

    def options(self, context, concept):
        assert context.world.semantics is not None
        current = dominant_root(context, concept)
        if current is None:
            return []
        found = []
        for relation in context.world.semantics.into(concept):
            other = dominant_root(context, relation.source)
            if other is not None and other != current and relation.colexification >= 20:
                found.append((1.0, {"root": current, "other": other, "from": relation.source}))
        return found

    def build(self, context, site, option, parts, rng):
        world, code = context.world, context.code
        first, second = world.form_of(code, str(option["root"])), world.form_of(code, str(option["other"]))
        form = first[: (len(first) + 1) // 2] + second[len(second) // 2 :]
        if form in (first, second) or len(form) < 2:
            return None
        return {"morpheme": _new_root(context, site, form, self.kind, parts), "origin": "contamination",
                "from": [concept_of(site), option["from"]]}


class BackFormation(SemanticChange):
    """Z odvozeného slova se odtrhne přípona a vznikne slovo pro základ.

    Nabízí se, když základní pojem dnes vyjadřuje jiné slovo než to, ze
    kterého odvozenina vznikla (*editor* existuje, *edit* chybí).
    """

    kind = "back_formation"
    base_rate = 5e-5

    def options(self, context, concept):
        world = context.world
        found = []
        for other, root in _derivations(context).get(concept, ()):
            if other != concept and dominant_root(context, concept) != world.morphemes[root].base:
                found.append((1.0, {"root": root, "from": other}))
        return found

    def build(self, context, site, option, parts, rng):
        world = context.world
        form = world.form_of(context.code, str(option["root"]))
        suffix = world.derivational_suffix
        if not suffix or len(form) <= len(suffix) + 1 or form[-len(suffix):] != suffix:
            return None
        return {"morpheme": _new_root(context, site, form[: -len(suffix)], self.kind, parts),
                "origin": "back_formation", "from": [option["from"]]}


def _derivations(context: InnovationContext) -> dict[str, list[tuple[str, str]]]:
    """Základní pojem → (pojem, kořen) odvozenin z něj, seřazeno podle pojmu."""
    state = context.code.phonology
    cached = state.cache.get("derivations")
    if cached is not None and cached[0] == state.lexicon_version:
        return cast(dict[str, list[tuple[str, str]]], cached[1])
    index: dict[str, list[tuple[str, str]]] = {}
    for other, root in sorted(state.dominant.items()):
        morpheme = context.world.morphemes[root]
        if morpheme.etymology == "derivation" and len(morpheme.sources) == 1:
            index.setdefault(morpheme.sources[0], []).append((other, root))
    state.cache["derivations"] = (state.lexicon_version, index)
    return index


LEXICAL_CHANGES: tuple[Change, ...] = (
    LexicalCoinage(), SemanticShift(), Conversion(), Derivation(), Compounding(),
    TabooReplacement(), Contamination(), BackFormation(),
)

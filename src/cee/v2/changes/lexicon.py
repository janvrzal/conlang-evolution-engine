"""Lexikální změny (iterace 3, oblast D)."""

from __future__ import annotations

from typing import Sequence

import numpy as np

from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.lexicon import Morpheme
from cee.v2.language.protoforms import coin
from cee.v2.pressures import Appeal, Conformity
from cee.v2.repertoire import Origin, Variant
from cee.v2.rng import stable_id


class LexicalCoinage(Change):
    """Nové slovo pro existující pojem.

    V M1 zastupuje všechny cesty vzniku slova (expresivní tvoření, opis,
    posun významu), protože lexém ještě nemá hláskovou ani významovou
    strukturu. Vlastní výhodu nového slova nese ``appeal``: většina inovací
    je téměř neutrální a o jejich osudu rozhoduje hlavně drift a síť, jen
    menšina má výraznou výhodu. Při silně výhodných inovacích by každá
    úspěšná změna prošla celým kontinuem a dialekty by nevznikaly.
    Výchozí hodnoty dávají v S1 retenci kolem 80 % za tisíciletí; kalibrují
    se v M7. Výhoda je zatím stejná ve všech skupinách, takže úspěšná změna
    časem projde celým kontinuem; místní výhodu přinese až tlak identity.
    """

    kind = "lexical_coinage"
    target = "lexical"
    pressures = {Appeal: 1.0, Conformity: 0.1}
    # Nová slova vymýšlejí dospělí, tempo se proto řídí kalendářním časem.
    base_rate = 4e-4
    rate_basis = "year"

    appeal_mean = -0.05
    appeal_sd = 0.15

    def _coin(
        self, context: InnovationContext, site: str, rng: np.random.Generator, parts: tuple
    ) -> str | None:
        """Morfém nového slova složený podle fonotaktiky jazyka (M2)."""
        world, code = context.world, context.code
        assert world.table is not None
        vocabulary = {
            morpheme: world.form_of(code, morpheme) for morpheme in code.phonology.vocabulary
        }
        form = coin(world.table, vocabulary, rng, set(vocabulary.values()))
        if form is None:
            return None
        concept = site.split(":", 1)[1]
        incumbent = [
            world.morphemes[morpheme].frequency for morpheme in sorted(code.phonology.vocabulary)
            if world.morphemes[morpheme].meaning == concept
        ]
        morpheme = Morpheme(
            id=stable_id("morpheme", self.kind, *parts),
            meaning=concept,
            form=form,
            frequency=incumbent[0] if incumbent else 0.3,
            origin_group=context.group.id,
            origin_tick=context.tick,
        )
        world.morphemes[morpheme.id] = morpheme
        return morpheme.id

    def sites(self, context: InnovationContext) -> Sequence[str]:
        return context.code.repertoire.variable_ids_of("lexical")

    def propose(
        self, context: InnovationContext, site: str, rng: np.random.Generator, index: int
    ) -> Variant | None:
        parts = (context.group.id, context.code.id, site, context.tick, index)
        payload: dict[str, object] = {
            "lexeme": stable_id("lexeme", self.kind, *parts),
            "appeal": float(rng.normal(self.appeal_mean, self.appeal_sd)),
        }
        world = context.world
        if world.table is not None:
            morpheme = self._coin(context, site, rng, parts)
            if morpheme is None:
                return None
            payload["morpheme"] = morpheme
        return Variant(
            id=stable_id("variant", self.kind, *parts),
            variable=site,
            payload=payload,
            origin=Origin(
                change=self.kind,
                tick=context.tick,
                year=context.year,
                group=context.group.id,
            ),
        )

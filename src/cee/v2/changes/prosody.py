"""Prozodické změny (krok D2): posun přízvuku a síla přízvuku.

Změny pracují nad proměnnými ``prosody:stress_rule`` a ``prosody:stress_strength``.
"""

from __future__ import annotations

from typing import Literal, Mapping, Sequence

import numpy as np

from cee.v2 import prosody
from cee.v2.changes.base import Change, InnovationContext
from cee.v2.language.processes import StressRule
from cee.v2.pressures import Actuation, Conformity, Pressure
from cee.v2.repertoire import Origin, Variant
from cee.v2.rng import RandomSource

PROSODY_PRESSURES: Mapping[type[Pressure], float] = {
    Conformity: 0.1,
    Actuation: 1.0,
}

#: Doložené směry posunu přízvuku s priory z literatury (Hyman 1977, 2014; Hayes 1995).
#: Posun na finálu záměrně chybí: oxytone vzniká redukcí/apokopou, ne pravidlem posunu.
STRESS_SHIFT_PRIORS: dict[StressRule, dict[StressRule, float]] = {
    "penult": {"initial": 0.7, "antepenult": 0.3},
    "initial": {"penult": 0.3, "second": 0.1},
    "antepenult": {"penult": 0.6, "initial": 0.4},
    "second": {"initial": 0.8, "penult": 0.2},
    "final": {"penult": 0.7, "initial": 0.3},
}


class StressShift(Change):
    """Posun pravidla přízvuku.

    Navrhuje se s priory doloženými z historického vývoje jazyků.
    Přízvuk na finále nevzniká pravidlem posunu, ale apokopou post-tonických slabik.
    """

    kind = "stress_shift"
    target = "prosody"
    rate_basis = "generation"
    base_rate = 0.02
    pressures = PROSODY_PRESSURES

    def sites(self, context: InnovationContext) -> Sequence[str]:
        var_id = prosody.stress_rule_variable_id()
        if var_id in context.world.variables:
            return (var_id,)
        return ()

    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        current = prosody.dominant_rule(context.world, context.group.id)
        targets = STRESS_SHIFT_PRIORS.get(current)
        if not targets:
            return None
        rules = list(targets.keys())
        probs = np.array([targets[r] for r in rules], dtype=np.float64)
        probs /= probs.sum()
        chosen_rule = rules[int(rng.choice(len(rules), p=probs))]
        origin = Origin(self.kind, context.tick, context.year, context.group.id)
        _, variant = prosody.register_stress_rule(context.world, chosen_rule, origin)
        return variant


class StressStrengthChange(Change):
    """Změna síly přízvuku (slabičné vs. přízvukové časování).

    Přechod mezi hodnotami weak a strong se zpětnou cestou (Dauer 1983, Schiering 2010).
    """

    kind = "stress_strength"
    target = "prosody"
    rate_basis = "generation"
    base_rate = 0.02
    pressures = PROSODY_PRESSURES

    def sites(self, context: InnovationContext) -> Sequence[str]:
        var_id = prosody.stress_strength_variable_id()
        if var_id in context.world.variables:
            return (var_id,)
        return ()

    def propose(
        self, context: InnovationContext, site: str, rng: RandomSource, index: int
    ) -> Variant | None:
        current = prosody.dominant_strength(context.world, context.group.id)
        target_strength: Literal["weak", "strong"] = "strong" if current == "weak" else "weak"
        origin = Origin(self.kind, context.tick, context.year, context.group.id)
        _, variant = prosody.register_stress_strength(context.world, target_strength, origin)
        return variant


PROSODY_CHANGES: tuple[Change, ...] = (StressShift(), StressStrengthChange())

__all__ = [
    "PROSODY_CHANGES",
    "StressShift",
    "StressStrengthChange",
]

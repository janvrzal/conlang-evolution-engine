//! Prozodické změny: posun přízvuku a síla přízvuku (zrcadlo `changes/prosody.py`).
//!
//! Místem změny je jediná prozodická proměnná, pokud ji svět sleduje; míra je jednotná.

use crate::changes::{Change, InnovationContext, NewVariant, Sites, PROSODY_PRESSURES};
use crate::ids::VariableId;
use crate::model::code::{StressRule, StressStrength};
use crate::model::repertoire::{Origin, VariableKind};
use crate::prosody;
use crate::rng::Stream;
use crate::world::World;

/// Doložené směry posunu přízvuku s priory z literatury (Hyman 1977, 2014; Hayes 1995).
/// Posun na finálu záměrně chybí: oxytone vzniká redukcí a apokopou, ne pravidlem posunu.
/// Váhový přízvuk (`Weight`) vzniká z předposledního a třetího od konce (dok. 30).
const STRESS_SHIFT_PRIORS: [(StressRule, &[(StressRule, f64)]); 6] = [
    (
        StressRule::Penult,
        &[
            (StressRule::Initial, 0.7),
            (StressRule::Antepenult, 0.3),
            (StressRule::Weight, 0.2),
        ],
    ),
    (
        StressRule::Initial,
        &[(StressRule::Penult, 0.3), (StressRule::Second, 0.1)],
    ),
    (
        StressRule::Antepenult,
        &[
            (StressRule::Penult, 0.6),
            (StressRule::Initial, 0.4),
            (StressRule::Weight, 0.3),
        ],
    ),
    (
        StressRule::Second,
        &[(StressRule::Initial, 0.8), (StressRule::Penult, 0.2)],
    ),
    (
        StressRule::Final,
        &[(StressRule::Penult, 0.7), (StressRule::Initial, 0.3)],
    ),
    // Váhový přízvuk se ztrátou délky samohlásek ustálí na předposlední slabice (latina →
    // románské jazyky), jinde na první (Hayes 1995; dok. 30).
    (
        StressRule::Weight,
        &[
            (StressRule::Penult, 0.6),
            (StressRule::Initial, 0.3),
            (StressRule::Antepenult, 0.1),
        ],
    ),
];

const BASE_RATE: f64 = 0.02;

fn origin(kind: &str, ctx: &InnovationContext) -> Origin {
    Origin {
        change: Some(kind.to_owned()),
        tick: ctx.tick,
        year: ctx.year,
        group: ctx.group,
        parent: crate::ids::VariantId::NONE,
    }
}

/// Zaregistrovaná varianta jako návrh (obsah a původ první registrace zůstává).
fn proposed(world: &World, variable: VariableId, variant: crate::ids::VariantId) -> NewVariant {
    NewVariant {
        name: world.registry.variants.name(variant.0).to_owned(),
        variable,
        payload: world.variants.payload[variant.index()].clone(),
        origin: world.variants.origin[variant.index()].clone(),
    }
}

fn sites_of(variable: Option<VariableId>) -> Sites {
    Sites {
        sites: variable.into_iter().collect(),
        weights: None,
    }
}

fn rate_of(variable: Option<VariableId>) -> f64 {
    if variable.is_some() {
        BASE_RATE
    } else {
        0.0
    }
}

/// Posun pravidla přízvuku s priory doloženými z historického vývoje jazyků.
pub struct StressShift;

impl Change for StressShift {
    fn kind(&self) -> &'static str {
        "stress_shift"
    }

    fn rate_basis_generation(&self) -> bool {
        true
    }

    fn target(&self) -> VariableKind {
        VariableKind::Prosody
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &PROSODY_PRESSURES
    }

    fn weighted_sites(&self, world: &World, _ctx: &InnovationContext) -> Sites {
        sites_of(prosody::stress_rule_variable(world))
    }

    fn rate_sum(&self, world: &World, _ctx: &InnovationContext) -> f64 {
        rate_of(prosody::stress_rule_variable(world))
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        _site: VariableId,
        rng: &mut Stream,
        _index: usize,
    ) -> Option<NewVariant> {
        let current = prosody::dominant_rule(world, ctx.group);
        let targets = STRESS_SHIFT_PRIORS
            .iter()
            .find(|(rule, _)| *rule == current)?
            .1;
        let weights: Vec<f64> = targets.iter().map(|t| t.1).collect();
        let chosen = targets[rng.choice(&weights).ok()?].0;
        let (variable, variant) =
            world.register_prosody("stress_rule", chosen.name(), &origin(self.kind(), ctx));
        Some(proposed(world, variable, variant))
    }
}

/// Změna síly přízvuku (slabičné a přízvukové časování; Dauer 1983, Schiering 2010).
pub struct StressStrengthChange;

impl Change for StressStrengthChange {
    fn kind(&self) -> &'static str {
        "stress_strength"
    }

    fn rate_basis_generation(&self) -> bool {
        true
    }

    fn target(&self) -> VariableKind {
        VariableKind::Prosody
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &PROSODY_PRESSURES
    }

    fn weighted_sites(&self, world: &World, _ctx: &InnovationContext) -> Sites {
        sites_of(prosody::stress_strength_variable(world))
    }

    fn rate_sum(&self, world: &World, _ctx: &InnovationContext) -> f64 {
        rate_of(prosody::stress_strength_variable(world))
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        _site: VariableId,
        _rng: &mut Stream,
        _index: usize,
    ) -> Option<NewVariant> {
        let target = match prosody::dominant_strength(world, ctx.group) {
            StressStrength::Weak => StressStrength::Strong,
            StressStrength::Strong => StressStrength::Weak,
        };
        let (variable, variant) =
            world.register_prosody("stress_strength", target.name(), &origin(self.kind(), ctx));
        Some(proposed(world, variable, variant))
    }
}

/// Prozodické změny v kanonickém pořadí.
pub fn changes() -> Vec<Box<dyn Change>> {
    vec![Box::new(StressShift), Box::new(StressStrengthChange)]
}

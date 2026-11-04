//! Morfologické změny: analogie nad tvary slov (zrcadlo `changes/morphology.py`).
//!
//! Místem změny je jeden tvar slova (kandidáti jsou v `morphology`, seřazení podle jména
//! formové proměnné). Proměnná analogie vzniká až při návrhu (`morphology::register`), proto
//! jsou **místa pořadová čísla kandidátů** (`VariableId(i)`) a po návrhu platí
//! `NewVariant::variable`; fáze inovací s tím počítá.

use std::sync::Arc;

use crate::changes::{Change, InnovationContext, NewVariant, Sites, MORPH_PRESSURES};
use crate::ids::{GroupId, VariableId, VariantId};
use crate::model::lexicon::FormChange;
use crate::model::repertoire::{Origin, VariableKind};
use crate::morphology::{self, FormSites};
use crate::rng::Stream;
use crate::world::World;

/// Druh analogické změny.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Analogy {
    Leveling,
    Extension,
    Rebracketing,
}

pub struct AnalogicalChange {
    which: Analogy,
}

impl AnalogicalChange {
    pub fn new(which: Analogy) -> AnalogicalChange {
        AnalogicalChange { which }
    }

    fn base_rate(&self) -> f64 {
        match self.which {
            Analogy::Leveling | Analogy::Extension => 0.004,
            // Sporadický jev: jednotky případů na jazyk za tisíciletí.
            Analogy::Rebracketing => 0.0002,
        }
    }

    /// Násobek míry: regularizace zesiluje druhojazyční mluvčí, reanalýza hranice ne.
    fn rate_scale(&self, world: &World, group: GroupId) -> f64 {
        match self.which {
            Analogy::Rebracketing => 1.0,
            _ => 1.0 + world.params.analogy_l2_boost * world.groups.main_code(group).l2_share,
        }
    }

    fn sites(&self, world: &World, group: GroupId) -> Arc<FormSites> {
        if !morphology::active(world) {
            return Arc::default();
        }
        match self.which {
            Analogy::Leveling => morphology::leveling_sites(world, group),
            Analogy::Extension => morphology::extension_sites(world, group),
            Analogy::Rebracketing => Arc::new(morphology::rebracketing_sites(world, group)),
        }
    }
}

impl Change for AnalogicalChange {
    fn kind(&self) -> &'static str {
        match self.which {
            Analogy::Leveling => "leveling",
            Analogy::Extension => "extension",
            Analogy::Rebracketing => "rebracketing",
        }
    }

    fn rate_basis_generation(&self) -> bool {
        true
    }

    fn target(&self) -> VariableKind {
        VariableKind::Form
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &MORPH_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        let found = self.sites(world, ctx.group);
        Sites {
            sites: (0..found.len()).map(VariableId::new).collect(),
            weights: None,
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        let count = self.sites(world, ctx.group).len();
        if count == 0 {
            return 0.0;
        }
        self.base_rate() * count as f64 * self.rate_scale(world, ctx.group)
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        _rng: &mut Stream,
        _index: usize,
    ) -> Option<NewVariant> {
        let found = self.sites(world, ctx.group);
        let change: FormChange = found.changes.get(site.index())?.clone();
        let origin = Origin {
            change: Some(self.kind().to_owned()),
            tick: ctx.tick,
            year: ctx.year,
            group: ctx.group,
            parent: VariantId::NONE,
        };
        let (variable, variant) = morphology::register(world, &change, &origin);
        Some(NewVariant {
            name: world.registry.variants.name(variant.0).to_owned(),
            variable,
            payload: world.variants.payload[variant.index()].clone(),
            origin: world.variants.origin[variant.index()].clone(),
        })
    }
}

/// Morfologické změny v kanonickém pořadí.
pub fn changes() -> Vec<Box<dyn Change>> {
    vec![
        Box::new(AnalogicalChange::new(Analogy::Leveling)),
        Box::new(AnalogicalChange::new(Analogy::Extension)),
        Box::new(AnalogicalChange::new(Analogy::Rebracketing)),
    ]
}

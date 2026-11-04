//! Zvukové změny: 33 rodin procesů (zrcadlo `changes/sound.py`).
//!
//! Každá rodina je parametrický prostor: z inventáře kódu vyrobí konkrétní procesy (třída
//! cíle × výstup × prostředí). Kandidáty staví `cee_core::candidates` z rysů tabulky hlásek,
//! jejich opory (počty výskytů prostředí ve slovní zásobě) drží `cee_core::index::SoundIndex`
//! (`phonology::index`). Kandidát, který ve slovní zásobě nemá aspoň `MIN_SUPPORT` výskytů,
//! se nenabízí; míra místa je `(rozpočet rodiny · min(1, opora / 8)) / počet míst rodiny`.
//! O tom, jestli se změna prosadí, nerozhoduje počet zasažených slov, ale tlaky a šíření.
//!
//! Váhy `prior` jsou autorský typologický prior podle obecné literatury o směrech zvukové
//! změny (lenice je častější než fortice); viz `docs/DIRECTIONAL_SOURCES.md`.
//!
//! **Místa.** Místem změny je v Pythonu ID procesní proměnné, která ale vzniká až při
//! návrhu. Tady je místo číslo kandidáta v pořadí míst rodiny (`VariableId` jako nosič
//! pořadí); `propose` ho přeloží na kandidáta, zaregistruje proměnnou a vrátí ji
//! v `NewVariant::variable` (fáze inovací dál pracuje s touto proměnnou).

use cee_core::candidates::FAMILIES;

use crate::changes::{Change, InnovationContext, NewVariant, Sites, SOUND_PRESSURES};
use crate::ids::{VariableId, VariantId};
use crate::model::repertoire::{Origin, Payload, VariableKind};
use crate::phonology::index::with_group;
use crate::phonology::register;
use crate::rng::Stream;
use crate::world::World;

/// Očekávaný počet zvukových inovací na skupinu a generaci (všechny rodiny dohromady).
pub const INNOVATIONS_PER_GENERATION: f64 = 0.6;

/// Prior rodin v pořadí `FAMILIES`.
pub const PRIORS: [f64; 33] = [
    1.0, 0.8, 0.4, 0.4, 0.3, 0.8, 0.8, 0.6, 0.5, 0.5, 0.6, 0.8, 0.5, 0.5, 1.2, 0.4, 0.5, 0.5, 0.4,
    0.15, 0.35, 0.2, 0.25, 0.35, 0.2, 0.3, 0.2, 0.2, 0.12, 0.08, 0.08, 0.04, 0.04,
];

/// Od které rodiny jsou tónové. Mají vlastní rozpočet inovací: do součtu priorů se
/// nepočítají, takže tempo ostatních rodin nezmění.
pub const FIRST_TONAL: usize = 28;

/// Míra rodiny na jednotku opory: `INNOVATIONS_PER_GENERATION · prior / součet priorů`
/// (součet bez tónových rodin).
pub fn scales() -> Vec<f64> {
    let total: f64 = PRIORS[..FIRST_TONAL].iter().sum();
    PRIORS
        .iter()
        .map(|prior| INNOVATIONS_PER_GENERATION * (prior / total))
        .collect()
}

/// Jedna rodina zvukových změn.
pub struct SoundChange {
    family: usize,
}

impl SoundChange {
    pub fn new(family: usize) -> SoundChange {
        SoundChange { family }
    }

    /// Má skupina hláskové tvary a neprázdnou slovní zásobu?
    fn live(world: &World, ctx: &InnovationContext) -> bool {
        world.table.is_some()
            && !world
                .groups
                .main_code(ctx.group)
                .phonology
                .vocabulary
                .is_empty()
    }
}

/// Všechny zvukové změny v pořadí rodin.
pub fn sound_changes() -> Vec<Box<dyn Change>> {
    (0..FAMILIES.len())
        .map(|family| Box::new(SoundChange::new(family)) as Box<dyn Change>)
        .collect()
}

impl Change for SoundChange {
    fn kind(&self) -> &'static str {
        FAMILIES[self.family]
    }

    fn rate_basis_generation(&self) -> bool {
        true
    }

    fn target(&self) -> VariableKind {
        VariableKind::Process
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &SOUND_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        if !SoundChange::live(world, ctx) {
            return Sites::default();
        }
        let found = with_group(world, ctx.group, |index, token| {
            index
                .family(token, self.family)
                .map(|family| (family.rates.clone(), family.total))
        })
        .expect("index zvukových změn");
        match found {
            Some((rates, total)) if !rates.is_empty() => Sites {
                sites: (0..rates.len()).map(VariableId::new).collect(),
                weights: (total > 0.0).then(|| rates.iter().map(|rate| rate / total).collect()),
            },
            _ => Sites::default(),
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        if !SoundChange::live(world, ctx) {
            return 0.0;
        }
        with_group(world, ctx.group, |index, token| {
            index
                .family(token, self.family)
                .map_or(0.0, |family| family.total)
        })
        .expect("index zvukových změn")
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        _rng: &mut Stream,
        _index: usize,
    ) -> Option<NewVariant> {
        let candidate = with_group(world, ctx.group, |index, token| {
            index
                .site_candidate(token, self.family, site.index())
                .map(|(candidate, _)| candidate.clone())
        })
        .expect("index zvukových změn")?;
        let origin_change = self.kind();
        let found = register(
            world,
            &candidate,
            origin_change,
            ctx.tick,
            ctx.year,
            ctx.group,
        )
        .expect("registrace zvukové změny");
        let name = world.registry.variants.name(found.changed.0).to_owned();
        Some(NewVariant {
            name,
            variable: found.variable,
            payload: Payload::Process {
                process: found.process,
                changed: true,
            },
            origin: Origin {
                change: Some(origin_change.to_owned()),
                tick: ctx.tick,
                year: ctx.year,
                group: ctx.group,
                parent: VariantId::NONE,
            },
        })
    }
}

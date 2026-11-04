//! Fáze 2: inovace (rámec R0; konkrétní změny dodávají R1b a R1c).
//!
//! **Vstup:** `World` (stav na začátku kroku), seznam změn, `SimulationConfig`.
//! **Výstup:** nové varianty ve `World.variants`, v živých fondech (`live.innovate`)
//! a záznamy `innovation` v historii.
//!
//! Postup jako `Simulation._innovate`: pro každou skupinu a změnu se spočte
//! očekávaný počet inovací (`rate_sum` × tempo × násobek `change_rates`), počet se
//! vylosuje Poissonem závislým jen na klíči (semínko, tik, skupina, kód, změna), a pro
//! každou inovaci se vybere místo z proudu `Stream::new(seed, [innovation, tik, skupina,
//! kód, změna])` a změna navrhne variantu. Míry se počítají souběžně přes skupiny
//! (rayon); zápis je sekvenční v kanonickém pořadí, takže výsledek nezávisí na vláknech.

use rayon::prelude::*;
use serde_json::json;

use crate::changes::{Change, InnovationContext, Sites};
use crate::ids::{GroupId, VariableId};
use crate::phases::StepContext;
use crate::rng::{cumulative, hash_poisson, innovation_group_key, pick, stable_int, Part, Stream};

const INNOVATION_CHANGE_DOMAIN: &str = "innovation-change";

/// Počáteční podíl inovace ve skupině a násobek četnosti inovací (`innovation_scale`).
///
/// Inovace vzniká u jednoho mluvčího: ve skupině s `N` lidmi má podíl úměrný `1 / N`
/// a inovací je úměrně `N`. Součin obou na velikosti nezávisí (Kimura 1968).
pub fn innovation_scale(ctx: &StepContext<'_>, group: GroupId) -> (f64, f64) {
    let config = ctx.config;
    let size = config.reference_population / f64::from(ctx.world.groups.population[group.index()]);
    let share = config.p0_max.min(config.p0_min.max(config.p0 * size));
    (share, config.p0 / share)
}

/// Očekávaný počet inovací (`phases.expected_counts` pro jednu dvojici skupina × změna).
pub fn expected_count(
    rate_sum: f64,
    renewal: f64,
    frequency: f64,
    dt: f64,
    generation: bool,
    scale: f64,
) -> f64 {
    let tempo = if generation { renewal } else { dt } * frequency;
    if rate_sum > 0.0 {
        rate_sum * tempo * scale
    } else {
        0.0
    }
}

/// Výběr místa z proudu náhody ve stavu `state`: (index, nový stav).
pub fn draw_site(state: u64, count: usize, cumulated: Option<&[f64]>) -> (usize, u64) {
    let mut stream = Stream::from_key(state);
    let index = match cumulated {
        None => stream.integers(count as u64) as usize,
        Some(cumulated) => pick(cumulated, stream.random()),
    };
    (index, stream.state)
}

/// Provede fázi inovací.
pub fn run(ctx: &mut StepContext<'_>, changes: &[Box<dyn Change>]) -> Result<(), String> {
    let dt = ctx.config.dt;
    let entries: Vec<GroupId> = ctx
        .world
        .group_ids()
        .into_iter()
        .filter(|g| !ctx.world.groups.written[g.index()])
        .collect();
    if entries.is_empty() || changes.is_empty() {
        return Ok(());
    }
    let rates = &ctx.world.params.change_rates;
    let known: Vec<&str> = changes.iter().map(|c| c.kind()).collect();
    if let Some(unknown) = rates.keys().find(|k| !known.contains(&k.as_str())) {
        return Err(format!("Parametry mění tempo neznámých změn: [{unknown}]."));
    }
    let change_keys: Vec<u64> = changes
        .iter()
        .map(|c| stable_int(&[Part::Str(INNOVATION_CHANGE_DOMAIN), Part::Str(c.kind())]))
        .collect();
    let seed = ctx.world.seed;
    let (tick, year) = (ctx.tick, ctx.year);
    let world = &*ctx.world;
    let contexts: Vec<InnovationContext> = entries
        .iter()
        .map(|&group| InnovationContext { group, tick, year })
        .collect();

    // Tempo se počítá ze stavu na začátku kroku pro všechny skupiny, než se uplatní první inovace.
    let rate_sums: Vec<Vec<f64>> = contexts
        .par_iter()
        .map(|context| {
            changes
                .iter()
                .map(|change| change.rate_sum(world, context))
                .collect()
        })
        .collect();
    let mut expected = vec![vec![0.0; changes.len()]; entries.len()];
    let mut shares = Vec::with_capacity(entries.len());
    for (g, &group) in entries.iter().enumerate() {
        let renewal = world.groups.renewal(group, dt);
        let (share, frequency) = innovation_scale(ctx, group);
        shares.push(share);
        for (c, change) in changes.iter().enumerate() {
            let scale = rates.get(change.kind()).copied().unwrap_or(1.0);
            expected[g][c] = expected_count(
                rate_sums[g][c],
                renewal,
                frequency,
                dt,
                change.rate_basis_generation(),
                scale,
            );
        }
    }
    if !expected.iter().flatten().any(|&e| e > 0.0) {
        return Ok(());
    }
    let mut counts = vec![vec![0_u64; changes.len()]; entries.len()];
    for (g, &group) in entries.iter().enumerate() {
        let code = &world.groups.main_code(group).id;
        let key = innovation_group_key(seed, u64::from(tick), world.group_name(group), code);
        for c in 0..changes.len() {
            counts[g][c] = hash_poisson(key, change_keys[c], expected[g][c]);
        }
    }
    // Místa inovací a jejich váhy závisejí jen na stavu na začátku kroku.
    let sites: Vec<Vec<Option<Sites>>> = contexts
        .par_iter()
        .enumerate()
        .map(|(g, context)| {
            (0..changes.len())
                .map(|c| (counts[g][c] > 0).then(|| changes[c].weighted_sites(world, context)))
                .collect()
        })
        .collect();

    for (g, &group) in entries.iter().enumerate() {
        for (c, change) in changes.iter().enumerate() {
            let count = counts[g][c];
            if count == 0 {
                continue;
            }
            let Some(found) = &sites[g][c] else { continue };
            apply_innovations(ctx, change.as_ref(), &contexts[g], shares[g], count, found)?;
            let _ = group;
        }
    }
    Ok(())
}

fn apply_innovations(
    ctx: &mut StepContext<'_>,
    change: &dyn Change,
    context: &InnovationContext,
    share: f64,
    count: u64,
    found: &Sites,
) -> Result<(), String> {
    if found.sites.is_empty() {
        return Ok(());
    }
    let group = context.group;
    let group_name = ctx.world.group_name(group).to_owned();
    let code_name = ctx.world.groups.main_code(group).id.clone();
    let mut rng = Stream::new(
        ctx.world.seed as u64,
        &[
            Part::Str("innovation"),
            Part::Uint(u64::from(ctx.tick)),
            Part::Str(&group_name),
            Part::Str(&code_name),
            Part::Str(change.kind()),
        ],
    );
    let cumulated = found.weights.as_deref().map(cumulative).transpose()?;
    for index in 0..count as usize {
        let (picked, state) = draw_site(rng.state, found.sites.len(), cumulated.as_deref());
        rng.state = state;
        let site: VariableId = found.sites[picked];
        let Some(variant) = change.propose(ctx.world, context, site, &mut rng, index) else {
            continue;
        };
        // Zvukové a formové změny zakládají proměnnou až při návrhu: místo je pořadí kandidáta,
        // platí proměnná varianty.
        let site = variant.variable;
        let world = &mut *ctx.world;
        if world.live.contains(site) {
            if !world.live.holds(group, site) {
                continue;
            }
        } else if world.stored(group, site).is_none() {
            continue;
        } else {
            let dists: Vec<_> = world
                .live
                .group_ids
                .iter()
                .map(|&g| world.stored(g, site))
                .collect();
            let mut live = std::mem::take(&mut world.live);
            let loaded = live.load(site, &dists, &world.registry.variants);
            world.live = live;
            loaded?;
        }
        let id = world.store_variant(
            &variant.name,
            variant.variable,
            variant.payload.clone(),
            variant.origin.clone(),
        );
        let held = world.distribution(group, site);
        if held.as_ref().is_some_and(|d| d.variants.contains(&id)) {
            continue; // tutéž změnu už skupina má
        }
        world
            .live
            .innovate(site, group, id, share, &world.registry.variants);
        let payload = json!({
            "group": group_name, "code": code_name, "change": change.kind(),
            "variable": world.registry.variables.name(site.0), "variant": world.registry.variants.name(id.0),
        });
        ctx.history
            .record("innovation", ctx.tick, context.year, payload);
    }
    Ok(())
}

//! Fáze 3: přenos jazyka mezi skupinami a tlaky (R1a).
//!
//! **Vstup:** `World.live` (bloky podílů variant), `World.links` (CSR vazby),
//! skupiny (populace, prestiž, otevřenost, obnova), `Parameters`, tlaky změn.
//! **Výstup:** nové podíly variant ve fondech (`PoolBlock::cells`), záznamy
//! `milestone`, `established`, `extinct` v historii, aktivace procesů a analogií
//! (nad prahem `activation_share`), změny dominantních kořenů a slovní zásoby
//! kódů, uvolnění ustálených proměnných do repertoárů.
//!
//! Python (`simulation._transmit`, `transmission.py`, `phases_transmission.py`,
//! `pressures*.py`) staví vstupy kroku (`prepare`), spočítá všechny bloky ze starého
//! stavu (`transmit`: míšení, selekce s tlaky, drift, inkrementace), vytvoří plán událostí
//! a zapíše ho v kanonickém pořadí. Jádra jsou v `cee_core::transmission` (`hear`,
//! `settle`) a `cee_core::pressures`; R1a je napojí na `PoolBlock` a `World`.
//!
//! Pořadí v kroku jako v Pythonu: příprava ([`crate::transfer::network::prepare`]) → přenos
//! všech bloků ze starého stavu ([`crate::transfer::block::transmit_block`]) → zápis po
//! blocích (smluvené body `record_grammar`, `follow_vocabulary`, pak uložení nových podílů)
//! → aktivace seřazené podle jmen (skupina, proměnná) → záznamy `established`, `extinct`,
//! `milestone` v kanonickém pořadí → [`release`].

use serde_json::json;

use crate::ids::{GroupId, VariableId, VariantId};
use crate::phases::{hooks, StepContext};
use crate::transfer::block::{leaves_before_enters, transmit_block, BlockOutcome, MILESTONES};
use crate::transfer::network::{prepare, TransmissionParams};
use crate::transfer::pressures::{plan, Pressures};

/// Vrátí ustálené proměnné z fondů do repertoárů skupin.
pub fn release(ctx: &mut StepContext<'_>) {
    let world = &mut *ctx.world;
    let mut live = std::mem::take(&mut world.live);
    let released = live.release(&world.registry.variants);
    let axis = live.group_ids.clone();
    world.live = live;
    for (variable, distributions) in released {
        for (group, distribution) in axis.iter().zip(distributions) {
            if let Some(distribution) = distribution {
                world
                    .groups
                    .main_code_mut(*group)
                    .repertoire
                    .set(variable, distribution);
            }
        }
    }
}

/// Záznam po přenosu v kanonickém pořadí (druh, skupina, hladina, proměnná, varianta podle jmen).
struct Record {
    kind: &'static str,
    group: Option<GroupId>,
    level: Option<u8>,
    variable: VariableId,
    variant: Option<VariantId>,
}

/// Provede fázi přenosu.
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    ctx.world.transfer.steps += 1;
    if ctx.world.live.is_empty() {
        return Ok(());
    }
    crate::transfer::sync(ctx.world);
    let params = TransmissionParams {
        dt: ctx.config.dt,
        alpha: ctx.config.alpha,
        selection: ctx.config.selection,
        kappa: ctx.config.kappa,
        sigma: ctx.config.sigma,
        adult_rate: ctx.config.adult_rate,
        loss_threshold: ctx.config.loss_threshold,
        establish_threshold: ctx.config.establish_threshold,
    };
    // Všechny bloky se počítají ze starého stavu; svět se zatím nemění.
    let outcomes: Vec<(usize, BlockOutcome)> = {
        let world = &*ctx.world;
        let inputs = prepare(world, &params, ctx.tick);
        let pressure_plan = plan(&world.params)?;
        let mut pressures = Pressures::new(world, &inputs, &pressure_plan)?;
        world
            .live
            .blocks
            .iter()
            .filter(|(_, block)| !block.is_empty())
            .map(|(&capacity, block)| {
                (
                    capacity,
                    transmit_block(
                        world,
                        &inputs,
                        &params,
                        &mut pressures,
                        block,
                        ctx.config.record_trajectories,
                    ),
                )
            })
            .collect()
    };
    let has_table = ctx.world.table.is_some();
    let mut records: Vec<Record> = Vec::new();
    let mut activations: Vec<(GroupId, VariableId)> = Vec::new();
    for (capacity, mut outcome) in outcomes {
        for &(variable, variant, group, level) in &outcome.milestones {
            records.push(Record {
                kind: "milestone",
                group: Some(group),
                level: Some(level),
                variable,
                variant: Some(variant),
            });
        }
        for &(variable, variant, group) in &outcome.established {
            records.push(Record {
                kind: "established",
                group: Some(group),
                level: None,
                variable,
                variant: Some(variant),
            });
        }
        for &(variable, variant) in &outcome.extinct {
            records.push(Record {
                kind: "extinct",
                group: None,
                level: None,
                variable,
                variant: Some(variant),
            });
        }
        for &(variant, group, share) in &outcome.trace {
            ctx.history
                .trajectories
                .entry((variant, group))
                .or_default()
                .push((ctx.tick, share));
        }
        // Konstrukční rozdělení je vstupem syntaktické přestavby.
        for &(variable, group) in &outcome.grammar {
            hooks::record_grammar(ctx, group, variable)?;
        }
        if has_table {
            leaves_before_enters(&mut outcome.crossings);
            hooks::follow_vocabulary(ctx, &outcome.crossings)?;
            activations.extend_from_slice(&outcome.activations);
        }
        let block = ctx
            .world
            .live
            .blocks
            .get_mut(&capacity)
            .ok_or("Blok živých proměnných zmizel během přenosu.")?;
        if block.cells.rows.len() != outcome.rows.len() {
            return Err("Řádky bloku se mezi přípravou a zápisem stavu změnily.".into());
        }
        block.cells.rows = outcome.rows;
    }
    // Kanonické pořadí aktivací nezávisí na tom, ve kterém řádku skladu proměnná leží.
    {
        let names = &ctx.world.registry;
        activations.sort_by(|a, b| {
            names
                .groups
                .name(a.0 .0)
                .cmp(names.groups.name(b.0 .0))
                .then_with(|| {
                    names
                        .variables
                        .name(a.1 .0)
                        .cmp(names.variables.name(b.1 .0))
                })
        });
    }
    for (group, variable) in activations {
        hooks::activate(ctx, group, variable)?;
    }
    write_records(ctx, records);
    release(ctx);
    Ok(())
}

/// Zapíše záznamy v kanonickém pořadí (druh, pak abecedně seřazené položky jako v Pythonu).
fn write_records(ctx: &mut StepContext<'_>, mut records: Vec<Record>) {
    let registry = &ctx.world.registry;
    let key = |r: &Record| {
        (
            r.kind,
            r.group.map(|g| registry.groups.name(g.0)).unwrap_or(""),
            r.level.unwrap_or(0),
            registry.variables.name(r.variable.0),
            r.variant.map(|v| registry.variants.name(v.0)).unwrap_or(""),
        )
    };
    records.sort_by(|a, b| key(a).cmp(&key(b)));
    for record in &records {
        let variable = registry.variables.name(record.variable.0);
        let variant = record.variant.map(|v| registry.variants.name(v.0));
        let payload = match record.kind {
            "milestone" => json!({
                "variable": variable,
                "variant": variant,
                "group": record.group.map(|g| registry.groups.name(g.0)),
                "level": MILESTONES[record.level.unwrap_or(0) as usize],
            }),
            "established" => json!({
                "variable": variable,
                "variant": variant,
                "group": record.group.map(|g| registry.groups.name(g.0)),
            }),
            _ => json!({ "variable": variable, "variant": variant }),
        };
        ctx.history.record(record.kind, ctx.tick, ctx.year, payload);
    }
}

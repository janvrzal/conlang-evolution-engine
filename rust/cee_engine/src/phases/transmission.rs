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
//! všech bloků ze starého stavu ([`crate::transfer::block::transmit_rows`]) → zápis po
//! blocích (smluvené body `record_grammar`, `follow_vocabulary`, pak uložení nových podílů)
//! → aktivace seřazené podle jmen (skupina, proměnná) → záznamy `established`, `extinct`,
//! `milestone` v kanonickém pořadí → [`release`].

use rayon::prelude::*;
use serde_json::json;

use crate::history::History;
use crate::ids::{GroupId, VariableId, VariantId};
use crate::model::pools::PoolBlock;
use crate::parallel;
use crate::phases::{hooks, StepContext};
use crate::transfer::block::{
    jobs, leaves_before_enters, transmit_rows, BlockOutcome, Job, MILESTONES,
};
use crate::transfer::factors::{block_factors, BlockFactors};
use crate::transfer::network::{prepare, TransmissionParams};
use crate::transfer::pressures::{plan_for, Pressures};

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
pub fn run(
    ctx: &mut StepContext<'_>,
    changes: &[Box<dyn crate::changes::Change>],
) -> Result<(), String> {
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
        completion_share: ctx.config.completion_share,
    };
    // Dvouprůchodový návrh: nejdřív hodnocení procesů (mění banku tvarů), potom přenos nad `&World`.
    let t = crate::timing::scope("transmission/prepare");
    let inputs = prepare(&*ctx.world, &params, ctx.tick);
    drop(t);
    let t = crate::timing::scope("transmission/assess");
    crate::transfer::assess::refresh(ctx.world, &inputs)?;
    drop(t);
    let t = crate::timing::scope("transmission/blocks");
    // Všechny bloky se počítají ze starého stavu; svět se zatím nemění. Bloky se dělí na úlohy
    // (kusy řádků), které běží souběžně; výsledky se skládají v pořadí bloků a řádků.
    let outcomes: Vec<(usize, BlockOutcome)> = {
        let world = &*ctx.world;
        let pressure_plan = plan_for(changes, &world.params)?;
        let pressures = Pressures::new(world, &inputs, &pressure_plan)?;
        let blocks: Vec<(usize, &PoolBlock)> = world
            .live
            .blocks
            .iter()
            .filter(|(_, block)| !block.is_empty())
            .map(|(&capacity, block)| (capacity, block))
            .collect();
        let factors: Vec<BlockFactors> = blocks
            .iter()
            .map(|(_, block)| block_factors(world, &inputs, block))
            .collect();
        let pools: Vec<&PoolBlock> = blocks.iter().map(|&(_, block)| block).collect();
        let groups = inputs.axis.len();
        let cells: usize = pools.iter().map(|b| b.len() * b.capacity * groups).sum();
        let split = parallel::worth_splitting(cells);
        let list = jobs(&pools, groups, split);
        let trace = ctx.config.record_trajectories;
        let run = |job: &Job| {
            transmit_rows(
                world,
                &inputs,
                &params,
                &pressures,
                pools[job.block],
                &factors[job.block],
                job.start,
                job.count,
                trace,
            )
        };
        let results: Vec<BlockOutcome> = if split {
            list.par_iter().map(run).collect()
        } else {
            list.iter().map(run).collect()
        };
        let mut merged: Vec<(usize, BlockOutcome)> = Vec::new();
        for (job, result) in list.iter().zip(results) {
            match merged.last_mut() {
                Some((capacity, found)) if *capacity == blocks[job.block].0 => found.append(result),
                _ => merged.push((blocks[job.block].0, result)),
            }
        }
        merged
    };
    drop(t);
    let t = crate::timing::scope("transmission/write");
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
            let _tv = crate::timing::scope("w/vocab");
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
    let ta = crate::timing::scope("w/activate");
    for (group, variable) in activations {
        hooks::activate(ctx, group, variable)?;
    }
    drop(ta);
    let ta = crate::timing::scope("w/records");
    write_records(ctx, records);
    drop(ta);
    let ta = crate::timing::scope("w/release");
    release(ctx);
    drop(ta);
    drop(t);
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
    records.par_sort_by(|a, b| key(a).cmp(&key(b)));
    // Záznamy se sestavují souběžně (čistá funkce), do historie jdou po řadě v seřazeném pořadí.
    let (tick, year) = (ctx.tick, ctx.year);
    let build = |record: &Record| {
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
        History::event(record.kind, tick, year, payload)
    };
    let events: Vec<_> = if parallel::worth_splitting(records.len() * 256) {
        records.par_iter().map(build).collect()
    } else {
        records.iter().map(build).collect()
    };
    ctx.history.events.extend(events);
}

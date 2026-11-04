//! Fronty fonologizace: aktivace procesu, zařazení slov, přepis tvarů a uzavření procesu
//! (zrcadlo `phonology.activate`, `_queue_all`, `restructure`).
//!
//! Jádro (`cee_core::code_state::CodeState`) nic nezapisuje do modelu světa: vrací přepsané
//! tvary a události a zapisuje je tu. Co jádro nemá (sklony slov, mapy hlásek pro operace
//! `change` a `tone`), vyžádá jako `CodeNeeds`; nic z toho nezapíše napůl, takže se po doplnění
//! volá znovu a hotová práce se nezopakuje.

use std::collections::BTreeMap;

use cee_core::code_state::{CodeNeeds, CodeState, Ctx, Event, Round, RoundOut, UsageInputs};
use cee_core::phonology::{Params, Units, NO_OVERLAY};
use serde_json::json;

use crate::ids::{GroupId, MorphemeId, ProcessId};
use crate::model::forms::UnitForm;
use crate::phases::StepContext;
use crate::phonology::columns::{draw_bias, refresh, sync_usage};
use crate::phonology::rows::{changed_share, ensure_rows, info_of, resolve_maps};
use crate::world::World;

/// Kolikrát se smí jedno volání jádra opakovat, než se usoudí, že se nic nehýbe.
const MAX_ROUNDS: usize = 1_000_000;

/// `_logit`: logit podílu oříznutého na 0,01 až 0,99.
fn logit(share: f64) -> f64 {
    let share = share.clamp(0.01, 0.99);
    (share / (1.0 - share)).ln()
}

/// Společné přípravy před voláním jádra: řádky procesů, sloupce, paměť četností kódu.
fn prepare(world: &mut World, group: GroupId) -> Result<(), String> {
    ensure_rows(world)?;
    refresh(world);
    sync_usage(world, group);
    Ok(())
}

/// Základ logitu prahu fonologizace (`log(p / (1 − p))`).
fn base_of(world: &World) -> f64 {
    let threshold = world.params.restructure_threshold;
    (threshold / (1.0 - threshold)).ln()
}

/// Doplní, co jádro vyžádalo. Mapy hlásek a sklony slov dopočítá; výchozí tvar, který
/// není v bance, a četnost užití, kterou jádro neumí určit, jsou chyby modelu světa.
fn resolve(world: &mut World, needs: &CodeNeeds) -> Result<(), String> {
    if let Some(&morpheme) = needs.forms.first() {
        return Err(format!(
            "morfém č. {morpheme} nemá výchozí tvar v bance tvarů světa"
        ));
    }
    if let Some(&morpheme) = needs.freq.first() {
        return Err(format!(
            "četnost užití lexému č. {morpheme} nejde určit ze sloupců světa"
        ));
    }
    for &(process, morpheme) in &needs.bias {
        draw_bias(world, process, morpheme)?;
    }
    if !needs.maps.is_empty() {
        resolve_maps(world, &needs.maps)?;
    }
    Ok(())
}

/// Do stavu procesů kódu zapíše řádky banky a redukčnost podle definic procesů.
fn set_rows(world: &mut World, group: GroupId) {
    let runtime = &world.sound.runtime;
    let state = &mut world
        .groups
        .main_code_mut(group)
        .phonology
        .sound
        .queues
        .state;
    for proc in &mut state.procs {
        let row = runtime.rows.get(proc.number).copied().unwrap_or(-1);
        let row = (row >= 0).then_some(row as usize);
        proc.row = row;
        proc.own_row = row;
        proc.reductive = world
            .processes
            .get(proc.number)
            .and_then(Option::as_ref)
            .is_some_and(|def| def.reductive);
    }
}

/// Zařadí morfémy do front všech živých procesů kódu skupiny (`_queue_all`); slova, která
/// si změnu už zapsala nebo čekají, se přeskočí, ostatní jen když na ně proces dopadne.
fn queue_units(world: &mut World, group: GroupId, members: &[MorphemeId]) -> Result<(), String> {
    if world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .live()
        .is_empty()
    {
        return Ok(());
    }
    prepare(world, group)?;
    set_rows(world, group);
    let mut waiting: Vec<i32> = members.iter().map(|m| m.0 as i32).collect();
    for _ in 0..MAX_ROUNDS {
        if waiting.is_empty() {
            return Ok(());
        }
        let needs = {
            let base = base_of(world);
            let lead = world.params.frequency_lead;
            let World {
                bank,
                groups,
                morphemes,
                sound,
                ..
            } = &mut *world;
            let runtime = &sound.runtime;
            let code = groups.main_code_mut(group);
            let rule = code.stress_rule.as_rule();
            let (form, cut, exponent) = code.forms.raw();
            let state = &mut code.phonology.sound.queues.state;
            let live = state.live();
            let biases: Vec<&[f64]> = live
                .iter()
                .map(|&at| {
                    runtime
                        .biases
                        .get(state.procs[at].number)
                        .map_or(&[][..], Vec::as_slice)
                })
                .collect();
            let reductive: Vec<bool> = live.iter().map(|&at| state.procs[at].reductive).collect();
            let ctx = Ctx {
                params: Params {
                    rule,
                    base,
                    lead_scale: lead,
                },
                units: Units {
                    form,
                    cut,
                    exponent,
                    default_form: &runtime.columns.default_form,
                    default_cut: &runtime.columns.default_cut,
                    default_exponent: &runtime.columns.default_exponent,
                    lexeme: &runtime.columns.lexeme,
                    overlay: &NO_OVERLAY,
                },
                usage: UsageInputs {
                    concept: &runtime.concept,
                    fixed: &morphemes.frequency,
                    weight: &runtime.columns.weight,
                    lexeme: &runtime.columns.lexeme,
                },
            };
            state.queue_units(&mut bank.bank, &ctx, &biases, &reductive, &waiting)?
        };
        let (done, needs) = needs;
        waiting.drain(..done);
        if needs.is_empty() {
            return Ok(());
        }
        resolve(world, &needs)?;
    }
    Err("fronty fonologizace se nedokončily".into())
}

/// Slovo se stalo dominantním: projdou jím i změny, které právě běží (`enter_units`).
pub fn enter_units(world: &mut World, group: GroupId, units: &[MorphemeId]) -> Result<(), String> {
    let state = &mut world.groups.main_code_mut(group).phonology;
    let mut entered = Vec::new();
    for &unit in units {
        if state.enter_vocabulary(unit) {
            state.version += 1;
            state.lexicon_version += 1;
            entered.push(unit);
        }
    }
    if entered.is_empty() {
        return Ok(());
    }
    queue_units(world, group, &entered)
}

/// Slovo přestalo být dominantní: opustí slovní zásobu kódu.
pub fn leave_vocabulary(world: &mut World, group: GroupId, unit: MorphemeId) {
    let state = &mut world.groups.main_code_mut(group).phonology;
    if state.leave_vocabulary(unit) {
        state.version += 1;
        state.lexicon_version += 1;
    }
}

/// Tvar morfému se změnil (analogie, jiný proces): ať ho živé procesy znovu posoudí.
pub fn requeue_all(world: &mut World, group: GroupId, morpheme: MorphemeId) -> Result<(), String> {
    queue_units(world, group, &[morpheme])
}

/// Proces poprvé zasáhl kód: zařadí do fronty všechna slova slovní zásoby, kterých se týká
/// a která si změnu ještě nezapsala (`activate`). Proces, který už kód zná (živý nebo uzavřený),
/// se přeskočí.
pub fn activate(world: &mut World, group: GroupId, process: ProcessId) -> Result<(), String> {
    let known = world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .find(process.index())
        .is_some();
    if known {
        return Ok(());
    }
    prepare(world, group)?;
    let row = crate::phonology::rows::row_of(world, process)?;
    let reductive = world
        .processes
        .get(process.index())
        .and_then(Option::as_ref)
        .map(|def| def.reductive)
        .ok_or_else(|| format!("proces č. {} nemá definici", process.0))?;
    {
        let sound = &mut world.groups.main_code_mut(group).phonology.sound;
        sound.order.push(process);
        sound.lifecycle_log.push((process, true));
    }
    for _ in 0..MAX_ROUNDS {
        let needs = {
            let base = base_of(world);
            let lead = world.params.frequency_lead;
            let count = world.morphemes.len();
            let World {
                bank,
                groups,
                morphemes,
                sound,
                ..
            } = &mut *world;
            let runtime = &sound.runtime;
            let code = groups.main_code_mut(group);
            let rule = code.stress_rule.as_rule();
            let mut flags = vec![0_u8; count];
            for member in code.phonology.vocabulary.iter() {
                if member.index() < count {
                    flags[member.index()] = 1;
                }
            }
            let (form, cut, exponent) = code.forms.raw();
            let state = &mut code.phonology.sound.queues.state;
            let bias = runtime
                .biases
                .get(process.index())
                .map_or(&[][..], Vec::as_slice);
            let ctx = Ctx {
                params: Params {
                    rule,
                    base,
                    lead_scale: lead,
                },
                units: Units {
                    form,
                    cut,
                    exponent,
                    default_form: &runtime.columns.default_form,
                    default_cut: &runtime.columns.default_cut,
                    default_exponent: &runtime.columns.default_exponent,
                    lexeme: &runtime.columns.lexeme,
                    overlay: &NO_OVERLAY,
                },
                usage: UsageInputs {
                    concept: &runtime.concept,
                    fixed: &morphemes.frequency,
                    weight: &runtime.columns.weight,
                    lexeme: &runtime.columns.lexeme,
                },
            };
            state.activate(
                &mut bank.bank,
                &ctx,
                process.index(),
                row,
                reductive,
                bias,
                &flags,
            )?
        };
        if needs.is_empty() {
            return Ok(());
        }
        resolve(world, &needs)?;
    }
    Err("aktivace procesu se nedokončila".into())
}

/// Fonologizace a uzavírání procesů ve skupinách po řadě (`restructure_groups`).
///
/// Záznamy `phonologized` a `process_closed` se do historie píšou po skupinách v pořadí
/// `groups`; skupiny bez živého procesu se přeskočí.
pub fn restructure_groups(ctx: &mut StepContext<'_>, groups: &[GroupId]) -> Result<(), String> {
    if ctx.world.table.is_none() {
        return Ok(());
    }
    for &group in groups {
        restructure_group(ctx, group)?;
    }
    Ok(())
}

/// Vstupy jednoho volání jádra, které se skládají ze stavu světa před vypůjčením.
struct Inputs {
    levels: Vec<f64>,
    full: Vec<bool>,
    numbers: Vec<usize>,
}

fn inputs_of(world: &mut World, group: GroupId) -> Result<Inputs, String> {
    let numbers: Vec<usize> = {
        let state = &world.groups.main_code(group).phonology.sound.queues.state;
        state
            .live()
            .iter()
            .map(|&at| state.procs[at].number)
            .collect()
    };
    let mut levels = Vec::with_capacity(numbers.len());
    let mut full = Vec::with_capacity(numbers.len());
    for &number in &numbers {
        let (variable, changed) = info_of(world, ProcessId::new(number))?;
        let share = changed_share(world, group, variable, changed);
        levels.push(if share > 0.0 {
            logit(share)
        } else {
            f64::NEG_INFINITY
        });
        full.push(share >= 1.0);
    }
    Ok(Inputs {
        levels,
        full,
        numbers,
    })
}

/// Zapíše přepsané tvary kódu a události procesů do historie.
fn apply(
    ctx: &mut StepContext<'_>,
    group: GroupId,
    out: &RoundOut,
    carried: &mut BTreeMap<usize, usize>,
) -> Result<Option<usize>, String> {
    let world = &mut *ctx.world;
    {
        let code = world.groups.main_code_mut(group);
        for rewrite in &out.rewrites {
            let exponent = if rewrite.exponent < 0 {
                MorphemeId::NONE
            } else {
                MorphemeId(rewrite.exponent as u32)
            };
            code.forms.set(
                MorphemeId::new(rewrite.morpheme),
                UnitForm {
                    form: rewrite.form as u32,
                    boundary: rewrite.cut,
                    exponent,
                },
            );
            code.phonology.version += 1;
        }
    }
    let group_name = world.group_name(group).to_owned();
    let mut resume = None;
    for event in &out.events {
        match *event {
            Event::Partial { proc, words } => {
                *carried.entry(proc).or_insert(0) += words;
                resume = Some(proc);
            }
            Event::Finished { proc, words } => {
                let total = carried.remove(&proc).unwrap_or(0) + words;
                if total > 0 {
                    let (variable, _) = info_of(world, ProcessId::new(proc))?;
                    let payload = json!({
                        "group": group_name,
                        "variable": world.registry.variables.name(variable.0),
                        "words": total,
                    });
                    ctx.history
                        .record("phonologized", ctx.tick, ctx.year, payload);
                }
            }
            Event::Closed {
                proc,
                restructured,
                relics,
            } => {
                let (variable, _) = info_of(world, ProcessId::new(proc))?;
                let sound = &mut world.groups.main_code_mut(group).phonology;
                sound
                    .sound
                    .lifecycle_log
                    .push((ProcessId::new(proc), false));
                sound.version += 1;
                let payload = json!({
                    "group": group_name,
                    "variable": world.registry.variables.name(variable.0),
                    "restructured": restructured,
                    "relics": relics,
                });
                ctx.history
                    .record("process_closed", ctx.tick, ctx.year, payload);
            }
        }
    }
    Ok(resume)
}

fn restructure_group(ctx: &mut StepContext<'_>, group: GroupId) -> Result<(), String> {
    let live = ctx
        .world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .live();
    if live.is_empty() {
        return Ok(());
    }
    let (tick, dt) = (i64::from(ctx.tick), ctx.config.dt);
    let mut resume: Option<usize> = None;
    let mut carried: BTreeMap<usize, usize> = BTreeMap::new();
    for _ in 0..MAX_ROUNDS {
        prepare(ctx.world, group)?;
        set_rows(ctx.world, group);
        let inputs = inputs_of(ctx.world, group)?;
        let world = &mut *ctx.world;
        let base = base_of(world);
        let lead = world.params.frequency_lead;
        let threshold =
            world.params.closure_generations * world.groups.generation_years[group.index()];
        let mut out = RoundOut::default();
        let needs = {
            let World {
                bank,
                groups,
                morphemes,
                sound,
                ..
            } = &mut *world;
            let runtime = &sound.runtime;
            let code = groups.main_code_mut(group);
            let rule = code.stress_rule.as_rule();
            let (form, cut, exponent) = code.forms.raw();
            let state: &mut CodeState = &mut code.phonology.sound.queues.state;
            let biases: Vec<&[f64]> = inputs
                .numbers
                .iter()
                .map(|&number| runtime.biases.get(number).map_or(&[][..], Vec::as_slice))
                .collect();
            let reductive: Vec<bool> = inputs
                .numbers
                .iter()
                .map(|&number| {
                    state
                        .procs
                        .iter()
                        .find(|proc| proc.number == number)
                        .is_some_and(|proc| proc.reductive)
                })
                .collect();
            let round = Round {
                ctx: Ctx {
                    params: Params {
                        rule,
                        base,
                        lead_scale: lead,
                    },
                    units: Units {
                        form,
                        cut,
                        exponent,
                        default_form: &runtime.columns.default_form,
                        default_cut: &runtime.columns.default_cut,
                        default_exponent: &runtime.columns.default_exponent,
                        lexeme: &runtime.columns.lexeme,
                        overlay: &NO_OVERLAY,
                    },
                    usage: UsageInputs {
                        concept: &runtime.concept,
                        fixed: &morphemes.frequency,
                        weight: &runtime.columns.weight,
                        lexeme: &runtime.columns.lexeme,
                    },
                },
                biases,
                reductive,
                levels: inputs.levels.clone(),
                full: inputs.full.clone(),
                tick,
                dt,
                threshold,
                resume,
            };
            state.restructure(&mut bank.bank, &round, &mut out)?
        };
        let stopped = apply(ctx, group, &out, &mut carried)?;
        match needs {
            None => return Ok(()),
            Some(needs) => {
                resume = stopped.or(resume);
                resolve(ctx.world, &needs)?;
            }
        }
    }
    Err("fonologizace skupiny se nedokončila".into())
}

//! Přenos jednoho bloku živých proměnných a události z jeho starého a nového stavu
//! (zrcadlo `transmission.transmit` a `simulation._plan`, `_changes`, `_crossings`,
//! `_activations`, `_trace_cells`).
//!
//! Blok se počítá **ze starého stavu**: po kusech řádků (pole mezivýsledků nerostou s celým
//! blokem; řádky jsou nezávislé, kusy dávají tytéž hodnoty) se spočítá slyšené (`hear`), tlaky
//! (`Pressures::fitness`) a výběr s driftem a ustálením (`settle`). Hustá pole žijí jen po dobu
//! jednoho kusu; nový stav se hned ukládá řídce jako řádky `cee_core::pools::Row`.
//! Svět se nemění, zápis udělá fáze až po všech blocích.

use cee_core::pools::Row;
use cee_core::transmission::{
    hear, settle, Channel, Cohorts, Flow, HearScratch, Network, Shape, State, FORGET, REMEMBER,
};

use crate::ids::{GroupId, MorphemeId, VariableId, VariantId};
use crate::model::pools::PoolBlock;
use crate::model::repertoire::{Payload, VariableKind};
use crate::phases::hooks::Crossing;
use crate::transfer::factors::BlockFactors;
use crate::transfer::network::{StepInputs, TransmissionParams};
use crate::transfer::pressures::Pressures;
use crate::world::World;

/// Hladiny milníků šíření inovace.
pub const MILESTONES: [f64; 3] = [0.1, 0.5, 0.9];
/// Nejvíc buněk (proměnné × skupiny × sloty) jednoho kusu bloku.
const CHUNK_CELLS: usize = 1 << 20;
/// Cílová velikost úlohy při souběhu: dost malá na vyrovnání práce, dost velká, aby režie
/// úlohy (pole, fronta) nebyla znát.
const JOB_CELLS: usize = 1 << 12;
/// Hladina, kterou slovo překračuje při vstupu do slovní zásoby a odchodu z ní.
const DOMINANCE: f64 = 0.5;

/// Co přenos jednoho bloku způsobí; čísla, žádné řetězce.
#[derive(Default)]
pub struct BlockOutcome {
    /// Nový stav všech řádků bloku (podíly a základny trendu), řídce.
    pub rows: Vec<Row>,
    /// (proměnná, varianta, skupina, číslo hladiny v `MILESTONES`).
    pub milestones: Vec<(VariableId, VariantId, GroupId, u8)>,
    pub established: Vec<(VariableId, VariantId, GroupId)>,
    pub extinct: Vec<(VariableId, VariantId)>,
    /// Konstrukční proměnné, jejichž rozdělení se ve skupině změnilo.
    pub grammar: Vec<(VariableId, GroupId)>,
    /// Odchody a poté příchody slov přes práh dominance.
    pub crossings: Vec<Crossing>,
    /// Procesy a analogie nad prahem aktivace: (skupina, proměnná).
    pub activations: Vec<(GroupId, VariableId)>,
    /// Dráhy inovací: (varianta, skupina, podíl).
    pub trace: Vec<(VariantId, GroupId, f64)>,
    /// Změny paměti zapomenutých variant: (proměnná, skupina, varianta, zapomenuta?).
    pub forgotten: Vec<(VariableId, GroupId, VariantId, bool)>,
}

/// Počet hladin `levels`, které nepřevyšují `value` (`numpy.searchsorted(levels, value, "right")`).
fn reached(value: f64) -> u8 {
    MILESTONES.iter().filter(|&&level| level <= value).count() as u8
}

/// Číslo varianty „změna“ sledované proměnné (procesu či analogie), je-li v bloku.
fn tracked_slot(world: &World, block: &PoolBlock, row: usize) -> Option<usize> {
    let variable = block.variables[row];
    let tracked = match world.variables.kind[variable.index()] {
        VariableKind::Process => {
            let process = world.variables.process[variable.index()];
            !process.is_none() && world.process(process).is_some()
        }
        VariableKind::Form => world.form_changes.contains_key(&variable),
        _ => false,
    };
    if !tracked {
        return None;
    }
    let changed = *world.transfer.derived.changed.get(variable.index())?;
    if changed == u32::MAX {
        return None;
    }
    block.slots[row].iter().position(|v| v.0 == changed)
}

/// Kus řádků jednoho bloku, který se počítá jako jeden celek (úloha souběhu).
#[derive(Clone, Copy, Debug)]
pub struct Job {
    /// Pořadí bloku v seznamu bloků kroku.
    pub block: usize,
    pub start: usize,
    pub count: usize,
}

/// Rozdělí bloky na úlohy. S `split` jsou úlohy malé (`JOB_CELLS`), aby se práce dala
/// vyrovnat mezi vlákna; bez něj jsou to kusy po `CHUNK_CELLS` jako dřív. Řádky jsou
/// nezávislé, takže rozdělení výsledek nemění (jen mez paměti a rychlost).
pub fn jobs(blocks: &[&PoolBlock], groups: usize, split: bool) -> Vec<Job> {
    let mut out = Vec::new();
    for (block, pool) in blocks.iter().enumerate() {
        let stride = (groups * pool.capacity).max(1);
        let cap = if split { JOB_CELLS } else { CHUNK_CELLS };
        let step = (cap / stride).clamp(1, (CHUNK_CELLS / stride).max(1));
        let mut start = 0;
        while start < pool.len() {
            let count = step.min(pool.len() - start);
            out.push(Job {
                block,
                start,
                count,
            });
            start += count;
        }
    }
    out
}

impl BlockOutcome {
    /// Připojí výsledek dalšího kusu téhož bloku (kusy v pořadí řádků).
    pub fn append(&mut self, mut other: BlockOutcome) {
        self.rows.append(&mut other.rows);
        self.milestones.append(&mut other.milestones);
        self.established.append(&mut other.established);
        self.extinct.append(&mut other.extinct);
        self.grammar.append(&mut other.grammar);
        self.crossings.append(&mut other.crossings);
        self.activations.append(&mut other.activations);
        self.trace.append(&mut other.trace);
        self.forgotten.append(&mut other.forgotten);
    }
}

/// Spočítá nový stav řádků `[start, start + count)` bloku a jejich události ze starého stavu
/// světa. Uvnitř úlohy je vše na jednom vlákně; souběh dělají úlohy.
#[allow(clippy::too_many_arguments)]
pub fn transmit_rows(
    world: &World,
    inputs: &StepInputs,
    params: &TransmissionParams,
    pressures: &Pressures<'_>,
    block: &PoolBlock,
    factors: &BlockFactors,
    start: usize,
    count: usize,
    trace: bool,
) -> BlockOutcome {
    let groups = inputs.axis.len();
    let slots = block.capacity;
    let stride = groups * slots;
    let mut outcome = BlockOutcome::default();
    let mut scratch: Vec<HearScratch> = Vec::new();
    let activation_share = world.params.activation_share;
    let has_table = world.table.is_some();
    let stop = start + count;
    let mut current = vec![0.0; count * stride];
    let mut previous = vec![0.0; count * stride];
    let mut present = Vec::with_capacity(count * groups);
    let mut slot_keys = Vec::with_capacity(count * slots);
    for local in 0..count {
        let row = start + local;
        block.cells.row_dense(
            row,
            &mut current[local * stride..(local + 1) * stride],
            &mut previous[local * stride..(local + 1) * stride],
        );
        present.extend_from_slice(&block.present[row]);
        slot_keys.extend_from_slice(&block.keys[row]);
    }
    let shape = Shape {
        variables: count,
        groups,
        slots,
    };
    let network = Network {
        components: &inputs.components,
        alone: &inputs.alone,
        alone_weight: &inputs.alone_weight,
    };
    let flows: Vec<Flow<'_>> = inputs
        .cross
        .iter()
        .zip(&factors.flows)
        .map(|(flow, factor)| Flow {
            factor: &factor[start..stop],
            components: &flow.components,
        })
        .collect();
    let channels: Vec<Channel<'_>> = inputs
        .sides
        .iter()
        .zip(&factors.sides)
        .map(|(side, factor)| Channel {
            factor: &factor[start..stop],
            learners: &side.learners,
            sources: &side.sources,
            weights: &side.weights,
        })
        .collect();
    let mut heard = vec![0.0; count * stride];
    hear(
        shape,
        &current,
        &present,
        &network,
        &flows,
        &channels,
        &mut scratch,
        1,
        &mut heard,
    );
    let mut fitness = vec![0.0; count * stride];
    pressures.fitness(block, start, count, &current, &heard, &mut fitness);
    let cohorts = Cohorts {
        drift_scale: &inputs.drift_scale,
        renewal: &inputs.renewal,
        loss_floor: &inputs.loss_floor,
        row_keys: &inputs.row_keys,
        selection: params.selection,
        kappa: params.kappa,
        adult_rate: params.adult_rate,
        establish_threshold: params.establish_threshold,
        completion_share: params.completion_share,
        forget_share: world.params.activation_share,
    };
    let forgotten = forgotten_mask(world, inputs, block, start, count);
    let state = State {
        current: &current,
        previous: &previous,
        present: &present,
        heard: &heard,
        fitness: Some(&fitness),
        slot_keys: &slot_keys,
        forgotten: forgotten.as_deref(),
    };
    let mut updated = vec![0.0; count * stride];
    let mut baseline = vec![0.0; count * stride];
    let mut marks = vec![0_i8; count * stride];
    settle(
        shape,
        &state,
        &cohorts,
        1,
        &mut updated,
        &mut baseline,
        &mut marks,
    );
    for (cell, &mark) in marks.iter().enumerate().filter(|(_, &mark)| mark != 0) {
        let (local, rest) = (cell / stride, cell % stride);
        let (column, slot) = (rest / slots, rest % slots);
        let row = start + local;
        outcome.forgotten.push((
            block.variables[row],
            inputs.axis[column],
            block.slots[row][slot],
            mark == FORGET,
        ));
        debug_assert!(mark == FORGET || mark == REMEMBER);
    }
    for local in 0..count {
        let row = start + local;
        let before = &current[local * stride..(local + 1) * stride];
        let after = &updated[local * stride..(local + 1) * stride];
        events(
            world,
            inputs,
            block,
            row,
            before,
            after,
            has_table,
            activation_share,
            trace,
            &mut outcome,
        );
        outcome.rows.push(Row::from_dense(
            after,
            &baseline[local * stride..(local + 1) * stride],
            groups,
            slots,
            slots,
        ));
    }
    outcome
}

/// Zapomenuté varianty řádků `[start, start + count)` jako pole `řádky × skupiny × sloty`;
/// `None`, když žádný z řádků nic zapomenutého nemá.
fn forgotten_mask(
    world: &World,
    inputs: &StepInputs,
    block: &PoolBlock,
    start: usize,
    count: usize,
) -> Option<Vec<bool>> {
    let memory = &world.transfer.forgotten;
    if memory.is_empty() {
        return None;
    }
    let (groups, slots) = (inputs.axis.len(), block.capacity);
    let stride = groups * slots;
    let mut mask: Option<Vec<bool>> = None;
    for local in 0..count {
        let row = start + local;
        let Some(entries) = memory.get(&block.variables[row].0) else {
            continue;
        };
        for &(group, variant) in entries {
            let group = GroupId(group);
            let column = match world.live.column(group) {
                Some(column) if inputs.axis.get(column) == Some(&group) => column,
                _ => match inputs.axis.iter().position(|&g| g == group) {
                    Some(column) => column,
                    None => continue,
                },
            };
            let Some(slot) = block.slots[row].iter().position(|v| v.0 == variant) else {
                continue;
            };
            mask.get_or_insert_with(|| vec![false; count * stride])
                [local * stride + column * slots + slot] = true;
        }
    }
    mask
}

/// Události řádku z podílů před krokem a po něm (buňky `skupina × slot`).
#[allow(clippy::too_many_arguments)]
fn events(
    world: &World,
    inputs: &StepInputs,
    block: &PoolBlock,
    row: usize,
    before: &[f64],
    after: &[f64],
    has_table: bool,
    activation_share: f64,
    trace: bool,
    outcome: &mut BlockOutcome,
) {
    let (groups, slots) = (inputs.axis.len(), block.capacity);
    let variable = block.variables[row];
    let kind = world.variables.kind[variable.index()];
    let variants = &block.slots[row];
    let innovation = |slot: usize| {
        let variant = variants[slot];
        !variant.is_none() && world.variants.innovation[variant.index()]
    };
    // Milníky a ustálení inovací.
    for slot in (0..slots).filter(|&s| innovation(s)) {
        for g in 0..groups {
            let (b, a) = (before[g * slots + slot], after[g * slots + slot]);
            let (first, last) = (reached(b), reached(a));
            for level in first..last {
                outcome
                    .milestones
                    .push((variable, variants[slot], inputs.axis[g], level));
            }
            if a == 1.0 && b < 1.0 {
                outcome
                    .established
                    .push((variable, variants[slot], inputs.axis[g]));
            }
        }
        let had = (0..groups).any(|g| before[g * slots + slot] > 0.0);
        let has = (0..groups).any(|g| after[g * slots + slot] > 0.0);
        if had && !has {
            outcome.extinct.push((variable, variants[slot]));
        }
    }
    // Konstrukční rozdělení, které se ve skupině změnilo.
    if kind == VariableKind::Construction {
        for g in 0..groups {
            if (0..slots).any(|s| before[g * slots + s] != after[g * slots + s]) {
                outcome.grammar.push((variable, inputs.axis[g]));
            }
        }
    }
    if has_table {
        // Odchody a příchody slov přes polovinu; příchody se přidají až po odchodech celého bloku,
        // proto se drží zvlášť na konci `outcome.crossings` (viz `finish_crossings`).
        if kind == VariableKind::Lexical {
            for g in 0..groups {
                for slot in 0..slots {
                    let variant = variants[slot];
                    if variant.is_none() {
                        continue;
                    }
                    let Payload::Lexical { morpheme, .. } =
                        &world.variants.payload[variant.index()]
                    else {
                        continue;
                    };
                    if morpheme.is_none() {
                        continue;
                    }
                    let (b, a) = (before[g * slots + slot], after[g * slots + slot]);
                    let enter = b < DOMINANCE && a >= DOMINANCE;
                    let leave = b >= DOMINANCE && a < DOMINANCE;
                    if enter || leave {
                        outcome.crossings.push(Crossing {
                            group: inputs.axis[g],
                            variable,
                            morpheme: MorphemeId(morpheme.0),
                            enter,
                        });
                    }
                }
            }
        }
        if let Some(slot) = tracked_slot(world, block, row) {
            for g in 0..groups {
                if after[g * slots + slot] >= activation_share {
                    outcome.activations.push((inputs.axis[g], variable));
                }
            }
        }
    }
    if trace {
        for slot in (0..slots).filter(|&s| innovation(s)) {
            for g in 0..groups {
                let (b, a) = (before[g * slots + slot], after[g * slots + slot]);
                if b > 0.0 || a > 0.0 {
                    outcome.trace.push((variants[slot], inputs.axis[g], a));
                }
            }
        }
    }
}

/// Odchody před příchody (Python: kořen, který jeden pojem opouští a druhý přebírá, ze slovní
/// zásoby na okamžik nevypadne). Zachová pořadí uvnitř skupiny odchodů i příchodů.
pub fn leaves_before_enters(crossings: &mut [Crossing]) {
    crossings.sort_by_key(|c| c.enter);
}

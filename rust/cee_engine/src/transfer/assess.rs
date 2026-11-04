//! Hodnocení změn pro tlaky nad hodnocením (zrcadlo `cee.v2.assessment` a `morphology.assess`).
//!
//! **Zvukové procesy** se hodnotí nad vzorkem nejčastějších slov kódu (`SAMPLE_WORDS`): kolik
//! slovní zásoby změna zasáhne, kolik nových homofonů vyrobí, jestli slova nezkrátí a jak změní
//! příznakovost a rozptyl samohlásek. K tomu je potřeba banka tvarů s tabulkami procesů, kterou
//! výpočet **mění** (nové tvary, mapy hlásek), a proto jde přenos dvěma průchody: nejdřív
//! [`refresh`] (má `&mut World`) spočítá hodnocení všech buněk, ke kterým změna dolehne, a uloží
//! je do [`Assessments`]; potom tlaky čtou uložené hodnoty ze `&World` (`seams::assess_cells`).
//! Hodnocení platí, dokud se nezmění verze kódu, nejvýš `STALE_TICKS` ticků (jako v Pythonu);
//! uložená hodnocení jsou součástí kontrolního bodu, aby výsledek nezávisel na obnově.
//!
//! **Analogické změny tvarů** se hodnotí rovnou ze stavu kódu (`form_cells`): je to čistá funkce
//! stavu a neměnné pohledy morfologie (`class_stats`), takže nic neukládá.
//!
//! Vzorek (výběr slov, váhy a čísla jejich tvarů) je odvozený stav v [`Sample`]; je to čistá
//! funkce stavu kódu a po obnově z kontrolního bodu se postaví znovu.

use serde::{Deserialize, Serialize};

use cee_core::bank::Outcome;

use crate::ids::{GroupId, MorphemeId, ProcessId, VariableId};
use crate::model::lexicon::{ProcessDef, Stress};
use crate::model::repertoire::VariableKind;
use crate::morphology::{apply_form_change, citation_id, class_stats, concept_totals, usage_frequency};
use crate::phonology::rows::{resolve_maps, row_of};
use crate::segments::SegmentTable;
use crate::transfer::assessed::Assessment;
use crate::transfer::network::StepInputs;
use crate::world::World;

/// Hodnocení se přepočítá nejdřív po tolika krocích, i když se verze kódu mění.
pub const STALE_TICKS: u32 = 8;
/// Hodnotí se nejčastější slova; cena hodnocení tak nezávisí na velikosti slovníku.
pub const SAMPLE_WORDS: usize = 120;
/// Nejmenší váha slova ve vzorku.
const MIN_WEIGHT: f64 = 0.01;

/// Uložené hodnocení procesu v jedné skupině.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Stored {
    pub variable: u32,
    /// Verze kódu (`PhonologyState::version`), pro kterou hodnocení platí.
    pub version: u64,
    pub tick: u32,
    pub value: Assessment,
}

/// Uložená hodnocení procesů podle skupiny (číslo skupiny), v každé seřazená podle proměnné.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Assessments {
    pub groups: Vec<Vec<Stored>>,
}

impl Assessments {
    pub fn get(&self, group: GroupId, variable: VariableId) -> Option<&Stored> {
        let list = self.groups.get(group.index())?;
        list.binary_search_by_key(&variable.0, |entry| entry.variable)
            .ok()
            .map(|at| &list[at])
    }

    fn put(&mut self, group: GroupId, entry: Stored) {
        if self.groups.len() <= group.index() {
            self.groups.resize(group.index() + 1, Vec::new());
        }
        let list = &mut self.groups[group.index()];
        match list.binary_search_by_key(&entry.variable, |e| e.variable) {
            Ok(at) => list[at] = entry,
            Err(at) => list.insert(at, entry),
        }
    }
}

/// Vzorek slov jednoho kódu: výběr a váhy (podle stavu slovní zásoby a četností pojmů)
/// a čísla aktuálních tvarů (podle verze kódu). Morfémy jsou v pořadí jmen.
#[derive(Clone, Debug, Default)]
pub struct Sample {
    /// Pro co platí výběr: verze slovní zásoby, verze četností pojmů, počet morfémů.
    selection: Option<(u64, u64, usize)>,
    pub morphemes: Vec<MorphemeId>,
    pub weights: Vec<f64>,
    pub total: f64,
    /// Verze kódu, pro kterou platí `ids`.
    forms: Option<u64>,
    pub ids: Vec<i64>,
}

impl Sample {
    /// Dorovná vzorek na stav kódu skupiny.
    fn sync(&mut self, world: &World, group: GroupId) {
        let code = world.groups.main_code(group);
        let state = &code.phonology;
        let key = (
            state.lexicon_version,
            world.concepts.version,
            world.morphemes.len(),
        );
        if self.selection != Some(key) {
            let (morphemes, weights, total) = select(world, group);
            self.morphemes = morphemes;
            self.weights = weights;
            self.total = total;
            self.selection = Some(key);
            self.forms = None;
        }
        if self.forms != Some(state.version) {
            self.ids = self
                .morphemes
                .iter()
                .map(|&m| i64::from(world.unit_of(group, m).form))
                .collect();
            self.forms = Some(state.version);
        }
    }
}

/// Výběr vzorku: nejčastější tvary slovní zásoby (shodu rozhodne jméno), v pořadí jmen,
/// s váhami nejméně 0,01 (`top_words`, `clipped_frequencies`).
fn select(world: &World, group: GroupId) -> (Vec<MorphemeId>, Vec<f64>, f64) {
    let code = world.groups.main_code(group);
    let totals = concept_totals(world, group);
    let names = &world.registry.morphemes;
    let mut keyed: Vec<(f64, MorphemeId)> = code
        .phonology
        .vocabulary
        .iter()
        .map(|m| (usage_frequency(world, &totals, m), m))
        .collect();
    keyed.sort_by(|a, b| {
        b.0.total_cmp(&a.0)
            .then_with(|| names.name(a.1 .0).cmp(names.name(b.1 .0)))
    });
    keyed.truncate(SAMPLE_WORDS);
    keyed.sort_by(|a, b| names.name(a.1 .0).cmp(names.name(b.1 .0)));
    let weights: Vec<f64> = keyed.iter().map(|&(f, _)| f.max(MIN_WEIGHT)).collect();
    let total: f64 = weights.iter().sum();
    (
        keyed.into_iter().map(|(_, m)| m).collect(),
        weights,
        if total == 0.0 { 1.0 } else { total },
    )
}

/// Může změna ovlivnit rozptyl samohlásek? (cílí na samohlásku a není nepřízvučná)
fn shapes_vowels(def: &ProcessDef, table: &SegmentTable) -> bool {
    def.stress != Stress::Unstressed && def.segment.is_some_and(|s| table.is_vowel(s))
}

/// Vzdálenost samohlásky k nejbližší jiné ze `others` (0, když žádná jiná není).
fn nearest(table: &SegmentTable, vowel: i32, others: &[i32]) -> f64 {
    let (height, back, rounded) = table.vowel_coordinates(vowel);
    let mut best: Option<f64> = None;
    for &other in others {
        if other == vowel {
            continue;
        }
        let (h, b, r) = table.vowel_coordinates(other);
        let distance = ((height - h).powi(2) + (back - b).powi(2) + 0.25 * (rounded - r).powi(2)).sqrt();
        best = Some(best.map_or(distance, |found| found.min(distance)));
    }
    best.unwrap_or(0.0)
}

/// Zisk rozptylu samohlásek (`_dispersion_gain`): o kolik se nový vokál vzdálí od sousedů oproti
/// vokálu, ze kterého vznikl; `before` a `after` jsou samohlásky slovní zásoby před změnou a po ní.
fn dispersion_gain(
    def: &ProcessDef,
    table: &SegmentTable,
    before: &[i32],
    after: &[i32],
) -> f64 {
    if !shapes_vowels(def, table) {
        return 0.0;
    }
    let Some(output) = def.segment else {
        return 0.0;
    };
    if before.contains(&output) {
        return 0.0;
    }
    let source = before
        .iter()
        .filter(|&&v| def.target.mask.get(v as usize).copied().unwrap_or(false))
        .map(|&v| nearest(table, v, before))
        .fold(None, |best: Option<f64>, d| Some(best.map_or(d, |b| b.max(d))));
    match source {
        None => 0.0,
        Some(source) => nearest(table, output, after) - source,
    }
}

/// Je buňka paradigmatu morfému nahrazena jinou konstrukcí (`_redundant_cell`)?
fn redundant_cell(world: &World, group: GroupId, morpheme: MorphemeId) -> bool {
    let (class, cell) = (
        world.morphemes.word_class[morpheme.index()],
        world.morphemes.cell[morpheme.index()],
    );
    if cell.is_none() {
        return false;
    }
    crate::syntax::catalog(world).iter().any(|f| {
        let same_class = f
            .word_class()
            .and_then(|n| world.registry.word_class_of(n))
            == Some(class);
        let same_cell = f
            .cell
            .as_deref()
            .and_then(|c| world.registry.cells.get(c))
            .map(crate::ids::CellId)
            == Some(cell);
        same_class && same_cell && crate::syntax::compensated(world, group, &f.id)
    })
}

/// Cena dvojice nových homofonů (`_pair`): geometrický průměr frekvencí, u tvarů téhož lexému
/// s vahou paradigmatu a vahou nadbytečné buňky.
fn pair_cost(world: &World, group: GroupId, sample: &Sample, first: usize, second: usize) -> f64 {
    let mut mass = (sample.weights[first] * sample.weights[second]).sqrt();
    let (a, b) = (sample.morphemes[first], sample.morphemes[second]);
    if world.morphemes.lexeme_id(a) == world.morphemes.lexeme_id(b) {
        mass *= world.params.paradigm_merge_weight;
        if redundant_cell(world, group, a) || redundant_cell(world, group, b) {
            mass *= world.params.redundant_merge_weight;
        }
    }
    mass
}

/// Hodnocení procesu ve skupině nad jejím vzorkem (`assess`).
fn assess_group(
    world: &mut World,
    sample: &Sample,
    group: GroupId,
    row: usize,
    process: ProcessId,
) -> Result<Assessment, String> {
    if sample.ids.is_empty() {
        return Ok([0.0; 5]);
    }
    let rule = world.groups.main_code(group).stress_rule.as_rule();
    let table = world.table.clone().ok_or("svět nemá tabulku hlásek")?;
    let def = world
        .process(process)
        .cloned()
        .ok_or_else(|| format!("proces č. {} nemá definici", process.0))?;
    let shapes = shapes_vowels(&def, &table);
    let changed = loop {
        match world.bank.bank.results(row, rule, &sample.ids)? {
            Outcome::Done(changed) => break changed,
            Outcome::Needs(segments) => resolve_maps(world, &[(row, segments)])?,
        }
    };
    let raw = world.bank.bank.assess_row(
        &sample.ids,
        &changed,
        &sample.weights,
        sample.ids.len(),
        shapes,
    );
    if raw.mass <= 0.0 {
        return Ok([0.0; 5]);
    }
    let mut merge = 0.0;
    for &(first, second) in &raw.pairs {
        merge += pair_cost(world, group, sample, first as usize, second as usize);
    }
    Ok([
        raw.mass / sample.total,
        merge / sample.total,
        raw.short / raw.mass,
        raw.marked / raw.mass,
        dispersion_gain(&def, &table, &raw.before, &raw.after),
    ])
}

/// Ke každému sloupci, který slyší změnu od `present`, přidá sloupce, které ji mohou slyšet
/// (učící se skupiny, jejichž zdroj ji nese): sítě, vazby mezi jazyky i kanály mimo síť.
fn learners_of(inputs: &StepInputs) -> Vec<Vec<usize>> {
    let mut learners: Vec<Vec<usize>> = vec![Vec::new(); inputs.axis.len()];
    let mut add = |learner: usize, source: usize| {
        if learner != source {
            learners[source].push(learner);
        }
    };
    let mut scan = |components: &[cee_core::transmission::Component]| {
        for component in components {
            for (position, &learner) in component.members.iter().enumerate() {
                let (from, to) = (
                    component.links.start[position],
                    component.links.start[position + 1],
                );
                for &source in &component.links.source[from..to] {
                    add(learner, component.members[source]);
                }
            }
        }
    };
    scan(&inputs.components);
    for flow in &inputs.cross {
        scan(&flow.components);
    }
    for side in &inputs.sides {
        for (&learner, &source) in side.learners.iter().zip(&side.sources) {
            add(learner, source);
        }
    }
    learners
}

/// Spočítá a uloží hodnocení všech sledovaných procesů ve skupinách, kam dolehnou (mají je
/// nebo je mohou slyšet), pokud uložené hodnocení nevypršelo. Volá se před přenosem kroku.
pub fn refresh(world: &mut World, inputs: &StepInputs) -> Result<(), String> {
    if world.table.is_none() {
        return Ok(());
    }
    // Sledované procesy a sloupce, kam dolehnou.
    struct Job {
        variable: VariableId,
        process: ProcessId,
        columns: Vec<usize>,
    }
    let mut jobs: Vec<Job> = Vec::new();
    let mut learners: Option<Vec<Vec<usize>>> = None;
    for block in world.live.blocks.values() {
        for (row, &variable) in block.variables.iter().enumerate() {
            if world.variables.kind[variable.index()] != VariableKind::Process {
                continue;
            }
            let process = world.variables.process[variable.index()];
            if process.is_none() || world.process(process).is_none() {
                continue;
            }
            let Some(&changed) = world.transfer.derived.changed.get(variable.index()) else {
                continue;
            };
            let Some(slot) = block.slots[row].iter().position(|v| v.0 == changed) else {
                continue;
            };
            let (present, _) = block.range_of(row, slot);
            if present.is_empty() {
                continue;
            }
            let learners = learners.get_or_insert_with(|| learners_of(inputs));
            let mut columns: Vec<usize> = Vec::new();
            for &column in &present {
                columns.push(column as usize);
                columns.extend_from_slice(&learners[column as usize]);
            }
            columns.sort_unstable();
            columns.dedup();
            jobs.push(Job {
                variable,
                process,
                columns,
            });
        }
    }
    if jobs.is_empty() {
        return Ok(());
    }
    let tick = inputs.tick;
    let mut samples = std::mem::take(&mut world.transfer.derived.samples);
    let result = (|| -> Result<(), String> {
        for job in &jobs {
            let row = row_of(world, job.process)?;
            for &column in &job.columns {
                let group = inputs.axis[column];
                let version = world.groups.main_code(group).phonology.version;
                let fresh = world
                    .transfer
                    .assessments
                    .get(group, job.variable)
                    .is_some_and(|s| s.version == version || tick.saturating_sub(s.tick) < STALE_TICKS);
                if fresh {
                    continue;
                }
                if samples.len() <= group.index() {
                    samples.resize(group.index() + 1, Sample::default());
                }
                samples[group.index()].sync(world, group);
                let value = assess_group(world, &samples[group.index()], group, row, job.process)?;
                world.transfer.assessments.put(
                    group,
                    Stored {
                        variable: job.variable.0,
                        version,
                        tick,
                        value,
                    },
                );
            }
        }
        Ok(())
    })();
    world.transfer.derived.samples = samples;
    result
}

/// Uložené hodnocení procesu ve sloupcích osy (`None` = hodnocení chybí).
pub fn process_cells(
    world: &World,
    variable: VariableId,
    columns: &[usize],
) -> Vec<Option<Assessment>> {
    let axis = &world.live.group_ids;
    columns
        .iter()
        .map(|&column| {
            world
                .transfer
                .assessments
                .get(axis[column], variable)
                .map(|stored| stored.value)
        })
        .collect()
}

/// Hodnocení analogické změny tvaru ve sloupcích osy: `[zisk, frekvence, splynutí před,
/// splynutí po, 0]`; `None`, když by změna tvar nezměnila (`morphology._assess_reference`).
pub fn form_cells(
    world: &World,
    variable: VariableId,
    columns: &[usize],
) -> Vec<Option<Assessment>> {
    let Some(change) = world.form_changes.get(&variable) else {
        return vec![None; columns.len()];
    };
    let axis = &world.live.group_ids;
    columns
        .iter()
        .map(|&column| {
            let group = axis[column];
            let new = apply_form_change(world, group, change)?;
            let current = world.unit_of(group, change.unit);
            let citation = world.bank.form(citation_id(world, group, change.unit));
            let gain = if change.operation == crate::model::lexicon::FormOperation::Level {
                1.0
            } else if change.operation.lexeme_wide() {
                0.0
            } else {
                let stats = class_stats(world, group);
                let class = world.morphemes.word_class[change.unit.index()];
                let cell = world.morphemes.cell[change.unit.index()];
                stats.share(class, cell, change.exponent)
                    - stats.share(class, cell, current.exponent)
            };
            let totals = concept_totals(world, group);
            let frequency =
                usage_frequency(world, &totals, world.morphemes.lexeme_id(change.unit));
            Some([
                gain,
                frequency,
                f64::from(world.bank.form(current.form) == citation),
                f64::from(new.form == citation),
                0.0,
            ])
        })
        .collect()
}

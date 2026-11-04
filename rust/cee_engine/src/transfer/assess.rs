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

use std::borrow::Cow;
use std::collections::HashMap;

use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use cee_core::bank::Outcome;

use crate::ids::{GroupId, MorphemeId, ProcessId, VariableId};
use crate::model::lexicon::{ProcessDef, Stress};
use crate::model::repertoire::VariableKind;
use crate::morphology::{
    apply_form_change, citation_id, class_stats, concept_totals, usage_frequency,
};
use crate::parallel;
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
    let _t = crate::timing::scope("views/sample-select");
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
        let distance =
            ((height - h).powi(2) + (back - b).powi(2) + 0.25 * (rounded - r).powi(2)).sqrt();
        best = Some(best.map_or(distance, |found| found.min(distance)));
    }
    best.unwrap_or(0.0)
}

/// Zisk rozptylu samohlásek (`_dispersion_gain`): o kolik se nový vokál vzdálí od sousedů oproti
/// vokálu, ze kterého vznikl; `before` a `after` jsou samohlásky slovní zásoby před změnou a po ní.
fn dispersion_gain(def: &ProcessDef, table: &SegmentTable, before: &[i32], after: &[i32]) -> f64 {
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
        .fold(None, |best: Option<f64>, d| {
            Some(best.map_or(d, |b| b.max(d)))
        });
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
        let same_class =
            f.word_class().and_then(|n| world.registry.word_class_of(n)) == Some(class);
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

/// Hodnocení procesu ve skupině nad jejím vzorkem (`assess`), část první: výsledky procesu
/// pro slova vzorku. Mění banku (nové tvary, mapy hlásek), proto běží sekvenčně v kanonickém
/// pořadí; vrací tvary slov po změně.
fn changed_forms(
    world: &mut World,
    sample: &Sample,
    group: GroupId,
    row: usize,
) -> Result<Vec<i64>, String> {
    let rule = world.groups.main_code(group).stress_rule.as_rule();
    loop {
        match world.bank.bank.results(row, rule, &sample.ids)? {
            Outcome::Done(changed) => return Ok(changed),
            Outcome::Needs(segments) => resolve_maps(world, &[(row, segments)])?,
        }
    }
}

/// Hodnocení procesu ve skupině, část druhá: jen čtení (svět i banka), proto může běžet
/// souběžně pro víc dvojic (skupina, proces).
fn assess_group(
    world: &World,
    sample: &Sample,
    group: GroupId,
    process: ProcessId,
    changed: &[i64],
) -> Result<Assessment, String> {
    if sample.ids.is_empty() {
        return Ok([0.0; 5]);
    }
    let table = world.table.as_ref().ok_or("svět nemá tabulku hlásek")?;
    let def = world
        .process(process)
        .ok_or_else(|| format!("proces č. {} nemá definici", process.0))?;
    let shapes = shapes_vowels(def, table);
    let raw = world.bank.bank.assess_row_ready(
        &sample.ids,
        changed,
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
        dispersion_gain(def, table, &raw.before, &raw.after),
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
    // Dvouprůchodový návrh: (1) sekvenčně v kanonickém pořadí (proces, sloupec) se vyberou dvojice,
    // které je třeba přepočítat, a spočítají se výsledky procesu (mění banku, přidělují čísla
    // nových tvarů); (2) souběžně se každá dvojice vyhodnotí jen čtením; (3) sekvenčně se
    // hodnocení uloží v témže pořadí.
    struct Item {
        job: usize,
        group: GroupId,
        version: u64,
        changed: Vec<i64>,
    }
    let mut samples = std::mem::take(&mut world.transfer.derived.samples);
    let result = (|| -> Result<(), String> {
        let mut wanted: Vec<(usize, GroupId, u64)> = Vec::new();
        for (at, job) in jobs.iter().enumerate() {
            for &column in &job.columns {
                let group = inputs.axis[column];
                let version = world.groups.main_code(group).phonology.version;
                let fresh = world
                    .transfer
                    .assessments
                    .get(group, job.variable)
                    .is_some_and(|s| {
                        s.version == version || tick.saturating_sub(s.tick) < STALE_TICKS
                    });
                if !fresh {
                    wanted.push((at, group, version));
                }
            }
        }
        // Vzorky skupin se dorovnají souběžně (každá skupina má vlastní vzorek, svět se jen čte).
        let top = wanted.iter().map(|w| w.1.index() + 1).max().unwrap_or(0);
        if samples.len() < top {
            samples.resize(top, Sample::default());
        }
        let mut needed = vec![false; samples.len()];
        for &(_, group, _) in &wanted {
            needed[group.index()] = true;
        }
        {
            let shared = &*world;
            let sync = |(at, sample): (usize, &mut Sample)| {
                if needed[at] {
                    sample.sync(shared, GroupId(at as u32));
                }
            };
            if parallel::worth_splitting(wanted.len() * SAMPLE_WORDS) {
                samples.par_iter_mut().enumerate().for_each(sync);
            } else {
                samples.iter_mut().enumerate().for_each(sync);
            }
        }
        let mut rows: Vec<usize> = Vec::with_capacity(jobs.len());
        for job in &jobs {
            rows.push(row_of(world, job.process)?);
        }
        // Už známé výsledky procesu se přečtou souběžně (jen čtení banky); zbytek sekvenčně v pořadí.
        let known: Vec<Option<Vec<i64>>> = {
            let bank = &world.bank.bank;
            let samples = &samples;
            let rows = &rows;
            let find = |&(at, group, _): &(usize, GroupId, u64)| {
                let ids = &samples[group.index()].ids;
                if ids.is_empty() {
                    return Some(Vec::new());
                }
                let rule = world.groups.main_code(group).stress_rule.as_rule();
                bank.known_results(rows[at], rule, ids)
            };
            if parallel::worth_splitting(wanted.len() * SAMPLE_WORDS) {
                wanted.par_iter().map(find).collect()
            } else {
                wanted.iter().map(find).collect()
            }
        };
        let mut items: Vec<Item> = Vec::with_capacity(wanted.len());
        for (&(at, group, version), known) in wanted.iter().zip(known) {
            let changed = match known {
                Some(changed) => changed,
                None => changed_forms(world, &samples[group.index()], group, rows[at])?,
            };
            items.push(Item {
                job: at,
                group,
                version,
                changed,
            });
        }
        let values: Vec<Result<Assessment, String>> = {
            let shared = &*world;
            let samples = &samples;
            let jobs = &jobs;
            let one = |item: &Item| {
                assess_group(
                    shared,
                    &samples[item.group.index()],
                    item.group,
                    jobs[item.job].process,
                    &item.changed,
                )
            };
            if parallel::worth_splitting(items.len() * SAMPLE_WORDS) {
                items.par_iter().map(one).collect()
            } else {
                items.iter().map(one).collect()
            }
        };
        // Příznakovost tvarů, kterou souběh dopočítával, se uloží (v pořadí položek).
        for item in &items {
            let ids = &samples[item.group.index()].ids;
            if !world.bank.bank.all_marked(ids, &item.changed) {
                world.bank.bank.ensure_marked(ids, &item.changed);
            }
        }
        for (item, value) in items.iter().zip(values) {
            world.transfer.assessments.put(
                item.group,
                Stored {
                    variable: jobs[item.job].variable.0,
                    version: item.version,
                    tick,
                    value: value?,
                },
            );
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
    form_cells_with(world, variable, columns, |column| {
        Cow::Owned(concept_totals(world, world.live.group_ids[column]))
    })
}

/// [`form_cells`] s úhrny pojmů skupin dodanými volajícím (`totals(sloupec)`), aby je tlaky
/// nepočítaly znovu pro každý řádek.
pub fn form_cells_with<'t>(
    world: &World,
    variable: VariableId,
    columns: &[usize],
    totals: impl Fn(usize) -> Cow<'t, HashMap<MorphemeId, f64>>,
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
            let totals = totals(column);
            let frequency = usage_frequency(world, &totals, world.morphemes.lexeme_id(change.unit));
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

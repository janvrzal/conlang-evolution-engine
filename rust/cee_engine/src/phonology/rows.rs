//! Procesní proměnné a jejich řádky v bance tvarů.
//!
//! [`register`] založí z kandidáta (popisu zvukové změny, který postavil index) procesní
//! proměnnou, její dvě varianty a `ProcessDef` (`phonology.register`): tatáž změna je tatáž
//! proměnná, takže se paralelní inovace sčítají. [`row_of`] zaregistruje proces v bance tvarů
//! (`cee_core::bank`), kde se nad řádkem procesu počítají tabulky výsledků podle tvarů
//! a pravidla přízvuku. Řádky jsou odvozený stav: po kopii světa se zaregistrují znovu.

use cee_core::bank::Bank;
use cee_core::candidates::{
    Candidate, Operation as CandidateOperation, Pat, SegTable, Stress as CandidateStress,
};
use cee_core::process::{Proc, MAP_UNRESOLVED};

use crate::ids::{GroupId, ProcessId, VariableId, VariantId};
use crate::model::lexicon::{Operation, ProcessDef, Stress};
use crate::model::repertoire::{variable_name, Origin, Payload, VariableKind};
use crate::phonology::index::snapshot;
use crate::rng::{stable_id, Part};
use crate::segments::{Pattern, SegmentTable};
use crate::world::World;

/// Jméno varianty „žádná změna“ procesní proměnné (`phonology.none_id`).
pub fn none_name(variable: &str) -> String {
    stable_id("variant", &[Part::Str("none"), Part::Str(variable)])
}

/// Jméno varianty „změna“ procesní proměnné (`phonology.changed_id`).
pub fn changed_name(variable: &str) -> String {
    stable_id("variant", &[Part::Str("changed"), Part::Str(variable)])
}

/// Procesní proměnná, její proces a varianta „změna“.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Registered {
    pub variable: VariableId,
    pub process: ProcessId,
    pub changed: VariantId,
}

fn pattern_of(pat: &Pat, table: &SegTable) -> Pattern {
    Pattern {
        key: pat.key(table),
        mask: pat.mask(table),
    }
}

/// `ProcessDef` z popisu kandidáta.
pub fn def_of(candidate: &Candidate, table: &SegTable) -> ProcessDef {
    let operation = match candidate.operation {
        CandidateOperation::Change => Operation::Change,
        CandidateOperation::Replace => Operation::Replace,
        CandidateOperation::Delete => Operation::Delete,
        CandidateOperation::InsertBefore => Operation::InsertBefore,
        CandidateOperation::Merge => Operation::MergeNext,
        CandidateOperation::Tone => Operation::Tone,
    };
    let stress = match candidate.stress {
        CandidateStress::Any => Stress::Any,
        CandidateStress::Stressed => Stress::Stressed,
        CandidateStress::Unstressed => Stress::Unstressed,
    };
    ProcessDef {
        family: cee_core::candidates::FAMILIES[candidate.family].to_owned(),
        target: pattern_of(&candidate.target, table),
        operation,
        changes: candidate.changes.clone(),
        segment: candidate.segment.map(|segment| segment as i32),
        left: candidate.left.as_ref().map(|pat| pattern_of(pat, table)),
        right: candidate.right.as_ref().map(|pat| pattern_of(pat, table)),
        right2: candidate.right2.as_ref().map(|pat| pattern_of(pat, table)),
        stress,
        medial: candidate.medial,
        ease: candidate.ease,
        clarity: candidate.clarity,
        reductive: candidate.reductive,
        label: candidate.label.clone(),
        allow: candidate
            .allow
            .iter()
            .filter_map(|mark| mark.chars().next())
            .collect(),
        tone: candidate.tone.map(|code| code as u32),
    }
}

/// Zaregistruje změnu: procesní proměnná `process:klíč` s variantami „žádná změna“ a „změna“.
///
/// Existující proměnná se jen vrátí. Nová dostane číslo procesu v registru, `ProcessDef`
/// (masky hlásek přes celou tabulku) a řádek v bance tvarů.
pub fn register(
    world: &mut World,
    candidate: &Candidate,
    change: &str,
    tick: u32,
    year: f64,
    group: GroupId,
) -> Result<Registered, String> {
    let table = snapshot();
    let key = candidate.key(table);
    let name = variable_name(VariableKind::Process, &key);
    if let Some(found) = world.registry.variables.get(&name) {
        let variable = VariableId(found);
        if variable.index() < world.variables.len() {
            let process = world.variables.process[variable.index()];
            let changed = world
                .registry
                .variants
                .get(&changed_name(&name))
                .map(VariantId)
                .ok_or_else(|| format!("proměnná {name} nemá variantu změny"))?;
            return Ok(Registered {
                variable,
                process,
                changed,
            });
        }
    }
    let none = world.registry.variant(&none_name(&name));
    let variable = world.store_variable(VariableKind::Process, &key, none);
    let process = world.registry.process(&name);
    world.variables.process[variable.index()] = process;
    let changed = world.registry.variant(&changed_name(&name));
    world.store_variant(
        &none_name(&name),
        variable,
        Payload::Process {
            process: ProcessId::NONE,
            changed: false,
        },
        Origin {
            change: None,
            tick,
            year,
            group: GroupId::NONE,
            parent: VariantId::NONE,
        },
    );
    world.store_variant(
        &changed_name(&name),
        variable,
        Payload::Process {
            process,
            changed: true,
        },
        Origin {
            change: Some(change.to_owned()),
            tick,
            year,
            group,
            parent: VariantId::NONE,
        },
    );
    if world.processes.len() <= process.index() {
        world.processes.resize(process.index() + 1, None);
    }
    world.processes[process.index()] = Some(def_of(candidate, table));
    let info = &mut world.sound.runtime.info;
    if info.len() <= process.index() {
        info.resize(process.index() + 1, (VariableId::NONE, VariantId::NONE));
    }
    info[process.index()] = (variable, changed);
    row_of(world, process)?;
    Ok(Registered {
        variable,
        process,
        changed,
    })
}

/// Rozdá zvukové změny rozběhnuté na startu (`LanguageSpec.processes`): kandidát rodiny
/// s daným popisem z inventáře jazyka se zaregistruje jako běžná procesní proměnná a každá
/// skupina jazyka ji dostane s počátečním podílem. Dok. 22, M7.3h.
pub fn seed_initial(world: &mut World) -> Result<(), String> {
    let seeds = std::mem::take(&mut world.initial_processes);
    for item in seeds {
        let Some(number) = world.registry.languages.get(&item.language) else {
            return Err(format!("processes: neznámý jazyk '{}'", item.language));
        };
        let groups: Vec<GroupId> = world
            .group_ids()
            .into_iter()
            .filter(|&g| world.groups.main_code(g).language.0 == number)
            .collect();
        let Some(&first) = groups.first() else {
            continue;
        };
        let built = cee_core::candidates::build(snapshot(), &item.inventory)?;
        let family = cee_core::candidates::FAMILIES
            .iter()
            .position(|f| *f == item.family)
            .ok_or_else(|| format!("processes: neznámá rodina '{}'", item.family))?;
        let candidate = built
            .candidates
            .iter()
            .find(|c| c.family == family && c.label == item.label)
            .cloned()
            .ok_or_else(|| {
                let labels: Vec<&str> = built
                    .candidates
                    .iter()
                    .filter(|c| c.family == family)
                    .map(|c| c.label.as_str())
                    .collect();
                format!(
                    "processes: rodina '{}' nemá v inventáři jazyka '{}' kandidáta '{}'; možnosti: {labels:?}",
                    item.family, item.language, item.label
                )
            })?;
        let year = world.start_year;
        let found = register(world, &candidate, &item.family, 0, year, first)?;
        let name = world.registry.variables.name(found.variable.0).to_owned();
        let none = world
            .registry
            .variants
            .get(&none_name(&name))
            .map(VariantId)
            .ok_or_else(|| format!("proměnná {name} nemá výchozí variantu"))?;
        for group in groups {
            let distribution = crate::model::repertoire::Distribution::from_pairs(
                vec![(none, 1.0 - item.share), (found.changed, item.share)],
                &world.registry.variants,
            );
            world
                .groups
                .main_code_mut(group)
                .repertoire
                .set(found.variable, distribution);
        }
    }
    Ok(())
}

/// Masky hlásek a parametry procesu pro banku tvarů (`FormBank._register_native`).
pub(crate) fn proc_of(def: &ProcessDef, table: &SegmentTable) -> Proc {
    let size = table.len() + 1;
    let side = |pattern: &Option<Pattern>| match pattern {
        Some(found) => found.mask.clone(),
        None => vec![true; size],
    };
    Proc {
        operation: match def.operation {
            Operation::Change => cee_core::process::OP_CHANGE,
            Operation::Replace => cee_core::process::OP_REPLACE,
            Operation::Delete => cee_core::process::OP_DELETE,
            Operation::InsertBefore => cee_core::process::OP_INSERT_BEFORE,
            Operation::InsertAfter => cee_core::process::OP_INSERT_AFTER,
            Operation::MergeNext => cee_core::process::OP_MERGE_NEXT,
            Operation::Tone => cee_core::process::OP_TONE,
        },
        stress: match def.stress {
            Stress::Any => cee_core::process::STRESS_NONE,
            Stress::Stressed => cee_core::process::STRESS_STRESSED,
            Stress::Unstressed => cee_core::process::STRESS_UNSTRESSED,
        },
        medial: def.medial,
        segment: def.segment.unwrap_or(-1),
        target: def.target.mask.clone(),
        left: side(&def.left),
        right: side(&def.right),
        right2: side(&def.right2),
        map: vec![MAP_UNRESOLVED; table.len()],
    }
}

/// Zaregistruje v bance všechny procesy světa, které tam ještě nejsou (po řadě podle čísla).
pub fn ensure_rows(world: &mut World) -> Result<(), String> {
    let Some(table) = world.table.clone() else {
        return Ok(());
    };
    // Fronty řadí shodné logity podle jmen morfémů (bajty UTF-8 jako body Unicode).
    let known = world.bank.bank.names.len();
    if known < world.registry.morphemes.len() {
        let names = world.registry.morphemes.names()[known..].to_vec();
        world.bank.bank.extend_names(known, names)?;
    }
    let runtime = &mut world.sound.runtime;
    if runtime.rows.len() < world.processes.len() {
        runtime.rows.resize(world.processes.len(), -1);
    }
    if world.bank.bank.proc_count() != runtime.row_process.len() {
        return Err(format!(
            "banka tvarů má {} procesů, ale řádky fonologie {}: procesy se do banky registrují jen přes phonology::row_of",
            world.bank.bank.proc_count(),
            runtime.row_process.len()
        ));
    }
    for (number, def) in world.processes.iter().enumerate() {
        if runtime.rows[number] >= 0 {
            continue;
        }
        let Some(def) = def else { continue };
        let row = runtime.row_process.len();
        world.bank.bank.register_proc(row, proc_of(def, &table))?;
        runtime.rows[number] = row as i32;
        runtime.row_process.push(ProcessId::new(number));
    }
    Ok(())
}

/// Řádek procesu v bance tvarů (proces se zaregistruje, když tam ještě není).
pub fn row_of(world: &mut World, process: ProcessId) -> Result<usize, String> {
    ensure_rows(world)?;
    match world.sound.runtime.rows.get(process.index()) {
        Some(&row) if row >= 0 => Ok(row as usize),
        _ => Err(format!("proces č. {} neexistuje", process.0)),
    }
}

/// Proměnná a varianta „změna“ procesu (z registru; pamatuje se).
pub fn info_of(world: &mut World, process: ProcessId) -> Result<(VariableId, VariantId), String> {
    let at = process.index();
    let info = &mut world.sound.runtime.info;
    if info.len() <= at {
        info.resize(at + 1, (VariableId::NONE, VariantId::NONE));
    }
    if info[at].0.is_none() {
        let name = world.registry.processes.name(process.0);
        let variable = world
            .registry
            .variables
            .get(name)
            .ok_or_else(|| format!("proces {name} nemá proměnnou"))?;
        let changed = world
            .registry
            .variants
            .get(&changed_name(name))
            .ok_or_else(|| format!("proces {name} nemá variantu změny"))?;
        info[at] = (VariableId(variable), VariantId(changed));
    }
    Ok(info[at])
}

/// Podíl varianty „změna“ procesu ve skupině (0, když ho skupina nemá).
pub fn changed_share(
    world: &World,
    group: GroupId,
    variable: VariableId,
    changed: VariantId,
) -> f64 {
    if world.live.contains(variable) && world.live.column(group).is_some() {
        return world
            .live
            .frequency(group, variable, changed)
            .unwrap_or(0.0);
    }
    world
        .stored(group, variable)
        .map_or(0.0, |distribution| distribution.frequency(changed))
}

/// Doplní výstupy operací `change` a `tone` pro hlásky, které si banka vyžádala
/// (nejbližší hlásku hledá tabulka hlásek, ne banka).
pub fn resolve_maps(world: &mut World, maps: &[(usize, Vec<i32>)]) -> Result<(), String> {
    let table = world.table.clone().ok_or("svět nemá tabulku hlásek")?;
    for (row, segments) in maps {
        let process = *world
            .sound
            .runtime
            .row_process
            .get(*row)
            .ok_or_else(|| format!("neznámý řádek procesu {row}"))?;
        let def = world
            .processes
            .get(process.index())
            .and_then(Option::as_ref)
            .ok_or_else(|| format!("proces č. {} nemá definici", process.0))?;
        let mut outputs = Vec::with_capacity(segments.len());
        for &segment in segments {
            let output = if def.operation == Operation::Tone {
                let code = def.tone.ok_or("proces s tónem nemá kód tónu")?;
                table.with_tone(segment, code)
            } else {
                let changes: Vec<(&str, &str)> = def
                    .changes
                    .iter()
                    .map(|(name, value)| (name.as_str(), value.as_str()))
                    .collect();
                table.changed(segment, &changes, &def.allow)?
            };
            outputs.push(output.map_or(-1, i64::from));
        }
        let wanted: Vec<i64> = segments.iter().map(|&segment| i64::from(segment)).collect();
        world.bank.bank.set_map(*row, &wanted, &outputs)?;
    }
    Ok(())
}

/// Banka tvarů světa (pro čtenáře mimo fonologii, např. hodnocení tlaků).
pub fn bank_of(world: &World) -> &Bank {
    &world.bank.bank
}

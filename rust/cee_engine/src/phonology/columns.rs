//! Sloupce morfémů a četnosti užití pro jádro front, sklony slov.
//!
//! **Četnost užití** morfému je čistá funkce dominantních kořenů kódu, četností pojmů
//! a sloupců morfémů (`cee_core::code_state::Usage`). Kód drží kořeny a paměť, svět
//! zbytek: sloupce a četnosti pojmů se tu odvozují a zneplatňují paměť kódů přes
//! `Runtime::epoch`; dominantní kořeny se do paměti kódu přenášejí z deníku
//! `PhonologyState::dominant_log` od posledního kurzoru.
//!
//! **Sklon slova** vůči procesu je seedovaná normální náhoda patřící lexému, ne tvaru:
//! všechny buňky paradigmatu tak změnu přijmou (nebo odmítnou) společně a výjimka
//! nevyrobí falešnou alternaci. Hodnota je čistá funkce (semínko, proces, lexém,
//! `word_bias_sd`); svět si ji pamatuje v poli podle čísla lexému (jedno pole na proces).

use crate::ids::{ConceptId, GroupId, MorphemeId};
use crate::model::lexicon::MorphemeKind;
use crate::rng::{Part, Stream};
use crate::world::World;

/// Obnoví sloupce morfémů a četnosti pojmů, pokud se od posledního použití změnily.
pub fn refresh(world: &mut World) {
    let runtime = &mut world.sound.runtime;
    let morphemes = &world.morphemes;
    let count = morphemes.len();
    let present = morphemes.present.iter().filter(|&&flag| flag).count();
    let stamp = (count, present, world.paradigms.len());
    if runtime.columns.stamp != stamp || runtime.columns.lexeme.len() != count {
        let columns = &mut runtime.columns;
        columns.stamp = stamp;
        columns.weight = Vec::with_capacity(count);
        columns.lexeme = Vec::with_capacity(count);
        columns.default_form = Vec::with_capacity(count);
        columns.default_cut = Vec::with_capacity(count);
        columns.default_exponent = Vec::with_capacity(count);
        for number in 0..count {
            let id = MorphemeId::new(number);
            if !morphemes.present[number] {
                columns.weight.push(f64::NAN);
                columns.lexeme.push(-1);
                columns.default_form.push(-1);
                columns.default_cut.push(-1);
                columns.default_exponent.push(-1);
                continue;
            }
            let class = morphemes.word_class[number];
            let cell = morphemes.cell[number];
            let weight = if morphemes.kind[number] == MorphemeKind::Word
                && !class.is_none()
                && !cell.is_none()
            {
                world
                    .paradigms
                    .get(class.index())
                    .and_then(Option::as_ref)
                    .and_then(|paradigm| paradigm.weight(cell))
                    .unwrap_or(f64::NAN)
            } else {
                f64::NAN
            };
            columns.weight.push(weight);
            columns.lexeme.push(morphemes.lexeme_id(id).0 as i32);
            let form = morphemes.form[number];
            columns
                .default_form
                .push(if form == u32::MAX { -1 } else { form as i32 });
            columns.default_cut.push(morphemes.boundary[number]);
            let exponent = morphemes.exponent[number];
            columns.default_exponent.push(if exponent.is_none() {
                -1
            } else {
                exponent.0 as i32
            });
        }
        runtime.epoch += 1;
    }
    let concept_stamp = (world.concepts.version, world.registry.concepts.len());
    if runtime.concept_stamp != concept_stamp || runtime.concept.len() != concept_stamp.1 {
        runtime.concept_stamp = concept_stamp;
        runtime.concept = (0..concept_stamp.1)
            .map(|concept| world.concepts.frequency_of(ConceptId::new(concept)))
            .collect();
        runtime.epoch += 1;
    }
}

/// Přenese do paměti četností kódu změny dominantních kořenů od posledního kurzoru
/// a zahodí ji, když se změnil vstup četností (`refresh` ho musí volat první).
pub fn sync_usage(world: &mut World, group: GroupId) {
    let epoch = world.sound.runtime.epoch;
    let phonology = &mut world.groups.main_code_mut(group).phonology;
    let queues = &mut phonology.sound.queues;
    if queues.epoch != epoch {
        queues.state.usage.invalidate_all();
        queues.epoch = epoch;
    }
    if queues.cursor > phonology.dominant_log.len() {
        // Deník se zkrátil (jiný kód pod týmž číslem): paměť se staví znovu.
        queues.state.usage = Default::default();
        queues.cursor = 0;
    }
    while queues.cursor < phonology.dominant_log.len() {
        let (concept, _, root) = phonology.dominant_log[queues.cursor];
        let root = if root.is_none() { -1 } else { root.0 as i32 };
        queues.state.usage.set_root(concept.index(), root);
        queues.cursor += 1;
    }
}

/// Sklon lexému vůči procesu: seedovaná normální náhoda, čistá funkce (semínko, proces, lexém,
/// `word_bias_sd`); sloupce světa ho jen pamatují.
pub fn bias_value(world: &World, process: usize, lexeme: usize) -> f64 {
    let variable = world.registry.processes.name(process as u32);
    let lexeme_name = world.registry.morphemes.name(lexeme as u32);
    Stream::new(
        world.seed as u64,
        &[
            Part::Str("word-bias"),
            Part::Str(variable),
            Part::Str(lexeme_name),
        ],
    )
    .normal(0.0, world.params.word_bias_sd)
}

/// Dolosuje sklon slova (lexému morfému) vůči procesu a zapamatuje ho.
pub fn draw_bias(world: &mut World, process: usize, morpheme: usize) -> Result<(), String> {
    let lexeme = match world.sound.runtime.columns.lexeme.get(morpheme) {
        Some(&lexeme) if lexeme >= 0 => lexeme as usize,
        _ => {
            return Err(format!(
                "morfém č. {morpheme} nemá lexém ve sloupcích světa"
            ))
        }
    };
    let value = bias_value(world, process, lexeme);
    let runtime = &mut world.sound.runtime;
    if runtime.biases.len() <= process {
        runtime.biases.resize_with(process + 1, Vec::new);
    }
    let column = &mut runtime.biases[process];
    if column.len() <= lexeme {
        column.resize(world.registry.morphemes.len().max(lexeme + 1), f64::NAN);
    }
    column[lexeme] = value;
    Ok(())
}

/// Sklon slova (morfému) vůči procesu; dolosuje ho, když ještě není.
pub fn word_bias(world: &mut World, process: usize, morpheme: usize) -> Result<f64, String> {
    let known = world
        .sound
        .runtime
        .columns
        .lexeme
        .get(morpheme)
        .filter(|&&lexeme| lexeme >= 0)
        .and_then(|&lexeme| {
            world
                .sound
                .runtime
                .biases
                .get(process)
                .and_then(|column| column.get(lexeme as usize))
                .copied()
        })
        .filter(|value| !value.is_nan());
    if let Some(value) = known {
        return Ok(value);
    }
    draw_bias(world, process, morpheme)?;
    let lexeme = world.sound.runtime.columns.lexeme[morpheme] as usize;
    Ok(world.sound.runtime.biases[process][lexeme])
}

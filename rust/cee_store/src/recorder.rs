//! Zápis běhu do jeho složky během počítání.
//!
//! Smyčka běhu po každém kroku zavolá [`Recorder::collect`] (počítá snímek, slovník a kontrolní
//! bod) a pak [`Batch::write`] do složky běhu. Na startu [`Recorder::start`] dá slovník
//! protojazyků v roce začátku.

use std::collections::BTreeMap;

use cee_engine::export::{self, LanguageLexicon};
use cee_engine::Simulation;
use serde_json::Value;

use crate::RunWriter;

/// Co a jak často se z běhu ukládá.
#[derive(Clone, Copy, Debug)]
pub struct RecordOptions {
    /// Po kolika letech kontrolní bod (`None` = žádné; „co kdyby“ se pak počítá od začátku).
    pub checkpoint_every: Option<f64>,
    /// Slovník jazyků při každém novém snímku pozorování.
    pub lexicon: bool,
}

impl Default for RecordOptions {
    fn default() -> Self {
        RecordOptions {
            checkpoint_every: Some(100.0),
            lexicon: true,
        }
    }
}

/// Data jednoho kroku k zápisu.
#[derive(Default)]
pub struct Batch {
    pub frame: Option<Value>,
    pub lexicon: Option<(f64, BTreeMap<String, LanguageLexicon>)>,
    /// Nové řádky záznamu událostí od minulé dávky.
    pub events: Vec<String>,
    /// Kontrolní bod bez záznamu: tik, rok, počet řádků záznamu k bodu, bajty.
    pub checkpoint: Option<(u32, f64, usize, Vec<u8>)>,
}

impl Batch {
    pub fn is_empty(&self) -> bool {
        self.frame.is_none()
            && self.lexicon.is_none()
            && self.events.is_empty()
            && self.checkpoint.is_none()
    }

    /// Zapíše data kroku; `seconds` = doba běhu do teď.
    pub fn write(self, writer: &mut RunWriter, seconds: f64) -> Result<(), String> {
        if let Some((year, lexicons)) = &self.lexicon {
            writer.add_lexicon(*year, lexicons)?;
        }
        writer.add_events(&self.events)?;
        if let Some((tick, year, events, bytes)) = &self.checkpoint {
            writer.add_checkpoint(*tick, *year, *events, bytes)?;
        }
        if let Some(frame) = &self.frame {
            writer.add_frame(frame, seconds)?;
        }
        Ok(())
    }
}

pub struct Recorder {
    pub options: RecordOptions,
    observed: usize,
    last_checkpoint: f64,
    /// Kolik řádků záznamu událostí už dávky předaly.
    logged: usize,
}

impl Recorder {
    /// Zapisovač pro simulaci v jejím současném stavu (na startu nebo po kontrolním bodu
    /// „co kdyby“).
    pub fn new(simulation: &Simulation, options: RecordOptions) -> Recorder {
        Recorder {
            options,
            observed: simulation.history.snapshots.len(),
            last_checkpoint: simulation.year(),
            logged: simulation.history.events.len(),
        }
    }

    /// Slovník protojazyků v roce začátku (jen u běhu od začátku).
    pub fn start(&self, simulation: &Simulation) -> Batch {
        Batch {
            lexicon: self.options.lexicon.then(|| {
                (
                    simulation.world.start_year,
                    simulation.history.proto.clone(),
                )
            }),
            ..Batch::default()
        }
    }

    /// Po kroku (nebo koncovém pozorování): nový snímek → snímek pro kreslení a slovník;
    /// uplynulo `checkpoint_every` let → kontrolní bod.
    pub fn collect(&mut self, simulation: &Simulation) -> Result<Batch, String> {
        let mut batch = Batch::default();
        let year = simulation.year();
        if simulation.history.snapshots.len() != self.observed {
            self.observed = simulation.history.snapshots.len();
            batch.frame = Some(export::frame(simulation));
            if self.options.lexicon {
                batch.lexicon = Some((year, export::language_lexicons(simulation)));
            }
        }
        let log = &simulation.history.events;
        batch.events = (self.logged..log.len())
            .map(|i| log.line(i).into_owned())
            .collect();
        self.logged = log.len();
        if let Some(every) = self.options.checkpoint_every {
            if year - self.last_checkpoint >= every - 1e-9 {
                self.last_checkpoint = year;
                let checkpoint = simulation.checkpoint_without_events();
                batch.checkpoint = Some((
                    checkpoint.tick,
                    checkpoint.year,
                    self.logged,
                    checkpoint.to_bytes()?,
                ));
            }
        }
        Ok(batch)
    }
}

//! Hlavní smyčka enginu (zrcadlo `cee.v2.simulation`).
//!
//! [`Simulation::step`] volá fáze v pořadí: události, inovace, přenos (s tlaky),
//! přestavby (fonologie, morfologie, syntax, prozodie), komunity, pozorování,
//! kontrolní bod. Každá fáze je modul v [`crate::phases`] s funkcí `run` a popsaným
//! vstupem a výstupem; kostra zatím běží s prázdnými těly fází, kterým chybí logika R1.

use std::collections::{BTreeMap, VecDeque};

use serde::{Deserialize, Serialize};

use crate::changes::{default_changes, Change};
use crate::checkpoint::Checkpoint;
use crate::events::WorldEvent;
use crate::history::{History, Snapshot};
use crate::phases::{self, StepContext};
use crate::variation;
use crate::vocabulary::seed_vocabulary_all;
use crate::world::World;

/// Konstanty běhu. Startovní hodnoty ze specifikace; kalibrují se v M7.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct SimulationConfig {
    /// Délka kroku v letech; nesmí být delší než nejkratší generace ve světě.
    pub dt: f64,
    pub alpha: f64,
    pub selection: f64,
    pub kappa: f64,
    pub sigma: f64,
    /// Počáteční podíl inovace ve skupině o `reference_population` obyvatelích.
    pub p0: f64,
    pub reference_population: f64,
    pub p0_min: f64,
    pub p0_max: f64,
    pub adult_rate: f64,
    /// Spodní mez frekvence; pod ní varianta zaniká.
    pub loss_threshold: f64,
    pub establish_threshold: f64,
    /// Po kolika krocích se počítají dialekty a jazyky.
    pub observe_every: u32,
    pub dialect_threshold: f64,
    pub language_threshold: f64,
    pub keep_distances: bool,
    pub record_trajectories: bool,
    /// Po kolika letech se automaticky uloží kontrolní bod (`None` = nikdy).
    pub checkpoint_every: Option<f64>,
}

impl Default for SimulationConfig {
    fn default() -> Self {
        SimulationConfig {
            dt: 25.0,
            alpha: 1.0,
            selection: 1.0,
            kappa: 0.3,
            sigma: 2.0,
            p0: 0.02,
            reference_population: 500.0,
            p0_min: 0.002,
            p0_max: 0.2,
            adult_rate: 0.05,
            loss_threshold: 0.001,
            establish_threshold: 0.999,
            observe_every: 4,
            dialect_threshold: 0.05,
            language_threshold: 0.25,
            keep_distances: false,
            record_trajectories: false,
            checkpoint_every: None,
        }
    }
}

pub struct Simulation {
    pub world: World,
    pub config: SimulationConfig,
    pub changes: Vec<Box<dyn Change>>,
    /// Události seřazené podle roku a pořadí zadání; čekající v `pending`.
    pub events: Vec<serde_json::Value>,
    pending: VecDeque<Box<dyn WorldEvent>>,
    pub history: History,
    pub tick: u32,
    pub checkpoints: BTreeMap<u32, Checkpoint>,
}

impl Simulation {
    pub fn new(
        world: World,
        config: SimulationConfig,
        events: Vec<Box<dyn WorldEvent>>,
    ) -> Result<Simulation, String> {
        Simulation::with_changes(world, config, events, default_changes())
    }

    pub fn with_changes(
        mut world: World,
        config: SimulationConfig,
        events: Vec<Box<dyn WorldEvent>>,
        changes: Vec<Box<dyn Change>>,
    ) -> Result<Simulation, String> {
        if world.groups.is_empty() {
            return Err("Svět potřebuje alespoň jednu skupinu mluvčích.".into());
        }
        check_step(&world, &config)?;
        world.sync_live_groups()?;
        if world.table.is_some() {
            seed_vocabulary_all(&mut world)?;
        }
        if !world.varied {
            world.varied = true;
            variation::seed(&mut world)?;
        }
        world.load_differing()?;
        let described = events.iter().map(|e| e.describe()).collect();
        let mut sorted: Vec<(usize, Box<dyn WorldEvent>)> =
            events.into_iter().enumerate().collect();
        sorted.sort_by(|a, b| {
            a.1.year()
                .partial_cmp(&b.1.year())
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.0.cmp(&b.0))
        });
        Ok(Simulation {
            world,
            config,
            changes,
            events: described,
            pending: sorted.into_iter().map(|(_, e)| e).collect(),
            history: History::default(),
            tick: 0,
            checkpoints: BTreeMap::new(),
        })
    }

    /// Rok po posledním provedeném kroku.
    pub fn year(&self) -> f64 {
        self.world.start_year + f64::from(self.tick) * self.config.dt
    }

    /// Provede kroky až do roku `until_year`.
    pub fn run(&mut self, until_year: f64) -> Result<&History, String> {
        while self.year() + self.config.dt <= until_year + 1e-9 {
            self.step()?;
        }
        Ok(&self.history)
    }

    /// Jeden krok: fáze v pořadí specifikace.
    pub fn step(&mut self) -> Result<(), String> {
        self.tick += 1;
        let year = self.year();
        let (tick, observe_every) = (self.tick, self.config.observe_every);
        {
            let mut ctx = StepContext {
                world: &mut self.world,
                history: &mut self.history,
                config: &self.config,
                tick,
                year,
            };
            phases::events::run(&mut ctx, &mut self.pending)?;
            phases::innovation::run(&mut ctx, &self.changes)?;
            phases::transmission::run(&mut ctx, &self.changes)?;
            phases::rebuild::run(&mut ctx)?;
            if phases::communities::run(&mut ctx)? {
                ctx.world.sync_live_groups()?;
            }
            if observe_every > 0 && tick % observe_every == 0 {
                phases::observe::run(&mut ctx)?;
            }
        }
        if let Some(every) = self.config.checkpoint_every {
            if (year - self.world.start_year) % every < 1e-9 {
                let checkpoint = self.checkpoint();
                self.checkpoints.insert(self.tick, checkpoint);
            }
        }
        Ok(())
    }

    /// Úplný stav běhu po posledním kroku (kopie; pokračování z něj je stejné).
    pub fn checkpoint(&self) -> Checkpoint {
        Checkpoint {
            tick: self.tick,
            year: self.year(),
            world: self.world.clone(),
            history: self.history.clone(),
        }
    }

    /// Pokračování z kontrolního bodu s (případně jinými) pozdějšími událostmi.
    pub fn resume(
        checkpoint: Checkpoint,
        config: SimulationConfig,
        events: Vec<Box<dyn WorldEvent>>,
        changes: Vec<Box<dyn Change>>,
    ) -> Result<Simulation, String> {
        let mut simulation =
            Simulation::with_changes(checkpoint.world, config, Vec::new(), changes)?;
        simulation.history = checkpoint.history;
        simulation.tick = checkpoint.tick;
        simulation.events = events.iter().map(|e| e.describe()).collect();
        let mut later: Vec<Box<dyn WorldEvent>> = events
            .into_iter()
            .filter(|e| e.year() > checkpoint.year)
            .collect();
        later.sort_by(|a, b| {
            a.year()
                .partial_cmp(&b.year())
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        simulation.pending = later.into();
        Ok(simulation)
    }

    pub fn snapshots(&self) -> &[Snapshot] {
        &self.history.snapshots
    }
}

fn check_step(world: &World, config: &SimulationConfig) -> Result<(), String> {
    if config.dt > world.generation_ceiling() {
        return Err(format!(
            "Krok {} let je delší než nejkratší generace ({} let).",
            config.dt,
            world.generation_ceiling()
        ));
    }
    Ok(())
}

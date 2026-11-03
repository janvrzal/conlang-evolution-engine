//! Fáze kroku simulace. Každá fáze je modul s funkcí `run` a jasným vstupem.
//!
//! `Simulation::step` volá fáze v tomto pořadí (jako `simulation.py`):
//!
//! | # | modul | čte | zapisuje | vlastník |
//! |---|---|---|---|---|
//! | 1 | [`events`] | `Vec<Box<dyn WorldEvent>>`, `World` | svět, historie (`edit_log`, `society`) | R1d |
//! | 2 | [`innovation`] | `World`, `&[Box<dyn Change>]`, `SimulationConfig` | nové varianty, živé fondy, historie (`innovation`) | R0 (rámec), R1b/c (změny) |
//! | 3 | [`transmission`] | `World.live`, tlaky, `TransferState` | podíly variant ve fondech, historie (`milestone`, `established`, `extinct`), aktivace procesů | R1a |
//! | 4 | [`rebuild`] | fondy po přenosu | tvary kódů (`forms`), slovní zásoba, historie | R1b (fonologie), R1c (morfologie, syntax, prozodie) |
//! | 5 | [`communities`] | `World` | skupiny, kódy, osa živých fondů | R1d |
//! | 6 | [`observe`] | `World` | `History.snapshots`, události pozorování | R1d |
//! | 7 | kontrolní bod | `Simulation` | `checkpoints` | R0 |
//!
//! Všechny fáze dostávají [`StepContext`]: svět, historii, konfiguraci, tik a rok.
//! Náhodu si fáze tvoří z klíče (`Stream::new(seed, &[...])`), nikdy ze sdíleného
//! generátoru, takže souběžné zpracování skupin dává stejný výsledek při libovolném
//! počtu vláken (viz `parallel`).

pub mod communities;
pub mod events;
pub mod hooks;
pub mod innovation;
pub mod observe;
pub mod rebuild;
pub mod transmission;

use crate::history::History;
use crate::simulation::SimulationConfig;
use crate::world::World;

/// Vstup každé fáze kroku.
pub struct StepContext<'a> {
    pub world: &'a mut World,
    pub history: &'a mut History,
    pub config: &'a SimulationConfig,
    pub tick: u32,
    pub year: f64,
}

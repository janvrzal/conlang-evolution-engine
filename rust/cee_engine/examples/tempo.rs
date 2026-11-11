//! Čas kroku po stoletích s rozpisem fází a s velikostí stavu, který s během roste.
//!
//! Po každém století vypíše řádek `##` (čas kroku, skupiny, tvary v bance, morfémy, procesy,
//! proměnné, živé proměnné, záznamy), řádky `#` (živé hláskové procesy kódů podle podílu změněné
//! varianty, průměr na kód) a kumulativní tabulku `timing::report`. Rozdíl dvou tabulek je čas
//! fází v daném století. Na konci otisk logu a volitelně export (pro porovnání před a po změně).
//!
//! `cargo run --release --example tempo -- <spec.json> [do_roku] [export.json]`

use std::time::Instant;

use cee_engine::ids::{GroupId, ProcessId};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{export, Simulation, SimulationConfig};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let text = std::fs::read_to_string(&args[0]).unwrap();
    let ws = WorldSpec::from_json(&text).unwrap();
    let until: f64 = args.get(1).map_or(ws.end_year, |s| s.parse().unwrap());
    cee_engine::parallel::init_default(0);
    cee_engine::timing::enable();
    let (w, events) = spec::build(&ws).unwrap();
    let mut sim = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    let start = Instant::now();
    let mut t = Instant::now();
    let mut century = (sim.year() / 100.0).floor();
    let mut steps = 0;
    while sim.year() + sim.config.dt <= until + 1e-9 {
        sim.step().unwrap();
        steps += 1;
        let c = (sim.year() / 100.0).floor();
        if c != century {
            let w = &sim.world;
            println!(
                "## {:>6} s/krok {:.3} skupin {}/{} tvarů {} morfémů {} procesů {}/{} proměnných {} variant {} živých {} zapomenutých {} záznamů {}",
                century * 100.0,
                t.elapsed().as_secs_f64() / steps as f64,
                w.group_ids().len(),
                w.groups.len(),
                w.bank.bank.len(),
                w.morphemes.len(),
                w.processes.len(),
                w.bank.bank.proc_count(),
                w.variables.len(),
                w.variants.len(),
                w.live.len(),
                w.transfer.forgotten.values().map(|set| set.len()).sum::<usize>(),
                sim.history.events.len()
            );
            let (mut vocab, mut procs, mut live, mut queued, mut codes) = (0, 0, 0, 0, 0);
            for g in w.group_ids() {
                let code = w.groups.main_code(g);
                codes += 1;
                vocab += code.phonology.vocabulary.len();
                let state = &code.phonology.sound.queues.state;
                procs += state.procs.len();
                for p in &state.procs {
                    if p.live {
                        live += 1;
                        queued += p.morphemes.len();
                    }
                }
            }
            // Živé procesy kódů podle podílu změněné varianty ve skupině a délky jejich front.
            let mut hist = [0usize; 7];
            let mut hist_queue = [0usize; 7];
            let pairs: Vec<(GroupId, usize, usize)> = sim
                .world
                .group_ids()
                .into_iter()
                .flat_map(|g| {
                    let state = &sim.world.groups.main_code(g).phonology.sound.queues.state;
                    state
                        .procs
                        .iter()
                        .filter(|p| p.live)
                        .map(|p| (g, p.number, p.morphemes.len()))
                        .collect::<Vec<_>>()
                })
                .collect();
            for (g, number, queue) in pairs {
                let (variable, changed) =
                    cee_engine::phonology::rows::info_of(&mut sim.world, ProcessId::new(number))
                        .unwrap();
                let share =
                    cee_engine::phonology::rows::changed_share(&sim.world, g, variable, changed);
                let bin = [0.0, 0.01, 0.05, 0.2, 0.5, 0.999999, f64::INFINITY]
                    .iter()
                    .position(|&edge| share <= edge)
                    .unwrap();
                hist[bin] += 1;
                hist_queue[bin] += queue;
            }
            println!("#  živé procesy podle podílu 0|≤.01|≤.05|≤.2|≤.5|<1|1: {hist:?} fronty {hist_queue:?}");
            println!(
                "#  na kód: slov {:.0} procesů {:.1} živých {:.1} ve frontách {:.0}",
                vocab as f64 / codes as f64,
                procs as f64 / codes as f64,
                live as f64 / codes as f64,
                queued as f64 / codes as f64
            );
            // Živé proměnné: kolik je všude ustálených (každá skupina jednu variantu) a kolik buněk
            // (proměnná × skupina) má víc variant; druhé číslo také bez podílů pod 5 %.
            let (mut settled, mut cells, mut mixed, mut mixed5) = (0, 0, 0, 0);
            for block in sim.world.live.iter_blocks() {
                for row in 0..block.len() {
                    let mut all = true;
                    for column in 0..block.groups {
                        if !block.present[row][column] {
                            continue;
                        }
                        let found = block.cell(row, column);
                        cells += 1;
                        if found.len() > 1 {
                            mixed += 1;
                            all = false;
                            if found.iter().filter(|(_, share, _)| *share >= 0.05).count() > 1 {
                                mixed5 += 1;
                            }
                        }
                    }
                    if all {
                        settled += 1;
                    }
                }
            }
            println!(
                "#  živé proměnné: všude ustálených {settled} z {}, buněk s víc variantami {mixed} ({mixed5} nad 5 %) z {cells}",
                sim.world.live.len()
            );
            print!("{}", cee_engine::timing::report());
            t = Instant::now();
            steps = 0;
            century = c;
        }
    }
    sim.observe_now().unwrap();
    eprintln!(
        "celkem {:.1} s, otisk {}",
        start.elapsed().as_secs_f64(),
        sim.history.digest()
    );
    if let Some(path) = args.get(2) {
        std::fs::write(
            path,
            serde_json::to_string(&export::export(&sim, true)).unwrap(),
        )
        .unwrap();
    }
}

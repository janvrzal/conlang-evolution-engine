//! Souběh na více jádrech nesmí změnit výsledek: otisk historie i export jsou stejné pro 1, 2, 3,
//! 4 a 8 vláken na scénářích valley-50, grid-5x5, shift, island-city a na příkladu `WorldSpec`.

use cee_engine::export::export;
use cee_engine::{parallel, scenarios, spec, Simulation, SimulationConfig};

const THREADS: [usize; 5] = [1, 2, 3, 4, 8];

/// Otisk historie a export běhu na lokální skupině `threads` vláken.
fn run_with(
    threads: usize,
    build: &(dyn Fn() -> Simulation + Sync),
    until: f64,
) -> (String, String) {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .expect("skupina vláken");
    pool.install(|| {
        let mut simulation = build();
        simulation.run(until).expect("běh");
        (
            simulation.history.digest(),
            export(&simulation, true).to_string(),
        )
    })
}

fn check(name: &str, build: &(dyn Fn() -> Simulation + Sync), until: f64) {
    // S nulovým prahem se dělí i malé světy, jinak by test u nich souběh nezkoušel.
    parallel::set_min_parallel_cells(0);
    let reference = run_with(1, build, until);
    for threads in THREADS {
        let found = run_with(threads, build, until);
        assert_eq!(found.0, reference.0, "{name}: otisk, vláken {threads}");
        assert!(found.1 == reference.1, "{name}: export, vláken {threads}");
    }
}

fn scenario(name: &'static str) -> impl Fn() -> Simulation {
    move || {
        let (world, events) = scenarios::by_name(name).expect("scénář");
        Simulation::new(world, SimulationConfig::default(), events).expect("simulace")
    }
}

#[test]
fn valley_50_je_stejne_na_vsech_poctech_vlaken() {
    check("valley-50", &scenario("valley-50"), 600.0);
}

#[test]
fn grid_5x5_je_stejne_na_vsech_poctech_vlaken() {
    check("grid-5x5", &scenario("grid-5x5"), 600.0);
}

#[test]
fn shift_je_stejne_na_vsech_poctech_vlaken() {
    check("shift", &scenario("shift"), 600.0);
}

#[test]
fn island_city_je_stejne_na_vsech_poctech_vlaken() {
    check("island-city", &scenario("island-city"), 600.0);
}

#[test]
fn priklad_world_spec_je_stejny_na_vsech_poctech_vlaken() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    );
    let text = std::fs::read_to_string(path).expect("příklad světa");
    let world_spec = spec::WorldSpec::from_json(&text).expect("popis světa");
    let build = move || {
        let (world, events) = spec::build(&world_spec).expect("svět");
        Simulation::new(world, SimulationConfig::default(), events).expect("simulace")
    };
    check("příklad WorldSpec", &build, 600.0);
}

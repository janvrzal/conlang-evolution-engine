//! Průběžně udržované pohledy kódu (`cee_engine::views`) se po každém kroku shodují s výpočtem
//! od nuly a přežijí uložení a obnovu z kontrolního bodu.

use cee_engine::checkpoint::Checkpoint;
use cee_engine::{scenarios, spec, views, Simulation, SimulationConfig};

fn scenario(name: &str) -> Simulation {
    let (world, events) = scenarios::by_name(name).expect("scénář");
    Simulation::new(world, SimulationConfig::default(), events).expect("simulace")
}

/// Krok po kroku do roku `until`; po každém kroku se pohledy porovnají s výpočtem od nuly.
fn run_checked(simulation: &mut Simulation, until: f64) {
    views::set_verify(true);
    while simulation.year() + simulation.config.dt <= until + 1e-9 {
        simulation.step().expect("krok");
        views::verify(&simulation.world)
            .unwrap_or_else(|e| panic!("rok {}: {e}", simulation.year()));
    }
}

#[test]
fn pohledy_odpovidaji_vypoctu_od_nuly_na_scenarich() {
    for name in [
        "morphology",
        "syntax",
        "valley-50",
        "shift",
        "island-city",
        "conquest",
    ] {
        let mut simulation = scenario(name);
        run_checked(&mut simulation, 600.0);
    }
}

#[test]
fn pohledy_odpovidaji_vypoctu_od_nuly_na_prikladu_world_spec() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    );
    let text = std::fs::read_to_string(path).expect("příklad světa");
    let world_spec = spec::WorldSpec::from_json(&text).expect("popis světa");
    let (world, events) = spec::build(&world_spec).expect("svět");
    let mut simulation =
        Simulation::new(world, SimulationConfig::default(), events).expect("simulace");
    run_checked(&mut simulation, 600.0);
}

/// Uložení a obnova: pohled se po načtení postaví znovu a běh pokračuje stejně jako nepřerušený.
#[test]
fn pohledy_prezijou_kontrolni_bod() {
    let mut whole = scenario("valley-50");
    run_checked(&mut whole, 900.0);
    let mut first = scenario("valley-50");
    run_checked(&mut first, 500.0);
    let bytes = first.checkpoint().to_bytes().expect("uložení");
    let restored = Checkpoint::from_bytes(&bytes).expect("načtení");
    let mut resumed = Simulation::resume(
        restored,
        SimulationConfig::default(),
        Vec::new(),
        cee_engine::changes::default_changes(),
    )
    .expect("obnova");
    // Hned po obnově je pohled postavený a odpovídá stavu.
    views::verify(&resumed.world).expect("pohled po obnově");
    run_checked(&mut resumed, 900.0);
    assert_eq!(resumed.history.digest(), whole.history.digest());
}

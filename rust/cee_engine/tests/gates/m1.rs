//! M1: dialektové kontinuum S1, metriky 7, 8 a 12, velká souhrnná skupina, přiblížení.

use std::collections::BTreeMap;
use std::sync::OnceLock;

use cee_engine::gates::m1;
use cee_engine::scenarios::{village_grid_default, SeedOptions};
use cee_engine::{Simulation, SimulationConfig};

use crate::common::{assert_passed, cached};

fn continuum() -> &'static Simulation {
    static CELL: OnceLock<Result<Simulation, String>> = OnceLock::new();
    cached(&CELL, || m1::run_continuum(2))
}

fn bordered() -> &'static Simulation {
    static CELL: OnceLock<Result<Simulation, String>> = OnceLock::new();
    cached(&CELL, || m1::run_bordered(2))
}

#[test]
#[ignore = "brána milníku (3 000 let, 20 vesnic)"]
fn s1_kontinuum_je_plynule_a_vzdalenost_roste_se_vzdalenosti() {
    assert_passed(&m1::check_s1_kontinuum(continuum()));
}

#[test]
#[ignore = "brána milníku (3 000 let, 20 vesnic)"]
fn s1_hranice_vytvori_svazek_izoglos() {
    assert_passed(&m1::check_s1_hranice(bordered()));
}

#[test]
#[ignore = "brána milníku (3 000 let, 20 vesnic)"]
fn metrika_7_usalene_zmeny_se_siri_po_s_krivce() {
    assert_passed(&m1::check_metrika_7(continuum()));
}

#[test]
#[ignore = "brána milníku (3 000 let, 20 vesnic)"]
fn metrika_8_vetsina_inovaci_zanikne() {
    assert_passed(&m1::check_metrika_8(continuum()));
}

#[test]
#[ignore = "brána milníku"]
fn velka_souhrnna_skupina_driftuje_mene_nez_mala_vesnice() {
    let (large, small) = m1::run_drift_pair(3).expect("běh driftu");
    assert_passed(&m1::check_velka_souhrnna_skupina(large, small));
}

// Metrika 9 (Séguyho zákon) se ověřuje v plném modelu na mapě: `m6b`.

#[test]
#[ignore = "brána milníku"]
fn metrika_12_stejne_semino_da_stejny_log_a_jine_semino_jiny() {
    let digest = |seed: i64| {
        let world = village_grid_default(6, 1, seed, &SeedOptions::default()).expect("svět");
        let mut simulation =
            Simulation::new(world, SimulationConfig::default(), Vec::new()).expect("běh");
        simulation.run(1000.0).expect("běh");
        simulation.history.digest()
    };
    assert_eq!(digest(4), digest(4));
    assert_ne!(digest(4), digest(5));
}

type State = BTreeMap<(String, String), Vec<(String, f64)>>;

/// Historie a stav východní oblasti při souhrnném a při zjemněném západě.
fn east(refine_west: bool) -> (Vec<serde_json::Map<String, serde_json::Value>>, State) {
    let world = m1::two_regions(refine_west, 40, false).expect("svět");
    let mut simulation =
        Simulation::new(world, SimulationConfig::default(), Vec::new()).expect("běh");
    simulation.run(2000.0).expect("běh");
    let events = m1::east_events(&simulation, false);
    let world = &simulation.world;
    let mut state = State::new();
    for name in ["east-0", "east-1", "east-2"] {
        let group = world
            .registry
            .groups
            .get(name)
            .map(cee_engine::GroupId)
            .expect("skupina");
        for variable in 0..world.variables.len() {
            let id = cee_engine::VariableId::new(variable);
            if let Some(d) = world.distribution(group, id) {
                let items = d
                    .variants
                    .iter()
                    .zip(&d.freqs)
                    .map(|(v, f)| (world.registry.variants.name(v.0).to_owned(), *f))
                    .collect();
                state.insert(
                    (
                        name.to_owned(),
                        world.registry.variables.name(id.0).to_owned(),
                    ),
                    items,
                );
            }
        }
    }
    (events, state)
}

/// Přepočet od začátku: zjemnění západu nesmí pohnout s východem.
#[test]
#[ignore = "brána milníku"]
fn priblizeni_nezmeni_historii_nepropojene_oblasti() {
    let (coarse_events, coarse_state) = east(false);
    let (fine_events, fine_state) = east(true);
    assert!(!coarse_events.is_empty() && coarse_events == fine_events);
    // Porovnávají se proměnné, které existují v obou světech (inovace západu jsou jen v jednom).
    let shared: Vec<_> = coarse_state
        .keys()
        .filter(|k| fine_state.contains_key(*k))
        .collect();
    assert!(!shared.is_empty());
    for key in shared {
        assert_eq!(coarse_state[key], fine_state[key], "{key:?}");
    }
}

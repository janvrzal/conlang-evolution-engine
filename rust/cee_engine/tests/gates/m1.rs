//! M1: dialektové kontinuum S1, metriky 7, 8 a 12, velká souhrnná skupina, přiblížení.

use std::collections::BTreeMap;

use cee_engine::gates::m1;
use cee_engine::scenarios::{village_grid_default, SeedOptions};
use cee_engine::{Simulation, SimulationConfig};

use crate::common::assert_statistical;

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

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (S1 3 000 let, 30 semínek)"]
fn statisticke_brany() {
    assert_statistical("m1");
}

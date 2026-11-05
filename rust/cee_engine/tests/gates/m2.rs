//! M2: metriky 3 až 6 nad zvukem, tři semínka.

use cee_engine::gates::m1::{east_events, two_regions};
use cee_engine::gates::metrics::lexicon_forms;
use cee_engine::scenarios::{village_grid_default, SeedOptions};
use cee_engine::{Simulation, SimulationConfig};

use crate::common::assert_statistical;

#[test]
#[ignore = "brána milníku"]
fn determinismus_s_fonologii() {
    let digest = || {
        let options = SeedOptions {
            phonology: true,
            ..SeedOptions::default()
        };
        let world = village_grid_default(4, 1, 8, &options).expect("svět");
        let mut simulation =
            Simulation::new(world, SimulationConfig::default(), Vec::new()).expect("běh");
        simulation.run(1000.0).expect("běh");
        let first = simulation.world.group_ids()[0];
        (
            simulation.history.digest(),
            lexicon_forms(&simulation.world, first),
        )
    };
    assert_eq!(digest(), digest());
}

/// Historie a podkladové tvary východu při souhrnném a při zjemněném západě.
#[test]
#[ignore = "brána milníku"]
fn priblizeni_nezmeni_zvukovou_historii_nepropojene_oblasti() {
    let east = |refine: bool| {
        let world = two_regions(refine, 60, true).expect("svět");
        let mut simulation =
            Simulation::new(world, SimulationConfig::default(), Vec::new()).expect("běh");
        simulation.run(2000.0).expect("běh");
        let events = east_events(&simulation, true);
        let world = &simulation.world;
        let forms: Vec<_> = ["east-0", "east-1", "east-2"]
            .iter()
            .map(|name| {
                let group = world
                    .registry
                    .groups
                    .get(name)
                    .map(cee_engine::GroupId)
                    .expect("skupina");
                lexicon_forms(world, group)
            })
            .collect();
        (events, forms)
    };
    let (coarse, fine) = (east(false), east(true));
    assert!(coarse
        .0
        .iter()
        .any(|e| e.get("kind").and_then(|k| k.as_str()) == Some("phonologized")));
    assert_eq!(coarse, fine);
}

/// Všechny brány milníku proti zamčeným cílovým pásmům (dokument 21), semínka od 201.
#[test]
#[ignore = "statistické brány milníku (3 000 let, 12 trojic semínek)"]
fn statisticke_brany() {
    assert_statistical("m2");
}

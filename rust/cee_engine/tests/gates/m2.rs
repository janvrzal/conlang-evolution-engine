//! M2: metriky 3 až 6 nad zvukem, tři semínka.

use std::sync::OnceLock;

use cee_engine::gates::m1::{east_events, two_regions};
use cee_engine::gates::m2::{self, PhonologyRun};
use cee_engine::gates::metrics::lexicon_forms;
use cee_engine::scenarios::{village_grid_default, SeedOptions};
use cee_engine::{Simulation, SimulationConfig};

use crate::common::{assert_every, assert_passed, cached, collect_runs};

const SEEDS: [i64; 3] = [1, 2, 3];

fn runs() -> &'static [(i64, PhonologyRun)] {
    static CELL: OnceLock<Result<Vec<(i64, PhonologyRun)>, String>> = OnceLock::new();
    cached(&CELL, || collect_runs(SEEDS, m2::run_phonology))
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn metrika_3_delka_slov_zustava_v_pasmu() {
    assert_every(runs(), m2::check_metrika_3);
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn metrika_4_inventare_lezi_v_pasmu_realnych_jazyku() {
    assert_every(runs(), m2::check_metrika_4);
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn metrika_5_homofonie_zustava_nizka() {
    assert_every(runs(), m2::check_metrika_5);
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn metrika_6_ustalene_zmeny_odpovidaji_prioru_a_nejsou_jednostranne() {
    let refs: Vec<&PhonologyRun> = runs().iter().map(|(_, run)| run).collect();
    assert_passed(&m2::check_metrika_6(&refs));
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn jazyky_z_ruznych_seedu_se_lisi() {
    let refs: Vec<&PhonologyRun> = runs().iter().map(|(_, run)| run).collect();
    assert_passed(&m2::check_jazyky_se_lisi(&refs));
}

#[test]
#[ignore = "brána milníku (3 000 let, tři semínka)"]
fn zvukove_zmeny_se_siri_arealne_a_maji_male_vyjimky() {
    assert_every(runs(), m2::check_zvukove_zmeny_se_siri);
}

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

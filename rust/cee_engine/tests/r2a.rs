//! Integrace oblastí enginu (R2a): hodnocení procesů a analogií pro tlaky, plán tlaků ze změn,
//! kontrolní bod s uloženými hodnoceními a švy mezi přenosem, fonologií, morfologií a kontaktem.

use cee_core::pressures::id;
use cee_engine::changes::{default_changes, lexicon, Change};
use cee_engine::checkpoint::Checkpoint;
use cee_engine::model::repertoire::VariableKind;
use cee_engine::scenarios;
use cee_engine::transfer::pressures::{kind_number, plan, plan_for};
use cee_engine::{Simulation, SimulationConfig};

fn simulation(name: &str) -> Simulation {
    let (world, events) = scenarios::by_name(name).expect("scénář");
    Simulation::new(world, SimulationConfig::default(), events).expect("simulace")
}

#[test]
fn hodnoceni_procesu_se_pocita_pred_prenosem_a_ukladuje() {
    let mut sim = simulation("phonology");
    for _ in 0..10 {
        sim.step().unwrap();
    }
    let stored: Vec<_> = sim
        .world
        .transfer
        .assessments
        .groups
        .iter()
        .flatten()
        .collect();
    assert!(!stored.is_empty(), "zvukové procesy mají uložené hodnocení");
    for entry in &stored {
        let [coverage, merge, short, marked, dispersion] = entry.value;
        assert!((0.0..=1.0 + 1e-9).contains(&coverage), "pokrytí {coverage}");
        assert!(merge >= 0.0 && merge.is_finite());
        assert!((0.0..=1.0 + 1e-9).contains(&short), "krátká slova {short}");
        assert!(marked.is_finite() && dispersion.is_finite());
        assert!(entry.tick <= sim.tick);
    }
    assert!(
        stored.iter().any(|e| e.value[0] > 0.0),
        "aspoň jedna změna zasahuje slovní zásobu"
    );
    // Seznam v každé skupině je seřazený podle proměnné (hledá se půlením).
    for list in &sim.world.transfer.assessments.groups {
        assert!(list.windows(2).all(|w| w[0].variable < w[1].variable));
    }
}

#[test]
fn ulozena_hodnoceni_prezijou_kontrolni_bod() {
    let mut sim = simulation("phonology");
    for _ in 0..10 {
        sim.step().unwrap();
    }
    let bytes = sim.checkpoint().to_bytes().unwrap();
    let restored = Checkpoint::from_bytes(&bytes).unwrap();
    assert_eq!(
        restored.world.transfer.assessments,
        sim.world.transfer.assessments
    );
    assert!(!restored.world.transfer.assessments.groups.is_empty());
}

#[test]
fn analogie_se_hodnoti_ze_stavu_kodu() {
    let mut sim = simulation("morphology");
    for _ in 0..24 {
        sim.step().unwrap();
    }
    let world = &sim.world;
    let axis = world.live.group_ids.len();
    let columns: Vec<usize> = (0..axis).collect();
    let mut found = 0;
    for &variable in world.form_changes.keys() {
        let values = cee_engine::transfer::seams::assess_cells(world, variable, &columns, sim.tick);
        assert_eq!(values.len(), axis);
        for value in values.into_iter().flatten() {
            let [gain, frequency, before, after, zero] = value;
            assert!(gain.is_finite() && (-1.0..=1.0).contains(&gain));
            assert!((0.0..=1.0).contains(&frequency));
            assert!(before == 0.0 || before == 1.0);
            assert!(after == 0.0 || after == 1.0);
            assert_eq!(zero, 0.0);
            found += 1;
        }
    }
    assert!(!world.form_changes.is_empty(), "svět má analogie");
    assert!(
        found > 0,
        "aspoň jedna analogie má v některé skupině hodnocení"
    );
}

#[test]
fn plan_tlaku_se_sklada_z_deklaraci_zmen() {
    let params = sim_params();
    let full = plan_for(&default_changes(), &params).unwrap();
    assert_eq!(full, plan(&params).unwrap());
    // Všech pět cílových druhů má `Norm`; tlaky jsou seřazené podle jména.
    for kind in &full {
        assert!(kind.iter().any(|&(p, _)| p == id::NORM));
        let names: Vec<&str> = kind
            .iter()
            .map(|&(p, _)| cee_engine::transfer::pressures::NAMES[p as usize])
            .collect();
        let mut sorted = names.clone();
        sorted.sort_unstable();
        assert_eq!(names, sorted);
    }
    // Lexikální změny: přitažlivost jen od tvoření, žádné obecné ocenění změny.
    let lexical = &full[kind_number(VariableKind::Lexical)];
    assert!(lexical.iter().any(|&(p, w)| p == id::APPEAL && w == 1.0));
    assert!(!lexical.iter().any(|&(p, _)| p == id::ACTUATION));
    // Jen lexikální změny: ostatní druhy plán nemají a zvukový tlak je neznámý.
    let only: Vec<Box<dyn Change>> = lexicon::changes();
    let narrow = plan_for(&only, &params).unwrap();
    assert!(narrow[kind_number(VariableKind::Process)].is_empty());
    let mut weights = params.clone();
    weights.pressure_weights.insert("articulation".into(), 2.0);
    assert!(plan_for(&only, &weights).is_err());
    let full_weighted = plan_for(&default_changes(), &weights).unwrap();
    let articulation = full_weighted[kind_number(VariableKind::Process)]
        .iter()
        .find(|&&(p, _)| p == id::ARTICULATION)
        .unwrap();
    assert_eq!(articulation.1, 2.0);
}

fn sim_params() -> cee_engine::parameters::Parameters {
    cee_engine::parameters::Parameters::default()
}

#[test]
fn nove_slovo_dostane_tvary_bunek_pri_vstupu_do_slovni_zasoby() {
    // Svět s významy a morfologií: po delším běhu mají lexémy vzniklé za běhu (složeniny,
    // odvozeniny) tvary buněk paradigmatu (`units_in`), takže slovní zásoba obsahuje tvary slov.
    let mut sim = simulation("morphology");
    sim.run(600.0).unwrap();
    let world = &sim.world;
    let mut grown = 0;
    for group in world.group_ids() {
        let code = world.groups.main_code(group);
        for unit in code.phonology.vocabulary.iter() {
            let lexeme = world.morphemes.lexeme_id(unit);
            if lexeme != unit && !world.morphemes.origin_group[lexeme.index()].is_none() {
                grown += 1;
            }
        }
    }
    assert!(grown > 0, "nové lexémy mají ve slovní zásobě tvary buněk");
}

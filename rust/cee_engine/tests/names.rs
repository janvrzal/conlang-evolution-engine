//! Modul jmen (dok. 34): jména jako slova s vlastní historií.
//!
//! Ověřuje, že jména nemění běh (otisk, slovník, vzdálenosti), že stejné semínko dává stejná
//! jména, že jméno ustrne (změna obecného slova ho nezmění), že prochází hláskovými změnami
//! nositele, že přejaté jméno začíná v podobě dárce a že se dá pokračovat z kontrolního bodu.

use cee_engine::checkpoint::Checkpoint;
use cee_engine::export;
use cee_engine::ids::{ConceptId, GroupId};
use cee_engine::names::generate::Query;
use cee_engine::names::{NameState, Role};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{scenarios, Simulation, SimulationConfig};
use serde_json::json;

fn config(names: bool) -> SimulationConfig {
    SimulationConfig {
        names,
        keep_distances: true,
        ..SimulationConfig::default()
    }
}

fn run(name: &str, until: f64, names: bool) -> Simulation {
    let (world, events) = scenarios::by_name(name).expect("scénář");
    let mut simulation = Simulation::new(world, config(names), events).expect("simulace");
    simulation.run(until).expect("běh");
    simulation
}

fn names(simulation: &Simulation) -> &NameState {
    simulation.names.as_ref().expect("modul jmen běžel")
}

#[test]
fn jmena_nemeni_otisk_slovnik_ani_vzdalenosti() {
    let without = run("kingdom", 600.0, false);
    let with = run("kingdom", 600.0, true);
    assert_eq!(
        without.history.digest(),
        with.history.digest(),
        "otisk historie"
    );
    assert_eq!(
        without.history.snapshots, with.history.snapshots,
        "snímky a vzdálenosti"
    );
    assert!(with.history.snapshots.iter().any(|s| s.distances.is_some()));
    for group in without.world.group_ids() {
        assert_eq!(
            export::lexicon(&without.world, group),
            export::lexicon(&with.world, group),
            "slovník skupiny {}",
            without.world.group_name(group)
        );
        assert_eq!(
            export::grammar(&without.world, group),
            export::grammar(&with.world, group)
        );
    }
    assert!(!names(&with).records.is_empty());
}

#[test]
fn stejne_seminko_da_stejna_jmena() {
    let first = run("kingdom", 600.0, true);
    let second = run("kingdom", 600.0, true);
    assert_eq!(names(&first).export(), names(&second).export());
}

#[test]
fn jmena_jsou_stejna_na_vice_vlaknech() {
    let on = |threads: usize| {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        pool.install(|| names(&run("kingdom", 400.0, true)).export())
    };
    assert_eq!(on(1), on(4));
}

#[test]
fn jmeno_prochazi_hlaskovymi_zmenami_nositele() {
    let simulation = run("kingdom", 1000.0, true);
    let state = names(&simulation);
    let changed: Vec<_> = state
        .records
        .iter()
        .filter(|r| r.timeline.iter().any(|s| s.cause.starts_with("sound:")))
        .collect();
    assert!(!changed.is_empty(), "žádné jméno neprošlo hláskovou změnou");
    // Změny se mohou i vrátit (a → e → a), aspoň některá jména se ale liší od založení.
    assert!(changed
        .iter()
        .any(|r| r.ipa_at(r.founded_year) != r.timeline.last().map(|s| s.ipa.as_str())));
    for record in changed {
        let last = record.timeline.last().unwrap();
        assert!(last.year > record.founded_year);
        for pair in record.timeline.windows(2) {
            assert!(
                pair[0].year <= pair[1].year,
                "{}: časová osa jde popořadě",
                record.id
            );
            assert_ne!(
                pair[0].ipa, pair[1].ipa,
                "{}: krok bez změny tvaru",
                record.id
            );
        }
        // Dnešní tvar je poslední krok časové osy.
        let table = simulation.world.table.as_ref().unwrap();
        assert_eq!(table.render(&record.form), last.ipa);
        // Každý proces jménem prošel nejvýš jednou.
        let sounds = record
            .timeline
            .iter()
            .filter(|s| s.cause.starts_with("sound:"))
            .count();
        assert!(sounds <= record.applied.len());
    }
}

#[test]
fn zmena_obecneho_slova_jmeno_nezmeni() {
    let (world, events) = scenarios::by_name("kingdom").expect("scénář");
    let mut simulation = Simulation::new(world, config(true), events).expect("simulace");
    let (index, object) = {
        let state = names(&simulation);
        let (object, &index) = state
            .current
            .iter()
            .find(|(k, _)| k.starts_with("language:"))
            .expect("jméno prajazyka");
        (index, object.clone())
    };
    let before = names(&simulation).records[index].clone();
    let concept_name = before.recipe[0].concept.clone().expect("pojem receptu");
    let world = &mut simulation.world;
    let group = world
        .registry
        .groups
        .get(&before.carrier)
        .map(GroupId)
        .expect("nositel");
    let concept = ConceptId(world.registry.concepts.get(&concept_name).expect("pojem"));
    // Slovo pojmu nahradí kořen jiného pojmu (jako výpůjčka nebo posun významu).
    let other = (0..world.registry.concepts.len() as u32)
        .map(ConceptId)
        .filter(|&c| c != concept)
        .map(|c| world.dominant_or_plural_root(group, c))
        .find(|r| !r.is_none() && *r != world.dominant_or_plural_root(group, concept))
        .expect("jiný kořen");
    let language = world.groups.main_code(group).language;
    let language = world.registry.languages.name(language.0).to_owned();
    let today_before = cee_engine::naming::endonym(world, &[before.carrier.clone()]);
    assert!(cee_engine::views::set_dominant(
        world, group, concept, other
    ));
    let today_after = cee_engine::naming::endonym(world, &[before.carrier.clone()]);
    assert_ne!(
        today_before, today_after,
        "starý výpočet jméno z dnešních slov mění"
    );
    let year = simulation.year() + simulation.config.dt;
    let state = simulation.names.as_mut().unwrap();
    state.step(&simulation.world, &[], 1, year, false);
    let after = &state.records[state.current[&object]];
    assert_eq!(
        after.form, before.form,
        "jméno jazyka {language} se změnilo s obecným slovem"
    );
    assert_eq!(
        after.recipe, before.recipe,
        "rozklad jména v historii zůstal"
    );
}

#[test]
fn prejate_jmeno_zacina_v_podobe_darce() {
    let simulation = run("kingdom", 1000.0, true);
    let state = names(&simulation);
    let exonyms: Vec<_> = state
        .records
        .iter()
        .filter(|r| r.role == Role::Exonym)
        .collect();
    assert!(!exonyms.is_empty(), "žádné exonymum");
    for exonym in exonyms {
        let source = exonym.source.as_ref().expect("zdroj exonyma");
        let donor = state
            .records
            .iter()
            .find(|r| r.id == source.record)
            .expect("dárce");
        assert_eq!(
            donor.ipa_at(exonym.founded_year),
            Some(source.ipa.as_str()),
            "{}",
            exonym.id
        );
        assert_ne!(
            donor.language, exonym.language,
            "exonymum vzniká v cizí řeči"
        );
        assert_eq!(exonym.timeline[0].cause, "borrowed");
    }
}

#[test]
fn novi_obyvatele_prevezmou_jmeno_mista() {
    let simulation = run("shift", 1200.0, true);
    let state = names(&simulation);
    let kept: Vec<_> = state
        .records
        .iter()
        .filter(|r| r.object.starts_with("territory:") && r.motivation == "substrate")
        .collect();
    assert!(
        !kept.is_empty(),
        "po přechodu jazyka žádné substrátové jméno"
    );
    for record in kept {
        let source = record.source.as_ref().unwrap();
        assert_ne!(source.language, record.language);
        let old = state
            .records
            .iter()
            .find(|r| r.id == source.record)
            .unwrap();
        assert_eq!(
            old.ended,
            Some(record.founded_year),
            "staré jméno skončilo s převzetím"
        );
    }
}

#[test]
fn pokracovani_z_kontrolniho_bodu_da_stejna_jmena() {
    let straight = run("kingdom", 800.0, true);
    let half = run("kingdom", 400.0, true);
    let bytes = half.checkpoint().to_bytes().expect("uložení");
    let checkpoint = Checkpoint::from_bytes(&bytes).expect("načtení");
    let (_, events) = scenarios::by_name("kingdom").expect("scénář");
    let mut resumed = Simulation::resume(
        checkpoint,
        config(true),
        events,
        cee_engine::changes::default_changes(),
    )
    .expect("pokračování");
    resumed.run(800.0).expect("běh");
    assert_eq!(names(&straight).export(), names(&resumed).export());
}

#[test]
fn generator_mist_podle_epochy() {
    let simulation = run("kingdom", 1000.0, true);
    let state = names(&simulation);
    let region = state.epochs[0].regions.keys().next().unwrap().clone();
    let query = |year: f64, attempt: u64| Query {
        region: region.clone(),
        year,
        count: 4,
        until: Some(1000.0),
        urban: true,
        attempt,
        kind: "place".into(),
    };
    let old = state.generate(&simulation.world, &query(150.0, 0)).unwrap();
    assert_eq!(
        old,
        state.generate(&simulation.world, &query(150.0, 0)).unwrap(),
        "determinismus"
    );
    assert_ne!(
        old,
        state.generate(&simulation.world, &query(150.0, 1)).unwrap(),
        "jiný pokus"
    );
    let young = state.generate(&simulation.world, &query(950.0, 0)).unwrap();
    let steps = |value: &serde_json::Value| -> usize {
        value["names"]
            .as_array()
            .unwrap()
            .iter()
            .map(|n| n["timeline"].as_array().unwrap().len() - 1)
            .sum()
    };
    assert_eq!(old["names"].as_array().unwrap().len(), 4);
    assert!(
        steps(&old) > steps(&young),
        "staré jméno má za sebou víc hláskových změn ({} proti {})",
        steps(&old),
        steps(&young)
    );
    for name in old["names"].as_array().unwrap() {
        assert_eq!(name["timeline"][0]["year"], json!(150.0));
        assert_eq!(name["timeline"][0]["cause"], json!("founded"));
    }
}

#[test]
fn uzamcene_jmeno_prajazyka_ze_zadani() {
    let spec_json = json!({
        "end_year": 300,
        "languages": [{"id": "a", "endonym": ["person", "language"], "endonym_form": "talvera"}, {"id": "b"}],
        "regions": [
            {"id": "c", "position": [0, 0], "neighbours": ["x"], "language": "a", "villages": 3},
            {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3},
        ],
        "semantics": false,
    });
    let world_spec = WorldSpec::from_json(&spec_json.to_string()).unwrap();
    assert!(spec::check(&world_spec)
        .iter()
        .all(|i| !i.path.contains("endonym_form")));
    let (world, events) = spec::build(&world_spec).expect("svět");
    let simulation = Simulation::new(world, config(true), events).expect("simulace");
    let record = names(&simulation)
        .current_of("language:a")
        .expect("jméno jazyka a");
    assert_eq!(record.motivation, "authored");
    assert_eq!(record.timeline[0].ipa, "talvera");
    assert_eq!(record.recipe.len(), 2, "recept zůstává jako výklad");

    let mut bad = spec_json.clone();
    bad["languages"][0]["endonym_form"] = json!("tal§vera");
    let issues = spec::check(&WorldSpec::from_json(&bad.to_string()).unwrap());
    assert!(issues.iter().any(|i| i.path == "languages.0.endonym_form"));
}

#[test]
fn osoby_a_rody_podle_tradice_komunity() {
    let simulation = run("kingdom", 1000.0, true);
    let state = names(&simulation);
    // Každý prajazyk má tradici osobních jmen a linie ji zdědí.
    for (object, steps) in &state.traditions {
        assert!(!steps.is_empty(), "{object}");
        for pair in steps.windows(2) {
            assert!(pair[0].year <= pair[1].year);
            assert_ne!(
                pair[0].paradigm, pair[1].paradigm,
                "{object}: krok bez změny"
            );
        }
    }
    assert!(state.traditions.keys().any(|k| k.starts_with("lineage:")));
    // Zakladatel státu je osoba; jméno státu podle zakladatele odkazuje na jeho záznam.
    let founder = state
        .current_of("person:founder:kingdom")
        .expect("zakladatel království");
    assert!(founder.full_name.as_deref().is_some_and(|f| !f.is_empty()));
    let kingdom = state.current_of("state:kingdom").expect("jméno království");
    if kingdom.motivation == "eponym" {
        let link = kingdom.recipe[0].name.as_deref().unwrap();
        assert!(state
            .records
            .iter()
            .any(|r| r.id == link
                && (r.object.starts_with("person:") || r.object.starts_with("house:"))));
    }
    // Místa pojmenovaná po zakladateli mají zakladatele jako osobu.
    for place in state
        .records
        .iter()
        .filter(|r| r.motivation == "eponymous_founder")
    {
        let link = place.recipe[0]
            .name
            .as_deref()
            .expect("odkaz na zakladatele");
        let person = state.records.iter().find(|r| r.id == link).unwrap();
        assert!(person.object.starts_with("person:founder:"));
        assert_eq!(person.founded_year, place.founded_year);
    }
}

#[test]
fn tradice_se_prenasi_institucemi() {
    // Království se spisovnou normou a školami: poddané linie jiného jazyka převezmou dvorská
    // jména nebo tradici vládnoucího jazyka (aspoň na některém semínku scénáře).
    let simulation = run("kingdom", 1500.0, true);
    let state = names(&simulation);
    let moved: Vec<_> = state
        .traditions
        .values()
        .flatten()
        .filter(|s| {
            matches!(
                s.cause.as_str(),
                "state_standard" | "state_prestige" | "liturgy"
            )
        })
        .collect();
    assert!(
        !moved.is_empty(),
        "žádný přenos tradice: {:?}",
        state.traditions
    );
    for step in moved {
        assert!(step.source.is_some());
    }
}

#[test]
fn generator_osob_podle_tradice_doby() {
    let simulation = run("kingdom", 1000.0, true);
    let state = names(&simulation);
    let region = state.epochs[0].regions.keys().next().unwrap().clone();
    let query = Query {
        region,
        year: 500.0,
        count: 5,
        until: None,
        urban: true,
        attempt: 0,
        kind: "person".into(),
    };
    let people = state.generate(&simulation.world, &query).unwrap();
    assert_eq!(people, state.generate(&simulation.world, &query).unwrap());
    assert_eq!(people["names"].as_array().unwrap().len(), 5);
    let tradition = people["tradition"].as_str().unwrap();
    for person in people["names"].as_array().unwrap() {
        assert_eq!(person["paradigm"].as_str(), Some(tradition));
        assert!(!person["name"].as_str().unwrap().is_empty());
    }
}

#[test]
fn zadana_tradice_osobnich_jmen() {
    let spec_json = json!({
        "end_year": 300,
        "languages": [{"id": "a", "person_names": "house_surety"}, {"id": "b"}],
        "regions": [
            {"id": "c", "position": [0, 0], "neighbours": ["x"], "language": "a", "villages": 3},
            {"id": "x", "position": [60, 0], "neighbours": ["c"], "language": "b", "villages": 3},
        ],
        "semantics": false,
    });
    let world_spec = WorldSpec::from_json(&spec_json.to_string()).unwrap();
    let (world, events) = spec::build(&world_spec).expect("svět");
    let simulation = Simulation::new(world, config(true), events).expect("simulace");
    let steps = &names(&simulation).traditions["language:a"];
    assert_eq!(steps[0].paradigm, "house_surety");
    assert_eq!(steps[0].cause, "authored");
    let mut bad = spec_json.clone();
    bad["languages"][0]["person_names"] = json!("neexistuje");
    let issues = spec::check(&WorldSpec::from_json(&bad.to_string()).unwrap());
    assert!(issues.iter().any(|i| i.path == "languages.0.person_names"));
}

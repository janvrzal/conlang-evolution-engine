//! Události, politika, kontakt, komunity, pozadí dějin a pozorování (R1d).

use cee_engine::edits::{self, Edits, Phase};
use cee_engine::export;
use cee_engine::observe::LineageTracker;
use cee_engine::scenarios;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::state::society::JournalMode;
use cee_engine::{Simulation, SimulationConfig};

fn run(name: &str, until: f64, config: SimulationConfig) -> Simulation {
    let (world, events) = scenarios::by_name(name).expect("scénář");
    let mut simulation = Simulation::new(world, config, events).expect("simulace");
    simulation.run(until).expect("běh");
    simulation
}

fn kinds(simulation: &Simulation, kind: &str) -> usize {
    simulation.history.of_kind(kind).count()
}

#[test]
fn prechod_jazyka_odstrani_stary_kod() {
    let simulation = run("shift", 2500.0, SimulationConfig::default());
    assert_eq!(kinds(&simulation, "bilingualism"), 3);
    assert!(
        kinds(&simulation, "language_shift") >= 1,
        "komunita musí přejít"
    );
    for group in simulation.world.group_ids() {
        assert!(simulation.world.groups.population[group.index()] >= 1);
    }
    // Každý snímek má skupiny jen jednou a jazyky pokrývají mluvené skupiny.
    let last = simulation.history.snapshots.last().expect("snímek");
    let listed: usize = last.languages.values().map(Vec::len).sum();
    let mut dialects: Vec<&String> = last.dialects.iter().flatten().collect();
    dialects.sort();
    dialects.dedup();
    assert_eq!(dialects.len(), listed);
}

#[test]
fn dobyti_a_elita() {
    let simulation = run("conquest", 1500.0, SimulationConfig::default());
    assert_eq!(kinds(&simulation, "conquest"), 1);
    let world = &simulation.world;
    let elite = world.registry.groups.get("l0+e0").expect("elita vznikla");
    let _ = elite;
    // Elita je menšina a přejde na jazyk poddaných.
    assert!(kinds(&simulation, "language_shift") >= 1);
}

#[test]
fn kralovstvi_ma_stat_normy_a_skoly() {
    let (world, events) = scenarios::kingdom(
        1,
        100.0,
        "promoted",
        Some(500.0),
        true,
        Some(300.0),
        &["mountains"],
    )
    .expect("království");
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.run(900.0).unwrap();
    assert_eq!(kinds(&simulation, "state"), 1);
    assert!(kinds(&simulation, "lingua_franca") >= 1);
    assert_eq!(kinds(&simulation, "standard"), 2);
    assert!(kinds(&simulation, "schools") >= 1);
    let exported = export::export(&simulation, true);
    assert_eq!(exported["states"].as_array().unwrap().len(), 1);
    assert_eq!(exported["standards"].as_object().unwrap().len(), 2);
    // Podíly jazyků v regionech se sčítají na 1 (domácí) a nejsou NaN.
    for (_, region) in exported["census"].as_object().unwrap() {
        let total: f64 = region["home"]
            .as_object()
            .unwrap()
            .values()
            .map(|v| v.as_f64().unwrap())
            .sum();
        assert!((total - 1.0).abs() < 1e-9, "součet podílů {total}");
    }
    for group in exported["groups"].as_array().unwrap() {
        assert!(group["population"].as_u64().unwrap() >= 1);
        assert!(group["prestige"].as_f64().unwrap().is_finite());
    }
}

/// Norma národa bez státu (dok. 38): česká pro dva kraje uvnitř německého státu; škola
/// národa na ni odkáže jménem a oba kraje ji čtou.
#[test]
fn norma_naroda_pres_vic_kraju() {
    let evropa: serde_json::Value =
        serde_json::from_str(include_str!("../../../src/cee/data/scenarios/evropa.json")).unwrap();
    let language = |id: &str| {
        evropa["languages"]
            .as_array()
            .unwrap()
            .iter()
            .find(|l| l["id"] == id)
            .unwrap()
            .clone()
    };
    let region = |id: &str, x: i64, lang: &str, neighbours: &[&str]| {
        serde_json::json!({"id": id, "name": id, "position": [x, 0], "neighbours": neighbours,
            "language": lang, "villages": 2})
    };
    let text = serde_json::json!({
        "format": evropa["format"], "name": "národ", "seed": 1, "start_year": 0, "end_year": 300,
        "languages": [language("germanic"), language("slavic")],
        "regions": [region("a", 0, "germanic", &["b"]), region("b", 7, "slavic", &["a", "c"]),
            region("c", 14, "slavic", &["b"])],
        "events": [
            {"kind": "state", "year": 0, "id": "st", "capital": "a", "regions": ["a", "b", "c"]},
            {"kind": "standard", "year": 100, "of": "st"},
            {"kind": "standard", "year": 150, "of": "cestina", "regions": ["b", "c"],
                "literacy": "towns"},
            {"kind": "schools", "year": 200, "of": "cestina"}
        ]
    })
    .to_string();
    let spec = WorldSpec::from_json(&text).unwrap();
    let (world, events) = spec::build(&spec).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.run(300.0).unwrap();
    let world = &simulation.world;
    let czech = world.society.standards["cestina"];
    for name in ["b-v0", "b-v1", "c-v0", "c-v1"] {
        let group = cee_engine::ids::GroupId(world.registry.groups.get(name).unwrap());
        assert_eq!(
            world.groups.standard[group.index()],
            czech,
            "{name} čte českou normu"
        );
        assert!(
            world.groups.schooling[group.index()] > 0.0,
            "{name} chodí do české školy"
        );
    }
    let state = world.society.standards["st"];
    let german = cee_engine::ids::GroupId(world.registry.groups.get("a-v0").unwrap());
    assert_eq!(world.groups.standard[german.index()], state);
    // Jméno národa nesmí kolidovat se státem ani krajem.
    let clash = text.replace("\"of\":\"cestina\",\"regions\"", "\"of\":\"b\",\"regions\"");
    assert_ne!(clash, text);
    let spec = WorldSpec::from_json(&clash).unwrap();
    let (world, events) = spec::build(&spec).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    assert!(simulation.run(300.0).is_err());
}

#[test]
fn hranice_a_strom_jazyku() {
    let simulation = run("tree", 2000.0, SimulationConfig::default());
    assert_eq!(kinds(&simulation, "border"), 2);
    // Hranice s faktorem 0 odřízla vazby.
    let exported = export::export(&simulation, true);
    assert!(!exported["lineages"].as_array().unwrap().is_empty());
}

#[test]
fn matice_vzdalenosti_je_symetricka() {
    let config = SimulationConfig {
        keep_distances: true,
        ..SimulationConfig::default()
    };
    let simulation = run("tree", 500.0, config);
    let snapshot = simulation.history.snapshots.last().unwrap();
    let n = snapshot.group_ids.len();
    let d = snapshot.distances.as_ref().expect("matice");
    assert_eq!(d.len(), n * n);
    for i in 0..n {
        assert!(d[i * n + i].abs() < 1e-9);
        for j in 0..n {
            assert!((d[i * n + j] - d[j * n + i]).abs() < 1e-9);
            assert!(d[i * n + j].is_finite());
        }
    }
}

#[test]
fn stejne_semeno_stejny_beh_nezavisly_na_vlaknech() {
    let digest = |threads: usize| {
        let pool = rayon::ThreadPoolBuilder::new()
            .num_threads(threads)
            .build()
            .unwrap();
        pool.install(|| {
            let simulation = run("kingdom", 600.0, SimulationConfig::default());
            simulation.history.digest()
        })
    };
    let one = digest(1);
    assert_eq!(one, digest(1));
    assert_eq!(one, digest(4));
}

#[test]
fn pozadi_dejin_generuje_udalosti() {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    ))
    .unwrap();
    let mut world_spec = WorldSpec::from_json(&text).unwrap();
    world_spec.background = "turbulent".into();
    let (world, events) = spec::build(&world_spec).unwrap();
    assert!(events.len() > 8, "pozadí přidalo události");
    let (again, again_events) = spec::build(&world_spec).unwrap();
    let described: Vec<_> = events.iter().map(|e| e.describe().to_string()).collect();
    let again_described: Vec<_> = again_events
        .iter()
        .map(|e| e.describe().to_string())
        .collect();
    assert_eq!(described, again_described, "stejný svět dá stejné dějiny");
    let _ = (world, again);
    let (world, events) = spec::build(&world_spec).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.run(world_spec.end_year.min(1200.0)).unwrap();
    let background = simulation
        .history
        .events
        .iter()
        .filter(|e| e.get("background").and_then(|b| b.as_bool()) == Some(true))
        .count();
    assert!(background > 0, "žádná událost pozadí neproběhla");
}

#[test]
fn denik_zmen_se_prehraje_na_novem_svete() {
    let (world, events) = scenarios::by_name("conquest").unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.world.society.journal = JournalMode::All;
    simulation.run(1100.0).unwrap();
    let journal = simulation.world.society.edit_log.clone();
    assert!(!journal.is_empty());
    let (mut fresh, _) = scenarios::by_name("conquest").unwrap();
    for (tick, items) in edits::by_tick(&journal) {
        for item in items.iter().filter(|i| i.phase == Phase::Event) {
            Edits::new(tick).replay(&mut fresh, item).unwrap();
        }
    }
    assert!(fresh.registry.groups.get("l0+e0").is_some());
    let _ = Edits::new(0);
}

#[test]
fn sledovani_linii_rozstepi_a_ukonci() {
    let mut tracker = LineageTracker::default();
    let names = |items: &[&str]| items.iter().map(|s| (*s).to_owned()).collect::<Vec<_>>();
    let first = tracker.update(&[names(&["a", "b", "c", "d"])], 1);
    assert_eq!(first.languages.len(), 1);
    assert_eq!(first.events[0]["kind"], "language_emerged");
    let parent = first.languages.keys().next().unwrap().clone();
    let second = tracker.update(&[names(&["a", "b", "c"]), names(&["d"])], 2);
    assert_eq!(second.languages.len(), 2);
    assert!(
        second.languages.contains_key(&parent),
        "větší shluk pokračuje"
    );
    assert_eq!(second.events.len(), 1);
    assert_eq!(second.events[0]["kind"], "language_split");
    assert_eq!(second.events[0]["parent"], parent.as_str());
    let third = tracker.update(&[names(&["a", "b", "c", "d"])], 3);
    assert_eq!(third.languages.len(), 1);
    assert!(third.events.iter().any(|e| e["kind"] == "language_ended"));
}

#[test]
fn pujcitelnost_odpovida_pythonu() {
    use cee_engine::contact;
    // Hodnoty z `cee.v2.contact` (kotva a normalizace přenositelnosti pojmů).
    assert!((contact::reference() - 0.16028590604026843).abs() < 1e-12);
    assert!((contact::normalizer(3.0, 0.0) - 5.106587626900806).abs() < 1e-9);
    assert!((contact::normalizer(0.5, 0.0) - 1.1159438851452446).abs() < 1e-9);
}

#[test]
fn kanaly_a_filtry_vypujcek() {
    use cee_engine::contact::{self, BorrowTable, ELITE, NEIGHBOR};
    use cee_engine::model::repertoire::VariableKind;
    let (world, _) = scenarios::by_name("conquest").unwrap();
    let table = BorrowTable::build(&world);
    let channels = contact::distinct_channels(&world.params);
    assert_eq!(channels, vec![ELITE, contact::TRADE]);
    let mut lexical = 0;
    for v in 0..world.variables.len() {
        let variable = cee_engine::VariableId::new(v);
        let kind = world.variables.kind[v];
        let neighbor = table.factor(&world, variable, NEIGHBOR);
        assert!(neighbor.is_finite() && neighbor >= 0.0);
        match kind {
            VariableKind::Lexical => lexical += 1,
            VariableKind::Process | VariableKind::Construction => {
                assert!((neighbor - 0.1).abs() < 1e-12)
            }
            _ => assert_eq!(neighbor, 0.0),
        }
    }
    assert!(lexical >= 149);
    // Rozdělení vazby mezi kanály se sčítá na 1.
    let (a, b) = (world.group_ids()[0], world.group_ids()[1]);
    let split = contact::channel_split(&world, a, b, &channels);
    assert!((split.neighbor + split.elite + split.trade - 1.0).abs() < 1e-12);
}

#[test]
fn adaptace_nahradi_cizi_hlasku_nejblizsi_domaci() {
    use cee_engine::contact;
    let (world, events) = scenarios::by_name("conquest").unwrap();
    // Slovní zásobu kódů doplní až stavba simulace.
    let world = Simulation::new(world, SimulationConfig::default(), events)
        .unwrap()
        .world;
    let group = world.group_ids()[0];
    let native = contact::inventory(&world, group);
    assert!(!native.is_empty());
    let table = world.table.as_ref().unwrap();
    let foreign = (0..table.len() as i32 - 1)
        .find(|s| !native.contains(s) && !table.is_vowel(*s) && table.tone_of(*s) == 0)
        .expect("cizí hláska");
    let adapted = contact::adapt(&world, &native, &[native[0], foreign]);
    assert_eq!(adapted[0], native[0]);
    assert!(native.contains(&adapted[1]));
    assert_eq!(table.is_vowel(adapted[1]), table.is_vowel(foreign));
    // Domácí tvar zůstane beze změny.
    assert_eq!(
        contact::adapt(&world, &native, &[native[0]]),
        vec![native[0]]
    );
}

#[test]
fn prevzeti_cizi_korene_zapise_adaptovany_tvar() {
    use cee_engine::contact;
    use cee_engine::MorphemeId;
    let (world, events) = scenarios::by_name("conquest").unwrap();
    let mut world = Simulation::new(world, SimulationConfig::default(), events)
        .unwrap()
        .world;
    let group = world
        .registry
        .groups
        .get("l0")
        .map(cee_engine::GroupId)
        .unwrap();
    let language = world.groups.main_code(group).language;
    let foreign = (0..world.morphemes.len())
        .map(MorphemeId::new)
        .find(|&m| {
            world.morphemes.present[m.index()] && world.morphemes.language[m.index()] != language
        })
        .expect("cizí morfém");
    assert!(world.groups.main_code(group).forms.get(foreign).is_none());
    contact::adopt(&mut world, group, foreign).unwrap();
    let unit = world
        .groups
        .main_code(group)
        .forms
        .get(foreign)
        .expect("tvar převzat");
    let native = contact::inventory(&world, group);
    let form = world.bank.form(unit.form).to_vec();
    assert!(!form.is_empty());
    // Všechny hlásky převzatého tvaru domácí hláskosled užívá (nebo je ve slovní zásobě už zahrnuta).
    let adapted_again = contact::adapt(&world, &native, &form);
    assert_eq!(adapted_again, form);
    // Druhé převzetí nic nemění.
    contact::adopt(&mut world, group, foreign).unwrap();
    assert_eq!(world.groups.main_code(group).forms.get(foreign), Some(unit));
}

//! Běh do složky, čtení zpět a „co kdyby“ z kontrolního bodu.

use super::recorder::{RecordOptions, Recorder};
use super::*;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{export, Simulation, SimulationConfig};

fn dir(name: &str) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let d = std::env::temp_dir().join(format!("cee-store-{name}-{}-{nanos}", std::process::id()));
    fs::create_dir_all(&d).unwrap();
    d
}

fn example() -> (WorldSpec, Value) {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    ))
    .unwrap();
    let mut value: Value = serde_json::from_str(&text).unwrap();
    value["end_year"] = json!(400);
    let events: Vec<Value> = value["events"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|e| e["year"].as_f64().unwrap() <= 400.0)
        .cloned()
        .collect();
    value["events"] = json!(events);
    (WorldSpec::from_json(&value.to_string()).unwrap(), value)
}

/// Spočítá simulaci do `end` a zapíše ji do `writer`.
fn record(simulation: &mut Simulation, writer: &mut RunWriter, end: f64, from_start: bool) {
    // krátký svět: body po 100 letech (výchozí je 250)
    let options = RecordOptions {
        checkpoint_every: Some(100.0),
        ..RecordOptions::default()
    };
    let mut recorder = Recorder::new(simulation, options);
    if from_start {
        recorder.start(simulation).write(writer, 0.0).unwrap();
    }
    while simulation.year() + simulation.config.dt <= end + 1e-9 {
        simulation.step().unwrap();
        recorder
            .collect(simulation)
            .unwrap()
            .write(writer, 1.0)
            .unwrap();
    }
    simulation.observe_now().unwrap();
    recorder
        .collect(simulation)
        .unwrap()
        .write(writer, 1.0)
        .unwrap();
    let result = export::export(simulation, true);
    writer
        .finish(Status::Done, None, 2.0, Some(&result))
        .unwrap();
}

#[test]
fn beh_se_zapise_a_precte() {
    let root = dir("beh");
    let project = root.join("svet.cee.json");
    let runs = runs_dir(&project);
    assert_eq!(runs, root.join("svet.cee.behy"));
    let (world, value) = example();
    let (w, events) = spec::build(&world).unwrap();
    let mut simulation = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    let mut writer = RunWriter::create(
        &runs,
        &NewRun {
            spec: Some(&value),
            engine: Some("test"),
            ..Default::default()
        },
    )
    .unwrap();
    // rozpracovaný běh tohoto procesu je `running`
    assert_eq!(info(&writer.dir).unwrap().status, Status::Running);
    record(&mut simulation, &mut writer, 400.0, true);

    let listed = list(&runs).unwrap();
    assert_eq!(listed.len(), 1);
    let run = runs.join(&listed[0].id);
    let about = &listed[0];
    assert_eq!(about.status, Status::Done);
    assert_eq!(about.year, 400.0);
    assert_eq!(about.spec_hash, spec_hash(&value));
    assert!(about.has_result);
    assert_eq!(about.checkpoints, 4, "body po 100 letech");
    assert_eq!(spec(&run).unwrap(), value);
    let frames = frames(&run, 0).unwrap();
    assert_eq!(frames.len(), about.frames);
    assert_eq!(super::frames(&run, 2).unwrap().len(), frames.len() - 2);
    assert_eq!(result(&run).unwrap().unwrap()["year"], 400.0);

    // protojazyk na startu, dnešní slovník = export
    let years = lexicon_years(&run).unwrap();
    assert_eq!(years[0].0, world.start_year);
    let proto_language = &world.languages[0].id;
    let proto = lexicon(&run, proto_language, world.start_year)
        .unwrap()
        .unwrap();
    assert_eq!(&proto, &simulation.history.proto[proto_language]);
    let now = export::language_lexicons(&simulation);
    for (language, expected) in &now {
        assert_eq!(&lexicon(&run, language, 400.0).unwrap().unwrap(), expected);
    }
    // protojazyk po rozpadu na linie v roce 400 už jako jazyk není (jen pod jménem linie)
    if !now.contains_key(proto_language) {
        assert!(lexicon(&run, proto_language, 400.0).unwrap().is_none());
    }
    let (language, today) = now.iter().next().unwrap();
    let (concept, form) = today.forms.iter().next().unwrap();
    let history = word_history(&run, language, concept).unwrap();
    assert_eq!(history.last().unwrap().form.as_ref(), Some(form));

    // kontrolní bod před rokem větvení
    let point = checkpoint_before(&run, 250.0).unwrap().unwrap();
    assert_eq!(point.year, 200.0);
    let checkpoint = load_checkpoint(&point).unwrap();
    assert_eq!(checkpoint.tick, point.tick);
    assert_eq!(checkpoint.history.events.len(), point.events);
    // záznam událostí v souboru = záznam běhu
    assert_eq!(
        read_lines(&run.join(EVENTS)).unwrap().len(),
        simulation.history.events.len()
    );
    assert!(checkpoint_before(&run, 0.0).unwrap().is_none());

    rename(&run, Some("první")).unwrap();
    assert_eq!(info(&run).unwrap().name.as_deref(), Some("první"));
    assert!(size(&run)["checkpoints"] > 0);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn co_kdyby_navaze_na_rodice() {
    let root = dir("cokdyby");
    let runs = root.join("svet.cee.behy");
    let (world, value) = example();
    let (w, events) = spec::build(&world).unwrap();
    let mut simulation = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    let mut parent = RunWriter::create(
        &runs,
        &NewRun {
            spec: Some(&value),
            ..Default::default()
        },
    )
    .unwrap();
    record(&mut simulation, &mut parent, 400.0, true);
    let parent_dir = parent.dir.clone();

    // změněná pozdější událost: větví se od jejího roku
    let mut changed_value = value.clone();
    let at = changed_value["events"]
        .as_array()
        .unwrap()
        .iter()
        .position(|e| e["year"].as_f64().unwrap() > 200.0)
        .unwrap();
    let old_year = changed_value["events"][at]["year"].as_f64().unwrap();
    changed_value["events"][at]["year"] = json!(old_year + 50.0);
    let changed = WorldSpec::from_json(&changed_value.to_string()).unwrap();
    let branch = spec::branch_year(&world, &changed).unwrap();
    assert_eq!(branch, old_year);
    let point = checkpoint_before(&parent_dir, branch).unwrap().unwrap();

    let mut child = RunWriter::create(
        &runs,
        &NewRun {
            spec: Some(&changed_value),
            parent: Some(&parent.info.id),
            branch_year: Some(branch),
            name: Some("co kdyby"),
            ..Default::default()
        },
    )
    .unwrap();
    child.branch_from(&point).unwrap();
    let checkpoint = load_checkpoint(&point).unwrap();
    let mut resumed = spec::resume(&changed, checkpoint, SimulationConfig::default()).unwrap();
    record(&mut resumed, &mut child, 400.0, false);

    // stejné jako celý běh změněného světa od začátku
    let (w, events) = spec::build(&changed).unwrap();
    let mut fresh = Simulation::new(w, SimulationConfig::default(), events).unwrap();
    fresh.run(400.0).unwrap();
    fresh.observe_now().unwrap();
    assert_eq!(resumed.history.digest(), fresh.history.digest());

    // větev nemá vlastní body před rokem větvení: najde je u rodiče
    let again = checkpoint_before(&child.dir, branch).unwrap().unwrap();
    assert_eq!(again.run, parent_dir);
    assert!(checkpoint_before(&child.dir, 400.0).unwrap().unwrap().run == child.dir);
    assert_eq!(
        read_lines(&child.dir.join(EVENTS)).unwrap().len(),
        resumed.history.events.len()
    );
    let about = info(&child.dir).unwrap();
    assert_eq!(about.parent.as_deref(), Some(parent.info.id.as_str()));
    assert_eq!(about.branch_year, Some(branch));
    // časová osa od začátku: převzaté snímky + nové
    let parent_frames = frames(&parent_dir, 0).unwrap();
    let child_frames = frames(&child.dir, 0).unwrap();
    assert_eq!(child_frames.len(), parent_frames.len());
    assert_eq!(child_frames[0], parent_frames[0]);
    let proto_language = &world.languages[0].id;
    assert!(lexicon(&child.dir, proto_language, world.start_year)
        .unwrap()
        .is_some());
    for (language, expected) in &export::language_lexicons(&fresh) {
        assert_eq!(
            &lexicon(&child.dir, language, 400.0).unwrap().unwrap(),
            expected
        );
    }
    assert_eq!(list(&runs).unwrap().len(), 2);
    delete(&child.dir).unwrap();
    assert_eq!(list(&runs).unwrap().len(), 1);
    fs::remove_dir_all(&root).unwrap();
}

#[test]
fn preruseny_beh_a_useknuty_soubor() {
    let root = dir("pad");
    let mut writer = RunWriter::create(&root, &NewRun::default()).unwrap();
    writer.add_frame(&json!({"year": 100}), 1.0).unwrap();
    writer.add_frame(&json!({"year": 200}), 2.0).unwrap();
    // jiný proces: běh zůstal `running` → přerušený
    writer.info.pid = std::process::id() + 1;
    write_info(&writer.dir, &writer.info).unwrap();
    assert_eq!(info(&writer.dir).unwrap().status, Status::Interrupted);
    // useknutý poslední člen gzipu (pád při zápisu): co jde rozbalit, zůstane; rozbitý
    // poslední člen se zahodí celý nebo po poslední celý řádek
    let path = writer.dir.join(FRAMES);
    let full = fs::read(&path).unwrap();
    for cut in 1..full.len() / 2 {
        fs::write(&path, &full[..full.len() - cut]).unwrap();
        let read = frames(&writer.dir, 0).unwrap();
        assert!(!read.is_empty() && read.len() <= 2, "{cut}");
        assert_eq!(read[0], json!({"year": 100}));
    }
    assert_eq!(stamp(0), "19700101-000000");
    assert_eq!(stamp(1_794_240_000), "20261109-160000");
    fs::remove_dir_all(&root).unwrap();
}

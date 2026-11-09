//! Příkazový řádek enginu: `cee run`, `cee scenario`, `cee export-tick0`.
//!
//! ```text
//! cee run <spec.json> -o export.json [--threads N] [--phase-times]
//! cee scenario <jméno> --until <rok> [-o export.json] [--threads N] [--history log.jsonl]
//! cee export-tick0 <scénář|spec.json> [-o tick0.json]
//! cee names <scénář|spec.json> --until <rok> [--region R --year Y[,Y2…] [--count N] [--village|--people]] [-o names.json]
//! cee scenarios
//! cee behavior [scénář ...] [--seeds 1..3] [-o behavior.json]
//! cee gates [--seeds 201] [--only m4b,m5::s3_substrat] [--list] [-o values.jsonl]
//! cee calibrate [--seeds 1] [--only typologie,m7::retence] [--set jméno=hodnota ...] [--variants varianty.json] [--list] [-o values.jsonl]
//! ```

use std::process::ExitCode;

use cee_engine::checkpoint::Checkpoint;
use cee_engine::export;
use cee_engine::gates;
use cee_engine::scenarios;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};

fn usage() -> String {
    "Použití:\n  cee run <spec.json> -o export.json [--threads N] [--phase-times]\n  cee scenario <jméno> --until <rok> [-o export.json] [--threads N] [--phase-times] [--history log.jsonl]\n  cee export-tick0 <scénář|spec.json> [-o tick0.json]\n  cee names <scénář|spec.json> --until <rok> [--region R --year Y[,Y2…] [--count N] [--village|--people] [--attempt K]] [-o names.json]\n  cee scenarios\n  cee behavior [scénář ...] [--seeds 1..3] [-o behavior.json]\n  cee gates [--seeds 201] [--only m4b,m5::s3_substrat] [--list] [-o values.jsonl]\n  cee calibrate [--seeds 1] [--only typologie,m7::retence] [--set jméno=hodnota ...] [--variants varianty.json] [--list] [-o values.jsonl]".to_owned()
}

struct Options {
    positional: Vec<String>,
    output: Option<String>,
    until: Option<f64>,
    threads: Option<usize>,
    checkpoint: Option<String>,
    history: Option<String>,
    seeds: Option<String>,
    only: Option<String>,
    list: bool,
    sets: Vec<String>,
    variants: Option<String>,
    phase_times: bool,
    region: Option<String>,
    year: Option<String>,
    count: Option<usize>,
    village: bool,
    people: bool,
    attempt: u64,
}

fn parse(args: &[String]) -> Result<Options, String> {
    let mut options = Options {
        positional: Vec::new(),
        output: None,
        until: None,
        threads: None,
        checkpoint: None,
        history: None,
        seeds: None,
        only: None,
        list: false,
        sets: Vec::new(),
        variants: None,
        phase_times: false,
        region: None,
        year: None,
        count: None,
        village: false,
        people: false,
        attempt: 0,
    };
    let mut iter = args.iter();
    while let Some(arg) = iter.next() {
        let mut value = |name: &str| {
            iter.next()
                .cloned()
                .ok_or_else(|| format!("{name} chce hodnotu"))
        };
        match arg.as_str() {
            "-o" | "--output" => options.output = Some(value("-o")?),
            "--until" => {
                options.until = Some(
                    value("--until")?
                        .parse()
                        .map_err(|_| "--until chce číslo")?,
                )
            }
            "--threads" => {
                options.threads = Some(
                    value("--threads")?
                        .parse()
                        .map_err(|_| "--threads chce číslo")?,
                )
            }
            "--checkpoint" => options.checkpoint = Some(value("--checkpoint")?),
            "--history" => options.history = Some(value("--history")?),
            "--seeds" => options.seeds = Some(value("--seeds")?),
            "--only" => options.only = Some(value("--only")?),
            "--list" => options.list = true,
            "--set" => options.sets.push(value("--set")?),
            "--variants" => options.variants = Some(value("--variants")?),
            "--phase-times" => options.phase_times = true,
            "--region" => options.region = Some(value("--region")?),
            "--year" => options.year = Some(value("--year")?),
            "--count" => {
                options.count = Some(value("--count")?.parse().map_err(|_| "--count chce číslo")?)
            }
            "--attempt" => {
                options.attempt = value("--attempt")?.parse().map_err(|_| "--attempt chce číslo")?
            }
            "--village" => options.village = true,
            "--people" => options.people = true,
            other if other.starts_with('-') => return Err(format!("neznámý přepínač {other}")),
            other => options.positional.push(other.to_owned()),
        }
    }
    Ok(options)
}

/// Varianty kalibrace: výchozí, `--set` (jedna varianta „přepis“) a `--variants` (soubor
/// `{"jméno": {"parametr": hodnota}}`). Hodnota `--set` je JSON, jinak text.
fn calibration_variants(
    options: &Options,
) -> Result<Vec<cee_engine::calibration::Variant>, String> {
    use cee_engine::calibration::Variant;
    let mut variants = vec![Variant::base()];
    if !options.sets.is_empty() {
        let mut overrides = serde_json::Map::new();
        for item in &options.sets {
            let (name, text) = item
                .split_once('=')
                .ok_or_else(|| format!("--set chce jméno=hodnota, ne {item}"))?;
            let value = serde_json::from_str(text)
                .unwrap_or_else(|_| serde_json::Value::String(text.to_owned()));
            overrides.insert(name.trim().to_owned(), value);
        }
        variants.push(Variant::new("přepis", overrides)?);
    }
    if let Some(path) = &options.variants {
        let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
        let file: serde_json::Map<String, serde_json::Value> =
            serde_json::from_str(&text).map_err(|e| format!("{path}: {e}"))?;
        for (name, overrides) in file {
            let overrides = overrides
                .as_object()
                .cloned()
                .ok_or_else(|| format!("{path}: varianta {name} chce objekt přepisů"))?;
            variants.push(Variant::new(&name, overrides)?);
        }
    }
    Ok(variants)
}

/// Konfigurace běhů pro export: výchozí a s modulem jmen.
fn named() -> SimulationConfig {
    SimulationConfig {
        names: true,
        ..SimulationConfig::default()
    }
}

/// Svět ze scénáře nebo ze souboru popisu (`.json`).
fn world_of(name: &str) -> Result<(cee_engine::world::World, Vec<Box<dyn cee_engine::events::WorldEvent>>), String> {
    if name.ends_with(".json") {
        let text = std::fs::read_to_string(name).map_err(|e| format!("{name}: {e}"))?;
        spec::build(&WorldSpec::from_json(&text)?)
    } else {
        scenarios::by_name(name)
    }
}

fn write(path: &Option<String>, value: &serde_json::Value) -> Result<(), String> {
    let text = serde_json::to_string_pretty(value).map_err(|e| e.to_string())?;
    match path {
        Some(path) => std::fs::write(path, text).map_err(|e| format!("{path}: {e}")),
        None => {
            println!("{text}");
            Ok(())
        }
    }
}

fn run_simulation(mut simulation: Simulation, until: f64, options: &Options) -> Result<(), String> {
    simulation.run(until)?;
    simulation.observe_now()?;
    if let Some(path) = &options.checkpoint {
        let bytes = simulation.checkpoint().to_bytes()?;
        std::fs::write(path, bytes).map_err(|e| format!("{path}: {e}"))?;
        let _ = Checkpoint::from_bytes(&std::fs::read(path).map_err(|e| e.to_string())?)?;
    }
    if let Some(path) = &options.history {
        let mut text = simulation.history.lines().join("\n");
        text.push('\n');
        std::fs::write(path, text).map_err(|e| format!("{path}: {e}"))?;
    }
    eprint!("{}", cee_engine::timing::report());
    eprintln!(
        "hotovo: rok {}, {} kroků, {} záznamů, {} tvarů v bance, otisk {}",
        simulation.year(),
        simulation.tick,
        simulation.history.events.len(),
        simulation.world.bank.bank.len(),
        simulation.history.digest()
    );
    write(&options.output, &export::export(&simulation, true))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = (|| -> Result<(), String> {
        let (command, rest) = args.split_first().ok_or_else(usage)?;
        let options = parse(rest)?;
        cee_engine::timing::enable_from_env();
        if options.phase_times {
            cee_engine::timing::enable();
        }
        match options.threads {
            Some(threads) => cee_engine::parallel::set_threads(threads),
            None => cee_engine::parallel::init_default(0),
        }
        match command.as_str() {
            "run" => {
                let path = options
                    .positional
                    .first()
                    .ok_or("chybí soubor popisu světa")?;
                let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
                let world_spec = WorldSpec::from_json(&text)?;
                let (world, events) = spec::build(&world_spec)?;
                let simulation = Simulation::new(world, named(), events)?;
                run_simulation(simulation, world_spec.end_year, &options)
            }
            "scenario" => {
                let name = options.positional.first().ok_or("chybí jméno scénáře")?;
                let until = options.until.ok_or("chybí --until <rok>")?;
                let (world, events) = scenarios::by_name(name)?;
                let simulation = Simulation::new(world, named(), events)?;
                run_simulation(simulation, until, &options)
            }
            "export-tick0" => {
                let name = options.positional.first().ok_or("chybí jméno scénáře")?;
                // Cesta k souboru `.json` = popis světa (`WorldSpec`), jinak jméno scénáře.
                let (world, events) = if name.ends_with(".json") {
                    let text = std::fs::read_to_string(name).map_err(|e| format!("{name}: {e}"))?;
                    spec::build(&WorldSpec::from_json(&text)?)?
                } else {
                    scenarios::by_name(name)?
                };
                let simulation = Simulation::new(world, named(), events)?;
                write(&options.output, &export::export(&simulation, true))
            }
            "names" => {
                let name = options.positional.first().ok_or("chybí scénář nebo popis světa")?;
                let until = options.until.ok_or("chybí --until <rok>")?;
                let (world, events) = world_of(name)?;
                let mut simulation = Simulation::new(world, named(), events)?;
                simulation.run(until)?;
                simulation.observe_now()?;
                eprint!("{}", cee_engine::timing::report());
                let names = simulation.names.as_ref().ok_or("modul jmen neběžel")?;
                let value = match (&options.region, &options.year) {
                    (Some(region), Some(years)) => {
                        let mut found = Vec::new();
                        for year in years.split(',') {
                            let year: f64 =
                                year.trim().parse().map_err(|_| "--year chce čísla oddělená čárkou")?;
                            found.push(names.generate(
                                &simulation.world,
                                &cee_engine::names::generate::Query {
                                    region: region.clone(),
                                    year,
                                    count: options.count.unwrap_or(5),
                                    until: Some(until),
                                    urban: !options.village,
                                    attempt: options.attempt,
                                    kind: if options.people { "person" } else { "place" }.into(),
                                },
                            )?);
                        }
                        serde_json::Value::Array(found)
                    }
                    (None, None) => names.export(),
                    _ => return Err("generátor chce --region i --year".into()),
                };
                write(&options.output, &value)
            }
            "gates" => {
                if options.list {
                    print!("{}", gates::statistical::list()?);
                    return Ok(());
                }
                let start = gates::parse_seeds(options.seeds.as_deref().unwrap_or("201"))?[0];
                let rows = gates::statistical::run_rows(&gates::statistical::ReportOptions {
                    start,
                    only: options
                        .only
                        .as_deref()
                        .map(|text| text.split(',').map(|s| s.trim().to_owned()).collect())
                        .unwrap_or_default(),
                    jsonl: options.output.clone(),
                })?;
                print!("{}", gates::statistical::render(&rows));
                let failed = rows.iter().filter(|row| !row.passed).count();
                if failed > 0 {
                    return Err(format!("{failed} veličin bran neprošlo"));
                }
                Ok(())
            }
            "calibrate" => {
                if options.list {
                    print!("{}", cee_engine::calibration::list()?);
                    return Ok(());
                }
                let start = gates::parse_seeds(options.seeds.as_deref().unwrap_or("1"))?[0];
                let rows = cee_engine::calibration::run_rows(&cee_engine::calibration::Options {
                    start,
                    only: options
                        .only
                        .as_deref()
                        .map(|text| text.split(',').map(|s| s.trim().to_owned()).collect())
                        .unwrap_or_default(),
                    variants: calibration_variants(&options)?,
                    jsonl: options.output.clone(),
                })?;
                print!("{}", cee_engine::calibration::render(&rows));
                Ok(())
            }
            "behavior" => {
                let seeds = match options.seeds.as_deref() {
                    Some(text) => gates::parse_seeds(text)?,
                    None => cee_engine::behavior::SEEDS.to_vec(),
                };
                let only: Vec<String> = options.positional.clone();
                if only.first().map(String::as_str) == Some("region-square") {
                    return write(&options.output, &cee_engine::behavior::run_square(&seeds)?);
                }
                write(&options.output, &cee_engine::behavior::run(&only, &seeds)?)
            }
            "scenarios" => {
                println!("{}", scenarios::SCENARIO_NAMES.join("\n"));
                Ok(())
            }
            _ => Err(usage()),
        }
    })();
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

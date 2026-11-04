//! Příkazový řádek enginu: `cee run`, `cee scenario`, `cee export-tick0`.
//!
//! ```text
//! cee run <spec.json> -o export.json [--threads N]
//! cee scenario <jméno> --until <rok> [-o export.json] [--threads N] [--history log.jsonl]
//! cee export-tick0 <scénář|spec.json> [-o tick0.json]
//! cee scenarios
//! cee behavior [scénář ...] [--seeds 1..3] [-o behavior.json]
//! cee gates [--seeds 101..120] [--only m4b,m5::s3_substrat] [--metrics] [--list] [-o audit.jsonl]
//! ```

use std::process::ExitCode;

use cee_engine::checkpoint::Checkpoint;
use cee_engine::export;
use cee_engine::gates;
use cee_engine::scenarios;
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{Simulation, SimulationConfig};

fn usage() -> String {
    "Použití:\n  cee run <spec.json> -o export.json [--threads N]\n  cee scenario <jméno> --until <rok> [-o export.json] [--threads N] [--history log.jsonl]\n  cee export-tick0 <scénář|spec.json> [-o tick0.json]\n  cee scenarios\n  cee behavior [scénář ...] [--seeds 1..3] [-o behavior.json]\n  cee gates [--seeds 101..120] [--only m4b,m5::s3_substrat] [--metrics] [--list] [-o audit.jsonl]".to_owned()
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
    metrics: bool,
    list: bool,
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
        metrics: false,
        list: false,
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
            "--metrics" => options.metrics = true,
            "--list" => options.list = true,
            other if other.starts_with('-') => return Err(format!("neznámý přepínač {other}")),
            other => options.positional.push(other.to_owned()),
        }
    }
    Ok(options)
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
    eprintln!(
        "hotovo: rok {}, {} kroků, {} záznamů, otisk {}",
        simulation.year(),
        simulation.tick,
        simulation.history.events.len(),
        simulation.history.digest()
    );
    write(&options.output, &export::export(&simulation, true))
}

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = (|| -> Result<(), String> {
        let (command, rest) = args.split_first().ok_or_else(usage)?;
        let options = parse(rest)?;
        if let Some(threads) = options.threads {
            cee_engine::parallel::set_threads(threads);
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
                let simulation = Simulation::new(world, SimulationConfig::default(), events)?;
                run_simulation(simulation, world_spec.end_year, &options)
            }
            "scenario" => {
                let name = options.positional.first().ok_or("chybí jméno scénáře")?;
                let until = options.until.ok_or("chybí --until <rok>")?;
                let (world, events) = scenarios::by_name(name)?;
                let simulation = Simulation::new(world, SimulationConfig::default(), events)?;
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
                let simulation = Simulation::new(world, SimulationConfig::default(), events)?;
                write(&options.output, &export::export(&simulation, true))
            }
            "gates" => {
                if options.list {
                    print!("{}", gates::audit::list());
                    return Ok(());
                }
                let audit = gates::audit::AuditOptions {
                    seeds: gates::parse_seeds(options.seeds.as_deref().unwrap_or("101..120"))?,
                    only: options
                        .only
                        .as_deref()
                        .map(|text| text.split(',').map(|s| s.trim().to_owned()).collect())
                        .unwrap_or_default(),
                    metrics: options.metrics,
                    jsonl: options.output.clone(),
                };
                print!("{}", gates::audit::run(&audit)?);
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

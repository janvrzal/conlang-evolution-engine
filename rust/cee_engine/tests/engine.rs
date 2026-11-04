//! Kostra enginu: stavba světa, fáze kroku, determinismus nezávislý na vláknech, kontrolní body.

use cee_engine::changes::{Change, InnovationContext, NewVariant, Sites};
use cee_engine::checkpoint::Checkpoint;
use cee_engine::export;
use cee_engine::ids::VariableId;
use cee_engine::model::repertoire::{Origin, Payload, VariableKind};
use cee_engine::rng::{stable_id, Part, Stream};
use cee_engine::scenarios::{self, SeedOptions};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::world::World;
use cee_engine::{Simulation, SimulationConfig};

/// Zkušební změna: na místech všech lexikálních proměnných skupiny navrhuje nové varianty.
struct Toy;

impl Change for Toy {
    fn kind(&self) -> &'static str {
        "toy"
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        let mut sites: Vec<VariableId> = (0..world.variables.len())
            .map(VariableId::new)
            .filter(|v| world.variables.kind[v.index()] == VariableKind::Lexical)
            .filter(|&v| world.distribution(ctx.group, v).is_some())
            .collect();
        sites.sort_by(|a, b| {
            world
                .registry
                .variables
                .name(a.0)
                .cmp(world.registry.variables.name(b.0))
        });
        let weights = sites.iter().map(|v| 1.0 + (v.0 % 3) as f64).collect();
        Sites {
            sites,
            weights: Some(weights),
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        self.weighted_sites(world, ctx).sites.len() as f64 * 0.01
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        index: usize,
    ) -> Option<NewVariant> {
        let draw = rng.integers(1_000_000);
        let name = stable_id(
            "variant",
            &[
                Part::Str("toy"),
                Part::Str(world.registry.variables.name(site.0)),
                Part::Uint(draw),
                Part::Uint(index as u64),
            ],
        );
        let origin = Origin {
            change: Some("toy".into()),
            tick: ctx.tick,
            year: ctx.year,
            group: ctx.group,
            parent: cee_engine::VariantId::NONE,
        };
        Some(NewVariant {
            name,
            variable: site,
            payload: Payload::Other(serde_json::json!({"toy": draw})),
            origin,
        })
    }
}

fn grid() -> World {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    scenarios::village_grid_default(4, 2, 5, &options).expect("svět")
}

fn toy_simulation() -> Simulation {
    let config = SimulationConfig {
        observe_every: 2,
        ..SimulationConfig::default()
    };
    Simulation::with_changes(grid(), config, Vec::new(), vec![Box::new(Toy)]).expect("simulace")
}

#[test]
fn svet_ma_zakladni_tvar() {
    let world = grid();
    assert_eq!(world.group_ids().len(), 8);
    assert!(!world.links.is_empty());
    assert!(world.morphemes.len() > 150);
    assert!(world.segments().is_some());
    let first = world.group_ids()[0];
    // Každý pojem výchozího slovníku má v repertoáru skupiny jedno slovo.
    let lexical = (0..world.variables.len())
        .filter(|&v| world.variables.kind[v] == VariableKind::Lexical)
        .count();
    assert!(lexical >= 149);
    assert!(
        world
            .groups
            .main_code(first)
            .repertoire
            .variable_ids()
            .len()
            >= lexical
    );
}

#[test]
fn kostra_bezi_a_inovace_vznikaji() {
    let mut simulation = toy_simulation();
    simulation.run(400.0).unwrap();
    assert_eq!(simulation.tick, 16);
    assert!(
        simulation.history.of_kind("innovation").count() > 0,
        "zkušební změna musí vyvolat inovace"
    );
    assert_eq!(simulation.snapshots().len(), 8);
    let exported = export::export(&simulation, true);
    assert_eq!(exported["format"], "cee-v2/1");
    assert_eq!(exported["tick"], 16);
    assert_eq!(exported["groups"].as_array().unwrap().len(), 8);
    assert!(!simulation.world.live.is_empty());
}

fn digest_with_threads(threads: usize) -> String {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    pool.install(|| {
        let mut simulation = toy_simulation();
        simulation.run(300.0).unwrap();
        simulation.history.digest()
    })
}

#[test]
fn vysledek_nezavisi_na_poctu_vlaken() {
    let one = digest_with_threads(1);
    assert_eq!(one, digest_with_threads(4));
    assert_eq!(one, digest_with_threads(3));
}

#[test]
fn kontrolni_bod_a_pokracovani() {
    let mut straight = toy_simulation();
    straight.run(300.0).unwrap();

    let mut first = toy_simulation();
    first.run(150.0).unwrap();
    let bytes = first.checkpoint().to_bytes().unwrap();
    let restored = Checkpoint::from_bytes(&bytes).unwrap();
    assert_eq!(restored.tick, 6);
    let config = SimulationConfig {
        observe_every: 2,
        ..SimulationConfig::default()
    };
    let mut resumed =
        Simulation::resume(restored, config, Vec::new(), vec![Box::new(Toy)]).unwrap();
    resumed.run(300.0).unwrap();
    assert_eq!(
        resumed.history.digest(),
        straight.history.digest(),
        "pokračování musí dát stejný běh"
    );
    assert_eq!(resumed.tick, straight.tick);
}

#[test]
fn spec_se_postavi_a_odmitne_chybne() {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    ))
    .unwrap();
    let world_spec = WorldSpec::from_json(&text).unwrap();
    let (world, events) = spec::build(&world_spec).unwrap();
    assert_eq!(world.group_ids().len(), 4 * 4);
    assert_eq!(events.len(), 8);
    let mut bigger = world_spec.clone();
    bigger.vocabulary = 200;
    assert!(spec::build(&bigger).is_ok(), "větší slovník se staví");
    bigger.vocabulary = 1_000_000;
    assert!(spec::build(&bigger).is_err());
    let mut unknown = world_spec;
    unknown.parameters.insert("nesmysl".into(), 1.into());
    assert!(spec::build(&unknown).is_err());
}

#[test]
fn udalost_se_provede() {
    // Přechod jazyka (R1d) běží: skupiny `x` přejdou na kód `y0`.
    let (world, events) = scenarios::language_shift(2, 300.0).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), events).unwrap();
    simulation.run(400.0).unwrap();
    assert!(simulation.history.of_kind("bilingualism").count() > 0);
}

#[test]
fn zivy_sklad_a_uvolneni() {
    let mut simulation = toy_simulation();
    simulation.run(100.0).unwrap();
    let world = &simulation.world;
    for variable in world.live.variable_ids() {
        for &group in &world.live.group_ids {
            if let Some(distribution) = world.distribution(group, variable) {
                let total: f64 = distribution.freqs.iter().sum();
                assert!((total - 1.0).abs() < 1e-9, "součet podílů je {total}");
            }
        }
    }
}

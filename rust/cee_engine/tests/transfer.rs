//! Přenos a tlaky (R1a): inovace se šíří, podíly se sčítají na 1, nic není NaN, běh je
//! deterministický a nezávisí na počtu vláken.

use cee_engine::changes::{Change, InnovationContext, NewVariant, Sites, LEXICAL_PRESSURES};
use cee_engine::ids::{VariableId, VariantId};
use cee_engine::model::repertoire::{Origin, Payload, VariableKind};
use cee_engine::rng::{stable_id, Part, Stream};
use cee_engine::scenarios::{self, SeedOptions};
use cee_engine::transfer::network::mixing;
use cee_engine::world::World;
use cee_engine::{Simulation, SimulationConfig};

/// Zkušební lexikální inovace: nové slovo ke stejnému morfému s vysokou přitažlivostí.
struct Attractive;

impl Change for Attractive {
    fn kind(&self) -> &'static str {
        "attractive"
    }

    fn target(&self) -> VariableKind {
        VariableKind::Lexical
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &LEXICAL_PRESSURES
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
        Sites {
            sites,
            weights: None,
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        self.weighted_sites(world, ctx).sites.len() as f64 * 0.001
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
                Part::Str("attractive"),
                Part::Str(world.registry.variables.name(site.0)),
                Part::Uint(draw),
                Part::Uint(index as u64),
            ],
        );
        let (incumbent, _) = world.dominant(ctx.group, site)?;
        let Payload::Lexical {
            lexeme, morpheme, ..
        } = world.variants.payload[incumbent.index()].clone()
        else {
            return None;
        };
        Some(NewVariant {
            name,
            variable: site,
            payload: Payload::Lexical {
                lexeme,
                morpheme,
                origin: "derivation".into(),
                appeal: 0.8,
            },
            origin: Origin {
                change: Some("attractive".into()),
                tick: ctx.tick,
                year: ctx.year,
                group: ctx.group,
                parent: VariantId::NONE,
            },
        })
    }
}

fn simulation() -> Simulation {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let world = scenarios::village_grid_default(4, 2, 5, &options).expect("svět");
    let config = SimulationConfig {
        observe_every: 0,
        ..SimulationConfig::default()
    };
    Simulation::with_changes(world, config, Vec::new(), vec![Box::new(Attractive)])
        .expect("simulace")
}

#[test]
fn mizeni_ma_radky_se_souctem_jedna() {
    let world = simulation().world;
    let axis = world.live.group_ids.clone();
    let rows = mixing(&world, &axis, 1.0);
    assert_eq!(rows.len(), axis.len());
    for entries in &rows {
        let total: f64 = entries.iter().map(|&(_, w)| w).sum();
        assert!(
            (total - 1.0).abs() < 1e-12,
            "řádek míšení má součet {total}"
        );
        assert!(entries.windows(2).all(|pair| pair[0].0 < pair[1].0));
    }
}

#[test]
fn pritazliva_inovace_se_siri_a_podily_jsou_v_poradku() {
    let mut simulation = simulation();
    simulation.run(3000.0).unwrap();
    let history = &simulation.history;
    assert!(history.of_kind("innovation").count() > 0);
    let milestones = history.of_kind("milestone").count();
    assert!(
        milestones > 0,
        "inovace s vysokou přitažlivostí se musí šířit"
    );
    assert!(
        history.of_kind("milestone").any(|e| e["level"] == 0.9),
        "někde musí inovace překročit devadesát procent"
    );
    assert!(history.of_kind("established").count() > 0);
    let world = &simulation.world;
    for variable in world.live.variable_ids() {
        for &group in &world.live.group_ids {
            if let Some(distribution) = world.distribution(group, variable) {
                let total: f64 = distribution.freqs.iter().sum();
                assert!((total - 1.0).abs() < 1e-9, "součet podílů je {total}");
                assert!(distribution
                    .freqs
                    .iter()
                    .chain(&distribution.previous)
                    .all(|v| v.is_finite() && *v >= 0.0));
            }
        }
    }
}

#[test]
fn zaznamy_milniku_jsou_v_kanonickem_poradi() {
    let mut simulation = simulation();
    simulation.run(800.0).unwrap();
    let mut last: Option<(u64, String)> = None;
    for event in simulation.history.events.iter().filter(|e| {
        matches!(
            e["kind"].as_str(),
            Some("milestone" | "established" | "extinct")
        )
    }) {
        let tick = event["tick"].as_u64().unwrap();
        let kind = event["kind"].as_str().unwrap().to_owned();
        if let Some((previous_tick, previous_kind)) = &last {
            assert!(
                tick > *previous_tick || (tick == *previous_tick && kind >= *previous_kind),
                "záznamy jednoho kroku jsou seřazené podle druhu"
            );
        }
        last = Some((tick, kind));
    }
}

fn digest_with_threads(threads: usize) -> String {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    pool.install(|| {
        let mut simulation = simulation();
        simulation.run(800.0).unwrap();
        simulation.history.digest()
    })
}

#[test]
fn vysledek_je_deterministicky_a_nezavisi_na_vlaknech() {
    let one = digest_with_threads(1);
    assert_eq!(one, digest_with_threads(1));
    assert_eq!(one, digest_with_threads(4));
}

#[test]
fn norm_zvyhodni_kodifikovanou_variantu_uumerne_skolni_docazce() {
    use cee_engine::transfer::network::{prepare, TransmissionParams};
    use cee_engine::transfer::pressures::{plan, Pressures};

    let mut simulation = simulation();
    simulation.run(1000.0).unwrap();
    let mut world = simulation.world.clone();
    cee_engine::transfer::sync(&mut world);
    let axis = world.live.group_ids.clone();
    let (standard, learner) = (axis[0], axis[1]);
    let config = SimulationConfig::default();
    let params = TransmissionParams {
        dt: config.dt,
        alpha: config.alpha,
        selection: config.selection,
        kappa: config.kappa,
        sigma: config.sigma,
        adult_rate: config.adult_rate,
        loss_threshold: config.loss_threshold,
        establish_threshold: config.establish_threshold,
    };
    let compute = |world: &World, block: &cee_engine::model::pools::PoolBlock, row: usize| {
        let inputs = prepare(world, &params, 1);
        let pressure_plan = plan(&world.params).unwrap();
        let pressures = Pressures::new(world, &inputs, &pressure_plan).unwrap();
        let cells = axis.len() * block.capacity;
        let mut current = vec![0.0; cells];
        let mut previous = vec![0.0; cells];
        block.cells.row_dense(row, &mut current, &mut previous);
        let heard = vec![0.0; cells];
        let mut out = vec![0.0; cells];
        pressures.fitness(block, row, 1, &current, &heard, &mut out);
        out
    };
    // Řádek, ve kterém standardní skupina má kodifikovanou variantu a řádek má víc variant.
    let mut checked = false;
    'search: for block in world.live.iter_blocks() {
        for row in 0..block.len() {
            let variable = block.variables[row];
            let Some((codified, _)) = world.dominant(standard, variable) else {
                continue;
            };
            let Some(slot) = block.slots[row].iter().position(|&v| v == codified) else {
                continue;
            };
            if block.slots[row].iter().filter(|v| !v.is_none()).count() < 2 {
                continue;
            }
            let before = compute(&world, block, row);
            let mut schooled = world.clone();
            cee_engine::transfer::sync(&mut schooled);
            schooled.groups.schooling[learner.index()] = 0.5;
            schooled.groups.standard[learner.index()] = standard;
            let after = compute(&schooled, block, row);
            let column = 1;
            for (at, (b, a)) in before.iter().zip(&after).enumerate() {
                if at == column * block.capacity + slot {
                    assert!(
                        (a - b - 0.3 * 0.5).abs() < 1e-12,
                        "norma {} místo 0,15",
                        a - b
                    );
                } else {
                    assert_eq!(b, a);
                }
            }
            checked = true;
            break 'search;
        }
    }
    assert!(checked, "svět musí mít řádek s kodifikovanou variantou");
}

#[test]
fn tabu_opotrebuje_inovovane_slovo_po_deseti_generacich() {
    use cee_engine::transfer::network::{prepare, TransmissionParams};
    use cee_engine::transfer::pressures::{plan, Pressures};

    let mut simulation = simulation();
    simulation.run(1000.0).unwrap();
    let mut world = simulation.world.clone();
    cee_engine::transfer::sync(&mut world);
    let axis = world.live.group_ids.clone();
    let learner = axis[1];
    let config = SimulationConfig::default();
    let params = TransmissionParams {
        dt: config.dt,
        alpha: config.alpha,
        selection: config.selection,
        kappa: config.kappa,
        sigma: config.sigma,
        adult_rate: config.adult_rate,
        loss_threshold: config.loss_threshold,
        establish_threshold: config.establish_threshold,
    };
    let compute = |world: &World, tick: u32, block: &cee_engine::model::pools::PoolBlock, row| {
        let inputs = prepare(world, &params, tick);
        let pressure_plan = plan(&world.params).unwrap();
        let pressures = Pressures::new(world, &inputs, &pressure_plan).unwrap();
        let cells = axis.len() * block.capacity;
        let mut current = vec![0.0; cells];
        let mut previous = vec![0.0; cells];
        block.cells.row_dense(row, &mut current, &mut previous);
        let mut out = vec![0.0; cells];
        pressures.fitness(block, row, 1, &current, &vec![0.0; cells], &mut out);
        out
    };
    let mut checked = false;
    'search: for block in world.live.iter_blocks() {
        for row in 0..block.len() {
            let variable = block.variables[row];
            if world.variables.kind[variable.index()] != VariableKind::Lexical {
                continue;
            }
            let Some(slot) = block.slots[row]
                .iter()
                .position(|&v| !v.is_none() && world.variants.innovation[v.index()])
            else {
                continue;
            };
            let concept = world.variables.concept[variable.index()];
            let mut tabooed = world.clone();
            cee_engine::transfer::sync(&mut tabooed);
            tabooed.groups.taboo[learner.index()] = vec![concept];
            // Brzy po vzniku slova tabu nepůsobí, po deseti generacích ano.
            let young = world.variants.origin[block.slots[row][slot].index()].tick;
            let early = compute(&world, young + 1, block, row);
            let early_taboo = compute(&tabooed, young + 1, block, row);
            assert_eq!(early, early_taboo);
            let late = compute(&world, young + 20, block, row);
            let late_taboo = compute(&tabooed, young + 20, block, row);
            for (at, (b, a)) in late.iter().zip(&late_taboo).enumerate() {
                if at == block.capacity + slot {
                    assert!((a - b + 0.6).abs() < 1e-12, "tabu {} místo −0,6", a - b);
                } else {
                    assert_eq!(b, a);
                }
            }
            checked = true;
            break 'search;
        }
    }
    assert!(checked, "svět musí mít inovované slovo");
}

#[test]
fn ekonomie_tresta_volny_opis_a_nic_jineho_nedela() {
    use cee_engine::grammar::Construction;
    use cee_engine::model::repertoire::Distribution;
    use cee_engine::transfer::network::{prepare, TransmissionParams};
    use cee_engine::transfer::pressures::{plan, Pressures, NAMES};
    use std::sync::Arc;

    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    let mut world = scenarios::village_grid_default(2, 2, 5, &options).expect("svět");
    world.sync_live_groups().unwrap();
    let mut periphrasis = Construction::new("PAST", "periphrastic");
    periphrasis.stage = Some("free".into());
    let (variable, free) = world.register_construction(&periphrasis, &Origin::inherited(0.0));
    let synthetic = world.dominant(world.live.group_ids[0], variable).unwrap().0;
    let group = world.live.group_ids[0];
    let pair = Distribution::from_pairs(
        vec![(synthetic, 0.9), (free, 0.1)],
        &world.registry.variants,
    );
    world
        .groups
        .main_code_mut(group)
        .repertoire
        .set(variable, pair);
    assert!(world.load_differing().unwrap().contains(&variable));
    let params_only_economy = {
        let mut params = (*world.params).clone();
        for name in NAMES {
            params
                .pressure_weights
                .insert(name.to_owned(), if name == "economy" { 1.0 } else { 0.0 });
        }
        params
    };
    world.params = Arc::new(params_only_economy);
    cee_engine::transfer::sync(&mut world);
    let config = SimulationConfig::default();
    let params = TransmissionParams {
        dt: config.dt,
        alpha: config.alpha,
        selection: config.selection,
        kappa: config.kappa,
        sigma: config.sigma,
        adult_rate: config.adult_rate,
        loss_threshold: config.loss_threshold,
        establish_threshold: config.establish_threshold,
    };
    let inputs = prepare(&world, &params, 1);
    let pressure_plan = plan(&world.params).unwrap();
    let pressures = Pressures::new(&world, &inputs, &pressure_plan).unwrap();
    let (block, row) = world
        .live
        .iter_blocks()
        .find_map(|b| b.row_of(variable).map(|r| (b, r)))
        .expect("živý řádek");
    let cells = world.live.group_ids.len() * block.capacity;
    let mut out = vec![0.0; cells];
    let zeros = vec![0.0; cells];
    pressures.fitness(block, row, 1, &zeros, &zeros, &mut out);
    let free_slot = block.slots[row].iter().position(|&v| v == free).unwrap();
    let synthetic_slot = block.slots[row]
        .iter()
        .position(|&v| v == synthetic)
        .unwrap();
    for g in 0..world.live.group_ids.len() {
        assert!((out[g * block.capacity + free_slot] + 0.15).abs() < 1e-15);
        assert_eq!(out[g * block.capacity + synthetic_slot], 0.0);
    }
}

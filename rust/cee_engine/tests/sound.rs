//! Zvukové změny, index prostředí a fonologizace (R1b).
//!
//! Přenos podílů patří R1a, takže tu se podíl změny skupině nastavuje přímo v repertoáru
//! (stav „proces dosáhl 100 %“) a testuje se, co následuje: aktivace, fronty, přepis tvarů,
//! uzavření procesu, kontrolní bod uprostřed a nezávislost na počtu vláken.

use cee_core::candidates::FAMILIES;
use cee_engine::changes::sound::{scales, sound_changes, SoundChange};
use cee_engine::changes::{Change, InnovationContext};
use cee_engine::checkpoint::Checkpoint;
use cee_engine::history::History;
use cee_engine::ids::{GroupId, MorphemeId, ProcessId, VariableId};
use cee_engine::model::repertoire::{Distribution, Payload, VariableKind};
use cee_engine::phases::hooks::{self, Crossing};
use cee_engine::phases::StepContext;
use cee_engine::phonology::{self, index::with_group};
use cee_engine::rng::Stream;
use cee_engine::scenarios::{self, SeedOptions};
use cee_engine::transfer::seams;
use cee_engine::world::World;
use cee_engine::{Simulation, SimulationConfig};

fn grid() -> World {
    let options = SeedOptions {
        syntax: true,
        semantics: true,
        ..SeedOptions::default()
    };
    scenarios::village_grid_default(4, 2, 5, &options).expect("svět")
}

fn simulation() -> Simulation {
    let config = SimulationConfig {
        observe_every: 2,
        ..SimulationConfig::default()
    };
    Simulation::new(grid(), config, Vec::new()).expect("simulace")
}

fn context(group: GroupId) -> InnovationContext {
    InnovationContext {
        group,
        tick: 1,
        year: 25.0,
    }
}

/// Rodina s nejvíc místy v první skupině světa.
fn richest_family(world: &World, group: GroupId) -> usize {
    (0..FAMILIES.len())
        .max_by_key(|&family| {
            with_group(world, group, |index, token| {
                index.family(token, family).map_or(0, |f| f.sites.len())
            })
            .unwrap()
        })
        .unwrap()
}

#[test]
fn miry_a_mista_rodin_jsou_konzistentni() {
    let sim = simulation();
    let world = &sim.world;
    let group = world.group_ids()[0];
    let ctx = context(group);
    let changes = sound_changes();
    assert_eq!(changes.len(), 34);
    // Rozpočet netónových rodin dá dohromady nejvýš 0,6 na generaci, tóny mají svůj.
    let total: f64 = scales()[..29].iter().sum();
    assert!((total - 0.6).abs() < 1e-12);
    let mut found = 0;
    for change in &changes {
        let sites = change.weighted_sites(world, &ctx);
        let rate = change.rate_sum(world, &ctx);
        if sites.sites.is_empty() {
            assert_eq!(rate, 0.0, "{}", change.kind());
            continue;
        }
        found += 1;
        assert!(rate > 0.0 && rate.is_finite(), "{}", change.kind());
        let weights = sites.weights.expect("váhy");
        assert_eq!(weights.len(), sites.sites.len());
        let sum: f64 = weights.iter().sum();
        assert!(
            (sum - 1.0).abs() < 1e-9,
            "podíly vah se sčítají na 1: {sum}"
        );
        assert!(weights.iter().all(|w| w.is_finite() && *w > 0.0));
        // Míra rodiny nepřekročí její rozpočet.
        let family = FAMILIES.iter().position(|k| *k == change.kind()).unwrap();
        assert!(rate <= scales()[family] + 1e-12);
    }
    assert!(
        found >= 8,
        "protojazyk má mít místa v mnoha rodinách ({found})"
    );
}

#[test]
fn navrh_zaregistruje_proces_a_je_idempotentni() {
    let mut sim = simulation();
    let group = sim.world.group_ids()[0];
    let family = richest_family(&sim.world, group);
    let change = SoundChange::new(family);
    let ctx = context(group);
    let mut rng = Stream::new(1, &[]);
    let sites = change.weighted_sites(&sim.world, &ctx);
    let variant = change
        .propose(&mut sim.world, &ctx, sites.sites[0], &mut rng, 0)
        .expect("návrh");
    let world = &sim.world;
    assert_eq!(
        world.variables.kind[variant.variable.index()],
        VariableKind::Process
    );
    let Payload::Process { process, changed } = variant.payload else {
        panic!("varianta změny nese proces");
    };
    assert!(changed);
    assert_eq!(world.variables.process[variant.variable.index()], process);
    let def = world.processes[process.index()].as_ref().expect("definice");
    assert_eq!(def.family, FAMILIES[family]);
    assert_eq!(
        world.registry.processes.name(process.0),
        world.registry.variables.name(variant.variable.0)
    );
    // Stejný návrh dá stejnou proměnnou a variantu (paralelní inovace se sčítají).
    let again = change
        .propose(&mut sim.world, &ctx, sites.sites[0], &mut rng, 1)
        .unwrap();
    assert_eq!(again.variable, variant.variable);
    assert_eq!(again.name, variant.name);
    // Proměnná má obě varianty a „žádná změna“ je výchozí.
    let default = sim.world.variables.default[variant.variable.index()];
    assert!(!default.is_none());
    assert_ne!(sim.world.registry.variants.name(default.0), variant.name);
}

fn digest_of(threads: usize) -> (String, usize) {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    pool.install(|| {
        let mut sim = simulation();
        sim.run(1500.0).unwrap();
        let sound = sim
            .history
            .of_kind("innovation")
            .filter(|e| {
                e["change"]
                    .as_str()
                    .is_some_and(|kind| FAMILIES.contains(&kind))
            })
            .count();
        (sim.history.digest(), sound)
    })
}

#[test]
fn inovace_vznikaji_a_vysledek_nezavisi_na_poctu_vlaken() {
    let (one, count) = digest_of(1);
    assert!(count > 0, "zvukové inovace musí vzniknout");
    assert_eq!(one, digest_of(4).0);
    assert_eq!(one, digest_of(3).0);
}

/// Svět s jedním procesem, který ve skupině dosáhl 100 %, a aktivovaný v jejím kódu.
fn fixed_process(sim: &mut Simulation) -> (GroupId, ProcessId, VariableId) {
    let group = sim.world.group_ids()[0];
    let family = richest_family(&sim.world, group);
    let change = SoundChange::new(family);
    let ctx = context(group);
    let mut rng = Stream::new(1, &[]);
    let sites = change.weighted_sites(&sim.world, &ctx);
    let variant = change
        .propose(&mut sim.world, &ctx, sites.sites[0], &mut rng, 0)
        .unwrap();
    let Payload::Process { process, .. } = variant.payload.clone() else {
        panic!("proces");
    };
    let id = sim.world.store_variant(
        &variant.name,
        variant.variable,
        variant.payload,
        variant.origin,
    );
    // Změna je ve všech skupinách na 100 %: proměnná se tak nikde neliší, a proto není živá
    // (rozdílná proměnná by po obnově z kontrolního bodu skončila ve fondech a přenos by ji míchal).
    for other in sim.world.group_ids() {
        sim.world
            .groups
            .main_code_mut(other)
            .repertoire
            .set(variant.variable, Distribution::fixed(id));
    }
    phonology::activate(&mut sim.world, group, process).unwrap();
    (group, process, variant.variable)
}

#[test]
fn aktivace_naplni_frontu_a_fonologizace_prepise_tvary_a_proces_se_uzavre() {
    let mut sim = simulation();
    let (group, process, variable) = fixed_process(&mut sim);
    let state = &sim.world.groups.main_code(group).phonology.sound;
    assert_eq!(state.order, vec![process]);
    assert_eq!(state.lifecycle_log, vec![(process, true)]);
    let proc = &state.queues.state.procs[0];
    assert!(proc.live && !proc.needed.is_empty(), "fronta má slova");
    assert!(
        proc.needed.windows(2).all(|w| w[0] <= w[1]),
        "fronta je seřazená"
    );
    let queued = proc.needed.len();
    assert!(sim.world.groups.main_code(group).forms.overridden() == 0);

    // Krok po kroku: podíl je 100 %, takže se přepíše, co dosáhlo prahu, a po dvou
    // generacích se proces uzavře.
    for _ in 0..5 {
        sim.step().unwrap();
    }
    // Při realistickém tempu (M9b) mezitím doběhnou i jiné hláskové změny: počítají se jen
    // události tohoto procesu.
    let name = sim.world.registry.variables.name(variable.0).to_owned();
    let group_name = sim.world.group_name(group).to_owned();
    // Proces je ve všech skupinách na 100 %, takže se rozběhne i jinde: počítá se skupina testu.
    let own = |e: &serde_json::Map<String, serde_json::Value>| {
        e["variable"] == name.as_str() && e["group"] == group_name.as_str()
    };
    let phonologized: u64 = sim
        .history
        .of_kind("phonologized")
        .filter(|e| own(e))
        .map(|e| e["words"].as_u64().unwrap())
        .sum();
    assert!(phonologized > 0, "slova si změnu zapsala");
    let closed: Vec<_> = sim
        .history
        .of_kind("process_closed")
        .filter(|e| own(e))
        .collect();
    assert_eq!(closed.len(), 1, "proces se uzavřel právě jednou");
    assert_eq!(
        closed[0]["restructured"].as_u64().unwrap() as usize,
        phonologized as usize
    );
    let relics = closed[0]["relics"].as_u64().unwrap() as usize;
    assert!(relics <= queued && relics + phonologized as usize <= queued + 1_000);
    let code = sim.world.groups.main_code(group);
    assert!(!code.phonology.sound.queues.state.procs[0].live);
    // Uzavřený proces tlak `Norm` nevrací zpět (`seams::closed`); jiná proměnná není uzavřená.
    assert!(seams::closed(&sim.world, group, variable));
    assert!(!seams::closed(
        &sim.world,
        sim.world.group_ids()[1],
        VariableId::new(0)
    ));
    let code = sim.world.groups.main_code(group);
    let own_log: Vec<_> = code
        .phonology
        .sound
        .lifecycle_log
        .iter()
        .copied()
        .filter(|&(p, _)| p == process)
        .collect();
    assert_eq!(own_log, vec![(process, true), (process, false)]);
    // Přepsané tvary se liší od výchozích a obsahují jen skutečné hlásky.
    let rewritten = code.forms.overridden();
    assert!(rewritten > 0);
    let table = sim.world.segments().unwrap();
    for member in code.phonology.vocabulary.iter() {
        if let Some(unit) = code.forms.get(member) {
            let form = sim.world.bank.form(unit.form);
            assert!(!form.is_empty());
            assert!(form.iter().all(|&s| s >= 0 && (s as usize) < table.len()));
        }
    }
    // Žádná čísla nejsou NaN: sklony slov tohoto procesu jsou konečné.
    let biases = &sim.world.sound.runtime.biases[process.index()];
    assert!(biases.iter().filter(|b| !b.is_nan()).all(|b| b.is_finite()));
}

#[test]
fn proces_pod_prahem_nepise_a_neuzavre_se() {
    let mut sim = simulation();
    let group = sim.world.group_ids()[0];
    let family = richest_family(&sim.world, group);
    let change = SoundChange::new(family);
    let ctx = context(group);
    let mut rng = Stream::new(1, &[]);
    let sites = change.weighted_sites(&sim.world, &ctx);
    let variant = change
        .propose(&mut sim.world, &ctx, sites.sites[0], &mut rng, 0)
        .unwrap();
    let Payload::Process { process, .. } = variant.payload.clone() else {
        panic!("proces");
    };
    let none = sim.world.variables.default[variant.variable.index()];
    let id = sim.world.store_variant(
        &variant.name,
        variant.variable,
        variant.payload,
        variant.origin,
    );
    // Podíl 1 % odpovídá logitu pod prahem 0,85 všech slov: nikdo nepíše.
    let distribution =
        Distribution::from_pairs(vec![(none, 0.99), (id, 0.01)], &sim.world.registry.variants);
    sim.world
        .groups
        .main_code_mut(group)
        .repertoire
        .set(variant.variable, distribution);
    phonology::activate(&mut sim.world, group, process).unwrap();
    for _ in 0..6 {
        sim.step().unwrap();
    }
    // Jen události tohoto procesu: jiné, přirozeně vzniklé změny se ve světě ujmout smějí.
    let name = sim
        .world
        .registry
        .variables
        .name(variant.variable.0)
        .to_owned();
    let group_name = sim.world.group_name(group).to_owned();
    let mine = |kind: &str| {
        sim.history
            .of_kind(kind)
            .filter(|e| e["variable"] == name.as_str() && e["group"] == group_name.as_str())
            .count()
    };
    assert_eq!(mine("phonologized"), 0);
    assert_eq!(mine("process_closed"), 0);
    let proc = &sim
        .world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .procs[0];
    assert!(proc.live && proc.fixed_since.is_none());
}

#[test]
fn kontrolni_bod_uprostred_fonologizace_da_stejny_beh() {
    let build = || {
        let mut sim = simulation();
        fixed_process(&mut sim);
        sim
    };
    let mut straight = build();
    for _ in 0..5 {
        straight.step().unwrap();
    }
    let mut first = build();
    first.step().unwrap();
    first.step().unwrap();
    let bytes = first.checkpoint().to_bytes().unwrap();
    let restored = Checkpoint::from_bytes(&bytes).unwrap();
    let config = SimulationConfig {
        observe_every: 2,
        ..SimulationConfig::default()
    };
    let mut resumed = Simulation::resume(
        restored,
        config,
        Vec::new(),
        cee_engine::changes::default_changes(),
    )
    .unwrap();
    for _ in 0..3 {
        resumed.step().unwrap();
    }
    assert!(straight.history.of_kind("phonologized").count() > 0);
    assert_eq!(resumed.history.digest(), straight.history.digest());
    let forms = |sim: &Simulation| {
        let group = sim.world.group_ids()[0];
        let code = sim.world.groups.main_code(group);
        code.phonology
            .vocabulary
            .iter()
            .map(|m| sim.world.form_of(group, m).to_vec())
            .collect::<Vec<_>>()
    };
    assert_eq!(forms(&resumed), forms(&straight));
}

#[test]
fn kontrolni_bod_za_behu_s_prirozenymi_inovacemi_da_stejny_beh() {
    let mut straight = simulation();
    for _ in 0..12 {
        straight.step().unwrap();
    }
    let mut first = simulation();
    for _ in 0..6 {
        first.step().unwrap();
    }
    let restored = Checkpoint::from_bytes(&first.checkpoint().to_bytes().unwrap()).unwrap();
    let config = SimulationConfig {
        observe_every: 2,
        ..SimulationConfig::default()
    };
    let mut resumed = Simulation::resume(
        restored,
        config,
        Vec::new(),
        cee_engine::changes::default_changes(),
    )
    .unwrap();
    for _ in 0..6 {
        resumed.step().unwrap();
    }
    assert!(straight.history.of_kind("innovation").count() > 0);
    assert_eq!(resumed.history.digest(), straight.history.digest());
}

fn step_context<'a>(
    world: &'a mut World,
    history: &'a mut History,
    config: &'a SimulationConfig,
) -> StepContext<'a> {
    StepContext {
        world,
        history,
        config,
        tick: 1,
        year: 25.0,
    }
}

#[test]
fn slovni_zasoba_po_prenosu_odchod_a_prichod_slova() {
    let mut sim = simulation();
    let (group, process, _) = fixed_process(&mut sim);
    let config = SimulationConfig::default();
    let mut history = History::default();
    // Lexikální proměnná s dominantním slovem skupiny.
    let (variable, root) = (0..sim.world.variables.len())
        .map(VariableId::new)
        .filter(|v| sim.world.variables.kind[v.index()] == VariableKind::Lexical)
        .find_map(|v| {
            let concept = sim.world.variables.concept[v.index()];
            let root = sim
                .world
                .groups
                .main_code(group)
                .phonology
                .dominant_of(concept);
            (!root.is_none()).then_some((v, root))
        })
        .expect("dominantní slovo");
    let concept = sim.world.variables.concept[variable.index()];
    let before_version = sim.world.groups.main_code(group).phonology.version;
    let mut ctx = step_context(&mut sim.world, &mut history, &config);
    assert!(hooks::is_sound_process(
        &ctx,
        ctx.world
            .variables
            .kind
            .iter()
            .position(|k| *k == VariableKind::Process)
            .map(VariableId::new)
            .unwrap()
    ));
    assert!(!hooks::is_sound_process(&ctx, variable));
    let crossing = |enter| Crossing {
        group,
        variable,
        morpheme: root,
        enter,
    };
    hooks::follow_vocabulary(&mut ctx, &[crossing(false)]).unwrap();
    {
        let state = &ctx.world.groups.main_code(group).phonology;
        assert!(state.dominant_of(concept).is_none());
        assert!(!state.vocabulary.contains(root));
        assert_eq!(state.uses_of(root), 0);
        assert!(state.version > before_version);
    }
    hooks::follow_vocabulary(&mut ctx, &[crossing(true)]).unwrap();
    let state = &ctx.world.groups.main_code(group).phonology;
    assert_eq!(state.dominant_of(concept), root);
    assert!(state.vocabulary.contains(root));
    assert_eq!(state.uses_of(root), 1);
    // Slovo, které se vrátilo, je znovu ve frontě živého procesu, pokud se ho proces týká
    // a nezapsal si ho (zařazený morfém čeká nejvýš jednou).
    let proc = &state.sound.queues.state.procs[0];
    let waiting = proc
        .morphemes
        .iter()
        .filter(|&&m| m == root.0 as i32)
        .count();
    assert!(waiting <= 1);
    let _ = (process, MorphemeId::NONE);
}

#[test]
fn aktivace_pres_hook_rozlisuje_zvukovy_proces() {
    let mut sim = simulation();
    let group = sim.world.group_ids()[0];
    let family = richest_family(&sim.world, group);
    let change = SoundChange::new(family);
    let mut rng = Stream::new(1, &[]);
    let sites = change.weighted_sites(&sim.world, &context(group));
    let variant = change
        .propose(&mut sim.world, &context(group), sites.sites[0], &mut rng, 0)
        .unwrap();
    let config = SimulationConfig::default();
    let mut history = History::default();
    let mut ctx = step_context(&mut sim.world, &mut history, &config);
    assert!(hooks::is_sound_process(&ctx, variant.variable));
    hooks::activate(&mut ctx, group, variant.variable).unwrap();
    let state = &ctx.world.groups.main_code(group).phonology.sound;
    assert_eq!(state.queues.state.procs.len(), 1);
    // Druhá aktivace téhož procesu nic nezmění.
    hooks::activate(&mut ctx, group, variant.variable).unwrap();
    let state = &ctx.world.groups.main_code(group).phonology.sound;
    assert_eq!(state.queues.state.procs.len(), 1);
    assert_eq!(state.order.len(), 1);
}

#[test]
fn prubezne_dorovnany_index_se_rovna_indexu_od_nuly() {
    let mut sim = simulation();
    let (group, _, _) = fixed_process(&mut sim);
    for _ in 0..4 {
        sim.step().unwrap();
    }
    assert!(sim.world.groups.main_code(group).forms.overridden() > 0);
    // Kopie světa zahodí odvozený stav, takže její index se staví od nuly.
    let fresh = sim.world.clone();
    for (family, kind) in FAMILIES.iter().enumerate() {
        let read = |world: &World| {
            with_group(world, group, |index, token| {
                index
                    .family(token, family)
                    .map(|f| (f.sites.clone(), f.rates.clone(), f.total))
            })
            .unwrap()
        };
        assert_eq!(read(&sim.world), read(&fresh), "{kind}");
    }
}

#[test]
fn cetnost_uziti_je_soucet_pojmu_korene() {
    use cee_core::code_state::UsageInputs;
    use cee_engine::model::lexicon::MorphemeKind;
    let mut sim = simulation();
    let group = sim.world.group_ids()[0];
    let world = &mut sim.world;
    phonology::columns::refresh(world);
    phonology::columns::sync_usage(world, group);
    let state = &world.groups.main_code(group).phonology;
    let mut roots: Vec<MorphemeId> = state
        .dominant
        .iter()
        .copied()
        .filter(|root| !root.is_none())
        .collect();
    roots.sort();
    roots.dedup();
    assert!(!roots.is_empty());
    let dominant = state.dominant.clone();
    let runtime = &world.sound.runtime;
    let inputs = UsageInputs {
        concept: &runtime.concept,
        fixed: &world.morphemes.frequency,
        weight: &runtime.columns.weight,
        lexeme: &runtime.columns.lexeme,
    };
    let mut usage = world
        .groups
        .main_code(group)
        .phonology
        .sound
        .queues
        .state
        .usage
        .clone();
    for root in roots {
        let sum: f64 = dominant
            .iter()
            .enumerate()
            .filter(|(_, r)| **r == root)
            .map(|(concept, _)| runtime.concept[concept])
            .sum();
        let mut expected = sum.min(1.0);
        let weight = runtime.columns.weight[root.index()];
        if world.morphemes.kind[root.index()] == MorphemeKind::Word && !weight.is_nan() {
            expected *= weight;
        }
        let got = usage.frequency(root.index(), &inputs).expect("četnost");
        assert!((got - expected).abs() < 1e-12, "{got} != {expected}");
    }
}

#[test]
fn povrchovy_tvar_prohani_zivym_procesem_jen_slova_co_si_zmenu_nezapsala() {
    let mut sim = simulation();
    let (group, _, _) = fixed_process(&mut sim);
    let before = phonology::surface_lexicon(&sim.world, group).unwrap();
    assert!(!before.is_empty());
    let underlying = |sim: &Simulation, group: GroupId| {
        let code = sim.world.groups.main_code(group);
        let mut found: Vec<(String, Vec<i32>)> = code
            .phonology
            .dominant
            .iter()
            .enumerate()
            .filter(|(_, root)| !root.is_none())
            .map(|(concept, &root)| {
                (
                    sim.world.registry.concepts.name(concept as u32).to_owned(),
                    sim.world.form_of(group, root).to_vec(),
                )
            })
            .collect();
        found.sort();
        found
    };
    // Změna je na 100 %, ale nikdo si ji ještě nezapsal: povrch se od podkladu liší.
    let base = underlying(&sim, group);
    assert_eq!(before.len(), base.len());
    let differing = before.iter().zip(&base).filter(|(a, b)| a.1 != b.1).count();
    assert!(differing > 0, "živý proces mění povrchový tvar");
    // Po uzavření procesu se zapsaná slova shodují s povrchem, relikty zůstávají podkladové.
    for _ in 0..5 {
        sim.step().unwrap();
    }
    let after = phonology::surface_lexicon(&sim.world, group).unwrap();
    let base = underlying(&sim, group);
    let differing_after = after.iter().zip(&base).filter(|(a, b)| a.1 != b.1).count();
    assert!(differing_after < differing);
}

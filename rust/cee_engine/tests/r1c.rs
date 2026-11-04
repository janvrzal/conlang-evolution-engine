//! Oblast R1c: změny (lexikální, morfologické, syntaktické, prozodické), přestavby,
//! souběžná variabilita a větší slovník. Bez přenosu (R1a) se nové varianty nešíří,
//! proto přestavby zkouší test zápisem rozdělení přímo do repertoáru.

use std::collections::BTreeMap;

use cee_engine::changes::{default_changes, InnovationContext};
use cee_engine::concepts::{slug, ConceptData};
use cee_engine::grammar::Template;
use cee_engine::ids::{GroupId, MorphemeId, VariableId};
use cee_engine::model::forms::UnitForm;
use cee_engine::model::lexicon::{FormChange, FormOperation, MorphemeKind};
use cee_engine::model::repertoire::{Distribution, Origin, Payload, VariableKind};
use cee_engine::phases::{rebuild, StepContext};
use cee_engine::rng::Stream;
use cee_engine::scenarios::{self, SeedOptions};
use cee_engine::spec::{self, WorldSpec};
use cee_engine::{morphology, prosody, syntax, vocabulary};
use cee_engine::{Simulation, SimulationConfig};
use serde_json::Value;

fn fixture() -> Value {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/concepts_r1c.json"
    ))
    .unwrap();
    serde_json::from_str(&text).unwrap()
}

fn full_options() -> SeedOptions {
    SeedOptions {
        syntax: true,
        semantics: true,
        prosody: true,
        ..SeedOptions::default()
    }
}

fn simulation() -> Simulation {
    let world = scenarios::village_grid_default(3, 2, 7, &full_options()).unwrap();
    Simulation::new(world, SimulationConfig::default(), Vec::new()).unwrap()
}

fn context(world: &cee_engine::World, group: GroupId) -> InnovationContext {
    InnovationContext {
        group,
        tick: 1,
        year: world.start_year,
    }
}

fn origin(group: GroupId) -> Origin {
    Origin {
        change: Some("test".into()),
        tick: 1,
        year: 0.0,
        group,
        parent: cee_engine::VariantId::NONE,
    }
}

// --- data pojmů proti Pythonu -----------------------------------------------------------------

#[test]
fn katalog_pojmu_sedi_s_pythonem() {
    let reference = fixture();
    let data = ConceptData::shared();
    let ids: Vec<&str> = data.catalog_ids().map(|c| c.0).collect();
    assert_eq!(
        ids.len() as u64,
        reference["catalog_ids_len"].as_u64().unwrap()
    );
    let head: Vec<&str> = reference["catalog_ids_head"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    assert_eq!(&ids[..head.len()], head.as_slice());
    let order = data.catalog_order();
    let expected: Vec<&str> = reference["catalog_order_head"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect();
    assert_eq!(
        order[..expected.len()]
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>(),
        expected
    );
    let tail = reference["catalog_order_tail"].as_array().unwrap();
    assert_eq!(
        order[order.len() - tail.len()].as_str(),
        tail[0].as_str().unwrap()
    );
    assert_eq!(order.len(), ids.len());
}

#[test]
fn slug_a_prumery_sedi_s_pythonem() {
    let reference = fixture();
    for (name, expected) in reference["slugs"].as_object().unwrap() {
        assert_eq!(slug(name), expected.as_str().unwrap(), "{name}");
    }
    let data = ConceptData::shared();
    let close = |a: f64, b: f64| (a - b).abs() < 1e-9;
    assert!(close(
        data.reference_borrowed(),
        reference["reference"].as_f64().unwrap()
    ));
    assert!(close(
        data.borrowing_normalizer(3.0),
        reference["normalizer_3"].as_f64().unwrap()
    ));
    assert!(close(
        data.borrowing_normalizer(0.5),
        reference["normalizer_05"].as_f64().unwrap()
    ));
    assert!(close(
        data.mean_borrowed_in(None),
        reference["mean_borrowed"].as_f64().unwrap()
    ));
    assert!(close(
        data.mean_borrowed_in(Some("culture")),
        reference["mean_borrowed_culture"].as_f64().unwrap()
    ));
    assert!(close(
        data.mean_frequency(None),
        reference["mean_frequency"].as_f64().unwrap()
    ));
    assert!(close(
        data.mean_frequency(Some("power")),
        reference["mean_frequency_power"].as_f64().unwrap()
    ));
    for (concept, domain) in reference["domain_head"].as_object().unwrap() {
        assert_eq!(data.domain(concept), domain.as_str().unwrap());
    }
    for (concept, frequency) in reference["freq_head"].as_object().unwrap() {
        assert!(close(
            data.frequency(concept).unwrap(),
            frequency.as_f64().unwrap()
        ));
    }
    let found = data.find(None, Some(965), None).map(|i| i.wold_id.as_str());
    assert_eq!(found, reference["find_concepticon"].as_str());
}

// --- změny ------------------------------------------------------------------------------------

#[test]
fn registr_zmen_ma_kanonicke_poradi() {
    let kinds: Vec<&str> = default_changes().iter().map(|c| c.kind()).collect();
    // Pořadí jako `DEFAULT_CHANGES`: lexikální (9), zvukové (33), morfologické (3),
    // syntaktické (10), prozodické (2).
    assert_eq!(kinds.len(), 9 + 33 + 3 + 10 + 2);
    assert_eq!(kinds[0], "lexical_coinage");
    assert_eq!(kinds[8], "lexical_borrowing");
    assert_eq!(kinds[9], cee_core::candidates::FAMILIES[0]);
    assert_eq!(kinds[9 + 32], cee_core::candidates::FAMILIES[32]);
    assert_eq!(kinds[42], "leveling");
    assert_eq!(kinds[45], "periphrasis");
    assert_eq!(*kinds.last().unwrap(), "stress_strength");
    let unique: std::collections::BTreeSet<&&str> = kinds.iter().collect();
    assert_eq!(unique.len(), kinds.len());
}

#[test]
fn miry_a_mista_jsou_konecna_a_vahy_se_scitaji_na_jedna() {
    let simulation = simulation();
    let world = &simulation.world;
    let changes = default_changes();
    let mut with_sites = 0;
    for group in world.group_ids() {
        let ctx = context(world, group);
        for change in &changes {
            let rate = change.rate_sum(world, &ctx);
            assert!(rate.is_finite() && rate >= 0.0, "{} {rate}", change.kind());
            let sites = change.weighted_sites(world, &ctx);
            if let Some(weights) = &sites.weights {
                assert_eq!(weights.len(), sites.sites.len());
                let total: f64 = weights.iter().sum();
                assert!((total - 1.0).abs() < 1e-9, "{} {total}", change.kind());
            }
            if rate > 0.0 && !sites.sites.is_empty() {
                with_sites += 1;
            }
        }
    }
    assert!(with_sites > 0);
}

#[test]
fn kazda_zmena_umi_navrhnout_variantu_bez_pádu() {
    let mut simulation = simulation();
    let group = simulation.world.group_ids()[0];
    let ctx = context(&simulation.world, group);
    let mut proposed: BTreeMap<&'static str, usize> = BTreeMap::new();
    for change in default_changes() {
        let sites = change.weighted_sites(&simulation.world, &ctx);
        let mut rng = Stream::new(1, &[cee_engine::rng::Part::Str(change.kind())]);
        for (index, &site) in sites.sites.iter().take(40).enumerate() {
            if let Some(variant) =
                change.propose(&mut simulation.world, &ctx, site, &mut rng, index)
            {
                assert!(variant.variable.index() < simulation.world.variables.len());
                if let Payload::Lexical { appeal, .. } = variant.payload {
                    assert!(appeal.is_finite());
                }
                *proposed.entry(change.kind()).or_default() += 1;
            }
        }
    }
    for kind in [
        "lexical_coinage",
        "semantic_shift",
        "derivation",
        "compounding",
    ] {
        assert!(
            proposed.get(kind).copied().unwrap_or(0) > 0,
            "{kind}: {proposed:?}"
        );
    }
}

fn run_digest(threads: usize, seed: i64) -> (String, BTreeMap<String, usize>) {
    let pool = rayon::ThreadPoolBuilder::new()
        .num_threads(threads)
        .build()
        .unwrap();
    pool.install(|| {
        let world = scenarios::village_grid_default(3, 2, seed, &full_options()).unwrap();
        let config = SimulationConfig {
            observe_every: 4,
            ..SimulationConfig::default()
        };
        let mut simulation = Simulation::new(world, config, Vec::new()).unwrap();
        simulation.run(1500.0).unwrap();
        let mut counts = BTreeMap::new();
        for event in simulation.history.of_kind("innovation") {
            let kind = event["change"].as_str().unwrap().to_owned();
            *counts.entry(kind).or_default() += 1;
        }
        (simulation.history.digest(), counts)
    })
}

#[test]
fn beh_je_deterministicky_a_nezavisi_na_vlaknech() {
    let (one, counts) = run_digest(1, 11);
    assert_eq!(one, run_digest(1, 11).0, "stejné semínko, stejný běh");
    assert_eq!(one, run_digest(4, 11).0, "počet vláken nesmí změnit běh");
    assert_ne!(one, run_digest(1, 12).0, "jiné semínko, jiný běh");
    let total: usize = counts.values().sum();
    assert!(total > 0, "inovace musí vznikat: {counts:?}");
    assert!(counts.len() >= 3, "víc druhů změn: {counts:?}");
}

// --- souběžná variabilita ---------------------------------------------------------------------

#[test]
fn variabilita_dava_mensinove_varianty_a_podily_se_scitaji() {
    let simulation = simulation();
    let world = &simulation.world;
    let cap = world.params.variation_cap;
    let mut varied = 0;
    for group in world.group_ids() {
        let code = world.groups.main_code(group);
        for variable in code.repertoire.variable_ids() {
            if world.variables.kind[variable.index()] != VariableKind::Lexical {
                continue;
            }
            let Some(found) = world.distribution(group, variable) else {
                continue;
            };
            let total: f64 = found.freqs.iter().sum();
            assert!((total - 1.0).abs() < 1e-9);
            if !found.is_fixed() {
                varied += 1;
                let (_, share) = found.dominant();
                assert!(
                    share >= 1.0 - cap - 1e-9,
                    "slovo autora má zůstat převládající"
                );
            }
        }
    }
    assert!(varied > 0, "svět má mít rozpracované změny");
}

// --- přestavby --------------------------------------------------------------------------------

fn step_context<'a>(simulation: &'a mut Simulation) -> StepContext<'a> {
    StepContext {
        world: &mut simulation.world,
        history: &mut simulation.history,
        config: &simulation.config,
        tick: 1,
        year: 25.0,
    }
}

fn first_word_unit(simulation: &Simulation, group: GroupId) -> MorphemeId {
    let world = &simulation.world;
    world
        .groups
        .main_code(group)
        .phonology
        .vocabulary
        .iter()
        .find(|&unit| {
            world.morphemes.kind[unit.index()] == MorphemeKind::Word
                && !world.morphemes.cell[unit.index()].is_none()
                && world.morphemes.boundary[unit.index()] >= 0
                && Some(world.morphemes.word_class[unit.index()].0)
                    == world.registry.word_classes.get("noun")
        })
        .expect("tvar slova")
}

#[test]
fn vyrovnani_prepise_kmen_podle_citacniho_tvaru() {
    let mut simulation = simulation();
    let group = simulation.world.group_ids()[0];
    let unit = first_word_unit(&simulation, group);
    // Kmen buňky se rozejde s citačním tvarem (alternace).
    let current = simulation.world.unit_of(group, unit);
    let mut altered = simulation.world.bank.form(current.form).to_vec();
    let table = simulation.world.table.clone().unwrap();
    altered[0] = if altered[0] == table.id_of("k").unwrap() {
        table.id_of("t").unwrap()
    } else {
        table.id_of("k").unwrap()
    };
    let form = simulation.world.bank.id_of(&altered);
    cee_engine::views::set_form(
        &mut simulation.world,
        group,
        unit,
        UnitForm {
            form,
            boundary: current.boundary,
            exponent: current.exponent,
        },
    );
    let sites = morphology::leveling_sites(&simulation.world, group);
    let at = sites
        .changes
        .iter()
        .position(|c| c.unit == unit)
        .expect("místo vyrovnání");
    let change = sites.changes[at].clone();
    assert_eq!(change.operation, FormOperation::Level);
    let (variable, changed) = morphology::register(&mut simulation.world, &change, &origin(group));
    simulation
        .world
        .groups
        .main_code_mut(group)
        .repertoire
        .set(variable, Distribution::fixed(changed));
    morphology::activate(&mut simulation.world, group, variable);
    assert_eq!(
        simulation
            .world
            .groups
            .main_code(group)
            .phonology
            .grammar
            .morph_active
            .len(),
        1
    );
    let mut ctx = step_context(&mut simulation);
    rebuild::morphology(&mut ctx, group).unwrap();
    let after = simulation.world.unit_of(group, unit);
    let (stem, _) = morphology::split(simulation.world.bank.form(after.form), after.boundary);
    let lexeme = simulation.world.morphemes.lexeme_id(unit);
    let citation = simulation.world.form_of(group, lexeme).to_vec();
    assert_eq!(stem, citation.as_slice(), "kmen je zase citační tvar");
    assert_eq!(simulation.history.of_kind("analogy").count(), 1);
    let state = &simulation.world.groups.main_code(group).phonology.grammar;
    assert!(state.morph_active.is_empty() && state.morph_closed.contains(&variable));
}

#[test]
fn nova_koncovka_se_zapise_do_tvaru_a_vznikne_bunka() {
    let mut simulation = simulation();
    let group = simulation.world.group_ids()[0];
    // Funkce PAST nese koncovku; povýšíme ji na novou syntetickou konstrukci z přiklonky.
    let mut construction = syntax::dominant(&simulation.world, group, "PAST").unwrap();
    construction.kind = "periphrastic".into();
    construction.source = Some("finish".into());
    construction.stage = Some("clitic".into());
    construction.exponent = None;
    let affix =
        syntax::new_affix(&mut simulation.world, group, &construction, 1).expect("koncovka");
    let mut next = construction.clone();
    next.kind = "synthetic".into();
    next.stage = None;
    next.exponent = Some(simulation.world.registry.morphemes.name(affix.0).to_owned());
    let (variable, variant) = simulation
        .world
        .register_construction(&next, &origin(group));
    simulation
        .world
        .groups
        .main_code_mut(group)
        .repertoire
        .set(variable, Distribution::fixed(variant));
    let ready = syntax::ready_constructions(&simulation.world, group);
    assert!(
        ready.iter().any(|r| r.variant == variant),
        "konstrukce je připravená k zápisu"
    );
    let mut ctx = step_context(&mut simulation);
    rebuild::syntax(&mut ctx, group).unwrap();
    let state = &simulation.world.groups.main_code(group).phonology.grammar;
    assert!(state.grammar_applied.contains(&variant));
    assert!(syntax::ready_constructions(&simulation.world, group).is_empty());
    // Znovu se nezapisuje.
    let mut ctx = step_context(&mut simulation);
    rebuild::syntax(&mut ctx, group).unwrap();
}

#[test]
fn prevladajici_pravidlo_prizvuku_se_zapise_do_kodu() {
    let mut simulation = simulation();
    let group = simulation.world.group_ids()[0];
    let before = simulation.world.groups.main_code(group).stress_rule;
    let target = if before.name() == "initial" {
        "final"
    } else {
        "initial"
    };
    let (variable, variant) =
        simulation
            .world
            .register_prosody("stress_rule", target, &origin(group));
    simulation
        .world
        .groups
        .main_code_mut(group)
        .repertoire
        .set(variable, Distribution::fixed(variant));
    assert!(prosody::plan(&simulation.world, group).is_some());
    let mut ctx = step_context(&mut simulation);
    rebuild::prosody(&mut ctx, group).unwrap();
    assert_eq!(
        simulation.world.groups.main_code(group).stress_rule.name(),
        target
    );
    assert_eq!(simulation.history.of_kind("stress_rule_changed").count(), 1);
    assert!(prosody::plan(&simulation.world, group).is_none());
}

#[test]
fn reanalyza_hranice_pridava_a_ubira_hlasku() {
    let form = [5, 6, 7];
    let added =
        morphology::rebracket(&form, 2, MorphemeId::NONE, FormOperation::Prepend, 9).unwrap();
    assert_eq!(added.form, vec![9, 5, 6, 7]);
    assert_eq!(added.boundary, 3);
    let dropped =
        morphology::rebracket(&form, -1, MorphemeId::NONE, FormOperation::DropInitial, 5).unwrap();
    assert_eq!(dropped.form, vec![6, 7]);
    assert_eq!(dropped.boundary, -1);
    assert!(
        morphology::rebracket(&form, 2, MorphemeId::NONE, FormOperation::DropInitial, 8).is_none()
    );
    let _ = FormChange {
        operation: FormOperation::Level,
        unit: MorphemeId(0),
        exponent: MorphemeId::NONE,
        segment: None,
    };
    let _ = (Template::Inflection, VariableId(0));
}

// --- větší slovník a vlastní pojmy -------------------------------------------------------------

fn example_spec() -> WorldSpec {
    let text = std::fs::read_to_string(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../src/cee/data/v2_example_world.json"
    ))
    .unwrap();
    WorldSpec::from_json(&text).unwrap()
}

#[test]
fn vetsi_slovnik_a_vlastni_pojmy_se_postavi() {
    let mut spec = example_spec();
    spec.vocabulary = 200;
    spec.concepts = vec![serde_json::json!({
        "id": "moje-slovo", "frequency": 0.4, "domain": "culture", "word_class": "verb",
        "related": [{"concept": "water", "kind": "polysemy", "direction": "to"}]
    })];
    let (world, _) = spec::build(&spec).unwrap();
    let lexical = (0..world.variables.len())
        .filter(|&v| world.variables.kind[v] == VariableKind::Lexical)
        .count();
    assert_eq!(lexical, 200 + 6 + 1, "výchozí + zdroje + katalog + vlastní");
    let id = world
        .registry
        .concepts
        .get("moje-slovo")
        .expect("vlastní pojem");
    let at = id as usize;
    assert_eq!(world.concepts.domain[at], 2, "culture");
    assert!((world.concept_frequency(cee_engine::ConceptId(id)) - 0.4).abs() < 1e-12);
    // Posun významu vlastního pojmu k vodě je v grafu.
    let water = cee_engine::ConceptId(world.registry.concepts.get("water").unwrap());
    let graph = world.semantics.as_deref().unwrap();
    assert!(graph
        .into(water)
        .any(|r| r.source.0 == id && r.polysemy > 0));
    // Slovník o n pojmech je začátkem slovníku o n + 1.
    let small = vocabulary::resolve(160, &[]).unwrap().ids();
    let large = vocabulary::resolve(180, &[]).unwrap().ids();
    assert_eq!(&large[..small.len()], small.as_slice());
    // Svět se větším slovníkem dá spustit.
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new()).unwrap();
    simulation.run(200.0).unwrap();
}

#[test]
fn spatny_vlastni_pojem_se_odmitne() {
    let mut spec = example_spec();
    spec.concepts = vec![serde_json::json!({"id": "water"})];
    assert!(spec::build(&spec).is_err(), "pojem už ve slovníku je");
    spec.concepts = vec![serde_json::json!({"id": "x", "domain": "nesmysl"})];
    assert!(spec::build(&spec).is_err());
    spec.concepts = Vec::new();
    spec.vocabulary = 100_000;
    assert!(spec::build(&spec).is_err());
}

#[test]
fn vypujcky_berou_slova_od_souseda_jineho_jazyka() {
    let (world, _) = spec::build(&example_spec()).unwrap();
    let mut simulation = Simulation::new(world, SimulationConfig::default(), Vec::new()).unwrap();
    let change = default_changes()
        .into_iter()
        .find(|c| c.kind() == "lexical_borrowing")
        .unwrap();
    let mut borrowers = 0;
    for group in simulation.world.group_ids() {
        let donors = cee_engine::changes::lexicon::donors(&simulation.world, group);
        let ctx = context(&simulation.world, group);
        let rate = change.rate_sum(&simulation.world, &ctx);
        if donors.is_empty() {
            assert_eq!(rate, 0.0, "bez cizího souseda se nepůjčuje");
            continue;
        }
        borrowers += 1;
        let total: f64 = donors.iter().map(|d| d.0).sum();
        assert!(total > 0.0 && total <= 1.0 + 1e-9);
        assert!(rate > 0.0 && rate.is_finite());
        let sites = change.weighted_sites(&simulation.world, &ctx);
        let mut rng = Stream::new(3, &[cee_engine::rng::Part::Str("loan")]);
        let own = simulation.world.groups.main_code(group).language;
        for (index, &site) in sites.sites.iter().enumerate() {
            let Some(variant) = change.propose(&mut simulation.world, &ctx, site, &mut rng, index)
            else {
                continue;
            };
            let Payload::Lexical {
                morpheme, origin, ..
            } = &variant.payload
            else {
                panic!("výpůjčka je lexikální varianta");
            };
            assert_eq!(origin, "loan");
            assert_ne!(simulation.world.morphemes.language[morpheme.index()], own);
            return;
        }
    }
    assert!(borrowers > 0, "svět má mít hraniční vazby mezi jazyky");
    panic!("žádná výpůjčka nevznikla");
}

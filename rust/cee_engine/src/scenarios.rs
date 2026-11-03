//! Hotové světy pro validační scénáře a benchmarky (zrcadlo `cee.v2.scenarios`).
//!
//! Stejné scénáře jako v Pythonu (`village_grid`, `region_world`, `contact_world`,
//! `island_and_city`, `language_shift`, `kingdom` a ostatní, které používají
//! `scripts/v2_digests.py` a testy bran). Události scénářů jsou nosiče
//! [`PendingEvent`] – jejich provedení patří R1d.

use std::collections::HashMap;
use std::sync::Arc;

use serde_json::json;

use crate::concepts::{ConceptData, ConceptGraph, Defaults};
use crate::events::{PendingEvent, WorldEvent};
use crate::grammar::{profile, Catalog, Construction, GRAMMATICAL_SOURCES};
use crate::ids::{GroupId, LanguageId, Registry};
use crate::model::code::{Code, StressRule, StressStrength};
use crate::model::group::GroupInit;
use crate::model::links::LinkKind;
use crate::model::repertoire::{Distribution, Origin, Repertoire};
use crate::model::territory::{Territory, TerritoryLevel};
use crate::parameters::Parameters;
use crate::protoform::{protolanguage, ProtoSpec};
use crate::rng::{stable_int, Part};
use crate::world::{gravity_links, Endings, World};

/// Odvozovací přípona protojazyka (jmenná, typ *-ka*).
pub const DERIVATIONAL_SUFFIX: &str = "ka";
/// Citační buňka každé třídy slov.
pub const CITATION_CELLS: [(&str, &str); 2] = [("noun", "SG"), ("verb", "PRES")];

fn endings(items: &[(&str, &str, &[(&str, f64)])]) -> Endings {
    items
        .iter()
        .map(|&(class, cell, options)| {
            ((class.to_owned(), cell.to_owned()), options.iter().map(|&(e, w)| (e.to_owned(), w)).collect())
        })
        .collect()
}

/// Dvě koncovky pro každou buňku: větší a menší vzor, jako v reálných jazycích.
pub fn proto_endings() -> Endings {
    endings(&[("noun", "PL", &[("i", 0.65), ("an", 0.35)]), ("verb", "PAST", &[("ta", 0.7), ("u", 0.3)])])
}

/// Koncovky buněk, které protojazyk se syntaxí může mít.
pub fn syntax_endings() -> Endings {
    let mut all = proto_endings();
    all.extend(endings(&[
        ("noun", "OBJ", &[("m", 0.6), ("ne", 0.4)]),
        ("noun", "DEF", &[("le", 0.7), ("n", 0.3)]),
        ("verb", "FUT", &[("sa", 0.6), ("bo", 0.4)]),
    ]));
    all
}

/// Přepínače modelu protojazyka (`village_grid` a `region_world` bez `languages`).
#[derive(Clone)]
pub struct SeedOptions {
    pub phonology: bool,
    pub morphology: bool,
    pub semantics: bool,
    pub syntax: bool,
    pub grammar: Option<Vec<(&'static str, Construction)>>,
    pub prosody: bool,
    pub stress_rule: StressRule,
    pub stress_strength: StressStrength,
}

impl Default for SeedOptions {
    fn default() -> Self {
        SeedOptions {
            phonology: false,
            morphology: false,
            semantics: false,
            syntax: false,
            grammar: None,
            prosody: false,
            stress_rule: StressRule::Penult,
            stress_strength: StressStrength::Weak,
        }
    }
}

/// Výchozí pojmy (`DEFAULT_CONCEPTS`).
pub fn default_concepts() -> Vec<String> {
    Defaults::shared().default_concepts.clone()
}

fn dedup_with(concepts: &[String], extra: &[&str]) -> Vec<String> {
    let mut seen = std::collections::HashSet::new();
    concepts.iter().map(String::as_str).chain(extra.iter().copied()).filter(|c| seen.insert(*c)).map(str::to_owned).collect()
}

/// Paradigmata podle profilu: buňka pro každou funkci vyjádřenou koncovkou.
pub fn grammar_paradigms(grammar: &[(&'static str, Construction)]) -> Result<Vec<(String, Vec<(String, f64)>)>, String> {
    let catalog = Catalog::shared();
    let mut cells: Vec<(String, Vec<(String, f64)>)> =
        CITATION_CELLS.iter().map(|(class, _)| ((*class).to_owned(), Vec::new())).collect();
    for entry in &catalog.functions {
        let Some((_, construction)) = grammar.iter().find(|(name, _)| *name == entry.id) else { continue };
        let Some(cell) = &entry.cell else { continue };
        if construction.kind != "synthetic" {
            continue;
        }
        let class = entry.word_class().ok_or("funkce s buňkou bez třídy slova")?;
        let slot = cells.iter_mut().find(|(c, _)| c == class).ok_or("neznámá třída")?;
        slot.1.push((cell.clone(), entry.weight));
    }
    Ok(cells)
}

fn install_paradigms(world: &mut World, grammar: Option<&[(&'static str, Construction)]>, plain: bool) -> Result<(), String> {
    if plain {
        world.set_paradigm("noun", &[("SG", 1.0), ("PL", 0.4)]);
        world.set_paradigm("verb", &[("PRES", 1.0), ("PAST", 0.5)]);
        return Ok(());
    }
    for (class, found) in grammar_paradigms(grammar.expect("gramatika"))? {
        let citation = CITATION_CELLS.iter().find(|(c, _)| *c == class).expect("citační buňka").1;
        let mut cells: Vec<(&str, f64)> = vec![(citation, 1.0)];
        cells.extend(found.iter().map(|(c, w)| (c.as_str(), *w)));
        world.set_paradigm(&class, &cells);
    }
    Ok(())
}

/// Každá funkce profilu dostane konstrukční proměnnou s výchozí konstrukcí.
fn seed_constructions(world: &mut World, base: Arc<Repertoire>, grammar: &[(&'static str, Construction)]) -> Result<Arc<Repertoire>, String> {
    let mut layer = Repertoire::over(base);
    let origin = Origin::inherited(world.start_year);
    let catalog = Catalog::shared().with_overrides(&world.params)?;
    for (name, construction) in grammar {
        if construction.function != *name || catalog.get(name).is_none() {
            return Err(format!("Neznámá nebo nesouhlasná funkce profilu: {name}."));
        }
        let (variable, variant) = world.register_construction(construction, &origin);
        layer.set(variable, Distribution::fixed(variant));
    }
    Ok(layer.freeze())
}

/// Prozodické proměnné protojazyka: pravidlo přízvuku a jeho síla.
fn seed_prosody(world: &mut World, base: Arc<Repertoire>, rule: StressRule, strength: StressStrength) -> Arc<Repertoire> {
    let mut layer = Repertoire::over(base);
    let origin = Origin::inherited(world.start_year);
    let (rule_var, rule_variant) = world.register_prosody("stress_rule", rule.name(), &origin);
    layer.set(rule_var, Distribution::fixed(rule_variant));
    let (strength_var, strength_variant) = world.register_prosody("stress_strength", strength.name(), &origin);
    layer.set(strength_var, Distribution::fixed(strength_variant));
    layer.freeze()
}

/// Třída slova každého ohebného pojmu výchozího slovníku.
fn word_classes(concepts: &[String]) -> HashMap<String, String> {
    let defaults = Defaults::shared();
    concepts
        .iter()
        .filter_map(|c| defaults.word_class(c).map(|class| (c.clone(), class.to_owned())))
        .collect()
}

/// Graf pojmů světa z vložených dat (`core_graph()`).
fn install_graph(world: &mut World) -> Result<(), String> {
    let graph = ConceptGraph::core(&mut world.registry, crate::data::CORE_SEMANTICS_JSON, Defaults::shared())?;
    world.grow_concepts();
    world.semantics = Some(Arc::new(graph));
    Ok(())
}

/// Protojazyk světa (slovník, tvary, gramatika, přízvuk) jako výchozí repertoár.
pub fn seed_language(world: &mut World, seed: i64, concepts: &[String], options: &SeedOptions) -> Result<Arc<Repertoire>, String> {
    let mut syntax = options.syntax;
    let mut morphology = options.morphology;
    let mut phonology = options.phonology;
    let grammar: Vec<(&'static str, Construction)> = match &options.grammar {
        Some(given) => {
            syntax = true;
            given.clone()
        }
        None => profile::syntax(),
    };
    let mut concepts = concepts.to_vec();
    if syntax {
        morphology = true;
        phonology = true;
        concepts = dedup_with(&concepts, &GRAMMATICAL_SOURCES);
        install_paradigms(world, Some(&grammar), false)?;
    } else if morphology {
        install_paradigms(world, None, true)?;
    }
    if options.semantics {
        install_graph(world)?;
    }
    if !(phonology || morphology || options.semantics) {
        return world.seed_lexicon(&concepts, None, None, None, &Endings::new(), "proto", None);
    }
    let fixed = HashMap::new();
    let (forms, frequencies) = protolanguage(
        &ProtoSpec {
            concepts: &concepts,
            seed: seed as u64,
            consonants: &Defaults::shared().default_consonants,
            vowels: &Defaults::shared().default_vowels,
            fixed: &fixed,
            tones: &[],
            known_frequencies: None,
        },
        ConceptData::shared(),
    )?;
    let classes = morphology.then(|| word_classes(&concepts));
    let used = if syntax {
        syntax_endings()
    } else if morphology {
        proto_endings()
    } else {
        Endings::new()
    };
    let mut base = world.seed_lexicon(&concepts, Some(&forms), Some(&frequencies), classes.as_ref(), &used, "proto", None)?;
    if syntax {
        base = seed_constructions(world, base, &grammar)?;
    }
    if phonology || options.prosody {
        base = seed_prosody(world, base, options.stress_rule, options.stress_strength);
    }
    if options.semantics && world.table.is_some() {
        world.derivational_suffix = world.table.as_ref().expect("tabulka").parse(DERIVATIONAL_SUFFIX)?;
    }
    Ok(base)
}

fn new_code(world: &mut World, base: &Arc<Repertoire>, language: LanguageId, rule: StressRule, strength: StressStrength) -> Code {
    let _ = world;
    let mut code = Code::new("main", Repertoire::over(base.clone()), language);
    code.stress_rule = rule;
    code.stress_strength = strength;
    code
}

/// Mřížka stejných vesnic s gravitačními vazbami na nejbližší sousedy.
///
/// S jedním řádkem je to scénář S1 (dialektové kontinuum). Vazby sahají jen do
/// `link_reach` násobku rozestupu.
#[allow(clippy::too_many_arguments)]
pub fn village_grid(
    columns: usize,
    rows: usize,
    seed: i64,
    options: &SeedOptions,
    concepts: &[String],
    spacing: f64,
    population: u32,
    generation_years: f64,
    openness: f64,
    link_reach: f64,
    params: Parameters,
) -> Result<World, String> {
    let mut world = World::new(seed, params);
    world.add_territory("world", None, Territory::new(TerritoryLevel::World))?;
    let mut valley = Territory::new(TerritoryLevel::Area);
    valley.position = Some(((columns as f64 - 1.0) * spacing / 2.0, (rows as f64 - 1.0) * spacing / 2.0));
    world.add_territory("valley", Some("world"), valley)?;
    let base = seed_language(&mut world, seed, concepts, options)?;
    let language = world.language("proto");
    for row in 0..rows {
        for column in 0..columns {
            let village = format!("v{row:02}-{column:02}");
            let mut settlement = Territory::new(TerritoryLevel::Settlement);
            settlement.position = Some((column as f64 * spacing, row as f64 * spacing));
            let territory = world.add_territory(&village, Some("valley"), settlement)?;
            let code = new_code(&mut world, &base, language, options.stress_rule, options.stress_strength);
            let mut init = GroupInit::new(&village, territory, population, vec![code]);
            init.generation_years = generation_years;
            init.openness = openness;
            world.add_group(init)?;
        }
    }
    gravity_links(&mut world, Some(spacing * link_reach), None)?;
    Ok(world)
}

/// `village_grid` s výchozími hodnotami Pythonu.
pub fn village_grid_default(columns: usize, rows: usize, seed: i64, options: &SeedOptions) -> Result<World, String> {
    village_grid(columns, rows, seed, options, &default_concepts(), 10.0, 500, 25.0, 0.1, 2.0, Parameters::default())
}

/// Region pro [`region_world`]: poloha těžiště, relativní hustota a sousedé.
#[derive(Clone, Debug)]
pub struct Region {
    pub id: String,
    pub position: (f64, f64),
    pub density: f64,
    pub neighbours: Vec<String>,
    pub villages: usize,
    pub prestige: f64,
    pub openness: Option<f64>,
    pub immigration: f64,
    pub language: Option<String>,
    pub terrain: String,
    pub identity: String,
    pub preserve: bool,
}

impl Region {
    pub fn new(id: &str, position: (f64, f64)) -> Region {
        Region {
            id: id.into(),
            position,
            density: 1.0,
            neighbours: Vec::new(),
            villages: 4,
            prestige: 0.5,
            openness: None,
            immigration: 0.0,
            language: None,
            terrain: "plain".into(),
            identity: "shared".into(),
            preserve: false,
        }
    }
}

/// Protojazyk vlastní linie (`ProtoLanguage`, `Language`).
#[derive(Clone, Debug)]
pub struct ProtoLanguage {
    pub id: String,
    pub grammar: Vec<(&'static str, Construction)>,
    pub consonants: Vec<String>,
    pub vowels: Vec<String>,
    pub stress_rule: StressRule,
    pub stress_strength: StressStrength,
    pub words: HashMap<String, String>,
    pub endonym: Vec<String>,
    pub tones: Vec<String>,
}

impl ProtoLanguage {
    pub fn new(id: &str) -> ProtoLanguage {
        let defaults = Defaults::shared();
        ProtoLanguage {
            id: id.into(),
            grammar: profile::syntax(),
            consonants: defaults.default_consonants.clone(),
            vowels: defaults.default_vowels.clone(),
            stress_rule: StressRule::Penult,
            stress_strength: StressStrength::Weak,
            words: HashMap::new(),
            endonym: Vec::new(),
            tones: Vec::new(),
        }
    }

    pub fn with_consonants(mut self, consonants: &[&str]) -> Self {
        self.consonants = consonants.iter().map(|c| (*c).to_owned()).collect();
        self
    }

    pub fn with_grammar(mut self, grammar: Vec<(&'static str, Construction)>) -> Self {
        self.grammar = grammar;
        self
    }
}

/// Protojazyky několika nepříbuzných linií (každý vlastní tvary a gramatiku).
///
/// Paradigmata světa jsou sjednocení buněk všech jazyků; každý jazyk dostane koncovky
/// jen ve svých buňkách.
pub fn seed_lineages(
    world: &mut World,
    languages: &[ProtoLanguage],
    seed: i64,
    concepts: &[String],
    semantics: bool,
) -> Result<HashMap<String, Arc<Repertoire>>, String> {
    let concepts = dedup_with(concepts, &GRAMMATICAL_SOURCES);
    let mut cells: HashMap<String, HashMap<String, Vec<String>>> = HashMap::new();
    let mut union: HashMap<String, std::collections::BTreeSet<String>> = HashMap::new();
    for language in languages {
        let mut own = HashMap::new();
        for (class, found) in grammar_paradigms(&language.grammar)? {
            let names: Vec<String> = found.into_iter().map(|(c, _)| c).collect();
            union.entry(class.clone()).or_default().extend(names.iter().cloned());
            own.insert(class, names);
        }
        cells.insert(language.id.clone(), own);
    }
    let catalog = Catalog::shared().with_overrides(&world.params)?;
    let order: HashMap<&str, usize> =
        catalog.functions.iter().enumerate().filter_map(|(i, e)| e.cell.as_deref().map(|c| (c, i))).collect();
    let weights: HashMap<&str, f64> =
        catalog.functions.iter().filter_map(|e| e.cell.as_deref().map(|c| (c, e.weight))).collect();
    for (class, citation) in CITATION_CELLS {
        let mut ordered: Vec<&String> = union.get(class).map(|s| s.iter().collect()).unwrap_or_default();
        ordered.sort_by_key(|c| order[c.as_str()]);
        let mut all: Vec<(&str, f64)> = vec![(citation, 1.0)];
        all.extend(ordered.iter().map(|c| (c.as_str(), weights[c.as_str()])));
        world.set_paradigm(class, &all);
    }
    if semantics {
        install_graph(world)?;
    }
    let classes = word_classes(&concepts);
    let used = syntax_endings();
    let mut bases = HashMap::new();
    for language in languages {
        let language_seed = stable_int(&[Part::Int(seed), Part::Str("language"), Part::Str(&language.id)]) % (1 << 31);
        let (forms, frequencies) = protolanguage(
            &ProtoSpec {
                concepts: &concepts,
                seed: language_seed,
                consonants: &language.consonants,
                vowels: &language.vowels,
                fixed: &language.words,
                tones: &language.tones,
                known_frequencies: None,
            },
            ConceptData::shared(),
        )?;
        let base = world.seed_lexicon(
            &concepts, Some(&forms), Some(&frequencies), Some(&classes), &used, &language.id, Some(&cells[&language.id]),
        )?;
        let base = seed_constructions(world, base, &language.grammar)?;
        bases.insert(language.id.clone(), seed_prosody(world, base, language.stress_rule, language.stress_strength));
    }
    Ok(bases)
}

/// Regiony jako sítě vesnic; sousední regiony spojují jen pohraniční vesnice.
///
/// Každý region má vesnici v těžišti a zbytek na prstenci o poloměru `village_spacing`;
/// uvnitř regionu gravitační vazby, mezi sousedními regiony jediná vazba mezi nejbližší
/// dvojicí vesnic (násobená `border_link_scale` a terénem).
#[allow(clippy::too_many_arguments)]
pub fn region_world(
    regions: &[Region],
    seed: i64,
    options: &SeedOptions,
    village_spacing: f64,
    generation_years: f64,
    link_reach: f64,
    params: Parameters,
    languages: &[ProtoLanguage],
) -> Result<World, String> {
    let mut world = World::new(seed, params);
    let concepts = default_concepts();
    let ids: Vec<&str> = regions.iter().map(|r| r.id.as_str()).collect();
    let unique: std::collections::HashSet<&&str> = ids.iter().collect();
    if unique.len() != ids.len() {
        return Err("Regiony musí mít jedinečná ID.".into());
    }
    for region in regions {
        let unknown: Vec<&String> = region.neighbours.iter().filter(|n| !ids.contains(&n.as_str())).collect();
        if !unknown.is_empty() {
            return Err(format!("Region '{}' sousedí s neznámými regiony: {unknown:?}.", region.id));
        }
        if region.villages < 1 {
            return Err(format!("Region '{}' musí mít aspoň jednu vesnici.", region.id));
        }
        if region.density <= 0.0 {
            return Err(format!("Region '{}' musí mít kladnou hustotu.", region.id));
        }
        Parameters::level(&world.params.terrain_access, &region.terrain, "úroveň terénu")?;
        Parameters::level(&world.params.identity_loyalty, &region.identity, "úroveň identity")?;
    }
    world.add_territory("world", None, Territory::new(TerritoryLevel::World))?;
    let lineages: HashMap<&str, &ProtoLanguage> = languages.iter().map(|l| (l.id.as_str(), l)).collect();
    let bases: HashMap<String, Arc<Repertoire>> = if !languages.is_empty() {
        if lineages.len() != languages.len() {
            return Err("Protojazyky musí mít jedinečná ID.".into());
        }
        for region in regions {
            if let Some(name) = &region.language {
                if !lineages.contains_key(name.as_str()) {
                    return Err(format!("Region '{}' má neznámý protojazyk '{name}'.", region.id));
                }
            }
        }
        let bases = seed_lineages(&mut world, languages, seed, &concepts, options.semantics)?;
        for language in languages {
            if !language.endonym.is_empty() {
                let lang = world.language(&language.id);
                let ids = language.endonym.iter().map(|c| world.registry.concept(c)).collect();
                world.society.endonyms.insert(lang, ids);
            }
        }
        if options.semantics && world.table.is_some() {
            world.derivational_suffix = world.table.as_ref().expect("tabulka").parse(DERIVATIONAL_SUFFIX)?;
        }
        bases
    } else {
        let named: Vec<&String> = regions.iter().filter_map(|r| r.language.as_ref()).collect();
        if !named.is_empty() {
            return Err(format!("Regiony {named:?} mají protojazyk, ale ``languages`` je prázdné."));
        }
        HashMap::from([("proto".to_owned(), seed_language(&mut world, seed, &concepts, options)?)])
    };
    let mut villages_of: HashMap<String, Vec<GroupId>> = HashMap::new();
    for region in regions {
        let lineage = if languages.is_empty() {
            None
        } else {
            lineages.get(region.language.as_deref().unwrap_or(&languages[0].id)).copied()
        };
        let language_name = lineage.map_or("proto", |l| l.id.as_str());
        let language = world.language(language_name);
        let mut territory = Territory::new(TerritoryLevel::Region);
        territory.position = Some(region.position);
        territory.terrain = region.terrain.clone();
        territory.native_language = language;
        world.add_territory(&region.id, Some("world"), territory)?;
        let population = ((region.density * world.params.population_per_density).round_ties_even() as i64).max(1) as u32;
        let base = bases[language_name].clone();
        let rule = lineage.map_or(options.stress_rule, |l| l.stress_rule);
        let strength = lineage.map_or(options.stress_strength, |l| l.stress_strength);
        let mut members = Vec::new();
        for index in 0..region.villages {
            let position = if index == 0 {
                region.position
            } else {
                let angle = 2.0 * std::f64::consts::PI * (index - 1) as f64 / (region.villages - 1) as f64;
                (region.position.0 + village_spacing * angle.cos(), region.position.1 + village_spacing * angle.sin())
            };
            let village = format!("{}-v{index}", region.id);
            let mut settlement = Territory::new(TerritoryLevel::Settlement);
            settlement.position = Some(position);
            let territory_id = world.add_territory(&village, Some(&region.id), settlement)?;
            let mut code = new_code(&mut world, &base, language, rule, strength);
            code.l2_share = region.immigration;
            let mut init = GroupInit::new(&village, territory_id, population, vec![code]);
            init.generation_years = generation_years;
            init.openness = region.openness.unwrap_or(world.params.village_openness);
            init.prestige = region.prestige;
            init.immigration = region.immigration;
            init.loyalty = world.params.identity_loyalty[&region.identity];
            init.preserved = region.preserve;
            members.push(world.add_group(init)?);
        }
        gravity_links(&mut world, Some(village_spacing * link_reach), Some(&members))?;
        villages_of.insert(region.id.clone(), members);
    }
    for region in regions {
        let mut neighbours = region.neighbours.clone();
        neighbours.sort();
        for neighbour in neighbours {
            let other = regions.iter().find(|r| r.id == neighbour).expect("soused");
            if neighbour < region.id && other.neighbours.contains(&region.id) {
                continue; // dvojici už spojil soused
            }
            let mut best: Option<(f64, GroupId, GroupId)> = None;
            for &a in &villages_of[&region.id] {
                for &b in &villages_of[&neighbour] {
                    let (pa, pb) = (world.position_of(a).unwrap_or((0.0, 0.0)), world.position_of(b).unwrap_or((0.0, 0.0)));
                    let distance = (pa.0 - pb.0).hypot(pa.1 - pb.1);
                    let better = best.map_or(true, |(d, ba, bb)| {
                        distance < d
                            || (distance == d
                                && (world.group_name(a), world.group_name(b)) < (world.group_name(ba), world.group_name(bb)))
                    });
                    if better {
                        best = Some((distance, a, b));
                    }
                }
            }
            let (_, first, second) = best.expect("vesnice");
            gravity_links(&mut world, None, Some(&[first, second]))?;
            let strength = world.links.get(first, second).expect("vazba").strength;
            let terrain = world.params.terrain_access[&region.terrain] * world.params.terrain_access[&other.terrain];
            let scaled = strength * world.params.border_link_scale * terrain;
            world.connect(first, second, scaled, LinkKind::Weak)?;
        }
    }
    Ok(world)
}

/// Skupina mluvčích v [`contact_world`].
#[derive(Clone, Debug)]
pub struct Place {
    pub id: String,
    pub position: (f64, f64),
    pub population: u32,
    pub prestige: f64,
    pub openness: f64,
    pub immigration: f64,
}

impl Place {
    pub fn new(id: &str, position: (f64, f64)) -> Place {
        Place { id: id.into(), position, population: 500, prestige: 0.5, openness: 0.1, immigration: 0.0 }
    }
}

/// Jeden protojazyk světa s víc jazyky a skupiny, které jím mluví.
#[derive(Clone, Debug)]
pub struct Language {
    pub proto: ProtoLanguage,
    pub places: Vec<Place>,
    /// Vazby uvnitř jazyka sahají do této vzdálenosti (km).
    pub link_reach: f64,
}

impl Language {
    pub fn new(id: &str, places: Vec<Place>) -> Language {
        Language { proto: ProtoLanguage::new(id), places, link_reach: 25.0 }
    }
}

/// Svět s několika nepříbuznými jazyky (M5); vazby vznikají jen uvnitř jazyka.
pub fn contact_world(languages: &[Language], seed: i64, semantics: bool, generation_years: f64, params: Parameters) -> Result<World, String> {
    let mut world = World::new(seed, params);
    world.add_territory("world", None, Territory::new(TerritoryLevel::World))?;
    let protos: Vec<ProtoLanguage> = languages.iter().map(|l| l.proto.clone()).collect();
    let bases = seed_lineages(&mut world, &protos, seed, &default_concepts(), semantics)?;
    for language in languages {
        let base = bases[&language.proto.id].clone();
        let lang_id = world.language(&language.proto.id);
        let area = format!("area-{}", language.proto.id);
        let mut area_territory = Territory::new(TerritoryLevel::Area);
        area_territory.position = Some(language.places[0].position);
        world.add_territory(&area, Some("world"), area_territory)?;
        let mut members = Vec::new();
        for place in &language.places {
            let mut settlement = Territory::new(TerritoryLevel::Settlement);
            settlement.position = Some(place.position);
            let territory = world.add_territory(&place.id, Some(&area), settlement)?;
            let mut code = new_code(&mut world, &base, lang_id, language.proto.stress_rule, language.proto.stress_strength);
            code.l2_share = place.immigration;
            let mut init = GroupInit::new(&place.id, territory, place.population, vec![code]);
            init.generation_years = generation_years;
            init.prestige = place.prestige;
            init.openness = place.openness;
            init.immigration = place.immigration;
            members.push(world.add_group(init)?);
        }
        gravity_links(&mut world, Some(language.link_reach), Some(&members))?;
    }
    if semantics && world.table.is_some() {
        world.derivational_suffix = world.table.as_ref().expect("tabulka").parse(DERIVATIONAL_SUFFIX)?;
    }
    Ok(world)
}

type Scenario = Result<(World, Vec<Box<dyn WorldEvent>>), String>;

fn event(year: f64, kind: &str, params: serde_json::Value) -> Box<dyn WorldEvent> {
    Box::new(PendingEvent::new(year, kind, params))
}

/// Scénář S2: izolovaný ostrov a obchodní město se stejným protojazykem.
pub fn island_and_city(seed: i64, immigration: f64) -> Result<World, String> {
    let mut places = vec![
        Place { population: 300, openness: 0.0, ..Place::new("island", (-200.0, 0.0)) },
        Place { population: 5000, openness: 0.3, immigration, ..Place::new("city", (0.0, 0.0)) },
    ];
    for (index, (x, y)) in [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)].into_iter().enumerate() {
        places.push(Place::new(&format!("v{index}"), (15.0 * x, 15.0 * y)));
    }
    contact_world(&[Language::new("proto", places)], seed, true, 25.0, Parameters::default())
}

/// Scénář S3: menšinový region přejde na prestižní jazyk souseda.
pub fn language_shift(seed: i64, start: f64) -> Scenario {
    let x_places = (0..3).map(|i| Place { prestige: 0.3, ..Place::new(&format!("x{i}"), (i as f64 * 10.0, 0.0)) }).collect();
    let y_places = (0..3)
        .map(|i| Place { population: 1000, prestige: 1.0, ..Place::new(&format!("y{i}"), (40.0 + i as f64 * 10.0, 0.0)) })
        .collect();
    let mut x = Language::new("x", x_places);
    x.proto = x.proto.with_grammar(profile::substrate()).with_consonants(&[
        "t", "k", "q", "s", "n", "m", "l", "ʃ", "x", "r", "j", "ts",
    ]);
    let world = contact_world(&[x, Language::new("y", y_places)], seed, true, 25.0, Parameters::default())?;
    let mut events = vec![event(start, "contact", json!({"pairs": [["x2", "y0"]], "strength": 0.5}))];
    for step in 0..3 {
        events.push(event(
            start + 25.0 * step as f64,
            "language_shift",
            json!({"group": format!("x{}", 2 - step), "target": "y0"}),
        ));
    }
    Ok((world, events))
}

/// Scénář S4: písmo v roce `writing`, škola (a tisk) v roce `school`.
pub fn diglossia(seed: i64, writing: f64, school: Option<f64>, printing: bool, literacy: f64, diglossic: bool) -> Scenario {
    let options = SeedOptions { syntax: true, semantics: true, ..SeedOptions::default() };
    let world = village_grid_default(6, 1, seed, &options)?;
    let groups: Vec<String> = world.group_ids().iter().map(|&g| world.group_name(g).to_owned()).collect();
    let elite = groups[2].clone();
    let mut events = vec![event(writing, "codification", json!({"source": elite, "groups": groups, "literacy": literacy}))];
    if let Some(year) = school {
        events.push(event(year, "schooling", json!({"groups": groups, "diglossic": diglossic})));
        if printing && !diglossic {
            events.push(event(year, "printing", json!({"standard": format!("written:{elite}")})));
        }
    }
    Ok((world, events))
}

/// Dobytí a přechod elity: superstrát (typ Normané v Anglii).
pub fn conquest(seed: i64, year: f64) -> Scenario {
    let l_places = (0..4)
        .map(|i| Place { population: 1000, ..Place::new(&format!("l{i}"), (((i % 2) * 10) as f64, ((i / 2) * 10) as f64)) })
        .collect();
    let mut e = Language::new(
        "e",
        vec![Place { population: 2000, prestige: 1.0, ..Place::new("e0", (300.0, 0.0)) }],
    );
    e.proto = e.proto.with_grammar(profile::substrate()).with_consonants(&[
        "t", "k", "s", "n", "m", "l", "ʃ", "f", "x", "v", "r", "j",
    ]);
    let world = contact_world(&[Language::new("l", l_places), e], seed, true, 25.0, Parameters::default())?;
    let events = vec![
        event(year, "conquest", json!({"elite": "e0", "seat": "l0", "regions": ["l0", "l1", "l2", "l3"]})),
        event(year + 100.0, "language_shift", json!({"group": "l0+e0", "target": "l0"})),
    ];
    Ok((world, events))
}

/// Stabilní dvojjazyčnost: vesnice užívá jazyk trhu jen mimo domov.
pub fn market_town(seed: i64, start: f64) -> Scenario {
    let a_places = (0..2).map(|i| Place::new(&format!("a{i}"), (i as f64 * 10.0, 0.0))).collect();
    let b = Language::new("b", vec![Place { population: 3000, prestige: 1.0, ..Place::new("b0", (30.0, 0.0)) }]);
    let world = contact_world(&[Language::new("a", a_places), b], seed, true, 25.0, Parameters::default())?;
    let events = vec![
        event(start, "contact", json!({"pairs": [["a1", "b0"]], "strength": 0.5})),
        event(start, "language_shift", json!({"group": "a1", "target": "b0", "initial_share": 0.3, "domain": "public"})),
    ];
    Ok((world, events))
}

/// Město, čtyři trhová městečka a osm vesnic s gravitační migrací.
pub fn migration_region(seed: i64, migration: f64) -> Result<World, String> {
    let directions = [(1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)];
    let mut places = vec![Place { population: 5000, prestige: 1.0, ..Place::new("city", (0.0, 0.0)) }];
    for (index, (x, y)) in directions.iter().enumerate() {
        places.push(Place { population: 1500, prestige: 0.7, ..Place::new(&format!("t{index}"), (25.0 * x, 25.0 * y)) });
    }
    let mut index = 0;
    for (dx, dy) in [(1.0, 1.0), (-1.0, -1.0)] {
        for (x, y) in directions {
            places.push(Place { population: 300, ..Place::new(&format!("v{index}"), (12.0 * dx + 25.0 * x, 12.0 * dy + 25.0 * y)) });
            index += 1;
        }
    }
    let mut world = contact_world(&[Language::new("proto", places)], seed, true, 25.0, Parameters::default())?;
    world.society.migration = migration;
    Ok(world)
}

/// Náboženská změna: vesnice přijmou víru s cizím liturgickým jazykem.
pub fn conversion(seed: i64, year: f64, devotion: f64) -> Scenario {
    let v_places = (0..4).map(|i| Place { population: 600, ..Place::new(&format!("v{i}"), (i as f64 * 10.0, 0.0)) }).collect();
    let mut r = Language::new("r", vec![Place { population: 5000, prestige: 1.0, ..Place::new("r0", (500.0, 0.0)) }]);
    r.proto = r.proto.with_consonants(&["t", "k", "s", "n", "m", "l", "r", "f", "x", "kʷ", "j", "d"]);
    let world = contact_world(&[Language::new("v", v_places), r], seed, true, 25.0, Parameters::default())?;
    let villages: Vec<String> = (0..4).map(|i| format!("v{i}")).collect();
    let events = vec![
        event(100.0, "codification", json!({"source": "r0", "groups": ["r0"], "literacy": 0.1})),
        event(year, "religious_change", json!({"liturgy": "written:r0", "groups": villages, "devotion": devotion})),
    ];
    Ok((world, events))
}

/// Rozpad jazyka se známou historií pro ověření stromu jazyků.
pub fn known_tree(seed: i64, first: f64, second: f64) -> Scenario {
    let mut places = Vec::new();
    for (position, cluster) in ["a", "b", "c"].iter().enumerate() {
        for index in 0..3 {
            places.push(Place::new(&format!("{cluster}{index}"), (((3 * position + index) * 10) as f64, 0.0)));
        }
    }
    let world = contact_world(&[Language::new("proto", places)], seed, true, 25.0, Parameters::default())?;
    let side = |c: &str| (0..3).map(|i| format!("{c}{i}")).collect::<Vec<_>>();
    let ab: Vec<String> = side("a").into_iter().chain(side("b")).collect();
    let events = vec![
        event(first, "border", json!({"first": ab, "second": side("c"), "factor": 0.0})),
        event(second, "border", json!({"first": side("a"), "second": side("b"), "factor": 0.0})),
    ];
    Ok((world, events))
}

/// Ukázkový stát čtyř jazyků (M6f): které regiony přejdou a které ne.
pub fn kingdom(
    seed: i64,
    founded: f64,
    policy: &str,
    modern: Option<f64>,
    lingua_franca: bool,
    standard: Option<f64>,
    own_standard: &[&str],
) -> Scenario {
    let region = |id: &str, pos: (f64, f64), language: &str| Region { language: Some(language.into()), ..Region::new(id, pos) };
    let regions = vec![
        Region { density: 2.0, neighbours: vec!["plain".into(), "mountains".into(), "south".into()], ..region("capital", (0.0, 0.0), "a") },
        Region { neighbours: vec!["capital".into()], ..region("plain", (60.0, 0.0), "b") },
        Region {
            density: 0.5,
            neighbours: vec!["capital".into()],
            terrain: "mountains".into(),
            identity: "strong".into(),
            ..region("mountains", (0.0, 60.0), "c")
        },
        Region { neighbours: vec!["capital".into()], identity: "distinct".into(), ..region("south", (0.0, -60.0), "d") },
    ];
    let languages = vec![
        ProtoLanguage::new("a"),
        ProtoLanguage::new("b").with_consonants(&["t", "k", "q", "s", "n", "m", "l", "ʃ", "x", "r", "j"]),
        ProtoLanguage::new("c")
            .with_grammar(profile::substrate())
            .with_consonants(&["p", "t", "k", "s", "n", "m", "l", "f", "v", "r", "j"]),
        ProtoLanguage::new("d").with_consonants(&["b", "d", "g", "s", "n", "m", "l", "r", "w"]),
    ];
    let options = SeedOptions::default();
    let world = region_world(&regions, seed, &options, 10.0, 25.0, 2.0, Parameters::default(), &languages)?;
    let ids = ["capital", "plain", "mountains", "south"];
    let mut events = Vec::new();
    if lingua_franca {
        events.push(event(0.0, "lingua_franca", json!({"source": "capital", "regions": &ids[1..]})));
    }
    events.push(event(founded, "state", json!({"id": "kingdom", "regions": ids, "capital": "capital", "policy": policy})));
    if let Some(year) = standard {
        events.push(event(year, "standard", json!({"of": "kingdom"})));
        for region in own_standard {
            events.push(event(year, "standard", json!({"of": region})));
        }
    }
    if let Some(year) = modern {
        events.push(event(year, "language_policy", json!({"state": "kingdom", "policy": "enforced"})));
        if standard.is_some() {
            events.push(event(year, "schools", json!({"of": "kingdom"})));
            for region in own_standard {
                events.push(event(year, "schools", json!({"of": region})));
            }
        }
    }
    Ok((world, events))
}

/// Scénář podle jména (pro CLI): `valley-50`, `grid-5x5`, `phonology`, `morphology`, `syntax`,
/// `shift`, `island-city`, `diglossia`, `conquest`, `market`, `migration`, `conversion`, `tree`, `kingdom`.
pub fn by_name(name: &str) -> Scenario {
    let none = |world: Result<World, String>| world.map(|w| (w, Vec::new()));
    match name {
        "phonology" => none(village_grid_default(4, 1, 2, &SeedOptions { phonology: true, ..SeedOptions::default() })),
        "morphology" => none(village_grid_default(4, 1, 2, &SeedOptions { morphology: true, semantics: true, ..SeedOptions::default() })),
        "syntax" => none(village_grid_default(4, 1, 2, &SeedOptions { syntax: true, semantics: true, ..SeedOptions::default() })),
        "grid-5x5" => none(village_grid_default(5, 5, 2, &SeedOptions { morphology: true, semantics: true, ..SeedOptions::default() })),
        "valley-50" => none(village_grid_default(10, 5, 1, &SeedOptions { syntax: true, semantics: true, ..SeedOptions::default() })),
        "shift" => language_shift(2, 300.0),
        "island-city" => none(island_and_city(2, 0.3)),
        "diglossia" => diglossia(1, 500.0, Some(1500.0), true, 0.05, false),
        "conquest" => conquest(1, 1000.0),
        "market" => market_town(1, 500.0),
        "migration" => none(migration_region(1, 0.1)),
        "conversion" => conversion(1, 500.0, 0.3),
        "tree" => known_tree(1, 300.0, 1800.0),
        "kingdom" => kingdom(1, 100.0, "promoted", None, false, None, &[]),
        other => Err(format!("Neznámý scénář '{other}'.")),
    }
}

/// Jména scénářů pro `cee scenario`.
pub const SCENARIO_NAMES: [&str; 14] = [
    "phonology", "morphology", "syntax", "grid-5x5", "valley-50", "shift", "island-city", "diglossia", "conquest",
    "market", "migration", "conversion", "tree", "kingdom",
];

#[allow(dead_code)]
fn _registry_marker(_: &Registry) {}

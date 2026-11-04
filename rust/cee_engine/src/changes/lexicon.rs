//! Lexikální a sémantické změny (zrcadlo `changes/lexicon.py`).
//!
//! Nové slovo pro pojem má vždy doložitelný původ: expresivní tvoření (nový kořen podle
//! fonotaktiky jazyka), posun významu, konverze, odvození, složenina, opis za tabu,
//! kontaminace, zpětné tvoření a výpůjčka od souseda jiného jazyka. O tom, které slovo se
//! prosadí, rozhodují lexikální tlaky (R1a), ne tato vrstva.
//!
//! **Návrh.** Sedm sémantických změn sdílí jednu strukturu ([`SemanticChange`]) s druhem
//! v `match`; jejich místa (pojmy, které mají cestu k novému slovu) a míry se drží v keši
//! kódu podle verze slovní zásoby. Nic nehledá podle řetězců: pojmy a kořeny jsou čísla,
//! jména se berou jen pro stabilní ID nových entit a klíče náhody.
//!
//! **Výpůjčky a kontakt (R1d).** Dárci a jejich podíl na vstupu se čtou přímo z vazeb a
//! skupin (`links`, `prestige`, `openness`, `elite`, `society.trade`); kanály berou z
//! `Parameters::channel_domains`. Až R1d dodá vlastní stav kontaktu, stačí zaměnit
//! [`donors`] a [`channel_exposures`].

use std::sync::Arc;

use crate::changes::{
    Change, InnovationContext, NewVariant, Sites, COINAGE_PRESSURES, LEXICAL_PRESSURES,
};
use crate::contact;
use crate::ids::{ConceptId, GroupId, MorphemeId, VariableId, VariantId};
use crate::model::lexicon::{MorphemeInit, MorphemeKind, MorphemeMeta};
use crate::model::repertoire::{Origin, Payload, VariableKind};
use crate::parameters::CHANNELS;
use crate::rng::{stable_id, Part, Stream};
use crate::syntax::dominant_root;
use crate::views::{SemanticRates, SEMANTIC_KINDS};
use crate::world::World;

/// Podíl expresivního tvoření ve světě s významy (jen malá část obměny slovníku).
const EXPRESSIVE_SHARE: f64 = 0.1;
const COINAGE_RATE: f64 = 4e-4;
const BORROWING_RATE: f64 = 1e-3;
const APPEAL_MEAN: f64 = -0.05;
const APPEAL_SD: f64 = 0.15;
/// Nejdelší složenina, která se v řeči ujme (počet hlásek).
const MAX_COMPOUND: usize = 10;

// --- společné pomocné funkce --------------------------------------------------------------

/// Lexikální proměnné kódu v pořadí jmen (`repertoire.variable_ids_of("lexical")`).
fn lexical_variables(world: &World, group: GroupId) -> Arc<Vec<VariableId>> {
    let code = world.groups.main_code(group);
    code.phonology
        .grammar
        .cache
        .get_or("lexical-variables", world.variables.len() as u64, || {
            let _t = crate::timing::scope("views/lexical-variables");
            code.repertoire
                .variable_ids_by_name(&world.registry.variables)
                .into_iter()
                .filter(|v| world.variables.kind.get(v.index()) == Some(&VariableKind::Lexical))
                .collect()
        })
}

/// Pojem lexikální proměnné.
fn concept_of(world: &World, site: VariableId) -> ConceptId {
    world.variables.concept[site.index()]
}

fn concept_name(world: &World, concept: ConceptId) -> &str {
    world.registry.concepts.name(concept.0)
}

fn origin(kind: &str, ctx: &InnovationContext, parent: VariantId) -> Origin {
    Origin {
        change: Some(kind.to_owned()),
        tick: ctx.tick,
        year: ctx.year,
        group: ctx.group,
        parent,
    }
}

/// Přitažlivost je čistá funkce semínka a jména varianty, takže je stejná ve všech
/// skupinách, které tutéž variantu vymyslí (`with_appeal`). Varianta, která ji už nese
/// (svět bez tvarů, výpůjčka přinášející přitažlivost zdroje), zůstane, jak je.
fn with_appeal(world: &World, mut variant: NewVariant) -> NewVariant {
    let sd = world.params.lexical_appeal_sd;
    if sd <= 0.0 || world.table.is_none() {
        return variant;
    }
    if let Payload::Lexical { appeal, .. } = &mut variant.payload {
        if *appeal == 0.0 {
            *appeal = Stream::new(
                world.seed as u64,
                &[Part::Str("lexical-appeal"), Part::Str(&variant.name)],
            )
            .normal(0.0, sd);
        }
    }
    variant
}

/// Kořeny, které kód užívá pro své pojmy, v pořadí jmen, a jejich tvary.
fn roots_with_forms(world: &World, group: GroupId) -> Vec<Vec<i32>> {
    let dominant = &world.groups.main_code(group).phonology.dominant;
    let mut roots: Vec<MorphemeId> = dominant.iter().copied().filter(|r| !r.is_none()).collect();
    roots.sort_by(|a, b| {
        world
            .registry
            .morphemes
            .name(a.0)
            .cmp(world.registry.morphemes.name(b.0))
    });
    roots.dedup();
    roots
        .into_iter()
        .map(|root| world.form_of(group, root).to_vec())
        .collect()
}

/// Nový kořen ze slabik, které jazyk užívá, a délky běžného slova (`protoforms.coin`).
///
/// Vezme kostru (pořadí souhlásek a samohlásek) náhodného existujícího slova a naplní ji
/// hláskami podle jejich četnosti v jazyce. `None`, když se nepodaří vyhnout homofonu.
pub fn coin(world: &World, group: GroupId, rng: &mut Stream) -> Option<Vec<i32>> {
    let table = world.table.as_ref()?;
    let forms = roots_with_forms(world, group);
    if forms.is_empty() {
        return None;
    }
    let (mut vowels, mut consonants) = (Vec::new(), Vec::new());
    for &segment in forms.iter().flatten() {
        if table.is_vowel(segment) {
            vowels.push(segment);
        } else {
            consonants.push(segment);
        }
    }
    if vowels.is_empty() || consonants.is_empty() {
        return None;
    }
    for _ in 0..12 {
        let skeleton = &forms[rng.integers(forms.len() as u64) as usize];
        let candidate: Vec<i32> = skeleton
            .iter()
            .map(|&segment| {
                if table.is_vowel(segment) {
                    vowels[rng.integers(vowels.len() as u64) as usize]
                } else {
                    consonants[rng.integers(consonants.len() as u64) as usize]
                }
            })
            .collect();
        if !forms.contains(&candidate) {
            return Some(candidate);
        }
    }
    None
}

/// Zaregistruje kořen nového slova; frekvenci a třídu má podle pojmu (`_new_root`).
#[allow(clippy::too_many_arguments)]
fn new_root(
    world: &mut World,
    ctx: &InnovationContext,
    site: VariableId,
    form: &[i32],
    kind: &str,
    parts: &[Part<'_>],
    sources: Vec<String>,
    base: Option<MorphemeId>,
) -> MorphemeId {
    let concept = concept_of(world, site);
    let mut all = Vec::with_capacity(parts.len() + 1);
    all.push(Part::Str(kind));
    all.extend_from_slice(parts);
    let name = stable_id("morpheme", &all);
    let meaning = concept_name(world, concept).to_owned();
    let form_id = world.bank.id_of(form);
    let frequency = world.concept_frequency(concept);
    let word_class = world.concepts.word_class[concept.index()];
    let language = world.groups.main_code(ctx.group).language;
    let id = world.registry.morpheme(&name);
    world.morphemes.store(
        id,
        MorphemeInit {
            meaning,
            form: form_id,
            frequency,
            kind: MorphemeKind::Root,
            origin_group: ctx.group,
            origin_tick: ctx.tick,
            word_class,
            lexeme: MorphemeId::NONE,
            cell: crate::ids::CellId::NONE,
            exponent: MorphemeId::NONE,
            boundary: -1,
            language,
            meta: MorphemeMeta {
                etymology: Some(kind.to_owned()),
                sources,
                base,
                meaning: String::new(),
            },
        },
    );
    id
}

fn lexical(morpheme: MorphemeId, origin: &str, lexeme: String) -> Payload {
    Payload::Lexical {
        lexeme,
        morpheme,
        origin: origin.to_owned(),
        appeal: 0.0,
    }
}

// --- expresivní tvoření ------------------------------------------------------------------

/// Nový kořen pro existující pojem. Ve světě bez hláskových tvarů zastupuje všechny cesty
/// vzniku slova a jeho výhodu nese náhodná přitažlivost; s tvary je to expresivní tvoření:
/// kořen ze slabik jazyka, vzácný a bez náhodné výhody.
pub struct LexicalCoinage;

impl LexicalCoinage {
    fn scale(world: &World) -> f64 {
        if world.semantics.is_some() {
            EXPRESSIVE_SHARE
        } else {
            1.0
        }
    }
}

impl Change for LexicalCoinage {
    fn kind(&self) -> &'static str {
        "lexical_coinage"
    }

    fn target(&self) -> VariableKind {
        VariableKind::Lexical
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &COINAGE_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        Sites {
            sites: lexical_variables(world, ctx.group).to_vec(),
            weights: None,
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        let count = lexical_variables(world, ctx.group).len();
        if count == 0 {
            return 0.0;
        }
        COINAGE_RATE * count as f64 * Self::scale(world)
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        index: usize,
    ) -> Option<NewVariant> {
        let group_name = world.group_name(ctx.group).to_owned();
        let code_name = world.groups.main_code(ctx.group).id.clone();
        let site_name = world.registry.variables.name(site.0).to_owned();
        let parts = [
            Part::Str(&group_name),
            Part::Str(&code_name),
            Part::Str(&site_name),
            Part::Uint(u64::from(ctx.tick)),
            Part::Uint(index as u64),
        ];
        let mut lexeme_parts = vec![Part::Str(self.kind())];
        lexeme_parts.extend_from_slice(&parts);
        let lexeme = stable_id("lexeme", &lexeme_parts);
        let payload = if world.table.is_none() {
            Payload::Lexical {
                lexeme,
                morpheme: MorphemeId::NONE,
                origin: String::new(),
                appeal: rng.normal(APPEAL_MEAN, APPEAL_SD),
            }
        } else {
            let form = coin(world, ctx.group, rng)?;
            let morpheme = new_root(
                world,
                ctx,
                site,
                &form,
                self.kind(),
                &parts,
                Vec::new(),
                None,
            );
            Payload::Lexical {
                lexeme,
                morpheme,
                origin: "coinage".into(),
                appeal: 0.0,
            }
        };
        let mut name_parts = vec![Part::Str(self.kind())];
        name_parts.extend_from_slice(&parts);
        let name = stable_id("variant", &name_parts);
        Some(with_appeal(
            world,
            NewVariant {
                name,
                variable: site,
                payload,
                origin: origin(self.kind(), ctx, VariantId::NONE),
            },
        ))
    }
}

// --- sémantické změny --------------------------------------------------------------------

/// Druh změny řízené grafem pojmů (pořadí je kanonické pořadí registru).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Semantic {
    Shift,
    Conversion,
    Derivation,
    Compounding,
    Taboo,
    Contamination,
    BackFormation,
}

/// Doložená cesta k novému slovu pojmu: váha, kořeny a pojmy, ze kterých slovo vzniká.
#[derive(Clone, Debug)]
struct Path {
    weight: f64,
    root: Option<MorphemeId>,
    other: Option<MorphemeId>,
    from: Vec<ConceptId>,
}

/// Místa semantické změny kódu: pojmy s cestou a jejich míry.
#[derive(Debug, Default)]
struct View {
    sites: Vec<VariableId>,
    rates: Vec<f64>,
    total: f64,
}

pub struct SemanticChange {
    which: Semantic,
}

impl SemanticChange {
    pub fn new(which: Semantic) -> SemanticChange {
        SemanticChange { which }
    }

    fn base_rate(&self) -> f64 {
        match self.which {
            Semantic::Shift => 4e-4,
            Semantic::Conversion => 1.5e-4,
            Semantic::Derivation => 4e-4,
            Semantic::Compounding => 3e-4,
            Semantic::Taboo => 1e-3,
            Semantic::Contamination => 2e-5,
            Semantic::BackFormation => 5e-5,
        }
    }

    fn enabled(world: &World) -> bool {
        world.semantics.is_some() && world.table.is_some()
    }

    /// Cesty k novému slovu pojmu (`options`).
    fn paths(&self, world: &World, group: GroupId, concept: ConceptId) -> Vec<Path> {
        let Some(graph) = world.semantics.as_deref() else {
            return Vec::new();
        };
        let class_of = |c: ConceptId| world.concepts.word_class.get(c.index()).copied();
        let compatible = |a: ConceptId, b: ConceptId| class_of(a) == class_of(b);
        let current = dominant_root(world, group, concept);
        let mut found = Vec::new();
        match self.which {
            Semantic::Shift => {
                for relation in graph.into(concept) {
                    let source = dominant_root(world, group, relation.source);
                    let Some(root) = source else { continue };
                    if Some(root) == current || !compatible(relation.source, concept) {
                        continue;
                    }
                    let weight = relation.shift_weight();
                    if weight > 0.0 {
                        found.push(Path {
                            weight,
                            root: Some(root),
                            other: None,
                            from: vec![relation.source],
                        });
                    }
                }
            }
            Semantic::Conversion => {
                for relation in graph.into(concept) {
                    let Some(root) = dominant_root(world, group, relation.source) else {
                        continue;
                    };
                    if compatible(relation.source, concept) {
                        continue;
                    }
                    if relation.polysemy >= 1 {
                        found.push(Path {
                            weight: f64::from(relation.polysemy).ln_1p(),
                            root: Some(root),
                            other: None,
                            from: vec![relation.source],
                        });
                    }
                }
            }
            Semantic::Derivation => {
                if world.derivational_suffix.is_empty() {
                    return found;
                }
                for relation in graph.into(concept) {
                    let Some(root) = dominant_root(world, group, relation.source) else {
                        continue;
                    };
                    let weight = relation.derivation_weight();
                    if weight > 0.0 {
                        found.push(Path {
                            weight,
                            root: Some(root),
                            other: None,
                            from: vec![relation.source],
                        });
                    }
                }
            }
            Semantic::Compounding => {
                for &(left, right) in graph.compounds_of(concept) {
                    let (first, second) = (
                        dominant_root(world, group, left),
                        dominant_root(world, group, right),
                    );
                    if let (Some(first), Some(second)) = (first, second) {
                        found.push(Path {
                            weight: 1.0,
                            root: Some(first),
                            other: Some(second),
                            from: vec![left, right],
                        });
                    }
                }
            }
            Semantic::Taboo => {
                if !world.groups.taboo[group.index()].contains(&concept) {
                    return found;
                }
                for relation in graph.into(concept) {
                    let source = dominant_root(world, group, relation.source);
                    if let Some(root) = source {
                        if Some(root) != current {
                            found.push(Path {
                                weight: 1.0,
                                root: Some(root),
                                other: None,
                                from: vec![relation.source],
                            });
                        }
                    }
                }
                if found.is_empty() {
                    found.push(Path {
                        weight: 1.0,
                        root: None,
                        other: None,
                        from: Vec::new(),
                    });
                }
            }
            Semantic::Contamination => {
                let Some(current) = current else {
                    return found;
                };
                for relation in graph.into(concept) {
                    let other = dominant_root(world, group, relation.source);
                    if let Some(other) = other {
                        if other != current && relation.colexification >= 20 {
                            found.push(Path {
                                weight: 1.0,
                                root: Some(current),
                                other: Some(other),
                                from: vec![relation.source],
                            });
                        }
                    }
                }
            }
            Semantic::BackFormation => {
                let derived = derivations(world, group);
                let held = current;
                if let Some(list) = derived.get(concept.index()) {
                    for &(other, root) in list {
                        let base = world.morphemes.meta[root.index()].base;
                        if other != concept && held != base {
                            found.push(Path {
                                weight: 1.0,
                                root: Some(root),
                                other: None,
                                from: vec![other],
                            });
                        }
                    }
                }
            }
        }
        found
    }

    /// Slot druhu v průběžném pohledu měr.
    fn slot(&self) -> usize {
        Semantic::ALL
            .iter()
            .position(|&w| w == self.which)
            .expect("druh sémantické změny")
    }

    /// Míra změny pojmu: základní míra krát součet vah cest; `None` bez cesty.
    fn rate_of(&self, world: &World, group: GroupId, concept: ConceptId) -> Option<f64> {
        let paths = self.paths(world, group, concept);
        (!paths.is_empty()).then(|| self.base_rate() * paths.iter().map(|p| p.weight).sum::<f64>())
    }

    /// Místa změny z měr pojmů (průběžný pohled) nebo, když není postavený, z cest od nuly.
    fn build_view(&self, world: &World, group: GroupId, rates: Option<&[Option<f64>]>) -> View {
        let mut view = View::default();
        if !Self::enabled(world) {
            return view;
        }
        for &site in lexical_variables(world, group).iter() {
            let concept = concept_of(world, site);
            let rate = match rates {
                Some(held) => held.get(concept.index()).copied().flatten(),
                None => self.rate_of(world, group, concept),
            };
            if let Some(rate) = rate {
                view.sites.push(site);
                view.rates.push(rate);
            }
        }
        view.total = view.rates.iter().sum();
        view
    }

    fn view(&self, world: &World, group: GroupId) -> Arc<View> {
        let code = world.groups.main_code(group);
        let held = &code.phonology.grammar.rates;
        if !held.built {
            return Arc::new(self.build_view(world, group, None));
        }
        let slot = self.slot();
        code.phonology
            .grammar
            .cache
            .get_or(self.kind(), held.versions[slot], || {
                self.build_view(world, group, Some(&held.rates[slot]))
            })
    }
}

impl Semantic {
    const ALL: [Semantic; SEMANTIC_KINDS] = [
        Semantic::Shift,
        Semantic::Conversion,
        Semantic::Derivation,
        Semantic::Compounding,
        Semantic::Taboo,
        Semantic::Contamination,
        Semantic::BackFormation,
    ];
}

/// Míry všech druhů změn pro všechny pojmy kódu, od nuly.
fn fresh_rates(world: &World, group: GroupId) -> SemanticRates {
    let size = world.registry.concepts.len();
    let mut rates = SemanticRates {
        built: true,
        concepts: size,
        rates: vec![vec![None; size]; SEMANTIC_KINDS],
        versions: [0; SEMANTIC_KINDS],
    };
    if SemanticChange::enabled(world) {
        for (slot, which) in Semantic::ALL.into_iter().enumerate() {
            let change = SemanticChange::new(which);
            for at in 0..size {
                rates.rates[slot][at] = change.rate_of(world, group, ConceptId::new(at));
            }
        }
    }
    rates
}

/// Postaví míry sémantických změn kódu od nuly.
pub fn build_rates(world: &mut World, group: GroupId) {
    let rates = fresh_rates(world, group);
    let state = &mut world.groups.main_code_mut(group).phonology.grammar;
    state.rates = rates;
    state.cache.clear();
}

/// Pojmy, jejichž cesty závisí na dominantním kořeni pojmu (ten, do kterého vedou vztahy z něj,
/// a složeniny, které ho obsahují); graf je neměnný, takže se staví jednou za svět.
fn dependents(world: &World) -> Arc<Vec<Vec<ConceptId>>> {
    world.grammar.cache.get_or("sem-dependents", 0, || {
        let size = world.registry.concepts.len();
        let mut list: Vec<Vec<ConceptId>> = vec![Vec::new(); size];
        if let Some(graph) = world.semantics.as_deref() {
            for relation in &graph.relations {
                if let Some(entry) = list.get_mut(relation.source.index()) {
                    entry.push(relation.target);
                }
            }
            for at in 0..size {
                for &(left, right) in graph.compounds_of(ConceptId::new(at)) {
                    for part in [left, right] {
                        if let Some(entry) = list.get_mut(part.index()) {
                            entry.push(ConceptId::new(at));
                        }
                    }
                }
            }
        }
        list
    })
}

/// Dominantní kořen pojmu se změnil: přepočítají se míry jen pojmů, kterých se to týká.
pub fn update_rates(
    world: &mut World,
    group: GroupId,
    concept: ConceptId,
    old: MorphemeId,
    new: MorphemeId,
) {
    let mut rates = std::mem::take(&mut world.groups.main_code_mut(group).phonology.grammar.rates);
    if !rates.built || rates.concepts != world.registry.concepts.len() {
        rates = fresh_rates(world, group);
        world
            .groups
            .main_code(group)
            .phonology
            .grammar
            .cache
            .clear();
    } else if SemanticChange::enabled(world) {
        let mut affected: Vec<ConceptId> = vec![concept];
        affected.extend(dependents(world).get(concept.index()).into_iter().flatten());
        for root in [old, new] {
            if !root.is_none() {
                if let Some(base) = crate::views::derivation_base(world, root) {
                    affected.push(ConceptId::new(base));
                }
            }
        }
        affected.sort();
        affected.dedup();
        for (slot, which) in Semantic::ALL.into_iter().enumerate() {
            let change = SemanticChange::new(which);
            for &at in &affected {
                let found = change.rate_of(world, group, at);
                let held = &mut rates.rates[slot][at.index()];
                if held.map(f64::to_bits) != found.map(f64::to_bits) {
                    *held = found;
                    rates.versions[slot] += 1;
                }
            }
        }
    }
    world.groups.main_code_mut(group).phonology.grammar.rates = rates;
}

/// Porovná míry s výpočtem od nuly.
pub fn verify_rates(world: &World, group: GroupId) -> Result<(), String> {
    let held = &world.groups.main_code(group).phonology.grammar.rates;
    if !held.built {
        return Err("míry sémantických změn nejsou postavené".into());
    }
    let fresh = fresh_rates(world, group);
    for slot in 0..SEMANTIC_KINDS {
        let same = held.rates[slot].len() == fresh.rates[slot].len()
            && held.rates[slot]
                .iter()
                .zip(&fresh.rates[slot])
                .all(|(a, b)| a.map(f64::to_bits) == b.map(f64::to_bits));
        if !same {
            return Err(format!(
                "{}: míry sémantické změny {slot} se liší od výpočtu od nuly",
                world.group_name(group)
            ));
        }
    }
    Ok(())
}

/// Základní pojem → (pojem, kořen) odvozenin z něj, seřazeno podle jména pojmu
/// (`_derivations`); pole podle čísla základního pojmu. Udržuje se průběžně
/// ([`crate::views::DominantIndex`]).
fn derivations(
    world: &World,
    group: GroupId,
) -> std::borrow::Cow<'_, [Vec<(ConceptId, MorphemeId)>]> {
    let index = &world.groups.main_code(group).phonology.grammar.dominant;
    if index.is_built() {
        std::borrow::Cow::Borrowed(index.derived())
    } else {
        std::borrow::Cow::Owned(
            crate::views::DominantIndex::build(world, group)
                .derived()
                .to_vec(),
        )
    }
}

impl Change for SemanticChange {
    fn kind(&self) -> &'static str {
        match self.which {
            Semantic::Shift => "semantic_shift",
            Semantic::Conversion => "conversion",
            Semantic::Derivation => "derivation",
            Semantic::Compounding => "compounding",
            Semantic::Taboo => "taboo_replacement",
            Semantic::Contamination => "contamination",
            Semantic::BackFormation => "back_formation",
        }
    }

    fn target(&self) -> VariableKind {
        VariableKind::Lexical
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &LEXICAL_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        if !Self::enabled(world) {
            return Sites::default();
        }
        let view = self.view(world, ctx.group);
        if view.sites.is_empty() || view.total <= 0.0 {
            return Sites::default();
        }
        Sites {
            sites: view.sites.clone(),
            weights: Some(view.rates.iter().map(|r| r / view.total).collect()),
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        if !Self::enabled(world) {
            return 0.0;
        }
        self.view(world, ctx.group).total
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        index: usize,
    ) -> Option<NewVariant> {
        let concept = concept_of(world, site);
        let paths = self.paths(world, ctx.group, concept);
        if paths.is_empty() {
            return None;
        }
        let weights: Vec<f64> = paths.iter().map(|p| p.weight).collect();
        let path = paths[rng.choice(&weights).ok()?].clone();
        let group = ctx.group;
        let group_name = world.group_name(group).to_owned();
        let site_name = world.registry.variables.name(site.0).to_owned();
        let parts = [
            Part::Str(&group_name),
            Part::Str(&site_name),
            Part::Uint(u64::from(ctx.tick)),
            Part::Uint(index as u64),
        ];
        let kind = self.kind();
        let names = |world: &World, from: &[ConceptId]| -> Vec<String> {
            from.iter()
                .map(|&c| concept_name(world, c).to_owned())
                .collect()
        };
        let root_name = |world: &World, root: Option<MorphemeId>| -> String {
            root.map(|r| world.registry.morphemes.name(r.0).to_owned())
                .unwrap_or_default()
        };
        let (payload, variant_name) = match self.which {
            Semantic::Shift => {
                let root = path.root?;
                let name = root_name(world, path.root);
                // Stejný posun téhož kořene ve dvou skupinách je tatáž varianta.
                let lexeme = stable_id(
                    "lexeme",
                    &[Part::Str("shift"), Part::Str(&name), Part::Str(&site_name)],
                );
                let variant = stable_id(
                    "variant",
                    &[Part::Str(kind), Part::Str(&site_name), Part::Str(&name)],
                );
                (lexical(root, "shift", lexeme), variant)
            }
            Semantic::Conversion => {
                let form = world.form_of(group, path.root?).to_vec();
                let sources = names(world, &path.from);
                let morpheme = new_root(world, ctx, site, &form, kind, &parts, sources, None);
                (
                    lexical(morpheme, "conversion", String::new()),
                    plain_name(kind, &parts),
                )
            }
            Semantic::Derivation => {
                let root = path.root?;
                let mut form = world.form_of(group, root).to_vec();
                form.extend_from_slice(&world.derivational_suffix);
                let sources = names(world, &path.from);
                let morpheme = new_root(world, ctx, site, &form, kind, &parts, sources, Some(root));
                (
                    lexical(morpheme, "derivation", String::new()),
                    plain_name(kind, &parts),
                )
            }
            Semantic::Compounding => {
                let mut form = world.form_of(group, path.root?).to_vec();
                form.extend_from_slice(world.form_of(group, path.other?));
                if form.len() > MAX_COMPOUND {
                    return None; // příliš dlouhá složenina se v řeči neujme
                }
                let sources = names(world, &path.from);
                let morpheme = new_root(world, ctx, site, &form, kind, &parts, sources, None);
                (
                    lexical(morpheme, "compound", String::new()),
                    plain_name(kind, &parts),
                )
            }
            Semantic::Taboo => {
                let morpheme = match path.root {
                    Some(root) => root,
                    None => {
                        let form = coin(world, group, rng)?;
                        new_root(world, ctx, site, &form, kind, &parts, Vec::new(), None)
                    }
                };
                (
                    lexical(morpheme, "circumlocution", String::new()),
                    plain_name(kind, &parts),
                )
            }
            Semantic::Contamination => {
                let first = world.form_of(group, path.root?).to_vec();
                let second = world.form_of(group, path.other?).to_vec();
                let mut form = first[..first.len().div_ceil(2)].to_vec();
                form.extend_from_slice(&second[second.len() / 2..]);
                if form == first || form == second || form.len() < 2 {
                    return None;
                }
                let morpheme = new_root(world, ctx, site, &form, kind, &parts, Vec::new(), None);
                (
                    lexical(morpheme, "contamination", String::new()),
                    plain_name(kind, &parts),
                )
            }
            Semantic::BackFormation => {
                let form = world.form_of(group, path.root?).to_vec();
                let suffix = world.derivational_suffix.clone();
                if suffix.is_empty() || form.len() <= suffix.len() + 1 || !form.ends_with(&suffix) {
                    return None;
                }
                let stem = &form[..form.len() - suffix.len()];
                let morpheme = new_root(world, ctx, site, stem, kind, &parts, Vec::new(), None);
                (
                    lexical(morpheme, "back_formation", String::new()),
                    plain_name(kind, &parts),
                )
            }
        };
        Some(with_appeal(
            world,
            NewVariant {
                name: variant_name,
                variable: site,
                payload,
                origin: origin(kind, ctx, VariantId::NONE),
            },
        ))
    }
}

fn plain_name(kind: &str, parts: &[Part<'_>]) -> String {
    let mut all = vec![Part::Str(kind)];
    all.extend_from_slice(parts);
    stable_id("variant", &all)
}

// --- výpůjčky ----------------------------------------------------------------------------

/// Filtr výpůjček slova v kanálu (`contact.borrowing_factor`) podle rozhraní kontaktu R1d:
/// `0,5 × přenositelnost pojmu × váha domény v kanálu`. Normalizaci přenositelnosti (průměr přes
/// pojmy z dat) si svět pamatuje podle síly půjčitelnosti.
fn borrowing_factor(world: &World, concept: ConceptId, channel: usize) -> f64 {
    let strength = world.params.borrowability_strength;
    let normalizer = if strength == 0.0 {
        1.0
    } else {
        *world
            .grammar
            .cache
            .get_or("borrowing-normalizer", strength.to_bits(), || {
                contact::normalizer(strength)
            })
    };
    let mut factor = contact::borrowing_kind(VariableKind::Lexical)
        * contact::transfer(world, concept, normalizer);
    let weight = contact::domain_weight(
        &world.params,
        channel,
        world.concepts.domain[concept.index()],
    );
    if weight != 1.0 {
        factor *= weight;
    }
    factor
}

/// Sousedé jiného jazyka a jejich podíl na vstupu skupiny: (váha, skupina) podle jména.
///
/// Váha je otevřenost × síla vazby × prestiž dárce / součet přes všechny sousedy (řádek
/// matice míšení pro `alpha` 1). Psané kódy se nepůjčují.
pub fn donors(world: &World, group: GroupId) -> Vec<(f64, GroupId)> {
    if world.table.is_none() || world.groups.written[group.index()] {
        return Vec::new();
    }
    let mut links: Vec<(f64, GroupId)> = world
        .links
        .from(group)
        .filter(|(target, _)| {
            world.groups.alive[target.index()] && !world.groups.written[target.index()]
        })
        .map(|(target, link)| {
            (
                link.strength * world.groups.prestige[target.index()],
                target,
            )
        })
        .collect();
    links.sort_by(|a, b| {
        world
            .registry
            .groups
            .name(a.1 .0)
            .cmp(world.registry.groups.name(b.1 .0))
    });
    let total: f64 = links.iter().map(|l| l.0).sum();
    if total <= 0.0 {
        return Vec::new();
    }
    let language = world.groups.main_code(group).language;
    let openness = world.groups.openness[group.index()];
    links
        .into_iter()
        .filter(|&(weight, target)| {
            weight > 0.0 && world.groups.main_code(target).language != language
        })
        .map(|(weight, target)| (openness * weight / total, target))
        .collect()
}

/// Kanály, kterými slova od dárce přicházejí, a jejich podíl (součet 1): rozdělení vazby
/// dává `contact::channel_split`, tady se vynechají kanály s nulovým podílem.
fn donor_channels(
    world: &World,
    group: GroupId,
    donor: GroupId,
    distinct: &[usize],
) -> Vec<(usize, f64)> {
    let split = contact::channel_split(world, group, donor, distinct);
    [
        (contact::NEIGHBOR, split.neighbor),
        (contact::ELITE, split.elite),
        (contact::TRADE, split.trade),
    ]
    .into_iter()
    .filter(|&(_, share)| share > 0.0)
    .collect()
}

/// Podíl vstupu skupiny od cizích dárců podle kanálů, seřazeno podle názvu kanálu.
fn channel_exposures(
    world: &World,
    group: GroupId,
    donors: &[(f64, GroupId)],
    distinct: &[usize],
) -> Vec<(usize, f64)> {
    let mut totals: Vec<(usize, f64)> = Vec::new();
    for &(weight, donor) in donors {
        for (channel, share) in donor_channels(world, group, donor, distinct) {
            match totals.iter_mut().find(|t| t.0 == channel) {
                Some(found) => found.1 += weight * share,
                None => totals.push((channel, weight * share)),
            }
        }
    }
    totals.sort_by(|a, b| CHANNELS[a.0].cmp(CHANNELS[b.0]));
    totals
}

/// Míry míst výpůjček skupiny (pro lexikální proměnné v pořadí jmen).
fn borrowing_rates(world: &World, group: GroupId, sites: &[VariableId]) -> Vec<f64> {
    let found = donors(world, group);
    if found.is_empty() {
        return Vec::new();
    }
    let distinct = contact::distinct_channels(&world.params);
    let channels: Vec<(usize, f64)> = if distinct.is_empty() {
        vec![(contact::NEIGHBOR, found.iter().map(|d| d.0).sum())]
    } else {
        channel_exposures(world, group, &found, &distinct)
    };
    sites
        .iter()
        .map(|&site| {
            let concept = concept_of(world, site);
            let sum: f64 = channels
                .iter()
                .map(|&(channel, exposure)| exposure * borrowing_factor(world, concept, channel))
                .sum();
            BORROWING_RATE * sum
        })
        .collect()
}

/// Výpůjčka: skupina převezme slovo sousedního jazyka pro pojem, který už má.
///
/// Vazba mezi jazyky propouští cizí varianty i bez této změny, jenže jako zděděné slovo
/// dárce bez sociálního ocenění inovace, takže se bez cizí elity neprosadí. Slovo ve
/// skutečnosti přinese dvojjazyčný mluvčí a dál se šíří jako každá inovace (Weinreich 1953,
/// Thomason a Kaufman 1988). Míra je úměrná podílu vstupu z cizího jazyka a přenositelnosti
/// slova; dárce se vybere podle téže váhy.
pub struct LexicalBorrowing;

impl Change for LexicalBorrowing {
    fn kind(&self) -> &'static str {
        "lexical_borrowing"
    }

    fn target(&self) -> VariableKind {
        VariableKind::Lexical
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &LEXICAL_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        let sites = lexical_variables(world, ctx.group);
        let rates = borrowing_rates(world, ctx.group, &sites);
        let total: f64 = rates.iter().sum();
        if rates.is_empty() || total <= 0.0 {
            return Sites::default();
        }
        Sites {
            sites: sites.to_vec(),
            weights: Some(rates.iter().map(|r| r / total).collect()),
        }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        let sites = lexical_variables(world, ctx.group);
        borrowing_rates(world, ctx.group, &sites).iter().sum()
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        index: usize,
    ) -> Option<NewVariant> {
        let group = ctx.group;
        let found = donors(world, group);
        if found.is_empty() {
            return None;
        }
        let concept = concept_of(world, site);
        let distinct = contact::distinct_channels(&world.params);
        let weights: Vec<f64> = if distinct.is_empty() {
            found.iter().map(|d| d.0).collect()
        } else {
            // Dárce se vybírá podle toho, kolik slov pojmu jeho kanály propustí.
            found
                .iter()
                .map(|&(weight, donor)| {
                    weight
                        * donor_channels(world, group, donor, &distinct)
                            .iter()
                            .map(|&(channel, share)| {
                                share * borrowing_factor(world, concept, channel)
                            })
                            .sum::<f64>()
                })
                .collect()
        };
        if weights.iter().sum::<f64>() <= 0.0 {
            return None;
        }
        let donor = found[rng.choice(&weights).ok()?].1;
        let (source, _) = world.dominant(donor, site)?;
        let Payload::Lexical {
            lexeme,
            morpheme,
            appeal,
            ..
        } = world.variants.payload[source.index()].clone()
        else {
            return None;
        };
        let own_language = world.groups.main_code(group).language;
        if morpheme.is_none() || world.morphemes.language[morpheme.index()] == own_language {
            return None;
        }
        if dominant_root(world, group, concept) == Some(morpheme) {
            return None;
        }
        let group_name = world.group_name(group).to_owned();
        let code_name = world.groups.main_code(group).id.clone();
        let site_name = world.registry.variables.name(site.0).to_owned();
        let name = plain_name(
            self.kind(),
            &[
                Part::Str(&group_name),
                Part::Str(&code_name),
                Part::Str(&site_name),
                Part::Uint(u64::from(ctx.tick)),
                Part::Uint(index as u64),
            ],
        );
        Some(with_appeal(
            world,
            NewVariant {
                name,
                variable: site,
                payload: Payload::Lexical {
                    lexeme,
                    morpheme,
                    origin: "loan".into(),
                    appeal,
                },
                origin: origin(self.kind(), ctx, source),
            },
        ))
    }
}

/// Lexikální změny v kanonickém pořadí (před zvukovými změnami).
pub fn changes() -> Vec<Box<dyn Change>> {
    let mut all: Vec<Box<dyn Change>> = vec![Box::new(LexicalCoinage)];
    for which in [
        Semantic::Shift,
        Semantic::Conversion,
        Semantic::Derivation,
        Semantic::Compounding,
        Semantic::Taboo,
        Semantic::Contamination,
        Semantic::BackFormation,
    ] {
        all.push(Box::new(SemanticChange::new(which)));
    }
    all.push(Box::new(LexicalBorrowing));
    all
}

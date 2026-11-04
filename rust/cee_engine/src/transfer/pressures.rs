//! Tlaky na varianty (zrcadlo `cee.v2.pressures`): součet vážených tlaků každé buňky bloku
//! (proměnná × skupina × slot) ze stavu na začátku kroku.
//!
//! Plán tlaků každého druhu proměnné je pevný ([`plan`], zrcadlo `pressures_by_kind` pro
//! výchozí změny); váhy přepisuje `Parameters::pressure_weights`. Tlaky jsou sloupcové: čtou
//! sloupce variant (`state::transfer::VariantColumns`), tvary kódů a banku tvarů ze `World`,
//! žádné řetězce a hashovací mapy v buňkách. Stav kroku (vlastníci tvarů pro lexikální jasnost,
//! slabost buněk, dominantní konstrukce) se staví líně a jen pro skupiny a funkce, na které
//! se tlak ptá.
//!
//! Tlaky na zvukové procesy a analogické tvary (`articulation`, `clarity`, `functional_load`,
//! `dispersion`, `phonotactics`; `uniformity`, `conservation`, `teachability`,
//! `distinctiveness`) čtou hodnocení nad vzorky slov; počítá je [`crate::transfer::assess`].

use cee_core::pressures::id;
use cee_core::transmission::{hash_normal_mixed, splitmix64};

use crate::grammar::{Construction, GrammaticalFunction, Template};
use crate::ids::{ConceptId, MorphemeId, VariableId, VariantId};
use crate::model::pools::PoolBlock;
use crate::model::repertoire::{Payload, VariableKind};
use crate::rng::{stable_int, Part};
use crate::transfer::network::StepInputs;
use crate::world::World;

/// Rozpětí náhodného ocenění změny (`Actuation.spread`).
const ACTUATION_SPREAD: f64 = 0.25;
/// Kolik ticků trvá epocha ocenění změn (`Actuation.epoch_ticks`, 8 generací).
const EPOCH_TICKS: u32 = 8;
/// Síla normy školy (`Norm.strength`).
const NORM_STRENGTH: f64 = 0.3;
/// Kolik generací musí být slovo v užívání, než ho tabu opotřebuje (`TABOO_GENERATIONS`).
const TABOO_GENERATIONS: f64 = 10.0;
const ERODED: f64 = -0.5;
const HOMOPHONE: f64 = -0.4;

/// Jména tlaků podle čísla (`cee_core::pressures::id`), pro `pressure_weights`.
pub const NAMES: [&str; id::COUNT] = [
    "actuation",
    "ambiguity",
    "appeal",
    "articulation",
    "clarity",
    "conformity",
    "conservation",
    "dispersion",
    "distinctiveness",
    "economy",
    "entrenchment",
    "expressivity",
    "functional_load",
    "fusion",
    "lexical_actuation",
    "lexical_clarity",
    "learnability",
    "motivation",
    "norm",
    "phonotactics",
    "taboo",
    "teachability",
    "uniformity",
];

/// Tlaky každého druhu proměnné: (číslo tlaku, váha), v pořadí sčítání.
pub type Plan = [Vec<(u8, f64)>; 5];

/// Číslo druhu proměnné v `cee_core::pressures` (pořadí `VARIABLE_KINDS`).
pub fn kind_number(kind: VariableKind) -> usize {
    match kind {
        VariableKind::Process => 0,
        VariableKind::Lexical => 1,
        VariableKind::Form => 2,
        VariableKind::Construction => 3,
        VariableKind::Prosody => 4,
    }
}

/// Plán tlaků podle výchozích změn (`pressures_by_kind`): sloučené tlaky změn téhož cíle
/// (nejvyšší váha), `Norm` na všech druzích, váhy přepsané z `pressure_weights`.
pub fn plan(params: &crate::parameters::Parameters) -> Result<Plan, String> {
    let table: [&[(u8, f64)]; 5] = [
        // process
        &[
            (id::ACTUATION, 1.0),
            (id::ARTICULATION, 1.0),
            (id::CLARITY, 0.6),
            (id::CONFORMITY, 0.1),
            (id::DISPERSION, 0.5),
            (id::FUNCTIONAL_LOAD, 1.0),
            (id::PHONOTACTICS, 0.4),
        ],
        // lexical
        &[
            (id::APPEAL, 1.0),
            (id::CONFORMITY, 0.1),
            (id::ENTRENCHMENT, 1.0),
            (id::LEXICAL_ACTUATION, 1.0),
            (id::LEXICAL_CLARITY, 1.0),
            (id::MOTIVATION, 1.0),
            (id::TABOO, 1.0),
        ],
        // form
        &[
            (id::ACTUATION, 1.0),
            (id::CONFORMITY, 0.1),
            (id::CONSERVATION, 1.0),
            (id::DISTINCTIVENESS, 1.0),
            (id::TEACHABILITY, 1.0),
            (id::UNIFORMITY, 1.0),
        ],
        // construction
        &[
            (id::ACTUATION, 1.0),
            (id::AMBIGUITY, 1.0),
            (id::CONFORMITY, 0.1),
            (id::ECONOMY, 1.0),
            (id::EXPRESSIVITY, 1.0),
            (id::FUSION, 1.0),
            (id::LEARNABILITY, 1.0),
        ],
        // prosody
        &[(id::ACTUATION, 1.0), (id::CONFORMITY, 0.1)],
    ];
    for name in params.pressure_weights.keys() {
        if !NAMES.contains(&name.as_str()) {
            return Err(format!(
                "Neznámé tlaky v pressure_weights: [{name}]; známé jsou {NAMES:?}."
            ));
        }
    }
    let weight_of = |pressure: u8, weight: f64| {
        params
            .pressure_weights
            .get(NAMES[pressure as usize])
            .copied()
            .unwrap_or(weight)
    };
    let mut plan: Plan = Default::default();
    for (kind, items) in table.iter().enumerate() {
        for &(pressure, weight) in *items {
            // Slovní ocenění změny zastupuje obecné; lexikální druh obecné nemá.
            if kind == 1 && pressure == id::ACTUATION {
                continue;
            }
            plan[kind].push((pressure, weight_of(pressure, weight)));
        }
        plan[kind].push((id::NORM, weight_of(id::NORM, 1.0)));
    }
    Ok(plan)
}

/// Katalog gramatických funkcí s odvozenými čísly pro tlaky na konstrukce.
struct Catalog {
    functions: Vec<GrammaticalFunction>,
    /// Konstrukční proměnná funkce, je-li ve světě.
    variable: Vec<Option<VariableId>>,
    /// Funkce, které daná funkce zastupuje (`compensates`), jako čísla v katalogu.
    compensates: Vec<Vec<usize>>,
    /// Funkce, které zastupují danou funkci.
    compensated_by: Vec<Vec<usize>>,
    word_class: Vec<Option<crate::ids::WordClassId>>,
    cell: Vec<Option<crate::ids::CellId>>,
}

impl Catalog {
    fn new(world: &World) -> Result<Catalog, String> {
        let functions = world.grammar_catalog()?;
        let index = |name: &str| functions.iter().position(|f| f.id == name);
        let compensates: Vec<Vec<usize>> = functions
            .iter()
            .map(|f| f.compensates.iter().filter_map(|n| index(n)).collect())
            .collect();
        let mut compensated_by = vec![Vec::new(); functions.len()];
        for (at, list) in compensates.iter().enumerate() {
            for &target in list {
                compensated_by[target].push(at);
            }
        }
        let variable = functions
            .iter()
            .map(|f| {
                world
                    .registry
                    .variables
                    .get(&crate::model::repertoire::variable_name(
                        VariableKind::Construction,
                        &f.id,
                    ))
                    .filter(|&number| (number as usize) < world.variables.len())
                    .map(VariableId)
            })
            .collect();
        let word_class = functions
            .iter()
            .map(|f| f.word_class().and_then(|n| world.registry.word_class_of(n)))
            .collect();
        let cell = functions
            .iter()
            .map(|f| {
                f.cell
                    .as_deref()
                    .and_then(|c| world.registry.cells.get(c))
                    .map(crate::ids::CellId)
            })
            .collect();
        Ok(Catalog {
            functions,
            variable,
            compensates,
            compensated_by,
            word_class,
            cell,
        })
    }

    fn index(&self, function: &str) -> Option<usize> {
        self.functions.iter().position(|f| f.id == function)
    }
}

/// Stav tlaků jednoho kroku: kontext světa a líně stavěné pomocné tabulky.
pub struct Pressures<'a> {
    world: &'a World,
    inputs: &'a StepInputs,
    plan: &'a Plan,
    /// Klíče ocenění změn skupin v epoše (podle sloupce osy).
    actuation_keys: Vec<u64>,
    l2: Vec<f64>,
    any_l2: bool,
    any_school: bool,
    any_taboo: bool,
    catalog: Catalog,
    /// Vlastníci tvarů podle sloupce osy: (tvar, pojem, kořen) seřazení; staví se líně.
    owners: Vec<Option<Vec<(u32, u32, u32)>>>,
    /// Slabost buňky podle (sloupec, funkce); `NaN` = ještě nespočtená.
    weakness: Vec<f64>,
    /// Dominantní varianta konstrukční proměnné funkce podle (sloupec, funkce).
    dominant: Vec<Option<Option<VariantId>>>,
}

impl<'a> Pressures<'a> {
    pub fn new(
        world: &'a World,
        inputs: &'a StepInputs,
        plan: &'a Plan,
    ) -> Result<Pressures<'a>, String> {
        let groups = &world.groups;
        let epoch = i64::from(inputs.tick / EPOCH_TICKS);
        let actuation_keys = inputs
            .axis
            .iter()
            .map(|&g| {
                stable_int(&[
                    Part::Int(world.seed),
                    Part::Str("actuation"),
                    Part::Int(epoch),
                    Part::Str(world.group_name(g)),
                ])
            })
            .collect();
        let l2: Vec<f64> = inputs
            .axis
            .iter()
            .map(|&g| groups.main_code(g).l2_share)
            .collect();
        let catalog = Catalog::new(world)?;
        let columns = inputs.axis.len();
        let functions = catalog.functions.len();
        Ok(Pressures {
            world,
            inputs,
            plan,
            actuation_keys,
            any_l2: l2.iter().any(|&share| share != 0.0),
            l2,
            any_school: inputs
                .axis
                .iter()
                .any(|&g| groups.schooling[g.index()] > 0.0),
            any_taboo: inputs
                .axis
                .iter()
                .any(|&g| !groups.taboo[g.index()].is_empty()),
            catalog,
            owners: vec![None; columns],
            weakness: vec![f64::NAN; columns * functions],
            dominant: vec![None; columns * functions],
        })
    }

    /// Fitness řádků `[first, first + count)` bloku do `out` (`count × skupiny × sloty`,
    /// vynulované); `current` a `heard` mají týž tvar.
    pub fn fitness(
        &mut self,
        block: &PoolBlock,
        first: usize,
        count: usize,
        current: &[f64],
        heard: &[f64],
        out: &mut [f64],
    ) {
        let (groups, slots) = (self.inputs.axis.len(), block.capacity);
        let stride = groups * slots;
        for local in 0..count {
            let row = first + local;
            let variable = block.variables[row];
            let kind = self.world.variables.kind[variable.index()];
            let plan = self.plan;
            let cells = &mut out[local * stride..(local + 1) * stride];
            let now = &current[local * stride..(local + 1) * stride];
            let heard = &heard[local * stride..(local + 1) * stride];
            let variants = &block.slots[row];
            for &(pressure, weight) in &plan[kind_number(kind)] {
                if weight == 0.0 {
                    continue;
                }
                self.apply(
                    pressure, weight, variable, variants, now, heard, cells, groups, slots,
                );
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn apply(
        &mut self,
        pressure: u8,
        weight: f64,
        variable: VariableId,
        variants: &[VariantId],
        current: &[f64],
        heard: &[f64],
        cells: &mut [f64],
        groups: usize,
        slots: usize,
    ) {
        let world = self.world;
        let has_table = world.table.is_some();
        let columns = &world.transfer.derived.variants;
        match pressure {
            id::CONFORMITY => {
                for (cell, &share) in cells.iter_mut().zip(current) {
                    add(cell, weight * (2.0 * share - 1.0));
                }
            }
            id::APPEAL => {
                for (slot, &variant) in variants.iter().enumerate() {
                    if variant.is_none() {
                        continue;
                    }
                    let appeal = columns.appeal[variant.index()];
                    let term = weight * if appeal.is_nan() { 0.0 } else { appeal }.clamp(-1.0, 1.0);
                    for g in 0..groups {
                        add(&mut cells[g * slots + slot], term);
                    }
                }
            }
            id::ENTRENCHMENT if has_table => {
                let params = &world.params;
                let concept = world.variables.concept[variable.index()];
                let mut protection = params.entrenchment_strength
                    * if params.entrenchment_frequency_exponent == 1.0 {
                        world.concept_frequency(concept)
                    } else {
                        world
                            .concept_frequency(concept)
                            .powf(params.entrenchment_frequency_exponent)
                    };
                if params.entrenchment_base != 0.0 {
                    protection += params.entrenchment_base;
                }
                for g in 0..groups {
                    for (slot, &variant) in variants.iter().enumerate() {
                        if variant.is_none() || !columns.is_word(variant) {
                            continue;
                        }
                        if current[g * slots + slot] >= 0.5 {
                            add(&mut cells[g * slots + slot], weight * protection);
                        }
                    }
                }
            }
            id::MOTIVATION if has_table => {
                for (slot, &variant) in variants.iter().enumerate() {
                    if variant.is_none() {
                        continue;
                    }
                    let appeal = columns.appeal[variant.index()];
                    let term = weight
                        * (columns.motivation[variant.index()]
                            + if appeal.is_nan() { 0.0 } else { appeal });
                    for g in 0..groups {
                        add(&mut cells[g * slots + slot], term);
                    }
                }
            }
            id::ACTUATION | id::LEXICAL_ACTUATION => {
                let lexical = pressure == id::LEXICAL_ACTUATION;
                for (slot, &variant) in variants.iter().enumerate() {
                    if variant.is_none()
                        || !world.variants.innovation[variant.index()]
                        || (lexical && !columns.is_word(variant))
                    {
                        continue;
                    }
                    let mixed = splitmix64(columns.key[variant.index()]);
                    for g in 0..groups {
                        // Slot, který kohorta neslyší, výběr nečte (slyšený × exp(…) je nula).
                        if heard[g * slots + slot] <= 0.0 && current[g * slots + slot] <= 0.0 {
                            continue;
                        }
                        let noise = hash_normal_mixed(self.actuation_keys[g], mixed);
                        add(
                            &mut cells[g * slots + slot],
                            weight * (ACTUATION_SPREAD * noise).clamp(-1.0, 1.0),
                        );
                    }
                }
            }
            id::LEXICAL_CLARITY if has_table => {
                let concept = world.variables.concept[variable.index()];
                for g in 0..groups {
                    for (slot, &variant) in variants.iter().enumerate() {
                        if variant.is_none() || !columns.is_word(variant) {
                            continue;
                        }
                        let at = g * slots + slot;
                        if current[at] <= 0.0 && heard[at] <= 0.0 {
                            continue;
                        }
                        let morpheme = MorphemeId(columns.morpheme[variant.index()] as u32);
                        add(
                            &mut cells[at],
                            weight * self.lexical_clarity(g, morpheme, concept),
                        );
                    }
                }
            }
            id::TABOO if self.any_taboo => {
                let concept = world.variables.concept[variable.index()];
                for g in 0..groups {
                    let group = self.inputs.axis[g];
                    if !world.groups.taboo[group.index()].contains(&concept) {
                        continue;
                    }
                    let generation = world.groups.generation_years[group.index()] / 25.0;
                    for (slot, &variant) in variants.iter().enumerate() {
                        if variant.is_none()
                            || !matches!(
                                world.variants.payload[variant.index()],
                                Payload::Lexical { .. }
                            )
                        {
                            continue;
                        }
                        let origin = &world.variants.origin[variant.index()];
                        let age = if origin.change.is_some() {
                            f64::from(self.inputs.tick) - f64::from(origin.tick)
                        } else {
                            1e9
                        };
                        if age >= TABOO_GENERATIONS * generation {
                            add(&mut cells[g * slots + slot], weight * -0.6);
                        }
                    }
                }
            }
            id::NORM if self.any_school => {
                for g in 0..groups {
                    let group = self.inputs.axis[g];
                    let schooling = world.groups.schooling[group.index()];
                    let standard = world.groups.standard[group.index()];
                    if schooling <= 0.0 || standard.is_none() || !world.groups.contains(standard) {
                        continue;
                    }
                    let Some((codified, _)) = world.dominant(standard, variable) else {
                        continue;
                    };
                    let Some(slot) = variants.iter().position(|&v| v == codified) else {
                        continue;
                    };
                    if crate::transfer::seams::closed(world, group, variable) {
                        continue;
                    }
                    add(
                        &mut cells[g * slots + slot],
                        weight * (NORM_STRENGTH * schooling),
                    );
                }
            }
            id::AMBIGUITY | id::ECONOMY | id::EXPRESSIVITY | id::FUSION | id::LEARNABILITY => {
                self.construction(pressure, weight, variable, variants, cells, groups, slots)
            }
            _ => {}
        }
    }

    // --- lexikální jasnost ---------------------------------------------------------------

    /// Tvary dominantních kořenů skupiny: (tvar, pojem, kořen) seřazené (vlastníci tvarů).
    fn owners_of(&mut self, column: usize) -> &[(u32, u32, u32)] {
        if self.owners[column].is_none() {
            let world = self.world;
            let group = self.inputs.axis[column];
            let state = &world.groups.main_code(group).phonology;
            let mut list: Vec<(u32, u32, u32)> = Vec::new();
            for (concept, &root) in state.dominant.iter().enumerate() {
                if root.is_none() {
                    continue;
                }
                list.push((world.unit_of(group, root).form, concept as u32, root.0));
            }
            list.sort_unstable();
            self.owners[column] = Some(list);
        }
        self.owners[column].as_deref().unwrap_or(&[])
    }

    /// Skóre jasnosti dvojice (morfém, pojem) ve skupině: zkrácené slovo a homofon s nepříbuzným
    /// pojmem (`lexical_index.clarity_scores`).
    fn lexical_clarity(&mut self, column: usize, morpheme: MorphemeId, concept: ConceptId) -> f64 {
        let world = self.world;
        let group = self.inputs.axis[column];
        let form = world.unit_of(group, morpheme).form;
        let default = world.morphemes.form[morpheme.index()];
        let length = world.bank.form(form).len();
        let mut value = 0.0;
        if length <= 2 && length < world.bank.form(default).len() {
            value = ERODED;
        }
        let graph = world.semantics.clone();
        let owners = self.owners_of(column);
        let begin = owners.partition_point(|owner| owner.0 < form);
        for &(owner_form, owner_concept, owner_root) in &owners[begin..] {
            if owner_form != form {
                break;
            }
            if owner_root != morpheme.0
                && owner_concept != concept.0
                && !graph
                    .as_ref()
                    .is_some_and(|g| g.related(ConceptId(owner_concept), concept))
            {
                value += HOMOPHONE;
                break;
            }
        }
        value
    }

    // --- tlaky na konstrukce -------------------------------------------------------------

    fn dominant_construction(&mut self, column: usize, function: usize) -> Option<&Construction> {
        let slot = column * self.catalog.functions.len() + function;
        if self.dominant[slot].is_none() {
            let found = self.catalog.variable[function].and_then(|variable| {
                self.world
                    .dominant(self.inputs.axis[column], variable)
                    .map(|(variant, _)| variant)
            });
            self.dominant[slot] = Some(found);
        }
        let variant = self.dominant[slot].flatten()?;
        match &self.world.variants.payload[variant.index()] {
            Payload::Construction(c) => Some(c),
            _ => None,
        }
    }

    /// Nese konstrukce roli funkcí, které její funkce zastupuje (`syntax.carries_role`)?
    fn carries_role(&self, construction: &Construction) -> bool {
        match self.catalog.index(&construction.function) {
            Some(at) if self.catalog.functions[at].template == Template::Order => {
                construction.kind == "fixed"
            }
            _ => construction.kind != "zero",
        }
    }

    /// Podíl tvarů buňky, které splynuly s citačním tvarem (`syntax.weakness`); funkce bez
    /// buňky má 0, bez třídy slova 1.
    fn weakness(&mut self, column: usize, function: usize) -> f64 {
        let slot = column * self.catalog.functions.len() + function;
        if !self.weakness[slot].is_nan() {
            return self.weakness[slot];
        }
        let value = {
            let world = self.world;
            let group = self.inputs.axis[column];
            let entry = &self.catalog.functions[function];
            if entry.cell.is_none() {
                0.0
            } else if entry.word_class().is_none() {
                1.0
            } else {
                let (class, cell) = (
                    self.catalog.word_class[function],
                    self.catalog.cell[function],
                );
                let (mut merged, mut total) = (0_u32, 0_u32);
                if let (Some(class), Some(cell)) = (class, cell) {
                    let code = world.groups.main_code(group);
                    for unit in code.phonology.vocabulary.iter() {
                        let at = unit.index();
                        if world.morphemes.kind[at] != crate::model::lexicon::MorphemeKind::Word
                            || world.morphemes.word_class[at] != class
                            || world.morphemes.cell[at] != cell
                        {
                            continue;
                        }
                        total += 1;
                        let lexeme = world.morphemes.lexeme_id(unit);
                        if world.form_of(group, unit) == world.form_of(group, lexeme) {
                            merged += 1;
                        }
                    }
                }
                if total == 0 {
                    1.0
                } else {
                    f64::from(merged) / f64::from(total)
                }
            }
        };
        self.weakness[slot] = value;
        value
    }

    /// Je slovo pro pojem ve skupině zvukově zchátralé (`syntax.eroded`)?
    fn eroded(&self, column: usize, concept: &str) -> bool {
        let world = self.world;
        let Some(number) = world.registry.concepts.get(concept) else {
            return true;
        };
        let group = self.inputs.axis[column];
        let root = world
            .groups
            .main_code(group)
            .phonology
            .dominant_of(ConceptId(number));
        if root.is_none() {
            return true;
        }
        world.form_of(group, root).len() < world.bank.form(world.morphemes.form[root.index()]).len()
    }

    /// Míra, do jaké roli funkce přebírají jiné dominantní konstrukce (`syntax.compensation`).
    fn compensation(&mut self, column: usize, function: usize) -> f64 {
        let mut found: f64 = 0.0;
        for &other in self.catalog.compensated_by[function].clone().iter() {
            let coverage = self.catalog.functions[other].coverage;
            if let Some(current) = self.dominant_construction(column, other).cloned() {
                if self.carries_role(&current) {
                    found = found.max(coverage);
                }
            }
        }
        found
    }

    /// Jak zřetelně konstrukce vyjadřuje svou funkci, 0 až 1 (`syntax.strength`).
    fn strength(&mut self, column: usize, variant: VariantId, construction: &Construction) -> f64 {
        let Some(function) = self.catalog.index(&construction.function) else {
            return 0.0;
        };
        match construction.kind.as_str() {
            "periphrastic" => 1.0,
            "synthetic" => {
                let group = self.inputs.axis[column];
                let applied = self
                    .world
                    .groups
                    .main_code(group)
                    .phonology
                    .grammar
                    .grammar_applied
                    .contains(&variant);
                if construction.exponent.is_some() && !applied {
                    return match &construction.donor {
                        None => 1.0,
                        Some(donor) => match self.catalog.index(donor) {
                            Some(donor) => 1.0 - self.weakness(column, donor),
                            None => 1.0,
                        },
                    };
                }
                1.0 - self.weakness(column, function)
            }
            "pre" | "embraced" | "post" => {
                let words = [&construction.source, &construction.reinforcer];
                let strong = words
                    .iter()
                    .filter_map(|w| w.as_deref())
                    .any(|word| !self.eroded(column, word));
                f64::from(u8::from(strong))
            }
            "zero" => {
                let context = self.catalog.functions[function].context;
                context.max(self.compensation(column, function))
            }
            _ => 0.0,
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn construction(
        &mut self,
        pressure: u8,
        weight: f64,
        variable: VariableId,
        variants: &[VariantId],
        cells: &mut [f64],
        groups: usize,
        slots: usize,
    ) {
        let world = self.world;
        let params = &world.params;
        let function_name = &world.variables.key[variable.index()];
        let Some(function) = self.catalog.index(function_name) else {
            return;
        };
        if pressure == id::LEARNABILITY && !self.any_l2 {
            return;
        }
        for (slot, &variant) in variants.iter().enumerate() {
            if variant.is_none() {
                continue;
            }
            let Payload::Construction(construction) = &world.variants.payload[variant.index()]
            else {
                continue;
            };
            let construction = construction.clone();
            for g in 0..groups {
                let score = match pressure {
                    id::ECONOMY => -params.economy_word_cost * f64::from(construction.words()),
                    id::FUSION => {
                        let rank = self.dominant_construction(g, function).map(rank_of);
                        match rank {
                            Some(current)
                                if current != 0 && rank_of(&construction) == current + 1 =>
                            {
                                params.fusion_bonus
                            }
                            _ => 0.0,
                        }
                    }
                    id::LEARNABILITY => {
                        let bound = f64::from(u8::from(is_bound(&construction)));
                        -params.learnability_strength * bound * self.l2[g]
                    }
                    id::EXPRESSIVITY => {
                        let mut need = self.catalog.functions[function].need;
                        if need == 0.0 {
                            0.0
                        } else {
                            let unexpressed = self
                                .dominant_construction(g, function)
                                .is_none_or(|current| current.kind == "zero");
                            if unexpressed {
                                need *= params.emergence_need_scale;
                            }
                            need * self.strength(g, variant, &construction)
                        }
                    }
                    _ => {
                        // Nejednoznačnost: funkce, kterou jazyk přestal vyjadřovat.
                        let mut score = 0.0;
                        let compensated = self.catalog.compensates[function].clone();
                        for target in compensated {
                            let lost = self.weakness(g, target);
                            if self.carries_role(&construction) {
                                score -= params.order_rigidity * (1.0 - lost);
                            } else {
                                score -= self.catalog.functions[target].need * lost;
                            }
                        }
                        score
                    }
                };
                add(&mut cells[g * slots + slot], weight * score);
            }
        }
    }
}

/// Pořadí na škále gramatikalizace (`Construction.rank`).
fn rank_of(construction: &Construction) -> u32 {
    match construction.kind.as_str() {
        "periphrastic" => 1 + u32::from(construction.stage.as_deref() == Some("clitic")),
        "synthetic" if construction.exponent.is_some() => 3,
        _ => 0,
    }
}

/// Je výraz vázaný na slovo (`Construction.bound`)?
fn is_bound(construction: &Construction) -> bool {
    construction.kind == "synthetic"
        || (construction.kind == "periphrastic" && construction.stage.as_deref() == Some("clitic"))
}

/// Přičte člen, pokud není nula (`x + 0` je `x`; fitness nikdy není −0, začíná +0).
#[inline]
fn add(cell: &mut f64, term: f64) {
    if term != 0.0 {
        *cell += term;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plan_ma_norm_na_kazdem_druhu_a_slovni_ocekavani_misto_obecneho() {
        let plan = plan(&crate::parameters::Parameters::default()).unwrap();
        for kind in &plan {
            assert!(kind.iter().any(|&(p, _)| p == id::NORM));
        }
        assert!(!plan[1].iter().any(|&(p, _)| p == id::ACTUATION));
        assert!(plan[1].iter().any(|&(p, _)| p == id::LEXICAL_ACTUATION));
        assert!(plan[0].iter().any(|&(p, _)| p == id::ACTUATION));
    }

    #[test]
    fn prepis_vahy_a_neznamy_tlak() {
        let mut params = crate::parameters::Parameters::default();
        params.pressure_weights.insert("conformity".into(), 0.5);
        let found = plan(&params).unwrap();
        assert!(found[0].contains(&(id::CONFORMITY, 0.5)));
        params.pressure_weights.insert("nesmysl".into(), 1.0);
        assert!(plan(&params).is_err());
    }

    #[test]
    fn poradi_konstrukce() {
        let mut c = Construction::new("PAST", "periphrastic");
        c.stage = Some("free".into());
        assert_eq!(rank_of(&c), 1);
        c.stage = Some("clitic".into());
        assert_eq!(rank_of(&c), 2);
        assert!(is_bound(&c));
        let mut s = Construction::new("PAST", "synthetic");
        assert_eq!(rank_of(&s), 0);
        s.exponent = Some("x".into());
        assert_eq!(rank_of(&s), 3);
    }
}

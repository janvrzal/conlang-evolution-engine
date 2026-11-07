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

use std::sync::OnceLock;

use cee_core::pressures::id;
use cee_core::transmission::{hash_normal_mixed, splitmix64};

use crate::grammar::{Construction, GrammaticalFunction, Template};
use crate::ids::{ConceptId, MorphemeId, VariableId, VariantId};
use crate::model::code::StressStrength;
use crate::model::lexicon::FormOperation;
use crate::model::pools::PoolBlock;
use crate::model::repertoire::{Payload, VariableKind};
use crate::rng::{stable_int, Part};
use crate::transfer::assessed::{apocope, form_score, process_score, RowAssessment};
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

/// Plán tlaků výchozích změn (`pressures_by_kind(DEFAULT_CHANGES)`); viz [`plan_for`].
pub fn plan(params: &crate::parameters::Parameters) -> Result<Plan, String> {
    plan_for(&crate::changes::default_changes(), params)
}

/// Váha normy (škola, spisovný jazyk) u každého cílového druhu. 2,25 od M9b: úměrně síle
/// hláskových změn (`Parameters::sound_actuation` 2,25), jinak škola při realistickém tempu
/// nářečí nesjednotí (brány m6a; dok. 24).
const NORM_WEIGHT: f64 = 2.25;

/// Plán tlaků podle deklarací změn (`pressures_by_kind`): všechny varianty jedné proměnné se
/// hodnotí stejnými tlaky, i když je vyrobily různé změny, proto se tlaky sdružují podle cílového
/// druhu proměnné (`Change::target`); deklaruje-li tentýž tlak víc změn, platí nejvyšší váha.
/// `Norm` (škola) působí na každý cílový druh. `Parameters::pressure_weights` přepíše výslednou
/// váhu tlaku podle jeho jména; neznámý tlak se odmítne. Tlaky jsou seřazené podle jména jako
/// v Pythonu (pořadí sčítání).
pub fn plan_for(
    changes: &[Box<dyn crate::changes::Change>],
    params: &crate::parameters::Parameters,
) -> Result<Plan, String> {
    let mut declared: [Vec<(u8, f64)>; 5] = Default::default();
    for change in changes {
        let target = &mut declared[kind_number(change.target())];
        if !target.iter().any(|&(pressure, _)| pressure == id::NORM) {
            target.push((id::NORM, NORM_WEIGHT));
        }
        for &(pressure, weight) in change.pressures() {
            match target.iter_mut().find(|item| item.0 == pressure) {
                Some(found) => found.1 = found.1.max(weight),
                None => target.push((pressure, weight)),
            }
        }
    }
    let known: Vec<&str> = {
        let mut names: Vec<&str> = declared
            .iter()
            .flatten()
            .map(|&(pressure, _)| NAMES[pressure as usize])
            .collect();
        names.push(NAMES[id::NORM as usize]);
        names
    };
    // Proti všem tlakům, ne jen aktivním: výchozí koeficient (artikulace) platí i ve světě
    // bez fonologie, kde tlak jen nepůsobí.
    for name in params.population_pressure_exponents.keys() {
        if !NAMES.contains(&name.as_str()) {
            return Err(format!(
                "Neznámé tlaky v population_pressure_exponents: [{name}]."
            ));
        }
    }
    for name in params.pressure_weights.keys() {
        if !known.contains(&name.as_str()) {
            let mut sorted = known.clone();
            sorted.sort_unstable();
            sorted.dedup();
            return Err(format!(
                "Neznámé tlaky v pressure_weights: [{name}]; známé jsou {sorted:?}."
            ));
        }
    }
    let mut plan: Plan = Default::default();
    for (kind, mut items) in declared.into_iter().enumerate() {
        items.sort_by(|a, b| NAMES[a.0 as usize].cmp(NAMES[b.0 as usize]));
        plan[kind] = items
            .into_iter()
            .map(|(pressure, weight)| {
                let weight = params
                    .pressure_weights
                    .get(NAMES[pressure as usize])
                    .copied()
                    .unwrap_or(weight);
                // Sociální ocenění hláskových změn má vlastní násobek (tempo, dok. 24).
                let weight =
                    if kind == kind_number(VariableKind::Process) && pressure == id::ACTUATION {
                        weight * params.sound_actuation
                    } else {
                        weight
                    };
                (pressure, weight)
            })
            .collect();
    }
    Ok(plan)
}

/// Živé buňky řádku (neprázdné `current` nebo `heard`): skupiny a dvojice (skupina, slot) podle
/// pořadí buněk; jen pro ně je tlak potřeba.
#[derive(Clone, Copy)]
struct Live<'a> {
    groups: &'a [usize],
    cells: &'a [(usize, usize)],
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
///
/// Tabulky jsou čistou funkcí stavu světa a staví se nejvýš jednou (`OnceLock`), takže je smějí
/// číst souběžné kusy řádků a výsledek nezávisí na tom, který kus tabulku postavil.
pub struct Pressures<'a> {
    world: &'a World,
    inputs: &'a StepInputs,
    plan: &'a Plan,
    /// Klíče ocenění změn skupin v epoše (podle sloupce osy).
    actuation_keys: Vec<u64>,
    /// Klíče společného ocenění regionu skupiny v epoše (podle sloupce osy; 0 = bez regionu).
    region_keys: Vec<u64>,
    l2: Vec<f64>,
    any_l2: bool,
    any_school: bool,
    any_taboo: bool,
    catalog: Catalog,
    /// Vlastníci tvarů podle sloupce osy: (tvar, pojem, kořen) seřazení; staví se líně.
    owners: Vec<OnceLock<Vec<(u32, u32, u32)>>>,
    /// Slabost buňky podle (sloupec, funkce).
    weakness: Vec<OnceLock<f64>>,
    /// Dominantní varianta konstrukční proměnné funkce podle (sloupec, funkce).
    dominant: Vec<OnceLock<Option<VariantId>>>,
    /// Hláskové změny bez podmínky okolí, které mohou vyprázdnit třídu hlásek (tahový řetěz).
    vacating: Vec<Vacating>,
    /// Pro každý proces: které z `vacating` jeho výstupy zaplní; staví se líně.
    fills: Vec<OnceLock<Vec<usize>>>,
    /// Výstupní hlásky procesů (líně) a hlásky skupin podle sloupce (líně) pro riziko splynutí.
    outputs: Vec<OnceLock<Vec<(i32, i32)>>>,
    inventories: Vec<OnceLock<Vec<i32>>>,
}

/// Změna bez podmínky okolí, která vyprazdňuje třídu hlásek (`target`).
struct Vacating {
    process: crate::ids::ProcessId,
    variable: VariableId,
    changed: VariantId,
}

/// Vyprazdňující změny s proměnnou a variantou „změna“ (jen ty, jejichž proměnná existuje).
fn vacating_changes(world: &World) -> Vec<Vacating> {
    crate::phonology::rows::vacating_processes(world)
        .into_iter()
        .filter_map(|process| {
            let name = world.registry.processes.name(process.0);
            let variable = world.registry.variables.get(name)?;
            let changed = world
                .registry
                .variants
                .get(&crate::phonology::rows::changed_name(name))?;
            Some(Vacating {
                process,
                variable: VariableId(variable),
                changed: VariantId(changed),
            })
        })
        .collect()
}

impl<'a> Pressures<'a> {
    /// Výhoda vzniku tónu (Haudricourt 1954, dok. 28): tón po souhlásce se stává rozlišovacím,
    /// když se ve skupině stírá rozdíl znělosti (ztráta znělosti, `voi` → −), tón z koncové
    /// souhlásky, když koncové h/ʔ mizí (`coda_loss` hrtanových).
    /// Člen = `tonogenesis_trigger` × (2 × nejvyšší podíl takové změny ve skupině − 1): bez
    /// spouštěče nevýhoda, s úplnou ztrátou znělosti výhoda. Ztráta znělosti na konci slova
    /// a spodoba znělosti se nepočítají (týkají se konce slova a shluků, ne náslovu).
    fn tone_trigger(&self, g: usize, process: crate::ids::ProcessId) -> f64 {
        let Some(Some(def)) = self.world.processes.get(process.index()) else {
            return 0.0;
        };
        let wanted: &[&str] = match def.family.as_str() {
            "tonogenesis_onset" => &["voi"],
            "tonogenesis_coda" => &[],
            _ => return 0.0,
        };
        let group = self.inputs.axis[g];
        let mut best: f64 = 0.0;
        for (index, other) in self.world.processes.iter().enumerate() {
            let Some(other) = other else { continue };
            // Ztráta znělosti (rys `voi` → −), ne znělost mezi samohláskami; u koncové souhlásky
            // její oslabení na h/ʔ (debukalizace), ne každé odpadnutí koncovky.
            let triggers = if wanted.is_empty() {
                // Úplná ztráta koncového h/ʔ (vietnamština, čínština), ne oslabení s → h.
                other.family == "coda_loss" && self.laryngeal_target(other)
            } else {
                other.family != def.family
                    && other.family != "final_devoicing"
                    && other.family != "voicing_assimilation"
                    && other
                        .changes
                        .iter()
                        .any(|(feature, value)| feature == "voi" && value == "-")
            };
            if !triggers {
                continue;
            }
            let name = self.world.registry.processes.name(index as u32);
            let (Some(variable), Some(changed)) = (
                self.world.registry.variables.get(name),
                self.world
                    .registry
                    .variants
                    .get(&crate::phonology::rows::changed_name(name)),
            ) else {
                continue;
            };
            let share = crate::phonology::rows::changed_share(
                self.world,
                group,
                VariableId(variable),
                VariantId(changed),
            );
            best = best.max(share);
        }
        // Spouštěč je nutná podmínka: bez něj tón nevýhodu, se ztrátou znělosti výhodu.
        self.world.params.tonogenesis_trigger * (2.0 * best - 1.0)
    }

    /// Míří změna jen na hrtanové souhlásky h nebo ʔ? Odpadnutí celé třídy frikativ (s, x, h …)
    /// se nepočítá: tón vzniká až z oslabeného *-s* → *-h* (Haudricourt 1954), ne z jeho ztráty.
    fn laryngeal_target(&self, def: &crate::model::lexicon::ProcessDef) -> bool {
        let Some(table) = self.world.table.as_ref() else {
            return false;
        };
        let laryngeal: Vec<i32> = ["h", "ʔ"]
            .iter()
            .filter_map(|ipa| table.id_of(ipa).ok())
            .collect();
        let mut any = false;
        for (segment, &inside) in def.target.mask.iter().enumerate() {
            if !inside || segment >= table.len() || !table.is_plain(segment as i32) {
                continue;
            }
            if !laryngeal.contains(&(segment as i32)) {
                return false;
            }
            any = true;
        }
        any
    }

    /// Leží skupina ve městě (`Territory::urban`)?
    fn urban(&self, group: crate::ids::GroupId) -> bool {
        let territory = self.world.groups.territory[group.index()];
        self.world
            .territories
            .get(territory.index())
            .is_some_and(|t| t.urban > 0.0)
    }

    /// Výhoda tahového řetězu (Martinet 1955; Labov 1994) pro změnu `process` ve sloupci `g`:
    /// zaplňuje-li třídu, kterou jiná změna bez podmínky okolí ve skupině z většiny vyprázdnila,
    /// dostane `chain_shift_weight` × (podíl té změny − ½) / ½. Pod polovinou žádnou.
    fn chain_bonus(&self, g: usize, process: crate::ids::ProcessId) -> f64 {
        // Mezeru zaplňuje sousední řada (posun bez podmínky okolí), ne podmíněné pravidlo, které
        // by nové hlásky jen vrátilo (znělost /V_V po ztrátě znělosti).
        if !self.vacating.iter().any(|v| v.process == process) {
            return 0.0;
        }
        let Some(slot) = self.fills.get(process.index()) else {
            return 0.0;
        };
        let fills = slot.get_or_init(|| {
            let ids: Vec<crate::ids::ProcessId> = self.vacating.iter().map(|v| v.process).collect();
            crate::phonology::rows::fills(self.world, process, &ids)
                .into_iter()
                .filter_map(|p| ids.iter().position(|&q| q == p))
                .collect()
        });
        let group = self.inputs.axis[g];
        let progress = fills
            .iter()
            .map(|&at| {
                let gap = &self.vacating[at];
                let share = crate::phonology::rows::changed_share(
                    self.world,
                    group,
                    gap.variable,
                    gap.changed,
                );
                ((share - 0.5) / 0.5).clamp(0.0, 1.0)
            })
            .fold(0.0, f64::max);
        self.world.params.chain_shift_weight * progress
    }

    /// Riziko splynutí řadového posunu bez podmínky okolí: podíl jeho výstupních hlásek, které
    /// skupina ještě má (cílová řada je obsazená), × `chain_shift_weight`, zmenšený o pokrok
    /// změny, která cílovou řadu vyprazdňuje (v polovině jejího průběhu je nulový). Ztráta znělosti *b d g* → *p t k* u jazyka,
    /// který *p t k* má, je proto nevýhodná; po vyprázdnění *p t k* (řetěz) ne (dok. 29).
    fn merger_risk(&self, g: usize, process: crate::ids::ProcessId) -> f64 {
        if !self.vacating.iter().any(|v| v.process == process) {
            return 0.0;
        }
        let outputs = self.outputs[process.index()]
            .get_or_init(|| crate::phonology::rows::outputs(self.world, process));
        if outputs.is_empty() {
            return 0.0;
        }
        let group = self.inputs.axis[g];
        let inventory =
            self.inventories[g].get_or_init(|| crate::contact::inventory(self.world, group));
        // Jen hlásky, které skupina má: kolik jejích vstupů by splynulo s hláskou, kterou už má.
        let has = |s: &i32| inventory.binary_search(s).is_ok();
        let own: Vec<&(i32, i32)> = outputs.iter().filter(|(input, _)| has(input)).collect();
        if own.is_empty() {
            return 0.0;
        }
        let present =
            own.iter().filter(|(_, output)| has(output)).count() as f64 / own.len() as f64;
        if present == 0.0 {
            return 0.0;
        }
        let fills = self.fills[process.index()].get_or_init(|| {
            let ids: Vec<crate::ids::ProcessId> = self.vacating.iter().map(|v| v.process).collect();
            crate::phonology::rows::fills(self.world, process, &ids)
                .into_iter()
                .filter_map(|p| ids.iter().position(|&q| q == p))
                .collect()
        });
        let vacated = fills
            .iter()
            .map(|&at| {
                let gap = &self.vacating[at];
                crate::phonology::rows::changed_share(self.world, group, gap.variable, gap.changed)
            })
            .fold(0.0, f64::max);
        // Zrcadlo `chain_bonus`: riziko mizí, když vyprazdňující změna přesáhne polovinu, a od
        // ní dál táhne bonus řetězu (souvislý přechod tlaku přes nulu).
        self.world.params.chain_shift_weight * present * (1.0 - vacated / 0.5).clamp(0.0, 1.0)
    }

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
        // Společné ocenění změny v regionu (dok. 27): změna, která „frčí“ ve městě a regionu, frčí
        // ve všech jeho vesnicích, s místní odchylkou. Bez něj si každá vesnice vybere jiné změny
        // a nářečí jednoho regionu se rozpadnou na jednovesnické jazyky.
        let region_keys = inputs
            .axis
            .iter()
            .map(|&g| {
                crate::polity::region_of(world, g).map_or(0, |region| {
                    stable_int(&[
                        Part::Int(world.seed),
                        Part::Str("actuation-region"),
                        Part::Int(epoch),
                        Part::Str(world.registry.territories.name(region.0)),
                    ])
                })
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
        let vacating = if world.params.chain_shift_weight > 0.0 {
            vacating_changes(world)
        } else {
            Vec::new()
        };
        let fills = (0..world.processes.len())
            .map(|_| OnceLock::new())
            .collect();
        let outputs = (0..world.processes.len())
            .map(|_| OnceLock::new())
            .collect();
        let inventories = (0..inputs.axis.len()).map(|_| OnceLock::new()).collect();
        Ok(Pressures {
            outputs,
            inventories,
            region_keys,
            vacating,
            fills,
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
            owners: (0..columns).map(|_| OnceLock::new()).collect(),
            weakness: (0..columns * functions).map(|_| OnceLock::new()).collect(),
            dominant: (0..columns * functions).map(|_| OnceLock::new()).collect(),
        })
    }

    /// Fitness řádků `[first, first + count)` bloku do `out` (`count × skupiny × sloty`,
    /// vynulované); `current` a `heard` mají týž tvar. Smí se volat souběžně z více vláken
    /// (pomocné tabulky jsou za `OnceLock`); každé volání píše jen do svého `out`. Tlak se
    /// počítá jen v buňkách, kde je `current` nebo `heard` nenulové (jen tam ho `settle` čte);
    /// ostatní buňky zůstanou nulové.
    pub fn fitness(
        &self,
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
            let assessed = self.assess_row(kind, variable, variants, now, heard);
            // Skupiny, které proměnnou nemají a neslyší (v žádném slotu), settle nečte: tlak
            // se počítá jen pro živé skupiny a ostatní buňky zůstanou nulové.
            // Stejně se přeskočí sloty skupiny, které nemají a neslyší (buňky `(skupina, slot)`).
            let mut live: Vec<usize> = Vec::new();
            let mut live_cells: Vec<(usize, usize)> = Vec::new();
            for g in 0..groups {
                let before = live_cells.len();
                for slot in 0..slots {
                    let at = g * slots + slot;
                    if now[at] != 0.0 || heard[at] != 0.0 {
                        live_cells.push((g, slot));
                    }
                }
                if live_cells.len() > before {
                    live.push(g);
                }
            }
            if live.is_empty() {
                continue;
            }
            let live = Live {
                groups: &live,
                cells: &live_cells,
            };
            for &(pressure, weight) in &plan[kind_number(kind)] {
                if weight == 0.0 {
                    continue;
                }
                let exponent = self
                    .world
                    .params
                    .population_pressure_exponents
                    .get(NAMES[pressure as usize])
                    .copied()
                    .unwrap_or(0.0);
                if exponent == 0.0 {
                    self.apply(
                        pressure,
                        weight,
                        variable,
                        variants,
                        now,
                        heard,
                        cells,
                        assessed.as_ref(),
                        live,
                        slots,
                    );
                    continue;
                }
                // Populační koeficient (Trudgill; dok. 22, M7.2e): příspěvek tlaku zvlášť,
                // pak násobený (populace / 500) ** exponent podle skupiny.
                let mut part = vec![0.0; cells.len()];
                self.apply(
                    pressure,
                    weight,
                    variable,
                    variants,
                    now,
                    heard,
                    &mut part,
                    assessed.as_ref(),
                    live,
                    slots,
                );
                for (at, &value) in part.iter().enumerate() {
                    if value != 0.0 {
                        let group = self.inputs.axis[at / slots];
                        let mut size = f64::from(self.world.groups.population[group.index()])
                            / POPULATION_REFERENCE;
                        // Město je síť čtvrtí, ne jedna obrovská obec: populační tlaky (ocenění
                        // změn, artikulace) v něm mají sílu jako ve vesnici (změny se šíří z měst,
                        // Labov 2001; dok. 27).
                        if self.urban(group) {
                            size /= self.world.params.city_size.max(1.0);
                        }
                        add(&mut cells[at], value * size.powf(exponent));
                    }
                }
            }
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn apply(
        &self,
        pressure: u8,
        weight: f64,
        variable: VariableId,
        variants: &[VariantId],
        current: &[f64],
        heard: &[f64],
        cells: &mut [f64],
        assessed: Option<&RowAssessment>,
        live: Live<'_>,
        slots: usize,
    ) {
        let world = self.world;
        let has_table = world.table.is_some();
        let columns = &world.transfer.derived.variants;
        match pressure {
            id::CONFORMITY => {
                for &(g, slot) in live.cells {
                    let at = g * slots + slot;
                    add(&mut cells[at], weight * (2.0 * current[at] - 1.0));
                }
            }
            id::APPEAL => {
                for &(g, slot) in live.cells {
                    let variant = variants[slot];
                    if variant.is_none() {
                        continue;
                    }
                    let appeal = columns.appeal[variant.index()];
                    let term = weight * if appeal.is_nan() { 0.0 } else { appeal }.clamp(-1.0, 1.0);
                    add(&mut cells[g * slots + slot], term);
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
                for &(g, slot) in live.cells {
                    let variant = variants[slot];
                    if variant.is_none() || !columns.is_word(variant) {
                        continue;
                    }
                    if current[g * slots + slot] >= 0.5 {
                        add(&mut cells[g * slots + slot], weight * protection);
                    }
                }
            }
            id::MOTIVATION if has_table => {
                for &(g, slot) in live.cells {
                    let variant = variants[slot];
                    if variant.is_none() {
                        continue;
                    }
                    let appeal = columns.appeal[variant.index()];
                    let term = weight
                        * (columns.motivation[variant.index()]
                            + if appeal.is_nan() { 0.0 } else { appeal });
                    add(&mut cells[g * slots + slot], term);
                }
            }
            id::ACTUATION | id::LEXICAL_ACTUATION => {
                let lexical = pressure == id::LEXICAL_ACTUATION;
                for &(g, slot) in live.cells {
                    let variant = variants[slot];
                    if variant.is_none()
                        || !world.variants.innovation[variant.index()]
                        || (lexical && !columns.is_word(variant))
                    {
                        continue;
                    }
                    // Slot, který kohorta neslyší, výběr nečte (slyšený × exp(…) je nula).
                    if heard[g * slots + slot] <= 0.0 && current[g * slots + slot] <= 0.0 {
                        continue;
                    }
                    let mixed = splitmix64(columns.key[variant.index()]);
                    let local = hash_normal_mixed(self.actuation_keys[g], mixed);
                    // Společné ocenění regionu jen u hláskových změn: rozpad nářečí řeší výslovnost;
                    // slovník a syntax zůstávají místní (jinak se po regionu šíří i nová slova
                    // a změny záporu a retence latiny klesne pod pásmo; dok. 27).
                    let rho = if world.variables.kind[variable.index()]
                        == crate::model::repertoire::VariableKind::Process
                    {
                        world.params.actuation_coherence
                    } else {
                        world.params.actuation_coherence_other
                    };
                    let noise = if rho > 0.0 && self.region_keys[g] != 0 {
                        let shared = hash_normal_mixed(self.region_keys[g], mixed);
                        rho.sqrt() * shared + (1.0 - rho).sqrt() * local
                    } else {
                        local
                    };
                    add(
                        &mut cells[g * slots + slot],
                        weight * (ACTUATION_SPREAD * noise).clamp(-1.0, 1.0),
                    );
                    if !lexical && !self.world.sound.shifts.is_empty() {
                        let group = self.inputs.axis[g];
                        let language = world.groups.main_code(group).language.0;
                        for shift in &self.world.sound.shifts {
                            if shift.variable == variable
                                && shift.changed == variant
                                && shift.language == language
                                && current[g * slots + slot] < shift.until
                                && (shift.regions.is_empty()
                                    || crate::polity::region_of(world, group)
                                        .is_some_and(|r| shift.regions.contains(&r)))
                            {
                                add(&mut cells[g * slots + slot], shift.pull);
                            }
                        }
                    }
                    if !lexical && world.params.tonogenesis_trigger > 0.0 {
                        if let Some(crate::model::repertoire::Payload::Process {
                            process,
                            changed: true,
                        }) = world.variants.payload.get(variant.index())
                        {
                            let bonus = self.tone_trigger(g, *process);
                            if bonus != 0.0 {
                                add(&mut cells[g * slots + slot], bonus);
                            }
                        }
                    }
                    if !lexical && !self.vacating.is_empty() {
                        if let Some(crate::model::repertoire::Payload::Process {
                            process,
                            changed: true,
                        }) = world.variants.payload.get(variant.index())
                        {
                            let bonus =
                                self.chain_bonus(g, *process) - self.merger_risk(g, *process);
                            if bonus != 0.0 {
                                add(&mut cells[g * slots + slot], bonus);
                            }
                        }
                    }
                }
            }
            id::LEXICAL_CLARITY if has_table => {
                let concept = world.variables.concept[variable.index()];
                for &(g, slot) in live.cells {
                    let variant = variants[slot];
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
            id::TABOO if self.any_taboo => {
                let concept = world.variables.concept[variable.index()];
                for &g in live.groups {
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
                for &g in live.groups {
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
            id::ARTICULATION
            | id::CLARITY
            | id::DISPERSION
            | id::FUNCTIONAL_LOAD
            | id::PHONOTACTICS
            | id::UNIFORMITY
            | id::CONSERVATION
            | id::TEACHABILITY
            | id::DISTINCTIVENESS => {
                if let Some(assessed) = assessed {
                    self.assessed_pressure(pressure, weight, variable, assessed, cells, slots);
                }
            }
            id::AMBIGUITY | id::ECONOMY | id::EXPRESSIVITY | id::FUSION | id::LEARNABILITY => self
                .construction(
                    pressure, weight, variable, variants, current, cells, live, slots,
                ),
            _ => {}
        }
    }

    // --- tlaky nad hodnocením ------------------------------------------------------------

    /// Hodnocení změny řádku (procesu či analogie) ve skupinách, kam dolehla; jednou pro všechny
    /// tlaky řádku. `None` pro řádky, které žádnou změnu nesledují.
    fn assess_row(
        &self,
        kind: VariableKind,
        variable: VariableId,
        variants: &[VariantId],
        current: &[f64],
        heard: &[f64],
    ) -> Option<RowAssessment> {
        if !matches!(kind, VariableKind::Process | VariableKind::Form) {
            return None;
        }
        let world = self.world;
        let changed = *world.transfer.derived.changed.get(variable.index())?;
        let slot = variants.iter().position(|v| v.0 == changed)?;
        let tracked = match kind {
            VariableKind::Process => world
                .process(world.variables.process[variable.index()])
                .is_some(),
            _ => world.form_changes.contains_key(&variable),
        };
        if !tracked {
            return None;
        }
        let slots = variants.len();
        let columns: Vec<usize> = (0..self.inputs.axis.len())
            .filter(|&g| current[g * slots + slot] > 0.0 || heard[g * slots + slot] > 0.0)
            .collect();
        if columns.is_empty() {
            return None;
        }
        let values = if kind == VariableKind::Form {
            crate::transfer::assess::form_cells_with(world, variable, &columns, |column| {
                crate::morphology::concept_totals(world, self.inputs.axis[column])
            })
        } else {
            crate::transfer::seams::assess_cells(world, variable, &columns, self.inputs.tick)
        };
        Some(RowAssessment {
            slot,
            columns,
            values,
        })
    }

    fn assessed_pressure(
        &self,
        pressure: u8,
        weight: f64,
        variable: VariableId,
        assessed: &RowAssessment,
        cells: &mut [f64],
        slots: usize,
    ) {
        let world = self.world;
        let params = &world.params;
        if pressure == id::TEACHABILITY && !self.any_l2 {
            return;
        }
        let process = match world.variables.kind[variable.index()] {
            VariableKind::Process => world.process(world.variables.process[variable.index()]),
            _ => None,
        };
        let form = world.form_changes.get(&variable);
        for (&g, values) in assessed.columns.iter().zip(&assessed.values) {
            let Some(values) = values else { continue };
            let group = self.inputs.axis[g];
            let score = match (process, form) {
                (Some(process), _) => {
                    let code = world.groups.main_code(group);
                    let coda = if pressure == id::PHONOTACTICS && apocope(process) {
                        crate::transfer::seams::coda_share(world, group)
                    } else {
                        0.0
                    };
                    process_score(
                        pressure,
                        process,
                        values,
                        code.stress_strength == StressStrength::Strong,
                        coda,
                        params,
                    )
                }
                (None, Some(change)) => form_score(
                    pressure,
                    change.operation == FormOperation::Level,
                    change.operation.lexeme_wide(),
                    values,
                    self.l2[g],
                ),
                _ => 0.0,
            };
            add(&mut cells[g * slots + assessed.slot], weight * score);
        }
    }

    // --- lexikální jasnost ---------------------------------------------------------------

    /// Tvary dominantních kořenů skupiny: (tvar, pojem, kořen) seřazené (vlastníci tvarů).
    fn owners_of(&self, column: usize) -> &[(u32, u32, u32)] {
        self.owners[column].get_or_init(|| {
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
            list
        })
    }

    /// Skóre jasnosti dvojice (morfém, pojem) ve skupině: zkrácené slovo a homofon s nepříbuzným
    /// pojmem (`lexical_index.clarity_scores`).
    fn lexical_clarity(&self, column: usize, morpheme: MorphemeId, concept: ConceptId) -> f64 {
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

    fn dominant_construction(&self, column: usize, function: usize) -> Option<&Construction> {
        let slot = column * self.catalog.functions.len() + function;
        let variant = *self.dominant[slot].get_or_init(|| {
            self.catalog.variable[function].and_then(|variable| {
                self.world
                    .dominant(self.inputs.axis[column], variable)
                    .map(|(variant, _)| variant)
            })
        });
        let variant = variant?;
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
    fn weakness(&self, column: usize, function: usize) -> f64 {
        let slot = column * self.catalog.functions.len() + function;
        *self.weakness[slot].get_or_init(|| {
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
        })
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
        crate::syntax::worn(
            world.form_of(group, root).len(),
            world.bank.form(world.morphemes.form[root.index()]).len(),
        )
    }

    /// Míra, do jaké roli funkce přebírají jiné dominantní konstrukce (`syntax.compensation`).
    fn compensation(&self, column: usize, function: usize) -> f64 {
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
    fn strength(&self, column: usize, variant: VariantId, construction: &Construction) -> f64 {
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
    #[allow(clippy::too_many_arguments)]
    fn construction(
        &self,
        pressure: u8,
        weight: f64,
        variable: VariableId,
        variants: &[VariantId],
        current: &[f64],
        cells: &mut [f64],
        live: Live<'_>,
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
        {
            for &(g, slot) in live.cells {
                let variant = variants[slot];
                if variant.is_none() {
                    continue;
                }
                let Payload::Construction(construction) = &world.variants.payload[variant.index()]
                else {
                    continue;
                };
                let construction: &Construction = construction;
                let score = match pressure {
                    id::ECONOMY => -params.economy_word_cost * f64::from(construction.words()),
                    id::FUSION => {
                        let rank = self.dominant_construction(g, function).map(current_rank);
                        match rank {
                            Some(current)
                                if current != 0 && rank_of(construction) == current + 1 =>
                            {
                                params.fusion_bonus
                            }
                            _ => 0.0,
                        }
                    }
                    id::LEARNABILITY => {
                        let bound = f64::from(u8::from(is_bound(construction)));
                        -params.learnability_strength * bound * self.l2[g]
                    }
                    id::EXPRESSIVITY => {
                        let entry = &self.catalog.functions[function];
                        let mut need = entry.need;
                        for (other, k) in &entry.reinforced_by {
                            if let Some(target) = self.catalog.index(other) {
                                need *= 1.0 + k * self.weakness(g, target);
                            }
                        }
                        if need == 0.0 {
                            0.0
                        } else {
                            let unexpressed = self
                                .dominant_construction(g, function)
                                .is_none_or(|current| current.kind == "zero");
                            if unexpressed {
                                need *= params.emergence_need_scale;
                            }
                            // Extravagance (Haspelmath 1999; Detges a Waltereit 2002): čerstvý volný opis
                            // přitahuje sám o sobě, přitažlivost slábne, jak opis zevšední
                            // (podíl ve skupině). Dok. 22, M7.3k.
                            let fresh = if construction.kind == "periphrastic"
                                && construction.stage.as_deref() == Some("free")
                            {
                                params.extravagance * (1.0 - current[g * slots + slot])
                            } else {
                                0.0
                            };
                            need * self.strength(g, variant, construction) + fresh
                        }
                    }
                    _ => {
                        // Nejednoznačnost: funkce, kterou jazyk přestal vyjadřovat.
                        let mut score = 0.0;
                        let compensated = self.catalog.compensates[function].clone();
                        for target in compensated {
                            let lost = self.weakness(g, target);
                            if self.carries_role(construction) {
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

/// Populace, při které populační koeficient tlaků nic nemění (vesnice výchozích scénářů).
const POPULATION_REFERENCE: f64 = 500.0;

/// Pořadí na škále gramatikalizace (`Construction.rank`).
fn rank_of(construction: &Construction) -> u32 {
    match construction.kind.as_str() {
        "periphrastic" => 1 + u32::from(construction.stage.as_deref() == Some("clitic")),
        "synthetic" if construction.exponent.is_some() => 3,
        // Vyblednutý člen (ukazatel jména) je o stupeň dál než koncovka.
        "zero" if construction.stage.as_deref() == Some("marker") => 4,
        _ => 0,
    }
}

/// Stupeň dnešní konstrukce pro bonus `Fusion`: jako [`rank_of`], ale zděděná syntetická
/// koncovka (bez zapsaného exponentu) je také koncovka (stupeň 3). Ovlivní jen krok o stupeň
/// dál, tedy vyblednutí v ukazatel (dok. 22, M7.2b); nová koncovka má exponent vždy.
fn current_rank(construction: &Construction) -> u32 {
    if construction.kind == "synthetic" {
        3
    } else {
        rank_of(construction)
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

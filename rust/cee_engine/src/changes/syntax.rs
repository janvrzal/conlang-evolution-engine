//! Syntaktické změny: deset kroků gramatikalizace (zrcadlo `changes/syntax.py`).
//!
//! Každá změna navrhuje *další krok* od konstrukce, která ve skupině právě převažuje.
//! Gramatikalizace tak jde jedním směrem (volné slovo, přiklonka, koncovka) a cykly se
//! uzavírají samy. Změna nezná konkrétní funkci: místem je každá funkce katalogu se šablonou
//! změny, kterou jazyk sleduje (má konstrukční proměnnou). Míra je jednotná (`base × počet
//! míst`), jen u zániku kategorie se odvozuje od slabosti koncovky a podílu druhojazyčných
//! mluvčích.

use crate::changes::{Change, InnovationContext, NewVariant, Sites, SYNTAX_PRESSURES};
use crate::grammar::{Construction, Template};
use crate::ids::{ConceptId, GroupId, VariableId, VariantId};
use crate::model::repertoire::{Origin, VariableKind};
use crate::rng::Stream;
use crate::syntax;
use crate::world::World;

/// Druh syntaktické změny (pořadí je kanonické pořadí registru).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Step {
    Periphrasis,
    Cliticization,
    Affixation,
    Exaptation,
    CategoryLoss,
    NegationReinforcement,
    NegationReduction,
    NegationRenewal,
    OrderFixation,
    OrderRelaxation,
    /// Vázaný člen ztratí určitost a stane se pouhým ukazatelem jména (Greenberg 1978,
    /// stadium III); funkce zůstane nevyjádřená a může se obnovit opisem.
    Bleaching,
}

pub struct SyntacticChange {
    which: Step,
}

impl SyntacticChange {
    pub fn new(which: Step) -> SyntacticChange {
        SyntacticChange { which }
    }

    fn template(&self) -> Template {
        match self.which {
            Step::NegationReinforcement | Step::NegationReduction | Step::NegationRenewal => {
                Template::Negation
            }
            Step::OrderFixation | Step::OrderRelaxation => Template::Order,
            _ => Template::Inflection,
        }
    }

    fn base_rate(&self) -> f64 {
        match self.which {
            Step::Periphrasis => 0.05,
            Step::Cliticization => 0.04,
            Step::Affixation => 0.03,
            Step::Exaptation => 0.02,
            Step::CategoryLoss => 0.02,
            Step::NegationReinforcement => 0.03,
            Step::NegationReduction => 0.03,
            Step::NegationRenewal => 0.01,
            Step::OrderFixation => 0.03,
            Step::OrderRelaxation => 0.01,
            // Jako připojení koncovky (0,03): dok. 22, M7.2b.
            Step::Bleaching => 0.03,
        }
    }

    /// Kolik důvodů k vypuštění výrazu mluvčí mají (násobek základní míry; jen zánik kategorie).
    fn pressure(&self, world: &World, group: GroupId, current: &Construction) -> f64 {
        if current.kind == "periphrastic" && current.stage.as_deref() == Some("free") {
            return 1.0;
        }
        if !syntax::bound(current) {
            return 0.0;
        }
        let unreliable = if current.kind == "synthetic" {
            syntax::weakness(world, group, &current.function)
        } else {
            0.0
        };
        unreliable + world.params.category_loss_l2_boost * world.groups.main_code(group).l2_share
    }

    /// Připouští dnešní konstrukce změnu (`applies`)?
    fn applies(&self, world: &World, group: GroupId, current: &Construction) -> bool {
        match self.which {
            Step::Periphrasis => {
                let open = match current.kind.as_str() {
                    "synthetic" => syntax::weakness(world, group, &current.function) != 0.0,
                    "zero" => true,
                    _ => false,
                };
                open && !sources(world, group, &current.function).is_empty()
            }
            Step::Cliticization => {
                current.kind == "periphrastic" && current.stage.as_deref() == Some("free")
            }
            Step::Affixation => {
                current.kind == "periphrastic" && current.stage.as_deref() == Some("clitic")
            }
            Step::Exaptation => {
                current.kind == "zero" && !donors(world, group, &current.function).is_empty()
            }
            Step::CategoryLoss => self.pressure(world, group, current) > 0.0,
            Step::NegationReinforcement => {
                current.kind == "pre" && !sources(world, group, &current.function).is_empty()
            }
            Step::NegationReduction => current.kind == "embraced",
            Step::NegationRenewal => current.kind == "post",
            Step::OrderFixation => {
                current.kind == "free"
                    && syntax::entry(world, &current.function).is_some_and(|e| !e.orders.is_empty())
            }
            Step::OrderRelaxation => current.kind == "fixed",
            Step::Bleaching => {
                syntax::bound(current)
                    && syntax::entry(world, &current.function).is_some_and(|e| e.bleaches)
            }
        }
    }

    /// Místa změny a jejich míry: funkce v pořadí jmen, jejichž dominantní konstrukce změnu připouští.
    fn found(&self, world: &World, group: GroupId) -> (Vec<VariableId>, Vec<f64>) {
        let mut sites = Vec::new();
        let mut rates = Vec::new();
        for entry in syntax::functions(world, Some(self.template())) {
            let Some(current) = syntax::dominant(world, group, &entry.id) else {
                continue;
            };
            if !self.applies(world, group, &current) {
                continue;
            }
            let Some(variable) = syntax::variable_of(world, &entry.id) else {
                continue;
            };
            sites.push(variable);
            rates.push(match self.which {
                Step::CategoryLoss => self.base_rate() * self.pressure(world, group, &current),
                _ => self.base_rate(),
            });
        }
        (sites, rates)
    }

    /// Následující konstrukce funkce (`next`), nebo `None`, když krok dnes nejde.
    fn next(
        &self,
        world: &mut World,
        group: GroupId,
        tick: u32,
        current: &Construction,
        rng: &mut Stream,
    ) -> Option<Construction> {
        let function = current.function.as_str();
        match self.which {
            Step::Periphrasis => {
                let options = sources(world, group, function);
                let source = pick(&options, rng)?;
                let mut c = Construction::new(function, "periphrastic").with_source(&source);
                c.stage = Some("free".into());
                Some(c)
            }
            Step::Cliticization => {
                let mut c = Construction::new(function, "periphrastic");
                c.source = current.source.clone();
                c.stage = Some("clitic".into());
                Some(c)
            }
            Step::Affixation => {
                let affix = syntax::new_affix(world, group, current, tick)?;
                let mut c = Construction::new(function, "synthetic");
                c.source = current.source.clone();
                c.exponent = Some(world.registry.morphemes.name(affix.0).to_owned());
                Some(c)
            }
            Step::Exaptation => {
                let found = donors(world, group, function);
                if found.is_empty() {
                    return None;
                }
                let (donor, exponent) = found[rng.integers(found.len() as u64) as usize].clone();
                let mut c = Construction::new(function, "synthetic");
                c.exponent = Some(exponent);
                c.donor = Some(donor);
                Some(c)
            }
            Step::CategoryLoss => Some(Construction::new(function, "zero")),
            Step::NegationReinforcement => {
                let options: Vec<String> = sources(world, group, function)
                    .into_iter()
                    .filter(|s| Some(s) != current.source.as_ref())
                    .collect();
                let reinforcer = pick(&options, rng)?;
                let mut c = Construction::new(function, "embraced");
                c.source = current.source.clone();
                c.reinforcer = Some(reinforcer);
                Some(c)
            }
            Step::NegationReduction => {
                let mut c = Construction::new(function, "post");
                c.source = current.reinforcer.clone();
                Some(c)
            }
            Step::NegationRenewal => {
                let mut c = Construction::new(function, "pre");
                c.source = current.source.clone();
                Some(c)
            }
            Step::OrderFixation => {
                let orders = syntax::entry(world, function)?.orders;
                let order = pick(&orders, rng)?;
                Some(Construction::new(function, "fixed").with_order(&order))
            }
            Step::OrderRelaxation => Some(Construction::new(function, "free")),
            Step::Bleaching => {
                let mut c = Construction::new(function, "zero");
                c.source = current.source.clone();
                c.stage = Some("marker".into());
                Some(c)
            }
        }
    }
}

/// Zdroje gramatikalizace funkce, které jazyk má jako slovo (v pořadí katalogu).
fn sources(world: &World, group: GroupId, function: &str) -> Vec<String> {
    let Some(entry) = syntax::entry(world, function) else {
        return Vec::new();
    };
    entry
        .sources
        .into_iter()
        .filter(|concept| {
            syntax::concept_of(world, concept)
                .is_some_and(|c: ConceptId| syntax::dominant_root(world, group, c).is_some())
        })
        .collect()
}

fn pick(options: &[String], rng: &mut Stream) -> Option<String> {
    if options.is_empty() {
        return None;
    }
    Some(options[rng.integers(options.len() as u64) as usize].clone())
}

/// Dárci koncovky pro funkci: (funkce dárce, jméno zbytkové koncovky).
fn donors(world: &World, group: GroupId, function: &str) -> Vec<(String, String)> {
    let Some(entry) = syntax::entry(world, function) else {
        return Vec::new();
    };
    let mut found = Vec::new();
    for donor in &entry.donors {
        let Some(other) = syntax::entry(world, donor) else {
            continue;
        };
        if other.word_class() != entry.word_class() {
            continue;
        }
        if !syntax::compensated(world, group, donor) {
            continue;
        }
        if let Some(exponent) = syntax::residual_exponent(world, group, &other) {
            found.push((
                donor.clone(),
                world.registry.morphemes.name(exponent.0).to_owned(),
            ));
        }
    }
    found
}

impl Change for SyntacticChange {
    fn kind(&self) -> &'static str {
        match self.which {
            Step::Periphrasis => "periphrasis",
            Step::Cliticization => "cliticization",
            Step::Affixation => "affixation",
            Step::Exaptation => "exaptation",
            Step::CategoryLoss => "category_loss",
            Step::NegationReinforcement => "negation_reinforcement",
            Step::NegationReduction => "negation_reduction",
            Step::NegationRenewal => "negation_renewal",
            Step::OrderFixation => "order_fixation",
            Step::OrderRelaxation => "order_relaxation",
            Step::Bleaching => "bleaching",
        }
    }

    fn rate_basis_generation(&self) -> bool {
        true
    }

    fn target(&self) -> VariableKind {
        VariableKind::Construction
    }

    fn pressures(&self) -> &'static [(u8, f64)] {
        &SYNTAX_PRESSURES
    }

    fn weighted_sites(&self, world: &World, ctx: &InnovationContext) -> Sites {
        let (sites, rates) = self.found(world, ctx.group);
        let weights = (self.which == Step::CategoryLoss && !sites.is_empty()).then(|| {
            let total: f64 = rates.iter().sum();
            rates.iter().map(|r| r / total).collect()
        });
        Sites { sites, weights }
    }

    fn rate_sum(&self, world: &World, ctx: &InnovationContext) -> f64 {
        let (sites, rates) = self.found(world, ctx.group);
        match self.which {
            Step::CategoryLoss => rates.iter().sum(),
            _ => self.base_rate() * sites.len() as f64,
        }
    }

    fn propose(
        &self,
        world: &mut World,
        ctx: &InnovationContext,
        site: VariableId,
        rng: &mut Stream,
        _index: usize,
    ) -> Option<NewVariant> {
        if world.variables.kind.get(site.index()) != Some(&VariableKind::Construction) {
            return None;
        }
        let function = world.variables.key[site.index()].clone();
        let current = syntax::dominant(world, ctx.group, &function)?;
        if !self.applies(world, ctx.group, &current) {
            return None;
        }
        let construction = self.next(world, ctx.group, ctx.tick, &current, rng)?;
        let origin = Origin {
            change: Some(self.kind().to_owned()),
            tick: ctx.tick,
            year: ctx.year,
            group: ctx.group,
            parent: VariantId::NONE,
        };
        let (variable, variant) = world.register_construction(&construction, &origin);
        Some(NewVariant {
            name: world.registry.variants.name(variant.0).to_owned(),
            variable,
            payload: world.variants.payload[variant.index()].clone(),
            origin: world.variants.origin[variant.index()].clone(),
        })
    }
}

/// Syntaktické změny v kanonickém pořadí.
pub fn changes() -> Vec<Box<dyn Change>> {
    [
        Step::Periphrasis,
        Step::Cliticization,
        Step::Affixation,
        Step::Exaptation,
        Step::CategoryLoss,
        Step::NegationReinforcement,
        Step::NegationReduction,
        Step::NegationRenewal,
        Step::OrderFixation,
        Step::OrderRelaxation,
        Step::Bleaching,
    ]
    .into_iter()
    .map(|step| Box::new(SyntacticChange::new(step)) as Box<dyn Change>)
    .collect()
}

//! Hledání míst inovací všech druhů změn jako jedna dávka nad čísly (krok B5b).
//!
//! `SiteIndex` drží stav tří indexů (morfologie `MorphIndex`, sémantika `SemanticIndex`
//! a syntaktická místa z konstrukcí) a jednou dávkou (`totals`) vrátí pro každou
//! skupinu a druh změny celkovou míru a počet míst. Zvukové změny mají vlastní
//! index (`index::SoundIndex`); ostatní druhy (výpůjčky, přízvuk, reanalýza hranice)
//! počítá Python výchozím postupem.
//!
//! **Sloupce výstupu** (pořadí je dohodnuté s Pythonem, `cee.v2.language.site_index`):
//! expresivní tvoření, sedm sémantických změn, vyrovnání, rozšíření, deset
//! syntaktických změn a výpůjčky slov.
//!
//! **Syntaktická místa** jsou funkce katalogu (pořadí podle jména): konstrukce, která
//! ve skupině převažuje, je číslo varianty a její druh a stupeň jsou sloupce
//! (`Constructions`). Místem změny je funkce, jejíž dominantní konstrukce změnu
//! připouští (`applies` v `changes/syntax.py`); míra je jednotná (`base × počet`),
//! jen u zániku kategorie se míra místa odvozuje od slabosti koncovky a podílu
//! druhojazyčných mluvčích a celek se sčítá párově jako `np.sum`.

use std::collections::HashMap;
use std::hash::BuildHasherDefault;

use crate::assess::pairwise_sum;
use crate::index::Fx;
use crate::morphology_index::MorphIndex;
use crate::semantic_index::{SemanticIndex, KINDS as SEMANTIC};

pub const COLUMNS: usize = 1 + SEMANTIC + 2 + SYNTAX + 1;
pub const COL_COINAGE: usize = 0;
pub const COL_SEMANTIC: usize = 1;
pub const COL_LEVELING: usize = COL_SEMANTIC + SEMANTIC;
pub const COL_EXTENSION: usize = COL_LEVELING + 1;
pub const COL_SYNTAX: usize = COL_EXTENSION + 1;
pub const COL_BORROWING: usize = COL_SYNTAX + SYNTAX;
/// Počet syntaktických změn: opis, přiklonka, srůst, exaptace, zánik kategorie,
/// posílení, zeslabení a obnova záporu, ustálení a uvolnění slovosledu.
pub const SYNTAX: usize = 10;

const PERIPHRASIS: usize = 0;
const CLITICIZATION: usize = 1;
const AFFIXATION: usize = 2;
const EXAPTATION: usize = 3;
const CATEGORY_LOSS: usize = 4;
const NEGATION_REINFORCEMENT: usize = 5;
const NEGATION_REDUCTION: usize = 6;
const NEGATION_RENEWAL: usize = 7;
const ORDER_FIXATION: usize = 8;

/// Šablona funkce katalogu.
pub const INFLECTION: u8 = 0;
pub const NEGATION: u8 = 1;
pub const ORDER: u8 = 2;
/// Šablona, kterou syntaktická změna hledá.
const TEMPLATE_OF: [u8; SYNTAX] = [
    INFLECTION, INFLECTION, INFLECTION, INFLECTION, INFLECTION, NEGATION, NEGATION, NEGATION,
    ORDER, ORDER,
];

/// Druhy konstrukcí (`Construction.kind`) a stupně opisu (`Construction.stage`).
pub const ZERO: i8 = 0;
pub const PERIPHRASTIC: i8 = 1;
pub const SYNTHETIC: i8 = 2;
pub const PRE: i8 = 3;
pub const EMBRACED: i8 = 4;
pub const POST: i8 = 5;
pub const FREE: i8 = 6;
pub const FIXED: i8 = 7;
pub const STAGE_FREE: i8 = 0;
pub const STAGE_CLITIC: i8 = 1;

type FxMap<K, V> = HashMap<K, V, BuildHasherDefault<Fx>>;

/// Katalog gramatických funkcí v pořadí jmen.
#[derive(Default)]
pub struct Catalog {
    pub count: usize,
    pub template: Vec<u8>,
    /// Slovní druh funkce: 0 žádný, 1 jméno, 2 sloveso (`GrammaticalFunction.word_class`).
    pub word_class: Vec<u8>,
    /// Číslo třídy a buňky v číslování morfémů (−1 = číslování je zatím nezná).
    pub class: Vec<i32>,
    pub cell: Vec<i32>,
    /// Má funkce buňku paradigmatu (`GrammaticalFunction.cell` není `None`)?
    pub has_cell: Vec<bool>,
    pub has_orders: Vec<bool>,
    pub coverage: Vec<f64>,
    source_start: Vec<u32>,
    sources: Vec<i32>,
    donor_start: Vec<u32>,
    donors: Vec<u32>,
    /// Pro funkci `d` seznam funkcí, které ji zastupují (`compensates`).
    deputy_start: Vec<u32>,
    deputies: Vec<u32>,
}

impl Catalog {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        template: Vec<u8>,
        word_class: Vec<u8>,
        class: Vec<i32>,
        cell: Vec<i32>,
        has_cell: Vec<bool>,
        has_orders: Vec<bool>,
        coverage: Vec<f64>,
        source_start: Vec<u32>,
        sources: Vec<i32>,
        donor_start: Vec<u32>,
        donors: Vec<u32>,
        deputy_start: Vec<u32>,
        deputies: Vec<u32>,
    ) -> Result<Catalog, String> {
        let count = template.len();
        let sized = [
            word_class.len(),
            class.len(),
            cell.len(),
            has_cell.len(),
            has_orders.len(),
            coverage.len(),
        ]
        .iter()
        .all(|&size| size == count);
        let starts = [
            (&source_start, sources.len()),
            (&donor_start, donors.len()),
            (&deputy_start, deputies.len()),
        ]
        .iter()
        .all(|(start, items)| start.len() == count + 1 && start.last() == Some(&(*items as u32)));
        if !sized || !starts {
            return Err("katalog funkcí má nesouhlasné pole".into());
        }
        Ok(Catalog {
            count,
            template,
            word_class,
            class,
            cell,
            has_cell,
            has_orders,
            coverage,
            source_start,
            sources,
            donor_start,
            donors,
            deputy_start,
            deputies,
        })
    }

    fn sources_of(&self, function: usize) -> &[i32] {
        &self.sources
            [self.source_start[function] as usize..self.source_start[function + 1] as usize]
    }

    fn donors_of(&self, function: usize) -> &[u32] {
        &self.donors[self.donor_start[function] as usize..self.donor_start[function + 1] as usize]
    }

    fn deputies_of(&self, function: usize) -> &[u32] {
        &self.deputies
            [self.deputy_start[function] as usize..self.deputy_start[function + 1] as usize]
    }
}

/// Druh a stupeň konstrukcí podle čísla varianty.
#[derive(Default)]
pub struct Constructions {
    kind: Vec<i8>,
    stage: Vec<i8>,
}

impl Constructions {
    pub fn set(&mut self, variant: usize, kind: i8, stage: i8) {
        if self.kind.len() <= variant {
            self.kind.resize(variant + 1, -1);
            self.stage.resize(variant + 1, -1);
        }
        self.kind[variant] = kind;
        self.stage[variant] = stage;
    }

    fn get(&self, variant: i32) -> Option<(i8, i8)> {
        let variant = usize::try_from(variant).ok()?;
        let kind = *self.kind.get(variant)?;
        (kind >= 0).then(|| (kind, self.stage[variant]))
    }
}

/// Místa syntaktických změn skupiny z posledního vyhodnocení.
#[derive(Default, Clone)]
struct Found {
    sites: [Vec<u32>; SYNTAX],
    rates: Vec<f64>,
}

/// Výpůjčky slov: podíl vstupu skupiny od cizích dárců podle kanálu a filtr výpůjček
/// podle kanálu a pojmu (obojí spočítá Python z kontaktu mezi jazyky).
pub struct Borrowing<'a> {
    pub channels: usize,
    /// Více kanálů s různými vahami domén: míra místa je součet přes kanály.
    pub distinct: bool,
    /// Skupina × kanál; skupina bez dárců (`donors` nepravda) výpůjčky nemá.
    pub exposure: &'a [f64],
    pub donors: &'a [bool],
    /// Kanál × číslo pojmu.
    pub factors: &'a [f64],
    pub concepts: usize,
}

/// Vstup dávky: skupiny (kódy) a jejich dnešní stav, který nenese žádný index.
pub struct Request<'a> {
    pub tokens: &'a [i64],
    /// Dominantní varianta konstrukce skupiny podle funkce katalogu (−1 = žádná).
    pub variants: &'a [i32],
    pub l2_share: &'a [f64],
    /// Počet lexikálních proměnných kódu (místa expresivního tvoření).
    pub lexical: &'a [i64],
    pub morph_on: &'a [bool],
    pub semantic_on: &'a [bool],
    /// Základní míra podle sloupce výstupu.
    pub bases: &'a [f64],
    pub coinage_scale: f64,
    pub analogy_boost: f64,
    pub loss_boost: f64,
    pub borrowing: Option<Borrowing<'a>>,
}

#[derive(Default)]
pub struct SiteIndex {
    pub morph: MorphIndex,
    pub semantic: SemanticIndex,
    pub catalog: Catalog,
    pub constructions: Constructions,
    results: FxMap<i64, Found>,
    current: Vec<Option<(i8, i8)>>,
    rates: Vec<f64>,
}

impl SiteIndex {
    pub fn new() -> SiteIndex {
        SiteIndex::default()
    }

    /// Celkové míry a počty míst: pole „skupina × sloupec“ po řádcích za sebou.
    pub fn totals(&mut self, request: &Request<'_>) -> Totals {
        let groups = request.tokens.len();
        let functions = self.catalog.count;
        let mut totals = vec![0.0; groups * COLUMNS];
        let mut counts = vec![0_i64; groups * COLUMNS];
        let uniform = |base: f64, count: i64, scale: f64| -> f64 {
            if count > 0 {
                base * count as f64 * scale
            } else {
                0.0
            }
        };
        for group in 0..groups {
            let token = request.tokens[group];
            let row = group * COLUMNS;
            let count = request.lexical[group];
            counts[row + COL_COINAGE] = count;
            totals[row + COL_COINAGE] =
                uniform(request.bases[COL_COINAGE], count, request.coinage_scale);
            if request.semantic_on[group] {
                for kind in 0..SEMANTIC {
                    let base = request.bases[COL_SEMANTIC + kind];
                    let (found, total) = self.semantic.count_total(token, kind, base);
                    counts[row + COL_SEMANTIC + kind] = found as i64;
                    totals[row + COL_SEMANTIC + kind] = total;
                }
            }
            if request.morph_on[group] {
                let (leveling, extension) = self.morph.counts(token);
                let scale = 1.0 + request.analogy_boost * request.l2_share[group];
                counts[row + COL_LEVELING] = i64::from(leveling);
                counts[row + COL_EXTENSION] = i64::from(extension);
                totals[row + COL_LEVELING] =
                    uniform(request.bases[COL_LEVELING], i64::from(leveling), scale);
                totals[row + COL_EXTENSION] =
                    uniform(request.bases[COL_EXTENSION], i64::from(extension), scale);
            }
            if let Some(borrowing) = &request.borrowing {
                if borrowing.donors[group] {
                    let (found, total) =
                        self.borrowing(token, group, borrowing, request.bases[COL_BORROWING]);
                    counts[row + COL_BORROWING] = found as i64;
                    totals[row + COL_BORROWING] = total;
                }
            }
            if functions > 0 {
                let variants = &request.variants[group * functions..(group + 1) * functions];
                let mut result = self.results.remove(&token).unwrap_or_default();
                self.syntax(token, variants, request, group, &mut result);
                for kind in 0..SYNTAX {
                    let found = result.sites[kind].len() as i64;
                    let base = request.bases[COL_SYNTAX + kind];
                    counts[row + COL_SYNTAX + kind] = found;
                    totals[row + COL_SYNTAX + kind] = if kind == CATEGORY_LOSS {
                        if found > 0 {
                            pairwise_sum(&result.rates)
                        } else {
                            0.0
                        }
                    } else {
                        uniform(base, found, 1.0)
                    };
                }
                self.results.insert(token, result);
            }
        }
        (totals, counts)
    }

    /// Počet míst výpůjček (lexikální proměnné kódu) a součet jejich měr: `base × podíl × filtr`
    /// u jednoho kanálu, `base × Σ podíl × filtr` u více kanálů; součet párový jako `np.sum`.
    fn borrowing(
        &mut self,
        token: i64,
        group: usize,
        borrowing: &Borrowing<'_>,
        base: f64,
    ) -> (usize, f64) {
        let mut rates = std::mem::take(&mut self.rates);
        rates.clear();
        let channels = borrowing.channels;
        let exposure = &borrowing.exposure[group * channels..(group + 1) * channels];
        self.semantic.for_each_site(token, |concept| {
            let at = |channel: usize| borrowing.factors[channel * borrowing.concepts + concept];
            if borrowing.distinct {
                let mut sum = 0.0;
                for (channel, &share) in exposure.iter().enumerate() {
                    sum += share * at(channel);
                }
                rates.push(base * sum);
            } else {
                rates.push(base * exposure[0] * at(0));
            }
        });
        let total = if rates.is_empty() {
            0.0
        } else {
            pairwise_sum(&rates)
        };
        let found = rates.len();
        self.rates = rates;
        (found, total)
    }

    /// Funkce, které jsou místy syntaktických změn skupiny (čísla funkcí katalogu,
    /// v pořadí jmen), a míry zániku kategorie na jejích místech.
    pub fn syntax_sites(&self, token: i64, kind: usize) -> (Vec<u32>, Vec<f64>) {
        match self.results.get(&token) {
            Some(result) => (
                result.sites[kind].clone(),
                if kind == CATEGORY_LOSS {
                    result.rates.clone()
                } else {
                    Vec::new()
                },
            ),
            None => (Vec::new(), Vec::new()),
        }
    }

    fn syntax(
        &mut self,
        token: i64,
        variants: &[i32],
        request: &Request<'_>,
        group: usize,
        result: &mut Found,
    ) {
        let mut current = std::mem::take(&mut self.current);
        current.clear();
        current.extend(
            variants
                .iter()
                .map(|&variant| self.constructions.get(variant)),
        );
        let catalog = &self.catalog;
        let dominant = self.semantic.dominant(token);
        let present = |concept: i32| -> bool {
            usize::try_from(concept)
                .ok()
                .and_then(|c| dominant.get(c))
                .is_some_and(|&root| root >= 0)
        };
        let weakness = |function: usize| -> f64 {
            if !catalog.has_cell[function] {
                return 0.0;
            }
            if catalog.word_class[function] == 0 {
                return 1.0;
            }
            self.morph
                .weakness(token, catalog.class[function], catalog.cell[function])
        };
        let sourced = |function: usize| catalog.sources_of(function).iter().any(|&c| present(c));
        // Zastoupila roli funkce jiná dominantní konstrukce (kompenzace)?
        let compensated = |function: usize| -> bool {
            let mut found = 0.0_f64;
            for &deputy in catalog.deputies_of(function) {
                let deputy = deputy as usize;
                if let Some((kind, _)) = current[deputy] {
                    let carries = if catalog.template[deputy] == ORDER {
                        kind == FIXED
                    } else {
                        kind != ZERO
                    };
                    if carries {
                        found = found.max(catalog.coverage[deputy]);
                    }
                }
            }
            found > 0.0
        };
        let residual = |donor: usize| -> bool {
            catalog.word_class[donor] != 0
                && catalog.has_cell[donor]
                && self
                    .morph
                    .residual(token, catalog.class[donor], catalog.cell[donor])
                    >= 0
        };
        let donors_found = |function: usize| -> bool {
            catalog.donors_of(function).iter().any(|&donor| {
                let donor = donor as usize;
                catalog.word_class[donor] == catalog.word_class[function]
                    && compensated(donor)
                    && residual(donor)
            })
        };
        let pressure = |function: usize, kind: i8, stage: i8| -> f64 {
            if kind == PERIPHRASTIC && stage == STAGE_FREE {
                return 1.0;
            }
            let bound = kind == SYNTHETIC || (kind == PERIPHRASTIC && stage == STAGE_CLITIC);
            if !bound {
                return 0.0;
            }
            let unreliable = if kind == SYNTHETIC {
                weakness(function)
            } else {
                0.0
            };
            unreliable + request.loss_boost * request.l2_share[group]
        };
        for sites in &mut result.sites {
            sites.clear();
        }
        result.rates.clear();
        for (function, found) in current.iter().enumerate() {
            let Some((kind, stage)) = *found else {
                continue;
            };
            for (change, &template) in TEMPLATE_OF.iter().enumerate() {
                if catalog.template[function] != template {
                    continue;
                }
                let applies = match change {
                    PERIPHRASIS => {
                        let allowed = match kind {
                            SYNTHETIC => weakness(function) != 0.0,
                            ZERO => true,
                            _ => false,
                        };
                        allowed && sourced(function)
                    }
                    CLITICIZATION => kind == PERIPHRASTIC && stage == STAGE_FREE,
                    AFFIXATION => kind == PERIPHRASTIC && stage == STAGE_CLITIC,
                    EXAPTATION => kind == ZERO && donors_found(function),
                    CATEGORY_LOSS => pressure(function, kind, stage) > 0.0,
                    NEGATION_REINFORCEMENT => kind == PRE && sourced(function),
                    NEGATION_REDUCTION => kind == EMBRACED,
                    NEGATION_RENEWAL => kind == POST,
                    ORDER_FIXATION => kind == FREE && catalog.has_orders[function],
                    _ => kind == FIXED,
                };
                if !applies {
                    continue;
                }
                result.sites[change].push(function as u32);
                if change == CATEGORY_LOSS {
                    // Míra místa: `base × tlak`, kde tlak je 1 u volného opisu, jinak
                    // slabost koncovky (jen syntetický výraz) plus podíl druhojazyčných.
                    result.rates.push(
                        request.bases[COL_SYNTAX + CATEGORY_LOSS] * pressure(function, kind, stage),
                    );
                }
            }
        }
        self.current = current;
    }
}

/// Dvojice (součty, počty) výstupu dávky.
pub type Totals = (Vec<f64>, Vec<i64>);

#[cfg(test)]
mod tests {
    use super::*;

    fn catalog() -> Catalog {
        // Funkce 0 (jméno, inflection, buňka 1), 1 (záporka, negation).
        Catalog::new(
            vec![INFLECTION, NEGATION],
            vec![1, 0],
            vec![0, -1],
            vec![1, -1],
            vec![true, false],
            vec![false, false],
            vec![0.0, 0.0],
            vec![0, 1, 2],
            vec![5, 5],
            vec![0, 0, 0],
            vec![],
            vec![0, 0, 0],
            vec![],
        )
        .expect("katalog")
    }

    #[test]
    fn opis_a_zanik_kategorie_podle_konstrukci() {
        let mut index = SiteIndex::new();
        index.catalog = catalog();
        index.constructions.set(0, ZERO, -1);
        index.constructions.set(1, PERIPHRASTIC, STAGE_FREE);
        index.constructions.set(2, PRE, -1);
        // Kód s dominantním kořenem pro pojem 5 (zdroj gramatikalizace).
        index
            .semantic
            .concepts
            .extend(&["a", "b", "c", "d", "e", "f"]);
        let dominant = [-1, -1, -1, -1, -1, 3];
        let input = crate::semantic_index::Input {
            token: 9,
            dominant: &dominant,
            sites: &[],
            taboo: &[],
            suffix: false,
        };
        index.semantic.set_roots(&[3], &[-1], &[-1]);
        index.semantic.sync(&input).expect("sync");
        let mut bases = [0.0; COLUMNS];
        bases[COL_SYNTAX + PERIPHRASIS] = 0.05;
        bases[COL_SYNTAX + CATEGORY_LOSS] = 0.02;
        bases[COL_SYNTAX + NEGATION_REINFORCEMENT] = 0.03;
        let variants = [0, 2];
        let request = Request {
            tokens: &[9],
            variants: &variants,
            l2_share: &[0.0],
            lexical: &[0],
            morph_on: &[false],
            semantic_on: &[false],
            bases: &bases,
            coinage_scale: 1.0,
            analogy_boost: 0.0,
            loss_boost: 1.0,
            borrowing: None,
        };
        let (totals, counts) = index.totals(&request);
        // Funkce 0 bez koncovky a se zdrojem: opis; záporka před slovesem: posílení.
        assert_eq!(counts[COL_SYNTAX + PERIPHRASIS], 1);
        assert_eq!(totals[COL_SYNTAX + PERIPHRASIS], 0.05);
        assert_eq!(counts[COL_SYNTAX + NEGATION_REINFORCEMENT], 1);
        assert_eq!(counts[COL_SYNTAX + CATEGORY_LOSS], 0);
        // Volný opis zanikne se základní mírou.
        let variants = [1, 2];
        let request = Request {
            variants: &variants,
            ..request
        };
        let (totals, counts) = index.totals(&request);
        assert_eq!(counts[COL_SYNTAX + CLITICIZATION], 1);
        assert_eq!(counts[COL_SYNTAX + CATEGORY_LOSS], 1);
        assert_eq!(totals[COL_SYNTAX + CATEGORY_LOSS], 0.02);
    }
}

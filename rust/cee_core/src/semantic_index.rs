//! Sémantické závislosti a místa sémantických změn na číslech: zrcadlo
//! `cee.v2.language.semantic_index` (`SemanticDependencies`, `SemanticSitesIndex`).
//!
//! Místem sémantické změny je pojem, který má kód mezi lexikálními proměnnými
//! (`site`), a míra místa je `base_rate × součet vah cest k pojmu`. Cesty (možnosti)
//! plynou z grafu pojmů (vztahy vedoucí do pojmu, recepty složenin), z dominantních
//! kořenů kódu (číslo kořene podle čísla pojmu, −1 = žádný), z tabu skupiny a
//! z několika vlastností kořenů (odvozenina, základ). Graf a vlastnosti vztahů
//! (váhy, které by potřebovaly `log1p`, shodnost slovních druhů) předá Python
//! předem spočítané, takže tu není žádná transcendentní funkce a součty vah jsou
//! prosté součty v pořadí vztahů jako v Pythonu (`sum` od nuly).
//!
//! **Přírůstkově.** Změna dominantního kořene pojmu dotkne jen pojmů, které na něm
//! závisí (sám pojem, cíle jeho vztahů a složenin, pojem, ze kterého je odvozen
//! starý či nový kořen); ty se přepočítají pro všechny druhy změn. Změna grafu,
//! tabu, přípony či množiny míst přepočítá vše. Výsledek je čistá funkce stavu, takže
//! se vždy shoduje s úplným přepočtem.
//!
//! **Pořadí míst** je pořadí jmen pojmů (`lexical:pojem`), míry se sčítají párově
//! (`pairwise_sum`) jen přes místa, v tomto pořadí, jako `np.sum` v Pythonu.

use crate::assess::pairwise_sum;
use crate::morphology_index::{FxMap, Names};

/// Počet druhů sémantických změn a jejich pořadí: posun, konverze, odvození,
/// složenina, opis za tabu, kontaminace, zpětné tvoření.
pub const KINDS: usize = 7;
const SHIFT: usize = 0;
const CONVERSION: usize = 1;
const DERIVATION: usize = 2;
const COMPOUNDING: usize = 3;
const TABOO: usize = 4;
const CONTAMINATION: usize = 5;
const BACK_FORMATION: usize = 6;

/// Příznaky vztahu.
pub const COMPATIBLE: u8 = 1;
pub const POLYSEMOUS: u8 = 2;
pub const COLEXIFIED: u8 = 4;

/// Vlastnost kořene dosud neznámá (doplní Python).
const UNKNOWN: i32 = -2;

/// Graf pojmů v řídkých řádcích podle cíle (CSR). Vztahy každého cíle jsou
/// seřazené podle jména zdroje (jak je dává `ConceptGraph.into`).
#[derive(Default)]
pub struct Graph {
    pub concepts: usize,
    into_start: Vec<u32>,
    source: Vec<i32>,
    shift: Vec<f64>,
    conversion: Vec<f64>,
    derivation: Vec<f64>,
    flags: Vec<u8>,
    compound_start: Vec<u32>,
    left: Vec<i32>,
    right: Vec<i32>,
    /// Pojmy, které se mění s dominantním kořenem pojmu (řádek podle zdroje).
    out_start: Vec<u32>,
    out_items: Vec<u32>,
}

impl Graph {
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        concepts: usize,
        into_start: Vec<u32>,
        source: Vec<i32>,
        shift: Vec<f64>,
        conversion: Vec<f64>,
        derivation: Vec<f64>,
        flags: Vec<u8>,
        compound_start: Vec<u32>,
        left: Vec<i32>,
        right: Vec<i32>,
    ) -> Result<Graph, String> {
        let relations = source.len();
        let compounds = left.len();
        if into_start.len() != concepts + 1
            || compound_start.len() != concepts + 1
            || into_start.last().copied() != Some(relations as u32)
            || compound_start.last().copied() != Some(compounds as u32)
            || [shift.len(), conversion.len(), derivation.len(), flags.len()]
                .iter()
                .any(|&size| size != relations)
            || right.len() != compounds
        {
            return Err("graf pojmů má nesouhlasné pole".into());
        }
        let mut pairs: Vec<(u32, u32)> = Vec::new();
        for target in 0..concepts {
            for relation in into_start[target]..into_start[target + 1] {
                if let Ok(from) = u32::try_from(source[relation as usize]) {
                    pairs.push((from, target as u32));
                }
            }
            for item in compound_start[target]..compound_start[target + 1] {
                for part in [left[item as usize], right[item as usize]] {
                    if let Ok(from) = u32::try_from(part) {
                        pairs.push((from, target as u32));
                    }
                }
            }
        }
        pairs.sort_unstable();
        pairs.dedup();
        let mut out_start = vec![0_u32; concepts + 2];
        for &(from, _) in &pairs {
            if (from as usize) < concepts {
                out_start[from as usize + 1] += 1;
            }
        }
        for at in 0..=concepts {
            out_start[at + 1] += out_start[at];
        }
        out_start.truncate(concepts + 1);
        let out_items = pairs
            .iter()
            .filter(|(from, _)| (*from as usize) < concepts)
            .map(|&(_, to)| to)
            .collect();
        Ok(Graph {
            concepts,
            into_start,
            source,
            shift,
            conversion,
            derivation,
            flags,
            compound_start,
            left,
            right,
            out_start,
            out_items,
        })
    }

    fn relations(&self, target: usize) -> std::ops::Range<usize> {
        if target >= self.concepts {
            return 0..0;
        }
        self.into_start[target] as usize..self.into_start[target + 1] as usize
    }

    fn compounds(&self, target: usize) -> std::ops::Range<usize> {
        if target >= self.concepts {
            return 0..0;
        }
        self.compound_start[target] as usize..self.compound_start[target + 1] as usize
    }

    fn affected(&self, source: usize) -> &[u32] {
        if source >= self.concepts {
            return &[];
        }
        &self.out_items[self.out_start[source] as usize..self.out_start[source + 1] as usize]
    }
}

/// Stav jednoho kódu.
#[derive(Default)]
struct Slot {
    synced: bool,
    graph_version: u64,
    suffix: bool,
    dominant: Vec<i32>,
    site: Vec<bool>,
    taboo: Vec<bool>,
    /// Součet vah cest podle pojmu pro každý druh změny (0 = pojem není místem).
    sum: [Vec<f64>; KINDS],
    /// Pojmy, ze kterých je (dnešním dominantním kořenem pojmu `o`) odvozen kořen:
    /// pro pojem `t` seznam pojmů `o`, jejichž kořen vznikl odvozením z `t`.
    derived_start: Vec<u32>,
    derived_items: Vec<u32>,
    /// Míry míst a jejich součet pro základní míru, se kterou se naposledy počítaly.
    compact: [Vec<f64>; KINDS],
    total: [f64; KINDS],
    base: [f64; KINDS],
    ready: [bool; KINDS],
}

/// Vstup jednoho kódu pro dorovnání.
pub struct Input<'a> {
    pub token: i64,
    /// Dominantní kořen podle čísla pojmu (−1 = žádný).
    pub dominant: &'a [i32],
    /// Čísla pojmů lexikálních proměnných kódu.
    pub sites: &'a [i32],
    /// Čísla pojmů tabu skupiny.
    pub taboo: &'a [i32],
    pub suffix: bool,
}

#[derive(Default)]
pub struct SemanticIndex {
    pub concepts: Names,
    pub graph: Graph,
    pub graph_version: u64,
    /// Pojmy seřazené podle jména a jejich pořadí.
    by_name: Vec<u32>,
    sorted_for: usize,
    /// Vlastnosti kořenů podle čísla morfému: pojem, ze kterého je kořen odvozen
    /// (−1 = není odvozenina z jediného pojmu), a číslo základu (−1 = žádný).
    root_source: Vec<i32>,
    root_base: Vec<i32>,
    /// Je kořen sloveso (`Morpheme.word_class == "verb"`)? Podle čísla morfému.
    root_verb: Vec<bool>,
    slots: Vec<Slot>,
    by_token: FxMap<i64, usize>,
    scratch: Vec<u32>,
    marks: Vec<bool>,
}

impl SemanticIndex {
    pub fn new() -> SemanticIndex {
        SemanticIndex::default()
    }

    pub fn set_graph(&mut self, graph: Graph) {
        self.graph = graph;
        self.graph_version += 1;
    }

    /// Doplní vlastnosti kořenů (číslo morfému, pojem zdroje odvozeniny, základ, zda je sloveso).
    pub fn set_roots(&mut self, numbers: &[u32], sources: &[i32], bases: &[i32], verbs: &[bool]) {
        for (at, &number) in numbers.iter().enumerate() {
            let number = number as usize;
            if self.root_source.len() <= number {
                self.root_source.resize(number + 1, UNKNOWN);
                self.root_base.resize(number + 1, UNKNOWN);
                self.root_verb.resize(number + 1, false);
            }
            self.root_source[number] = sources[at];
            self.root_base[number] = bases[at];
            self.root_verb[number] = verbs[at];
        }
    }

    /// Je kořen sloveso? (Neznámý kořen není.)
    pub fn is_verb(&self, root: i32) -> bool {
        usize::try_from(root)
            .ok()
            .and_then(|root| self.root_verb.get(root))
            .copied()
            .unwrap_or(false)
    }

    fn slot_of(&mut self, token: i64) -> usize {
        if let Some(&found) = self.by_token.get(&token) {
            return found;
        }
        self.slots.push(Slot::default());
        let found = self.slots.len() - 1;
        self.by_token.insert(token, found);
        found
    }

    fn slot(&self, token: i64) -> Option<&Slot> {
        self.by_token.get(&token).map(|&found| &self.slots[found])
    }

    fn known(&self, root: i32) -> bool {
        root < 0
            || self
                .root_source
                .get(root as usize)
                .is_some_and(|&s| s != UNKNOWN)
    }

    fn source_of(&self, root: i32) -> i32 {
        if root < 0 {
            -1
        } else {
            self.root_source
                .get(root as usize)
                .copied()
                .unwrap_or(-1)
                .max(-1)
        }
    }

    fn base_of(&self, root: i32) -> i32 {
        if root < 0 {
            -1
        } else {
            self.root_base.get(root as usize).copied().unwrap_or(-1)
        }
    }

    /// Dorovná kód. Vrací čísla kořenů, jejichž vlastnosti Python ještě nedodal
    /// (nic se pak nezměnilo, volající je doplní a zavolá znovu).
    pub fn sync(&mut self, input: &Input<'_>) -> Result<Vec<u32>, String> {
        let concepts = self.graph.concepts.max(self.concepts.len());
        if input.dominant.len() > concepts {
            return Err("dominantní kořeny jsou delší než číslování pojmů".into());
        }
        if self.sorted_for != self.concepts.len() {
            let names = &self.concepts;
            self.by_name = (0..names.len() as u32).collect();
            self.by_name
                .sort_by(|&a, &b| names.get(a as usize).cmp(names.get(b as usize)));
            self.sorted_for = names.len();
        }
        let at = self.slot_of(input.token);
        // Nový pohled na kód: dominantní kořeny dorovnané na počet pojmů.
        let mut dominant = vec![-1_i32; concepts];
        dominant[..input.dominant.len()].copy_from_slice(input.dominant);
        let mut site = vec![false; concepts];
        for &concept in input.sites {
            if let Some(slot) = usize::try_from(concept).ok().and_then(|c| site.get_mut(c)) {
                *slot = true;
            }
        }
        let mut taboo = vec![false; concepts];
        for &concept in input.taboo {
            if let Some(slot) = usize::try_from(concept).ok().and_then(|c| taboo.get_mut(c)) {
                *slot = true;
            }
        }
        let mut marks = std::mem::take(&mut self.marks);
        let mut dirty = std::mem::take(&mut self.scratch);
        marks.clear();
        marks.resize(concepts, false);
        dirty.clear();
        let slot = &self.slots[at];
        let reset = !slot.synced
            || slot.graph_version != self.graph_version
            || slot.suffix != input.suffix
            || slot.dominant.len() != concepts
            || slot.taboo != taboo
            || slot.site != site;
        // Změněné dominantní kořeny a jejich vlastnosti.
        let mut needs: Vec<u32> = Vec::new();
        let mut changed: Vec<usize> = Vec::new();
        for (concept, &now) in dominant.iter().enumerate() {
            let old = if reset { -1 } else { slot.dominant[concept] };
            if reset || old != now {
                changed.push(concept);
                for root in [old, now] {
                    if !self.known(root) {
                        needs.push(root as u32);
                    }
                }
            }
        }
        if !needs.is_empty() {
            needs.sort_unstable();
            needs.dedup();
            self.marks = marks;
            self.scratch = dirty;
            return Ok(needs);
        }
        // Dotčené pojmy.
        if reset {
            dirty.extend(0..concepts as u32);
        } else {
            let mut mark = |concept: usize, dirty: &mut Vec<u32>| {
                if concept < concepts && !marks[concept] {
                    marks[concept] = true;
                    dirty.push(concept as u32);
                }
            };
            for &concept in &changed {
                mark(concept, &mut dirty);
                for &target in self.graph.affected(concept) {
                    mark(target as usize, &mut dirty);
                }
                for root in [slot.dominant[concept], dominant[concept]] {
                    let source = self.source_of(root);
                    if source >= 0 {
                        mark(source as usize, &mut dirty);
                    }
                }
            }
        }
        // Zpětné tvoření: pojmy, jejichž dominantní kořen je odvozenina z daného pojmu.
        let mut counts = vec![0_u32; concepts + 1];
        for &root in &dominant {
            let source = self.source_of(root);
            if source >= 0 && (source as usize) < concepts {
                counts[source as usize + 1] += 1;
            }
        }
        for at in 0..concepts {
            counts[at + 1] += counts[at];
        }
        let mut fill = counts.clone();
        let mut items = vec![0_u32; counts[concepts] as usize];
        for (concept, &root) in dominant.iter().enumerate() {
            let source = self.source_of(root);
            if source >= 0 && (source as usize) < concepts {
                items[fill[source as usize] as usize] = concept as u32;
                fill[source as usize] += 1;
            }
        }
        let weights = {
            let view = Evaluator {
                index: self,
                dominant: &dominant,
                taboo: &taboo,
                suffix: input.suffix,
                derived_start: &counts,
                derived_items: &items,
            };
            let mut sums: Vec<[f64; KINDS]> = Vec::with_capacity(dirty.len());
            for &concept in &dirty {
                let mut row = [0.0; KINDS];
                for (kind, value) in row.iter_mut().enumerate() {
                    *value = view.sum(kind, concept as usize);
                }
                sums.push(row);
            }
            sums
        };
        let slot = &mut self.slots[at];
        for sums in &mut slot.sum {
            sums.resize(concepts, 0.0);
        }
        for (position, &concept) in dirty.iter().enumerate() {
            for (sums, &weight) in slot.sum.iter_mut().zip(&weights[position]) {
                sums[concept as usize] = weight;
            }
        }
        slot.dominant = dominant;
        slot.site = site;
        slot.taboo = taboo;
        slot.suffix = input.suffix;
        slot.graph_version = self.graph_version;
        slot.derived_start = counts;
        slot.derived_items = items;
        slot.ready = [false; KINDS];
        slot.synced = true;
        self.scratch = dirty;
        self.marks = marks;
        Ok(Vec::new())
    }

    fn prepare(&mut self, token: i64, kind: usize, base: f64) {
        let Some(&at) = self.by_token.get(&token) else {
            return;
        };
        let slot = &mut self.slots[at];
        if slot.ready[kind] && slot.base[kind] == base {
            return;
        }
        let compact = &mut slot.compact[kind];
        compact.clear();
        for &concept in &self.by_name {
            let concept = concept as usize;
            if concept < slot.site.len() && slot.site[concept] && slot.sum[kind][concept] > 0.0 {
                compact.push(base * slot.sum[kind][concept]);
            }
        }
        slot.total[kind] = pairwise_sum(compact);
        slot.base[kind] = base;
        slot.ready[kind] = true;
    }

    /// Součet měr míst druhu změny (0, když kód místa nemá) při základní míře `base`.
    pub fn total(&mut self, token: i64, kind: usize, base: f64) -> f64 {
        self.prepare(token, kind, base);
        self.slot(token).map_or(0.0, |s| {
            if s.compact[kind].is_empty() {
                0.0
            } else {
                s.total[kind]
            }
        })
    }

    /// Počet míst a součet jejich měr při základní míře `base`.
    pub fn count_total(&mut self, token: i64, kind: usize, base: f64) -> (usize, f64) {
        self.prepare(token, kind, base);
        self.slot(token)
            .map_or((0, 0.0), |s| (s.compact[kind].len(), s.total[kind]))
    }

    /// Míry míst v pořadí jmen pojmů.
    pub fn rates(&mut self, token: i64, kind: usize, base: f64) -> Vec<f64> {
        self.prepare(token, kind, base);
        self.slot(token)
            .map_or_else(Vec::new, |s| s.compact[kind].clone())
    }

    /// Čísla pojmů míst v pořadí jmen pojmů.
    pub fn sites(&self, token: i64, kind: usize) -> Vec<u32> {
        let Some(slot) = self.slot(token) else {
            return Vec::new();
        };
        self.by_name
            .iter()
            .copied()
            .filter(|&concept| {
                let concept = concept as usize;
                concept < slot.site.len() && slot.site[concept] && slot.sum[kind][concept] > 0.0
            })
            .collect()
    }

    /// Zavolá `visit` pro pojem každého místa kódu (lexikální proměnné) v pořadí jmen pojmů.
    pub fn for_each_site(&self, token: i64, mut visit: impl FnMut(usize)) {
        let Some(slot) = self.slot(token) else {
            return;
        };
        for &concept in &self.by_name {
            let concept = concept as usize;
            if concept < slot.site.len() && slot.site[concept] {
                visit(concept);
            }
        }
    }

    /// Dominantní kořeny, které index započítal (pro syntax a testy).
    pub fn dominant(&self, token: i64) -> &[i32] {
        self.slot(token).map_or(&[], |s| &s.dominant)
    }
}

/// Počítá součty vah cest podle stavu kódu (čistá funkce).
struct Evaluator<'a> {
    index: &'a SemanticIndex,
    dominant: &'a [i32],
    taboo: &'a [bool],
    suffix: bool,
    derived_start: &'a [u32],
    derived_items: &'a [u32],
}

impl Evaluator<'_> {
    fn root(&self, concept: i32) -> i32 {
        usize::try_from(concept)
            .ok()
            .and_then(|c| self.dominant.get(c))
            .copied()
            .unwrap_or(-1)
    }

    /// Součet vah cest ke pojmu `target` (po vztazích v pořadí, od nuly), 0 bez cest.
    fn sum(&self, kind: usize, target: usize) -> f64 {
        let graph = &self.index.graph;
        let current = self.dominant.get(target).copied().unwrap_or(-1);
        let mut total = 0.0;
        match kind {
            SHIFT | CONVERSION | DERIVATION | TABOO | CONTAMINATION => {
                if kind == DERIVATION && !self.suffix {
                    return 0.0;
                }
                if kind == CONTAMINATION && current < 0 {
                    return 0.0;
                }
                if kind == TABOO && !self.taboo.get(target).copied().unwrap_or(false) {
                    return 0.0;
                }
                let mut found = false;
                for relation in graph.relations(target) {
                    let source = self.root(graph.source[relation]);
                    let flags = graph.flags[relation];
                    let weight = match kind {
                        SHIFT => {
                            if source < 0
                                || source == current
                                || flags & COMPATIBLE == 0
                                || graph.shift[relation] <= 0.0
                            {
                                continue;
                            }
                            graph.shift[relation]
                        }
                        CONVERSION => {
                            if source < 0 || flags & COMPATIBLE != 0 || flags & POLYSEMOUS == 0 {
                                continue;
                            }
                            graph.conversion[relation]
                        }
                        DERIVATION => {
                            if source < 0 || graph.derivation[relation] <= 0.0 {
                                continue;
                            }
                            graph.derivation[relation]
                        }
                        TABOO => {
                            if source < 0 || source == current {
                                continue;
                            }
                            1.0
                        }
                        _ => {
                            if source < 0 || source == current || flags & COLEXIFIED == 0 {
                                continue;
                            }
                            1.0
                        }
                    };
                    found = true;
                    total += weight;
                }
                if kind == TABOO && !found {
                    // Bez příbuzného slova se hledá nový opis: jediná cesta.
                    total += 1.0;
                }
                total
            }
            COMPOUNDING => {
                for item in graph.compounds(target) {
                    if self.root(graph.left[item]) >= 0 && self.root(graph.right[item]) >= 0 {
                        total += 1.0;
                    }
                }
                total
            }
            BACK_FORMATION => {
                let start = self.derived_start[target] as usize;
                let end = self.derived_start[target + 1] as usize;
                for &other in &self.derived_items[start..end] {
                    let root = self.dominant[other as usize];
                    if other as usize != target && current != self.index.base_of(root) {
                        total += 1.0;
                    }
                }
                total
            }
            _ => 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Pojmy 0 (voda), 1 (oheň), 2 (déšť); vztah 0 → 1 se slovními druhy shodnými.
    fn index() -> SemanticIndex {
        let mut index = SemanticIndex::new();
        index.concepts.extend(&["fire", "rain", "water"]);
        // Cíl 0 (fire) má jeden vztah ze zdroje 2 (water); cíl 1 (rain) ho nemá.
        // Recept: déšť = oheň + voda (cíl 1).
        let graph = Graph::new(
            3,
            vec![0, 1, 1, 1],
            vec![2],
            vec![0.7],
            vec![0.0],
            vec![0.0],
            vec![COMPATIBLE],
            vec![0, 0, 1, 1],
            vec![0],
            vec![2],
        )
        .expect("graf");
        index.set_graph(graph);
        index
    }

    #[test]
    fn posun_a_slozenina_podle_dominantnich_korenu() {
        let mut index = index();
        let input = Input {
            token: 1,
            dominant: &[10, -1, 11],
            sites: &[0, 1, 2],
            taboo: &[],
            suffix: false,
        };
        assert!(!index.sync(&input).expect("sync").is_empty());
        index.set_roots(&[10, 11], &[-1, -1], &[-1, -1], &[false, false]);
        assert!(index.sync(&input).expect("sync").is_empty());
        // Posun na „oheň“: zdroj „voda“ má kořen jiný než oheň.
        assert_eq!(index.sites(1, SHIFT), vec![0]);
        assert_eq!(index.rates(1, SHIFT, 0.5), vec![0.5 * 0.7]);
        // Složenina „déšť“ má obě části.
        assert_eq!(index.sites(1, COMPOUNDING), vec![1]);
        assert_eq!(index.total(1, COMPOUNDING, 0.25), 0.25);
        // Voda ztratí kořen: posun i složenina zaniknou.
        let input = Input {
            dominant: &[10, -1, -1],
            ..input
        };
        assert!(index.sync(&input).expect("sync").is_empty());
        assert!(index.sites(1, SHIFT).is_empty());
        assert!(index.sites(1, COMPOUNDING).is_empty());
        assert_eq!(index.total(1, SHIFT, 0.5), 0.0);
    }
}

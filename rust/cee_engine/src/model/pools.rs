//! Živé fondy: proměnné, ve kterých se skupiny liší (zrcadlo `cee.v2.pools`).
//!
//! Repertoáry skupin jsou výhodné pro ukládání, přenos ale potřebuje jednu proměnnou
//! přes všechny skupiny naráz. Proměnné, ve kterých se skupiny liší, proto tvoří bloky
//! o tvaru (proměnné, skupiny, sloty); slot je místo pro jednu variantu. Uložení je
//! **řídké po variantách** (`cee_core::pools::Cells`: pro každý řádek a slot seřazené
//! buňky skupin s podílem a trendovou základnou); hustý pohled
//! ([`PoolBlock::dense`]) vzniká jen na dobu jednoho kroku. Proměnné se dělí do bloků
//! podle potřebné kapacity slotů (2, 4, 8, …).
//!
//! Slot drží **číslo varianty** (`VariantId::NONE` = prázdný slot). Jediné čtení stavu
//! skupiny je [`crate::world::World::distribution`].

use std::collections::{BTreeMap, HashMap};

use cee_core::pools::Cells;
use rayon::prelude::*;
use serde::{Deserialize, Serialize};

use crate::ids::{GroupId, Numbering, VariableId, VariantId};
use crate::model::repertoire::Distribution;
use crate::rng::{stable_int, Part};

const MIN_CAPACITY: usize = 2;

/// Řádek (proměnná) odebraný z bloku nebo připravený k vložení.
pub struct Row {
    pub variable: VariableId,
    /// Hustě `skupiny × šířka` (šířka = počet slotů řádku).
    pub freqs: Vec<f64>,
    pub previous: Vec<f64>,
    pub present: Vec<bool>,
    pub slots: Vec<VariantId>,
    pub keys: Vec<u64>,
}

/// Proměnné se stejnou kapacitou slotů.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PoolBlock {
    pub capacity: usize,
    pub groups: usize,
    pub variables: Vec<VariableId>,
    /// Varianty ve slotech po řádcích (`capacity` slotů na řádek).
    pub slots: Vec<Vec<VariantId>>,
    /// Má skupina (sloupec) proměnnou? Po řádcích.
    pub present: Vec<Vec<bool>>,
    /// Klíče variant pro hashovaný drift, po řádcích a slotech.
    pub keys: Vec<Vec<u64>>,
    #[serde(with = "cells_serde")]
    pub cells: Cells,
    /// Roste s každou změnou řádků a slotů; podle něj si fáze zneplatňují popisy řádků.
    pub layout: u64,
    /// Řádek proměnné (rejstřík k `variables`); po načtení ze zálohy prázdný, pak se hledá
    /// lineárně.
    #[serde(skip)]
    rows: HashMap<VariableId, usize>,
}

mod cells_serde {
    use cee_core::pools::Cells;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    type Flat = (
        usize,
        usize,
        Vec<i64>,
        Vec<i16>,
        Vec<i32>,
        Vec<f64>,
        Vec<f64>,
    );

    pub fn serialize<S: Serializer>(cells: &Cells, serializer: S) -> Result<S::Ok, S::Error> {
        let (pointer, slot, group, freq, prev) = cells.to_flat();
        let flat: Flat = (
            cells.groups,
            cells.capacity,
            pointer,
            slot,
            group,
            freq,
            prev,
        );
        flat.serialize(serializer)
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<Cells, D::Error> {
        let (groups, capacity, pointer, slot, group, freq, prev) = Flat::deserialize(deserializer)?;
        Ok(Cells::from_flat(
            groups, capacity, &pointer, &slot, &group, &freq, &prev,
        ))
    }
}

impl PoolBlock {
    pub fn new(groups: usize, capacity: usize) -> PoolBlock {
        PoolBlock {
            capacity,
            groups,
            variables: Vec::new(),
            slots: Vec::new(),
            present: Vec::new(),
            keys: Vec::new(),
            cells: Cells::new(groups, capacity),
            layout: 0,
            rows: HashMap::new(),
        }
    }

    pub fn len(&self) -> usize {
        self.variables.len()
    }

    pub fn is_empty(&self) -> bool {
        self.variables.is_empty()
    }

    pub fn row_of(&self, variable: VariableId) -> Option<usize> {
        if self.rows.len() == self.variables.len() {
            return self.rows.get(&variable).copied();
        }
        self.variables.iter().position(|&v| v == variable)
    }

    /// Hustý pohled `řádky × skupiny × kapacita` (podíly, základny) – jen na dobu kroku.
    pub fn dense(&self) -> (Vec<f64>, Vec<f64>) {
        let size = self.len() * self.groups * self.capacity;
        let (mut freqs, mut previous) = (vec![0.0; size], vec![0.0; size]);
        self.cells.dense(&mut freqs, &mut previous);
        (freqs, previous)
    }

    /// Hustý pohled jen pro vybrané řádky `selected`: `(freqs, present)` o tvaru
    /// `selected.len() × groups × capacity` a `selected.len() × groups`.
    pub fn dense_selected(&self, selected: &[usize]) -> (Vec<f64>, Vec<bool>) {
        let stride = self.groups * self.capacity;
        let mut freqs = vec![0.0; selected.len() * stride];
        let mut scratch = vec![0.0; stride];
        let mut present = Vec::with_capacity(selected.len() * self.groups);
        for (out_row, &row) in selected.iter().enumerate() {
            scratch.fill(0.0);
            self.cells.row_dense(
                row,
                &mut freqs[out_row * stride..(out_row + 1) * stride],
                &mut scratch,
            );
            present.extend_from_slice(&self.present[row]);
        }
        (freqs, present)
    }

    /// Přidá řádek; jeho pole mají `skupiny × šířka` s šířkou ≤ kapacita.
    pub fn append(&mut self, row: Row) {
        let width = row.slots.len();
        debug_assert!(width <= self.capacity);
        let mut slots = row.slots;
        slots.resize(self.capacity, VariantId::NONE);
        let mut keys = row.keys;
        keys.resize(self.capacity, 0);
        if self.rows.len() == self.variables.len() {
            self.rows.insert(row.variable, self.variables.len());
        }
        self.variables.push(row.variable);
        self.slots.push(slots);
        self.present.push(row.present);
        self.keys.push(keys);
        self.cells.append_dense(&row.freqs, &row.previous, width);
        self.layout += 1;
    }

    /// Vyjme řádky (kopie obsahu) a nahradí je posledními jako `swap_remove`.
    pub fn extract(&mut self, rows: &[usize]) -> Vec<Row> {
        let mut taken = Vec::new();
        for &row in rows {
            let (mut f, mut p) = (
                vec![0.0; self.groups * self.capacity],
                vec![0.0; self.groups * self.capacity],
            );
            self.cells.row_dense(row, &mut f, &mut p);
            taken.push(Row {
                variable: self.variables[row],
                freqs: f,
                previous: p,
                present: self.present[row].clone(),
                slots: self.slots[row].clone(),
                keys: self.keys[row].clone(),
            });
        }
        let mut order = rows.to_vec();
        order.sort_unstable_by(|a, b| b.cmp(a));
        let indexed = self.rows.len() == self.variables.len();
        for row in order {
            if indexed {
                self.rows.remove(&self.variables[row]);
                if let Some(&last) = self.variables.last() {
                    if row + 1 < self.variables.len() {
                        self.rows.insert(last, row);
                    }
                }
            }
            self.variables.swap_remove(row);
            self.slots.swap_remove(row);
            self.present.swap_remove(row);
            self.keys.swap_remove(row);
            self.cells.swap_remove(row);
        }
        self.layout += 1;
        taken
    }

    /// Sloty s kladným podílem u jedné skupiny: (slot, podíl, základna).
    pub fn cell(&self, row: usize, column: usize) -> Vec<(usize, f64, f64)> {
        self.cells.rows[row].cell(column)
    }

    /// Mapa rozšíření varianty ve slotu: sloupce skupin a podíly.
    pub fn range_of(&self, row: usize, slot: usize) -> (Vec<i64>, Vec<f64>) {
        self.cells.rows[row].range_of(slot)
    }

    /// Nová varianta ve slotu u jedné skupiny: ostatní podíly se zmenší, základna se vyrovná.
    pub fn add_share(&mut self, row: usize, column: usize, slot: usize, share: f64) {
        let capacity = self.capacity;
        self.cells.rows[row].add_share(column, slot, share, capacity);
    }

    fn free_slots(&mut self, row: usize, freed: &[usize]) {
        let capacity = self.capacity;
        for &slot in freed {
            self.slots[row][slot] = VariantId::NONE;
            self.keys[row][slot] = 0;
        }
        self.cells.rows[row].free_slots(freed, capacity);
        self.layout += 1;
    }
}

fn capacity_for(slots: usize) -> usize {
    let mut capacity = MIN_CAPACITY;
    while capacity < slots {
        capacity *= 2;
    }
    capacity
}

/// Sklad živých proměnných.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct LivePools {
    /// Osa skupin: sloupec → skupina (kanonické pořadí podle jmen).
    pub group_ids: Vec<GroupId>,
    /// Skupina (číslo) → sloupec, `u32::MAX` = není v ose.
    column_of: Vec<u32>,
    pub blocks: BTreeMap<usize, PoolBlock>,
    block_of: HashMap<VariableId, usize>,
    keys: HashMap<VariantId, u64>,
}

impl LivePools {
    pub fn len(&self) -> usize {
        self.block_of.len()
    }

    pub fn is_empty(&self) -> bool {
        self.block_of.is_empty()
    }

    pub fn contains(&self, variable: VariableId) -> bool {
        self.block_of.contains_key(&variable)
    }

    /// Čísla živých proměnných vzestupně.
    pub fn variable_ids(&self) -> Vec<VariableId> {
        let mut ids: Vec<VariableId> = self.block_of.keys().copied().collect();
        ids.sort();
        ids
    }

    pub fn column(&self, group: GroupId) -> Option<usize> {
        match self.column_of.get(group.index()) {
            Some(&c) if c != u32::MAX => Some(c as usize),
            _ => None,
        }
    }

    /// Bloky podle kapacity vzestupně, bez prázdných.
    pub fn iter_blocks(&self) -> impl Iterator<Item = &PoolBlock> {
        self.blocks.values().filter(|b| !b.is_empty())
    }

    /// Nastaví osu skupin (po události, která skupiny přidala či ubrala); sklad musí být prázdný.
    pub fn set_axis(&mut self, group_ids: Vec<GroupId>) {
        self.column_of.clear();
        for (column, group) in group_ids.iter().enumerate() {
            if self.column_of.len() <= group.index() {
                self.column_of.resize(group.index() + 1, u32::MAX);
            }
            self.column_of[group.index()] = column as u32;
        }
        self.group_ids = group_ids;
        self.blocks.clear();
        self.block_of.clear();
    }

    /// Klíč varianty pro hashovaný drift; nezávisí na slotu ani na bloku.
    pub fn key(&mut self, variant: VariantId, names: &Numbering) -> u64 {
        *self.keys.entry(variant).or_insert_with(|| {
            stable_int(&[Part::Str("variant-key"), Part::Str(names.name(variant.0))])
        })
    }

    pub fn holds(&self, group: GroupId, variable: VariableId) -> bool {
        let (Some(&capacity), Some(column)) = (self.block_of.get(&variable), self.column(group))
        else {
            return false;
        };
        let block = &self.blocks[&capacity];
        block
            .row_of(variable)
            .is_some_and(|row| block.present[row][column])
    }

    /// Podíl varianty; `None` = skupina proměnnou nemá.
    pub fn frequency(
        &self,
        group: GroupId,
        variable: VariableId,
        variant: VariantId,
    ) -> Option<f64> {
        let block = &self.blocks[self.block_of.get(&variable)?];
        let row = block.row_of(variable)?;
        let column = self.column(group)?;
        if !block.present[row][column] {
            return None;
        }
        let Some(slot) = block.slots[row].iter().position(|&v| v == variant) else {
            return Some(0.0);
        };
        Some(block.cells.rows[row].value(column, slot).max(0.0))
    }

    /// Nejčastější varianta a její podíl; shodu rozhodne menší jméno varianty.
    pub fn dominant(
        &self,
        group: GroupId,
        variable: VariableId,
        names: &Numbering,
    ) -> Option<(VariantId, f64)> {
        let block = &self.blocks[self.block_of.get(&variable)?];
        let row = block.row_of(variable)?;
        let column = self.column(group)?;
        if !block.present[row][column] {
            return None;
        }
        let mut best: Option<(VariantId, f64)> = None;
        for (slot, freq, _) in block.cell(row, column) {
            let variant = block.slots[row][slot];
            if variant.is_none() {
                continue;
            }
            let better = match best {
                None => true,
                Some((b, f)) => freq > f || (freq == f && names.name(variant.0) < names.name(b.0)),
            };
            if better {
                best = Some((variant, freq));
            }
        }
        best
    }

    /// Rozdělení skupiny jako `Distribution` (varianty seřazené podle jmen).
    pub fn get(
        &self,
        group: GroupId,
        variable: VariableId,
        names: &Numbering,
    ) -> Option<Distribution> {
        let block = &self.blocks[self.block_of.get(&variable)?];
        let row = block.row_of(variable)?;
        let column = self.column(group)?;
        if !block.present[row][column] {
            return None;
        }
        let mut used: Vec<(VariantId, f64, f64)> = block
            .cell(row, column)
            .into_iter()
            .filter(|&(slot, _, _)| !block.slots[row][slot].is_none())
            .map(|(slot, f, p)| (block.slots[row][slot], f, p))
            .collect();
        used.sort_by(|a, b| names.name(a.0 .0).cmp(names.name(b.0 .0)));
        Some(Distribution {
            variants: used.iter().map(|u| u.0).collect(),
            freqs: used.iter().map(|u| u.1).collect(),
            previous: used.iter().map(|u| u.2).collect(),
        })
    }

    /// Mapa rozšíření varianty: skupiny, které ji mají (seřazené podle sloupce), a podíly.
    pub fn range_of(&self, variable: VariableId, variant: VariantId) -> (Vec<GroupId>, Vec<f64>) {
        let Some(&capacity) = self.block_of.get(&variable) else {
            return (vec![], vec![]);
        };
        let block = &self.blocks[&capacity];
        let Some(row) = block.row_of(variable) else {
            return (vec![], vec![]);
        };
        let Some(slot) = block.slots[row].iter().position(|&v| v == variant) else {
            return (vec![], vec![]);
        };
        let (columns, shares) = block.range_of(row, slot);
        columns
            .into_iter()
            .zip(shares)
            .filter(|&(c, _)| block.present[row][c as usize])
            .map(|(c, s)| (self.group_ids[c as usize], s))
            .unzip()
    }

    /// Převezme proměnnou z repertoárů všech skupin (v pořadí osy); `None` = skupina ji nemá.
    pub fn load(
        &mut self,
        variable: VariableId,
        distributions: &[Option<Distribution>],
        names: &Numbering,
    ) -> Result<(), String> {
        if self.block_of.contains_key(&variable) {
            return Err(format!("Proměnná {} už je živá.", names.name(variable.0)));
        }
        let mut variants: Vec<VariantId> = distributions
            .iter()
            .flatten()
            .flat_map(|d| d.variants.iter().copied())
            .collect();
        variants.sort_by(|a, b| names.name(a.0).cmp(names.name(b.0)));
        variants.dedup();
        let groups = self.group_ids.len();
        let width = variants.len();
        let (mut freqs, mut previous) = (vec![0.0; groups * width], vec![0.0; groups * width]);
        let mut present = vec![false; groups];
        for (column, item) in distributions.iter().enumerate() {
            let Some(item) = item else { continue };
            present[column] = true;
            for ((&variant, &freq), &before) in
                item.variants.iter().zip(&item.freqs).zip(&item.previous)
            {
                let slot = variants
                    .iter()
                    .position(|&v| v == variant)
                    .expect("varianta");
                freqs[column * width + slot] = freq;
                previous[column * width + slot] = before;
            }
        }
        let keys: Vec<u64> = variants.iter().map(|&v| self.key(v, names)).collect();
        // Rezerva jednoho slotu: proměnná se načítá kvůli nové inovaci.
        let capacity = capacity_for(width + 1);
        self.place(
            capacity,
            Row {
                variable,
                freqs,
                previous,
                present,
                slots: variants,
                keys,
            },
        );
        Ok(())
    }

    fn place(&mut self, capacity: usize, row: Row) {
        let capacity = capacity.max(capacity_for(
            row.slots.iter().filter(|v| !v.is_none()).count(),
        ));
        // Sloty bez varianty se vynechají (řádek se zhustí).
        let used: Vec<usize> = (0..row.slots.len())
            .filter(|&i| !row.slots[i].is_none())
            .collect();
        let (groups, old) = (self.group_ids.len(), row.slots.len());
        let mut freqs = Vec::with_capacity(groups * used.len());
        let mut previous = Vec::with_capacity(groups * used.len());
        for g in 0..groups {
            for &s in &used {
                freqs.push(row.freqs[g * old + s]);
                previous.push(row.previous[g * old + s]);
            }
        }
        let variable = row.variable;
        let block = self
            .blocks
            .entry(capacity)
            .or_insert_with(|| PoolBlock::new(groups, capacity));
        block.append(Row {
            variable,
            freqs,
            previous,
            present: row.present,
            slots: used.iter().map(|&i| row.slots[i]).collect(),
            keys: used.iter().map(|&i| row.keys[i]).collect(),
        });
        self.block_of.insert(variable, capacity);
    }

    fn relocate(&mut self, variable: VariableId, capacity: usize) {
        let held = self.block_of[&variable];
        let block = self.blocks.get_mut(&held).expect("blok");
        let row = block.row_of(variable).expect("řádek");
        let mut taken = block.extract(&[row]);
        let row = taken.pop().expect("řádek");
        // `extract` vrací hustě kapacitu bloku; sloty a pole mají stejnou šířku.
        self.place(capacity.max(MIN_CAPACITY), row);
    }

    /// Nová varianta v jedné skupině s podílem `share`, bez trendu.
    pub fn innovate(
        &mut self,
        variable: VariableId,
        group: GroupId,
        variant: VariantId,
        share: f64,
        names: &Numbering,
    ) {
        let column = self.column(group).expect("skupina v ose");
        let held = self.block_of[&variable];
        {
            let block = &self.blocks[&held];
            let row = block.row_of(variable).expect("řádek");
            let known = block.slots[row].contains(&variant);
            if !known && !block.slots[row].iter().any(|v| v.is_none()) {
                self.relocate(variable, block.capacity * 2);
            }
        }
        let key = self.key(variant, names);
        let held = self.block_of[&variable];
        let block = self.blocks.get_mut(&held).expect("blok");
        let row = block.row_of(variable).expect("řádek");
        let slot = match block.slots[row].iter().position(|&v| v == variant) {
            Some(slot) => slot,
            None => {
                let slot = block.slots[row]
                    .iter()
                    .position(|v| v.is_none())
                    .expect("volný slot");
                block.slots[row][slot] = variant;
                block.keys[row][slot] = key;
                block.layout += 1;
                slot
            }
        };
        block.add_share(row, column, slot, share);
    }

    /// Vyjme proměnné, které jsou všude stejné a ustálené (rozdělení skupin k zápisu do repertoárů).
    ///
    /// Uvolní také sloty variant, které už nežije žádná skupina, a proměnné využívající
    /// jen čtvrtinu kapacity přesune do menšího bloku.
    pub fn release(&mut self, names: &Numbering) -> Vec<(VariableId, Vec<Option<Distribution>>)> {
        let mut released: Vec<(VariableId, Vec<Option<Distribution>>)> = Vec::new();
        for capacity in self.blocks.keys().copied().collect::<Vec<_>>() {
            if self.blocks[&capacity].is_empty() {
                continue;
            }
            // 1) sloty bez výskytu
            {
                let block = self.blocks.get_mut(&capacity).expect("blok");
                for row in 0..block.len() {
                    let mut alive = vec![false; block.capacity];
                    for cell in 0..block.cells.rows[row].len() {
                        if block.cells.rows[row].freq[cell] > 0.0 {
                            alive[block.cells.rows[row].slot[cell] as usize] = true;
                        }
                    }
                    let dead: Vec<usize> = (0..block.capacity)
                        .filter(|&s| !alive[s] && !block.slots[row][s].is_none())
                        .collect();
                    if !dead.is_empty() {
                        block.free_slots(row, &dead);
                    }
                }
            }
            // 2) jednotné ustálené řádky (řádky jsou nezávislé, hledají se souběžně a v pořadí řádků)
            let uniform: Vec<usize> = {
                let block = &self.blocks[&capacity];
                (0..block.len())
                    .into_par_iter()
                    .map_init(
                        || (vec![-1_i64; block.groups], vec![0_usize; block.groups]),
                        |(leader, counts), row| {
                            leader.fill(-1);
                            counts.fill(0);
                            let r = &block.cells.rows[row];
                            for cell in 0..r.len() {
                                if r.freq[cell] > 0.0 {
                                    counts[r.group[cell] as usize] += 1;
                                }
                            }
                            for (g, chosen) in leader.iter_mut().enumerate() {
                                if !block.present[row][g] {
                                    continue;
                                }
                                let (mut best, mut best_f) = (0_i64, f64::NEG_INFINITY);
                                for slot in 0..block.capacity {
                                    let f = r.value(g, slot);
                                    if f > best_f {
                                        best_f = f;
                                        best = slot as i64;
                                    }
                                }
                                *chosen = best;
                            }
                            let first = *leader.iter().max().unwrap_or(&-1);
                            let single =
                                (0..block.groups).all(|g| counts[g] <= 1 || !block.present[row][g]);
                            let same = leader.iter().all(|&l| l == first || l == -1);
                            (single && same).then_some(row)
                        },
                    )
                    .flatten()
                    .collect()
            };
            for &row in &uniform {
                let variable = self.blocks[&capacity].variables[row];
                let dists = self
                    .group_ids
                    .iter()
                    .map(|&g| self.get(g, variable, names))
                    .collect();
                released.push((variable, dists));
            }
            let taken = self
                .blocks
                .get_mut(&capacity)
                .expect("blok")
                .extract(&uniform);
            for row in taken {
                self.block_of.remove(&row.variable);
            }
            // 3) řídké řádky do menšího bloku
            if capacity > MIN_CAPACITY {
                let sparse: Vec<VariableId> = {
                    let block = &self.blocks[&capacity];
                    (0..block.len())
                        .filter(|&row| {
                            block.slots[row].iter().filter(|v| !v.is_none()).count() <= capacity / 4
                        })
                        .map(|row| block.variables[row])
                        .collect()
                };
                for variable in sparse {
                    self.relocate(variable, capacity / 2);
                }
            }
        }
        released.sort_by(|a, b| names.name(a.0 .0).cmp(names.name(b.0 .0)));
        released
    }
}

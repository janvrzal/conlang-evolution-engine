//! Řídké živé fondy: výskyty variant po řádcích (proměnných), zrcadlo `RowCells` a
//! uložení buněk v `PoolBlock` z `cee.v2.pools`.
//!
//! Řádek drží buňky (slot, skupina, podíl, trendová základna) seřazené podle slotu
//! a v něm podle skupiny; buňka tu je, má-li kladný podíl nebo nenulovou základnu.
//! Úsek jednoho slotu je souvislý (`starts[slot]..starts[slot + 1]`), takže mapa
//! rozšíření varianty je přímo její úsek. Operace nad řádkem (přidání podílu,
//! uvolnění slotů) dávají přesně totéž co Python, včetně pořadí plovoucích operací.

// Indexované smyčky přes sloty jsou tu záměrně: pořadí operací je součástí smlouvy.
#![allow(clippy::needless_range_loop)]

use crate::transmission::ranges;

/// Výskyty variant jedné proměnné.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Row {
    pub slot: Vec<i16>,
    pub group: Vec<i32>,
    pub freq: Vec<f64>,
    pub prev: Vec<f64>,
    /// Začátky úseků slotů, délka `kapacita + 1`.
    pub starts: Vec<i64>,
}

impl Row {
    /// Řádek z buněk seřazených podle slotu a skupiny; začátky úseků se dopočtou.
    pub fn build(
        slot: Vec<i16>,
        group: Vec<i32>,
        freq: Vec<f64>,
        prev: Vec<f64>,
        capacity: usize,
    ) -> Row {
        let mut starts = vec![0_i64; capacity + 1];
        for &item in &slot {
            starts[item as usize + 1] += 1;
        }
        for index in 0..capacity {
            starts[index + 1] += starts[index];
        }
        Row {
            slot,
            group,
            freq,
            prev,
            starts,
        }
    }

    /// Buňky z husté matice `skupiny × šířka` (po řádcích); sloty ≤ `capacity`.
    pub fn from_dense(
        freqs: &[f64],
        previous: &[f64],
        groups: usize,
        width: usize,
        capacity: usize,
    ) -> Row {
        let kept = |at: usize| freqs[at] > 0.0 || previous[at] != 0.0;
        let mut starts = vec![0_i64; capacity + 1];
        for group in 0..groups {
            for slot in 0..width {
                if kept(group * width + slot) {
                    starts[slot + 1] += 1;
                }
            }
        }
        for index in 0..capacity {
            starts[index + 1] += starts[index];
        }
        let total = starts[capacity] as usize;
        let mut row = Row {
            slot: vec![0; total],
            group: vec![0; total],
            freq: vec![0.0; total],
            prev: vec![0.0; total],
            starts: starts.clone(),
        };
        for group in 0..groups {
            for slot in 0..width {
                let at = group * width + slot;
                if kept(at) {
                    let place = starts[slot] as usize;
                    starts[slot] += 1;
                    row.slot[place] = slot as i16;
                    row.group[place] = group as i32;
                    row.freq[place] = freqs[at];
                    row.prev[place] = previous[at];
                }
            }
        }
        row
    }

    pub fn len(&self) -> usize {
        self.slot.len()
    }

    pub fn is_empty(&self) -> bool {
        self.slot.is_empty()
    }

    /// Úsek buněk jednoho slotu: `[od, do)`.
    pub fn span(&self, slot: usize) -> (usize, usize) {
        if slot + 1 >= self.starts.len() {
            return (self.len(), self.len());
        }
        (self.starts[slot] as usize, self.starts[slot + 1] as usize)
    }

    /// Zapíše buňky do husté matice `skupiny × kapacita` (po řádcích, předem vynulované).
    pub fn scatter(&self, capacity: usize, freqs: &mut [f64], previous: &mut [f64]) {
        for index in 0..self.len() {
            let at = self.group[index] as usize * capacity + self.slot[index] as usize;
            freqs[at] = self.freq[index];
            previous[at] = self.prev[index];
        }
    }

    /// Podíl varianty ve slotu u skupiny (0, když tam není).
    pub fn value(&self, column: usize, slot: usize) -> f64 {
        let (start, stop) = self.span(slot);
        let groups = &self.group[start..stop];
        let at = groups.partition_point(|&group| (group as usize) < column);
        if at < groups.len() && groups[at] as usize == column {
            self.freq[start + at]
        } else {
            0.0
        }
    }

    /// Sloty s kladným podílem u jedné skupiny: (slot, podíl, základna) vzestupně podle slotu.
    pub fn cell(&self, column: usize) -> Vec<(usize, f64, f64)> {
        // Úsek každého slotu je seřazený podle skupiny: binární hledání místo průchodu celým
        // řádkem (dotaz na všechny skupiny byl kvadratický v počtu skupin).
        let mut found = Vec::new();
        for slot in 0..self.starts.len().saturating_sub(1) {
            let (start, stop) = self.span(slot);
            let groups = &self.group[start..stop];
            let at = groups.partition_point(|&group| (group as usize) < column);
            if at < groups.len() && groups[at] as usize == column {
                let index = start + at;
                if self.freq[index] > 0.0 {
                    found.push((slot, self.freq[index], self.prev[index]));
                }
            }
        }
        found
    }

    /// Mapa rozšíření varianty: sloupce skupin s kladným podílem a ty podíly.
    pub fn range_of(&self, slot: usize) -> (Vec<i64>, Vec<f64>) {
        let (start, stop) = self.span(slot);
        (start..stop)
            .filter(|&index| self.freq[index] > 0.0)
            .map(|index| (i64::from(self.group[index]), self.freq[index]))
            .unzip()
    }

    /// Nová varianta ve slotu u jedné skupiny: ostatní podíly skupiny se zmenší a základna
    /// se vyrovná (`freqs[skupina] *= 1 − podíl; freqs[skupina, slot] += podíl;
    /// previous = freqs`).
    pub fn add_share(&mut self, column: usize, slot: usize, share: f64, capacity: usize) {
        let mine: Vec<usize> = (0..self.len())
            .filter(|&index| self.group[index] as usize == column)
            .collect();
        let mut scaled: Vec<f64> = mine
            .iter()
            .map(|&index| self.freq[index] * (1.0 - share))
            .collect();
        let here = mine
            .iter()
            .position(|&index| self.slot[index] as usize == slot);
        if let Some(position) = here {
            scaled[position] += share;
        }
        if !scaled.is_empty() && !scaled.iter().all(|&value| value > 0.0) {
            self.add_share_general(column, slot, share, capacity);
            return;
        }
        for (&index, &value) in mine.iter().zip(&scaled) {
            self.freq[index] = value;
            self.prev[index] = value;
        }
        if here.is_none() {
            // Skupina varianty ještě nemá: nová buňka se vloží na své místo v úseku slotu.
            let (start, stop) = self.span(slot);
            let at =
                start + self.group[start..stop].partition_point(|&group| (group as usize) < column);
            self.slot.insert(at, slot as i16);
            self.group.insert(at, column as i32);
            self.freq.insert(at, 0.0 + share);
            self.prev.insert(at, 0.0 + share);
            for start in &mut self.starts[slot + 1..] {
                *start += 1;
            }
        }
    }

    /// Totéž pro skupinu, jejíž buňka by zanikla (podíl 0 se základnou ≠ 0); buňky se přeskládají.
    fn add_share_general(&mut self, column: usize, slot: usize, share: f64, capacity: usize) {
        let mut mine: Vec<(i16, f64)> = Vec::new();
        let mut rest: Vec<(i16, i32, f64, f64)> = Vec::new();
        for index in 0..self.len() {
            if self.group[index] as usize == column {
                mine.push((self.slot[index], self.freq[index] * (1.0 - share)));
            } else {
                rest.push((
                    self.slot[index],
                    self.group[index],
                    self.freq[index],
                    self.prev[index],
                ));
            }
        }
        match mine.iter().position(|&(item, _)| item as usize == slot) {
            Some(position) => mine[position].1 += share,
            None => mine.push((slot as i16, 0.0 + share)),
        }
        rest.extend(
            mine.into_iter()
                .filter(|&(_, value)| value > 0.0)
                .map(|(item, value)| (item, column as i32, value, value)),
        );
        rest.sort_by_key(|&(item, group, _, _)| (item, group));
        *self = Row::build(
            rest.iter().map(|cell| cell.0).collect(),
            rest.iter().map(|cell| cell.1).collect(),
            rest.iter().map(|cell| cell.2).collect(),
            rest.iter().map(|cell| cell.3).collect(),
            capacity,
        );
    }

    /// Odebere buňky uvolněných slotů.
    pub fn free_slots(&mut self, freed: &[usize], capacity: usize) {
        let keep: Vec<usize> = (0..self.len())
            .filter(|&index| !freed.contains(&(self.slot[index] as usize)))
            .collect();
        *self = Row::build(
            keep.iter().map(|&index| self.slot[index]).collect(),
            keep.iter().map(|&index| self.group[index]).collect(),
            keep.iter().map(|&index| self.freq[index]).collect(),
            keep.iter().map(|&index| self.prev[index]).collect(),
            capacity,
        );
    }

    /// Paměť řádku v bajtech (jen data).
    pub fn nbytes(&self) -> usize {
        self.slot.len() * (2 + 4 + 8 + 8) + self.starts.len() * 8
    }
}

/// Buňky všech řádků bloku (proměnných se stejnou kapacitou slotů).
#[derive(Debug, Clone, Default)]
pub struct Cells {
    pub groups: usize,
    pub capacity: usize,
    pub rows: Vec<Row>,
    staged: Option<Vec<Row>>,
}

impl Cells {
    pub fn new(groups: usize, capacity: usize) -> Cells {
        Cells {
            groups,
            capacity,
            ..Cells::default()
        }
    }

    /// Řádky z uloženého stavu: `pointer[r]..pointer[r + 1]` jsou buňky řádku r.
    pub fn from_flat(
        groups: usize,
        capacity: usize,
        pointer: &[i64],
        slot: &[i16],
        group: &[i32],
        freq: &[f64],
        prev: &[f64],
    ) -> Cells {
        let rows = pointer
            .windows(2)
            .map(|pair| {
                let (low, high) = (pair[0] as usize, pair[1] as usize);
                Row::build(
                    slot[low..high].to_vec(),
                    group[low..high].to_vec(),
                    freq[low..high].to_vec(),
                    prev[low..high].to_vec(),
                    capacity,
                )
            })
            .collect();
        Cells {
            groups,
            capacity,
            rows,
            staged: None,
        }
    }

    /// Stav jako pole po řádcích za sebou: ukazatele, sloty, skupiny, podíly, základny.
    #[allow(clippy::type_complexity)]
    pub fn to_flat(&self) -> (Vec<i64>, Vec<i16>, Vec<i32>, Vec<f64>, Vec<f64>) {
        let mut pointer = vec![0_i64];
        let (mut slot, mut group, mut freq, mut prev) =
            (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        for row in &self.rows {
            slot.extend_from_slice(&row.slot);
            group.extend_from_slice(&row.group);
            freq.extend_from_slice(&row.freq);
            prev.extend_from_slice(&row.prev);
            pointer.push(slot.len() as i64);
        }
        (pointer, slot, group, freq, prev)
    }

    /// Přidá řádek z husté matice `skupiny × šířka` (šířka ≤ kapacita).
    pub fn append_dense(&mut self, freqs: &[f64], previous: &[f64], width: usize) {
        self.rows.push(Row::from_dense(
            freqs,
            previous,
            self.groups,
            width,
            self.capacity,
        ));
    }

    /// Hustý tvar jednoho řádku (`skupiny × kapacita`) do vynulovaných polí.
    pub fn row_dense(&self, row: usize, freqs: &mut [f64], previous: &mut [f64]) {
        self.rows[row].scatter(self.capacity, freqs, previous);
    }

    /// Hustý pohled celého bloku (`řádky × skupiny × kapacita`) do vynulovaných polí.
    pub fn dense(&self, freqs: &mut [f64], previous: &mut [f64]) {
        let size = self.groups * self.capacity;
        for (index, row) in self.rows.iter().enumerate() {
            row.scatter(
                self.capacity,
                &mut freqs[index * size..(index + 1) * size],
                &mut previous[index * size..(index + 1) * size],
            );
        }
    }

    /// Připraví nový stav celého bloku z hustých polí (řádky na `threads` vláknech,
    /// každý úsek řádků vlastní výstup); zapíše ho až `commit`.
    pub fn stage(&mut self, freqs: &[f64], previous: &[f64], threads: usize) {
        let size = self.groups * self.capacity;
        let (groups, capacity) = (self.groups, self.capacity);
        let build = |first: usize, last: usize| -> Vec<Row> {
            (first..last)
                .map(|row| {
                    Row::from_dense(
                        &freqs[row * size..(row + 1) * size],
                        &previous[row * size..(row + 1) * size],
                        groups,
                        capacity,
                        capacity,
                    )
                })
                .collect()
        };
        let parts = ranges(self.rows.len(), threads);
        let rows = if parts.len() == 1 {
            build(parts[0].0, parts[0].1)
        } else {
            std::thread::scope(|scope| {
                let handles: Vec<_> = parts
                    .iter()
                    .map(|&(first, last)| scope.spawn(move || build(first, last)))
                    .collect();
                handles
                    .into_iter()
                    .flat_map(|handle| handle.join().expect("vlákno přípravy řádků"))
                    .collect()
            })
        };
        self.staged = Some(rows);
    }

    /// Zapíše stav připravený `stage`; počet řádků se mezitím nesměl změnit.
    pub fn commit(&mut self) -> Result<(), String> {
        let staged = self.staged.take().ok_or("není co zapsat")?;
        if staged.len() != self.rows.len() {
            return Err("Řádky bloku se mezi přípravou a zápisem stavu změnily.".into());
        }
        self.rows = staged;
        Ok(())
    }

    /// Odebere řádek tak, že na jeho místo přijde poslední (jako `extract` v Pythonu).
    pub fn swap_remove(&mut self, row: usize) -> Row {
        self.rows.swap_remove(row)
    }

    /// Počet uložených buněk celého bloku.
    pub fn entries(&self) -> usize {
        self.rows.iter().map(Row::len).sum()
    }

    pub fn nbytes(&self) -> usize {
        self.rows.iter().map(Row::nbytes).sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dense(freq: &[f64]) -> (Vec<f64>, Vec<f64>) {
        (freq.to_vec(), freq.to_vec())
    }

    #[test]
    fn radek_z_husteho_tvaru_a_zpet() {
        // Tři skupiny, dva sloty: skupina 1 má jen druhý slot, skupina 2 má základnu bez podílu.
        let freqs = [1.0, 0.0, 0.0, 1.0, 0.5, 0.0];
        let previous = [1.0, 0.0, 0.0, 1.0, 0.5, 0.25];
        let row = Row::from_dense(&freqs, &previous, 3, 2, 4);
        assert_eq!(row.slot, vec![0, 0, 1, 1]);
        assert_eq!(row.group, vec![0, 2, 1, 2]);
        assert_eq!(row.starts, vec![0, 2, 4, 4, 4]);
        let (mut back_f, mut back_p) = (vec![0.0; 3 * 4], vec![0.0; 3 * 4]);
        row.scatter(4, &mut back_f, &mut back_p);
        assert_eq!(back_f[0], 1.0);
        assert_eq!(back_p[2 * 4 + 1], 0.25);
        assert_eq!(row.value(2, 0), 0.5);
        assert_eq!(row.value(1, 0), 0.0);
        assert_eq!(row.cell(2), vec![(0, 0.5, 0.5)]);
    }

    #[test]
    fn pridani_podilu_vlozi_bunku_a_zmensi_ostatni() {
        let (freqs, previous) = dense(&[1.0, 0.0, 1.0, 0.0]);
        let mut row = Row::from_dense(&freqs, &previous, 2, 2, 2);
        row.add_share(1, 1, 0.25, 2);
        assert_eq!(row.slot, vec![0, 0, 1]);
        assert_eq!(row.group, vec![0, 1, 1]);
        assert_eq!(row.freq, vec![1.0, 0.75, 0.25]);
        assert_eq!(row.prev, row.freq);
        assert_eq!(row.starts, vec![0, 2, 3]);
    }

    #[test]
    fn zanikla_bunka_se_prestavi_obecnou_cestou() {
        // Skupina 0 má podíl 0 se základnou: přidání podílu buňku odstraní, zbude jen nový slot.
        let freqs = [0.0, 1.0];
        let previous = [0.5, 1.0];
        let mut row = Row::from_dense(&freqs, &previous, 1, 2, 2);
        row.add_share(0, 1, 0.5, 2);
        assert_eq!(row.slot, vec![1]);
        assert_eq!(row.freq, vec![1.0]);
        assert_eq!(row.starts, vec![0, 0, 1]);
        row.add_share(0, 0, 0.25, 2);
        assert_eq!(row.slot, vec![0, 1]);
        assert_eq!(row.freq, vec![0.25, 0.75]);
        row.free_slots(&[1], 2);
        assert_eq!(row.slot, vec![0]);
        assert_eq!(row.starts, vec![0, 1, 1]);
    }

    #[test]
    fn stav_bloku_se_zapise_az_po_commit() {
        let mut cells = Cells::new(2, 2);
        cells.append_dense(&[1.0, 0.0, 0.0, 1.0], &[1.0, 0.0, 0.0, 1.0], 2);
        cells.stage(&[0.5, 0.5, 0.0, 1.0], &[0.5, 0.5, 0.0, 1.0], 1);
        assert_eq!(cells.entries(), 2);
        cells.commit().unwrap();
        assert_eq!(cells.entries(), 3);
        let (pointer, slot, group, freq, prev) = cells.to_flat();
        let again = Cells::from_flat(2, 2, &pointer, &slot, &group, &freq, &prev);
        assert_eq!(again.rows, cells.rows);
    }
}

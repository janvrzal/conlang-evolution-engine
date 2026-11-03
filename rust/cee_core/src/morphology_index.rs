//! Morfologické indexy kódu na číslech: zrcadlo `cee.v2.language.morphology_index`.
//!
//! Jeden stav kódu (klíč je `FormStore.token`) nese čtyři věci, které dřív držely
//! čtyři indexy nad řetězcovými množinami a slovníky:
//!
//! - **členství** (`WordMembershipIndex`): tvary slov (morfém druhu „tvar slova“
//!   s třídou a buňkou) ve slovní zásobě kódu;
//! - **koncovky tříd** (`ExponentIndex`): pro (třídu, buňku) kolik tvarů nese kterou
//!   koncovku a pro koncovku kolik tvarů má kterou podobu koncovky;
//! - **kandidáti** (`MorphologyCandidateIndex`): tvary, kde je místo pro vyrovnání
//!   (kmen se liší od citačního tvaru) a pro rozšíření vzoru (koncovka buňky se liší
//!   od produktivní nebo splynula s citačním tvarem);
//! - **slabost buněk** (`WeaknessIndex`): kolik tvarů buňky zní jako citační tvar.
//!
//! Stav jsou ploché sloupce podle čísla morfému z registru (stejné sloupce jako
//! `MorphemeTable`: druh, třída, buňka, lexém, koncovka, hranice) a malé tabulky
//! podle (třídy, buňky) a koncovky. V horké cestě (jeden průchod členy kódu za
//! tik) není žádný řetězec ani hašovací mapa: porovnávají se syrová čísla
//! z úložiště tvarů kódu (`form`, `boundary`, `exponent`) a z úložiště kořene s tím,
//! co index započítal. Mapy jsou jen pro položky, které se mění (buňky, podoby
//! koncovek).
//!
//! **Čistota.** Příspěvek tvaru (koncovka, podoba koncovky, splynutí, vyrovnání,
//! rozšíření) je čistá funkce jeho tvaru, tvaru kořene a popisu buňky
//! (produktivní koncovka). Přírůstkový stav je proto vždy stejný jako výpočet od
//! nuly a nezáleží na pořadí dorovnání.
//!
//! **Tvary bez banky.** Výchozí tvar morfému, který kód nepřepsal, drží index ve
//! vlastní aréně (`Defaults`), kterou plní Python na požádání (`needs`). Nezařazuje
//! se tak do banky tvarů světa žádný tvar, který model nepoužívá; přepsané tvary
//! mají číslo v bance a čtou se z ní.
//!
//! **Pořadí podle řetězců.** Remízy (produktivní koncovka, podoba koncovky) a pořadí
//! míst rozhodují řetězcová ID, jako dřív; index proto drží jména morfémů
//! (`Names`, bajty UTF-8 se řadí stejně jako body Unicode v Pythonu).

use std::cmp::Ordering;
use std::collections::HashMap;
use std::hash::BuildHasherDefault;

use crate::bank::Bank;
use crate::index::Fx;

pub(crate) type FxMap<K, V> = HashMap<K, V, BuildHasherDefault<Fx>>;

/// Kód druhu morfému „tvar slova“ (`MORPHEME_KINDS` v `cee.v2.tables`).
pub const KIND_WORD: i8 = 2;
/// Syrová hodnota v úložišti: morfém tvar nemá (platí výchozí).
const RAW_NONE: i32 = -1;

/// Jména podle čísla (UTF-8 za sebou), aby šlo řadit podle řetězců bez Pythonu.
#[derive(Default)]
pub struct Names {
    bytes: Vec<u8>,
    ends: Vec<u32>,
}

impl Names {
    pub fn len(&self) -> usize {
        self.ends.len()
    }

    pub fn is_empty(&self) -> bool {
        self.ends.is_empty()
    }

    /// Připojí další jména (v pořadí čísel).
    pub fn extend<S: AsRef<str>>(&mut self, names: &[S]) {
        for name in names {
            self.bytes.extend_from_slice(name.as_ref().as_bytes());
            self.ends.push(self.bytes.len() as u32);
        }
    }

    pub fn get(&self, number: usize) -> &[u8] {
        let start = if number == 0 {
            0
        } else {
            self.ends[number - 1] as usize
        };
        &self.bytes[start..self.ends[number] as usize]
    }
}

/// Výchozí tvary morfémů podle čísla (obsah hlásek), které doplňuje Python.
#[derive(Default)]
pub struct Defaults {
    start: Vec<u32>,
    length: Vec<u32>,
    pool: Vec<i32>,
}

impl Defaults {
    pub fn get(&self, number: usize) -> Option<&[i32]> {
        match self.start.get(number) {
            Some(&start) if start != u32::MAX => {
                Some(&self.pool[start as usize..(start + self.length[number]) as usize])
            }
            _ => None,
        }
    }

    pub fn set(&mut self, number: usize, form: &[i32]) {
        if self.start.len() <= number {
            self.start.resize(number + 1, u32::MAX);
            self.length.resize(number + 1, 0);
        }
        if self.start[number] != u32::MAX {
            return;
        }
        self.start[number] = self.pool.len() as u32;
        self.length[number] = form.len() as u32;
        self.pool.extend_from_slice(form);
    }
}

/// Podoby koncovek (konce tvarů od hranice) jako čísla; shodné podoby mají totéž číslo.
#[derive(Default)]
pub struct Shapes {
    ids: FxMap<Box<[i32]>, u32>,
    start: Vec<u32>,
    length: Vec<u32>,
    pool: Vec<i32>,
}

impl Shapes {
    fn intern(&mut self, shape: &[i32]) -> u32 {
        if let Some(&found) = self.ids.get(shape) {
            return found;
        }
        let id = self.start.len() as u32;
        self.start.push(self.pool.len() as u32);
        self.length.push(shape.len() as u32);
        self.pool.extend_from_slice(shape);
        self.ids.insert(shape.into(), id);
        id
    }

    pub fn get(&self, id: u32) -> &[i32] {
        let start = self.start[id as usize] as usize;
        &self.pool[start..start + self.length[id as usize] as usize]
    }
}

/// Sloupce světa podle čísla morfému (`MorphemeTable`): druh, třída, buňka,
/// lexém, koncovka a hranice výchozího tvaru.
pub struct Columns<'a> {
    pub kind: &'a [i8],
    pub class: &'a [i32],
    pub cell: &'a [i32],
    pub lexeme: &'a [i32],
    pub exponent: &'a [i32],
    pub boundary: &'a [i32],
}

fn item<T: Copy>(values: &[T], number: usize, missing: T) -> T {
    values.get(number).copied().unwrap_or(missing)
}

/// Úložiště tvarů kódu (`FormStore.raw()`): číslo tvaru v bance, hranice, koncovka.
pub struct Store<'a> {
    pub form: &'a [i32],
    pub boundary: &'a [i32],
    pub exponent: &'a [i32],
}

/// Vstup jednoho kódu: příznaky slovní zásoby a úložiště tvarů.
pub struct CodeInput<'a> {
    pub token: i64,
    pub flags: &'a [u8],
    pub store: Store<'a>,
}

/// Pohled na aktuální tvar morfému v kódu: přepsaný z banky, jinak výchozí z arény.
struct View<'a> {
    bank: &'a Bank,
    cols: &'a Columns<'a>,
    defaults: &'a Defaults,
    store: &'a Store<'a>,
}

impl<'a> View<'a> {
    fn raw_form(&self, number: usize) -> i32 {
        item(self.store.form, number, RAW_NONE)
    }

    /// Hlásky aktuálního tvaru, nebo `None`, když chybí výchozí tvar v aréně.
    fn form(&self, number: usize) -> Option<&'a [i32]> {
        let raw = self.raw_form(number);
        if raw >= 0 {
            Some(self.bank.form_of(raw as usize))
        } else {
            self.defaults.get(number)
        }
    }

    fn boundary(&self, number: usize) -> i32 {
        if self.raw_form(number) >= 0 {
            item(self.store.boundary, number, RAW_NONE)
        } else {
            item(self.cols.boundary, number, RAW_NONE)
        }
    }

    fn exponent(&self, number: usize) -> i32 {
        if self.raw_form(number) >= 0 {
            item(self.store.exponent, number, RAW_NONE)
        } else {
            item(self.cols.exponent, number, RAW_NONE)
        }
    }

    /// Syrový stav tvaru a kořene, jak ho index porovnává s tím, co započítal.
    fn seen(&self, number: usize) -> Seen {
        let root = item(self.cols.lexeme, number, RAW_NONE);
        Seen {
            form: self.raw_form(number),
            boundary: item(self.store.boundary, number, RAW_NONE),
            exponent: item(self.store.exponent, number, RAW_NONE),
            root_form: if root >= 0 {
                self.raw_form(root as usize)
            } else {
                RAW_NONE
            },
        }
    }
}

/// Syrová čísla úložiště, ze kterých vyšel započítaný příspěvek tvaru.
#[derive(Clone, Copy, PartialEq, Eq)]
struct Seen {
    form: i32,
    boundary: i32,
    exponent: i32,
    root_form: i32,
}

/// Dosud nezapočítáno (žádný skutečný stav se mu nerovná).
const FRESH: Seen = Seen {
    form: i32::MIN,
    boundary: i32::MIN,
    exponent: i32::MIN,
    root_form: i32::MIN,
};

/// Příspěvek jednoho tvaru slova.
#[derive(Clone, Copy)]
struct Contrib {
    counted: bool,
    /// Koncovka tvaru (−1 = žádná) a číslo podoby koncovky.
    exponent: i32,
    shape: u32,
    /// Tvar zní jako citační tvar (splynul).
    merged: bool,
    /// Kmen se liší od citačního tvaru (místo pro vyrovnání).
    leveling: bool,
    /// Produktivní koncovka, kterou by tvar mohl převzít (−1 = není místo).
    extension: i32,
}

const NO_CONTRIB: Contrib = Contrib {
    counted: false,
    exponent: -1,
    shape: 0,
    merged: false,
    leveling: false,
    extension: -1,
};

/// Statistika jedné (třídy, buňky).
struct Cell {
    class: i32,
    cell: i32,
    /// Koncovka a počet tvarů, které ji nesou.
    exponents: Vec<(i32, u32)>,
    /// Počet tvarů buňky a z nich splynulých s citačním tvarem.
    total: u32,
    merged: u32,
    /// Popisovač, se kterým jsou spočítaní kandidáti rozšíření: produktivní koncovka
    /// (−1 = žádná) a zda má její nejčastější podoba aspoň jednu hlásku.
    productive: i32,
    ends: bool,
}

/// Stav jednoho kódu.
#[derive(Default)]
struct Slot {
    flags: Vec<u8>,
    members: Vec<u32>,
    seen: Vec<Seen>,
    contrib: Vec<Contrib>,
    cells: Vec<Cell>,
    /// Koncovka → podoby koncovky a počty tvarů.
    shapes: FxMap<i32, Vec<(u32, u32)>>,
    leveling: u32,
    extension: u32,
    synced: bool,
}

impl Slot {
    fn cell_index(&mut self, class: i32, cell: i32) -> usize {
        match self
            .cells
            .binary_search_by_key(&(class, cell), |c| (c.class, c.cell))
        {
            Ok(found) => found,
            Err(found) => {
                self.cells.insert(
                    found,
                    Cell {
                        class,
                        cell,
                        exponents: Vec::new(),
                        total: 0,
                        merged: 0,
                        productive: -1,
                        ends: false,
                    },
                );
                found
            }
        }
    }

    fn find(&self, class: i32, cell: i32) -> Option<&Cell> {
        self.cells
            .binary_search_by_key(&(class, cell), |c| (c.class, c.cell))
            .ok()
            .map(|found| &self.cells[found])
    }

    fn give(&mut self, class: i32, cell: i32, value: &Contrib) {
        let at = self.cell_index(class, cell);
        let stats = &mut self.cells[at];
        stats.total += 1;
        stats.merged += u32::from(value.merged);
        if value.exponent >= 0 {
            match stats
                .exponents
                .iter_mut()
                .find(|(exponent, _)| *exponent == value.exponent)
            {
                Some((_, count)) => *count += 1,
                None => stats.exponents.push((value.exponent, 1)),
            }
            let shapes = self.shapes.entry(value.exponent).or_default();
            match shapes.iter_mut().find(|(shape, _)| *shape == value.shape) {
                Some((_, count)) => *count += 1,
                None => shapes.push((value.shape, 1)),
            }
        }
        self.leveling += u32::from(value.leveling);
        self.extension += u32::from(value.extension >= 0);
    }

    fn take(&mut self, class: i32, cell: i32, value: &Contrib) {
        let at = self.cell_index(class, cell);
        let stats = &mut self.cells[at];
        stats.total -= 1;
        stats.merged -= u32::from(value.merged);
        if value.exponent >= 0 {
            let position = stats
                .exponents
                .iter()
                .position(|(exponent, _)| *exponent == value.exponent)
                .expect("započítaná koncovka");
            stats.exponents[position].1 -= 1;
            if stats.exponents[position].1 == 0 {
                stats.exponents.remove(position);
            }
            let shapes = self
                .shapes
                .get_mut(&value.exponent)
                .expect("podoby koncovky");
            let position = shapes
                .iter()
                .position(|(shape, _)| *shape == value.shape)
                .expect("započítaná podoba");
            shapes[position].1 -= 1;
            if shapes[position].1 == 0 {
                shapes.remove(position);
            }
            if shapes.is_empty() {
                self.shapes.remove(&value.exponent);
            }
        }
        self.leveling -= u32::from(value.leveling);
        self.extension -= u32::from(value.extension >= 0);
    }

    /// Nejčastější podoba koncovky; při shodě počtů ta s menší posloupností hlásek.
    fn dominant_shape(&self, exponent: i32, shapes: &Shapes) -> Option<u32> {
        let counts = self.shapes.get(&exponent)?;
        let mut best: Option<(u32, u32)> = None;
        for &(shape, count) in counts {
            best = match best {
                None => Some((shape, count)),
                Some((held, top)) => {
                    let better = count > top
                        || (count == top
                            && shapes.get(shape).cmp(shapes.get(held)) == Ordering::Less);
                    if better {
                        Some((shape, count))
                    } else {
                        Some((held, top))
                    }
                }
            };
        }
        best.map(|(shape, _)| shape)
    }

    /// Produktivní koncovka buňky: nejvíc tvarů, při shodě menší jméno koncovky.
    fn productive(cell: &Cell, names: &Names) -> i32 {
        let mut best: Option<(i32, u32)> = None;
        for &(exponent, count) in &cell.exponents {
            best = match best {
                None => Some((exponent, count)),
                Some((held, top)) => {
                    let better = count > top
                        || (count == top
                            && names.get(exponent as usize).cmp(names.get(held as usize))
                                == Ordering::Less);
                    if better {
                        Some((exponent, count))
                    } else {
                        Some((held, top))
                    }
                }
            };
        }
        best.map_or(-1, |(exponent, _)| exponent)
    }
}

/// Co index žádá od Pythonu, než dokončí dorovnání: výchozí tvary morfémů.
pub type Needs = Vec<u32>;

/// Příspěvek tvaru podle jeho tvaru, tvaru kořene a popisu buňky.
struct Facts<'a> {
    form: &'a [i32],
    root: &'a [i32],
    boundary: i32,
    exponent: i32,
}

impl Facts<'_> {
    fn stem(&self) -> &[i32] {
        match self.boundary {
            b if b < 0 => self.form,
            b => &self.form[..(b as usize).min(self.form.len())],
        }
    }

    fn ending(&self) -> &[i32] {
        match self.boundary {
            b if b < 0 => &[],
            b => &self.form[(b as usize).min(self.form.len())..],
        }
    }
}

/// Rozšíření: produktivní koncovka buňky, když tvar nese jinou nebo splynul.
fn extension_of(productive: i32, ends: bool, exponent: i32, merged: bool) -> i32 {
    if productive < 0 || !ends {
        -1
    } else if exponent != productive || merged {
        productive
    } else {
        -1
    }
}

#[derive(Default)]
pub struct MorphIndex {
    pub names: Names,
    pub defaults: Defaults,
    shapes: Shapes,
    slots: Vec<Slot>,
    by_token: FxMap<i64, usize>,
    dirty: Vec<u32>,
    fresh: Vec<u32>,
    removed: Vec<u32>,
}

impl MorphIndex {
    pub fn new() -> MorphIndex {
        MorphIndex::default()
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

    /// Dorovná kód na aktuální stav. Chybí-li výchozí tvary, vrátí jejich čísla
    /// a nic nezmění (volající je doplní a zavolá znovu).
    pub fn sync(
        &mut self,
        bank: &Bank,
        cols: &Columns<'_>,
        input: &CodeInput<'_>,
    ) -> Result<Needs, String> {
        let place = self.slot_of(input.token);
        let Self {
            names,
            defaults,
            shapes,
            slots,
            dirty,
            fresh,
            removed,
            ..
        } = self;
        let slot = &mut slots[place];
        let view = View {
            bank,
            cols,
            defaults,
            store: &input.store,
        };
        // 1. Členství: jen když se příznaky slovní zásoby změnily.
        let changed_flags = !slot.synced || slot.flags != input.flags;
        fresh.clear();
        removed.clear();
        if changed_flags {
            let is_member = |number: usize| {
                input.flags[number] != 0
                    && at_kind(cols, number) == KIND_WORD
                    && item(cols.class, number, -1) >= 0
                    && item(cols.cell, number, -1) >= 0
            };
            let mut next = 0;
            let old = &slot.members;
            for number in 0..input.flags.len() {
                if !is_member(number) {
                    continue;
                }
                let number = number as u32;
                while next < old.len() && old[next] < number {
                    removed.push(old[next]);
                    next += 1;
                }
                if next < old.len() && old[next] == number {
                    next += 1;
                } else {
                    fresh.push(number);
                }
            }
            removed.extend_from_slice(&old[next..]);
        }
        // 2. Členové, jejichž syrový stav se od započítaného liší.
        dirty.clear();
        let kept = slot
            .members
            .iter()
            .filter(|number| removed.binary_search(number).is_err());
        for &number in kept.chain(fresh.iter()) {
            let seen = slot.seen.get(number as usize).copied().unwrap_or(FRESH);
            if seen != view.seen(number as usize) {
                dirty.push(number);
            }
        }
        // Výchozí tvary, které ještě nejsou v aréně.
        let mut needs: Needs = Vec::new();
        for &number in dirty.iter() {
            let root = item(cols.lexeme, number as usize, -1);
            for unit in [number as i32, root] {
                if unit >= 0 && view.form(unit as usize).is_none() {
                    needs.push(unit as u32);
                }
            }
        }
        if !needs.is_empty() {
            needs.sort_unstable();
            needs.dedup();
            return Ok(needs);
        }
        // 3. Úprava stavu.
        if slot.seen.len() < input.flags.len() {
            slot.seen.resize(input.flags.len(), FRESH);
            slot.contrib.resize(input.flags.len(), NO_CONTRIB);
        }
        let touched = changed_flags || !dirty.is_empty();
        for &number in removed.iter() {
            let unit = number as usize;
            if slot.contrib[unit].counted {
                let value = slot.contrib[unit];
                slot.take(cols.class[unit], cols.cell[unit], &value);
                slot.contrib[unit] = NO_CONTRIB;
            }
            slot.seen[unit] = FRESH;
        }
        if changed_flags {
            let members = &mut slot.members;
            members.retain(|number| removed.binary_search(number).is_err());
            members.extend_from_slice(fresh);
            members.sort_unstable();
            slot.flags.clear();
            slot.flags.extend_from_slice(input.flags);
        }
        for &number in dirty.iter() {
            let unit = number as usize;
            if slot.contrib[unit].counted {
                let value = slot.contrib[unit];
                slot.take(cols.class[unit], cols.cell[unit], &value);
            }
            let root = item(cols.lexeme, unit, -1) as usize;
            let facts = Facts {
                form: view.form(unit).expect("výchozí tvar je v aréně"),
                root: view.form(root).expect("výchozí tvar kořene je v aréně"),
                boundary: view.boundary(unit),
                exponent: view.exponent(unit),
            };
            let (class, cell) = (cols.class[unit], cols.cell[unit]);
            let merged = facts.form == facts.root;
            let exponent = facts.exponent.max(-1);
            let shape = if exponent >= 0 {
                shapes.intern(facts.ending())
            } else {
                0
            };
            let (productive, ends) = {
                let stats = slot.cell_index(class, cell);
                (slot.cells[stats].productive, slot.cells[stats].ends)
            };
            let value = Contrib {
                counted: true,
                exponent,
                shape,
                merged,
                leveling: facts.stem() != facts.root,
                extension: extension_of(productive, ends, exponent, merged),
            };
            slot.give(class, cell, &value);
            slot.contrib[unit] = value;
            slot.seen[unit] = view.seen(unit);
        }
        slot.synced = true;
        if touched {
            refresh_cells(slot, names, shapes, cols);
        }
        Ok(Vec::new())
    }

    /// Počty míst vyrovnání a rozšíření kódu.
    pub fn counts(&self, token: i64) -> (u32, u32) {
        self.slot(token)
            .map_or((0, 0), |s| (s.leveling, s.extension))
    }

    /// Slabost buňky: podíl tvarů splynulých s citačním tvarem (1, když tvary nejsou).
    pub fn weakness(&self, token: i64, class: i32, cell: i32) -> f64 {
        match self.slot(token).and_then(|s| s.find(class, cell)) {
            Some(stats) if stats.total > 0 => f64::from(stats.merged) / f64::from(stats.total),
            _ => 1.0,
        }
    }

    /// Koncovka, kterou by buňka mohla předat jiné funkci (produktivní, s neprázdnou
    /// podobou), nebo −1.
    pub fn residual(&self, token: i64, class: i32, cell: i32) -> i32 {
        match self.slot(token).and_then(|s| s.find(class, cell)) {
            Some(stats) if stats.productive >= 0 && stats.ends => stats.productive,
            _ => -1,
        }
    }

    /// Místa vyrovnání (`extension` nepravda) či rozšíření seřazená podle řetězcového
    /// ID místa: čísla tvarů a (u rozšíření) čísla koncovek.
    pub fn candidates(&self, token: i64, extension: bool) -> (Vec<u32>, Vec<i32>) {
        let Some(slot) = self.slot(token) else {
            return (Vec::new(), Vec::new());
        };
        let mut found: Vec<(u32, i32)> = slot
            .members
            .iter()
            .filter_map(|&number| {
                let value = slot.contrib[number as usize];
                if extension {
                    (value.extension >= 0).then_some((number, value.extension))
                } else {
                    value.leveling.then_some((number, -1))
                }
            })
            .collect();
        let names = &self.names;
        let key = |item: &(u32, i32)| -> Vec<u8> {
            let mut bytes = names.get(item.0 as usize).to_vec();
            bytes.push(b'|');
            if extension {
                bytes.extend_from_slice(names.get(item.1 as usize));
            }
            bytes
        };
        found.sort_by_cached_key(key);
        found.into_iter().unzip()
    }

    /// Počty koncovek (třída, buňka, koncovka, počet) a podoby koncovek
    /// (koncovka, hlásky, počet), obojí po položkách seřazených podle čísel.
    #[allow(clippy::type_complexity)]
    pub fn stats(&self, token: i64) -> (Vec<[i64; 4]>, Vec<(i32, Vec<i32>, u32)>) {
        let Some(slot) = self.slot(token) else {
            return (Vec::new(), Vec::new());
        };
        let mut cells = Vec::new();
        for stats in &slot.cells {
            let mut sorted = stats.exponents.clone();
            sorted.sort_unstable();
            for (exponent, count) in sorted {
                cells.push([
                    i64::from(stats.class),
                    i64::from(stats.cell),
                    i64::from(exponent),
                    i64::from(count),
                ]);
            }
        }
        let mut exponents: Vec<_> = slot.shapes.keys().copied().collect();
        exponents.sort_unstable();
        let mut shapes = Vec::new();
        for exponent in exponents {
            let mut counts = slot.shapes[&exponent].clone();
            counts.sort_by(|a, b| self.shapes.get(a.0).cmp(self.shapes.get(b.0)));
            for (shape, count) in counts {
                shapes.push((exponent, self.shapes.get(shape).to_vec(), count));
            }
        }
        (cells, shapes)
    }

    /// Koncovky buňky (třída, buňka) kódu a počty tvarů, které je nesou (`class_stats.exponents`);
    /// pořadí není určené, `None`, když buňka nemá žádný tvar s koncovkou. Hodnocení analogických
    /// změn z toho čte podíly koncovek.
    pub fn cell_exponents(&self, token: i64, class: i32, cell: i32) -> Option<&[(i32, u32)]> {
        let stats = self.slot(token)?.find(class, cell)?;
        if stats.exponents.is_empty() {
            None
        } else {
            Some(&stats.exponents)
        }
    }

    /// Nejčastější dnešní podoba koncovky (`class_stats.endings`), nebo `None`, když ji nenese
    /// žádný tvar slova kódu. Při shodě počtů vyhrává menší posloupnost hlásek.
    pub fn dominant_ending(&self, token: i64, exponent: i32) -> Option<&[i32]> {
        let slot = self.slot(token)?;
        slot.dominant_shape(exponent, &self.shapes)
            .map(|shape| self.shapes.get(shape))
    }

    /// Výchozí tvar morfému v aréně (`Defaults`), pokud tam je.
    pub fn default_form(&self, number: usize) -> Option<&[i32]> {
        self.defaults.get(number)
    }

    /// Čísla členů kódu vzestupně (pro testy).
    pub fn members(&self, token: i64) -> Vec<u32> {
        self.slot(token)
            .map_or_else(Vec::new, |s| s.members.clone())
    }
}

fn at_kind(cols: &Columns<'_>, number: usize) -> i8 {
    item(cols.kind, number, -1)
}

/// Přepočítá popisovače buněk a kandidáty rozšíření tam, kde se popisovač změnil.
fn refresh_cells(slot: &mut Slot, names: &Names, shapes: &Shapes, cols: &Columns<'_>) {
    let mut changed: Vec<usize> = Vec::new();
    for index in 0..slot.cells.len() {
        let productive = Slot::productive(&slot.cells[index], names);
        let ends = productive >= 0
            && slot
                .dominant_shape(productive, shapes)
                .is_some_and(|shape| !shapes.get(shape).is_empty());
        let cell = &mut slot.cells[index];
        if cell.productive != productive || cell.ends != ends {
            cell.productive = productive;
            cell.ends = ends;
            changed.push(index);
        }
    }
    if changed.is_empty() {
        return;
    }
    let keys: Vec<(i32, i32, i32, bool)> = changed
        .iter()
        .map(|&index| {
            let cell = &slot.cells[index];
            (cell.class, cell.cell, cell.productive, cell.ends)
        })
        .collect();
    for position in 0..slot.members.len() {
        let unit = slot.members[position] as usize;
        let key = (cols.class[unit], cols.cell[unit]);
        if let Some(&(_, _, productive, ends)) = keys
            .iter()
            .find(|(class, cell, _, _)| (*class, *cell) == key)
        {
            let value = slot.contrib[unit];
            let extension = extension_of(productive, ends, value.exponent, value.merged);
            if extension != value.extension {
                slot.extension =
                    slot.extension + u32::from(extension >= 0) - u32::from(value.extension >= 0);
                slot.contrib[unit].extension = extension;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct World {
        kind: Vec<i8>,
        class: Vec<i32>,
        cell: Vec<i32>,
        lexeme: Vec<i32>,
        exponent: Vec<i32>,
        boundary: Vec<i32>,
    }

    impl World {
        fn cols(&self) -> Columns<'_> {
            Columns {
                kind: &self.kind,
                class: &self.class,
                cell: &self.cell,
                lexeme: &self.lexeme,
                exponent: &self.exponent,
                boundary: &self.boundary,
            }
        }
    }

    /// Kořen 0 (třída 0) a jeho tvary 1 a 2 v buňce 1; koncovky 3 a 4.
    /// Tvary mají výchozí podobu kmen [1, 2] + koncovka 3 s podobou [5].
    fn world() -> World {
        World {
            kind: vec![0, 2, 2, 1, 1],
            class: vec![0, 0, 0, 0, 0],
            cell: vec![-1, 1, 1, 1, 1],
            lexeme: vec![0, 0, 0, 3, 4],
            exponent: vec![-1, 3, 3, -1, -1],
            boundary: vec![-1, 2, 2, -1, -1],
        }
    }

    fn start(bank: &mut Bank) -> MorphIndex {
        let mut index = MorphIndex::new();
        index.names.extend(&["a", "b", "c", "x", "y"]);
        index.defaults.set(0, &[1, 2]);
        index.defaults.set(1, &[1, 2, 5]);
        index.defaults.set(2, &[1, 2, 5]);
        bank.push(&[1, 2]).expect("tvar 0");
        bank.push(&[3, 2]).expect("tvar 1");
        index
    }

    fn sync(index: &mut MorphIndex, bank: &Bank, world: &World, store: [&[i32]; 3]) {
        let input = CodeInput {
            token: 7,
            flags: &[1, 1, 1, 0, 0],
            store: Store {
                form: store[0],
                boundary: store[1],
                exponent: store[2],
            },
        };
        let needs = index.sync(bank, &world.cols(), &input).expect("sync");
        assert!(needs.is_empty());
    }

    #[test]
    fn dorovnani_kandidatu_a_slabosti() {
        let mut bank = Bank::new(10, vec![false; 11]).expect("banka");
        let mut index = start(&mut bank);
        let world = world();
        let none = [-1_i32; 5];
        sync(&mut index, &bank, &world, [&none, &none, &none]);
        assert_eq!(index.members(7), vec![1, 2]);
        // Kmen je citační tvar a tvary nesplynuly: žádné místo.
        assert_eq!(index.counts(7), (0, 0));
        assert_eq!(index.weakness(7, 0, 1), 0.0);
        let (cells, shapes) = index.stats(7);
        assert_eq!(cells, vec![[0, 1, 3, 2]]);
        assert_eq!(shapes, vec![(3, vec![5], 2)]);
        // Tvar 2 splyne s citačním tvarem (bez koncovky): polovina buňky splynula.
        let (mut form, mut boundary, mut exponent) = (none, none, none);
        (form[2], boundary[2], exponent[2]) = (0, 2, 3);
        sync(&mut index, &bank, &world, [&form, &boundary, &exponent]);
        assert_eq!(index.weakness(7, 0, 1), 0.5);
        // Podoby [5] a [] jsou stejně časté, vyhrává menší (prázdná): koncovka bez podoby.
        assert_eq!(index.residual(7, 0, 1), -1);
        assert_eq!(index.counts(7), (0, 0));
        // Tvar 2 dostane kmen [3] a jinou koncovku: místo vyrovnání i rozšíření.
        (form[2], boundary[2], exponent[2]) = (1, 1, 4);
        sync(&mut index, &bank, &world, [&form, &boundary, &exponent]);
        assert_eq!(index.counts(7), (1, 1));
        assert_eq!(index.residual(7, 0, 1), 3);
        assert_eq!(index.candidates(7, false), (vec![2], vec![-1]));
        assert_eq!(index.candidates(7, true), (vec![2], vec![3]));
        // Návrat k výchozímu stavu vrátí i místa.
        sync(&mut index, &bank, &world, [&none, &none, &none]);
        assert_eq!(index.counts(7), (0, 0));
        assert_eq!(index.weakness(7, 0, 1), 0.0);
    }

    #[test]
    fn chybejici_vychozi_tvar_se_vyzada() {
        let mut bank = Bank::new(10, vec![false; 11]).expect("banka");
        let mut index = MorphIndex::new();
        index.names.extend(&["a", "b", "c", "x", "y"]);
        bank.push(&[1]).expect("tvar");
        let world = world();
        let none = [-1_i32; 5];
        let input = CodeInput {
            token: 1,
            flags: &[1, 1, 1, 0, 0],
            store: Store {
                form: &none,
                boundary: &none,
                exponent: &none,
            },
        };
        let needs = index.sync(&bank, &world.cols(), &input).expect("sync");
        assert_eq!(needs, vec![0, 1, 2]);
        assert!(index.members(1).is_empty());
    }
}

//! Banka tvarů a tabulky procesů: zrcadlo `cee.v2.language.bank`.
//!
//! Čísla tvarů se přidělují po řadě a shodují se s Pythonem: banka v Pythonu
//! je zdroj pravdy o tom, které tvary existují, a každý nový tvar sem pošle
//! (`push`). Tvary, které vzniknou tady (výsledky procesů), se vrací Pythonu
//! (`take_created`) hned v téže otázce, takže se číslování nerozejde.
//!
//! Nic tu nezávisí na pořadí průchodu slovníkem s náhodným hasherem:
//! vyhledání tvaru používá pevný hasher a tvary se řadí jen podle čísla.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::hash::{BuildHasherDefault, Hasher};

use crate::process::{apply, apply_cut, has_site, missing_map, Proc, Scratch, RULE_COUNT};

/// V tabulce procesu: tvar se zatím nezkoumal.
pub const UNKNOWN: i64 = -2;
/// V tabulce procesu: proces tvar nemění.
pub const UNCHANGED: i64 = -1;

const NO_NEXT: u32 = u32::MAX;

/// Hasher, který jen vrací číslo, které dostal (klíčem je už hash tvaru).
#[derive(Default)]
pub struct IdentityHasher(u64);

impl Hasher for IdentityHasher {
    fn finish(&self) -> u64 {
        self.0
    }
    fn write(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            self.0 = (self.0 << 8) | u64::from(byte);
        }
    }
    fn write_u64(&mut self, value: u64) {
        self.0 = value;
    }
}

type Index = HashMap<u64, u32, BuildHasherDefault<IdentityHasher>>;

/// FNV-1a přes hlásky tvaru; pevná funkce bez náhodné soli.
fn hash_form(form: &[i32]) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for &segment in form {
        hash ^= u64::from(segment as u32);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash ^ (form.len() as u64)
}

/// Bity změn, kterým hláska může být cílem, levým a pravým sousedem.
#[derive(Default, Clone)]
struct SegmentBits {
    target: Vec<u64>,
    left: Vec<u64>,
    right: Vec<u64>,
    /// Počet změn, které už bity hlásky zahrnují.
    known: usize,
}

/// Výsledky jednoho procesu s jedním pravidlem přízvuku pro každý tvar.
#[derive(Default)]
struct Table {
    results: Vec<i64>,
}

/// Co vrátí dávkový výpočet: buď výsledky, nebo hlásky, jejichž výstup změny
/// musí napřed spočítat Python.
pub enum Outcome {
    Done(Vec<i64>),
    Needs(Vec<i32>),
}

/// Hlásky, jejichž výstup operace `change` či `tone` musí napřed spočítat
/// Python, podle řádku změny.
pub type MapNeeds = BTreeMap<usize, BTreeSet<i32>>;

/// Výsledek aplikace změny na tvar i s hranicí kmen | koncovka.
#[derive(Debug, PartialEq, Eq)]
pub enum Applied {
    /// Chybí mapa hlásek (viz `MapNeeds`), nic se nespočítalo.
    Blocked,
    /// Změna tvar nemění, nebo by slovo zaniklo.
    Unchanged,
    /// Nový tvar (číslo v bance) a nová hranice kmen | koncovka (−1 = žádná).
    Changed { form: u32, cut: i32 },
}

pub struct Bank {
    boundary: i32,
    pub(crate) vowel: Vec<bool>,
    /// Hlásky, které jsou polosamohlásky (sonorita 3), pro příznakovost slabik.
    pub(crate) glide: Vec<bool>,
    /// Příznakovost slabičné stavby tvaru (NaN = zatím nespočítaná), viz `assess`.
    pub(crate) marked: Vec<f64>,
    flat: Vec<i32>,
    starts: Vec<usize>,
    lengths: Vec<u32>,
    index: Index,
    chain: Vec<u32>,
    /// Kolik tvarů zná Python; od tohoto čísla výš jsou tvary vzniklé tady.
    python_known: usize,
    procs: Vec<Proc>,
    tables: Vec<Option<Table>>,
    segment_bits: Vec<SegmentBits>,
    /// Pro každý tvar: pro kolik změn už je předfiltrován, a jeho bity.
    screened: Vec<u32>,
    rows: Vec<Vec<u64>>,
    scratch: Scratch,
}

impl Bank {
    pub fn new(boundary: i32, vowel: Vec<bool>) -> Result<Bank, String> {
        if boundary < 0 || vowel.len() != boundary as usize + 1 {
            return Err("maska samohlásek musí mít délku „počet hlásek + 1“".into());
        }
        Ok(Bank {
            boundary,
            segment_bits: vec![SegmentBits::default(); vowel.len()],
            glide: vec![false; vowel.len()],
            marked: Vec::new(),
            vowel,
            flat: Vec::new(),
            starts: Vec::new(),
            lengths: Vec::new(),
            index: Index::default(),
            chain: Vec::new(),
            python_known: 0,
            procs: Vec::new(),
            tables: Vec::new(),
            screened: Vec::new(),
            rows: Vec::new(),
            scratch: Scratch::default(),
        })
    }

    /// Nastaví polosamohlásky (maska délky „počet hlásek + 1“); už spočítaná
    /// příznakovost tvarů se zahodí.
    pub fn set_glide(&mut self, glide: Vec<bool>) -> Result<(), String> {
        if glide.len() != self.vowel.len() {
            return Err("maska polosamohlásek musí mít délku „počet hlásek + 1“".into());
        }
        self.glide = glide;
        self.marked.clear();
        Ok(())
    }

    pub fn len(&self) -> usize {
        self.lengths.len()
    }

    pub fn is_empty(&self) -> bool {
        self.lengths.is_empty()
    }

    pub fn proc_count(&self) -> usize {
        self.procs.len()
    }

    pub(crate) fn form(&self, id: usize) -> &[i32] {
        let start = self.starts[id];
        &self.flat[start..start + self.lengths[id] as usize]
    }

    fn find(&self, form: &[i32], hash: u64) -> Option<u32> {
        let mut current = *self.index.get(&hash)?;
        loop {
            if self.form(current as usize) == form {
                return Some(current);
            }
            current = self.chain[current as usize];
            if current == NO_NEXT {
                return None;
            }
        }
    }

    /// Číslo tvaru; nový tvar dostane další číslo.
    fn intern(&mut self, form: &[i32]) -> u32 {
        let hash = hash_form(form);
        if let Some(found) = self.find(form, hash) {
            return found;
        }
        let id = self.lengths.len() as u32;
        self.starts.push(self.flat.len());
        self.lengths.push(form.len() as u32);
        self.flat.extend_from_slice(form);
        // Nový tvar se zařadí na začátek řetězce tvarů se stejným hashem.
        let next = self.index.insert(hash, id).unwrap_or(NO_NEXT);
        self.chain.push(next);
        id
    }

    fn check_segments(&self, form: &[i32]) -> Result<(), String> {
        match form
            .iter()
            .find(|&&segment| segment < 0 || segment >= self.boundary)
        {
            Some(segment) => Err(format!("hláska {segment} není v tabulce hlásek")),
            None => Ok(()),
        }
    }

    /// Tvar, který vznikl v Pythonu. Vrací jeho číslo, které se musí shodovat
    /// s číslem v Pythonu (jinak se banky rozešly).
    pub fn push(&mut self, form: &[i32]) -> Result<u32, String> {
        self.check_segments(form)?;
        if self.python_known != self.len() {
            return Err("banka má tvary, které Python ještě nepřevzal".into());
        }
        let before = self.len();
        let id = self.intern(form);
        if id as usize != before {
            return Err("tvar už v bance je, Python ho měl znát".into());
        }
        self.python_known = self.len();
        Ok(id)
    }

    /// Tvary vzniklé tady od posledního převzetí: (číslo prvního, hlásky, délky).
    pub fn take_created(&mut self) -> (usize, Vec<i32>, Vec<i64>) {
        let first = self.python_known;
        let begin = if first < self.len() {
            self.starts[first]
        } else {
            self.flat.len()
        };
        let flat = self.flat[begin..].to_vec();
        let lengths = self.lengths[first..]
            .iter()
            .map(|&length| i64::from(length))
            .collect();
        self.python_known = self.len();
        (first, flat, lengths)
    }

    pub fn register_proc(&mut self, row: usize, proc: Proc) -> Result<(), String> {
        if row != self.procs.len() {
            return Err(format!(
                "změna č. {row} se registruje mimo pořadí (čekáno {})",
                self.procs.len()
            ));
        }
        let size = self.vowel.len();
        let masks = [&proc.target, &proc.left, &proc.right, &proc.right2];
        if masks.iter().any(|mask| mask.len() != size) || proc.map.len() != size - 1 {
            return Err("masky změny mají špatnou délku".into());
        }
        self.procs.push(proc);
        Ok(())
    }

    pub fn set_map(&mut self, row: usize, segments: &[i64], outputs: &[i64]) -> Result<(), String> {
        let proc = self.procs.get_mut(row).ok_or("neznámá změna")?;
        if segments.len() != outputs.len() {
            return Err("délky polí se liší".into());
        }
        for (&segment, &output) in segments.iter().zip(outputs) {
            if segment < 0 || segment as usize >= proc.map.len() {
                return Err(format!("hláska {segment} není v tabulce hlásek"));
            }
            proc.map[segment as usize] = output as i32;
        }
        Ok(())
    }

    // --- bitové předfiltry --------------------------------------------------

    fn ensure_segment_bits(&mut self, segment: usize) {
        let count = self.procs.len();
        let bits = &mut self.segment_bits[segment];
        if bits.known >= count {
            return;
        }
        let words = count.div_ceil(64);
        bits.target.resize(words, 0);
        bits.left.resize(words, 0);
        bits.right.resize(words, 0);
        for row in bits.known..count {
            let proc = &self.procs[row];
            let (word, bit) = (row / 64, 1u64 << (row % 64));
            if proc.target[segment] {
                bits.target[word] |= bit;
            }
            if proc.left[segment] {
                bits.left[word] |= bit;
            }
            if proc.right[segment] {
                bits.right[word] |= bit;
            }
        }
        bits.known = count;
    }

    /// Hromadný předfiltr (`FormBank.screen`): které změny v tvaru mají místo.
    pub fn screen(&mut self, form_id: usize) -> Result<(), String> {
        if form_id >= self.len() {
            return Err(format!("tvar č. {form_id} neexistuje"));
        }
        if self.screened.len() <= form_id {
            self.screened.resize(form_id + 1, 0);
            self.rows.resize(form_id + 1, Vec::new());
        }
        let count = self.procs.len();
        if self.screened[form_id] as usize >= count {
            return Ok(());
        }
        let words = count.div_ceil(64);
        let mut bits = vec![0u64; words];
        let (start, size) = (self.starts[form_id], self.lengths[form_id] as usize);
        let boundary = self.boundary as usize;
        for position in 0..size {
            let segment = self.flat[start + position] as usize;
            let previous = if position > 0 {
                self.flat[start + position - 1] as usize
            } else {
                boundary
            };
            let following = if position + 1 < size {
                self.flat[start + position + 1] as usize
            } else {
                boundary
            };
            self.ensure_segment_bits(segment);
            self.ensure_segment_bits(previous);
            self.ensure_segment_bits(following);
            let target = &self.segment_bits[segment].target;
            let left = &self.segment_bits[previous].left;
            let right = &self.segment_bits[following].right;
            for word in 0..words {
                bits[word] |= target[word] & left[word] & right[word];
            }
        }
        self.rows[form_id] = bits;
        self.screened[form_id] = count as u32;
        Ok(())
    }

    /// Bity změn, které v tvaru mohou mít místo (po slovech od nejnižších bitů).
    pub fn rows_of(&mut self, form_id: usize) -> Result<Vec<u64>, String> {
        self.screen(form_id)?;
        Ok(self.rows[form_id].clone())
    }

    pub fn may_apply(&mut self, form_id: usize, row: usize) -> Result<bool, String> {
        self.screen(form_id)?;
        Ok(self.rows[form_id]
            .get(row / 64)
            .is_some_and(|word| (word >> (row % 64)) & 1 == 1))
    }

    // --- tabulky procesů ----------------------------------------------------

    fn table_mut(&mut self, row: usize, rule: u8) -> Result<&mut Table, String> {
        if row >= self.procs.len() || rule as usize >= RULE_COUNT {
            return Err("neznámá změna nebo pravidlo přízvuku".into());
        }
        let slot = row * RULE_COUNT + rule as usize;
        if self.tables.len() <= slot {
            self.tables.resize_with(slot + 1, || None);
        }
        Ok(self.tables[slot].get_or_insert_with(Table::default))
    }

    fn grow_results(&mut self, row: usize, rule: u8, top: usize) -> Result<(), String> {
        let table = self.table_mut(row, rule)?;
        if top >= table.results.len() {
            let size = (top + 1).max(2 * table.results.len()).max(64);
            table.results.resize(size, UNKNOWN);
        }
        Ok(())
    }

    fn stored(&self, row: usize, rule: u8, form_id: usize) -> i64 {
        let slot = row * RULE_COUNT + rule as usize;
        self.tables
            .get(slot)
            .and_then(|table| table.as_ref())
            .and_then(|table| table.results.get(form_id))
            .copied()
            .unwrap_or(UNKNOWN)
    }

    fn store(&mut self, row: usize, rule: u8, form_id: usize, value: i64) {
        let slot = row * RULE_COUNT + rule as usize;
        if let Some(Some(table)) = self.tables.get_mut(slot) {
            table.results[form_id] = value;
        }
    }

    /// Výsledek procesu pro každý tvar (`ProcessTable.results`). Tvary bez
    /// místa se hromadně označí jako beze změny, proces se aplikuje jen na
    /// zbytek a v pořadí čísel tvarů, takže nové tvary dostanou stejná čísla
    /// jako v Pythonu.
    pub fn results(&mut self, row: usize, rule: u8, form_ids: &[i64]) -> Result<Outcome, String> {
        let size = self.len();
        let mut top = 0usize;
        for &id in form_ids {
            if id < 0 || id as usize >= size {
                return Err(format!("tvar č. {id} neexistuje"));
            }
            top = top.max(id as usize);
        }
        if form_ids.is_empty() {
            return Ok(Outcome::Done(Vec::new()));
        }
        self.grow_results(row, rule, top)?;
        let mut missing: Vec<usize> = form_ids
            .iter()
            .map(|&id| id as usize)
            .filter(|&id| self.stored(row, rule, id) == UNKNOWN)
            .collect();
        missing.sort_unstable();
        missing.dedup();
        // Tvary bez místa pro změnu se hromadně označí, aplikuje se jen na zbytek.
        let mut candidates = Vec::with_capacity(missing.len());
        for &id in &missing {
            if has_site(&self.procs[row], self.form(id), self.boundary) {
                candidates.push(id);
            } else {
                self.store(row, rule, id, UNCHANGED);
            }
        }
        // Nejdřív zjistit, které výstupy změn Python ještě nespočítal; dokud
        // něco chybí, nic se nemění (ani nové tvary), ať zůstane pořadí čísel.
        let mut needs = BTreeSet::new();
        for &id in &candidates {
            let (start, length) = (self.starts[id], self.lengths[id] as usize);
            missing_map(
                &self.procs[row],
                &self.flat[start..start + length],
                &self.vowel,
                self.boundary,
                rule,
                &mut self.scratch,
                &mut needs,
            );
        }
        if !needs.is_empty() {
            return Ok(Outcome::Needs(needs.into_iter().collect()));
        }
        for &id in &candidates {
            let (start, length) = (self.starts[id], self.lengths[id] as usize);
            let changed = apply(
                &self.procs[row],
                &self.flat[start..start + length],
                &self.vowel,
                self.boundary,
                rule,
                &mut self.scratch,
            );
            let value = match changed {
                None => UNCHANGED,
                Some(form) => i64::from(self.intern(&form)),
            };
            self.store(row, rule, id, value);
        }
        let out = form_ids
            .iter()
            .map(|&id| self.stored(row, rule, id as usize))
            .collect();
        Ok(Outcome::Done(out))
    }

    /// Výsledek pro jeden tvar bez režie polí. Vrací už známý výsledek,
    /// ``NEEDS_MAP``, když Python musí napřed doplnit mapu hlásek, nebo
    /// ``CREATED``, když vznikl nový tvar, který si má Python převzít
    /// (výsledek je pak uložen a vrátí ho další dotaz).
    pub fn result(&mut self, row: usize, rule: u8, form_id: usize) -> Result<i64, String> {
        if form_id >= self.len() {
            return Err(format!("tvar č. {form_id} neexistuje"));
        }
        let found = self.stored(row, rule, form_id);
        if found != UNKNOWN {
            return Ok(found);
        }
        if row >= self.procs.len() || rule as usize >= RULE_COUNT {
            return Err("neznámá změna nebo pravidlo přízvuku".into());
        }
        self.grow_results(row, rule, form_id)?;
        if !has_site(&self.procs[row], self.form(form_id), self.boundary) {
            self.store(row, rule, form_id, UNCHANGED);
            return Ok(UNCHANGED);
        }
        let (start, length) = (self.starts[form_id], self.lengths[form_id] as usize);
        let mut needs = BTreeSet::new();
        missing_map(
            &self.procs[row],
            &self.flat[start..start + length],
            &self.vowel,
            self.boundary,
            rule,
            &mut self.scratch,
            &mut needs,
        );
        if !needs.is_empty() {
            return Ok(NEEDS_MAP);
        }
        let before = self.len();
        let changed = apply(
            &self.procs[row],
            &self.flat[start..start + length],
            &self.vowel,
            self.boundary,
            rule,
            &mut self.scratch,
        );
        let value = match changed {
            None => UNCHANGED,
            Some(form) => i64::from(self.intern(&form)),
        };
        self.store(row, rule, form_id, value);
        Ok(if self.len() > before { CREATED } else { value })
    }

    /// Výsledek procesu pro jeden tvar jako `result`, ale nevrací kódy chyb:
    /// `None` znamená, že chybí mapa hlásek (zapsaná do `needs`), jinak číslo
    /// výsledného tvaru nebo `UNCHANGED`. Nový tvar vzniklý aplikací si
    /// převezme Python z `take_created`.
    pub fn lookup(
        &mut self,
        row: usize,
        rule: u8,
        form_id: usize,
        needs: &mut MapNeeds,
    ) -> Result<Option<i64>, String> {
        Ok(match self.result(row, rule, form_id)? {
            NEEDS_MAP => {
                self.collect_needs(row, rule, form_id, needs);
                None
            }
            CREATED => Some(self.stored(row, rule, form_id)),
            found => Some(found),
        })
    }

    fn collect_needs(&mut self, row: usize, rule: u8, form_id: usize, needs: &mut MapNeeds) {
        let (start, length) = (self.starts[form_id], self.lengths[form_id] as usize);
        let mut missing = BTreeSet::new();
        missing_map(
            &self.procs[row],
            &self.flat[start..start + length],
            &self.vowel,
            self.boundary,
            rule,
            &mut self.scratch,
            &mut missing,
        );
        if !missing.is_empty() {
            needs.entry(row).or_default().extend(missing);
        }
    }

    /// Aplikace změny na konkrétní tvar i s hranicí kmen | koncovka (`cut`,
    /// −1 = žádná): `Process.apply_tracked`. Tabulka výsledků se nepoužije
    /// ani nezmění; nový tvar se zařadí do banky.
    pub fn apply_tracked(
        &mut self,
        row: usize,
        rule: u8,
        form_id: usize,
        cut: i32,
        needs: &mut MapNeeds,
    ) -> Result<Applied, String> {
        if form_id >= self.len() {
            return Err(format!("tvar č. {form_id} neexistuje"));
        }
        if row >= self.procs.len() || rule as usize >= RULE_COUNT {
            return Err("neznámá změna nebo pravidlo přízvuku".into());
        }
        let (start, length) = (self.starts[form_id], self.lengths[form_id] as usize);
        let mut missing = BTreeSet::new();
        missing_map(
            &self.procs[row],
            &self.flat[start..start + length],
            &self.vowel,
            self.boundary,
            rule,
            &mut self.scratch,
            &mut missing,
        );
        if !missing.is_empty() {
            needs.entry(row).or_default().extend(missing);
            return Ok(Applied::Blocked);
        }
        let changed = apply_cut(
            &self.procs[row],
            &self.flat[start..start + length],
            &self.vowel,
            self.boundary,
            rule,
            cut,
            &mut self.scratch,
        );
        Ok(match changed {
            None => Applied::Unchanged,
            Some((form, cut)) => Applied::Changed {
                form: self.intern(&form),
                cut,
            },
        })
    }

    /// Hlásky tvaru (pro testy a převody).
    pub fn form_of(&self, form_id: usize) -> &[i32] {
        self.form(form_id)
    }

    /// Uložené výsledky tabulky (pro testy a ladění); chybějící jsou `UNKNOWN`.
    pub fn stored_results(&self, row: usize, rule: u8) -> Vec<i64> {
        let slot = row * RULE_COUNT + rule as usize;
        match self.tables.get(slot).and_then(|table| table.as_ref()) {
            Some(table) => table.results[..self.len().min(table.results.len())].to_vec(),
            None => Vec::new(),
        }
    }
}

/// Návratové hodnoty `Bank::result`, které nejsou číslem tvaru.
pub const NEEDS_MAP: i64 = -3;
pub const CREATED: i64 = -4;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::process::{OP_DELETE, OP_REPLACE, STRESS_NONE};

    /// Čtyři hlásky: 0 = a, 1 = k, 2 = t, 3 = d; hranice = 4.
    fn bank() -> Bank {
        let mut bank = Bank::new(4, vec![true, false, false, false, false]).unwrap();
        let everything = vec![true; 5];
        let mut target = vec![false; 5];
        target[2] = true;
        let mut vowels = vec![false; 5];
        vowels[0] = true;
        bank.register_proc(
            0,
            Proc {
                operation: OP_REPLACE,
                stress: STRESS_NONE,
                medial: false,
                segment: 3,
                target,
                left: vowels.clone(),
                right: vowels,
                right2: everything.clone(),
                map: vec![-3; 4],
            },
        )
        .unwrap();
        let mut target = vec![false; 5];
        target[1] = true;
        bank.register_proc(
            1,
            Proc {
                operation: OP_DELETE,
                stress: STRESS_NONE,
                medial: false,
                segment: -1,
                target,
                left: everything.clone(),
                right: everything.clone(),
                right2: everything,
                map: vec![-3; 4],
            },
        )
        .unwrap();
        bank
    }

    #[test]
    fn tvary_dostavaji_cisla_po_rade_a_duplicity_ne() {
        let mut bank = bank();
        assert_eq!(bank.push(&[1, 0, 2, 0]).unwrap(), 0);
        assert_eq!(bank.push(&[1, 0]).unwrap(), 1);
        assert!(bank.push(&[1, 0]).is_err());
        assert_eq!(bank.len(), 2);
    }

    #[test]
    fn proces_znovu_pouzije_existujici_tvar_a_bez_mista_nic_nemeni() {
        let mut bank = bank();
        bank.push(&[1, 0, 2, 0]).unwrap(); // kata -> kada
        bank.push(&[1, 0, 3, 0]).unwrap(); // kada samo
        bank.push(&[2, 0]).unwrap(); // ta: bez místa
        match bank.results(0, 3, &[0, 1, 2, 0]).unwrap() {
            Outcome::Done(found) => assert_eq!(found, vec![1, -1, -1, 1]),
            Outcome::Needs(_) => panic!("změna nepotřebuje mapu"),
        }
        assert_eq!(bank.len(), 3);
        // Nic nevzniklo, tak není co předat Pythonu.
        let (first, flat, lengths) = bank.take_created();
        assert_eq!((first, flat.len(), lengths.len()), (3, 0, 0));
    }

    #[test]
    fn novy_tvar_se_vrati_pythonu_a_predfiltr_zna_bity() {
        let mut bank = bank();
        bank.push(&[1, 0, 2, 0]).unwrap();
        bank.push(&[0, 1, 0]).unwrap();
        // k se maže: kata -> ata, aka -> aa (pokles pod dvě hlásky nehrozí).
        match bank.results(1, 0, &[0, 1]).unwrap() {
            Outcome::Done(found) => assert_eq!(found, vec![2, 3]),
            Outcome::Needs(_) => panic!(),
        }
        let (first, flat, lengths) = bank.take_created();
        assert_eq!((first, flat, lengths), (2, vec![0, 2, 0, 0, 0], vec![3, 2]));
        assert!(bank.may_apply(0, 1).unwrap() && bank.may_apply(0, 0).unwrap());
        assert!(!bank.may_apply(1, 0).unwrap());
    }

    #[test]
    fn jednotlivy_dotaz_hlasi_vznik_noveho_tvaru() {
        let mut bank = bank();
        bank.push(&[1, 0, 2, 0]).unwrap();
        assert_eq!(bank.result(0, 3, 0).unwrap(), CREATED);
        assert_eq!(bank.result(0, 3, 0).unwrap(), 1);
        assert_eq!(bank.stored_results(0, 3), vec![1, UNKNOWN]);
    }
}

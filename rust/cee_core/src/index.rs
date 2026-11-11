//! Prostředí hlásek a opory zvukových změn: zrcadlo `cee.v2.language.sound_index`.
//!
//! Stav jednoho kódu (skupiny) tvoří ploché sloupce podle čísla morfému z registru
//! (`counted_form`, `counted_rule`), výskyty hlásek, opory kandidátů a pro každou
//! rodinu místa s mírami. Nic se neukládá po řetězcích ani v hašovacích mapách
//! v horkých cestách (mapa je jen u pojmenování prostředí a u hledání sady
//! kandidátů pro inventář, tedy při nové položce).
//!
//! **Bez deníků.** Python předá bez kopírování tři pole podle čísla morfému
//! (tvary kódu, výchozí tvary světa, příznaky slovní zásoby); jedním hustým
//! průchodem se najdou morfémy, jejichž tvar se od započítaného liší, a dorovnají
//! se jen ony. Opory kandidátů se mění o celá čísla, takže výsledek nezávisí na
//! pořadí sčítání. Míry rodin jsou `(scale · min(1, opora / 8)) / n` a jejich
//! součet je párový jako `np.sum` (`assess::pairwise_sum`).
//!
//! **Shoda kandidátů s výskytem** je průnik čtyř bitových řádků (cíl, vlevo,
//! vpravo, druhá vpravo) a filtru přízvuku; sada kandidátů se pro inventář
//! předá jednou jako transponované bitové sady (pro každý sloupec hlásky bity
//! kandidátů).
//!
//! **Určitost.** Skupiny jsou nezávislé (každá zapisuje jen do vlastního stavu),
//! společné je jen jmenování prostředí (`Contexts`), které se při dávce plní
//! předem v pevném pořadí skupin. Paralelizace po skupinách by tedy výsledek
//! nezměnila; zatím je jedno vlákno.

use std::collections::HashMap;
use std::hash::{BuildHasherDefault, Hasher};

use crate::assess::pairwise_sum;
use crate::bank::Bank;
use crate::candidates::{self, Built, Candidate, SegTable};
use crate::morphology_index::Defaults;
use crate::process::{nuclei, stressed_nucleus, RULE_COUNT};

/// V poli `counted_form`: morfém není započítán.
pub const UNCOUNTED: i32 = -2;
/// Opora, od které se kandidát nabízí, a opora plné šance.
const MIN_SUPPORT: i64 = 2;
const FULL_SUPPORT: i64 = 8;
/// Tvar, jehož prostředí se zatím nepočítala.
const UNKNOWN: u32 = u32::MAX;
/// Číslo tvaru od tohoto čísla výš je výchozí tvar morfému mimo banku: `PRIVATE` plus číslo morfému.
/// Výchozí tvary, které kód nepřepsal, drží index ve vlastní aréně (`SoundIndex::private`), aby se
/// do banky tvarů světa nezařazoval tvar, který model nepoužívá.
pub const PRIVATE: i32 = 1 << 30;

/// Deterministický hašovač (bez náhodné soli), jako `rustc-hash`.
#[derive(Default)]
pub struct Fx(u64);

impl Fx {
    fn add(&mut self, word: u64) {
        self.0 = (self.0.rotate_left(5) ^ word).wrapping_mul(0x517c_c1b7_2722_0a95);
    }
}

impl Hasher for Fx {
    fn write(&mut self, bytes: &[u8]) {
        for &byte in bytes {
            self.add(u64::from(byte));
        }
    }
    fn write_u32(&mut self, value: u32) {
        self.add(u64::from(value));
    }
    fn write_u64(&mut self, value: u64) {
        self.add(value);
    }
    fn write_usize(&mut self, value: usize) {
        self.add(value as u64);
    }
    fn finish(&self) -> u64 {
        self.0
    }
}

type FxMap<K, V> = HashMap<K, V, BuildHasherDefault<Fx>>;

/// Prostředí (předchozí, hláska, další, přízvuk, druhá další) jako čísla,
/// společná všem kódům, a prostředí tvarů (tvar × pravidlo → seznam čísel).
#[derive(Default)]
struct Contexts {
    previous: Vec<u32>,
    segment: Vec<u32>,
    following: Vec<u32>,
    following2: Vec<u32>,
    stressed: Vec<bool>,
    ids: FxMap<(u64, u64), u32>,
    /// Pro každé pravidlo a číslo tvaru: začátek a délka seznamu v `pool`.
    forms: [Vec<(u32, u32)>; RULE_COUNT],
    /// Totéž pro výchozí tvary mimo banku, podle čísla morfému.
    private_forms: [Vec<(u32, u32)>; RULE_COUNT],
    pool: Vec<u32>,
    nuclei: Vec<usize>,
    fresh: Vec<u32>,
}

impl Contexts {
    fn intern(
        &mut self,
        previous: u32,
        segment: u32,
        following: u32,
        stressed: bool,
        following2: u32,
    ) -> u32 {
        let key = (
            (u64::from(previous) << 32) | u64::from(segment),
            (u64::from(following) << 32) | (u64::from(following2) << 1) | u64::from(stressed),
        );
        if let Some(&found) = self.ids.get(&key) {
            return found;
        }
        let found = self.segment.len() as u32;
        self.previous.push(previous);
        self.segment.push(segment);
        self.following.push(following);
        self.following2.push(following2);
        self.stressed.push(stressed);
        self.ids.insert(key, found);
        found
    }

    /// Totéž jen pro čtení: už zapamatovaný seznam prostředí, jinak `None`.
    fn cached_of_form(&self, form: usize, rule: u8) -> Option<(usize, usize)> {
        let outside = form >= PRIVATE as usize;
        let (table, key) = if outside {
            (&self.private_forms[rule as usize], form - PRIVATE as usize)
        } else {
            (&self.forms[rule as usize], form)
        };
        let &(start, length) = table.get(key)?;
        (start != UNKNOWN).then_some((start as usize, length as usize))
    }

    /// Prostředí všech hlásek tvaru (čistá funkce tvaru a pravidla, proto zapamatovaná):
    /// začátek a délka seznamu v `pool`.
    fn of_form(
        &mut self,
        bank: &Bank,
        private: &Defaults,
        form: usize,
        rule: u8,
    ) -> (usize, usize) {
        let outside = form >= PRIVATE as usize;
        let key = if outside {
            form - PRIVATE as usize
        } else {
            form
        };
        let table = if outside {
            &mut self.private_forms[rule as usize]
        } else {
            &mut self.forms[rule as usize]
        };
        if table.len() <= key {
            let size = if outside {
                key + 1
            } else {
                bank.len().max(key + 1)
            };
            table.resize(size, (UNKNOWN, 0));
        }
        let (start, length) = table[key];
        if start != UNKNOWN {
            return (start as usize, length as usize);
        }
        let boundary = bank.boundary() as u32;
        let segments = if outside {
            private.get(key).expect("výchozí tvar je v aréně")
        } else {
            bank.form_of(form)
        };
        nuclei(segments, &bank.vowel, &mut self.nuclei);
        let stress = stressed_nucleus(&self.nuclei, rule, segments);
        let mut fresh = std::mem::take(&mut self.fresh);
        fresh.clear();
        let last = segments.len();
        for (index, &segment) in segments.iter().enumerate() {
            let previous = if index > 0 {
                segments[index - 1] as u32
            } else {
                boundary
            };
            let following = if index + 1 < last {
                segments[index + 1] as u32
            } else {
                boundary
            };
            let following2 = if index + 2 < last {
                segments[index + 2] as u32
            } else {
                boundary
            };
            fresh.push(self.intern(
                previous,
                segment as u32,
                following,
                stress == Some(index),
                following2,
            ));
        }
        let start = self.pool.len();
        self.pool.extend_from_slice(&fresh);
        self.fresh = fresh;
        let table = if outside {
            &mut self.private_forms[rule as usize]
        } else {
            &mut self.forms[rule as usize]
        };
        table[key] = (start as u32, last as u32);
        (start, last)
    }

    /// Vyčistí keš prostředí pro tvary, které už nejsou živé.
    fn retain_forms(&mut self, alive: &[bool]) {
        for table in &mut self.forms {
            if table.len() > alive.len() {
                table.truncate(alive.len());
            }
            for (form, slot) in table.iter_mut().enumerate() {
                if !alive[form] {
                    *slot = (UNKNOWN, 0);
                }
            }
            while let Some(&(start, _)) = table.last() {
                if start == UNKNOWN {
                    table.pop();
                } else {
                    break;
                }
            }
        }
    }
}

/// Sada kandidátů pro jeden inventář jako transponované bitové sady.
struct CandidateSet {
    inventory: Vec<u32>,
    /// Sloupce hlásek (inventář a hranice slova), seřazené.
    columns: Vec<u32>,
    count: usize,
    words: usize,
    /// `[sloupec * words + slovo]`: bity kandidátů, jejichž maska hlásku ve sloupci pouští.
    target: Vec<u64>,
    left: Vec<u64>,
    right: Vec<u64>,
    right2: Vec<u64>,
    stressed_rows: Vec<u64>,
    unstressed_rows: Vec<u64>,
    /// Konec každé rodiny v řádcích kandidátů.
    family_ends: Vec<usize>,
    /// Popisy kandidátů a ID proměnných, když sadu sestavil Rust (`candidates`).
    built: Option<Built>,
    refs: usize,
}

impl CandidateSet {
    fn column(&self, segment: u32) -> Result<usize, String> {
        self.columns
            .binary_search(&segment)
            .map_err(|_| format!("hláska {segment} nemá sloupec v maskách kandidátů"))
    }

    /// Přičte `diff` k opoře každého kandidáta, na kterého prostředí dopadne.
    fn add(
        &self,
        contexts: &Contexts,
        vowel: &[bool],
        context: usize,
        diff: i64,
        supports: &mut [i64],
    ) -> Result<(), String> {
        let segment = contexts.segment[context];
        let columns = [
            self.column(segment)?,
            self.column(contexts.previous[context])?,
            self.column(contexts.following[context])?,
            self.column(contexts.following2[context])?,
        ];
        let words = self.words;
        let stressed = contexts.stressed[context];
        let stressed_ok = if stressed { u64::MAX } else { 0 };
        let unstressed_ok = if !stressed && vowel[segment as usize] {
            u64::MAX
        } else {
            0
        };
        let rows = [
            &self.target[columns[0] * words..][..words],
            &self.left[columns[1] * words..][..words],
            &self.right[columns[2] * words..][..words],
            &self.right2[columns[3] * words..][..words],
        ];
        for word in 0..words {
            let mut bits = rows[0][word]
                & rows[1][word]
                & rows[2][word]
                & rows[3][word]
                & (!self.stressed_rows[word] | stressed_ok)
                & (!self.unstressed_rows[word] | unstressed_ok);
            while bits != 0 {
                supports[word * 64 + bits.trailing_zeros() as usize] += diff;
                bits &= bits - 1;
            }
        }
        Ok(())
    }
}

/// Místa jedné rodiny: pořadí v rodině, míry a jejich součet.
#[derive(Default, Clone)]
pub struct Family {
    pub sites: Vec<u32>,
    pub rates: Vec<f64>,
    pub total: f64,
    valid: bool,
}

#[derive(Default)]
struct Group {
    counted_form: Vec<i32>,
    counted_rule: Vec<u8>,
    /// Výskyty hlásek, seřazené podle hlásky; inventář jsou hlásky s kladným počtem.
    occurrences: Vec<(u32, i64)>,
    inventory: Vec<u32>,
    /// Inventář, pro který platí `supports`, a sada kandidátů (nebo žádná).
    valid_for: Option<Vec<u32>>,
    set: Option<usize>,
    supports: Vec<i64>,
    effective: Vec<i64>,
    families: Vec<Family>,
}

impl Group {
    fn bump(&mut self, segment: u32, diff: i64) {
        match self.occurrences.binary_search_by_key(&segment, |&(s, _)| s) {
            Ok(at) => self.occurrences[at].1 += diff,
            Err(at) => self.occurrences.insert(at, (segment, diff)),
        }
    }

    fn refresh_inventory(&mut self) {
        self.inventory.clear();
        self.inventory.extend(
            self.occurrences
                .iter()
                .filter(|&&(_, count)| count > 0)
                .map(|&(s, _)| s),
        );
    }
}

/// Vstup jedné skupiny: pole podle čísla morfému (nic se nekopíruje).
pub struct GroupInput<'a> {
    pub token: i64,
    pub rule: u8,
    pub flags: &'a [u8],
    pub forms: &'a [i32],
}

/// Práce, která zbývá po první části dorovnání skupiny.
struct Pending {
    at: usize,
    /// Opory se počítají celé (změnil se inventář), jinak jen z rozdílu `nets`.
    full: bool,
    nets: Vec<(u32, i64)>,
}

/// Co Rust vyžaduje od Pythonu, než dokončí dorovnání.
#[derive(Default, Debug)]
pub struct Needs {
    /// Pozice skupiny a čísla morfémů, jejichž výchozí tvar ještě není v bance.
    pub defaults: Vec<(usize, Vec<u32>)>,
    /// Inventáře, pro které chybí sada kandidátů.
    pub sets: Vec<Vec<u32>>,
}

impl Needs {
    pub fn is_empty(&self) -> bool {
        self.defaults.is_empty() && self.sets.is_empty()
    }
}

pub struct SoundIndex {
    scales: Vec<f64>,
    contexts: Contexts,
    /// Výchozí tvary morfémů mimo banku (doplňuje je Python na požádání, viz `Needs::defaults`).
    private: Defaults,
    groups: Vec<Group>,
    by_token: FxMap<i64, usize>,
    sets: Vec<Option<CandidateSet>>,
    set_ids: FxMap<Vec<u32>, usize>,
    /// Snímek tabulky hlásek: s ním si Rust sady kandidátů staví sám (bez něj je žádá od Pythonu).
    table: Option<SegTable>,
    delta: Vec<(u32, i64)>,
    nets: Vec<(u32, i64)>,
    pooled: Vec<u32>,
}

impl SoundIndex {
    pub fn new(scales: Vec<f64>) -> SoundIndex {
        SoundIndex {
            scales,
            contexts: Contexts::default(),
            private: Defaults::default(),
            groups: Vec::new(),
            by_token: FxMap::default(),
            sets: Vec::new(),
            set_ids: FxMap::default(),
            table: None,
            delta: Vec::new(),
            nets: Vec::new(),
            pooled: Vec::new(),
        }
    }

    /// Doplní výchozí tvary morfémů (obsah hlásek), které si index vyžádal.
    pub fn set_defaults(&mut self, numbers: &[u32], forms: &[Vec<i32>]) {
        for (number, form) in numbers.iter().zip(forms) {
            self.private.set(*number as usize, form);
        }
    }

    pub fn family_count(&self) -> usize {
        self.scales.len()
    }

    fn group_of(&mut self, token: i64) -> usize {
        if let Some(&found) = self.by_token.get(&token) {
            return found;
        }
        self.groups.push(Group::default());
        let found = self.groups.len() - 1;
        self.by_token.insert(token, found);
        found
    }

    /// Zaregistruje sadu kandidátů pro inventář (masky z Pythonu, po řádcích kandidátů).
    #[allow(clippy::too_many_arguments)]
    pub fn register_set(
        &mut self,
        inventory: Vec<u32>,
        columns: Vec<u32>,
        masks: [&[bool]; 3],
        right2: &[bool],
        right2_rows: &[i64],
        stressed_rows: &[i64],
        unstressed_rows: &[i64],
        family_ends: Vec<usize>,
    ) -> Result<(), String> {
        let inventory_key = inventory.clone();
        let set = prepare_set(
            self.scales.len(),
            Registration {
                inventory,
                columns,
                masks,
                right2,
                right2_rows,
                stressed_rows,
                unstressed_rows,
                family_ends,
                built: None,
            },
        )?;
        insert_set(&mut self.sets, &mut self.set_ids, inventory_key, set);
        Ok(())
    }

    /// Nastaví snímek tabulky hlásek; od té chvíle si Rust sady kandidátů staví sám.
    pub fn set_table(&mut self, table: SegTable) {
        self.table = Some(table);
    }

    pub fn table(&self) -> Option<&SegTable> {
        self.table.as_ref()
    }

    pub fn has_table(&self) -> bool {
        self.table.is_some()
    }

    /// Vyčistí keš prostředí pro tvary, které už nejsou živé.
    pub fn retain_forms(&mut self, alive: &[bool]) {
        self.contexts.retain_forms(alive);
    }

    fn release_set(&mut self, slot: usize) {
        if let Some(set) = self.sets[slot].as_mut() {
            set.refs -= 1;
            if set.refs == 0 {
                let inventory = std::mem::take(&mut set.inventory);
                self.set_ids.remove(&inventory);
                self.sets[slot] = None;
            }
        }
    }

    /// Dorovná skupiny na aktuální stav. Co chybí (výchozí tvary, sady kandidátů),
    /// vrátí; volající to doplní a zavolá znovu (dorovnání je opakovatelné).
    ///
    /// Postup ve třech částech: (1) rozdíl tvarů a inventář každé skupiny, (2) chybějící sady
    /// kandidátů pro nové inventáře se **staví souběžně** (čistá funkce tabulky hlásek a inventáře;
    /// do tabulky sad se zapisují sekvenčně v pořadí skupin), (3) opory a rodiny každé skupiny.
    /// Výsledek je stejný, jako kdyby se skupiny dorovnávaly po jedné: opory jsou celá čísla
    /// a sada je funkce inventáře.
    pub fn sync(&mut self, bank: &Bank, inputs: &[GroupInput<'_>]) -> Result<Needs, String> {
        let mut needs = Needs::default();
        let mut pending: Vec<Pending> = Vec::new();
        for (position, input) in inputs.iter().enumerate() {
            let at = self.group_of(input.token);
            if let Some(found) = self.sync_group_diff(bank, at, position, input, &mut needs)? {
                pending.push(found);
            }
        }
        self.prebuild_sets(&pending)?;
        self.apply_all(bank, pending)?;
        Ok(needs)
    }

    /// Postaví sady kandidátů pro inventáře, které ještě nemají sadu (každý jednou, v pořadí
    /// skupin), souběžně; zapíše je do tabulky sad sekvenčně v témže pořadí.
    fn prebuild_sets(&mut self, pending: &[Pending]) -> Result<(), String> {
        let Some(table) = self.table.as_ref() else {
            return Ok(());
        };
        let mut missing: Vec<&Vec<u32>> = Vec::new();
        for found in pending {
            let inventory = &self.groups[found.at].inventory;
            if !self.set_ids.contains_key(inventory) && !missing.contains(&inventory) {
                missing.push(inventory);
            }
        }
        if missing.is_empty() {
            return Ok(());
        }
        let families = self.scales.len();
        let built: Vec<Result<CandidateSet, String>> = if missing.len() > 1 {
            use rayon::prelude::*;
            missing
                .par_iter()
                .map(|inventory| make_set(table, families, inventory))
                .collect()
        } else {
            missing
                .iter()
                .map(|inventory| make_set(table, families, inventory))
                .collect()
        };
        let inventories: Vec<Vec<u32>> = missing.into_iter().cloned().collect();
        for (inventory, set) in inventories.into_iter().zip(built) {
            insert_set(&mut self.sets, &mut self.set_ids, inventory, set?);
        }
        Ok(())
    }

    /// První část dorovnání skupiny: rozdíl tvarů a inventář. Vrátí práci pro druhou část,
    /// má-li skupina co dopočítat (opory a rodiny).
    fn sync_group_diff(
        &mut self,
        bank: &Bank,
        at: usize,
        position: usize,
        input: &GroupInput<'_>,
        needs: &mut Needs,
    ) -> Result<Option<Pending>, String> {
        let size = input.flags.len().max(self.groups[at].counted_form.len());
        let effective = |number: usize| -> i32 {
            if number >= input.flags.len() || input.flags[number] == 0 {
                return UNCOUNTED;
            }
            match input.forms.get(number) {
                Some(&form) if form >= 0 => form,
                _ if self.private.get(number).is_some() => PRIVATE + number as i32,
                _ => -1,
            }
        };
        // Výchozí tvar, který index ještě nezná, doplní Python (pak se zavolá znovu).
        let missing: Vec<u32> = (0..size)
            .filter(|&n| effective(n) == -1)
            .map(|n| n as u32)
            .collect();
        if !missing.is_empty() {
            needs.defaults.push((position, missing));
            return Ok(None);
        }
        let Self {
            contexts,
            groups,
            delta,
            nets,
            set_ids,
            table,
            ..
        } = self;
        let group = &mut groups[at];
        if group.counted_form.len() < size {
            group.counted_form.resize(size, UNCOUNTED);
            group.counted_rule.resize(size, 0);
        }
        delta.clear();
        for number in 0..size {
            let new = effective(number);
            let old = group.counted_form[number];
            if new == old {
                continue;
            }
            if old >= 0 {
                let (start, length) = contexts.of_form(
                    bank,
                    &self.private,
                    old as usize,
                    group.counted_rule[number],
                );
                delta.extend(
                    contexts.pool[start..start + length]
                        .iter()
                        .map(|&c| (c, -1)),
                );
            }
            if new >= 0 {
                let (start, length) =
                    contexts.of_form(bank, &self.private, new as usize, input.rule);
                delta.extend(contexts.pool[start..start + length].iter().map(|&c| (c, 1)));
                group.counted_rule[number] = input.rule;
            }
            group.counted_form[number] = new;
        }
        merge(delta, nets);
        for &(context, diff) in nets.iter() {
            group.bump(contexts.segment[context as usize], diff);
        }
        if !nets.is_empty() {
            group.refresh_inventory();
        }
        if group.inventory.is_empty() {
            self.release_group_set(at);
            let group = &mut self.groups[at];
            group.valid_for = None;
            group.supports.clear();
            group.effective.clear();
            group.families.clear();
            return Ok(None);
        }
        let full = group.valid_for.as_ref() != Some(&group.inventory);
        if !full && nets.is_empty() {
            return Ok(None);
        }
        if !set_ids.contains_key(&group.inventory) && table.is_none() {
            // Sada pro nový inventář chybí; podpory se po jejím doplnění přepočítají celé.
            group.valid_for = None;
            if !needs.sets.contains(&group.inventory) {
                needs.sets.push(group.inventory.clone());
            }
            return Ok(None);
        }
        Ok(Some(Pending {
            at,
            full,
            nets: if full { Vec::new() } else { nets.clone() },
        }))
    }

    /// Druhá část dorovnání všech skupin: opory kandidátů se počítají **souběžně** (každá skupina
    /// čte sdílená prostředí a sadu a píše do vlastního pole opor), ukládají se sekvenčně. Skupina,
    /// jejíž prostředí ještě nejsou zapamatovaná (nemělo by nastat), jde starou sekvenční cestou.
    fn apply_all(&mut self, bank: &Bank, pending: Vec<Pending>) -> Result<(), String> {
        if pending.len() < 2 {
            for found in pending {
                self.sync_group_apply(bank, found)?;
            }
            return Ok(());
        }
        // Sady, které mezitím zmizely, se postaví znovu (sekvenčně).
        for found in &pending {
            let inventory = &self.groups[found.at].inventory;
            if !self.set_ids.contains_key(inventory) {
                let table = self.table.as_ref().ok_or("sada kandidátů zmizela")?;
                build_set(
                    &mut self.sets,
                    &mut self.set_ids,
                    self.scales.len(),
                    table,
                    inventory,
                )?;
            }
        }
        struct Work {
            found: Pending,
            slot: usize,
            supports: Vec<i64>,
            effective: Vec<i64>,
            families: Vec<Family>,
            done: bool,
        }
        let mut work: Vec<Work> = Vec::with_capacity(pending.len());
        for found in pending {
            let group = &mut self.groups[found.at];
            let slot = *self
                .set_ids
                .get(&group.inventory)
                .ok_or("sada kandidátů zmizela")?;
            let (supports, effective, families) = if found.full {
                (
                    Vec::new(),
                    Vec::new(),
                    vec![Family::default(); self.scales.len()],
                )
            } else {
                (
                    std::mem::take(&mut group.supports),
                    std::mem::take(&mut group.effective),
                    std::mem::take(&mut group.families),
                )
            };
            work.push(Work {
                found,
                slot,
                supports,
                effective,
                families,
                done: false,
            });
        }
        let results: Vec<Result<bool, String>> = {
            use rayon::prelude::*;
            let (contexts, sets, groups, scales) =
                (&self.contexts, &self.sets, &self.groups, &self.scales);
            let vowel = &bank.vowel;
            let compute = |item: &mut Work| -> Result<bool, String> {
                let set = sets[item.slot].as_ref().ok_or("sada kandidátů zmizela")?;
                if !item.found.full {
                    for &(context, diff) in &item.found.nets {
                        set.add(contexts, vowel, context as usize, diff, &mut item.supports)?;
                    }
                    compute_families(
                        set,
                        scales,
                        &item.supports,
                        &mut item.effective,
                        &mut item.families,
                    );
                    return Ok(true);
                }
                let group = &groups[item.found.at];
                let mut pooled: Vec<u32> = Vec::new();
                for number in 0..group.counted_form.len() {
                    let form = group.counted_form[number];
                    if form >= 0 {
                        let Some((start, length)) =
                            contexts.cached_of_form(form as usize, group.counted_rule[number])
                        else {
                            return Ok(false);
                        };
                        pooled.extend_from_slice(&contexts.pool[start..start + length]);
                    }
                }
                pooled.sort_unstable();
                item.supports = vec![0; set.count];
                let mut run = 0;
                while run < pooled.len() {
                    let context = pooled[run];
                    let mut end = run + 1;
                    while end < pooled.len() && pooled[end] == context {
                        end += 1;
                    }
                    set.add(
                        contexts,
                        vowel,
                        context as usize,
                        (end - run) as i64,
                        &mut item.supports,
                    )?;
                    run = end;
                }
                compute_families(
                    set,
                    scales,
                    &item.supports,
                    &mut item.effective,
                    &mut item.families,
                );
                Ok(true)
            };
            work.par_iter_mut().map(compute).collect()
        };
        for (item, result) in work.iter_mut().zip(results) {
            item.done = result?;
        }
        // Uložení v pořadí skupin: nejdřív se sady nových inventářů uchopí (`refs`), teprve potom se
        // uvolňují dosavadní, aby sada, kterou potřebuje jiná skupina, nezanikla.
        let mut previous: Vec<usize> = Vec::new();
        for item in &mut work {
            if !item.done {
                continue;
            }
            let group = &mut self.groups[item.found.at];
            group.supports = std::mem::take(&mut item.supports);
            group.effective = std::mem::take(&mut item.effective);
            group.families = std::mem::take(&mut item.families);
            if item.found.full {
                if let Some(old) = group.set.replace(item.slot) {
                    previous.push(old);
                }
                group.valid_for = Some(group.inventory.clone());
                self.sets[item.slot]
                    .as_mut()
                    .ok_or("sada kandidátů zmizela")?
                    .refs += 1;
            }
        }
        for old in previous {
            self.release_set(old);
        }
        for item in work {
            if !item.done {
                self.sync_group_apply(bank, item.found)?;
            }
        }
        Ok(())
    }

    /// Druhá část dorovnání skupiny: opory kandidátů a rodiny (sada pro inventář už je postavená).
    fn sync_group_apply(&mut self, bank: &Bank, pending: Pending) -> Result<(), String> {
        let Pending { at, full, nets } = pending;
        let Self {
            contexts,
            groups,
            pooled,
            sets,
            set_ids,
            table,
            scales,
            ..
        } = self;
        let group = &mut groups[at];
        if !set_ids.contains_key(&group.inventory) {
            // Sadu mezitím uvolnila jiná skupina: postaví se znovu.
            let table = table.as_ref().ok_or("sada kandidátů zmizela")?;
            build_set(sets, set_ids, scales.len(), table, &group.inventory)?;
        }
        let Some(&slot) = set_ids.get(&group.inventory) else {
            return Err("sada kandidátů zmizela".into());
        };
        let vowel = &bank.vowel;
        let families = self.scales.len();
        if full {
            // Opory z tvarů celé slovní zásoby: prostředí se nejdřív sečtou po číslech.
            pooled.clear();
            for number in 0..group.counted_form.len() {
                let form = group.counted_form[number];
                if form >= 0 {
                    let (start, length) = contexts.of_form(
                        bank,
                        &self.private,
                        form as usize,
                        group.counted_rule[number],
                    );
                    pooled.extend_from_slice(&contexts.pool[start..start + length]);
                }
            }
            pooled.sort_unstable();
            let set = self.sets[slot].as_ref().ok_or("sada kandidátů zmizela")?;
            let mut supports = std::mem::take(&mut group.supports);
            supports.clear();
            supports.resize(set.count, 0);
            let mut run = 0;
            while run < pooled.len() {
                let context = pooled[run];
                let mut end = run + 1;
                while end < pooled.len() && pooled[end] == context {
                    end += 1;
                }
                set.add(
                    contexts,
                    vowel,
                    context as usize,
                    (end - run) as i64,
                    &mut supports,
                )?;
                run = end;
            }
            group.supports = supports;
            let previous = group.set.replace(slot);
            group.valid_for = Some(group.inventory.clone());
            group.effective.clear();
            group.families.clear();
            group.families.resize(families, Family::default());
            self.sets[slot]
                .as_mut()
                .ok_or("sada kandidátů zmizela")?
                .refs += 1;
            if let Some(previous) = previous {
                self.release_set(previous);
            }
        } else {
            let set = self.sets[slot].as_ref().ok_or("sada kandidátů zmizela")?;
            for &(context, diff) in nets.iter() {
                set.add(contexts, vowel, context as usize, diff, &mut group.supports)?;
            }
        }
        self.refresh_families(at, slot);
        Ok(())
    }

    fn release_group_set(&mut self, at: usize) {
        if let Some(slot) = self.groups[at].set.take() {
            self.release_set(slot);
        }
    }

    /// Přepočítá rodiny, kterým se změnily efektivní opory.
    fn refresh_families(&mut self, at: usize, slot: usize) {
        let Some(set) = self.sets[slot].as_ref() else {
            return;
        };
        let group = &mut self.groups[at];
        compute_families(
            set,
            &self.scales,
            &group.supports,
            &mut group.effective,
            &mut group.families,
        );
    }
}

/// Přepočítá rodiny, kterým se změnily efektivní opory.
fn compute_families(
    set: &CandidateSet,
    scales: &[f64],
    supports: &[i64],
    effective: &mut Vec<i64>,
    families: &mut Vec<Family>,
) {
    let next_effective: Vec<i64> = supports
        .iter()
        .map(|&s| {
            if s < MIN_SUPPORT {
                0
            } else {
                s.min(FULL_SUPPORT)
            }
        })
        .collect();
    let known = effective.len() == next_effective.len();
    if families.len() < scales.len() {
        families.resize(scales.len(), Family::default());
    }
    let mut begin = 0;
    for (family, &end) in set.family_ends.iter().enumerate() {
        let state = &mut families[family];
        if known && state.valid && effective[begin..end] == next_effective[begin..end] {
            begin = end;
            continue;
        }
        state.sites.clear();
        state.rates.clear();
        for (offset, &support) in supports[begin..end].iter().enumerate() {
            if support >= MIN_SUPPORT {
                state.sites.push(offset as u32);
            }
        }
        let sites = state.sites.len();
        // Relativní četnost kandidátů (přirozenost změny); rovnoměrně, když je všude 1.
        let weight_of = |site: u32| {
            set.built
                .as_ref()
                .and_then(|b| b.candidates.get(begin + site as usize))
                .map_or(1.0, |c| c.weight)
        };
        let weight_sum: f64 = state.sites.iter().map(|&site| weight_of(site)).sum();
        for &site in &state.sites {
            let support = supports[begin + site as usize] as f64;
            let share = (support / FULL_SUPPORT as f64).min(1.0);
            let weight = weight_of(site);
            let rate = if weight_sum == sites as f64 {
                (scales[family] * share) / sites as f64
            } else {
                scales[family] * share * weight / weight_sum
            };
            state.rates.push(rate);
        }
        state.total = if sites == 0 {
            0.0
        } else {
            pairwise_sum(&state.rates)
        };
        state.valid = true;
        begin = end;
    }
    *effective = next_effective;
}

impl SoundIndex {
    // --- čtení --------------------------------------------------------------

    fn find(&self, token: i64) -> Option<&Group> {
        self.by_token.get(&token).map(|&at| &self.groups[at])
    }

    pub fn inventory(&self, token: i64) -> Vec<u32> {
        self.find(token)
            .map(|g| g.inventory.clone())
            .unwrap_or_default()
    }

    pub fn has_families(&self, token: i64) -> bool {
        self.find(token).is_some_and(|g| !g.families.is_empty())
    }

    pub fn family(&self, token: i64, family: usize) -> Option<&Family> {
        self.find(token)
            .and_then(|g| g.families.get(family))
            .filter(|f| f.valid)
    }

    /// Součty měr (kód × rodina) po řádcích; 0 tam, kde kód nemá místa.
    pub fn totals(&self, tokens: &[i64]) -> Vec<f64> {
        let families = self.scales.len();
        let mut out = vec![0.0; tokens.len() * families];
        for (row, &token) in tokens.iter().enumerate() {
            if let Some(group) = self.find(token) {
                for (family, state) in group.families.iter().enumerate() {
                    if state.valid {
                        out[row * families + family] = state.total;
                    }
                }
            }
        }
        out
    }

    /// Sada kandidátů skupiny (když ji sestavil Rust) a začátek rodiny v řádcích kandidátů.
    fn built_of(&self, token: i64, family: usize) -> Option<(&Built, usize)> {
        let group = self.find(token)?;
        let set = self.sets.get(group.set?)?.as_ref()?;
        let built = set.built.as_ref()?;
        let begin = if family == 0 {
            0
        } else {
            *set.family_ends.get(family - 1)?
        };
        Some((built, begin))
    }

    /// ID proměnných (`process:` + klíč procesu) míst jedné rodiny v pořadí míst.
    pub fn site_ids(&self, token: i64, family: usize) -> Option<Vec<&str>> {
        let (built, begin) = self.built_of(token, family)?;
        let state = self.family(token, family)?;
        Some(
            state
                .sites
                .iter()
                .map(|&site| built.ids[begin + site as usize].as_str())
                .collect(),
        )
    }

    /// Opory míst jedné rodiny v pořadí míst.
    pub fn site_supports(&self, token: i64, family: usize) -> Option<Vec<i64>> {
        let (_, begin) = self.built_of(token, family)?;
        let state = self.family(token, family)?;
        let group = self.find(token)?;
        Some(
            state
                .sites
                .iter()
                .map(|&site| group.supports[begin + site as usize])
                .collect(),
        )
    }

    /// Popis kandidáta jednoho místa rodiny a snímek tabulky, ze kterého se sestavil.
    pub fn site_candidate(
        &self,
        token: i64,
        family: usize,
        position: usize,
    ) -> Option<(&Candidate, &SegTable)> {
        let (built, begin) = self.built_of(token, family)?;
        let state = self.family(token, family)?;
        let site = *state.sites.get(position)? as usize;
        Some((built.candidates.get(begin + site)?, self.table.as_ref()?))
    }

    pub fn supports(&self, token: i64) -> Vec<i64> {
        self.find(token)
            .map(|g| g.supports.clone())
            .unwrap_or_default()
    }

    /// Počty prostředí kódu (jen nenulové): předchozí, hláska, další, přízvuk, druhá další, počet.
    #[allow(clippy::type_complexity)]
    pub fn context_counts(
        &mut self,
        bank: &Bank,
        token: i64,
    ) -> (Vec<u32>, Vec<u32>, Vec<u32>, Vec<bool>, Vec<u32>, Vec<i64>) {
        let mut out = (
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
            Vec::new(),
        );
        let Some(&at) = self.by_token.get(&token) else {
            return out;
        };
        let group = &self.groups[at];
        let contexts = &mut self.contexts;
        let mut pooled = Vec::new();
        for number in 0..group.counted_form.len() {
            let form = group.counted_form[number];
            if form >= 0 {
                let (start, length) = contexts.of_form(
                    bank,
                    &self.private,
                    form as usize,
                    group.counted_rule[number],
                );
                pooled.extend_from_slice(&contexts.pool[start..start + length]);
            }
        }
        pooled.sort_unstable();
        let mut run = 0;
        while run < pooled.len() {
            let context = pooled[run] as usize;
            let mut end = run + 1;
            while end < pooled.len() && pooled[end] as usize == context {
                end += 1;
            }
            out.0.push(contexts.previous[context]);
            out.1.push(contexts.segment[context]);
            out.2.push(contexts.following[context]);
            out.3.push(contexts.stressed[context]);
            out.4.push(contexts.following2[context]);
            out.5.push((end - run) as i64);
            run = end;
        }
        out
    }

    /// Co je započítáno (tvar a pravidlo každého morfému), pro uložení a obnovu.
    pub fn export(&self, token: i64) -> (Vec<i32>, Vec<u8>) {
        self.find(token)
            .map(|g| (g.counted_form.clone(), g.counted_rule.clone()))
            .unwrap_or_default()
    }

    /// Obnoví stav skupiny z uloženého `counted_form`/`counted_rule`; opory se přepočítají při příštím dorovnání.
    pub fn import(
        &mut self,
        bank: &Bank,
        token: i64,
        counted_form: Vec<i32>,
        counted_rule: Vec<u8>,
    ) -> Result<(), String> {
        if counted_form.len() != counted_rule.len() {
            return Err("uložená pole mají různou délku".into());
        }
        let at = self.group_of(token);
        self.release_group_set(at);
        let mut group = Group::default();
        let contexts = &mut self.contexts;
        for number in 0..counted_form.len() {
            let form = counted_form[number];
            if form >= 0 {
                let known = if form >= PRIVATE {
                    self.private.get((form - PRIVATE) as usize).is_some()
                } else {
                    (form as usize) < bank.len()
                };
                if !known {
                    return Err("uložený tvar není v bance ani v aréně výchozích tvarů".into());
                }
                let (start, length) =
                    contexts.of_form(bank, &self.private, form as usize, counted_rule[number]);
                for &context in &contexts.pool[start..start + length] {
                    group.bump(contexts.segment[context as usize], 1);
                }
            }
        }
        group.counted_form = counted_form;
        group.counted_rule = counted_rule;
        group.refresh_inventory();
        self.groups[at] = group;
        Ok(())
    }
}

/// Co `register` potřebuje: masky kandidátů a případně jejich popisy.
struct Registration<'a> {
    inventory: Vec<u32>,
    columns: Vec<u32>,
    masks: [&'a [bool]; 3],
    right2: &'a [bool],
    right2_rows: &'a [i64],
    stressed_rows: &'a [i64],
    unstressed_rows: &'a [i64],
    family_ends: Vec<usize>,
    built: Option<Built>,
}

/// Sestaví sadu kandidátů všech rodin pro inventář z tabulky hlásek a zaregistruje ji.
fn build_set(
    sets: &mut Vec<Option<CandidateSet>>,
    set_ids: &mut FxMap<Vec<u32>, usize>,
    families: usize,
    table: &SegTable,
    inventory: &[u32],
) -> Result<(), String> {
    let set = make_set(table, families, inventory)?;
    insert_set(sets, set_ids, inventory.to_vec(), set);
    Ok(())
}

/// Sada kandidátů všech rodin pro inventář (čistá funkce tabulky hlásek a inventáře).
fn make_set(table: &SegTable, families: usize, inventory: &[u32]) -> Result<CandidateSet, String> {
    let built = candidates::build(table, inventory)?;
    let masks = candidates::masks(table, inventory, &built);
    let ends = built.family_ends.clone();
    prepare_set(
        families,
        Registration {
            inventory: inventory.to_vec(),
            columns: masks.columns,
            masks: [&masks.target, &masks.left, &masks.right],
            right2: &masks.right2,
            right2_rows: &masks.right2_rows,
            stressed_rows: &masks.stressed_rows,
            unstressed_rows: &masks.unstressed_rows,
            family_ends: ends,
            built: Some(built),
        },
    )
}

/// Sada kandidátů z masek (transponované bitové sady).
fn prepare_set(families: usize, given: Registration<'_>) -> Result<CandidateSet, String> {
    let Registration {
        inventory,
        columns,
        masks,
        right2,
        right2_rows,
        stressed_rows,
        unstressed_rows,
        family_ends,
        built,
    } = given;
    let width = columns.len();
    if width == 0 || masks.iter().any(|mask| mask.len() % width != 0) {
        return Err("masky kandidátů nemají šířku sloupců".into());
    }
    let count = masks[0].len() / width;
    if masks.iter().any(|mask| mask.len() != count * width)
        || right2.len() != right2_rows.len() * width
    {
        return Err("masky kandidátů mají různý tvar".into());
    }
    if family_ends.len() != families || family_ends.last().is_some_and(|&end| end != count) {
        return Err("konce rodin nesedí s počtem kandidátů nebo rodin".into());
    }
    let words = count.div_ceil(64).max(1);
    let transpose = |rows: &dyn Fn(usize, usize) -> bool| -> Vec<u64> {
        let mut out = vec![0_u64; width * words];
        for row in 0..count {
            for column in 0..width {
                if rows(row, column) {
                    out[column * words + row / 64] |= 1 << (row % 64);
                }
            }
        }
        out
    };
    let target = transpose(&|row, column| masks[0][row * width + column]);
    let left = transpose(&|row, column| masks[1][row * width + column]);
    let right = transpose(&|row, column| masks[2][row * width + column]);
    // Kandidáti bez druhé následující hlásky ji nepodmiňují: samé jedničky.
    let mut second = vec![u64::MAX; width * words];
    for (at, &row) in right2_rows.iter().enumerate() {
        let row = row as usize;
        for column in 0..width {
            let bit = 1_u64 << (row % 64);
            if right2[at * width + column] {
                second[column * words + row / 64] |= bit;
            } else {
                second[column * words + row / 64] &= !bit;
            }
        }
    }
    let rows_to_bits = |rows: &[i64]| -> Vec<u64> {
        let mut out = vec![0_u64; words];
        for &row in rows {
            out[row as usize / 64] |= 1 << (row as usize % 64);
        }
        out
    };
    let set = CandidateSet {
        inventory: inventory.clone(),
        columns,
        count,
        words,
        target,
        left,
        right,
        right2: second,
        stressed_rows: rows_to_bits(stressed_rows),
        unstressed_rows: rows_to_bits(unstressed_rows),
        family_ends,
        built,
        refs: 0,
    };
    Ok(set)
}

/// Zapíše sadu kandidátů do tabulky sad (do prvního volného místa).
fn insert_set(
    sets: &mut Vec<Option<CandidateSet>>,
    set_ids: &mut FxMap<Vec<u32>, usize>,
    inventory: Vec<u32>,
    set: CandidateSet,
) {
    let slot = match sets.iter().position(Option::is_none) {
        Some(free) => {
            sets[free] = Some(set);
            free
        }
        None => {
            sets.push(Some(set));
            sets.len() - 1
        }
    };
    set_ids.insert(inventory, slot);
}

/// Seřadí změny prostředí a sečte je po číslech; nulové součty vynechá.
fn merge(delta: &mut [(u32, i64)], out: &mut Vec<(u32, i64)>) {
    out.clear();
    delta.sort_unstable_by_key(|&(context, _)| context);
    for &(context, diff) in delta.iter() {
        match out.last_mut() {
            Some(last) if last.0 == context => last.1 += diff,
            _ => out.push((context, diff)),
        }
    }
    out.retain(|&(_, diff)| diff != 0);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bank() -> Bank {
        // Hlásky: 0 = p, 1 = a, 2 = t, 3 = i; hranice 4. Samohlásky a, i.
        let mut bank = Bank::new(4, vec![false, true, false, true, false]).unwrap();
        bank.push(&[0, 1, 2, 1]).unwrap(); // pata
        bank.push(&[2, 3]).unwrap(); // ti
        bank
    }

    #[test]
    fn merge_secte_po_cislech_a_vynecha_nuly() {
        let mut delta = vec![(3, 1), (1, 1), (3, -1), (2, 1), (1, 1)];
        let mut out = Vec::new();
        merge(&mut delta, &mut out);
        assert_eq!(out, vec![(1, 2), (2, 1)]);
    }

    #[test]
    fn prostredi_tvaru_ma_prizvuk_podle_pravidla() {
        let bank = bank();
        let mut contexts = Contexts::default();
        // pata s předposledním přízvukem: přízvučné je první „a“ (index 1).
        let private = Defaults::default();
        let (start, length) = contexts.of_form(&bank, &private, 0, 3);
        assert_eq!(length, 4);
        let stressed: Vec<bool> = (0..length)
            .map(|k| contexts.stressed[contexts.pool[start + k] as usize])
            .collect();
        assert_eq!(stressed, vec![false, true, false, false]);
        // Tentýž tvar podruhé: ze zapamatovaného seznamu, beze změny.
        assert_eq!(contexts.of_form(&bank, &private, 0, 3), (start, length));
    }

    #[test]
    fn dorovnani_zapocita_slova_a_odecte_zmeny() {
        let bank = bank();
        let mut index = SoundIndex::new(vec![0.5]);
        let flags = [1_u8, 1];
        // Výchozí tvary „pata“ a „ti“ drží index mimo banku.
        index.set_defaults(&[0, 1], &[vec![0, 1, 2, 1], vec![2, 3]]);
        let mut forms = vec![-1_i32, -1];
        let inputs = |forms: &'_ [i32]| {
            vec![GroupInput {
                token: 7,
                rule: 3,
                flags: &flags,
                forms: forms.to_vec().leak(),
            }]
        };
        // Bez sady kandidátů jen počítá výskyty a žádá sadu pro inventář.
        let needs = index.sync(&bank, &inputs(&forms)).unwrap();
        assert_eq!(index.inventory(7), vec![0, 1, 2, 3]);
        assert_eq!(needs.sets, vec![vec![0, 1, 2, 3]]);
        // Slovo „ti“ se změní na „pata“: inventář se nemění, výskyty ano.
        forms[1] = 0;
        let _ = index.sync(&bank, &inputs(&forms)).unwrap();
        assert_eq!(
            index.groups[0].occurrences,
            vec![(0, 2), (1, 4), (2, 2), (3, 0)]
        );
        assert_eq!(index.inventory(7), vec![0, 1, 2]);
        let (_, segments, _, _, _, counts) = index.context_counts(&bank, 7);
        assert_eq!(counts.iter().sum::<i64>(), 8);
        assert_eq!(segments.len(), counts.len());
        // Export a obnova vrátí totéž.
        let (cf, cr) = index.export(7);
        let mut other = SoundIndex::new(vec![0.5]);
        other.set_defaults(&[0, 1], &[vec![0, 1, 2, 1], vec![2, 3]]);
        other.import(&bank, 7, cf, cr).unwrap();
        assert_eq!(other.inventory(7), index.inventory(7));
    }

    #[test]
    fn chybejici_vychozi_tvar_se_vyzada() {
        let bank = bank();
        let mut index = SoundIndex::new(vec![0.5]);
        let flags = [1_u8];
        let inputs = [GroupInput {
            token: 1,
            rule: 0,
            flags: &flags,
            forms: &[],
        }];
        let needs = index.sync(&bank, &inputs).unwrap();
        assert_eq!(needs.defaults, vec![(0, vec![0])]);
    }
}

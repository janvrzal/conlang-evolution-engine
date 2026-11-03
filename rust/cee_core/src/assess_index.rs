//! Hodnocení zvukových procesů nad vzorky slov kódů: stav a výpočet v Rustu (B3b).
//!
//! Zrcadlo `cee.v2.language.assessment_index` a `cee.v2.assessment`. Index drží pro každý
//! kód (podle `FormStore.token`):
//!
//! - **vzorek** slov (čísla morfémů v pořadí jmen, váhy a jejich součet od Pythonu, protože
//!   výběr a frekvence užití počítá Python), čísla aktuálních tvarů v bance a počty samohlásek.
//!   Tvary se dorovnávají hustým průchodem po vzorku (sto dvacet čtení z polí `FormStore`
//!   a výchozích tvarů), ne deníkem;
//! - **uložená hodnocení** procesů (verze kódu, tik a pět hodnot), seřazená podle čísla proměnné.
//!   Hodnocení zůstává platné, dokud se nezmění verze kódu, nejvýš `STALE_TICKS` ticků;
//! - **hodnocení tvarů** (`form_assess`): změny tvarů zaregistrované podle čísla proměnné a hustá
//!   tabulka hodnot každého kódu, platná pro jednu verzi kódu. Počítá je Rust ze stavu morfologického
//!   indexu míst (koncovky a jejich podoby), z úložiště tvarů kódu a z dominantních kořenů.
//!
//! Co Rust nezná (výběr vzorku a váhy, výchozí tvary mimo banku, mapy hlásek procesů, cena
//! dvojic stejného lexému v buňce, kterou jiná konstrukce nahrazuje, výchozí tvar morfému
//! v aréně morfologického indexu), zapíše do `Needs` a výpočet té položky vynechá; volající
//! dodá a zavolá znovu. Součty plovoucích čísel
//! jsou párové po celé šířce matice jako dřív (`assess::pairwise_sum`), takže výsledek je bit po
//! bitu stejný jako v Pythonu.

use std::collections::{BTreeMap, BTreeSet, HashMap};

use crate::bank::{Bank, Outcome};
use crate::form_assess::{self, FormChange, FormCtx, FormRegistry, FormState};

/// Hodnocení se přepočítá nejdřív po tolika krocích, i když se verze kódu mění.
pub const STALE_TICKS: i64 = 8;

/// Pět hodnot hodnocení procesu, jako `cee.v2.assessment.ProcessAssessment`.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Assessment {
    pub coverage: f64,
    pub merge: f64,
    pub short: f64,
    pub marked: f64,
    pub dispersion: f64,
}

/// Hodnocení tvaru jednoho kódu (`cee.v2.morphology.FormAssessment`); `present` = není `None`.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct FormEntry {
    pub present: bool,
    pub gain: f64,
    pub frequency: f64,
    pub before: bool,
    pub after: bool,
}

/// Co volající musí dodat, než výpočet dokončí. Množiny, aby pořadí nezáviselo na pořadí objevení.
#[derive(Default, Debug)]
pub struct Needs {
    /// Skupiny, jejichž vzorek (výběr a váhy) má přepočítat Python.
    pub samples: BTreeSet<usize>,
    /// (skupina, morfém), jejichž výchozí tvar ještě není v bance.
    pub defaults: BTreeSet<(usize, u32)>,
    /// Mapy hlásek procesu (řádek změny → hlásky), které má spočítat Python.
    pub maps: BTreeMap<usize, BTreeSet<i32>>,
    /// (skupina, morfém): je jeho buňka paradigmatu nahrazena jinou konstrukcí?
    pub redundant: BTreeSet<(usize, u32)>,
    /// Skupiny, kterým chybí podíl slov s koncovou souhláskou.
    pub coda: BTreeSet<usize>,
    /// Morfémy, jejichž výchozí tvar chybí v aréně morfologického indexu míst (hodnocení tvarů).
    pub morph_defaults: BTreeSet<u32>,
}

impl Needs {
    pub fn is_empty(&self) -> bool {
        self.samples.is_empty()
            && self.defaults.is_empty()
            && self.maps.is_empty()
            && self.redundant.is_empty()
            && self.coda.is_empty()
            && self.morph_defaults.is_empty()
    }
}

/// Vstupy jednoho volání pro všechny skupiny kroku (podle pozice skupiny).
pub struct Inputs<'a> {
    pub tokens: &'a [i64],
    pub versions: &'a [i64],
    pub rules: &'a [u8],
    /// Pole tvarů kódů podle čísla morfému (−1 = výchozí).
    pub forms: Vec<&'a [i32]>,
    /// Výchozí tvary morfémů světa (−1 = ještě nejsou v bance), lexémy a buňky morfémů (−1 = žádná).
    pub defaults: &'a [i32],
    pub lexeme: &'a [i32],
    pub cell: &'a [i32],
    pub paradigm_weight: f64,
    pub redundant_weight: f64,
}

/// Odpovědi na `Needs::redundant` v rámci jednoho kroku.
#[derive(Default)]
pub struct Memo {
    pub redundant: HashMap<(usize, u32), bool>,
}

/// Vzorek slov jednoho kódu.
#[derive(Default)]
pub struct Sample {
    pub morphemes: Vec<u32>,
    pub weights: Vec<f64>,
    pub total: f64,
    pub ids: Vec<i64>,
    /// Počty samohlásek vzorku podle čísla hlásky.
    pub vowels: Vec<i64>,
    /// Verze kódu, při které Python vzorek naposledy přepočítal (dodal).
    refreshed: Option<i64>,
    /// Verze kódu, ke které jsou čísla tvarů a samohlásky dorovnané.
    synced: Option<i64>,
}

struct Entry {
    variable: u32,
    version: i64,
    tick: i64,
    value: Assessment,
}

#[derive(Default)]
struct Group {
    sample: Sample,
    cache: Vec<Entry>,
    form: FormState,
}

/// Co o procesu potřebuje zisk rozptylu samohlásek.
#[derive(Clone, Default)]
pub struct ProcessInfo {
    /// Může změna ovlivnit rozptyl vokálů (cílí na samohlásku a není nepřízvučná).
    pub shapes: bool,
    /// Výstupní hláska procesu (−1 = žádná).
    pub output: i32,
    /// Maska hlásek, na které proces cílí (podle čísla hlásky).
    pub target: Vec<bool>,
}

/// Index hodnocení všech kódů světa.
#[derive(Default)]
pub struct AssessIndex {
    groups: HashMap<i64, Group>,
    processes: HashMap<u32, ProcessInfo>,
    /// Souřadnice samohlásek (výška, zadnost, zaokrouhlení) podle čísla hlásky.
    coords: Vec<[f64; 3]>,
    /// Analogické změny tvarů podle čísla proměnné (hodnocení tvarů, viz `form_assess`).
    forms: FormRegistry,
}

fn nearest(coords: &[[f64; 3]], vowel: i32, others: &[i32]) -> f64 {
    let [height, back, rounded] = coords[vowel as usize];
    let mut best: Option<f64> = None;
    for &other in others {
        if other == vowel {
            continue;
        }
        let [h, b, r] = coords[other as usize];
        let (dh, db, dr) = (height - h, back - b, rounded - r);
        let distance = (dh * dh + db * db + 0.25 * (dr * dr)).sqrt();
        best = Some(match best {
            Some(found) if found <= distance => found,
            _ => distance,
        });
    }
    best.unwrap_or(0.0)
}

impl AssessIndex {
    pub fn new() -> AssessIndex {
        AssessIndex::default()
    }

    /// Souřadnice samohlásek tabulky hlásek (jedno pole `[výška, zadnost, zaokrouhlení]` na hlásku).
    pub fn set_coordinates(&mut self, coords: Vec<[f64; 3]>) {
        self.coords = coords;
    }

    pub fn register_process(&mut self, variable: u32, info: ProcessInfo) {
        self.processes.insert(variable, info);
    }

    pub fn has_process(&self, variable: u32) -> bool {
        self.processes.contains_key(&variable)
    }

    /// Zisk rozptylu vokálů (`cee.v2.assessment._dispersion_gain`) z vokálů před změnou a po ní.
    fn dispersion_gain(&self, info: &ProcessInfo, before: &[i32], after: &[i32]) -> f64 {
        if !info.shapes || info.output < 0 {
            return 0.0;
        }
        if before.binary_search(&info.output).is_ok() {
            return 0.0;
        }
        let mut best: Option<f64> = None;
        for &source in before {
            if !info.target.get(source as usize).copied().unwrap_or(false) {
                continue;
            }
            let found = nearest(&self.coords, source, before);
            best = Some(match best {
                Some(old) if old >= found => old,
                _ => found,
            });
        }
        match best {
            None => 0.0,
            Some(source) => nearest(&self.coords, info.output, after) - source,
        }
    }

    // --- vzorek ------------------------------------------------------------------------------

    /// Přijme vzorek, který Python přepočítal při verzi `version` (čísla tvarů se dorovnají napříště).
    pub fn set_sample(
        &mut self,
        token: i64,
        version: i64,
        morphemes: Vec<u32>,
        weights: Vec<f64>,
        total: f64,
    ) -> Result<(), String> {
        if morphemes.len() != weights.len() {
            return Err("vzorek a váhy mají různou délku".into());
        }
        let sample = &mut self.groups.entry(token).or_default().sample;
        sample.morphemes = morphemes;
        sample.weights = weights;
        sample.total = total;
        sample.refreshed = Some(version);
        sample.synced = None;
        Ok(())
    }

    /// Je vzorek skupiny dorovnaný na její verzi? Když ne, zapíše, co chybí (přepočet vzorku
    /// Pythonem, výchozí tvary v bance); jinak dorovná tvary a samohlásky.
    fn ensure_sample(
        &mut self,
        bank: &Bank,
        g: usize,
        inp: &Inputs<'_>,
        needs: &mut Needs,
    ) -> bool {
        let version = inp.versions[g];
        let group = self.groups.entry(inp.tokens[g]).or_default();
        let sample = &mut group.sample;
        if sample.synced == Some(version) {
            return true;
        }
        if sample.refreshed != Some(version) {
            needs.samples.insert(g);
            return false;
        }
        let stored = inp.forms[g];
        let mut ids = Vec::with_capacity(sample.morphemes.len());
        let mut missing = false;
        for &morpheme in &sample.morphemes {
            let own = stored.get(morpheme as usize).copied().unwrap_or(-1);
            let id = if own >= 0 {
                own
            } else {
                inp.defaults.get(morpheme as usize).copied().unwrap_or(-1)
            };
            if id < 0 {
                needs.defaults.insert((g, morpheme));
                missing = true;
            }
            ids.push(i64::from(id));
        }
        if missing {
            return false;
        }
        let mut vowels = vec![0_i64; bank.vowel.len()];
        for &id in &ids {
            for &segment in bank.form(id as usize) {
                if bank.vowel[segment as usize] {
                    vowels[segment as usize] += 1;
                }
            }
        }
        sample.ids = ids;
        sample.vowels = vowels;
        sample.synced = Some(version);
        true
    }

    // --- hodnocení procesů ---------------------------------------------------------------------

    /// Hodnocení procesu `variable` (řádek změny v bance `proc_row`) pro skupiny `groups` (pozice
    /// v `inp`) v ticku `tick`. Platná uložená hodnocení se použijí, zastaralá se spočítají naráz
    /// (šířka matice je nejdelší vzorek mezi nimi pro dané pravidlo přízvuku, jako dřív). Položka
    /// bez hodnocení (chybí něco z `needs`) je `None`.
    #[allow(clippy::too_many_arguments)]
    pub fn assess(
        &mut self,
        bank: &mut Bank,
        inp: &Inputs<'_>,
        memo: &mut Memo,
        variable: u32,
        proc_row: usize,
        groups: &[usize],
        tick: i64,
        needs: &mut Needs,
        out: &mut Vec<Option<Assessment>>,
    ) -> Result<(), String> {
        out.clear();
        out.resize(groups.len(), None);
        let mut stale: Vec<usize> = Vec::new();
        for (at, &g) in groups.iter().enumerate() {
            let version = inp.versions[g];
            let found = self.groups.get(&inp.tokens[g]).and_then(|group| {
                group
                    .cache
                    .binary_search_by_key(&variable, |entry| entry.variable)
                    .ok()
                    .map(|position| &group.cache[position])
            });
            match found {
                Some(entry) if entry.version == version || tick - entry.tick < STALE_TICKS => {
                    out[at] = Some(entry.value);
                }
                _ => stale.push(at),
            }
        }
        if stale.is_empty() {
            return Ok(());
        }
        let mut ready = true;
        for &at in &stale {
            ready &= self.ensure_sample(bank, groups[at], inp, needs);
        }
        if !ready {
            return Ok(());
        }
        let info = self
            .processes
            .get(&variable)
            .cloned()
            .ok_or_else(|| format!("proces č. {variable} není zaregistrovaný"))?;
        let mut by_rule: BTreeMap<u8, Vec<usize>> = BTreeMap::new();
        for &at in &stale {
            by_rule.entry(inp.rules[groups[at]]).or_default().push(at);
        }
        for (rule, members) in by_rule {
            let width = members
                .iter()
                .map(|&at| self.groups[&inp.tokens[groups[at]]].sample.ids.len())
                .max()
                .unwrap_or(0);
            let mut blocked = false;
            let mut found: Vec<(usize, Assessment)> = Vec::with_capacity(members.len());
            for &at in &members {
                let g = groups[at];
                if width == 0 {
                    found.push((at, Assessment::default()));
                    continue;
                }
                let changed = {
                    let sample = &self.groups[&inp.tokens[g]].sample;
                    match bank.results(proc_row, rule, &sample.ids)? {
                        Outcome::Needs(segments) => {
                            needs.maps.entry(proc_row).or_default().extend(segments);
                            blocked = true;
                            continue;
                        }
                        Outcome::Done(changed) => changed,
                    }
                };
                match self.assess_sample(bank, inp, memo, g, &info, &changed, width, needs) {
                    Some(value) => found.push((at, value)),
                    None => blocked = true,
                }
            }
            if blocked {
                continue;
            }
            for (at, value) in found {
                let g = groups[at];
                out[at] = Some(value);
                let group = self.groups.entry(inp.tokens[g]).or_default();
                let entry = Entry {
                    variable,
                    version: inp.versions[g],
                    tick,
                    value,
                };
                match group
                    .cache
                    .binary_search_by_key(&variable, |entry| entry.variable)
                {
                    Ok(position) => group.cache[position] = entry,
                    Err(position) => group.cache.insert(position, entry),
                }
            }
        }
        Ok(())
    }

    /// Hodnocení jednoho vzorku (skupiny `g`) po aplikaci procesu; `None`, chybí-li odpověď na `needs`.
    #[allow(clippy::too_many_arguments)]
    fn assess_sample(
        &self,
        bank: &mut Bank,
        inp: &Inputs<'_>,
        memo: &mut Memo,
        g: usize,
        info: &ProcessInfo,
        changed: &[i64],
        width: usize,
        needs: &mut Needs,
    ) -> Option<Assessment> {
        let sample = &self.groups[&inp.tokens[g]].sample;
        let raw = bank.assess_row(&sample.ids, changed, &sample.weights, width, info.shapes);
        if raw.mass <= 0.0 {
            return Some(Assessment::default());
        }
        let mut merge = 0.0_f64;
        let mut complete = true;
        for &(first, second) in &raw.pairs {
            match pair_cost(inp, memo, g, sample, first as usize, second as usize, needs) {
                Some(cost) => merge += cost,
                None => complete = false,
            }
        }
        if !complete {
            return None;
        }
        Some(Assessment {
            coverage: raw.mass / sample.total,
            merge: merge / sample.total,
            short: raw.short / raw.mass,
            marked: raw.marked / raw.mass,
            dispersion: self.dispersion_gain(info, &raw.before, &raw.after),
        })
    }

    // --- uložení pro kontrolní bod --------------------------------------------------------------

    /// Uložená hodnocení kódu: (proměnná, verze, tik, pět hodnot).
    pub fn export(&self, token: i64) -> Vec<(u32, i64, i64, [f64; 5])> {
        self.groups
            .get(&token)
            .map(|group| {
                group
                    .cache
                    .iter()
                    .map(|entry| {
                        let v = entry.value;
                        (
                            entry.variable,
                            entry.version,
                            entry.tick,
                            [v.coverage, v.merge, v.short, v.marked, v.dispersion],
                        )
                    })
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Obnoví uložená hodnocení kódu (nahradí stávající).
    pub fn import(&mut self, token: i64, entries: Vec<(u32, i64, i64, [f64; 5])>) {
        let group = self.groups.entry(token).or_default();
        group.cache = entries
            .into_iter()
            .map(|(variable, version, tick, v)| Entry {
                variable,
                version,
                tick,
                value: Assessment {
                    coverage: v[0],
                    merge: v[1],
                    short: v[2],
                    marked: v[3],
                    dispersion: v[4],
                },
            })
            .collect();
        group.cache.sort_by_key(|entry| entry.variable);
    }

    /// Zapomene vše o kódu (např. zaniklá skupina).
    pub fn forget(&mut self, token: i64) {
        self.groups.remove(&token);
    }

    // --- hodnocení tvarů ---------------------------------------------------------------------

    /// Zaregistruje analogickou změnu tvaru (číslo proměnné z registru).
    pub fn register_form(&mut self, variable: u32, change: FormChange) {
        self.forms.register(variable, change);
    }

    pub fn has_form(&self, variable: u32) -> bool {
        self.forms.has(variable)
    }

    /// Zaregistrované analogické změny tvarů (čte je přestavba kódu).
    pub fn forms(&self) -> &FormRegistry {
        &self.forms
    }

    /// Hodnocení tvaru `variable` v kódu skupiny `g`; `None`, když výpočet čeká na výchozí tvar
    /// morfému (zapsáno do `needs`). Hodnoty se drží po verzi kódu a dopočítávají se podle potřeby.
    pub fn form_lookup(
        &mut self,
        ctx: &FormCtx<'_>,
        g: usize,
        variable: u32,
        needs: &mut Needs,
    ) -> Result<Option<FormEntry>, String> {
        let group = self.groups.entry(ctx.inp.tokens[g]).or_default();
        form_assess::lookup(&self.forms, &mut group.form, ctx, g, variable, needs)
    }
}

/// Cena dvojice nových homofonů (`cee.v2.assessment._pair`): geometrický průměr váh, u buněk téhož
/// lexému s vahou paradigmatu a vahou nadbytečné buňky; `None`, chybí-li odpověď na `needs`.
fn pair_cost(
    inp: &Inputs<'_>,
    memo: &mut Memo,
    g: usize,
    sample: &Sample,
    first: usize,
    second: usize,
    needs: &mut Needs,
) -> Option<f64> {
    let mut mass = (sample.weights[first] * sample.weights[second]).sqrt();
    let (a, b) = (sample.morphemes[first], sample.morphemes[second]);
    let lexeme = |morpheme: u32| inp.lexeme.get(morpheme as usize).copied().unwrap_or(-1);
    if lexeme(a) >= 0 && lexeme(a) == lexeme(b) {
        mass *= inp.paradigm_weight;
        let mut redundant = false;
        let mut unknown = false;
        for morpheme in [a, b] {
            if inp.cell.get(morpheme as usize).copied().unwrap_or(-1) < 0 {
                continue;
            }
            match memo.redundant.get(&(g, morpheme)) {
                Some(true) => {
                    redundant = true;
                    break;
                }
                Some(false) => {}
                None => {
                    needs.redundant.insert((g, morpheme));
                    unknown = true;
                }
            }
        }
        if unknown && !redundant {
            return None;
        }
        if redundant {
            mass *= inp.redundant_weight;
        }
    }
    Some(mass)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn index_with_vowels() -> AssessIndex {
        let mut index = AssessIndex::new();
        // Hlásky 0 až 3: samohlásky s (výška, zadnost, zaokrouhlení); hláska 4 je souhláska.
        index.set_coordinates(vec![
            [2.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 1.0],
            [1.0, 0.5, 0.0],
            [0.0, 0.0, 0.0],
        ]);
        index
    }

    #[test]
    fn zisk_rozptylu_je_vzdalenost_noveho_vokalu_minus_nejblizsi_zdroj() {
        let index = index_with_vowels();
        let info = ProcessInfo {
            shapes: true,
            output: 3,
            target: vec![true, false, false, false, false],
        };
        // Před změnou a, o (0, 1), po změně přibude 3 (zdroj je 0).
        let gain = index.dispersion_gain(&info, &[0, 1], &[0, 1, 3]);
        let near = nearest(&index.coords, 3, &[0, 1, 3]);
        let source = nearest(&index.coords, 0, &[0, 1]);
        assert_eq!(gain.to_bits(), (near - source).to_bits());
        // Výstup už ve slovní zásobě je: nic se nezískává.
        assert_eq!(index.dispersion_gain(&info, &[0, 3], &[0, 3]), 0.0);
        // Bez vokálové změny nebo bez zdroje v cíli je zisk nulový.
        let flat = ProcessInfo {
            shapes: false,
            ..info.clone()
        };
        assert_eq!(index.dispersion_gain(&flat, &[0, 1], &[0, 1, 3]), 0.0);
        assert_eq!(index.dispersion_gain(&info, &[1, 2], &[1, 2, 3]), 0.0);
    }

    #[test]
    fn nejblizsi_vokal_bez_dalsich_je_nula_a_sebe_nepocita() {
        let index = index_with_vowels();
        assert_eq!(nearest(&index.coords, 0, &[0]), 0.0);
        assert_eq!(nearest(&index.coords, 0, &[]), 0.0);
        let d = nearest(&index.coords, 0, &[0, 1]);
        assert_eq!(d.to_bits(), (4.0_f64 + 1.0).sqrt().to_bits());
    }

    #[test]
    fn ulozena_hodnoceni_se_exportuji_a_obnovi_bez_zmeny() {
        let mut index = AssessIndex::new();
        let entries = vec![
            (7, 3, 11, [0.5, 0.25, 0.125, -0.0625, 1.5]),
            (2, 4, 12, [0.0, 0.0, 0.0, 0.0, 0.0]),
        ];
        index.import(9, entries.clone());
        let mut expected = entries;
        expected.sort_by_key(|entry| entry.0);
        assert_eq!(index.export(9), expected);
        index.forget(9);
        assert!(index.export(9).is_empty());
    }

    #[test]
    fn cena_dvojice_stejneho_lexemu_ma_vahu_paradigmatu_a_ptá_se_na_nahradu() {
        let sample = Sample {
            morphemes: vec![0, 1],
            weights: vec![0.25, 1.0],
            total: 1.25,
            ..Sample::default()
        };
        let tokens = [1_i64];
        let versions = [0_i64];
        let rules = [0_u8];
        let forms: Vec<&[i32]> = vec![&[]];
        let inp = Inputs {
            tokens: &tokens,
            versions: &versions,
            rules: &rules,
            forms,
            defaults: &[],
            lexeme: &[3, 3],
            cell: &[-1, 2],
            paradigm_weight: 0.5,
            redundant_weight: 0.25,
        };
        let mut memo = Memo::default();
        let mut needs = Needs::default();
        assert!(pair_cost(&inp, &mut memo, 0, &sample, 0, 1, &mut needs).is_none());
        assert!(needs.redundant.contains(&(0, 1)));
        memo.redundant.insert((0, 1), true);
        let cost = pair_cost(&inp, &mut memo, 0, &sample, 0, 1, &mut needs).unwrap();
        assert_eq!(cost.to_bits(), (0.5_f64 * 0.5 * 0.25).to_bits());
        // Jiné lexémy: jen geometrický průměr.
        let other = Inputs {
            lexeme: &[3, 4],
            ..inp
        };
        let plain = pair_cost(&other, &mut memo, 0, &sample, 0, 1, &mut needs).unwrap();
        assert_eq!(plain.to_bits(), 0.5_f64.to_bits());
    }
}

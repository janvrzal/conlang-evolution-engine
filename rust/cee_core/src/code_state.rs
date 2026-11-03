//! Stav fonologie jednoho kódu v Rustu (B6c): fronty živých procesů, dominantní
//! kořeny pojmů a četnosti užití.
//!
//! Python dřív držel fronty (`pending`, `queued`, `restructured`) jako objekty
//! a před každým voláním jádra z nich skládal seznamy (`_targets`). Teď žijí
//! tady, podle čísla procesu (z registru) a morfému: Python posílá jen vstupy,
//! které mu patří (tvary kódu, sloupce světa, sklony slov), a čte rozhodnutí.
//!
//! **Pořadí fronty** je dvojice (potřebný logit, jméno morfému), stejně jako
//! `ProcessQueue` v Pythonu; jména drží banka (`Bank::names`), bajty UTF-8 se
//! řadí jako body Unicode. Shodné logity mají buňky téhož lexému.
//!
//! **Četnosti užití** (`World.usage_frequency`) jsou čistá funkce dominantních
//! kořenů kódu, četností pojmů a sloupců morfémů. Paměť podle čísla morfému se
//! zneplatňuje po kořenech: změna dominantního kořene pojmu zruší hodnoty všech
//! tvarů starého i nového kořene (`epoch` podle lexému), změna četností pojmů
//! všechno (`global`). Pojmy kořene se sčítají v pořadí, v jakém pojmy vstoupily
//! do mapy dominantních kořenů (`stamp`), tedy zleva doprava jako `sum` v Pythonu.
//!
//! Žádná transcendentní funkce se tu nepočítá: logity a sklony slov dodává Python.

use std::cell::RefCell;

use crate::bank::Bank;
use crate::phonology::{self, Frequency, Needs, Params, Rewrite, Target, Units, SKIP};

/// Vstupy četností užití: sloupce světa podle čísla morfému a četnosti pojmů.
pub struct UsageInputs<'a> {
    /// Četnost každého pojmu (podle čísla pojmu z registru).
    pub concept: &'a [f64],
    /// Statická frekvence morfému (sloupec `frequency`).
    pub fixed: &'a [f64],
    /// Váha buňky paradigmatu tvaru slova, NaN = bez váhy.
    pub weight: &'a [f64],
    /// Číslo lexému morfému (sloupec `lexeme`).
    pub lexeme: &'a [i32],
}

/// Dominantní kořeny pojmů a paměť četností užití.
#[derive(Default, Clone)]
pub struct Usage {
    /// Číslo pojmu → číslo dominantního kořene, −1 = žádný.
    roots: Vec<i32>,
    /// Pořadí vstupu pojmu do mapy dominantních kořenů (podle něj se sčítá).
    stamp: Vec<u64>,
    next_stamp: u64,
    /// Číslo kořene → pojmy, pro které je dominantní, vzestupně podle `stamp`.
    by_root: Vec<Vec<u32>>,
    value: Vec<f64>,
    /// Klíč platnosti hodnoty morfému (0 = nespočítáno).
    valid: Vec<u64>,
    /// Počet zneplatnění podle čísla lexému.
    epoch: Vec<u64>,
    global: u64,
}

impl Usage {
    /// Dominantní kořen pojmu se změnil (−1 = pojem kořen ztratil).
    pub fn set_root(&mut self, concept: usize, root: i32) {
        if concept >= self.roots.len() {
            self.roots.resize(concept + 1, -1);
            self.stamp.resize(concept + 1, 0);
        }
        let old = self.roots[concept];
        if old == root {
            return;
        }
        if old >= 0 {
            let list = &mut self.by_root[old as usize];
            if let Some(at) = list.iter().position(|&item| item as usize == concept) {
                list.remove(at);
            }
            self.invalidate(old as usize);
        } else {
            // Pojem do mapy vstupuje poprvé (nebo znovu po odebrání): na konec pořadí.
            self.stamp[concept] = self.next_stamp;
            self.next_stamp += 1;
        }
        self.roots[concept] = root;
        if root >= 0 {
            let root = root as usize;
            if root >= self.by_root.len() {
                self.by_root.resize_with(root + 1, Vec::new);
            }
            let key = self.stamp[concept];
            let stamps = &self.stamp;
            let list = &mut self.by_root[root];
            let at = list.partition_point(|&item| stamps[item as usize] < key);
            list.insert(at, concept as u32);
            self.invalidate(root);
        }
    }

    fn invalidate(&mut self, root: usize) {
        if root >= self.epoch.len() {
            self.epoch.resize(root + 1, 0);
        }
        self.epoch[root] += 1;
    }

    /// Změnily se četnosti pojmů: žádná hodnota v paměti neplatí.
    pub fn invalidate_all(&mut self) {
        self.global += 1;
    }

    /// Četnost užití morfému; `None`, když ho sloupce světa nezahrnují.
    pub fn frequency(&mut self, morpheme: usize, inputs: &UsageInputs) -> Option<f64> {
        let lexeme = *inputs.lexeme.get(morpheme)?;
        if lexeme < 0 {
            return None;
        }
        let lexeme = lexeme as usize;
        let key = self.epoch.get(lexeme).copied().unwrap_or(0) + self.global + 1;
        if self.valid.get(morpheme) == Some(&key) {
            return Some(self.value[morpheme]);
        }
        let fixed = *inputs.fixed.get(morpheme)?;
        let concepts = self.by_root.get(lexeme).map(Vec::as_slice).unwrap_or(&[]);
        let total = if concepts.is_empty() {
            fixed
        } else {
            let mut sum = 0.0;
            for &concept in concepts {
                sum += *inputs.concept.get(concept as usize)?;
            }
            let mut total = if sum < 1.0 { sum } else { 1.0 };
            let weight = inputs.weight.get(morpheme).copied().unwrap_or(f64::NAN);
            if !weight.is_nan() {
                total *= weight;
            }
            total
        };
        if morpheme >= self.valid.len() {
            self.valid.resize(morpheme + 1, 0);
            self.value.resize(morpheme + 1, 0.0);
        }
        self.valid[morpheme] = key;
        self.value[morpheme] = total;
        Some(total)
    }

    /// Dvojice (pojem, kořen) v pořadí vstupu do mapy; z nich se stav obnoví.
    pub fn roots_in_order(&self) -> Vec<(usize, i32)> {
        let mut found: Vec<(u64, usize)> = (0..self.roots.len())
            .filter(|&concept| self.roots[concept] >= 0)
            .map(|concept| (self.stamp[concept], concept))
            .collect();
        found.sort_unstable();
        found
            .into_iter()
            .map(|(_, concept)| (concept, self.roots[concept]))
            .collect()
    }
}

/// Četnosti užití pro jádro fronty: počítá je paměť `Usage` ze sloupců světa.
pub struct LiveUsage<'a, 'b> {
    usage: RefCell<&'a mut Usage>,
    inputs: &'b UsageInputs<'b>,
}

impl<'a, 'b> LiveUsage<'a, 'b> {
    pub fn new(usage: &'a mut Usage, inputs: &'b UsageInputs<'b>) -> Self {
        LiveUsage {
            usage: RefCell::new(usage),
            inputs,
        }
    }
}

impl Frequency for LiveUsage<'_, '_> {
    fn of(&self, lexeme: usize) -> Option<f64> {
        self.usage.borrow_mut().frequency(lexeme, self.inputs)
    }
}

/// Jeden proces kódu: fronta čekajících morfémů a přepsané morfémy.
#[derive(Default, Clone)]
pub struct Proc {
    /// Číslo procesu v registru.
    pub number: usize,
    /// Živý proces má frontu; uzavřený si ponechá jen přepsané morfémy.
    pub live: bool,
    pub reductive: bool,
    /// Řádek tabulky procesu v bance pro pravidlo přízvuku kódu; `None` = tabulka
    /// s tímto pravidlem v bance ještě není.
    pub row: Option<usize>,
    pub queued: Vec<u8>,
    pub done: Vec<u8>,
    pub needed: Vec<f64>,
    pub morphemes: Vec<i32>,
    /// Kdy dosáhl změněný tvar procesu 100 % (tik).
    pub fixed_since: Option<i64>,
}

/// Fronty a četnosti jednoho kódu.
#[derive(Default, Clone)]
pub struct CodeState {
    /// Procesy v pořadí, ve kterém kód zasáhly (živé i uzavřené).
    pub procs: Vec<Proc>,
    pub usage: Usage,
}

/// Co je společné všem voláním jádra jednoho kódu.
pub struct Ctx<'a> {
    pub params: Params,
    pub units: Units<'a>,
    pub usage: UsageInputs<'a>,
}

/// Co má Python doplnit; čísla front jsou čísla procesů z registru.
#[derive(Default, Debug)]
pub struct CodeNeeds {
    /// Sklon slova: (číslo procesu, morfém).
    pub bias: Vec<(usize, usize)>,
    pub freq: Vec<usize>,
    pub forms: Vec<usize>,
    pub maps: Vec<(usize, Vec<i32>)>,
    /// Procesy, jejichž tabulka s pravidlem přízvuku se má v bance založit.
    pub tables: Vec<usize>,
}

impl CodeNeeds {
    pub fn is_empty(&self) -> bool {
        self.bias.is_empty()
            && self.freq.is_empty()
            && self.forms.is_empty()
            && self.maps.is_empty()
            && self.tables.is_empty()
    }
}

/// `Needs` jádra s čísly front přeložená na čísla procesů (`number` dá číslo procesu fronty).
fn needs_with(needs: Needs, number: impl Fn(usize) -> usize) -> CodeNeeds {
    CodeNeeds {
        bias: needs
            .bias
            .into_iter()
            .map(|(target, morpheme)| (number(target), morpheme))
            .collect(),
        freq: needs.freq.into_iter().collect(),
        forms: needs.forms.into_iter().collect(),
        maps: needs
            .maps
            .into_iter()
            .map(|(row, segments)| (row, segments.into_iter().collect()))
            .collect(),
        tables: needs.tables.into_iter().map(number).collect(),
    }
}

/// Totéž pro fronty dané indexy procesů `live`.
fn needs_of(needs: Needs, procs: &[Proc], live: &[usize]) -> CodeNeeds {
    needs_with(needs, |target| procs[live[target]].number)
}

fn set_flag(flags: &mut Vec<u8>, morpheme: usize, value: u8) {
    if morpheme >= flags.len() {
        if value == 0 {
            return;
        }
        flags.resize(morpheme + 1, 0);
    }
    flags[morpheme] = value;
}

/// Zařadí morfém do fronty na místo dané dvojicí (logit, jméno).
fn insert_sorted(proc: &mut Proc, needed: f64, morpheme: usize, names: &[String]) {
    let name = names[morpheme].as_bytes();
    let (mut low, mut high) = (0, proc.needed.len());
    while low < high {
        let middle = (low + high) / 2;
        let before = proc.needed[middle];
        let less = before < needed
            || (before == needed && names[proc.morphemes[middle] as usize].as_bytes() < name);
        if less {
            low = middle + 1;
        } else {
            high = middle;
        }
    }
    proc.needed.insert(low, needed);
    proc.morphemes.insert(low, morpheme as i32);
    set_flag(&mut proc.queued, morpheme, 1);
}

fn target_of<'a>(proc: &'a Proc, bias: &'a [f64], strict: bool) -> Target<'a> {
    Target {
        row: match proc.row {
            Some(row) => row as i64,
            None if strict => SKIP,
            None => phonology::NO_TABLE,
        },
        queued: &proc.queued,
        restructured: &proc.done,
        bias,
        reductive: proc.reductive,
    }
}

/// Událost zpracování procesu skupiny, v pořadí vzniku.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    /// Fáze odebírání z fronty procesu skončila; kolik slov se v tomto průchodu přepsalo.
    Finished { proc: usize, words: usize },
    /// Fáze se zastavila kvůli chybějícím údajům; kolik slov se do té doby přepsalo.
    Partial { proc: usize, words: usize },
    /// Proces se uzavřel (po ustálení): kolik morfémů si ho zapsalo a kolik reliktů ve frontě zůstalo.
    Closed {
        proc: usize,
        restructured: usize,
        relics: usize,
    },
}

/// Vstup `restructure` jedné skupiny.
pub struct Round<'a> {
    pub ctx: Ctx<'a>,
    /// Sklony slov živých procesů v pořadí `live` na začátku průchodu.
    pub biases: Vec<&'a [f64]>,
    /// Logit sdíleného podílu změny v každém živém procesu (−∞ = podíl nekladný).
    pub levels: Vec<f64>,
    /// Podíl změny dosáhl 100 %.
    pub full: Vec<bool>,
    pub tick: i64,
    pub dt: f64,
    /// `closure_generations × generation_years`.
    pub threshold: f64,
}

/// Výstup `restructure`: přepsané tvary a události procesů.
#[derive(Default)]
pub struct RoundOut {
    pub rewrites: Vec<Rewrite>,
    pub events: Vec<Event>,
}

impl CodeState {
    /// Indexy živých procesů v pořadí vzniku.
    pub fn live(&self) -> Vec<usize> {
        (0..self.procs.len())
            .filter(|&index| self.procs[index].live)
            .collect()
    }

    pub fn find(&self, number: usize) -> Option<usize> {
        self.procs.iter().position(|proc| proc.number == number)
    }

    /// `_queue` pro všechny živé procesy a každý z morfémů po řadě. Vrací počet
    /// dokončených morfémů a to, co chybí; zastaví se **před** morfémem, kterému
    /// něco chybí (jeho zařazení do procesů, které už jde, se provede a při dalším
    /// volání se nezopakuje: zařazený morfém čeká a přeskočí se).
    pub fn queue_units(
        &mut self,
        bank: &mut Bank,
        ctx: &Ctx,
        biases: &[&[f64]],
        morphemes: &[i32],
    ) -> Result<(usize, CodeNeeds), String> {
        let live = self.live();
        for (position, &morpheme) in morphemes.iter().enumerate() {
            let (found, needs) = {
                let targets: Vec<Target> = live
                    .iter()
                    .zip(biases)
                    .map(|(&index, &bias)| target_of(&self.procs[index], bias, false))
                    .collect();
                let source = LiveUsage::new(&mut self.usage, &ctx.usage);
                phonology::queue_morpheme(
                    bank,
                    &ctx.params,
                    &ctx.units,
                    &targets,
                    morpheme as usize,
                    &source,
                )?
            };
            for insert in &found {
                let proc = &mut self.procs[live[insert.target]];
                insert_sorted(proc, insert.needed, insert.morpheme, &bank.names);
            }
            let missing = !needs.is_empty() || !needs.tables.is_empty();
            if missing {
                return Ok((position, needs_of(needs, &self.procs, &live)));
            }
        }
        Ok((morphemes.len(), CodeNeeds::default()))
    }

    /// `activate`: proces `number` poprvé zasáhl kód; fronta vznikne ze slovní
    /// zásoby (příznaky `vocabulary`). Chybí-li něco, nevznikne nic.
    #[allow(clippy::too_many_arguments)]
    pub fn activate(
        &mut self,
        bank: &mut Bank,
        ctx: &Ctx,
        number: usize,
        row: usize,
        reductive: bool,
        bias: &[f64],
        vocabulary: &[u8],
    ) -> Result<CodeNeeds, String> {
        if self.find(number).is_some() {
            return Err(format!("proces č. {number} už v kódu je"));
        }
        let target = Target {
            row: row as i64,
            queued: &[],
            restructured: &[],
            bias,
            reductive,
        };
        let names = std::mem::take(&mut bank.names);
        let result = {
            let source = LiveUsage::new(&mut self.usage, &ctx.usage);
            phonology::activate(
                bank,
                &ctx.params,
                &ctx.units,
                row,
                vocabulary,
                &target,
                &source,
                Some(&names),
            )
        };
        bank.names = names;
        let out = result?;
        if !out.needs.is_empty() {
            // Jediná fronta je proces sám.
            return Ok(needs_with(out.needs, |_| number));
        }
        let mut proc = Proc {
            number,
            live: true,
            reductive,
            row: Some(row),
            needed: out.needed,
            morphemes: out.morphemes.iter().map(|&item| item as i32).collect(),
            ..Proc::default()
        };
        for &morpheme in &out.morphemes {
            set_flag(&mut proc.queued, morpheme, 1);
        }
        self.procs.push(proc);
        Ok(CodeNeeds::default())
    }

    /// Fonologizace jedné skupiny (`phonology.restructure`) pro živé procesy
    /// v pořadí vzniku. Chybí-li údaj, vrátí ho; Python ho doplní a zavolá znovu
    /// (hotová práce se nezopakuje, protože stav je tady).
    pub fn restructure(
        &mut self,
        bank: &mut Bank,
        round: &Round,
        out: &mut RoundOut,
    ) -> Result<Option<CodeNeeds>, String> {
        let live0 = self.live();
        let ctx = &round.ctx;
        for (k, &index) in live0.iter().enumerate() {
            let level = round.levels[k];
            let proc = &self.procs[index];
            let mut words = 0;
            let mut stepped = false;
            if !(proc.needed.is_empty() || proc.needed[0] >= level) {
                stepped = true;
                let row = proc
                    .row
                    .ok_or_else(|| format!("proces č. {} nemá tabulku v bance", proc.number))?;
                let alive: Vec<usize> = (0..live0.len())
                    .filter(|&other| self.procs[live0[other]].live)
                    .collect();
                let step = {
                    let targets: Vec<Target> = alive
                        .iter()
                        .map(|&other| {
                            target_of(&self.procs[live0[other]], round.biases[other], true)
                        })
                        .collect();
                    let skip = alive
                        .iter()
                        .position(|&other| other == k)
                        .ok_or("proces uprostřed kroku není živý")?;
                    let source = LiveUsage::new(&mut self.usage, &ctx.usage);
                    phonology::step(
                        bank,
                        &ctx.params,
                        &ctx.units,
                        row,
                        &proc.needed,
                        &proc.morphemes,
                        level,
                        &targets,
                        skip,
                        &source,
                    )?
                };
                let proc = &mut self.procs[index];
                for &morpheme in &proc.morphemes[..step.popped] {
                    set_flag(&mut proc.queued, morpheme as usize, 0);
                }
                proc.needed.drain(..step.popped);
                proc.morphemes.drain(..step.popped);
                for rewrite in &step.rewrites {
                    set_flag(&mut proc.done, rewrite.morpheme, 1);
                    words += 1;
                    out.rewrites.push(*rewrite);
                }
                for insert in &step.inserts {
                    let target = &mut self.procs[live0[alive[insert.target]]];
                    insert_sorted(target, insert.needed, insert.morpheme, &bank.names);
                }
                let missing = !step.needs.is_empty() || !step.needs.tables.is_empty();
                if missing {
                    let number = self.procs[index].number;
                    let live: Vec<usize> = alive.iter().map(|&other| live0[other]).collect();
                    out.events.push(Event::Partial {
                        proc: number,
                        words,
                    });
                    return Ok(Some(needs_of(step.needs, &self.procs, &live)));
                }
            }
            let proc = &mut self.procs[index];
            if stepped {
                out.events.push(Event::Finished {
                    proc: proc.number,
                    words,
                });
            }
            if round.full[k] {
                let since = *proc.fixed_since.get_or_insert(round.tick);
                if ((round.tick - since) as f64) * round.dt >= round.threshold {
                    let restructured = proc.done.iter().filter(|&&flag| flag == 1).count();
                    let relics = proc.needed.len();
                    proc.live = false;
                    proc.needed = Vec::new();
                    proc.morphemes = Vec::new();
                    proc.queued = Vec::new();
                    out.events.push(Event::Closed {
                        proc: proc.number,
                        restructured,
                        relics,
                    });
                }
            } else {
                proc.fixed_since = None;
            }
        }
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn inputs<'a>(
        concept: &'a [f64],
        fixed: &'a [f64],
        weight: &'a [f64],
        lexeme: &'a [i32],
    ) -> UsageInputs<'a> {
        UsageInputs {
            concept,
            fixed,
            weight,
            lexeme,
        }
    }

    #[test]
    fn cetnost_secte_pojmy_korene_v_poradi_vstupu_a_zneplatni_po_korenech() {
        let (concept, fixed) = ([0.25, 0.5, 0.75], [0.1, 0.2, 0.3]);
        let (weight, lexeme) = ([f64::NAN, 0.5, f64::NAN], [0, 0, 2]);
        let data = inputs(&concept, &fixed, &weight, &lexeme);
        let mut usage = Usage::default();
        // Bez dominantních pojmů platí statická frekvence morfému.
        assert_eq!(usage.frequency(0, &data), Some(0.1));
        usage.set_root(2, 0);
        usage.set_root(0, 0);
        // (0,75 + 0,25) = 1,0 se ořízne na 1; tvar buňky má navíc váhu.
        assert_eq!(usage.frequency(0, &data), Some(1.0));
        assert_eq!(usage.frequency(1, &data), Some(0.5));
        // Kořen 2 pojmy nemá: statická frekvence.
        assert_eq!(usage.frequency(2, &data), Some(0.3));
        usage.set_root(1, 2);
        assert_eq!(usage.frequency(2, &data), Some(0.5));
        // Pojem 2 přešel ke kořeni 2: kořen 0 má jen pojem 0 (0,25).
        usage.set_root(2, 2);
        assert_eq!(usage.frequency(0, &data), Some(0.25));
        assert_eq!(usage.frequency(2, &data), Some(1.0));
        assert_eq!(usage.roots_in_order(), vec![(2, 2), (0, 0), (1, 2)]);
        usage.invalidate_all();
        assert_eq!(usage.frequency(1, &data), Some(0.125));
        // Morfém mimo sloupce světa nejde určit.
        assert_eq!(usage.frequency(9, &data), None);
    }

    #[test]
    fn znovu_vlozeny_pojem_je_na_konci_poradi_prepsany_zustava() {
        let mut usage = Usage::default();
        usage.set_root(0, 5);
        usage.set_root(1, 5);
        usage.set_root(0, 6); // přepsání: pořadí zůstává
        usage.set_root(0, -1); // odebrání
        usage.set_root(0, 5); // znovu: na konec
        assert_eq!(usage.roots_in_order(), vec![(1, 5), (0, 5)]);
    }

    #[test]
    fn zarazeni_do_fronty_radi_podle_logitu_a_jmena() {
        let names: Vec<String> = ["b", "a", "c"]
            .iter()
            .map(|name| name.to_string())
            .collect();
        let mut proc = Proc::default();
        insert_sorted(&mut proc, -1.0, 0, &names);
        insert_sorted(&mut proc, -1.0, 1, &names);
        insert_sorted(&mut proc, -2.0, 2, &names);
        assert_eq!(proc.morphemes, vec![2, 1, 0]);
        assert_eq!(proc.needed, vec![-2.0, -1.0, -1.0]);
        assert_eq!(proc.queued, vec![1, 1, 1]);
    }
}

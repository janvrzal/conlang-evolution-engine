//! Statistické brány: tři druhy bran nad rozdělením přes N semínek (`cee gates --report`).
//!
//! Staré brány (`m1` až `m6c`) jsou jednorázové: jedno až tři semínka a práh, který se
//! nastavil podle toho, jak často jev nastával v tehdejším enginu. Tady se každá z 52 bran
//! vyhodnotí jako statistický test proti **cílovému pásmu z literatury** (soubor
//! `src/cee/data/v2_gate_targets.json`, stav „návrh“, dokud ho uživatel neschválí):
//!
//! - **invariant**: podmínka musí platit v každém běhu (jeden až několik semínek);
//! - **možnost jevu**: jev nastal aspoň na `k` z `N` semínkách; `k` plyne z binomického
//!   rozdělení tak, aby falešné selhání při skutečné míře `p_min` mělo pravděpodobnost
//!   nejvýš 1 % (`P(Bin(N, p_min) < k) <= 0,01`, stejně jako pravidlo v dokumentu 09);
//! - **míra nebo pásmo**: metrika na `N` semínkách, medián a 95% bootstrapový interval;
//!   brána projde, když se interval překrývá s cílovým pásmem, nebo když medián leží
//!   v širším pásmu.
//!
//! Hodnoty bere z reportů starých bran (`Report` jedné dávky na jednom semínku), žádný běh
//! ani parametr enginu se nemění. Popis je v `docs/engine-v2/21-statisticke-brany.md`.

use std::collections::BTreeMap;
use std::fmt::Write as _;
use std::io::Write as _;
use std::panic::{catch_unwind, AssertUnwindSafe};

use serde::Deserialize;
use serde_json::json;

use super::stats::{threshold_k, wilson_interval};
use super::{batches, Batch, Report, Runner, GATES};

/// Cílová pásma jako data (vložená při sestavení).
pub const TARGETS_JSON: &str = include_str!("../../../../src/cee/data/v2_gate_targets.json");

/// Hladina falešného selhání brány „možnost jevu“.
pub const ALPHA: f64 = 0.01;
/// Počet vzorků bootstrapu.
const BOOTSTRAP: usize = 4000;

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq)]
pub enum Kind {
    #[serde(rename = "invariant")]
    Invariant,
    #[serde(rename = "možnost")]
    Possibility,
    #[serde(rename = "pásmo")]
    Band,
}

impl Kind {
    pub fn label(self) -> &'static str {
        match self {
            Kind::Invariant => "invariant",
            Kind::Possibility => "možnost",
            Kind::Band => "pásmo",
        }
    }
}

/// Podmínka na přepočtenou hodnotu metriky (`hodnota × scale`).
#[derive(Clone, Debug, Deserialize)]
pub struct Condition {
    pub metric: String,
    #[serde(default = "one")]
    pub scale: f64,
    pub op: String,
    pub value: f64,
}

fn one() -> f64 {
    1.0
}

impl Condition {
    fn holds(&self, report: &Report) -> bool {
        let value = metric_value(report, &self.metric) * self.scale;
        match self.op.as_str() {
            ">" => value > self.value,
            ">=" => value >= self.value,
            "<" => value < self.value,
            "<=" => value <= self.value,
            "==" => value == self.value,
            _ => false,
        }
    }
}

/// Jedna měřená veličina brány „pásmo“.
#[derive(Clone, Debug, Deserialize)]
pub struct Measure {
    pub label: String,
    pub metric: String,
    #[serde(default = "one")]
    pub scale: f64,
    pub band: [f64; 2],
    #[serde(default)]
    pub wide: Option<[f64; 2]>,
    /// „literatura“ (pásmo má oporu v citovaném zdroji) nebo „návrh“ (z věrohodnosti).
    pub support: String,
    pub source: String,
    pub conversion: String,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Target {
    pub id: String,
    pub kind: Kind,
    pub n: usize,
    /// Nejnižší skutečná míra jevu, při které brána „možnost“ ještě nemá selhat.
    #[serde(default)]
    pub p_min: f64,
    /// Metriky, které musí platit v každém běhu (u invariantu prázdné = všechny).
    #[serde(default)]
    pub require: Vec<String>,
    /// Podmínky jevu (u „možnosti“; prázdné = prošla stará brána).
    #[serde(default)]
    pub event: Vec<Condition>,
    #[serde(default)]
    pub measures: Vec<Measure>,
    /// Zdroj, na kterém stojí druh a `p_min` (u „možnosti“ a invariantu).
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub support: String,
    #[serde(default)]
    pub note: String,
}

#[derive(Debug, Deserialize)]
pub struct Targets {
    pub status: String,
    pub gates: Vec<Target>,
}

impl Targets {
    pub fn shared() -> Result<Targets, String> {
        let targets: Targets =
            serde_json::from_str(TARGETS_JSON).map_err(|e| format!("v2_gate_targets.json: {e}"))?;
        Ok(targets)
    }

    /// Soubor pokrývá právě registr 52 bran.
    pub fn check(&self) -> Result<(), String> {
        for gate in GATES {
            let found = self.gates.iter().filter(|t| t.id == gate.id).count();
            if found != 1 {
                return Err(format!("brána {} je v cílech {found}x", gate.id));
            }
        }
        for target in &self.gates {
            if !GATES.iter().any(|g| g.id == target.id) {
                return Err(format!("cíl {} není v registru bran", target.id));
            }
            match target.kind {
                Kind::Band if target.measures.is_empty() => {
                    return Err(format!("{}: pásmo bez měřené veličiny", target.id))
                }
                Kind::Possibility if !(target.p_min > 0.0 && target.p_min < 1.0) => {
                    return Err(format!("{}: možnost chce 0 < p_min < 1", target.id))
                }
                _ => {}
            }
        }
        Ok(())
    }
}

fn metric_value(report: &Report, name: &str) -> f64 {
    report
        .metrics
        .iter()
        .find(|m| m.name == name)
        .map_or(f64::NAN, |m| m.value)
}

fn metric_passed(report: &Report, name: &str) -> bool {
    report.metrics.iter().any(|m| m.name == name && m.passed)
}

/// Práh `k` brány „možnost“: nejmenší počet úspěchů, který stačí; aspoň 1.
pub fn required_successes(n: usize, p_min: f64) -> u32 {
    threshold_k(n as u32, p_min, ALPHA).max(1)
}

/// Pravděpodobnost, že brána selže, když je skutečná míra jevu `p`.
pub fn failure_probability(n: usize, k: u32, p: f64) -> f64 {
    super::stats::binomial_cdf_lt(i64::from(k), n as u32, p)
}

// --- pomocné statistiky ------------------------------------------------------------------------

pub fn median_of(values: &[f64]) -> f64 {
    let mut sorted: Vec<f64> = values.to_vec();
    sorted.sort_by(|a, b| a.total_cmp(b));
    match sorted.len() {
        0 => f64::NAN,
        n if n % 2 == 1 => sorted[n / 2],
        n => (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0,
    }
}

/// Deterministická náhoda bootstrapu (`splitmix64`), aby byl výpis opakovatelný.
struct SplitMix(u64);

impl SplitMix {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
}

fn hash_text(text: &str) -> u64 {
    text.bytes().fold(0xCBF2_9CE4_8422_2325, |h, b| {
        (h ^ u64::from(b)).wrapping_mul(0x0000_0100_0000_01B3)
    })
}

/// Percentilový bootstrapový 95% interval mediánu.
pub fn bootstrap_median_interval(values: &[f64], salt: &str) -> (f64, f64) {
    if values.is_empty() {
        return (f64::NAN, f64::NAN);
    }
    let mut rng = SplitMix(hash_text(salt));
    let n = values.len();
    let mut medians = Vec::with_capacity(BOOTSTRAP);
    let mut sample = vec![0.0; n];
    for _ in 0..BOOTSTRAP {
        for slot in sample.iter_mut() {
            *slot = values[(rng.next() % n as u64) as usize];
        }
        medians.push(median_of(&sample));
    }
    medians.sort_by(|a, b| a.total_cmp(b));
    let at = |q: f64| medians[((q * (BOOTSTRAP - 1) as f64).round() as usize).min(BOOTSTRAP - 1)];
    (at(0.025), at(0.975))
}

// --- vyhodnocení -------------------------------------------------------------------------------

/// Jeden řádek výpisu (brána může mít víc veličin).
#[derive(Clone, Debug)]
pub struct Row {
    pub gate: String,
    pub kind: Kind,
    pub label: String,
    pub n: usize,
    pub estimate: f64,
    pub low: f64,
    pub high: f64,
    pub target: String,
    pub passed: bool,
    pub support: String,
}

/// Co se z jedné dávky na jednom semínku (nebo trojici) zachovalo pro bránu.
pub type SeedResult = Result<Report, String>;

fn fmt(value: f64) -> String {
    if value.is_nan() {
        "nic".to_owned()
    } else if value.abs() >= 100.0 {
        format!("{value:.0}")
    } else if value.abs() >= 10.0 {
        format!("{value:.1}")
    } else {
        format!("{value:.3}")
    }
}

/// Vyhodnotí bránu na výsledcích semínek (první `n`).
pub fn evaluate(target: &Target, results: &[SeedResult]) -> Vec<Row> {
    let n = target.n.min(results.len());
    let results = &results[..n];
    let base = |label: &str| Row {
        gate: target.id.clone(),
        kind: target.kind,
        label: label.to_owned(),
        n,
        estimate: f64::NAN,
        low: f64::NAN,
        high: f64::NAN,
        target: String::new(),
        passed: false,
        support: target.support.clone(),
    };
    if n < target.n {
        let mut row = base("málo semínek");
        row.target = format!("potřeba {}", target.n);
        return vec![row];
    }
    match target.kind {
        Kind::Invariant => {
            let held = results
                .iter()
                .filter(|r| {
                    r.as_ref().is_ok_and(|report| {
                        if target.require.is_empty() {
                            report.passed()
                        } else {
                            target.require.iter().all(|m| metric_passed(report, m))
                        }
                    })
                })
                .count();
            let mut row = base("platí v každém běhu");
            row.estimate = held as f64 / n as f64;
            row.low = row.estimate;
            row.high = row.estimate;
            row.target = "= 1 (každý běh)".to_owned();
            row.passed = held == n;
            vec![row]
        }
        Kind::Possibility => {
            let occurred = results
                .iter()
                .filter(|r| {
                    r.as_ref().is_ok_and(|report| {
                        let required = target.require.iter().all(|m| metric_passed(report, m));
                        let event = if target.event.is_empty() {
                            report.passed()
                        } else {
                            target.event.iter().all(|c| c.holds(report))
                        };
                        required && event
                    })
                })
                .count() as u32;
            let k = required_successes(n, target.p_min);
            let (low, high) = wilson_interval(occurred, n as u32).unwrap_or((f64::NAN, f64::NAN));
            let mut row = base("jev nastal v podílu běhů");
            row.estimate = f64::from(occurred) / n as f64;
            row.low = low;
            row.high = high;
            row.target = format!(
                ">= {k} z {n} (p_min {}, falešný poplach {:.2} %)",
                fmt(target.p_min),
                100.0 * failure_probability(n, k, target.p_min)
            );
            row.passed = occurred >= k;
            vec![row]
        }
        Kind::Band => {
            let mut rows = Vec::new();
            for measure in &target.measures {
                let values: Vec<f64> = results
                    .iter()
                    .filter_map(|r| r.as_ref().ok())
                    .map(|report| metric_value(report, &measure.metric) * measure.scale)
                    .filter(|v| !v.is_nan())
                    .collect();
                let mut row = base(&measure.label);
                row.support = measure.support.clone();
                row.target = format!("[{}, {}]", fmt(measure.band[0]), fmt(measure.band[1]));
                if values.len() * 2 < n {
                    row.target.push_str(" (málo hodnot)");
                    row.n = values.len();
                    rows.push(row);
                    continue;
                }
                let median = median_of(&values);
                let (low, high) =
                    bootstrap_median_interval(&values, &format!("{}|{}", target.id, measure.label));
                let overlap = low <= measure.band[1] && high >= measure.band[0];
                let in_wide = measure
                    .wide
                    .is_some_and(|w| median >= w[0] && median <= w[1]);
                row.n = values.len();
                row.estimate = median;
                row.low = low;
                row.high = high;
                row.passed = overlap || in_wide;
                rows.push(row);
            }
            // Požadované metriky (invariantní část brány) musí platit v každém běhu.
            if !target.require.is_empty() {
                let held = results
                    .iter()
                    .filter(|r| {
                        r.as_ref()
                            .is_ok_and(|rep| target.require.iter().all(|m| metric_passed(rep, m)))
                    })
                    .count();
                let mut row = base("invariantní část v každém běhu");
                row.estimate = held as f64 / n as f64;
                row.low = row.estimate;
                row.high = row.estimate;
                row.target = "= 1 (každý běh)".to_owned();
                row.passed = held == n;
                rows.push(row);
            }
            rows
        }
    }
}

// --- běh ---------------------------------------------------------------------------------------

pub struct ReportOptions {
    /// První semínko; běhy dávky používají `start, start + 1, …` (u trojic po třech).
    pub start: i64,
    pub only: Vec<String>,
    /// Zápis hodnot všech metrik po semínkách (JSONL).
    pub jsonl: Option<String>,
}

fn wanted(only: &[String], batch: &Batch, gate: &str) -> bool {
    only.is_empty()
        || only.iter().any(|item| {
            item == gate
                || item == batch.id
                || gate
                    .strip_prefix(item.as_str())
                    .is_some_and(|rest| rest.starts_with("::"))
        })
}

fn execute(runner: Runner, seeds: &[i64]) -> Result<Vec<(&'static str, Report)>, String> {
    let outcome = catch_unwind(AssertUnwindSafe(|| match runner {
        Runner::Single(run) => run(seeds[0]),
        Runner::Triplet(run) => run([seeds[0], seeds[1], seeds[2]]),
    }));
    match outcome {
        Ok(result) => result,
        Err(_) => Err("pád enginu".to_owned()),
    }
}

/// Spustí dávky, vyhodnotí všech 52 bran a vrátí řádky.
pub fn run_rows(options: &ReportOptions) -> Result<Vec<Row>, String> {
    let targets = Targets::shared()?;
    targets.check()?;
    let mut sink = match &options.jsonl {
        Some(path) => Some(std::fs::File::create(path).map_err(|e| format!("{path}: {e}"))?),
        None => None,
    };
    let mut collected: BTreeMap<String, Vec<SeedResult>> = BTreeMap::new();
    for batch in batches() {
        let chosen: Vec<&Target> = targets
            .gates
            .iter()
            .filter(|t| {
                batch.gates.contains(&t.id.as_str()) && wanted(&options.only, &batch, &t.id)
            })
            .collect();
        let Some(count) = chosen.iter().map(|t| t.n).max() else {
            continue;
        };
        for index in 0..count {
            let seeds: Vec<i64> = match batch.run {
                Runner::Single(_) => vec![options.start + index as i64],
                Runner::Triplet(_) => (0..3)
                    .map(|j| options.start + 3 * index as i64 + j)
                    .collect(),
            };
            eprintln!(
                "dávka {} vzorek {}/{count} semínka {seeds:?}",
                batch.id,
                index + 1
            );
            let outcome = execute(batch.run, &seeds);
            for target in &chosen {
                let result: SeedResult = match &outcome {
                    Err(message) => Err(message.clone()),
                    Ok(reports) => reports
                        .iter()
                        .find(|(id, _)| *id == target.id)
                        .map(|(_, report)| report.clone())
                        .ok_or_else(|| "dávka brány nevrátila".to_owned()),
                };
                if let (Some(file), Ok(report)) = (sink.as_mut(), &result) {
                    let metrics: Vec<_> = report
                        .metrics
                        .iter()
                        .map(|m| json!({"metric": m.name, "value": m.value, "passed": m.passed}))
                        .collect();
                    let line = json!({"gate": target.id, "seeds": seeds, "metrics": metrics});
                    writeln!(file, "{line}").map_err(|e| e.to_string())?;
                }
                collected.entry(target.id.clone()).or_default().push(result);
            }
        }
    }
    let mut rows = Vec::new();
    for target in &targets.gates {
        if let Some(results) = collected.get(&target.id) {
            rows.extend(evaluate(target, results));
        }
    }
    Ok(rows)
}

/// Markdown tabulka: brána, druh, N, medián, interval, cílové pásmo, prošla.
pub fn render(rows: &[Row]) -> String {
    let mut text = String::from(
        "| brána | druh | veličina | N | medián / podíl | interval 95 % | cílové pásmo | podpora | prošla |\n|---|---|---|---:|---:|---|---|---|---|\n",
    );
    for row in rows {
        let _ = writeln!(
            text,
            "| {} | {} | {} | {} | {} | [{}, {}] | {} | {} | {} |",
            row.gate,
            row.kind.label(),
            row.label,
            row.n,
            fmt(row.estimate),
            fmt(row.low),
            fmt(row.high),
            row.target,
            row.support,
            if row.passed { "prošla" } else { "neprošla" }
        );
    }
    let gates: std::collections::BTreeSet<&str> = rows.iter().map(|r| r.gate.as_str()).collect();
    let passed = gates
        .iter()
        .filter(|g| rows.iter().filter(|r| r.gate == **g).all(|r| r.passed))
        .count();
    let _ = writeln!(text, "\nBrány, které prošly: {passed} z {}.", gates.len());
    text
}

/// Seznam bran s druhem a N (`--report --list`).
pub fn list() -> Result<String, String> {
    let targets = Targets::shared()?;
    targets.check()?;
    let mut text = format!(
        "Stav cílů: {}\n\n| brána | druh | N | p_min |\n|---|---|---:|---:|\n",
        targets.status
    );
    for target in &targets.gates {
        let _ = writeln!(
            text,
            "| {} | {} | {} | {} |",
            target.id,
            target.kind.label(),
            target.n,
            if target.kind == Kind::Possibility {
                fmt(target.p_min)
            } else {
                "-".to_owned()
            }
        );
    }
    Ok(text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gates::Cmp;

    fn report(value: f64) -> Report {
        let mut report = Report::new();
        report.check("x", value, Cmp::Gt, 0.0);
        report
    }

    #[test]
    fn cile_pokryvaji_registr() {
        Targets::shared().unwrap().check().unwrap();
    }

    #[test]
    fn median_a_bootstrap_jsou_opakovatelne() {
        let values = [1.0, 2.0, 3.0, 4.0, 10.0];
        assert_eq!(median_of(&values), 3.0);
        let first = bootstrap_median_interval(&values, "a");
        assert_eq!(first, bootstrap_median_interval(&values, "a"));
        assert!(first.0 >= 1.0 && first.1 <= 10.0 && first.0 <= 3.0 && first.1 >= 3.0);
    }

    #[test]
    fn prah_k_je_aspon_jedna_a_falesny_poplach_do_procenta() {
        // Jev s mírou 0,2 se při 30 semínkách objeví aspoň jednou (0,8^30 = 0,12 %).
        let k = required_successes(30, 0.2);
        assert!(k >= 1);
        assert!(failure_probability(30, k, 0.2) <= ALPHA);
        // Při malém N plyne z pravidla k = 0, brána ale nikdy nesmí projít bez jevu.
        assert_eq!(required_successes(5, 0.2), 1);
    }

    #[test]
    fn pasmo_prekryv_a_sire_pasmo() {
        let target = |band: [f64; 2], wide: Option<[f64; 2]>| Target {
            id: "t".into(),
            kind: Kind::Band,
            n: 8,
            p_min: 0.0,
            require: Vec::new(),
            event: Vec::new(),
            measures: vec![Measure {
                label: "x".into(),
                metric: "x".into(),
                scale: 1.0,
                band,
                wide,
                support: "návrh".into(),
                source: String::new(),
                conversion: String::new(),
            }],
            source: String::new(),
            support: String::new(),
            note: String::new(),
        };
        let results: Vec<SeedResult> = (1..=8).map(|v| Ok(report(f64::from(v)))).collect();
        assert!(evaluate(&target([4.0, 5.0], None), &results)[0].passed);
        assert!(!evaluate(&target([20.0, 30.0], None), &results)[0].passed);
        assert!(evaluate(&target([20.0, 30.0], Some([3.0, 6.0])), &results)[0].passed);
    }

    #[test]
    fn invariant_chce_vsechny_behy() {
        let target = Target {
            id: "t".into(),
            kind: Kind::Invariant,
            n: 3,
            p_min: 0.0,
            require: Vec::new(),
            event: Vec::new(),
            measures: Vec::new(),
            source: String::new(),
            support: String::new(),
            note: String::new(),
        };
        let good: Vec<SeedResult> = vec![Ok(report(1.0)), Ok(report(1.0)), Ok(report(1.0))];
        let bad: Vec<SeedResult> = vec![Ok(report(1.0)), Ok(report(-1.0)), Ok(report(1.0))];
        assert!(evaluate(&target, &good)[0].passed);
        assert!(!evaluate(&target, &bad)[0].passed);
    }

    #[test]
    fn moznost_chce_k_z_n() {
        let target = Target {
            id: "t".into(),
            kind: Kind::Possibility,
            n: 30,
            p_min: 0.2,
            require: Vec::new(),
            event: Vec::new(),
            measures: Vec::new(),
            source: String::new(),
            support: String::new(),
            note: String::new(),
        };
        let none: Vec<SeedResult> = (0..30).map(|_| Ok(report(-1.0))).collect();
        let some: Vec<SeedResult> = (0..30)
            .map(|i| Ok(report(if i % 3 == 0 { 1.0 } else { -1.0 })))
            .collect();
        assert!(!evaluate(&target, &none)[0].passed);
        assert!(evaluate(&target, &some)[0].passed);
    }
}

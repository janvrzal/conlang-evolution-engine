//! Brány milníků M1 až M6c v Rustu (zrcadlo `tests/v2/test_v2_m*_gate.py`).
//!
//! Každý milník má modul `m1` až `m6c` se třemi druhy věcí: **běhy** (`run_*`: scénář,
//! semínko, délka), **kontroly** (`check_*`: metriky jednoho běhu jako [`Report`]) a **dávky**
//! (`batches()`: běh jednoho semínka a vyhodnocení všech bran, které z něj plynou).
//!
//! Verdikt brány dává [`statistical`]: metriky z `N` semínek proti zamčenému cílovému pásmu
//! (`src/cee/data/v2_gate_targets.json`, dokument 21). Prahy v `Report` jsou jen definice jevu
//! u bran typu „možnost“. Integrační testy (`tests/gates/`) i příkaz `cee gates` volají totéž. Metriky ([`metrics`]) se počítají
//! z historie, snímků a stavu světa v Rustu; co Rust zatím v datech nemá, je v dokumentu
//! `docs/engine-v2/19-engine-v-rustu.md` (oddíl R2b).

pub mod m1;
pub mod m2;
pub mod m3;
pub mod m3b;
pub mod m4;
pub mod m4b;
pub mod m5;
pub mod m6a;
pub mod m6b;
pub mod m6c;
pub mod metrics;
pub mod statistical;
pub mod stats;

use std::fmt::Write as _;

/// Jak se hodnota metriky porovnává s prahem.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Cmp {
    Lt,
    Le,
    Gt,
    Ge,
    Eq,
    /// Dolní mez včetně, horní mez včetně (`Metric::upper`).
    Between,
}

/// Jedno tvrzení brány: co se měřilo, kolik vyšlo a jaký je práh.
#[derive(Clone, Debug)]
pub struct Metric {
    pub name: String,
    pub value: f64,
    pub cmp: Cmp,
    pub threshold: f64,
    /// Horní mez pro [`Cmp::Between`].
    pub upper: f64,
    pub passed: bool,
}

impl Metric {
    /// Práh jako text (`< 0,01`, `∈ [3, 8]`).
    pub fn threshold_text(&self) -> String {
        match self.cmp {
            Cmp::Lt => format!("< {}", number(self.threshold)),
            Cmp::Le => format!("<= {}", number(self.threshold)),
            Cmp::Gt => format!("> {}", number(self.threshold)),
            Cmp::Ge => format!(">= {}", number(self.threshold)),
            Cmp::Eq => format!("= {}", number(self.threshold)),
            Cmp::Between => format!("[{}, {}]", number(self.threshold), number(self.upper)),
        }
    }
}

fn number(value: f64) -> String {
    if value.is_nan() {
        "nic".to_owned()
    } else if value.fract() == 0.0 && value.abs() < 1e9 {
        format!("{value:.0}")
    } else {
        format!("{value:.4}")
    }
}

/// Výsledek jedné kontroly: seznam metrik.
#[derive(Clone, Debug, Default)]
pub struct Report {
    pub metrics: Vec<Metric>,
}

impl Report {
    pub fn new() -> Report {
        Report::default()
    }

    /// Zapíše metriku; `NaN` (hodnota, kterou nešlo spočítat) nikdy neprojde.
    pub fn check(&mut self, name: &str, value: f64, cmp: Cmp, threshold: f64) -> bool {
        self.push(name, value, cmp, threshold, threshold)
    }

    /// Hodnota v uzavřeném intervalu `[low, high]`.
    pub fn between(&mut self, name: &str, value: f64, low: f64, high: f64) -> bool {
        self.push(name, value, Cmp::Between, low, high)
    }

    /// Logické tvrzení (hodnota 1 = platí).
    pub fn flag(&mut self, name: &str, holds: bool) -> bool {
        self.push(name, f64::from(u8::from(holds)), Cmp::Eq, 1.0, 1.0)
    }

    /// Něco, co kontrola potřebuje, ve světě není (skupina, proměnná): neprojde.
    pub fn missing(&mut self, what: &str) {
        self.push(&format!("chybí: {what}"), f64::NAN, Cmp::Eq, 1.0, 1.0);
    }

    fn push(&mut self, name: &str, value: f64, cmp: Cmp, threshold: f64, upper: f64) -> bool {
        let passed = !value.is_nan()
            && match cmp {
                Cmp::Lt => value < threshold,
                Cmp::Le => value <= threshold,
                Cmp::Gt => value > threshold,
                Cmp::Ge => value >= threshold,
                Cmp::Eq => value == threshold,
                Cmp::Between => value >= threshold && value <= upper,
            };
        self.metrics.push(Metric {
            name: name.to_owned(),
            value,
            cmp,
            threshold,
            upper,
            passed,
        });
        passed
    }

    /// Přidá metriky jiné kontroly s předponou.
    pub fn extend(&mut self, prefix: &str, other: Report) {
        for mut metric in other.metrics {
            if !prefix.is_empty() {
                metric.name = format!("{prefix}: {}", metric.name);
            }
            self.metrics.push(metric);
        }
    }

    pub fn passed(&self) -> bool {
        self.metrics.iter().all(|m| m.passed)
    }

    /// Text neúspěšných metrik (jedna na řádek).
    pub fn failures(&self) -> String {
        let mut text = String::new();
        for metric in self.metrics.iter().filter(|m| !m.passed) {
            let _ = writeln!(
                text,
                "  {}: {} (práh {})",
                metric.name,
                number(metric.value),
                metric.threshold_text()
            );
        }
        text
    }

    /// Markdown řádky `| metrika | hodnota | práh | prošla |` pro bránu `gate`.
    pub fn table_rows(&self, gate: &str) -> String {
        let mut text = String::new();
        for metric in &self.metrics {
            let _ = writeln!(
                text,
                "| {gate} | {} | {} | {} | {} |",
                metric.name,
                number(metric.value),
                metric.threshold_text(),
                if metric.passed {
                    "prošla"
                } else {
                    "neprošla"
                }
            );
        }
        text
    }
}

/// Rozsah `101..120`, seznam `1,2,3` nebo jejich kombinace (`1..3,7`).
pub fn parse_seeds(text: &str) -> Result<Vec<i64>, String> {
    let mut seeds = Vec::new();
    for part in text.split(',').map(str::trim).filter(|p| !p.is_empty()) {
        if let Some((from, to)) = part.split_once("..") {
            let (from, to): (i64, i64) = (
                from.trim()
                    .parse()
                    .map_err(|_| format!("semínko '{part}'"))?,
                to.trim().parse().map_err(|_| format!("semínko '{part}'"))?,
            );
            if to < from {
                return Err(format!("prázdný rozsah semínek '{part}'"));
            }
            seeds.extend(from..=to);
        } else {
            seeds.push(part.parse().map_err(|_| format!("semínko '{part}'"))?);
        }
    }
    if seeds.is_empty() {
        return Err("chybí semínka".into());
    }
    Ok(seeds)
}

/// Brána v registru (cílové pásmo má v `v2_gate_targets.json`).
#[derive(Clone, Copy, Debug)]
pub struct GateInfo {
    pub id: &'static str,
}

/// Běh a vyhodnocení bran pro jedno semínko (nebo trojici semínek).
pub type SeedRun = fn(i64) -> Result<Vec<(&'static str, Report)>, String>;
/// Totéž pro dávku, která potřebuje tři semínka najednou.
pub type TripletRun = fn([i64; 3]) -> Result<Vec<(&'static str, Report)>, String>;

#[derive(Clone, Copy)]
pub enum Runner {
    Single(SeedRun),
    Triplet(TripletRun),
}

/// Dávka: jeden běh scénáře, ze kterého se vyhodnotí víc bran.
pub struct Batch {
    pub id: &'static str,
    pub gates: &'static [&'static str],
    pub run: Runner,
}

/// Všechny dávky všech milníků v pořadí Pythonu (`scripts/v2_gate_rates.py`).
pub fn batches() -> Vec<Batch> {
    let mut all = Vec::new();
    all.extend(m1::batches());
    all.extend(m2::batches());
    all.extend(m3::batches());
    all.extend(m3b::batches());
    all.extend(m4::batches());
    all.extend(m4b::batches());
    all.extend(m5::batches());
    all.extend(m6a::batches());
    all.extend(m6b::batches());
    all.extend(m6c::batches());
    all
}

/// Registr 47 bran milníků (52 převzatých z Pythonu, 5. 11. 2026 sloučeno: zvukové metriky
/// M2, M3, M3b a M4 do `m2::zvukove_metriky`, strom M6c do `m6c::strom`, zrušeno `m4b::bez_padu`).
/// Brána `m2::zvukove_metriky` je ve víc dávkách, ostatní v právě jedné.
pub const GATES: [GateInfo; 47] = [
    GateInfo {
        id: "m1::s1_kontinuum",
    },
    GateInfo {
        id: "m1::s1_hranice",
    },
    GateInfo {
        id: "m1::metrika_7",
    },
    GateInfo {
        id: "m1::metrika_8",
    },
    GateInfo {
        id: "m1::velka_skupina_drift",
    },
    GateInfo {
        id: "m2::metrika_4",
    },
    GateInfo {
        id: "m2::zvukove_metriky",
    },
    GateInfo {
        id: "m2::metrika_6",
    },
    GateInfo {
        id: "m2::ruznost_seedu",
    },
    GateInfo {
        id: "m2::zvukove_zmeny_se_siri",
    },
    GateInfo {
        id: "m3::sturtevantuv_paradox",
    },
    GateInfo {
        id: "m3::morfologizace",
    },
    GateInfo {
        id: "m3::produktivni_vzor",
    },
    GateInfo { id: "m3::analogie" },
    GateInfo {
        id: "m3b::metrika_1",
    },
    GateInfo {
        id: "m3b::metrika_2",
    },
    GateInfo {
        id: "m3b::nova_slova",
    },
    GateInfo {
        id: "m3b::erodovana_slova",
    },
    GateInfo { id: "m3b::tabu" },
    GateInfo {
        id: "m4::analytizace",
    },
    GateInfo {
        id: "m4::velky_cyklus",
    },
    GateInfo {
        id: "m4::jespersen",
    },
    GateInfo {
        id: "m4::bez_eroze",
    },
    GateInfo {
        id: "m4b::clen_vznikne",
    },
    GateInfo {
        id: "m4b::exaptace",
    },
    GateInfo {
        id: "m4b::jazyk_bez_kategorie",
    },
    GateInfo { id: "m5::s2_mesto" },
    GateInfo { id: "m5::s2_l2" },
    GateInfo {
        id: "m5::s3_prechod",
    },
    GateInfo {
        id: "m5::s3_substrat",
    },
    GateInfo { id: "m5::vypujcky" },
    GateInfo {
        id: "m5::bez_dvojjazycnosti",
    },
    GateInfo {
        id: "m5::metrika_11",
    },
    GateInfo {
        id: "m6a::s4_skola",
    },
    GateInfo {
        id: "m6a::s4_bez_skoly",
    },
    GateInfo {
        id: "m6a::skola_sjednoti",
    },
    GateInfo {
        id: "m6a::skola_zmrazena",
    },
    GateInfo {
        id: "m6a::psany_kod_stoji",
    },
    GateInfo {
        id: "m6b::metrika_9",
    },
    GateInfo {
        id: "m6b::elita_prejde",
    },
    GateInfo {
        id: "m6b::superstrat",
    },
    GateInfo {
        id: "m6b::jazyk_trhu",
    },
    GateInfo {
        id: "m6b::loajalita",
    },
    GateInfo { id: "m6b::migrace" },
    GateInfo {
        id: "m6b::ferguson",
    },
    GateInfo {
        id: "m6b::nabozenstvi",
    },
    GateInfo { id: "m6c::strom" },
];

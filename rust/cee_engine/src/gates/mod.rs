//! Brány milníků M1 až M6c v Rustu (zrcadlo `tests/v2/test_v2_m*_gate.py`).
//!
//! Každý milník má modul `m1` až `m6c` se čtyřmi druhy věcí: **běhy** (`run_*`: scénář,
//! semínko, délka), **kontroly** (`check_*`: metriky a prahy Pythonu) a **dávky** pro audit
//! (`batches()`: běh jednoho semínka a vyhodnocení všech bran, které z něj plynou). Kontroly
//! nevrací první neúspěšné tvrzení, ale celé [`Report`]: každá metrika má hodnotu, práh
//! a výsledek, takže jde vypsat tabulku „brána, metrika, hodnota, práh, prošla“.
//!
//! Integrační testy (`tests/gates/`) a příkaz `cee gates` (audit míry průchodu na semínkách,
//! `scripts/v2_gate_rates.py` v Pythonu) volají totéž. Metriky ([`metrics`]) se počítají
//! z historie, snímků a stavu světa v Rustu; co Rust zatím v datech nemá, je v dokumentu
//! `docs/engine-v2/19-engine-v-rustu.md` (oddíl R2b).

pub mod audit;
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

/// Brána v registru auditu: jméno, soubor milníku a kolik semínek má dnes v Pythonu.
#[derive(Clone, Copy, Debug)]
pub struct GateInfo {
    pub id: &'static str,
    pub seeds_today: &'static str,
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

/// Registr 52 stochastických bran (jména jako v Pythonu) se semínky dnešních testů.
pub const GATES: [GateInfo; 52] = [
    GateInfo {
        id: "m1::s1_kontinuum",
        seeds_today: "1",
    },
    GateInfo {
        id: "m1::s1_hranice",
        seeds_today: "1",
    },
    GateInfo {
        id: "m1::metrika_7",
        seeds_today: "1",
    },
    GateInfo {
        id: "m1::metrika_8",
        seeds_today: "1",
    },
    GateInfo {
        id: "m1::velka_skupina_drift",
        seeds_today: "1",
    },
    GateInfo {
        id: "m2::metrika_3",
        seeds_today: "3",
    },
    GateInfo {
        id: "m2::metrika_4",
        seeds_today: "3",
    },
    GateInfo {
        id: "m2::metrika_5",
        seeds_today: "3",
    },
    GateInfo {
        id: "m2::metrika_6",
        seeds_today: "3 (soubor)",
    },
    GateInfo {
        id: "m2::ruznost_seedu",
        seeds_today: "3 (soubor)",
    },
    GateInfo {
        id: "m2::zvukove_zmeny_se_siri",
        seeds_today: "3",
    },
    GateInfo {
        id: "m3::sturtevantuv_paradox",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3::morfologizace",
        seeds_today: "10 (aspoň 4)",
    },
    GateInfo {
        id: "m3::produktivni_vzor",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3::analogie",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3::zvukove_metriky",
        seeds_today: "10 (aspoň 5)",
    },
    GateInfo {
        id: "m3b::metrika_1",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3b::metrika_2",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3b::nova_slova",
        seeds_today: "2",
    },
    GateInfo {
        id: "m3b::erodovana_slova",
        seeds_today: "1",
    },
    GateInfo {
        id: "m3b::tabu",
        seeds_today: "12 (aspoň 1)",
    },
    GateInfo {
        id: "m3b::zvukove_metriky",
        seeds_today: "2",
    },
    GateInfo {
        id: "m4::analytizace",
        seeds_today: "1",
    },
    GateInfo {
        id: "m4::velky_cyklus",
        seeds_today: "10 (aspoň 2)",
    },
    GateInfo {
        id: "m4::jespersen",
        seeds_today: "19 (aspoň 1)",
    },
    GateInfo {
        id: "m4::bez_eroze",
        seeds_today: "1",
    },
    GateInfo {
        id: "m4b::clen_vznikne",
        seeds_today: "50 (1 až N-1 s členem)",
    },
    GateInfo {
        id: "m4b::bez_padu",
        seeds_today: "3",
    },
    GateInfo {
        id: "m4b::exaptace",
        seeds_today: "10 (aspoň 2)",
    },
    GateInfo {
        id: "m4b::jazyk_bez_kategorie",
        seeds_today: "1",
    },
    GateInfo {
        id: "m5::s2_mesto",
        seeds_today: "2",
    },
    GateInfo {
        id: "m5::s2_l2",
        seeds_today: "2",
    },
    GateInfo {
        id: "m5::s3_prechod",
        seeds_today: "2",
    },
    GateInfo {
        id: "m5::s3_substrat",
        seeds_today: "12 (aspoň 1)",
    },
    GateInfo {
        id: "m5::vypujcky",
        seeds_today: "2",
    },
    GateInfo {
        id: "m5::bez_dvojjazycnosti",
        seeds_today: "2",
    },
    GateInfo {
        id: "m5::metrika_11",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6a::s4_skola",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6a::s4_bez_skoly",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6a::skola_sjednoti",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6a::skola_zmrazena",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6a::psany_kod_stoji",
        seeds_today: "1",
    },
    GateInfo {
        id: "m6b::metrika_9",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6b::elita_prejde",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6b::superstrat",
        seeds_today: "10 (aspoň 2)",
    },
    GateInfo {
        id: "m6b::jazyk_trhu",
        seeds_today: "10 (aspoň 2)",
    },
    GateInfo {
        id: "m6b::loajalita",
        seeds_today: "1",
    },
    GateInfo {
        id: "m6b::migrace",
        seeds_today: "10 (aspoň 2)",
    },
    GateInfo {
        id: "m6b::ferguson",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6b::nabozenstvi",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6c::strom_odpovida",
        seeds_today: "2",
    },
    GateInfo {
        id: "m6c::strom_stabilni",
        seeds_today: "2",
    },
];

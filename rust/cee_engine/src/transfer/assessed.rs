//! Tlaky nad hodnocením: zvukové procesy (`articulation`, `clarity`, `functional_load`,
//! `dispersion`, `phonotactics`) a analogické změny tvarů (`uniformity`, `conservation`,
//! `teachability`, `distinctiveness`).
//!
//! Skóre je čistá funkce pěti hodnot hodnocení a popisu změny; hodnocení samo (co by změna
//! udělala se vzorkem slov kódu) dodávají [`crate::transfer::seams`], protože stojí na bance
//! tvarů s tabulkami procesů a na morfologickém indexu kódů. Skupina, ke které změna vůbec
//! nedolehla, se nehodnotí; hodnocení, které chybí, dá nulové skóre.
//!
//! Pět hodnot procesu: `[pokrytí, splynutí, krátká slova, příznakovost, rozptyl vokálů]`.
//! Pět hodnot tvaru: `[zisk, frekvence, splynutí před, splynutí po, 0]` (příznaky jako 0/1).

use crate::model::lexicon::{ProcessDef, Stress};
use crate::parameters::Parameters;

/// Hodnocení jedné buňky (viz popis modulu).
pub type Assessment = [f64; 5];

/// Nejvýš tolik vzorku se nedrží; viz seams. Počet hodnot hodnocení.
pub const VALUES: usize = 5;

/// Hodnocení řádku: buňky (sloupce osy), kam změna dolehla, a jejich hodnocení.
pub struct RowAssessment {
    /// Slot varianty „změna“ v řádku.
    pub slot: usize,
    pub columns: Vec<usize>,
    pub values: Vec<Option<Assessment>>,
}

/// Příznak: redukce v nepřízvučné pozici (síla přízvuku skupiny zesiluje úsporu).
pub fn reductive_unstressed(process: &ProcessDef) -> bool {
    process.reductive && process.stress == Stress::Unstressed
}

pub fn apocope(process: &ProcessDef) -> bool {
    process.family == "apocope"
}

/// Skóre procesu v jedné skupině (bez váhy tlaku); `pressure` je číslo z `cee_core::pressures::id`.
pub fn process_score(
    pressure: u8,
    process: &ProcessDef,
    values: &Assessment,
    strong_stress: bool,
    coda_share: f64,
    params: &Parameters,
) -> f64 {
    use cee_core::pressures::id;
    let [_, merge, short, marked, dispersion] = *values;
    match pressure {
        id::ARTICULATION => {
            if reductive_unstressed(process) && strong_stress {
                process.ease * params.stress_strength_multiplier
            } else {
                process.ease
            }
        }
        id::CLARITY => (process.clarity - params.clarity_short_factor * short).clamp(-1.0, 1.0),
        id::DISPERSION => (params.dispersion_factor * dispersion).clamp(-1.0, 1.0),
        id::FUNCTIONAL_LOAD => {
            let scaled = params.functional_load_scale * merge;
            // `min(1.0, NaN)` v Pythonu vrací první argument; porovnání zachová totéž.
            -(if scaled < 1.0 { scaled } else { 1.0 })
        }
        id::PHONOTACTICS => {
            let mut delta = marked;
            if apocope(process) && params.coda_tolerance_scale > 0.0 {
                delta *= (1.0 - params.coda_tolerance_scale * coda_share).clamp(0.0, 1.0);
            }
            -delta.clamp(-1.0, 1.0)
        }
        _ => 0.0,
    }
}

/// Skóre analogické změny tvaru v jedné skupině (bez váhy tlaku).
pub fn form_score(
    pressure: u8,
    level: bool,
    lexeme_wide: bool,
    values: &Assessment,
    l2_share: f64,
) -> f64 {
    use cee_core::pressures::id;
    let [gain, frequency, before, after, _] = *values;
    match pressure {
        id::UNIFORMITY => {
            if level {
                0.4
            } else {
                0.35 * gain
            }
        }
        id::CONSERVATION => {
            if lexeme_wide {
                0.0
            } else {
                -0.6 * (2.0 * frequency - 1.0)
            }
        }
        id::TEACHABILITY => {
            if lexeme_wide {
                0.0
            } else {
                l2_share
            }
        }
        id::DISTINCTIVENESS => match (before != 0.0, after != 0.0) {
            (false, true) => -0.8,
            (true, false) => 0.6,
            _ => 0.0,
        },
        _ => 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::lexicon::Operation;
    use crate::segments::Pattern;
    use cee_core::pressures::id;

    fn process(reductive: bool, stress: Stress, family: &str) -> ProcessDef {
        ProcessDef {
            family: family.into(),
            target: Pattern {
                key: String::new(),
                mask: vec![],
            },
            operation: Operation::Delete,
            changes: vec![],
            segment: None,
            left: None,
            right: None,
            right2: None,
            stress,
            medial: false,
            ease: 0.5,
            clarity: -0.4,
            reductive,
            label: String::new(),
            allow: vec![],
            tone: None,
        }
    }

    #[test]
    fn zvukove_tlaky_podle_vzorcu() {
        let params = Parameters::default();
        let p = process(true, Stress::Unstressed, "reduction");
        let v = [0.3, 0.1, 0.2, 0.5, 0.05];
        assert_eq!(
            process_score(id::ARTICULATION, &p, &v, false, 0.0, &params),
            0.5
        );
        assert_eq!(
            process_score(id::ARTICULATION, &p, &v, true, 0.0, &params),
            0.5 * params.stress_strength_multiplier
        );
        let clarity = process_score(id::CLARITY, &p, &v, false, 0.0, &params);
        assert!((clarity - (-0.4 - params.clarity_short_factor * 0.2)).abs() < 1e-15);
        assert!(
            (process_score(id::FUNCTIONAL_LOAD, &p, &v, false, 0.0, &params)
                + params.functional_load_scale * 0.1)
                .abs()
                < 1e-15
        );
        let saturated = [0.3, 10.0, 0.0, 0.0, 0.0];
        assert_eq!(
            process_score(id::FUNCTIONAL_LOAD, &p, &saturated, false, 0.0, &params),
            -1.0
        );
        assert_eq!(
            process_score(id::DISPERSION, &p, &v, false, 0.0, &params),
            0.2
        );
        assert_eq!(
            process_score(id::PHONOTACTICS, &p, &v, false, 0.0, &params),
            -0.5
        );
    }

    #[test]
    fn fonotaktika_apokopy_se_zmirnuje_podilem_koncovych_souhlasek() {
        let params = Parameters {
            coda_tolerance_scale: 1.0,
            ..Parameters::default()
        };
        let p = process(false, Stress::Any, "apocope");
        let v = [0.3, 0.0, 0.0, 0.8, 0.0];
        let score = process_score(id::PHONOTACTICS, &p, &v, false, 0.5, &params);
        assert!((score + 0.4).abs() < 1e-15);
    }

    #[test]
    fn tvarove_tlaky_podle_vzorcu() {
        let v = [0.4, 0.9, 0.0, 1.0, 0.0];
        assert_eq!(form_score(id::UNIFORMITY, true, false, &v, 0.0), 0.4);
        assert!((form_score(id::UNIFORMITY, false, false, &v, 0.0) - 0.14).abs() < 1e-15);
        assert!((form_score(id::CONSERVATION, false, false, &v, 0.0) + 0.48).abs() < 1e-15);
        assert_eq!(form_score(id::CONSERVATION, false, true, &v, 0.0), 0.0);
        assert_eq!(form_score(id::TEACHABILITY, false, false, &v, 0.25), 0.25);
        assert_eq!(form_score(id::DISTINCTIVENESS, false, false, &v, 0.0), -0.8);
        let repaired = [0.0, 0.0, 1.0, 0.0, 0.0];
        assert_eq!(
            form_score(id::DISTINCTIVENESS, false, false, &repaired, 0.0),
            0.6
        );
    }
}

//! Statistika zpevněných bran (zrcadlo `tests/v2/gate_checks.py`, pravidlo k z N podle Wilsona
//! v `docs/engine-v2/09-zpevneni-bran.md`).

/// Kritická hodnota standardního normálního rozdělení pro 95% oboustranný interval.
pub const Z_95: f64 = 1.959_963_984_540_054;

/// Wilsonův skórový interval spolehlivosti binomického podílu, meze oříznuté do `[0, 1]`.
pub fn wilson_interval(successes: u32, total: u32) -> Result<(f64, f64), String> {
    if total == 0 {
        return Err("Celkový počet pokusů musí být kladný.".into());
    }
    if successes > total {
        return Err(format!(
            "Počet úspěchů ({successes}) musí ležet v rozsahu 0..{total}."
        ));
    }
    let z2 = Z_95 * Z_95;
    let n = f64::from(total);
    let denom = n + z2;
    let p = f64::from(successes) / n;
    let center = f64::from(successes) + z2 / 2.0;
    let spread = Z_95 * (n * p * (1.0 - p) + z2 / 4.0).sqrt();
    Ok((
        ((center - spread) / denom).clamp(0.0, 1.0),
        ((center + spread) / denom).clamp(0.0, 1.0),
    ))
}

/// Přesná pravděpodobnost `P(Bin(n, p) < k)`.
pub fn binomial_cdf_lt(k: i64, n: u32, p: f64) -> f64 {
    if k <= 0 {
        return 0.0;
    }
    if k > i64::from(n) {
        return 1.0;
    }
    if p == 0.0 {
        return 1.0;
    }
    if p == 1.0 {
        return 0.0;
    }
    let mut total = 0.0;
    for j in 0..k as u32 {
        total += combinations(n, j) * p.powi(j as i32) * (1.0 - p).powi((n - j) as i32);
    }
    total.clamp(0.0, 1.0)
}

fn combinations(n: u32, k: u32) -> f64 {
    let k = k.min(n - k.min(n));
    let mut result: u128 = 1;
    for step in 0..u128::from(k) {
        result = result * (u128::from(n) - step) / (step + 1);
    }
    result as f64
}

/// Největší `k` v `0..=n`, pro které `P(Bin(n, p_lower) < k) <= alpha`.
pub fn threshold_k(n: u32, p_lower: f64, alpha: f64) -> u32 {
    for k in (0..=n).rev() {
        if binomial_cdf_lt(i64::from(k), n, p_lower) <= alpha {
            return k;
        }
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wilson_sedi_s_tabulkou_zpevneni() {
        let (low, high) = wilson_interval(19, 20).unwrap();
        assert!((low - 0.764).abs() < 5e-4 && (high - 0.991).abs() < 5e-4);
        let (low, _) = wilson_interval(20, 20).unwrap();
        assert!((low - 0.839).abs() < 5e-4);
        let (low, high) = wilson_interval(8, 20).unwrap();
        assert!((low - 0.219).abs() < 5e-4 && (high - 0.613).abs() < 5e-4);
        assert!(wilson_interval(3, 2).is_err() && wilson_interval(0, 0).is_err());
    }

    #[test]
    fn prahy_k_sedi_s_dokumentem() {
        // N = 10: 20/20 dává k = 5, 19/20 dává k = 4, 15/20 dává k = 2, 11/20 dává k = 0.
        let k = |s| threshold_k(10, wilson_interval(s, 20).unwrap().0, 0.01);
        assert_eq!((k(20), k(19), k(15), k(11)), (5, 4, 2, 0));
        // N = 12 pro 11/20 dává k = 1, N = 19 pro 8/20 dává k = 1.
        assert_eq!(threshold_k(12, wilson_interval(11, 20).unwrap().0, 0.01), 1);
        assert_eq!(threshold_k(19, wilson_interval(8, 20).unwrap().0, 0.01), 1);
    }

    #[test]
    fn binomicka_distribuce_ma_okrajove_pripady() {
        assert_eq!(binomial_cdf_lt(0, 5, 0.5), 0.0);
        assert_eq!(binomial_cdf_lt(6, 5, 0.5), 1.0);
        assert!((binomial_cdf_lt(1, 3, 0.5) - 0.125).abs() < 1e-12);
        assert_eq!(binomial_cdf_lt(2, 4, 0.0), 1.0);
        assert_eq!(binomial_cdf_lt(2, 4, 1.0), 0.0);
    }

    #[test]
    fn zarazeni_mir() {}
}

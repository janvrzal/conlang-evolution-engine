//! Stav přenosu a tlaků (R1a).
//!
//! Sem patří odvozené keše přenosu: připravené vstupy kroku (`transmission.prepare`),
//! popis řádků pro tlaky u bloku fondů, mixing matrix. Vše odvozené se do kontrolního
//! bodu nemusí ukládat (`#[serde(skip)]`) a po obnově se postaví znovu.

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct TransferState {
    /// Počet kroků přenosu, které svět provedl (jen pro ladění a statistiky).
    pub steps: u64,
}

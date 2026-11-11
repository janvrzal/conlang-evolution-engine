//! Příznaky morfémů (bitové pole podle čísla morfému).
//!
//! Fronty procesů kódu si pamatují, které morfémy čekají (`queued`) a které si změnu už
//! zapsaly (`done`). Dřív to bylo pole bajtů 0/1 dlouhé jako nejvyšší číslo morfému, pro každý
//! proces každé skupiny: v Evropě při realistickém tempu přes 1 GB. Bitové pole je osmkrát menší
//! a čte se stejně.

/// Bitové pole příznaků; neuvedené (za koncem) je `false`.
#[derive(Clone, Debug, Default)]
pub struct Flags {
    words: Vec<u64>,
}

/// Prázdné příznaky (pro cíle bez fronty).
pub static EMPTY: Flags = Flags { words: Vec::new() };

impl Flags {
    pub fn get(&self, index: usize) -> bool {
        self.words
            .get(index / 64)
            .is_some_and(|word| word >> (index % 64) & 1 == 1)
    }

    /// Nastaví příznak; pole roste jen kvůli nastavení na `true`.
    pub fn set(&mut self, index: usize, on: bool) {
        let at = index / 64;
        if at >= self.words.len() {
            if !on {
                return;
            }
            self.words.resize(at + 1, 0);
        }
        let bit = 1_u64 << (index % 64);
        if on {
            self.words[at] |= bit;
        } else {
            self.words[at] &= !bit;
        }
    }

    pub fn count(&self) -> usize {
        self.words
            .iter()
            .map(|word| word.count_ones() as usize)
            .sum()
    }

    pub fn any(&self) -> bool {
        self.words.iter().any(|&word| word != 0)
    }

    /// Z bajtů 0/1 (dřívější podoba, kontrolní body).
    pub fn from_bytes(bytes: &[u8]) -> Flags {
        let mut flags = Flags::default();
        for (index, &byte) in bytes.iter().enumerate() {
            if byte == 1 {
                flags.set(index, true);
            }
        }
        flags
    }

    /// Bajty 0/1 po nejvyšší nastavený příznak (podoba kontrolního bodu).
    pub fn to_bytes(&self) -> Vec<u8> {
        let last = (0..self.words.len() * 64)
            .rev()
            .find(|&index| self.get(index));
        match last {
            None => Vec::new(),
            Some(last) => (0..=last).map(|index| u8::from(self.get(index))).collect(),
        }
    }

    /// Čísla nastavených příznaků vzestupně (podoba kontrolního bodu: proces změní desítky
    /// slov z desítek tisíc morfémů, bajt na morfém by v Talveře dal 336 MB na bod).
    pub fn indices(&self) -> Vec<u32> {
        let mut out = Vec::with_capacity(self.count());
        for (at, &word) in self.words.iter().enumerate() {
            let mut rest = word;
            while rest != 0 {
                let bit = rest.trailing_zeros() as usize;
                out.push((at * 64 + bit) as u32);
                rest &= rest - 1;
            }
        }
        out
    }

    /// Z čísel nastavených příznaků (opak [`Flags::indices`]).
    pub fn from_indices(indices: &[u32]) -> Flags {
        let mut flags = Flags::default();
        for &index in indices {
            flags.set(index as usize, true);
        }
        flags
    }

    /// Bajty v paměti.
    pub fn nbytes(&self) -> usize {
        self.words.capacity() * 8
    }
}

impl PartialEq for Flags {
    /// Shoda nastavených příznaků (nulová slova na konci nevadí).
    fn eq(&self, other: &Self) -> bool {
        let (short, long) = if self.words.len() <= other.words.len() {
            (&self.words, &other.words)
        } else {
            (&other.words, &self.words)
        };
        short == &long[..short.len()] && long[short.len()..].iter().all(|&word| word == 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn priznaky_jako_bajty() {
        let mut flags = Flags::default();
        flags.set(3, true);
        flags.set(130, true);
        flags.set(500, false);
        assert!(flags.get(3) && flags.get(130) && !flags.get(4) && !flags.get(9999));
        assert_eq!(flags.count(), 2);
        let bytes = flags.to_bytes();
        assert_eq!(bytes.len(), 131);
        assert_eq!(Flags::from_bytes(&bytes), flags);
        flags.set(130, false);
        assert_eq!(flags, Flags::from_bytes(&[0, 0, 0, 1]));
        assert_eq!(Flags::from_indices(&flags.indices()), flags);
        assert!(flags.any() && !EMPTY.any());
    }
}

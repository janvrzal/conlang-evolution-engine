//! Síť vazeb mezi skupinami: mapa a řídká matice CSR (zrcadlo `world.Link`, `tables.LinkTable`).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::ids::GroupId;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LinkKind {
    Strong,
    Weak,
}

impl LinkKind {
    pub fn name(self) -> &'static str {
        match self {
            LinkKind::Strong => "strong",
            LinkKind::Weak => "weak",
        }
    }
}

/// Směrovaná vazba: `source` se učí od `target` se sílou `strength`.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Link {
    pub strength: f64,
    pub kind: LinkKind,
}

/// Vazby jako řídká matice po řádcích (zdroj) se sloupci (cíl) seřazenými podle čísla.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct LinkCsr {
    pub row_start: Vec<u32>,
    pub target: Vec<GroupId>,
    pub strength: Vec<f64>,
    pub kind: Vec<LinkKind>,
}

impl LinkCsr {
    /// Cíle a síly vazeb zdroje.
    pub fn row(&self, source: GroupId) -> (&[GroupId], &[f64]) {
        let (low, high) = match self.row_start.get(source.index()..=source.index() + 1) {
            Some(range) => (range[0] as usize, range[1] as usize),
            None => (0, 0),
        };
        (&self.target[low..high], &self.strength[low..high])
    }
}

/// Mapa vazeb `(zdroj, cíl)` → vazba; CSR se přepočítá jen po změně.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Links {
    map: BTreeMap<(GroupId, GroupId), Link>,
    #[serde(skip)]
    csr: Option<LinkCsr>,
}

impl Links {
    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }

    pub fn get(&self, source: GroupId, target: GroupId) -> Option<&Link> {
        self.map.get(&(source, target))
    }

    pub fn set(&mut self, source: GroupId, target: GroupId, link: Link) {
        self.map.insert((source, target), link);
        self.csr = None;
    }

    pub fn remove_group(&mut self, group: GroupId) {
        self.map.retain(|&(a, b), _| a != group && b != group);
        self.csr = None;
    }

    /// Vazby podle čísel skupin (zdroj, cíl).
    pub fn iter(&self) -> impl Iterator<Item = (&(GroupId, GroupId), &Link)> {
        self.map.iter()
    }

    /// Vazby zdroje podle čísla cíle.
    pub fn from(&self, source: GroupId) -> impl Iterator<Item = (GroupId, &Link)> {
        self.map.range((source, GroupId(0))..=(source, GroupId(u32::MAX))).map(|(&(_, t), l)| (t, l))
    }

    /// Řídká matice vazeb pro `groups` skupin (přepočítá se jen po změně vazeb).
    pub fn csr(&mut self, groups: usize) -> &LinkCsr {
        if self.csr.as_ref().map_or(true, |c| c.row_start.len() != groups + 1) {
            let mut csr = LinkCsr { row_start: vec![0; groups + 1], ..LinkCsr::default() };
            for (&(source, target), link) in &self.map {
                if source.index() < groups {
                    csr.row_start[source.index() + 1] += 1;
                    csr.target.push(target);
                    csr.strength.push(link.strength);
                    csr.kind.push(link.kind);
                }
            }
            for row in 0..groups {
                csr.row_start[row + 1] += csr.row_start[row];
            }
            self.csr = Some(csr);
        }
        self.csr.as_ref().expect("CSR")
    }
}

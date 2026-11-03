//! Skupiny mluvčích jako sloupce (zrcadlo `world.SpeechGroup`).
//!
//! Základní jednotka simulace: lidé na jednom místě s vlastními kódy. Pole jsou
//! sloupce podle čísla skupiny z registru (`GroupId`); skupina se neodebírá z polí,
//! jen se označí `alive = false` (čísla se nikdy nepřečíslovávají). Kanonické pořadí
//! průchodu (podle jmen) dává [`Groups::sorted`].

use serde::{Deserialize, Serialize};

use crate::ids::{ConceptId, GroupId, Numbering, TerritoryId};
use crate::model::code::Code;

/// Kde skupina kód užívá.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Domain {
    Home,
    Public,
}

impl Domain {
    pub fn name(self) -> &'static str {
        match self {
            Domain::Home => "home",
            Domain::Public => "public",
        }
    }
}

/// Vstup pro přidání skupiny; výchozí hodnoty jsou jako v Pythonu.
pub struct GroupInit {
    pub id: String,
    pub territory: TerritoryId,
    pub population: u32,
    pub codes: Vec<Code>,
    pub generation_years: f64,
    pub prestige: f64,
    pub openness: f64,
    pub literacy: f64,
    pub schooling: f64,
    pub taboo: Vec<ConceptId>,
    pub aggregate: bool,
    pub internal_diversity: f64,
    pub community: GroupId,
    pub immigration: f64,
    pub transmitted: bool,
    pub written: bool,
    pub standard: GroupId,
    pub liturgy: GroupId,
    pub devotion: f64,
    pub loyalty: f64,
    pub domain: Domain,
    pub home_pull: f64,
    pub preserved: bool,
    pub revival: f64,
    pub elite: bool,
}

impl GroupInit {
    pub fn new(id: &str, territory: TerritoryId, population: u32, codes: Vec<Code>) -> GroupInit {
        GroupInit {
            id: id.to_owned(),
            territory,
            population,
            codes,
            generation_years: 25.0,
            prestige: 0.5,
            openness: 0.1,
            literacy: 0.0,
            schooling: 0.0,
            taboo: Vec::new(),
            aggregate: false,
            internal_diversity: 0.0,
            community: GroupId::NONE,
            immigration: 0.0,
            transmitted: true,
            written: false,
            standard: GroupId::NONE,
            liturgy: GroupId::NONE,
            devotion: 0.0,
            loyalty: 0.0,
            domain: Domain::Home,
            home_pull: 0.0,
            preserved: false,
            revival: 0.0,
            elite: false,
        }
    }

    /// Kontrola jako `SpeechGroup.__post_init__`.
    pub fn validate(&self) -> Result<(), String> {
        if self.population == 0 {
            return Err(format!("Skupina '{}' musí mít kladnou populaci.", self.id));
        }
        if self.generation_years <= 0.0 {
            return Err(format!(
                "Skupina '{}' musí mít kladnou délku generace.",
                self.id
            ));
        }
        if !(0.0..=1.0).contains(&self.openness) {
            return Err(format!(
                "Otevřenost skupiny '{}' musí ležet v intervalu 0 až 1.",
                self.id
            ));
        }
        if self.prestige < 0.0 {
            return Err(format!("Prestiž skupiny '{}' nesmí být záporná.", self.id));
        }
        if self.codes.is_empty() {
            return Err(format!("Skupina '{}' musí mít alespoň jeden kód.", self.id));
        }
        Ok(())
    }
}

/// Sloupce skupin; vše podle čísla skupiny.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct Groups {
    pub alive: Vec<bool>,
    pub territory: Vec<TerritoryId>,
    pub population: Vec<u32>,
    pub generation_years: Vec<f64>,
    pub prestige: Vec<f64>,
    pub openness: Vec<f64>,
    pub literacy: Vec<f64>,
    pub schooling: Vec<f64>,
    pub taboo: Vec<Vec<ConceptId>>,
    pub aggregate: Vec<bool>,
    pub internal_diversity: Vec<f64>,
    /// Společná komunita víc skupin (`NONE` = skupina je komunitou sama).
    pub community: Vec<GroupId>,
    pub immigration: Vec<f64>,
    pub transmitted: Vec<bool>,
    pub written: Vec<bool>,
    pub standard: Vec<GroupId>,
    pub liturgy: Vec<GroupId>,
    pub devotion: Vec<f64>,
    pub loyalty: Vec<f64>,
    pub domain: Vec<Domain>,
    pub home_pull: Vec<f64>,
    pub preserved: Vec<bool>,
    pub revival: Vec<f64>,
    pub elite: Vec<bool>,
    /// Kódy skupiny; první je hlavní (`main_code`).
    pub codes: Vec<Vec<Code>>,
}

impl Groups {
    /// Počet obsazených čísel (včetně odebraných skupin).
    pub fn len(&self) -> usize {
        self.alive.len()
    }

    pub fn is_empty(&self) -> bool {
        self.count() == 0
    }

    /// Počet žijících skupin.
    pub fn count(&self) -> usize {
        self.alive.iter().filter(|&&a| a).count()
    }

    pub fn contains(&self, id: GroupId) -> bool {
        self.alive.get(id.index()).copied().unwrap_or(false)
    }

    /// Uloží skupinu pod číslem z registru.
    pub fn store(&mut self, id: GroupId, init: GroupInit) -> Result<(), String> {
        init.validate()?;
        let at = id.index();
        if self.contains(id) {
            return Err(format!("Skupina '{}' už existuje.", init.id));
        }
        while self.alive.len() <= at {
            self.alive.push(false);
            self.territory.push(TerritoryId::NONE);
            self.population.push(0);
            self.generation_years.push(25.0);
            self.prestige.push(0.5);
            self.openness.push(0.1);
            self.literacy.push(0.0);
            self.schooling.push(0.0);
            self.taboo.push(Vec::new());
            self.aggregate.push(false);
            self.internal_diversity.push(0.0);
            self.community.push(GroupId::NONE);
            self.immigration.push(0.0);
            self.transmitted.push(true);
            self.written.push(false);
            self.standard.push(GroupId::NONE);
            self.liturgy.push(GroupId::NONE);
            self.devotion.push(0.0);
            self.loyalty.push(0.0);
            self.domain.push(Domain::Home);
            self.home_pull.push(0.0);
            self.preserved.push(false);
            self.revival.push(0.0);
            self.elite.push(false);
            self.codes.push(Vec::new());
        }
        self.alive[at] = true;
        self.territory[at] = init.territory;
        self.population[at] = init.population;
        self.generation_years[at] = init.generation_years;
        self.prestige[at] = init.prestige;
        self.openness[at] = init.openness;
        self.literacy[at] = init.literacy;
        self.schooling[at] = init.schooling;
        self.taboo[at] = init.taboo;
        self.aggregate[at] = init.aggregate;
        self.internal_diversity[at] = init.internal_diversity;
        self.community[at] = init.community;
        self.immigration[at] = init.immigration;
        self.transmitted[at] = init.transmitted;
        self.written[at] = init.written;
        self.standard[at] = init.standard;
        self.liturgy[at] = init.liturgy;
        self.devotion[at] = init.devotion;
        self.loyalty[at] = init.loyalty;
        self.domain[at] = init.domain;
        self.home_pull[at] = init.home_pull;
        self.preserved[at] = init.preserved;
        self.revival[at] = init.revival;
        self.elite[at] = init.elite;
        self.codes[at] = init.codes;
        Ok(())
    }

    /// Označí skupinu za odebranou a vrátí její kódy.
    pub fn remove(&mut self, id: GroupId) -> Vec<Code> {
        self.alive[id.index()] = false;
        std::mem::take(&mut self.codes[id.index()])
    }

    pub fn main_code(&self, id: GroupId) -> &Code {
        &self.codes[id.index()][0]
    }

    pub fn main_code_mut(&mut self, id: GroupId) -> &mut Code {
        &mut self.codes[id.index()][0]
    }

    /// Žijící skupiny v kanonickém pořadí (podle jmen) – `World.group_ids()`.
    pub fn sorted(&self, names: &Numbering) -> Vec<GroupId> {
        let mut ids: Vec<GroupId> = (0..self.len())
            .filter(|&i| self.alive[i])
            .map(GroupId::new)
            .collect();
        ids.sort_by(|a, b| names.name(a.0).cmp(names.name(b.0)));
        ids
    }

    /// Podíl skupiny, který se za krok učí jazyk znovu (0 bez dětí): `World.renewal`.
    pub fn renewal(&self, id: GroupId, dt: f64) -> f64 {
        let at = id.index();
        if !self.transmitted[at] || (self.written[at] && self.openness[at] == 0.0) {
            return 0.0;
        }
        (dt / self.generation_years[at]).min(1.0)
    }

    /// Nejkratší délka generace žijících skupin; krok simulace nesmí být delší.
    pub fn generation_ceiling(&self) -> f64 {
        (0..self.len())
            .filter(|&i| self.alive[i])
            .map(|i| self.generation_years[i])
            .fold(f64::INFINITY, f64::min)
    }
}

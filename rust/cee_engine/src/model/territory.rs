//! Strom území (zrcadlo `world.Territory`).

use serde::{Deserialize, Serialize};

use crate::ids::{LanguageId, TerritoryId};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TerritoryLevel {
    World,
    Continent,
    Region,
    Area,
    Settlement,
}

impl TerritoryLevel {
    pub fn name(self) -> &'static str {
        match self {
            TerritoryLevel::World => "world",
            TerritoryLevel::Continent => "continent",
            TerritoryLevel::Region => "region",
            TerritoryLevel::Area => "area",
            TerritoryLevel::Settlement => "settlement",
        }
    }
}

/// Uzel stromu území. Bez potomků je území „nerozepsané“.
fn full_permeability() -> f64 {
    1.0
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Territory {
    pub level: TerritoryLevel,
    pub parent: TerritoryId,
    pub children: Vec<TerritoryId>,
    /// Poloha těžiště v mapových jednotkách (km).
    pub position: Option<(f64, f64)>,
    pub refined_from_year: Option<f64>,
    /// Terén (klíč `Parameters::terrain_access`); popis krajiny pro jména a mapu.
    pub terrain: String,
    /// Prostupnost 0–1: 1 = krajina, přes kterou se snadno chodí a obchoduje, 0 = úplná izolace
    /// (žádný kontakt přes hranici). Násobí vazby přes hranici regionu a dosah státu (dok. 31).
    #[serde(default = "full_permeability")]
    pub permeability: f64,
    /// Původní jazyk území (linie), pokud ho scénář zná.
    pub native_language: LanguageId,
    /// Město: úmrtnost navíc proti venkovu za generaci, kterou doplní příliv z vesnic regionu
    /// (Wrigley 1967); 0 = vesnice (dok. 27).
    #[serde(default)]
    pub urban: f64,
    /// Velikost města jako násobek vesnice (pro normalizaci kohorty a populačních tlaků);
    /// 0 = použije se výchozí `Parameters::city_size`.
    #[serde(default)]
    pub city_size: f64,
    /// Rok, kdy sídlo založila migrace (osadníci); `None` u sídel scénáře (dok. 30).
    #[serde(default)]
    pub settled: Option<f64>,
}

impl Territory {
    pub fn new(level: TerritoryLevel) -> Territory {
        Territory {
            level,
            parent: TerritoryId::NONE,
            children: Vec::new(),
            position: None,
            refined_from_year: None,
            terrain: "plain".into(),
            permeability: 1.0,
            native_language: LanguageId::NONE,
            urban: 0.0,
            city_size: 0.0,
            settled: None,
        }
    }
}

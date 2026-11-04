//! Data enginu vložená do binárky.
//!
//! Soubory z `src/cee/data/` se vkládají přes `include_str!` při sestavení. Důvod:
//! binárka `cee` a vazba pro server jsou tak samostatné (žádná cesta k datům za
//! běhu, žádná shoda verzí dat a kódu) a čtení je bez I/O. Cena je velikost
//! binárky (asi 3 MB) a nutnost sestavit znovu po změně dat; pro testy a pokusy
//! s jinými daty slouží `SegmentTable::from_json` a podobné funkce, které berou
//! text zvenku.
//!
//! Tabulka hlásek (`v2_segments.json`), katalog gramatiky (`v2_grammar.json`)
//! a výchozí pojmy (`v2_defaults.json`) vyrábí `scripts/export_v2_data.py`
//! z Pythonu (PanPhon, licence MIT, atribuce v hlavičce souboru a v dokumentaci).

pub const SEGMENTS_JSON: &str = include_str!("../../../src/cee/data/v2_segments.json");
pub const GRAMMAR_JSON: &str = include_str!("../../../src/cee/data/v2_grammar.json");
pub const DEFAULTS_JSON: &str = include_str!("../../../src/cee/data/v2_defaults.json");
pub const CONCEPTS_JSON: &str = include_str!("../../../src/cee/data/v2_concepts.json");
pub const CONCEPT_FREQUENCIES_JSON: &str =
    include_str!("../../../src/cee/data/v2_concept_frequencies.json");
pub const CORE_SEMANTICS_JSON: &str = include_str!("../../../src/cee/data/v2_core_semantics.json");
pub const CATALOG_SEMANTICS_JSON: &str =
    include_str!("../../../src/cee/data/v2_catalog_semantics.json");
pub const STANDING_VARIATION_JSON: &str =
    include_str!("../../../src/cee/data/v2_standing_variation.json");

/// Metaparametry (výchozí hodnoty, druhy, popisy, skupiny, meze); jediný zdroj pro Rust,
/// Python i UI. Formát popisuje `docs/engine-v2/19-engine-v-rustu.md`, oddíl „Metaparametry“.
pub const PARAMETERS_JSON: &str = include_str!("../../../src/cee/data/v2_parameters.json");

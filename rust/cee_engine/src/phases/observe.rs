//! Fáze 6: pozorování dialektů a jazyků (R1d).
//!
//! **Vstup:** `World` (kódy, repertoáry, živé fondy), prahy z `SimulationConfig`,
//! sledování linií (`SocietyState::lineages`). **Výstup:** snímek v `History::snapshots`
//! a události `language_emerged`, `language_split`, `language_ended` v historii.
//! Zrcadlo `observe.observe`.
//!
//! Do dialektů a jazyků se počítá jen řeč z domova: psaný kód nemá mluvčí a kód trhu,
//! úřadu nebo školy (veřejná doména) je druhý jazyk. Shluky počítá jádro
//! (`observe::observe_world`, průměrná vazba mezi sousedícími shluky, lineárně v počtu
//! skupin); linie jazyků mezi snímky páruje `LineageTracker`.

use std::collections::BTreeMap;

use serde_json::Value;

use crate::history::Snapshot;
use crate::observe::{code_distances, observe_world};
use crate::phases::StepContext;

/// Zapíše snímek pozorování a události linií.
pub fn run(ctx: &mut StepContext<'_>) -> Result<(), String> {
    let observed = observe_world(
        ctx.world,
        &ctx.world.society.lineages,
        ctx.config.dialect_threshold,
        ctx.config.language_threshold,
    );
    let names: Vec<String> = observed
        .spoken
        .iter()
        .map(|&g| ctx.world.group_name(g).to_owned())
        .collect();
    let cluster_names = |clusters: &[Vec<usize>]| -> Vec<Vec<String>> {
        clusters
            .iter()
            .map(|cluster| cluster.iter().map(|&at| names[at].clone()).collect())
            .collect()
    };
    let dialects = cluster_names(&observed.dialects);
    let language_clusters = cluster_names(&observed.languages);
    let update = ctx
        .world
        .society
        .lineages
        .update(&language_clusters, ctx.tick);
    let distances = ctx.config.keep_distances.then(|| {
        // Matice mluvených skupin z matice všech živých skupin.
        let all = code_distances(ctx.world);
        let live = ctx.world.live.group_ids.len();
        let position: BTreeMap<_, _> = ctx
            .world
            .live
            .group_ids
            .iter()
            .enumerate()
            .map(|(at, &g)| (g, at))
            .collect();
        let at: Vec<usize> = observed.spoken.iter().map(|g| position[g]).collect();
        let mut out = Vec::with_capacity(at.len() * at.len());
        for &first in &at {
            for &second in &at {
                out.push(all[first * live + second]);
            }
        }
        out
    });
    ctx.history.snapshots.push(Snapshot {
        tick: ctx.tick,
        year: ctx.year,
        dialects,
        languages: update.languages,
        group_ids: if distances.is_some() {
            names
        } else {
            Vec::new()
        },
        distances,
    });
    for event in update.events {
        let Value::Object(mut payload) = event else {
            continue;
        };
        let kind = payload
            .remove("kind")
            .and_then(|k| k.as_str().map(str::to_owned))
            .ok_or("událost linie bez druhu")?;
        ctx.history
            .record(&kind, ctx.tick, ctx.year, Value::Object(payload));
    }
    Ok(())
}

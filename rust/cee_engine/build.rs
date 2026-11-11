//! Otisk sestavení enginu (`CEE_ENGINE_BUILD`): FNV-1a nad zdrojem enginu, jádra a vloženými
//! daty. Kontrolní bod z jiného sestavení se nenačte (jiné rozložení struktur nebo jiná
//! dynamika); „co kdyby“ pak počítá od začátku.

use std::path::{Path, PathBuf};

fn files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            files(&path, out);
        } else if matches!(
            path.extension().and_then(|e| e.to_str()),
            Some("rs" | "json" | "toml")
        ) {
            out.push(path);
        }
    }
}

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let dirs = [
        root.join("src"),
        root.join("../cee_core/src"),
        root.join("../../src/cee/data"),
    ];
    let mut all = Vec::new();
    for dir in &dirs {
        println!("cargo:rerun-if-changed={}", dir.display());
        files(dir, &mut all);
    }
    all.push(root.join("Cargo.toml"));
    all.sort();
    let mut hash: u64 = 0xcbf29ce484222325;
    for path in &all {
        let name = path
            .strip_prefix(root)
            .unwrap_or(path)
            .to_string_lossy()
            .into_owned();
        for byte in name.bytes().chain(std::fs::read(path).unwrap_or_default()) {
            hash ^= u64::from(byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }
    println!("cargo:rustc-env=CEE_ENGINE_BUILD={hash:016x}");
}

# Rust: jádra a engine v2

Pracovní prostor Cargo se třemi crates. Přehled architektury a rozhraní fází:
[`docs/engine-v2/19-engine-v-rustu.md`](../docs/engine-v2/19-engine-v-rustu.md).

| crate | obsah |
|---|---|
| `cee_core` | jádra výpočtů (banka tvarů, procesy, přenos, tlaky, indexy). Vazba na Python (PyO3) je za feature `python` (výchozí zapnutá; maturin ji zapíná sám). Bez ní je to čistá knihovna. |
| `cee_engine` | engine v2 celý v Rustu (svět, náhoda, fáze kroku, export, kontrolní body) a binárka `cee`. Čistý Rust, na `cee_core` závisí bez feature `python`. |
| `cee_py` | tenká vazba PyO3 nad `cee_engine` pro server (modul `cee_engine_py`): běh ze `WorldSpec`, krokování bez GIL, zrušení, snímky a export `cee-v2/1`. Mimo `default-members`. |

Kořen `rust/` má `default-members = ["cee_engine"]`, takže `cargo test` a `cargo clippy` v `rust/` stavějí
čistý Rust bez PyO3.

## Prostředí

```sh
export PATH=$HOME/.cargo/bin:$PATH CARGO_BUILD_JOBS=4
```

## Čistý Rust (`cee_engine`)

```sh
cd rust
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test                                  # vektory z Pythonu, kostra, vlákna, kontrolní body
cargo run -p cee_engine --bin cee -- scenarios
cargo run --release -p cee_engine --bin cee -- scenario valley-50 --until 200 -o export.json
cargo run -p cee_engine --bin cee -- export-tick0 syntax          # nebo cesta k WorldSpec .json
```

Porovnání světa v ticku 0 s Pythonem (potřebuje sestavenou binárku `rust/target/debug/cee`):

```sh
PYTHONPATH=src:. python scripts/v2_compare_tick0.py [--with-variation] [scénář | spec.json ...]
```

Data (tabulka hlásek z PanPhon, katalog gramatiky, výchozí pojmy) vyrábí jednou
`scripts/export_v2_data.py` do `src/cee/data/`; vektory pro testy
`scripts/export_v2_rust_vectors.py` do `rust/cee_engine/tests/fixtures/`.

## Rozšíření pro Python (`cee_core`, stávající Python engine)

Pracovní prostor má společný adresář `rust/target`, wheel proto vzniká v `rust/target/wheels`:

```sh
cd rust/cee_core
/Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python
cd ../..
mkdir -p rust/cee_core/target/py
/Users/janvrzal/Documents/CEE/.venv/bin/python -m pip install --no-deps --upgrade --force-reinstall \
    --target rust/cee_core/target/py rust/target/wheels/cee_core-0.1.0-cp311-cp311-macosx_11_0_arm64.whl
PYTHONPATH=src:.:rust/cee_core/target/py python scripts/v2_digests.py --quick
```

Do sdíleného prostředí (venv) se nic neinstaluje; rozšíření se hledá přes `PYTHONPATH`
(`rust/cee_core/target/py`, ten je mimo git).

## Vazba enginu pro server (`cee_py`)

Server (`src/cee/v2/runner.py`, endpointy `/api/v2`) spouští běhy v Rustu přes modul `cee_engine_py`. Sestavení a instalace
jen do adresáře mimo git, **do sdíleného venv se nic neinstaluje**:

```sh
cd rust/cee_py
/Users/janvrzal/Documents/CEE/.venv/bin/maturin build --release -i /Users/janvrzal/Documents/CEE/.venv/bin/python
cd ../..
mkdir -p rust/cee_py/target/py
/Users/janvrzal/Documents/CEE/.venv/bin/python -m pip install --no-deps --upgrade --force-reinstall \
    --target rust/cee_py/target/py rust/target/wheels/cee_engine_py-0.1.0-cp311-cp311-macosx_11_0_arm64.whl
```

Jak server vazbu najde: `runner.native()` zkusí `import cee_engine_py` a když selže, přidá do `sys.path`
`rust/cee_py/target/py` (cesta od umístění `runner.py`, tedy od kořene repozitáře). Server tedy nepotřebuje `PYTHONPATH`;
jiné umístění jde zadat přes `PYTHONPATH`. Bez sestavené vazby `POST /api/v2/runs` skončí chybou `ImportError` s odkazem sem.
Po změně Rust kódu je potřeba vazbu znovu sestavit a nainstalovat. Test vazby se bez ní přeskočí:

```sh
PYTHONPATH=src:. python -m pytest tests/test_v2_rust_binding.py tests/test_api_v2.py
```

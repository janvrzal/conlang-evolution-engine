"""Vektory z Pythonu pro testy enginu v Rustu (``rust/cee_engine/tests/fixtures``).

Náhoda (``rng.py``, numpy generátor stavby světa), rozbor zápisu IPA a změny rysů
tabulky hlásek, výchozí parametry. Rust je čte v ``tests/vectors.rs``.

Použití:  PYTHONPATH=src python scripts/export_v2_rust_vectors.py
"""

from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import numpy as np

from cee.v2.language.protoforms import protolanguage
from cee.v2.language.segments import default_table
from cee.v2.parameters import Parameters
from cee.v2.rng import Stream, generator, hash_poisson, stable_id, stable_int

OUT = Path(__file__).resolve().parents[1] / "rust" / "cee_engine" / "tests" / "fixtures"


def conv(value):
    if hasattr(value, "items"):
        return {key: conv(item) for key, item in value.items()}
    return value


def rng_vectors() -> dict:
    parts_cases = [
        ["a"], ["ab", "c"], ["a", "bc"], ["stream", 5, "innovation", 3, "v00-01", "main"],
        ["x", 0.5], ["x", 1.0], ["x", 1e-05], ["x", 1e16], ["x", 123456789.125], ["x", 0.1], ["x", -2.5],
        ["x", 1e22], ["x", 1.5e-7], ["ěščř", 7], [-3, "innovation"],
    ]
    stable = [{"parts": p, "value": str(stable_int(*p))} for p in parts_cases]
    ids = [{"prefix": "variant", "parts": ["proto", "lexical:water"], "value": stable_id("variant", "proto", "lexical:water")}]
    streams = []
    for seed, parts in [(1, ["a"]), (2, ["innovation", 3, "v00-00", "main", "x"]), (2**63 + 5, ["z"])]:
        stream = Stream(seed, *parts)
        row = {"seed": str(seed), "parts": parts, "key": str(stream.state)}
        row["u64"] = [str(stream.next_u64()) for _ in range(4)]
        row["random"] = [stream.random() for _ in range(3)]
        row["integers"] = [stream.integers(n) for n in (1, 2, 7, 1000, 2**40, 3, 5)]
        weights = [0.5, 0.0, 1.5, 3.0, 0.25]
        row["choice"] = [stream.choice(len(weights), weights) for _ in range(6)]
        row["normal"] = [stream.normal(1.0, 2.0) for _ in range(3)]
        row["poisson"] = [stream.poisson(lam) for lam in (0.3, 4.0, 29.0, 31.0, 120.5, 0.0)]
        row["state"] = str(stream.state)
        streams.append(row)
    hashed = []
    for lam in (0.01, 0.8, 5.0, 29.9, 30.0, 45.0, 200.0):
        for row_key, col_key in ((1, 2), (2**63 + 9, 77), (123456789, 987654321)):
            value = hash_poisson(
                np.array([row_key], dtype=np.uint64), np.array([col_key], dtype=np.uint64),
                np.array([lam]), pairwise=True)
            hashed.append({"row": str(row_key), "column": str(col_key), "lambda": lam, "value": int(value[0])})
    return {"stable_int": stable, "stable_id": ids, "streams": streams, "hash_poisson": hashed}


def numpy_vectors() -> dict:
    out = []
    for seed, parts in [(1, ["protolanguage"]), (2, ["protolanguage"]), (2**64 - 1, ["protolanguage"]), (12345, ["x", "y"])]:
        rng = generator(seed, *parts)
        weights = np.array([1.0, 2.0, 3.0, 0.5, 0.25, 4.0, 1.0])
        weights = weights / weights.sum()
        row = {"seed": str(seed), "parts": parts}
        row["integers"] = [int(rng.integers(1, 4)) for _ in range(6)]
        row["random"] = [float(rng.random()) for _ in range(3)]
        row["choice"] = [int(rng.choice(len(weights), p=weights)) for _ in range(8)]
        row["integers_wide"] = [int(rng.integers(0, 100)) for _ in range(5)]
        row["uniform"] = [float(rng.uniform(-3.0, -0.2)) for _ in range(3)]
        row["integers_after"] = [int(rng.integers(1, 4)) for _ in range(3)]
        out.append(row)
    return {"cases": out}


def protolanguage_vectors() -> dict:
    cases = []
    concepts = ["water", "fire", "one", "two", "thing", "step", "go"] + [f"concept-{i:04d}" for i in range(25)]
    for seed, kwargs in [
        (1, {}), (2, {}), (7, {"consonants": ("t", "k", "q", "s", "n", "m", "l", "ʃ", "x", "r", "j", "ts")}),
        (3, {"consonants": ("p", "t", "k", "s", "n"), "vowels": ("a", "i", "u"), "tones": ("˥", "˧", "˩")}),
        (4, {"fixed": {"water": "aqua"}}),
    ]:
        forms, freqs = protolanguage(concepts, seed=seed, **kwargs)
        row = {"seed": seed, "concepts": concepts, "forms": forms, "freqs": freqs}
        for key in ("consonants", "vowels", "tones"):
            if key in kwargs:
                row[key] = list(kwargs[key])
        if "fixed" in kwargs:
            row["fixed"] = kwargs["fixed"]
        cases.append(row)
    return {"cases": cases}


def segment_vectors() -> dict:
    table = default_table()
    words = [
        "pata", "kena", "ɡuli", "sɔ", "tsa", "kʷa", "ʃiqa", "a˥ta", "ka˧˥", "ká", "kǎ", "tʰa", "nja", "aŋ͡m",
        "kʲa", "ãta", "tiːra", "ɐta", "ɾa", "ʔa", "ðaθ", "xar", "mʷa", "aːpu",
    ]
    parsed = []
    for word in words:
        try:
            parsed.append({"ipa": word, "form": list(table.parse(word)), "render": table.render(table.parse(word))})
        except ValueError:
            parsed.append({"ipa": word, "form": None})
    changes = []
    sample = ["p", "t", "k", "b", "d", "ɡ", "s", "z", "m", "n", "l", "r", "a", "e", "i", "o", "u", "ə", "kʲ", "tʰ", "ɛ", "ɔ"]
    requests = [
        (("voi", "-"),), (("voi", "+"),), (("cont", "+"),), (("nas", "+"),), (("hi", "+"),), (("lo", "+"),),
        (("round", "+"),), (("back", "-"),), (("son", "+"), ("cons", "-")), (("delrel", "+"),),
    ]
    for ipa in sample:
        segment = table.id_of(ipa)
        for request in requests:
            for allow in ((), ("ʲ",)):
                result = table.changed(segment, tuple(request), allow)
                changes.append({"segment": segment, "ipa": ipa, "changes": [list(r) for r in request],
                                "allow": list(allow), "result": result})
    features = [table.names[i] for i in range(len(table.names))] if False else list(table.index)[:5]
    return {"parse": parsed, "changed": changes, "count": len(table.ipa), "features": features}


def parameter_vectors() -> dict:
    return {field.name: conv(getattr(Parameters(), field.name)) for field in fields(Parameters)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in (
        ("rng", rng_vectors()), ("numpy", numpy_vectors()), ("protolanguage", protolanguage_vectors()),
        ("segments", segment_vectors()), ("parameters", parameter_vectors()),
    ):
        (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
                                          encoding="utf-8")
        print(f"{name}.json")


if __name__ == "__main__":
    main()

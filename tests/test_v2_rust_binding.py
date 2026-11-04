"""Vazba enginu v Rustu (``cee_engine_py``): příklad světa do roku 300, průběh a export.

Krátký test jen nad vazbou; sestavení vazby je v ``rust/README.md``.
"""

import json
import time
from pathlib import Path

import pytest

from cee.v2 import runner

try:
    binding = runner.native()
except ImportError:
    pytest.skip("vazba cee_engine_py není sestavená (rust/README.md)", allow_module_level=True)

EXAMPLE = Path(__file__).parent.parent / "src" / "cee" / "data" / "v2_example_world.json"


def example(end_year: float = 300) -> dict:
    return {**json.loads(EXAMPLE.read_text(encoding="utf-8")), "end_year": end_year}


def test_beh_po_krocich_a_export():
    handle = binding.Run(json.dumps(example()))
    assert handle.start_year == 0 and handle.end_year == 300 and handle.year == 0
    while handle.advance(3):
        assert not handle.finished or handle.year < 300
    assert handle.finished and 0 < handle.year <= 300
    assert handle.snapshots > 0 and json.loads(handle.frame())["year"] == handle.year
    result = json.loads(handle.export())
    assert result["format"] == "cee-v2/1" and result["year"] == handle.year
    assert result["groups"] and result["lineages"]


def test_zruseni_a_neplatny_popis():
    handle = binding.Run(json.dumps(example(2000)))
    handle.cancel()
    assert handle.advance(5) is False and handle.cancelled and handle.tick == 0
    with pytest.raises(ValueError):
        binding.Run(json.dumps({**example(), "regions": []}))
    assert binding.check_spec(json.dumps(example())) is None
    assert binding.check_spec("{}")


def test_runner_na_vazbe():
    run = runner.start("vazba", example())
    for _ in range(2400):
        if run.status != "running":
            break
        time.sleep(0.05)
    view = run.status_view()
    assert view["status"] == "done" and view["progress"] == 1.0 and view["frames"]
    assert run.status_view(since=view["frame_count"])["frames"] == []
    assert run.result["format"] == "cee-v2/1"

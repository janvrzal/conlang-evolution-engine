from __future__ import annotations

import pytest

import cee.v2.assessment as assessment_module
import cee.v2.pressures.lexical as lexical_pressure_module
import cee.v2.pressures.linguistic as linguistic_pressure_module
import cee.v2.pressures.morphological as morphological_pressure_module
from cee.v2.scenarios import village_grid
from cee.v2.simulation import Simulation
from scripts.v2_timing import Timing, instrument, patched, timed_wrapper


def test_timed_wrapper_preserves_return_and_counts_call() -> None:
    timing = Timing.create()

    def original(value: int, *, extra: int = 0) -> int:
        return value + extra

    wrapped = timed_wrapper("fake", timing, original)
    assert wrapped(3, extra=4) == 7
    assert timing.calls["fake"] == 1
    assert timing.seconds["fake"] >= 0


def test_timed_wrapper_counts_exception_and_propagates_it() -> None:
    timing = Timing.create()

    def original() -> None:
        raise LookupError("expected")

    wrapped = timed_wrapper("fake", timing, original)
    with pytest.raises(LookupError, match="expected"):
        wrapped()
    assert timing.calls["fake"] == 1


def test_patched_restores_attribute_after_exception() -> None:
    class Example:
        def call(self) -> str:
            return "original"

    instance = Example()
    original = instance.call
    with pytest.raises(RuntimeError):
        with patched(instance, "call", lambda: "temporary"):
            assert instance.call() == "temporary"
            raise RuntimeError("expected")
    assert instance.call() == "original"
    assert "call" not in instance.__dict__
    assert original() == "original"


def test_timing_instrumentation_preserves_short_simulation_digest() -> None:
    world = village_grid(2, seed=2, phonology=True)
    events = ()
    plain = Simulation(world, events=events)
    plain.run(50)

    world = village_grid(2, seed=2, phonology=True)
    measured = Simulation(world, events=events)
    timing = Timing.create()
    with instrument(measured, timing):
        measured.run(50)

    assert measured.history.digest() == plain.history.digest()
    assert timing.calls["phase.innovate"] > 0
    assert timing.calls["phase.transmit"] > 0


def test_instrument_measures_sites_and_scores_and_restores_on_error() -> None:
    class FakeChange:
        kind = "fake-change"

        def sites(self, context: object) -> list[int]:
            return [1]

    class FakePressure:
        def scores(self, batch: object) -> list[float]:
            return [1.0]

    class FakeSimulation:
        changes = [FakeChange()]
        pressures = {"fake": ((FakePressure(), 1.0),)}

        def _innovate(self, year: float) -> None:
            return None

        def _transmit(self, year: float) -> None:
            return None

    change_method = FakeChange.sites
    pressure_method = FakePressure.scores
    simulation = FakeSimulation()
    timing = Timing.create()
    with pytest.raises(RuntimeError, match="expected"):
        with instrument(simulation, timing):  # type: ignore[arg-type]
            simulation.changes[0].sites(None)
            simulation.pressures["fake"][0][0].scores(None)
            raise RuntimeError("expected")

    assert timing.calls["change.sites.fake-change"] == 1
    assert timing.calls["pressure.FakePressure"] == 1
    assert FakeChange.sites is change_method
    assert FakePressure.scores is pressure_method


def test_instrument_measures_inherited_methods_per_concrete_type() -> None:
    class ChangeBase:
        def sites(self, context: object) -> list[int]:
            return [1]

    class FirstChange(ChangeBase):
        kind = "first-kind"

    class SecondChange(ChangeBase):
        kind = "second-kind"

    class PressureBase:
        def scores(self, batch: object) -> list[float]:
            return [1.0]

    class FirstPressure(PressureBase):
        pass

    class SecondPressure(PressureBase):
        pass

    original_sites = ChangeBase.sites
    original_scores = PressureBase.scores

    class FakeSimulation:
        changes = [FirstChange(), SecondChange()]
        pressures = {"fake": ((FirstPressure(), 1.0), (SecondPressure(), 1.0))}

        def _innovate(self, year: float) -> None:
            return None

        def _transmit(self, year: float) -> None:
            return None

    simulation = FakeSimulation()
    timing = Timing.create()
    with pytest.raises(RuntimeError, match="expected"):
        with instrument(simulation, timing):  # type: ignore[arg-type]
            for change in simulation.changes:
                change.sites(None)
            for weighted in simulation.pressures.values():
                for pressure, _ in weighted:
                    pressure.scores(None)
            raise RuntimeError("expected")

    assert timing.calls["change.sites.first-kind"] == 1
    assert timing.calls["change.sites.second-kind"] == 1
    assert timing.calls["pressure.FirstPressure"] == 1
    assert timing.calls["pressure.SecondPressure"] == 1
    assert "sites" not in FirstChange.__dict__
    assert "sites" not in SecondChange.__dict__
    assert "scores" not in FirstPressure.__dict__
    assert "scores" not in SecondPressure.__dict__
    assert ChangeBase.sites is original_sites
    assert PressureBase.scores is original_scores


def test_optional_helper_instrumentation_restores_all_functions_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helpers = (
        (assessment_module, "_assess_batch", "assessment._assess_batch"),
        (linguistic_pressure_module, "_process_scores", "pressure.linguistic._process_scores"),
        (morphological_pressure_module, "_form_scores", "pressure.morphological._form_scores"),
        (lexical_pressure_module, "_clarity_map", "pressure.lexical._clarity_map"),
    )
    originals = []

    def fake(*args, **kwargs):
        return "ok"

    for module, name, _ in helpers:
        monkeypatch.setattr(module, name, fake)
        originals.append(fake)

    class FakeSimulation:
        changes: list[object] = []
        pressures: dict[str, tuple[tuple[object, float], ...]] = {}

        def _innovate(self, year: float) -> None:
            return None

        def _transmit(self, year: float) -> None:
            return None

    simulation = FakeSimulation()
    timing = Timing.create()
    with pytest.raises(RuntimeError, match="expected"):
        with instrument(simulation, timing, include_helpers=True):  # type: ignore[arg-type]
            for index, (module, name, _) in enumerate(helpers):
                assert getattr(module, name) is not originals[index]
                assert getattr(module, name)() == "ok"
            raise RuntimeError("expected")

    for (module, name, label), original in zip(helpers, originals):
        assert getattr(module, name) is original
        assert timing.calls[label] == 1

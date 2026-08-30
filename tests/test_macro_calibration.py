from cee.metrics.macro_calibration import calibrate_macro_grid


def test_macro_grid_returns_closest_candidate_first():
    target = {"identity": 0.7, "substitution": 0.2, "gap": 0.1}

    results = calibrate_macro_grid(
        [{"change_rate": 0.5}, {"change_rate": 2.0}],
        target,
        lambda candidate: target if candidate["change_rate"] == 0.5 else {"gap": 1.0},
    )

    assert results[0].parameters == {"change_rate": 0.5}
    assert results[0].distance == 0.0

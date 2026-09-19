from cee.metrics.macro_calibration import calibrate_macro_grid, deletion_diagnostics


def test_macro_grid_returns_closest_candidate_first():
    target = {"identity": 0.7, "substitution": 0.2, "gap": 0.1}

    results = calibrate_macro_grid(
        [{"change_rate": 0.5}, {"change_rate": 2.0}],
        target,
        lambda candidate: target if candidate["change_rate"] == 0.5 else {"gap": 1.0},
    )

    assert results[0].parameters == {"change_rate": 0.5}
    assert results[0].distance == 0.0


def test_deletion_diagnostics_ignores_non_phonological_and_empty_events():
    events = [
        {"kind": "sound_change", "schema_id": "syncope", "deleted_segments": 3},
        {"kind": "sound_change", "schema_id": "syncope", "deleted_segments": 2},
        {"kind": "sound_change", "schema_id": "lenition", "deleted_segments": 0},
        {"kind": "contact", "deleted_segments": 10},
    ]

    assert deletion_diagnostics(events) == {"syncope": 5}

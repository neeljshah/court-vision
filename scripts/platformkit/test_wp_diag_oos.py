"""Synthetic verification for strictly date-ordered OOS WP diagnostics."""
from scripts.platformkit.wp_diag_oos import diagnose, walk_forward_isotonic


def _ticks(probability, outcome_fn):
    ticks = []
    for day in range(12):
        for index in range(20):
            ticks.append({"game": "NBA_%02d_%02d" % (day, index), "timestamp": "2026-01-%02dT12:00:00Z" % (day + 1),
                          "model_prob": probability(index), "outcome": outcome_fn(index), "phase": "Q%d" % (index % 4 + 1)})
    return ticks


def test_miscalibrated_series_has_positive_oos_delta_and_strict_dates():
    report = walk_forward_isotonic(_ticks(lambda index: 0.9 if index % 2 else 0.1,
                                           lambda index: 0.0 if index % 2 else 1.0))
    assert report["fold_count"] >= 3
    assert report["pooled"]["delta"] > 0
    assert all(row["train_date_max"] < row["test_date_min"] for row in report["folds"])
    assert all(row["date_ordering_asserted"] for row in report["folds"])


def test_calibrated_series_oos_delta_is_near_zero_and_is_split_by_sport():
    ticks = _ticks(lambda index: 1.0 if index % 2 else 0.0,
                  lambda index: 1.0 if index % 2 else 0.0)
    nfl = dict(ticks[0])
    nfl["game"] = "NFL_00_00"
    ticks.append(nfl)
    report = diagnose(ticks)
    section = report["sports"]["NBA"]
    assert set(report["sports"]) == {"NBA", "NFL"}
    assert abs(section["walk_forward_isotonic"]["pooled"]["delta"]) < 1e-12
    small = [row for rows in section["phase_reliability"].values() for row in rows if row["n"] < 50]
    assert all(row["status"] == "INSUFFICIENT" for row in small)
    assert all("wilson_95_low" in row and "wilson_95_high" in row for row in small)

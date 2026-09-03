"""Per-file CONSTRUCT test for S88 (no real corpus read; synthetic records only).

    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_s88_phase_recal.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import bucket_recalibration as BR
from scripts.platformkit.ingame.s88_phase_recal import score_bucket, walk_forward_inner_selected


def _rec(game_id, date, phase_bucket, model_prob, recal_prob, market_prob, outcome, is_informative=True):
    return {"game_id": game_id, "date": date, "phase_bucket": phase_bucket, "phase": phase_bucket.split("|")[0],
           "margin": 0.0, "model_prob": model_prob, "recal_prob": recal_prob, "market_prob": market_prob,
           "outcome": outcome, "is_informative": is_informative}


def _synthetic_records():
    # 5 game-first dates, 2 games/date, one phase bucket -- exhaustively enumerated (CONSTRUCT).
    records = []
    dates = ["2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    for di, d in enumerate(dates):
        for gi in range(2):
            gid = "g_%d_%d" % (di, gi)
            records.append(_rec(gid, d, "late|leading_big", model_prob=0.6, recal_prob=0.6,
                                market_prob=0.55, outcome=1.0))
    return records


def test_walk_forward_burn_in_passthrough_and_train_never_includes_test_date():
    """n = 10 (CONSTRUCT): 5 dates x 2 games, every record enumerated by hand above."""
    records = _synthetic_records()
    out, burn_dates, fold_choices = walk_forward_inner_selected(records, burn_in_frac=0.2, inner_val_frac=0.2)
    assert len(out) == len(records) == 10
    # burn-in dates pass raw model_prob through unchanged, flagged in_burn_in.
    burned = [r for r in out if r["in_burn_in"]]
    assert burned and all(r["date"] in burn_dates for r in burned)
    assert all(r["recal_prob"] == r["model_prob"] for r in burned)
    # non-burn-in folds: n_train reported by each fold equals the count of records whose
    # date is strictly BEFORE that fold's test date -- proves the test date's own rows
    # never entered training (no leakage into the walk-forward train set).
    by_date_count = {}
    for r in records:
        by_date_count[r["date"]] = by_date_count.get(r["date"], 0) + 1
    dates_sorted = sorted(by_date_count)
    for fc in fold_choices:
        expected_train = sum(by_date_count[d] for d in dates_sorted if d < fc["date"])
        assert fc["n_train"] == expected_train
        assert fc["spec"] in BR.SPECS  # winner is always one of the declared specs
    # every scored (non-burn-in) record's date shows up in exactly one fold_choices entry
    scored_dates = {r["date"] for r in out if not r["in_burn_in"]}
    assert scored_dates == {fc["date"] for fc in fold_choices}


def test_walk_forward_first_date_is_always_burn_in():
    records = _synthetic_records()
    out, burn_dates, _ = walk_forward_inner_selected(records, burn_in_frac=0.2, inner_val_frac=0.2)
    first_date = min(r["date"] for r in records)
    assert first_date in burn_dates
    assert all(r["in_burn_in"] for r in out if r["date"] == first_date)


def test_score_bucket_matches_hand_computed_brier_and_verdict():
    """n = 8 games (CONSTRUCT): recal is exactly right (0/1), incumbent and market are not --
    delta_vs_incumbent and delta_vs_market must both read IMPROVED with a hand-checkable Brier."""
    records = []
    for gi in range(8):
        outcome = 1.0 if gi % 2 == 0 else 0.0
        recal = outcome  # perfect recal prediction
        records.append(_rec("g%d" % gi, "d", "late|leading_big",
                            model_prob=0.7 if outcome == 1.0 else 0.3,
                            recal_prob=recal, market_prob=0.6 if outcome == 1.0 else 0.4,
                            outcome=outcome))
    row = score_bucket(records)
    assert row["n"] == 8 and row["n_informative"] == 8 and row["n_games_informative"] == 8
    assert row["brier_recal"] == 0.0
    assert abs(row["brier_incumbent"] - 0.09) < 1e-9   # (0.7-1)^2 == (0.3-0)^2 == 0.09 every game
    assert abs(row["brier_market"] - 0.16) < 1e-9       # (0.6-1)^2 == (0.4-0)^2 == 0.16 every game
    assert row["verdict_vs_incumbent"] == "IMPROVED"
    assert row["verdict_vs_market"] == "MODEL_AHEAD"
    assert row["delta_vs_incumbent_ci95"][0] > 0.0
    assert row["delta_vs_market_ci95"][0] > 0.0


def test_score_bucket_excludes_non_informative_ticks():
    informative = _rec("g0", "d", "late|leading_big", 0.7, 1.0, 0.6, 1.0, is_informative=True)
    stale = _rec("g1", "d", "late|leading_big", 0.9, 0.1, 0.9, 1.0, is_informative=False)
    row = score_bucket([informative, stale])
    assert row["n"] == 2 and row["n_informative"] == 1 and row["n_games_informative"] == 1
    assert row["brier_recal"] == 0.0  # only the informative row (perfect recal) is scored

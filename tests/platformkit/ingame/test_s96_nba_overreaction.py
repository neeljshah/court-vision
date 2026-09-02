"""Per-file test for S96 (event overreaction / drift on the NBA in-play line).

python -m pytest tests/platformkit/ingame/test_s96_nba_overreaction.py -q
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s96_nba_overreaction as s96


def _frame(n_games: int = 40, n_ticks: int = 40, seed: int = 0):
    """Driftless random-walk lines with scoring events, outcomes drawn from the final line."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        line = np.cumsum(rng.normal(0.0, 0.20, n_ticks))
        margin = np.cumsum(rng.choice([0, 0, 1, 2, 3, -3], n_ticks)).astype(int)
        y = int(rng.random() < s96.sigmoid(line[-1]))
        for t in range(n_ticks):
            rows.append({"game_id": g, "game_date": "2025-01-%02d" % (1 + g % 28),
                         "ts": 1000 + t, "period_bucket": "P1", "margin": int(margin[t]),
                         "model": 0.5, "market": float(s96.sigmoid(line[t])), "y": y})
    return pd.DataFrame(rows)


def _prepared(**kw) -> pd.DataFrame:
    raw = _frame(**kw)
    raw = raw.rename(columns={"period_bucket": "phase"})
    raw["game"] = raw["game_id"].astype(str)
    raw["date"] = raw["game"].map(raw.groupby("game")["game_date"].min())
    raw = raw.sort_values(["game", "ts"], kind="mergesort").reset_index(drop=True)
    raw["lm"] = s96.logit(raw["market"])
    grp = raw.groupby("game", sort=False)
    raw["dmargin"], raw["m1"] = grp["margin"].diff(), grp["lm"].diff()
    return raw


def test_bar_is_byte_identical_to_the_register_row():
    """Q3: the bar in the artifact must equal the bar in the spec -- never lowered."""
    assert s96.IMPROVEMENT_BAR == 0.004
    assert s96.SPEC["improvement_bar"] == 0.004
    assert s96.SPEC["edge_claimed"] is False


def test_assign_windows_tags_only_the_k_ticks_after_an_event():
    df = pd.DataFrame({
        "game": ["a"] * 8, "ts": range(8), "phase": ["P1"] * 8, "date": ["2025-01-01"] * 8,
        "margin": [0, 0, 3, 3, 3, 3, 3, 3], "market": [0.5] * 8, "model": [0.5] * 8,
        "y": [1] * 8, "game_date": ["2025-01-01"] * 8,
    })
    df["lm"] = s96.logit(df["market"])
    g = df.groupby("game", sort=False)
    df["dmargin"], df["m1"] = g["margin"].diff(), g["lm"].diff()
    df.loc[2, "m1"] = 0.8                      # the move at the event tick
    win = s96.assign_windows(df, threshold=3, k=3)
    assert list(win["ts"]) == [3, 4, 5]        # the event tick itself is NOT re-priced
    assert list(win["j"]) == [1, 2, 3]
    assert win["decay"].tolist() == pytest.approx([1.0, 2 / 3, 1 / 3])
    assert win["event_move"].tolist() == pytest.approx([0.8, 0.8, 0.8])


def test_a_second_event_restarts_the_window():
    df = pd.DataFrame({
        "game": ["a"] * 6, "ts": range(6), "phase": ["P1"] * 6, "date": ["2025-01-01"] * 6,
        "margin": [0, 3, 3, 6, 6, 6], "market": [0.5] * 6, "model": [0.5] * 6,
        "y": [1] * 6, "game_date": ["2025-01-01"] * 6,
    })
    df["lm"] = s96.logit(df["market"])
    g = df.groupby("game", sort=False)
    df["dmargin"], df["m1"] = g["margin"].diff(), g["lm"].diff()
    df.loc[1, "m1"], df.loc[3, "m1"] = 0.5, -0.9
    win = s96.assign_windows(df, threshold=3, k=3).set_index("ts")
    assert win.loc[2, "event_move"] == pytest.approx(0.5)
    assert win.loc[4, "event_move"] == pytest.approx(-0.9)   # the newer event owns tick 4
    assert win.loc[4, "j"] == 1


@pytest.mark.parametrize("lam_true", [0.4, -0.4])
def test_fit_lambda_recovers_a_planted_distortion(lam_true):
    """The line shown is logit(true) + lam_true * adj; the grid must find lam_true (both signs)."""
    rng = np.random.default_rng(1)
    n = 60000
    true_l, adj = rng.normal(0.0, 1.2, n), rng.normal(0.0, 0.8, n)
    train = pd.DataFrame({"phase": "P1", "adj": adj, "lm": true_l + lam_true * adj,
                          "y": (rng.random(n) < s96.sigmoid(true_l)).astype(int)})
    assert s96.fit_lambda(train)["P1"] == pytest.approx(lam_true, abs=0.08)


def test_walk_forward_is_game_purged_and_embargoed():
    win = s96.assign_windows(_prepared(), threshold=3, k=5)
    scored, folds = s96.walk_forward(win)
    ok = [f for f in folds if f["status"] == "OK"]
    assert ok, "no scorable fold"
    for f in ok:
        assert f["train_date_max"] < f["embargo_cut"] <= f["test_start"]
    assert not scored.empty


def test_flipping_held_out_outcomes_does_not_move_the_arm():
    """Q4 leak contract: the arm reads only TRAIN outcomes, never the test fold's."""
    win = s96.assign_windows(_prepared(), threshold=3, k=5)
    scored, folds = s96.walk_forward(win)
    last = max(f["fold"] for f in folds if f["status"] == "OK")
    test_games = set(scored.loc[scored["fold"] == last, "game"])
    flipped = win.copy()
    rows = flipped["game"].isin(test_games)
    flipped.loc[rows, "y"] = 1 - flipped.loc[rows, "y"]
    scored2, _ = s96.walk_forward(flipped)
    a = scored.loc[scored["fold"] == last, "p_arm"].to_numpy()
    b = scored2.loc[scored2["fold"] == last, "p_arm"].to_numpy()
    assert np.max(np.abs(a - b)) == 0.0


def test_run_writes_the_artifact_and_claims_no_edge(tmp_path):
    out = s96.run(out_dir=tmp_path, stem="t", frame=_prepared())
    assert (tmp_path / "t.json").exists() and (tmp_path / "t.csv").exists()
    assert out["premise"]["3"]["n_events"] > 0
    assert out["improvement_bar"] == 0.004
    assert out["edge_claimed"] is False
    series = pd.read_csv(tmp_path / "t.csv")
    assert {"d_arm_vs_market", "d_arm_vs_recal", "cluster_id"} <= set(series.columns)
    text = (tmp_path / "t.json").read_text(encoding="ascii")
    assert "uncharged" in text and "SINGLE-WINDOW" in text
    src = Path(s96.__file__).read_text(encoding="utf-8")   # Q1/Q2: nothing charged, nothing sealed
    for banned in ("_charge_ledger", "backtest_fwer", "prereg_seal", "sha256"):
        assert banned not in src

"""S58 trial-B module: checkpoint never past the anchor, prior strictly before game_date, seal-before-
charge on a TMP ledger, K read from the row, per-game CSV reproduces the pooled Brier.
python -m pytest tests/platformkit/eval_gate/test_s58_nba_halftime_asof_trial.py -q"""
import hashlib, json

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.eval_gate import s58_nba_halftime_asof_trial as T

TEAMS = ["BOS", "NYK", "LAL", "GSW", "PHX", "WAS", "MIA", "DEN"]


def _games(seed=0, n=400):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        h, a = rng.choice(TEAMS, 2, replace=False)
        d = pd.Timestamp("2023-10-20") + pd.Timedelta(days=int(i * 2))
        rows.append({"game_id": "g%04d" % i, "date": d, "season": "2023-24" if d < pd.Timestamp("2024-08-01") else "2024-25",
                     "home_team": h, "away_team": a, "home_win": float(rng.integers(0, 2))})
    return pd.DataFrame(rows)


def _ticks(seed=1, n_games=60):
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        a, h = rng.choice(["pho", "wsh", "bos", "nyk", "lal", "gsw"], 2, replace=False)
        date = pd.Timestamp("2024-10-22") + pd.Timedelta(days=int(g * 5))
        y = int(rng.integers(0, 2))
        for k, (per, clock) in enumerate([(1, 720.0), (2, 300.0), (2, 60.0), (2, 0.0), (3, 700.0), (4, 100.0)]):
            rows.append({"game_id": "n%03d" % g, "game_date": date.strftime("%Y-%m-%d"), "ts": 1000 + g * 100 + k, "period": per,
                         "game_clock_s": clock, "score_home": 50 + k * 5 + (5 if y else 0), "score_away": 50 + k * 5, "margin": 0,
                         "market_prob": float(np.clip(0.55 + (0.2 if y else -0.2) * k / 6 + rng.normal(0, 0.03), 0.02, 0.98)),
                         "traded": True, "market_ticker": "nba-%s-%s-%s" % (a, h, date.strftime("%Y-%m-%d")), "outcome_home_win": y, "venue": "polymarket"})
    return pd.DataFrame(rows)


def test_checkpoint_rule_and_aliases():
    cp = T.halftime_checkpoints(_ticks())
    assert len(cp) == 60 and (cp["elapsed"] <= T.ANCHOR).all() and (cp["elapsed"] == 24.0).all()   # (2, 0.0) is the last <= 24 tick
    assert set(cp["home"]) | set(cp["away"]) <= {"PHX", "WAS", "BOS", "NYK", "LAL", "GSW"}
    assert set(cp["unit"]) == {"2024-25", "2025-26"}


def test_prior_is_strictly_before_game_date():
    cp = T.halftime_checkpoints(_ticks()); games = _games()  # noqa: E702
    pri = T.asof_priors(cp, games)
    assert all(pd.Timestamp(u) == pd.Timestamp(d) for u, d in zip(pri["elo_until_date"], pri["game_date"]))
    assert pri["prior_stale"].sum() == int((pd.to_datetime(pri["game_date"]).dt.date > games["date"].max().date()).sum())
    assert ((pri["p0_asof"] > 0) & (pri["p0_asof"] < 1)).all()


def test_seal_charge_score(tmp_path):
    cp = T.halftime_checkpoints(_ticks()); games = _games()  # noqa: E702
    prereg = tmp_path / "prereg.md"; prereg.write_text("frozen", "ascii"); ledger = tmp_path / "l.jsonl"  # noqa: E702
    with pytest.raises(AssertionError):
        T.run_trial(cp, games, ledger_path=ledger, prereg_path=prereg, prereg_sha256="00")
    assert not ledger.exists()
    seal = hashlib.sha256(prereg.read_bytes()).hexdigest()
    res = T.run_trial(cp, games, ledger_path=ledger, prereg_path=prereg, prereg_sha256=seal,
                      out_path=tmp_path / "o.json", pergame_path=tmp_path / "pg.csv")
    rows = [json.loads(l) for l in ledger.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["k_cumulative"] == 1 == res["k_at_launch"] and rows[0]["family"] == T.FAMILY
    assert res["verdict"] in ("AHEAD", "BEHIND", "NULL", "SINGLE-WINDOW") and set(res["units"]) == {"2024-25", "2025-26"}
    pg = pd.read_csv(tmp_path / "pg.csv", comment="#")
    assert len(pg) == 60 and abs(((pg["model"] - pg["y"]) ** 2).mean() - res["pooled"]["brier"]["model"]) < 1e-12
    assert abs(pg["d"].mean() - res["pooled"]["improvement"]) < 1e-12

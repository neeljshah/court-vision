"""Per-file test for scripts.platformkit.props_eval_mlb (network-free, canned df).

Run (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval_mlb.py -q
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from scripts.platformkit import props_eval_mlb as M


def _batter_row(game_pk, date, pid, order, ab, h, tb, rbi, runs, bb):
    return {
        "game_pk": game_pk, "date": date, "team": "AAA", "player_id": pid,
        "player": f"B{pid}", "position": "OF", "is_pitcher": False,
        "batting_order": order, "atBats": ab, "hits": h, "totalBases": tb,
        "rbi": rbi, "runs": runs, "homeRuns": 0, "doubles": 0, "triples": 0,
        "baseOnBalls": bb, "strikeOuts": 1, "stolenBases": 0, "hitByPitch": 0,
        "outs": 0, "earnedRuns": 0, "battersFaced": 0, "pitch_strikeOuts": 0,
        "hits_allowed": 0, "baseOnBalls_allowed": 0, "inningsPitched": 0,
    }


def _pitcher_row(game_pk, date, pid, bf, k, er, outs):
    return {
        "game_pk": game_pk, "date": date, "team": "BBB", "player_id": pid,
        "player": f"P{pid}", "position": "P", "is_pitcher": True,
        "batting_order": 0, "atBats": 0, "hits": 0, "totalBases": 0, "rbi": 0,
        "runs": 0, "homeRuns": 0, "doubles": 0, "triples": 0, "baseOnBalls": 0,
        "strikeOuts": 0, "stolenBases": 0, "hitByPitch": 0, "outs": outs,
        "earnedRuns": er, "battersFaced": bf, "pitch_strikeOuts": k,
        "hits_allowed": 6, "baseOnBalls_allowed": 2, "inningsPitched": outs / 3.0,
    }


def _canned_df():
    # 4 dated games, two recurring players (one batter pid=1, one pitcher pid=2).
    rows = []
    # G1 (earliest): seeds priors, no prediction (no prior yet).
    rows.append(_batter_row(101, "2026-06-01", 1, 3, ab=4, h=2, tb=3, rbi=1, runs=1, bb=1))
    rows.append(_pitcher_row(101, "2026-06-01", 2, bf=25, k=7, er=2, outs=18))
    # G2
    rows.append(_batter_row(102, "2026-06-03", 1, 3, ab=4, h=1, tb=2, rbi=0, runs=1, bb=0))
    rows.append(_pitcher_row(102, "2026-06-03", 2, bf=24, k=6, er=3, outs=18))
    # G3
    rows.append(_batter_row(103, "2026-06-05", 1, 3, ab=5, h=3, tb=4, rbi=2, runs=2, bb=1))
    rows.append(_pitcher_row(103, "2026-06-05", 2, bf=26, k=9, er=1, outs=21))
    # G4 (latest): a huge batter game; must NOT inform earlier preds (leak guard).
    rows.append(_batter_row(104, "2026-06-07", 1, 3, ab=6, h=6, tb=12, rbi=9, runs=6, bb=3))
    rows.append(_pitcher_row(104, "2026-06-07", 2, bf=28, k=12, er=0, outs=24))
    return pd.DataFrame(rows)


def test_backtest_returns_per_stat_with_predictions():
    res = M.backtest_calibration_mlb(_canned_df())
    assert isinstance(res, dict)
    assert res["overall"]["n"] > 0
    per_stat = res["per_stat"]
    # at least one batter and one pitcher stat produced settled predictions
    assert per_stat.get("Hits", {}).get("n", 0) > 0
    assert per_stat.get("Pitcher Strikeouts", {}).get("n", 0) > 0
    for d in per_stat.values():
        if d.get("n", 0) > 0:
            assert 0.0 <= d["brier"] <= 1.0
            assert d["ece"] is not None


def test_leak_free_post_asof_game_does_not_change_earlier_preds():
    full = _canned_df()
    # drop the latest game; earlier predictions must be byte-identical.
    trimmed = full[full["game_pk"] != 104].copy()

    def hits_pairs(df):
        preds = M._collect_per_stat_preds(df, ["Hits"])
        return [(round(d["p_over"], 6), d["outcome"], str(d["date"]))
                for d in preds["Hits"]]

    full_early = [p for p in hits_pairs(full) if p[2] < "2026-06-07"]
    trimmed_all = hits_pairs(trimmed)
    assert full_early == trimmed_all
    assert len(full_early) > 0


def test_public_funcs_never_raise_on_bad_input(tmp_path):
    for bad in (None, pd.DataFrame(), "nope", 123):
        res = M.backtest_calibration_mlb(bad)
        assert res["overall"]["n"] == 0
    # write cache with empty df still returns a payload, no raise (temp path so the
    # real cache is never clobbered by an empty backtest).
    out = os.path.join(str(tmp_path), "empty_cache.json")
    pl = M.write_calibration_cache_mlb(pd.DataFrame(), out_path=out)
    assert isinstance(pl, dict)


def test_cache_writes_and_round_trips(tmp_path):
    out = os.path.join(str(tmp_path), "prop_calibration.json")
    pl = M.write_calibration_cache_mlb(_canned_df(), out_path=out)
    assert pl["written"] is True
    assert pl["sport"] == "mlb"
    assert os.path.exists(out)
    with open(out, "r", encoding="ascii") as fh:
        payload = json.load(fh)
    assert payload["sport"] == "mlb"
    assert isinstance(payload["per_stat"], dict)
    # the existing tiering loader round-trips the MLB cache unchanged
    loaded = M.load_calibration(out)
    assert isinstance(loaded, dict)
    for stat, rec in loaded.items():
        assert "bss" in rec and "n" in rec


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

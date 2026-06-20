"""Per-file tests for ingame_clv_trend.py -- multi-batch in-game CLV trend/delta.

OFFLINE + deterministic: all grade files written to tmp dirs; no network.

Acceptance criteria (workstream BE-INGAME-CLV-TREND):
  (A) 3+ batches with rising batch-mean CLV -> verdict IMPROVING, monotone_improving True.
  (B) 3+ batches with worsening CLV -> verdict WORSENING, regression_flag True.
  (C) < 2 scored batches -> verdict INSUFFICIENT_DATA.
  (D) CLV may be INSUFFICIENT_DATA per batch (batch with n_ticks==0 -> mean_clv None).
  (E) No $ / roi / pnl / profit / bankroll / dollar key anywhere in output.
  (F) edge_claimed = False; units = 'probability'.
  (G) delta_series has correct values (batch[i+1].mean - batch[i].mean).
  (H) trend_from_aggregate: < min_games graded games -> agg INSUFFICIENT_DATA -> trend INSUFFICIENT_DATA.
  (I) format_trend_report has no '$' character; contains verdict string.
  (J) compute_trend never raises (even on malformed / empty input).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_trend.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

import scripts.platformkit.ingame.ingame_clv_trend as tr
import scripts.platformkit.ingame.ingame_clv_aggregate as agg

# --------------------------------------------------------------------------- #
# helpers: build synthetic clv_series / grade files                            #
# --------------------------------------------------------------------------- #

def _ts(hour: int, minute: int = 0) -> str:
    base = datetime(2026, 6, 1, hour, minute, 0, tzinfo=timezone.utc)
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_series(mean_clvs: List[float], n_ticks_each: int = 10) -> List[dict]:
    """Build a synthetic clv_series list (already settle_ts-sorted)."""
    out = []
    for i, clv in enumerate(mean_clvs):
        out.append({
            "game_id": "G%d" % i,
            "settle_ts": _ts(i + 1),
            "mean_clv": clv,
            "n_ticks": n_ticks_each,
        })
    return out


def _make_zero_tick_series(n: int) -> List[dict]:
    """Games where n_ticks==0 so per-batch mean is None (INSUFFICIENT_DATA per batch)."""
    out = []
    for i in range(n):
        out.append({
            "game_id": "Z%d" % i,
            "settle_ts": _ts(i + 1),
            "mean_clv": 0.0,
            "n_ticks": 0,
        })
    return out


def _write_game(grade_dir: Path, sport: str, gid: str, rows: List[dict]) -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _tick_ts(gidx: int, tick_i: int) -> str:
    base = (datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
            + timedelta(hours=gidx, seconds=30 * tick_i))
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _positive_clv_game(gidx: int, gid: str, n: int = 14) -> List[dict]:
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        market = close if i == n - 1 else 0.50 + (close - 0.50) * frac
        model = 0.60 + (close - 0.60) * frac
        rows.append({
            "sport": "nba", "game_id": gid, "ts": _tick_ts(gidx, i),
            "market_prob": round(market, 6),
            "model_prob": round(min(0.99, max(0.01, model)), 6),
            "side": "home", "state_summary": "live",
        })
    return rows


# --------------------------------------------------------------------------- #
# (A) rising CLV -> IMPROVING, monotone_improving True                         #
# --------------------------------------------------------------------------- #
def test_rising_clv_improving():
    # 3 batches of 3 games each -> 9 games total; CLV rises each batch.
    # batch 0: mean 0.02, batch 1: mean 0.04, batch 2: mean 0.06
    clvs = [0.02] * 3 + [0.04] * 3 + [0.06] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    assert result["verdict"] == "IMPROVING", (
        "expected IMPROVING for rising batches, got %s; batches=%s"
        % (result["verdict"], result["batches"])
    )
    assert result["monotone_improving"] is True
    assert result["regression_flag"] is False
    assert result["edge_claimed"] is False
    assert result["units"] == "probability"
    assert result["n_scored_batches"] == 3
    assert result["first_batch_mean_clv"] < result["last_batch_mean_clv"]


# --------------------------------------------------------------------------- #
# (B) worsening CLV -> WORSENING, regression_flag True                         #
# --------------------------------------------------------------------------- #
def test_worsening_clv_behind():
    # 3 batches descending: 0.06 -> 0.04 -> 0.02
    clvs = [0.06] * 3 + [0.04] * 3 + [0.02] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    assert result["verdict"] == "WORSENING", (
        "expected WORSENING for declining batches, got %s" % result["verdict"]
    )
    assert result["monotone_improving"] is False
    assert result["regression_flag"] is True
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------- #
# (C) < 2 scored batches -> INSUFFICIENT_DATA                                  #
# --------------------------------------------------------------------------- #
def test_single_batch_insufficient():
    # Only 3 games total -> 1 batch -> < min_batches=2
    clvs = [0.05, 0.06, 0.07]
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    assert result["verdict"] == "INSUFFICIENT_DATA", (
        "single batch should give INSUFFICIENT_DATA, got %s" % result["verdict"]
    )
    assert result["monotone_improving"] is False


def test_empty_series_insufficient():
    result = tr.compute_trend([])
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["n_batches"] == 0
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------- #
# (D) zero-tick batches are INSUFFICIENT_DATA per batch                        #
# --------------------------------------------------------------------------- #
def test_zero_tick_batches_insufficient():
    # 9 games all with n_ticks=0 -> all batch means are None -> n_scored=0
    series = _make_zero_tick_series(9)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    assert result["verdict"] == "INSUFFICIENT_DATA", (
        "all-zero-tick games -> INSUFFICIENT_DATA, got %s" % result["verdict"]
    )
    assert result["n_scored_batches"] == 0
    for b in result["batches"]:
        assert b["verdict"] == "INSUFFICIENT_DATA", (
            "zero-tick batch should have verdict INSUFFICIENT_DATA, got %s" % b
        )


def test_mixed_tick_batches_partial():
    # First 3 games have n_ticks>0 (batch 0 scored); last 3 have n_ticks=0 (batch 1 no score).
    # Only 1 scored batch -> INSUFFICIENT_DATA.
    series = _make_series([0.05, 0.06, 0.07]) + _make_zero_tick_series(3)
    # Fix timestamps to be monotone.
    for i, s in enumerate(series):
        s["settle_ts"] = _ts(i + 1)
        s["game_id"] = "MX%d" % i
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    # Only 1 scored batch from the first window; second window has None -> insufficient.
    assert result["n_scored_batches"] == 1
    assert result["verdict"] == "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------- #
# (E) no $ / roi / pnl / profit / bankroll key                                 #
# --------------------------------------------------------------------------- #
def test_no_dollar_field_anywhere():
    clvs = [0.02] * 3 + [0.04] * 3 + [0.06] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    banned = ("roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
              "profit", "ev_dollars", "money")
    blob = json.dumps(result).lower()
    for tok in banned:
        assert tok not in blob, "banned token %r leaked into trend output" % tok


# --------------------------------------------------------------------------- #
# (F) edge_claimed = False; units = 'probability'                              #
# --------------------------------------------------------------------------- #
def test_edge_claimed_false_units_probability():
    series = _make_series([0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)
    assert result["edge_claimed"] is False
    assert result["units"] == "probability"


# --------------------------------------------------------------------------- #
# (G) delta_series correctness                                                 #
# --------------------------------------------------------------------------- #
def test_delta_series_values():
    # 3 batches of 3 games: mean 0.02, 0.05, 0.03
    clvs = [0.02] * 3 + [0.05] * 3 + [0.03] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)

    assert len(result["delta_series"]) == 2, (
        "expected 2 deltas for 3 batches, got %d" % len(result["delta_series"])
    )
    delta0 = result["delta_series"][0]
    delta1 = result["delta_series"][1]
    # batch 1 mean - batch 0 mean ~ 0.03
    assert abs(delta0 - 0.03) < 1e-5, "delta[0] expected ~+0.03, got %+.6f" % delta0
    # batch 2 mean - batch 1 mean ~ -0.02
    assert abs(delta1 - (-0.02)) < 1e-5, "delta[1] expected ~-0.02, got %+.6f" % delta1


# --------------------------------------------------------------------------- #
# (H) trend_from_aggregate: thin real data -> INSUFFICIENT_DATA end-to-end     #
# --------------------------------------------------------------------------- #
def test_trend_from_aggregate_real_data_insufficient():
    # Real on-disk grade dir has fewer than MIN_GAMES games.
    result = tr.trend_from_aggregate()
    assert result["agg_verdict"] == "INSUFFICIENT_DATA", (
        "expected agg INSUFFICIENT_DATA on real disk, got %s" % result["agg_verdict"]
    )
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["edge_claimed"] is False


def test_trend_from_aggregate_synthetic(tmp_path):
    # Build 9 synthetic games with positive CLV -> aggregate BEATS -> trend reads rising.
    gd = tmp_path / "grade"
    for k in range(9):
        _write_game(gd, "nba", "TG%d" % k, _positive_clv_game(k, "TG%d" % k))

    result = tr.trend_from_aggregate(
        grade_dir=gd,
        batch_size=3, min_fill=2, min_batches=2,
        agg_min_games=5, agg_min_total_ticks=40,
    )
    # 9 games, all with the same shape -> mean_clv identical across batches -> FLAT or IMPROVING.
    assert result["agg_verdict"] == "BEAT"
    assert result["verdict"] in ("IMPROVING", "FLAT"), (
        "9 same-shape positive-CLV games should be FLAT or IMPROVING, got %s" % result["verdict"]
    )
    assert result["edge_claimed"] is False
    assert "agg_n_games" in result
    assert result["agg_n_games"] == 9


# --------------------------------------------------------------------------- #
# (I) format_trend_report has no '$', contains verdict                         #
# --------------------------------------------------------------------------- #
def test_format_trend_report_no_dollar():
    clvs = [0.01] * 3 + [0.03] * 3 + [0.05] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2)
    report = tr.format_trend_report(result)

    assert "$" not in report, "format_trend_report must not contain a dollar sign"
    assert result["verdict"] in report, "report must contain the verdict string"
    assert "probability" in report.lower()


def test_format_trend_report_insufficient():
    result = tr.compute_trend([])
    report = tr.format_trend_report(result)
    assert "$" not in report
    assert "INSUFFICIENT_DATA" in report


# --------------------------------------------------------------------------- #
# (J) compute_trend never raises                                               #
# --------------------------------------------------------------------------- #
def test_compute_trend_never_raises_on_garbage():
    bad_inputs = [
        None,
        [None, None],
        [{"game_id": "x"}],                  # missing mean_clv, n_ticks
        [{"mean_clv": "NaN", "n_ticks": "?", "settle_ts": "bad"}],
        "not a list",
        42,
    ]
    for inp in bad_inputs:
        try:
            result = tr.compute_trend(inp)  # type: ignore[arg-type]
            # Should return INSUFFICIENT_DATA gracefully.
            assert result["verdict"] == "INSUFFICIENT_DATA", (
                "expected INSUFFICIENT_DATA for garbage input %r, got %s"
                % (inp, result.get("verdict"))
            )
        except Exception as exc:
            pytest.fail(
                "compute_trend raised %s on input %r" % (type(exc).__name__, inp)
            )


# --------------------------------------------------------------------------- #
# regression_flag correctness (mixed: rise then drop)                          #
# --------------------------------------------------------------------------- #
def test_regression_flag_on_mixed_series():
    # batch 0: mean 0.02, batch 1: mean 0.06, batch 2: mean 0.01
    # -> step 0->1 rises, step 1->2 drops by 0.05 > DELTA_THRESH -> regression_flag True
    clvs = [0.02] * 3 + [0.06] * 3 + [0.01] * 3
    series = _make_series(clvs)
    result = tr.compute_trend(series, batch_size=3, min_fill=2, min_batches=2,
                              delta_thresh=tr.DELTA_THRESH)

    assert result["regression_flag"] is True, (
        "mixed series with a big drop should flag regression, got %s" % result
    )
    assert result["verdict"] == "WORSENING", (
        "last < first -> WORSENING, got %s" % result["verdict"]
    )
    assert result["monotone_improving"] is False

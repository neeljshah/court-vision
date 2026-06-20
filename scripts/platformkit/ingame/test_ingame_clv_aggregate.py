"""Per-file tests for ingame_clv_aggregate.py -- honest multi-game in-game CLV aggregator.

OFFLINE + deterministic: all grade files are written to tmp dirs; no network.

Acceptance criteria (from BACKLOG.md ig-clv-aggregate):
  (a) Synthetic pairs with a PLANTED positive CLV -> aggregator RECOVERS verdict BEAT
      once >= MIN_GAMES games are present (game-clustered CI lower bound > 0).
  (b) Synthetic pairs with PLANTED negative CLV -> BEHIND.
  (c) MARKET-COPY games (model == market) -> pooled_mean_clv == 0.0 -> MATCH.
  (d) Below MIN_GAMES -> INSUFFICIENT_DATA regardless of raw signal (variance, not signal).
  (e) No $ field anywhere; units = 'probability'; edge_claimed = False.
  (f) REAL on-disk data (if any) -> INSUFFICIENT_DATA (not enough games yet).
  (g) Empty grade dir -> INSUFFICIENT_DATA.
  (h) format_report carries no $ string.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_aggregate.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

import scripts.platformkit.ingame.ingame_clv_aggregate as agg


# --------------------------------------------------------------------------------------- #
# helpers to write synthetic grade files                                                  #
# --------------------------------------------------------------------------------------- #
def _ts(game_idx: int, tick_i: int) -> str:
    base = (datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
            + timedelta(hours=game_idx, seconds=30 * tick_i))
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_game(grade_dir: Path, sport: str, gid: str,
                rows: List[dict]) -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _positive_clv_game(gidx: int, gid: str, *, n: int = 14,
                        sport: str = "nba") -> List[dict]:
    """Game where model consistently leads the market toward the closing line.

    The market drifts from 0.50 to 0.65 (close). The model starts at ~0.60 (ahead
    of market) and tracks toward 0.65. Edge at each tick = model - market > 0;
    realized move = close - market > 0 -> CLV > 0 on every scored tick.
    """
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        # model is ahead: interpolates from 0.60 -> close (always ahead of market pre-close).
        model = 0.60 + (close - 0.60) * frac
        model = min(0.99, max(0.01, model))
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


def _negative_clv_game(gidx: int, gid: str, *, n: int = 14,
                        sport: str = "nba") -> List[dict]:
    """Game where model consistently leans AWAY from the closing line -> CLV < 0."""
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        # model leans the WRONG way (toward 0.35, away from 0.65).
        model = 0.50 - (close - 0.50) * frac * 0.8
        model = min(0.99, max(0.01, model))
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


def _copy_game(gidx: int, gid: str, *, n: int = 14,
               sport: str = "nba") -> List[dict]:
    """Market-copy game: model == market on every tick -> CLV = 0 on every scored tick."""
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(market, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


# --------------------------------------------------------------------------------------- #
# (a) planted positive CLV -> BEAT once >= MIN_GAMES games                                #
# --------------------------------------------------------------------------------------- #
def test_positive_clv_recovered_beat(tmp_path):
    gd = tmp_path / "grade"
    n_games = agg.MIN_GAMES + 2   # comfortably above threshold
    for k in range(n_games):
        _write_game(gd, "nba", "POS-G%d" % k,
                    _positive_clv_game(k, "POS-G%d" % k))
    result = agg.aggregate(grade_dir=gd, min_games=agg.MIN_GAMES,
                           min_total_ticks=agg.MIN_TOTAL_TICKS)
    assert result["verdict"] == "BEAT", (
        "expected BEAT for positive CLV pool, got %s (mean_clv=%+.5f, ci95=%s)"
        % (result["verdict"], result["pooled_mean_clv"], result["clv_ci95"])
    )
    assert result["pooled_mean_clv"] > agg.EPS_DEFAULT
    lo, hi = result["clv_ci95"]
    assert lo > 0.0, "expected CI lower bound > 0 for BEAT verdict"
    assert result["n_games"] == n_games
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (b) planted negative CLV -> BEHIND                                                      #
# --------------------------------------------------------------------------------------- #
def test_negative_clv_recovered_behind(tmp_path):
    gd = tmp_path / "grade"
    n_games = agg.MIN_GAMES + 2
    for k in range(n_games):
        _write_game(gd, "nba", "NEG-G%d" % k,
                    _negative_clv_game(k, "NEG-G%d" % k))
    result = agg.aggregate(grade_dir=gd, min_games=agg.MIN_GAMES,
                           min_total_ticks=agg.MIN_TOTAL_TICKS)
    assert result["verdict"] == "BEHIND", (
        "expected BEHIND for negative CLV pool, got %s (mean_clv=%+.5f)"
        % (result["verdict"], result["pooled_mean_clv"])
    )
    assert result["pooled_mean_clv"] < -agg.EPS_DEFAULT


# --------------------------------------------------------------------------------------- #
# (c) market-copy games -> pooled_mean_clv == 0 -> MATCH                                 #
# --------------------------------------------------------------------------------------- #
def test_market_copy_is_match(tmp_path):
    gd = tmp_path / "grade"
    n_games = agg.MIN_GAMES + 2
    for k in range(n_games):
        _write_game(gd, "nba", "COPY-G%d" % k, _copy_game(k, "COPY-G%d" % k))
    result = agg.aggregate(grade_dir=gd, min_games=agg.MIN_GAMES,
                           min_total_ticks=agg.MIN_TOTAL_TICKS)
    assert abs(result["pooled_mean_clv"]) < 1e-10, (
        "market-copy pool should have pooled_mean_clv==0, got %+.8f"
        % result["pooled_mean_clv"]
    )
    # MATCH (not BEAT) even if raw mean were ever nonzero from floating-point noise.
    assert result["verdict"] in ("MATCH", "INSUFFICIENT_DATA"), result


# --------------------------------------------------------------------------------------- #
# (d) below MIN_GAMES -> INSUFFICIENT_DATA regardless of signal                           #
# --------------------------------------------------------------------------------------- #
def test_too_few_games_insufficient(tmp_path):
    gd = tmp_path / "grade"
    few = agg.MIN_GAMES - 1   # one short of threshold
    for k in range(few):
        _write_game(gd, "nba", "FEW-G%d" % k,
                    _positive_clv_game(k, "FEW-G%d" % k))
    result = agg.aggregate(grade_dir=gd, min_games=agg.MIN_GAMES,
                           min_total_ticks=agg.MIN_TOTAL_TICKS)
    assert result["verdict"] == "INSUFFICIENT_DATA", (
        "expected INSUFFICIENT_DATA below MIN_GAMES, got %s (n_games=%d)"
        % (result["verdict"], result["n_games"])
    )
    assert result["n_games"] == few
    assert result["edge_claimed"] is False


def test_zero_games_insufficient(tmp_path):
    gd = tmp_path / "grade"
    gd.mkdir()
    result = agg.aggregate(grade_dir=gd)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["n_games"] == 0


# --------------------------------------------------------------------------------------- #
# (e) no $ field; units = 'probability'; edge_claimed = False                             #
# --------------------------------------------------------------------------------------- #
def test_no_dollar_field_anywhere(tmp_path):
    gd = tmp_path / "grade"
    for k in range(agg.MIN_GAMES + 2):
        _write_game(gd, "nba", "D-G%d" % k,
                    _positive_clv_game(k, "D-G%d" % k))
    result = agg.aggregate(grade_dir=gd)
    banned = ("roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
              "profit", "edge_pct", "ev_dollars", "money")
    blob = json.dumps(result).lower()
    for tok in banned:
        assert tok not in blob, "banned token %r leaked into aggregate output" % tok
    assert result["units"] == "probability"
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (f) real on-disk data -> INSUFFICIENT_DATA                                              #
# --------------------------------------------------------------------------------------- #
def test_real_on_disk_is_insufficient():
    result = agg.aggregate()   # default DEFAULT_GRADE_DIR
    # Real data has far fewer than MIN_GAMES settled in-game graded files.
    assert result["verdict"] == "INSUFFICIENT_DATA", (
        "expected INSUFFICIENT_DATA for real on-disk data, got %s (n_games=%d)"
        % (result["verdict"], result["n_games"])
    )
    assert result["n_games"] < agg.MIN_GAMES
    assert result["edge_claimed"] is False
    assert result["units"] == "probability"


# --------------------------------------------------------------------------------------- #
# (g) empty grade dir -> INSUFFICIENT_DATA                                               #
# --------------------------------------------------------------------------------------- #
def test_empty_grade_dir_insufficient(tmp_path):
    gd = tmp_path / "nonexistent_dir"   # does not exist -> discover_grade_files returns []
    result = agg.aggregate(grade_dir=gd)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["n_games"] == 0


# --------------------------------------------------------------------------------------- #
# (h) format_report has no $ string                                                       #
# --------------------------------------------------------------------------------------- #
def test_format_report_no_dollar(tmp_path):
    gd = tmp_path / "grade"
    for k in range(agg.MIN_GAMES + 2):
        _write_game(gd, "nba", "R-G%d" % k,
                    _positive_clv_game(k, "R-G%d" % k))
    result = agg.aggregate(grade_dir=gd)
    report = agg.format_report(result)
    assert "$" not in report, "format_report must not contain any dollar sign"
    assert "probability" in report.lower()
    assert result["verdict"] in report


# --------------------------------------------------------------------------------------- #
# per-game slice: injected paths list                                                     #
# --------------------------------------------------------------------------------------- #
def test_injected_paths_list(tmp_path):
    gd = tmp_path / "grade"
    paths = []
    for k in range(agg.MIN_GAMES + 1):
        p = _write_game(gd, "nba", "INJ-G%d" % k,
                        _positive_clv_game(k, "INJ-G%d" % k))
        paths.append(p)
    # inject paths directly (bypassing discover_grade_files)
    result = agg.aggregate(paths=paths, min_games=agg.MIN_GAMES,
                           min_total_ticks=agg.MIN_TOTAL_TICKS)
    assert result["n_games"] == len(paths)
    assert result["verdict"] == "BEAT"


# --------------------------------------------------------------------------------------- #
# clv_series is ordered by settle_ts                                                      #
# --------------------------------------------------------------------------------------- #
def test_clv_series_ordered_by_settle_ts(tmp_path):
    gd = tmp_path / "grade"
    for k in range(agg.MIN_GAMES + 1):
        _write_game(gd, "nba", "ORD-G%d" % k,
                    _positive_clv_game(k, "ORD-G%d" % k))
    result = agg.aggregate(grade_dir=gd)
    series = result["clv_series"]
    assert len(series) >= agg.MIN_GAMES
    for i in range(len(series) - 1):
        assert series[i]["settle_ts"] <= series[i + 1]["settle_ts"], (
            "clv_series not ordered by settle_ts at index %d" % i
        )

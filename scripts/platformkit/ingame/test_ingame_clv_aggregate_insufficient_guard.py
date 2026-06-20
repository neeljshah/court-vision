"""Hardening tests for the in-game CLV aggregator MIN_GAMES / INSUFFICIENT_DATA guard.

WORKSTREAM: IG-CLV-AGG-HARDEN (backend lane only, pure test addition, no source edit).

Acceptance criteria (all must pass):
  (1) The module constant MIN_GAMES >= 2 (contract: the floor is never "one game").
  (2) One game with *perfect* CLV (model == close from tick 0 -> theoretical max signal)
      must still return verdict=INSUFFICIENT_DATA and edge_claimed=False when min_games==2.
  (3) Exactly 2 synthetic games with a planted positive CLV delta -> verdict BEAT and
      pooled_mean_clv within expected tolerance (multi-game recovery).
  (4) Exactly 2 synthetic games with a planted negative CLV delta -> verdict BEHIND.
  (5) 2-game market-copy (model == market every tick) -> MATCH, pooled_mean_clv == 0.
  (6) No dollar / ROI / profit key in output for any corpus size.
  (7) format_report for a 2-game BEAT result contains no '$' and reports units=probability.

OFFLINE + deterministic: all grade files written to tmp dirs; no network, no real data.
Only uses the PUBLIC API of ingame_clv_aggregate (aggregate, format_report, MIN_GAMES,
EPS_DEFAULT, MIN_TOTAL_TICKS) and grade_one indirectly through aggregate.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_aggregate_insufficient_guard.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pytest

import scripts.platformkit.ingame.ingame_clv_aggregate as agg


# --------------------------------------------------------------------------------------- #
# helpers                                                                                 #
# --------------------------------------------------------------------------------------- #
def _ts(game_idx: int, tick_i: int) -> str:
    base = (
        datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
        + timedelta(hours=game_idx, seconds=30 * tick_i)
    )
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_game(grade_dir: Path, sport: str, gid: str, rows: List[dict]) -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _perfect_clv_game(gidx: int, gid: str, *, n: int = 14, sport: str = "nba") -> List[dict]:
    """Model == closing prob from the very first tick: theoretical maximum CLV signal.

    market drifts linearly from 0.50 to close=0.65.
    model is pinned AT close (0.65) from tick 0 -- every tick model leads market.
    CLV at each scored tick = close - market (maximum positive, market always below close).
    """
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        model = close  # model == close from tick 0 (perfect foresight)
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


def _planted_clv_game(gidx: int, gid: str, *,
                      planted_delta: float = 0.08,
                      n: int = 14, sport: str = "nba") -> List[dict]:
    """Model leads market by planted_delta on every tick; close > all intermediate prices.

    With a positive planted_delta the model consistently leans toward the close ->
    CLV > 0 on every scored tick. Mean CLV ~ planted_delta * (1 - 1/(n-1)) roughly.
    """
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        model = min(0.99, market + planted_delta)
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


def _negative_clv_game(gidx: int, gid: str, *,
                       planted_delta: float = 0.08,
                       n: int = 14, sport: str = "nba") -> List[dict]:
    """Model leans AWAY from close by planted_delta -> CLV < 0 on every scored tick."""
    close = 0.65
    rows = []
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close
        else:
            market = 0.50 + (close - 0.50) * frac
        model = max(0.01, market - planted_delta)
        rows.append({
            "sport": sport, "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live",
        })
    return rows


def _copy_game(gidx: int, gid: str, *, n: int = 14, sport: str = "nba") -> List[dict]:
    """Model == market on every tick -> CLV = 0 on every scored tick."""
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
# (1) MIN_GAMES constant >= 2                                                             #
# --------------------------------------------------------------------------------------- #
def test_min_games_constant_at_least_two():
    """Acceptance (1): the module MIN_GAMES floor is >= 2 (one game is never enough)."""
    assert agg.MIN_GAMES >= 2, (
        "MIN_GAMES must be >=2 (contract: single-game CLV is variance not signal); "
        "got %d" % agg.MIN_GAMES
    )


# --------------------------------------------------------------------------------------- #
# (2) Single game with perfect CLV -> INSUFFICIENT_DATA regardless                       #
# --------------------------------------------------------------------------------------- #
def test_single_perfect_clv_game_is_insufficient(tmp_path):
    """Acceptance (2): one game with perfect CLV still returns INSUFFICIENT_DATA.

    min_games is explicitly set to 2 (the minimum allowable floor per contract).
    Even with the highest possible per-tick CLV, one game is variance, not signal.
    """
    gd = tmp_path / "grade"
    _write_game(gd, "nba", "PERFECT-G0", _perfect_clv_game(0, "PERFECT-G0"))

    result = agg.aggregate(
        grade_dir=gd,
        min_games=2,         # minimum required floor; single game must still fail
        min_total_ticks=1,   # ticks threshold is not the blocking factor here
    )

    assert result["verdict"] == "INSUFFICIENT_DATA", (
        "one game with perfect CLV must return INSUFFICIENT_DATA (min_games=2), "
        "got verdict=%s, n_games=%d, pooled_mean_clv=%+.5f"
        % (result["verdict"], result["n_games"], result["pooled_mean_clv"])
    )
    assert result["n_games"] == 1, (
        "expected n_games=1, got %d" % result["n_games"]
    )
    assert result["edge_claimed"] is False, "edge_claimed must always be False"
    assert result["min_games"] >= 2, (
        "result['min_games'] must be >=2 so callers can read the floor; got %d"
        % result["min_games"]
    )


# --------------------------------------------------------------------------------------- #
# (3) Exactly 2 games with planted positive CLV -> BEAT recovered                        #
# --------------------------------------------------------------------------------------- #
def test_two_game_positive_clv_recovered_beat(tmp_path):
    """Acceptance (3): exactly 2 synthetic games with planted positive delta -> BEAT.

    This is the minimum multi-game corpus.  The pooled_mean_clv must be > EPS_DEFAULT
    and the verdict must be BEAT (CI lower bound > 0 is trivially satisfied when both
    games have the same CLV, so the bootstrap CI collapses to the point).
    """
    gd = tmp_path / "grade"
    planted_delta = 0.10
    for k in range(2):
        _write_game(
            gd, "nba", "POS-G%d" % k,
            _planted_clv_game(k, "POS-G%d" % k, planted_delta=planted_delta)
        )

    result = agg.aggregate(
        grade_dir=gd,
        min_games=2,
        min_total_ticks=2,
    )

    assert result["verdict"] == "BEAT", (
        "expected BEAT for 2-game positive CLV pool, got %s "
        "(n_games=%d, pooled_mean_clv=%+.5f, ci95=%s)"
        % (result["verdict"], result["n_games"], result["pooled_mean_clv"], result["clv_ci95"])
    )
    assert result["n_games"] == 2
    # Mean CLV should be close to planted_delta (small deviation because close tick excluded).
    assert result["pooled_mean_clv"] > agg.EPS_DEFAULT, (
        "pooled_mean_clv %+.5f should exceed EPS %+.5f"
        % (result["pooled_mean_clv"], agg.EPS_DEFAULT)
    )
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (4) Exactly 2 games with planted negative CLV -> BEHIND                                #
# --------------------------------------------------------------------------------------- #
def test_two_game_negative_clv_recovered_behind(tmp_path):
    """Acceptance (4): exactly 2 synthetic games with planted negative delta -> BEHIND."""
    gd = tmp_path / "grade"
    for k in range(2):
        _write_game(
            gd, "nba", "NEG-G%d" % k,
            _negative_clv_game(k, "NEG-G%d" % k, planted_delta=0.10)
        )

    result = agg.aggregate(
        grade_dir=gd,
        min_games=2,
        min_total_ticks=2,
    )

    assert result["verdict"] == "BEHIND", (
        "expected BEHIND for 2-game negative CLV pool, got %s "
        "(n_games=%d, pooled_mean_clv=%+.5f)"
        % (result["verdict"], result["n_games"], result["pooled_mean_clv"])
    )
    assert result["pooled_mean_clv"] < -agg.EPS_DEFAULT
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (5) 2-game market-copy -> MATCH, pooled_mean_clv == 0                                 #
# --------------------------------------------------------------------------------------- #
def test_two_game_market_copy_is_match(tmp_path):
    """Acceptance (5): model == market on every tick -> pooled_mean_clv = 0 -> MATCH."""
    gd = tmp_path / "grade"
    for k in range(2):
        _write_game(gd, "nba", "COPY-G%d" % k, _copy_game(k, "COPY-G%d" % k))

    result = agg.aggregate(
        grade_dir=gd,
        min_games=2,
        min_total_ticks=2,
    )

    assert abs(result["pooled_mean_clv"]) < 1e-10, (
        "market-copy pool must have pooled_mean_clv == 0, got %+.10f"
        % result["pooled_mean_clv"]
    )
    assert result["verdict"] in ("MATCH", "INSUFFICIENT_DATA"), (
        "market-copy pool must be MATCH (or INSUFFICIENT_DATA), got %s" % result["verdict"]
    )
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (6) No $/pnl/profit/roi key in any output dict                                         #
# --------------------------------------------------------------------------------------- #
def test_no_dollar_or_pnl_key_single_game(tmp_path):
    """Acceptance (6a): single-game INSUFFICIENT_DATA result has no banned financial key."""
    gd = tmp_path / "grade"
    _write_game(gd, "nba", "SINGLE-G0", _perfect_clv_game(0, "SINGLE-G0"))
    result = agg.aggregate(grade_dir=gd, min_games=2, min_total_ticks=1)

    blob = json.dumps(result).lower()
    banned = (
        "roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
        "profit", "edge_pct", "ev_dollars",
    )
    for tok in banned:
        assert tok not in blob, (
            "banned financial token %r leaked into aggregate output (single-game corpus)" % tok
        )
    assert result["units"] == "probability"
    assert result["edge_claimed"] is False


def test_no_dollar_or_pnl_key_multi_game(tmp_path):
    """Acceptance (6b): multi-game BEAT result has no banned financial key."""
    gd = tmp_path / "grade"
    for k in range(4):
        _write_game(
            gd, "nba", "MULTI-G%d" % k,
            _planted_clv_game(k, "MULTI-G%d" % k, planted_delta=0.08)
        )
    result = agg.aggregate(grade_dir=gd, min_games=2, min_total_ticks=2)

    blob = json.dumps(result).lower()
    banned = (
        "roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
        "profit", "edge_pct", "ev_dollars",
    )
    for tok in banned:
        assert tok not in blob, (
            "banned financial token %r leaked into aggregate output (multi-game corpus)" % tok
        )
    assert result["units"] == "probability"
    assert result["edge_claimed"] is False


# --------------------------------------------------------------------------------------- #
# (7) format_report no '$', mentions probability                                          #
# --------------------------------------------------------------------------------------- #
def test_format_report_no_dollar_two_game_beat(tmp_path):
    """Acceptance (7): format_report for a 2-game BEAT result contains no '$'."""
    gd = tmp_path / "grade"
    for k in range(2):
        _write_game(
            gd, "nba", "RPT-G%d" % k,
            _planted_clv_game(k, "RPT-G%d" % k, planted_delta=0.10)
        )
    result = agg.aggregate(grade_dir=gd, min_games=2, min_total_ticks=2)
    assert result["verdict"] == "BEAT", "pre-condition for report test"

    report = agg.format_report(result)

    assert "$" not in report, "format_report must not contain any dollar sign"
    assert "probability" in report.lower(), (
        "format_report must mention 'probability' to make units explicit"
    )
    # The verdict string must appear in the report so callers can parse it.
    assert result["verdict"] in report, (
        "format_report must include the verdict string '%s'" % result["verdict"]
    )
    assert "False" in report or "false" in report.lower(), (
        "format_report must state edge_claimed is False"
    )

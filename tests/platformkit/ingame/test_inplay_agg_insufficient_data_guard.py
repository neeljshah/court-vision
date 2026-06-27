"""TH-06 -- Honesty guard: single-game in-play aggregate MUST return INSUFFICIENT_DATA.

Even when a single captured game shows "perfect" positive CLV, the pool MUST return
INSUFFICIENT_DATA because n_games=1 < MIN_GAMES. One game is variance, not signal.
No $, no roi, no pnl in output. edge_claimed always False.

Acceptance criteria (from BACKLOG TH-06):
  (1) 1 game with planted perfect CLV -> pool_verdict == INSUFFICIENT_DATA
  (2) edge_claimed == False
  (3) MIN_GAMES >= 2 (structural: any single game can NEVER bind a verdict)
  (4) no $/roi/pnl key anywhere in the output dict

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_agg_insufficient_data_guard.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.platformkit.ingame import inplay_aggregate_grade as ag


# --------------------------------------------------------------------------------------- #
# helpers                                                                                  #
# --------------------------------------------------------------------------------------- #
def _ts(i: int) -> str:
    base = datetime(2026, 6, 19, 20, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=30 * i)
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_game(grade_dir: Path, gid: str, rows: list, *, sport: str = "nba") -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _perfect_clv_game(gid: str, outcome: float, *, n: int = 14) -> list:
    """A single game where the model has "perfect" positive CLV toward the realized outcome.

    The model sits much closer to the realized outcome (1.0) than the market close on every
    tick. This is the best-case scenario for a single-game grade -- and the guard must still
    return INSUFFICIENT_DATA because n_games=1 < MIN_GAMES. Perfect CLV on ONE game is
    variance, not signal.

    close_line: the in-play close (final tick, held-out yardstick, imperfect ~0.65).
    model: aggressively leading toward the realized outcome from tick 0 (always >= 0.80).
    market: starts at 0.50, linearly drifts toward close_line.
    """
    rows = []
    close_line = 0.50 + (outcome - 0.50) * 0.30  # imperfect close (~0.65 for outcome=1)
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close_line                    # the in-play CLOSE (held-out yardstick)
        else:
            market = 0.50 + (close_line - 0.50) * frac
        # Model aggressively leads toward outcome from the start -- maximally positive CLV.
        model = min(0.99, max(0.01, outcome * 0.95))
        rows.append({
            "sport": "nba", "game_id": gid, "ts": _ts(i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live", "outcome": outcome,
        })
    return rows


# --------------------------------------------------------------------------------------- #
# TH-06 ACCEPTANCE TESTS                                                                   #
# --------------------------------------------------------------------------------------- #

def test_single_game_perfect_clv_returns_insufficient_data(tmp_path):
    """Acceptance (1): 1 game with planted perfect CLV -> INSUFFICIENT_DATA.

    Even with maximally positive CLV on every tick, a single game cannot bind a verdict.
    One game is variance, not signal. MIN_GAMES >= 2 structurally blocks any single-game
    pool from ever producing BEAT, MATCH, or BEHIND.
    """
    gd = tmp_path / "ingame_grade"
    gid = "PERFECT-G0"
    rows = _perfect_clv_game(gid, outcome=1.0, n=14)
    _write_game(gd, gid, rows)

    pool = ag.aggregate_grade(grade_dir=gd)

    assert pool["pool_verdict"] == "INSUFFICIENT_DATA", (
        "Expected INSUFFICIENT_DATA for n_games=1, got: %s (n_games=%d, pooled_mean_clv=%.4f)"
        % (pool["pool_verdict"], pool["n_games"], pool["pooled_mean_clv"])
    )
    assert pool["n_games"] == 1


def test_single_game_edge_claimed_false(tmp_path):
    """Acceptance (2): edge_claimed is always False, even with perfect single-game CLV."""
    gd = tmp_path / "ingame_grade"
    gid = "EDGE-G0"
    _write_game(gd, gid, _perfect_clv_game(gid, outcome=1.0))

    pool = ag.aggregate_grade(grade_dir=gd)

    assert pool["edge_claimed"] is False, (
        "edge_claimed must be False; got: %r" % pool["edge_claimed"]
    )


def test_min_games_structural_bound():
    """Acceptance (3): MIN_GAMES >= 2 -- structurally a single game CANNOT bind any verdict."""
    assert ag.MIN_GAMES >= 2, (
        "MIN_GAMES must be >= 2 so a single-game pool CANNOT bind a verdict; got: %d"
        % ag.MIN_GAMES
    )


def test_no_dollar_roi_pnl_key_in_output(tmp_path):
    """Acceptance (4): no $/roi/pnl key in the output dict (units = probability only)."""
    gd = tmp_path / "ingame_grade"
    gid = "NOKEY-G0"
    _write_game(gd, gid, _perfect_clv_game(gid, outcome=1.0))

    pool = ag.aggregate_grade(grade_dir=gd)

    banned_tokens = (
        "roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
        "profit", "edge_pct", "ev_dollars", "money",
    )
    blob = json.dumps(pool).lower()
    for tok in banned_tokens:
        assert tok not in blob, (
            "Banned token %r leaked into aggregate_grade output" % tok
        )

    assert pool["units"] == "probability"
    assert pool["edge_claimed"] is False


def test_exactly_min_games_minus_one_returns_insufficient_data(tmp_path):
    """Guard: MIN_GAMES - 1 games with perfect CLV -> still INSUFFICIENT_DATA."""
    gd = tmp_path / "ingame_grade"
    n_games = ag.MIN_GAMES - 1
    assert n_games >= 1, "MIN_GAMES must be >= 2 for this test to be meaningful"
    for k in range(n_games):
        gid = "ALMOST-G%d" % k
        outcome = 1.0 if k % 2 == 0 else 0.0
        _write_game(gd, gid, _perfect_clv_game(gid, outcome=outcome))

    pool = ag.aggregate_grade(grade_dir=gd)

    assert pool["pool_verdict"] == "INSUFFICIENT_DATA", (
        "Expected INSUFFICIENT_DATA for n_games=%d (< MIN_GAMES=%d), got: %s"
        % (pool["n_games"], ag.MIN_GAMES, pool["pool_verdict"])
    )


def test_empty_pool_returns_insufficient_data(tmp_path):
    """Corner: zero game files -> INSUFFICIENT_DATA, edge_claimed False, no $ key."""
    gd = tmp_path / "ingame_grade_empty"
    gd.mkdir(parents=True, exist_ok=True)

    pool = ag.aggregate_grade(grade_dir=gd)

    assert pool["pool_verdict"] == "INSUFFICIENT_DATA", pool
    assert pool["n_games"] == 0
    assert pool["edge_claimed"] is False

    banned_tokens = ("roi", "pnl", "stake", "dollar", "$", "profit")
    blob = json.dumps(pool).lower()
    for tok in banned_tokens:
        assert tok not in blob, "Banned token %r in empty pool output" % tok

"""Per-file tests for ingame.inplay_aggregate_grade -- the MULTI-GAME aggregate CLV grader.

OFFLINE + deterministic: every per-game grade file is written to a tmp dir; no network, no
predictor corpus. The grader reuses the EXISTING leak-free live_grade.grade_game ->
inplay_clv_replay per game, then pools with GAME-CLUSTERED stats. Covers the binding contracts:

  (a) A pool of MANY games where the model GENUINELY beats the close on the OUTCOME -> BEAT,
      with the game-clustered outcome-DM p < 0.05 (and a positive game-clustered CLV CI).
  (b) A pool where the model just COPIES / shrinks to the close -> MATCH (no beat): pooled
      mean_clv ~ 0 AND the outcome-DM cannot clear arm B (the market-follow trap is impossible).
  (c) TOO FEW games -> INSUFFICIENT_DATA (one/few games is variance, not signal).
  (d) NO $ field anywhere in the output (units / probability only; edge_claimed False).
  (e) The REAL on-disk single game -> INSUFFICIENT_DATA.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_aggregate_grade.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.platformkit.ingame import inplay_aggregate_grade as ag


# --------------------------------------------------------------------------------------- #
# fixtures: write per-game paired-capture jsonl files (the live_grade row schema).         #
# --------------------------------------------------------------------------------------- #
def _ts(game_idx: int, i: int) -> str:
    base = (datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc)
            + timedelta(hours=game_idx, seconds=30 * i))
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_game(grade_dir: Path, gid: str, rows: list, *, sport: str = "mlb") -> Path:
    d = grade_dir / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % gid)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=True) + "\n")
    return p


def _beat_game(gidx: int, gid: str, outcome: float, *, n: int = 14) -> list:
    """A game the model BEATS the CLOSE on OUTCOME-Brier (H1 leak-free shape, mirrors the
    canonical aggregate_clv_to_corpus fixture). The closing line (FINAL tick) is the
    held-out yardstick: informative-but-IMPERFECT, landing at ~0.65 toward the realized
    outcome, never on it. The model sits CLOSER to the realized outcome than that single
    held-out close on every scored state -> loss_close - loss_model > 0 (model beats the
    close on the outcome) AND positive per-state CLV toward the close."""
    rows = []
    close_line = 0.50 + (outcome - 0.50) * 0.30   # imperfect close (~0.65 / ~0.35)
    for i in range(n):
        frac = i / (n - 1)
        if i == n - 1:
            market = close_line                    # the in-play CLOSE (yardstick)
        else:
            market = 0.50 + (close_line - 0.50) * frac
        model = 0.50 + (outcome - 0.50) * (0.70 + 0.25 * frac)  # sharper toward outcome
        model = min(0.99, max(0.01, model))
        rows.append({
            "sport": "mlb", "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(model, 6),
            "side": "home", "state_summary": "live", "outcome": outcome,
        })
    return rows


def _copy_game(gidx: int, gid: str, outcome: float, *, n: int = 14) -> list:
    """A market-FOLLOW / shrink-to-close game: model == the held-out close_line on every
    tick. Against the single held-out close the per-state outcome-Brier d == 0 on every
    scored state -> arm B cannot clear -> MATCH (the +18.38% market-follow trap stays
    structurally impossible). The final tick == close_line is the held-out yardstick."""
    rows = []
    close_line = 0.50 + (outcome - 0.50) * 0.30
    for i in range(n):
        frac = i / (n - 1)
        market = close_line if i == n - 1 else 0.50 + (close_line - 0.50) * frac
        rows.append({
            "sport": "mlb", "game_id": gid, "ts": _ts(gidx, i),
            "market_prob": round(market, 6), "model_prob": round(close_line, 6),
            "side": "home", "state_summary": "live", "outcome": outcome,
        })
    return rows


# --------------------------------------------------------------------------------------- #
# (a) genuine multi-game BEAT -> BEAT with outcome-DM p < 0.05.                             #
# --------------------------------------------------------------------------------------- #
def test_pool_beat_when_model_beats_close_on_outcome(tmp_path):
    gd = tmp_path / "ingame_grade"
    # 6 games, mixed home win/loss, model consistently leads toward the realized outcome.
    outcomes = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    for k, o in enumerate(outcomes):
        _write_game(gd, "BEAT-G%d" % k, _beat_game(k, "BEAT-G%d" % k, o))
    pool = ag.aggregate_grade(grade_dir=gd)
    assert pool["pool_verdict"] == "BEAT", pool
    assert pool["pooled_mean_clv"] > 0.0
    assert pool["clv_ci95"][0] > 0.0          # game-clustered CI lower bound positive
    assert pool["outcome_dm_mean_diff"] > 0.0  # model beats close on outcome
    assert pool["outcome_dm_p"] < 0.05, pool
    assert pool["outcome_dm_n_clusters"] == len(outcomes)
    # CLV-over-time series present, ordered, numbers only.
    assert len(pool["clv_over_time"]) == len(outcomes)
    assert pool["clv_over_time"] == sorted(
        pool["clv_over_time"], key=lambda e: e["settle_ts"])


# --------------------------------------------------------------------------------------- #
# H2: vs_close STAYS 'UNPROVEN' even on a single-window pool BEAT; pool_verdict is reported #
# separately; a real vs_close upgrade ONLY flows through maybe_vs_close_upgrade.            #
# --------------------------------------------------------------------------------------- #
def test_vs_close_stays_unproven_even_on_pool_beat(tmp_path):
    gd = tmp_path / "ingame_grade"
    outcomes = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    for k, o in enumerate(outcomes):
        _write_game(gd, "H2-G%d" % k, _beat_game(k, "H2-G%d" % k, o))
    pool = ag.aggregate_grade(grade_dir=gd)
    # A single pooled window BEAT is a MEASUREMENT, NOT a replicated vs_close proof.
    assert pool["pool_verdict"] == "BEAT", pool
    assert pool["vs_close"] == "UNPROVEN", pool          # NEVER upgraded off one window
    # pool_verdict reported SEPARATELY, scoped as a single-window measurement token.
    assert pool["pool_verdict_label"] == "POOL_BEAT_SINGLE_WINDOW"
    # A non-BEAT pool leaves vs_close UNPROVEN too (sanity).
    gd2 = tmp_path / "ingame_grade2"
    for k, o in enumerate(outcomes):
        _write_game(gd2, "C-G%d" % k, _copy_game(k, "C-G%d" % k, o))
    pool2 = ag.aggregate_grade(grade_dir=gd2)
    assert pool2["vs_close"] == "UNPROVEN"
    assert pool2["pool_verdict_label"] == pool2["pool_verdict"]


def test_real_vs_close_upgrade_only_via_maybe_vs_close_upgrade():
    from scripts.platformkit.improve import clv_corpus_inject as ci
    # The ONLY path to a real vs_close upgrade: gate_ship AND n_rep>=2 AND clustered-DM
    # p<0.05 (all_positive). A single-window pool BEAT meets NONE of these on its own.
    good = {"dm_p": 0.01, "all_positive": True}
    assert ci.maybe_vs_close_upgrade(
        gate_ship=True, n_rep=2, close_corpus=good)["vs_close"] == "PROVEN"
    # Any missing condition -> None (vs_close stays UNPROVEN).
    assert ci.maybe_vs_close_upgrade(gate_ship=False, n_rep=2, close_corpus=good) is None
    assert ci.maybe_vs_close_upgrade(gate_ship=True, n_rep=1, close_corpus=good) is None
    assert ci.maybe_vs_close_upgrade(
        gate_ship=True, n_rep=2, close_corpus={"dm_p": 0.20, "all_positive": True}) is None


# --------------------------------------------------------------------------------------- #
# (b) market-copy pool -> MATCH (no beat, mean_clv ~ 0).                                    #
# --------------------------------------------------------------------------------------- #
def test_pool_match_when_model_copies_close(tmp_path):
    gd = tmp_path / "ingame_grade"
    outcomes = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    for k, o in enumerate(outcomes):
        _write_game(gd, "COPY-G%d" % k, _copy_game(k, "COPY-G%d" % k, o))
    pool = ag.aggregate_grade(grade_dir=gd)
    assert pool["pool_verdict"] == "MATCH", pool
    # A pure market-copy / shrink-to-close cannot BEAT the held-out close on the OUTCOME:
    # d == 0 on every scored state (model == the single held-out close), so arm B (the
    # two-arm BEAT gate) can NEVER fire -> MATCH, never a fabricated BEAT (shrink-trap).
    assert pool["outcome_dm_mean_diff"] == 0.0
    assert pool["pool_verdict"] != "BEAT"
    assert pool["vs_close"] == "UNPROVEN"


# --------------------------------------------------------------------------------------- #
# H1: the OUTCOME arm is LEAK-FREE -- the close is fixed ONCE to pairs[-1].market_prob and #
# the final close tick is EXCLUDED from the scored states. A market-copy pool -> d == 0.   #
# --------------------------------------------------------------------------------------- #
def test_outcome_losses_hold_out_close_once_and_exclude_close_tick(tmp_path):
    gd = tmp_path / "ingame_grade"
    n = 10
    p = _write_game(gd, "H1", _beat_game(0, "H1", 1.0, n=n))
    pairs = ag.lg._load_pairs(p)
    assert len(pairs) == n
    close = ag._clip01(pairs[-1]["market_prob"])   # THE held-out close

    d, cluster = ag._outcome_losses(p, 1.0)
    # n captured ticks -> n-1 scored states (the final close tick is EXCLUDED).
    assert len(d) == n - 1
    assert len(cluster) == n - 1
    assert all(c == "H1" for c in cluster)
    # The close used is CONSTANT and == pairs[-1].market_prob (fixed once, held out).
    loss_close = (close - 1.0) ** 2
    for r, dt in zip(pairs[:-1], d):
        loss_model = (ag._clip01(r["model_prob"]) - 1.0) ** 2
        assert abs(dt - (loss_close - loss_model)) < 1e-12   # same single close per state


def test_market_copy_outcome_losses_are_zero(tmp_path):
    # The shrink-trap: a market-copy game (model == the held-out close on every tick) ->
    # d == 0 on EVERY scored state -> arm B cannot fire (MATCH, never a fabricated BEAT).
    gd = tmp_path / "ingame_grade"
    p = _write_game(gd, "COPY1", _copy_game(0, "COPY1", 1.0, n=12))
    d, _cluster = ag._outcome_losses(p, 1.0)
    assert d, "expected scored states"
    assert all(abs(dt) < 1e-12 for dt in d), d   # market-copy -> no fire


# --------------------------------------------------------------------------------------- #
# (c) too few games -> INSUFFICIENT_DATA.                                                   #
# --------------------------------------------------------------------------------------- #
def test_too_few_games_insufficient(tmp_path):
    gd = tmp_path / "ingame_grade"
    # 2 beat-games -> below MIN_GAMES (5): honest "can't tell yet", never a beat.
    for k, o in enumerate([1.0, 0.0]):
        _write_game(gd, "FEW-G%d" % k, _beat_game(k, "FEW-G%d" % k, o))
    pool = ag.aggregate_grade(grade_dir=gd)
    assert pool["pool_verdict"] == "INSUFFICIENT_DATA", pool
    assert pool["n_games"] == 2


# --------------------------------------------------------------------------------------- #
# (d) NO $ field anywhere; units / probability only.                                        #
# --------------------------------------------------------------------------------------- #
def test_no_dollar_field_anywhere(tmp_path):
    gd = tmp_path / "ingame_grade"
    for k, o in enumerate([1.0, 0.0, 1.0, 1.0, 0.0, 1.0]):
        _write_game(gd, "D-G%d" % k, _beat_game(k, "D-G%d" % k, o))
    pool = ag.aggregate_grade(grade_dir=gd)
    banned = ("roi", "pnl", "stake", "bankroll", "dollar", "usd", "$",
              "profit", "edge_pct", "ev_dollars", "money")
    blob = json.dumps(pool).lower()
    for tok in banned:
        assert tok not in blob, "banned token %r leaked into output" % tok
    assert pool["units"] == "probability"
    assert pool["edge_claimed"] is False
    # format_report also carries no $.
    assert "$" not in ag.format_report(pool)


# --------------------------------------------------------------------------------------- #
# (e) the REAL on-disk single game -> INSUFFICIENT_DATA.                                     #
# --------------------------------------------------------------------------------------- #
def test_real_on_disk_single_game_insufficient():
    # Reads the actual data/cache/ingame_grade dir (today: one partial mlb game, 4 ticks).
    pool = ag.aggregate_grade()  # default DEFAULT_GRADE_DIR
    assert pool["pool_verdict"] == "INSUFFICIENT_DATA", pool
    assert pool["n_games"] < ag.MIN_GAMES
    assert pool["edge_claimed"] is False
    assert pool["units"] == "probability"

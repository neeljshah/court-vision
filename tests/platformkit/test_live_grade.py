"""Per-file tests for ingame.live_grade -- the in-game GRADE BRIDGE (P3 clause-2).

OFFLINE + deterministic: every callback is INJECTED (no network, no predictor corpus, no
real venue). Covers:
  1. capture_pair_once writes a correct paired row (atomic), aligned to the home side.
  2. capture_pair_once SKIPS (writes nothing) when the market side is missing/None or the
     model prob is missing -- a misaligned/half-missing pair is never graded.
  3. grade_game -> INSUFFICIENT_DATA for < min_ticks pairs (a single partial game).
  4. grade_game -> BEAT on a synthetic settled series where the stored model LED the market
     toward the close; market-follow stored model -> MATCH/INSUFFICIENT_DATA (never BEAT).

Run: python -m pytest tests/platformkit/test_live_grade.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.ingame import live_grade as lg


def _t(i: int) -> datetime:
    return datetime(2026, 6, 18, 1, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=60 * i)


# --------------------------------------------------------------------------------------- #
# 1. capture writes a correct paired row.                                                 #
# --------------------------------------------------------------------------------------- #
def test_capture_writes_correct_paired_row(tmp_path):
    state = {"home_score": 3, "away_score": 1, "inning": 5, "half": "top"}
    summary = lg.capture_pair_once(
        "mlb", "G1", now=_t(0),
        live_state_fn=lambda s, g: state,
        model_fn=lambda st: 0.62,
        market_fetch_fn=lambda s, g: 0.55,
        out_dir=tmp_path,
    )
    assert summary["status"] == "captured"
    assert summary["model_prob"] == 0.62
    assert summary["market_prob"] == 0.55
    assert summary["side"] == "home"
    assert summary["n_pairs_total"] == 1

    path = tmp_path / "mlb" / "G1.jsonl"
    rows = [json.loads(ln) for ln in path.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["sport"] == "mlb" and row["game_id"] == "G1"
    assert row["model_prob"] == 0.62 and row["market_prob"] == 0.55
    assert row["side"] == "home"
    assert "inning=5" in row["state_summary"] and "home_score=3" in row["state_summary"]

    # A second capture appends, not clobbers.
    lg.capture_pair_once("mlb", "G1", now=_t(1),
                         live_state_fn=lambda s, g: state,
                         model_fn=lambda st: 0.60,
                         market_fetch_fn=lambda s, g: 0.56,
                         out_dir=tmp_path)
    rows2 = [json.loads(ln) for ln in path.read_text(encoding="ascii").splitlines() if ln.strip()]
    assert len(rows2) == 2


# --------------------------------------------------------------------------------------- #
# 1b (LANE 3): the optional `extra` kwarg persists enrichment fields additively.          #
# --------------------------------------------------------------------------------------- #
def test_extra_fields_persist_additively(tmp_path):
    lg.capture_pair_once(
        "mlb", "E1", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 1, "away_score": 0},
        model_fn=lambda st: 0.60, market_fetch_fn=lambda s, g: 0.55,
        out_dir=tmp_path,
        extra={"xg_home": 1.2, "xg_away": 0.8, "espn_wp": 0.61},
    )
    path = tmp_path / "mlb" / "E1.jsonl"
    row = json.loads(path.read_text(encoding="ascii").splitlines()[0])
    assert row["xg_home"] == 1.2 and row["xg_away"] == 0.8 and row["espn_wp"] == 0.61
    # Core keys are untouched.
    assert row["model_prob"] == 0.60 and row["market_prob"] == 0.55 and row["side"] == "home"


def test_extra_cannot_overwrite_core_keys(tmp_path):
    lg.capture_pair_once(
        "mlb", "E2", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 1, "away_score": 0},
        model_fn=lambda st: 0.60, market_fetch_fn=lambda s, g: 0.55,
        out_dir=tmp_path,
        extra={"model_prob": 0.99, "side": "away", "new_field": "kept"},
    )
    path = tmp_path / "mlb" / "E2.jsonl"
    row = json.loads(path.read_text(encoding="ascii").splitlines()[0])
    assert row["model_prob"] == 0.60, "extra can never overwrite the real model_prob"
    assert row["side"] == "home", "extra can never overwrite the alignment side"
    assert row["new_field"] == "kept", "a non-colliding extra key still persists"


def test_extra_non_dict_is_a_noop(tmp_path):
    summary = lg.capture_pair_once(
        "mlb", "E3", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 1, "away_score": 0},
        model_fn=lambda st: 0.60, market_fetch_fn=lambda s, g: 0.55,
        out_dir=tmp_path, extra="not-a-dict",
    )
    assert summary["status"] == "captured"
    path = tmp_path / "mlb" / "E3.jsonl"
    row = json.loads(path.read_text(encoding="ascii").splitlines()[0])
    assert set(row.keys()) == {"sport", "game_id", "ts", "market_prob", "model_prob",
                               "side", "state_summary"}


# --------------------------------------------------------------------------------------- #
# 2. misaligned / missing pairs are SKIPPED, not graded.                                  #
# --------------------------------------------------------------------------------------- #
def test_missing_market_side_is_skipped_not_written(tmp_path):
    summary = lg.capture_pair_once(
        "nba", "G2", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 50, "away_score": 48},
        model_fn=lambda st: 0.58,
        market_fetch_fn=lambda s, g: None,  # venue could not confirm the home side
        out_dir=tmp_path,
    )
    assert summary["status"] == "skipped"
    assert summary["reason"] == "missing_market_prob"
    assert not (tmp_path / "nba" / "G2.jsonl").exists()


def test_missing_model_prob_is_skipped(tmp_path):
    summary = lg.capture_pair_once(
        "nba", "G3", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 50, "away_score": 48},
        model_fn=lambda st: None,
        market_fetch_fn=lambda s, g: 0.55,
        out_dir=tmp_path,
    )
    assert summary["status"] == "skipped"
    assert summary["reason"] == "missing_model_prob"
    assert not (tmp_path / "nba" / "G3.jsonl").exists()


def test_out_of_range_prob_is_skipped(tmp_path):
    summary = lg.capture_pair_once(
        "nba", "G4", now=_t(0),
        live_state_fn=lambda s, g: {"home_score": 1, "away_score": 0},
        model_fn=lambda st: 1.4,  # out of [0,1] -> never fabricate, skip
        market_fetch_fn=lambda s, g: 0.5,
        out_dir=tmp_path,
    )
    assert summary["status"] == "skipped"
    assert not (tmp_path / "nba" / "G4.jsonl").exists()


def test_no_live_state_is_skipped(tmp_path):
    summary = lg.capture_pair_once(
        "nba", "G5", now=_t(0),
        live_state_fn=lambda s, g: None,
        model_fn=lambda st: 0.5,
        market_fetch_fn=lambda s, g: 0.5,
        out_dir=tmp_path,
    )
    assert summary["status"] == "skipped"
    assert summary["reason"] == "no_live_state"


# --------------------------------------------------------------------------------------- #
# 3. grade_game -> INSUFFICIENT_DATA for a single partial game (< min_ticks pairs).        #
# --------------------------------------------------------------------------------------- #
def _capture_series(tmp_path, sport, gid, model_of_market, n, start=0.50, end=0.65):
    """Capture n paired ticks on a market drift start->end; model_of_market(market)->model."""
    for i in range(n):
        frac = i / (n - 1) if n > 1 else 0.0
        market = start + (end - start) * frac
        lg.capture_pair_once(
            sport, gid, now=_t(i),
            live_state_fn=lambda s, g: {"home_score": i, "away_score": 0},
            model_fn=(lambda m: (lambda st: model_of_market(m)))(market),
            market_fetch_fn=(lambda m: (lambda s, g: m))(market),
            out_dir=tmp_path,
        )
    return tmp_path / sport / ("%s.jsonl" % gid)


def test_grade_insufficient_data_single_partial_game(tmp_path):
    # 5 pairs -> 4 scored < MIN_TICKS (8): an honest can't-tell, never a beat.
    path = _capture_series(tmp_path, "nba", "P1", lambda m: min(1.0, m + 0.05), n=5)
    out = lg.grade_game(str(path))
    assert out["n_pairs"] == 5
    assert out["verdict"] == "INSUFFICIENT_DATA", out


def test_grade_missing_file_is_insufficient(tmp_path):
    out = lg.grade_game(str(tmp_path / "nope" / "X.jsonl"))
    assert out["n_pairs"] == 0
    assert out["verdict"] == "INSUFFICIENT_DATA"


# --------------------------------------------------------------------------------------- #
# 4. settled series: leading stored model BEATs; market-follow stored model never beats.  #
# --------------------------------------------------------------------------------------- #
def test_grade_leading_stored_model_beats(tmp_path):
    # The market drifts 0.50 -> 0.65 (closes at 0.65). The stored model LED it upward at
    # every tick (model = market + 0.05). Replaying those stored model_probs -> positive
    # CLV. L2 GUARD: a SINGLE game NEVER reads 'BEAT' (single-fold = artifact); the raw
    # beat is DOWNGRADED to the neutral per-game token. 'BEAT' is reserved for the gated
    # aggregate. The raw verdict is preserved separately for traceability.
    path = _capture_series(tmp_path, "nba", "B1", lambda m: min(1.0, m + 0.05), n=12)
    out = lg.grade_game(str(path))
    assert out["verdict"] == "PER_GAME_CLV_POSITIVE", out  # NOT 'BEAT' for one game
    assert out["verdict"] != "BEAT"
    assert out["raw_per_game_verdict"] == "BEAT"
    assert out["per_game"] is True
    assert out["mean_clv"] > 0
    assert out["hit_rate"] > 0.5
    assert out["n_pairs"] == 12
    assert out["side"] == "home"
    assert out["edge_claimed"] is False


def test_grade_market_follow_stored_model_never_beats(tmp_path):
    # The stored model just COPIED the market (zero edge every tick) -> can never beat.
    path = _capture_series(tmp_path, "nba", "M1", lambda m: m, n=12)
    out = lg.grade_game(str(path))
    assert out["verdict"] in ("MATCH", "INSUFFICIENT_DATA"), out
    assert out["verdict"] != "BEAT"


def test_grade_skips_halfmissing_row_in_file(tmp_path):
    # A hand-written file with one half-missing (model_prob None) row must be dropped, not
    # graded -- the load guard mirrors the capture-time alignment guard.
    path = tmp_path / "nba" / "H1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    good = {"sport": "nba", "game_id": "H1", "ts": _t(0).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "market_prob": 0.5, "model_prob": 0.55, "side": "home", "state_summary": "live"}
    bad = {"sport": "nba", "game_id": "H1", "ts": _t(1).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "market_prob": 0.5, "model_prob": None, "side": "home", "state_summary": "live"}
    path.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n", encoding="ascii")
    out = lg.grade_game(str(path))
    assert out["n_pairs"] == 1  # the half-missing row was skipped


# --------------------------------------------------------------------------------------- #
# 1c: same-SECOND ticks each retain their DISTINCT model_prob (no silent overwrite).       #
# --------------------------------------------------------------------------------------- #
def test_same_second_ticks_keep_distinct_model_probs(tmp_path):
    # Two ticks share the EXACT same ts but carry DIFFERENT model_probs. The old
    # ts-keyed lookup collapsed them (the 2nd overwrote the 1st), so the 1st tick was
    # mis-scored with the WRONG model number. The positional lookup keeps each tick's
    # own model_prob. We build a series where the model LEADS the market at the first
    # of the duplicate pair but the 2nd duplicate is market-follow: under the buggy
    # collapse the lead would be erased (replaced by the follow value) and the verdict
    # would differ. Here we assert each stored model_prob is used by checking the spy.
    ts0 = _t(0).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        # Two DISTINCT model_probs at the SAME second.
        {"sport": "nba", "game_id": "S1", "ts": ts0, "market_prob": 0.50,
         "model_prob": 0.70, "side": "home", "state_summary": "live"},
        {"sport": "nba", "game_id": "S1", "ts": ts0, "market_prob": 0.52,
         "model_prob": 0.30, "side": "home", "state_summary": "live"},
    ]
    path = tmp_path / "nba" / "S1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")

    # Spy on the replay to record the (market_prob, model_prob) pairs the harness sees.
    seen = []
    import scripts.platformkit.forward_capture.inplay_clv_replay as ic_mod
    orig = ic_mod.replay_series

    def _spy(series, model_fn, **kw):
        for i, tick in enumerate(series):
            seen.append((float(tick["prob"]), float(model_fn(tick, series[: i + 1]))))
        return orig(series, model_fn, **kw)

    import scripts.platformkit.ingame.live_grade as lg_mod
    old = lg_mod.ic.replay_series
    lg_mod.ic.replay_series = _spy
    try:
        lg.grade_game(str(path))
    finally:
        lg_mod.ic.replay_series = old

    # Each same-second tick kept its OWN distinct model_prob (no overwrite/collapse).
    assert (0.50, 0.70) in seen
    assert (0.52, 0.30) in seen

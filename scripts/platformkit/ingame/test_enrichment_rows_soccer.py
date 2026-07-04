"""Per-file tests for enrichment_rows_soccer (LANE 4: GATE A's real producer).

OFFLINE + deterministic: fixture grade_dir/fotmob_dir (tmp_path) + an injected
SoccerOutcomeResolver(finals_df=...) -- no real disk data touched.

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_enrichment_rows_soccer.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from scripts.platformkit.ingame import enrichment_rows_soccer as R
from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver


def _finals_df():
    return pd.DataFrame([
        {"event_id": "1", "date": "2026-06-29", "home_team": "Germany",
         "away_team": "Paraguay", "home_score": 2.0, "away_score": 0.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},
        {"event_id": "2", "date": "2026-06-30", "home_team": "Ivory Coast",
         "away_team": "Norway", "home_score": 1.0, "away_score": 1.0,
         "status_name": "STATUS_FULL_TIME", "completed": True},  # draw -> y=None
    ])


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _mk_grade_dir(tmp_path, ticker, rows):
    p = tmp_path / "grade" / "soccer_intl" / ("%s.jsonl" % ticker)
    _write_jsonl(p, rows)
    return tmp_path / "grade" / "soccer_intl"


def test_asof_join_basic_hit(tmp_path):
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.2, "xg_away": 0.3, "sot_diff": 2, "cutoff_min": 40.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert len(rows) == 1
    r = rows[0]
    assert r["game_id"] == ticker
    assert r["y"] == 1.0  # home (Germany) won 2-0
    assert r["model_prob"] == 0.55
    assert r["model_prob_enriched"] is not None
    assert 0.0 < r["model_prob_enriched"] < 1.0
    assert r["xg_home"] == 1.2 and r["xg_away"] == 0.3


def test_asof_future_snapshot_never_joins(tmp_path):
    """A fotmob snapshot fetched AFTER the tick ts must never join it."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:00:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=0.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        # ONLY a future snapshot exists relative to the tick -> must not join
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T13:00:00Z",
         "xg_home": 2.0, "xg_away": 0.1, "sot_diff": 5, "cutoff_min": 90.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert rows == []


def test_asof_picks_latest_eligible_not_earliest(tmp_path):
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:30:00Z",
         "market_prob": 0.6, "model_prob": 0.5, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:00:00Z",
         "xg_home": 0.1, "xg_away": 0.1, "sot_diff": 0, "cutoff_min": 10.0},
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:20:00Z",
         "xg_home": 0.9, "xg_away": 0.1, "sot_diff": 3, "cutoff_min": 35.0},
        # after the tick -- must not be picked
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T13:00:00Z",
         "xg_home": 5.0, "xg_away": 0.1, "sot_diff": 9, "cutoff_min": 90.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert len(rows) == 1
    assert rows[0]["xg_asof_min"] == 35.0
    assert rows[0]["xg_home"] == 0.9


def test_matchup_guard_no_fixture_match_is_skipped(tmp_path):
    """A fotmob sidecar for a DIFFERENT matchup must never join."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "111.jsonl", [
        {"home": "Brazil", "away": "Japan", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.0, "xg_away": 1.0, "sot_diff": 0, "cutoff_min": 40.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert rows == []


def test_draw_outcome_is_honest_skip_not_imputed(tmp_path):
    """SoccerOutcomeResolver returns None for draws (no binary home_win) --
    the producer must skip these games entirely, never impute a label."""
    ticker = "KXWCGAME-26JUN30CIVNOR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-30T12:10:00Z",
         "market_prob": 0.5, "model_prob": 0.5, "side": "home",
         "state_summary": "home_score=1.0 away_score=1.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "222.jsonl", [
        {"home": "Ivory Coast", "away": "Norway", "fetch_ts": "2026-06-30T12:05:00Z",
         "xg_home": 1.0, "xg_away": 1.0, "sot_diff": 0, "cutoff_min": 40.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert rows == []


def test_no_grade_dir_is_insufficient_floor(tmp_path):
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=tmp_path / "absent", fotmob_dir=tmp_path / "also_absent",
                        resolver=res)
    assert rows == []


def test_no_fotmob_snapshots_is_insufficient_floor(tmp_path):
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=tmp_path / "no_fotmob", resolver=res)
    assert rows == []


def test_gate_contract_shape_matches_judge_expectations(tmp_path):
    """Rows must carry the exact keys ingame_enrichment_gates.judge_enrichment
    reads: game_id, model_prob, model_prob_enriched, y."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.2, "xg_away": 0.3, "sot_diff": 2, "cutoff_min": 40.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert len(rows) == 1
    for key in ("game_id", "model_prob", "model_prob_enriched", "y"):
        assert key in rows[0]

    from scripts.platformkit.ingame import ingame_enrichment_gates as gate
    judged = gate.judge_enrichment(rows)
    assert judged["overall_verdict"] == "INSUFFICIENT_FORWARD"  # 1 game < MIN_GAMES


def test_build_rows_never_raises_on_missing_resolver_parquet(tmp_path):
    """No resolver injected + no real parquet reachable at the fake path ->
    honest [] (never raises)."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.2, "xg_away": 0.3, "sot_diff": 2, "cutoff_min": 40.0},
    ])
    inert = SoccerOutcomeResolver(finals_parquet=tmp_path / "nope.parquet")
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=inert)
    assert rows == []


def test_rows_fn_zero_arg_entry_point_never_raises():
    """rows_fn() must match the gate's RowsFn contract (zero-arg callable) and
    never raise even against whatever real data currently exists on disk."""
    rows = R.rows_fn()
    assert isinstance(rows, list)


# --------------------------------------------------------------------------- #
# LANE 2: provenance separation (live vs backfill-validation)                 #
# --------------------------------------------------------------------------- #
def test_default_provenance_is_live_no_extra_field(tmp_path):
    """Unchanged default behavior: live-provenance rows carry NO provenance
    key at all (byte-identical to the pre-LANE-2 contract)."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    fotmob_dir = tmp_path / "fotmob"
    _write_jsonl(fotmob_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.2, "xg_away": 0.3, "sot_diff": 2, "cutoff_min": 40.0},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=fotmob_dir, resolver=res)
    assert len(rows) == 1
    assert "provenance" not in rows[0]


def test_backfill_provenance_tags_rows_and_reads_backfill_dir(tmp_path):
    """provenance='backfill' reads the DIFFERENT sidecar dir passed as
    fotmob_dir and tags every row provenance='backfill_validation'."""
    ticker = "KXWCGAME-26JUN29GERPAR"
    grade_dir = _mk_grade_dir(tmp_path, ticker, [
        {"sport": "soccer_intl", "game_id": ticker, "ts": "2026-06-29T12:10:00Z",
         "market_prob": 0.6, "model_prob": 0.55, "side": "home",
         "state_summary": "home_score=1.0 away_score=0.0"},
    ])
    backfill_dir = tmp_path / "fotmob_backfill"
    _write_jsonl(backfill_dir / "999.jsonl", [
        {"home": "Germany", "away": "Paraguay", "fetch_ts": "2026-06-29T12:05:00Z",
         "xg_home": 1.2, "xg_away": 0.3, "sot_diff": 2, "cutoff_min": 40.0,
         "provenance": "fotmob_finished_reconstruction"},
    ])
    res = SoccerOutcomeResolver(finals_df=_finals_df())
    rows = R.build_rows(grade_dir=grade_dir, fotmob_dir=backfill_dir, resolver=res,
                        provenance=R.PROVENANCE_BACKFILL)
    assert len(rows) == 1
    assert rows[0]["provenance"] == "backfill_validation"


def test_backfill_provenance_default_dir_is_separate_from_live_default_dir():
    assert R.DEFAULT_FOTMOB_BACKFILL_DIR != R.DEFAULT_FOTMOB_DIR
    assert R.DEFAULT_FOTMOB_BACKFILL_DIR.name == "fotmob_backfill"
    assert R.DEFAULT_FOTMOB_DIR.name == "fotmob_live"


def test_rows_fn_backfill_zero_arg_entry_point_never_raises():
    rows = R.rows_fn_backfill()
    assert isinstance(rows, list)
    for r in rows:
        assert r.get("provenance") == "backfill_validation"

"""Tests for the UNIFIED in-game shadow logger + grader.

The shadow lane MUST be safe to run in production: it is strictly
read-only over data/live and append-only into data/cache/ingame, and it must NOT
change the production serving default. The core contract proven here:

  * DISABLED-IS-NOOP: with ``CV_INGAME_SBS`` OFF (the default), the unified
    projector that the logger shadows is a byte-identical pass-through of the
    production ``project_snapshot`` -- i.e. importing/using the unified shadow
    surface changes NOTHING about the served value. (This is the safety property
    that lets the logger run alongside the live poller.)
  * The logger writes ONLY to its own data/cache/ingame/unified_shadow_<gid>.jsonl
    and never to data/live.
  * The grader round-trips a hand-built shadow log into the three component
    verdicts (player lines / final score / win prob) without touching real data.

Runs fully offline (NBA_OFFLINE=1) and forces CPU; the SBS v2 player head load is
avoided by keeping the flag OFF for the no-op test and by exercising the grader on
a synthetic log (no model load needed).
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("NBA_OFFLINE", "1")
os.environ["NBA_FORCE_CPU"] = "1"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pytest  # noqa: E402


def _snapshot():
    return {
        "game_id": "0042500317",
        "period": 2,
        "clock": "6:00",
        "game_status": "LIVE",
        "home_team": "BOS",
        "away_team": "NYK",
        "home_score": 50,
        "away_score": 47,
        "players": [
            {"player_id": 1629029, "name": "A", "team": "BOS", "min": 18,
             "pts": 12, "reb": 4, "ast": 3, "fg3m": 2, "stl": 1, "blk": 0,
             "tov": 1, "pf": 2},
            {"player_id": 1628369, "name": "B", "team": "NYK", "min": 17,
             "pts": 9, "reb": 6, "ast": 2, "fg3m": 1, "stl": 0, "blk": 1,
             "tov": 2, "pf": 1},
        ],
    }


# --------------------------------------------------------------------------- #
# DISABLED = no-op: the shadowed unified projector is byte-identical to prod.
# This is the production-safety contract for the whole shadow lane.
# --------------------------------------------------------------------------- #
def test_unified_disabled_is_noop_identity(monkeypatch):
    """Flag OFF -> project_unified == project_snapshot, byte-for-byte.

    The logger forces the flag ON only inside its OWN process; the live serving
    path (flag OFF, default) is unchanged. We assert the unchanged-path identity
    directly here so the safety property is enforced by CI.
    """
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)
    # import AFTER clearing the flag so module-level reads see OFF
    from src.ingame.unified_projector import project_unified
    from scripts.predict_in_game import project_snapshot

    snap = _snapshot()
    assert project_unified(snap) == project_snapshot(snap)


def test_unified_disabled_does_not_build_heads(monkeypatch):
    """Flag OFF must not construct either validated head (pure pass-through)."""
    monkeypatch.delenv("CV_INGAME_SBS", raising=False)
    from src.ingame import unified_projector as up

    def _boom_player(*a, **k):
        raise AssertionError("player head built while disabled")

    def _boom_team(*a, **k):
        raise AssertionError("team head built while disabled")

    monkeypatch.setattr(up, "_project_player_lines", _boom_player)
    monkeypatch.setattr(up, "_project_team", _boom_team)
    out = up.project_unified(_snapshot())
    assert isinstance(out, list)  # project_snapshot returns a list of row dicts


# --------------------------------------------------------------------------- #
# Logger writes ONLY to its own data/cache/ingame log, never to data/live.
# --------------------------------------------------------------------------- #
def test_logger_writes_only_its_own_log(tmp_path, monkeypatch):
    import scripts.ingame.unified_shadow_logger as logger

    # point both dirs at tmp; seed a fake live snapshot
    live = tmp_path / "live"
    out = tmp_path / "cache"
    live.mkdir()
    out.mkdir()
    snap = _snapshot()
    snap_path = live / "0042500317_1700000000000.json"
    snap_path.write_text(json.dumps(snap), encoding="utf-8")
    live_mtime_before = snap_path.stat().st_mtime_ns

    # snapshot_paths_for_game binds LIVE_DIR as a default arg at def-time, so point
    # discovery at the tmp live dir explicitly (and patch the attr for good measure).
    monkeypatch.setattr(logger, "LIVE_DIR", str(live))
    monkeypatch.setattr(
        logger, "snapshot_paths_for_game",
        lambda gid, live_dir=str(live): logger.glob.glob(
            logger.os.path.join(str(live), f"{gid}_*.json")),
    )

    # Stub the unified projection so we don't need the trained v2 model / sim run.
    def _fake_unified(snapshot, **kw):
        return {
            "enabled": True,
            "schema_version": "unified-1",
            "device": "cpu",
            "player_lines": [
                {"player_id": 1629029, "name": "A", "team": "BOS", "stat": "pts",
                 "current": 12.0, "projected_final": 25.0,
                 "grid_bucket": "12min(endQ1)", "gate_decision": "v2"},
            ],
            "team": {"home_final_mean": 110.0, "away_final_mean": 104.0,
                     "margin_mean": 6.0, "total_mean": 214.0,
                     "home_win_prob": 0.72, "n_sims": 100,
                     "poss_remaining_mean": 80.0},
            "production_baseline": [],
        }

    monkeypatch.setattr(logger.up, "project_unified", _fake_unified)
    monkeypatch.setattr(logger, "_gamelog_store", lambda: None)
    monkeypatch.setattr(logger, "_load_player_projector", lambda: None)
    monkeypatch.setattr(logger, "_resolve_game_date", lambda gid, paths: None)

    n = logger.log_existing("0042500317", out_dir=str(out), skip_logged=False,
                            n_sims=10, device="cpu")
    assert n == 1

    # the only file written under out is the unified shadow log
    written = list(out.iterdir())
    assert len(written) == 1
    assert written[0].name == "unified_shadow_0042500317.jsonl"

    # the live snapshot was NOT modified
    assert snap_path.stat().st_mtime_ns == live_mtime_before
    # ... and is still byte-identical
    assert json.loads(snap_path.read_text(encoding="utf-8")) == snap

    # the log record has the three components
    rec = json.loads(written[0].read_text(encoding="utf-8").strip())
    assert rec["projections"][0]["unified_proj"] == 25.0
    assert rec["team"]["unified_home_win_prob"] == 0.72


# --------------------------------------------------------------------------- #
# Grader round-trips a synthetic log into the three component verdicts.
# --------------------------------------------------------------------------- #
def test_grader_three_components(tmp_path):
    import scripts.ingame.grade_unified_shadow as grader

    # synthetic shadow log: one endQ1 record. unified player proj is closer to the
    # actual final than production -> player UNIFIED LIFT for pts.
    rec = {
        "game_id": "0042500317",
        "grid_bucket": "12min(endQ1)",
        "gate_decision": "v2",
        "projections": [
            {"player_id": 1629029, "stat": "pts", "current": 12.0,
             "prod_proj": 30.0, "unified_proj": 24.0},  # actual=25 -> uni closer
        ],
        "team": {
            "prod_home_final": None, "prod_away_final": None,
            "prod_home_win_prob": None,
            "unified_home_final": 108.0, "unified_away_final": 103.0,
            "unified_home_win_prob": 0.65,
            "unified_margin_mean": 5.0, "unified_total_mean": 211.0,
        },
    }
    log = tmp_path / "unified_shadow_0042500317.jsonl"
    log.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    records = grader.load_shadow_log(str(log))
    assert len(records) == 1

    # actuals: player pts=25 (uni 24 beats prod 30); team final 110-104 (home win)
    player_actuals = {(1629029, "pts"): 25.0}
    player = grader.grade_player_lines(records, player_actuals)
    assert player["uni_evaluated"] == 1
    assert player["uni_wins"] == 1
    assert player["verdict"] == "PLAYER: UNIFIED LIFT"

    team = grader.grade_team(records, actual_home=110.0, actual_away=104.0,
                             home_win=1)
    # production carried no team head -> "UNIFIED ONLY" honesty verdicts
    assert team["prod_has_score"] is False
    assert team["prod_has_wp"] is False
    assert "UNIFIED ONLY" in team["score_verdict"]
    assert "UNIFIED ONLY" in team["wp_verdict"]
    # unified score MAE = mean(|108-110|, |103-104|) = 1.5
    assert team["uni_score_mae_mean"] == pytest.approx(1.5)
    # brier for p=0.65, y=1 -> (0.65-1)^2 = 0.1225
    assert team["uni_brier_mean"] == pytest.approx(0.1225)


def test_grader_winprob_vs_prod_when_prod_has_head(tmp_path):
    """If a production payload DID carry a win-prob head, the grader compares it."""
    import scripts.ingame.grade_unified_shadow as grader

    rec = {
        "game_id": "g", "grid_bucket": "30min(midQ3)", "gate_decision": "v2",
        "projections": [],
        "team": {
            "prod_home_final": None, "prod_away_final": None,
            "prod_home_win_prob": 0.50,   # uninformative prod
            "unified_home_final": None, "unified_away_final": None,
            "unified_home_win_prob": 0.80,  # confident + correct
        },
    }
    log = tmp_path / "unified_shadow_g.jsonl"
    log.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    records = grader.load_shadow_log(str(log))
    team = grader.grade_team(records, actual_home=None, actual_away=None, home_win=1)
    assert team["prod_has_wp"] is True
    # unified brier (0.8,1)=0.04 < prod brier (0.5,1)=0.25 -> unified beats prod
    assert team["wp_verdict"] == "WINPROB: UNIFIED BEATS PROD"

"""Per-file test for live_p0 (P1) + the ingame_live_state wiring that consumes it.

Principled checks (no network -- the pregame snapshot is read from a tmp dir / injected):
  (1) served number carries the PROVEN PRIOR when a pregame snapshot exists (NOT BASE).
  (2) honest, LABELLED BASE_FALLBACK when no snapshot exists (no fabricated 0.5).
  (3) leak-free: p0 comes ONLY from pregame_probs (no live score / close / outcome field).
  (4) live_state auto-supplies p0 from the provider; an explicit caller p0 still wins.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import live_p0 as lp
from scripts.platformkit.ingame import ingame_live_state as ils


def _write_snapshot(store_dir: Path, sport: str, preds: list) -> None:
    d = store_dir / sport / "latest.json"
    d.parent.mkdir(parents=True, exist_ok=True)
    env = {"schema_version": "1.0.0", "sport": sport, "status": "ok",
           "predictions": preds}
    d.write_text(json.dumps(env), encoding="utf-8")


def test_prior_carried_not_base(tmp_path):
    _write_snapshot(tmp_path, "nba", [
        {"sport": "nba", "game_id": "G1", "pregame_probs": {"home_ml": 0.62, "away_ml": 0.38}},
    ])
    res = lp.live_p0("nba", "G1", store_dir=tmp_path)
    assert res["source"] == lp.SRC_PRIOR
    assert abs(res["p0"] - 0.62) < 1e-9
    # the convenience accessor returns the float the served number will carry
    assert abs(lp.p0_for("nba", "G1", store_dir=tmp_path) - 0.62) < 1e-9


def test_missing_snapshot_is_labelled_base_not_fabricated(tmp_path):
    # no file on disk at all
    res = lp.live_p0("nba", "G1", store_dir=tmp_path)
    assert res["source"] == lp.SRC_BASE
    assert res["p0"] is None  # NOT a fabricated 0.5 prior
    assert lp.p0_for("nba", "G1", store_dir=tmp_path) is None


def test_unknown_game_is_base(tmp_path):
    _write_snapshot(tmp_path, "nba", [
        {"sport": "nba", "game_id": "OTHER", "pregame_probs": {"home_ml": 0.55}},
    ])
    res = lp.live_p0("nba", "G1", store_dir=tmp_path)
    assert res["source"] == lp.SRC_BASE and res["p0"] is None


def test_away_only_prior_resolves_home(tmp_path):
    _write_snapshot(tmp_path, "mlb", [
        {"sport": "mlb", "game_id": "G2", "pregame_probs": {"away_ml": 0.40}},
    ])
    res = lp.live_p0("mlb", "G2", store_dir=tmp_path)
    assert res["source"] == lp.SRC_PRIOR
    assert abs(res["p0"] - 0.60) < 1e-9


def test_leak_free_only_reads_pregame_probs(tmp_path):
    # a live score / close / outcome on the record must NOT become p0; only pregame_probs.
    _write_snapshot(tmp_path, "nba", [
        {"sport": "nba", "game_id": "G3", "pregame_probs": {"home_ml": 0.58},
         "live_home_prob": 0.91, "devigged_prob": 0.95, "outcome": 1.0,
         "markets": [{"side": "home", "devigged_prob": 0.95}]},
    ])
    res = lp.live_p0("nba", "G3", store_dir=tmp_path)
    assert abs(res["p0"] - 0.58) < 1e-9  # the pregame prior, NOT 0.91/0.95/1.0


def test_live_state_auto_supplies_prior_not_base():
    # an in-progress ESPN event + an injected p0_provider -> the served state carries PRIOR.
    board = {"events": [{
        "id": "G1",
        "status": {"type": {"state": "in", "shortDetail": "Q3 5:00"},
                   "period": 3, "clock": 300.0},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "SAS"}, "score": "70"},
            {"homeAway": "away", "team": {"abbreviation": "NYK"}, "score": "65"},
        ]}],
    }]}

    def fake_provider(sport, game_id):
        return 0.62 if game_id == "G1" else None

    st = ils.live_state("nba", http_get=lambda url: board, p0_provider=fake_provider)
    assert st is not None
    assert st["p0_source"] == "PRIOR"
    assert abs(st["p0"] - 0.62) < 1e-9  # NOT None / BASE


def test_live_state_labels_base_when_no_prior():
    board = {"events": [{
        "id": "G9",
        "status": {"type": {"state": "in", "shortDetail": "Q1"},
                   "period": 1, "clock": 600.0},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "AAA"}, "score": "10"},
            {"homeAway": "away", "team": {"abbreviation": "BBB"}, "score": "8"},
        ]}],
    }]}
    st = ils.live_state("nba", http_get=lambda url: board,
                        p0_provider=lambda s, g: None)
    assert st is not None
    assert st["p0_source"] == "BASE_FALLBACK" and st["p0"] is None


def test_resolved_exact_id_still_prior(tmp_path):
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "401815840", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.70}},
    ])
    res = lp.live_p0_resolved("mlb", "401815840", home="New York Yankees",
                              away="Cincinnati Reds", store_dir=tmp_path)
    assert res["source"] == lp.SRC_PRIOR and abs(res["p0"] - 0.70) < 1e-9


def test_resolved_team_match_bridges_id_namespaces(tmp_path):
    # snapshot keyed under a DIFFERENT provider id than the live feed; teams match -> PRIOR_TEAMS
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "1631929388", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.70}},
    ])
    res = lp.live_p0_resolved("mlb", "401815840", home="New York Yankees",
                              away="Cincinnati Reds", store_dir=tmp_path)
    assert res["source"] == lp.SRC_PRIOR_TEAMS
    assert abs(res["p0"] - 0.70) < 1e-9


def test_resolved_doubleheader_is_ambiguous_base(tmp_path):
    # two games, SAME teams, different ids (a doubleheader) -> ambiguous -> BASE, never guess
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "AAA1", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.70}},
        {"game_id": "AAA2", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.66}},
    ])
    res = lp.live_p0_resolved("mlb", "401815840", home="New York Yankees",
                              away="Cincinnati Reds", store_dir=tmp_path)
    assert res["source"] == lp.SRC_BASE and res["p0"] is None


def test_resolved_wrong_teams_is_base(tmp_path):
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "X", "home": "Boston Red Sox", "away": "Tampa Bay Rays",
         "pregame_probs": {"home_ml": 0.55}},
    ])
    res = lp.live_p0_resolved("mlb", "401815840", home="New York Yankees",
                              away="Cincinnati Reds", store_dir=tmp_path)
    assert res["source"] == lp.SRC_BASE and res["p0"] is None


def test_resolved_team_match_leak_free(tmp_path):
    # a live/outcome field on the record must NOT become p0 even on a team match.
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "1631929388", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.70}, "live_home_prob": 0.93, "outcome": 1.0},
    ])
    res = lp.live_p0_resolved("mlb", "401815840", home="New York Yankees",
                              away="Cincinnati Reds", store_dir=tmp_path)
    assert abs(res["p0"] - 0.70) < 1e-9  # the pregame prior, NOT 0.93 / 1.0


def test_live_state_production_resolves_by_teams(tmp_path, monkeypatch):
    # no injected provider -> production path uses live_p0_resolved against the snapshot.
    _write_snapshot(tmp_path, "mlb", [
        {"game_id": "1631929388", "home": "New York Yankees", "away": "Cincinnati Reds",
         "pregame_probs": {"home_ml": 0.70}},
    ])
    monkeypatch.setattr(lp, "DEFAULT_STORE_DIR", tmp_path)
    board = {"events": [{
        "id": "401815840",  # ESPN live id != the 10-digit snapshot id
        "status": {"type": {"state": "in", "shortDetail": "Top 5"}, "period": 5},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "NYY",
                                          "displayName": "New York Yankees"}, "score": "3"},
            {"homeAway": "away", "team": {"abbreviation": "CIN",
                                          "displayName": "Cincinnati Reds"}, "score": "2"},
        ]}],
    }]}
    st = ils.live_state("mlb", http_get=lambda url: board)
    assert st is not None
    assert st["p0_source"] == "PRIOR_TEAMS"
    assert abs(st["p0"] - 0.70) < 1e-9


def test_live_state_explicit_p0_wins():
    board = {"events": [{
        "id": "G1",
        "status": {"type": {"state": "in", "shortDetail": "Q2"},
                   "period": 2, "clock": 400.0},
        "competitions": [{"competitors": [
            {"homeAway": "home", "team": {"abbreviation": "H"}, "score": "30"},
            {"homeAway": "away", "team": {"abbreviation": "A"}, "score": "28"},
        ]}],
    }]}
    # caller passes p0 explicitly -> it wins; the provider is not consulted.
    st = ils.live_state("nba", http_get=lambda url: board, p0=0.71,
                        p0_provider=lambda s, g: 0.40)
    assert st["p0_source"] == "CALLER"
    assert abs(st["p0"] - 0.71) < 1e-9

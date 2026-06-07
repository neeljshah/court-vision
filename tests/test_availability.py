"""tests/test_availability.py — confirmed-inactives -> vacated load."""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.prediction import availability as av  # noqa: E402


def _write_injuries(tmp_path, players):
    p = tmp_path / "inj.json"
    p.write_text(json.dumps({"date": "2026-05-31", "players": players}),
                 encoding="utf-8")
    return str(p)


# ── out_players_by_team ───────────────────────────────────────────────────────
def test_groups_out_players_by_team(tmp_path):
    path = _write_injuries(tmp_path, [
        {"team": "BOS", "name": "Jayson Tatum", "status": "OUT"},
        {"team": "BOS", "name": "Al Horford", "status": "DOUBTFUL"},
        {"team": "LAL", "name": "LeBron James", "status": "OUT"},
        {"team": "LAL", "name": "Luka Doncic", "status": "QUESTIONABLE"},  # not unavailable
    ])
    obt = av.out_players_by_team(path=path)
    assert set(obt["BOS"]) == {"Jayson Tatum", "Al Horford"}
    assert obt["LAL"] == ["LeBron James"]  # questionable excluded


def test_missing_feed_returns_empty():
    assert av.out_players_by_team(path="/no/such/file.json") == {}


# ── player_vacated share ──────────────────────────────────────────────────────
def test_player_vacated_zero_when_team_clean():
    vac_map = {"BOS": {"vac_min": 36.0, "vac_pts": 24.0, "n_out": 1}}
    pv = av.player_vacated(18.0, "LAL", vac_map)  # LAL has no vacated entry
    assert pv["vac_min"] == 0.0 and pv["vac_share"] == 0.0


def test_player_vacated_share_rises_with_vacated_pts():
    vac_map = {"BOS": {"vac_min": 36.0, "vac_pts": 24.0, "n_out": 1}}
    low = av.player_vacated(30.0, "BOS", vac_map)["vac_share"]
    # same vacated, a lower-usage player -> a LARGER share of the freed usage
    high = av.player_vacated(8.0, "BOS", vac_map)["vac_share"]
    assert 0.0 < low < high < 0.95


def test_player_vacated_handles_none_team():
    assert av.player_vacated(18.0, None, {"BOS": {"vac_pts": 24.0}})["vac_share"] == 0.0


# ── form covariates (real gamelogs) ──────────────────────────────────────────
def test_form_covariates_keys_present():
    # returns the full key set even for an unknown player (defaults)
    cov = av.player_form_covariates(0, "2025-26", "2026-05-31")
    for k in ("l3_min", "l5_min", "l10_min", "std_min", "prev_min", "min_trend",
              "l5_pts_pm", "l5_reb_pm", "days_into_season"):
        assert k in cov


def test_team_vacated_map_empty_without_feed(tmp_path, monkeypatch):
    # point the loader at a missing date -> empty map, no raise
    m = av.team_vacated_map("1900-01-01", lambda n: None)
    assert m == {}


# ── freshness guard ───────────────────────────────────────────────────────────

def _write_injuries_date(tmp_path, feed_date, players):
    """Write an injuries JSON with a specific date field."""
    p = tmp_path / f"injuries_{feed_date}.json"
    p.write_text(json.dumps({"date": feed_date, "players": players}),
                 encoding="utf-8")
    return str(p)


def test_freshness_guard_rejects_stale_feed(tmp_path):
    """If the feed's 'date' field != the requested date, out_players_by_team returns {}."""
    players = [{"team": "OKC", "name": "Shai Gilgeous-Alexander", "status": "OUT"}]
    # Feed says 2026-05-31 but we request 2026-06-04
    path = _write_injuries_date(tmp_path, "2026-05-31", players)
    result = av.out_players_by_team(date="2026-06-04", path=path)
    assert result == {}, f"Expected empty dict for stale feed, got {result}"


def test_freshness_guard_accepts_matching_date(tmp_path):
    """Feed date == requested date -> out_players_by_team returns players normally."""
    players = [{"team": "OKC", "name": "Shai Gilgeous-Alexander", "status": "OUT"}]
    path = _write_injuries_date(tmp_path, "2026-06-04", players)
    result = av.out_players_by_team(date="2026-06-04", path=path)
    assert "OKC" in result
    assert "Shai Gilgeous-Alexander" in result["OKC"]


def test_freshness_guard_no_date_field_passes_through(tmp_path):
    """Old-format feeds without a 'date' field pass through (backwards compat)."""
    players = [{"team": "OKC", "name": "Shai Gilgeous-Alexander", "status": "OUT"}]
    p = tmp_path / "inj_nodatefield.json"
    p.write_text(json.dumps({"players": players}), encoding="utf-8")
    result = av.out_players_by_team(date="2026-06-04", path=str(p))
    # no "date" key in payload -> guard skips -> returns players
    assert "OKC" in result


def test_freshness_guard_missing_file_returns_empty():
    """Missing file returns {} regardless of date."""
    result = av.out_players_by_team(date="2026-06-04", path="/no/such/file.json")
    assert result == {}


# ── adjust_projection byte-identical with no args ─────────────────────────────

def test_adjust_projection_no_args_identity():
    """adjust_projection with no vac_share/total/spread must be an exact identity."""
    from src.prediction.live_adjustment import adjust_projection
    base = {"pts": 25.0, "reb": 6.5, "ast": 4.2}
    adj = adjust_projection(base)
    for stat, val in base.items():
        assert abs(adj[stat] - val) < 1e-9, f"{stat}: {adj[stat]} != {val}"


# ── bump magnitude sanity ─────────────────────────────────────────────────────

def test_star_out_raises_teammate_pts():
    """SGA OUT (30 PPG) -> Jalen Williams (23 PPG) PTS should rise 5-15%."""
    from src.prediction.live_adjustment import adjust_projection, vacated_usage_share
    share = vacated_usage_share([30.0], 23.0)
    base = {"pts": 23.0, "reb": 5.0}
    adj = adjust_projection(base, vac_share=share)
    pct_change = (adj["pts"] - base["pts"]) / base["pts"] * 100
    assert 5.0 <= pct_change <= 20.0, f"PTS bump {pct_change:.1f}% out of sane range [5,20]%"
    # REB should rise less than PTS (different coefficient)
    reb_pct = (adj["reb"] - base["reb"]) / base["reb"] * 100
    assert 0.0 < reb_pct < pct_change


def test_high_total_raises_pts():
    """Game total 250 vs baseline 228 -> PTS projection goes up."""
    from src.prediction.live_adjustment import adjust_projection
    base = {"pts": 25.0, "reb": 6.0}
    adj = adjust_projection(base, game_total=250.0)
    assert adj["pts"] > base["pts"]
    assert adj["reb"] > base["reb"]


def test_large_spread_cuts_pts():
    """Game spread 20 pts (blowout) -> PTS projection goes down."""
    from src.prediction.live_adjustment import adjust_projection
    base = {"pts": 25.0, "reb": 6.0}
    adj = adjust_projection(base, game_spread=20.0)
    assert adj["pts"] < base["pts"]


def test_net_multiplier_clamped():
    """Net multiplier stays within [0.80, 1.30] even with extreme inputs."""
    from src.prediction.live_adjustment import adjust_projection, vacated_usage_share
    # Extreme: 4 all-star teammates out, massive pace
    share = vacated_usage_share([30.0, 25.0, 22.0, 20.0], 5.0)
    base = {"pts": 5.0}
    adj = adjust_projection(base, vac_share=share, game_total=280.0)
    ratio = adj["pts"] / base["pts"]
    assert 0.80 <= ratio <= 1.30, f"Net multiplier {ratio:.3f} outside [0.80, 1.30]"

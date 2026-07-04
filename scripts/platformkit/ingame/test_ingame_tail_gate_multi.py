"""Per-file tests for ingame_tail_gate_multi (pre-registered forward-only judging).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_gate_multi.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_tail_gate_multi as gm


def _band(verdict, n_games=30):
    return {"venue_verdict": verdict, "n_games": n_games, "n_ticks": n_games * 5}


def test_confirmed_forward_ships_review(tmp_path):
    def scan_fn(since=None):
        if since is None:
            return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
        return {
            "bands": {"[0.10,0.20)": _band("VENUE_UNDERPRICES"),
                     "[0.65,0.80)": _band("CALIBRATED")},
            "n_games_resolved": 40, "n_games_graded": 40,
        }
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("soccer_intl", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "SHIP_REVIEW"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["edge_claimed"] is False
    assert doc["hypotheses"][0]["forward_verdict"] == "CONFIRMED_FORWARD"


def test_all_rejected_forward_rejects(tmp_path):
    def scan_fn(since=None):
        if since is None:
            return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
        return {
            "bands": {"[0.10,0.20)": _band("VENUE_OVERPRICES"),
                     "[0.65,0.80)": _band("VENUE_UNDERPRICES")},
            "n_games_resolved": 40, "n_games_graded": 40,
        }
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("soccer_intl", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "REJECT"


def test_no_forward_games_pending(tmp_path):
    def scan_fn(since=None):
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("tennis", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    assert headline["n"] == 0


def test_pre_registration_never_scores_discovery_sample(tmp_path):
    """A game before the pre-registration stamp must NEVER appear in the
    forward scan's bands (enforced by ingame_tail_scan_multi's since filter --
    here we simulate the scan_fn honoring 'since' by returning EMPTY forward
    bands even though discovery has a confirmable signal)."""
    calls = []

    def scan_fn(since=None):
        calls.append(since)
        if since is None:
            return {"bands": {"[0.10,0.20)": _band("VENUE_UNDERPRICES")},
                    "n_games_resolved": 50, "n_games_graded": 50}
        # forward (since=pre_registered_at): nothing captured yet
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    out = tmp_path / "verdict.json"
    headline = gm.run_gate_for_sport("tennis", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["hypotheses"][0]["forward_verdict"] == "INSUFFICIENT_FORWARD"
    assert doc["hypotheses"][0]["discovery_band_reference_only"]["venue_verdict"] == \
        "VENUE_UNDERPRICES"
    # both a discovery (since=None) and a forward (since=stamp) call were made
    assert None in calls and gm.PRE_REGISTERED_AT in calls


def test_run_gate_all_never_raises(monkeypatch):
    def _boom(sport, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(gm, "scan_sport", _boom)
    # run_gate_for_sport wraps scan_sport calls in try/except internally via
    # the default scan_fn lambda, so a raising scan_sport must not propagate.
    headlines = gm.run_gate_all(sports=["tennis"])
    assert headlines[0]["verdict"] == "PENDING_FORWARD"


# --------------------------------------------------------------------------- #
# LANE 5: per-sport pre-registration stamps (wnba/npb/kbo)                    #
# --------------------------------------------------------------------------- #
def test_existing_sports_keep_original_stamp():
    """tennis/soccer_intl/soccer must keep the ORIGINAL global stamp untouched."""
    for sport in ("tennis", "soccer_intl", "soccer"):
        assert gm.pre_registered_at_for(sport) == "2026-07-04T00:00:00Z"
    assert gm.PRE_REGISTERED_AT == "2026-07-04T00:00:00Z"


def test_new_sports_get_fresh_later_stamp():
    """wnba/npb/kbo must be pre-registered at a FRESH stamp, strictly later
    than the original sports' stamp (before any of their capture exists)."""
    for sport in ("wnba", "npb", "kbo"):
        stamp = gm.pre_registered_at_for(sport)
        assert stamp == "2026-07-04T12:00:00Z"
        assert stamp > gm.pre_registered_at_for("tennis")


# --------------------------------------------------------------------------- #
# LANE 1: nba pre-registration stamp (NBA-season-open-safe future date)       #
# --------------------------------------------------------------------------- #
def test_nba_gets_season_open_safe_future_stamp():
    """nba must be pre-registered at an October 2026 stamp -- strictly later
    than every other sport's stamp, and before the 2026-27 NBA season tips
    off, so it is trivially forward-only (no NBA in-play tick can predate
    it)."""
    stamp = gm.pre_registered_at_for("nba")
    assert stamp == "2026-10-01T00:00:00Z"
    assert stamp > gm.pre_registered_at_for("tennis")
    assert stamp > gm.pre_registered_at_for("wnba")


def test_nba_gate_uses_its_own_stamp_as_forward_filter(tmp_path):
    calls = []

    def scan_fn(since=None):
        calls.append(since)
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    out = tmp_path / "nba_verdict.json"
    headline = gm.run_gate_for_sport("nba", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    assert headline["n"] == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["pre_registered_at"] == "2026-10-01T00:00:00Z"
    assert None in calls and "2026-10-01T00:00:00Z" in calls
    assert "2026-07-04T00:00:00Z" not in calls
    assert "2026-07-04T12:00:00Z" not in calls


def test_unknown_sport_falls_back_to_default_stamp():
    assert gm.pre_registered_at_for("some_future_sport") == gm.PRE_REGISTERED_AT


def test_new_sport_gate_uses_its_own_stamp_as_forward_filter(tmp_path):
    """run_gate_for_sport(wnba) with no explicit pre_registered_at must call
    scan_fn(since=<wnba's own stamp>), not the tennis/soccer stamp."""
    calls = []

    def scan_fn(since=None):
        calls.append(since)
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    out = tmp_path / "wnba_verdict.json"
    headline = gm.run_gate_for_sport("wnba", scan_fn=scan_fn, verdict_out=out)
    assert headline["verdict"] == "PENDING_FORWARD"
    assert headline["n"] == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["pre_registered_at"] == "2026-07-04T12:00:00Z"
    assert None in calls and "2026-07-04T12:00:00Z" in calls
    assert "2026-07-04T00:00:00Z" not in calls


def test_new_sports_start_pending_forward_n_zero(tmp_path):
    for sport in ("wnba", "npb", "kbo"):
        def scan_fn(since=None):
            return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}
        out = tmp_path / ("%s_verdict.json" % sport)
        headline = gm.run_gate_for_sport(sport, scan_fn=scan_fn, verdict_out=out)
        assert headline["verdict"] == "PENDING_FORWARD"
        assert headline["n"] == 0
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["sport"] == sport
        assert doc["pre_registered_at"] == "2026-07-04T12:00:00Z"
        assert doc["edge_claimed"] is False


def test_existing_sport_output_unchanged_when_stamp_not_passed_explicitly(tmp_path):
    """Regression: calling run_gate_for_sport for an EXISTING sport without an
    explicit pre_registered_at must still resolve to the original stamp (the
    refactor's default-lookup path must not silently change existing sports'
    forward-filter behavior)."""
    calls = []

    def scan_fn(since=None):
        calls.append(since)
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    out = tmp_path / "tennis_verdict.json"
    gm.run_gate_for_sport("tennis", scan_fn=scan_fn, verdict_out=out)
    assert "2026-07-04T00:00:00Z" in calls
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["pre_registered_at"] == "2026-07-04T00:00:00Z"


# --------------------------------------------------------------------------- #
# LANE 1 regression: adding nba must not change ANY existing sport's stamp or #
# verdict-doc shape -- byte-identical output for every pre-existing sport.    #
# --------------------------------------------------------------------------- #
def test_existing_sports_stamp_and_output_unchanged_by_nba_addition(tmp_path):
    def scan_fn(since=None):
        return {"bands": {}, "n_games_resolved": 0, "n_games_graded": 0}

    expected_stamps = {
        "tennis": "2026-07-04T00:00:00Z",
        "soccer_intl": "2026-07-04T00:00:00Z",
        "soccer": "2026-07-04T00:00:00Z",
        "wnba": "2026-07-04T12:00:00Z",
        "npb": "2026-07-04T12:00:00Z",
        "kbo": "2026-07-04T12:00:00Z",
    }
    for sport, expected in expected_stamps.items():
        assert gm.pre_registered_at_for(sport) == expected
        out = tmp_path / ("%s_verdict.json" % sport)
        headline = gm.run_gate_for_sport(sport, scan_fn=scan_fn, verdict_out=out)
        assert headline["verdict"] == "PENDING_FORWARD"
        assert headline["n"] == 0
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc["sport"] == sport
        assert doc["pre_registered_at"] == expected
        assert doc["edge_claimed"] is False
        assert doc["verdict"] == "PENDING_FORWARD"


def test_sports_list_includes_nba_alongside_all_prior_sports():
    """SPORTS must contain every previously-registered sport UNCHANGED, plus
    nba newly appended -- no existing sport removed or reordered away."""
    for sport in ("tennis", "soccer_intl", "soccer", "wnba", "npb", "kbo"):
        assert sport in gm.SPORTS
    assert "nba" in gm.SPORTS

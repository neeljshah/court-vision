"""predict_service.test_produce_mlb_slate -- ws3-mlb-slate-resolver-regression.

Acceptance criteria (per workstream spec):
  (a) >=10-game ESPN-displayName MLB slate -> >2 distinct home_ml, status='ok', records>0.
  (b) Fully-unresolvable slate -> status='unavailable' with honest reason note.
  (c) No '$' / 'pnl' / 'roi' key in any prediction record.

All tests run OFFLINE (synthetic feeds + resolver-wired fake predict_fn; no corpus needed).

Run (per-file only):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_produce_mlb_slate.py -q

INVARIANTS: ASCII only; no $ field; stale-never-green; <=300 LOC; per-file only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.produce import produce_sport
from domains.mlb.team_name_resolver import resolve as _resolve_mlb

# ---------------------------------------------------------------------------
# Shared fixtures: slate, probs, feeds, predict_fns
# ---------------------------------------------------------------------------

# Exact ESPN displayName forms as the live schedule feed emits them (>=10 games).
_ESPN_SLATE: List[tuple] = [
    ("New York Yankees",    "Boston Red Sox"),
    ("Los Angeles Dodgers", "San Francisco Giants"),
    ("Houston Astros",      "Texas Rangers"),
    ("Atlanta Braves",      "Miami Marlins"),
    ("Chicago Cubs",        "St. Louis Cardinals"),
    ("Minnesota Twins",     "Cleveland Guardians"),
    ("Toronto Blue Jays",   "Baltimore Orioles"),
    ("Seattle Mariners",    "Oakland Athletics"),
    ("Tampa Bay Rays",      "Kansas City Royals"),
    ("San Diego Padres",    "Colorado Rockies"),
]
assert len(_ESPN_SLATE) >= 10

# Synthetic Elo-derived probs: distinct per resolved corpus key, none within
# 0.01 of the init-collapse constant 0.5345 (confirms no fabricated flat prior).
_PROB: Dict[str, float] = {
    "NYY": 0.6200, "LAD": 0.5950, "HOU": 0.5720, "ATL": 0.5500,
    "CHC": 0.5200, "MIN": 0.4950, "TOR": 0.4720, "SEA": 0.4530,
    "TAM": 0.4360, "SDG": 0.4200,
}
_INIT_PROB = 0.5345  # the P0 collapse value -- synthetic predictor never emits this


def _espn_predict_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
    """Resolver-wired fake predict_fn: mirrors MLBPredictor._resolve_or_upper path.

    Resolves ESPN displayNames -> corpus keys via team_name_resolver.resolve().
    Returns {} (honest empty, no fabrication) for any unresolvable name.
    """
    h_key = _resolve_mlb(home)
    a_key = _resolve_mlb(away)
    if h_key is None or a_key is None:
        return {}  # unresolvable: no prediction emitted
    return {"pregame": {"p_home_win": round(_PROB.get(h_key, 0.5200), 4)}}


def _null_predict_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
    return {}  # all-unresolvable simulation


def _empty_odds(sport: str) -> Dict[str, Any]:
    return {"events": [], "as_of": "2026-06-20T00:00:00+00:00"}


def _espn_sched(sport: str) -> List[Dict[str, Any]]:
    return [{"game_id": f"{a}@{h}", "home": h, "away": a, "tipoff": None}
            for h, a in _ESPN_SLATE]


def _unknown_sched(sport: str) -> List[Dict[str, Any]]:
    pairs = [
        ("Exhibition Team Alpha", "Practice Squad Beta"),
        ("Unknown City Widgets",  "Mystery State Sluggers"),
        ("Ghost League Aces",     "Phantom Park Tigers"),
        ("Fabricated FC United",  "Made-Up Bay Stars"),
    ]
    return [{"game_id": f"{a}@{h}", "home": h, "away": a, "tipoff": None}
            for h, a in pairs]


def _ok_env():
    return produce_sport("mlb", schedule_feed=_espn_sched,
                         odds_feed=_empty_odds, predict_fn=_espn_predict_fn)


def _unresolvable_env():
    return produce_sport("mlb", schedule_feed=_unknown_sched,
                         odds_feed=_empty_odds, predict_fn=_null_predict_fn)


# ---------------------------------------------------------------------------
# (a) ESPN-name slate: status='ok', records>0, >2 distinct home_ml, no collapse
# ---------------------------------------------------------------------------

class TestEspnNameSlateDistinctProbs:
    """(a): ESPN display names resolve -> distinct calibrated probs, status='ok'."""

    def test_status_ok_records_nonempty(self) -> None:
        env = _ok_env()
        assert env.status == "ok", "status=%r note=%r" % (env.status, env.note)
        assert len(env.predictions) > 0, "envelope has 0 records"

    def test_more_than_two_distinct_home_ml(self) -> None:
        env = _ok_env()
        assert env.status == "ok", "status=%r" % env.status
        probs = [round(r.pregame_probs.get("home_ml", 0.0), 4)
                 for r in env.predictions if r.pregame_probs.get("home_ml") is not None]
        distinct = len(set(probs))
        assert distinct > 2, (
            ">2 distinct home_ml required; got %d distinct: %r" % (distinct, sorted(set(probs))))

    def test_all_ten_games_resolved(self) -> None:
        env = _ok_env()
        assert env.status == "ok", "status=%r" % env.status
        n = len(env.predictions)
        assert n == len(_ESPN_SLATE), "expected %d records, got %d" % (len(_ESPN_SLATE), n)

    def test_no_collapse_value_in_probs(self) -> None:
        """No game emits the init-rating collapse prob (0.5345 +/- 0.005)."""
        env = _ok_env()
        probs = [r.pregame_probs.get("home_ml") for r in env.predictions
                 if r.pregame_probs.get("home_ml") is not None]
        for p in probs:
            assert abs(p - _INIT_PROB) > 0.005, (
                "collapse prob 0.5345 emitted: prob=%.4f slate=%r" % (p, probs))


# ---------------------------------------------------------------------------
# (b) Genuinely unresolvable slate -> status='unavailable' with honest reason
# ---------------------------------------------------------------------------

class TestFlatSlateYieldsUnavailable:
    """(b): unresolvable slate -> status='unavailable'."""

    def test_status_unavailable(self) -> None:
        env = _unresolvable_env()
        assert env.status == "unavailable", "status=%r note=%r" % (env.status, env.note)

    def test_note_nonempty(self) -> None:
        env = _unresolvable_env()
        assert env.note, "unavailable envelope must carry a non-empty reason note"

    def test_never_ok(self) -> None:
        env = _unresolvable_env()
        assert env.status != "ok", "status must never be 'ok' for an unresolvable slate"


# ---------------------------------------------------------------------------
# (c) No '$' / 'pnl' / 'roi' key in any record
# ---------------------------------------------------------------------------

class TestHonestyNoMoneyFields:
    """(c): no $ / pnl / roi field in any prediction record."""

    def test_no_dollar_pnl_roi_in_records(self) -> None:
        env = _ok_env()
        assert env.status == "ok", "precondition: status='ok'"
        for rec in env.predictions:
            for key in rec.to_dict():
                ks = str(key).lower()
                assert "$" not in ks, "banned key '$' in record %s: %r" % (rec.game_id, key)
                assert "pnl" not in ks, "banned key 'pnl' in record %s: %r" % (rec.game_id, key)
                assert "roi" not in ks, "banned key 'roi' in record %s: %r" % (rec.game_id, key)
            for key in (rec.pregame_probs or {}):
                assert "$" not in str(key), "$ in pregame_probs key %r" % key

    def test_honest_note_present_no_edge_claim(self) -> None:
        env = _ok_env()
        hn = env.honest_note or ""
        assert len(hn) > 0, "honest_note must be non-empty"
        assert "roi" not in hn.lower(), "honest_note must not mention roi"

    def test_edge_claimed_absent_or_false(self) -> None:
        env = _ok_env()
        for rec in env.predictions:
            ec = rec.to_dict().get("edge_claimed")
            assert ec is None or ec is False or ec == 0, (
                "edge_claimed must be absent or False; got %r" % ec)


# ---------------------------------------------------------------------------
# Resolver sanity: every ESPN name in the slate maps to the right corpus key
# ---------------------------------------------------------------------------

_RESOLVER_CASES = [
    ("New York Yankees",    "NYY"), ("Boston Red Sox",       "BOS"),
    ("Los Angeles Dodgers", "LAD"), ("San Francisco Giants", "SFG"),
    ("Houston Astros",      "HOU"), ("Texas Rangers",        "TEX"),
    ("Atlanta Braves",      "ATL"), ("Miami Marlins",        "MIA"),
    ("Chicago Cubs",        "CHC"), ("St. Louis Cardinals",  "STL"),
    ("Minnesota Twins",     "MIN"), ("Cleveland Guardians",  "CLE"),
    ("Toronto Blue Jays",   "TOR"), ("Baltimore Orioles",    "BAL"),
    ("Seattle Mariners",    "SEA"), ("Oakland Athletics",    "OAK"),
    ("Tampa Bay Rays",      "TAM"), ("Kansas City Royals",   "KAN"),
    ("San Diego Padres",    "SDG"), ("Colorado Rockies",     "COL"),
]


class TestEspnNameResolution:
    """Resolver maps every ESPN displayName in the slate to the correct corpus key."""

    @pytest.mark.parametrize("espn_name,expected", _RESOLVER_CASES)
    def test_resolve(self, espn_name: str, expected: str) -> None:
        got = _resolve_mlb(espn_name)
        assert got == expected, "%r -> expected %r, got %r" % (espn_name, expected, got)

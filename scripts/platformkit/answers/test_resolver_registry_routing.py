"""Per-file test: 3 coverage_stress routing/composition fixes in
resolver_registry.py --
  1. matchup winprob: "between X and Y" splitting + entity-based sport
     inference (no sport token in the query text).
  2. injury_report: "is X injured" phrasing extracts a PLAYER (not team),
     and an honest "not on current injury report" ok answer when the store
     is built but the player has zero rows in it.
  3. compound-question splitting on explicit conjunction markers only.

Run: python -m pytest scripts/platformkit/answers/test_resolver_registry_routing.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.answers import resolver_registry as R

# ---------------------------------------------------------------------------
# FIX 1 -- matchup splitting + sport inference
# ---------------------------------------------------------------------------


def test_between_and_splits_matchup():
    assert R._split_matchup(R._entity_from_query(
        "Who wins between Ashleigh Barty and Mirra Andreeva?")) == ("Ashleigh Barty", "Mirra Andreeva")
    assert R._split_matchup(R._entity_from_query(
        "Who wins between Norwich and Bournemouth?")) == ("Norwich", "Bournemouth")


def test_vs_splitting_still_works_no_regression():
    assert R._split_matchup("Lakers vs Celtics") == ("Lakers", "Celtics")
    assert R._split_matchup("Lakers @ Celtics") == ("Celtics", "Lakers")


def _profiles_df(rows):
    return pd.DataFrame(rows, columns=["entity_id", "entity_name", "sport"])


def test_sport_inference_overrides_default_when_entities_agree(monkeypatch):
    df = _profiles_df([
        (1, "Ashleigh Barty", "tennis"), (2, "Mirra Andreeva", "tennis"),
        (3, "Boston Celtics", "nba"),
    ])
    monkeypatch.setattr(R._ask, "load_profiles", lambda *a, **k: df)
    captured = {}

    def fake_dispatch(sport, home, away, ingame_state=None):
        captured["sport"] = sport
        return {"status": "ok", "category": "winprob", "sport": sport}

    monkeypatch.setattr(R._winprob, "dispatch", fake_dispatch)
    out = R.resolve("Who wins between Ashleigh Barty and Mirra Andreeva?", sport="nba")
    assert captured["sport"] == "tennis"
    assert out["status"] == "ok"


def _fake_dispatch(captured):
    def _dispatch(sport, home, away, ingame_state=None):
        captured["sport"] = sport
        return {"status": "ok"}
    return _dispatch


def test_sport_inference_conflict_falls_back_to_given_sport(monkeypatch):
    df = _profiles_df([(1, "Ashleigh Barty", "tennis"), (2, "Norwich", "soccer")])
    monkeypatch.setattr(R._ask, "load_profiles", lambda *a, **k: df)
    captured = {}
    monkeypatch.setattr(R._winprob, "dispatch", _fake_dispatch(captured))
    R.resolve("Who wins between Ashleigh Barty and Norwich?", sport="nba")
    assert captured["sport"] == "nba"  # conflicting inference -> honest fallback, not a guess


def test_sport_inference_absent_data_falls_back_no_regression(monkeypatch):
    monkeypatch.setattr(R._ask, "load_profiles", lambda *a, **k: pd.DataFrame())
    captured = {}
    monkeypatch.setattr(R._winprob, "dispatch", _fake_dispatch(captured))
    R.resolve("who wins Lakers vs Celtics", sport="nba")
    assert captured["sport"] == "nba"


# ---------------------------------------------------------------------------
# FIX 2 -- "is X injured" routing
# ---------------------------------------------------------------------------


def test_is_x_injured_classifies_and_extracts_player():
    assert R.classify("Is Grayson Allen injured right now?") == "injury_report"
    assert R._injury_player_from_query("Is Grayson Allen injured right now?") == "Grayson Allen"
    assert R.classify("is Justin Turner injured") == "injury_report"
    assert R._injury_player_from_query("is Justin Turner injured") == "Justin Turner"


def test_is_x_injured_player_listed_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(R._edge_facts.FS, "FACTS_DIR", tmp_path)
    path = R._edge_facts.FS.path_for("injury", "nba")
    R._edge_facts.FS.append_new(path, [
        {"player_name": "Grayson Allen", "team": "Phoenix Suns", "status": "OUT", "detail": "ankle",
         "report_date": "2026-07-16", "source": "espn", "source_url": "u1",
         "fetched_at": R._edge_facts.FS.utc_now_iso()},
    ], lambda r: (r["player_name"], r["fetched_at"]))
    out = R.resolve("Is Grayson Allen injured right now?", sport="nba")
    assert out["status"] == "ok"
    assert out["category"] == "edge_facts_injury_report"
    assert out["rows"][0]["status"] == "OUT"


def test_is_x_injured_player_not_in_store_is_honest_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(R._edge_facts.FS, "FACTS_DIR", tmp_path)
    path = R._edge_facts.FS.path_for("injury", "mlb")
    R._edge_facts.FS.append_new(path, [
        {"player_name": "Someone Else", "team": "LAD", "status": "OUT", "detail": "d",
         "report_date": "2026-07-16", "source": "espn", "source_url": "u1",
         "fetched_at": R._edge_facts.FS.utc_now_iso()},
    ], lambda r: (r["player_name"], r["fetched_at"]))
    out = R.resolve("is Justin Turner injured", sport="mlb")
    assert out["status"] == "ok"
    assert "not found on the current injury report" in out["note"]
    assert out["player"] == "Justin Turner"


def test_is_x_injured_no_store_is_no_data(monkeypatch, tmp_path):
    monkeypatch.setattr(R._edge_facts.FS, "FACTS_DIR", tmp_path)
    out = R.resolve("is Justin Turner injured", sport="mlb")
    assert out["status"] == "no_data"


def test_injury_report_team_phrasing_regression_unaffected(monkeypatch, tmp_path):
    """'injury report for <team>' still extracts to team= (old lead-in path),
    unaffected by the new is-X-injured player= path."""
    monkeypatch.setattr(R._edge_facts.FS, "FACTS_DIR", tmp_path)
    path = R._edge_facts.FS.path_for("injury", "nba")
    R._edge_facts.FS.append_new(path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-07-16", "source": "espn", "source_url": "u1",
         "fetched_at": R._edge_facts.FS.utc_now_iso()},
    ], lambda r: (r["player_name"], r["fetched_at"]))
    out = R.resolve("injury report for Atlanta Hawks", sport="nba")
    assert out["status"] == "ok"
    assert out["team"] == "Atlanta Hawks"
    assert out["player"] is None


# ---------------------------------------------------------------------------
# FIX 3 -- compound-question splitting
# ---------------------------------------------------------------------------


def test_split_compound_and_also_marker():
    parts = R._split_compound(
        "ok two things -- what's Chelsea's home strength, and also who wins if they play Everton")
    assert parts is not None and len(parts) == 2
    assert "Chelsea" in parts[0]
    assert "Everton" in parts[1]


def test_split_compound_numbered_marker():
    parts = R._split_compound("1) what is Julius Randle's ppg 2) what is Trae Young's ppg")
    assert parts == ["what is Julius Randle's ppg", "what is Trae Young's ppg"]


def test_split_compound_none_for_combined_conditional_no_regression():
    q = ("What's the combined win probability if both Jamal Murray and Julius Randle are out "
         "for their respective teams in a Nuggets vs Bucks game?")
    assert R._split_compound(q) is None  # no marker -> single-question path, honest no_data downstream


def test_split_compound_none_for_plain_player_question_no_regression():
    """A bare player question is never mistaken for a compound one --
    same routing as before this fix (player_stat family)."""
    assert R._split_compound("What is Julius Randle's offensive rebound rate?") is None
    assert R.classify("What is Julius Randle's offensive rebound rate?") == "player_stat"


# ---------------------------------------------------------------------------
# ADDED SCOPE (2026-07-19) -- new-family classify() reroute, ahead of
# ranking/concept_rating, without regressing the shipped ranking behavior
# those two categories already own.
# ---------------------------------------------------------------------------
def test_new_claims_families_reroute_to_verified_claims():
    for q in ("who are the best shooters in the nba this season",
              "defense adjusted true shooting leaders",
              "best lineup on-off net rating players this season"):
        assert R.classify(q) == "verified_claims", q


def test_new_claims_reroute_does_not_regress_existing_ranking_routes():
    for q in ("top 5 gravity", "top shooters", "gravity leaders"):
        assert R.classify(q) == "ranking", q


def test_resolve_compound_envelope_ok_if_any_part_ok(monkeypatch):
    def fake_classify(q):
        return "player_stat" if "Randle" in q else "mechanism_effect"

    monkeypatch.setattr(R, "classify", fake_classify)

    def fake_lookup(query, sport, window):
        if "Randle" in query:
            return {"status": "ok", "row": pd.Series({
                "sources": "s", "window": "w", "entity_name": "Julius Randle", "attribute": "ppg",
                "raw_value": 20.0, "percentile": 50.0, "rating_2k": 62.0, "n": 10.0, "status": "DESCRIPTIVE",
            })}
        return {"status": "no_entity"}

    monkeypatch.setattr(R._ask, "answer_lookup", fake_lookup)
    monkeypatch.setattr(R, "mechanism_effect",
                        lambda sport, mechanism: {"status": "not_supported", "category": "mechanism_effect"})

    out = R.resolve("1) Julius Randle ppg 2) some unmapped mechanism thing", sport="nba")
    assert out["status"] == "ok"
    assert out["category"] == "compound_question"
    assert len(out["parts"]) == 2
    assert out["parts"][0]["status"] == "ok"

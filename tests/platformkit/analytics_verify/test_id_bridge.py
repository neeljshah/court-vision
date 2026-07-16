"""Proof that the two PRODUCTION writers (clv_ledger.record_bet and
grade_predictions.grade_one_pred) now emit a joinable canonical event key, and
that id_bridge.build joins them at >=95% on new-style rows.

Per-file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/analytics_verify/test_id_bridge.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.analytics_verify import id_bridge as _ib
from scripts.platformkit.paper import grade_predictions as _gp

# One canonical fixture game, shared by both writers.
_SPORT, _DATE = "nba", "2026-06-20"
_HOME, _AWAY = "Golden State Warriors", "Los Angeles Lakers"
_MATCHUP = f"{_AWAY}@{_HOME}"  # ESPN 'Away@Home'


# "run line" is a market BOTH writers can produce AND market_resolver grades
# (moneyline has no resolver group, which is why the real graded ledger has none).
_MARKET, _GROUP, _LINE = "run line", "Run line", -1.5


def _write_clv_bet(path, matchup=_MATCHUP, **kw):
    """Place a real clv bet via the production writer, into *path*."""
    return _clv.record_bet(
        sport=_SPORT, matchup=matchup, side="home", taken_book="fanduel",
        taken_decimal=2.0, model_prob=0.55, market=_MARKET,
        event_id=kw.get("event_id", "CLV1"), game_date=_DATE, path=path)


def _grade_pred(home=_HOME, away=_AWAY, matchup=_MATCHUP, **kw):
    """Grade a real prediction twin via the production writer path."""
    row = {
        "sport": _SPORT, "matchup": matchup, "group": _GROUP,
        "selection": f"{home} {_LINE}", "line": _LINE, "fair_odds": 2.0,
        "event_id": kw.get("event_id", "PRED1"),
        "commence_time": _DATE + "T02:00Z",
    }
    final = {"home": home, "away": away, "home_score": 110, "away_score": 99}
    return _gp.grade_one_pred(row, final)


def test_both_writers_emit_matching_ckey(tmp_path):
    """The two independent writers stamp the SAME ckey for one game+market,
    even though bet_id and pred_key are unrelated schemes."""
    bet = _write_clv_bet(tmp_path / "clv.jsonl")
    twin = _grade_pred()
    assert bet["ckey"] and twin["ckey"]
    assert bet["ckey"] == twin["ckey"], (bet["ckey"], twin["ckey"])


def test_bridge_joins_new_rows_at_95pct(tmp_path):
    """End-to-end: write N new-style rows from BOTH real writers over the same
    games, then id_bridge.build must join >=95% of graded rows to a clv bet."""
    clv_path = tmp_path / "clv_ledger.jsonl"
    graded_path = tmp_path / "paper_predictions_graded.jsonl"
    out = tmp_path / "id_bridge.jsonl"

    n = 20
    graded_rows = []
    for i in range(n):
        home, away = f"Home Team {i}", f"Away Team {i}"
        matchup = f"{away}@{home}"
        _write_clv_bet(clv_path, matchup=matchup, event_id=f"CLV{i}")
        twin = _grade_pred(home=home, away=away, matchup=matchup,
                           event_id=f"PRED{i}")
        assert twin is not None and twin["ckey"], "writer must stamp a ckey"
        graded_rows.append(twin)
    with graded_path.open("w", encoding="utf-8") as fh:
        for r in graded_rows:
            fh.write(json.dumps(r) + "\n")

    stats = _ib.build(graded=graded_path, clv=clv_path, out=out)
    assert stats["graded_settled"] == n
    assert stats["join_rate"] >= 0.95, stats
    assert stats["rows_appended"] >= n

    # every emitted bridge row is a real pred_key<->bet_id link with no edge claim.
    for r in _ib.iter_jsonl(out):
        assert r["pred_key"] and r["bet_id"] and r["ckey"]
        assert r["edge_claimed"] is False
        assert r["match_basis"] == "ckey"  # both sides carried a stamped ckey


def test_build_is_idempotent(tmp_path):
    clv_path = tmp_path / "clv.jsonl"
    graded_path = tmp_path / "graded.jsonl"
    out = tmp_path / "b.jsonl"
    _write_clv_bet(clv_path)
    twin = _grade_pred()
    with graded_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(twin) + "\n")
    # clv event_id differs from graded, but ckey matches -> one join.
    first = _ib.build(graded=graded_path, clv=clv_path, out=out)
    second = _ib.build(graded=graded_path, clv=clv_path, out=out)
    assert first["rows_appended"] >= 1
    assert second["rows_appended"] == 0  # idempotent: no dup lines


def test_row_ckey_prefers_stamped():
    row = {"ckey": "already|stamped|key", "sport": "nba"}
    assert _ib.row_ckey(row, "clv") == "already|stamped|key"


def test_apply_bridge_join_enriches_graded(tmp_path):
    """attribution's consumption path: a graded bet bridged to a clv bet inherits
    that clv row's claim_tags + CLV and is stamped _ckey_bet_id."""
    bridge = tmp_path / "b.jsonl"
    bridge.write_text(json.dumps(
        {"pred_key": "PK1", "bet_id": "B1", "ckey": "k"}) + "\n", encoding="utf-8")
    bets = [
        {"source": "graded", "pred_key": "PK1", "bet_id": None,
         "claim_tags": None, "clv_pct": None, "clv_is_proxy": False},
        {"source": "clv", "pred_key": None, "bet_id": "B1",
         "claim_tags": {"card9": True}, "clv_pct": 3.2, "clv_is_proxy": False},
    ]
    rate = _ib.apply_bridge_join(bets, bridge)
    assert rate == 1.0
    g = bets[0]
    assert g["_ckey_bet_id"] == "B1"
    assert g["claim_tags"] == {"card9": True}
    assert g["clv_pct"] == 3.2

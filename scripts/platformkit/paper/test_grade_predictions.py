"""Per-file test: scripts.platformkit.paper.grade_predictions + finals_fetch.

Uses synthetic predictions + an injected final fetch -- NEVER touches the network or
the real ledgers.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.paper import finals_fetch as ff
from scripts.platformkit.paper import grade_predictions as gp


def _write_preds(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_parse_summary_only_when_final():
    final_payload = {"header": {"competitions": [{
        "status": {"type": {"state": "post", "completed": True}},
        "competitors": [
            {"homeAway": "home", "score": "9", "team": {"displayName": "Cincinnati Reds"}},
            {"homeAway": "away", "score": "1", "team": {"displayName": "New York Mets"}},
        ]}]}}
    out = ff.parse_summary(final_payload)
    assert out is not None
    assert out["home_score"] == 9 and out["away_score"] == 1
    # In-progress -> None (never fabricated).
    inprog = json.loads(json.dumps(final_payload))
    inprog["header"]["competitions"][0]["status"]["type"] = {"state": "in", "completed": False}
    assert ff.parse_summary(inprog) is None


def test_grade_predictions_settles_resolvable_markets(tmp_path: Path):
    preds = tmp_path / "preds.jsonl"
    graded = tmp_path / "graded.jsonl"
    _write_preds(preds, [
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "Game total", "selection": "Over 6.5", "line": 6.5, "fair_odds": 1.9},
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "First 5 innings", "selection": "Cincinnati Reds ML",
         "line": None, "fair_odds": 1.8},  # segment -> ungradable
        {"sport": "mlb", "event_id": "E2", "matchup": "A@B",
         "group": "Game total", "selection": "Over 5", "line": 5, "fair_odds": 1.9},  # no final
    ])

    def fake_fetch(eid, sport):
        if eid == "E1":
            return {"state": "post", "home": "Cincinnati Reds", "away": "New York Mets",
                    "home_score": 9, "away_score": 1}
        return None  # E2 not final

    res = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    assert res["n_graded_now"] == 1  # only the Game total on the final game
    assert res["n_win"] == 1
    assert res["n_ungradable_market"] == 1  # the segment market
    assert res["n_no_final"] == 1  # E2

    rows = [json.loads(l) for l in graded.read_text(encoding="utf-8").splitlines() if l]
    assert len(rows) == 1
    g = rows[0]
    assert g["outcome"] == "win"
    assert g["stake_units"] == 1.0
    assert g["unit_result"] == round((1.9 - 1.0) * 1.0, 6)
    assert g["executed"] is False
    assert g["clv_status"] == "no_close"
    for k in ("pnl", "roi", "profit", "dollars"):
        assert k not in g


def test_grade_predictions_uses_close_proxy_for_moneyline_selection(tmp_path: Path):
    """A moneyline-selection row (selection == home/away team) with a captured
    close_proxy gets real CLV -- clv_status='proxy' (honest, excluded from the
    true-close aggregate), never 'no_close' when a real proxy close exists."""
    preds = tmp_path / "preds.jsonl"
    graded = tmp_path / "graded.jsonl"
    _write_preds(preds, [
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "1X2", "selection": "Cincinnati Reds", "line": None, "fair_odds": 1.8,
         "close_proxy": {"close_decimal_home": 1.75, "close_decimal_away": 2.20,
                         "fair_close_prob": None}},
    ])

    def fake_fetch(eid, sport):
        return {"state": "post", "home": "Cincinnati Reds", "away": "New York Mets",
                "home_score": 9, "away_score": 1}

    res = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    assert res["n_graded_now"] == 1
    rows = [json.loads(l) for l in graded.read_text(encoding="utf-8").splitlines() if l]
    g = rows[0]
    assert g["clv_status"] == "proxy"
    assert g["clv_is_proxy"] is True
    assert g["clv_pct"] is not None
    assert g["beat_close"] is not None
    for k in ("pnl", "roi", "profit", "dollars"):
        assert k not in g


def test_grade_predictions_degenerate_proxy_stays_no_close(tmp_path: Path):
    """A booksum<1 (arb/degenerate) close_proxy raises in the Shin devig -- caught,
    never crashes the grading pass, falls back to no_close (mirrors _log_unpriced's
    own devig guard). Real production data has hit this shape."""
    preds = tmp_path / "preds.jsonl"
    graded = tmp_path / "graded.jsonl"
    _write_preds(preds, [
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "1X2", "selection": "Cincinnati Reds", "line": None, "fair_odds": 1.8,
         "close_proxy": {"close_decimal_home": 1.75, "close_decimal_away": 9.0,
                         "fair_close_prob": None}},  # booksum = 1/1.75+1/9.0 < 1
    ])

    def fake_fetch(eid, sport):
        return {"state": "post", "home": "Cincinnati Reds", "away": "New York Mets",
                "home_score": 9, "away_score": 1}

    res = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    assert res["n_graded_now"] == 1  # never crashes the pass
    rows = [json.loads(l) for l in graded.read_text(encoding="utf-8").splitlines() if l]
    g = rows[0]
    assert g["clv_status"] == "no_close"
    assert g["clv_pct"] is None


def test_grade_predictions_no_proxy_stays_no_close(tmp_path: Path):
    """A derived-market row (no close_proxy ever captured) is unchanged: no_close."""
    preds = tmp_path / "preds.jsonl"
    graded = tmp_path / "graded.jsonl"
    _write_preds(preds, [
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "Game total", "selection": "Over 6.5", "line": 6.5, "fair_odds": 1.9,
         "close_proxy": None},
    ])

    def fake_fetch(eid, sport):
        return {"state": "post", "home": "Cincinnati Reds", "away": "New York Mets",
                "home_score": 9, "away_score": 1}

    res = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    rows = [json.loads(l) for l in graded.read_text(encoding="utf-8").splitlines() if l]
    g = rows[0]
    assert g["clv_status"] == "no_close"
    assert g["clv_is_proxy"] is False
    assert g["clv_pct"] is None
    assert g["beat_close"] is None


def test_grade_predictions_idempotent(tmp_path: Path):
    preds = tmp_path / "preds.jsonl"
    graded = tmp_path / "graded.jsonl"
    _write_preds(preds, [
        {"sport": "mlb", "event_id": "E1", "matchup": "New York Mets@Cincinnati Reds",
         "group": "Game total", "selection": "Over 6.5", "line": 6.5, "fair_odds": 1.9},
    ])

    def fake_fetch(eid, sport):
        return {"state": "post", "home": "Cincinnati Reds", "away": "New York Mets",
                "home_score": 9, "away_score": 1}

    r1 = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    assert r1["n_graded_now"] == 1
    r2 = gp.grade_predictions(preds, graded, final_fetch=fake_fetch)
    assert r2["n_graded_now"] == 0  # already graded
    assert r2["n_skip_already"] == 1
    rows = [l for l in graded.read_text(encoding="utf-8").splitlines() if l]
    assert len(rows) == 1  # no duplicate twin

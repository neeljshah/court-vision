"""Per-file test: scripts.platformkit.paper.pnl_series (equity curve from ledgers).

Uses synthetic temp ledgers -- NEVER touches the real data/frontend ledgers.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.paper import pnl_series as ps


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _settled(clv_path: Path, graded_path: Path):
    # CLV ledger: an open row (ignored), a win and a loss settled.
    _write_jsonl(clv_path, [
        {"status": "open", "sport": "mlb", "matchup": "A@B", "unit_result": None},
        {"status": "settled", "sport": "mlb", "matchup": "A@B", "outcome": "win",
         "unit_result": 1.17, "settled_at": "2026-06-17T23:01:00+00:00",
         "clv_pct": None, "clv_status": "no_close"},
        {"status": "settled", "sport": "mlb", "matchup": "C@D", "outcome": "loss",
         "unit_result": -1.0, "settled_at": "2026-06-18T23:01:00+00:00",
         "clv_pct": None, "clv_status": "no_close"},
    ])
    # Graded predictions: one win, one void (None -> excluded).
    _write_jsonl(graded_path, [
        {"status": "settled", "sport": "nba", "outcome": "win", "unit_result": 0.9,
         "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "sport": "nba", "outcome": "void", "unit_result": None,
         "settled_at": "2026-06-18T22:30:00+00:00"},
    ])


def test_collect_settled_filters_and_orders(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    _settled(clv, graded)
    rows = ps.collect_settled(clv, graded)
    # 3 settled with numeric unit_result (open + void excluded).
    assert len(rows) == 3
    # Time-ordered by settled_at.
    ts = [r["settled_at"] for r in rows]
    assert ts == sorted(ts)


def test_build_series_cumulative_and_daily(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    _settled(clv, graded)
    rows = ps.collect_settled(clv, graded)
    payload = ps.build_series(rows, start_units=100.0)
    s = payload["summary"]
    # total = 1.17 - 1.0 + 0.9 = 1.07
    assert s["total_units"] == round(1.17 - 1.0 + 0.9, 6)
    assert s["current_units"] == round(100.0 + 1.07, 6)
    assert s["n_bets"] == 3
    assert s["n_win"] == 2 and s["n_loss"] == 1
    assert s["win_rate"] == round(2 / 3, 6)
    # All clv_pct None -> INSUFFICIENT_DATA, never a fabricated number.
    assert s["mean_clv_pct_or_INSUFFICIENT"] == "INSUFFICIENT_DATA"
    assert payload["edge_claimed"] is False
    # Daily buckets present.
    days = {d["day"] for d in payload["daily"]}
    assert "2026-06-17" in days and "2026-06-18" in days
    # Final point's balance matches current_units.
    assert payload["points"][-1]["balance_units"] == s["current_units"]


def test_build_and_write_units_only(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    out = tmp_path / "pnl.json"
    bkp = tmp_path / "bank.json"
    _settled(clv, graded)
    payload = ps.build_and_write(
        clv_path=clv, graded_pred_path=graded, output_path=out,
        bankroll_path=bkp, update_bankroll=True)
    assert out.exists()
    raw = json.loads(out.read_text(encoding="utf-8"))
    # No banned $ keys in the written curve.
    blob = json.dumps(raw)
    for k in ('"pnl"', '"roi"', '"profit"', '"dollars"'):
        assert k not in blob
    # Bankroll synced to the same current_units.
    bank = json.loads(bkp.read_text(encoding="utf-8"))
    assert bank["current_units"] == payload["summary"]["current_units"]


def test_build_and_write_refuses_canonical_path(tmp_path: Path):
    """RETIRED writer: pnl_series must HARD-REFUSE to clobber the canonical file so the
    supervised bankroll_daemon stays the SINGLE writer (no dual-writer schema split)."""
    import pytest
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    _settled(clv, graded)
    with pytest.raises(ValueError):
        ps.build_and_write(
            clv_path=clv, graded_pred_path=graded,
            output_path=ps.CANONICAL_OUTPUT, bankroll_path=tmp_path / "b.json")
    # The canonical file was NOT created/touched by this module.
    assert ps.CANONICAL_OUTPUT.name == "paper_pnl_series.json"
    assert ps.DEFAULT_OUTPUT.name == "paper_pnl_series_modelview.json"


def test_select_one_position_per_market(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    clv.write_text("", encoding="utf-8")
    # Both sides of one two-way market logged as model views; only the higher-prob
    # side (Over, 0.6) must reach the curve -- not both.
    _write_jsonl(graded, [
        {"status": "settled", "channel": "paper_prediction", "event_id": "E1",
         "group": "Game total", "line": 6.5, "selection": "Over 6.5",
         "model_prob": 0.6, "outcome": "win", "unit_result": 0.9,
         "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "channel": "paper_prediction", "event_id": "E1",
         "group": "Game total", "line": 6.5, "selection": "Under 6.5",
         "model_prob": 0.4, "outcome": "loss", "unit_result": -1.0,
         "settled_at": "2026-06-18T22:00:00+00:00"},
    ])
    rows = ps.collect_settled(clv, graded)
    assert len(rows) == 1
    assert rows[0]["selection"] == "Over 6.5"


def test_per_team_two_sided_markets_are_distinct(tmp_path: Path):
    """A per-team total (home O/U + away O/U at one line) is TWO markets, not one.

    The same (event_id, group, line) tuple covers four selections that are really two
    distinct markets (home total, away total). Each team's market keeps ONE pick (its
    higher-prob side); the two teams are NOT collapsed together. Symmetric game markets
    (game total, run line) stay one-per-(event,group,line) -- one side, no both-sides.
    """
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    clv.write_text("", encoding="utf-8")
    ev = "G1"
    home, away = "Atlanta Braves", "San Francisco Giants"
    _write_jsonl(graded, [
        # PER-TEAM "Team total": home O/U AND away O/U at the SAME line 4.5.
        {"status": "settled", "event_id": ev, "group": "Team total", "line": 4.5,
         "home_team": home, "away_team": away,
         "selection": "Atlanta Braves Over 4.5", "model_prob": 0.62,
         "outcome": "win", "unit_result": 0.9, "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "event_id": ev, "group": "Team total", "line": 4.5,
         "home_team": home, "away_team": away,
         "selection": "Atlanta Braves Under 4.5", "model_prob": 0.38,
         "outcome": "loss", "unit_result": -1.0, "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "event_id": ev, "group": "Team total", "line": 4.5,
         "home_team": home, "away_team": away,
         "selection": "San Francisco Giants Over 4.5", "model_prob": 0.45,
         "outcome": "loss", "unit_result": -1.0, "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "event_id": ev, "group": "Team total", "line": 4.5,
         "home_team": home, "away_team": away,
         "selection": "San Francisco Giants Under 4.5", "model_prob": 0.55,
         "outcome": "win", "unit_result": 0.95, "settled_at": "2026-06-18T22:00:00+00:00"},
        # SYMMETRIC "Game total": Over/Under one shared line -> ONE market, one side.
        {"status": "settled", "event_id": ev, "group": "Game total", "line": 8.5,
         "home_team": home, "away_team": away, "selection": "Over 8.5",
         "model_prob": 0.6, "outcome": "win", "unit_result": 0.9,
         "settled_at": "2026-06-18T22:00:00+00:00"},
        {"status": "settled", "event_id": ev, "group": "Game total", "line": 8.5,
         "home_team": home, "away_team": away, "selection": "Under 8.5",
         "model_prob": 0.4, "outcome": "loss", "unit_result": -1.0,
         "settled_at": "2026-06-18T22:00:00+00:00"},
    ])
    rows = ps.collect_settled(clv, graded)
    sels = sorted(r["selection"] for r in rows)
    # 3 positions: home total pick, away total pick, one game-total side.
    assert len(rows) == 3, sels
    # Each team's total survives as ITS OWN market (its higher-prob side).
    assert "Atlanta Braves Over 4.5" in sels       # home: 0.62 > 0.38 Under
    assert "San Francisco Giants Under 4.5" in sels  # away: 0.55 > 0.45 Over
    # Symmetric game total keeps exactly ONE side (no both-sides double count).
    game_total = [r for r in rows if r["group"] == "Game total"]
    assert len(game_total) == 1 and game_total[0]["selection"] == "Over 8.5"


def test_select_positions_keys_distinguish_team_but_not_symmetric():
    """Unit-level: team token only splits the per-team group, never the symmetric one."""
    from scripts.platformkit.paper import pnl_normalize as nz
    rows = [
        {"event_id": "G1", "group": "Team total", "line": 4.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "AAA Over 4.5"},
        {"event_id": "G1", "group": "Team total", "line": 4.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "AAA Under 4.5"},
        {"event_id": "G1", "group": "Team total", "line": 4.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "BBB Over 4.5"},
        {"event_id": "G1", "group": "Team total", "line": 4.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "BBB Under 4.5"},
        {"event_id": "G1", "group": "Game total", "line": 8.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "Over 8.5"},
        {"event_id": "G1", "group": "Game total", "line": 8.5,
         "home_team": "AAA", "away_team": "BBB", "selection": "Under 8.5"},
    ]
    per_team = nz._per_team_groups(rows)
    assert per_team == {"Team total"}  # auto-detected, Game total excluded
    keys = {nz._position_key(r, per_team) for r in rows}
    # 2 per-team keys (one per team) + 1 symmetric key = 3 distinct markets.
    assert len(keys) == 3
    assert ("G1", "Team total", 4.5, "AAA") in keys
    assert ("G1", "Team total", 4.5, "BBB") in keys
    assert ("G1", "Game total", 8.5) in keys


def test_clv_symmetric_two_way_collapses_to_one_position():
    """A symmetric two-way CLV market (home ML AND away ML) -> ONE position.

    The CLV ledger schema is (sport, matchup, side, ...) with no event_id/group/line.
    Both sides recorded (the bug) must collapse to the single model-backed side
    (highest model_prob), never both -- a duplicate same-side row collapses too.
    """
    from scripts.platformkit.paper import pnl_normalize as nz
    rows = [
        {"sport": "nba", "matchup": "A@B", "side": "home", "model_prob": 0.586,
         "outcome": "loss", "settled_at": "2026-06-18T23:00:00+00:00"},
        {"sport": "nba", "matchup": "A@B", "side": "away", "model_prob": 0.414,
         "outcome": "win", "settled_at": "2026-06-18T23:00:00+00:00"},
        # a duplicate of the backed (home) side on the same day -> still one position
        {"sport": "nba", "matchup": "A@B", "side": "home", "model_prob": 0.586,
         "outcome": "loss", "settled_at": "2026-06-18T23:05:00+00:00"},
    ]
    sel = nz.select_clv_positions(rows)
    assert len(sel) == 1
    assert sel[0]["side"] == "home"  # the model-backed side (0.586 > 0.414)


def test_clv_per_team_two_sided_markets_stay_distinct():
    """A genuine per-team CLV market (distinct LINE) is NOT collapsed into one.

    Two real markets on the same matchup/day that carry a different `line` (e.g. each
    team's own total) keep their own (sport, matchup, line, day) key -- so they survive
    as TWO distinct positions, while a symmetric same-line two-way still collapses.
    """
    from scripts.platformkit.paper import pnl_normalize as nz
    rows = [
        # market 1: home team total (line 4.5) -- both sides logged
        {"sport": "mlb", "matchup": "A@B", "side": "home", "line": 4.5,
         "model_prob": 0.62, "outcome": "win", "settled_at": "2026-06-18T23:00:00+00:00"},
        {"sport": "mlb", "matchup": "A@B", "side": "away", "line": 4.5,
         "model_prob": 0.38, "outcome": "loss", "settled_at": "2026-06-18T23:00:00+00:00"},
        # market 2: a DIFFERENT line on the same matchup/day -> distinct market
        {"sport": "mlb", "matchup": "A@B", "side": "home", "line": 9.5,
         "model_prob": 0.55, "outcome": "loss", "settled_at": "2026-06-18T23:00:00+00:00"},
    ]
    sel = nz.select_clv_positions(rows)
    lines = sorted(r["line"] for r in sel)
    assert lines == [4.5, 9.5]   # two distinct markets, neither dropped
    # the same-line two-way collapsed to its model-backed (home, 0.62) side
    m1 = [r for r in sel if r["line"] == 4.5]
    assert len(m1) == 1 and m1[0]["side"] == "home"


def test_clv_curve_reconciles_to_one_per_market(tmp_path: Path):
    """The equity curve / n_bets reconcile to the ONE-position-per-market set.

    Two settled rows that are the two sides of one symmetric two-way market collapse to
    a single position; collect_settled (which now applies select_clv_positions to the
    CLV ledger) yields ONE row, so the curve sums the model-backed side only.
    """
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    graded.write_text("", encoding="utf-8")
    _write_jsonl(clv, [
        {"status": "settled", "sport": "nba", "matchup": "A@B", "side": "home",
         "model_prob": 0.586, "taken_decimal": 1.95, "outcome": "loss",
         "unit_result": -1.0, "settled_at": "2026-06-18T23:00:00+00:00"},
        {"status": "settled", "sport": "nba", "matchup": "A@B", "side": "away",
         "model_prob": 0.414, "taken_decimal": 2.60, "outcome": "win",
         "unit_result": 1.6, "settled_at": "2026-06-18T23:00:00+00:00"},
    ])
    rows = ps.collect_settled(clv, graded)
    assert len(rows) == 1                       # one position, not two
    assert rows[0]["side"] == "home"            # the model-backed side
    s = ps.build_series(rows, start_units=100.0)["summary"]
    assert s["n_bets"] == 1
    # curve sums ONLY the model-backed (home, loss) side at flat 1u -> -1.0
    assert s["total_units"] == -1.0
    assert s["current_units"] == 99.0


def test_flat_unit_normalisation_removes_legacy_stakes(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    graded.write_text("", encoding="utf-8")
    # Legacy CLV row with a relabeled dollar-Kelly stake (500u) must NOT dominate;
    # it is re-staked to flat 1u from its decimal + outcome.
    _write_jsonl(clv, [
        {"status": "settled", "sport": "mlb", "matchup": "A@B", "outcome": "win",
         "taken_decimal": 2.49, "stake_units": 500.0, "unit_result": 745.0,
         "settled_at": "2026-06-17T23:01:00+00:00"},
        {"status": "settled", "sport": "mlb", "matchup": "C@D", "outcome": "loss",
         "taken_decimal": 3.33, "stake_units": 500.0, "unit_result": -500.0,
         "settled_at": "2026-06-18T23:01:00+00:00"},
    ])
    rows = ps.collect_settled(clv, graded)
    assert len(rows) == 2
    assert all(r["stake_units"] == 1.0 for r in rows)
    by = {r["matchup"]: r["unit_result"] for r in rows}
    assert by["A@B"] == round(2.49 - 1.0, 6)  # flat 1u win
    assert by["C@D"] == -1.0  # flat 1u loss
    payload = ps.build_series(rows, start_units=100.0)
    # total = +1.49 - 1.0 = +0.49, not +245.
    assert payload["summary"]["total_units"] == round(1.49 - 1.0, 6)


def test_empty_ledgers_safe(tmp_path: Path):
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    clv.write_text("", encoding="utf-8")
    graded.write_text("", encoding="utf-8")
    rows = ps.collect_settled(clv, graded)
    payload = ps.build_series(rows, start_units=100.0)
    assert payload["summary"]["n_bets"] == 0
    assert payload["summary"]["current_units"] == 100.0
    assert payload["summary"]["win_rate"] is None


def test_mean_clv_small_n_floor_and_n_clv(tmp_path: Path):
    """FIX 3: a few true closes (< MIN_CLV_N) report INSUFFICIENT_DATA, not a number;
    n_clv (the true-close count) is surfaced so the sample size is visible."""
    from scripts.platformkit.paper import paper_today as pt
    clv = tmp_path / "clv.jsonl"
    graded = tmp_path / "graded.jsonl"
    graded.write_text("", encoding="utf-8")
    # 3 settled rows WITH a captured close (below the floor) + 1 without.
    _write_jsonl(clv, [
        {"status": "settled", "sport": "mlb", "matchup": "A@B", "outcome": "win",
         "taken_decimal": 2.0, "unit_result": 1.0, "clv_pct": 3.0,
         "settled_at": "2026-06-18T20:00:00+00:00"},
        {"status": "settled", "sport": "mlb", "matchup": "C@D", "outcome": "loss",
         "taken_decimal": 2.0, "unit_result": -1.0, "clv_pct": -1.0,
         "settled_at": "2026-06-18T20:30:00+00:00"},
        {"status": "settled", "sport": "mlb", "matchup": "E@F", "outcome": "win",
         "taken_decimal": 2.0, "unit_result": 1.0, "clv_pct": 2.0,
         "settled_at": "2026-06-18T21:00:00+00:00"},
        {"status": "settled", "sport": "mlb", "matchup": "G@H", "outcome": "loss",
         "taken_decimal": 2.0, "unit_result": -1.0, "clv_pct": None,
         "settled_at": "2026-06-18T21:30:00+00:00"},
    ])
    rows = ps.collect_settled(clv, graded)
    s = ps.build_series(rows, start_units=100.0)["summary"]
    assert pt.MIN_CLV_N >= 8
    assert s["mean_clv_pct_or_INSUFFICIENT"] == "INSUFFICIENT_DATA"
    assert s["n_clv"] == 3  # only the captured-close rows counted, surfaced

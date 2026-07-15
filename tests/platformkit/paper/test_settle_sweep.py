"""Per-file tests for scripts.platformkit.paper.settle_sweep: routing
classification, bet_id/edge_key pairing (never double-settle), inventory
buckets, sweep() dry-run vs write, and the VOID encoding proven invisible to
the REAL circuit_breaker.rolling_clv / clv_ledger.clv_summary / paper_trail.
clv_summary (not fakes -- these are the exact consumers the encoding was
chosen against, see settle_sweep.py's module docstring).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    tests/platformkit/paper/test_settle_sweep.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from scripts.platformkit.execution import circuit_breaker as cb
from scripts.platformkit.paper import settle_sweep as ss

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
OLD_TS = "2026-06-20T00:00:00Z"    # ~25 days before NOW -> 14-30d bucket
VOLD_TS = "2026-05-01T00:00:00Z"   # >30d bucket
RECENT_TS = "2026-07-13T00:00:00Z"  # <7d -> excluded from the backlog


def _write(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _bet_id(row):
    return "|".join([row["sport"], row["event_id"], row["market"], row["side"],
                     row["taken_book"], row["ts"][:10]])


def _ml_bet(**over):
    row = {"sport": "mlb", "matchup": "CIN @ COL", "side": "home",
           "taken_book": "dk", "taken_decimal": 1.9, "market": "moneyline",
           "market_type": "moneyline", "status": "open", "ts": OLD_TS,
           "event_id": "G1"}
    row.update(over)
    if row.get("bet_id") is None:
        row["bet_id"] = _bet_id(row)
    return row


def _prop_bet(sport="mlb", **over):
    row = {"sport": sport, "matchup": "CIN @ COL", "side": "home",
           "taken_book": "dk", "taken_decimal": 1.9, "market": "prop",
           "market_type": "prop", "prop_player": "X", "prop_stat": "Hits",
           "line": 0.5, "status": "open", "ts": OLD_TS, "event_id": "G2"}
    row.update(over)
    if row.get("bet_id") is None:
        row["bet_id"] = _bet_id(row)
    return row


def _ingame_bet(**over):
    row = {"sport": "mlb", "game_id": "KXMLBGAME-26JUN281920NYYBOS",
           "matchup": "KXMLBGAME-26JUN281920NYYBOS", "market": "win_home",
           "side": "home", "taken_book": "paper_ingame", "taken_decimal": 1.15,
           "channel": "paper_ingame", "status": "open", "ts": OLD_TS,
           "edge_key": "mlb|KXMLBGAME-26JUN281920NYYBOS|win_home|home|2026-06-20"}
    row.update(over)
    return row


# --------------------------------------------------------------------------- #
# _classify routing
# --------------------------------------------------------------------------- #
def test_classify_routes_game_moneyline():
    assert ss._classify(_ml_bet()) == (ss.REASON_ROUTE_ML, False)


def test_classify_routes_paper_ingame_channel_regardless_of_market():
    assert ss._classify(_ingame_bet()) == (ss.REASON_ROUTE_INGAME, False)


def test_classify_routes_mlb_and_soccer_props():
    assert ss._classify(_prop_bet(sport="mlb")) == (ss.REASON_ROUTE_PROP, False)
    assert ss._classify(_prop_bet(sport="soccer_intl")) == (ss.REASON_ROUTE_PROP, False)


def test_classify_no_resolver_for_unsupported_prop_sport():
    assert ss._classify(_prop_bet(sport="nba")) == (ss.REASON_NO_RESOLVER, True)


def test_classify_malformed_identity_missing_sport():
    assert ss._classify(_ml_bet(sport="")) == (ss.REASON_MALFORMED, True)


def test_classify_malformed_identity_no_anchor():
    row = _ml_bet(matchup="", event_id="", game_id=None)
    assert ss._classify(row) == (ss.REASON_MALFORMED, True)


# --------------------------------------------------------------------------- #
# pairing -- never double-settle, across BOTH bet_id and edge_key conventions
# --------------------------------------------------------------------------- #
def test_aged_open_excludes_row_with_settled_twin_by_bet_id():
    bet = _ml_bet()
    settled_twin = dict(bet, status="settled", clv_pct=1.0)
    _, aged = ss._aged_open_rows([bet, settled_twin], NOW)
    assert aged == []


def test_aged_open_excludes_ingame_row_with_settled_twin_by_edge_key():
    bet = _ingame_bet()
    settled_twin = dict(bet, status="settled")
    _, aged = ss._aged_open_rows([bet, settled_twin], NOW)
    assert aged == []


def test_aged_open_excludes_ingame_row_whose_twin_carries_a_minted_bet_id():
    """The real-ledger phantom-open bug: a settled in-game twin carries BOTH
    the edge_key its open row is keyed by AND a minted bet_id (back-filled by
    clv_settle_write). Pairing must match on ANY shared identity, not just
    each side's first key."""
    bet = _ingame_bet()  # open row: edge_key only, no bet_id
    settled_twin = dict(bet, status="settled",
                        bet_id="mlb|KXMLBGAME-26JUN281920NYYBOS|win_home|home|paper_ingame|2026-06-20")
    _, aged = ss._aged_open_rows([bet, settled_twin], NOW)
    assert aged == []


def test_aged_open_includes_genuinely_open_row():
    _, aged = ss._aged_open_rows([_ml_bet()], NOW)
    assert len(aged) == 1


def test_aged_open_excludes_recent_rows():
    _, aged = ss._aged_open_rows([_ml_bet(ts=RECENT_TS)], NOW)
    assert aged == []


def test_age_bucket_boundaries():
    assert ss._age_bucket(6.9) is None
    assert ss._age_bucket(7.0) == "7-14d"
    assert ss._age_bucket(13.9) == "7-14d"
    assert ss._age_bucket(14.0) == "14-30d"
    assert ss._age_bucket(29.9) == "14-30d"
    assert ss._age_bucket(30.0) == ">30d"


# --------------------------------------------------------------------------- #
# inventory()
# --------------------------------------------------------------------------- #
def test_inventory_buckets_by_sport_market_channel_reason(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [
        _ml_bet(),
        _prop_bet(sport="mlb", ts=VOLD_TS, event_id="G4"),
        _ingame_bet(),
        _ml_bet(ts=RECENT_TS, event_id="G3"),  # excluded: too recent
    ])
    inv = ss.inventory(ledger)
    assert inv["n_total_rows"] == 4
    assert inv["n_aged_ge_7d"] == 3
    assert inv["by_sport"] == {"mlb": 3}
    assert inv["by_market_type"] == {"moneyline": 1, "prop": 1, "win_home": 1}
    assert inv["by_channel"]["paper_ingame"] == 1
    assert inv["by_stuck_reason"][ss.REASON_ROUTE_ML] == 1
    assert inv["by_stuck_reason"][ss.REASON_ROUTE_PROP] == 1
    assert inv["by_stuck_reason"][ss.REASON_ROUTE_INGAME] == 1
    assert inv["by_age_bucket"][">30d"] == 1


def test_inventory_read_only_never_mutates_ledger(tmp_path):
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [_ml_bet()])
    before = ledger.read_text(encoding="utf-8")
    ss.inventory(ledger)
    assert ledger.read_text(encoding="utf-8") == before


# --------------------------------------------------------------------------- #
# sweep() dry run -- classification only, no settler invoked, no write
# --------------------------------------------------------------------------- #
def test_sweep_dry_run_reports_routing_without_writing(tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [_ml_bet(), _prop_bet(sport="nba")])  # 1 route, 1 void-eligible

    monkeypatch.setattr(ss, "_try_backfill_as_of",
                        lambda p: pytest.fail("dry run must never call a settler"))
    monkeypatch.setattr(ss, "_try_settle_open_props",
                        lambda p: pytest.fail("dry run must never call a settler"))
    monkeypatch.setattr(ss, "_try_ingame_settle_open",
                        lambda p: pytest.fail("dry run must never call a settler"))

    before = ledger.read_text(encoding="utf-8")
    out = ss.sweep(ledger, write=False)
    assert out["write"] is False
    assert out["n_aged_considered"] == 2
    assert out["n_would_void_candidates"] == 1
    assert ledger.read_text(encoding="utf-8") == before  # untouched


# --------------------------------------------------------------------------- #
# sweep(write=True) -- settlers invoked once per route; VOID appended only for
# rows still open afterwards that are provably unroutable
# --------------------------------------------------------------------------- #
def test_sweep_write_settles_via_existing_settler_and_voids_unroutable(
        tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    settleable = _ml_bet(event_id="G1")
    unroutable = _prop_bet(sport="nba", event_id="G2")  # no resolver -> VOID
    _write(ledger, [settleable, unroutable])

    calls = {"backfill": 0}

    def _fake_backfill(path):
        calls["backfill"] += 1
        with open(path, "a", encoding="utf-8") as fh:  # simulate a real settle
            fh.write(json.dumps(dict(settleable, status="settled",
                                     outcome="win", clv_pct=2.0)) + "\n")
        return {"settled_now": 1}

    monkeypatch.setattr(ss, "_try_backfill_as_of", _fake_backfill)
    monkeypatch.setattr(ss, "_try_settle_open_props",
                        lambda p: pytest.fail("no prop route in this fixture"))
    monkeypatch.setattr(ss, "_try_ingame_settle_open",
                        lambda p: pytest.fail("no ingame route in this fixture"))

    out = ss.sweep(ledger, write=True)
    assert calls["backfill"] == 1
    assert out["n_settled_now"] == 1
    assert out["n_voided"] == 1
    assert out["n_left_open"] == 0

    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()]
    void_rows = [r for r in rows if r.get("outcome") == ss.VOID_OUTCOME]
    assert len(void_rows) == 1
    assert void_rows[0]["status"] == "settled"  # NOT the literal status string
    assert void_rows[0]["void_reason"] == ss.REASON_NO_RESOLVER
    assert void_rows[0]["clv_pct"] is None
    assert void_rows[0]["unit_result"] == 0.0


def test_sweep_write_is_idempotent_across_two_calls(tmp_path, monkeypatch):
    """A second sweep() call must never re-void an already-terminal row."""
    ledger = tmp_path / "clv_ledger.jsonl"
    _write(ledger, [_prop_bet(sport="nba")])
    monkeypatch.setattr(ss, "_try_backfill_as_of", lambda p: {})
    monkeypatch.setattr(ss, "_try_settle_open_props", lambda p: {})
    monkeypatch.setattr(ss, "_try_ingame_settle_open", lambda p: {})

    out1 = ss.sweep(ledger, write=True)
    assert out1["n_voided"] == 1
    out2 = ss.sweep(ledger, write=True)
    assert out2["n_voided"] == 0       # already terminal -- not re-voided
    assert out2["n_aged_before"] == 0  # no longer genuinely open


# --------------------------------------------------------------------------- #
# VOID encoding is invisible to the REAL consumers named in the module
# docstring -- imports the real functions, never a fake, to prove the claim.
# --------------------------------------------------------------------------- #
def test_void_row_excluded_from_real_rolling_clv():
    twin = ss._void_twin(_ml_bet(), ss.REASON_MALFORMED)
    out = cb.rolling_clv([twin], "moneyline", "2026-07-15T12:00:00Z")
    assert out["n"] == 0  # clv_pct=None -> rolling_clv skips it entirely
    assert out["median_clv_pct"] is None


def test_void_row_excluded_from_clv_ledger_summary():
    from scripts.platformkit import clv_ledger as _clv
    twin = ss._void_twin(_ml_bet(), ss.REASON_MALFORMED)
    summary = _clv.clv_summary([twin])
    assert summary["n_bets"] == 0  # status=="settled" but clv_pct is None -> excluded


def test_void_row_paper_trail_open_count_not_double_counted(tmp_path):
    """The exact gotcha the encoding avoids: paper_trail.clv_summary's n_open
    counts status != "settled" over the RAW (uncollapsed) rows -- a literal
    status="VOID_UNRESOLVABLE" twin would count TWICE (the original open row
    AND the terminal twin both match "!= settled"). status="settled" keeps
    this at exactly one (the original open row only)."""
    from frontend import paper_trail as pt
    ledger = tmp_path / "clv_ledger.jsonl"
    bet = _ml_bet()
    twin = ss._void_twin(bet, ss.REASON_MALFORMED)
    _write(ledger, [bet, twin])
    summary = pt.clv_summary(ledger)
    assert summary["n_open"] == 1  # not 2 -- the twin's status=="settled" is skipped

"""Tests for clv_scoreboard -- per-channel CLV truth table.

Per-file: python -m pytest scripts/platformkit/clv/test_clv_scoreboard.py -q
"""
from __future__ import annotations

from scripts.platformkit.clv import clv_scoreboard as S


def _row(bet_id, channel, status="settled", clv_status="no_close",
         clv_pct=None, unit_result=0.0, settled_at="2026-06-25T00:00:00Z",
         closing=None):
    r = {"bet_id": bet_id, "channel": channel, "status": status,
         "clv_status": clv_status, "clv_pct": clv_pct,
         "unit_result": unit_result, "settled_at": settled_at, "sport": "mlb"}
    if closing is not None:
        r["closing_decimal_home"] = closing
    return r


def test_dedup_keeps_latest_settled():
    led = [
        _row("b1", "paper", unit_result=-1.0, settled_at="2026-06-25T01:00:00Z"),
        _row("b1", "paper", unit_result=-1.0, settled_at="2026-06-25T02:00:00Z"),
    ]
    b = S.scoreboard(led)
    assert b["total_settled"] == 1  # twin collapsed


def test_measurable_split_and_coverage():
    led = [
        # measurable moneyline: 2 rows, both true_close
        _row("m1", "moneyline", clv_status="true_close", clv_pct=2.0,
             unit_result=1.0, closing=2.0),
        _row("m2", "moneyline", clv_status="true_close", clv_pct=-1.0,
             unit_result=-1.0, closing=2.0),
        # props: no close
        _row("p1", "paper", clv_status="no_close", unit_result=1.0),
        _row("p2", "paper", clv_status="no_close", unit_result=-1.0),
    ]
    b = S.scoreboard(led)
    assert b["total_settled"] == 4
    assert b["total_measurable"] == 2
    ml = b["channels"]["moneyline"]
    assert ml["n_measurable"] == 2
    assert ml["coverage_pct"] == 100.0
    assert ml["mean_clv_pct"] == 0.5  # (2 + -1)/2
    assert ml["beat_close_pct"] == 50.0
    pp = b["channels"]["paper"]
    assert pp["n_measurable"] == 0
    assert pp["coverage_pct"] == 0.0
    assert pp["mean_clv_pct"] is None  # no CLV for props
    assert pp["beat_close_pct"] is None


def test_no_closing_lines_verdict():
    led = [_row("p%d" % i, "paper", unit_result=1.0) for i in range(5)]
    b = S.scoreboard(led)
    assert b["total_measurable"] == 0
    assert "NO closing lines" in b["verdict"] or "unprovable" in b["verdict"]


def test_significant_positive_clv_flagged():
    # tight positive cluster -> CI excludes 0 -> significant + positive
    led = [
        _row("m%d" % i, "moneyline", clv_status="true_close",
             clv_pct=3.0 + (i % 2) * 0.2, unit_result=1.0, closing=2.0,
             settled_at="2026-06-25T%02d:00:00Z" % i)
        for i in range(12)
    ]
    b = S.scoreboard(led)
    ml = b["channels"]["moneyline"]
    assert ml["clv_significant"] is True
    assert ml["mean_clv_pct"] > 0
    assert "SIGNAL" in b["verdict"]


def test_offmarket_row_excluded_from_measurable():
    # A row whose taken price (12.0) is wildly longer than its side's close (1.95) is
    # off-market -> excluded from the measurable set + counted as suspect, so its
    # fabricated +497% CLV never inflates the channel mean (the dishonesty guard).
    led = [
        {"bet_id": "good", "channel": "moneyline", "status": "settled",
         "clv_status": "true_close", "clv_pct": -1.0, "unit_result": -1.0,
         "settled_at": "2026-06-25T01:00:00Z", "sport": "mlb", "side": "home",
         "taken_decimal": 1.95, "closing_decimal_home": 1.95,
         "closing_decimal_away": 1.95},
        {"bet_id": "bad", "channel": "moneyline", "status": "settled",
         "clv_status": "true_close", "clv_pct": 497.0, "unit_result": 1.0,
         "settled_at": "2026-06-25T02:00:00Z", "sport": "mlb", "side": "away",
         "taken_decimal": 12.0, "closing_decimal_home": 1.95,
         "closing_decimal_away": 1.95},
    ]
    b = S.scoreboard(led)
    ml = b["channels"]["moneyline"]
    assert ml["n_settled"] == 2            # both are real placed bets
    assert ml["n_measurable"] == 1         # only the on-market row is measurable
    assert ml["n_suspect_excluded"] == 1
    assert b["total_suspect_excluded"] == 1
    assert ml["mean_clv_pct"] == -1.0      # NOT dragged toward +497 by the garbage row


def test_render_runs():
    led = [_row("m1", "moneyline", clv_status="true_close", clv_pct=1.0,
                unit_result=1.0, closing=2.0)]
    txt = S.render(S.scoreboard(led))
    assert "CLV SCOREBOARD" in txt and "VERDICT" in txt


# --------------------------------------------------------------------------------------- #
# W1 FIX: kx-proxy measurable tier -- SEPARATE from true_close, never merged.              #
# --------------------------------------------------------------------------------------- #
def test_proxy_row_counted_in_proxy_tier_not_true_close():
    led = [
        {"bet_id": "px1", "channel": "paper_ingame", "status": "settled",
         "clv_status": "proxy", "clv_pct": 3.0, "clv_is_proxy": True,
         "unit_result": 1.0, "settled_at": "2026-06-25T01:00:00Z", "sport": "mlb"},
    ]
    b = S.scoreboard(led)
    ch = b["channels"]["paper_ingame"]
    assert ch["n_measurable"] == 0          # never counted as true_close
    assert ch["n_measurable_proxy"] == 1
    assert ch["clv_proxy_pct"] == 3.0
    assert b["total_measurable"] == 0       # top-level true_close total untouched
    assert b["total_measurable_proxy"] == 1


def test_no_close_paper_ingame_row_recovered_via_enrich(monkeypatch):
    # simulate a kx close having been derived for this row's ticker.
    monkeypatch.setattr(S, "enrich_paper_ingame_no_close",
                        lambda r: ({**r, "clv_status": "proxy", "clv_pct": 5.0,
                                    "clv_is_proxy": True}
                                   if r.get("channel") == "paper_ingame" else r))
    led = [
        {"bet_id": "nc1", "channel": "paper_ingame", "status": "settled",
         "clv_status": "no_close", "clv_pct": None, "unit_result": 1.0,
         "settled_at": "2026-06-25T01:00:00Z", "sport": "mlb"},
    ]
    b = S.scoreboard(led)
    ch = b["channels"]["paper_ingame"]
    assert ch["n_measurable_proxy"] == 1
    assert ch["n_measurable"] == 0


def test_still_no_close_row_stays_unmeasurable_either_tier():
    led = [
        {"bet_id": "nc2", "channel": "paper_ingame", "status": "settled",
         "clv_status": "no_close", "clv_pct": None, "unit_result": -1.0,
         "settled_at": "2026-06-25T01:00:00Z", "sport": "mlb", "game_id": "NEVER-DERIVED"},
    ]
    b = S.scoreboard(led)
    ch = b["channels"]["paper_ingame"]
    assert ch["n_measurable"] == 0
    assert ch["n_measurable_proxy"] == 0


# --------------------------------------------------------------------------------------- #
# Quarantine adjudication: EXCLUDE-FROM-AGGREGATES rows dropped + counted, not vanished.    #
# --------------------------------------------------------------------------------------- #
def test_quarantined_row_excluded_and_counted(monkeypatch):
    monkeypatch.setattr(S, "quarantined_bet_ids", lambda: {"bad1"})
    led = [
        _row("bad1", "moneyline", clv_status="true_close", clv_pct=2.0,
             unit_result=1.0, closing=2.0),
        _row("good1", "moneyline", clv_status="true_close", clv_pct=1.0,
             unit_result=1.0, closing=2.0),
    ]
    b = S.scoreboard(led)
    assert b["total_settled"] == 1           # quarantined row dropped
    assert b["n_excluded_quarantined"] == 1   # but counted, never silently vanished
    assert b["channels"]["moneyline"]["n_settled"] == 1


def test_no_quarantine_hits_is_unchanged_behavior(monkeypatch):
    monkeypatch.setattr(S, "quarantined_bet_ids", lambda: set())
    led = [_row("m1", "moneyline", clv_status="true_close", clv_pct=1.0,
                unit_result=1.0, closing=2.0)]
    b = S.scoreboard(led)
    assert b["n_excluded_quarantined"] == 0
    assert b["total_settled"] == 1


def test_render_shows_proxy_line_when_present():
    led = [
        {"bet_id": "px2", "channel": "paper_ingame", "status": "settled",
         "clv_status": "proxy", "clv_pct": 3.0, "clv_is_proxy": True,
         "unit_result": 1.0, "settled_at": "2026-06-25T01:00:00Z", "sport": "mlb"},
    ]
    txt = S.render(S.scoreboard(led))
    assert "proxy (kx last-tick" in txt

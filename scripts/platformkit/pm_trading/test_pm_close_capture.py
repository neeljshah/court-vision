"""Per-file test for pm_close_capture -- the PM/Kalshi close sweep.

Fully offline (temp ledger + injected capture_fn). Pins: only CONFIRMED (non-proxy)
closes are stamped (true_close, clv_is_proxy=False); a proxy/open market is counted but
NEVER written; a row with no event_id or an already-resolved row is skipped (idempotent);
outcome/unit_result are preserved. No network.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_pm_close_capture.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.pm_trading import pm_close_capture as P
from scripts.platformkit.pm_trading.close_capture import CloseResult


def _row(bet_id, *, event_id="KXMLBGAME-X", clv_pct=None, is_proxy=True, outcome="win"):
    return {"channel": "paper_pm", "status": "settled", "is_pm": True,
            "sport": "mlb", "side": "home", "taken_decimal": 2.0, "bet_id": bet_id,
            "event_id": event_id, "outcome": outcome, "unit_result": 1.0,
            "clv_pct": clv_pct, "clv_is_proxy": is_proxy}


def _write(tmp_path, rows):
    p = tmp_path / "clv.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _confirmed_close(row, *, kalshi_fetch=None):
    return CloseResult(close_home_dec=1.80, close_away_dec=2.10,
                       is_proxy=False, close_source="kalshi", close_venue="kalshi")


def _proxy_close(row, *, kalshi_fetch=None):
    return CloseResult(close_home_dec=1.80, close_away_dec=2.10,
                       is_proxy=True, close_source="proxy")


def test_stamps_confirmed_close(tmp_path):
    p = _write(tmp_path, [_row("pm|kalshi|g1|home")])
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_targets"] == 1 and out["n_captured"] == 1
    assert out["executed"] is False
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    settled = [r for r in rows if r.get("clv_pct") is not None]
    assert settled, "a settled twin with clv_pct should be appended"
    s = settled[-1]
    assert s["clv_is_proxy"] is False and s["clv_status"] == "true_close"
    assert s["outcome"] == "win" and s["unit_result"] == 1.0   # preserved


def test_stamps_close_source_and_venue_on_settled_row(tmp_path):
    """ROOT CAUSE FIX (2026-07-09): sweep_closes previously computed
    res.close_source only for its own diagnostic counter and never passed it
    to settle_closing_line -- settled ledger rows carried no close_source/
    close_venue at all. Now both flow through the settle_closing_line kwargs."""
    p = _write(tmp_path, [_row("pm|kalshi|g4|home")])
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_captured"] == 1
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    settled = [r for r in rows if r.get("clv_pct") is not None][-1]
    assert settled["close_source"] == "kalshi"
    assert settled["close_venue"] == "kalshi"


def test_proxy_close_is_counted_not_written(tmp_path):
    p = _write(tmp_path, [_row("pm|kalshi|g2|home")])
    out = P.sweep_closes(p, capture_fn=_proxy_close)
    assert out["n_proxy"] == 1 and out["n_captured"] == 0
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert all(r.get("clv_pct") is None for r in rows)   # nothing fabricated


def test_skips_no_event_id_and_already_kalshi_resolved(tmp_path):
    rows = [_row("pm|a", event_id=""),                       # no event_id -> skip
            {**_row("pm|b", clv_pct=4.2, is_proxy=False),
             "close_source": "kalshi"}]                       # real same-venue -> skip
    p = _write(tmp_path, rows)
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_targets"] == 0 and out["n_captured"] == 0


def test_cross_venue_confirmed_row_stays_a_target(tmp_path):
    """ROOT CAUSE FIX (2026-07-08b): grade_paper.grade_one may stamp
    clv_is_proxy=False from its OWN cross-venue line_store resolution
    (close_source='cross_venue_fallback', grade_one's new explicit tag for a
    row settled AFTER this fix). That must NOT be treated as 'already
    resolved' -- this sweep needs a real chance to overwrite it with the
    genuine Kalshi close. Previously such a row was skipped forever
    (n_targets stayed 0)."""
    rows = [{**_row("pm|c", clv_pct=-3.1, is_proxy=False),
             "close_source": "cross_venue_fallback"}]
    p = _write(tmp_path, rows)
    out = P.sweep_closes(p, capture_fn=_confirmed_close)
    assert out["n_targets"] == 1 and out["n_captured"] == 1


def test_resolved_keys_forward_only_vs_same_venue_vs_legacy():
    """Unit-level contract for _resolved_keys:
      - no close_source/close_venue at all (row settled BEFORE this fix, or a
        Level-1 close whose book is genuinely unknown) -> forward-only, left
        resolved (never reconsidered -- avoids churning dead old rows through
        the bounded max_rows budget every tick).
      - close_source names a non-kalshi/poly book (grade_one's explicit
        cross-venue match) -> NOT resolved, stays a target.
      - close_source names kalshi/poly -> genuinely resolved, skip.
    """
    legacy = [{**_row("pm|d", clv_pct=1.0, is_proxy=False)}]  # no close_source key
    assert P._resolved_keys(legacy) == {"pm|d"}
    cross = [{**_row("pm|e", clv_pct=1.0, is_proxy=False), "close_source": "fanduel"}]
    assert P._resolved_keys(cross) == set()
    same_venue = [{**_row("pm|f", clv_pct=1.0, is_proxy=False), "close_source": "kalshi"}]
    assert P._resolved_keys(same_venue) == {"pm|f"}


def test_dry_run_never_writes_ledger(tmp_path):
    """dry_run=True resolves + counts but appends nothing (read-only verify)."""
    p = _write(tmp_path, [_row("pm|dry1")])
    out = P.sweep_closes(p, capture_fn=_confirmed_close, dry_run=True)
    assert out["n_captured"] == 1 and out["dry_run"] is True
    assert out["n_same_venue"] == 1  # close_source="kalshi" from _confirmed_close
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    assert all(r.get("clv_pct") is None for r in rows)  # nothing appended


def test_no_close_available_is_honest(tmp_path):
    p = _write(tmp_path, [_row("pm|g3|home")])
    out = P.sweep_closes(p, capture_fn=lambda r, **k: None)
    assert out["n_no_close"] == 1 and out["n_captured"] == 0


def test_sweep_bounded_by_max_rows(tmp_path):
    """max_rows caps work per sweep (the m18 heartbeat-flap guard): with 3
    targets and max_rows=1, exactly one capture attempt happens."""
    import json
    from scripts.platformkit.pm_trading.pm_close_capture import sweep_closes
    ledger = tmp_path / "ledger.jsonl"
    rows = [
        {"bet_id": "b%d" % i, "channel": "paper_pm", "venue": "kalshi",
         "settled": True, "clv_status": "pending", "ticker": "T%d" % i}
        for i in range(3)
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")
    calls = []
    def fake_cap(row, kalshi_fetch=None):
        calls.append(row["bet_id"])
        return None  # no close found -- nothing written
    out = sweep_closes(ledger, capture_fn=fake_cap, max_rows=1)
    assert len(calls) <= 1
    assert out.get("edge_claimed") is False


def test_memoized_kalshi_fetch_one_call_per_sport(monkeypatch):
    """The per-sweep memoizer fetches each sport ONCE regardless of row count
    (the m18 429/heartbeat root cause was one full fetch PER ROW)."""
    import scripts.platformkit.odds_provider.kalshi as _k
    from scripts.platformkit.pm_trading.pm_close_capture import _memoized_kalshi_fetch
    calls = []

    class FakeProvider:
        def __init__(self, **kw):
            pass
        def fetch(self, sport):
            calls.append(sport)
            return []

    monkeypatch.setattr(_k, "KalshiProvider", FakeProvider)
    fetch = _memoized_kalshi_fetch()
    assert fetch is not None
    for _ in range(5):
        fetch("mlb")
        fetch("wnba")
    assert calls == ["mlb", "wnba"]

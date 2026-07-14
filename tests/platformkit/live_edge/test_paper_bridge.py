"""Per-file test for LIVE-EDGE PAPER-BRIDGE (event_key/resolve_identity/bridge).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_paper_bridge.py -q
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scripts.platformkit import clv_ledger
from scripts.platformkit.live_edge.paper import bridge
from scripts.platformkit.live_edge.paper.event_key import make_event_key, market_family_of
from scripts.platformkit.live_edge.paper.resolve_identity import resolve_identity, resolve_source_id


def _write_line_history(tmp_path, sport, date, rows):
    d = tmp_path / sport
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{date}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return tmp_path


_REC = {
    "sport": "soccer_fixture", "game_id": "SYN1", "home": "Synthetic United",
    "away": "Fixture City", "market_type": "moneyline", "side": "home",
    "line": None, "odds": 1.8, "book": "fixture_book", "devigged_prob": 0.60,
    "captured_at": "2026-07-20T00:00:06+00:00", "commence_time": "2026-07-20T19:00Z",
}


def test_market_family_of():
    assert market_family_of("pregame.moneyline") == "moneyline"
    assert market_family_of("") == "unknown"
    assert market_family_of(None) == "unknown"


def test_make_event_key_canonicalizes():
    ek = make_event_key("nba", "2026-04-27", "Boston Celtics", "Philadelphia 76ers", "pregame.moneyline")
    assert ek.sport == "nba"
    assert ek.date == "2026-04-27"
    assert ek.market_family == "moneyline"
    assert ek.home != "Boston Celtics"  # canonicalized, not raw


def test_resolve_source_id_exact_join(tmp_path):
    lh = _write_line_history(tmp_path, "soccer_fixture", "2026-07-20", [_REC])
    rec = resolve_source_id("soccer_fixture", "2026-07-20", "SYN1",
                             devigged_prob=0.60, line_history_dir=lh)
    assert rec is not None
    assert rec["home"] == "Synthetic United"
    assert rec["away"] == "Fixture City"


def test_resolve_source_id_honest_miss(tmp_path):
    lh = _write_line_history(tmp_path, "soccer_fixture", "2026-07-20", [_REC])
    assert resolve_source_id("soccer_fixture", "2026-07-20", "NO_SUCH_ID", line_history_dir=lh) is None


def test_resolve_identity_end_to_end(tmp_path):
    lh = _write_line_history(tmp_path, "soccer_fixture", "2026-07-20", [_REC])
    shadow_row = {"sport": "soccer_fixture", "game": "SYN1", "market": "pregame.moneyline",
                  "market_price": 0.60, "conditioned_pred": 0.70, "book": "fixture_book",
                  "ts": "2026-07-20T12:00:00+00:00"}
    identity = resolve_identity(shadow_row, line_history_dir=lh)
    assert identity is not None
    ek = identity["event_key"]
    assert ek.sport == "soccer_fixture" and ek.date == "2026-07-20" and ek.market_family == "moneyline"
    assert identity["side"] == "home"
    assert identity["odds_decimal"] == 1.8
    assert identity["book"] == "fixture_book"


def test_resolve_identity_missing_fields_is_none():
    assert resolve_identity({"sport": "nba"}) is None
    assert resolve_identity({}) is None


def test_bridge_select_threshold():
    row = {"conditioned_pred": 0.70, "market_price": 0.60}
    assert bridge.select(row, threshold=0.05) is True
    assert bridge.select(row, threshold=0.50) is False
    assert bridge.select({"conditioned_pred": None, "market_price": 0.6}) is False


def test_run_bridge_row_full_chain(tmp_path):
    lh = _write_line_history(tmp_path, "soccer_fixture", "2026-07-20", [_REC])
    shadow_row = {"sport": "soccer_fixture", "game": "SYN1", "market": "pregame.moneyline",
                  "market_price": 0.60, "conditioned_pred": 0.70, "book": "fixture_book",
                  "ts": "2026-07-20T12:00:00+00:00", "mechanism_applied": None,
                  "edge_claimed": False}
    ledger_path = tmp_path / "ledger.jsonl"
    result = bridge.run_bridge_row(shadow_row, threshold=0.05, path=ledger_path, line_history_dir=lh)
    assert result["status"] == "recorded"
    bet = result["bet"]
    assert bet["channel"] == bridge.CHANNEL_LIVE_EDGE_PAPER
    assert bet["side"] == "home"
    assert bet["taken_decimal"] == 1.8
    assert bet["executed"] is False  # invariant: never a real bet

    ledger = clv_ledger.load_ledger(path=ledger_path)
    assert len(ledger) == 1
    assert ledger[0]["bet_id"] == bet["bet_id"]


def test_run_bridge_row_ungradeable_identity_is_honest(tmp_path):
    shadow_row = {"sport": "nowhere_sport", "game": "GHOST", "market": "pregame.moneyline",
                  "market_price": 0.5, "conditioned_pred": 0.5, "ts": "2026-07-20T12:00:00+00:00"}
    result = bridge.run_bridge_row(shadow_row, path=tmp_path / "unused.jsonl")
    assert result["status"] == "ungradeable_identity"


def test_run_bridge_row_not_selected(tmp_path):
    lh = _write_line_history(tmp_path, "soccer_fixture", "2026-07-20", [_REC])
    shadow_row = {"sport": "soccer_fixture", "game": "SYN1", "market": "pregame.moneyline",
                  "market_price": 0.60, "conditioned_pred": 0.605,  # tiny divergence
                  "ts": "2026-07-20T12:00:00+00:00"}
    result = bridge.run_bridge_row(shadow_row, threshold=0.05, path=tmp_path / "ledger2.jsonl",
                                    line_history_dir=lh)
    assert result["status"] == "not_selected"


def test_real_soccer_slice_resolution_rate_ge_95pct():
    """Real-slice gate: >=95% of the on-disk soccer/soccer_intl shadow rows
    from 2026-07-14 must resolve an identity via the exact-provenance join
    (never a fuzzy string match). Skips honestly if the fixture data isn't
    present in this clone (data/ is gitignored, absent from a fresh clone)."""
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    shadow_path = repo_root / "data" / "omni" / "live_edge" / "shadow" / "2026-07-14.jsonl"
    if not shadow_path.is_file():
        pytest.skip("2026-07-14 shadow ledger not present in this clone (data/ is gitignored)")
    rows = []
    for ln in shadow_path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        if r.get("sport") in ("soccer", "soccer_intl"):
            rows.append(r)
    assert rows, "expected real soccer/soccer_intl rows in the 2026-07-14 shadow ledger"
    n_resolved = sum(1 for r in rows if resolve_identity(r) is not None)
    rate = n_resolved / len(rows)
    assert rate >= 0.95, f"resolution rate {rate:.3f} on {len(rows)} rows is below the 95% bar"

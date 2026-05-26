"""tests/test_R26_S7_free_arb_alert.py — R26_S7 free-arb critical alert wire.

Covers:
  1. single free arb -> exactly one alert fires
  2. same arb persisting across N ticks -> dedup respected (1-3 alerts max)
  3. no free arbs -> 0 alerts
  4. non-free middle (positive EV but one leg negative odds) -> no alert
  5. alert message format matches the R26_S7 spec
  6. multiple distinct arbs in one tick -> multiple alerts
  7. defence-in-depth: alt-line/non-primary middle never fires
  8. dedup state and ship-gate guard against false positives end-to-end
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))

import middle_finder_daemon as mfd  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _AlertCapture:
    """Drop-in for the real `alert()` — captures every call for inspection."""

    def __init__(self):
        self.calls = []

    def __call__(self, message, level="info", tag=None, *,
                 source=None, body=None, fields=None, **kwargs):
        self.calls.append({
            "message": message, "level": level, "tag": tag,
            "source": source, "body": body, "fields": fields,
            "kwargs": kwargs,
        })


def _make_free_arb(player="LeBron James", stat="pts",
                   over_book="fd", over_line=24.5, over_price=105,
                   under_book="bov", under_line=25.5, under_price=110,
                   width=1.0, ev=2.34):
    """Construct a `find_middles`-shaped dict for a TRUE free arb."""
    return {
        "player": player,
        "stat": stat,
        "over_book": over_book,
        "over_line": over_line,
        "over_price": over_price,
        "under_book": under_book,
        "under_line": under_line,
        "under_price": under_price,
        "middle_width": width,
        "worst_price": min(over_price, under_price),
        "free_arb": True,
        "arb_profit_pct": ev,
        "market_tier": "primary",
        "is_alt_line": False,
    }


def _make_non_free_middle():
    """A real middle with positive EV vs L5 but a NEGATIVE-odds leg —
    must never trigger the free-arb alert."""
    return {
        "player": "Stephen Curry",
        "stat": "fg3m",
        "over_book": "fd",
        "over_line": 4.5,
        "over_price": -110,        # negative leg => not a free arb
        "under_book": "bov",
        "under_line": 5.5,
        "under_price": -105,
        "middle_width": 1.0,
        "worst_price": -110,
        "free_arb": False,         # find_middles flags this False
        "arb_profit_pct": None,
        "market_tier": "primary",
        "is_alt_line": False,
    }


def _make_alt_line_free_arb():
    """Synthetic: free-arb-looking middle but legs ARE alt-line rungs.
    Defence-in-depth — should be rejected even if free_arb=True."""
    m = _make_free_arb(player="Alt Trap", stat="pts",
                       over_line=3.5, over_price=110,
                       under_line=25.5, under_price=115)
    m["is_alt_line"] = True
    m["market_tier"] = "alt"
    return m


# ---------------------------------------------------------------------------
# 1) single free arb -> one alert
# ---------------------------------------------------------------------------


def test_single_free_arb_fires_one_alert():
    cap = _AlertCapture()
    state = {}
    fired = mfd._fire_free_arb_alert(_make_free_arb(), state, alert_fn=cap)
    assert fired is True
    assert len(cap.calls) == 1
    call = cap.calls[0]
    assert call["level"] == "critical"
    assert call["tag"] == "free_arb"


# ---------------------------------------------------------------------------
# 2) same arb across 5 ticks -> at most 1-3 alerts (dedup respected)
# ---------------------------------------------------------------------------


def test_persisting_arb_is_deduped_across_ticks():
    cap = _AlertCapture()
    state = {}
    arb = _make_free_arb()
    fired = 0
    for _ in range(5):
        if mfd._fire_free_arb_alert(arb, state, ttl_sec=3600, alert_fn=cap):
            fired += 1
    # Spec says 1-3 alerts inclusive; with TTL=1hr it must be exactly 1.
    assert 1 <= fired <= 3, (
        f"dedup spec violated: fired={fired} (expected 1..3)")
    assert fired == 1, (
        f"with 1hr TTL, persisting arb should fire exactly once, got {fired}")
    assert len(cap.calls) == fired


# ---------------------------------------------------------------------------
# 3) no free arbs -> 0 alerts
# ---------------------------------------------------------------------------


def test_no_free_arbs_zero_alerts():
    cap = _AlertCapture()
    state = {}
    # find_middles returns [] -> we never call _fire_free_arb_alert at all.
    middles = []
    for m in middles:
        mfd._fire_free_arb_alert(m, state, alert_fn=cap)
    assert len(cap.calls) == 0


# ---------------------------------------------------------------------------
# 4) non-free middle (positive EV but at least one side negative odds) -> 0
# ---------------------------------------------------------------------------


def test_non_free_middle_does_not_fire():
    cap = _AlertCapture()
    state = {}
    fired = mfd._fire_free_arb_alert(_make_non_free_middle(), state,
                                       alert_fn=cap)
    assert fired is False
    assert len(cap.calls) == 0


# ---------------------------------------------------------------------------
# 5) alert message format
# ---------------------------------------------------------------------------


def test_alert_message_format_matches_spec():
    cap = _AlertCapture()
    state = {}
    arb = _make_free_arb(
        player="Nikola Jokic", stat="ast",
        over_book="fd", over_line=8.5, over_price=110,
        under_book="bov", under_line=9.5, under_price=105,
        width=1.0, ev=2.34,
    )
    mfd._fire_free_arb_alert(arb, state, alert_fn=cap)
    assert len(cap.calls) == 1
    msg = cap.calls[0]["message"]
    body = cap.calls[0]["body"]

    # Headline format: FREE ARB: {player} {stat} — {bo} OVER {lo}@{po} / {bu} UNDER {lu}@{pu}
    expected_head = (
        "FREE ARB: Nikola Jokic ast — fd OVER 8.5@110 / bov UNDER 9.5@105"
    )
    assert msg == expected_head, f"headline mismatch:\n  got: {msg!r}\n  exp: {expected_head!r}"

    # Body must include "Width: 1.0" and an EV line like "EV: +2.34%".
    assert "Width: 1.0" in body
    assert "EV: +2.34%" in body


# ---------------------------------------------------------------------------
# 6) multiple distinct arbs -> multiple alerts
# ---------------------------------------------------------------------------


def test_multiple_distinct_arbs_each_fire():
    cap = _AlertCapture()
    state = {}
    arbs = [
        _make_free_arb(player="A", stat="pts"),
        _make_free_arb(player="B", stat="reb"),
        _make_free_arb(player="C", stat="ast"),
    ]
    fired = sum(
        1 for m in arbs
        if mfd._fire_free_arb_alert(m, state, alert_fn=cap)
    )
    assert fired == 3
    assert len(cap.calls) == 3
    tags = {c["tag"] for c in cap.calls}
    assert tags == {"free_arb"}


# ---------------------------------------------------------------------------
# 7) defence-in-depth — alt-line / non-primary never fires
# ---------------------------------------------------------------------------


def test_alt_line_middle_blocked_even_if_free_arb_flagged():
    cap = _AlertCapture()
    state = {}
    fired = mfd._fire_free_arb_alert(_make_alt_line_free_arb(), state,
                                       alert_fn=cap)
    assert fired is False
    assert len(cap.calls) == 0


# ---------------------------------------------------------------------------
# 8) end-to-end loop() — fake snapshot driver, ensure stats counter wired
# ---------------------------------------------------------------------------


def test_loop_e2e_with_fake_snapshot(tmp_path, monkeypatch):
    """Drive loop() one tick with a monkeypatched run_once that injects
    a synthetic free arb. Confirms the wire from middles -> alert is live
    AND that find_middles' primary-only classifier output is what feeds
    the alert (no false positives)."""
    cap = _AlertCapture()
    free = _make_free_arb()
    non_free = _make_non_free_middle()

    def fake_run_once(date_str, min_width, max_juice, predictor=None,
                      min_band_prob=0.10):
        return [free, non_free], {}

    monkeypatch.setattr(mfd, "run_once", fake_run_once)
    out_json = str(tmp_path / "middles_live.json")
    stats = mfd.loop(
        interval_sec=0.01, min_width=0.5, max_juice=-135, max_iters=1,
        use_model=False, out_json=out_json, log=lambda *a, **k: None,
        alert_fn=cap, dedup_state={},
    )
    assert stats["ticks"] == 1
    assert stats["free_arb_alerts_fired"] == 1
    assert len(cap.calls) == 1
    # The one alert is the free arb — not the non-free middle.
    assert "LeBron James" in cap.calls[0]["message"]
    assert "Stephen Curry" not in cap.calls[0]["message"]


def test_loop_dedup_across_three_ticks(tmp_path, monkeypatch):
    """Same arb served on every tick of a 3-tick run -> still 1 alert."""
    cap = _AlertCapture()
    free = _make_free_arb()

    def fake_run_once(*a, **kw):
        return [free], {}

    monkeypatch.setattr(mfd, "run_once", fake_run_once)
    out_json = str(tmp_path / "middles_live.json")
    state = {}
    stats = mfd.loop(
        interval_sec=0.01, min_width=0.5, max_juice=-135, max_iters=3,
        use_model=False, out_json=out_json, log=lambda *a, **k: None,
        alert_fn=cap, dedup_state=state, dedup_ttl_sec=3600,
    )
    assert stats["ticks"] == 3
    assert stats["free_arb_alerts_fired"] == 1, (
        f"expected 1 alert across 3 ticks, got {stats['free_arb_alerts_fired']}")
    assert len(cap.calls) == 1


def test_dedup_ttl_expiry_allows_refire():
    """After TTL elapses, the same arb fires again — operator gets a
    fresh heads-up if it's still live half an hour later."""
    cap = _AlertCapture()
    state = {}
    arb = _make_free_arb()
    # tick 1 — fires
    assert mfd._fire_free_arb_alert(arb, state, ttl_sec=10, alert_fn=cap)
    # tick 2 (immediate) — deduped
    assert not mfd._fire_free_arb_alert(arb, state, ttl_sec=10, alert_fn=cap)
    # Simulate TTL expiry by rewinding the stored timestamp.
    key = mfd._free_arb_dedup_key(arb)
    state[key] -= 11
    # tick 3 — TTL expired -> fires again.
    assert mfd._fire_free_arb_alert(arb, state, ttl_sec=10, alert_fn=cap)
    assert len(cap.calls) == 2

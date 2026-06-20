"""Per-file tests for the recency + dead-market gate added to build_slate.

Verifies QA iter 9/10 P1+P2 fixes:
  (a) a matchup with tipoff 24 h in the past is dropped (or stamped stale).
  (b) a 'Yes vs No' binary matchup is excluded.
  (c) a fresh future matchup is unchanged and status='ok'.
  (d) the response carries no $ field and honest_note is present.

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \\
    python -m pytest scripts/platformkit/frontend/test_slate_recency_gate.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.platformkit.frontend import slate as slate_mod

# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

_T_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
_T_PAST_24H = (_T_NOW - timedelta(hours=24)).isoformat()
_T_PAST_3H = (_T_NOW - timedelta(hours=3)).isoformat()
_T_FUTURE_2H = (_T_NOW + timedelta(hours=2)).isoformat()


class _StubPredictor:
    """Minimal predictor stub: .predict() returns a canned pregame block."""

    def predict(self, home, away, **kwargs):  # noqa: ANN001
        return {
            "p_home_win": 0.55,
            "total_mean": 215.0,
            "honest_note": "Moneyline matches the devigged close.",
        }


def _stub_factory(sport):  # noqa: ANN001
    return _StubPredictor()


def _stub_factory_none(sport):  # noqa: ANN001
    return None


# ---------------------------------------------------------------------------
# (a) Tipoff 24 h in the past: dropped or stale
# ---------------------------------------------------------------------------

def test_past_24h_tipoff_is_dropped_or_stale():
    """A matchup whose tipoff was 24 h ago must not appear as status='ok'."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "NYK", "away": "SAS", "tipoff_utc": _T_PAST_24H}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    rows = payload["rows"]
    # The row must either be absent (dropped) or flagged stale -- never ok.
    if rows:
        row = rows[0]
        assert row.get("status") != "ok", (
            f"Past-24h tipoff served as ok: {row}"
        )
        assert row.get("stale") is True or row.get("status") == "stale"
    else:
        # Row was dropped -- gate_dropped should be non-zero.
        assert payload.get("gate_dropped", 0) >= 1


def test_past_24h_tipoff_absent_from_ok_rows():
    """Convenience: no row with status='ok' survives a 24 h stale tipoff."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "NYK", "away": "SAS", "tipoff_utc": _T_PAST_24H},
                  {"home": "BOS", "away": "LAL", "tipoff_utc": _T_FUTURE_2H}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    ok_matchups = [r["matchup"] for r in payload["rows"] if r.get("status") == "ok"]
    assert "NYK vs SAS" not in ok_matchups, (
        "Stale 24h matchup must not appear as ok"
    )


# ---------------------------------------------------------------------------
# (b) 'Yes vs No' binary excluded
# ---------------------------------------------------------------------------

def test_yes_vs_no_binary_excluded():
    """A Polymarket-style 'Yes vs No' matchup must be dropped."""
    payload = slate_mod.build_slate(
        "soccer_intl",
        matchups=[{"home": "Yes", "away": "No"}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    rows = payload["rows"]
    assert rows == [], f"'Yes vs No' binary must be dropped; got {rows}"
    assert payload.get("gate_dropped", 0) >= 1


def test_yes_vs_no_binary_both_orderings():
    """Both 'Yes vs No' and 'No vs Yes' must be dropped."""
    for home, away in [("Yes", "No"), ("No", "Yes")]:
        payload = slate_mod.build_slate(
            "soccer_intl",
            matchups=[{"home": home, "away": away}],
            predictor_factory=_stub_factory,
            now=_T_NOW,
        )
        assert payload["rows"] == [], (
            f"Binary '{home} vs {away}' must be dropped"
        )


# ---------------------------------------------------------------------------
# (c) Fresh future matchup is unchanged and status='ok'
# ---------------------------------------------------------------------------

def test_future_matchup_passes_unchanged():
    """A matchup with a future tipoff must survive the gate with status='ok'."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "BOS", "away": "LAL", "tipoff_utc": _T_FUTURE_2H}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    assert payload["status"] in {"ok", "unavailable"}
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["matchup"] == "BOS vs LAL"
    assert row["status"] == "ok"
    assert row.get("stale") is not True
    assert row.get("hours_old") is None


def test_no_tipoff_passes_unchanged():
    """A matchup without any tipoff key must not be dropped (do not block on missing data)."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "DEN", "away": "GSW"}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["status"] == "ok"


# ---------------------------------------------------------------------------
# (d) No $ field; honest_note present
# ---------------------------------------------------------------------------

_DOLLAR_KEYS = {"pnl", "roi", "profit", "usd", "dollar", "stake_usd", "expected_return_usd"}


def _has_dollar_field(obj) -> bool:  # noqa: ANN001
    """Recursively check for any $ / ROI / profit field in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in _DOLLAR_KEYS or k.startswith("$"):
                return True
            if _has_dollar_field(v):
                return True
    elif isinstance(obj, list):
        return any(_has_dollar_field(i) for i in obj)
    return False


def test_no_dollar_fields_and_honest_note_present():
    """Slate payload must carry honest_note and zero $ / ROI / profit fields."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "BOS", "away": "LAL", "tipoff_utc": _T_FUTURE_2H}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    assert "honest_note" in payload, "honest_note key must be present"
    assert payload["honest_note"], "honest_note must be non-empty"
    assert not _has_dollar_field(payload), (
        "Slate payload must not contain $ / ROI / profit fields"
    )


def test_mixed_slate_gate():
    """Gate drops stale + binary rows; fresh row survives; honest_note present."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[
            # Stale: 24 h past
            {"home": "NYK", "away": "SAS", "tipoff_utc": _T_PAST_24H},
            # Binary: should be dropped
            {"home": "Yes", "away": "No"},
            # Fresh: should survive
            {"home": "BOS", "away": "LAL", "tipoff_utc": _T_FUTURE_2H},
        ],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    ok_rows = [r for r in payload["rows"] if r.get("status") == "ok"]
    matchups_ok = {r["matchup"] for r in ok_rows}
    # Fresh matchup must survive as ok.
    assert "BOS vs LAL" in matchups_ok
    # Stale + binary must not appear as ok.
    assert "NYK vs SAS" not in matchups_ok
    assert "Yes vs No" not in {r["matchup"] for r in payload["rows"]}
    assert not _has_dollar_field(payload)
    assert "honest_note" in payload


# ---------------------------------------------------------------------------
# Dead-market gate tests
# ---------------------------------------------------------------------------

def test_dead_market_prob_dropped():
    """A matchup whose market has market_prob near zero must be dropped."""
    def market_lookup(sport, home, away):  # noqa: ANN001
        return {"line": "Yes -9999", "p_home_implied": 0.0005}

    payload = slate_mod.build_slate(
        "soccer_intl",
        matchups=[{"home": "England", "away": "Croatia", "tipoff_utc": _T_FUTURE_2H}],
        predictor_factory=_stub_factory,
        market_lookup=market_lookup,
        now=_T_NOW,
    )
    # The market_prob (0.0005) is below DEAD_MARKET_PROB (0.001) -> must be dropped.
    rows = payload["rows"]
    assert rows == [] or all(r.get("status") != "ok" for r in rows)
    assert payload.get("gate_dropped", 0) >= 1


# ---------------------------------------------------------------------------
# Stamp (0-6 h past) path
# ---------------------------------------------------------------------------

def test_tipoff_3h_past_is_stamped_not_dropped():
    """A tipoff 3 h past (within 6 h window) must be stamped stale, not dropped."""
    payload = slate_mod.build_slate(
        "nba",
        matchups=[{"home": "NYK", "away": "SAS", "tipoff_utc": _T_PAST_3H}],
        predictor_factory=_stub_factory,
        now=_T_NOW,
    )
    # Row must be present (not dropped) and stamped stale.
    rows = payload["rows"]
    assert len(rows) == 1, f"3h stale row should be stamped, not dropped: {rows}"
    row = rows[0]
    assert row.get("stale") is True
    assert row.get("status") == "stale"
    assert isinstance(row.get("hours_old"), float)
    assert 2.9 < row["hours_old"] < 3.1

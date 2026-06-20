"""Per-file test for scripts.platformkit.bestbets.slate_ev_recency_gate (R6-5).

Acceptance criteria:
  A. tipoff 11mo past + matchup 'Yes vs No'  -> DROPPED
  B. ev=683.2 row (otherwise valid)          -> DROPPED or capped+ev_capped=True
  C. current-day team-vs-team row             -> KEPT unchanged (no ev_capped key)
  D. No $ / roi / pnl / bankroll / profit / stake / usd / dollar field in output
  E. Pure: input list not mutated; input card dicts not mutated
  F. Never raises on garbage input
  G. Empty input -> empty output
  H. Non-string matchup -> DROPPED (not a team-vs-team row)
  I. tipoff within window + valid matchup     -> KEPT
  J. ev at exactly EV_CAP -> NOT capped; ev just above -> capped
  K. ev_raw preserved on capped row; ev_cap_note set (no $ content)
  L. Negative pathological ev capped to -EV_CAP (sign preserved)

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_slate_ev_recency_gate.py -q

RAILS: ASCII only; per-file only; no full pytest suite; no $ fields.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from scripts.platformkit.bestbets.slate_ev_recency_gate import (
    EV_CAP,
    EV_CAP_NOTE,
    STALE_TIPOFF_HOURS,
    apply_ev_recency_gate,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Fixed reference time for all tests.
_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

# Tipoff scenarios relative to _NOW.
_TIPOFF_FUTURE = (_NOW + timedelta(hours=3)).isoformat()
_TIPOFF_TODAY_JUST_INSIDE = (_NOW - timedelta(hours=STALE_TIPOFF_HOURS - 1)).isoformat()
_TIPOFF_STALE = (_NOW - timedelta(hours=STALE_TIPOFF_HOURS + 1)).isoformat()
_TIPOFF_11MO_PAST = (_NOW - timedelta(days=335)).isoformat()  # ~11 months

FORBIDDEN_KEYS = frozenset({
    "pnl", "roi", "bankroll", "profit", "stake", "usd", "dollar",
})


def _no_forbidden(obj: Any) -> bool:
    """Return True when obj (recursively) contains no forbidden $ keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                return False
            if not _no_forbidden(v):
                return False
    elif isinstance(obj, (list, tuple)):
        return all(_no_forbidden(item) for item in obj)
    return True


def _row(**overrides) -> Dict[str, Any]:
    """Build a minimal valid slate row that passes all gate checks."""
    base: Dict[str, Any] = {
        "game_id": "nba_001",
        "matchup": "Celtics vs Lakers",
        "sport": "nba",
        "tipoff_utc": _TIPOFF_FUTURE,
        "ev": 0.08,
        "edge_vs_market": 0.08,
        "market_prob": 0.50,
        "model_prob": 0.58,
        "tier": "A",
        "confidence": 0.58,
    }
    base.update(overrides)
    return base


def _gate(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Run the gate with the fixed reference time."""
    return apply_ev_recency_gate(rows, now=_NOW)


# ---------------------------------------------------------------------------
# A. tipoff 11mo past + matchup 'Yes vs No' -> DROPPED
# ---------------------------------------------------------------------------

class TestAcceptanceCriteriaA:
    """QA iter 10 P1: Polymarket binary with 11mo stale tipoff."""

    def test_yes_vs_no_11mo_past_dropped(self):
        """Replicates the exact QA bug: 'Yes vs No', tipoff ~11mo past."""
        row = _row(
            game_id="polymarket_binary",
            matchup="Yes vs No",
            tipoff_utc=_TIPOFF_11MO_PAST,
            ev=683.2,
            edge_vs_market=683.2,
            market_prob=0.0005,
        )
        result = _gate([row])
        assert result == [], "Polymarket 11mo binary must be dropped"

    def test_yes_vs_no_any_stale_dropped(self):
        """'Yes vs No' matchup with ANY past tipoff -> dropped."""
        row = _row(matchup="Yes vs No", tipoff_utc=_TIPOFF_STALE, ev=10.0)
        assert _gate([row]) == []

    def test_yes_vs_no_future_tipoff_dropped(self):
        """'Yes vs No' matchup is dropped even with a future tipoff (non-sports binary)."""
        row = _row(matchup="Yes vs No", tipoff_utc=_TIPOFF_FUTURE, ev=0.05)
        assert _gate([row]) == []

    def test_yes_vs_no_case_insensitive(self):
        """'YES VS NO' and 'yes vs no' variants all dropped."""
        for variant in ("YES VS NO", "yes vs no", "Yes Vs No", "Market: yes vs no"):
            row = _row(matchup=variant, tipoff_utc=_TIPOFF_FUTURE)
            assert _gate([row]) == [], f"Variant {variant!r} should be dropped"


# ---------------------------------------------------------------------------
# B. ev=683.2 row (with valid matchup + recent tipoff) -> dropped or capped
# ---------------------------------------------------------------------------

class TestAcceptanceCriteriaB:
    """ev=683.2 on a valid row must not pass through uncapped."""

    def test_ev_683_valid_matchup_recent_tipoff_capped(self):
        """ev=683.2, valid matchup, recent tipoff -> kept but capped to EV_CAP."""
        row = _row(ev=683.2, edge_vs_market=683.2, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        assert len(result) == 1, "Row with valid matchup/tipoff must be kept"
        out = result[0]
        assert out.get("ev_capped") is True, "ev_capped must be True"
        assert abs(out["ev"]) <= EV_CAP, f"ev must be <= EV_CAP={EV_CAP}"
        assert abs(out["edge_vs_market"]) <= EV_CAP, "edge_vs_market must also be capped"

    def test_ev_683_stale_tipoff_dropped(self):
        """ev=683.2 + stale tipoff -> dropped (stale-never-green takes priority)."""
        row = _row(ev=683.2, tipoff_utc=_TIPOFF_STALE)
        assert _gate([row]) == []

    def test_ev_raw_preserved_on_capped_row(self):
        """ev_raw preserves the original value before capping."""
        row = _row(ev=683.2, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        assert len(result) == 1
        assert result[0].get("ev_raw") == pytest.approx(683.2)

    def test_ev_cap_note_present(self):
        """ev_cap_note is set on capped rows and contains no $ content."""
        row = _row(ev=100.0, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        note = result[0].get("ev_cap_note", "")
        assert note, "ev_cap_note must be non-empty"
        # Must not contain forbidden $ terms
        for bad in ("profit", "roi", "pnl", "dollar", "usd", "stake"):
            assert bad not in note.lower(), f"ev_cap_note must not contain '{bad}'"


# ---------------------------------------------------------------------------
# C. Current-day team-vs-team row -> KEPT unchanged
# ---------------------------------------------------------------------------

class TestAcceptanceCriteriaC:
    """Valid current-day team-vs-team rows must pass through untouched."""

    def test_clean_nba_row_kept(self):
        """Valid NBA row: matchup, recent tipoff, normal ev -> kept unchanged."""
        row = _row(sport="nba", matchup="Celtics vs Lakers", ev=0.08,
                   tipoff_utc=_TIPOFF_FUTURE)
        original = copy.deepcopy(row)
        result = _gate([row])
        assert len(result) == 1
        out = result[0]
        assert out["matchup"] == "Celtics vs Lakers"
        assert out["ev"] == original["ev"]
        assert "ev_capped" not in out, "ev_capped must NOT appear on a clean row"

    def test_clean_soccer_row_kept(self):
        """Valid soccer_intl row -> kept."""
        row = _row(sport="soccer_intl", matchup="Brazil vs Argentina",
                   tipoff_utc=_TIPOFF_FUTURE, ev=0.05)
        result = _gate([row])
        assert len(result) == 1
        assert result[0]["sport"] == "soccer_intl"

    def test_clean_mlb_row_kept(self):
        """Valid MLB row -> kept."""
        row = _row(sport="mlb", matchup="Yankees vs Red Sox",
                   tipoff_utc=_TIPOFF_FUTURE, ev=0.04)
        result = _gate([row])
        assert len(result) == 1

    def test_multi_row_only_bad_dropped(self):
        """Mixed batch: only the 'Yes vs No' + stale rows are removed."""
        rows = [
            _row(game_id="clean1", matchup="Celtics vs Lakers", tipoff_utc=_TIPOFF_FUTURE),
            _row(game_id="binary", matchup="Yes vs No", tipoff_utc=_TIPOFF_FUTURE),
            _row(game_id="stale", matchup="France vs Germany", tipoff_utc=_TIPOFF_STALE),
            _row(game_id="clean2", matchup="Bulls vs Heat", tipoff_utc=_TIPOFF_FUTURE),
        ]
        result = _gate(rows)
        ids = {r["game_id"] for r in result}
        assert ids == {"clean1", "clean2"}


# ---------------------------------------------------------------------------
# D. No $ / roi / pnl / bankroll field in output
# ---------------------------------------------------------------------------

class TestNoForbiddenFields:

    def test_clean_row_no_forbidden_keys(self):
        """Clean row output has no forbidden $ keys."""
        result = _gate([_row()])
        assert _no_forbidden(result), "Forbidden $ key found in output"

    def test_capped_row_no_forbidden_keys(self):
        """Capped row (ev=100) output has no forbidden $ keys."""
        result = _gate([_row(ev=100.0, tipoff_utc=_TIPOFF_FUTURE)])
        assert _no_forbidden(result), "Forbidden $ key found in capped output"

    def test_empty_output_no_forbidden_keys(self):
        """All-dropped output: still no forbidden $ keys."""
        result = _gate([_row(matchup="Yes vs No")])
        assert _no_forbidden(result)

    def test_ev_cap_note_no_dollar_terms(self):
        """EV_CAP_NOTE constant does not contain forbidden $ terms."""
        for term in ("profit", "roi", "pnl", "dollar", "usd", "stake", "bankroll"):
            assert term not in EV_CAP_NOTE.lower(), \
                f"EV_CAP_NOTE must not contain '{term}'"


# ---------------------------------------------------------------------------
# E. Purity: input list and dicts never mutated
# ---------------------------------------------------------------------------

class TestPurity:

    def test_input_list_not_mutated(self):
        """apply_ev_recency_gate must not mutate the input list."""
        rows = [
            _row(game_id="a"),
            _row(game_id="b", matchup="Yes vs No"),
        ]
        original_len = len(rows)
        _gate(rows)
        assert len(rows) == original_len

    def test_input_dict_not_mutated_on_clean_row(self):
        """Input dicts must not be mutated for clean rows."""
        row = _row(game_id="x", ev=0.08)
        original = copy.deepcopy(row)
        _gate([row])
        assert row == original

    def test_input_dict_not_mutated_on_capped_row(self):
        """Input dicts must not be mutated even when EV is capped."""
        row = _row(ev=999.0, tipoff_utc=_TIPOFF_FUTURE)
        original = copy.deepcopy(row)
        _gate([row])
        assert row == original, "Input dict must not be mutated by EV cap"
        assert row["ev"] == 999.0, "Original ev must be unchanged in input"

    def test_returned_list_is_new_object(self):
        """Returned list is a new object."""
        rows = [_row()]
        result = _gate(rows)
        assert result is not rows

    def test_returned_dicts_are_new_objects(self):
        """Returned card dicts are new copies."""
        row = _row()
        result = _gate([row])
        assert len(result) == 1
        assert result[0] is not row


# ---------------------------------------------------------------------------
# F. Never raises on garbage input
# ---------------------------------------------------------------------------

class TestNeverRaises:

    def test_empty_list_no_raise(self):
        result = apply_ev_recency_gate([], now=_NOW)
        assert result == []

    def test_none_input_no_raise(self):
        result = apply_ev_recency_gate(None, now=_NOW)  # type: ignore[arg-type]
        assert result == []

    def test_non_list_input_no_raise(self):
        result = apply_ev_recency_gate("garbage", now=_NOW)  # type: ignore[arg-type]
        assert isinstance(result, list)

    def test_list_with_none_entries_no_raise(self):
        """None entries inside list -> silently dropped, no raise."""
        result = apply_ev_recency_gate([None, None, _row()], now=_NOW)
        assert isinstance(result, list)

    def test_list_with_mixed_garbage_no_raise(self):
        result = apply_ev_recency_gate([42, "bad", True, _row()], now=_NOW)  # type: ignore[list-item]
        assert isinstance(result, list)

    def test_row_with_all_none_values_no_raise(self):
        row = {k: None for k in ["matchup", "tipoff_utc", "ev", "edge_vs_market"]}
        apply_ev_recency_gate([row], now=_NOW)

    def test_empty_dict_no_raise(self):
        """Completely empty dict -> silently dropped (non-string matchup)."""
        apply_ev_recency_gate([{}], now=_NOW)

    def test_large_mixed_batch_no_raise(self):
        rows = (
            [_row(game_id=f"ok{i}") for i in range(30)]
            + [_row(matchup="Yes vs No") for _ in range(10)]
            + [_row(tipoff_utc=_TIPOFF_STALE) for _ in range(10)]
            + [None, "garbage", 42]  # type: ignore[list-item]
        )
        result = apply_ev_recency_gate(rows, now=_NOW)
        assert len(result) == 30


# ---------------------------------------------------------------------------
# G. Empty input -> empty output
# ---------------------------------------------------------------------------

class TestEmptyInput:

    def test_empty_list_returns_empty(self):
        assert _gate([]) == []

    def test_all_dropped_returns_empty(self):
        rows = [
            _row(matchup="Yes vs No"),
            _row(tipoff_utc=_TIPOFF_STALE),
        ]
        assert _gate(rows) == []


# ---------------------------------------------------------------------------
# H. Non-string matchup -> DROPPED
# ---------------------------------------------------------------------------

class TestNonStringMatchup:

    def test_none_matchup_dropped(self):
        """matchup=None -> dropped (not a team-vs-team row)."""
        row = _row(matchup=None)
        assert _gate([row]) == []

    def test_int_matchup_dropped(self):
        """matchup=42 -> dropped."""
        row = _row(matchup=42)
        assert _gate([row]) == []

    def test_empty_string_matchup_dropped(self):
        """matchup='' -> dropped."""
        row = _row(matchup="")
        assert _gate([row]) == []

    def test_list_matchup_dropped(self):
        """matchup=[] -> dropped."""
        row = _row(matchup=[])
        assert _gate([row]) == []


# ---------------------------------------------------------------------------
# I. tipoff within window + valid matchup -> KEPT
# ---------------------------------------------------------------------------

class TestTipoffWithinWindow:

    def test_tipoff_1h_ago_within_12h_window_kept(self):
        """tipoff 1h ago is within the 12h window -> kept."""
        tipoff = (_NOW - timedelta(hours=1)).isoformat()
        row = _row(tipoff_utc=tipoff)
        result = _gate([row])
        assert len(result) == 1

    def test_tipoff_just_inside_window_kept(self):
        """tipoff at exactly STALE_TIPOFF_HOURS - 1 hours -> kept."""
        result = _gate([_row(tipoff_utc=_TIPOFF_TODAY_JUST_INSIDE)])
        assert len(result) == 1

    def test_tipoff_future_kept(self):
        """Future tipoff -> kept."""
        result = _gate([_row(tipoff_utc=_TIPOFF_FUTURE)])
        assert len(result) == 1

    def test_no_tipoff_field_kept(self):
        """Row with no tipoff key -> not dropped on this criterion alone."""
        row = _row()
        del row["tipoff_utc"]
        result = _gate([row])
        assert len(result) == 1

    def test_none_tipoff_kept(self):
        """tipoff_utc=None -> not dropped on this criterion alone."""
        result = _gate([_row(tipoff_utc=None)])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# J. EV boundary: exactly EV_CAP not capped; above EV_CAP capped
# ---------------------------------------------------------------------------

class TestEvBoundary:

    def test_ev_exactly_at_cap_not_capped(self):
        """ev exactly == EV_CAP -> NOT capped; ev_capped must not appear."""
        row = _row(ev=EV_CAP, edge_vs_market=EV_CAP)
        result = _gate([row])
        assert len(result) == 1
        out = result[0]
        assert "ev_capped" not in out, "ev_capped must not appear at boundary"
        assert out["ev"] == pytest.approx(EV_CAP)

    def test_ev_just_above_cap_is_capped(self):
        """ev = EV_CAP + 0.001 -> capped."""
        row = _row(ev=EV_CAP + 0.001)
        result = _gate([row])
        out = result[0]
        assert out.get("ev_capped") is True
        assert abs(out["ev"]) <= EV_CAP

    def test_ev_zero_not_capped(self):
        """ev=0 -> not capped."""
        row = _row(ev=0.0)
        result = _gate([row])
        assert "ev_capped" not in result[0]

    def test_negative_ev_at_minus_cap_not_capped(self):
        """ev = -EV_CAP -> not capped."""
        row = _row(ev=-EV_CAP)
        result = _gate([row])
        assert "ev_capped" not in result[0]

    def test_negative_ev_below_cap_capped(self):
        """ev = -(EV_CAP + 1) -> capped to -EV_CAP."""
        row = _row(ev=-(EV_CAP + 1.0))
        result = _gate([row])
        out = result[0]
        assert out.get("ev_capped") is True
        assert out["ev"] == pytest.approx(-EV_CAP)

    def test_no_ev_field_not_capped(self):
        """Row with no ev/edge_vs_market field -> not capped, no ev_capped key."""
        row = _row()
        del row["ev"]
        del row["edge_vs_market"]
        result = _gate([row])
        assert "ev_capped" not in result[0]


# ---------------------------------------------------------------------------
# K. ev_raw and ev_cap_note on capped rows
# ---------------------------------------------------------------------------

class TestEvCapMetadata:

    def test_ev_raw_is_original_value(self):
        """ev_raw preserves the pre-cap EV."""
        raw_ev = 42.7
        row = _row(ev=raw_ev, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        assert result[0]["ev_raw"] == pytest.approx(raw_ev)

    def test_ev_cap_note_is_ascii(self):
        """ev_cap_note must be ASCII-safe (no Unicode)."""
        row = _row(ev=100.0, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        note = result[0].get("ev_cap_note", "")
        note.encode("ascii")  # raises UnicodeEncodeError if not ASCII


# ---------------------------------------------------------------------------
# L. Negative pathological EV capped with sign preserved
# ---------------------------------------------------------------------------

class TestNegativeEvCap:

    def test_large_negative_ev_capped_to_minus_ev_cap(self):
        """ev=-683.2 -> capped to -EV_CAP (sign preserved)."""
        row = _row(ev=-683.2, tipoff_utc=_TIPOFF_FUTURE)
        result = _gate([row])
        out = result[0]
        assert out.get("ev_capped") is True
        assert out["ev"] == pytest.approx(-EV_CAP)
        assert out["ev_raw"] == pytest.approx(-683.2)


# ---------------------------------------------------------------------------
# Integration: full board scenario replicating QA iter 10 P1
# ---------------------------------------------------------------------------

class TestIntegration:

    def test_qa_iter10_p1_scenario(self):
        """Full replication of QA iter 10 P1 raw :8098 slate bug.

        Board contains:
          * Polymarket 'Yes vs No', tipoff 11mo past, ev=683.2 -> DROPPED
          * Stale soccer card, tipoff 13h past -> DROPPED
          * Clean NBA card, future tipoff, ev=0.08 -> KEPT unchanged
          * Capped NBA card, future tipoff, ev=15.0 -> KEPT, ev_capped=True
        """
        rows = [
            _row(
                game_id="pm_binary",
                matchup="Yes vs No",
                sport="soccer_intl",
                tipoff_utc=_TIPOFF_11MO_PAST,
                ev=683.2,
                edge_vs_market=683.2,
            ),
            _row(
                game_id="stale_soccer",
                matchup="France vs Germany",
                sport="soccer_intl",
                tipoff_utc=(_NOW - timedelta(hours=13)).isoformat(),
                ev=0.05,
            ),
            _row(
                game_id="clean_nba",
                matchup="Celtics vs Lakers",
                sport="nba",
                tipoff_utc=_TIPOFF_FUTURE,
                ev=0.08,
            ),
            _row(
                game_id="capped_nba",
                matchup="Bulls vs Heat",
                sport="nba",
                tipoff_utc=_TIPOFF_FUTURE,
                ev=15.0,
            ),
        ]
        result = _gate(rows)
        ids = {r["game_id"] for r in result}

        assert "pm_binary" not in ids, "QA P1 Polymarket binary must be dropped"
        assert "stale_soccer" not in ids, "Stale soccer row must be dropped"
        assert "clean_nba" in ids, "Clean NBA row must survive"
        assert "capped_nba" in ids, "Capped NBA row must survive (after capping)"

        clean = next(r for r in result if r["game_id"] == "clean_nba")
        assert clean["ev"] == pytest.approx(0.08)
        assert "ev_capped" not in clean

        capped = next(r for r in result if r["game_id"] == "capped_nba")
        assert capped.get("ev_capped") is True
        assert abs(capped["ev"]) <= EV_CAP
        assert capped.get("ev_raw") == pytest.approx(15.0)

        assert _no_forbidden(result), "Forbidden $ key in output"

    def test_order_preserved(self):
        """Surviving rows appear in original input order."""
        rows = [
            _row(game_id="a", matchup="Celtics vs Lakers"),
            _row(game_id="b", matchup="Yes vs No"),    # dropped
            _row(game_id="c", matchup="France vs Germany", tipoff_utc=_TIPOFF_FUTURE),
            _row(game_id="d", tipoff_utc=_TIPOFF_STALE),  # dropped
            _row(game_id="e", matchup="Cubs vs Cardinals"),
        ]
        result = _gate(rows)
        ids = [r["game_id"] for r in result]
        assert ids == ["a", "c", "e"]

    def test_injectable_now_controls_stale_threshold(self):
        """Injecting different 'now' changes the stale verdict."""
        tipoff_str = (_NOW - timedelta(hours=10)).isoformat()  # 10h ago
        row = _row(tipoff_utc=tipoff_str)

        # With default 12h window: 10h ago is NOT stale -> kept
        result_kept = apply_ev_recency_gate([row], now=_NOW)
        assert len(result_kept) == 1, "10h ago is within 12h window"

        # With 8h window: 10h ago IS stale -> dropped
        result_dropped = apply_ev_recency_gate([row], now=_NOW, stale_hours=8)
        assert result_dropped == [], "10h ago is stale when window=8h"

    def test_injectable_ev_cap(self):
        """Injecting a tighter ev_cap fires the cap at a lower threshold."""
        row = _row(ev=3.0, tipoff_utc=_TIPOFF_FUTURE)

        # With default EV_CAP=5.0: ev=3.0 not capped
        result_uncapped = apply_ev_recency_gate([row], now=_NOW, ev_cap=5.0)
        assert "ev_capped" not in result_uncapped[0]

        # With ev_cap=2.0: ev=3.0 is capped
        result_capped = apply_ev_recency_gate([row], now=_NOW, ev_cap=2.0)
        assert result_capped[0].get("ev_capped") is True
        assert abs(result_capped[0]["ev"]) <= 2.0

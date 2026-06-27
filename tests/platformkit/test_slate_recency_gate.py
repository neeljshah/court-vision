"""Per-file test for slate_recency_gate (BE-E-slate-recency-gate, QA iter 9/10).

Acceptance criteria:
  1. A game tipoff 150 h past -> dropped (hours_old >= 150).
  2. A Yes/No binary (tipoff 2025-07-02) -> dropped.
  3. A game tipoff 1 h future -> retained with no stale flag.
  4. Output preserves all non-stale fields (no field removed from kept games).
  5. No $ field added to any row.
  6. Works on both payload shapes: {"games":[...]} and {"rows":[...]}.
  7. A game tipoff 3 h past (within default 6 h window) -> stamped stale=True,
     hours_old~3, status='stale' (not dropped).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \\
    tests/platformkit/test_slate_recency_gate.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.platformkit.frontend.slate_recency_gate import apply_recency_gate, STALE_DROP_HOURS

# Reference "now": 2026-06-20T12:00:00Z (post NBA-Finals offseason)
_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

# Completed NBA Finals game -- tipoff 2026-06-14, ~150 h before _NOW.
_FINALS_GAME = {
    "game_id": "401859967",
    "home": "New York Knicks",
    "away": "San Antonio Spurs",
    "tipoff": "2026-06-14T00:00:00+00:00",
    "status": "ok",
    "p_home_win": 0.53,
    "note": "MATCH",
}

# Polymarket Yes/No binary, tipoff 2025-07-02 (~11 months past).
_BINARY_GAME = {
    "game_id": "558934",
    "home": "Yes",
    "away": "No",
    "tipoff": "2025-07-02T00:00:00+00:00",
    "status": "ok",
    "edges": [{"model_prob": 0.3421, "market_prob": 0.0005, "ev": 683.2}],
}

# Future game: tipoff 1 h from _NOW = 2026-06-20T13:00:00Z.
_FUTURE_GAME = {
    "game_id": "999",
    "home": "England",
    "away": "Croatia",
    "tipoff": "2026-06-20T13:00:00+00:00",
    "status": "ok",
    "p_home_win": 0.42,
    "market": "-110",
    "edge": 0.03,
    "verdict": "MATCH",
    "note": "Pregame MATCHES close.",
}

# Recent game: tipoff 3 h before _NOW = 2026-06-20T09:00:00Z (inside 6 h window).
_RECENT_GAME = {
    "game_id": "888",
    "home": "Portugal",
    "away": "Ghana",
    "tipoff": "2026-06-20T09:00:00+00:00",
    "status": "ok",
    "p_home_win": 0.61,
}


# -------------------------------------------------------------------------
# Games-shape tests ({"games": [...]})
# -------------------------------------------------------------------------

class TestGamesShape:
    def test_past_150h_game_dropped(self):
        """NYK@SAS game (150 h past) must be dropped -- not served as live pregame."""
        payload = {"sport": "nba", "status": "ok", "games": [_FINALS_GAME, _FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        ids = [g["game_id"] for g in out["games"]]
        assert "401859967" not in ids, "150-h-old Finals game must be dropped"
        assert "999" in ids, "future game must survive"
        assert out.get("recency_dropped") == 1

    def test_yes_no_binary_dropped(self):
        """Non-sports Yes/No binary (558934, 11 months past) must be dropped."""
        payload = {"sport": "soccer_intl", "status": "ok",
                   "games": [_BINARY_GAME, _FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        ids = [g["game_id"] for g in out["games"]]
        assert "558934" not in ids, "Yes/No Polymarket binary must be dropped"
        assert "999" in ids

    def test_future_game_retained_no_stale_flag(self):
        """A game with tipoff 1 h in the future must survive with no stale annotation."""
        payload = {"sport": "soccer_intl", "status": "ok", "games": [_FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        assert len(out["games"]) == 1
        g = out["games"][0]
        assert g["game_id"] == "999"
        assert "stale" not in g, "future game must not carry stale flag"
        assert "hours_old" not in g, "future game must not carry hours_old"
        assert "recency_dropped" not in out
        assert "recency_stamped" not in out

    def test_recent_past_game_stamped_not_dropped(self):
        """A game 3 h past tipoff (within 6 h window) -> stamped stale, not dropped."""
        payload = {"sport": "soccer_intl", "status": "ok", "games": [_RECENT_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        assert len(out["games"]) == 1, "3-h-past game must be STAMPED not dropped"
        g = out["games"][0]
        assert g["stale"] is True
        assert g["status"] == "stale"
        assert g.get("hours_old") is not None
        assert abs(g["hours_old"] - 3.0) < 0.1, "hours_old should be ~3.0"
        assert out.get("recency_stamped") == 1
        assert "recency_dropped" not in out

    def test_output_preserves_all_non_stale_fields(self):
        """Kept games must retain every original field; no field silently removed."""
        payload = {"sport": "soccer_intl", "status": "ok", "games": [_FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        g = out["games"][0]
        for key in _FUTURE_GAME:
            assert key in g, f"field '{key}' was lost from kept game"
            assert g[key] == _FUTURE_GAME[key]

    def test_no_dollar_field_added(self):
        """No $ / PnL / ROI field is added by the gate."""
        payload = {"sport": "nba", "status": "ok",
                   "games": [_FUTURE_GAME, _RECENT_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        forbidden = {"dollar", "pnl", "roi", "profit", "expected_value_dollar",
                     "ev_dollar", "ev_$", "winnings"}
        all_keys = set(out.keys())
        for g in out["games"]:
            all_keys |= set(g.keys())
        dirty = all_keys & {k.lower() for k in forbidden}
        assert not dirty, f"forbidden $ fields present: {dirty}"

    def test_empty_games_list_passthrough(self):
        """An empty games list is returned as-is, no crash."""
        payload = {"sport": "nba", "status": "unavailable", "games": []}
        out = apply_recency_gate(payload, now=_NOW)
        assert out["games"] == []

    def test_non_dict_payload_passthrough(self):
        """Non-dict payloads pass through unchanged (defensive)."""
        assert apply_recency_gate("nope", now=_NOW) == "nope"
        assert apply_recency_gate(None, now=_NOW) is None

    def test_payload_without_games_or_rows_passthrough(self):
        """Payload with no 'games' or 'rows' key is returned unchanged."""
        payload = {"status": "unavailable", "note": "no data"}
        out = apply_recency_gate(payload, now=_NOW)
        assert out == payload

    def test_missing_tipoff_game_retained(self):
        """A game with no tipoff field is retained (we never drop on missing tipoff)."""
        no_tipoff = {"game_id": "notip", "home": "Brazil", "away": "France", "status": "ok"}
        payload = {"sport": "soccer_intl", "games": [no_tipoff]}
        out = apply_recency_gate(payload, now=_NOW)
        assert len(out["games"]) == 1
        assert out["games"][0]["game_id"] == "notip"

    def test_all_past_games_dropped_yields_empty_list(self):
        """When all games are dropped, 'games' is an empty list."""
        payload = {"sport": "nba", "games": [_FINALS_GAME, _BINARY_GAME]}
        out = apply_recency_gate(payload, now=_NOW)
        assert out["games"] == []
        assert out.get("recency_dropped") == 2

    def test_mixed_batch(self):
        """Full batch: 150h-past dropped, binary dropped, 3h-past stamped, future kept."""
        payload = {"sport": "mixed", "games": [
            _FINALS_GAME, _BINARY_GAME, _RECENT_GAME, _FUTURE_GAME,
        ]}
        out = apply_recency_gate(payload, now=_NOW)
        ids = {g["game_id"] for g in out["games"]}
        assert "401859967" not in ids
        assert "558934" not in ids
        assert "888" in ids
        assert "999" in ids
        assert out["recency_dropped"] == 2
        assert out["recency_stamped"] == 1


# -------------------------------------------------------------------------
# Rows-shape tests ({"rows": [...]}) -- flat slate.build_slate output
# -------------------------------------------------------------------------

_FUTURE_ROW = {
    "sport": "nba", "matchup": "BOS vs LAL",
    "tipoff": "2026-06-20T13:00:00+00:00",
    "status": "ok", "model": "P(home)=55.1%",
    "p_home_win": 0.551, "market": "-110", "edge": 0.02,
    "verdict": "MATCH", "note": "Pregame MATCHES close.",
}

_STALE_ROW = {
    "sport": "nba", "matchup": "NYK vs SAS",
    "tipoff": "2026-06-14T00:00:00+00:00",   # 150 h past
    "status": "ok", "model": "P(home)=53.0%",
    "p_home_win": 0.53,
}


class TestRowsShape:
    def test_stale_row_dropped(self):
        """A flat row with tipoff 150 h past must be dropped."""
        payload = {"sport": "nba", "status": "ok", "rows": [_STALE_ROW, _FUTURE_ROW]}
        out = apply_recency_gate(payload, now=_NOW)
        matchups = [r["matchup"] for r in out["rows"]]
        assert "NYK vs SAS" not in matchups
        assert "BOS vs LAL" in matchups
        assert out.get("recency_dropped") == 1

    def test_future_row_retained_no_stale(self):
        """A flat row with tipoff 1 h future is retained unchanged."""
        payload = {"sport": "nba", "status": "ok", "rows": [_FUTURE_ROW]}
        out = apply_recency_gate(payload, now=_NOW)
        assert len(out["rows"]) == 1
        r = out["rows"][0]
        assert "stale" not in r
        assert "hours_old" not in r

    def test_fields_preserved_in_rows(self):
        """Every original field survives in a retained flat row."""
        payload = {"sport": "nba", "rows": [_FUTURE_ROW]}
        out = apply_recency_gate(payload, now=_NOW)
        r = out["rows"][0]
        for key, val in _FUTURE_ROW.items():
            assert key in r and r[key] == val, f"field '{key}' lost or changed"

    def test_no_dollar_field_in_rows(self):
        """No $ field is added to rows-shape output."""
        payload = {"sport": "nba", "rows": [_FUTURE_ROW]}
        out = apply_recency_gate(payload, now=_NOW)
        all_keys = set(out.keys()) | set(out["rows"][0].keys())
        assert "dollar" not in " ".join(all_keys)
        assert "$" not in " ".join(all_keys)


# -------------------------------------------------------------------------
# Threshold / injectable-now behaviour
# -------------------------------------------------------------------------

class TestThresholdBehaviour:
    def test_custom_stale_drop_hours(self):
        """stale_drop_hours=200 means a 150-h-past game is STAMPED not dropped."""
        payload = {"games": [_FINALS_GAME, _FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW, stale_drop_hours=200.0)
        ids = {g["game_id"] for g in out["games"]}
        assert "401859967" in ids, "within 200 h -> stamped not dropped"
        g = next(x for x in out["games"] if x["game_id"] == "401859967")
        assert g["stale"] is True
        assert g.get("hours_old", 0) > 140

    def test_stale_drop_hours_zero_drops_all_past(self):
        """stale_drop_hours=0 means ANY past game is dropped immediately."""
        payload = {"games": [_RECENT_GAME, _FUTURE_GAME]}
        out = apply_recency_gate(payload, now=_NOW, stale_drop_hours=0.0)
        ids = {g["game_id"] for g in out["games"]}
        assert "888" not in ids, "3-h-past game dropped when threshold=0"
        assert "999" in ids

    def test_injectable_now(self):
        """Injecting a past 'now' can make future games appear in the future."""
        past_now = datetime(2026, 6, 14, 1, 0, 0, tzinfo=timezone.utc)
        payload = {"games": [_FINALS_GAME]}
        # With past_now, _FINALS_GAME tipoff (06-14T00:00) is only 1 h past.
        out = apply_recency_gate(payload, now=past_now, stale_drop_hours=6.0)
        assert len(out["games"]) == 1
        g = out["games"][0]
        assert g.get("stale") is True
        assert g.get("hours_old", 0) < 2.0


if __name__ == "__main__":
    import sys
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-q"]))

"""test_season_games_2025_26.py — tier1-3 (loop 5).

Pins the season_games_2025-26.json file contract so cycles 99a/100c/100d's
q1_<stat>_l5 coverage doesn't silently regress when the per-quarter daemon
relies on this season file for game_id enumeration.

Four cases:
1. File exists at the expected path with the v8 schema {v, rows}.
2. 2025-26 game count is plausible (>= 600 — partial-season tolerant, ~1230
   expected by season end).
3. The gamelog-reconstruction fallback gracefully handles bad inputs
   (missing dates, malformed matchups) instead of crashing.
4. The 2025-26 file's column set is a SUPERSET of the minimum required by
   per-quarter-daemon + rest-travel: game_id, season, game_date, plus
   home_team/away_team for the majority of rows.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.fetch_season_games_2025_26 import (  # noqa: E402
    merge,
    reconstruct_from_gamelogs,
)

_PATH = os.path.join(PROJECT_DIR, "data", "nba", "season_games_2025-26.json")


# ── 1. file exists with expected schema ──────────────────────────────────────

def test_file_exists_with_expected_schema():
    """season_games_2025-26.json must live at the canonical path with the
    {v: int, rows: [...]} envelope. This is what the per-quarter daemon
    and rest-travel reconstruction both depend on."""
    assert os.path.exists(_PATH), f"missing: {_PATH}"
    with open(_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    assert isinstance(payload, dict), "envelope must be a dict"
    assert "v" in payload and "rows" in payload, "must carry {v, rows}"
    assert isinstance(payload["rows"], list)
    assert payload["rows"], "rows must be non-empty"
    # Per-row keys at minimum: game_id, season, game_date.
    sample = payload["rows"][0]
    for k in ("game_id", "season", "game_date"):
        assert k in sample, f"row missing required key: {k}"
    # game_id must be 10-char zero-padded string.
    for r in payload["rows"][:50]:
        gid = str(r["game_id"])
        assert len(gid) == 10 and gid.isdigit(), (
            f"game_id must be 10-digit string, got {gid!r}"
        )


# ── 2. plausible game count ──────────────────────────────────────────────────

def test_game_count_at_least_600():
    """A live 2025-26 snapshot mid-season should still have 600+ games.
    Full regular season = 1230 + playoffs."""
    with open(_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    n = len(payload["rows"])
    assert n >= 600, (
        f"2025-26 game count {n} is implausibly low — "
        f"either the fetch broke or only a tiny window was indexed."
    )


# ── 3. gamelog reconstruction handles bad inputs gracefully ──────────────────

def test_reconstruction_handles_malformed_rows(tmp_path, monkeypatch):
    """reconstruct_from_gamelogs must skip — never crash — when a gamelog
    cache has missing dates, unparseable matchups, or zero rows."""
    # Point reconstruction at an empty cache dir → should return [].
    import scripts.fetch_season_games_2025_26 as mod
    monkeypatch.setattr(mod, "_NBA_CACHE", str(tmp_path))
    rows = reconstruct_from_gamelogs("2099-00")
    assert rows == [], "empty cache must yield empty list, no exception"

    # Now drop a fake gamelog file with garbage rows.
    fake = [
        {"game_id": "0022500001", "game_date": "Oct 21, 2025",
         "matchup": "OKC vs. HOU"},          # well-formed
        {"game_id": "0022500002", "game_date": "",
         "matchup": "BOS @ NYK"},             # missing date
        {"game_id": "0022500003", "game_date": "Oct 22, 2025",
         "matchup": "totally garbage"},       # bad matchup
        {"game_id": "", "game_date": "Oct 22, 2025",
         "matchup": "LAL @ GSW"},             # missing game_id
        {"game_id": "0022500005", "game_date": "Oct 23, 2025",
         "matchup": "LAL vs. GSW"},           # well-formed
    ]
    (tmp_path / "gamelog_full_999_2025-26.json").write_text(
        json.dumps(fake), encoding="utf-8"
    )
    rows = reconstruct_from_gamelogs("2025-26")
    gids = {r["game_id"] for r in rows}
    assert "0022500001" in gids
    assert "0022500005" in gids
    # Malformed rows must be dropped silently — not crash, not pass through.
    assert "0022500002" not in gids
    assert "0022500003" not in gids
    # All survivors must have home_team + away_team populated.
    for r in rows:
        assert r["home_team"] and r["away_team"]
        assert r["season"] == "2025-26"


# ── 4. schema matches 2024-25 minimum columns ────────────────────────────────

def test_schema_minimum_matches_2024_25():
    """Every column present in the 2024-25 file's minimum-required set
    (game_id, season, game_date) must also be present in 2025-26. Rich
    columns like home_off_rtg are populated by fetch_historical_seasons.py
    and may be partial — but the structural keys must be uniform."""
    ref_path = os.path.join(PROJECT_DIR, "data", "nba",
                            "season_games_2024-25.json")
    if not os.path.exists(ref_path):
        pytest.skip("no 2024-25 reference file to compare against")
    with open(ref_path, encoding="utf-8") as f:
        ref = json.load(f)
    with open(_PATH, encoding="utf-8") as f:
        new = json.load(f)
    ref_min = {"game_id", "season", "game_date"}
    new_keys = set(new["rows"][0].keys())
    assert ref_min.issubset(new_keys), (
        f"2025-26 missing required keys: {ref_min - new_keys}"
    )
    # Majority of rows should have home_team/away_team populated.
    home_pop = sum(1 for r in new["rows"]
                   if r.get("home_team") and r.get("away_team"))
    frac = home_pop / max(len(new["rows"]), 1)
    assert frac >= 0.5, (
        f"home_team/away_team populated on only {frac:.1%} of rows — "
        f"per-quarter daemon will work but rest-travel won't"
    )


# ── 5. merge preserves rich existing fields ──────────────────────────────────

def test_merge_preserves_existing_rich_fields():
    """merge() must keep any rich fields (off_rtg etc.) already present
    in the existing file when the fresh row only has the minimum keys."""
    existing = {
        "0022500001": {
            "game_id": "0022500001", "season": "2025-26",
            "game_date": "2025-10-21", "home_team": "OKC",
            "away_team": "HOU", "home_off_rtg": 117.5,  # rich field
        }
    }
    fresh = [
        {"game_id": "0022500001", "season": "2025-26",
         "game_date": "2025-10-21", "home_team": "OKC", "away_team": "HOU"},
        {"game_id": "0022500002", "season": "2025-26",
         "game_date": "2025-10-22", "home_team": "BOS", "away_team": "NYK"},
    ]
    merged = merge(existing, fresh)
    by_gid = {r["game_id"]: r for r in merged}
    # Rich field preserved.
    assert by_gid["0022500001"]["home_off_rtg"] == 117.5
    # New row added.
    assert by_gid["0022500002"]["home_team"] == "BOS"

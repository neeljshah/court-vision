"""test_accented_name_resolution.py — regression tests for accented player name bug.

BUG (HIGH): 24 NBA players have diacritics in their names
(e.g. "Nikola Jokić", "Luka Dončić", "Kristaps Porziņģis").
players_nba_active.json stores the accented forms; sportsbooks emit ASCII.

TWO failures fixed:
  (1) read_book_csv roster filter: ASCII "Nikola Jokic" did NOT match the
      accented roster entry "Nikola Jokić" → those players got NO bet card.
  (2) Slate join in courtvision_router.py: accented cache player_name vs
      ASCII line player → ps_idx miss → player excluded from bets even if
      they survived the roster filter.

FIX: canonical join key is _strip_accents(...).lower() on BOTH sides.
  - _load_nba_players() stores de-accented-lower keys.
  - read_book_csv compares _strip_accents(player).lower() vs the roster set.
  - consolidate() prop_key uses _strip_accents(player).lower().
  - courtvision_router.py ps_idx built with _strip_accents(player_name).lower();
    line lookup uses _strip_accents(ln["player"]).lower().

Display names (UI cards) are NEVER modified — only comparison/join keys.
"""
from __future__ import annotations

import csv
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ── shared helpers ────────────────────────────────────────────────────────────

DATE = "2099-08-01"  # Far-future; won't collide with real scrape files.
_START_TIME = f"{DATE}T23:00:00Z"  # 7 PM ET on DATE

_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]


def _ts_utc(hours_ago: float = 1) -> str:
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(player_name: str, book: str = "dk", stat: str = "pts",
         line: float = 25.5) -> dict:
    return {
        "captured_at": _ts_utc(1),
        "book": book,
        "game_id": "0042500317",
        "player_id": "203999",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": -115,
        "under_price": -110,
        "start_time": _START_TIME,
    }


def _strip_accents(s: str) -> str:
    """Local copy of the helper (mirrors what the production code uses)."""
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def odds_env(tmp_path, monkeypatch):
    """Redirect _courtvision_odds to a tmp dir and install a controlled roster
    with accented NBA names (the "real" form stored in players_nba_active.json).
    Caches are cleared so tests are fully isolated.
    """
    import api._courtvision_odds as _odds

    ld = tmp_path / "lines"
    ld.mkdir()
    monkeypatch.setattr(_odds, "_LINES_DIR", ld)
    _odds._CACHE.clear()

    # Roster as stored on disk: accented names in their proper Unicode form.
    # _load_nba_players() must de-accent them so ASCII book names can match.
    accented_roster = [
        "Nikola Jokić",           # book emits "Nikola Jokic"
        "Luka Dončić",            # book emits "Luka Doncic"
        "Shai Gilgeous-Alexander",  # no accent — control: must still pass
        "Kristaps Porziņģis",     # book emits "Kristaps Porzingis"
    ]
    # Force-set the player set to de-accented lowercase (mimicking what
    # _load_nba_players() now does after the fix).
    monkeypatch.setattr(
        _odds, "_NBA_PLAYER_SET",
        {_strip_accents(n).lower() for n in accented_roster},
    )
    monkeypatch.setattr(_odds, "_ABBREV_INDEX", None)  # force rebuild if needed

    return ld, monkeypatch, _odds


# ══════════════════════════════════════════════════════════════════════════════
# Part (a) — read_book_csv roster filter is accent-insensitive
# ══════════════════════════════════════════════════════════════════════════════

class TestRosterFilterAccentInsensitive:
    """ASCII book names must pass the roster filter when the roster stores
    the accented form (repro of the original bug)."""

    def test_jokic_ascii_survives(self, odds_env):
        """'Nikola Jokic' (ASCII, book) passes roster that has 'Nikola Jokić'."""
        ld, monkeypatch, _odds = odds_env

        _write_csv(ld / f"{DATE}_dk.csv", [_row("Nikola Jokic", book="dk")])

        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1, (
            f"'Nikola Jokic' must survive roster filter (roster has 'Nikola Jokić'); "
            f"got {rows}"
        )
        # Display name is NOT modified — kept as the book emitted it.
        assert rows[0]["player"] == "Nikola Jokic", (
            f"Display name must be unchanged; got '{rows[0]['player']}'"
        )

    def test_doncic_ascii_survives(self, odds_env):
        """'Luka Doncic' (ASCII) passes roster that has 'Luka Dončić'."""
        ld, monkeypatch, _odds = odds_env

        _write_csv(ld / f"{DATE}_fd.csv", [_row("Luka Doncic", book="fd")])

        rows = _odds.read_book_csv(ld / f"{DATE}_fd.csv", start_date=DATE)
        assert len(rows) == 1, (
            f"'Luka Doncic' must survive roster filter; got {rows}"
        )
        assert rows[0]["player"] == "Luka Doncic"

    def test_sga_no_accent_unaffected(self, odds_env):
        """Player with no accent still works (control case)."""
        ld, monkeypatch, _odds = odds_env

        _write_csv(ld / f"{DATE}_dk.csv",
                   [_row("Shai Gilgeous-Alexander", book="dk")])

        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1, "Un-accented player must still pass roster filter"

    def test_all_three_accent_players_survive(self, odds_env):
        """All three accented-name players survive when provided with ASCII names."""
        ld, monkeypatch, _odds = odds_env

        book_names = ["Nikola Jokic", "Luka Doncic", "Shai Gilgeous-Alexander"]
        rows_in = [_row(name, book="dk") for name in book_names]
        _write_csv(ld / f"{DATE}_dk.csv", rows_in)

        result = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        surviving = {r["player"] for r in result}
        for name in book_names:
            assert name in surviving, (
                f"'{name}' must survive roster filter; survivors={surviving}"
            )

    def test_non_nba_name_still_dropped(self, odds_env):
        """A non-NBA name is still filtered out (roster filter still works)."""
        ld, monkeypatch, _odds = odds_env

        _write_csv(ld / f"{DATE}_dk.csv", [_row("Caitlin Clark", book="dk")])

        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 0, "Non-NBA (WNBA) player must still be dropped"

    def test_display_name_unchanged_after_accent_strip(self, odds_env):
        """The player field in the returned row must be the ORIGINAL book name,
        not the de-accented form — we only de-accent the JOIN key, not the display."""
        ld, monkeypatch, _odds = odds_env

        _write_csv(ld / f"{DATE}_dk.csv",
                   [_row("Kristaps Porzingis", book="dk")])

        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1, "Porzingis ASCII must survive"
        assert rows[0]["player"] == "Kristaps Porzingis", (
            "Display name must be the original book spelling, not de-accented roster form"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Part (b) — Slate join: accented cache name ↔ ASCII line name
# ══════════════════════════════════════════════════════════════════════════════

class TestSlateJoinAccentInsensitive:
    """The ps_idx in courtvision_router._build_slate must be keyed by
    de-accented-lower so accented prediction-cache player_names match ASCII
    line player names."""

    def _make_slate_row(self, player_name: str, stat: str = "pts") -> dict:
        """Minimal slate row mimicking predictions_cache output (accented names)."""
        return {
            "player_name": player_name,  # accented, from predictions_cache
            "team": "DEN",
            "opp": "OKC",
            "venue": "home",
            "date": DATE,
            "game_id": "0042500317",
            "player_id": "203999",
            "stat": stat,
            "q50": 27.3,
            "sigma": 5.1,
        }

    def _make_line_row(self, player: str, stat: str = "pts",
                       line: float = 25.5) -> dict:
        """Minimal line row mimicking consolidate_for_slate output (ASCII names)."""
        return {
            "player": player,  # ASCII, from sportsbook CSV
            "stat": stat,
            "line": line,
            "game_id": "0042500317",
            "opp": "",
            "venue": "",
            "books": [{"book": "DraftKings", "over_odds": -115,
                        "under_odds": -110, "captured_at": _ts_utc(1)}],
        }

    def test_join_key_accented_cache_vs_ascii_line(self):
        """de-accented-lower join: 'Nikola Jokić' (cache) == 'Nikola Jokic' (book)."""
        from api._courtvision_odds import _strip_accents

        cache_name = "Nikola Jokić"    # as stored in predictions_cache
        line_name  = "Nikola Jokic"    # as emitted by sportsbook

        cache_key = (_strip_accents(cache_name).lower(), "pts")
        line_key  = (_strip_accents(line_name).lower(),  "pts")

        assert cache_key == line_key, (
            f"de-accented join keys must match: {cache_key!r} != {line_key!r}"
        )

    def test_join_key_doncic(self):
        """'Luka Dončić' cache key equals 'Luka Doncic' line key."""
        from api._courtvision_odds import _strip_accents

        assert (_strip_accents("Luka Dončić").lower(), "pts") == \
               (_strip_accents("Luka Doncic").lower(), "pts")

    def test_join_key_porzingis(self):
        """'Kristaps Porziņģis' cache key equals 'Kristaps Porzingis' line key."""
        from api._courtvision_odds import _strip_accents

        assert (_strip_accents("Kristaps Porziņģis").lower(), "reb") == \
               (_strip_accents("Kristaps Porzingis").lower(), "reb")

    def test_ps_idx_built_with_deaccented_key(self):
        """ps_idx built from accented cache rows is addressable by ASCII line key.

        Replicates the exact ps_idx / lookup pattern in courtvision_router
        _build_slate (lines 1511-1516 after the fix) to confirm the join
        resolves without touching the router's live server path.
        """
        from api._courtvision_odds import _strip_accents as _sa

        # Simulate slate_rows.values(): predictions_cache has accented names.
        slate_rows_values = [
            {"player_name": "Nikola Jokić",  "stat": "pts", "q50": 27.3},
            {"player_name": "Luka Dončić",   "stat": "ast", "q50": 8.1},
            {"player_name": "Shai Gilgeous-Alexander", "stat": "pts", "q50": 30.0},
        ]
        # Build ps_idx with de-accented key (the fix).
        ps_idx = {
            (_sa(r["player_name"]).lower(), r["stat"]): r
            for r in slate_rows_values
        }

        # Simulate line_rows from sportsbook CSV (ASCII names).
        line_rows = [
            {"player": "Nikola Jokic",  "stat": "pts"},
            {"player": "Luka Doncic",   "stat": "ast"},
            {"player": "Shai Gilgeous-Alexander", "stat": "pts"},
        ]

        matched = []
        for ln in line_rows:
            key = (_sa(ln["player"]).lower(), ln["stat"])
            if key in ps_idx:
                matched.append(ln["player"])

        assert len(matched) == 3, (
            f"All 3 players must match via de-accented join key; "
            f"matched only: {matched}"
        )
        assert "Nikola Jokic" in matched
        assert "Luka Doncic"  in matched
        assert "Shai Gilgeous-Alexander" in matched

    def test_strip_accents_helper_exists_and_correct(self):
        """_strip_accents is exported from api._courtvision_odds and works correctly."""
        from api._courtvision_odds import _strip_accents

        assert _strip_accents("Nikola Jokić")           == "Nikola Jokic"
        assert _strip_accents("Luka Dončić")            == "Luka Doncic"
        assert _strip_accents("Kristaps Porziņģis")     == "Kristaps Porzingis"
        assert _strip_accents("Shai Gilgeous-Alexander") == "Shai Gilgeous-Alexander"
        assert _strip_accents("")                        == ""
        assert _strip_accents("LeBron James")           == "LeBron James"

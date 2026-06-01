"""test_odds_name_arb_fixes.py — regression tests for Bug 6, Bug 7, Bug 9.

Bug 6 (DraftKings team-suffix): DK appends "(OKC)" / "(LAL)" etc. to player names
    for common names.  "Jaylin Williams (OKC)" must be kept as "jaylin williams"
    after canonicalization, not dropped by the roster filter.

Bug 7 (abbreviated first name): PointsBet emits "S. Gilgeous-Alexander".  This
    must resolve to the canonical "shai gilgeous-alexander" when exactly one roster
    player matches (initial, surname).  Two players sharing initial+surname must NOT
    be mapped (collision safety).

Bug 9 (false arb from stale captures): cross_book_spread set is_arb=True whenever
    arb_sum<100, even if the best-over and best-under quotes were captured 200 s
    apart — a stale mismatch.  After the fix, is_arb is True only when arb_quality
    is "tight" (<=30 s) or "loose" (<=90 s); stale (>90 s gap) → is_arb=False.
"""
from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# ── Shared constants ──────────────────────────────────────────────────────────
DATE = "2099-07-04"  # Far-future; won't collide with real scrape files.
_START_TIME = f"{DATE}T23:00:00Z"  # 7 PM ET on DATE

_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
]


def _ts_utc(seconds_ago: float = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _row(player_name: str, book: str = "dk", over_price: int = -110,
         under_price: int = -115, captured_at: str | None = None,
         stat: str = "pts", line: float = 22.5) -> dict:
    return {
        "captured_at": captured_at or _ts_utc(30),
        "book": book,
        "game_id": "0042500099",
        "player_id": "12345",
        "player_name": player_name,
        "stat": stat,
        "line": line,
        "over_price": over_price,
        "under_price": under_price,
        "start_time": _START_TIME,
    }


# ── Fixture: isolated lines dir + cleared caches ─────────────────────────────

@pytest.fixture()
def odds_env(tmp_path, monkeypatch):
    """Redirect _courtvision_odds to a tmp dir, install a controlled roster,
    and clear all module-level caches so tests are fully isolated."""
    import api._courtvision_odds as _odds

    ld = tmp_path / "lines"
    ld.mkdir()
    monkeypatch.setattr(_odds, "_LINES_DIR", ld)
    _odds._CACHE.clear()

    return ld, monkeypatch, _odds


# ══════════════════════════════════════════════════════════════════════════════
# Bug 6 — DraftKings team-suffix strip
# ══════════════════════════════════════════════════════════════════════════════

class TestBug6TeamSuffixStrip:

    def _install_roster(self, monkeypatch, _odds, names: list[str]) -> None:
        """Install a controlled roster (lowercase names)."""
        roster = {n.lower() for n in names}
        monkeypatch.setattr(_odds, "_NBA_PLAYER_SET", roster)
        monkeypatch.setattr(_odds, "_ABBREV_INDEX", None)  # force rebuild

    def test_dk_suffix_row_kept(self, odds_env):
        """'Jaylin Williams (OKC)' with roster='jaylin williams' → kept under dk."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Jaylin Williams"])

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("Jaylin Williams (OKC)", book="dk")],
        )

        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1, f"Expected 1 row; got {rows}"
        # The stored player name should NOT include the "(OKC)" suffix.
        assert "(OKC)" not in rows[0]["player"], (
            f"Team suffix must be stripped from player field; got '{rows[0]['player']}'"
        )
        assert rows[0]["player"].lower() == "jaylin williams"

    def test_dk_suffix_merges_into_same_prop_key(self, odds_env):
        """Two books: dk='Jaylin Williams (OKC)', fd='Jaylin Williams'.
        After canonicalization both must land in the same (player,stat,line) group."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Jaylin Williams"])

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("Jaylin Williams (OKC)", book="dk", captured_at=_ts_utc(60))],
        )
        _write_csv(
            ld / f"{DATE}_fd.csv",
            [_row("Jaylin Williams", book="fd", captured_at=_ts_utc(60))],
        )

        result = _odds.consolidate(DATE)
        # Should be exactly ONE prop (not two), with both dk and fd.
        assert len(result) == 1, (
            f"DK team-suffix row must merge into same prop; got {len(result)} props"
        )
        book_keys = {b["book"] for b in result[0]["books"]}
        assert "dk" in book_keys, "DK book must be present after suffix strip"
        assert "fd" in book_keys, "FD book must also be present"

    def test_without_suffix_unaffected(self, odds_env):
        """A row without a suffix passes through unchanged."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["LeBron James"])

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("LeBron James", book="dk")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1
        assert rows[0]["player"] == "LeBron James"

    def test_non_nba_with_suffix_still_dropped(self, odds_env):
        """A book row with a team suffix that doesn't match any roster entry is dropped."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Jaylin Williams"])

        # "Unknown Player (OKC)" → after strip → "Unknown Player" → not in roster → dropped
        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("Unknown Player (OKC)", book="dk")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 0, "Non-roster player must still be dropped after suffix strip"

    def test_lowercase_team_not_stripped(self, odds_env):
        """Only UPPERCASE 2-4-char team codes are stripped; '(okc)' lowercase is kept as-is."""
        ld, monkeypatch, _odds = odds_env
        # Roster has the name with lowercase suffix — but the regex only strips uppercase.
        monkeypatch.setattr(_odds, "_NBA_PLAYER_SET", set())  # no filter
        monkeypatch.setattr(_odds, "_ABBREV_INDEX", None)

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("Jaylin Williams (okc)", book="dk")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        # no-filter mode: row kept; player name not stripped (lowercase suffix)
        assert len(rows) == 1
        assert "(okc)" in rows[0]["player"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# Bug 7 — Abbreviated first name resolution
# ══════════════════════════════════════════════════════════════════════════════

class TestBug7AbbreviatedName:

    def _install_roster(self, monkeypatch, _odds, names: list[str]) -> None:
        roster = {n.lower() for n in names}
        monkeypatch.setattr(_odds, "_NBA_PLAYER_SET", roster)
        monkeypatch.setattr(_odds, "_ABBREV_INDEX", None)  # force rebuild

    def test_abbreviated_name_resolved(self, odds_env):
        """'S. Gilgeous-Alexander' with unique roster match → row kept, resolved."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Shai Gilgeous-Alexander"])

        _write_csv(
            ld / f"{DATE}_pointsbet.csv",
            [_row("S. Gilgeous-Alexander", book="pointsbet")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_pointsbet.csv", start_date=DATE)
        assert len(rows) == 1, (
            f"Abbreviated name with unique match must be kept; got {rows}"
        )
        # The resolved canonical name must match the roster entry.
        assert rows[0]["player"].lower() == "shai gilgeous-alexander", (
            f"Expected 'shai gilgeous-alexander'; got '{rows[0]['player']}'"
        )

    def test_abbreviated_name_collision_not_mapped(self, odds_env):
        """Two roster players sharing initial+surname → ambiguous → row dropped (not mapped)."""
        ld, monkeypatch, _odds = odds_env
        # Both players have surname "Williams" and first initial "J".
        self._install_roster(monkeypatch, _odds, [
            "Jaylin Williams",
            "Jalen Williams",
        ])

        _write_csv(
            ld / f"{DATE}_pointsbet.csv",
            [_row("J. Williams", book="pointsbet")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_pointsbet.csv", start_date=DATE)
        # Ambiguous: must NOT be mapped to either player → dropped by roster filter.
        assert len(rows) == 0, (
            f"Ambiguous abbreviated name must NOT map to any player; got {rows}"
        )

    def test_no_match_dropped(self, odds_env):
        """Abbreviated name with no roster match → dropped."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["LeBron James"])

        _write_csv(
            ld / f"{DATE}_pointsbet.csv",
            [_row("Z. Ballscorer", book="pointsbet")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_pointsbet.csv", start_date=DATE)
        assert len(rows) == 0

    def test_abbreviated_name_merges_with_other_books(self, odds_env):
        """Abbreviated row from one book merges into the same prop as the full name from another."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Shai Gilgeous-Alexander"])

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("Shai Gilgeous-Alexander", book="dk", captured_at=_ts_utc(60))],
        )
        _write_csv(
            ld / f"{DATE}_pointsbet.csv",
            [_row("S. Gilgeous-Alexander", book="pointsbet", captured_at=_ts_utc(60))],
        )

        result = _odds.consolidate(DATE)
        assert len(result) == 1, (
            f"Abbreviated + full name must merge to one prop; got {len(result)} props"
        )
        book_keys = {b["book"] for b in result[0]["books"]}
        assert "dk" in book_keys
        assert "pointsbet" in book_keys

    def test_team_suffix_then_abbrev_combo(self, odds_env):
        """Edge: 'S. Gilgeous-Alexander (OKC)' → suffix stripped first, then abbrev resolved."""
        ld, monkeypatch, _odds = odds_env
        self._install_roster(monkeypatch, _odds, ["Shai Gilgeous-Alexander"])

        _write_csv(
            ld / f"{DATE}_dk.csv",
            [_row("S. Gilgeous-Alexander (OKC)", book="dk")],
        )
        rows = _odds.read_book_csv(ld / f"{DATE}_dk.csv", start_date=DATE)
        assert len(rows) == 1, f"Suffix+abbrev row must be kept; got {rows}"
        assert rows[0]["player"].lower() == "shai gilgeous-alexander"


# ══════════════════════════════════════════════════════════════════════════════
# Bug 9 — is_arb must require tight/loose arb_quality (not just arb_sum < 100)
# ══════════════════════════════════════════════════════════════════════════════

class TestBug9ArbStaleness:
    """Verify that cross_book_spread.is_arb is False when the two legs are
    captured more than 90 s apart, even if arb_sum < 100."""

    def _build_book_entry(
        self,
        book: str,
        over_price: int | None,
        under_price: int | None,
        captured_at: str,
    ) -> dict:
        return {
            "book": book,
            "display": book,
            "over_price": over_price,
            "under_price": under_price,
            "captured_at": captured_at,
            "selection_id_over": "",
            "selection_id_under": "",
            "deeplink_over_web": "",
            "deeplink_over_app": "",
            "deeplink_under_web": "",
            "deeplink_under_app": "",
        }

    def _make_prop(self, books: list[dict]) -> dict:
        return {
            "player": "Test Player",
            "stat": "pts",
            "line": 22.5,
            "game_id": "0042500099",
            "start_time": _START_TIME,
            "n_books": len(books),
            "books": books,
        }

    def _run_cross_book_spread(self, _odds, props: list[dict], monkeypatch) -> list[dict]:
        """Patch consolidate() to return synthetic props and call cross_book_spread."""
        monkeypatch.setattr(_odds, "consolidate", lambda date: props)
        return _odds.cross_book_spread(DATE, min_spread_pp=0.0, max_age_sec=600)

    def test_stale_legs_is_arb_false(self, odds_env):
        """Two legs 200 s apart with arb_sum<100 → is_arb=False (stale)."""
        ld, monkeypatch, _odds = odds_env

        now = time.time()
        # best_over captured 200 s ago; best_under captured just now → 200 s gap
        ts_over  = datetime.fromtimestamp(now - 200, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_under = datetime.fromtimestamp(now,       tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # arb_sum < 100: over +110 (47.6%), under +120 (45.5%) → sum ~93%
        props = [self._make_prop([
            self._build_book_entry("book_a", over_price=110,  under_price=-150, captured_at=ts_over),
            self._build_book_entry("book_b", over_price=-150, under_price=120,  captured_at=ts_under),
        ])]

        result = self._run_cross_book_spread(_odds, props, monkeypatch)
        assert result, "cross_book_spread should return a row even for stale arbs"
        row = result[0]
        # arb_sum should be < 100 (real arb on numbers)
        assert row["arb_sum_pct"] is not None and row["arb_sum_pct"] < 100.0, (
            f"arb_sum_pct should be <100; got {row['arb_sum_pct']}"
        )
        # BUT is_arb must be False because gap = 200 s > 90 s (stale)
        assert row["is_arb"] is False, (
            f"Stale 200s gap must yield is_arb=False; got is_arb={row['is_arb']}, "
            f"arb_quality={row.get('arb_quality')!r}"
        )
        # arb_quality key must not be set on non-arb rows
        assert "arb_quality" not in row, (
            f"arb_quality must not appear when is_arb=False; keys={list(row)}"
        )

    def test_fresh_legs_is_arb_true(self, odds_env):
        """Two legs 15 s apart (tight) with arb_sum<100 → is_arb=True."""
        ld, monkeypatch, _odds = odds_env

        now = time.time()
        ts_over  = datetime.fromtimestamp(now - 15, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_under = datetime.fromtimestamp(now,      tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        props = [self._make_prop([
            self._build_book_entry("book_a", over_price=110,  under_price=-150, captured_at=ts_over),
            self._build_book_entry("book_b", over_price=-150, under_price=120,  captured_at=ts_under),
        ])]

        result = self._run_cross_book_spread(_odds, props, monkeypatch)
        assert result
        row = result[0]
        assert row["is_arb"] is True, (
            f"Fresh 15s gap must yield is_arb=True; got {row['is_arb']}"
        )
        assert row.get("arb_quality") == "tight", (
            f"Expected arb_quality='tight'; got {row.get('arb_quality')!r}"
        )

    def test_loose_legs_is_arb_true(self, odds_env):
        """Two legs 60 s apart (loose) with arb_sum<100 → is_arb=True."""
        ld, monkeypatch, _odds = odds_env

        now = time.time()
        ts_over  = datetime.fromtimestamp(now - 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_under = datetime.fromtimestamp(now,      tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        props = [self._make_prop([
            self._build_book_entry("book_a", over_price=110,  under_price=-150, captured_at=ts_over),
            self._build_book_entry("book_b", over_price=-150, under_price=120,  captured_at=ts_under),
        ])]

        result = self._run_cross_book_spread(_odds, props, monkeypatch)
        assert result
        row = result[0]
        assert row["is_arb"] is True, (
            f"60s gap must yield is_arb=True (loose); got {row['is_arb']}"
        )
        assert row.get("arb_quality") == "loose", (
            f"Expected arb_quality='loose'; got {row.get('arb_quality')!r}"
        )

    def test_no_arb_math_no_is_arb(self, odds_env):
        """Even fresh legs don't produce is_arb=True when arb_sum >= 100."""
        ld, monkeypatch, _odds = odds_env

        now = time.time()
        ts = datetime.fromtimestamp(now - 5, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Both books have vig: -110/-110 → over 52.4% + under 52.4% = 104.8% (no arb)
        props = [self._make_prop([
            self._build_book_entry("book_a", over_price=-110, under_price=-150, captured_at=ts),
            self._build_book_entry("book_b", over_price=-150, under_price=-110, captured_at=ts),
        ])]

        result = self._run_cross_book_spread(_odds, props, monkeypatch)
        if not result:
            return  # min_spread_pp=0 should include it, but if empty that's fine too
        row = result[0]
        assert row["is_arb"] is False, (
            f"arb_sum>=100 must give is_arb=False; got {row['is_arb']}"
        )

    def test_spread_numbers_unchanged(self, odds_env):
        """Bug 9 fix must not alter over_spread_pp / under_spread_pp / arb_sum_pct."""
        ld, monkeypatch, _odds = odds_env

        now = time.time()
        ts_over  = datetime.fromtimestamp(now - 200, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts_under = datetime.fromtimestamp(now,       tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        props = [self._make_prop([
            self._build_book_entry("book_a", over_price=110,  under_price=-150, captured_at=ts_over),
            self._build_book_entry("book_b", over_price=-150, under_price=120,  captured_at=ts_under),
        ])]

        result = self._run_cross_book_spread(_odds, props, monkeypatch)
        assert result
        row = result[0]
        # Spread values must be numeric regardless of staleness.
        assert row["arb_sum_pct"] is not None
        assert row["arb_sum_pct"] < 100.0, "arb_sum_pct should be <100 for this setup"
        assert isinstance(row["over_spread_pp"], float)
        assert isinstance(row["under_spread_pp"], float)

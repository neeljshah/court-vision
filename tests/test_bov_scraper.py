"""tests/test_bov_scraper.py - tests for scripts/bov_scraper_daemon.py.

Covers:
  * Malformed Bovada JSON (missing markets / displayGroups / outcomes) is
    handled gracefully - no exception, returns [] rows.
  * Dedup collapses 3 identical (book, player, stat, line) rows within the
    same 1-min window to a single CSV write.
  * Schema validation: all 11 canonical columns present on every written row.
  * Book-alias resolution: clv._book_canon("bov") == "bovada".
"""
from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from scripts import bov_scraper_daemon as bsd  # noqa: E402


# ── synthetic Bovada payloads ──────────────────────────────────────────────

def _index_payload(events: List[Dict[str, Any]]) -> bytes:
    """Wrap a list of event stubs in the index-endpoint envelope."""
    return json.dumps([{"events": events}]).encode("utf-8")


def _event_stub(ev_id: str, link: str,
                start_ms: int = 1763846400000) -> Dict[str, Any]:
    return {"id": ev_id, "link": link, "startTime": start_ms}


def _detail_payload_complete() -> bytes:
    """A well-formed Bovada event-detail payload with two player-prop rows."""
    return json.dumps([{
        "events": [{
            "displayGroups": [{
                "description": "Player Points",
                "markets": [{
                    "description": "Total Points - LeBron James (LAL)",
                    "status": "open",
                    "outcomes": [
                        {"description": "Over",
                         "price": {"handicap": "25.5", "american": "-110"}},
                        {"description": "Under",
                         "price": {"handicap": "25.5", "american": "-110"}},
                    ],
                }, {
                    "description": "Total Points - Jaylen Brown (BOS)",
                    "status": "open",
                    "outcomes": [
                        {"description": "Over",
                         "price": {"handicap": "21.5", "american": "+105"}},
                        {"description": "Under",
                         "price": {"handicap": "21.5", "american": "-130"}},
                    ],
                }],
            }],
        }],
    }]).encode("utf-8")


def _detail_payload_missing_markets() -> bytes:
    """Detail payload where the displayGroup has no `markets` key at all."""
    return json.dumps([{
        "events": [{
            "displayGroups": [{
                "description": "Player Points",
                # no `markets`
            }],
        }],
    }]).encode("utf-8")


def _detail_payload_junk() -> bytes:
    """Detail payload that's structurally degenerate at multiple levels."""
    return json.dumps([
        {"events": [
            # event with no displayGroups
            {"foo": "bar"},
            # event with displayGroups that's not a list
            {"displayGroups": "lol"},
            # event with a dg that's not a dict
            {"displayGroups": ["whoops"]},
            # event with a dg whose markets list contains non-dicts
            {"displayGroups": [{"description": "Player Points",
                                 "markets": [None, 7, "x"]}]},
            # market with NO outcomes
            {"displayGroups": [{"description": "Player Points", "markets": [{
                "description": "Total Points - X (LAL)", "outcomes": []}]}]},
            # market with outcomes missing price field
            {"displayGroups": [{"description": "Player Points", "markets": [{
                "description": "Total Points - Y (BOS)",
                "outcomes": [{"description": "Over"}]}]}]},
        ]},
    ]).encode("utf-8")


def _detail_payload_non_player_dg() -> bytes:
    """Detail payload whose displayGroup isn't a player-prop group."""
    return json.dumps([{
        "events": [{
            "displayGroups": [{
                "description": "Game Lines",  # NOT in allowlist
                "markets": [{
                    "description": "Total Points - LeBron James (LAL)",
                    "outcomes": [
                        {"description": "Over",
                         "price": {"handicap": "25.5", "american": "-110"}},
                        {"description": "Under",
                         "price": {"handicap": "25.5", "american": "-110"}},
                    ],
                }],
            }],
        }],
    }]).encode("utf-8")


# ── fake HTTP layer ─────────────────────────────────────────────────────────

def _make_http_fn(routes: Dict[str, Tuple[int, Optional[bytes], Optional[str]]]):
    """Return a stub `_http_get`-compatible callable.

    Matches URLs by substring (so callers don't have to enumerate every
    Bovada path variant). Default response = 404 to surface routing typos.
    """
    def _fn(url: str, timeout: float = 15.0):
        for needle, resp in routes.items():
            if needle in url:
                return resp
        return (404, None, f"no stub matched {url}")
    return _fn


# ───────────────────────────────────────────────────────────────────────────


class TestGracefulParse(unittest.TestCase):
    """HTML/JSON parse handles missing markets gracefully (no exception)."""

    def test_missing_markets_no_exception(self):
        rows = bsd._parse_event_detail(
            json.loads(_detail_payload_missing_markets().decode("utf-8")),
            ev_id="evX", start_iso="2026-05-26T00:00:00",
            captured_at="2026-05-26T08:00:00")
        self.assertEqual(rows, [])

    def test_junk_payload_no_exception(self):
        rows = bsd._parse_event_detail(
            json.loads(_detail_payload_junk().decode("utf-8")),
            ev_id="evJ", start_iso="2026-05-26T00:00:00",
            captured_at="2026-05-26T08:00:00")
        # All shapes are degenerate; some markets pass the dg/player check
        # but have no usable outcomes -> no rows survive.
        self.assertEqual(rows, [])

    def test_non_player_displaygroup_skipped(self):
        rows = bsd._parse_event_detail(
            json.loads(_detail_payload_non_player_dg().decode("utf-8")),
            ev_id="evG", start_iso="2026-05-26T00:00:00",
            captured_at="2026-05-26T08:00:00")
        self.assertEqual(rows, [],
                         "Game Lines is not a player-prop displayGroup")

    def test_complete_payload_emits_rows(self):
        """Sanity: a well-formed detail payload produces 2 rows (LeBron, Brown)."""
        rows = bsd._parse_event_detail(
            json.loads(_detail_payload_complete().decode("utf-8")),
            ev_id="evC", start_iso="2026-05-26T00:00:00",
            captured_at="2026-05-26T08:00:00")
        self.assertEqual(len(rows), 2)
        players = {r["player_name"] for r in rows}
        self.assertEqual(players, {"LeBron James", "Jaylen Brown"})
        for r in rows:
            self.assertEqual(r["book"], "bov")
            self.assertEqual(r["stat"], "pts")
            self.assertEqual(r["line"], 25.5 if r["player_name"] == "LeBron James" else 21.5)

    def test_fetch_sport_handles_5xx(self):
        http_fn = _make_http_fn({
            "basketball/nba": (502, None, "bad gateway"),
        })
        n, rows, diag = bsd.fetch_sport("nba", http_fn=http_fn,
                                          captured_at="2026-05-26T08:00:00")
        self.assertEqual(n, 0)
        self.assertEqual(rows, [])
        self.assertEqual(diag["index_status"], 502)
        self.assertEqual(diag["n_5xx"], 1)

    def test_fetch_sport_403_raises_blocked(self):
        http_fn = _make_http_fn({
            "basketball/nba": (403, b"", "forbidden"),
        })
        with self.assertRaises(bsd.BovadaBlocked):
            bsd.fetch_sport("nba", http_fn=http_fn,
                             captured_at="2026-05-26T08:00:00")


class TestDedup(unittest.TestCase):
    """Dedupe collapses 3 identical (book, player, stat, line) within same minute."""

    def _row(self, captured_at: str = "2026-05-26T08:00:00",
             line: float = 25.5, player: str = "LeBron James") -> Dict[str, Any]:
        return {
            "captured_at":   captured_at,
            "book":          "bov",
            "game_id":       "g1",
            "player_id":     "",
            "player_name":   player,
            "team":          "LAL",
            "stat":          "pts",
            "line":          line,
            "over_price":    "-110",
            "under_price":   "-110",
            "market_status": "open",
        }

    def test_intra_minute_dedup(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "2026-05-26_bov.csv")
            r = self._row()
            # 3 identical rows in same minute.
            n = bsd.append_rows([dict(r), dict(r), dict(r)], path)
            self.assertEqual(n, 1, "3 identical rows -> 1 write")
            # A 4th identical row in a later append should also dedup.
            n2 = bsd.append_rows([dict(r)], path)
            self.assertEqual(n2, 0, "4th identical row -> 0 writes")
            # File row count = 1 + 1 header.
            self.assertEqual(bsd._row_count(path), 1)

    def test_different_lines_not_deduped(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "2026-05-26_bov.csv")
            rows = [self._row(line=25.5), self._row(line=26.5), self._row(line=27.5)]
            n = bsd.append_rows(rows, path)
            self.assertEqual(n, 3, "different lines = different keys")

    def test_different_minutes_not_deduped(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "2026-05-26_bov.csv")
            rows = [
                self._row(captured_at="2026-05-26T08:00:00"),
                self._row(captured_at="2026-05-26T08:01:00"),
                self._row(captured_at="2026-05-26T08:05:00"),
            ]
            n = bsd.append_rows(rows, path)
            self.assertEqual(n, 3, "different minutes = different keys")


class TestSchemaValidation(unittest.TestCase):
    """All 12 canonical columns present on every written row.

    R19_L1 added `is_alt_line` (bool) to mark Bovada alt-line ladder
    rungs vs the primary line. R20_M1 keeps this column and adds the
    in-memory derived `market_tier` ('primary'|'alt') in the readers.
    """

    EXPECTED_COLS = [
        "captured_at", "book", "game_id", "player_id", "player_name",
        "team", "stat", "line", "over_price", "under_price",
        "market_status", "is_alt_line",
    ]

    def test_eleven_canonical_columns(self):
        self.assertEqual(bsd._FIELDS, self.EXPECTED_COLS)
        self.assertEqual(len(bsd._FIELDS), 12)

    def test_csv_header_matches(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "2026-05-26_bov.csv")
            row = {
                "captured_at": "2026-05-26T08:00:00", "book": "bov",
                "game_id": "g1", "player_id": "", "player_name": "X",
                "team": "LAL", "stat": "pts", "line": 25.5,
                "over_price": "-110", "under_price": "-110",
                "market_status": "open",
            }
            bsd.append_rows([row], path)
            with open(path, encoding="utf-8") as fh:
                rdr = csv.reader(fh)
                header = next(rdr)
            self.assertEqual(header, self.EXPECTED_COLS)

    def test_end_to_end_writes_full_schema(self):
        """Fake HTTP -> fetch_cycle -> CSV has 11-col header and complete rows."""
        index_body = _index_payload([
            _event_stub("ev1", "/basketball/nba/lal-bos-202605262100"),
        ])
        # Route order matters: longer-needle (more specific) wins because
        # _make_http_fn iterates dict insertion order.
        http_fn = _make_http_fn({
            "lal-bos-202605262100":      (200, _detail_payload_complete(), None),
            "basketball/nba?":            (200, index_body, None),
            "basketball/wnba?":           (200, _index_payload([]), None),
            "baseball/mlb?":              (200, _index_payload([]), None),
        })
        with tempfile.TemporaryDirectory() as td:
            summary = bsd.fetch_cycle(["nba", "wnba", "mlb"],
                                       lines_dir=td, http_fn=http_fn,
                                       captured_at="2026-05-26T08:00:00")
            self.assertEqual(summary["rows_new"], 2)
            self.assertIn("nba", summary["sports_with_data"])
            self.assertNotIn("wnba", summary["sports_with_data"])
            self.assertNotIn("mlb", summary["sports_with_data"])
            with open(summary["out_path"], encoding="utf-8") as fh:
                rdr = csv.DictReader(fh)
                self.assertEqual(rdr.fieldnames, self.EXPECTED_COLS)
                rows = list(rdr)
            self.assertEqual(len(rows), 2)
            for r in rows:
                for col in self.EXPECTED_COLS:
                    self.assertIn(col, r)
                self.assertEqual(r["book"], "bov")
                self.assertNotEqual(r["player_name"], "")
                self.assertNotEqual(r["line"], "")


class TestBookAlias(unittest.TestCase):
    """`bov` and `bovada` both resolve to canonical `bovada` in clv._BOOK_ALIASES."""

    def test_clv_book_canon_resolves_bov(self):
        from src.betting import clv  # noqa: PLC0415
        self.assertEqual(clv._book_canon("bov"),    "bovada")
        self.assertEqual(clv._book_canon("bovada"), "bovada")
        self.assertEqual(clv._book_canon("BOV"),    "bovada",
                         "case-insensitive resolution")
        self.assertIn("bov",    clv._BOOK_ALIASES)
        self.assertIn("bovada", clv._BOOK_ALIASES)
        self.assertEqual(clv._BOOK_ALIASES["bov"],    "bovada")
        self.assertEqual(clv._BOOK_ALIASES["bovada"], "bovada")


class TestBlockedDaemon(unittest.TestCase):
    """Persistent 403 across all sports -> daemon exits with `blocked_persistent`."""

    def test_persistent_block_giveup(self):
        # Every URL returns 403 -> fetch_cycle raises BovadaBlocked every tick.
        http_fn = _make_http_fn({
            "bovada.lv": (403, b"forbidden", "forbidden"),
        })
        sleeps: List[float] = []
        ticks = {"i": 0}
        # Fake clock advances 30 real-min per tick - so after 3 ticks we're at
        # 60 real-min of blocking, which triggers the 1-h giveup.
        base = datetime(2026, 5, 26, 8, 0, 0)
        def clock_fn():
            from datetime import timedelta
            t = base + timedelta(minutes=30 * ticks["i"])
            ticks["i"] += 1
            return t
        def sleep_fn(s):
            sleeps.append(s)
        with tempfile.TemporaryDirectory() as td:
            out = bsd.run_daemon(
                ["nba"], interval_min=5, lines_dir=td,
                sleep_fn=sleep_fn, http_fn=http_fn,
                clock_fn=clock_fn, block_giveup_hours=1.0,
                max_iters=10,  # safety; actual exit should be earlier
            )
        self.assertEqual(out["exit_reason"], "blocked_persistent")


if __name__ == "__main__":
    unittest.main()

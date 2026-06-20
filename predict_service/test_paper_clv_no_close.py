"""predict_service.test_paper_clv_no_close -- acceptance tests for W5-clv-series-no-close.

Verifies:
  * /api/paper/clv summary includes n_total_rows>0, n_no_close, n_open derived from
    a fixture ledger that has real rows but ZERO closing lines.
  * /api/paper/clv/series returns status=ok with an explicit no_close_reason (not a
    silent empty) when nothing is gradeable.
  * When a fixture row HAS a closing line the series contains that point.
  * No $ key in any response.
  * mean_clv_pct stays null (never fabricated) when n_bets=0.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_paper_clv_no_close.py -q

INVARIANTS: <=300 LOC; ASCII-only; no secrets; per-file test only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from frontend.serve import app


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------

def _write(path: Path, rows: list) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return str(path)


def _open_row(matchup: str = "NYK@SAS", sport: str = "nba",
              ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    return {
        "ts": ts, "sport": sport, "matchup": matchup,
        "side": "away", "taken_book": "espn:DK",
        "taken_decimal": 2.6, "model_prob": 0.41,
        "stake_units": 1.0, "market_type": "moneyline",
        "status": "open", "executed": False,
    }


def _settled_no_close(matchup: str = "NYK@SAS", sport: str = "nba",
                      ts: str = "2026-06-18T22:00:00+00:00") -> dict:
    """Settled row with NO closing line -- the VOID/pending no-close case."""
    row = _open_row(matchup, sport, ts)
    row.update({
        "status": "settled", "settled_at": "2026-06-18T23:00:00+00:00",
        "clv_pct": None, "beat_close": None, "clv_is_proxy": False,
        "clv_status": "no_close",
        "clv_note": "no closing line captured; CLV unavailable (win/loss only)",
        "graded": True, "outcome": "win",
        "settle_key": "nba|NYK@SAS|away|espn:DK|2.6|" + ts,
    })
    return row


def _settled_with_close(matchup: str = "BOS@MIA", sport: str = "nba",
                        ts: str = "2026-06-18T22:05:00+00:00") -> dict:
    """Settled row WITH a real closing line -- appears in the series."""
    row = _open_row(matchup, sport, ts)
    row.update({
        "status": "settled", "settled_at": "2026-06-18T23:05:00+00:00",
        "clv_pct": 2.3, "beat_close": True, "clv_is_proxy": False,
        "clv_status": "true_close",
        "graded": True, "outcome": "win",
        "settle_key": "nba|BOS@MIA|away|espn:DK|2.6|" + ts,
    })
    return row


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/paper/clv -- summary tests
# ---------------------------------------------------------------------------

class TestClvSummaryNoClose:
    """All settled rows in the fixture have NO closing line."""

    def test_n_total_rows_positive(self, client: TestClient, tmp_path: Path) -> None:
        """n_total_rows reflects every row in the ledger, not just gradeable ones."""
        rows = [
            _open_row("A@B", "nba", "2026-06-18T20:00:00+00:00"),
            _open_row("C@D", "nba", "2026-06-18T20:01:00+00:00"),
            _settled_no_close("NYK@SAS", "nba"),
        ]
        ledger = _write(tmp_path / "l.jsonl", rows)
        r = client.get("/api/paper/clv", params={"ledger": ledger})
        assert r.status_code == 200
        body = r.json()
        assert body["n_total_rows"] > 0, "n_total_rows must be positive (got 0)"
        assert body["n_total_rows"] == 3

    def test_n_no_close_in_summary(self, client: TestClient, tmp_path: Path) -> None:
        """n_no_close equals the count of settled rows without a closing line."""
        rows = [_settled_no_close(), _settled_no_close("OKC@DEN", "nba",
                                                        "2026-06-18T22:01:00+00:00")]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv", params={"ledger": ledger}).json()
        assert body["n_no_close"] == 2

    def test_n_open_in_summary(self, client: TestClient, tmp_path: Path) -> None:
        """n_open equals the count of open (not-yet-settled) rows."""
        rows = [
            _open_row("A@B", "nba", "2026-06-18T20:00:00+00:00"),
            _open_row("C@D", "nba", "2026-06-18T20:01:00+00:00"),
            _settled_no_close(),
        ]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv", params={"ledger": ledger}).json()
        assert body["n_open"] == 2

    def test_n_bets_zero_when_no_close(self, client: TestClient, tmp_path: Path) -> None:
        """n_bets=0 (gradeable count) when ALL settled rows have no closing line."""
        rows = [_settled_no_close()]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv", params={"ledger": ledger}).json()
        assert body["n_bets"] == 0

    def test_mean_clv_pct_null_not_fabricated(self, client: TestClient,
                                               tmp_path: Path) -> None:
        """mean_clv_pct must be null (None) when n_bets=0 -- never a fabricated 0."""
        rows = [_settled_no_close()]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv", params={"ledger": ledger}).json()
        assert body["mean_clv_pct"] is None, (
            "mean_clv_pct must be null when no gradeable bets exist, not %r"
            % body["mean_clv_pct"]
        )

    def test_status_ok(self, client: TestClient, tmp_path: Path) -> None:
        ledger = _write(tmp_path / "l.jsonl", [_settled_no_close()])
        body = client.get("/api/paper/clv", params={"ledger": ledger}).json()
        assert body["status"] == "ok"

    def test_no_dollar_keys(self, client: TestClient, tmp_path: Path) -> None:
        """No $ / roi / profit / bankroll key anywhere in the CLV summary."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_no_close()])
        body_str = json.dumps(
            client.get("/api/paper/clv", params={"ledger": ledger}).json()
        ).lower()
        for banned in ("dollar", "roi", "profit", "bankroll", "$edge"):
            assert banned not in body_str, "Banned term '%s' in CLV response" % banned


# ---------------------------------------------------------------------------
# /api/paper/clv/series -- no gradeable points
# ---------------------------------------------------------------------------

class TestClvSeriesNoClose:
    """All settled rows have no closing line -> series is empty with honest reason."""

    def test_status_ok_when_nothing_gradeable(self, client: TestClient,
                                               tmp_path: Path) -> None:
        """status=ok even when count=0 -- never a 500 or error state."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_no_close()])
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["status"] == "ok"

    def test_explicit_no_close_reason_present(self, client: TestClient,
                                               tmp_path: Path) -> None:
        """no_close_reason must be present when count=0 and n_no_close>0 (not silent)."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_no_close()])
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["count"] == 0
        assert body["n_no_close"] > 0
        reason = body.get("no_close_reason", "")
        assert reason, (
            "no_close_reason must be a non-empty string when count=0 and "
            "n_no_close>0; got %r" % reason
        )
        # Must mention INSUFFICIENT_DATA or no closing lines
        assert "INSUFFICIENT_DATA" in reason or "no closing" in reason.lower(), (
            "no_close_reason should reference INSUFFICIENT_DATA or 'no closing'; "
            "got: %r" % reason
        )

    def test_n_no_close_in_series_response(self, client: TestClient,
                                            tmp_path: Path) -> None:
        """n_no_close in the series response matches the number of void settled rows."""
        rows = [
            _settled_no_close("A@B", "nba", "2026-06-18T22:00:00+00:00"),
            _settled_no_close("C@D", "nba", "2026-06-18T22:01:00+00:00"),
        ]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["n_no_close"] == 2

    def test_empty_series_list_when_nothing_gradeable(self, client: TestClient,
                                                        tmp_path: Path) -> None:
        """series list is empty (not absent) when count=0."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_no_close()])
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["series"] == []

    def test_no_close_reason_absent_when_series_has_points(self, client: TestClient,
                                                             tmp_path: Path) -> None:
        """no_close_reason must NOT appear when the series actually has graded points."""
        rows = [_settled_with_close()]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["count"] == 1
        assert "no_close_reason" not in body or body.get("no_close_reason") is None, (
            "no_close_reason should be absent when series has real points"
        )


# ---------------------------------------------------------------------------
# /api/paper/clv/series -- with a real closing line
# ---------------------------------------------------------------------------

class TestClvSeriesWithClose:
    """When a row HAS a closing line the series contains that point."""

    def test_point_appears_in_series(self, client: TestClient, tmp_path: Path) -> None:
        """A settled row with clv_pct set contributes exactly one series point."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_with_close()])
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["status"] == "ok"
        assert body["count"] == 1
        pt = body["series"][0]
        assert abs(pt["clv_pct"] - 2.3) < 1e-6
        assert "cumulative_mean_clv_pct" in pt

    def test_no_close_excluded_real_close_included(self, client: TestClient,
                                                    tmp_path: Path) -> None:
        """A mixed ledger: only the row with a close appears; no-close row is excluded."""
        rows = [_settled_no_close(), _settled_with_close()]
        ledger = _write(tmp_path / "l.jsonl", rows)
        body = client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        assert body["count"] == 1
        assert body["n_no_close"] == 1
        assert body["series"][0]["matchup"] == "BOS@MIA"

    def test_no_dollar_keys_in_series(self, client: TestClient, tmp_path: Path) -> None:
        """No $ / roi / profit key in any series response."""
        ledger = _write(tmp_path / "l.jsonl", [_settled_with_close()])
        body_str = json.dumps(
            client.get("/api/paper/clv/series", params={"ledger": ledger}).json()
        ).lower()
        for banned in ("dollar", "roi", "profit", "$edge"):
            assert banned not in body_str, (
                "Banned term '%s' in CLV series response" % banned
            )

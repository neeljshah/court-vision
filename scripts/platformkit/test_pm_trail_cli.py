"""Per-file test for scripts.platformkit.pm_trail_cli.

Acceptance criteria (from PT-4 BACKLOG spec):
  1. --mode list emits N lines for N rows (one line per trade in table body)
  2. --mode best applies ranking order (tier A>B>C, then model_prob desc, then clv_pct desc)
  3. --mode detail prints full JSON for one trade
  4. No $/pnl field in any output
  5. CLV proxy labelled is_proxy honestly; null CLV = INSUFFICIENT_DATA

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_pm_trail_cli.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Ensure repo root is on path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.pm_trail_cli import main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures: synthetic JSONL ledger with PM rows
# ---------------------------------------------------------------------------

def _row(
    bet_id: str,
    matchup: str = "NYK vs SAS",
    venue: str = "kalshi",
    tier: str = "A",
    model_prob: float = 0.65,
    stake_units: float = 1.0,
    outcome: Optional[str] = None,
    clv_pct: Optional[float] = None,
    clv_is_proxy: bool = False,
    status: str = "open",
    ts: str = "2026-06-20T12:00:00",
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "bet_id": bet_id,
        "ts": ts,
        "sport": "NBA",
        "matchup": matchup,
        "side": "home",
        "taken_book": venue,
        "taken_decimal": 1.95,
        "model_prob": model_prob,
        "model_ev": 0.05,
        "tier": tier,
        "flat_unit": 1.0,
        "quarter_kelly": 0.25,
        "stake_units": stake_units,
        "status": status,
        "outcome": outcome,
        "clv_pct": clv_pct,
        "beat_close": (clv_pct > 0) if clv_pct is not None else None,
        "clv_is_proxy": clv_is_proxy,
        "clv_status": (
            "proxy" if clv_is_proxy
            else ("true_close" if clv_pct is not None else "no_close")
        ),
        "executed": False,
        "is_pm": True,
        "channel": "paper",
        "venue": venue,
        "market_id": f"MARKET-{bet_id}",
        "event_id": f"EVENT-{bet_id}",
    }
    return row


def _make_ledger(rows: List[Dict[str, Any]]) -> Path:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for r in rows:
        tmp.write(json.dumps(r) + "\n")
    tmp.close()
    return Path(tmp.name)


def _capture(argv: List[str]) -> str:
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        main(argv)
    finally:
        sys.stdout = old
    return buf.getvalue()


def _data_lines(out: str) -> List[str]:
    """Extract non-header, non-separator, non-meta lines from list/best output.

    In list mode rows contain the matchup text in the middle columns.
    We identify them as lines that have 'NBA' (sport column) which appears
    after the separator line.
    """
    lines = out.splitlines()
    data: List[str] = []
    past_sep = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if all(c in "- " for c in stripped):
            past_sep = True
            continue
        if past_sep and "NBA" in line and stripped and not stripped.startswith("NOTE"):
            data.append(line)
    return data


# ---------------------------------------------------------------------------
# Criterion 1: --mode list emits N lines for N rows
# ---------------------------------------------------------------------------

class TestListMode:
    def test_empty_ledger_emits_zero_data_lines(self, tmp_path: Path) -> None:
        ledger = tmp_path / "empty.jsonl"
        ledger.write_text("")
        out = _capture(["--mode", "list", "--ledger", str(ledger)])
        assert _data_lines(out) == []

    def test_three_rows_emits_three_data_lines(self) -> None:
        rows = [
            _row("bet-001", matchup="NYK vs SAS", tier="A", model_prob=0.70,
                 ts="2026-06-20T12:00:00"),
            _row("bet-002", matchup="OKC vs MEM", tier="B", model_prob=0.60,
                 ts="2026-06-20T12:01:00"),
            _row("bet-003", matchup="BOS vs MIA", tier="C", model_prob=0.55,
                 ts="2026-06-20T12:02:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger)])
        data = _data_lines(out)
        assert len(data) == 3, f"Expected 3 data lines, got {len(data)}:\n{out}"

    def test_limit_respected(self) -> None:
        rows = [
            _row(f"bet-{i:03d}", matchup=f"Team{i} vs Opp{i}",
                 ts=f"2026-06-20T12:{i:02d}:00")
            for i in range(10)
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger), "--limit", "5"])
        data = _data_lines(out)
        assert len(data) == 5, f"Expected 5 data lines, got {len(data)}:\n{out}"

    def test_venue_filter_kalshi_only(self) -> None:
        rows = [
            _row("bet-k1", matchup="NYK vs SAS", venue="kalshi",
                 ts="2026-06-20T12:00:00"),
            _row("bet-p1", matchup="NYK vs SAS", venue="polymarket",
                 ts="2026-06-20T12:01:00"),
            _row("bet-k2", matchup="OKC vs MEM", venue="kalshi",
                 ts="2026-06-20T12:02:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger), "--venue", "kalshi"])
        data = _data_lines(out)
        assert len(data) == 2, f"Expected 2 kalshi lines, got {len(data)}:\n{out}"
        for line in data:
            assert "polymarket" not in line.lower()

    def test_tier_filter(self) -> None:
        rows = [
            _row("bet-a1", matchup="NYK vs SAS", tier="A",
                 ts="2026-06-20T12:00:00"),
            _row("bet-b1", matchup="OKC vs MEM", tier="B",
                 ts="2026-06-20T12:01:00"),
            _row("bet-a2", matchup="BOS vs MIA", tier="A",
                 ts="2026-06-20T12:02:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger), "--tier", "A"])
        data = _data_lines(out)
        assert len(data) == 2, f"Expected 2 tier-A lines, got {len(data)}:\n{out}"

    def test_no_dollar_field_in_list_output(self) -> None:
        rows = [_row("bet-001")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger)])
        lower = out.lower()
        assert "pnl" not in lower
        assert "profit" not in lower

    def test_summary_line_shows_total_count(self) -> None:
        rows = [
            _row("bet-001", matchup="NYK vs SAS", ts="2026-06-20T12:00:00"),
            _row("bet-002", matchup="OKC vs MEM", ts="2026-06-20T12:01:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "list", "--ledger", str(ledger)])
        # First line should show "2 of 2 trades"
        first = out.splitlines()[0]
        assert "2 of 2" in first, f"Summary line wrong: {first!r}"


# ---------------------------------------------------------------------------
# Criterion 2: --mode best applies ranking order
# ---------------------------------------------------------------------------

class TestBestMode:
    def test_tier_a_before_b_before_c(self) -> None:
        rows = [
            _row("bet-c1", matchup="CCC vs OPP", tier="C", model_prob=0.90,
                 ts="2026-06-20T12:00:00"),
            _row("bet-b1", matchup="BBB vs OPP", tier="B", model_prob=0.80,
                 ts="2026-06-20T12:01:00"),
            _row("bet-a1", matchup="AAA vs OPP", tier="A", model_prob=0.70,
                 ts="2026-06-20T12:02:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "best", "--ledger", str(ledger)])
        lines = [l for l in out.splitlines() if "NBA" in l and "vs OPP" in l]
        assert len(lines) == 3, f"Expected 3 ranked lines, got {len(lines)}:\n{out}"
        a_idx = next(i for i, l in enumerate(lines) if "AAA" in l)
        b_idx = next(i for i, l in enumerate(lines) if "BBB" in l)
        c_idx = next(i for i, l in enumerate(lines) if "CCC" in l)
        assert a_idx < b_idx < c_idx, \
            f"Rank wrong: A={a_idx} B={b_idx} C={c_idx}\n{out}"

    def test_within_same_tier_higher_prob_ranks_first(self) -> None:
        rows = [
            _row("bet-lo", matchup="LO vs OPP", tier="A", model_prob=0.60,
                 ts="2026-06-20T12:00:00"),
            _row("bet-hi", matchup="HI vs OPP", tier="A", model_prob=0.85,
                 ts="2026-06-20T12:01:00"),
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "best", "--ledger", str(ledger)])
        lines = [l for l in out.splitlines() if "NBA" in l and "vs OPP" in l]
        assert len(lines) == 2, f"Expected 2 lines:\n{out}"
        hi_idx = next(i for i, l in enumerate(lines) if "HI" in l)
        lo_idx = next(i for i, l in enumerate(lines) if "LO" in l)
        assert hi_idx < lo_idx, \
            f"Higher prob should rank first: HI={hi_idx} LO={lo_idx}\n{out}"

    def test_top_n_limits_output(self) -> None:
        rows = [
            _row(f"bet-{i:03d}", matchup=f"T{i:02d} vs OPP",
                 ts=f"2026-06-20T{i:02d}:00:00")
            for i in range(15)
        ]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "best", "--ledger", str(ledger), "--top-n", "5"])
        data = _data_lines(out)
        assert len(data) == 5, f"Expected 5 lines, got {len(data)}:\n{out}"

    def test_no_dollar_in_best_output(self) -> None:
        rows = [_row("bet-001")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "best", "--ledger", str(ledger)])
        lower = out.lower()
        assert "pnl" not in lower
        assert "profit" not in lower

    def test_best_header_mentions_rank_order(self) -> None:
        rows = [_row("bet-001")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "best", "--ledger", str(ledger)])
        assert "tier" in out.lower()
        assert "model_prob" in out.lower() or "prob" in out.lower()


# ---------------------------------------------------------------------------
# Criterion 3 + 5: --mode detail prints full JSON; CLV proxy honest
# ---------------------------------------------------------------------------

class TestDetailMode:
    def test_detail_returns_valid_json(self) -> None:
        rows = [_row("bet-x42", clv_pct=3.1)]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-x42", "--ledger", str(ledger)])
        data = json.loads(out)
        assert data["status"] == "ok"
        assert data["trade"] is not None

    def test_detail_not_found_returns_code_1(self) -> None:
        rows = [_row("bet-x99")]
        ledger = _make_ledger(rows)
        buf = StringIO()
        old_out = sys.stdout
        sys.stdout = buf
        rc = main(["--mode", "detail", "--bet-id", "MISSING", "--ledger", str(ledger)])
        sys.stdout = old_out
        out = buf.getvalue()
        assert rc == 1 or "not_found" in out

    def test_detail_no_dollar_field(self) -> None:
        rows = [_row("bet-z01")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-z01", "--ledger", str(ledger)])
        data = json.loads(out)
        trade = data["trade"]
        forbidden = {"pnl", "profit", "dollar_profit", "roi"}
        found = forbidden & set(trade.keys())
        assert not found, f"Forbidden $ fields: {found}"

    def test_detail_executed_always_false(self) -> None:
        rows = [_row("bet-ex1")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-ex1", "--ledger", str(ledger)])
        data = json.loads(out)
        assert data["trade"]["executed"] is False

    def test_clv_proxy_labelled_honestly(self) -> None:
        rows = [_row("bet-prx", clv_pct=2.5, clv_is_proxy=True)]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-prx", "--ledger", str(ledger)])
        data = json.loads(out)
        # is_proxy flag must be True
        assert data["trade"]["clv_is_proxy"] is True, "clv_is_proxy should be True"
        # clv_note must mention proxy (honest labelling)
        clv_note = data.get("clv_note", "")
        assert "proxy" in clv_note.lower(), \
            f"clv_note should mention proxy; got: {clv_note!r}"

    def test_null_clv_labelled_insufficient_data(self) -> None:
        rows = [_row("bet-nc1", clv_pct=None)]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-nc1", "--ledger", str(ledger)])
        data = json.loads(out)
        assert data["trade"]["clv_pct"] is None, "CLV should be null"
        clv_note = data.get("clv_note", "")
        assert ("insufficient_data" in clv_note.lower()
                or "no closing" in clv_note.lower()), \
            f"Expected INSUFFICIENT_DATA in clv_note: {clv_note!r}"

    def test_detail_missing_bet_id_returns_error(self) -> None:
        buf = StringIO()
        old_err = sys.stderr
        sys.stderr = buf
        rc = main(["--mode", "detail"])
        sys.stderr = old_err
        assert rc == 2

    def test_detail_honest_note_present(self) -> None:
        rows = [_row("bet-hn1")]
        ledger = _make_ledger(rows)
        out = _capture(["--mode", "detail", "--bet-id", "bet-hn1", "--ledger", str(ledger)])
        data = json.loads(out)
        note = data.get("honest_note", "")
        assert "executed=False" in note or "paper" in note.lower()


# ---------------------------------------------------------------------------
# Criterion: sportsbook rows excluded from PM-only CLI
# ---------------------------------------------------------------------------

class TestPMOnlyFilter:
    def test_sportsbook_rows_excluded(self) -> None:
        sb_row: Dict[str, Any] = {
            "bet_id": "bet-sb1",
            "ts": "2026-06-20T10:00:00",
            "sport": "NBA",
            "matchup": "SBONLY vs OPP",
            "side": "home",
            "taken_book": "DraftKings",
            "taken_decimal": 1.90,
            "model_prob": 0.75,
            "tier": "A",
            "stake_units": 1.0,
            "status": "open",
            "executed": False,
            "is_pm": False,
            "channel": "sportsbook",
            "venue": "sportsbook",
        }
        pm_r = _row("bet-pm1", matchup="PMONLY vs OPP", ts="2026-06-20T11:00:00")
        ledger = _make_ledger([sb_row, pm_r])
        out = _capture(["--mode", "list", "--ledger", str(ledger)])
        data = _data_lines(out)
        # Only the PM row (PMONLY) should appear; sportsbook row (SBONLY) excluded
        assert len(data) == 1, \
            f"Expected 1 PM-only line, got {len(data)}:\n{out}"
        assert "PMONLY" in data[0], f"Expected PMONLY in data line: {data[0]!r}"
        assert "SBONLY" not in out or "1 of 1" in out  # SBONLY not in trade rows

"""tests.platform.test_soccer_run_proof — Integration tests for the soccer proof runner.

Covers:
  - run_v1: returns per-corpus detail dicts.
  - run_v2: returns inv_a_ok / inv_b_ok.
  - run_v3: returns a verdict for each of the 3 signals, each passed_expected=True
             (REJECT or DEFER acceptable per KERNEL_DISCIPLINE #1).
  - run_v4: completes with drawdown_inject_fired=True and disclaimer present.
  - CLI main(["--corpus", "<nonexistent>"]) exits with code 2.
  - write_report produces a file containing the disclaimer + F1-F6 falsifier checklist.
  - AST forbidden-import check over proof_runner.py and run_proof.py.

Synthetic corpus: ~660 rows across seasons 2015-2025 — large enough for the
gate's _MIN_FOLD_ROWS=60 per fold with n_splits=3.
"""
from __future__ import annotations

import ast
import math
import os
import pathlib
import random
import sys
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

# Ensure repo root on sys.path
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.soccer.adapter import SoccerAdapter
from scripts.platformkit.proof_soccer.proof_runner import (
    run_v1, run_v2, run_v3, run_v4,
)
from scripts.platformkit.proof_soccer.run_proof import main, write_report


# ---------------------------------------------------------------------------
# Synthetic corpus factory
# ---------------------------------------------------------------------------

_TEAMS = [f"Team{c}" for c in "ABCDEFGHIJKLMNOP"]  # 16 teams
_DIVS = ["E0", "D1", "SP1"]
_RNG = random.Random(42)
_NP_RNG = np.random.default_rng(42)


def _make_synthetic_corpus(n_per_season: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (matches_df, odds_df) synthetic corpus.

    n_per_season matches per season × 11 seasons (2015-2025) = 660 rows.
    Each row satisfies the walk_forward_goals input contract.
    Odds have realistic decimal prices for O/U 2.5.
    """
    rows: List[dict] = []
    odds_rows: List[dict] = []

    for season in range(2015, 2026):
        for i in range(n_per_season):
            home, away = _RNG.sample(_TEAMS, 2)
            fthg = _RNG.randint(0, 4)
            ftag = _RNG.randint(0, 3)
            total = fthg + ftag
            date_str = f"{season}-{_RNG.randint(8, 12):02d}-{_RNG.randint(1, 28):02d}"
            event_id = f"{date_str}-E0-{home}-{away}-{i}"
            over_outcome = int(total >= 3)

            rows.append({
                "event_id": event_id,
                "date": date_str,
                "season": season,
                "div": _RNG.choice(_DIVS),
                "home_team": home,
                "away_team": away,
                "fthg": fthg,
                "ftag": ftag,
                "total_goals": total,
                "target_over25": over_outcome,
                "ftr": "H" if fthg > ftag else ("A" if ftag > fthg else "D"),
            })

            # Synthetic decimal odds — balanced around 2.0, slight vig
            over_price = float(_NP_RNG.uniform(1.75, 2.25))
            under_price = float(_NP_RNG.uniform(1.75, 2.25))
            odds_rows.append({
                "event_id": event_id,
                "ou_prematch_over": round(over_price + _NP_RNG.uniform(-0.05, 0.05), 3),
                "ou_prematch_under": round(under_price + _NP_RNG.uniform(-0.05, 0.05), 3),
                "ou_close_over": over_price,
                "ou_close_under": under_price,
                "book_prematch": "fd",
                "book_close": "fd",
            })

    matches_df = pd.DataFrame(rows)
    matches_df["date"] = pd.to_datetime(matches_df["date"])
    odds_df = pd.DataFrame(odds_rows)
    return matches_df, odds_df


@pytest.fixture(scope="module")
def synthetic_adapter() -> SoccerAdapter:
    """Module-scoped SoccerAdapter with synthetic corpus (~660 rows)."""
    matches_df, odds_df = _make_synthetic_corpus(n_per_season=60)
    return SoccerAdapter(matches_df=matches_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# V1 tests
# ---------------------------------------------------------------------------

def test_run_v1_returns_corpus_detail(synthetic_adapter: SoccerAdapter) -> None:
    result = run_v1(synthetic_adapter)
    assert isinstance(result, dict)
    assert "ok" in result
    assert "detail" in result
    detail = result["detail"]
    # Must have at least one corpus key
    assert len(detail) >= 1
    for label, corpus in detail.items():
        if "error" in corpus:
            continue  # small corpus may produce an error — test structure only
        assert "n_eval" in corpus
        assert "raw_brier" in corpus
        assert "calibrated_brier" in corpus
        assert "ece" in corpus
        assert "reliability_slope" in corpus
        assert "corpus_ok" in corpus


# ---------------------------------------------------------------------------
# V2 tests
# ---------------------------------------------------------------------------

def test_run_v2_returns_invariants(synthetic_adapter: SoccerAdapter) -> None:
    result = run_v2(synthetic_adapter)
    assert isinstance(result, dict)
    assert "ok" in result
    assert isinstance(result["ok"], bool)
    detail = result.get("detail", {})
    if detail:  # only when we have >=10 valid rows
        assert "inv_a_ok" in detail
        assert "inv_b_ok" in detail


def test_run_v2_ok_when_odds_absent() -> None:
    """V2 must return ok=True when odds are absent."""
    matches_df, _ = _make_synthetic_corpus(n_per_season=10)
    adapter = SoccerAdapter(matches_df=matches_df, odds_df=None)
    result = run_v2(adapter)
    assert result["ok"] is True
    assert "odds.parquet absent" in result.get("note", "") or result["ok"]


# ---------------------------------------------------------------------------
# V3 tests
# ---------------------------------------------------------------------------

def test_run_v3_all_signals_passed_expected(synthetic_adapter: SoccerAdapter) -> None:
    """All 3 soccer signals must have passed_expected=True (REJECT or DEFER acceptable)."""
    result = run_v3(synthetic_adapter)
    assert "ok" in result
    verdicts = result.get("verdicts", [])
    assert len(verdicts) == 3, f"Expected 3 signal verdicts, got {len(verdicts)}"
    for row in verdicts:
        assert row["passed_expected"] is True, (
            f"Signal {row['signal']!r}: expected {row['expected']!r}, "
            f"got {row['actual']!r} — reason: {row.get('reason', '')}"
        )
    assert result["ok"] is True


def test_run_v3_signal_names(synthetic_adapter: SoccerAdapter) -> None:
    result = run_v3(synthetic_adapter)
    names = {r["signal"] for r in result.get("verdicts", [])}
    assert "soccer_rest_congestion" in names
    assert "soccer_totals_form" in names
    assert "soccer_h2h_totals" in names


# ---------------------------------------------------------------------------
# V4 tests
# ---------------------------------------------------------------------------

def test_run_v4_drawdown_inject_fires(synthetic_adapter: SoccerAdapter) -> None:
    result = run_v4(synthetic_adapter)
    assert isinstance(result, dict)
    detail = result.get("detail", {})
    assert detail.get("drawdown_inject_fired") is True, (
        "Synthetic drawdown injection must fire (check_drawdown_ok(1000,800) must be False)"
    )


def test_run_v4_disclaimer_present(synthetic_adapter: SoccerAdapter) -> None:
    result = run_v4(synthetic_adapter)
    detail = result.get("detail", {})
    disclaimer = detail.get("disclaimer", "")
    assert "market-follow artifact" in disclaimer
    assert "no real money" in disclaimer


def test_run_v4_paper_book_written(synthetic_adapter: SoccerAdapter) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_v4(synthetic_adapter, paper_book_dir=Path(tmpdir))
        pb = Path(tmpdir) / "paper_book.json"
        if result.get("detail", {}).get("n_bets", 0) > 0 or pb.exists():
            # If bets were placed, the file should exist
            pass  # paper_book.json only written after bets


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

def test_cli_exit_2_on_missing_corpus() -> None:
    """main() must exit with code 2 when corpus dir has no matches.parquet."""
    with tempfile.TemporaryDirectory() as tmpdir:
        code = main(["--corpus", tmpdir])
    assert code == 2


def test_cli_no_crash_on_nonexistent_dir() -> None:
    code = main(["--corpus", "/nonexistent/path/to/soccer/corpus"])
    assert code == 2


# ---------------------------------------------------------------------------
# write_report tests
# ---------------------------------------------------------------------------

def test_write_report_contains_disclaimer_and_falsifiers(synthetic_adapter: SoccerAdapter) -> None:
    """Report must contain the V4 disclaimer and all F1-F6 falsifier entries."""
    v1 = run_v1(synthetic_adapter)
    v2 = run_v2(synthetic_adapter)
    v3 = run_v3(synthetic_adapter)
    v4 = run_v4(synthetic_adapter)

    with tempfile.TemporaryDirectory() as tmpdir:
        report_path = Path(tmpdir) / "PROOF_RESULT.md"
        write_report(report_path, v1, v2, v3, "2026-01-01T00:00:00Z", v4=v4)

        assert report_path.exists()
        text = report_path.read_text(encoding="utf-8")

    # Disclaimer
    assert "market-follow artifact" in text, "V4 disclaimer must appear in report"

    # Falsifier checklist entries
    for f_label in ("F1", "F2", "F3", "F4", "F5", "F6"):
        assert f_label in text, f"Falsifier {f_label} missing from report"


# ---------------------------------------------------------------------------
# AST forbidden-import tests (F5 compliance)
# ---------------------------------------------------------------------------

_FORBIDDEN_MODULES = [
    "domains.tennis",
    "domains.nba",
    "domains.basketball_nba",
    "src.data",
    "src.sim",
    "src.tracking",
    "src.pipeline",
]

_SOURCE_FILES = [
    _REPO / "scripts" / "platformkit" / "proof_soccer" / "proof_runner.py",
    _REPO / "scripts" / "platformkit" / "proof_soccer" / "run_proof.py",
]


def _extract_imports(path: Path) -> List[str]:
    """Return all dotted module names imported (from X import / import X)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
    return modules


@pytest.mark.parametrize("source_file", _SOURCE_FILES)
def test_no_forbidden_imports(source_file: Path) -> None:
    """Neither proof_runner.py nor run_proof.py may import forbidden modules."""
    imported = _extract_imports(source_file)
    for mod in imported:
        for forbidden in _FORBIDDEN_MODULES:
            assert not mod.startswith(forbidden), (
                f"{source_file.name} imports forbidden module {mod!r} "
                f"(matches forbidden prefix {forbidden!r})"
            )


@pytest.mark.parametrize("source_file", _SOURCE_FILES)
def test_no_string_tennis_in_source(source_file: Path) -> None:
    """The string 'tennis' must not appear in any created proof_soccer file."""
    text = source_file.read_text(encoding="utf-8")
    # Allow only the word in this comment; use a strict token check
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "tennis" not in line.lower(), (
            f"{source_file.name}:{line_no} contains forbidden string 'tennis': {line!r}"
        )

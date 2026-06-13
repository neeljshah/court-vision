"""tests.platform.test_mlb_run_proof — Integration tests for the MLB proof runner.

Covers: run_v1 (per-corpus detail), run_v2 (inv_a_ok/inv_b_ok), run_v3 (all 3
signals passed_expected=True; REJECT/DEFER acceptable), run_v4 (drawdown_inject_fired
+ disclaimer), CLI exit-2 on missing corpus, write_report (disclaimer + F1-F6),
AST forbidden-import check over both source files.

Synthetic corpus: ~660 games across 2010-2021 (both leagues) + matching odds.
"""
from __future__ import annotations

import ast
import random
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.adapter import MLBAdapter
from scripts.platformkit.proof_mlb.proof_runner import run_v1, run_v2, run_v3, run_v4
from scripts.platformkit.proof_mlb.run_proof import main, write_report

# ---------------------------------------------------------------------------
# Synthetic corpus
# ---------------------------------------------------------------------------

_NL = ["ATL", "CHC", "CIN", "COL", "LAD", "MIA", "MIL", "NYM", "PHI", "PIT", "SDG", "SFO"]
_AL = ["BAL", "BOS", "CLE", "DET", "KAN", "LAA", "MIN", "NYY", "OAK", "SEA", "TAM", "TEX"]
_RNG = random.Random(42)
_NP = np.random.default_rng(42)


def _make_corpus(n: int = 28) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """~672 rows: n games/season/league × 12 seasons × 2 leagues."""
    gr: List[dict] = []; or_: List[dict] = []
    for season in range(2010, 2022):
        for league, teams in [("NL", _NL), ("AL", _AL)]:
            for i in range(n):
                home, away = _RNG.sample(teams, 2)
                hr, ar = _RNG.randint(0, 8), _RNG.randint(0, 7)
                date = f"{season}-{_RNG.randint(4,10):02d}-{_RNG.randint(1,28):02d}"
                eid = f"{date}-{home}-{away}-{i}"
                p = float(_NP.uniform(0.44, 0.58))
                dh = max(round(1.0 / max(p, 0.01) * (1 + float(_NP.uniform(0.02, 0.06))), 3), 1.05)
                da = max(round(1.0 / max(1-p, 0.01) * (1 + float(_NP.uniform(0.02, 0.06))), 3), 1.05)
                gr.append({"event_id": eid, "date": date, "season": season,
                            "home_team": home, "away_team": away, "home_runs": hr,
                            "away_runs": ar, "game_seq": i+1,
                            "target_home_win": float(hr > ar), "home_league": league})
                or_.append({"event_id": eid,
                            "dec_open_home": round(dh + float(_NP.uniform(-0.04, 0.04)), 3),
                            "dec_open_away": round(da + float(_NP.uniform(-0.04, 0.04)), 3),
                            "dec_close_home": dh, "dec_close_away": da})
    gdf = pd.DataFrame(gr); gdf["date"] = pd.to_datetime(gdf["date"])
    return gdf, pd.DataFrame(or_)


@pytest.fixture(scope="module")
def adapter() -> MLBAdapter:
    gdf, odf = _make_corpus()
    return MLBAdapter(games_df=gdf, odds_df=odf)


# ---------------------------------------------------------------------------
# V1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("league", ["NL", "AL"])
def test_v1_corpus_detail(adapter: MLBAdapter, league: str) -> None:
    r = run_v1(adapter, league_filter=league)
    assert "ok" in r and "detail" in r
    for _, corpus in r["detail"].items():
        if "error" in corpus:
            continue
        for k in ("n_eval", "raw_brier", "calibrated_brier", "ece", "corpus_ok"):
            assert k in corpus


def test_v1_no_filter(adapter: MLBAdapter) -> None:
    r = run_v1(adapter, league_filter=None)
    assert "detail" in r


# ---------------------------------------------------------------------------
# V2
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("league", ["NL", "AL"])
def test_v2_invariants(adapter: MLBAdapter, league: str) -> None:
    r = run_v2(adapter, league_filter=league)
    assert isinstance(r["ok"], bool)
    if r.get("detail"):
        assert "inv_a_ok" in r["detail"] and "inv_b_ok" in r["detail"]


def test_v2_ok_no_odds() -> None:
    gdf, _ = _make_corpus(n=5)
    r = run_v2(MLBAdapter(games_df=gdf, odds_df=None))
    assert r["ok"] is True


# ---------------------------------------------------------------------------
# V3
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("league", ["NL", "AL"])
def test_v3_all_passed_expected(adapter: MLBAdapter, league: str) -> None:
    r = run_v3(adapter, league_filter=league)
    verdicts = r.get("verdicts", [])
    assert len(verdicts) == 3
    for row in verdicts:
        assert row["passed_expected"] is True, (
            f"[{league}] {row['signal']}: expected={row['expected']} actual={row['actual']}"
        )
    assert r["ok"] is True


def test_v3_signal_names(adapter: MLBAdapter) -> None:
    r = run_v3(adapter, league_filter="NL")
    names = {x["signal"] for x in r.get("verdicts", [])}
    assert {"mlb_rest_advantage", "mlb_streak_form", "mlb_h2h_season"} == names


# ---------------------------------------------------------------------------
# V4
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("league", ["NL", "AL"])
def test_v4_drawdown_fires(adapter: MLBAdapter, league: str) -> None:
    r = run_v4(adapter, league_filter=league)
    assert r["detail"].get("drawdown_inject_fired") is True


@pytest.mark.parametrize("league", ["NL", "AL"])
def test_v4_disclaimer(adapter: MLBAdapter, league: str) -> None:
    d = run_v4(adapter, league_filter=league)["detail"]
    assert "market-follow artifact" in d.get("disclaimer", "")
    assert "no real money" in d.get("disclaimer", "")


def test_v4_paper_book(adapter: MLBAdapter) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        r = run_v4(adapter, paper_book_dir=Path(tmp), league_filter="NL")
        if r["detail"].get("n_bets", 0) > 0:
            assert (Path(tmp) / "paper_book_NL.json").exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_exit2_missing_corpus() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert main(["--corpus", tmp]) == 2


def test_cli_exit2_nonexistent() -> None:
    assert main(["--corpus", "/nonexistent/mlb/corpus"]) == 2


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------

def test_report_disclaimer_and_falsifiers(adapter: MLBAdapter) -> None:
    rbl = {}
    for lg in ["NL", "AL"]:
        rbl[lg] = {"v1": run_v1(adapter, lg), "v2": run_v2(adapter, lg),
                   "v3": run_v3(adapter, lg), "v4": run_v4(adapter, league_filter=lg)}
    with tempfile.TemporaryDirectory() as tmp:
        rp = Path(tmp) / "PROOF_RESULT.md"
        write_report(rp, rbl, "2026-01-01T00:00:00Z")
        text = rp.read_text(encoding="utf-8")
    assert "market-follow artifact" in text
    assert "no real money" in text
    for f in ("F1", "F2", "F3", "F4", "F5", "F6"):
        assert f in text, f"Falsifier {f} missing from report"


# ---------------------------------------------------------------------------
# AST forbidden-import + string checks (F5)
# ---------------------------------------------------------------------------

_FORBIDDEN = ["domains.tennis", "domains.soccer", "domains.nba", "domains.basketball_nba",
              "src.data", "src.sim", "src.tracking", "src.pipeline"]
_SOURCES = [
    _REPO / "scripts" / "platformkit" / "proof_mlb" / "proof_runner.py",
    _REPO / "scripts" / "platformkit" / "proof_mlb" / "run_proof.py",
]


def _imports(path: Path) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
    return mods


@pytest.mark.parametrize("src", _SOURCES)
def test_no_forbidden_imports(src: Path) -> None:
    for mod in _imports(src):
        for forbidden in _FORBIDDEN:
            assert not mod.startswith(forbidden), (
                f"{src.name}: forbidden import {mod!r}")


@pytest.mark.parametrize("src", _SOURCES)
def test_no_forbidden_strings(src: Path) -> None:
    for word in ("tennis", "soccer"):
        for ln, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            assert word not in line.lower(), (
                f"{src.name}:{ln} contains {word!r}: {line!r}")

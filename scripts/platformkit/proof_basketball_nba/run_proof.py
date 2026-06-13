"""scripts.platformkit.proof_basketball_nba.run_proof — CLI for the NBA moneyline proof.

Mirrors proof_mlb/run_proof.py structure exactly:
  _load_adapter(corpus_dir) -> NBAAdapter or None
  main() prints a V1 calibration report and adapter structure check.

F5: ZERO other-sport-domain / src.data / src.sim / src.tracking / src.pipeline.
CLI: python run_proof.py [--corpus data/domains/basketball_nba] [--verbose]
Exits code 2 if games.parquet absent. PRIVATE: never commit to public repo.
"""
from __future__ import annotations

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

import argparse
import datetime as dt
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from domains.basketball_nba.adapter import NBAAdapter

logger = logging.getLogger(__name__)

_DEFAULT_CORPUS = "data/domains/basketball_nba"


# ---------------------------------------------------------------------------
# Corpus loader (mirrors proof_mlb._load_adapter)
# ---------------------------------------------------------------------------

def _load_adapter(corpus_dir: Path) -> Optional[NBAAdapter]:
    """Return a NBAAdapter or None when games.parquet is absent."""
    games_path = corpus_dir / "games.parquet"
    if not games_path.exists():
        return None
    try:
        games_df = pd.read_parquet(games_path)
    except Exception as exc:
        logger.error("Failed to read games.parquet: %s", exc)
        return None
    odds_df: Optional[pd.DataFrame] = None
    odds_path = corpus_dir / "odds.parquet"
    if odds_path.exists():
        try:
            odds_df = pd.read_parquet(odds_path)
        except Exception:
            logger.warning("odds.parquet unreadable; CLV columns will be absent")
    return NBAAdapter(games_df=games_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# Lightweight V1: calibration summary (no external proof_runner dependency)
# ---------------------------------------------------------------------------

def _run_v1(adapter: NBAAdapter) -> dict:
    """Calibration summary: Brier score of Elo signal vs home_win target."""
    from src.loop.signal import Hypothesis
    hyp = Hypothesis(name="nba_elo_home", target="winprob",
                     scope="pregame", statement="Elo P(home win)")
    try:
        fb = adapter.feature_bundle(hyp)
    except Exception as exc:
        return {"ok": False, "detail": {"error": str(exc)}}

    sig = fb.signal_col
    tgt = fb.target
    brier = float(np.mean((sig - tgt) ** 2))
    n = len(tgt)
    home_rate = float(np.mean(tgt))
    null_brier = float(home_rate * (1 - home_rate))
    has_lines = fb.lines is not None and not np.all(np.isnan(fb.lines))
    market_brier: Optional[float] = None
    if has_lines and fb.lines is not None:
        valid = ~np.isnan(fb.lines)
        if valid.sum() > 0:
            market_brier = float(np.mean((fb.lines[valid] - tgt[valid]) ** 2))

    ok = brier < null_brier + 0.05  # generous: Elo should beat naive null
    return {
        "ok": ok,
        "detail": {
            "n_eval": n,
            "raw_brier": round(brier, 4),
            "null_brier": round(null_brier, 4),
            "home_rate": round(home_rate, 4),
            "market_brier": round(market_brier, 4) if market_brier else None,
            "market_beats_model": (market_brier < brier) if market_brier else None,
            "base_cols": fb.base.shape[1],
            "has_lines": has_lines,
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="NBA moneyline adapter proof runner."
    )
    parser.add_argument("--corpus", default=_DEFAULT_CORPUS)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    repo_root = Path(__file__).resolve().parents[3]
    corpus_dir = (
        (repo_root / args.corpus) if not Path(args.corpus).is_absolute()
        else Path(args.corpus)
    )

    adapter = _load_adapter(corpus_dir)
    if adapter is None:
        print(
            f"[run_proof] corpus not built: games.parquet not found at {corpus_dir}.\n"
            "Run domains/basketball_nba/ingest_schedule.py first.",
            file=sys.stderr,
        )
        return 2

    run_ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    print(f"[run_proof] NBA adapter proof at {run_ts}")
    print(f"[run_proof] corpus: {corpus_dir}")

    print("\n[run_proof] V1: Calibration check ...")
    v1 = _run_v1(adapter)
    d = v1.get("detail", {})
    if "error" in d:
        print(f"  ERROR: {d['error']}")
    else:
        print(f"  n_eval       : {d.get('n_eval')}")
        print(f"  raw_brier    : {d.get('raw_brier')}")
        print(f"  null_brier   : {d.get('null_brier')}")
        print(f"  home_rate    : {d.get('home_rate')}")
        print(f"  market_brier : {d.get('market_brier')}")
        print(f"  mkt>model    : {d.get('market_beats_model')}")
        print(f"  base_cols    : {d.get('base_cols')}")
        print(f"  has_lines    : {d.get('has_lines')}")
    print(f"  V1 ok={v1['ok']}")

    print(f"\n[run_proof] Overall: {'PASS' if v1['ok'] else 'FAIL'}")
    return 0 if v1["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

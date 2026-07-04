"""scripts.platformkit.venue_history.nba_close_benchmark -- benchmark the NBA
pregame model against the OWN-DATA close corpus (nba_close_corpus.py).

WHAT THIS COMPARES: on the subset of NBA games that made it into the close
corpus (see nba_close_corpus.py's honest exclusion accounting), compute Brier
for (a) the leak-free walk-forward GenericRatingModel pregame probability
(scripts.platformkit.generic_rating -- the SAME cross-sport predictor object
used by platform_scoreboard.py, read-only reuse, no edits to that gated
module) and (b) the close-implied probability from our own venue history.

EXPECTED, HONEST RESULT: markets are efficient; the model should MATCH or
TRAIL the close. This is recorded plainly either way -- a "we trail the
close" verdict is the expected efficient-market outcome, not a failure.

METHOD (leak-free): GenericRatingModel.walkforward() is run over the FULL,
date-ordered games.parquet history (so the rating carries all prior-season
information exactly as platform_scoreboard.py does) -- this produces a
PREGAME probability for every game BEFORE that game's own result updates the
rating. We then slice down to just the games.parquet rows whose game_id
appears in the close corpus (a small, non-contiguous subset) and score Brier
on that subset for both the model and the close. No result information from
a benchmarked game ever leaks into its own or an earlier prediction.

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; offline; no
data/registry writes; no flag flips; NO $-edge/ROI claims -- calibration
(Brier) only, and "beats the close" is NOT a claim this module is allowed to
make even if the number briefly favors the model (see module docstring above
and .claude/rules/no-edge-claims.md) -- report the number, do not spin it.

CLI: python -m scripts.platformkit.venue_history.nba_close_benchmark [--json]
     python -m scripts.platformkit.venue_history.nba_close_benchmark --split [--json]
       (per-split report: 2023-24 ESPN-backfilled extension vs the existing
       2024-26 odds_api-referenced corpus -- see run_benchmark_split_report)

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_nba_close_benchmark.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from scripts.platformkit.generic_rating import GenericRatingModel, _brier, _ece, _logloss
from scripts.platformkit.venue_history.nba_close_corpus import DEFAULT_OUT, GAMES_PARQUET

_NOTE = ("Efficient-market expectation: the model MATCHES or TRAILS the close. "
         "Brier/ECE only -- calibration, not edge. No $-edge or ROI claim.")


def _load_games_with_ids(games_parquet: Path = GAMES_PARQUET) -> List[Dict[str, Any]]:
    import pandas as pd  # noqa: PLC0415

    df = pd.read_parquet(games_parquet)
    df = df.sort_values(["date", "game_id"], kind="mergesort").reset_index(drop=True)
    return [
        {"game_id": str(r.game_id), "home": str(r.home_team), "away": str(r.away_team),
         "season": str(r.season), "home_win": float(r.home_win)}
        for r in df.itertuples(index=False)
    ]


_SPLIT_CUTOFF = "2024-11-15"  # odds_api native coverage start; before this is the
# ESPN-backfilled 2023-24 extension (see nba_close_corpus.py's 2023-24 EXTENSION
# note) -- kept as two labelled splits, never pooled into one blended verdict.


def _score_split(games: List[Dict[str, Any]], model_probs: List[float],
                 close_by_gid: Dict[str, float], gids: List[str]) -> Optional[Dict[str, Any]]:
    """Brier/logloss/ECE for model vs close on exactly *gids* (leak-free:
    model_probs already came from a single full-history walkforward run;
    this only slices which rows get scored). None if *gids* is empty."""
    if not gids:
        return None
    idx_by_gid = {g["game_id"]: i for i, g in enumerate(games)}
    y = np.array([games[idx_by_gid[gid]]["home_win"] for gid in gids], dtype=float)
    p_model = np.array([model_probs[idx_by_gid[gid]] for gid in gids], dtype=float)
    p_close = np.array([close_by_gid[gid] for gid in gids], dtype=float)
    model_metrics = {"brier": round(_brier(p_model, y), 5), "logloss": round(_logloss(p_model, y), 5),
                     "ece": round(_ece(p_model, y), 5)}
    close_metrics = {"brier": round(_brier(p_close, y), 5), "logloss": round(_logloss(p_close, y), 5),
                     "ece": round(_ece(p_close, y), 5)}
    brier_gap = round(model_metrics["brier"] - close_metrics["brier"], 5)
    verdict = "MATCHES_CLOSE_WITHIN_NOISE" if brier_gap <= 0.003 else "TRAILS_CLOSE"
    return {"n_games": len(gids), "model": model_metrics, "close": close_metrics,
            "brier_gap_model_minus_close": brier_gap, "verdict": verdict}


def run_benchmark_split_report(*, corpus_path: Optional[Path] = None,
                               games_parquet: Path = GAMES_PARQUET,
                               model: Optional[GenericRatingModel] = None,
                               split_cutoff: str = _SPLIT_CUTOFF) -> Dict[str, Any]:
    """Same leak-free walk-forward scoring as run_benchmark(), but reported as
    TWO independent, provenance-separated splits: games dated before
    *split_cutoff* (the ESPN-backfilled 2023-24 extension, corpus_id
    polymarket_nba_2023_pilot) vs on/after it (the existing 2024-26 corpus).
    Never pools the two splits into one blended Brier -- each gets its own
    honest MATCHES/TRAILS verdict (see .claude/rules/no-edge-claims.md)."""
    import pandas as pd  # noqa: PLC0415

    corpus_fp = Path(corpus_path) if corpus_path is not None else DEFAULT_OUT
    if not corpus_fp.exists():
        return {"error": f"close corpus not found at {corpus_fp} -- run nba_close_corpus.build_corpus() first",
                "note": _NOTE}
    close_df = pd.read_parquet(corpus_fp)
    if close_df.empty:
        return {"error": "close corpus is empty (0 games matched)", "note": _NOTE}
    close_by_gid = {str(r.game_id): float(r.close_prob_home) for r in close_df.itertuples(index=False)}
    date_by_gid = {str(r.game_id): str(r.date)[:10] for r in close_df.itertuples(index=False)}

    games = _load_games_with_ids(games_parquet)
    if not games:
        return {"error": f"games.parquet not found or empty at {games_parquet}", "note": _NOTE}

    mdl = model or GenericRatingModel(hfa=65.0)
    model_probs = mdl.walkforward(games)  # pregame, leak-free, full history

    idx_by_gid = {g["game_id"]: i for i, g in enumerate(games)}
    overlap_gids = [gid for gid in close_by_gid if gid in idx_by_gid]
    if not overlap_gids:
        return {"error": "0 games overlap between games.parquet and the close corpus", "note": _NOTE}

    pre_gids = [g for g in overlap_gids if date_by_gid.get(g, "") < split_cutoff]
    post_gids = [g for g in overlap_gids if date_by_gid.get(g, "") >= split_cutoff]

    return {
        "split_cutoff": split_cutoff,
        "n_games_overlap_total": len(overlap_gids),
        "extension_2023_24": _score_split(games, model_probs, close_by_gid, pre_gids),
        "existing_2024_26": _score_split(games, model_probs, close_by_gid, post_gids),
        "note": ("Two provenance-separated splits, never pooled: extension_2023_24 is the "
                 "ESPN-backfilled 2023 PM pilot window, existing_2024_26 is the odds_api-"
                 "referenced corpus. " + _NOTE),
    }


def run_benchmark(*, corpus_path: Optional[Path] = None,
                  games_parquet: Path = GAMES_PARQUET,
                  model: Optional[GenericRatingModel] = None) -> Dict[str, Any]:
    """Score the leak-free walk-forward model vs the close corpus on their
    overlapping game_ids. Honest verdict: model expected to match/trail close."""
    import pandas as pd  # noqa: PLC0415

    corpus_fp = Path(corpus_path) if corpus_path is not None else DEFAULT_OUT
    if not corpus_fp.exists():
        return {"error": f"close corpus not found at {corpus_fp} -- run nba_close_corpus.build_corpus() first",
                "note": _NOTE}
    close_df = pd.read_parquet(corpus_fp)
    if close_df.empty:
        return {"error": "close corpus is empty (0 games matched)", "note": _NOTE}
    close_by_gid = {str(r.game_id): float(r.close_prob_home) for r in close_df.itertuples(index=False)}

    games = _load_games_with_ids(games_parquet)
    if not games:
        return {"error": f"games.parquet not found or empty at {games_parquet}", "note": _NOTE}

    mdl = model or GenericRatingModel(hfa=65.0)
    model_probs = mdl.walkforward(games)  # pregame, leak-free, full history

    idx_by_gid = {g["game_id"]: i for i, g in enumerate(games)}
    overlap_gids = [gid for gid in close_by_gid if gid in idx_by_gid]
    if not overlap_gids:
        return {"error": "0 games overlap between games.parquet and the close corpus", "note": _NOTE}

    y = np.array([games[idx_by_gid[gid]]["home_win"] for gid in overlap_gids], dtype=float)
    p_model = np.array([model_probs[idx_by_gid[gid]] for gid in overlap_gids], dtype=float)
    p_close = np.array([close_by_gid[gid] for gid in overlap_gids], dtype=float)

    model_metrics = {"brier": round(_brier(p_model, y), 5), "logloss": round(_logloss(p_model, y), 5),
                     "ece": round(_ece(p_model, y), 5)}
    close_metrics = {"brier": round(_brier(p_close, y), 5), "logloss": round(_logloss(p_close, y), 5),
                     "ece": round(_ece(p_close, y), 5)}
    brier_gap = round(model_metrics["brier"] - close_metrics["brier"], 5)
    # Honest verdict: within-noise match (<=0.003, same tolerance platform_scoreboard
    # uses for baseline comparisons) vs a clear trail. NEVER "beats the close".
    if brier_gap <= 0.003:
        verdict = "MATCHES_CLOSE_WITHIN_NOISE"
    else:
        verdict = "TRAILS_CLOSE"

    return {
        "n_games_overlap": len(overlap_gids),
        "n_games_close_corpus": len(close_by_gid),
        "n_games_schedule": len(games),
        "model": model_metrics,
        "close": close_metrics,
        "brier_gap_model_minus_close": brier_gap,
        "verdict": verdict,
        "note": _NOTE,
    }


def _main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--split" in argv:
        rep = run_benchmark_split_report()
        if "--json" in argv:
            print(json.dumps(rep, indent=2))
            return 0
        if "error" in rep:
            print(f"ERROR: {rep['error']}\nNOTE: {rep['note']}")
            return 1
        for key, label in (("extension_2023_24", "2023-24 extension (ESPN-backfilled)"),
                           ("existing_2024_26", "2024-26 (odds_api-referenced)")):
            seg = rep[key]
            if seg is None:
                print(f"{label}: 0 games -- no split result")
                continue
            print(f"{label}: n={seg['n_games']}  model Brier={seg['model']['brier']}  "
                  f"close Brier={seg['close']['brier']}  gap={seg['brier_gap_model_minus_close']}  "
                  f"verdict={seg['verdict']}")
        print(f"NOTE: {rep['note']}")
        return 0

    rep = run_benchmark()
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    if "error" in rep:
        print(f"ERROR: {rep['error']}\nNOTE: {rep['note']}")
        return 1
    print(f"nba_close_benchmark -- {rep['n_games_overlap']} overlapping games "
          f"(of {rep['n_games_close_corpus']} in the close corpus)")
    print(f"  model: Brier={rep['model']['brier']}  close: Brier={rep['close']['brier']}"
          f"  gap={rep['brier_gap_model_minus_close']}  verdict={rep['verdict']}")
    print(f"NOTE: {rep['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

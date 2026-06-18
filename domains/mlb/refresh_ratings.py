"""domains.mlb.refresh_ratings -- CURRENT-as-of MLB ratings without touching the
frozen pipeline.

The frozen corpus (data/domains/mlb/games.parquet) ends 2021-11-02. domains/mlb/ingest_current
materializes games_current.parquet (2022..2026-06-16) from the free MLB Stats API, mapped onto
the SAME SBR codes. This module CONCATENATES (frozen 2010-2021 + current 2022-2026) and runs the
SAME engines the frozen predictor uses -- so today's MLB slate is rated as-of 2026-06-16 instead
of on 4.6yr-stale Elo.

NON-DESTRUCTIVE: the frozen games.parquet and its predictor/tests are untouched. MLBPredictor
already accepts a `games_df=` argument; we just hand it the combined frame. The frozen
default-path predictor (MLBPredictor() with no args) is byte-identical to before.

HONEST: results-only refresh, no odds for 2022+, calibration not edge. The walk-forward MOV-Elo
is leak-free by construction (snapshot-before-update). <=300 LOC.
Run: python -m domains.mlb.refresh_ratings --home BOS --away TOR
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

_REPO = Path(__file__).resolve().parents[2]
_FROZEN = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_CURRENT = _REPO / "data" / "domains" / "mlb" / "games_current.parquet"

_SCHEMA = ["event_id", "date", "season", "home_team", "away_team",
           "home_runs", "away_runs", "target_home_win", "game_seq", "home_league"]


def load_combined_corpus(
    frozen_path: Optional[Path] = None,
    current_path: Optional[Path] = None,
):
    """Return frozen + current concatenated, schema-aligned, chronologically sorted.

    Raises FileNotFoundError if either parquet is missing (current is built by
    domains.mlb.ingest_current). Both must share the frozen schema.
    """
    import pandas as pd  # noqa: PLC0415

    fp = frozen_path or _FROZEN
    cp = current_path or _CURRENT
    if not fp.exists():
        raise FileNotFoundError(f"frozen MLB corpus missing at {fp}")
    if not cp.exists():
        raise FileNotFoundError(
            f"current MLB corpus missing at {cp}; run "
            "`python -m domains.mlb.ingest_current` first")

    frozen = pd.read_parquet(fp)
    current = pd.read_parquet(cp)
    frozen["date"] = pd.to_datetime(frozen["date"])
    current["date"] = pd.to_datetime(current["date"])
    combined = pd.concat([frozen[_SCHEMA], current[_SCHEMA]], ignore_index=True)
    combined = combined.sort_values(
        ["date", "home_team", "away_team", "game_seq"]).reset_index(drop=True)
    return combined


def refreshed_predictor(repo_root: Optional[Path] = None):
    """An MLBPredictor built on (frozen + current) -> ratings as-of the current corpus.

    Same class, same engines as the frozen predictor; only the corpus is extended.
    """
    from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415

    combined = load_combined_corpus()
    return MLBPredictor(games_df=combined, repo_root=repo_root)


def frozen_predictor(repo_root: Optional[Path] = None):
    """The unchanged frozen predictor (2010-2021 only) for contrast."""
    from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415

    return MLBPredictor(repo_root=repo_root)


def refreshed_elo() -> Dict[str, float]:
    """Final MOV-Elo ratings after replaying the COMBINED corpus (as-of 2026-06-16)."""
    from scripts.platformkit.proof_mlb.beat_the_close_ml import final_ratings  # noqa: PLC0415

    return final_ratings(load_combined_corpus())


def frozen_elo() -> Dict[str, float]:
    """Final MOV-Elo ratings from the frozen 2010-2021 corpus only (for contrast)."""
    import pandas as pd  # noqa: PLC0415
    from scripts.platformkit.proof_mlb.beat_the_close_ml import final_ratings  # noqa: PLC0415

    return final_ratings(pd.read_parquet(_FROZEN))


def _main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Refreshed (as-of 2026-06-16) MLB predictor.")
    ap.add_argument("--home", default="BOS")
    ap.add_argument("--away", default="TOR")
    args = ap.parse_args()

    combined = load_combined_corpus()
    print(f"combined corpus: {len(combined)} games, "
          f"{combined['date'].min().date()}..{combined['date'].max().date()}")
    rp = refreshed_predictor()
    print(f"refreshed predictor: {rp.n_games} games, {len(rp.teams)} teams "
          f"(ratings as-of 2026-06-16)")
    pre = rp.predict(args.home, args.away)
    print(json.dumps(pre, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

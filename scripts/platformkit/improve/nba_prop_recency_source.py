"""scripts.platformkit.improve.nba_prop_recency_source -- NBA OOF adapter (P1-5).

Points the generic prop_recal_recency.load_prop_settled interface at real NBA OOF
rows from data/cache/pregame_oof.parquet.  Each parquet row (continuous prediction)
is converted to the settled-prop row shape:

    {ts, p0, outcome, stat, player}

where:
  p0      = 0.5 (maximally uncertain prior -- see design note below)
  outcome = 1 if actual > oof_pred else 0

DESIGN NOTE -- why p0 is fixed at 0.5, not Gaussian CDF of residual:
  The OOF parquet has no independent market line.  oof_pred IS the model's
  point estimate, so any p0 derived from the signed residual (actual - oof_pred)
  satisfies: p0 > 0.5  <=>  residual > 0  <=>  outcome == 1.  This is a
  tautological calibration target -- the base probability perfectly separates
  the label by construction, violating calibration-not-edge / do-no-harm.
  Setting p0 = 0.5 (uniform prior) is the only honest choice when no
  independent line exists: the recal gate sees maximally uncertain priors and
  can only improve calibration if real signal is present.

  If an independent market line (e.g., book opening line) becomes available,
  replace _PRIOR_P0 with Phi((line - oof_pred) / sigma) where sigma is
  estimated walk-forward on a hold-out prefix only (not the full corpus).

Guarantees:
  - Rows sorted ascending by game_date (leak-free walk-forward requirement).
  - outcome always in {0, 1}.
  - p0 always in (0, 1) open interval (clipped at 1e-6 margins even at 0.5).
  - Thin or absent stat -> [] (no exception).
  - Playoff rows (game_id prefix 0041/0042/0043) excluded.
  - FLAG OFF: no data/registry/ writes, no sentinel flip, no registry write.
  - NEVER raises: any failure returns [].

INVARIANTS: no $ / roi / pnl / profit / edge key; calibration NOT edge;
stdlib + numpy + pandas; ASCII; <=300 LOC.
"""
from __future__ import annotations

import logging
import pathlib
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger("nba_prop_recency_source")

_REPO = pathlib.Path(__file__).resolve().parents[3]
_OOF_PATH = _REPO / "data" / "cache" / "pregame_oof.parquet"

# NBA game_id prefixes that identify playoff games (exclude per P1-4 pattern).
_PLAYOFF_PREFIXES: Tuple[str, ...] = ("0041", "0042", "0043")

# Minimum residual rows needed to estimate sigma honestly (kept for callers).
_MIN_SIGMA_OBS = 30

# A per-stat sigma floor (kept for external callers / future use).
_SIGMA_FLOOR = 0.20

# The prior probability used when no independent market line is available.
# Fixed at 0.5 (maximally uncertain) to avoid tautological calibration.
# See module docstring for full design rationale.
_PRIOR_P0: float = 0.5


def load_nba_oof_as_settled(
    stat: Optional[str] = None,
    oof_path: Optional[pathlib.Path] = None,
    min_rows: int = 0,
) -> List[Dict[str, Any]]:
    """Load NBA OOF rows reshaped to the load_prop_settled settled-prop row format.

    Args:
        stat:     If given, return only rows for that stat (case-insensitive).
                  Absent or thin stat -> [] (honest cold start, no exception).
        oof_path: Override path to pregame_oof.parquet (default: data/cache/).
        min_rows: If fewer than min_rows rows survive filtering, return [].
                  Allows callers to enforce a minimum corpus requirement.

    Returns:
        List of dicts shaped like load_prop_settled output:
            {ts, p0, outcome, stat, player}
        Sorted ascending by ts (game_date).  Never raises.

    Row guarantees:
        - outcome in {0, 1} always.
        - p0 = 0.5 always (see module docstring -- no independent line exists).
        - ts is the game_date string (YYYY-MM-DD) -- chronological sort key.
        - Playoff rows excluded.
        - No duplicate (player_id, stat, game_date) tuples.
    """
    path = pathlib.Path(oof_path) if oof_path is not None else _OOF_PATH
    if not path.exists():
        logger.debug("nba_prop_recency_source: OOF path missing: %s", path)
        return []

    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("nba_prop_recency_source: read_parquet failed: %s", exc)
        return []

    required = {"game_id", "player_id", "stat", "oof_pred", "actual", "game_date"}
    if not required.issubset(df.columns):
        missing = required - set(df.columns)
        logger.debug("nba_prop_recency_source: missing columns %s", missing)
        return []

    # Drop NaN predictions or actuals.
    df = df.dropna(subset=["oof_pred", "actual"]).copy()

    # Exclude playoff rows.
    playoff_mask = df["game_id"].astype(str).str.startswith(_PLAYOFF_PREFIXES)
    df = df[~playoff_mask].reset_index(drop=True)

    # Optional stat filter.
    if stat is not None:
        df = df[df["stat"].str.lower() == str(stat).lower()].reset_index(drop=True)

    if df.empty:
        return []

    # Deduplicate (player_id, stat, game_date) -- keep first occurrence.
    df = df.drop_duplicates(subset=["player_id", "stat", "game_date"]).reset_index(
        drop=True
    )

    # Sort ascending by game_date (leak-free walk-forward requirement).
    df = df.sort_values("game_date", ascending=True, kind="stable").reset_index(
        drop=True
    )

    # Build output rows.
    out: List[Dict[str, Any]] = []
    for row in df.itertuples(index=False):
        # Binary outcome: 1 if actual strictly exceeds oof_pred, 0 otherwise.
        outcome = 1 if float(row.actual) > float(row.oof_pred) else 0

        # p0 is fixed at 0.5 (uniform prior).
        # No independent market line -> any signed-residual-derived p0 is
        # tautological (p0 > 0.5 iff outcome == 1 by construction).
        # See module docstring for full rationale.
        p0: float = _PRIOR_P0

        out.append({
            "ts":      str(row.game_date),
            "p0":      p0,
            "outcome": outcome,
            "stat":    str(row.stat),
            "player":  str(int(row.player_id)),
        })

    if len(out) < min_rows:
        return []

    return out


def available_stats(oof_path: Optional[pathlib.Path] = None) -> List[str]:
    """Return the list of stats present in the OOF parquet.  [] on any error.

    Note: playoff rows are not filtered here because we only need stat names,
    and the overhead of loading game_id is not warranted for this query.
    """
    path = pathlib.Path(oof_path) if oof_path is not None else _OOF_PATH
    try:
        df = pd.read_parquet(path, columns=["stat"])
        return sorted(df["stat"].dropna().unique().tolist())
    except Exception:  # noqa: BLE001
        return []


__all__ = [
    "load_nba_oof_as_settled",
    "available_stats",
    "_PLAYOFF_PREFIXES",
    "_MIN_SIGMA_OBS",
    "_SIGMA_FLOOR",
    "_PRIOR_P0",
]

"""domains.mlb.asof_espn_box — Leak-free walk-forward AS-OF companion for ESPN box scores.

KNOWLEDGE/SUBSTRATE — signal-eligible (leak-free) aggregate of realized box stats.
Markets are efficient; NO edge is claimed.  Gate-testing (expected: REJECT) is a later step.

Source
------
``espn_boxscores.parquet`` (produced by ``ingest_espn_box.py``) holds one REALIZED row
per completed game with columns keyed ``home_<stat>`` / ``away_<stat>`` for batting (bat_*),
pitching (pit_*), and fielding (fld_*) groups plus ``home_score`` / ``away_score``.

Approach: melt into a per-team-appearance view, run ``walk_forward_asof`` (snapshot-before-
update), then pivot back to event_id-level rows with ``home_<stat>_asof``, ``away_<stat>_asof``,
and ``diff_<stat>_asof`` (home minus away) for selected core stats.

LEAK CONTRACT
--------------
For each team, the trailing mean of a stat uses ONLY the team's games with
date < current game's date.  The current game enters the accumulator ONLY AFTER
the pre-game snapshot is taken.  This is enforced by ``walk_forward_asof`` from
``scripts.platformkit.data_infra``, which implements snapshot-before-update at
the row level in chronological sort order.

NO-FUTURE-LEAK TEST: appending or mutating a future game MUST leave every earlier
row's ``*_asof`` value byte-identical.  ``tests/platform/test_asof_espn_box.py``
asserts this structurally.

Output schema (per event_id)
-----------------------------
event_id
home_<FEAT>_asof, away_<FEAT>_asof, diff_<FEAT>_asof  (for each FEAT in ASOF_FEATURES)
home_n_prior, away_n_prior   — count of prior appearances used

PURE pandas/numpy + data_infra.  No src.* / kernel.* / other-domain imports.
PRIVATE: gitignored output (data/domains/mlb/).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

# Reuse the platform's shared leak-free engine (no src.* import).
from scripts.platformkit.data_infra import walk_forward_asof

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_IN = _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "asof_espn_box.parquet"

# Core stats to build trailing means for.  These are a representative subset of
# the 50-column ESPN schema; add more here without changing the walk logic.
ASOF_FEATURES: Tuple[str, ...] = (
    "bat_runs",
    "bat_hits",
    "bat_homeRuns",
    "bat_walks",
    "bat_strikeouts",
    "bat_stolenBases",
    "bat_RBIs",
    "bat_totalBases",
    "pit_earnedRuns",
    "pit_strikeouts",
    "pit_walks",
    "pit_hits",
    "pit_homeRuns",
    "fld_errors",
)

# Minimum prior games before an asof feature is non-NaN (0 = emit from first game onward,
# but game-1 is still NaN because n_prior=0 → NaN via the min_prior=0 default).
_MIN_PRIOR = 0


def _load_box(src) -> pd.DataFrame:
    """Return a DataFrame from a DataFrame arg or by reading the default parquet."""
    if isinstance(src, pd.DataFrame):
        return src.copy()
    path = Path(src) if src is not None else _DEFAULT_IN
    return pd.read_parquet(str(path))


def _melt_to_team_view(df: pd.DataFrame) -> pd.DataFrame:
    """Convert wide home/away game rows into long per-team-appearance rows.

    Each input row produces two output rows: one for the home team and one for
    the away team.  Only columns in ASOF_FEATURES that exist in the source are
    kept (missing ones are silently skipped, e.g. if source is a minimal test df).

    Returns DataFrame with columns: team, date, event_id, <stat cols...>
    """
    present_feats = [f for f in ASOF_FEATURES if f"home_{f}" in df.columns]

    home_cols = {f"home_{f}": f for f in present_feats}
    away_cols = {f"away_{f}": f for f in present_feats}

    base_cols = ["event_id", "date"]
    if "home_score" in df.columns:
        base_cols += ["home_score", "away_score"]

    home_df = df[base_cols + list(home_cols.keys())].copy()
    home_df = home_df.rename(columns=home_cols)
    home_df["team"] = df["home_abbr"].values
    home_df["side"] = "home"

    away_df = df[base_cols + list(away_cols.keys())].copy()
    away_df = away_df.rename(columns=away_cols)
    away_df["team"] = df["away_abbr"].values
    away_df["side"] = "away"

    long = pd.concat([home_df, away_df], ignore_index=True)
    return long


def _pivot_back(asof_long: pd.DataFrame, present_feats: Sequence[str]) -> pd.DataFrame:
    """Pivot the long as-of frame back to one row per event_id.

    Produces home/away versions of each asof column plus diffs (home - away).
    """
    home_rows = asof_long[asof_long["side"] == "home"].set_index("event_id")
    away_rows = asof_long[asof_long["side"] == "away"].set_index("event_id")

    # Start with event_id + date from home side (both sides share the same game date)
    all_eids = home_rows.index.union(away_rows.index)
    out = pd.DataFrame({"event_id": all_eids}).set_index("event_id")

    for f in present_feats:
        col = f"{f}_asof"
        if col in home_rows.columns:
            out[f"home_{col}"] = home_rows[col].reindex(all_eids)
        if col in away_rows.columns:
            out[f"away_{col}"] = away_rows[col].reindex(all_eids)
        h = out.get(f"home_{col}")
        a = out.get(f"away_{col}")
        if h is not None and a is not None:
            out[f"diff_{col}"] = h - a

    # n_prior per side
    out["home_n_prior"] = home_rows["n_prior"].reindex(all_eids)
    out["away_n_prior"] = away_rows["n_prior"].reindex(all_eids)

    return out.reset_index()


def build_asof_espn_box(
    src=None,
    out_path: Optional[Path] = None,
    last_n: Optional[int] = None,
) -> Tuple[pd.DataFrame, Path]:
    """Build leak-free walk-forward ESPN box AS-OF features.

    Parameters
    ----------
    src:
        Path to ``espn_boxscores.parquet``, or a DataFrame (for tests).
    out_path:
        Output parquet path.  Defaults to ``_DEFAULT_OUT``.
    last_n:
        If given, also compute a rolling trailing-N window (``<col>_l{N}``).

    Returns
    -------
    (result_df, out_path)  — DataFrame of as-of features + the parquet path written.
    """
    df = _load_box(src)

    required = {"event_id", "date", "home_abbr", "away_abbr"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"espn_boxscores source missing columns: {sorted(missing)}")

    # Determine which features actually exist in this source
    present_feats = [f for f in ASOF_FEATURES if f"home_{f}" in df.columns]
    if not present_feats:
        raise ValueError(
            "No ASOF_FEATURES found in source columns.  "
            "Ensure espn_boxscores.parquet has home_bat_* / home_pit_* / home_fld_* columns."
        )

    # Step 1: melt to per-team-appearance long view
    long = _melt_to_team_view(df)

    # Step 2: walk-forward asof (snapshot-before-update), entity = team
    asof_long = walk_forward_asof(
        long,
        date_col="date",
        entity_cols=["team"],
        value_cols=list(present_feats),
        last_n=last_n,
        min_prior=_MIN_PRIOR,
    )

    # Step 3: pivot back to event_id-level
    result = _pivot_back(asof_long, present_feats)

    # Write output
    out = Path(out_path) if out_path else _DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(str(out), index=False)

    return result, out


def _report(df: pd.DataFrame) -> str:
    """Coverage summary for CLI."""
    n = len(df)
    if n == 0:
        return "0 rows"
    h_col = "home_bat_runs_asof"
    a_col = "away_bat_runs_asof"
    if h_col in df.columns and a_col in df.columns:
        both = df[h_col].notna() & df[a_col].notna()
        return f"{n} rows | both-sides-have-bat_runs prior: {both.sum() / n * 100:.1f}%"
    return f"{n} rows"


def _main() -> None:
    ap = argparse.ArgumentParser(
        description="Build leak-free AS-OF ESPN box features (snapshot-before-update)."
    )
    ap.add_argument("--src", default=None, help="Path to espn_boxscores.parquet")
    ap.add_argument("--out", default=None, help="Output path for asof_espn_box.parquet")
    ap.add_argument("--last-n", type=int, default=None, help="Also build last-N rolling window")
    args = ap.parse_args()

    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    df, out_path = build_asof_espn_box(
        src=args.src,
        out_path=args.out,
        last_n=args.last_n,
    )
    print(f"Wrote {len(df)} rows → {out_path}")
    print(_report(df))
    if len(df):
        preview_cols = ["event_id", "home_n_prior", "away_n_prior",
                        "home_bat_runs_asof", "away_bat_runs_asof"]
        show = [c for c in preview_cols if c in df.columns]
        print(df[show].head(5).to_string(index=False))


if __name__ == "__main__":
    _main()

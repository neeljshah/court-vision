"""domains.mlb.sp_quality_asof -- Family SP1 (as-of starter quality from statcast).

PREREG (DEEP_FEATURES_PREREG.md lines 54-56, declared before testing):
"SP1 as-of starter quality from statcast (EW xwOBA-against last 6 starts,
walk-forward) -- kills pitcher-blindness with data already on the pod."

INPUT: raw Statcast pitch-level frames (statcast_fuller__<season>.parquet,
~720k rows/season) with columns incl. game_pk, game_date, inning,
inning_topbot ('Top'/'Bot'), pitcher, home_team, away_team,
estimated_woba_using_speedangle (populated on PA-terminal pitches only).
There is NO is_starter flag -- the starter for a team-half is the pitcher of
that half's inning-1 pitches: the Top-of-1 pitcher is the HOME team's
starter (home team is on defense while the away team bats top of the
inning); the Bot-of-1 pitcher is the AWAY team's starter.

PER-START xwOBA-against = mean(estimated_woba_using_speedangle) over that
game's PA-terminal rows for the identified starter's pitcher id (naturally
spans every inning the starter pitched before being relieved, since a
starter never appears on the opposing team-half).

WALK-FORWARD FEATURE (prereg constants, declared here): per pitcher, sorted
by (game_date, game_pk), sp_xwoba_against_asof at start i = an
exponentially-weighted mean (ALPHA=0.35 default) of the STRICTLY PRIOR up to
WINDOW=6 starts' per-start xwOBA-against, most-recent-prior weighted
highest: weight_j = (1-alpha)**(k-1-j) for the j-th of k prior values
(j=0..k-1, oldest first), normalized to sum to 1. Start i's OWN value is
never in its own window (excluded before the window is read). NaN when
n_prior_starts == 0 (debut). A start with no PA-terminal rows (no raw value)
still gets an asof read from earlier starts, but contributes nothing to
later starts' windows.

Pure core: build_sp_quality_asof_from_frame(pitches_df) -> frame, no I/O.
Thin loader: build_sp_quality_asof(statcast_paths) reads + concats parquet
paths, then delegates to the core. Fails closed (empty frame) if no path
exists -- real-data run happens on the pod; this worktree has no data/.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
_STATCAST_DIR = _REPO / "data" / "cache" / "statcast"

ALPHA = 0.35
WINDOW = 6

_OUT_COLS = ["pitcher", "game_pk", "game_date", "team", "sp_xwoba_against_asof", "n_prior_starts"]

DEFAULT_STATCAST_PATHS = [
    _STATCAST_DIR / "statcast_fuller__2022.parquet",
    _STATCAST_DIR / "statcast_fuller__2023.parquet",
]


def _identify_starters(pitches: pd.DataFrame) -> pd.DataFrame:
    """One row per (game_pk, team) with the team-half's inning-1 pitcher (the
    starter), that team's game_date, and 'side' (Top=home pitching, Bot=away
    pitching) carried for the per-start aggregation merge."""
    inn1 = pitches[pitches["inning"] == 1]
    meta = pitches.groupby("game_pk", as_index=False).agg(
        game_date=("game_date", "first"), home_team=("home_team", "first"),
        away_team=("away_team", "first"))
    home = inn1[inn1["inning_topbot"] == "Top"].groupby("game_pk", as_index=False)["pitcher"].first()
    home["side"] = "Top"
    away = inn1[inn1["inning_topbot"] == "Bot"].groupby("game_pk", as_index=False)["pitcher"].first()
    away["side"] = "Bot"
    starters = pd.concat([home, away], ignore_index=True).merge(meta, on="game_pk", how="left")
    starters["team"] = np.where(starters["side"] == "Top", starters["home_team"], starters["away_team"])
    return starters[["game_pk", "game_date", "pitcher", "side", "team"]]


def _per_start_xwoba(pitches: pd.DataFrame, starters: pd.DataFrame) -> pd.DataFrame:
    """Merge each starter onto its OWN outing's PA-terminal rows (matched by
    game_pk + pitcher id -- a starter only ever appears on one team-half, so
    this naturally captures every inning pitched before a pitching change)."""
    pa = pitches[pitches["estimated_woba_using_speedangle"].notna()]
    agg = pa.merge(starters[["game_pk", "pitcher"]], on=["game_pk", "pitcher"], how="inner") \
        .groupby(["game_pk", "pitcher"], as_index=False) \
        .agg(sp_xwoba_against=("estimated_woba_using_speedangle", "mean"))
    return starters.merge(agg, on=["game_pk", "pitcher"], how="left")


def _ew_asof_sequence(values: Sequence[float], alpha: float = ALPHA,
                       window: int = WINDOW) -> Tuple[List[float], List[int]]:
    """For each position i (in the given chronological order), an EW mean
    over up to `window` immediately preceding NON-NULL values (see module
    docstring for the weight formula). Current position's own value is
    appended to history only AFTER its asof is computed, and only if it is
    not NaN -- so it can never affect its own read, and a later position can
    never affect an earlier one."""
    hist: List[float] = []
    asof: List[float] = []
    nprior: List[int] = []
    for v in values:
        window_vals = hist[-window:] if hist else []
        k = len(window_vals)
        nprior.append(k)
        if k == 0:
            asof.append(float("nan"))
        else:
            w = np.array([(1 - alpha) ** (k - 1 - j) for j in range(k)])
            asof.append(float(np.dot(w, window_vals) / w.sum()))
        if not (isinstance(v, float) and np.isnan(v)):
            hist.append(v)
    return asof, nprior


def build_sp_quality_asof_from_frame(pitches: pd.DataFrame, alpha: float = ALPHA) -> pd.DataFrame:
    """Pure core: raw pitch-level frame in -> per-start asof feature frame out."""
    if pitches.empty:
        return pd.DataFrame(columns=_OUT_COLS)
    starters = _identify_starters(pitches)
    starts = _per_start_xwoba(pitches, starters)
    starts["game_date"] = pd.to_datetime(starts["game_date"])
    starts = starts.sort_values(["pitcher", "game_date", "game_pk"]).reset_index(drop=True)

    def _asof_for_group(g: pd.DataFrame) -> pd.DataFrame:
        a, n = _ew_asof_sequence(g["sp_xwoba_against"].tolist(), alpha=alpha)
        return pd.DataFrame({"sp_xwoba_against_asof": a, "n_prior_starts": n}, index=g.index)

    asof = starts.groupby("pitcher", sort=False, group_keys=False).apply(
        _asof_for_group, include_groups=False)
    starts = starts.join(asof)
    return starts[_OUT_COLS].reset_index(drop=True)


def build_sp_quality_asof(statcast_paths: List[Path], alpha: float = ALPHA) -> pd.DataFrame:
    """Thin loader: read + concat existing statcast parquet paths, delegate
    to the pure core. Fails closed (empty frame) if none of the paths exist
    -- this worktree has no data/; the real run happens on the pod."""
    frames = [pd.read_parquet(p) for p in statcast_paths if Path(p).exists()]
    if not frames:
        return pd.DataFrame(columns=_OUT_COLS)
    pitches = pd.concat(frames, ignore_index=True)
    return build_sp_quality_asof_from_frame(pitches, alpha=alpha)


def load_default() -> pd.DataFrame:
    """CLI convenience: build from DEFAULT_STATCAST_PATHS."""
    return build_sp_quality_asof(DEFAULT_STATCAST_PATHS)


__all__ = [
    "build_sp_quality_asof", "build_sp_quality_asof_from_frame", "load_default",
    "DEFAULT_STATCAST_PATHS", "ALPHA", "WINDOW",
]


if __name__ == "__main__":
    out = load_default()
    print(f"sp_quality_asof: {len(out)} starter-appearances "
          f"(n_with_prior>=1: {(out['n_prior_starts'] >= 1).sum() if not out.empty else 0})")

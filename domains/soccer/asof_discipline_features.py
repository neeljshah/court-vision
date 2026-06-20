"""domains.soccer.asof_discipline_features -- leak-free AS-OF trailing EW form for
the DISCIPLINE / POSSESSION-PROXY substrate (corners / fouls / yellow / red /
SoT-ratio), the football-data.co.uk dense mirror of the ESPN-28 match-stats fields.

The ESPN-28 athlete/match feed (offsides, saves, possessionPct, ...) is RICH but
THIN on disk (~185 graded matches) -- too few rows for a leak-free walk-forward with
cross-corpus replication. The IDENTICAL discipline + possession-proxy facts live,
DENSE (~26k matches, 6 leagues, ~100% coverage), in the football-data match_stats
sidecar (HC/AC corners, HF/AF fouls, HY/AY yellows, HR/AR reds, HST/HS SoT-ratio as a
possession/territory proxy). This builder aggregates THOSE as strictly-prior trailing
exponentially-weighted (EW) form, so the gate has a real corpus to test on; the
ESPN-28 feed itself is reported INSUFFICIENT_DATA honestly by the gate-run.

LEAK-NOTE: the feature row for match *i* uses ONLY each team's matches whose
``date < date(i)`` -- a strict snapshot-BEFORE-update walk-forward (identical
discipline to domains.soccer.asof_features and domains.soccer.ratings). The current
match's own discipline stats are NEVER folded into its own feature. The realized
result is the LABEL only, never a feature. NO season/match-final aggregate is read on
a per-row. This DEEPENS the substrate / calibration; NO market edge is claimed.

EW (recency) form: snapshot reads the PRE-match EW state; update folds a settled match
in with step ALPHA after the snapshot. A team with no prior match gets an all-NaN row
(we REFUSE to 0-fill an unseen team into a fake value).

PURE pandas/numpy. NO src.* / kernel.* / domains.nba.* imports.
PRIVATE: lives under data/domains/soccer/ which is never tracked.
football-data.co.uk data is free for personal/research use only.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.soccer.config import DATA_DIR_REL

_REPO_ROOT = Path(__file__).resolve().parents[2]
ALPHA = 0.20  # EW update step (recency form; matches ratings/pregame_winprob spirit)

# The team-fact stats we trail (each is a per-match count or ratio; SoT-ratio is the
# free possession/territory proxy standing in for ESPN possessionPct).
_STATS: Tuple[str, ...] = ("corners", "fouls", "yellow", "red", "sot_ratio")

# Output column contract (parquet column order). For each stat we emit the home and
# away PRIOR-only EW value plus the home-minus-away diff (the gate's candidate axis).
ASOF_DISC_COLS: Tuple[str, ...] = (
    "event_id",
    "home_corners_asof", "away_corners_asof", "diff_corners_asof",
    "home_fouls_asof", "away_fouls_asof", "diff_fouls_asof",
    "home_yellow_asof", "away_yellow_asof", "diff_yellow_asof",
    "home_red_asof", "away_red_asof", "diff_red_asof",
    "home_sot_ratio_asof", "away_sot_ratio_asof", "diff_sot_ratio_asof",
    "home_n_prior", "away_n_prior",
)


class _TeamEW:
    """Running prior-match EW state for one team across ALL its appearances.

    ``snapshot()`` reads the PRE-match EW values (all-NaN before the first match);
    ``update(...)`` folds a settled match in afterwards with step ALPHA. A team's
    discipline is a team fact, not a home/away fact, so home and away appearances
    feed the SAME running state.
    """

    __slots__ = ("n", "ew", "alpha")

    def __init__(self, alpha: float = ALPHA) -> None:
        self.n = 0
        self.alpha = alpha
        self.ew: Dict[str, float] = {s: float("nan") for s in _STATS}

    def snapshot(self) -> Dict[str, float]:
        """Prior-only EW values; all-NaN when this team has no prior match."""
        if self.n == 0:
            return {s: float("nan") for s in _STATS}
        return dict(self.ew)

    def update(self, vals: Dict[str, float]) -> None:
        """Fold a settled match in. A stat that is non-finite this match is simply
        not updated (its EW carries forward) -- we never inject a 0 for a missing
        stat. The row counts toward ``n`` once at least one core stat is finite."""
        any_finite = False
        for s in _STATS:
            v = vals.get(s, float("nan"))
            if not np.isfinite(v):
                continue
            any_finite = True
            cur = self.ew[s]
            if not np.isfinite(cur):
                self.ew[s] = v               # seed EW with the first finite value
            else:
                self.ew[s] = cur + self.alpha * (v - cur)
        if any_finite:
            self.n += 1


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Pinned (date, div, home_team, away_team) chronological order, mergesort-stable
    -- the SAME ordering rule as domains.soccer.asof_features / ratings, so the
    walk-forward sequence is single and deterministic."""
    n = len(df)
    keys = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).astype("int64").values,
            "k1": (df["div"].astype(str).values
                   if "div" in df.columns else [""] * n),
            "k2": df["home_team"].astype(str).values,
            "k3": df["away_team"].astype(str).values,
        },
        index=df.index,
    )
    order = keys.sort_values(["k0", "k1", "k2", "k3"], kind="mergesort").index
    return df.loc[order].reset_index(drop=True)


def build_asof_disc_frame(match_stats: pd.DataFrame, alpha: float = ALPHA) -> pd.DataFrame:
    """Pure transform: match_stats contract DataFrame -> ASOF_DISC_COLS DataFrame.

    Walk-forward, snapshot-BEFORE-update. Separated from I/O so the leak-free
    contract is unit-testable from fixtures. Output is 1:1 with input rows, keyed by
    event_id; every feature is NaN when that team's n_prior == 0.
    """
    if match_stats is None or len(match_stats) == 0:
        return pd.DataFrame(columns=list(ASOF_DISC_COLS))

    df = _sorted(match_stats)

    def _f(col: str) -> np.ndarray:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").astype("float64").values
        return np.full(len(df), np.nan, dtype="float64")

    # home/away raw per-match facts (the "for" stat of each team)
    raw = {
        "corners": (_f("home_corners"), _f("away_corners")),
        "fouls": (_f("home_fouls"), _f("away_fouls")),
        "yellow": (_f("home_yellow"), _f("away_yellow")),
        "red": (_f("home_red"), _f("away_red")),
        "sot_ratio": (_f("home_sot_ratio"), _f("away_sot_ratio")),
    }
    home = df["home_team"].astype(str).values
    away = df["away_team"].astype(str).values
    event_id = df["event_id"].astype(str).values

    hist: Dict[str, _TeamEW] = {}
    rows: List[Dict[str, object]] = []

    def _diff(x: float, y: float) -> float:
        return (x - y) if (np.isfinite(x) and np.isfinite(y)) else float("nan")

    for i in range(len(df)):
        h, a = home[i], away[i]
        h_hist = hist.setdefault(h, _TeamEW(alpha))
        a_hist = hist.setdefault(a, _TeamEW(alpha))

        # ---- SNAPSHOT (strictly prior matches only) ----
        hs = h_hist.snapshot()
        as_ = a_hist.snapshot()

        row: Dict[str, object] = {"event_id": event_id[i]}
        for s in _STATS:
            row[f"home_{s}_asof"] = hs[s]
            row[f"away_{s}_asof"] = as_[s]
            row[f"diff_{s}_asof"] = _diff(hs[s], as_[s])
        row["home_n_prior"] = h_hist.n
        row["away_n_prior"] = a_hist.n
        rows.append(row)

        # ---- UPDATE (post-match; never seen by this match's own snapshot) ----
        h_vals = {s: raw[s][0][i] for s in _STATS}
        a_vals = {s: raw[s][1][i] for s in _STATS}
        h_hist.update(h_vals)
        a_hist.update(a_vals)

    out = pd.DataFrame(rows, columns=list(ASOF_DISC_COLS))
    out["home_n_prior"] = out["home_n_prior"].astype("int64")
    out["away_n_prior"] = out["away_n_prior"].astype("int64")
    return out


def build_asof_discipline_features(
    match_stats: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
    alpha: float = ALPHA,
) -> Path:
    """Build the leak-free AS-OF discipline/possession-proxy feature parquet.

    match_stats: the match_stats sidecar contract DataFrame (event_id, date,
        home_team, away_team, home_/away_ corners/fouls/yellow/red/sot_ratio). If
        None, the default data/domains/soccer/match_stats.parquet is read.
    out_path: defaults to data/domains/soccer/asof_discipline_features.parquet.
    Returns the written parquet path.
    """
    if match_stats is None:
        src = _REPO_ROOT / DATA_DIR_REL / "match_stats.parquet"
        match_stats = pq.read_table(src).to_pandas()
    out_file = (Path(out_path) if out_path
                else (_REPO_ROOT / DATA_DIR_REL / "asof_discipline_features.parquet"))
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df = build_asof_disc_frame(match_stats, alpha=alpha)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_file)
    return out_file


def main() -> None:
    """CLI: build the sidecar, print rows + a sample + coverage."""
    parser = argparse.ArgumentParser(
        description="leak-free AS-OF EW discipline/possession-proxy form for soccer")
    parser.add_argument("--out-path", default=None)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    args = parser.parse_args()
    out_file = build_asof_discipline_features(out_path=args.out_path, alpha=args.alpha)
    df = pq.read_table(out_file).to_pandas()
    print(f"asof_discipline_features: wrote {len(df)} rows -> {out_file}")
    cols = ["event_id", "diff_corners_asof", "diff_fouls_asof",
            "diff_yellow_asof", "home_n_prior", "away_n_prior"]
    print(df[cols].head(5).to_string(index=False))
    have = (df["home_n_prior"] > 0) & (df["away_n_prior"] > 0)
    cov = (have.mean() * 100.0) if len(df) else 0.0
    print(f"coverage (both teams have prior history): {have.sum()}/{len(df)} "
          f"= {cov:.1f}%")


if __name__ == "__main__":
    main()


__all__ = ["ALPHA", "ASOF_DISC_COLS", "build_asof_disc_frame",
           "build_asof_discipline_features"]

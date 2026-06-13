"""domains.soccer.asof_features — leak-free AS-OF rolling shot-quality form.

Walk a chronologically-sorted match sequence (the W59 ``match_stats`` sidecar) and
emit, for EACH match, both teams' PRIOR-only rolling shot / shot-on-target form.
Shots-on-target (SoT) is a free xG proxy, so a team's trailing SoT-for / SoT-against
and SoT ratio describe its recent attacking-quality and defensive-suppression form.

LEAK-NOTE: the feature row for match *i* uses ONLY each team's matches whose
``date < date(i)`` — a strict snapshot-BEFORE-update walk-forward (identical
discipline to ``domains.soccer.ratings``).  A team's history aggregates EVERY
prior appearance, whether it played HOME or AWAY (a team's shots are a team fact,
not a home/away fact).  The current match's own stats are NEVER folded into its
own feature.  This DEEPENS the substrate / calibration; NO market edge is claimed.

PURE pandas/numpy.  NO src.* / kernel.* / domains.nba.* imports (falsifier F5).

PRIVATE: lives under data/domains/soccer/ which is never tracked.
football-data.co.uk data is free for personal/research use only.
"""
from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.soccer.config import DATA_DIR_REL

_REPO_ROOT = Path(__file__).resolve().parents[2]
ROLL_N = 10  # last-N window for the rolling (recency) form variant

# Output column contract (parquet column order).
ASOF_COLS: Tuple[str, ...] = (
    "event_id",
    # home team prior-only expanding form
    "home_sot_for_asof", "home_sot_against_asof",
    "home_shots_for_asof", "home_shots_against_asof",
    # away team prior-only expanding form
    "away_sot_for_asof", "away_sot_against_asof",
    "away_shots_for_asof", "away_shots_against_asof",
    # home-minus-away diffs of the 4 expanding stats
    "diff_sot_for_asof", "diff_sot_against_asof",
    "diff_shots_for_asof", "diff_shots_against_asof",
    # last-N rolling SoT-for variant
    "home_sot_for_l10", "away_sot_for_l10",
    # also expose the prior-only SoT ratio (free xG-quality proxy)
    "home_sot_ratio_for_asof", "away_sot_ratio_for_asof",
    # history depth (NaN features when 0)
    "home_n_prior", "away_n_prior",
)


class _TeamHistory:
    """Running prior-match aggregates for one team (home or away appearances).

    Holds expanding sums (for the expanding mean) plus a bounded deque of the
    last-N SoT-for values (for the rolling mean).  ``snapshot()`` reads the
    PRE-match state; ``update(...)`` folds a settled match in afterwards.
    """

    __slots__ = ("n", "sum_shots_for", "sum_shots_against",
                 "sum_sot_for", "sum_sot_against",
                 "sum_sot_ratio_for", "n_ratio", "sot_for_window")

    def __init__(self) -> None:
        self.n = 0
        self.sum_shots_for = 0.0
        self.sum_shots_against = 0.0
        self.sum_sot_for = 0.0
        self.sum_sot_against = 0.0
        self.sum_sot_ratio_for = 0.0
        self.n_ratio = 0  # ratio only counts matches with a defined ratio
        self.sot_for_window: Deque[float] = deque(maxlen=ROLL_N)

    def snapshot(self) -> Dict[str, float]:
        """Return prior-only means; all-NaN when this team has no prior match."""
        if self.n == 0:
            nan = float("nan")
            return {
                "sot_for": nan, "sot_against": nan,
                "shots_for": nan, "shots_against": nan,
                "sot_ratio_for": nan, "sot_for_l10": nan, "n_prior": 0,
            }
        inv = 1.0 / self.n
        ratio = (self.sum_sot_ratio_for / self.n_ratio
                 if self.n_ratio > 0 else float("nan"))
        win = self.sot_for_window
        l10 = (sum(win) / len(win)) if win else float("nan")
        return {
            "sot_for": self.sum_sot_for * inv,
            "sot_against": self.sum_sot_against * inv,
            "shots_for": self.sum_shots_for * inv,
            "shots_against": self.sum_shots_against * inv,
            "sot_ratio_for": ratio,
            "sot_for_l10": l10,
            "n_prior": self.n,
        }

    def update(self, shots_for: float, shots_against: float,
               sot_for: float, sot_against: float) -> None:
        """Fold a settled match in.  Non-finite stats are treated as 0 for the
        expanding sums but a row still counts toward ``n`` ONLY when at least the
        core shot/SoT facts are finite; fully-NaN rows are skipped entirely so
        they neither inflate counts nor poison later means."""
        vals = (shots_for, shots_against, sot_for, sot_against)
        if not all(np.isfinite(v) for v in vals):
            return  # skip un-gradeable rows (keeps later snapshots clean)
        self.n += 1
        self.sum_shots_for += shots_for
        self.sum_shots_against += shots_against
        self.sum_sot_for += sot_for
        self.sum_sot_against += sot_against
        self.sot_for_window.append(sot_for)
        if shots_for != 0.0:
            self.sum_sot_ratio_for += sot_for / shots_for
            self.n_ratio += 1


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by the pinned (date, div, home_team, away_team) chronological order.

    Mergesort-stable so same-day ties keep their original relative order — the
    SAME ordering rule used by domains.soccer.ratings, guaranteeing a single,
    deterministic walk-forward sequence.
    """
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


def build_asof_features(
    match_stats: Optional[pd.DataFrame] = None,
    out_path: Optional[str] = None,
) -> Path:
    """Build the leak-free AS-OF rolling shot-quality feature parquet.

    Parameters
    ----------
    match_stats:
        The W59 sidecar contract DataFrame (event_id, date, home_team,
        away_team, home_shots, away_shots, home_sot, away_sot).  If None, the
        default ``data/domains/soccer/match_stats.parquet`` is read.  Accepting a
        DataFrame lets tests drive synthetic corpora with no I/O.
    out_path:
        Output parquet path.  Defaults to
        ``data/domains/soccer/asof_features.parquet``.

    Returns
    -------
    Path
        The written parquet path.  Output is 1:1 with input rows, keyed by
        ``event_id``; every feature is NaN when that team's ``n_prior == 0``.
    """
    if match_stats is None:
        src = _REPO_ROOT / DATA_DIR_REL / "match_stats.parquet"
        match_stats = pq.read_table(src).to_pandas()
    out_file = (Path(out_path) if out_path
                else (_REPO_ROOT / DATA_DIR_REL / "asof_features.parquet"))
    out_file.parent.mkdir(parents=True, exist_ok=True)

    df = build_asof_frame(match_stats)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), out_file)
    return out_file


def build_asof_frame(match_stats: pd.DataFrame) -> pd.DataFrame:
    """Pure transform: sidecar contract DataFrame -> ASOF_COLS DataFrame.

    Walk-forward, snapshot-BEFORE-update.  Separated from I/O so the leak-free
    contract is unit-testable from fixtures.
    """
    if match_stats is None or len(match_stats) == 0:
        return pd.DataFrame(columns=list(ASOF_COLS))

    df = _sorted(match_stats)

    def _f(col: str) -> np.ndarray:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce").astype("float64").values
        return np.full(len(df), np.nan, dtype="float64")

    hs, as_ = _f("home_shots"), _f("away_shots")
    hst, ast = _f("home_sot"), _f("away_sot")
    home = df["home_team"].astype(str).values
    away = df["away_team"].astype(str).values
    event_id = df["event_id"].astype(str).values

    hist: Dict[str, _TeamHistory] = {}
    rows: List[Dict[str, object]] = []

    for i in range(len(df)):
        h, a = home[i], away[i]
        h_hist = hist.setdefault(h, _TeamHistory())
        a_hist = hist.setdefault(a, _TeamHistory())

        # ---- SNAPSHOT (strictly prior matches only) ----
        hs_ = h_hist.snapshot()
        as_snap = a_hist.snapshot()

        def _diff(x: float, y: float) -> float:
            return (x - y) if (np.isfinite(x) and np.isfinite(y)) else float("nan")

        rows.append({
            "event_id": event_id[i],
            "home_sot_for_asof": hs_["sot_for"],
            "home_sot_against_asof": hs_["sot_against"],
            "home_shots_for_asof": hs_["shots_for"],
            "home_shots_against_asof": hs_["shots_against"],
            "away_sot_for_asof": as_snap["sot_for"],
            "away_sot_against_asof": as_snap["sot_against"],
            "away_shots_for_asof": as_snap["shots_for"],
            "away_shots_against_asof": as_snap["shots_against"],
            "diff_sot_for_asof": _diff(hs_["sot_for"], as_snap["sot_for"]),
            "diff_sot_against_asof": _diff(hs_["sot_against"], as_snap["sot_against"]),
            "diff_shots_for_asof": _diff(hs_["shots_for"], as_snap["shots_for"]),
            "diff_shots_against_asof": _diff(hs_["shots_against"], as_snap["shots_against"]),
            "home_sot_for_l10": hs_["sot_for_l10"],
            "away_sot_for_l10": as_snap["sot_for_l10"],
            "home_sot_ratio_for_asof": hs_["sot_ratio_for"],
            "away_sot_ratio_for_asof": as_snap["sot_ratio_for"],
            "home_n_prior": hs_["n_prior"],
            "away_n_prior": as_snap["n_prior"],
        })

        # ---- UPDATE (post-match; never seen by this match's own snapshot) ----
        # home team: shots_for=home shots, against=away shots (and SoT likewise)
        h_hist.update(hs[i], as_[i], hst[i], ast[i])
        # away team: its "for" stats are the AWAY columns, "against" the HOME
        a_hist.update(as_[i], hs[i], ast[i], hst[i])

    out = pd.DataFrame(rows, columns=list(ASOF_COLS))
    out["home_n_prior"] = out["home_n_prior"].astype("int64")
    out["away_n_prior"] = out["away_n_prior"].astype("int64")
    return out


def main() -> None:
    """CLI: build the feature sidecar, print rows + a sample + coverage."""
    parser = argparse.ArgumentParser(
        description="leak-free AS-OF rolling shot-quality form for soccer")
    parser.add_argument("--out-path", default=None)
    args = parser.parse_args()
    out_file = build_asof_features(out_path=args.out_path)
    df = pq.read_table(out_file).to_pandas()
    print(f"asof_features: wrote {len(df)} rows -> {out_file}")
    sample_cols = ["event_id", "home_sot_for_asof", "away_sot_for_asof",
                   "diff_sot_for_asof", "home_n_prior", "away_n_prior"]
    print(df[sample_cols].head(5).to_string(index=False))
    have = (df["home_n_prior"] > 0) & (df["away_n_prior"] > 0)
    cov = (have.mean() * 100.0) if len(df) else 0.0
    print(f"coverage (both teams have prior history): {have.sum()}/{len(df)} "
          f"= {cov:.1f}%")


if __name__ == "__main__":
    main()

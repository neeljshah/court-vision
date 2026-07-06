"""domains.mlb.asof_inning -- leak-free walk-forward AS-OF inning-scoring-shape.

ONDISK_RECLAIM_TARGETS.md row #8: sbro raw CSVs (``data/domains/mlb/_raw/sbro/
mlb-odds-*.csv``) carry a per-team, per-inning run line (``1st``..``9th``) that is
discarded at ``ingest_sbro`` (only ``Final`` survives into games.parquet/odds.parquet).
This builder reclaims the EARLY (innings 1-3) vs LATE (innings 7-9) scoring split as
a leak-free PRIOR-ONLY trailing team rate -- "early scoring shape" / bullpen-exposure
proxy (a team that scores late more than early may face weaker relief more often).

LEAK CONTRACT: reuses ``scripts.platformkit.asof_common.walk_forward_asof`` --
snapshot BEFORE update, mirroring ``domains.mlb.asof_features`` / ``asof_sp_form``.
Each event's early/late run counts for the CURRENT game are folded into that team's
running history only AFTER that game's as-of value has already been recorded, so a
team never sees its own game's result.  Same-game own-row exclusion is enforced by
the shared primitive's snapshot-then-update ordering (see assert_no_future_leak).

Row pairing + event_id mirror ``domains.mlb.ingest_sbro`` exactly (V/H strict pairs,
``{date:%Y%m%d}-{HOME}-{AWAY}-{seq}``) so this joins 1:1 onto the SAME games.parquet
corpus A (2010-2021) with zero new join risk.

Output: ``data/domains/mlb/asof_inning.parquet`` (atomic write via tmp+replace),
columns: event_id, home/away_early_rate_asof, home/away_late_rate_asof,
early_rate_diff_asof, late_rate_diff_asof, home/away_innings_n_prior.

PURE pandas/numpy.  No src.*/kernel.*/api.* imports.  ACCURACY ONLY -- NO EDGE CLAIM.

CLI:  python -m domains.mlb.asof_inning
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.config import RAW_DIR_REL, YEARS
from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EARLY_COLS = ("1st", "2nd", "3rd")
_LATE_COLS = ("7th", "8th", "9th")
OUT_PATH_DEFAULT = _REPO_ROOT / "data/domains/mlb/asof_inning.parquet"

OUT_COLS = (
    "event_id",
    "home_early_rate_asof", "away_early_rate_asof", "early_rate_diff_asof",
    "home_late_rate_asof", "away_late_rate_asof", "late_rate_diff_asof",
    "home_innings_n_prior", "away_innings_n_prior",
)


# --------------------------------------------------------------------------- #
# Raw row-pairing (mirrors ingest_sbro._iter_pairs / _eid exactly)
# --------------------------------------------------------------------------- #

def _parse_date(mmdd: int, season: int) -> dt.date:
    mm, dd = mmdd // 100, mmdd % 100
    if not (3 <= mm <= 11):
        raise ValueError(f"month {mm} outside [3,11]")
    return dt.date(season, mm, dd)


def _eid(date: dt.date, home: str, away: str, seq: int) -> str:
    return f"{date:%Y%m%d}-{home.upper()}-{away.upper()}-{seq}"


def _innings_sum(row: pd.Series, cols: Tuple[str, ...]) -> float:
    """Sum inning cells; 'x' (team didn't bat, e.g. walk-off) counts as 0 runs."""
    total = 0.0
    saw_numeric = False
    for c in cols:
        v = row.get(c)
        if isinstance(v, str) and v.strip().lower() == "x":
            continue
        try:
            total += float(v)
            saw_numeric = True
        except (TypeError, ValueError):
            continue
    return total if saw_numeric else float("nan")


def _iter_pairs(raw: pd.DataFrame) -> Iterator[Tuple[pd.Series, pd.Series, bool]]:
    """Yield (v_row, h_row, valid) -- identical contract to ingest_sbro._iter_pairs."""
    arr = raw.reset_index(drop=True)
    for i in range(len(arr) // 2):
        r0, r1 = arr.iloc[2 * i], arr.iloc[2 * i + 1]
        ok = (str(r0["VH"]).strip().upper() == "V"
              and str(r1["VH"]).strip().upper() == "H"
              and r0["Date"] == r1["Date"]
              and int(r1["Rot"]) == int(r0["Rot"]) + 1)
        yield r0, r1, ok


def build_events_frame(frames: Optional[List[Tuple[int, pd.DataFrame]]] = None) -> pd.DataFrame:
    """Read sbro raw CSVs -> one row per game with early/late run sums per side.

    ``frames`` accepts an in-memory ``[(season, raw_df), ...]`` list (tests pass tiny
    synthetic frames); default reads every cached CSV under ``RAW_DIR_REL``.
    Columns: event_id, date, home_team, away_team, home_early, away_early,
    home_late, away_late (all leak-free RAW per-game observations -- the caller
    walk-forwards them into a strictly-prior trailing rate; this frame itself is
    NOT yet leak-free, it is the per-game input to walk_forward_asof).
    """
    if frames is None:
        raw_root = _REPO_ROOT / RAW_DIR_REL
        frames = []
        for y in YEARS:
            fp = raw_root / f"mlb-odds-{y}.csv"
            if fp.exists():
                frames.append((y, pd.read_csv(str(fp), low_memory=False)))

    rows: List[dict] = []
    for season, raw in frames:
        seq: dict = {}
        for vr, hr, ok in _iter_pairs(raw):
            if not ok:
                continue
            try:
                gd = _parse_date(int(vr["Date"]), season)
            except (ValueError, TypeError):
                continue
            home = str(hr["Team"]).strip().upper()
            away = str(vr["Team"]).strip().upper()
            seq[(gd, home, away)] = seq.get((gd, home, away), 0) + 1
            s = seq[(gd, home, away)]
            rows.append({
                "event_id": _eid(gd, home, away, s), "date": pd.Timestamp(gd),
                "home_team": home, "away_team": away,
                "home_early": _innings_sum(hr, _EARLY_COLS),
                "away_early": _innings_sum(vr, _EARLY_COLS),
                "home_late": _innings_sum(hr, _LATE_COLS),
                "away_late": _innings_sum(vr, _LATE_COLS),
            })
    if not rows:
        return pd.DataFrame(columns=["event_id", "date", "home_team", "away_team",
                                      "home_early", "away_early", "home_late", "away_late"])
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Walk-forward AS-OF (leak-free, snapshot-before-update via shared primitive)
# --------------------------------------------------------------------------- #

def build_asof_inning(events: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Leak-free trailing early/late run-rate per team, diffed home-away.

    Two independent walk-forward passes (early, late) keyed by team name -- a team's
    history is shared across its home and away appearances (mirrors asof_features).
    """
    ev = events if events is not None else build_events_frame()
    if len(ev) == 0:
        return pd.DataFrame(columns=list(OUT_COLS))

    early = walk_forward_asof(
        ev,
        AsofSpec(sort_keys=("date", "home_team", "away_team", "event_id"),
                 slots=(("home_team", "home_early", "home_early"),
                        ("away_team", "away_early", "away_early"))),
        lambda: ExpandingMean(min_prior=0),
    )
    late = walk_forward_asof(
        ev,
        AsofSpec(sort_keys=("date", "home_team", "away_team", "event_id"),
                 slots=(("home_team", "home_late", "home_late"),
                        ("away_team", "away_late", "away_late"))),
        lambda: ExpandingMean(min_prior=0),
    )

    out = early.merge(late, on="event_id", how="inner", suffixes=("", "_late_dup"))
    out = out.rename(columns={
        "home_early_asof": "home_early_rate_asof", "away_early_asof": "away_early_rate_asof",
        "home_late_asof": "home_late_rate_asof", "away_late_asof": "away_late_rate_asof",
        "home_early_n_prior": "home_innings_n_prior",
        "away_early_n_prior": "away_innings_n_prior",
    })
    out["early_rate_diff_asof"] = out["home_early_rate_asof"] - out["away_early_rate_asof"]
    out["late_rate_diff_asof"] = out["home_late_rate_asof"] - out["away_late_rate_asof"]
    return out[list(OUT_COLS)]


def _atomic_write_parquet(df: pd.DataFrame, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp))
    os.replace(str(tmp), str(out_path))
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Leak-free walk-forward AS-OF MLB inning shape -> parquet")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out_path = Path(args.out) if args.out else OUT_PATH_DEFAULT

    ev = build_events_frame()
    df = build_asof_inning(ev)
    _atomic_write_parquet(df, out_path)

    n = len(df)
    both = int(((df["home_innings_n_prior"] > 0) & (df["away_innings_n_prior"] > 0)).sum()) if n else 0
    dmin = ev["date"].min() if n else None
    dmax = ev["date"].max() if n else None
    print(f"wrote {out_path}")
    print(f"{n} rows | both-teams-have-prior {both / n * 100.0:.1f}%" if n else "0 rows")
    print(f"date coverage: {dmin} .. {dmax}")
    if n:
        print(df.head(5).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

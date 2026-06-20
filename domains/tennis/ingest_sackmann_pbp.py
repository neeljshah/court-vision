"""domains.tennis.ingest_sackmann_pbp -- Grand Slam POINT-BY-POINT acquirer + parser.

Source: github.com/JeffSackmann/tennis_slam_pointbypoint (CC BY-NC-SA, keyless).
Files per slam-year: ``<year>-<slam>-points.csv`` and ``<year>-<slam>-matches.csv``.

This is the GENUINELY-NEW tennis signal class (true point-by-point), distinct from
the set-level data (ingest_setdetail_states / tennis_setdetail_gate -> already
REJECTED) and the match-level Sackmann ATP/WTA (ingest_sackmann.py).

LICENSE NOTE: CC BY-NC-SA -- private research use only. Outputs under data/cache/
are gitignored; nothing derived goes to the public repo.

NETWORK POLICY: fetch_pbp() downloads + caches to data/cache/sackmann_pbp/_raw/
with a polite per-file delay; build_points()/build_matches()/aggregate_match_pbp()
are PURE transforms that read only local fixtures/cache. Tests call ONLY the
transforms with fixtures -- never the network. Import is side-effect-free.

LEAK CONTRACT: this module produces ONE row of point-derived stats per (match,
player) describing THAT match's own points. It is the raw observation. The as-of
trailing rates (strictly-prior, shift1/prior-N) are built downstream by
asof_pbp.py via the hardened walk_forward_asof primitive -- a match NEVER sees its
own points as a feature; the match result is the LABEL only.

PURE pandas/numpy + stdlib urllib. ASCII only. CALIBRATION only -- NO $ EDGE.
"""
from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_BASE = "https://raw.githubusercontent.com/JeffSackmann/tennis_slam_pointbypoint/master"
_UA = "tennis-pbp-ingest/1.0 (private research; github.com/JeffSackmann)"
_TIMEOUT = 40
_POLITENESS = 1.0
_MAX_RETRIES = 3

CACHE_DIR = Path("data/cache/sackmann_pbp")
RAW_DIR = CACHE_DIR / "_raw"

# Columns the Sackmann *-points.csv exposes that we depend on. We READ defensively:
# missing optional columns degrade a derived stat to NaN, never to a fabricated 0.
_POINT_COLS_CORE = ["match_id", "PointNumber", "PointWinner", "PointServer"]
_POINT_COLS_OPT = [
    "SetNo", "GameNo", "P1GamesWon", "P2GamesWon", "P1Score", "P2Score",
    "P1BreakPoint", "P2BreakPoint", "P1BreakPointWon", "P2BreakPointWon",
    "P1BreakPointMissed", "ServeNumber", "RallyCount", "P1Ace", "P2Ace",
    "GamePoint", "SetPoint", "BreakPoint",
]

# Per (match, player) aggregate stat columns this module emits. These are the NEW
# point-resolution signal candidates; each is a within-match RATE (0..1) or count.
AGG_STAT_COLS = [
    "bp_save_pct",        # break points saved while serving (pressure: defend)
    "bp_convert_pct",     # break points converted while returning (pressure: attack)
    "pressure_win_pct",   # win% on deuce/BP/GP/SP points (clutch)
    "serve1_win_pct",     # serve+1: win% when ServeNumber==1 (first-serve pts won)
    "short_rally_win_pct",  # win% on rallies <=4 strokes (serve+1 tendency proxy)
    "long_rally_win_pct",   # win% on rallies >=5 strokes (grind tendency)
    "decider_pts_win_pct",  # win% on deciding-set points (best_of dependent)
]
AGG_COUNT_COLS = ["pts_played", "serve_pts", "return_pts", "pressure_pts", "decider_pts"]


# --------------------------------------------------------------------------- #
# Network (BOUNDED + polite). Never called by tests.
# --------------------------------------------------------------------------- #
def _fetch_one(name: str, dest: Path) -> bool:
    """Download one CSV by basename into dest. Returns True on success (cached or new)."""
    if dest.exists() and dest.stat().st_size > 0:
        return True
    url = f"{_BASE}/{name}"
    last: Optional[Exception] = None
    for attempt in range(_MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            time.sleep(_POLITENESS)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False  # honest: file simply does not exist
            last = exc
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(_POLITENESS * (attempt + 1))
    if last is not None:
        print(f"[pbp] FAILED {name}: {type(last).__name__} {last}")
    return False


def fetch_pbp(year: int, slam: str) -> dict:
    """Bounded acquire one slam-year's points + matches CSVs. Returns status dict.

    slam in {ausopen, frenchopen, wimbledon, usopen}. NETWORK -- not for tests.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pts_name = f"{year}-{slam}-points.csv"
    mts_name = f"{year}-{slam}-matches.csv"
    ok_pts = _fetch_one(pts_name, RAW_DIR / pts_name)
    ok_mts = _fetch_one(mts_name, RAW_DIR / mts_name)
    return {"year": year, "slam": slam, "points_ok": ok_pts, "matches_ok": ok_mts,
            "points_path": str(RAW_DIR / pts_name), "matches_path": str(RAW_DIR / mts_name)}


# --------------------------------------------------------------------------- #
# Pure transforms (fixtures + cache only). These ARE what tests exercise.
# --------------------------------------------------------------------------- #
def build_points(path: "str | Path | pd.DataFrame") -> pd.DataFrame:
    """Load + normalise a *-points.csv. Keeps core + any present optional columns.

    Accepts a path/buffer OR an already-loaded DataFrame (the latter keeps the pure
    transform testable from in-memory fixtures without a temp file).
    """
    df = path.copy() if isinstance(path, pd.DataFrame) else pd.read_csv(path)
    for c in _POINT_COLS_CORE:
        if c not in df.columns:
            raise ValueError(f"points file missing required column {c!r}")
    keep = _POINT_COLS_CORE + [c for c in _POINT_COLS_OPT if c in df.columns]
    out = df[keep].copy()
    out["PointWinner"] = pd.to_numeric(out["PointWinner"], errors="coerce")
    out["PointServer"] = pd.to_numeric(out["PointServer"], errors="coerce")
    return out


def build_matches(path: str | Path) -> pd.DataFrame:
    """Load a *-matches.csv. Carries match_id + player names + round (for chrono key)."""
    df = pd.read_csv(path)
    if "match_id" not in df.columns:
        raise ValueError("matches file missing match_id")
    return df


def _safe_rate(num: float, den: float) -> float:
    return float(num) / float(den) if den > 0 else float("nan")


def _is_pressure(row: pd.Series) -> bool:
    for flag in ("BreakPoint", "GamePoint", "SetPoint"):
        v = row.get(flag)
        if pd.notna(v) and float(v) == 1:
            return True
    # deuce: both scores >= 40 / "AD"
    s1, s2 = row.get("P1Score"), row.get("P2Score")
    if isinstance(s1, str) and isinstance(s2, str):
        big = {"40", "AD"}
        if s1 in big and s2 in big:
            return True
    return False


def aggregate_match_pbp(points: pd.DataFrame, best_of: int = 5) -> pd.DataFrame:
    """Collapse one match's points into ONE row PER PLAYER (player in {1,2}).

    Output columns: match_id, player (1|2) + AGG_STAT_COLS + AGG_COUNT_COLS.
    Every rate is computed ONLY from points within this match (raw observation);
    leak-free trailing rates are built downstream. Missing optional inputs ->
    the dependent stat is NaN (never 0-filled).
    """
    rows = []
    has_rally = "RallyCount" in points.columns
    has_servenum = "ServeNumber" in points.columns
    has_setno = "SetNo" in points.columns
    decider_set = best_of // 2 + 1  # 3 for bo5, 2 for bo3

    pw = points["PointWinner"]
    sv = points["PointServer"]
    pressure_mask = points.apply(_is_pressure, axis=1) if len(points) else pd.Series([], dtype=bool)

    for player in (1, 2):
        opp = 2 if player == 1 else 1
        served = sv == player
        returned = sv == opp
        won = pw == player

        serve_pts = int(served.sum())
        return_pts = int(returned.sum())
        pts_played = int(((sv == 1) | (sv == 2)).sum())

        # break-point save: serving + opponent has BP -> won the point
        bp_face = served & (
            (points.get("P1BreakPoint" if opp == 1 else "P2BreakPoint", pd.Series(0, index=points.index)) == 1)
            | (points.get("BreakPoint", pd.Series(0, index=points.index)) == 1) & served
        ) if ("P1BreakPoint" in points.columns or "BreakPoint" in points.columns) else pd.Series(False, index=points.index)
        bp_save = _safe_rate((bp_face & won).sum(), bp_face.sum())

        # break-point convert: returning + you have BP -> won the point
        bp_chance = returned & (
            (points.get("P1BreakPoint" if player == 1 else "P2BreakPoint", pd.Series(0, index=points.index)) == 1)
            | (points.get("BreakPoint", pd.Series(0, index=points.index)) == 1) & returned
        ) if ("P1BreakPoint" in points.columns or "BreakPoint" in points.columns) else pd.Series(False, index=points.index)
        bp_conv = _safe_rate((bp_chance & won).sum(), bp_chance.sum())

        # pressure: deuce/BP/GP/SP points the player participated in
        part = (sv == 1) | (sv == 2)
        pres = pressure_mask & part
        pressure_win = _safe_rate((pres & won).sum(), pres.sum())

        # serve+1: first-serve points won while serving
        if has_servenum:
            s1 = served & (points["ServeNumber"] == 1)
            serve1_win = _safe_rate((s1 & won).sum(), s1.sum())
        else:
            serve1_win = float("nan")

        # rally length tendencies
        if has_rally:
            rc = pd.to_numeric(points["RallyCount"], errors="coerce")
            short = part & (rc <= 4)
            long_ = part & (rc >= 5)
            short_win = _safe_rate((short & won).sum(), short.sum())
            long_win = _safe_rate((long_ & won).sum(), long_.sum())
        else:
            short_win = long_win = float("nan")

        # deciding set
        if has_setno:
            dec = part & (pd.to_numeric(points["SetNo"], errors="coerce") == decider_set)
            decider_win = _safe_rate((dec & won).sum(), dec.sum())
            decider_pts = int(dec.sum())
        else:
            decider_win = float("nan")
            decider_pts = 0

        rows.append({
            "match_id": points["match_id"].iloc[0] if len(points) else None,
            "player": player,
            "bp_save_pct": bp_save,
            "bp_convert_pct": bp_conv,
            "pressure_win_pct": pressure_win,
            "serve1_win_pct": serve1_win,
            "short_rally_win_pct": short_win,
            "long_rally_win_pct": long_win,
            "decider_pts_win_pct": decider_win,
            "pts_played": pts_played,
            "serve_pts": serve_pts,
            "return_pts": return_pts,
            "pressure_pts": int(pres.sum()),
            "decider_pts": decider_pts,
        })
    return pd.DataFrame(rows)


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def _cli() -> None:
    ap = argparse.ArgumentParser(description="Bounded-acquire Sackmann Grand Slam point-by-point.")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--slam", required=True,
                    choices=["ausopen", "frenchopen", "wimbledon", "usopen"])
    args = ap.parse_args()
    st = fetch_pbp(args.year, args.slam)
    print(st)
    if not st["points_ok"]:
        print("[pbp] points file unreachable -- TIER3_BLOCKED for this corpus")
        return
    pts = build_points(st["points_path"])
    best_of = 5  # Grand Slam men bo5; women bo3 -> overridden per-match downstream if matches has it
    agg = (pts.groupby("match_id", group_keys=False)
              .apply(lambda g: aggregate_match_pbp(g, best_of=best_of)))
    out = CACHE_DIR / f"{args.year}-{args.slam}-pbp_agg.parquet"
    write_parquet(agg.reset_index(drop=True), out)
    print(f"[pbp] wrote {len(agg)} player-match rows -> {out}")


if __name__ == "__main__":
    _cli()

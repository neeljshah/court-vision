"""domains.basketball_nba.box_integrity_scan -- read-only integrity scan over
espn_boxscores.parquet (live) and any backfill sibling (e.g.
espn_boxscores_2024_25.parquet). NEVER writes to either parquet -- flags only,
to a separate quarantine artifact under data/domains/basketball_nba/.

FOUND BY (incidental, this scan): event 0022400230 (BOS-TOR 2024-11-16) is
stored as 114-114 -- an impossible NBA final (no ties in regulation+OT). This
module generalizes that single catch into a repeatable 3-criteria scan:
  (a) home_score == away_score (any status -- a tie is never valid)
  (b) STATUS_FINAL row with a score <50 or >200 (sanity band, not a rule --
      NBA finals essentially never fall outside it)
  (c) box-detail sanity: any home_*/away_* stat column negative, or a
      points-subset column (fast_break_pts/paint_pts/tov_pts) exceeding that
      side's own total score

CROSS-CHECK: for each flagged row, re-fetch ESPN fresh (1 req/s, reusing
ingest_espn_box.fetch_scoreboard/fetch_box verbatim -- same endpoints/parser
already proven by backfill_box_espn) and classify:
  - "our-capture-corrupted": ESPN's current data no longer matches what we
    stored -> our capture was stale/broken, forward-fix is safe.
  - "source-was-wrong": ESPN's current data still matches what we stored ->
    the anomaly is upstream, not our capture.
  - "unresolved": no matching ESPN event found for that date/matchup.
This distinction only decides where a FUTURE forward-fix belongs; it never
mutates data/ itself. ponytail: iterrows over ~3k rows is plenty fast for a
one-off scan; no need to vectorize.

CLI:  python -m domains.basketball_nba.box_integrity_scan [--crosscheck]
Test: python -m pytest domains/basketball_nba/test_box_integrity_scan.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from domains.basketball_nba.backfill_box_espn import _rate_limited_getter
from domains.basketball_nba.ingest_espn_box import fetch_box, fetch_scoreboard

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data" / "domains" / "basketball_nba"
DEFAULT_SOURCES = {
    "live": _DATA_DIR / "espn_boxscores.parquet",
    "backfill_2024_25": _DATA_DIR / "espn_boxscores_2024_25.parquet",
}
DEFAULT_OUT = _DATA_DIR / "box_integrity_quarantine.json"

_META_COLS = {
    "event_id", "date", "home_abbr", "away_abbr", "home_score", "away_score",
    "status", "venue", "attendance",
}
_PTS_SUBSET_SUFFIXES = ("fast_break_pts", "paint_pts", "tov_pts")
_SCORE_LO, _SCORE_HI = 50, 200


def _box_detail_cols(df: pd.DataFrame) -> List[str]:
    """home_*/away_* stat columns (excludes score/meta), numeric only."""
    return [
        c for c in df.columns
        if c not in _META_COLS
        and (c.startswith("home_") or c.startswith("away_"))
        and pd.api.types.is_numeric_dtype(df[c])
    ]


def scan_integrity(df: pd.DataFrame, source: str) -> List[Dict[str, Any]]:
    """Pure, no I/O. Returns one dict per flagged row with reasons[]."""
    flags: List[Dict[str, Any]] = []
    detail_cols = _box_detail_cols(df)
    for _, r in df.iterrows():
        status = r.get("status")
        if status == "STATUS_POSTPONED":
            continue  # not-yet-played placeholder row (0-0 is expected, not a tie)
        reasons: List[str] = []
        hs, as_ = r.get("home_score"), r.get("away_score")
        if pd.notna(hs) and pd.notna(as_) and float(hs) == float(as_):
            reasons.append("tied_score")
        if status == "STATUS_FINAL" and pd.notna(hs) and pd.notna(as_):
            if not (_SCORE_LO <= float(hs) <= _SCORE_HI) or not (_SCORE_LO <= float(as_) <= _SCORE_HI):
                reasons.append("score_out_of_range")
        for c in detail_cols:
            v = r.get(c)
            if pd.isna(v):
                continue
            v = float(v)
            if v < 0:
                reasons.append(f"negative:{c}")
                continue
            if c.endswith(_PTS_SUBSET_SUFFIXES):
                side = "home" if c.startswith("home_") else "away"
                total = r.get(f"{side}_score")
                if pd.notna(total) and v > float(total):
                    reasons.append(f"exceeds_total:{c}")
        if reasons:
            flags.append({
                "source": source,
                "event_id": str(r.get("event_id")),
                "date": str(r.get("date")),
                "home_abbr": r.get("home_abbr"), "away_abbr": r.get("away_abbr"),
                "home_score": None if pd.isna(hs) else float(hs),
                "away_score": None if pd.isna(as_) else float(as_),
                "status": None if pd.isna(status) else str(status),
                "reasons": reasons,
            })
    return flags


def scan_sources(sources: Optional[Dict[str, Path]] = None) -> List[Dict[str, Any]]:
    """Read-only scan over every configured parquet. A missing file is
    skipped (never an error -- backfill parquets come and go)."""
    src = sources or DEFAULT_SOURCES
    flags: List[Dict[str, Any]] = []
    for name, path in src.items():
        p = Path(path)
        if not p.exists():
            continue
        df = pd.read_parquet(p)
        flags.extend(scan_integrity(df, name))
    return flags


def _yyyymmdd(date_val: Any) -> Optional[str]:
    try:
        return pd.Timestamp(date_val).strftime("%Y%m%d")
    except (TypeError, ValueError):
        return None


def crosscheck_espn(flags: List[Dict[str, Any]], sleep_s: float = 1.0,
                     http_get: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Re-fetch ESPN fresh for each flagged event and classify. Rate-limited
    (reuses backfill_box_espn._rate_limited_getter, default 1 req/s).
    Scoreboard responses are cached per-date so a shared date across flags
    doesn't repeat the scoreboard call."""
    getter = http_get or _rate_limited_getter(sleep_s)
    scoreboard_cache: Dict[str, List[dict]] = {}
    out: List[Dict[str, Any]] = []
    for f in flags:
        date_str = _yyyymmdd(f.get("date"))
        classification = "unresolved"
        fresh: Optional[dict] = None
        if date_str is not None:
            events = scoreboard_cache.get(date_str)
            if events is None:
                events = fetch_scoreboard(date_str, http_get=getter)
                scoreboard_cache[date_str] = events
            for ev in events:
                row = fetch_box(ev["event_id"], http_get=getter)
                if row and row.get("home_abbr") == f.get("home_abbr") \
                        and row.get("away_abbr") == f.get("away_abbr"):
                    fresh = row
                    break
            if fresh is not None:
                same = (fresh.get("home_score") == f.get("home_score")
                        and fresh.get("away_score") == f.get("away_score"))
                classification = "source-was-wrong" if same else "our-capture-corrupted"
        out.append({**f, "espn_fresh_home_score": None if fresh is None else fresh.get("home_score"),
                    "espn_fresh_away_score": None if fresh is None else fresh.get("away_score"),
                    "espn_fresh_status": None if fresh is None else fresh.get("status"),
                    "classification": classification})
    return out


def write_quarantine(flags: List[Dict[str, Any]], out_path: Optional[Path] = None) -> Path:
    dest = Path(out_path) if out_path is not None else DEFAULT_OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"flagged": flags, "count": len(flags)}, indent=2), encoding="utf-8")
    return dest


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Scan espn_boxscores parquets for corrupted rows.")
    ap.add_argument("--crosscheck", action="store_true", help="re-fetch ESPN fresh (network, 1 req/s)")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    flags = scan_sources()
    print(f"Flagged {len(flags)} row(s) across {len(DEFAULT_SOURCES)} source(s).")
    if args.crosscheck and flags:
        flags = crosscheck_espn(flags, sleep_s=args.sleep)
        by_class: Dict[str, int] = {}
        for f in flags:
            by_class[f["classification"]] = by_class.get(f["classification"], 0) + 1
        print(f"Classification: {by_class}")
    dest = write_quarantine(flags, out_path=Path(args.out) if args.out else None)
    print(f"Wrote quarantine artifact: {dest}")
    print("Descriptive only; NEVER touches the source parquets; no $ claim.")


if __name__ == "__main__":
    _main()

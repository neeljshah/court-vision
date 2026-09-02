"""domains.basketball_wnba.ingest_linescores -- WNBA per-checkpoint linescore corpus.

LANE 4 step 1: extend the on-the-fly linescore fetch that
run_ingame_blend_check.py used inline (fetch_linescores_for_date, reading
competitor.linescores straight off the ESPN scoreboard payload -- confirmed
live 2026-07-03, no per-event summary call needed) into a small standalone
ingest that PERSISTS one row per completed game to
data/domains/wnba/linescores.parquet, with cumulative scores at end-Q1 / half
/ end-Q3 plus the final outcome. This turns the check script's "re-fetch every
run" cost into a one-time backfill + incremental top-up, and gives candidate
family fitting (ingame_blend_families.py) a stable, reusable corpus instead of
recomputing on-the-fly for every fit/validate/test split.

SCHEMA (one row per completed event with 4 clean regulation-period linescores):
  event_id, date, season, home_team, away_team,
  home_q1..home_q4, away_q1..away_q4 (raw per-period points),
  home_end_q1, away_end_q1, home_half, away_half, home_end_q3, away_end_q3
    (cumulative through that checkpoint),
  home_score, away_score (final), home_win (1.0/0.0).

An event without exactly 4 parseable numeric regulation-period linescores on
BOTH sides is skipped entirely (never zero-filled or interpolated) -- same
honest-skip contract as run_ingame_blend_check.fetch_linescores_for_date.
OT-period linescores (index >=4 in the ESPN list) are ignored here: only the
4 regulation-period checkpoints are needed for this family study, and this
module's home_score/away_score are read from the scoreboard's own final
`score` field (which DOES include OT), not summed from linescores, so OT
games are not miscounted.

Network isolation: http_get is injectable; no network at import time.
PRIVATE: data/domains/wnba/ is never tracked; no src.*/kernel.* imports (F5).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingest_linescores.py -q
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from domains.basketball_wnba.ingest_espn import (
    _default_http_get,
    _SCOREBOARD_URL,
    season_calendar,
)
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "wnba" / "linescores.parquet"

LINESCORE_COLS: tuple = (
    "event_id", "date", "season", "home_team", "away_team",
    "home_q1", "home_q2", "home_q3", "home_q4",
    "away_q1", "away_q2", "away_q3", "away_q4",
    "home_end_q1", "away_end_q1", "home_half", "away_half",
    "home_end_q3", "away_end_q3",
    "home_score", "away_score", "home_win",
)


def _parse_event_linescores(ev: dict, date: str, season: str) -> dict:
    """One ESPN scoreboard event -> a flat linescore-checkpoint row, or {} if the
    event lacks a clean 4-period regulation linescore on both sides, an unusable
    (non-completed / malformed) status, or a parseable final score.

    PURE -- no I/O. Mirrors ingest_espn._parse_event's honest-skip discipline:
    a partial event is dropped, never faked/interpolated.
    """
    comps = ev.get("competitions") or []
    if not comps:
        return {}
    comp = comps[0]
    status = comp.get("status") or {}
    typ = status.get("type") or {}
    if not bool(typ.get("completed")):
        return {}

    eid = str(ev.get("id") or "")
    if not eid:
        return {}

    linescores: Dict[str, List[float]] = {}
    finals: Dict[str, float] = {}
    names: Dict[str, str] = {}
    for c in comp.get("competitors") or []:
        side = c.get("homeAway")
        if side not in ("home", "away"):
            continue
        names[side] = ((c.get("team") or {}).get("displayName") or "").strip()
        try:
            finals[side] = float(c.get("score"))
        except (TypeError, ValueError):
            return {}
        ls = c.get("linescores") or []
        vals: List[float] = []
        for x in ls[:4]:
            try:
                vals.append(float(x.get("value")))
            except (TypeError, ValueError):
                return {}
        if len(vals) != 4 or any(math.isnan(v) for v in vals):
            return {}
        linescores[side] = vals

    if "home" not in linescores or "away" not in linescores:
        return {}
    if not names.get("home") or not names.get("away"):
        return {}

    hq, aq = linescores["home"], linescores["away"]
    home_score, away_score = finals["home"], finals["away"]
    row = {
        "event_id": eid, "date": date, "season": season,
        "home_team": names["home"], "away_team": names["away"],
        "home_q1": hq[0], "home_q2": hq[1], "home_q3": hq[2], "home_q4": hq[3],
        "away_q1": aq[0], "away_q2": aq[1], "away_q3": aq[2], "away_q4": aq[3],
        "home_end_q1": hq[0], "away_end_q1": aq[0],
        "home_half": hq[0] + hq[1], "away_half": aq[0] + aq[1],
        "home_end_q3": hq[0] + hq[1] + hq[2], "away_end_q3": aq[0] + aq[1] + aq[2],
        "home_score": home_score, "away_score": away_score,
        "home_win": 1.0 if home_score > away_score else (
            0.0 if home_score < away_score else float("nan")),
    }
    return row


def fetch_day_linescores(date: str, season: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Parsed linescore-checkpoint rows for every COMPLETED, clean-4-period event
    on *date* (YYYYMMDD). Same honest-skip contract as ingest_espn.fetch_day."""
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(date=date))
    rows: List[dict] = []
    for ev in payload.get("events") or []:
        row = _parse_event_linescores(ev, date, season)
        if row:
            rows.append(row)
    return rows


def ingest_season_linescores(
    year: str,
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
    dates_override: Optional[Sequence[str]] = None,
) -> Path:
    """Backfill one WNBA *year* season's linescore corpus via the calendar index,
    then per-date scoreboard fetch, merged/deduped into the parquet at out_path.

    Same two-call (calendar + per-date) pattern as ingest_espn.ingest_season;
    *dates_override* lets a test inject dates directly and skip the calendar call.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    dates = list(dates_override) if dates_override is not None else season_calendar(year, http_get=getter)
    rows: List[dict] = []
    for date in dates:
        got = fetch_day_linescores(date, year, http_get=getter)
        log.info("linescores season=%s date=%s rows=%d", year, date, len(got))
        rows.extend(got)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(LINESCORE_COLS))
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (pd.concat([existing, new_df], ignore_index=True)
                      .drop_duplicates(subset=["event_id"], keep="last"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out) from exc

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df = new_df.sort_values(["date", "event_id"], kind="mergesort").reset_index(drop=True)
        write_parquet_atomic(new_df, out)
    log.info("Wrote %d linescore rows to %s", len(new_df), out)
    return out


def ingest_seasons_linescores(
    years: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Backfill multiple seasons' linescores into the SAME parquet (dedup on
    event_id across the whole call)."""
    out = Path(out_path) if out_path else _DEFAULT_OUT
    for year in years:
        ingest_season_linescores(year, http_get=http_get, out_path=out)
    return out


def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Ingest ESPN WNBA per-checkpoint linescores.")
    parser.add_argument("--years", nargs="+", default=["2024", "2025", "2026"])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dest = ingest_seasons_linescores(args.years, out_path=args.out)
    df = pd.read_parquet(dest)
    print(f"Done: {dest} -- {len(df)} total rows across seasons {sorted(df['season'].unique().tolist())}")
    for s in sorted(df["season"].unique().tolist()):
        n = int((df["season"] == s).sum())
        print(f"  season={s}: {n} games")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "fetch_day_linescores", "ingest_season_linescores", "ingest_seasons_linescores",
    "LINESCORE_COLS", "_DEFAULT_OUT",
]

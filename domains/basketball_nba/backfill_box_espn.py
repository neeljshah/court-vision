"""domains.basketball_nba.backfill_box_espn -- resumable ESPN box-detail
backfill for past NBA seasons.

CONTEXT: espn_boxscores.parquet's box-detail cols (fast_break_pts, paint_pts,
tov_pts) are non-null only from 2026-01-20 (when the live capture in
ingest_espn_box started) even though ESPN's site.api summary endpoint DOES
carry these fields for old games -- spot-checked 2024-11-01 BOS@CHA
(event 401704698): home_fast_break_pts=6.0, away_paint_pts=56.0,
home_tov_pts=24.0, all populated. Not blocked -- just never fetched for
history. This backfills historical seasons into a SEPARATE parquet, never
touching the live espn_boxscores.parquet, reusing ingest_espn_box's
fetch/parse code VERBATIM (fetch_scoreboard, fetch_box -- same endpoints,
same parser, same column schema).

Politeness: 1 req/s, sleep BEFORE every call (mirrors backfill_pbp_espn.py's
_get_json). Resumable: a JSON checkpoint of done dates next to the output
parquet; chunked write after every date so a killed run loses <=1 day of
work, not the whole season.

Per-file test: python -m pytest domains/basketball_nba/test_backfill_box_espn.py -q
CLI: python -m domains.basketball_nba.backfill_box_espn --season 2024-25
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Callable, List, Optional, Set

import pandas as pd

from domains.basketball_nba.ingest_espn_box import (
    _default_http_get, fetch_box, fetch_scoreboard,
)
from scripts.platformkit.ops.safe_parquet_write import write_parquet_atomic

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_DATA_DIR = _REPO_ROOT / "data" / "domains" / "basketball_nba"


def _season_dates(season: str, games_parquet: Path = _GAMES_PARQUET) -> List[str]:
    """All distinct game dates for *season* from games.parquet, as YYYYMMDD."""
    g = pd.read_parquet(games_parquet)
    d = pd.to_datetime(g.loc[g["season"] == season, "date"])
    return sorted({x.strftime("%Y%m%d") for x in d})


def _state_path(out_path: Path) -> Path:
    return out_path.with_name(out_path.stem + "_state.json")


def _load_done(state_path: Path) -> Set[str]:
    if state_path.exists():
        try:
            return set(json.loads(state_path.read_text(encoding="utf-8")).get("done_dates", []))
        except Exception:  # noqa: BLE001 -- corrupt state must not abort a resume
            return set()
    return set()


def _save_done(state_path: Path, done: Set[str]) -> None:
    state_path.write_text(json.dumps({"done_dates": sorted(done)}), encoding="utf-8")


def _rate_limited_getter(sleep_s: float) -> Callable[[str], dict]:
    """Wrap ingest_espn_box's own http_get with a fixed pre-call sleep (politeness)."""
    def _get(url: str) -> dict:
        time.sleep(sleep_s)
        return _default_http_get(url)
    return _get


def _append_rows(out_path: Path, rows: List[dict]) -> None:
    """Merge *rows* into out_path parquet, dedup on event_id (keep last).
    Same merge convention as ingest_espn_box.ingest_range."""
    if not rows:
        return
    new_df = pd.DataFrame(rows)
    if "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out_path.exists():
        try:
            existing = pd.read_parquet(out_path)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = pd.concat([existing, new_df], ignore_index=True).drop_duplicates(
                subset=["event_id"], keep="last"
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("S95: unreadable existing parquet %s" % out_path) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(new_df, out_path)


def backfill(season: str, out_path: Path, sleep_s: float = 1.0, limit: int = 0,
             http_get: Optional[Callable] = None,
             games_parquet: Path = _GAMES_PARQUET) -> dict:
    """Resumable box-detail backfill for *season* -> *out_path* (a SEPARATE
    parquet -- never the live espn_boxscores.parquet). Chunked write +
    checkpoint after every date so a killed run resumes cleanly. Returns a
    counters dict; never raises per-game (mirrors ingest_espn_box)."""
    getter = http_get or _rate_limited_getter(sleep_s)
    state_path = _state_path(out_path)
    done = _load_done(state_path)
    dates = _season_dates(season, games_parquet=games_parquet)
    if limit > 0:
        dates = dates[:limit]
    todo = [d for d in dates if d not in done]
    log.info("season=%s dates=%d done=%d todo=%d", season, len(dates), len(done), len(todo))

    c = {"dates_done": 0, "games_written": 0, "games_empty": 0}
    for date in todo:
        events = fetch_scoreboard(date, http_get=getter)
        rows = []
        for ev in events:
            row = fetch_box(ev["event_id"], http_get=getter)
            if row:
                row["date"] = date
                rows.append(row)
                c["games_written"] += 1
            else:
                c["games_empty"] += 1
                log.debug("event_id=%s date=%s: empty parse", ev["event_id"], date)
        _append_rows(out_path, rows)
        done.add(date)
        _save_done(state_path, done)
        c["dates_done"] += 1
        log.info("date=%s events=%d written=%d [%d/%d dates]", date, len(events), len(rows),
                  c["dates_done"], len(todo))
    log.info("DONE %s", c)
    return c


def _main() -> None:
    ap = argparse.ArgumentParser(description="Resumable ESPN box-detail backfill (separate parquet).")
    ap.add_argument("--season", default="2024-25")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0, help="max dates this run (0 = all missing)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = Path(args.out) if args.out else _DATA_DIR / f"espn_boxscores_{args.season.replace('-', '_')}.parquet"
    c = backfill(args.season, out, sleep_s=args.sleep, limit=args.limit)
    print(f"RESULT {c}")


if __name__ == "__main__":
    _main()

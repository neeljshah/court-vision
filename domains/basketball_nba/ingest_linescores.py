"""domains.basketball_nba.ingest_linescores — per-quarter NBA scores (the in-game unlock).

In-game is the real edge (conditioning on realized state beats the static line), but NBA had
NO leak-free in-game reconstruction on disk. ESPN's summary endpoint DOES expose per-quarter
linescores (header.competitions[].competitors[].linescores) — this ingests them so we can
reconstruct mid-game states (cumulative score after Q1/Q2/Q3) and validate/sharpen the NBA
in-game repricer, exactly like the MLB per-inning work.

Output parquet (one row per game): event_id, date, home_abbr, away_abbr,
  home_q1..home_q4, away_q1..away_q4 (regulation; OT folded into q4 to keep regulation clean).

INVARIANTS: never edit src/ or kernel/; reuse the ESPN fetchers; pure stdlib/pandas; <=300 LOC.
HONEST: descriptive realized data; the model input is the AS-OF reconstruction, never the future.
CLI: python -m domains.basketball_nba.ingest_linescores --start 20260120 --end 20260524
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

from domains.basketball_nba.ingest_espn_box import _default_http_get, fetch_scoreboard

log = logging.getLogger(__name__)
_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "data" / "domains" / "basketball_nba" / "linescores.parquet"
_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={eid}"


def fetch_linescores(event_id: str, http_get: Optional[Callable] = None) -> Dict:
    """Parse per-quarter linescores for one game; {} on error/incomplete."""
    getter = http_get or _default_http_get
    try:
        data = getter(_SUMMARY.format(eid=event_id))
    except Exception as exc:  # noqa: BLE001
        log.debug("summary fetch failed eid=%s: %s", event_id, exc)
        return {}
    comps = data.get("header", {}).get("competitions", [])
    if not comps:
        return {}
    row: Dict[str, object] = {"event_id": str(event_id)}
    for t in comps[0].get("competitors", []):
        side = "home" if t.get("homeAway") == "home" else "away"
        abbr = (t.get("team", {}) or {}).get("abbreviation")
        ls = t.get("linescores") or []
        vals: List[float] = []
        for x in ls:
            v = x.get("displayValue", x.get("value"))
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                vals.append(float("nan"))
        if len(vals) < 4:
            return {}                       # need 4 regulation quarters
        row[f"{side}_abbr"] = abbr
        for q in range(4):
            row[f"{side}_q{q + 1}"] = vals[q]
        if len(vals) > 4:                   # fold OT into q4 so regulation stays comparable
            row[f"{side}_q4"] += sum(vals[4:])
    return row if {"home_abbr", "away_abbr"} <= set(row) else {}


def ingest_range(dates: Sequence[str], http_get: Optional[Callable] = None,
                 out_path: Optional[Path] = None) -> Path:
    out = Path(out_path) if out_path else _OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for date in dates:
        for ev in fetch_scoreboard(date, http_get=getter):
            r = fetch_linescores(ev["event_id"], http_get=getter)
            if r:
                r["date"] = date
                rows.append(r)
    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not new_df.empty:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (pd.concat([existing, new_df], ignore_index=True)
                      .drop_duplicates(subset=["event_id"], keep="last"))
        except Exception as exc:  # noqa: BLE001
            log.warning("merge failed %s: %s — overwriting", out, exc)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df.to_parquet(out, index=False)
    log.info("wrote %d linescore rows to %s", len(new_df), out)
    return out


def _daterange(start: str, end: str) -> List[str]:
    s, e = pd.to_datetime(start), pd.to_datetime(end)
    return [d.strftime("%Y%m%d") for d in pd.date_range(s, e, freq="D")]


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Ingest NBA per-quarter linescores from ESPN.")
    ap.add_argument("--start", default="20251021")
    ap.add_argument("--end", default="20260524")
    args = ap.parse_args(argv)
    out = ingest_range(_daterange(args.start, args.end))
    df = pd.read_parquet(out)
    print(f"linescores rows: {len(df)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

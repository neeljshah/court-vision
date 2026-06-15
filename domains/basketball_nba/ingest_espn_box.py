"""domains.basketball_nba.ingest_espn_box — ESPN free-API NBA team box-score ingestion.

KNOWLEDGE/SUBSTRATE ONLY — NOT a model-feed signal.
Realized post-game box stats; must be joined as-of before feeding any model.
Markets are efficient; this adds data depth, not edge.

Endpoints (free, no auth):
  scoreboard: https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD
  summary:    https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=<id>

NBA boxscore shape (differs from MLB):
  Each team's ``statistics`` list contains entries of the form
  ``{name, displayValue, label}`` — there is NO nested ``stats`` sub-list.
  - Simple stats (integers):  displayValue is a plain number string.
  - Compound stats (e.g. FG):  displayValue is "made-attempted" (e.g. "36-90").
  The parser handles both forms and stores NaN for any missing or unparseable field.

Network isolation: http_get is INJECTABLE; no network at import time.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date}"
)
_SUMMARY_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"

# ---------------------------------------------------------------------------
# Stat spec: (stat_name_in_api, output_column_suffix, is_compound)
#   is_compound=True  -> displayValue is "X-Y"; emits col_made + col_attempted
#   is_compound=False -> displayValue is a plain number; emits col directly
# ---------------------------------------------------------------------------
_STAT_SPECS: Tuple[Tuple[str, str, bool], ...] = (
    # --- shooting ---
    ("fieldGoalsMade-fieldGoalsAttempted",                 "fg",   True),
    ("fieldGoalPct",                                       "fg_pct", False),
    ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", "fg3", True),
    ("threePointFieldGoalPct",                             "fg3_pct", False),
    ("freeThrowsMade-freeThrowsAttempted",                 "ft",   True),
    ("freeThrowPct",                                       "ft_pct", False),
    # --- rebounding ---
    ("totalRebounds",                                      "reb",  False),
    ("offensiveRebounds",                                  "oreb", False),
    ("defensiveRebounds",                                  "dreb", False),
    # --- playmaking / defense ---
    ("assists",                                            "ast",  False),
    ("steals",                                             "stl",  False),
    ("blocks",                                             "blk",  False),
    # --- turnovers ---
    ("turnovers",                                          "tov",  False),
    ("teamTurnovers",                                      "team_tov", False),
    ("totalTurnovers",                                     "total_tov", False),
    # --- fouls ---
    ("fouls",                                              "pf",   False),
    ("technicalFouls",                                     "tech", False),
    ("flagrantFouls",                                      "flagrant", False),
    # --- other scoring context ---
    ("fastBreakPoints",                                    "fast_break_pts", False),
    ("pointsInPaint",                                      "paint_pts", False),
    ("turnoverPoints",                                     "tov_pts", False),
    ("largestLead",                                        "largest_lead", False),
)

# Build lookup: api stat name -> (col_suffix, is_compound)
_STAT_LOOKUP: Dict[str, Tuple[str, bool]] = {
    name: (col, compound) for name, col, compound in _STAT_SPECS
}

# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------

def _default_http_get(url: str) -> dict:
    """Fetch url via urllib; returns {} on any error."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("ESPN fetch failed url=%s err=%s", url, exc)
        return {}


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def _parse_compound(display: str) -> Tuple[Optional[float], Optional[float]]:
    """Parse 'X-Y' displayValue into (made, attempted). Returns (None, None) on error."""
    try:
        parts = display.split("-")
        if len(parts) == 2:
            return float(parts[0]), float(parts[1])
    except (TypeError, ValueError, AttributeError):
        pass
    return None, None


def _parse_float(display: str) -> Optional[float]:
    """Parse plain number displayValue. Returns None on error."""
    try:
        return float(str(display).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _parse_team_block(block: dict) -> Dict[str, Optional[float]]:
    """Parse one boxscore teams entry into a flat stat dict.

    Returns column names WITHOUT side prefix (caller adds home_/away_).
    Compound stats (FG/3P/FT) emit two columns: col_made, col_attempted.
    Simple stats emit one column: col.
    """
    # Build lookup from stat name -> displayValue
    stat_display: Dict[str, str] = {}
    for entry in block.get("statistics") or []:
        name = entry.get("name", "")
        dv = entry.get("displayValue", "")
        stat_display[name] = dv

    row: Dict[str, Optional[float]] = {}
    for api_name, (col, is_compound) in _STAT_LOOKUP.items():
        dv = stat_display.get(api_name)
        if is_compound:
            made, attempted = _parse_compound(dv or "")
            row[f"{col}_made"] = made
            row[f"{col}_attempted"] = attempted
        else:
            row[col] = _parse_float(dv or "")
    return row


def _parse_summary(payload: dict, event_id: str) -> dict:
    """Extract per-team box stats from an ESPN NBA summary payload.

    Returns flat dict: event_id, home/away_abbr, scores, status, venue,
    attendance, home/away_<stat>* columns.
    Returns {} on empty/missing/malformed payload. PURE — no I/O.
    """
    if not payload:
        return {}

    teams_raw = payload.get("boxscore", {}).get("teams")
    if not isinstance(teams_raw, list) or len(teams_raw) < 2:
        return {}

    team_data: Dict[str, dict] = {}
    team_meta: Dict[str, dict] = {}
    for block in teams_raw:
        side = block.get("homeAway", "")
        if side in ("home", "away"):
            team_data[side] = _parse_team_block(block)
            team_meta[side] = block.get("team", {})

    if "home" not in team_data or "away" not in team_data:
        return {}

    home_score: Optional[float] = None
    away_score: Optional[float] = None
    status_name = ""
    comps = (payload.get("header") or {}).get("competitions") or []
    if comps:
        comp = comps[0]
        for ct in comp.get("competitors") or []:
            try:
                score: Optional[float] = float(ct.get("score", ""))
            except (TypeError, ValueError):
                score = None
            if ct.get("homeAway") == "home":
                home_score = score
            elif ct.get("homeAway") == "away":
                away_score = score
        status_name = comp.get("status", {}).get("type", {}).get("name", "")

    gi = payload.get("gameInfo") or {}
    venue = (gi.get("venue") or {}).get("fullName", "")
    try:
        attendance: Optional[float] = float(gi.get("attendance") or "")
    except (TypeError, ValueError):
        attendance = None

    row: dict = {
        "event_id": str(event_id),
        "home_abbr": team_meta.get("home", {}).get("abbreviation", ""),
        "away_abbr": team_meta.get("away", {}).get("abbreviation", ""),
        "home_score": home_score,
        "away_score": away_score,
        "status": status_name,
        "venue": venue,
        "attendance": attendance,
    }
    for side in ("home", "away"):
        for k, v in team_data[side].items():
            row[f"{side}_{k}"] = v
    return row


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def fetch_scoreboard(date: str, http_get: Optional[Callable] = None) -> List[dict]:
    """Return [{event_id, date, name}] for YYYYMMDD date string."""
    getter = http_get or _default_http_get
    payload = getter(_SCOREBOARD_URL.format(date=date))
    return [
        {"event_id": str(ev["id"]), "date": date, "name": ev.get("name", "")}
        for ev in (payload.get("events") or [])
        if ev.get("id")
    ]


def fetch_box(event_id: str, http_get: Optional[Callable] = None) -> dict:
    """Fetch and parse box stats for a single ESPN event_id; returns {} on error."""
    getter = http_get or _default_http_get
    payload = getter(_SUMMARY_URL.format(event_id=event_id))
    return _parse_summary(payload, event_id)


# ---------------------------------------------------------------------------
# Ingest range — writes gitignored parquet
# ---------------------------------------------------------------------------

def ingest_range(
    dates: Sequence[str],
    http_get: Optional[Callable] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """Fetch ESPN box scores for *dates* (YYYYMMDD) and write/merge a parquet.

    One row per game; dedup on event_id (keep last).
    Descriptive/realized only — NOT a model input without as-of join.
    """
    out = Path(out_path) if out_path else _DEFAULT_OUT
    getter = http_get or _default_http_get
    rows: List[dict] = []
    for date in dates:
        events = fetch_scoreboard(date, http_get=getter)
        log.info("date=%s events=%d", date, len(events))
        for ev in events:
            eid = ev["event_id"]
            row = fetch_box(eid, http_get=getter)
            if row:
                row["date"] = date
                rows.append(row)
            else:
                log.debug("event_id=%s: empty parse (may be in-progress)", eid)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    # Normalise date to datetime64 so a merge with an existing (datetime-typed) parquet
    # does not produce a mixed str/datetime column that pyarrow refuses to write.
    if not new_df.empty and "date" in new_df.columns:
        new_df["date"] = pd.to_datetime(new_df["date"], format="mixed", errors="coerce")
    if out.exists() and not new_df.empty:
        try:
            existing = pd.read_parquet(out)
            if "date" in existing.columns:
                existing["date"] = pd.to_datetime(existing["date"], format="mixed", errors="coerce")
            new_df = (
                pd.concat([existing, new_df], ignore_index=True)
                .drop_duplicates(subset=["event_id"], keep="last")
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Could not read existing parquet %s: %s — overwriting", out, exc
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    if not new_df.empty:
        new_df.to_parquet(out, index=False)
    log.info("Wrote %d rows to %s", len(new_df), out)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Ingest ESPN NBA box scores.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, out_path=args.out)}")


if __name__ == "__main__":
    _main()

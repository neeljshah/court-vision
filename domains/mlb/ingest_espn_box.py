"""domains.mlb.ingest_espn_box — ESPN free-API MLB team box-score ingestion.

KNOWLEDGE/SUBSTRATE ONLY — NOT a model-feed signal.
Realized post-game box stats; must be joined as-of before feeding any model.
Markets are efficient; this adds data depth, not edge.

Endpoints (free, no auth):
  scoreboard: https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates=YYYYMMDD
  summary:    https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event=<id>

Network isolation: http_get is INJECTABLE; no network at import time.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0"
_TIMEOUT = 12
_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard?dates={date}"
_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event={event_id}"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "data" / "domains" / "mlb" / "espn_boxscores.parquet"

# Subset of ESPN's 59/76/35 sub-stats per category.
_BATTING_FIELDS = (
    "runs", "hits", "homeRuns", "doubles", "triples", "RBIs",
    "atBats", "plateAppearances", "walks", "strikeouts", "stolenBases",
    "caughtStealing", "hitByPitch", "sacFlies", "sacHits",
    "runnersLeftOnBase", "groundBalls", "flyBalls",
    "totalBases", "extraBaseHits", "pitches", "GIDPs",
)
_PITCHING_FIELDS = (
    "wins", "losses", "saves", "innings", "earnedRuns", "runs",
    "hits", "homeRuns", "walks", "strikeouts", "battersFaced",
    "pitches", "strikes", "wildPitches", "balks",
    "groundBalls", "flyBalls", "qualityStarts", "completeGames", "shutouts",
)
_FIELDING_FIELDS = (
    "errors", "putouts", "assists", "doublePlays", "passedBalls",
    "outfieldAssists", "triplePlays",
)
_GROUP_FIELDS = {"batting": _BATTING_FIELDS, "pitching": _PITCHING_FIELDS, "fielding": _FIELDING_FIELDS}
_GROUP_PREFIX = {"batting": "bat", "pitching": "pit", "fielding": "fld"}


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

def _extract_stat_group(stats_list: list, fields: Sequence[str]) -> Dict[str, Optional[float]]:
    """Convert ESPN stats list [{name, value, displayValue}] -> {name: float|None}."""
    lookup: Dict[str, Optional[float]] = {}
    for item in stats_list:
        name = item.get("name")
        if name not in fields:
            continue
        raw = item.get("value")
        if raw is None:
            try:
                raw = float(str(item.get("displayValue", "")).replace(",", ""))
            except (TypeError, ValueError):
                raw = None
        else:
            try:
                raw = float(raw)
            except (TypeError, ValueError):
                raw = None
        lookup[name] = raw
    return {f: lookup.get(f) for f in fields}


def _parse_team_block(block: dict) -> Dict[str, Optional[float]]:
    """Parse one boxscore teams entry into a flat stat dict."""
    row: Dict[str, Optional[float]] = {}
    for sg in block.get("statistics", []):
        gname = sg.get("name", "")
        if gname not in _GROUP_FIELDS:
            continue
        prefix = _GROUP_PREFIX[gname]
        for k, v in _extract_stat_group(sg.get("stats") or [], _GROUP_FIELDS[gname]).items():
            row[f"{prefix}_{k}"] = v
    return row


def _parse_summary(payload: dict, event_id: str) -> dict:
    """Extract per-team box stats from an ESPN summary payload.

    Returns flat dict: event_id, home/away_abbr, scores, status, venue,
    attendance, home/away bat_*/pit_*/fld_* stats.
    Returns {} on empty/missing payload. PURE — no I/O.
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
        "home_score": home_score, "away_score": away_score,
        "status": status_name, "venue": venue, "attendance": attendance,
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
            if not row:
                log.debug("event_id=%s: empty parse (may be in-progress)", eid)
                continue
            # DATA-INTEGRITY GATE: only persist a game whose ESPN status is FINAL.
            # An in-progress/suspended/postponed summary still carries a partial
            # boxscore + a live header score; appending it would pollute the
            # realized-box parquet (consumed as realized truth) until a later
            # final re-ingest. Skip until truly final. (ESPN type name e.g.
            # 'STATUS_FINAL'; covers STATUS_FINAL / *_FINAL_* variants ending FINAL.)
            if not str(row.get("status", "")).upper().endswith("FINAL"):
                log.debug("event_id=%s: status=%r not FINAL -- skipped",
                          eid, row.get("status"))
                continue
            row["date"] = date
            rows.append(row)

    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
    # Normalise date to datetime64 so appends merge cleanly with a datetime-typed parquet
    # (a mixed str/datetime column makes pyarrow refuse the write).
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
            log.warning("Could not read existing parquet %s: %s — overwriting", out, exc)

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
    parser = argparse.ArgumentParser(description="Ingest ESPN MLB box scores.")
    parser.add_argument("--dates", nargs="+", default=[dt.date.today().strftime("%Y%m%d")])
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"Done: {ingest_range(args.dates, out_path=args.out)}")


if __name__ == "__main__":
    _main()

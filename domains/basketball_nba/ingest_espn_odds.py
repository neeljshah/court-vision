"""
domains/basketball_nba/ingest_espn_odds.py
------------------------------------------
Ingest ESPN odds JSON files (data/cache/spreads/YYYYMMDD.json) and emit a
tidy parquet at data/domains/basketball_nba/odds.parquet.

Schema (EXACT):
    date       : str  (YYYY-MM-DD, from filename)
    home_team  : str  (canonical abbr)
    away_team  : str  (canonical abbr)
    home_ml    : float | None  (American moneyline)
    away_ml    : float | None
    total      : float | None  (over/under)
    spread     : float | None  (home spread)

Provider priority: "ESPN BET" > "DraftKings" (first non-Live non-empty entry).
Alias map: ESPN abbr -> canonical NBA abbr.
Graceful-skip: malformed events/files are silently dropped.
"""
from __future__ import annotations

import json
import pathlib
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SPREADS_DIR = pathlib.Path("data/cache/spreads")
_DEFAULT_OUT = pathlib.Path("data/domains/basketball_nba/odds.parquet")

# ESPN abbreviation -> canonical NBA abbreviation
_ALIAS: dict[str, str] = {
    "GS": "GSW",
    "NY": "NYK",
    "NO": "NOP",
    "SA": "SAS",
    "UTAH": "UTA",
    "WSH": "WAS",
}

# Provider name preference order (exact strings from ESPN API; Live lines excluded)
_PREFERRED_PROVIDERS = ["ESPN BET", "DraftKings"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical(abbr: str) -> str:
    """Apply ESPN→canonical alias map; pass through unknown abbreviations."""
    return _ALIAS.get(abbr, abbr)


def _pick_odds(odds_list: list) -> Optional[dict]:
    """
    Return the first odds entry matching a preferred provider (non-live).
    Preferred order: ESPN BET, then DraftKings.
    Live-line providers (name contains 'Live') are skipped.
    Returns None if no usable entry found.
    """
    by_provider: dict[str, dict] = {}
    for entry in odds_list:
        pname = entry.get("provider", {}).get("name", "")
        if "Live" in pname:
            continue
        for pref in _PREFERRED_PROVIDERS:
            if pname == pref and pref not in by_provider:
                by_provider[pref] = entry
    for pref in _PREFERRED_PROVIDERS:
        if pref in by_provider:
            return by_provider[pref]
    return None


def _parse_event(ev: dict, date_str: str) -> Optional[dict]:
    """
    Extract one row from a single ESPN event dict.
    Returns None if the event has no usable odds or is malformed.
    """
    try:
        comp = ev.get("competitions", [{}])[0]
        competitors = comp.get("competitors", [])
        teams: dict[str, str] = {}
        for c in competitors:
            side = c.get("homeAway", "")
            abbr = c.get("team", {}).get("abbreviation", "")
            if side in ("home", "away") and abbr:
                teams[side] = _canonical(abbr)
        if "home" not in teams or "away" not in teams:
            return None

        odds_list = comp.get("odds", [])
        if not odds_list:
            return None

        odds = _pick_odds(odds_list)
        if odds is None:
            return None

        home_team_odds = odds.get("homeTeamOdds", {}) or {}
        away_team_odds = odds.get("awayTeamOdds", {}) or {}

        home_ml = home_team_odds.get("moneyLine")
        away_ml = away_team_odds.get("moneyLine")
        total = odds.get("overUnder")
        spread = odds.get("spread")

        # Convert to float or None; reject non-numeric noise
        def _to_float(v) -> Optional[float]:
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return {
            "date": date_str,
            "home_team": teams["home"],
            "away_team": teams["away"],
            "home_ml": _to_float(home_ml),
            "away_ml": _to_float(away_ml),
            "total": _to_float(total),
            "spread": _to_float(spread),
        }
    except Exception:
        return None


def _date_from_filename(path: pathlib.Path) -> str:
    """Convert YYYYMMDD stem to YYYY-MM-DD."""
    s = path.stem  # e.g. "20251021"
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_odds(
    spreads_dir: pathlib.Path | str = _SPREADS_DIR,
    out_path: pathlib.Path | str | None = None,
) -> pathlib.Path:
    """
    Read all YYYYMMDD.json files in *spreads_dir* and write a parquet of
    extracted odds to *out_path* (default: data/domains/basketball_nba/odds.parquet).

    Returns the resolved output path.
    """
    spreads_dir = pathlib.Path(spreads_dir)
    if out_path is None:
        out_path = _DEFAULT_OUT
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for json_file in sorted(spreads_dir.glob("*.json")):
        date_str = _date_from_filename(json_file)
        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ev in raw.get("events", []):
            row = _parse_event(ev, date_str)
            if row is not None:
                rows.append(row)

    _COLS = ["date", "home_team", "away_team", "home_ml", "away_ml", "total", "spread"]

    if rows:
        df = pd.DataFrame(rows, columns=_COLS).sort_values("date").reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=_COLS)

    df.to_parquet(out_path, index=False)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    out = build_odds()
    df = pd.read_parquet(out)
    ml_coverage = df["home_ml"].notna().mean()
    print(f"Wrote {len(df):,} rows -> {out}")
    print(f"home_ml coverage: {ml_coverage:.1%}")
    if len(df):
        print("Sample row:")
        print(df.iloc[0].to_dict())
    sys.exit(0)

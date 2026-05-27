"""Build static player profile parquet from data/cache/playerinfo/*.json."""
from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "playerinfo"
OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "cache" / "player_profile_features.parquet"

D1_SCHOOLS: set[str] = {
    "Duke", "Kentucky", "North Carolina", "UCLA", "Kansas",
    "Michigan", "Michigan State", "Wake Forest", "Villanova", "Florida",
    "Arizona", "Indiana", "Connecticut", "Syracuse", "Gonzaga",
    "Texas", "USC", "Stanford", "Memphis", "Louisville",
    "Ohio State", "Maryland", "Georgetown", "Notre Dame", "Marquette",
    "Butler", "Baylor", "Tennessee", "Arkansas", "Iowa",
    "Missouri", "Oklahoma", "Texas A&M", "Georgia Tech", "Florida State",
    "Virginia", "Oregon", "Washington", "Nevada", "Utah",
    "UNLV", "Cincinnati", "Georgetown", "Providence", "Seton Hall",
    "St. John's", "DePaul", "Creighton", "Xavier", "Dayton",
    "UConn", "Wake Forest", "Purdue", "Illinois", "Minnesota",
}


def parse_height(raw: str) -> Optional[int]:
    """Convert '6-0' → 72 inches; return None on blank/malformed."""
    if not raw or not raw.strip():
        return None
    parts = raw.strip().split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) * 12 + int(parts[1])
    except (ValueError, TypeError):
        return None


def parse_weight(raw: str) -> Optional[int]:
    """Convert '175' → 175; return None on blank/malformed."""
    if not raw or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return None


def parse_birthdate(raw: str) -> Optional[date]:
    """Parse ISO datetime string to date; return None on failure."""
    if not raw or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.rstrip("Z")).date()
    except (ValueError, TypeError):
        return None


def parse_draft_int(raw: str) -> Optional[int]:
    """Return int for numeric strings, None for 'Undrafted' or empty."""
    if not raw or not raw.strip() or raw.strip().lower() == "undrafted":
        return None
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return None


def extract_row(info: dict, as_of: date) -> dict:
    """Extract and compute all features from a common_player_info dict."""
    birthdate = parse_birthdate(info.get("BIRTHDATE", ""))
    from_year = info.get("FROM_YEAR")
    school = info.get("SCHOOL", "") or ""
    country = info.get("COUNTRY", "") or ""
    draft_year_raw = info.get("DRAFT_YEAR", "") or ""
    undrafted = draft_year_raw.strip().lower() == "undrafted"

    age_precise_days = (as_of - birthdate).days if birthdate else None
    years_in_league = (as_of.year - from_year) if from_year else None

    season_exp_raw = info.get("SEASON_EXP")
    try:
        season_exp = int(season_exp_raw) if season_exp_raw is not None else None
    except (ValueError, TypeError):
        season_exp = None

    college_clean = school.strip() if school.strip() else None

    college_d1_flag: Optional[int]
    if not college_clean:
        college_d1_flag = None
    else:
        college_d1_flag = 1 if college_clean in D1_SCHOOLS else 0

    g75_raw = info.get("GREATEST_75_FLAG", "") or ""
    greatest_75 = 1 if g75_raw.strip().upper() == "Y" else 0

    to_year_raw = info.get("TO_YEAR")
    try:
        to_year = int(to_year_raw) if to_year_raw is not None else None
    except (ValueError, TypeError):
        to_year = None

    from_year_int: Optional[int]
    try:
        from_year_int = int(from_year) if from_year is not None else None
    except (ValueError, TypeError):
        from_year_int = None

    return {
        "player_id": int(info["PERSON_ID"]),
        "player_name": info.get("DISPLAY_FIRST_LAST", ""),
        "height_in": parse_height(info.get("HEIGHT", "")),
        "weight_lb": parse_weight(info.get("WEIGHT", "")),
        "birthdate": birthdate,
        "draft_year": parse_draft_int(draft_year_raw),
        "draft_round": parse_draft_int(str(info.get("DRAFT_ROUND", "") or "")),
        "draft_number": parse_draft_int(str(info.get("DRAFT_NUMBER", "") or "")),
        "undrafted_flag": 1 if undrafted else 0,
        "country": country if country.strip() else None,
        "intl_flag": 0 if country.strip().upper() == "USA" else 1,
        "college": college_clean,
        "college_d1_flag": college_d1_flag,
        "position": info.get("POSITION", "") or None,
        "from_year": from_year_int,
        "to_year": to_year,
        "season_exp": season_exp,
        "greatest_75_flag": greatest_75,
        "age_precise_days_as_of": age_precise_days,
        "years_in_league_as_of": years_in_league,
        "rookie_flag_as_of": 1 if (season_exp is not None and season_exp <= 1) else 0,
        "profile_as_of": as_of.isoformat(),
    }


def build(as_of: date) -> pd.DataFrame:
    """Iterate all JSON files and return a DataFrame of player profiles."""
    rows: list[dict] = []
    skipped: list[str] = []

    json_files = sorted(CACHE_DIR.glob("*.json"))
    log.info("Found %d JSON files in %s", len(json_files), CACHE_DIR)

    for fpath in json_files:
        try:
            with fpath.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            cpi_list = data.get("common_player_info", [])
            if not cpi_list:
                log.warning("No common_player_info in %s — skipping", fpath.name)
                skipped.append(str(fpath))
                continue
            row = extract_row(cpi_list[0], as_of)
            rows.append(row)
        except Exception as exc:
            log.warning("Malformed file %s (%s) — skipping", fpath.name, exc)
            skipped.append(str(fpath))

    if skipped:
        log.warning("Skipped %d file(s):", len(skipped))
        for s in skipped:
            log.warning("  %s", s)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["birthdate"] = pd.to_datetime(df["birthdate"]).dt.date
    int_nullable = [
        "height_in", "weight_lb", "draft_year", "draft_round", "draft_number",
        "from_year", "to_year", "season_exp", "age_precise_days_as_of",
        "years_in_league_as_of",
    ]
    for col in int_nullable:
        df[col] = pd.array(df[col], dtype=pd.Int64Dtype())

    return df


def report(df: pd.DataFrame) -> None:
    """Print rowcount, distinct player_id, and null rates."""
    print(f"\n{'='*55}")
    print(f"Rows           : {len(df):,}")
    print(f"Distinct IDs   : {df['player_id'].nunique():,}")
    print(f"\nNull rates per column:")
    null_rates = (df.isnull().sum() / len(df) * 100).sort_values(ascending=False)
    for col, rate in null_rates.items():
        print(f"  {col:<35s} {rate:5.1f}%")
    print("=" * 55)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build player profile parquet")
    parser.add_argument("--as-of", default=date.today().isoformat(),
                        help="Reference date YYYY-MM-DD (default: today UTC)")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    log.info("Building player profiles as_of %s", as_of)

    df = build(as_of)
    if df.empty:
        log.error("No rows built — aborting write.")
        return

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PATH, index=False, engine="pyarrow")
    log.info("Written %d rows → %s", len(df), OUT_PATH)

    report(df)


if __name__ == "__main__":
    main()

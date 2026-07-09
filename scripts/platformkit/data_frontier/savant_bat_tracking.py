"""scripts.platformkit.data_frontier.savant_bat_tracking -- Statcast bat-tracking +
catch-probability/OAA leaderboard CSVs (frontier census ranks 2 + 9, both
KEYLESS_CONFIRMED). 2024+ signal family, zero overlap with statcast_fuller
(2022-2023, pre-bat-tracking era).

Three leaderboard families, same baseballsavant.mlb.com/leaderboard/<family>?csv=true
endpoint shape (params probed live this session, see per-family PARAMS below):
  bat_tracking          -- avg_bat_speed, squared_up/blast rates, swords, whiffs
  outs_above_average    -- range/OAA defense (rank-9, "LIKELY_KEYLESS" -> confirmed here)
  catch_probability     -- 5/4/3/2/1-star catch-prob buckets, OAA cross-check

Output: data/cache/statcast/leaderboards/<family>_<year>.csv (raw, skip-if-cached)
        data/cache/statcast/leaderboards/<family>_consolidated.parquet (all cached
        years for that family, concatenated with a 'year' column)

CLI: python -m scripts.platformkit.data_frontier.savant_bat_tracking [--years 2024 2025 2026]
"""
from __future__ import annotations

import argparse
import io
import json
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from scripts.platformkit.data_frontier._politeness import atomic_write_bytes, log_line

_REPO = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO / "data" / "cache" / "statcast" / "leaderboards"
_LOG_FP = _REPO / "data" / "cache" / "logs" / "savant_leaderboards.log"
_HDR = {"User-Agent": "Mozilla/5.0 (research; bounded pull, data-frontier lane)"}
_DELAY_S = 1.5
_URL = "https://baseballsavant.mlb.com/leaderboard/{family}"

# family -> (url segment, params-by-year builder). Params confirmed 200/real-CSV
# via a live one-off probe this session (2026-07-09).
_FAMILIES: Dict[str, str] = {
    "bat_tracking": "bat-tracking",
    "outs_above_average": "outs_above_average",
    "catch_probability": "catch_probability",
}

# Families whose leaderboard endpoint IGNORES every season-like param we tried.
# Confirmed live 2026-07-09: bat-tracking with year=2021, year=2024, season=2024,
# years=2024 all returned byte-identical content (md5 6a899c03...). outs_above_average
# and catch_probability were NOT retested here -- their per-year files already differ
# on disk, so their startYear/endYear + year params are working as-is.
# These families are captured as dated snapshots instead of fake per-year files.
_SNAPSHOT_FAMILIES = {"bat_tracking"}


def _params(family: str, year: int) -> Dict[str, str]:
    if family == "bat_tracking":
        return {"type": "batter", "year": str(year), "minSwings": "0", "csv": "true"}
    if family == "outs_above_average":
        return {"type": "Fielder", "startYear": str(year), "endYear": str(year), "csv": "true"}
    if family == "catch_probability":
        return {"year": str(year), "csv": "true"}
    raise ValueError(f"unknown family {family}")


def fetch_one(family: str, year: int, fetcher=None, timeout: float = 30.0):
    get = fetcher or requests.get
    url = _URL.format(family=_FAMILIES[family])
    return get(url, params=_params(family, year), headers=_HDR, timeout=timeout)


def _pull_snapshot(family, years, fetcher, out_dir, log_path, delay_s, today, landed, skipped, failed):
    """family's endpoint ignores the season param -- capture ONE dated snapshot
    per as-of day instead of re-fetching one identical CSV per requested year."""
    snap_fp = out_dir / f"{family}_{today}.csv"
    if snap_fp.exists():
        skipped[family].append(today)
        return
    probe_year = max(years) if years else date.today().year
    r = fetch_one(family, probe_year, fetcher=fetcher)
    if r.status_code == 200 and len(r.content) > 50:
        atomic_write_bytes(snap_fp, r.content)
        atomic_write_bytes(out_dir / f"{family}_latest.csv", r.content)
        landed[family].append(today)
        log_line(log_path, f"OK {family} snapshot {today} bytes={len(r.content)}")
    else:
        failed[family].append(today)
        log_line(log_path, f"FAIL {family} snapshot {today} HTTP {getattr(r, 'status_code', '?')}")
    time.sleep(delay_s)


def pull(
    years: List[int],
    families: Optional[List[str]] = None,
    *,
    fetcher=None,
    out_dir: Path = _OUT_DIR,
    log_path: Path = _LOG_FP,
    delay_s: float = _DELAY_S,
    today: Optional[str] = None,
) -> Dict[str, object]:
    """Skip-if-cached per (family, year) CSV for year-keyed families; skip-if-
    captured-today for snapshot families; then rebuild each family's consolidated
    parquet from whatever CSVs exist on disk (not just this run's)."""
    families = families or list(_FAMILIES)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = today or date.today().isoformat()
    landed: Dict[str, List] = {f: [] for f in families}
    skipped: Dict[str, List] = {f: [] for f in families}
    failed: Dict[str, List] = {f: [] for f in families}

    for family in families:
        if family in _SNAPSHOT_FAMILIES:
            _pull_snapshot(family, years, fetcher, out_dir, log_path, delay_s, today,
                            landed, skipped, failed)
            continue
        for year in years:
            csv_fp = out_dir / f"{family}_{year}.csv"
            if csv_fp.exists():
                skipped[family].append(year)
                continue
            r = fetch_one(family, year, fetcher=fetcher)
            if r.status_code == 200 and len(r.content) > 50:
                atomic_write_bytes(csv_fp, r.content)
                landed[family].append(year)
                log_line(log_path, f"OK {family} {year} bytes={len(r.content)}")
            else:
                failed[family].append(year)
                log_line(log_path, f"FAIL {family} {year} HTTP {getattr(r, 'status_code', '?')}")
            time.sleep(delay_s)

    consolidated_rows: Dict[str, int] = {}
    for family in families:
        if family in _SNAPSHOT_FAMILIES:
            parts = []
            for csv_fp in sorted(out_dir.glob(f"{family}_????-??-??.csv")):
                as_of = csv_fp.stem[len(family) + 1:]  # strip "<family>_" prefix (family itself has underscores)
                try:
                    df = pd.read_csv(csv_fp, encoding="utf-8-sig")
                except Exception as exc:  # noqa: BLE001 -- honest skip, not a hard fail
                    log_line(log_path, f"PARSE_FAIL {family} {as_of} {exc}")
                    continue
                df["as_of"] = as_of
                parts.append(df)
            if parts:
                out = pd.concat(parts, ignore_index=True)
                out.to_parquet(out_dir / f"{family}_consolidated.parquet", index=False)
                consolidated_rows[family] = int(len(out))
            else:
                consolidated_rows[family] = 0
            continue
        parts = []
        for year in years:
            csv_fp = out_dir / f"{family}_{year}.csv"
            if not csv_fp.exists():
                continue
            try:
                df = pd.read_csv(csv_fp, encoding="utf-8-sig")
            except Exception as exc:  # noqa: BLE001 -- honest skip, not a hard fail
                log_line(log_path, f"PARSE_FAIL {family} {year} {exc}")
                continue
            df["year"] = year
            parts.append(df)
        if parts:
            out = pd.concat(parts, ignore_index=True)
            out.to_parquet(out_dir / f"{family}_consolidated.parquet", index=False)
            consolidated_rows[family] = int(len(out))
        else:
            consolidated_rows[family] = 0

    try:
        out_dir_str = str(out_dir.relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        out_dir_str = str(out_dir)  # out_dir outside REPO_ROOT (e.g. a test tmp_path)
    return {
        "years": years, "landed": landed, "skipped_already_cached": skipped,
        "failed": failed, "consolidated_rows": consolidated_rows,
        "out_dir": out_dir_str,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Statcast bat-tracking / OAA / catch-probability leaderboards.")
    ap.add_argument("--years", nargs="+", type=int, default=[2024, 2025, 2026])
    ap.add_argument("--families", nargs="+", default=None, choices=list(_FAMILIES))
    a = ap.parse_args(argv)
    res = pull(a.years, a.families)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


__all__ = ["fetch_one", "pull", "main", "_FAMILIES", "_params"]

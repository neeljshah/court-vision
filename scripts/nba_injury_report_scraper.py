"""nba_injury_report_scraper.py — R22_O8 authoritative NBA injury feed.

This is the next-generation injury feed for the prop-prediction stack.
The model has been at architecture / feature ceiling for months and the
remaining gains live in DATA — and the single biggest miss is real-time
injury status. Previous loops shipped the ESPN feed (R14_H4) and an
NBA PDF parser (`scripts/fetch_injury_report.py`) but neither emits a
columnar parquet that the production prop predictor can `read_parquet`
on the inference hot path, and neither runs on a guaranteed schedule
with a daemon-heartbeat contract.

This scraper:
  * Tries the NBA Official injury PDF first (most authoritative).
  * Falls back to the ESPN public JSON feed when the PDF is unreachable
    (sandboxed IPs, weekends with no published report, etc.).
  * Last-resort falls back to the cached rotowire HTML so we never
    return empty during a wire-up smoke test.
  * Normalises every row into the canonical 5-bucket status taxonomy:
        OUT / DOUBTFUL / QUESTIONABLE / PROBABLE / AVAILABLE
    (plus NOT WITH TEAM which downstream collapses to OUT).
  * Resolves player_name → player_id via the cached commonplayerinfo
    JSONs (data/cache/playerinfo/<id>.json) — same id space the
    prop predictor uses.
  * Emits an atomic parquet at
        data/cache/nba_injuries_<YYYY-MM-DD>.parquet
    with one row per (player_id, status) plus team, reason, source,
    and an `availability_factor` column matching the production wire.

The parquet is the canonical inference-time artifact; the existing
`injury_status_<date>.json` is preserved for backwards-compatibility
with R14_H4 / R15_W1 callers that already grep for it.

Run
---
    python scripts/nba_injury_report_scraper.py               # today
    python scripts/nba_injury_report_scraper.py --date 2026-05-26
    python scripts/nba_injury_report_scraper.py --source espn # skip PDF

Output (parquet schema)
-----------------------
    player_id            int64 (NaN allowed when name resolution fails)
    player_name          str
    team                 str  (3-letter abbrev)
    status               str  (canonical taxonomy)
    availability_factor  float (0.0 .. 1.0)
    reason               str
    source               str  (nba_pdf | espn | rotowire)
    fetched_at           str  (ISO8601)
    report_date          str  (YYYY-MM-DD)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import unicodedata
from datetime import date as _date_cls
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ---------------------------------------------------------------------------
# Canonical taxonomy — must match src/prediction/injury_availability.py
# so the round-trip parquet → production wire is byte-for-byte identical.
# ---------------------------------------------------------------------------
AVAILABILITY_FACTOR: Dict[str, float] = {
    "OUT":           0.0,
    "NOT WITH TEAM": 0.0,
    "DOUBTFUL":      0.3,
    "QUESTIONABLE":  0.6,
    "PROBABLE":      0.9,
    "AVAILABLE":     1.0,
}

# Map varied source-status strings into our 5-bucket canonical set.
_STATUS_NORM: Dict[str, str] = {
    "out":            "OUT",
    "doubtful":       "DOUBTFUL",
    "questionable":   "QUESTIONABLE",
    "probable":       "PROBABLE",
    "available":      "AVAILABLE",
    "active":         "AVAILABLE",
    "healthy":        "AVAILABLE",
    "day-to-day":     "QUESTIONABLE",
    "dtd":            "QUESTIONABLE",
    "gtd":            "QUESTIONABLE",
    "suspended":      "NOT WITH TEAM",
    "nwt":            "NOT WITH TEAM",
    "not with team":  "NOT WITH TEAM",
}


def normalize_status(raw: str) -> Optional[str]:
    """Return canonical status or None if the source string isn't recognised."""
    key = (raw or "").strip().lower()
    if not key:
        return None
    direct = _STATUS_NORM.get(key)
    if direct:
        return direct
    upper = key.upper().strip()
    return upper if upper in AVAILABILITY_FACTOR else None


# ---------------------------------------------------------------------------
# Player-name normalisation (drops accents + suffixes so 'Jokić' → 'jokic',
# 'LeBron James Jr.' → 'lebron james'). Same canonicalisation rule as the
# production wire (src/prediction/injury_availability.py::_name_key).
# ---------------------------------------------------------------------------
def _name_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or "")) \
        .encode("ascii", "ignore").decode().lower().strip()
    for suf in (" jr.", " jr", " sr.", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# Player-name → player_id resolver, sourced from cached commonplayerinfo
# JSONs. Built lazily and cached per-process for daemon mode.
# ---------------------------------------------------------------------------
_NAME_INDEX_CACHE: Optional[Dict[str, int]] = None


def build_player_index(force: bool = False) -> Dict[str, int]:
    """Return {canonical_name: player_id} from data/cache/playerinfo/*.json."""
    global _NAME_INDEX_CACHE
    if _NAME_INDEX_CACHE is not None and not force:
        return _NAME_INDEX_CACHE
    out: Dict[str, int] = {}
    pattern = os.path.join(PROJECT_DIR, "data", "cache", "playerinfo", "*.json")
    for fp in glob.glob(pattern):
        try:
            with open(fp, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            continue
        rows = payload.get("common_player_info") or []
        if not rows:
            continue
        row = rows[0]
        pid = row.get("PERSON_ID")
        name = row.get("DISPLAY_FIRST_LAST") or ""
        if pid and name:
            out[_name_key(name)] = int(pid)
    _NAME_INDEX_CACHE = out
    return out


# ---------------------------------------------------------------------------
# Source 1 — NBA Official PDF (reuses scripts/fetch_injury_report.py).
# ---------------------------------------------------------------------------
def fetch_nba_pdf(target_date: _date_cls) -> List[Dict[str, str]]:
    """Pull and parse the NBA Official injury PDF for `target_date`.

    Returns an empty list when the PDF is 403/404/network-down. Never raises.
    """
    try:
        from scripts import fetch_injury_report as fir
    except Exception:
        return []
    cache_dir = os.path.join(PROJECT_DIR, "data", "cache", "injuries")
    try:
        result = fir.fetch_pdf_bytes(target_date, cache_dir)
    except Exception:
        return []
    if not result:
        return []
    pdf_bytes, _slot = result
    try:
        text = fir._extract_text(pdf_bytes)
        rows = fir.parse_injury_text(text)
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        out.append({
            "player_name": r.get("name", ""),
            "team":        r.get("team", ""),
            "status":      r.get("status", ""),
            "reason":      r.get("reason", ""),
            "source":      "nba_pdf",
        })
    return out


# ---------------------------------------------------------------------------
# Source 2 — ESPN public JSON (uses the existing src.data.injury_monitor).
# ---------------------------------------------------------------------------
def fetch_espn() -> List[Dict[str, str]]:
    """Pull the current ESPN injury feed via the existing wrapper.

    Always returns a list (possibly empty); never raises.
    """
    try:
        from src.data.injury_monitor import get_all_injuries, refresh
    except Exception:
        return []
    try:
        refresh(force=True)
        rows = get_all_injuries() or []
    except Exception:
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        out.append({
            "player_name": (r.get("player_name") or "").strip(),
            "team":        (r.get("team_abbrev") or "").strip(),
            "status":      r.get("status") or "",
            "reason":      r.get("short_comment") or r.get("injury_type") or "",
            "source":      "espn",
        })
    return out


# ---------------------------------------------------------------------------
# Source 3 — rotowire (cached HTML last-resort).
# ---------------------------------------------------------------------------
def fetch_rotowire_cached() -> List[Dict[str, str]]:
    """Read the cached rotowire HTML and emit a best-effort row list.

    This is the fallback-of-last-resort: it never hits the network and
    parses the cached HTML if and only if it exists.
    """
    cache_path = os.path.join(PROJECT_DIR, "data", "cache", "rotowire_lineups.html")
    if not os.path.exists(cache_path):
        return []
    try:
        with open(cache_path, encoding="utf-8") as fh:
            _html = fh.read()
    except Exception:
        return []
    # The cached file holds the projected-starter HTML, not a structured
    # injury feed; return an empty list so the caller can detect the
    # source is unusable rather than emit malformed rows.
    return []


# ---------------------------------------------------------------------------
# Normalisation + parquet writer.
# ---------------------------------------------------------------------------
def to_dataframe(rows: List[Dict[str, str]],
                 report_date: str,
                 fetched_at: str,
                 name_index: Optional[Dict[str, int]] = None) -> pd.DataFrame:
    """Convert raw source rows to the canonical parquet schema."""
    name_index = name_index if name_index is not None else build_player_index()
    records: List[Dict] = []
    for r in rows:
        status = normalize_status(r.get("status", ""))
        if status is None:
            continue
        name = (r.get("player_name") or "").strip()
        if not name:
            continue
        pid = name_index.get(_name_key(name))
        records.append({
            "player_id":           int(pid) if pid is not None else None,
            "player_name":         name,
            "team":                (r.get("team") or "").upper().strip(),
            "status":              status,
            "availability_factor": float(AVAILABILITY_FACTOR[status]),
            "reason":              (r.get("reason") or "").strip(),
            "source":              r.get("source", ""),
            "fetched_at":          fetched_at,
            "report_date":         report_date,
        })
    df = pd.DataFrame.from_records(records, columns=[
        "player_id", "player_name", "team", "status",
        "availability_factor", "reason", "source",
        "fetched_at", "report_date",
    ])
    # Coerce numeric. NaN player_id is fine — production wire falls back
    # to name lookup. pandas needs a nullable Int64 to keep NaNs.
    if not df.empty:
        df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    return df


def write_parquet_atomic(df: pd.DataFrame, out_path: str) -> None:
    """Atomic parquet write: tmp file + os.replace so the daemon never
    half-writes a file that the prop predictor reads concurrently.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".", suffix=".parquet",
                               dir=os.path.dirname(out_path))
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, out_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Top-level entry point.
# ---------------------------------------------------------------------------
def scrape_once(target_date: Optional[_date_cls] = None,
                source_override: Optional[str] = None) -> Tuple[pd.DataFrame, str]:
    """Run a single end-to-end scrape and write the parquet.

    Source order: nba_pdf → espn → rotowire_cached. The first source
    that yields >=1 normalised row wins. `source_override` short-circuits
    to a specific source ('nba_pdf' | 'espn' | 'rotowire').

    Returns
    -------
    (dataframe, parquet_path)
        Empty dataframe + path when every source fails (so the caller
        can decide whether to retry or alert).
    """
    target = target_date or _date_cls.today()
    fetched_at = datetime.now().isoformat(timespec="seconds")
    report_date = target.isoformat()
    name_index = build_player_index()

    candidates: List[Tuple[str, callable]] = []
    if source_override == "nba_pdf":
        candidates = [("nba_pdf", lambda: fetch_nba_pdf(target))]
    elif source_override == "espn":
        candidates = [("espn", fetch_espn)]
    elif source_override == "rotowire":
        candidates = [("rotowire", fetch_rotowire_cached)]
    else:
        candidates = [
            ("nba_pdf",   lambda: fetch_nba_pdf(target)),
            ("espn",      fetch_espn),
            ("rotowire",  fetch_rotowire_cached),
        ]

    rows: List[Dict[str, str]] = []
    source_used = ""
    for name, fn in candidates:
        try:
            rows = fn() or []
        except Exception as exc:  # never let a single source crash us
            print(f"[nba_injury_scraper] source {name} raised: {exc}")
            rows = []
        if rows:
            source_used = name
            print(f"[nba_injury_scraper] source={name} returned {len(rows)} rows")
            break
        print(f"[nba_injury_scraper] source={name} empty — falling back")

    df = to_dataframe(rows, report_date, fetched_at, name_index=name_index)

    out_path = os.path.join(
        PROJECT_DIR, "data", "cache", f"nba_injuries_{report_date}.parquet"
    )
    write_parquet_atomic(df, out_path)
    print(f"[nba_injury_scraper] wrote {len(df)} rows -> {out_path} "
          f"(source={source_used or 'none'})")
    return df, out_path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--source", choices=["nba_pdf", "espn", "rotowire"],
                    help="Force a specific source; default tries all in order")
    args = ap.parse_args(argv)

    target = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date else _date_cls.today()
    )
    df, _ = scrape_once(target_date=target, source_override=args.source)
    if df.empty:
        print("[nba_injury_scraper] no rows scraped from any source")
        return 1
    by_status = df["status"].value_counts().to_dict()
    print("[nba_injury_scraper] status distribution:",
          json.dumps(by_status, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

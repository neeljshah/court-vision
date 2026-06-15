"""domains.soccer.ingest_footballdata — football-data.co.uk CSVs → matches.parquet + odds.parquet.

BUILD-SEPARABLE: ``fetch_raw`` downloads/caches CSVs (network-only, never called by tests);
``build_matches``, ``build_odds``, ``build_report`` are pure transforms (fixture-tested, no I/O).
PRIVATE: combined with price data these artefacts are price-bearing; data/domains/soccer/ is
never tracked.  football-data.co.uk data is free for personal/research use only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.soccer.config import (
    DATA_DIR_REL, LEAGUES, RAW_DIR_REL, URL_TEMPLATE, season_code,
)

_UA = "soccer-domain-ingest/1.0 (private research; football-data.co.uk)"
_TIMEOUT, _POLITENESS, _MAX_RETRIES = 30, 0.5, 3
_REPO_ROOT = Path(__file__).resolve().parents[2]
MATCHES_COLS: Tuple[str, ...] = (
    "event_id", "date", "season", "div", "home_team", "away_team",
    "fthg", "ftag", "total_goals", "target_over25", "ftr",
)
ODDS_COLS: Tuple[str, ...] = (
    "event_id", "div", "date",
    "ou_prematch_over", "ou_prematch_under", "ou_close_over", "ou_close_under",
    "book_prematch", "book_close",
    "p_over", "p_under", "pc_over", "pc_under",
    "avg_over", "avg_under", "avgc_over", "avgc_under",
    "b365_over", "b365_under", "b365c_over", "b365c_under",
    "max_over", "max_under", "maxc_over", "maxc_under",
)

FrameTuple = Tuple[str, int, pd.DataFrame]  # (div, season_start_year, raw_df)

def _slug(name: str) -> str:
    """Lowercase *name*, replace every non-alphanumeric character with ``_``."""
    return re.sub(r"[^a-z0-9]", "_", name.lower())

def _make_event_id(date: "dt.date | pd.Timestamp", div: str, home: str, away: str) -> str:
    """Deterministic pre-match event identifier."""
    if isinstance(date, pd.Timestamp):
        date = date.date()
    return f"{date:%Y%m%d}-{div}-{_slug(home)}-{_slug(away)}"

def _safe_float(series: pd.Series) -> pd.Series:
    """Coerce to float32; replace values <=1.0 (invalid decimal odds) with NaN."""
    f = pd.to_numeric(series, errors="coerce").astype("float32")
    return f.where(f > 1.0, other=np.nan)

def _best_price(
    df: pd.DataFrame,
    pin_over: str, pin_under: str,
    avg_over: str, avg_under: str,
    b365_over: str, b365_under: str,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Three-level fallback: Pinnacle > market_avg > bet365. Returns (over, under, book)."""
    def _get(col: str) -> pd.Series:
        return _safe_float(df.get(col, pd.Series(dtype="float32", index=df.index)))
    p_ov, p_un = _get(pin_over), _get(pin_under)
    a_ov, a_un = _get(avg_over), _get(avg_under)
    b_ov, b_un = _get(b365_over), _get(b365_under)
    ov = pd.Series(np.nan, index=df.index, dtype="float32")
    un = pd.Series(np.nan, index=df.index, dtype="float32")
    bk = pd.Series("none", index=df.index, dtype=object)
    for ok, o, u, label in [
        (b_ov.notna() & b_un.notna(), b_ov, b_un, "bet365"),
        (a_ov.notna() & a_un.notna(), a_ov, a_un, "market_avg"),
        (p_ov.notna() & p_un.notna(), p_ov, p_un, "pinnacle"),
    ]:
        ov = ov.where(~ok, o); un = un.where(~ok, u); bk = bk.where(~ok, label)
    return ov, un, bk

def _fetch_url(url: str, dest: Path, timeout: int = _TIMEOUT) -> dict:
    """Fetch *url* to *dest* with retries. HTTP 404 is RECORDED not raised."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    last_err: Exception = RuntimeError("no attempt made")
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            return {"url": url, "file": str(dest), "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "fetched_at": dt.datetime.utcnow().isoformat()}
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            last_err = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                return {"url": url, "file": str(dest), "status": "404",
                        "fetched_at": dt.datetime.utcnow().isoformat()}
            time.sleep(2 ** attempt)
    return {"url": url, "file": str(dest), "error": str(last_err),
            "fetched_at": dt.datetime.utcnow().isoformat()}


def fetch_raw(
    out_dir: Optional[str] = None,
    divs: Optional[List[str]] = None,
    start_years: Optional[List[int]] = None,
    force: bool = False,
    offline: bool = False,
) -> dict:
    """Download football-data.co.uk CSVs idempotently.

    ``offline=True`` → no-op (used by tests). Returns manifest dict keyed
    ``"{season_code}_{div}"``. 404 responses are recorded, not raised.
    """
    if offline:
        return {}
    raw_root = Path(out_dir) if out_dir else (_REPO_ROOT / RAW_DIR_REL)
    raw_root.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_root / "manifest.json"
    manifest: dict = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    if divs is None: divs = list(LEAGUES.keys())
    current_yr = dt.date.today().year
    if start_years is None: start_years = list(range(2000, current_yr + 1))
    entries: dict = {}
    for yr in start_years:
        sc = season_code(yr)
        for div in divs:
            key = f"{sc}_{div}"; url = URL_TEMPLATE.format(season=sc, div=div)
            dest = raw_root / f"{sc}_{div}.csv"
            if dest.exists() and dest.stat().st_size > 0 and not force and yr < current_yr - 1:
                entries[key] = {"url": url, "file": str(dest), "status": "cached"}; continue
            entries[key] = _fetch_url(url, dest); time.sleep(_POLITENESS)
    manifest.update(entries)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return entries


def build_matches(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """(div, season_start_year, raw_df) iterable → matches.parquet contract.

    Drops rows missing FTHG/FTAG (warns). target_over25=1 iff total_goals>=3.
    Sort: (date, div, home_team, away_team) mergesort.
    """
    parts: List[pd.DataFrame] = []
    for div, season_yr, raw in frames:
        df = raw.copy(); df["_div"] = str(div); df["_season"] = int(season_yr)
        df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=list(MATCHES_COLS))
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.dropna(subset=["date"]).copy()
    n_before = len(combined)
    combined = combined.dropna(subset=["FTHG", "FTAG"]).copy()
    if (n_dropped := n_before - len(combined)):
        import warnings; warnings.warn(
            f"build_matches: dropped {n_dropped} row(s) missing FTHG or FTAG.", stacklevel=2)
    combined["fthg"] = pd.to_numeric(combined["FTHG"], errors="coerce").astype("Int64")
    combined["ftag"] = pd.to_numeric(combined["FTAG"], errors="coerce").astype("Int64")
    combined = combined.dropna(subset=["fthg", "ftag"]).copy()
    combined["total_goals"] = (combined["fthg"] + combined["ftag"]).astype("Int64")
    combined["target_over25"] = (combined["total_goals"] >= 3).astype("int8")
    combined["ftr"] = combined.get("FTR", pd.Series(dtype=str, index=combined.index)).fillna("").astype(str)
    combined["home_team"] = combined["HomeTeam"].astype(str)
    combined["away_team"] = combined["AwayTeam"].astype(str)
    combined["div"] = combined["_div"].astype(str)
    combined["season"] = combined["_season"].astype(int)
    combined["event_id"] = combined.apply(
        lambda r: _make_event_id(r["date"], r["div"], r["home_team"], r["away_team"]), axis=1)
    return (combined[list(MATCHES_COLS)]
            .sort_values(["date", "div", "home_team", "away_team"], kind="mergesort")
            .reset_index(drop=True))


def build_odds(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """(div, season_start_year, raw_df) iterable → odds.parquet contract.

    DATA CONTRACT — column semantics (read before any CLV / line-movement work):
      * ``ou_prematch_*`` / ``book_prematch`` come from the football-data NON-C
        columns (P>2.5, Avg>2.5, B365>2.5). These are the scraped PRE-MATCH price
        (a near-close / latest weekly snapshot), NOT a true exchange OPENER.
      * ``ou_close_*`` / ``book_close`` come from the explicit *C series
        (PC>2.5, AvgC>2.5, B365C>2.5) — the closing price.
      * DO NOT compute CLV / line movement as (close - prematch): the prematch leg
        is not a genuine opener, so any such delta would be FABRICATED. CLV needs a
        real captured opener from a live feed.

    Pre-match fallback: Pinnacle P>2.5 → Avg>2.5 → B365>2.5.
    Close fallback: PC>2.5 → AvgC>2.5 → B365C>2.5.
    Missing cols (older seasons) → NA. Only rows with ≥1 price kept.
    """
    parts: List[pd.DataFrame] = []
    for div, _, raw in frames:
        df = raw.copy(); df["_div"] = str(div)
        df["date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        parts.append(df)
    if not parts:
        return pd.DataFrame(columns=list(ODDS_COLS))
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.dropna(subset=["date"]).copy()
    combined["home_team"] = combined["HomeTeam"].astype(str)
    combined["away_team"] = combined["AwayTeam"].astype(str)
    combined["div"] = combined["_div"].astype(str)
    combined["event_id"] = combined.apply(
        lambda r: _make_event_id(r["date"], r["div"], r["home_team"], r["away_team"]), axis=1)

    _RAW: Dict[str, str] = {
        "p_over": "P>2.5", "p_under": "P<2.5",
        "pc_over": "PC>2.5", "pc_under": "PC<2.5",
        "avg_over": "Avg>2.5", "avg_under": "Avg<2.5",
        "avgc_over": "AvgC>2.5", "avgc_under": "AvgC<2.5",
        "b365_over": "B365>2.5", "b365_under": "B365<2.5",
        "b365c_over": "B365C>2.5", "b365c_under": "B365C<2.5",
        "max_over": "Max>2.5", "max_under": "Max<2.5",
        "maxc_over": "MaxC>2.5", "maxc_under": "MaxC<2.5",
    }
    for out_col, raw_col in _RAW.items():
        combined[out_col] = _safe_float(combined[raw_col]) if raw_col in combined.columns else np.nan

    ov, un, bk = _best_price(combined, "P>2.5", "P<2.5", "Avg>2.5", "Avg<2.5", "B365>2.5", "B365<2.5")
    combined["ou_prematch_over"], combined["ou_prematch_under"], combined["book_prematch"] = ov, un, bk

    cv, cu, ck = _best_price(combined, "PC>2.5", "PC<2.5", "AvgC>2.5", "AvgC<2.5", "B365C>2.5", "B365C<2.5")
    combined["ou_close_over"], combined["ou_close_under"], combined["book_close"] = cv, cu, ck

    has_price = combined[["ou_prematch_over", "ou_prematch_under", "ou_close_over", "ou_close_under"]].notna().any(axis=1)
    out = (combined.loc[has_price, list(ODDS_COLS)]
           .sort_values(["date", "div", "event_id"], kind="mergesort")
           .reset_index(drop=True))

    float_cols = [c for c in ODDS_COLS if c not in ("event_id", "div", "date", "book_prematch", "book_close")]
    for col in float_cols:
        out[col] = out[col].astype("float32")

    return out


def build_report(frames: Iterable[FrameTuple]) -> dict:
    """Summarise ingest coverage. Returns rows_in/out/dropped, odds rows, coverage %."""
    frames_list = list(frames)
    m_df = build_matches(iter(frames_list))
    o_df = build_odds(iter(frames_list))
    total_in = sum(len(r) for _, _, r in frames_list)
    by_div_season = {
        f"{div}/{yr}": {"rows_in": len(raw),
                        "rows_out": int(((m_df["div"] == div) & (m_df["season"] == yr)).sum())}
        for div, yr, raw in frames_list
    }
    prematch_cov = (o_df["ou_prematch_over"].notna().sum() / len(o_df) * 100) if len(o_df) else 0.0
    close_cov = (o_df["ou_close_over"].notna().sum() / len(o_df) * 100) if len(o_df) else 0.0
    return {
        "rows_in": total_in,
        "rows_out_matches": len(m_df),
        "rows_dropped": total_in - len(m_df),
        "odds_rows": len(o_df),
        "prematch_coverage_pct": round(prematch_cov, 2),
        "close_coverage_pct": round(close_cov, 2),
        "by_div_season": by_div_season,
    }


def main() -> None:
    """Entry point: ``python -m domains.soccer.ingest_footballdata [--fetch] [--build]``."""
    parser = argparse.ArgumentParser(description="football-data.co.uk ingest → parquet")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--divs", default=",".join(LEAGUES.keys()))
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=dt.date.today().year)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()
    divs = [d.strip() for d in args.divs.split(",")]
    start_years = list(range(args.start_year, args.end_year + 1))
    do_all = not args.fetch and not args.build
    if args.fetch or do_all:
        mf = fetch_raw(out_dir=args.raw_dir, divs=divs, start_years=start_years, force=args.force)
        ok = sum(1 for e in mf.values() if "error" not in e and e.get("status") != "404")
        print(f"fetch_raw: {ok}/{len(mf)} files ok")
    if args.build or do_all:
        raw_root = Path(args.raw_dir) if args.raw_dir else (_REPO_ROOT / RAW_DIR_REL)
        out_root = Path(args.out_dir) if args.out_dir else (_REPO_ROOT / DATA_DIR_REL)
        out_root.mkdir(parents=True, exist_ok=True)
        raw_frames: List[FrameTuple] = []
        for yr in start_years:
            sc = season_code(yr)
            for div in divs:
                fpath = raw_root / f"{sc}_{div}.csv"
                if not fpath.exists(): continue
                try: raw_frames.append((div, yr, pd.read_csv(fpath, low_memory=False)))
                except Exception as exc: print(f"[warn] {fpath.name}: {exc}")
        if not raw_frames:
            print("No raw CSV files found; run with --fetch first."); return
        m_df = build_matches(iter(raw_frames)); o_df = build_odds(iter(raw_frames))
        pq.write_table(pa.Table.from_pandas(m_df, preserve_index=False), out_root / "matches.parquet")
        pq.write_table(pa.Table.from_pandas(o_df, preserve_index=False), out_root / "odds.parquet")
        r = build_report(iter(raw_frames))
        print(f"build: {len(m_df)} matches, {len(o_df)} odds | dropped={r['rows_dropped']} | "
              f"prematch={r['prematch_coverage_pct']:.1f}% close={r['close_coverage_pct']:.1f}%")


if __name__ == "__main__":
    main()

"""domains.mlb.ingest_sbro — SBR MLB xlsx → games.parquet + odds.parquet.

BUILD-SEPARABLE: fetch_raw is network-only; build_* are pure transforms.
Orientation: H row = HOME moneyline; V row = AWAY moneyline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from domains.mlb.config import (
    FETCH_UA, RAW_DIR_REL, URL_TEMPLATE, YEARS, am_to_decimal, resolve_league,
)

_TIMEOUT, _POLITENESS, _MAX_RETRIES = 30, 1.0, 3
_QUARANTINE_MAX_FRAC = 0.02
_REPO_ROOT = Path(__file__).resolve().parents[2]
_XLSX_RENAME = {"Unnamed: 18": "runline_odds", "Unnamed: 20": "openou_odds", "Unnamed: 22": "closeou_odds"}
GAMES_COLS: Tuple[str, ...] = (
    "event_id", "date", "season", "home_team", "away_team",
    "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
)
ODDS_COLS: Tuple[str, ...] = (
    "event_id", "date", "season",
    "ml_open_home_am", "ml_open_away_am", "ml_close_home_am", "ml_close_away_am",
    "dec_open_home", "dec_open_away", "dec_close_home", "dec_close_away", "book",
    "runline", "runline_odds", "openou", "openou_odds", "closeou", "closeou_odds",
)
FrameTuple = Tuple[int, pd.DataFrame]


def _to_float(val) -> float:
    """Coerce to float; 'NL'/non-numeric → NaN."""
    if isinstance(val, str) and val.strip().upper() == "NL":
        return float("nan")
    try:
        return float(val)
    except (TypeError, ValueError):
        return float("nan")

def _parse_date(mmdd: int, season: int) -> dt.date:
    mm, dd = mmdd // 100, mmdd % 100
    if not (3 <= mm <= 11):
        raise ValueError(f"month {mm} outside [3,11]")
    return dt.date(season, mm, dd)

def _eid(date: dt.date, home: str, away: str, seq: int) -> str:
    return f"{date:%Y%m%d}-{home.upper()}-{away.upper()}-{seq}"

def _iter_pairs(raw: pd.DataFrame) -> Iterator[Tuple[pd.Series, pd.Series, bool]]:
    """Yield (v_row, h_row, valid) pairs in file order; odd trailing row ignored."""
    arr = raw.reset_index(drop=True)
    for i in range(len(arr) // 2):
        r0, r1 = arr.iloc[2 * i], arr.iloc[2 * i + 1]
        ok = (str(r0["VH"]).strip().upper() == "V"
              and str(r1["VH"]).strip().upper() == "H"
              and r0["Date"] == r1["Date"]
              and int(r1["Rot"]) == int(r0["Rot"]) + 1)
        yield r0, r1, ok


def _http_get(url: str, dest: Path) -> dict:
    """Fetch url to dest with retries; 404/Cloudflare recorded, not raised."""
    req = urllib.request.Request(url, headers={"User-Agent": FETCH_UA})
    ts = dt.datetime.utcnow().isoformat()
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                data = r.read()
            if len(data) < 5000 and b"cloudflare" in data.lower():
                return {"url": url, "status": "cloudflare_challenge", "fetched_at": ts}
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {"url": url, "xlsx": str(dest), "bytes": len(data),
                    "sha256_xlsx": hashlib.sha256(data).hexdigest(), "fetched_at": ts}
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                return {"url": url, "status": "404", "fetched_at": ts}
            time.sleep(2 ** attempt)
    return {"url": url, "error": "max retries exceeded", "fetched_at": ts}


def fetch_raw(out_dir: Optional[str] = None, years: Optional[List[int]] = None,
              force: bool = False, offline: bool = False) -> dict:
    """Download SBR xlsx idempotently; convert to CSV. offline=True → no-op."""
    if offline:
        return {}
    raw_root = Path(out_dir) if out_dir else (_REPO_ROOT / RAW_DIR_REL)
    raw_root.mkdir(parents=True, exist_ok=True)
    mpath = raw_root / "manifest.json"
    manifest: dict = json.loads(mpath.read_text("utf-8")) if mpath.exists() else {}
    if years is None:
        years = list(YEARS)
    entries: dict = {}
    for y in years:
        url = URL_TEMPLATE.format(year=y)
        csv_dest = raw_root / f"mlb-odds-{y}.csv"
        if csv_dest.exists() and csv_dest.stat().st_size > 0 and not force:
            entries[str(y)] = {"status": "cached", "url": url, "csv": str(csv_dest)}
            continue
        entry = _http_get(url, raw_root / f"mlb-odds-{y}.xlsx")
        if "error" in entry or entry.get("status") in ("404", "cloudflare_challenge"):
            entries[str(y)] = entry
        else:
            try:                                        # openpyxl: one line
                df = pd.read_excel(entry["xlsx"], engine="openpyxl")
            except ImportError as exc:
                entry["error"] = f"openpyxl not installed: {exc}"
                entries[str(y)] = entry
                time.sleep(_POLITENESS)
                continue
            df.rename(columns=_XLSX_RENAME, inplace=True)
            df["season"] = y
            csv_dest.write_text(df.to_csv(index=False), encoding="utf-8")
            entry.update({"csv": str(csv_dest),
                          "sha256_csv": hashlib.sha256(csv_dest.read_bytes()).hexdigest()})
            entries[str(y)] = entry
        time.sleep(_POLITENESS)
    manifest.update(entries)
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return entries


def build_games(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """Pure: (season, raw_df) → games.parquet contract.  Strict V/H pairing;
    quarantine > 2 % raises; tied finals dropped; game_seq doubleheader seq.
    """
    parts: List[pd.DataFrame] = []
    total_rows = total_q = 0
    for season, raw in frames:
        total_rows += len(raw)
        seq: Dict[Tuple, int] = {}
        rows: List[dict] = []
        for vr, hr, ok in _iter_pairs(raw):
            if not ok:
                total_q += 1
                continue
            try:
                gd = _parse_date(int(vr["Date"]), season)
            except (ValueError, TypeError):
                total_q += 1
                continue
            home, away = str(hr["Team"]).strip().upper(), str(vr["Team"]).strip().upper()
            try:
                hr_runs, ar_runs = int(hr["Final"]), int(vr["Final"])
            except (ValueError, TypeError):
                total_q += 1
                continue
            if hr_runs == ar_runs:
                continue
            seq[(gd, home, away)] = seq.get((gd, home, away), 0) + 1
            s = seq[(gd, home, away)]
            rows.append({"event_id": _eid(gd, home, away, s), "date": pd.Timestamp(gd),
                         "season": season, "home_team": home, "away_team": away,
                         "home_runs": hr_runs, "away_runs": ar_runs,
                         "target_home_win": 1 if hr_runs > ar_runs else 0,
                         "game_seq": s, "home_league": resolve_league(home, season)})
        if rows:
            parts.append(pd.DataFrame(rows))
    if total_rows and total_q / total_rows > _QUARANTINE_MAX_FRAC:
        raise RuntimeError(
            f"quarantine fraction {total_q/total_rows:.1%} > {_QUARANTINE_MAX_FRAC:.1%}"
        )
    if not parts:
        return pd.DataFrame(columns=list(GAMES_COLS))
    out = pd.concat(parts, ignore_index=True)
    out["target_home_win"] = out["target_home_win"].astype("int8")
    out["game_seq"] = out["game_seq"].astype("int8")
    return (out[list(GAMES_COLS)]
            .sort_values(["date", "home_team", "away_team", "game_seq"], kind="mergesort")
            .reset_index(drop=True))

def build_odds(frames: Iterable[FrameTuple]) -> pd.DataFrame:
    """Pure: (season, raw_df) → odds.parquet. H row = HOME price, V row = AWAY."""
    parts: List[pd.DataFrame] = []
    for season, raw in frames:
        seq: Dict[Tuple, int] = {}
        rows: List[dict] = []
        for vr, hr, ok in _iter_pairs(raw):
            if not ok:
                continue
            try:
                gd = _parse_date(int(vr["Date"]), season)
            except (ValueError, TypeError):
                continue
            home, away = str(hr["Team"]).strip().upper(), str(vr["Team"]).strip().upper()
            seq[(gd, home, away)] = seq.get((gd, home, away), 0) + 1
            s = seq[(gd, home, away)]
            ml_oh, ml_ch = _to_float(hr.get("Open")), _to_float(hr.get("Close"))
            ml_oa, ml_ca = _to_float(vr.get("Open")), _to_float(vr.get("Close"))
            dec = [am_to_decimal(x) for x in (ml_oh, ml_ch, ml_oa, ml_ca)]
            if all(np.isnan(x) for x in dec):
                continue
            rows.append({"event_id": _eid(gd, home, away, s), "date": pd.Timestamp(gd), "season": season,
                         "ml_open_home_am": ml_oh, "ml_open_away_am": ml_oa,
                         "ml_close_home_am": ml_ch, "ml_close_away_am": ml_ca,
                         "dec_open_home": float(dec[0]), "dec_open_away": float(dec[2]),
                         "dec_close_home": float(dec[1]), "dec_close_away": float(dec[3]),
                         "book": "sbro_archive",
                         "runline": _to_float(hr.get("RunLine")), "runline_odds": _to_float(hr.get("runline_odds")),
                         "openou": _to_float(hr.get("OpenOU")), "openou_odds": _to_float(hr.get("openou_odds")),
                         "closeou": _to_float(hr.get("CloseOU")), "closeou_odds": _to_float(hr.get("closeou_odds"))})
        if rows:
            parts.append(pd.DataFrame(rows))
    if not parts:
        return pd.DataFrame(columns=list(ODDS_COLS))
    out = pd.concat(parts, ignore_index=True)
    _F32 = ("dec_open_home", "dec_open_away", "dec_close_home", "dec_close_away",
            "runline", "runline_odds", "openou", "openou_odds", "closeou", "closeou_odds")
    for c in _F32:
        out[c] = out[c].astype("float32")
    return (out[list(ODDS_COLS)]
            .sort_values(["date", "event_id"], kind="mergesort")
            .reset_index(drop=True))

def build_report(frames: Iterable[FrameTuple]) -> dict:
    """Coverage summary. ``mean_devig_p_home`` ~0.50–0.58 confirms orientation."""
    fl = list(frames)
    g_df, o_df = build_games(iter(fl)), build_odds(iter(fl))
    total_in = sum(len(r) for _, r in fl)
    qc = td = 0
    for _, raw in fl:
        for vr, hr, ok in _iter_pairs(raw):
            if not ok:
                qc += 1
                continue
            try:
                if int(hr["Final"]) == int(vr["Final"]):
                    td += 1
            except (ValueError, TypeError):
                qc += 1
    season_cov: dict = {}
    for s in sorted({ss for ss, _ in fl}):
        sub = o_df[o_df["season"] == s] if len(o_df) else pd.DataFrame()
        n = len(sub)
        oc = round((sub["dec_open_home"].notna() | sub["dec_open_away"].notna()).sum() / n * 100, 2) if n else 0.0
        cc = round((sub["dec_close_home"].notna() | sub["dec_close_away"].notna()).sum() / n * 100, 2) if n else 0.0
        season_cov[str(s)] = {"odds_rows": n, "open_ml_coverage_pct": oc, "close_ml_coverage_pct": cc}
    mdph: Optional[float] = None
    if len(o_df):
        dh, da = o_df["dec_close_home"].astype(float), o_df["dec_close_away"].astype(float)
        mask = dh.notna() & da.notna() & (dh > 1.0) & (da > 1.0)
        if mask.sum() > 0:
            ph, pa = 1.0 / dh[mask], 1.0 / da[mask]
            mdph = round(float((ph / (ph + pa)).mean()), 4)
    return {"rows_in": total_in, "rows_out_games": len(g_df), "rows_out_odds": len(o_df),
            "quarantine_count": qc, "quarantine_fraction": round(qc / (total_in / 2), 4) if total_in else 0.0,
            "tied_final_drops": td, "season_coverage": season_cov, "mean_devig_p_home": mdph}


def main() -> None:
    """Entry: ``python -m domains.mlb.ingest_sbro [--fetch] [--build]``."""
    ap = argparse.ArgumentParser(description="SBR MLB ingest → parquet")
    for flag in ("--fetch", "--build", "--offline", "--force"):
        ap.add_argument(flag, action="store_true")
    for opt in ("--years", "--raw-dir", "--out-dir"):
        ap.add_argument(opt, default=None)
    args = ap.parse_args()
    yrs = [int(y.strip()) for y in args.years.split(",")] if args.years else None
    do_all = not args.fetch and not args.build
    if (args.fetch or do_all) and not args.offline:
        mf = fetch_raw(out_dir=args.raw_dir, years=yrs, force=args.force)
        ok = sum(1 for e in mf.values() if "error" not in e and e.get("status") != "404")
        print(f"fetch_raw: {ok}/{len(mf)} ok")
    if args.build or do_all:
        raw_root = Path(args.raw_dir) if args.raw_dir else (_REPO_ROOT / RAW_DIR_REL)
        out_root = Path(args.out_dir) if args.out_dir else (_REPO_ROOT / "data/domains/mlb")
        out_root.mkdir(parents=True, exist_ok=True)
        raw_frames: List[FrameTuple] = []
        for y in (yrs or list(YEARS)):
            fp = raw_root / f"mlb-odds-{y}.csv"
            if fp.exists():
                try:
                    raw_frames.append((y, pd.read_csv(str(fp), low_memory=False)))
                except Exception as exc:
                    print(f"[warn] {fp.name}: {exc}")
        if not raw_frames:
            print("No raw CSVs; run --fetch first."); return
        g_df, o_df = build_games(iter(raw_frames)), build_odds(iter(raw_frames))
        pq.write_table(pa.Table.from_pandas(g_df, preserve_index=False), str(out_root / "games.parquet"))
        pq.write_table(pa.Table.from_pandas(o_df, preserve_index=False), str(out_root / "odds.parquet"))
        r = build_report(iter(raw_frames))
        print(f"build: {len(g_df)} games, {len(o_df)} odds | quarantine={r['quarantine_count']} "
              f"({r['quarantine_fraction']:.1%}) | tied={r['tied_final_drops']} | devig_p_home={r['mean_devig_p_home']}")


if __name__ == "__main__":
    main()

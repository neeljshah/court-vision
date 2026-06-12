"""domains.tennis.ingest_sackmann — Sackmann ATP/WTA CSV → matches.parquet + players.parquet.

LICENSE NOTE: Jeff Sackmann's tennis_atp / tennis_wta data is CC BY-NC-SA.
Private research use only. Nothing derived from it goes to the public repo.
PRIVATE: outputs are price-bearing or license-restricted; data/domains/tennis/ is never tracked.

NETWORK POLICY: fetch_raw() downloads and caches CSVs; build_matches() / build_players() are
pure transforms that read only from the local _raw/ cache. Tests call only the transform
functions with fixture paths — never fetch_raw(). Import is side-effect-free (zero network).
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
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_BASE_ATP = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master"
_BASE_WTA = "https://raw.githubusercontent.com/JeffSackmann/tennis_wta/master"
_UA = "tennis-domain-ingest/1.0 (private research; github.com/JeffSackmann)"
_TIMEOUT = 30
_POLITENESS = 0.5
_MAX_RETRIES = 3

ROUND_ORDER: dict[str, int] = {
    "ER": 0, "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4,
    "RR": 5, "R128": 6, "R64": 7, "R32": 8, "R16": 9,
    "QF": 10, "SF": 11, "BR": 12, "F": 13,
}
_ROUND_DEFAULT = 6
_RETIREMENT_TOKENS = frozenset(["ret", "w/o", "def", "abn", "walkover"])
_SURFACE_MAP: dict[str, str] = {
    "hard": "Hard", "clay": "Clay", "grass": "Grass", "carpet": "Carpet",
}

MATCHES_REQUIRED_COLS = [
    "event_id", "date", "tour", "tourney_id", "tourney_name", "tourney_level",
    "surface", "best_of", "round", "match_num",
    "p1_id", "p2_id", "p1_name", "p2_name", "p1_rank", "p2_rank",
    "winner", "score", "retirement", "minutes",
]
PLAYERS_REQUIRED_COLS = [
    "player_id", "name_first", "name_last", "full_name",
    "hand", "dob", "ioc", "height", "tour",
]


def _round_key(r: str) -> int:
    return ROUND_ORDER.get(str(r).strip(), _ROUND_DEFAULT)


def _retirement_flag(score: str) -> bool:
    if not isinstance(score, str):
        return False
    sl = score.lower()
    return any(tok in sl for tok in _RETIREMENT_TOKENS)


def _normalize_surface(raw: Optional[str]) -> str:
    if not raw or isinstance(raw, float):
        return "Unknown"
    return _SURFACE_MAP.get(str(raw).strip().lower(), str(raw).strip() or "Unknown")


def _fetch_url(url: str, dest: Path, timeout: int = _TIMEOUT) -> dict:
    """Fetch *url* to *dest* with retries. Returns manifest entry dict."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    last_err: Exception = RuntimeError("no attempt")
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return {
                "url": url, "file": str(dest), "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "fetched_at": dt.datetime.utcnow().isoformat(),
            }
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            last_err = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                return {"url": url, "file": str(dest), "status": "404",
                        "fetched_at": dt.datetime.utcnow().isoformat()}
            time.sleep(2 ** attempt)
    return {"url": url, "file": str(dest), "error": str(last_err),
            "fetched_at": dt.datetime.utcnow().isoformat()}


def fetch_raw(
    years: list[int] | None = None,
    raw_dir: str = "data/domains/tennis/_raw",
    tours: list[str] | None = None,
    offline: bool = False,
    force: bool = False,
) -> list[dict]:
    """Download Sackmann CSVs to *raw_dir* idempotently (skip if present with size>0).

    Current-season year and player files are always re-fetched (they are mutable).
    Returns list of manifest entries (one per file attempted).
    """
    if offline:
        return []
    raw = Path(raw_dir)
    raw.mkdir(parents=True, exist_ok=True)
    manifest_path = raw / "manifest.json"
    manifest: list[dict] = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else []
    if years is None:
        years = list(range(1968, dt.date.today().year + 1))
    if tours is None:
        tours = ["atp", "wta"]
    current_year = dt.date.today().year
    entries: list[dict] = []
    for tour in tours:
        base = _BASE_ATP if tour == "atp" else _BASE_WTA
        pfile = raw / f"sackmann/{tour}_players.csv"
        pfile.parent.mkdir(parents=True, exist_ok=True)
        entries.append(_fetch_url(f"{base}/{tour}_players.csv", pfile))
        time.sleep(_POLITENESS)
        for yr in years:
            mfile = raw / f"sackmann/{tour}_matches_{yr}.csv"
            mfile.parent.mkdir(parents=True, exist_ok=True)
            murl = f"{base}/{tour}_matches_{yr}.csv"
            if mfile.exists() and mfile.stat().st_size > 0 and not force and yr != current_year:
                entries.append({"url": murl, "file": str(mfile), "status": "cached"})
                continue
            entries.append(_fetch_url(murl, mfile))
            time.sleep(_POLITENESS)
    manifest.extend(entries)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return entries


def build_players(raw_dir: str = "data/domains/tennis/_raw", out_dir: str = "data/domains/tennis") -> pd.DataFrame:
    """Read cached atp_players.csv + wta_players.csv → players.parquet."""
    raw = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    for tour in ("atp", "wta"):
        p = raw / f"sackmann/{tour}_players.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, dtype=str)
        df["tour"] = tour
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No player CSV files found under {raw_dir}/sackmann/")
    return _transform_players(pd.concat(frames, ignore_index=True), out_dir)


def _transform_players(raw_df: pd.DataFrame, out_dir: str) -> pd.DataFrame:
    """Normalise a raw players DataFrame into the contract schema."""
    df = raw_df.copy()
    id_col = "player_id" if "player_id" in df.columns else df.columns[0]
    df = df.rename(columns={id_col: "player_id"})
    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    for col in ("name_first", "name_last", "hand", "ioc"):
        if col not in df.columns:
            df[col] = pd.NA
    df["full_name"] = (df["name_first"].fillna("").str.strip() + " " + df["name_last"].fillna("").str.strip()).str.strip()
    df["dob"] = pd.to_datetime(df["dob"], format="%Y%m%d", errors="coerce").dt.date if "dob" in df.columns else pd.NaT
    df["height"] = pd.to_numeric(df["height"], errors="coerce").astype("float32") if "height" in df.columns else float("nan")
    out = df[PLAYERS_REQUIRED_COLS].dropna(subset=["player_id"]).copy()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), Path(out_dir) / "players.parquet")
    return out


def build_matches(
    raw_dir: str = "data/domains/tennis/_raw",
    out_dir: str = "data/domains/tennis",
    tours: list[str] | None = None,
    start_year: int = 1968,
    end_year: int = 2026,
) -> pd.DataFrame:
    """Read cached Sackmann match CSVs → matches.parquet (§3.2 column contract)."""
    if tours is None:
        tours = ["atp", "wta"]
    raw = Path(raw_dir)
    frames: list[pd.DataFrame] = []
    for tour in tours:
        for yr in range(start_year, end_year + 1):
            p = raw / f"sackmann/{tour}_matches_{yr}.csv"
            if not p.exists():
                continue
            try:
                df = pd.read_csv(p, dtype=str, low_memory=False)
            except Exception:
                continue
            df["_tour"] = tour
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No match CSV files found under {raw_dir}/sackmann/")
    return _transform_matches(pd.concat(frames, ignore_index=True), out_dir)


def _transform_matches(raw_df: pd.DataFrame, out_dir: str) -> pd.DataFrame:
    """Normalise raw Sackmann match rows into the §3.2 contract."""
    df = raw_df.copy()
    tour_col = "_tour" if "_tour" in df.columns else "tour"
    winner_id = pd.to_numeric(df.get("winner_id", pd.Series(dtype="float64")), errors="coerce")
    loser_id = pd.to_numeric(df.get("loser_id", pd.Series(dtype="float64")), errors="coerce")
    # Stable orientation: p1 = min(winner_id, loser_id) — outcome-blind, kills ex-post label leak
    p1_is_winner = winner_id <= loser_id
    df["p1_id"] = winner_id.where(p1_is_winner, loser_id).astype("Int64")
    df["p2_id"] = loser_id.where(p1_is_winner, winner_id).astype("Int64")
    df["p1_name"] = df.get("winner_name", pd.Series(dtype=str)).where(p1_is_winner, df.get("loser_name", pd.Series(dtype=str)))
    df["p2_name"] = df.get("loser_name", pd.Series(dtype=str)).where(p1_is_winner, df.get("winner_name", pd.Series(dtype=str)))
    df["p1_rank"] = pd.to_numeric(df.get("winner_rank", pd.Series(dtype="float64")), errors="coerce").where(p1_is_winner, pd.to_numeric(df.get("loser_rank", pd.Series(dtype="float64")), errors="coerce")).astype("float32")
    df["p2_rank"] = pd.to_numeric(df.get("loser_rank", pd.Series(dtype="float64")), errors="coerce").where(p1_is_winner, pd.to_numeric(df.get("winner_rank", pd.Series(dtype="float64")), errors="coerce")).astype("float32")
    df["winner"] = p1_is_winner.map({True: 1, False: 2}).astype("int8")
    df["date"] = pd.to_datetime(df.get("tourney_date", pd.Series(dtype=str)), format="%Y%m%d", errors="coerce").dt.date
    df["surface"] = df.get("surface", pd.Series(dtype=str)).apply(_normalize_surface)
    df["best_of"] = pd.to_numeric(df.get("best_of", pd.Series(dtype="float64")), errors="coerce").fillna(3).astype("int8")
    df["match_num"] = pd.to_numeric(df.get("match_num", pd.Series(dtype="float64")), errors="coerce").fillna(0).astype("int32")
    df["score"] = df.get("score", pd.Series(dtype=str)).fillna("").astype(str)
    df["retirement"] = df["score"].apply(_retirement_flag)
    df["minutes"] = pd.to_numeric(df.get("minutes", pd.Series(dtype="float64")), errors="coerce").astype("float32")
    df["tour"] = df[tour_col].astype(str)
    for fld in ("tourney_id", "tourney_name", "tourney_level", "round"):
        df[fld] = df.get(fld, pd.Series(dtype=str)).fillna("").astype(str)

    def _make_event_id(row: pd.Series) -> str:
        d = row["date"].strftime("%Y%m%d") if isinstance(row["date"], dt.date) else "00000000"
        return f"{d}-{row['tour']}-{row['tourney_id']}-{row['p1_id']}-{row['p2_id']}-{row['match_num']}"

    df["event_id"] = df.apply(_make_event_id, axis=1)
    df["_round_ord"] = df["round"].apply(_round_key)
    df = df.sort_values(
        ["date", "tour", "tourney_id", "_round_ord", "match_num"],
        kind="mergesort", na_position="last",
    ).reset_index(drop=True)
    # Tour-level filter: keep G/M/A/F/D/O and numeric (250/500) — drop Q/C challengers
    _keep = {"G", "M", "A", "F", "D", "O", ""}
    df = df[df["tourney_level"].isin(_keep) | df["tourney_level"].str.match(r"^\d+$", na=False)].copy()
    out = df[MATCHES_REQUIRED_COLS].copy()
    # Deduplicate event_ids deterministically
    if out["event_id"].duplicated().any():
        mask = out["event_id"].duplicated(keep=False)
        out.loc[mask, "event_id"] = (
            out.loc[mask, "event_id"] + "-"
            + out.loc[mask].groupby("event_id").cumcount().astype(str)
        )
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), Path(out_dir) / "matches.parquet")
    return out


def load_matches(path: str | Path = "data/domains/tennis/matches.parquet") -> pd.DataFrame:
    """Load matches.parquet in the pinned chronological sort order.

    This is the single authoritative loader every downstream tennis module uses.
    """
    df = pd.read_parquet(path)
    if "date" not in df.columns:
        return df
    df["_round_ord"] = df["round"].apply(_round_key)
    df = df.sort_values(
        ["date", "tour", "tourney_id", "_round_ord", "match_num"],
        kind="mergesort", na_position="last",
    ).reset_index(drop=True)
    return df.drop(columns=["_round_ord"])


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Sackmann ATP/WTA ingest")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--tours", default="atp,wta")
    parser.add_argument("--start-year", type=int, default=1968)
    parser.add_argument("--end-year", type=int, default=dt.date.today().year)
    parser.add_argument("--raw-dir", default="data/domains/tennis/_raw")
    parser.add_argument("--out-dir", default="data/domains/tennis")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    tours = [t.strip() for t in args.tours.split(",")]
    do_all = not args.fetch and not args.build
    if args.fetch or do_all:
        entries = fetch_raw(years=list(range(args.start_year, args.end_year + 1)),
                            raw_dir=args.raw_dir, tours=tours, force=args.force)
        ok = sum(1 for e in entries if "error" not in e and e.get("status") != "404")
        print(f"fetch_raw: {ok}/{len(entries)} files ok")
    if args.build or do_all:
        m = build_matches(raw_dir=args.raw_dir, out_dir=args.out_dir, tours=tours,
                          start_year=args.start_year, end_year=args.end_year)
        p = build_players(raw_dir=args.raw_dir, out_dir=args.out_dir)
        print(f"build: {len(m)} matches, {len(p)} players → {args.out_dir}/")


if __name__ == "__main__":
    _cli()

"""scripts.platformkit.clv.kx_ticker_close -- Kalshi-ticker CLOSE-PROXY derivation (Lane 5).

THE GAP: in-game ledger rows are CLV-ungradeable when game_id is a Kalshi
ticker (e.g. "KXMLBGAME-26JUN281920NYYBOS"), because close capture
(odds_provider.line_store.get_close) is keyed to the ESPN numeric game_id
corpus (data/cache/line_history/). The two id spaces never join -- the
"off_id_space" cause in clv_ledger_backfill_report.

THE FIX: the in-play tick files this repo ALREADY writes
(data/cache/ingame_grade/<sport>/<TICKER>.jsonl, via live_grade.capture_pair_once)
carry the FULL venue price series for that ticker, one row per tick:
    {"sport","game_id","ts","market_prob","model_prob","side","state_summary"}
market_prob is ALWAYS the HOME side's venue-implied win probability
(live_grade.PAIR_SIDE == "home", reused byte-identical, not reinvented). No new
network call is needed -- the close-analogue is already on disk.

HONEST CONVENTION (binding -- this is a proxy, never a market-official close):
  close_prob = the LAST tick's market_prob (home-side implied prob) in the file.
  close_ts   = that tick's ts. n_ticks = total valid ticks (coverage signal).
  close_kind = "last_tick" ALWAYS -- the last captured venue price before our
               capture loop stopped ticking (board rotation, restart, etc); NOT
               verified against an exchange settlement record. Never relabel
               this "official" or "true_close" downstream.
A file with zero usable (market_prob in [0,1]) ticks yields NOTHING (an honest
skip) -- never a fabricated close from an empty/corrupt series.

OUTPUT: data/cache/kx_closes/<sport>/<date>.jsonl (append-only, idempotent by
ticker -- see write_closes()). Row: {"ticker","sport","close_prob","close_ts",
"n_ticks","close_kind","derived_at"}. <date> = UTC date of close_ts (same
bucketing convention as odds_provider.snapshot.write_quotes).

INVARIANTS: scripts/platformkit/clv/ only; <=300 LOC; ASCII; stdlib only; no
network; reads ingame_grade/ (read-only); writes ONLY kx_closes/; never
touches line_history or the ledger; never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/clv/test_kx_ticker_close.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_CLOSES_DIR = _REPO_ROOT / "data" / "cache" / "kx_closes"

CLOSE_KIND = "last_tick"  # the ONLY value this module ever writes -- see module docstring


def _prob01(value: Any) -> Optional[float]:
    """Coerce to a probability in [0,1]; None on non-numeric / out-of-range."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _is_kx_ticker(name: str) -> bool:
    """A Kalshi contract ticker is a non-numeric venue id (never an ESPN numeric game_id)."""
    s = str(name or "").strip()
    return bool(s) and not s.isdigit()


def _date_of(iso_ts: str) -> Optional[str]:
    """UTC calendar date (YYYY-MM-DD) of an ISO ts, or None if unparseable."""
    try:
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _iter_tick_files(sport: str, *, grade_dir: Optional[Path] = None) -> List[Path]:
    """Every ticker tick file under data/cache/ingame_grade/<sport>/, sorted. Never raises."""
    base = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    sport_dir = base / str(sport).lower()
    if not sport_dir.exists():
        return []
    try:
        return sorted(p for p in sport_dir.glob("*.jsonl") if _is_kx_ticker(p.stem))
    except OSError:
        return []


def derive_close(path: Path) -> Optional[Dict[str, Any]]:
    """Derive the close-proxy for ONE ticker's tick file.

    Keeps rows with a usable market_prob AND a parseable ts (a settle-stamp row
    from settle_stamp.py carries no market_prob and is naturally excluded). The
    LAST such row by ts is the close proxy. None on a missing/empty/all-invalid
    file (honest skip, never a fabricated close). Never raises.
    """
    ticker = path.stem
    sport = None
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                mp = _prob01(rec.get("market_prob"))
                ts = rec.get("ts")
                if mp is None or not ts:
                    continue  # excludes settle-stamp rows (no market_prob) and bad ticks
                if sport is None and rec.get("sport"):
                    sport = str(rec["sport"]).lower()
                rows.append({"market_prob": mp, "ts": str(ts),
                             "side": str(rec.get("side", "home"))})
    except OSError as exc:  # noqa: BLE001 -- unreadable file is an honest skip
        logger.debug("kx_ticker_close derive_close read failed %s: %s", path, exc)
        return None
    if not rows:
        return None
    rows.sort(key=lambda r: r["ts"])
    last = rows[-1]
    return {
        "ticker": ticker,
        "sport": sport or "",
        "close_prob": last["market_prob"],
        "close_ts": last["ts"],
        "close_side": last["side"],
        "n_ticks": len(rows),
        "close_kind": CLOSE_KIND,
    }


def derive_closes_for_sport(sport: str, *, grade_dir: Optional[Path] = None
                            ) -> List[Dict[str, Any]]:
    """derive_close() for every ticker tick file under one sport's grade dir. Skips
    (omits) files that yield no usable close. Never raises."""
    out: List[Dict[str, Any]] = []
    for p in _iter_tick_files(sport, grade_dir=grade_dir):
        d = derive_close(p)
        if d is not None:
            out.append(d)
    return out


def _closes_path(sport: str, date: str, *, out_dir: Optional[Path] = None) -> Path:
    base = Path(out_dir) if out_dir is not None else DEFAULT_CLOSES_DIR
    return base / str(sport).lower() / ("%s.jsonl" % date)


def _existing_tickers(path: Path) -> set:
    seen = set()
    if not path.is_file():
        return seen
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("ticker"):
                    seen.add(str(rec["ticker"]))
    except OSError:
        pass
    return seen


def _append_atomic(path: Path, lines: List[str]) -> None:
    """Same tmp-file + os.replace discipline as live_grade._append_atomic."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            existing = fh.read()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(existing)
        for line in lines:
            fh.write(line + "\n")
    os.replace(str(tmp), str(path))


def write_closes(sport: str, *, grade_dir: Optional[Path] = None,
                 out_dir: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Derive + persist close-proxies for every ticker tick file of *sport*.

    IDEMPOTENT (matched by 'ticker'): safe to call repeatedly, e.g. once per
    wake -- only new tickers get appended. Never raises; returns {sport,
    n_derived, n_written, n_skipped_existing, n_skipped_no_close, paths}.
    """
    nowdt = now or datetime.now(timezone.utc)
    derived = derive_closes_for_sport(sport, grade_dir=grade_dir)
    by_date: Dict[str, List[Dict[str, Any]]] = {}
    for d in derived:
        date = _date_of(d["close_ts"]) or nowdt.date().isoformat()
        by_date.setdefault(date, []).append(d)

    n_written = 0
    n_skipped_existing = 0
    paths: List[str] = []
    for date, rows in by_date.items():
        target = _closes_path(sport, date, out_dir=out_dir)
        seen = _existing_tickers(target)
        new_lines = []
        for row in rows:
            if row["ticker"] in seen:
                n_skipped_existing += 1
                continue
            stamped = dict(row)
            stamped["derived_at"] = nowdt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            new_lines.append(json.dumps(stamped, ensure_ascii=True))
            n_written += 1
        if new_lines:
            _append_atomic(target, new_lines)
        paths.append(str(target))

    # Files that produced no derivable close (empty/corrupt) are counted here.
    n_total_files = len(_iter_tick_files(sport, grade_dir=grade_dir))
    return {
        "sport": str(sport).lower(),
        "n_ticker_files": n_total_files,
        "n_derived": len(derived),
        "n_written": n_written,
        "n_skipped_existing": n_skipped_existing,
        "n_skipped_no_close": n_total_files - len(derived),
        "paths": paths,
        "honest_note": (
            "close_kind is ALWAYS 'last_tick' -- the last captured venue tick "
            "price before our capture loop stopped, NOT an exchange-official "
            "settlement/expiration close. Never present as an official close."
        ),
    }


def get_close_prob(ticker: str, sport: str, *,
                   closes_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Look up a previously-derived close row for *ticker* across ALL date-bucket
    files under data/cache/kx_closes/<sport>/. Returns the row dict (ticker,
    sport, close_prob, close_ts, close_side, n_ticks, close_kind, derived_at) or
    None if never derived. Never raises. Pure read, no derivation side effect --
    callers needing a fresh derive should call write_closes() first."""
    base = Path(closes_dir) if closes_dir is not None else DEFAULT_CLOSES_DIR
    sport_dir = base / str(sport).lower()
    if not sport_dir.exists():
        return None
    want = str(ticker)
    try:
        for f in sorted(sport_dir.glob("*.jsonl")):
            with f.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict) and str(rec.get("ticker")) == want:
                        return rec
    except OSError as exc:  # noqa: BLE001 -- unreadable corpus is an honest miss
        logger.debug("kx_ticker_close get_close_prob read failed %s: %s", sport_dir, exc)
        return None
    return None


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Derive Kalshi-ticker close-proxies from in-play ticks; "
                    "writes data/cache/kx_closes/<sport>/<date>.jsonl.")
    ap.add_argument("--sport", action="append", default=None,
                    help="sport to process (repeatable); default mlb + soccer_intl")
    a = ap.parse_args(list(argv) if argv is not None else None)
    results = [write_closes(s) for s in (a.sport or ["mlb", "soccer_intl"])]
    print(json.dumps(results, indent=2, ensure_ascii=True, default=str))
    return 0


__all__ = [
    "CLOSE_KIND", "DEFAULT_GRADE_DIR", "DEFAULT_CLOSES_DIR",
    "derive_close", "derive_closes_for_sport", "write_closes", "get_close_prob",
]

if __name__ == "__main__":
    raise SystemExit(_main())

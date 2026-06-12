"""backfill_nba_archives.py — Retroactive sweep of local line archives into the forward-capture ledger.

Emits each row via the N-CLV-001 writer with source="archive", ts_quality="reconstructed".
KERNEL_DISCIPLINE #3: reconstructed rows MUST NOT count toward the 60-day forward baseline.
Forward queries exclude them: WHERE ts_quality != 'reconstructed' (or use forward_only_filter()).
Idempotent via record_key() dedup.  Use --dry-run to report without writing.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from ledger_schema import record_key, validate  # noqa: E402
from ledger_writer import append, read_all  # noqa: E402

_SPORT = "nba"
_SOURCE = "archive"
_TS_RECONSTRUCTED = "reconstructed"

_ARCHIVE_DIRS: List[Path] = [
    _REPO_ROOT / "data" / "lines",
    _REPO_ROOT / "data" / "cache" / "odds_api",
    _REPO_ROOT / "data" / "cache" / "lines_archive",
    _REPO_ROOT / "data" / "cache" / "closing_lines",
]

_STAT_MAP: Dict[str, str] = {
    "pts": "player_points", "reb": "player_rebounds", "ast": "player_assists",
    "fg3m": "player_threes", "blk": "player_blocks", "stl": "player_steals",
    "tov": "player_turnovers", "pra": "player_points_rebounds_assists",
    "pr": "player_points_rebounds", "pa": "player_points_assists",
    "ra": "player_rebounds_assists",
    "player_points": "player_points", "player_rebounds": "player_rebounds",
    "player_assists": "player_assists", "player_threes": "player_threes",
    "player_blocks": "player_blocks", "player_steals": "player_steals",
}
_MAINLINE_MAP: Dict[str, str] = {"moneyline": "moneyline", "spread": "spread", "total": "total"}


def _norm_ts(raw: str, fallback_path: Optional[Path] = None) -> str:
    s = (raw or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        if not (s.endswith("Z") or "+" in s[10:]):
            s += "Z"
        return s
    if fallback_path:
        dt = datetime.datetime.utcfromtimestamp(fallback_path.stat().st_mtime)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return ""


def _price(raw) -> Optional[float]:
    if raw is None or raw == "" or raw != raw:
        return None
    try:
        return float(str(raw).replace(" ", "").lstrip("+"))
    except (ValueError, TypeError):
        return None


def _rec(event_id, market, book, price, side, ts) -> dict:
    return {
        "sport": _SPORT, "event_id": event_id, "market": market, "book": book,
        "price": price, "side": side, "kind": "close",
        "ts_utc_observed": ts, "source": _SOURCE, "ts_quality": _TS_RECONSTRUCTED,
    }


def _iter_csv(path: Path) -> Iterator[Tuple[dict, bool]]:
    """Parse a standard prop/mainline CSV file."""
    fb_ts = _norm_ts("", path)
    try:
        rows = list(csv.DictReader(open(path, encoding="utf-8", errors="replace")))
    except Exception:
        return
    for raw in rows:
        cols = set(raw.keys())
        ts = _norm_ts(raw.get("captured_at", ""), path) or fb_ts
        book = raw.get("book", "").strip()

        # Mainline format
        if "market_type" in cols and "price" in cols:
            gid = raw.get("game_id", "").strip()
            mkt = _MAINLINE_MAP.get(raw.get("market_type", "").strip().lower())
            side = raw.get("side", "").strip().lower()
            line_v = raw.get("line", "").strip()
            price = _price(raw.get("price"))
            if not (mkt and book and gid and price is not None):
                yield {}, False
                continue
            yield _rec(gid, mkt, book, price, f"{side}:{line_v}" if line_v else side, ts), True
            continue

        # Player-prop format
        gid = raw.get("game_id", "").strip()
        stat = raw.get("stat", "").strip().lower()
        player = raw.get("player_name", "").strip()
        line_v = raw.get("line", "").strip()
        over_p = _price(raw.get("over_price"))
        under_p = _price(raw.get("under_price"))
        mkt = _STAT_MAP.get(stat)
        eid = gid or f"unknown_{player.replace(' ', '_')}_{stat}"
        if not (mkt and book and player and line_v):
            yield {}, False
            continue
        if over_p is not None:
            yield _rec(eid, mkt, book, over_p, f"over:{player}:{line_v}", ts), True
        if under_p is not None:
            yield _rec(eid, mkt, book, under_p, f"under:{player}:{line_v}", ts), True


def _iter_odds_api_json(path: Path) -> Iterator[Tuple[dict, bool]]:
    fb_ts = _norm_ts("", path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    ts = _norm_ts(payload.get("timestamp", ""), path) or fb_ts
    data = payload.get("data", {})
    eid = data.get("id", "")
    if not eid or "nba" not in data.get("sport_key", "").lower():
        return
    for bm in data.get("bookmakers", []):
        book = bm.get("key", "").strip()
        if not book:
            continue
        for mkt_obj in bm.get("markets", []):
            mkt = _STAT_MAP.get(mkt_obj.get("key", "").strip(), mkt_obj.get("key", ""))
            for out in mkt_obj.get("outcomes", []):
                direction = out.get("name", "").strip().lower()
                player = out.get("description", "").strip()
                price = _price(out.get("price"))
                point = out.get("point")
                if direction not in ("over", "under") or price is None or not player or point is None:
                    yield {}, False
                    continue
                yield _rec(eid, mkt, book, price, f"{direction}:{player}:{point}", ts), True


def _archive_files(dirs: List[Path]) -> Iterator[Tuple[Path, str]]:
    for base in dirs:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.csv")):
            yield p, "csv"
        if "odds_api" in str(base):
            for p in sorted(base.rglob("*.json")):
                if "historical_event_odds" in str(p):
                    yield p, "json"


def forward_only_filter(records: List[dict]) -> List[dict]:
    """Return rows that are NOT tagged reconstructed — the canonical forward-only view."""
    return [r for r in records if r.get("ts_quality") != _TS_RECONSTRUCTED]


def _existing_keys(ledger_root: Optional[Path]) -> Set[Tuple]:
    from ledger_writer import _DEFAULT_ROOT as _dr  # noqa: PLC0415
    root = ledger_root if ledger_root is not None else _dr
    sport_dir = Path(root) / _SPORT
    seen: Set[Tuple] = set()
    if not sport_dir.exists():
        return seen
    for jf in sport_dir.glob("*.jsonl"):
        try:
            for row in read_all(_SPORT, jf.stem, root):
                seen.add(record_key(row))
        except Exception:
            pass
    return seen


def run_sweep(
    dry_run: bool = False,
    ledger_root: Optional[Path] = None,
    archive_dirs: Optional[List[Path]] = None,
) -> dict:
    """Sweep archive dirs and emit ledger rows.  Pass ledger_root=tmp_path in tests."""
    dirs = archive_dirs if archive_dirs is not None else _ARCHIVE_DIRS
    stats: dict = dict(
        dirs_found=sum(1 for d in dirs if d.exists()),
        dirs_absent=sum(1 for d in dirs if not d.exists()),
        files_processed=0,
        rows_written=0,
        rows_skipped_unmapped=0,
        rows_skipped_duplicate=0,
        ts_quality_split={},
    )

    seen = _existing_keys(ledger_root)

    for file_path, kind in _archive_files(dirs):
        stats["files_processed"] += 1
        row_iter = _iter_csv(file_path) if kind == "csv" else _iter_odds_api_json(file_path)
        for rec, ok in row_iter:
            if not ok or not rec:
                stats["rows_skipped_unmapped"] += 1
                continue
            try:
                validate(rec)
            except ValueError:
                stats["rows_skipped_unmapped"] += 1
                continue
            rk = record_key(rec)
            if rk in seen:
                stats["rows_skipped_duplicate"] += 1
                continue
            seen.add(rk)
            tq = rec.get("ts_quality", "none")
            stats["ts_quality_split"][tq] = stats["ts_quality_split"].get(tq, 0) + 1
            stats["rows_written"] += 1
            if not dry_run:
                append(rec, root=ledger_root)

    return stats


def _prove_forward_exclusion(ledger_root: Optional[Path]) -> dict:
    """Read ledger back and return total/reconstructed/forward row counts."""
    from ledger_writer import _DEFAULT_ROOT as _dr  # noqa: PLC0415
    root = ledger_root if ledger_root is not None else _dr
    sport_dir = Path(root) / _SPORT
    all_rows: List[dict] = []
    if sport_dir.exists():
        for jf in sorted(sport_dir.glob("*.jsonl")):
            try:
                all_rows.extend(read_all(_SPORT, jf.stem, root))
            except Exception:
                pass
    forward = forward_only_filter(all_rows)
    reconstructed = [r for r in all_rows if r.get("ts_quality") == _TS_RECONSTRUCTED]
    return dict(
        total_rows=len(all_rows),
        reconstructed_rows=len(reconstructed),
        forward_rows=len(forward),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retroactive NBA line archive sweep into the forward-capture ledger."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report counts without writing to the ledger.")
    args = parser.parse_args()

    stats = run_sweep(dry_run=args.dry_run)
    proof = _prove_forward_exclusion(ledger_root=None)

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"\n=== backfill_nba_archives [{mode}] ===")
    print(f"  Archive dirs found   : {stats['dirs_found']}")
    print(f"  Archive dirs absent  : {stats['dirs_absent']}")
    print(f"  Files processed      : {stats['files_processed']}")
    label = "(would write)" if args.dry_run else "written"
    print(f"  Rows {label:<22}: {stats['rows_written']}")
    print(f"  Rows skipped unmapped: {stats['rows_skipped_unmapped']}")
    print(f"  Rows skipped (dupes) : {stats['rows_skipped_duplicate']}")
    print("\n  ts_quality split:")
    for tq, cnt in sorted(stats["ts_quality_split"].items()):
        print(f"    {tq:<20}: {cnt}")
    if not stats["ts_quality_split"]:
        print("    (no rows processed)")

    print("\n  Forward-view exclusion proof (existing ledger):")
    print(f"    Total rows          : {proof['total_rows']}")
    print(f"    Reconstructed rows  : {proof['reconstructed_rows']}")
    print(f"    Forward-only rows   : {proof['forward_rows']}")
    if proof["total_rows"] > 0:
        assert proof["forward_rows"] == proof["total_rows"] - proof["reconstructed_rows"]
        print("    [PASS] forward_only_filter excludes all reconstructed rows.")
    else:
        print("    (ledger empty; run without --dry-run to populate)")
    print()


if __name__ == "__main__":
    main()

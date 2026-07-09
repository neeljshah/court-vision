"""scripts.platformkit.venue_history.census -- coverage census over everything
under data/venue_history/ (kalshi settled-candle JSONLs, polymarket per-game/
per-day JSONLs), per sport and per series/lane subdirectory.

Sample-reads (never loads a whole corpus): file COUNT is a real listdir, but
per-file candle/price counts are summed from an on-disk "n_candles"/"n_prices"
field already stamped by the writer (kalshi_intragame / polymarket_intragame /
polymarket_game_slug_backfill), falling back to a cheap line-count for a file
with neither field. Date ranges come from the writer's own progress sidecar
when present (cheap, already aggregated) else from the min/max filename.

No $ fields anywhere in the output (calibration/coverage-only, see
no-edge-claims rule). ASCII-only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_census.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VENUE_HISTORY_DIR = _REPO_ROOT / "data" / "venue_history"
DEFAULT_OUT_PATH = _REPO_ROOT / "data" / "frontend" / "ops" / "venue_history_census.json"


def _read_progress(dir_path: Path) -> Dict[str, Any]:
    prog = dir_path / "_progress.json"
    try:
        return json.loads(prog.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- missing/corrupt sidecar -> no aggregate stats
        return {}


def _sample_scan(files: List[Path], *, sample_n: int = 25) -> Dict[str, Any]:
    """Read up to *sample_n* files, summing each doc's own n_candles/n_prices
    stamp (a file with neither field falls back to 1-doc-per-line) and
    tracking the min/max of any "close_time" (kalshi) or "date" (polymarket)
    field seen -- a real scan of the date range, not a sidecar guess. Row
    total is averaged over the sample and scaled by the full file count.
    Never loads more than *sample_n* files."""
    if not files:
        return {"n_rows_estimate": 0, "min_date": None, "max_date": None}
    sample = files[:sample_n]
    total = 0
    counted = 0
    dates: List[str] = []
    for fp in sample:
        try:
            with fp.open("r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception:  # noqa: BLE001 -- one bad file must not kill the census
            continue
        rows = 0
        for line in lines:
            try:
                doc = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(doc, dict):
                rows += 1
                continue
            if isinstance(doc.get("n_candles"), int):
                rows += doc["n_candles"]
            elif isinstance(doc.get("n_prices"), int):
                rows += doc["n_prices"]
            else:
                rows += 1
            for key in ("close_time", "date"):
                v = doc.get(key)
                if isinstance(v, str) and len(v) >= 10:
                    dates.append(v[:10])
        total += rows
        counted += 1
    n_rows_estimate = int(round((total / counted) * len(files))) if counted else 0
    return {
        "n_rows_estimate": n_rows_estimate,
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }


def _date_range_from_filenames(files: List[Path]) -> Dict[str, Optional[str]]:
    """A file's leading YYYY-MM-DD prefix (polymarket convention) if present;
    kalshi tickers embed dates mid-string so this degrades to None for them
    (the progress sidecar's earliest/latest fields are the authoritative
    source for kalshi -- see census_dir)."""
    dates = []
    for fp in files:
        name = fp.stem
        if len(name) >= 10 and name[4] == "-" and name[7] == "-":
            dates.append(name[:10])
    if not dates:
        return {"min_date": None, "max_date": None}
    return {"min_date": min(dates), "max_date": max(dates)}


def census_dir(dir_path: Path) -> Dict[str, Any]:
    """One leaf directory's census: file count, sampled row estimate, date
    range. Date range PREFERS the progress sidecar's own earliest/latest
    (aggregated over the FULL backfill run, not just the sample) since files
    are sorted by ticker/slug name, not date, so a small sample skews toward
    alphabetically-early tickers; falls back to the sampled docs' own
    close_time/date field, then the filename prefix (polymarket convention),
    in that order -- never fabricated when all three are absent."""
    files = sorted(p for p in dir_path.glob("*.jsonl") if p.is_file())
    progress = _read_progress(dir_path)
    scan = _sample_scan(files)
    fname_range = _date_range_from_filenames(files)
    earliest = progress.get("earliest_close_time") or progress.get("earliest_date_confirmed")
    latest = progress.get("latest_date_confirmed")
    return {
        "n_files": len(files),
        "n_rows_estimate": scan["n_rows_estimate"],
        "min_date": (str(earliest)[:10] if earliest else None) or scan["min_date"] or fname_range["min_date"],
        "max_date": (str(latest)[:10] if latest else None) or scan["max_date"] or fname_range["max_date"],
        "has_progress_sidecar": bool(progress),
    }


def census_venue(venue_dir: Path) -> Dict[str, Any]:
    """One venue root (kalshi/ or polymarket/): census the venue root itself
    plus every immediate subdirectory (a sport, or a sport/series-lane)."""
    out: Dict[str, Any] = {}
    if not venue_dir.is_dir():
        return out
    for child in sorted(venue_dir.iterdir()):
        if not child.is_dir():
            continue
        out[child.name] = census_dir(child)
        # one level deeper: per-series subdirs written by run_all_backfills
        for grandchild in sorted(child.iterdir()):
            if grandchild.is_dir():
                out["%s/%s" % (child.name, grandchild.name)] = census_dir(grandchild)
    return out


def build_census(venue_history_dir: Path = DEFAULT_VENUE_HISTORY_DIR) -> Dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "venue_history_dir": str(venue_history_dir),
        "kalshi": census_venue(venue_history_dir / "kalshi"),
        "polymarket": census_venue(venue_history_dir / "polymarket"),
        "honest_note": "coverage/file-count census only, no price or edge fields; "
                       "n_rows_estimate is a sampled average scaled by file count, not exact",
    }


def write_census(out_path: Path = DEFAULT_OUT_PATH,
                 venue_history_dir: Path = DEFAULT_VENUE_HISTORY_DIR) -> Dict[str, Any]:
    doc = build_census(venue_history_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, indent=1, ensure_ascii=True), encoding="utf-8")
    return doc


def main() -> None:
    doc = write_census()
    print(json.dumps({"kalshi_dirs": len(doc["kalshi"]), "polymarket_dirs": len(doc["polymarket"])}))


if __name__ == "__main__":
    main()


__all__ = ["census_dir", "census_venue", "build_census", "write_census",
           "DEFAULT_VENUE_HISTORY_DIR", "DEFAULT_OUT_PATH"]

"""scripts.platformkit.ingame.fotmob_wc_finished_enum -- LANE 3 item 1:
CORPUS EXTENSION enumerator. Lists every FINISHED FotMob match across the
World Cup 2026 tournament window (2026-06-11..2026-07-04), NOT just our 39
captured soccer_intl games. This is a corpus-size/coverage measurement
serving analysis 2/3's honest framing (how big is the finished-match
universe vs what we can actually grade) -- it does NOT feed the gate corpus.

WHY THE GATE CORPUS STAYS OUR 39 CAPTURED GAMES: for a WC match we did not
run inplay_capture_loop against, there is no captured tick series and no
'baseline model prob' (score+minute in-play model) to condition -- the
enrichment gate's Brier-delta judge needs BOTH arms (baseline, enriched) per
tick, which only exists for games we actually captured. This module answers
a DIFFERENT, honest question: "how many finished WC matches exist that we
could theoretically extend into" -- useful for future backfill budgeting,
not for widening the current validation corpus.

METHOD (bounded, resumable, leak-free): walk date_str in the tournament
window via a WC-league-filtered fetch (fetch_matches_for_date returns EVERY
league playing that day -- domestic cups, U20s, friendlies -- not just the
tournament; a raw scan over 2026-06-11..07-04 returned 1525 "finished"
matches globally, confirming this). This module re-fetches the raw payload
itself (bypassing ingame_fotmob's league-flattening) and keeps only
leagues whose name contains "world cup" (case-insensitive) -- FotMob's own
group-stage league naming ("World Cup Grp. A", verified live 2026-07-04).
Keeps status.finished==True entries only, dedupes by matchId, writes ONE
roster file (not per-match sidecars -- this is a corpus census, not a
re-fetch of shotmaps already covered by fotmob_backfill_soccer). A date
already present in the roster's `dates_scanned` is skipped unless
force=True (resumable).

POLITENESS: 1 req/s between date-page fetches; ~24 calendar days worst case
(2026-06-11..07-04) = ~24 requests total, far under any reasonable budget.

HONESTY: this is a coverage census only -- no probability field, no Brier,
no gate gets scored from this file. n_finished_matches_total vs
n_finished_matches_captured (our 39) is reported for context in analysis 1's
writeup; the enrichment gate corpus itself never changes.

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; 1 req/s; resumable;
no data/registry write; no flag flip; never raises; no network in tests
(injected fetch_fn only).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_wc_finished_enum.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
ROSTER_PATH = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_wc_finished_roster.json"

# Tournament window, pre-declared in the LANE 3 brief -- inclusive.
TOURNAMENT_START = date(2026, 6, 11)
TOURNAMENT_END = date(2026, 7, 4)


def _date_range(start: date, end: date) -> List[str]:
    out: List[str] = []
    d = start
    while d <= end:
        out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out


def _is_finished(m: Dict[str, Any]) -> bool:
    st = m.get("status") or {}
    return bool(st.get("finished")) and not st.get("cancelled")


_WC_LEAGUE_MARKER = "world cup"


def _default_wc_leagues_for_date(date_str: str) -> List[dict]:
    """Raw matches?date= payload, filtered to leagues whose name contains
    "world cup" (case-insensitive) -- bypasses ingame_fotmob's league-
    flattening so the league name survives for this filter (see module
    docstring: an unfiltered scan pulls every league globally, ~1500+/day).
    [] on any failure -- never raises."""
    try:
        from domains.soccer.ingame_fotmob import _http_get_json, _MATCHES_URL
        payload = _http_get_json(_MATCHES_URL.format(date=date_str))
        if not isinstance(payload, dict):
            return []
        out: List[dict] = []
        for lg in payload.get("leagues") or []:
            if not isinstance(lg, dict):
                continue
            name = str(lg.get("name") or "")
            if _WC_LEAGUE_MARKER not in name.lower():
                continue
            out.extend(m for m in (lg.get("matches") or []) if isinstance(m, dict))
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("fotmob_wc_finished_enum: fetch failed for %s: %s", date_str, exc)
        return []


def scan_window(*, start: date = TOURNAMENT_START, end: date = TOURNAMENT_END,
                fetch_fn: Optional[Callable[[str], List[dict]]] = None,
                sleep_s: float = 1.0, budget: Optional[int] = None,
                existing_dates: Optional[List[str]] = None,
                force: bool = False) -> Dict[str, Any]:
    """Scan every date in [start, end] for FINISHED, WC-league-filtered
    FotMob matches. Returns {matches: [{id, home, away, date_str}],
    dates_scanned, n_requests, errors}. *fetch_fn* defaults to
    _default_wc_leagues_for_date (WC-filtered); tests inject their own list
    of already-filtered match dicts. *existing_dates* (from a prior roster)
    is skipped unless force=True -- resumable. *budget* caps NEW
    date-fetches this call. Never raises."""
    if fetch_fn is None:
        fetch_fn = _default_wc_leagues_for_date

    result: Dict[str, Any] = {"matches": [], "dates_scanned": [], "n_requests": 0, "errors": []}
    already = set(existing_dates or []) if not force else set()
    seen_ids: set = set()

    for ds in _date_range(start, end):
        if ds in already:
            continue
        if budget is not None and result["n_requests"] >= budget:
            break
        try:
            matches = fetch_fn(ds)
        except Exception as exc:  # noqa: BLE001 -- one bad date must not kill the scan
            result["errors"].append("%s: fetch failed: %s" % (ds, exc))
            result["n_requests"] += 1
            time.sleep(sleep_s)
            continue
        result["n_requests"] += 1
        result["dates_scanned"].append(ds)
        for m in matches:
            if not _is_finished(m):
                continue
            mid = m.get("id")
            if mid is None or mid in seen_ids:
                continue
            seen_ids.add(mid)
            result["matches"].append({
                "id": mid,
                "home": (m.get("home") or {}).get("name"),
                "away": (m.get("away") or {}).get("name"),
                "date_str": ds,
            })
        time.sleep(sleep_s)
    return result


def _load_roster(path: Path) -> Dict[str, Any]:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 -- a corrupt roster is an honest fresh start
        logger.debug("fotmob_wc_finished_enum: roster read failed: %s", exc)
    return {"matches": [], "dates_scanned": []}


def _atomic_write(path: Path, doc: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("fotmob_wc_finished_enum: roster write failed: %s", exc)


def build_roster(*, roster_path: Optional[Path] = None,
                 fetch_fn: Optional[Callable[[str], List[dict]]] = None,
                 sleep_s: float = 1.0, budget: Optional[int] = None,
                 force: bool = False, n_captured: Optional[int] = None) -> Dict[str, Any]:
    """Resumable census pass: merges a new scan_window() call into the
    existing roster file (additive, dedup by matchId), writes it back, and
    returns the merged doc. *n_captured* (our already-graded game count) is
    stamped into the doc for the honest coverage-ratio comparison -- never
    used to widen the gate corpus. Never raises."""
    path = Path(roster_path) if roster_path is not None else ROSTER_PATH
    prior = _load_roster(path)
    scan = scan_window(fetch_fn=fetch_fn, sleep_s=sleep_s, budget=budget,
                       existing_dates=prior.get("dates_scanned"), force=force)

    merged_ids = {m["id"] for m in prior.get("matches", [])}
    merged = list(prior.get("matches", []))
    for m in scan["matches"]:
        if m["id"] not in merged_ids:
            merged.append(m)
            merged_ids.add(m["id"])

    dates_scanned = sorted(set(prior.get("dates_scanned", [])) | set(scan["dates_scanned"]))
    doc = {
        "component": "fotmob_wc_finished_enum", "sport": "soccer_intl",
        "tournament_window": [TOURNAMENT_START.isoformat(), TOURNAMENT_END.isoformat()],
        "matches": merged, "dates_scanned": dates_scanned,
        "n_finished_matches_total": len(merged),
        "n_finished_matches_captured": n_captured,
        "errors": scan.get("errors", []),
        "honest_note": ("Coverage census only -- no probability/Brier field, no gate is "
                        "scored from this file. The enrichment-gate validation corpus stays "
                        "the 39 already-captured soccer_intl games; this roster answers a "
                        "separate coverage question (how many finished WC matches exist "
                        "tournament-wide) for future backfill budgeting."),
    }
    _atomic_write(path, doc)
    return doc


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    import glob as _glob
    n_captured = len(_glob.glob(str(_REPO_ROOT / "data" / "cache" / "ingame_grade"
                                     / "soccer_intl" / "KXWCGAME-*.jsonl")))
    doc = build_roster(n_captured=n_captured)
    print(json.dumps({k: v for k, v in doc.items() if k != "matches"}, indent=1, default=str))
    print("roster file: %s" % ROSTER_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ROSTER_PATH", "TOURNAMENT_START", "TOURNAMENT_END",
    "scan_window", "build_roster",
]

"""scripts.platformkit.ingame.fotmob_backfill_soccer -- LANE 2: FotMob xG
BACKFILL for the captured soccer_intl corpus (GATE A validation NOW, not
waiting on the forward flywheel).

THE GAP: GATE A needs enriched forward ticks, but domains.soccer.ingame_fotmob
only activates going forward (at restart) -- we hold ~39 ALREADY-CAPTURED
soccer_intl games (data/cache/ingame_grade/soccer_intl/KXWCGAME-*.jsonl) with
real tick series + resolvable outcomes, but only 5 live fotmob sidecars.
Wave-10 proved a FINISHED match's shotmap persists in full (every shot, real
minute) -- so one finished-match fetch reconstructs an as-of xG series per
game, no live polling needed.

METHOD (bounded, resumable, leak-free): per ticker, parse_wc_ticker -> resolve
both FIFA codes to real names via the SAME SoccerOutcomeResolver used by
enrichment_rows_soccer/soccer_outcome (xG matching never disagrees with
settlement) -> fetch_matches_for_date(date +/-1 day) -> match_to_fixture ->
ONE fetch_match_detail -> reconstruct snapshots at representative checkpoints
using the EXACT SAME asof_state_at the live poller uses (join logic
byte-identical between live and backfill).

RECONSTRUCTED MINUTE: a finished match has no live "current minute", so each
snapshot's cutoff_min is one of _CHECKPOINT_MINUTES (15/30/45/60/75/90),
coarser than live sampling but never leaking (asof_state_at still strictly
excludes any shot/event past cutoff_min). Each snapshot's synthetic fetch_ts
is spread across the REAL tick span (first..last tick ts) so real ticks have
eligible snapshots to as-of-join against.

PROVENANCE (binding -- never pooled with the forward channel): sidecars land
under data/domains/soccer_intl/fotmob_backfill/<matchId>.jsonl (SEPARATE from
fotmob_live/; the forward gate's default rows_fn never reads this dir), each
row tagged provenance="fotmob_finished_reconstruction". enrichment_rows_soccer
.build_rows gained an additive provenance kwarg selecting this dir; those rows
carry provenance="backfill_validation".

HONESTY CAVEAT (repeated in every validation artifact): reconstructed as-of xG
assumes the finished match's recorded shot minutes are accurate and ignores
any post-hoc xG revisions FotMob applies after settlement -- a coarser,
retrospective reconstruction, reported ONLY via a VALIDATION verdict
(data/domains/soccer_intl/enrichment_gate_validation.json), never the forward
verdict file.

POLITENESS: 1 req/s between HTTP calls; resumable (an existing sidecar is
skipped unless force=True); bounded to ~39 tickers (~78 requests worst case).

INVARIANTS: platformkit-only; <=300 LOC; ASCII only; no data/registry write;
no flag flip; never raises; never touches inplay_capture_loop.py.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_fotmob_backfill_soccer.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "soccer_intl"
BACKFILL_SIDECAR_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_backfill"

PROVENANCE_SIDECAR = "fotmob_finished_reconstruction"
PROVENANCE_ROWS = "backfill_validation"

# Representative as-of checkpoints spanning a 90-minute match; extra-time
# games (AET, e.g. KXWCGAME-26JUL01BELSEN) simply see their later checkpoints
# capped by asof_state_at's own strict cutoff (no shot past cutoff leaks in
# regardless of how far cutoff extends past 90).
_CHECKPOINT_MINUTES = (15.0, 30.0, 45.0, 60.0, 75.0, 90.0)


def _date_candidates(date: Any) -> List[str]:
    """A ticker's nominal date +/- 1 day, YYYYMMDD strings (mirrors
    SoccerOutcomeResolver.final_score's +/-1 day tolerance)."""
    out = []
    for delta in (0, -1, 1):
        try:
            out.append((date + timedelta(days=delta)).strftime("%Y%m%d"))
        except Exception:  # noqa: BLE001
            continue
    return out


def _resolve_ticker_names(ticker: str, resolver: Any):
    """(home_name, away_name) via the injected resolver's own code index, or
    None if unresolvable -- never a guess (mirrors enrichment_rows_soccer)."""
    try:
        from scripts.platformkit.ingame.soccer_outcome import parse_wc_ticker, _resolve_code
        parsed = parse_wc_ticker(ticker)
        if parsed is None or not resolver.available:
            return None
        _date, code_a, code_b = parsed
        name_a = _resolve_code(code_a, resolver._name_index)  # noqa: SLF001
        name_b = _resolve_code(code_b, resolver._name_index)  # noqa: SLF001
        if name_a is None or name_b is None:
            return None
        return (parsed[0], name_a, name_b)
    except Exception as exc:  # noqa: BLE001
        logger.debug("fotmob_backfill_soccer: ticker resolve failed %s: %s", ticker, exc)
        return None


def find_finished_match(ticker: str, resolver: Any, *,
                        fetch_matches: Callable[[str], List[dict]],
                        match_to_fixture_fn: Callable[..., Optional[dict]]
                        ) -> Optional[dict]:
    """Resolve *ticker* -> its FotMob finished-match record (dict with an
    'id'), scanning date +/-1 day. None if unresolvable or ambiguous --
    never a guess."""
    resolved = _resolve_ticker_names(ticker, resolver)
    if resolved is None:
        return None
    date, home_name, away_name = resolved
    for ds in _date_candidates(date):
        try:
            matches = fetch_matches(ds)
        except Exception:  # noqa: BLE001
            continue
        if not matches:
            continue
        fx = match_to_fixture_fn(matches, home_name, away_name)
        if fx is not None:
            return fx
    return None


def reconstruct_snapshots(detail: dict, match_id: Any, home: str, away: str,
                          tick_timestamps: List[str], *,
                          asof_fn: Callable[[dict, float], Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    """One row per _CHECKPOINT_MINUTES entry, each an asof_fn(detail, cutoff)
    snapshot tagged with provenance + match/team fields + a synthetic
    fetch_ts spread across tick_timestamps (sorted) so the enrichment
    producer's as-of join has eligible snapshots. If tick_timestamps is
    empty, falls back to synthetic ISO timestamps (still monotonic, but the
    join will then honestly find nothing to pair against -- never fabricated
    ticks). Never raises."""
    rows: List[Dict[str, Any]] = []
    try:
        ts_sorted = sorted(t for t in tick_timestamps if t)
        n_ck = len(_CHECKPOINT_MINUTES)
        for i, cutoff in enumerate(_CHECKPOINT_MINUTES):
            if ts_sorted:
                # Spread checkpoints evenly across the REAL tick span so a
                # tick can find a <=-eligible snapshot; last checkpoint gets
                # the final tick timestamp (never a future-of-corpus stamp).
                idx = min(int(i * len(ts_sorted) / n_ck), len(ts_sorted) - 1)
                fetch_ts = ts_sorted[idx]
            else:
                fetch_ts = (datetime(1970, 1, 1, tzinfo=timezone.utc)
                            + timedelta(minutes=cutoff)).isoformat()
            row = asof_fn(detail, cutoff)
            row.update({
                "match_id": match_id, "home": home, "away": away,
                "fetch_ts": fetch_ts, "provenance": PROVENANCE_SIDECAR,
            })
            rows.append(row)
    except Exception as exc:  # noqa: BLE001 -- a reconstruction failure yields fewer rows
        logger.debug("fotmob_backfill_soccer: reconstruct failed for %s: %s", match_id, exc)
    return rows


def backfill_sidecar_path(match_id: Any, *, out_dir: Optional[Path] = None) -> Path:
    return (out_dir or BACKFILL_SIDECAR_DIR) / f"{match_id}.jsonl"


def write_sidecar(match_id: Any, rows: List[Dict[str, Any]], *,
                  out_dir: Optional[Path] = None) -> None:
    """Overwrite (not append) -- a backfill sidecar is a full reconstruction
    from one finished-match fetch, not an incremental live stream. Best-
    effort; never raises."""
    try:
        d = out_dir or BACKFILL_SIDECAR_DIR
        d.mkdir(parents=True, exist_ok=True)
        path = backfill_sidecar_path(match_id, out_dir=d)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True, default=str) + "\n")
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001
        logger.debug("fotmob_backfill_soccer: write_sidecar failed for %s: %s", match_id, exc)


def _tick_timestamps(grade_file: Path) -> List[str]:
    out: List[str] = []
    try:
        with grade_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(rec, dict) and rec.get("ts"):
                    out.append(str(rec["ts"]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("fotmob_backfill_soccer: tick read failed %s: %s", grade_file, exc)
    return out


def backfill_all(*, grade_dir: Optional[Path] = None, out_dir: Optional[Path] = None,
                 resolver: Optional[Any] = None, force: bool = False,
                 sleep_s: float = 1.0, budget: Optional[int] = None,
                 fetch_matches: Optional[Callable[[str], List[dict]]] = None,
                 fetch_detail: Optional[Callable[[Any], Optional[dict]]] = None,
                 match_to_fixture_fn: Optional[Callable[..., Optional[dict]]] = None,
                 asof_fn: Optional[Callable[[dict, float], Dict[str, Any]]] = None
                 ) -> Dict[str, Any]:
    """Bounded, resumable backfill pass over every KXWCGAME-* grade file.
    Skips a ticker whose matchId sidecar already exists unless force=True.
    *budget* caps the number of NEW (non-skipped) matches fetched this call
    (politeness/testability). Returns a summary dict; never raises."""
    gdir = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    odir = Path(out_dir) if out_dir is not None else BACKFILL_SIDECAR_DIR
    summary = {"n_tickers": 0, "n_resolved": 0, "n_fetched": 0, "n_written": 0,
              "n_skipped_existing": 0, "n_unresolved": 0, "errors": []}
    try:
        if fetch_matches is None or fetch_detail is None or match_to_fixture_fn is None or asof_fn is None:
            from domains.soccer.ingame_fotmob import (
                fetch_matches_for_date as _fm, fetch_match_detail as _fd,
                match_to_fixture as _mtf, asof_state_at as _asof,
            )
            fetch_matches = fetch_matches or _fm
            fetch_detail = fetch_detail or _fd
            match_to_fixture_fn = match_to_fixture_fn or _mtf
            asof_fn = asof_fn or _asof

        if resolver is None:
            from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
            resolver = SoccerOutcomeResolver()

        if not gdir.is_dir():
            return summary

        for gf in sorted(gdir.glob("KXWCGAME-*.jsonl")):
            summary["n_tickers"] += 1
            ticker = gf.stem
            if budget is not None and summary["n_fetched"] >= budget:
                break
            fx = find_finished_match(ticker, resolver, fetch_matches=fetch_matches,
                                     match_to_fixture_fn=match_to_fixture_fn)
            if fx is None:
                summary["n_unresolved"] += 1
                continue
            summary["n_resolved"] += 1
            match_id = fx.get("id")
            sidecar = backfill_sidecar_path(match_id, out_dir=odir)
            if sidecar.is_file() and not force:
                summary["n_skipped_existing"] += 1
                continue
            try:
                detail = fetch_detail(match_id)
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append("%s: detail fetch failed: %s" % (ticker, exc))
                continue
            summary["n_fetched"] += 1
            time.sleep(sleep_s)
            if detail is None:
                summary["errors"].append("%s: no detail for matchId=%s" % (ticker, match_id))
                continue
            home = (fx.get("home") or {}).get("name")
            away = (fx.get("away") or {}).get("name")
            ticks = _tick_timestamps(gf)
            rows = reconstruct_snapshots(detail, match_id, home, away, ticks, asof_fn=asof_fn)
            if rows:
                write_sidecar(match_id, rows, out_dir=odir)
                summary["n_written"] += 1
    except Exception as exc:  # noqa: BLE001 -- a pass failure yields an honest partial summary
        summary["errors"].append("backfill_all failed: %s" % exc)
    return summary


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    summary = backfill_all()
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_GRADE_DIR", "BACKFILL_SIDECAR_DIR", "PROVENANCE_SIDECAR", "PROVENANCE_ROWS",
    "find_finished_match", "reconstruct_snapshots", "backfill_sidecar_path",
    "write_sidecar", "backfill_all",
]

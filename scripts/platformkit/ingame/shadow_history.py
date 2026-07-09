"""scripts.platformkit.ingame.shadow_history -- DURABLE shadow-evidence APPEND store (LANE 2).

The four model_prob_{wnba,nba,tennis,sp}_shadow fields inplay_capture_loop computes every
tick currently persist ONLY inside data/cache/ingame_grade/_capture_heartbeat.json, which is
OVERWRITTEN (not appended) each cycle -- so a promotion decision ("has this shadow tracked
the market for N games?") has no history to look back at, only this instant's snapshot.

This module is the fix: append_shadow_rows(rows, now) takes the SAME per-game row dicts the
capture loop already builds (heartbeat's "games" list) and appends the ones that carry at
least one non-absent shadow key to
  data/cache/ingame_shadow_history/<sport>/<date>.jsonl
one compact JSON record per line (ts, sport, game_id, reason, model_prob, the 4 shadow
fields, market devig if present). ATOMIC (true append, no full-file read), FAIL-OPEN (any
exception is swallowed -- this is measurement plumbing, never allowed to sink a caller),
and BOUNDED (skips writing once a sport/date file already exceeds MAX_BYTES_PER_DAY, so a
runaway cycle can never balloon disk).

HONESTY (binding): measurement only -- no $ / roi / pnl / edge field anywhere. A row with
every shadow field None is DROPPED (nothing to accrue); "no shadow yet" is silence, not a
fabricated zero.

INVARIANTS: build only under scripts/platformkit/ingame/; <=150 LOC; ASCII only; no network
at import; never edits inplay_capture_loop.py itself (the caller wires ONE hook there).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_shadow_history.py -q
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/shadow_history.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HISTORY_DIR = _REPO_ROOT / "data" / "cache" / "ingame_shadow_history"

# The shadow keys inplay_capture_loop writes onto each per-game row (see
# _wnba_shadow/_nba_shadow/_nba_ladder_shadow/_tennis_shadow/_sp_shadow in that file).
# A row is history-worthy iff at least one of these is not None. model_prob_nba_ladder_
# shadow ADDED (mechanism-ladder base spec, frozen coefficients) alongside the existing
# model_prob_nba_shadow (NBARepricer) -- additive, forward capture now grades both.
SHADOW_KEYS: List[str] = [
    "model_prob_wnba_shadow", "model_prob_nba_shadow", "model_prob_nba_ladder_shadow",
    "model_prob_tennis_shadow", "model_prob_sp_shadow",
]

# ponytail: single-writer daemon, no multi-process race to guard -- a plain size check
# before an append is enough; add a lock only if a second writer ever appears.
MAX_BYTES_PER_DAY = 50 * 1024 * 1024  # 50MB/day/sport


def _utc(now: Optional[datetime]) -> datetime:
    d = now if now is not None else datetime.now(timezone.utc)
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


def _has_shadow(row: Dict[str, Any]) -> bool:
    return any(row.get(k) is not None for k in SHADOW_KEYS)

def _record(row: Dict[str, Any], ts: str) -> Dict[str, Any]:
    rec = {"ts": ts, "sport": row.get("sport"), "game_id": row.get("game_id"),
           "reason": row.get("reason"), "model_prob": row.get("model_prob")}
    for k in SHADOW_KEYS:
        rec[k] = row.get(k)
    devig = row.get("devigged_price")
    if devig is not None:
        rec["devigged_price"] = devig
    return rec


def _day_path(sport: str, day: str, base: Path) -> Path:
    return base / str(sport).lower() / ("%s.jsonl" % day)


def append_shadow_rows(rows: Iterable[Dict[str, Any]], now: Optional[datetime] = None,
                       history_dir: Optional[Path] = None) -> int:
    """Append every shadow-carrying row in *rows* to its sport/date jsonl. Returns rows written.

    Non-shadow rows (every SHADOW_KEYS entry is None/absent) are filtered out silently --
    they have nothing to accrue. Fail-open: a bad *rows* item, an unwritable directory, or
    any I/O error is logged and skipped, never raised (this must never sink the caller's
    heartbeat write). Size-bounded per sport/day (MAX_BYTES_PER_DAY); once a file is already
    over the bound, further rows for that sport/day are dropped (logged once per call).
    """
    nowdt = _utc(now)
    ts = nowdt.strftime("%Y-%m-%dT%H:%M:%SZ")
    day = nowdt.strftime("%Y-%m-%d")
    base = Path(history_dir) if history_dir is not None else DEFAULT_HISTORY_DIR
    written = 0
    by_path: Dict[Path, List[str]] = {}
    try:
        for row in rows or []:
            if not isinstance(row, dict) or not _has_shadow(row):
                continue
            sport = str(row.get("sport") or "unknown")
            path = _day_path(sport, day, base)
            by_path.setdefault(path, []).append(json.dumps(_record(row, ts), ensure_ascii=True))
    except Exception as exc:  # noqa: BLE001 -- a bad rows iterable never raises to the caller
        logger.warning("shadow_history: failed scanning rows: %s", exc)
        return 0
    for path, lines in by_path.items():
        try:
            written += _append_bounded(path, lines)
        except Exception as exc:  # noqa: BLE001 -- one bad file never blocks the others
            logger.warning("shadow_history: append failed for %s: %s", path, exc)
    return written


def _append_bounded(path: Path, lines: List[str]) -> int:
    """True append (no full-file read) of *lines*, dropped once *path* exceeds the bound."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        size = path.stat().st_size if path.is_file() else 0
    except OSError:
        size = 0
    if size >= MAX_BYTES_PER_DAY:
        logger.warning("shadow_history: %s over size bound, dropping %d row(s)",
                       path, len(lines))
        return 0
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")
    return len(lines)


def demo() -> None:  # pragma: no cover -- manual smoke, not part of the test suite
    """Tiny self-check: a mixed rows list appends only the shadow-carrying ones."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rows = [
            {"sport": "mlb", "game_id": "g1", "reason": "ok",
             "model_prob_sp_shadow": 0.61},
            {"sport": "mlb", "game_id": "g2", "reason": "no_live_state"},
        ]
        n = append_shadow_rows(rows, history_dir=Path(td))
        assert n == 1, "expected exactly 1 shadow-carrying row appended, got %d" % n
        out = _day_path("mlb", datetime.now(timezone.utc).strftime("%Y-%m-%d"), Path(td))
        assert out.is_file() and len(out.read_text(encoding="utf-8").strip().splitlines()) == 1
    print("shadow_history demo OK")


if __name__ == "__main__":  # pragma: no cover
    demo()


__all__ = ["append_shadow_rows", "SHADOW_KEYS", "MAX_BYTES_PER_DAY", "DEFAULT_HISTORY_DIR"]

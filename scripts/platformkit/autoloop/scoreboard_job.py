"""scripts.platformkit.autoloop.scoreboard_job -- M24: weekly cadence wrapper
around scripts.platformkit.reports.weekly_scoreboard. Renders the CURRENT ISO
week's one-page scoreboard (docs/research/scoreboard/YYYY-Www.md) once per
week. write_week() itself is already an idempotent overwrite (a same-week
rerun produces the identical file path), so this job's own job is only to
avoid a needless re-render within the same week -- not to guard corruption.

WATERMARK: watermarks[STATE_KEY] holds the last-rendered ISO week label
(e.g. "2026-W29"). A tick whose current week matches the stored label is
skipped (already rendered this week); any other week (a fresh week, or none
stored yet) fires write_week() and re-arms the watermark to the new label --
a new week re-arms it, same own-success stamp-on-success convention as
M20/M22/M23. A raise from write_week() propagates uncaught (never caught
here) and is isolated one level up by maintenance_templates.run_all's own
try/except, same as every other job in the table -- no watermark is written
on that path, so the next tick (still the same week) retries.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; never writes
data/registry/; never flips a flag; no $/ROI/edge claims (weekly_scoreboard's
own docstring already enforces this at render time).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/autoloop/test_scoreboard_job.py -q
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from scripts.platformkit.reports import weekly_scoreboard as WS

STATE_KEY = "M24_weekly_scoreboard"


def _default_current_week() -> Tuple[int, int, str]:
    return WS.current_week()


def run_scoreboard(watermarks: Dict[str, Any], *,
                   current_week_fn: Optional[Callable[[], Tuple[int, int, str]]] = None,
                   write_fn: Optional[Callable[[int, int], Any]] = None) -> Dict[str, Any]:
    """One M24 tick: render the current ISO week's scoreboard iff not already
    rendered this week (watermark = last-rendered week label)."""
    year, week, label = (current_week_fn or _default_current_week)()
    prior = (watermarks.get(STATE_KEY) or {}).get("week")
    if prior == label:
        return {"status": "skipped", "week": label}
    out_path = (write_fn or WS.write_week)(year, week)
    watermarks[STATE_KEY] = {"week": label, "path": str(out_path)}
    return {"status": "ran", "week": label, "path": str(out_path)}


__all__ = ["run_scoreboard", "STATE_KEY"]

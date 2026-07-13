"""Per-file test for scripts.platformkit.autoloop.scoreboard_job.

Acceptance criteria:
1. Same ISO week as the stored watermark -> skip, write_fn not called.
2. New ISO week (watermark unset or a different label) -> write_fn(year, week)
   called, watermark re-armed to the new label.
3. watermarks dict is mutated in place (same convention every other
   maintenance job in this package uses).
4. _default_current_week delegates to weekly_scoreboard.current_week() (no
   duplicated ISO-week math here).
5. Registration: weekly_scoreboard_cadence appears in maintenance_templates._JOB_TABLE.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/autoloop/test_scoreboard_job.py -q
"""
from __future__ import annotations

from scripts.platformkit.autoloop import scoreboard_job as SJ


def test_same_week_skips_no_write_call():
    calls = []
    watermarks = {SJ.STATE_KEY: {"week": "2026-W28", "path": "x.md"}}
    out = SJ.run_scoreboard(
        watermarks,
        current_week_fn=lambda: (2026, 28, "2026-W28"),
        write_fn=lambda y, w: calls.append((y, w)),
    )
    assert out == {"status": "skipped", "week": "2026-W28"}
    assert calls == []


def test_new_week_fires_and_rearms_watermark():
    calls = []
    watermarks = {SJ.STATE_KEY: {"week": "2026-W28", "path": "old.md"}}
    out = SJ.run_scoreboard(
        watermarks,
        current_week_fn=lambda: (2026, 29, "2026-W29"),
        write_fn=lambda y, w: calls.append((y, w)) or "docs/research/scoreboard/2026-W29.md",
    )
    assert out["status"] == "ran"
    assert out["week"] == "2026-W29"
    assert calls == [(2026, 29)]
    assert watermarks[SJ.STATE_KEY] == {"week": "2026-W29", "path": "docs/research/scoreboard/2026-W29.md"}


def test_missing_watermark_treated_as_due():
    calls = []
    watermarks: dict = {}
    out = SJ.run_scoreboard(
        watermarks,
        current_week_fn=lambda: (2026, 29, "2026-W29"),
        write_fn=lambda y, w: calls.append((y, w)) or "out.md",
    )
    assert out["status"] == "ran"
    assert calls == [(2026, 29)]
    assert watermarks[SJ.STATE_KEY]["week"] == "2026-W29"


def test_default_current_week_fn_delegates_to_weekly_scoreboard(monkeypatch):
    from scripts.platformkit.reports import weekly_scoreboard as WS
    monkeypatch.setattr(WS, "current_week", lambda: (2031, 5, "2031-W05"))
    assert SJ._default_current_week() == (2031, 5, "2031-W05")


def test_registered_in_job_table():
    from scripts.platformkit.autoloop import maintenance_templates as MT
    keys = [row[0] for row in MT._JOB_TABLE]
    assert "weekly_scoreboard_cadence" in keys
    row = next(r for r in MT._JOB_TABLE if r[0] == "weekly_scoreboard_cadence")
    assert row[1] == "scripts.platformkit.autoloop.scoreboard_job"
    assert row[2] == "run_scoreboard"
    assert "watermarks" in row[3]

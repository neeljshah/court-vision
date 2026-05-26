# Daily Workflow — Cron / Task Scheduler

`scripts/daily_workflow.py` is a single Python entry point that wraps the
two operational stages a human would otherwise run by hand each day:

| Stage   | When  | What it does |
|---------|-------|--------------|
| evening | ~7pm ET (after pregame predictions land) | snapshot today's recs → refresh operator dashboard cache → fire info alert |
| morning | ~8am ET (after games settle overnight)    | settle yesterday's snapshot → reconcile vs box score → report W/L/ROI → refresh dashboard → fire info alert |
| all     | catch-up after a missed day               | runs evening then morning back-to-back |

The orchestrator is intentionally side-effect-isolated: every step is
exception-trapped, a failed step never aborts the rest, and a critical
alert fires per failed step via the R21_N3 layered alert path (vault
markdown + critical stack JSON + Discord if configured).

## CLI quick reference

```bash
# Run a stage (real side effects):
python scripts/daily_workflow.py evening
python scripts/daily_workflow.py morning
python scripts/daily_workflow.py all

# Inspect what would run without writing anything:
python scripts/daily_workflow.py --dry-run evening
python scripts/daily_workflow.py --dry-run morning

# Print the last N days of run history (from the markdown log):
python scripts/daily_workflow.py --summary --days 7

# JSON output (for piping into jq):
python scripts/daily_workflow.py evening --json
python scripts/daily_workflow.py --summary --json
```

Exit codes
- `0` — every step completed without raising
- `1` — at least one step failed (the rest still ran)
- `2` — bad CLI usage

## Where artifacts land

| Artifact | Path |
|----------|------|
| Append-only run log | `vault/Improvements/daily_workflow.md` |
| Rec snapshot (evening) | `data/cache/rec_tracker/rec_snapshot_<date>.json` |
| Settled rec parquet (morning) | `data/cache/rec_tracker/rec_settled.parquet` |
| Operator dashboard HTML snapshot | `data/cache/operator_dashboard_snapshot.html` |
| Reconcile JSON (morning) | `data/cache/settlement_reconciliation_<date>.json` |
| Alert critical stack | `data/cache/alerts/critical_<date>.json` |
| Alert vault log | `vault/Improvements/alerts.md` |

## Reading the log

```bash
python scripts/daily_workflow.py --summary --days 14
```

prints one row per run with the stage, duration, fail count, and
per-step OK/FAIL grid. Use `--json` to machine-parse it.

The markdown file itself is human-readable — each run looks like:

```
## 2026-05-26T19:00:12Z  stage=evening
- duration: 12.4s
- critical_failures: 0
- steps:
  - snapshot_recs: OK (8.1s)
  - refresh_dashboard: OK (4.2s)
  - alert_evening: OK (0.1s)
```

## Windows Task Scheduler

Two tasks — one per stage. Both use `Conda` to enter the `basketball_ai`
env and run the orchestrator from the project root.

Save the XML below as `daily_workflow_evening.xml`, then import:

```cmd
schtasks /Create /TN "CourtVision_Evening" /XML daily_workflow_evening.xml
```

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>CourtVision evening recs snapshot + dashboard refresh.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-26T19:00:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      <Enabled>true</Enabled>
    </CalendarTrigger>
  </Triggers>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT15M</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>C:\Users\neelj\miniconda3\condabin\conda.bat</Command>
      <Arguments>run -n basketball_ai python C:\Users\neelj\nba-ai-system\scripts\daily_workflow.py evening</Arguments>
      <WorkingDirectory>C:\Users\neelj\nba-ai-system</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

For the morning task: copy the file, change `StartBoundary` to e.g.
`2026-05-26T08:00:00` and swap `evening` to `morning` in `<Arguments>`.

Verify both registered:

```cmd
schtasks /Query /TN "CourtVision_Evening" /V
schtasks /Query /TN "CourtVision_Morning" /V
```

Run on demand (skips the schedule):

```cmd
schtasks /Run /TN "CourtVision_Evening"
```

## crontab (Linux / WSL / macOS)

Add two lines to `crontab -e`. Replace `/home/neelj/nba-ai-system` with
your checkout path and `/home/neelj/miniconda3/bin/conda` with the
conda binary.

```cron
# CourtVision daily workflow — times are LOCAL (set TZ at the top if needed).
TZ=America/New_York

# Evening: 7:00pm ET, every day
0 19 * * * cd /home/neelj/nba-ai-system && /home/neelj/miniconda3/bin/conda run -n basketball_ai python scripts/daily_workflow.py evening >> vault/Improvements/daily_workflow.cron.log 2>&1

# Morning: 8:00am ET, every day
0 8  * * * cd /home/neelj/nba-ai-system && /home/neelj/miniconda3/bin/conda run -n basketball_ai python scripts/daily_workflow.py morning >> vault/Improvements/daily_workflow.cron.log 2>&1
```

`>> ...cron.log 2>&1` captures stdout/stderr from cron itself. The
durable record per run is the markdown log written by the orchestrator
— the cron log is just for debugging if a stage never fires at all.

## Verifying it's working

After install, on the next scheduled time:

```bash
# Look at the most recent runs:
python scripts/daily_workflow.py --summary --days 1

# Spot-check the artifacts landed:
ls -lt data/cache/rec_tracker/        # snapshot files
ls -lt data/cache/operator_dashboard_snapshot.html
ls -lt data/cache/alerts/             # any critical stacks?
tail -40 vault/Improvements/daily_workflow.md
```

If a step started raising, the orchestrator will have written a
`critical_<date>.json` to `data/cache/alerts/` AND a `[CRITICAL]` line
to `vault/Improvements/alerts.md` — both grep-able from a phone via
the operator dashboard.

## Catch-up after a missed day

If neither cron fired for a whole day (laptop closed, on a flight, …),
the morning of the next day, run:

```bash
python scripts/daily_workflow.py all
```

This drives the evening stage for today AND the morning stage for
yesterday in one invocation. Each writes its own log entry.

## Safety guarantees

- `--dry-run` writes **nothing** — vault log, snapshot file, dashboard
  cache, and alert paths are all skipped.
- The orchestrator NEVER places real bets — it only reads from the
  prediction cache + ledger and writes operator artifacts.
- Subprocess invocations are list-form (no `shell=True`), so there's
  no shell-injection surface even if the schedule is fed a malformed
  date override.
- Logging is append-only and idempotent: re-running an evening on the
  same date overwrites the snapshot file (deterministic name) but
  always appends a fresh log entry so you have an audit trail.

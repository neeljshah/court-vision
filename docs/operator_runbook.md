# Operator Runbook

One-page guide to driving the production betting system day-to-day. Open this
when you sit down in the morning; you should not need any other doc to get
through a normal slate.

Maintained by R32_Y7. Last refresh: 2026-05-26.

---

## TL;DR

1. **Every morning**: open `vault/MORNING.md` (auto-generated nightly).
2. **Cron drives the day**: `scripts/daily_workflow.py evening` runs at 7pm ET,
   `scripts/daily_workflow.py morning` runs at 8am ET.
3. **Dashboard**: `python scripts/mobile_html_server.py --port 8766`, then
   browse `http://localhost:8766/operator`.
4. **Alerts**: tail `vault/Improvements/alerts.md` — everything urgent lands there.
5. **Place bets**: `python scripts/place_bet.py --player ... --stat ... --line ... --side ... --book ... --odds ... --stake ...`.

Everything below is detail you only need when something deviates from the happy
path.

---

## 1. Architecture (ASCII)

```
                                 +---------------------------------+
                                 |  scrapers (always-on daemons)   |
                                 |   - nba_injury_report_scraper   |
                                 |   - fetch_live_prop_lines       |
                                 |   - nba_lineup_daemon           |
                                 |   - clv_tracker_daemon          |
                                 |   - middle_finder_daemon        |
                                 |   - line_move_detector          |
                                 |   - bankroll_monitor_daemon     |
                                 +-----------------+---------------+
                                                   |
                                                   v
                          +------------------------+------------------------+
                          |     orchestrator: daily_workflow.py             |
                          |     (cron: evening @ 7pm, morning @ 8am)        |
                          +-----+----------+--------+--------+-------+------+
                                |          |        |        |       |
              +-----------------+          |        |        |       +----------------+
              v                            v        v        v                        |
  +-------------------------+   +----------+--+  +--+------+  +-----------+           |
  | predictions_cache_*.par |-->| live_rec_   |->| ledger  |->| settle    |--> CLV    |
  | (m2_family + prop)      |   | engine.py   |  | _.csv   |  | _daemon   |    track  |
  +-------------------------+   +-------------+  +---------+  +-----------+           |
                                       |              ^                               |
                                       v              | place_bet.py                  |
                                +-------------+       |                               |
                                | operator    |-------+                               |
                                | dashboard   |<--------- alerts.md <-----------------+
                                | /operator   |
                                +-------------+
                                       ^
                                       |
                                +-------------+         +-------------------+
                                | MORNING.md  |<--------| nightly cleanup +  |
                                +-------------+         | drift + reconcile  |
                                                        +-------------------+
```

Daemons feed the prediction caches and lines. The orchestrator drives the
recommendation engine and writes a daily snapshot. The operator reads
`/operator` + `MORNING.md`, picks bets, runs `place_bet.py`, and the post-game
settle path closes the loop into CLV.

---

## 2. Daily timeline (Eastern Time)

| Time      | What runs                                            | What to check                       |
|-----------|------------------------------------------------------|-------------------------------------|
| Continuous | All 14 daemons (`scripts/daemon_registry.json`)     | `daemon_watchdog.py --once`         |
| Continuous | `nba_injury_report_scraper.py` (every ~15 min)      | `data/cache/nba_injuries_<date>.parquet` |
| 7:00 pm   | `daily_workflow.py evening`                          | `vault/Improvements/daily_workflow.md` |
| 7:00 pm   | live_rec_tracker `--snapshot` (today's recs)         | `data/cache/rec_tracker/rec_snapshot_<date>.json` |
| 7:00 pm   | Dashboard cache refreshed                            | `data/cache/operator_dashboard_snapshot.html` |
| Game time | Operator places bets via `place_bet.py`              | `data/pnl_ledger.csv` row appended  |
| Post game | `auto_settle_daemon` settles bets from quarter-box   | ledger row goes `pending` -> `won/lost/push` |
| 2:00 am   | `nightly_cleanup.py --commit`                        | `data/cache/nightly_cleanup_<date>.json` |
| 2:00 am   | `ledger_insurance.py --backup`                       | `data/backups/pnl_ledger.csv.<date>.gz` |
| 2:15 am   | `feature_drift_detector.py`                          | `data/cache/drift_today.json`       |
| 8:00 am   | `daily_workflow.py morning`                          | `vault/MORNING.md` regenerated      |
| 8:00 am   | `live_rec_tracker --settle <yesterday>`              | `data/cache/rec_tracker/rec_settled.parquet` |
| 8:00 am   | `reconcile_settlements.py --days 1`                  | `data/cache/reconcile_<date>.json`  |

If a row is missing from the table above, the cron probably did not fire —
check Task Scheduler / cron logs first, then `vault/Improvements/alerts.md`.

---

## 3. Files to open (operator questions)

| Question | File to open |
|----------|--------------|
| "What should I bet today?" | `vault/MORNING.md` (top section: tonight's ranked recs) |
| "What does the system see right now?" | `http://localhost:8766/operator` |
| "Did yesterday's recs win?" | `python scripts/live_rec_tracker.py --report --days 7` |
| "Is anything broken?" | `vault/Improvements/alerts.md` (newest at top) |
| "Are settlements correct?" | `data/cache/reconcile_<yesterday>.json` |
| "Have features drifted?" | `data/cache/drift_today.json` |
| "Is my ledger backed up?" | `python scripts/ledger_insurance.py --list` |
| "Are the daemons alive?" | `python scripts/daemon_watchdog.py --once` |
| "What changed in the last batch?" | `git log --oneline -20` + `vault/Improvements/Tracker Improvements Log.md` |
| "What's the current bankroll?" | `data/cache/bankroll_state.json` |

---

## 4. Cron setup (copy-paste)

### Windows Task Scheduler (XML)

Save as `nba_evening.xml`, then `schtasks /Create /XML nba_evening.xml /TN "NBA Evening Workflow"`.

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-26T19:00:00</StartBoundary>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
      <Enabled>true</Enabled>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>C:\Users\neelj\miniconda3\envs\basketball_ai\python.exe</Command>
      <Arguments>scripts/daily_workflow.py evening</Arguments>
      <WorkingDirectory>C:\Users\neelj\nba-ai-system</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

Duplicate the file for 8:00 am with `--Arguments>scripts/daily_workflow.py morning`.

### Linux crontab

```cron
# m h dom mon dow command  (all times America/New_York)
0 19 * * * cd /workspace/nba-ai-system && python scripts/daily_workflow.py evening >> logs/daily_workflow.log 2>&1
0 8  * * * cd /workspace/nba-ai-system && python scripts/daily_workflow.py morning >> logs/daily_workflow.log 2>&1
0 2  * * * cd /workspace/nba-ai-system && python scripts/nightly_cleanup.py --commit >> logs/nightly_cleanup.log 2>&1
5 2  * * * cd /workspace/nba-ai-system && python scripts/ledger_insurance.py --backup --keep 60 >> logs/ledger_backup.log 2>&1
15 2 * * * cd /workspace/nba-ai-system && python scripts/feature_drift_detector.py --out data/cache/drift_today.json >> logs/drift.log 2>&1
* * * * * cd /workspace/nba-ai-system && python scripts/daemon_watchdog.py --once >> logs/watchdog.log 2>&1
```

### Always-on (run once at boot)

```bash
# Dashboard HTTP server (serves /operator)
nohup python scripts/mobile_html_server.py --port 8766 > logs/mobile_html.log 2>&1 &

# Injury feed (interval-controlled internally)
nohup python scripts/nba_injury_report_scraper.py --daemon > logs/injury_scraper.log 2>&1 &

# Live recommendation engine ad-hoc (manual when slate changes mid-day)
python scripts/live_recommendation_engine.py --bankroll 1000 --top 10
```

---

## 5. Common operations

### Enable the multitask-MLP m2_family path

```bash
# Linux / mac
export M2_FAMILY_USE_MLP=1
python scripts/live_recommendation_engine.py --bankroll 1000 --top 10
```

```powershell
# Windows
$env:M2_FAMILY_USE_MLP = '1'
python scripts/live_recommendation_engine.py --bankroll 1000 --top 10
```

Default is the multi5 ensemble at `data/models/m2_family/`. With the env var
set, it loads `data/models/m2_family_mlp/` instead. Unset the var to revert.

### Run live recommendations on-demand

```bash
python scripts/live_recommendation_engine.py \
  --bankroll 1000 --top 10 --min-edge 0.05 \
  --exclude-books PP
```

### Restore a ledger backup

```bash
# Inspect
python scripts/ledger_insurance.py --list
python scripts/ledger_insurance.py --verify --date 2026-05-26

# Dry-run (always do this first)
python scripts/ledger_insurance.py --restore 2026-05-26

# Commit
python scripts/ledger_insurance.py --restore 2026-05-26 --commit
```

The pre-restore live file is preserved as `pnl_ledger.csv.pre_restore_<ts>`
in `data/`.

### Void a DNP settlement

```bash
# Identify mismatch
python scripts/reconcile_settlements.py --days 3 --out data/cache/reconcile.json
# Look for "player_dnp_but_settled" rows -> use bet_id with the void tool
# (the void path lives inside auto_settle_daemon; manually edit the ledger
# row's status to 'void' then re-run reconcile to confirm clean.)
```

### Recover a line_killed bet

```bash
# List all killed bets
python scripts/recover_line_killed.py --list

# Refund a specific bet (idempotent)
python scripts/recover_line_killed.py --refund <bet_id>

# Refund every line_killed older than 24h (dry-run first)
python scripts/recover_line_killed.py --refund-all
python scripts/recover_line_killed.py --refund-all --commit

# Try to replace with a fresh line at the same threshold
python scripts/recover_line_killed.py --reprice <bet_id>
```

### Refresh the drift report

```bash
python scripts/feature_drift_detector.py --features all --current-days 14 \
  --out data/cache/drift_today.json
```

Status will be `OK` or `BLOCKED` with a reason string and per-feature
`stable / drift_minor / drift_major` classes.

---

## 6. Incident response

### "A daemon died"

```bash
# 1. Identify
python scripts/daemon_watchdog.py --once
# 2. Watchdog auto-restarts if heartbeat / process check fails; manual restart:
#    look up restart_cmd in scripts/daemon_registry.json and run it.
# 3. Confirm heartbeat refreshes:
ls -la data/cache/daemon_heartbeats/
```

If a daemon restarts more than 3 times in a rolling hour the watchdog stops
restarting it and fires a critical alert — investigate before un-rate-limiting.

### "Alert spam in alerts.md"

R26_S5 alert dedup is already in place. If a single check is still flooding:

```bash
# Look for the offending alert source
tail -200 vault/Improvements/alerts.md | grep "source="
# Confirm dedup window is sane (default 60 min per identical alert key)
grep ALERT_DEDUP src/alerts/discord_webhook.py
```

### "Predictions look stale"

```bash
# 1. Check predictions cache freshness
ls -lt data/cache/predictions_cache_*.parquet | head -3
# 2. R30_W4 freshness check
python -m tests.test_R30_W4_data_freshness
# 3. Force a rebuild (manual; only do this if cron is broken)
python scripts/build_predictions_cache.py --date $(date +%F)
```

### "Bankroll mismatch"

```bash
# 1. Compare ledger sum vs bankroll snapshot
python scripts/reconcile_settlements.py --days 7
# 2. Verify backup integrity
python scripts/ledger_insurance.py --verify
# 3. If the live file is corrupted, restore the most recent backup (see Section 5)
```

### "Drift jumped"

```bash
# 1. Read the drift report
cat data/cache/drift_today.json | python -m json.tool | head -60
# 2. If status == BLOCKED, the prediction cache will refuse to write — fix root cause first
# 3. If only minor drifts, monitor; if major drifts persist >3 days, schedule a retrain
```

### "I lost track of what's running"

```bash
# All daemon names + last heartbeat ages
python scripts/daemon_watchdog.py --once
# All today's recs vs settled
python scripts/live_rec_tracker.py --report --days 1
# Open dashboard
python scripts/mobile_html_server.py --port 8766
# browse http://localhost:8766/operator
```

---

## 7. Reference: shipped operator tools

| Tool                                    | Purpose                              | First shipped |
|-----------------------------------------|--------------------------------------|---------------|
| `scripts/daily_workflow.py`             | Cron-able evening + morning driver   | R26_S3        |
| `scripts/operator_dashboard.py`         | HTML page assembler                  | R22_O5        |
| `/operator` route in `mobile_html_server.py` | HTTP serving of dashboard       | R30_W4        |
| `vault/MORNING.md`                      | Auto-generated daily brief           | R28_U5        |
| `vault/Improvements/alerts.md`          | Layered alert log (warn / critical)  | R21_N3        |
| `scripts/live_recommendation_engine.py` | Live ranked, sized, filtered recs    | R23_P8        |
| `M2_FAMILY_USE_MLP=1`                   | Multitask MLP m2_family override     | R31_X3        |
| `scripts/ledger_insurance.py`           | Daily backup / restore / verify      | R27_T7        |
| `scripts/nightly_cleanup.py`            | Cache + snapshot prune               | R28_U3        |
| Probe archiver (R31_X4)                 | Old probe rollup into archive        | R31_X4        |
| `scripts/daemon_watchdog.py`            | 14-daemon restart loop               | R19_L3        |
| `scripts/daemon_registry.json`          | Watchdog config                      | R19_L3        |
| `scripts/reconcile_settlements.py`      | Ledger vs box-truth audit            | R24_Q8        |
| `scripts/live_rec_tracker.py`           | Snapshot + settle + report per day   | R24_Q4        |
| `scripts/feature_drift_detector.py`     | Per-feature KS / z-score drift       | R27_T3        |
| `scripts/nba_injury_report_scraper.py`  | Parquet injury feed                  | R22_O8        |
| `scripts/recover_line_killed.py`        | Refund / reprice line_killed bets    | R21_N2        |
| `scripts/place_bet.py`                  | Append a bet row to the ledger       | R16_E7        |

---

## Hard rules

- **Never** bypass `place_bet.py` to put rows in the ledger by hand.
- **Never** delete files under `data/pnl_ledger.csv`, `data/models/`,
  `data/nba/`, or `data/backups/`. `nightly_cleanup.py` already protects
  these — do not "help" it.
- **Never** push to remote without confirming `reconcile_settlements.py --days 1`
  is clean.
- **Always** dry-run `--restore` and `--refund-all` first; commit only after
  inspecting the output.
- **Always** check `vault/Improvements/alerts.md` before running anything
  marked "force / rebuild / recover".

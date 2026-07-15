# 07 - Run and Monitor Without Claude

This is the operator runbook. It assumes you have already cloned the repo and
installed the `basketball_ai` conda environment. Once those are done, you do not
need Claude -- you need two PowerShell commands.

Everything here is **paper / units only**. No dollar amounts appear anywhere in
the stack; the self-improve loop is measurement-only until a human deliberately
enables it; and real-money mode is default-DENY with a separate, signed-token
gate. Those rails are not preferences -- they are hard-coded into every daemon.

---

## 1. Start and stop in one line each

```powershell
# Start the full supervised stack and open the UI:
.\go.ps1

# Stop everything cleanly:
.\stop.ps1
```

That is the whole runbook for most days. Both scripts live in the repo root.

### What `.\go.ps1` actually does (four steps)

1. **Arms the self-improve sentinel.** Creates
   `data\cache\improve\PIPELINE_ENABLED` if absent. This file is the
   human-managed gate that permits the recalibration ratchet to run. It is
   idempotent -- if it already exists the script skips silently.
2. **Launches the supervised stack** via `boot.ps1`. The supervisor process
   (`-m supervisor`) starts detached in a hidden window. It owns all 45 child
   services, auto-restarts anything that dies, and keeps running after this
   shell closes or after Claude exits.
3. **Waits up to 150 seconds** for `all_ready` to turn true in
   `data\frontend\ops\supervisor_status.json`, printing a per-service status
   line every six seconds.
4. **Opens the UI** at `http://localhost:3000`.

### What `.\stop.ps1` does

Calls `boot.ps1 -Stop`, which sends `SIGTERM` to the supervisor process group,
waits three seconds for children to drain, then sweeps any stragglers by process
pattern and by port (8098, 8099, 3000). The self-improve sentinel stays in place
so the next `.\go.ps1` re-arms without another human decision.

---

## 2. What happens inside during boot

`boot.ps1` (called by `go.ps1`) runs two phases before any service starts:

### Phase 1: M10 governance preflight

```
python -m governance.run_governance
```

Six gates run in sequence:

| Gate | What it checks |
|---|---|
| `honesty_linter` | No retracted number or dollar-edge claim in any envelope or proposal |
| `provenance` | Every filled/estimated number is labelled FILLED; none presented as real |
| `concurrency` | CLV ledger is intact via the lock-guarded path; no torn rows |
| `pkl_integrity` | Every model pkl's `n_features_in_` matches its meta.json registry entry |
| `leak_audit` | Walk-forward vintage and schema are leak-free where a build artifact exists |
| `parity` | Train and inference feature sets match for any provided candidates |

If a gate fails without `-StrictGovernance`, the paper stack still boots but the
session is marked `GOVERNANCE_ELIGIBLE=false`. If `-StrictGovernance` is passed,
boot aborts on any failure. Real-money mode stays default-DENY regardless of the
preflight verdict.

### Phase 2: Supervisor hand-off

The supervisor (`supervisor/supervisor.py`) takes ownership of 45 process specs
declared in `supervisor/manifest.py` + `supervisor/stack_specs.py`. It sorts them
into a dependency-ordered DAG (topological sort) and boots them in order:

```
m1_producer  (alive = ready)
     |
m1_api_paper  (HTTP 200 at /health on port 8099)
    /   \
m1_api_boards  (TCP port 8098)   m1_paper  (heartbeat file fresh)
    |
m1_ui  (TCP port 3000)

Independent branches (a failure is one red entry, not a cascade):
  m1_bankroll  m1_line_daemon  m6_ingame_loop  m2_inplay  m2_inplay_capture
  m4_selfimprove  m7_ingame_refresh  m5_autonomy_monitor
  m8_ci_cadence  m10_best_bets_compute  m11_ingame_pred_tick
  m12_pm_paper_tick  m13_props_pred_tick
  ...plus 28 more daemons added since 2026-06-20 (m14-m27, m29-m41 -- e.g.
  m38_autoloop, m39_injury_facts_nba, m40_wedge_restarter,
  m41_public_splits), each its own independent branch. See
  `supervisor/stack_specs.py` for the full, current inventory.
```

A child does not start until everything it `depends_on` has passed its readiness
probe. A process that is alive but has a stale heartbeat fails its probe
(stale-never-green). The supervisor uses capped exponential backoff before
re-launching a dead child: 2 s, 4 s, 8 s, ... up to 60 s.

The one canonical status document is `data\frontend\ops\supervisor_status.json`,
rewritten atomically every tick. Every service's `state`, `pid`, and `restarts`
count is there. The UI reads this file directly.

---

## 3. The live UI at http://localhost:3000

The UI is a Next.js app (`webapp/`). It reads the canonical files in
`data\frontend\` via read-only API routes. It never recomputes, never writes to
`data\`, and never spawns a daemon.

### /system -- is the stack healthy and learning?

`webapp/app/system/page.tsx`

This is the first page to open when you want to know what is happening.

- **LiveIndicator** -- at the very top. Reads `supervisor_status.json` in real
  time: green `ALL SERVICES READY` / amber `DEGRADED` / grey `IDLE`. Includes
  per-service state, PID, restart count, and last probe result. This is the
  fastest way to see if something died.
- **OpsPanel** -- per-service health from the autonomy monitor
  (`data\frontend\ops\autonomy_status.json`), including feed staleness. A feed
  that has gone quiet shows as stale-red, never as a fabricated green.
- **SchedulerFreshnessPanel** -- per-sport last-update age for the prediction
  producer (`m1_producer`, cadence 10 min NBA / 15 min MLB / 20 min soccer).
- **Self-improve ratchet status** -- a banner explains the READY-but-INERT state
  (the `PIPELINE_ENABLED` sentinel controls this; see section 4).
- **SelfImprovePanel + RatchetPanel** -- cycle timeline (cold-start /
  hold / ship verdicts from `data\frontend\improve_ledger.jsonl`), the FSM state,
  and n_promoted (currently 0, shown honestly).
- **ParityGrid** -- 4-sport cross-sport completeness grid (GREEN = the honest,
  proven finding that the kernel adapts correctly across NBA/MLB/soccer/tennis).
- **GateMatrix** -- per-sport, per-direction, in-game calibration gate verdicts.
  The meta-finding: generic in-game micro-state REJECTS across all four sports.
  A REJECT is a success -- it means the live market already prices that
  information.
- **GateLedgerPanel** -- every signal ever run through the leak-free gate, with
  its verdict (SHIP / HOLD / REJECT / INSUFFICIENT_DATA).
- **BacklogPanel** -- ranked measurement backlog (what gets validated next).

### /models -- how is the predictor getting better?

`webapp/app/models/page.tsx`

This page tells the improvement story:

- **ModelsRunningTable** -- live services + the gateway face catalog
  (`/api/catalog`), showing each contracted API face (prediction / execution /
  lines / intelligence), its version, and its honest note.
- **BssDeltaChart** -- per-sport Brier Skill Score delta across improvement
  cycles (recharts line chart). A flat line means the model is in cold start
  (not enough settled games); a downward Brier delta means calibration improved
  that cycle.
- **CalibTrendPanel** -- ECE (calibration error) trend.
- **ShipTimeline** -- every SHIP / HOLD / REJECT / INSUFFICIENT_DATA decision
  in chronological order with its reason.
- **CycleNarrativePanel** -- prose summary of ratchet convergence across recent
  cycles.
- **Clv2ndCorpusPanel** -- shows `REPLICATION_PENDING` until real closing prices
  populate a second CLV corpus. This is honest: vs_close is UNPROVEN where no
  liquid in-play prices exist.
- **GateLedgerPanel** -- full gate-verdict ledger (same panel as /system).

---

## 4. The three human gates -- and exactly how to flip each

### Gate 1: Self-improve sentinel (calibration ratchet)

**What it controls:** Whether the recalibration ratchet is allowed to ship a new
calibration map when a candidate passes all five eval-gate criteria. Without the
sentinel the loop runs, scores settled games, and appends INSUFFICIENT_DATA
verdicts to the ledger -- but never ships anything and never flips any flag.

**Current state:** READY but INERT. The sentinel was created by `go.ps1` when you
first ran it, so the ratchet is armed and measuring. The key gate is the
`pipeline_enabled()` check inside `scripts/platformkit/improve/selfimprove_runner.py`,
which reads only the filesystem -- it cannot be tricked by an environment variable.

**To arm** (if not already done by `go.ps1`):
```powershell
# go.ps1 does this automatically. To do it manually:
New-Item -Path "data\cache\improve\PIPELINE_ENABLED" -ItemType File -Force
```

**To disarm** (stop the ratchet from ever shipping):
```powershell
Remove-Item "data\cache\improve\PIPELINE_ENABLED" -ErrorAction SilentlyContinue
```

Source: `scripts/platformkit/improve/pipeline_flag.py`,
`scripts/platformkit/improve/selfimprove_runner.py`.

### Gate 2: Power-on autostart (survive a reboot)

**What it controls:** Whether the stack restarts automatically at Windows logon
after a reboot or power-off. Without this gate you have to re-run `.\go.ps1` each
time. The mechanism is a Windows Scheduled Task that runs `watchdog_autostart.ps1`
at logon; the watchdog sits above the supervisor and re-runs `boot.ps1` if the
supervisor process dies.

**Default state:** OFF. The task is not registered unless you explicitly register
it.

**To enable** (the human go-live step):
```powershell
.\register_autostart.ps1 -Register
```

**To disable** (remove autostart):
```powershell
.\register_autostart.ps1 -Unregister
```

**To preview what it will do** (safe, no changes):
```powershell
.\register_autostart.ps1
```

The watchdog itself (`watchdog_autostart.ps1`) polls every 15 seconds. If the
supervisor process disappears it re-runs `boot.ps1` with capped exponential
backoff, appending every death and restart to `logs\watchdog_autostart.log`.
The governance preflight always runs first; real money stays default-DENY.

Source: `register_autostart.ps1`, `watchdog_autostart.ps1`.

### Gate 3: Real-money mode (default-DENY, triple lock)

**What it controls:** Whether the stack is permitted to even consider executing
real-money bets. The default is hard DENY. There is no $ field anywhere in the
output; the gateway stamps `real_money_enabled=False` on every response via a
constant (`scripts/platformkit/gateway/gateway.py::RAIL_REAL_MONEY_ENABLED`).

**Enabling real-money mode requires three things simultaneously:**

1. The M4 paper-CLV gate (`scripts/platformkit/pm_trading/realmoney_gate.py`)
   must find the paper-trading record eligible (CLV metrics clear the
   pre-registered bar with sufficient sample size).
2. A human must pass `human_approved=True` explicitly.
3. A valid HMAC-SHA256 authorization token, generated by
   `governance.realmoney_gate.sign_token()` and bound to the exact current
   eligibility snapshot, must be presented. The signing secret is read from the
   `GOVERNANCE_REALMONEY_SECRET` environment variable -- if that variable is
   absent, no token can ever verify and the gate can only DENY.

A stale, forged, or tampered token is rejected. This gate governs the mode
switch only -- it never authorizes an individual bet, never places an order,
and never flips a feature flag.

**Current state:** DENY. The paper CLV record does not yet have sufficient
real closing-line coverage to evaluate eligibility. No action is needed or
recommended.

Source: `governance/realmoney_gate.py`,
`scripts/platformkit/pm_trading/realmoney_gate.py`,
`scripts/platformkit/gateway/gateway.py`.

---

## 5. Progress at a glance

Here is the fastest read-out without opening a browser:

```powershell
# Is the stack running? What died?
Get-Content data\frontend\ops\supervisor_status.json | python -m json.tool

# Latest self-improve verdict (last 5 cycles):
Get-Content data\frontend\improve_ledger.jsonl -Tail 5

# Is the PIPELINE_ENABLED sentinel present?
Test-Path data\cache\improve\PIPELINE_ENABLED

# Is autostart registered?
Get-ScheduledTask -TaskName "NBA-AI-Stack-Autostart" -ErrorAction SilentlyContinue |
    Select-Object State, TaskName
```

From the UI, the one-line summary is always the `LiveIndicator` at the top of
`/system`. Green `ALL SERVICES READY` means all 45 services passed their probes.
Amber `DEGRADED` means at least one independent branch failed (the serving spine
may still be healthy -- check the OpsPanel). Grey `IDLE` means the supervisor
status file is stale (stack is not running).

---

## 6. Production serving and rebuild note

`go.ps1` sets the environment variable `NBA_AI_UI_CMD=npm run start` before
calling `boot.ps1`. This means the UI is served from the **production build**
(pre-compiled static assets), not from the Next.js development server. The
production build is stable and does not corrupt stylesheets under load.

A production build must exist in `webapp/`. If it does not (first clone, or after
a front-end change), build it once:

```powershell
cd webapp
npm install       # first time only
npm run build     # compiles to webapp/.next/
cd ..
```

You only need to rebuild after editing files under `webapp/`. Prediction logic,
daemons, and API routes under `predict_service/` or `scripts/platformkit/` do not
require a front-end rebuild.

If you want the hot-reloading dev server instead (slower start, auto-refreshes on
file changes):

```powershell
# Override the UI command before calling go.ps1:
$env:NBA_AI_UI_CMD = "npm run dev"
.\go.ps1
```

For a read-only view without starting any daemons (just the UI + boards API):

```powershell
.\view_local.ps1        # opens :3000 (UI) + :8098 (boards)
.\view_local.ps1 -Stop  # stops those two processes only
```

---

## 7. Headless / server mode

If you do not want the Next.js UI (for example on a remote machine or a dedicated
server):

```powershell
.\boot.ps1 -NoUI    # skips m1_ui entirely; services on :8098 and :8099 still run
```

To abort boot if any governance gate fails (instead of booting paper with a
warning):

```powershell
.\boot.ps1 -StrictGovernance
```

To preview the full dependency plan without starting anything:

```powershell
.\boot.ps1 -DryRun
```

---

## Where to look in the repo

| File | Purpose |
|---|---|
| `go.ps1` | One-command start: arms sentinel, calls boot.ps1, opens UI |
| `stop.ps1` | One-command stop: drains supervisor and all children |
| `boot.ps1` | Core boot: M10 governance preflight then supervisor hand-off |
| `register_autostart.ps1` | Gate 2 (autostart): preview / register / unregister the logon task |
| `watchdog_autostart.ps1` | Outer watchdog: re-runs boot.ps1 if the supervisor process dies |
| `view_local.ps1` | Read-only view: UI + boards API only, no daemons |
| `supervisor/manifest.py` | 45-service DAG: ProcSpec, RestartPolicy, ReadinessSpec, topo sort |
| `supervisor/stack_specs.py` | Concrete process inventory: commands, ports, heartbeat paths |
| `supervisor/supervisor.py` | Supervisor class: boot(), supervise(), drain(), HeartbeatReaper |
| `supervisor/health.py` | Readiness probe implementations (TCP, HTTP 200, heartbeat-fresh) |
| `governance/run_governance.py` | M10 preflight: aggregates all honesty/correctness gates |
| `governance/realmoney_gate.py` | Gate 3 (real-money): default-DENY + eligibility + signed token |
| `scripts/platformkit/improve/pipeline_flag.py` | Gate 1 (self-improve): PIPELINE_ENABLED sentinel check |
| `scripts/platformkit/gateway/gateway.py` | Gateway face registry + RAIL_REAL_MONEY_ENABLED=False constant |
| `data\frontend\ops\supervisor_status.json` | Live per-service state: all_ready, pid, restarts (local) |
| `data\frontend\improve_ledger.jsonl` | Append-only self-improve verdict log (local) |
| `logs\m9_supervisor.out` | Supervisor stdout log |
| `logs\watchdog_autostart.log` | Watchdog restart history |
| `webapp/app/system/page.tsx` | /system page: LiveIndicator, OpsPanel, GateMatrix, ratchet |
| `webapp/app/models/page.tsx` | /models page: BssDeltaChart, ShipTimeline, CLV corpus status |

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)

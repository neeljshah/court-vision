# 08 -- The Live, Independent Stack

> **Summary:** The stack runs unattended. One command (`boot.ps1`) starts 45
> supervised processes in dependency order, gates each one on a readiness probe
> before unblocking its dependents, then auto-restarts any process that dies or
> whose heartbeat goes stale -- with capped exponential backoff and a per-daemon
> rate limit of three restarts per hour. A governance preflight runs first; if it
> fails, the paper stack boots anyway but real money stays default-DENY. Claude is
> not involved in any of this at runtime. **Everything below has been verified
> against the source files listed at the bottom of this document.**

---

## 1. The problem this solves

A live sports-intelligence platform has a short expiry window: odds move, games
start, and a human who has to manually restart five processes every morning is a
single point of failure. The design goal here is that the operator runs one
command, then does nothing -- a dead process restarts itself, a hung process
(alive but frozen, writing no heartbeat) is reaped and relaunched, and an ops
dashboard always shows exactly what is green and what is not.

---

## 2. Single-command boot

```
.\boot.ps1              # full stack, with Next.js UI on port 3000
.\boot.ps1 -NoUI        # headless backend profile (no UI)
.\boot.ps1 -DryRun      # print the dependency graph + readiness plan, exit
.\boot.ps1 -Stop        # graceful SIGTERM drain in reverse dependency order
```

Before any process starts, `boot.ps1` runs a governance preflight:

```
python -m governance.run_governance
Gates: honesty_linter | provenance | concurrency | pkl_integrity |
       leak_audit | parity
```

If governance passes, the supervisor boots. If it fails, the paper stack still
boots (real-money eligibility is set to false for the session) unless `-StrictGovernance`
was supplied, in which case the whole boot aborts. Real money is default-DENY regardless.

---

## 3. The supervisor: how it keeps things alive

The supervisor (`supervisor/supervisor.py`, class `Supervisor`) owns the lifecycle
of every child process. It does four things:

**Dependency-ordered boot.** The 45 process specs in `supervisor/stack_specs.py` form a
DAG: each spec declares `depends_on` edges. At boot the supervisor sorts that DAG
topologically (Kahn's algorithm) and launches processes in that order. A process does
not launch until every process it depends on has passed its readiness probe.

**Readiness probes.** Each spec carries one of three probe kinds, implemented in
`supervisor/health.py`:

| Kind | What it checks |
|---|---|
| `tcp-port-open` | TCP connection succeeds on the declared port |
| `http-200` | HTTP GET to a path returns 200 |
| `heartbeat-file-fresh` | Heartbeat file mtime is within `fresh_sec` seconds |

Critically, a process that is alive but has a stale heartbeat does NOT read
"ready" -- stale-never-green. A `HeartbeatReaper` in the supervisor tracks
consecutively stale reads (threshold: 2) and terminates the process so the
restart logic can relaunch it with backoff.

**Capped exponential backoff.** Every process carries a `RestartPolicy`. The
default is `max_retries=None` (retry forever) with `backoff_base_sec=2.0` and
`backoff_cap_sec=60.0`. The backoff for attempt `n` is:

```
delay = min(60, 2.0 * 2**(n-1))   # 2s, 4s, 8s, 16s, 32s, 60s, 60s, ...
```

The supervisor never retries a dead process in a tight loop. The Next.js UI uses
a slightly wider policy (base=3s, cap=90s) because npm startup is slower.

**Failure isolation.** A failed non-critical process does not sink the rest.
The supervisor marks it `FAILED` and keeps all other processes running. The one
canonical status document (`data/frontend/ops/supervisor_status.json`) is
rewritten atomically on every supervise tick so the ops dashboard always has a
fresh view -- never a stale-green.

**Graceful drain.** `-Stop` calls `Supervisor.drain()`, which terminates processes
in reverse dependency order (dependents first, then the things they depend on),
preventing torn state.

---

## 4. The supervised processes (17 of 45 documented in detail here)

The manifest (`supervisor/stack_specs.py`, read by `supervisor/manifest.py`) declares
45 `ProcSpec` entries (`m1_producer` through `m41_public_splits`). The 17 below --
the serving spine plus the earliest independent daemons -- are documented in
detail. The remaining 28 (`m1_bankroll`, `m14_brain_rebuild` through
`m27_ingame_paper_settle`, and `m29_output_freshness` through
`m41_public_splits`) are additional independent daemons registered in the same
manifest; see `supervisor/stack_specs.py` for their specs and inline rail
comments.

### 4a. The serving spine (boots first; dependents wait on these)

```
m1_producer -> m1_api_paper -> m1_api_boards -> m1_ui
                            \-> m1_paper
```

| Name | Module | Port | Readiness | What it does |
|---|---|---|---|---|
| `m1_producer` | `predict_service.scheduler` | -- | alive | Produces a calibrated SnapshotEnvelope per active sport every 10 min (NBA), 15 min (MLB), 20 min (soccer) and writes `data/frontend/predict_service/_heartbeat.json`. This is the always-on data producer; the API degrades gracefully (status: unavailable) until the first cycle lands. |
| `m1_api_paper` | `predict_service.app` | 8099 | HTTP 200 `/health` | The Auto-API. Serves `/api/predict/{sport}`, `/api/paper/trail`, `/api/paper/clv`, and `/health`. Starts only after `m1_producer` is alive. |
| `m1_api_boards` | `platformkit.frontend.serve` | 8098 | TCP connect | The legacy boards API (existing predictions dashboard). Starts after `m1_api_paper` is ready. |
| `m1_ui` | `npm run dev` (in `court-visions/`) | 3000 | TCP connect | The Next.js live dashboard. Skipped in `-NoUI` mode. |
| `m1_paper` | `pm_trading.auto_loop --forever` | -- | heartbeat | The self-improving paper loop. One honest cycle: paper-trade today's real games -> grade finished games via CLV -> recalibrate (gated by eval-gate) -> line snapshot. Cadence ~20 min. Beats `data/cache/daemon_heartbeats/m1_paper.txt`; a stale beat reads NOT-READY. |

### 4b. Independent branches (no `depends_on`; failure is one red entry, not a cascade) -- 12 of 40 total documented here

| Name | Module | Cadence | Heartbeat file | What it does |
|---|---|---|---|---|
| `m1_line_daemon` | `odds_provider.line_snapshot_daemon` | 900 s slow / 60 s near-tip | `m1_line_daemon.txt` | Phase-aware line and close capture. Slows down (900 s) when no game is near tip; accelerates to 60 s within 45 min of tip to guarantee a snapshot inside the close window for CLV settlement. |
| `m6_ingame_loop` | `ingame.live_loop` | 20 s live / 120 s idle | `ingame/_heartbeat.json` | The in-game spine. Per tick: fetch live ESPN scoreboard -> ingest game states -> reprice each live game using the pregame prior -> write a per-game snapshot atomically (`data/frontend/ingame/<sport>/<game_id>.json`). A down feed degrades to empty, never fabricated. |
| `m2_inplay` | `odds_provider.inplay_runner` | 20 s live / idle varies | `m2_inplay.txt` | Supervised wrapper for `inplay_snapshot_daemon.serve_inplay_forever`. Per-sport isolation inside the loop: one bad feed never stops the others. Paper / measurement only. |
| `m2_inplay_capture` | `ingame.inplay_capture_runner` | 20 s live / 120 s idle | `m2_inplay_capture.txt` | W4 in-play capture daemon. Per live game per tick: captures (model_prob, devigged-price) pair -> appends to `data/cache/ingame_grade/<sport>/<game_id>.jsonl`, paper-decides in UNITS (executed=False), stamps held-out home_win label on FINAL. Paper-only; no flag flip. |
| `m4_selfimprove` | `improve.selfimprove_runner` | 60 s | `m4_selfimprove.txt` | P4 supervised self-improve wrapper. Checkpoint-resumable (`data/cache/improve/checkpoint.json`): the cursor only ever advances, so a restart never reprocesses settled games. Default wiring is measurement-only -- `recalibrate_fn` returns `None` (NO_CANDIDATE) unless a real recalibrator module is present. Nothing ships, no flag flips. |
| `m7_ingame_refresh` | `ingame.ingame_refresh_runner_svc` | 3600 s | `m7_ingame_refresh.txt` | P7 living in-game refresh loop. Hourly: folds newly-settled in-season finals -> re-gates -> re-fits the served in-game model, with honest swap or downgrade of provenance. Per-sport isolated. Paper / measurement only. |
| `m5_autonomy_monitor` | `autonomy.autonomy_monitor_runner` | 60 s | `m5_autonomy_monitor.txt` | Composes the ONE canonical autonomy status object every ~60 s and atomically publishes `data/frontend/ops/autonomy_status.json`. A dead monitor is itself RED (stale heartbeat), never silently absent. Ships nothing, flips no flag. |
| `m8_ci_cadence` | `progress.ci_cadence_runner` | hourly-light | `m8_ci_cadence.txt` | W4 continuous-improvement cadence. Each tick: refresh backlog -> enqueue one measurement kind -> auto-gate (INERT: NO_CANDIDATE while the pipeline-enabled sentinel is absent) -> survivor re-check -> append one progress row. Beats at boot and on every sleep boundary so a hung tick ages out as NOT-READY. |
| `m10_best_bets_compute` | `bestbets.bestbets_compute_runner` | 120 s | `m10_best_bets_compute.txt` | Re-ranks calibrated model-vs-market divergence cards across sports every 120 s and atomically writes `data/frontend/best_bets.json`. UNITS not dollars; calibration not edge; no flag flip. A compute failure degrades to `overall=degraded` in the output envelope -- the heartbeat still advances so the supervisor can distinguish "alive but unhappy" from "dead". |
| `m11_ingame_pred_tick` | `ingame.ingame_pred_tick_runner` | 20 s live / 120 s idle | `m11_ingame_pred_tick.txt` | Phase-aware in-game prediction tick. Writes `data/frontend/ingame/live_pred_<game_id>.json` per live game. CLV reads `INSUFFICIENT_DATA` when no liquid in-play prices are available. Measurement only. |
| `m12_pm_paper_tick` | `pm_trading.pm_paper_tick_runner` | 60 s | `m12_pm_paper_tick.txt` | Captures Kalshi / Polymarket model-vs-price pairs and appends canonical rows to `data/frontend/clv_ledger.jsonl`. UNITS not dollars; `is_pm=True`, `executed=False`; no flag flip; real-money default-DENY. Dollar-field keys are stripped before any row is written. |
| `m13_props_pred_tick` | `props.props_pred_tick_runner` | 300 s | `m13_props_pred_tick.txt` | Re-scores prop lines every 300 s on fresh prices and writes `data/frontend/props_snapshot.json`. Reports `overall=UNAVAILABLE` during the NBA offseason (no live prop lines). Measurement only. |

---

## 5. Boot dependency graph

```
                    m1_producer  (no deps; boots first)
                         |
                   m1_api_paper  (HTTP 200 /health required)
                   /            \
          m1_api_boards        m1_paper
                |
             m1_ui

Independent (no depends_on -- dead = one red entry, not a cascade); 12 of 40
documented in section 4b, plus 28 more (m1_bankroll, m14_brain_rebuild through
m27_ingame_paper_settle, m29_output_freshness through m41_public_splits):
  m1_line_daemon
  m6_ingame_loop
  m2_inplay
  m2_inplay_capture
  m4_selfimprove
  m7_ingame_refresh
  m5_autonomy_monitor
  m8_ci_cadence
  m10_best_bets_compute
  m11_ingame_pred_tick
  m12_pm_paper_tick
  m13_props_pred_tick
  ... (28 more -- see supervisor/stack_specs.py)
```

All 45 processes split into a 5-process serving spine (`m1_producer` ->
`m1_api_paper` -> `m1_api_boards` -> `m1_ui`, with `m1_paper` also depending on
`m1_api_paper`) and 40 independent branches. The independent branches are
intentionally isolated so that a broken odds feed or a self-improve checkpoint
corruption does not cascade into the serving spine.

---

## 6. The daemon watchdog (a second, complementary supervisor)

Alongside the `Supervisor` class there is a lighter, independently-deployable
watchdog (`scripts/daemon_watchdog.py`, registry `scripts/daemon_registry.json`).
Where the `Supervisor` owns the processes it spawns, the watchdog polls an
external registry of 28 named daemons (some overlap, some additional) that may
be launched separately or by other scripts. Every 60 seconds it asks two
questions per daemon:

1. Is the heartbeat file fresher than `expected_interval_sec * 3`?
2. Is there a live process matching `process_match` in the process table?

If either check fails, the daemon is considered dead. The watchdog then:

- Appends a row to `vault/Improvements/daemon_restarts.md`.
- Fires a Discord `WARN` alert via `src.alerts.discord_webhook.post_alert`.
- Shells out the platform-appropriate restart command (`restart_cmd_win` on
  Windows, `restart_cmd` on POSIX).
- Records the restart in a per-daemon sliding-window rate limiter: no daemon
  can be restarted more than 3 times per rolling 60-minute window.

The watchdog itself runs in a tmux session started by
`scripts/launch_daemon_watchdog.sh` (idempotent: no-ops if already running).

---

## 7. Why the stack runs without Claude

At runtime Claude is not in the loop at all. The autonomous behavior comes from:

- **The supervisor** (`supervisor/supervisor.py`): stdlib-only, no external deps, runs forever via `run_forever()`.
- **Heartbeat files** (`data/cache/daemon_heartbeats/*.txt`): each daemon writes a UTC timestamp; the supervisor and watchdog read mtime to decide health, with no network calls.
- **Stale-never-green** invariant: every readiness probe requires a file that actually exists and is recently updated. An absent file means NOT-READY, not a default-green pass.
- **The paper loop** (`m1_paper` / `auto_loop.py --forever`): cycles through paper-trade -> grade -> recalibrate -> line-capture on its own cadence. Recalibration is gated by `eval_gate`; nothing ships unless the gate approves.
- **Failure isolation**: no critical-path dependency on any single independent daemon. A dead feed produces empty output, not an exception that propagates.

A human is required for exactly two things: initial `boot.ps1` invocation, and the explicit flip needed to enable real-money execution (which defaults to DENY and requires a signed token). Everything else runs unattended.

---

## 8. Calibration and honesty rails baked into the daemons

Every daemon in the stack observes the same rails, enforced in each module's
docstring as a binding contract rather than a comment:

- **UNITS not dollars:** no `dollar_pnl`, `roi`, `profit`, or `dollar` field appears in any output JSON. Dollar-field keys are stripped by `pm_paper_tick_runner` before any row is written.
- **Calibration not edge:** `best_bets.json` ranks calibrated model-vs-market divergence cards. The word "edge" does not appear in the ranking logic.
- **Real-money default-DENY:** `m12_pm_paper_tick` hardcodes `executed=False` and `clv_status=INSUFFICIENT_DATA`. No daemon flips a flag, writes `data/registry/`, or initiates a real order.
- **Stale-never-green:** every daemon that has a readiness check uses `kind=HEARTBEAT` with a `fresh_sec` window that exceeds the daemon's cadence by at least 2x plus margin. An absent or stale file reads NOT-READY.

---

## Where to look in the repo

| File | What it contains |
|---|---|
| `boot.ps1` | Single-command boot; governance preflight; dependency-ordered start comments |
| `supervisor/manifest.py` | `ProcSpec`, `RestartPolicy`, `ReadinessSpec` dataclasses; topological sort (`topo_order`); `manifest()` selector |
| `supervisor/stack_specs.py` | The 45-entry process inventory (`base_specs()`); heartbeat paths; per-proc readiness windows |
| `supervisor/supervisor.py` | `Supervisor` class: `boot()`, `supervise()`, `drain()`, `run_forever()`; `HeartbeatReaper` integration |
| `supervisor/health.py` | Readiness probe implementations (TCP, HTTP 200, heartbeat-fresh) |
| `scripts/daemon_registry.json` | 28-daemon registry for the standalone watchdog; restart commands for both Windows and POSIX |
| `scripts/daemon_watchdog.py` | Standalone watchdog: heartbeat-age check, process-alive check, rate limiter (3/hr), Discord alert, restart shell-out |
| `scripts/launch_daemon_watchdog.sh` | Idempotent launcher for the watchdog in a tmux session |
| `ops/liveness.py` | `heartbeat()` (atomic write), `is_live()`, `liveness_snapshot()` |
| `ops/service_registry.py` | Maps ProcSpec names to liveness components and freshness sources for the health aggregator |
| `ops/health_aggregator.py` | Composes the ops status page from liveness + freshness readings |
| `scripts/platformkit/ingame/live_loop.py` | M6: in-game spine loop (ingest -> reprice -> snapshot, 20 s live / 120 s idle) |
| `scripts/platformkit/improve/selfimprove_runner.py` | M4: checkpoint-resumable self-improve wrapper |
| `scripts/platformkit/ingame/ingame_refresh_runner_svc.py` | M7: living in-game refresh (hourly, folds settled finals -> re-gate -> re-fit) |
| `scripts/platformkit/bestbets/bestbets_compute_runner.py` | M10: best-bets compute (120 s, UNITS not dollars, stale-never-green) |
| `scripts/platformkit/pm_trading/pm_paper_tick_runner.py` | M12: PM paper-trade tick (60 s, dollar-fields stripped, executed=False) |
| `scripts/platformkit/props/props_pred_tick_runner.py` | M13: props prediction tick (300 s, writes props_snapshot.json) |
| `scripts/platformkit/pm_trading/auto_loop.py` | M1 paper loop: paper-trade -> grade -> self-improve -> line-capture cycle |

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md)

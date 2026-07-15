# The Always-On Daemon Fleet

This is the process layer nobody sees in a demo: 45 long-lived Python loops
that boot alongside the FastAPI/Next.js stack and keep capturing lines,
repricing live games, settling paper bets, and re-gating candidate signals
with zero chat session attached. None of it claims a dollar edge -- every
daemon below is PAPER (`executed=False`), UNITS not `$`, and the honest
result on most cycles is an empty scan or a REJECT logged to a ledger. This
doc catalogs what actually runs, how the supervisor decides a daemon is
alive vs. merely running, and the liveness machinery that grew out of three
real production incidents.

Source: `supervisor/stack_specs.py` (the 45-`ProcSpec` inventory),
`supervisor/manifest.py` (the DAG + readiness types), `supervisor/_restart.py`
+ `supervisor/_beat_thread.py` (spawn/backoff/heartbeat internals),
`scripts/platformkit/autonomy/heartbeat_reaper.py`,
`scripts/platformkit/odds_provider/kalshi_rate_governor.py`, and the older
`scripts/daemon_registry.json` + `scripts/daemon_watchdog.py` pair. See also
[docs/PLATFORM_TOOLING.md](PLATFORM_TOOLING.md) for the always-on-stack
summary table and the calibration tooling this fleet feeds.

---

## The supervisor model

`boot.ps1` brings up the local product; `supervisor/` **describes** what it
launches, it does not spawn anything at import time. Each process is a
`ProcSpec` (`supervisor/manifest.py`): a launch shape (`kind="py"` -> `python
-u -m module`, or `kind="node"` -> an npm command), an optional listen port,
`depends_on` edges, a `ReadinessSpec`, a `RestartPolicy`, and env overrides.
`manifest(profile)` topologically sorts the specs (Kahn's algorithm, stable
on insertion order) so a dependency always boots before its dependents; a
cyclic `depends_on` graph is a config error and raises `CycleError` rather
than booting a broken order. Two profiles: `default` (full stack, with the
Next.js UI) and `backend` (drops the `kind="node"` UI process and prunes it
from every `depends_on` edge so the DAG stays well-formed).

**Readiness** decides a process is READY, not merely alive:

| Kind | Check |
|---|---|
| `tcp-port-open` | the declared port accepts a connection |
| `http-200` | `http_path` on `port` returns 200 |
| `heartbeat-file-fresh` | heartbeat file mtime is within `fresh_sec` |
| `none` | ready as soon as the process is alive |

**Restart** is a capped exponential backoff: `delay = min(backoff_cap_sec,
backoff_base_sec * 2**(attempt-1))`, attempt 1-based. The default policy
(`_FOREVER`, base=2s, cap=60s) retries indefinitely -- every long-lived loop
in this fleet uses it; a `max_retries` cap exists for the type but nothing in
`base_specs()` currently sets one. Before the launch loop runs,
`reconcile_survivors()` kills any already-running child matching each spec's
cmdline pattern (`match_pattern`) so a re-boot never duplicates a process or
collides on a port -- boot is idempotent.

A dead process is one thing; a **hung** one is the harder case, covered
next.

---

## Liveness patterns that evolved

Three separate incidents shaped the layers below. Each is a design lesson,
not a one-off patch.

### 1. Two-layer heartbeats (the supervisor's own tick can starve its beat)

`Supervisor.run_forever()` used to stamp its own liveness heartbeat once per
tick, serially *after* `supervise()` returned. `supervise()` probes every
`ProcSpec` (45 as of this writing); each TCP/HTTP probe has its own 2.0s
timeout (`supervisor/health.py`). Under fleet load, several probes stacking
serially in the same tick could push one `supervise()` pass close to or past
the watchdog's staleness threshold -- the watchdog then declared the
*supervisor itself* wedged, killed it, and `reconcile_survivors()` rebooted
the **entire fleet**, so unrelated daemons appeared to crash in lockstep when
they were actually being restarted by a healthy supervisor's own reboot.

The fix (`supervisor/_beat_thread.py`, `BeatThread`) is a daemon thread that
stamps the self-heartbeat on a fixed 20s wall-clock cadence, decoupled from
`supervise()`'s duration -- a slow tick no longer starves the beat. This is
the same pattern independently found and fixed for `m13_props_pred_tick` on
2026-06-26: one unit of work (there, prop scoring; here, one probe sweep)
exceeding the staleness window even though the process is healthy. Two-layer
heartbeat = one thread beats on a fixed clock, a separate slower loop does
the real work.

### 2. Hung != crashed -- the heartbeat reaper

The supervisor's normal restart path (`reap_and_restart`, `supervisor/_restart.py`)
only fires when a process has actually **died**. A wedged-but-alive loop
(heartbeat frozen, process still running) would read READY forever under
that path alone -- the "stale-as-green" honesty violation.
`scripts/platformkit/autonomy/heartbeat_reaper.py` closes the gap: it wraps
`ops.circuit_breaker.CircuitBreaker` per service. Every tick,
`reap_stale_heartbeat()` feeds it the heartbeat's age vs. its declared
`fresh_sec` window:

- fresh -> `record_success` (breaker heals to CLOSED, status `HEALTHY`)
- stale -> `record_failure` (breaker trips OPEN after `fail_threshold`,
  default 2 consecutive stale ticks -- absorbs one late beat without a
  flap-restart)
- absent, but the daemon has beaten before -> treated as stale (a heartbeat
  that appeared then vanished is a hung/crashed loop)
- absent, and the daemon has *never* beaten -> `KEEP` (a daemon that
  legitimately writes no heartbeat is never reaped on absence alone; the
  supervisor's own dead-proc path owns true crashes)

A tripped breaker yields status `STALE_HUNG` (never `READY`) and a `restart`
verdict: the supervisor kills the hung child and arms a fresh backoff window
via `arm_backoff`. The breaker's own cooldown (default 60s) is the natural
rate cap so a slow-to-recover daemon isn't restart-hammered.

### 3. Crash-rate breaker (C7) and the HTTP wedge reaper (M33)

Per-spec backoff paces *individual* relaunches, but says nothing about a
spec that is **chronically** broken -- flapping at the backoff cap forever
with no escalation. `note_relaunch()` tracks relaunch timestamps in a
rolling window; more than `_CRASH_MAX` relaunches inside `_CRASH_WINDOW_SEC`
trips a distinct breaker (logged once as DEGRADED, restarts continue) so the
status surface shows chronic flapping instead of silent noise.

A separate failure mode the heartbeat reaper can't see: an HTTP-readiness
process (e.g. `m1_api_paper` on :8099) whose event loop wedges keeps its
port **listening** while every HTTP probe times out -- no heartbeat file
means `heartbeat_reaper` never fires. `m33_http_wedge_reaper` (30s cadence)
probes each declared HTTP-readiness target's port + HTTP health + per-PID
CPU%, and kills *only* a PID meeting both >=3 consecutive >10s timeouts
(port still listening) **and** CPU>50% sustained >120s -- the supervisor's
normal restart path relaunches it from there. No broader restart authority
than that single targeted kill.

### 4. The cross-process rate governor (shared Kalshi ceiling)

Two production daemons (`m2_inplay_capture` and the pregame line-snapshot
daemon) both hit Kalshi's keyless-tier endpoint with no shared budget --
1,678 unpaced 429s/day on the unpaced side vs. 197 on the paced side, per the
diagnosis in `docs/research/organization-sprint/PROPOSED_kalshi_rate_governor_2026-07-05.md`.
`scripts/platformkit/odds_provider/kalshi_rate_governor.py` is the fix: each
daemon **process** gets its own token bucket sized to a fair share of a
conservative `BASE_RPS=15.0` ceiling (well under Kalshi's documented ~30
rps, leaving headroom for callers not yet wired to the governor). Coordination
across processes happens only through a shared JSON state file (atomic
tmp+replace) -- on any 429, `on_429()` writes a pressure timestamp; every
`acquire()` (this process or the other daemon's, on its next read) halves its
effective refill rate for a 30s decay window. Fail-open throughout: a
missing/corrupt state file, a broken clock, or any internal error grants the
token immediately rather than blocking a real request.

Per-process fair shares (`DEFAULT_RATE_SHARES`):

| Caller | Share | Why |
|---|---|---|
| `capture` | 0.35 | steadier 20s live-interval loop |
| `snapshot` | 0.65 | faster 5s loop, more sports (8 vs. 6) |
| `feed_health` | 0.15 | 10-minute probe, not a hot loop |
| `close_capture` | 0.15 | 900s settled-row sweep, not a hot loop |
| *(unknown caller)* | 0.5 | default -- see the m18 war story below |

`KALSHI_GOVERNOR_OFF=1` makes `acquire()` an immediate no-op (byte-identical
decision paths; it only spaces out HTTP calls).

---

## The daemon catalog (`supervisor/stack_specs.py`, m1-m41)

Every row is a real `ProcSpec`. "Cadence" is the daemon's own declared tick
(from its `argv --interval` or runner docstring); "fresh" is the
`ReadinessSpec.fresh_sec` window (roughly 2-3x cadence + margin) for
heartbeat-readiness specs, or `NONE` for daemons whose freshness is checked
by a sentinel instead (see next section). Heartbeats live at
`data/cache/daemon_heartbeats/<name>.txt` unless noted.

| ID | Module | Cadence | Readiness | Purpose | Output |
|---|---|---|---|---|---|
| `m1_producer` | `predict_service.scheduler` | 600s (NBA; up to 1200s soccer) | heartbeat, fresh 1500s | Produces the calibrated envelope for every active sport | `data/frontend/predict_service/_heartbeat.json` |
| `m1_api_paper` | `predict_service.app` :8099 | -- | http `/health` | Auto-API: serves read-only calibrated envelopes | -- |
| `m1_api_boards` | `scripts.platformkit.frontend.serve` :8098 | -- | tcp | Boards API for the UI | -- |
| `m1_ui` | `npm run dev` (Next.js) :3000 | -- | tcp | Dashboard (dropped in `backend` profile) | -- |
| `m1_paper` | `pm_trading.auto_loop --forever` | ~1200s | heartbeat, fresh 2700s | Paper-trading loop | `m1_paper.txt` |
| `m1_line_daemon` | `odds_provider.line_snapshot_daemon` | phase-aware, up to 900s idle | heartbeat, fresh 2700s | Captures closing-line snapshots for CLV | `m1_line_daemon.txt` |
| `m1_bankroll` | `platformkit.paper.bankroll_daemon` | 600s | heartbeat, fresh 1500s | Daily + cumulative UNITS P&L from settled paper bets | `paper_pnl_series.json`, `paper_bankroll.json`, `paper_today.json` |
| `m6_ingame_loop` | `ingame.live_loop --sports mlb,soccer,soccer_intl,nba,tennis` | tick-based | heartbeat, fresh 300s | Multi-sport in-game repricer | `data/frontend/ingame/_heartbeat.json` |
| `m2_inplay` | `odds_provider.inplay_runner` | tick-based | heartbeat, fresh 300s | Venue-native in-play capture (independent branch) | `m2_inplay.txt` |
| `m4_selfimprove` | `improve.selfimprove_runner` | tick-based | heartbeat, fresh 300s | Self-improve ratchet (measurement-only by default) | `m4_selfimprove.txt` |
| `m7_ingame_refresh` | `ingame.ingame_refresh_runner_svc` | 3600s | heartbeat, fresh 7800s | Folds settled finals -> re-gates/re-fits served in-game model | `m7_ingame_refresh.txt` |
| `m5_autonomy_monitor` | `autonomy.autonomy_monitor_runner` | ~60s | heartbeat, fresh 300s | Composes the one canonical autonomy status | `data/frontend/ops/autonomy_status.json` |
| `m8_ci_cadence` | `progress.ci_cadence_runner` | hourly-light | heartbeat, fresh 7800s | Continuous-improvement cadence tick (measurement-only) | -- |
| `m2_inplay_capture` | `ingame.inplay_capture_runner` | 20s live / 120s idle | heartbeat, fresh 300s | Captures (model_prob, devigged price) pairs + paper decisions | `data/cache/ingame_grade/<sport>/<game_id>.jsonl` |
| `m10_best_bets_compute` | `bestbets.bestbets_compute_runner` | 120s | heartbeat, fresh 300s | Model-vs-market divergence ranked by calibrated confidence | `data/frontend/best_bets.json` |
| `m11_ingame_pred_tick` | `ingame.ingame_pred_tick_runner` | 20s live / 120s idle | heartbeat, fresh 300s | Per-game in-game prediction tick | `data/frontend/ingame/live_pred_<game_id>.json` |
| `m12_pm_paper_tick` | `pm_trading.pm_paper_tick_runner` | 60s | heartbeat, fresh 150s | Records model-vs-PM-price pairs per market | `data/cache/pm_paper/<market>.jsonl` |
| `m13_props_pred_tick` | `props.props_pred_tick_runner` | 300s | heartbeat, fresh 660s | Re-scores prop lines on fresh price | `data/frontend/props_snapshot.json` |
| `m14_brain_rebuild` | `platformkit.brain_rebuild_runner --with-models` | 6h default | heartbeat, fresh 46800s | Rebuilds the person-free Obsidian brain (`vault/_Organized`) | -- |
| `m15_prop_settle` | `bestbets.prop_settle_runner` | 900s | heartbeat, fresh 1980s | Settles OPEN player props on the real post-game stat | `clv_ledger.jsonl` |
| `m16_prop_close_capture` | `clv.prop_close_capture_runner` | 60s | heartbeat, fresh 150s | Snapshots live two-way price of OPEN in-game props | `prop_close_store` |
| `m17_kalshi_scan` | `pm_trading.kalshi_scan_runner` | 1800s | heartbeat, fresh 3900s | Scans which Kalshi market types develop real two-way liquidity | daily high-water mark |
| `m18_pm_close_capture` | `pm_trading.pm_close_capture_runner` | 900s | heartbeat, fresh 1980s | Resolves + stamps confirmed Kalshi settled closes onto paper_pm bets | -- |
| `m19_asof_reclaim` | `ceiling.asof_reclaim_daemon --interval 86400` | 86400s | none | Daily re-gates leak-free `*_diff_asof` candidates vs. leak-free Elo | `data/frontend/ceiling_reclaim_scoreboard.jsonl` |
| `m20_ingame_clv_verdict` | `ingame.ingame_clv_verdict_daemon --interval 600` | 600s | none | Replays captured M11 tick series through the in-play CLV grade | `data/frontend/ops/ingame_clv_verdict.json` |
| `m21_ingame_baseout_gate` | `improve.ingame_baseout_gate_daemon --interval 3600` | 3600s | none | Leak-free test: does deep base-out state anticipate the in-play close beyond model_prob | `data/frontend/ops/ingame_baseout_gate.json` |
| `m22_best_price_scan` | `clv.best_price_scan_daemon --interval 240` | 240s | none | Best sportsbook price per side vs. sharp (Pinnacle/cross-book) fair | `data/frontend/ops/best_price_scan.json` + catches log |
| `m23_scraped_line_gaps` | `clv.scraped_line_gaps_daemon --interval 240` | 240s | none | Same hunt, sourced from our own scraped feed (not OddsAPI) | `data/frontend/ops/scraped_line_gaps.json` |
| `m24_ingame_placement_funnel` | `ingame.ingame_placement_funnel --interval 300` | 300s | none | Per-stage bet-placement funnel diagnostic | `data/frontend/ops/ingame_placement_funnel.json` |
| `m25_ingame_outcome_verdict` | `ingame.ingame_outcome_verdict --interval 900` | 900s | none | Per-segment Brier of live model vs. real OUTCOME vs. venue in-play price | `data/frontend/ops/ingame_outcome_verdict.json` |
| `m26_ingame_segment_trust` | `ingame.ingame_segment_trust --interval 1800` | 1800s | none | Cross-corpus TRUSTED/ADVERSE/NEUTRAL replication gate on m25's verdict | `data/frontend/ops/ingame_segment_trust.json` |
| `m27_ingame_paper_settle` | `ingame.ingame_paper_settle --interval 900` | 900s | none | Settles OPEN `paper_ingame` rows from the ticker-resolved final score | `data/frontend/ops/ingame_paper_settle_status.json` |
| `m29_output_freshness` | `ops_sentinel.output_freshness_runner --interval 300` | 300s | heartbeat, fresh 660s | Checks m19-m27's own output artifact mtime vs. cadence (see below) | `data/frontend/ops/output_freshness.json` |
| `m30_feed_health` | `odds_provider.feed_health_runner --interval 600` | 600s | heartbeat, fresh 1320s | Live-probes every (provider, sport) pair for silent 401/403/timeout drops | `data/frontend/ops/feed_health.json` |
| `m31_mlb_context` | `platformkit.mlb_context_runner --interval 21600` | 6h | heartbeat, fresh 45000s | Probables/weather/HP-umpire + injury snapshot | context parquets |
| `m32_mlb_context_autogate` | `platformkit.mlb_context_autogate_runner --interval 86400` | daily | heartbeat, fresh 190000s | Nightly re-run of SP-offset + weather-totals gates | `data/frontend/ops/mlb_context_autogate.json` |
| `m33_http_wedge_reaper` | `autonomy.http_wedge_reaper_runner --interval 30` | 30s | heartbeat, fresh 90s | Kills a wedged HTTP-readiness PID (port listening + CPU>50%>120s) | -- |
| `m34_freshness_sla` | `autonomy.freshness_sla_runner --interval 300` | 300s | heartbeat, fresh 660s | Generalized per-daemon output-artifact SLA scoreboard (fleet-wide) | `data/frontend/ops/freshness_sla.json` |
| `m35_ingame_tail_multi` | `ingame.ingame_tail_multi_runner --interval 21600` | 6h | heartbeat, fresh 45000s | Tennis/soccer_intl tail-band scan + pre-registered gate (**not yet running**) | `data/frontend/ops/ingame_tail_multi.json` |
| `m36_ingame_grading_multi` | `ingame.ingame_grading_multi_runner --interval 900` | 900s | heartbeat, fresh 2000s | soccer_intl/tennis/wnba counterpart to m25+m26 (**not yet running**) | `ingame_outcome_verdict_multi.json`, `ingame_segment_trust_multi.json` |
| `m37_ingame_enrichment` | `ingame.ingame_enrichment_runner --interval 30` | 30s | heartbeat, fresh 90s | Combined fotmob + GUMBO + book-depth capture tick (**not yet running**) | `data/frontend/ops/ingame_enrichment.json` |
| `m38_autoloop` | `autoloop.autoloop_runner --interval 86400` | daily | heartbeat, fresh 190000s | Zero-LLM composed ratchet/reclaim-gate/claims-factory cycle (**not yet running**) | `data/frontend/ops/autoloop_report.json`, `autoloop_human_queue.jsonl` |
| `m39_injury_facts_nba` | `edge_engine.injury_daemon --interval 21600` | 6h | heartbeat, fresh 45000s | NBA/WNBA injury-facts snapshotter, the NBA sibling of m31's MLB context snapshot (**not yet running**) | `data/cache/daemon_heartbeats/m39_injury_facts_nba.txt` |
| `m40_wedge_restarter` | `ops_sentinel.wedge_restarter --interval 300` | 300s | heartbeat, fresh 660s | Turns a persistent output-freshness RED into a rate-limited restart request the supervisor honors (**not yet running**) | `data/cache/daemon_heartbeats/m40_wedge_restarter.txt` |
| `m41_public_splits` | `data_frontier.an_public_splits --interval 86400` | daily | heartbeat, fresh 190000s | Action Network public-splits daily capture (**not yet running**) | `data/cache/daemon_heartbeats/m41_public_splits.txt` |

A handful of daemons ("`independent branch`" in the source comments, mostly
m19-m41) declare `depends_on=[]` on purpose: one dead feed is one red status
row and the rest of the fleet keeps running. The `readiness=none` group
(m19-m27) trades a HEARTBEAT window for a daily-batch shape where a fixed
freshness window would just flicker -- but that shape has its own blind spot,
covered next.

### The older watchdog layer

Before `supervisor/`, a simpler pattern covered scraper/paper-trading
daemons: `scripts/daemon_registry.json` (28 entries -- `vault_dashboard_daemon`,
`clv_tracker_daemon`, `middle_finder_daemon`, `line_move_detector`,
`arb_emitter_daemon`, `nba_lineup_daemon`, `bankroll_monitor_daemon`,
`auto_settle_daemon`, `unified_scraper_orchestrator`, `fd_scraper`,
`bov_scraper`, `pinnacle_scraper`, `dk_inplay_scraper`, `fd_inplay_scraper`,
`predict_service_api`, `predict_service_scheduler`, `line_snapshot_daemon`,
`ingame_live_loop`, `m2_inplay`, `m2_inplay_capture`, `m4_selfimprove`,
`m7_ingame_refresh`, `m10_best_bets_compute`, `m11_ingame_pred_tick`,
`m12_pm_paper_tick`, `cross_venue_arb`, `m13_props_pred_tick`,
`wnba_injuries_daily`) each carrying a
launch command, a heartbeat path, a `ps`-matched `process_match` string, and
a `restart_cmd` already wrapped in `nohup`/`tmux`. `scripts/daemon_watchdog.py`
sweeps this registry independently of the supervisor: a daemon is dead if its
heartbeat is older than `expected_interval_sec * 3` **or** no matching
process is found; on death it shells the `restart_cmd`, fires a Discord WARN
alert, and appends a row to `vault/Improvements/daemon_restarts.md`, capped
at 3 restarts/hour per daemon (sliding window) so a chronically broken daemon
doesn't restart-loop forever. `--dry-run` and `--once` exist for the unit
test and manual probes. This layer still runs for the daemons registered in
it; it is not a duplicate of `supervisor/` -- it predates it and was never
migrated.

---

## Reading fleet health

No single file tells you "is everything fine" -- reading health means
knowing which sentinel owns which question:

- **`data/frontend/ops/feed_health.json`** (m30, every 600s) -- per
  `(provider, sport)` GREEN/RED. Closes the blind spot where
  `aggregate.default_providers()` silently drops a down/blocked odds book
  from the merged slate; a 401/403/timeout used to just vanish.
- **`data/frontend/ops/ingame_paper_settle_status.json`** (m27, every 900s)
  -- whether the in-game paper-settle arm is draining OPEN `paper_ingame`
  rows. See the m27 war story below for why this file exists at all.
- **`.bot_state/live_status.json`** -- the autonomous build/platform loop's
  own stop-flag + status surface (`scripts/bot_guards/watch.py`,
  `scripts/platform_harness/build_status.py`); read by `stop_bot.py` to
  confirm nothing is mid-run before it brakes. Not a daemon heartbeat --
  it's the higher-level "is the bot loop itself running" answer.
- **`data/frontend/ops/output_freshness.json`** (m29, every 300s) -- the
  readiness=NONE daemons (m19-m27) have no useful HEARTBEAT window, so a
  wedged tick (process alive, but its scoreboard/verdict file stopped
  advancing) was otherwise invisible. m29 checks each declared output
  artifact's mtime against its own cadence and writes GREEN/RED. Read-only,
  no restart authority -- it exists purely to make a silent failure visible
  to a human or to m5.
- **`data/frontend/ops/freshness_sla.json`** (m34, every 300s) -- the same
  idea generalized to the *entire* fleet, not just m19-m27: a
  HEARTBEAT-fresh process can still be looping with a wedged inner step
  (beating its own heartbeat while silently failing to touch its real
  output). A daemon absent from `freshness_sla.TABLE` reads `NA`, never
  `GREEN` -- an honest gap, not a silent pass.
- **`data/frontend/ops/autonomy_status.json`** (m5, every ~60s) -- the one
  canonical composed status across the fleet; m5 itself beats a heartbeat so
  a dead monitor is its own red entry rather than an absent-as-green file.

---

## War stories (design lessons, not war trophies)

**The m18 heartbeat flap (2026-07-07).** `m18_pm_close_capture` started
flapping its heartbeat under a full live slate. Root cause:
`kalshi_rate_governor.py`'s `DEFAULT_RATE_SHARES` had no entry for
`close_capture`, so it fell back to the unknown-caller default of 0.5 --
which, added to the two live-trading daemons' shares, over-subscribed the
shared 15 rps Kalshi ceiling and triggered a 429 storm that slowed every
sweep past its freshness bar. The fix registered an explicit 0.15 share for
`close_capture` (a 900s-interval settled-row sweep, not a hot loop -- it
doesn't need much), bounded the sweep to a max-rows-per-tick cap so a
throttled sweep can never outlast its own freshness window, and moved the
heartbeat beat to fire *before* the sweep rather than after. Lesson: an
"unknown caller" default in a shared-resource governor is not a safe
default -- every real caller needs an explicit, reasoned share, or it
silently steals from the ones that do.

**The m27 zero-settle silent failure (2026-07-01).** The in-game
day-trader channel placed 82 `paper_ingame` bets over time; zero of them
ever settled. Nothing crashed, nothing alerted -- `inplay_daytrader` placed
correctly, but no settler ever matched the rows because they were keyed by
the **Kalshi ticker**, not the ESPN game id an earlier settler expected. The
gap was invisible precisely because m27 (like m19-m26) uses
`readiness=none`: the process was alive the whole time, so the supervisor's
own health view read fine. The fix was two-fold: (1) `m27_ingame_paper_settle`
itself, which resolves each bet's final score directly from the Kalshi
ticker (`ingame_outcome_label.final_score` joined to the local realized-box
parquet) so settlement no longer depends on an id bridge that didn't exist;
and (2) `m29_output_freshness`, built specifically because this class of bug
-- a `readiness=none` daemon whose *output*, not its process, silently
stopped advancing -- had no sentinel at all. A game not yet final stays
OPEN rather than being force-settled; already-settled rows are skipped by
edge_key, so re-runs are idempotent.

**The supervisor-tick wedge (2026-06-23 through 2026-07-04, 36+ events).**
Covered above under "two-layer heartbeats" -- included here as the
clearest example of a false-positive cascade: the supervisor's *own*
serial-probe tick occasionally ran long enough to trip the watchdog, which
then killed and rebooted the healthy supervisor, which then relaunched
every spec, making unrelated daemons look like they'd crashed independently
when they'd actually just been restarted by the reboot. Diagnosing that
required reading `logs/watchdog_autostart.log` and
`data/frontend/ops/api_crash_20260704_rootcause.json` side by side and
noticing the restart timestamps clustered, not scattered -- a lockstep
crash pattern is almost always one thing restarting many things, not many
things failing at once.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)

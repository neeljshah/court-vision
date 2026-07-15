"""supervisor.stack_specs -- the supervised process INVENTORY (the DATA table).

This is a DATA module: the literal ProcSpec inventory of the real always-on
stack boot.ps1 launches (producer/scheduler, Auto-API :8099, boards API :8098,
UI :3000, paper loop, line daemon, in-game loops). It was carved out of
``supervisor.manifest`` so manifest.py stays under the <=300 LOC rail and keeps
only the dataclasses + topo_order + the manifest() selector. Behavior-preserving
move only -- the ProcSpec list is byte-for-byte the prior _base_specs().

Sport-blind: nothing here imports a sport adapter. Readiness paths reuse the
real on-disk heartbeats. Stdlib-only, ASCII-only, no process is spawned, no flag
is flipped, ``data/registry/`` is never written.
"""
from __future__ import annotations

import os
from typing import List

from supervisor.manifest import (
    HEARTBEAT,
    HTTP,
    TCP,
    ProcSpec,
    ReadinessSpec,
    RestartPolicy,
)

# --------------------------------------------------------------------------- #
# The real stack inventory
# --------------------------------------------------------------------------- #
# Heartbeat paths mirror the REAL writers (relative to repo root):
_PRED_HB = "data/frontend/predict_service/_heartbeat.json"
_INGAME_HB = "data/frontend/ingame/_heartbeat.json"
# The two supervised runner daemons beat ops.liveness txt heartbeats (P2 + P4).
_INPLAY_HB = "data/cache/daemon_heartbeats/m2_inplay.txt"
_SELFIMPROVE_HB = "data/cache/daemon_heartbeats/m4_selfimprove.txt"
# RB-P0-03: m1_paper + m1_line_daemon historically had readiness=NONE and wrote
# NO heartbeat -- a hung loop read READY forever. BOTH daemons now BEAT their
# declared heartbeat every cycle (auto_loop.main / line_snapshot_daemon.serve_forever
# call ops.liveness.heartbeat), so readiness is flipped to kind=HEARTBEAT below:
# an ABSENT heartbeat (fresh boot, not yet beating) OR a STALE one (hung loop)
# now reads NOT-READY -- never a stale-green. fresh_sec exceeds each loop's slowest
# cadence (paper ~20min default, line phase-aware up to 15min) by a safe margin.
_PAPER_HB = "data/cache/daemon_heartbeats/m1_paper.txt"
_LINE_DAEMON_HB = "data/cache/daemon_heartbeats/m1_line_daemon.txt"
# m1_bankroll -- the daily-bankroll measurement daemon (PAPER-only). It beats this
# heartbeat at boot + every tick; absent/stale -> NOT-READY (never a stale-green).
_BANKROLL_HB = "data/cache/daemon_heartbeats/m1_bankroll.txt"
# The living in-game refresh loop (folds newly-settled finals -> re-gate -> re-fit).
_INGAME_REFRESH_HB = "data/cache/daemon_heartbeats/m7_ingame_refresh.txt"
# M5 -- the autonomy monitor: publishes the ONE canonical autonomy_status.json on a
# ~60s cadence + beats this heartbeat. MEASUREMENT-ONLY (composes, never ships).
_AUTONOMY_MONITOR_HB = "data/cache/daemon_heartbeats/m5_autonomy_monitor.txt"
# M8 -- the continuous-improvement CADENCE (W4): the ci_cadence_runner loop-wrapper
# runs ONE ci_cadence tick (INERT, measurement-only) per HOURLY-light interval and beats
# this heartbeat at boot + every tick. Absent/stale -> NOT-READY (never a stale-green).
_CI_CADENCE_HB = "data/cache/daemon_heartbeats/m8_ci_cadence.txt"
# W4 -- the in-play CAPTURE daemon (inplay_capture_runner loop-wrapper): per live game
# per tick captures (model, devigged-price) pairs + paper UNIT decisions + FINAL labels,
# beating this heartbeat on every phase-aware (live/idle) poll boundary. PAPER-ONLY.
_INPLAY_CAPTURE_HB = "data/cache/daemon_heartbeats/m2_inplay_capture.txt"
# M29 -- the OUTPUT-FRESHNESS sentinel. m19-m27 all use readiness=NONE (a daily/
# slow-batch loop has no useful HEARTBEAT window), so a WEDGED tick -- process still
# alive, but its scoreboard/verdict/status file silently stopped advancing -- is
# INVISIBLE to the supervisor's own health view today. Every ~300s this checks each
# of those 9 daemons' declared output artifact mtime against its expected cadence and
# writes GREEN/RED per daemon to data/frontend/ops/output_freshness.json. NO restart
# authority (read-only visibility only; the supervisor + heartbeat_reaper still own
# restarts). Independent branch (no depends_on) so a dead sentinel tick is itself ONE
# red status entry. NO $ field, NO flag flip, NO data/registry/ write, NO real-money
# action.
_OUTPUT_FRESHNESS_HB = "data/cache/daemon_heartbeats/m29_output_freshness.txt"
# M30 -- the FEED-HEALTH sentinel. aggregate.default_providers() silently drops a
# down/blocked odds-book venue from the merged slate (a 401/403/timeout just vanishes
# -- nobody notices without reading logs). Every ~600s this live-probes every real
# (provider, sport) pair and writes GREEN/RED per venue to
# data/frontend/ops/feed_health.json. Read-only visibility only, NO restart authority.
# Independent branch (no depends_on) so a dead sentinel tick is itself ONE red row.
# NO $ field, NO flag flip, NO data/registry/ write, NO real-money action.
_FEED_HEALTH_HB = "data/cache/daemon_heartbeats/m30_feed_health.txt"

# M38 -- the AUTOLOOP daemon (AUTOLOOP_SPEC_2026-07-06.md, sha e654d58a...; R-B/
# R-B erratum + R-C/R-D/R-E rulings binding). ZERO-LLM: composes the EXISTING
# P4 ratchet / reclaim-gate / claims-factory / FWER-curve harnesses under a
# sha-pinned standing-prereg registry (scripts/platformkit/autoloop/templates/)
# -- no new math, no new gate. Watermark-triggered (corpus content-sha, not a
# timer) so unchanged settled data never re-fits and never inflates K. Daily
# cadence (86400s); readiness=NONE would also be defensible (mirrors m19), but
# a HEARTBEAT is used here (mirrors m29/m30) so the freshness sentinels can see
# it too. fresh_sec = 2x the 86400s cadence + margin so a healthy daily tick
# stays fresh while a genuinely dead/hung run ages out. MEASUREMENT/SUPPRESS-
# ONLY: never flips a flag, never writes data/registry/, never touches
# PIPELINE_ENABLED, never promotes a SHIP into the served predictor (an
# in-model SHIP or a SHIP_REVIEW is a human/Fable queue row, sec 4 of the
# spec) -- appends only to data/frontend/ops/autoloop_report.json +
# autoloop_human_queue.jsonl + the append-only K ledger/reject_ledger under
# data/cache/autoloop/. Independent branch (no depends_on) so a dead tick is
# ONE red status entry. NOT YET RUNNING -- registered here but requires a
# supervisor restart (or an explicit orchestrator reload) to take effect per
# R-C; this wave does NOT bounce the supervisor.
_AUTOLOOP_HB = "data/cache/daemon_heartbeats/m38_autoloop.txt"

# M31 -- MLB pregame-context snapshotter (probables/weather/umps + injuries + edge
# facts, 6h cadence). Heartbeat freshness gates readiness; see mlb_context_runner.
_MLB_CONTEXT_HB = "data/cache/daemon_heartbeats/m31_mlb_context.txt"

# M32 -- MLB context autogate: nightly re-run of the SP-offset + weather-totals
# candidate gates against the growing M31 context corpus. VERDICTS ONLY -- never
# wires/ships a winner. Heartbeat freshness gates readiness; see
# mlb_context_autogate_runner.
_MLB_CONTEXT_AUTOGATE_HB = "data/cache/daemon_heartbeats/m32_mlb_context_autogate.txt"
_INGAME_TAIL_MULTI_HB = "data/cache/daemon_heartbeats/m35_ingame_tail_multi.txt"
_INGAME_GRADING_MULTI_HB = "data/cache/daemon_heartbeats/m36_ingame_grading_multi.txt"

# M37 -- LANE 2 combined wave-10 enrichment tick: fotmob (soccer live, ~30s
# runner cadence, fotmob's own poll_once paces its per-match GETs internally)
# + gumbo (mlb live GUMBO ticks, id-bridged via game_pk_bridge_live) + book-
# depth (live in-play kalshi/polymarket snapshots), each source try/except-
# isolated so one raising source never sinks the tick or blocks a sibling.
# CAPTURE/MEASUREMENT ONLY -- touches no bet/decision path, flips no flag,
# writes no data/registry/; composes ONE small ops summary doc
# (data/frontend/ops/ingame_enrichment.json). NOT YET RUNNING -- registered
# here but requires a supervisor restart to take effect (restart pending).
# fresh_sec = 2x the 30s cadence + margin.
_INGAME_ENRICHMENT_HB = "data/cache/daemon_heartbeats/m37_ingame_enrichment.txt"

# M14 -- the brain-rebuild cadence (brain_rebuild_runner loop-wrapper): rebuilds the
# organized, person-free Obsidian brain (vault/_Organized) from the deep
# _vault_legacy_archive source on a slow (default 6h) cadence so the knowledge graph
# stays FULLY REACHABLE + fresh WITHOUT a self-installing OS scheduler. It beats this
# heartbeat at boot + every boundary; absent/stale -> NOT-READY (never a stale-green).
_BRAIN_REBUILD_HB = "data/cache/daemon_heartbeats/m14_brain_rebuild.txt"

# M33 -- the HTTP-readiness WEDGE reaper (reliability lane, closes the gap
# heartbeat_reaper does not cover: an HTTP-readiness proc, e.g. m1_api_paper
# :8099, whose event loop wedges keeps its port LISTENING with every HTTP probe
# timing out -- no heartbeat file means heartbeat_reaper never restarts it).
# Every 30s it probes each declared HTTP-readiness target's port + HTTP health
# + per-PID CPU%; kills ONLY a PID meeting BOTH >=3 consecutive >10s timeouts
# (port still listening) AND CPU>50% sustained >120s (the supervisor's normal
# restart/backoff path relaunches it). See http_wedge_reaper_runner.TARGETS.
# NO $ field, NO flag flip, NO data/registry/ write, NO restart authority
# beyond the single targeted kill.
_HTTP_WEDGE_REAPER_HB = "data/cache/daemon_heartbeats/m33_http_wedge_reaper.txt"

# M34 -- the per-daemon FRESHNESS SLA scoreboard (reliability lane). Every 300s
# checks every supervised daemon name against freshness_sla.TABLE and writes a
# GREEN/RED/NA row per daemon (a name absent from TABLE reads NA, never GREEN).
# Read-only, NO restart authority. See freshness_sla.TABLE + freshness_sla_runner.
_FRESHNESS_SLA_HB = "data/cache/daemon_heartbeats/m34_freshness_sla.txt"

# M39 -- NBA/WNBA injury-facts snapshotter (the NBA sibling of m31's MLB injury
# snapshot). Every 6h it fetches the ESPN injuries feed for each wired basketball
# sport, snapshot-dates every row (as-of vintage history), and appends to the same
# injury_facts_<sport>.jsonl the gamebrief layer reads. KNOWLEDGE/SUBSTRATE only.
# fresh_sec = 2x the 21600s cadence + margin (mirrors m31).
_INJURY_FACTS_HB = "data/cache/daemon_heartbeats/m39_injury_facts_nba.txt"

# M40 -- the WEDGE-RESTARTER detector. Reads m29's output_freshness.json; a daemon
# RED for >=3 consecutive reads gets ONE rate-limited RESTART_REQUEST row appended
# to data/frontend/ops/restart_requests.jsonl, which the supervisor's own pickup
# seam (supervisor._restart.process_restart_requests) honors -- protected-daemon-
# safe + max 1 honored restart per daemon per 30min. REQUEST-ONLY (the detector
# decides nothing about killing; the supervisor is the sole actor). 300s cadence
# (mirrors m29, the source it reads); fresh_sec=660 (>2x + margin). NO $ field, NO
# flag flip, NO data/registry/ write, NO restart authority of its own.
_WEDGE_RESTARTER_HB = "data/cache/daemon_heartbeats/m40_wedge_restarter.txt"
# M42 -- the EXECUTION-QUALITY tick: closes the last manual-only hop in the
# execution-quality loop (measured CLV -> breaker states -> digest -> webapp).
# Every 120s it (a) runs ingame_realized_clv.backfill(write=True) ONE-SHOT per
# bet (min-age filtered so a bet is graded only once its longest horizon could
# have ticked -- grading earlier would permanently lock an incomplete sidecar
# row) and (b) rebuilds paper_today.build_today() -> data/frontend/
# paper_today.json so the per-market circuit-breaker states + execution block
# the webapp reads stay fresh between m1_bankroll's own ~600s writes.
# MEASUREMENT ONLY -- no bet/decision path touched, no flag flip, no
# data/registry/ write, no $ field, no edge claim. Independent branch (no
# depends_on) so a dead tick is itself ONE red status entry. NOT YET RUNNING --
# registered here but requires a supervisor restart to take effect. fresh_sec
# = 2.5x the 120s cadence + margin.
_EXEC_QUALITY_HB = "data/cache/daemon_heartbeats/m42_exec_quality.txt"

# M41 -- Action Network public-betting-splits DAILY capture (frontier queue rank 3).
# In-season reprobe 2026-07-09 confirmed /web/v2/scoreboard/mlb bet_info
# tickets/money percents POPULATED (1436/1696 non-null, 13 games); the puller
# (scripts.platformkit.data_frontier.an_public_splits) appends one row per
# (game, book, market, side) to data/cache/public_splits/<league>/<date>.jsonl
# at 1 req/s. Sentiment-vs-price capture only -- no bet, no flag, no $ field.
# fresh_sec = 2x the 86400s cadence + margin (mirrors m38's daily-daemon shape).
_PUBLIC_SPLITS_HB = "data/cache/daemon_heartbeats/m41_public_splits.txt"

# M43 -- the SETTLEMENT SWEEP (EXECUTION_BACKLOG.md lever 7). Hundreds of open
# paper positions aged >=7d (320 true after identity-pairing correction; the
# backlog doc's 698 included 377 phantom opens m27 had already settled under
# minted-bet_id twins) sit unsettled even though a settler already exists per
# channel/market (backfill_as_of / prop_settler.settle_open_props /
# ingame_paper_settle.settle_open) -- nothing SWEEPS the aged backlog through
# them on a schedule. Hourly this retries the aged backlog via those existing
# (imported, never reimplemented) settlers, then appends an honest VOID twin
# for any row that is provably unroutable (malformed identity, or no resolver
# wired for that sport/market) -- see scripts.platformkit.paper.settle_sweep's
# module docstring for the VOID encoding rationale. Settlement/measurement
# only: no $ field, no flag flip, no data/registry/ write, no edge claim.
# fresh_sec = 2.5x the 3600s cadence + margin (mirrors m42's ratio).
_SETTLE_SWEEP_HB = "data/cache/daemon_heartbeats/m43_settle_sweep.txt"

_FOREVER = RestartPolicy(max_retries=None, backoff_base_sec=2.0, backoff_cap_sec=60.0)

# The Next.js UI directory. Default "court-visions" (the original wired app);
# set NBA_AI_UI_DIR=webapp to boot the newer P5/P6 dashboard (reads :8099,
# /api/improve/status, /api/parity, /api/ops/status). Additive + reversible:
# nothing changes unless the env var is explicitly set.
_UI_DIR = os.environ.get("NBA_AI_UI_DIR", "court-visions").strip() or "court-visions"
# Prod build serve vs dev: NBA_AI_UI_CMD overrides (e.g. "npm run start" after a
# `npm run build`). Default keeps the existing dev-server behavior.
_UI_CMD = os.environ.get("NBA_AI_UI_CMD", "npm run dev").strip() or "npm run dev"


def base_specs() -> List[ProcSpec]:
    """The default profile: the full stack boot.ps1 launches (with the UI)."""
    return [
        ProcSpec(
            name="m1_producer", kind="py",
            module="predict_service.scheduler", argv=["--interval", "600"],
            # The scheduler produces all active sports + writes _PRED_HB every
            # cycle. RB EARLY-WARNING: a default NONE readiness leaves fresh_sec
            # unset, so the health_aggregator stale-never-green DEGRADED arm (which
            # requires fresh_sec is not None) can NEVER fire for this CRITICAL
            # producer -- its health is binary at the single 2700s liveness wall
            # (silent 2000s reads GREEN, 2701s reads DOWN), so a hung producer is
            # invisible for up to ~45min. A HEARTBEAT ReadinessSpec restores the
            # middle band: a healthy producer beats well within its cadence (NBA
            # ~600s, soccer ~1200s slowest) -> OK; a silent 1500-2700s window ->
            # DEGRADED (early warning); silent >2700s -> still DOWN (the 2700s
            # liveness window in ops.liveness._FRONTEND_LIVE_WINDOW is UNCHANGED, so
            # genuine death is never masked). fresh_sec=1500 sits safely ABOVE the
            # slowest healthy beat (soccer ~1200s) WITH margin so an idle-but-healthy
            # producer never false-REDs, yet below the 2700s liveness/data-SLA wall
            # so the gap fires DEGRADED rather than staying silently GREEN.
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_PRED_HB, fresh_sec=1500.0),
            restart_policy=_FOREVER,
        ),
        ProcSpec(
            name="m1_api_paper", kind="py", module="predict_service.app",
            port=8099, depends_on=["m1_producer"],
            readiness=ReadinessSpec(kind=HTTP, http_path="/health"),
            restart_policy=_FOREVER,
        ),
        ProcSpec(
            name="m1_api_boards", kind="py",
            module="scripts.platformkit.frontend.serve",
            port=8098, depends_on=["m1_api_paper"],
            readiness=ReadinessSpec(kind=TCP),
            restart_policy=_FOREVER,
        ),
        ProcSpec(
            name="m1_ui", kind="node", cmd=_UI_CMD,
            port=3000, depends_on=["m1_api_boards"], cwd=_UI_DIR,
            readiness=ReadinessSpec(kind=TCP),
            restart_policy=RestartPolicy(
                max_retries=None, backoff_base_sec=3.0, backoff_cap_sec=90.0),
        ),
        ProcSpec(
            name="m1_paper", kind="py",
            module="scripts.platformkit.pm_trading.auto_loop",
            argv=["--forever"], depends_on=["m1_api_paper"],
            # RB-P0-03: the loop now BEATS _PAPER_HB at boot + every cycle, so
            # readiness is HEARTBEAT: absence (not-yet-beating) OR staleness (hung
            # cycle) -> not-ready, never a stale-green NONE. The default cycle is
            # ~20min (--interval 1200); fresh_sec=2700 (>2x + margin) keeps a
            # HEALTHY loop fresh between beats while a genuinely DEAD loop ages out.
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_PAPER_HB, fresh_sec=2700.0),
            restart_policy=_FOREVER,
        ),
        ProcSpec(
            name="m1_line_daemon", kind="py",
            module="scripts.platformkit.odds_provider.line_snapshot_daemon",
            # RB-P0-03: serve_forever now BEATS _LINE_DAEMON_HB at boot + every tick,
            # so readiness is HEARTBEAT: absence/staleness -> not-ready (no stale-green).
            # The slowest phase-aware cadence is SLOW_INTERVAL_SEC=900s when no game is
            # near tip; fresh_sec=2700 (>2x + margin) keeps a healthy daemon fresh while
            # a dead/hung tick ages out.
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_LINE_DAEMON_HB, fresh_sec=2700.0),
            restart_policy=_FOREVER,
        ),
        # m1_bankroll -- the DAILY-bankroll measurement daemon (PAPER-only). Every
        # ~600s it reads the SETTLED placed paper bets from the CLV ledger, accumulates
        # the DAILY + CUMULATIVE units P&L onto the starting bankroll, and writes
        # data/frontend/paper_pnl_series.json + paper_bankroll.json + paper_today.json
        # (the execution / best-bets view), then beats _BANKROLL_HB. The curve
        # RECONCILES to the staked bets (it is the literal sum of their graded
        # unit_results, flat 1 unit). Independent branch (no depends_on) so a dead tick
        # is ONE red status entry. UNITS not $, no edge claimed, no flag flip, no
        # data/registry/ write, no autostart, no real money. The runner BEATS at boot +
        # every tick; fresh_sec=1500 (>2x the 600s cadence + margin) keeps a healthy
        # daemon fresh while a genuinely dead/hung tick ages out (never a stale-green).
        ProcSpec(
            name="m1_bankroll", kind="py",
            module="scripts.platformkit.paper.bankroll_daemon",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_BANKROLL_HB, fresh_sec=1500.0),
            restart_policy=_FOREVER,
        ),
        # m6 -- the always-on MULTI-SPORT in-game loop. Pass an explicit --sports so
        # coverage is DETERMINISTIC (it reprices every sport that can be live right
        # now -- MLB live mid-season, soccer club + World Cup, NBA even in offseason,
        # tennis) rather than the old NBA-only default that went dark all summer. A
        # sport with zero live games is an honest idle and never blocks the others;
        # the loop still beats _INGAME_HB every tick on a quiet slate.
        ProcSpec(
            name="m6_ingame_loop", kind="py",
            module="scripts.platformkit.ingame.live_loop",
            argv=["--sports", "mlb,soccer,soccer_intl,nba,tennis"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INGAME_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # P2 -- in-play capture daemon (per-sport isolated INSIDE the loop). Fully
        # independent branch (no depends_on) so a dead capture feed is ONE red
        # status entry and the rest of the stack keeps running.
        ProcSpec(
            name="m2_inplay", kind="py",
            module="scripts.platformkit.odds_provider.inplay_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INPLAY_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # P4 -- self-improve daemon (checkpoint-resumable; measurement-only by
        # default). Independent branch; one dead source = one red entry.
        ProcSpec(
            name="m4_selfimprove", kind="py",
            module="scripts.platformkit.improve.selfimprove_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_SELFIMPROVE_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # M7 -- the LIVING in-game refresh loop: folds newly-settled in-season finals
        # into each sport's corpora, RE-GATES + RE-FITS the served in-game model, and
        # HONESTLY swaps (or DOWNGRADES) its provenance. Checkpoint-resumable, per-sport
        # isolated, hourly cadence. Independent branch (no depends_on) so a dead settled
        # feed is ONE red status entry and the rest of the stack keeps running.
        ProcSpec(
            name="m7_ingame_refresh", kind="py",
            module="scripts.platformkit.ingame.ingame_refresh_runner_svc",
            # m7 beats HOURLY (cadence_sec=3600); a 300s freshness window would
            # flicker stale between beats. Set the window to comfortably exceed
            # the beat cadence (2x + margin) so a healthy m7 reads fresh and only
            # a genuinely DEAD/stalled m7 ages out.
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INGAME_REFRESH_HB, fresh_sec=7800.0),
            restart_policy=_FOREVER,
        ),
        # M5 -- the AUTONOMY MONITOR (measurement-only). Every ~60s it composes the
        # ONE canonical autonomy status (status_composer) and ATOMICALLY publishes
        # data/frontend/ops/autonomy_status.json, then beats this heartbeat so a
        # DEAD monitor (stale status file) is itself RED, never absent-as-green.
        # Independent branch (no depends_on) so a sick monitor is ONE red status
        # entry and the rest of the stack keeps running. It ships nothing, flips no
        # flag, registers no autostart, touches no real money.
        ProcSpec(
            name="m5_autonomy_monitor", kind="py",
            module="scripts.platformkit.autonomy.autonomy_monitor_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_AUTONOMY_MONITOR_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # M8 -- the CONTINUOUS-IMPROVEMENT cadence (W4, measurement-only). The
        # ci_cadence_runner loop-wrapper runs ONE ci_cadence tick per HOURLY-light
        # interval: refresh backlog -> enqueue a measurement kind (ALLOWED_KINDS only) ->
        # auto-gate (INERT: recalibrate_fn=None -> NO_CANDIDATE while the sentinel is
        # absent) -> re-gate grown data + survivor re-check -> append ONE progress row.
        # The ship path stays INERT/proposal-only. Independent branch (no depends_on) so
        # a dead cadence is ONE red status entry and the rest of the stack keeps running.
        # m8 beats hourly; fresh_sec=7800 (>2x + margin) keeps a healthy runner fresh
        # while a genuinely dead/hung tick ages out. It ships nothing, flips no flag,
        # registers no autostart, creates no sentinel, touches no real money.
        ProcSpec(
            name="m8_ci_cadence", kind="py",
            module="scripts.platformkit.progress.ci_cadence_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_CI_CADENCE_HB, fresh_sec=7800.0),
            restart_policy=_FOREVER,
        ),
        # W4 -- the in-play CAPTURE daemon (measurement-only). The inplay_capture_runner
        # loop-wrapper drives serve_forever: per live game per tick it captures the
        # (model_prob carrying the proven P1 prior, devigged KX<league>GAME price) pair ->
        # data/cache/ingame_grade/<sport>/<game_id>.jsonl, paper-decides in UNITS
        # (executed=False, idempotent), and stamps the held-out home_win label on ESPN
        # FINAL so the OUTCOME arm can fire once >=5 games settle. Independent branch (no
        # depends_on) so a dead capture feed is ONE red status entry and the rest of the
        # stack keeps running. Phase-aware cadence 20s live / 120s idle; fresh_sec=300
        # (>2x idle + margin) keeps a healthy loop fresh while a dead tick ages out.
        # PAPER-ONLY: no $ field, no real money, no flag flip, no autostart arm.
        ProcSpec(
            name="m2_inplay_capture", kind="py",
            module="scripts.platformkit.ingame.inplay_capture_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INPLAY_CAPTURE_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # M10 -- best-bets compute daemon (MEASUREMENT-ONLY, W11/W12).
        # Every 120s: computes model-vs-market divergence ranked by calibrated
        # confidence across all sports and atomically writes
        # data/frontend/best_bets.json. Independent branch (no depends_on) so a
        # dead compute run is ONE red status entry. NO $ field, NO flag flip,
        # NO data/registry/ write, NO autostart.
        ProcSpec(
            name="m10_best_bets_compute", kind="py",
            module="scripts.platformkit.bestbets.bestbets_compute_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m10_best_bets_compute.txt",
                fresh_sec=300.0),   # 2x cadence (240s) + margin
            restart_policy=_FOREVER,
        ),
        # M11 -- in-game prediction tick daemon (MEASUREMENT-ONLY, W11/W12).
        # Phase-aware: 20s live / 120s idle. Writes
        # data/frontend/ingame/live_pred_<game_id>.json per live game.
        # Independent branch (no depends_on). NO $ field, NO flag flip.
        ProcSpec(
            name="m11_ingame_pred_tick", kind="py",
            module="scripts.platformkit.ingame.ingame_pred_tick_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m11_ingame_pred_tick.txt",
                fresh_sec=300.0),   # 2x idle (240s) + margin
            restart_policy=_FOREVER,
        ),
        # M12 -- PM (Kalshi/Polymarket) paper-trail tick (PAPER-ONLY, W11/W12).
        # Every 60s: records model-vs-PM-price pairs per market to
        # data/cache/pm_paper/<market>.jsonl. Independent branch (no depends_on).
        # NO $ field, NO real money, NO flag flip, NO autostart.
        ProcSpec(
            name="m12_pm_paper_tick", kind="py",
            module="scripts.platformkit.pm_trading.pm_paper_tick_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m12_pm_paper_tick.txt",
                fresh_sec=150.0),   # 2x cadence (120s) + margin
            restart_policy=_FOREVER,
        ),
        # M13 -- props prediction tick daemon (MEASUREMENT-ONLY, W11/W12).
        # Every 300s: re-scores prop lines on fresh price; writes
        # data/frontend/props_snapshot.json. Independent branch (no depends_on).
        # NO $ field, NO flag flip, NO autostart.
        ProcSpec(
            name="m13_props_pred_tick", kind="py",
            module="scripts.platformkit.props.props_pred_tick_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m13_props_pred_tick.txt",
                fresh_sec=660.0),   # 2x cadence (600s) + margin
            restart_policy=_FOREVER,
        ),
        # M14 -- the BRAIN-REBUILD cadence (intelligence MAP, person-free, NO edge).
        # The brain_rebuild_runner loop-wrapper rebuilds vault/_Organized from the deep
        # _vault_legacy_archive source on a slow (default 6h) cadence: organize -> the
        # full DEEP model stages (--with-models: calibration / drivers / mechanisms /
        # archetypes / keystats / concept-nodes+map / crosslinks / transfer / form-
        # profiles) -> digest -> export -> graph-finalize, keeping the whole ~5k-node
        # brain ONE fully-reachable person-free graph WITHOUT a self-installing OS
        # scheduler. --with-models is REQUIRED: the base organize alone yields only
        # ~600 nodes, so a light rebuild would rmtree the deep brain back down -- the
        # deep stages are what make it ~5k nodes. It serializes against manual
        # brain_pipeline runs via a best-effort lockfile (no two rmtree the same tree at
        # once). Independent branch (no depends_on) so a dead rebuild is ONE red status
        # entry and the rest of the stack keeps running. m14 beats at boot + every
        # boundary; fresh_sec (>2x the 6h cadence + margin) keeps a healthy runner fresh
        # while a genuinely dead/hung rebuild ages out. It ships nothing, flips no flag,
        # creates no sentinel, writes no data/registry/ or MEMORY.md, arms no autostart /
        # real money / push.
        ProcSpec(
            name="m14_brain_rebuild", kind="py",
            module="scripts.platformkit.brain_rebuild_runner",
            argv=["--with-models"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_BRAIN_REBUILD_HB, fresh_sec=46800.0),
            restart_policy=_FOREVER,
        ),
        # M15 -- the prop-SETTLE arm (PAPER-only, the missing settle counterpart to
        # m13's place arm). Every 900s it settles OPEN player props on the REAL
        # post-game stat into clv_ledger.jsonl so the CLV-yardstick ledger drains
        # instead of accumulating an open backlog; unresolvable props stay PENDING
        # (never fabricated), idempotent on already-settled twins. Independent branch
        # (no depends_on) so a dead settle arm is ONE red status entry. UNITS not $;
        # executed=False; NO edge claim, NO flag flip, NO data/registry/ write.
        ProcSpec(
            name="m15_prop_settle", kind="py",
            module="scripts.platformkit.bestbets.prop_settle_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m15_prop_settle.txt",
                fresh_sec=1980.0),   # 2x cadence (900s) + margin
            restart_policy=_FOREVER,
        ),
        # M16 -- the prop-CLOSE-CAPTURE arm (CLV measurability + improve-loop fuel).
        # Every 60s it snapshots the live two-way price of OPEN in-game props into
        # prop_close_store so they become CLV-measurable; the captured-close corpus is
        # the 2nd independent corpus the recalibrator needs to ship a calibration win.
        # A faster supervised cadence (vs auto_loop's 20min tick) catches the last
        # price before a market suspends. Cheap-when-idle (skips network when no
        # in-game props open); non-fabricating (records only a real two-way). Independent
        # branch (no depends_on). PRICES not bets; NO $ field, NO flag flip, NO
        # data/registry/ write.
        ProcSpec(
            name="m16_prop_close_capture", kind="py",
            module="scripts.platformkit.clv.prop_close_capture_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m16_prop_close_capture.txt",
                fresh_sec=150.0),   # 2x cadence (60s) + margin
            restart_policy=_FOREVER,
        ),
        # M17 -- the Kalshi LIQUID-SURFACE scanner (DISCOVERY-only). Every 1800s it scans
        # which Kalshi sports market types actually develop takeable two-way liquidity
        # during the live slate (most prop/total contracts stay listed-not-traded) and
        # keeps a per-type daily high-water mark. Independent branch (no depends_on).
        # Read-only; NO placement, NO $ field, NO flag flip, NO data/registry/ write.
        ProcSpec(
            name="m17_kalshi_scan", kind="py",
            module="scripts.platformkit.pm_trading.kalshi_scan_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m17_kalshi_scan.txt",
                fresh_sec=3900.0),   # 2x cadence (1800s) + margin
            restart_policy=_FOREVER,
        ),
        # M18 -- the PM (Kalshi/Polymarket) CLOSE-CAPTURE arm. Every 900s it resolves +
        # stamps CONFIRMED Kalshi settled closes onto settled paper_pm bets so our
        # best-realized channel becomes CLV-measurable (it carried clv_pct=None because
        # the resolver was never run). Non-fabricating (open/inferred markets never
        # stamped), idempotent. Independent branch (no depends_on). PAPER measurement;
        # NO placement, NO $ field, NO flag flip, NO data/registry/ write.
        ProcSpec(
            name="m18_pm_close_capture", kind="py",
            module="scripts.platformkit.pm_trading.pm_close_capture_runner",
            readiness=ReadinessSpec(
                kind=HEARTBEAT,
                heartbeat_path="data/cache/daemon_heartbeats/m18_pm_close_capture.txt",
                fresh_sec=1980.0),   # 2x cadence (900s) + margin
            restart_policy=_FOREVER,
        ),
        # M19 -- the CEILING asof-reclaim GATE daemon. Daily it re-gates every on-disk
        # leak-free *_diff_asof candidate (NBA ast/dreb/fg3m/stl/blk + MLB sp_ra_diff)
        # through the REAL single-corpus walk-forward DM gate vs leak-free Elo, appends
        # a scoreboard row, and logs each SHIP/REJECT to the reject_ledger. This is the
        # "getting better" search running on the flywheel with NO Claude in the loop:
        # the ingest daemons refresh the asof parquets, this re-gates them. CANDIDATE-
        # ONLY -- reads parquets additively, flips NO flag, touches NO predictor, makes
        # NO real-money action; a control-failing SHIP is downgraded to SHIP_REVIEW for
        # a human (never auto-shipped). REJECT is the expected, honest verdict. Readiness
        # NONE (a daily batch is ready when alive; a daily heartbeat window is useless).
        # Independent branch (no depends_on).
        ProcSpec(
            name="m19_asof_reclaim", kind="py",
            module="scripts.platformkit.ceiling.asof_reclaim_daemon",
            argv=["--interval", "86400"],
            restart_policy=_FOREVER,
        ),
        # M20 -- the IN-GAME CLV VERDICT daemon. Every ~10min it replays the captured
        # M11 model/market tick series (data/cache/ingame_grade/<sport>/) through
        # ingame_clv_grade.grade_sport and writes the honest in-play-close anticipation
        # verdict to data/frontend/ops/ingame_clv_verdict.json. This makes the in-game
        # gap-hunt CONTINUOUS + measurable on the flywheel (it was only ever a manual CLI
        # run). The in-game GAME engine is the project's validated freshness lever and the
        # one channel that MATCHES the in-play close with a faint positive CLV tilt; this
        # daemon keeps that verdict live. CLV is PROBABILITY space (calibration), NOT a $
        # edge; places NO bet, flips NO flag, no real-money action. Readiness NONE.
        ProcSpec(
            name="m20_ingame_clv_verdict", kind="py",
            module="scripts.platformkit.ingame.ingame_clv_verdict_daemon",
            argv=["--interval", "600"],
            restart_policy=_FOREVER,
        ),
        # M21 -- the IN-GAME BASE-OUT TRIGGER. The in-game GAME channel MATCHES the
        # in-play close; to cross from MATCH to BEAT we need a conditioning signal the
        # live model is NOT already using. The deep MLB base-out / RE24 / count / pitch
        # state only began flowing into the paired tick series after the ESPN<->Kalshi
        # id gap closed, so the corpus that could prove (or kill) that lever is only now
        # accumulating. Hourly this gate asks, leak-free, "does deep state anticipate the
        # in-play close BEYOND model_prob?" and writes INSUFFICIENT until the corpus is
        # large enough, then SHIP_REVIEW (two-corpus replicated lift + null collapse, for
        # a human) or REJECT (already priced -- the expected, honest verdict). It crosses
        # on its OWN -> no date-guessing. CANDIDATE-ONLY: reads the captured cache, flips
        # NO flag, touches NO predictor, places NO bet. Probability space, NOT a $ edge.
        # Readiness NONE (slow batch). Independent branch (no depends_on).
        ProcSpec(
            name="m21_ingame_baseout_gate", kind="py",
            module="scripts.platformkit.improve.ingame_baseout_gate_daemon",
            argv=["--interval", "3600"],
            restart_policy=_FOREVER,
        ),
        # M22 -- the BEST-PRICE SCAN daemon. The honest, model-free "use more books to
        # find gaps" lever: best_price.value_bets takes the BEST sportsbook price per
        # side across every wired book and asks whether it beats the SHARP fair
        # (Pinnacle / cross-book median). A manual run sees only one instant, but
        # cross-book mispricings are TRANSIENT (a book lags ~60-120s then corrects), so
        # the only way more books actually pays off is to POLL them continuously. Every
        # ~4min this writes the live scan to data/frontend/ops/best_price_scan.json and
        # appends a catch-log row ONLY when a real +CLV gap appears -- so the rare
        # transient gaps accumulate into evidence (data/frontend/ops/best_price_catches
        # .jsonl). The common, honest result is an empty scan on an efficient slate.
        # +CLV is PROBABILITY space, NOT a $ edge; reads aggregated public odds only,
        # flips NO flag, places NO bet, no real-money action. Readiness NONE. Independent
        # branch (no depends_on).
        ProcSpec(
            name="m22_best_price_scan", kind="py",
            module="scripts.platformkit.clv.best_price_scan_daemon",
            argv=["--interval", "240"],
            restart_policy=_FOREVER,
        ),
        # M23 -- the SCRAPED-LINE GAP daemon. Same model-free line-shop hunt as m22 but
        # sourced from OUR OWN scraped feed (data/cache/line_history/<sport>/<date>.jsonl
        # -- DraftKings + FanDuel + Pinnacle, ML/spread/total), NOT OddsAPI and NOT a
        # live re-fetch. Every ~4min it scans every sport for a best-book price that
        # beats the sharp fair, FRESHNESS-GATED so a stale quote can never manufacture a
        # fake edge (the classic stale-line mirage: a 30-min-old soft line showing +CLV
        # on both sides). Writes data/frontend/ops/scraped_line_gaps.json + appends a
        # catch-log row ONLY when a real, contemporaneous +CLV gap appears. The common,
        # honest result is an empty scan on an efficient slate. +CLV is PROBABILITY
        # space, NOT a $ edge; reads our own files only, flips NO flag, places NO bet,
        # no real-money action. Readiness NONE. Independent branch (no depends_on).
        ProcSpec(
            name="m23_scraped_line_gaps", kind="py",
            module="scripts.platformkit.clv.scraped_line_gaps_daemon",
            argv=["--interval", "240"],
            restart_policy=_FOREVER,
        ),
        # M24 -- the IN-GAME PLACEMENT FUNNEL diagnostic. The ledger shows the in-game
        # day-trader channel STARVED (1 paper_ingame bet vs 136 pregame) even though the
        # engine is fully wired -- but WHY is invisible: each live tick that fails to bet
        # returns a one-word reason and nothing aggregates them. Every ~5min this folds
        # the per-game decisions inplay_capture_loop.poll_once already returns into a
        # stage funnel (markets->live_state->model_prob->home_leg->priced->tier_floor->
        # bet) + reason histogram and writes data/frontend/ops/ingame_placement_funnel
        # .json, so during a live slate we SEE exactly which stage drops the volume and
        # tune the real cause instead of guessing. Diagnostic only: it does its own read-
        # only poll, places NO bet, flips NO flag, no $ field, no edge. Readiness NONE.
        ProcSpec(
            name="m24_ingame_placement_funnel", kind="py",
            module="scripts.platformkit.ingame.ingame_placement_funnel",
            argv=["--interval", "300"],
            restart_policy=_FOREVER,
        ),
        # M25 -- the IN-GAME OUTCOME-GATED VERDICT. The in-game CLV verdict (m20) can only
        # compare model_prob vs the CONTEMPORANEOUS venue price; it cannot say whether a
        # per-segment lean is the model being wrong (lag) or right (the thin venue quote
        # lagging). This resolves the held-out OUTCOME directly from the Kalshi ticker
        # (ticker encodes date + away+home abbrs -> join to the local realized-box parquet)
        # and every ~15min computes, per inning segment, the Brier of the live model vs the
        # OUTCOME against the Brier of the venue in-play price, with a game-clustered
        # bootstrap CI. Writes data/frontend/ops/ingame_outcome_verdict.json. A
        # BETTER_THAN_VENUE segment means better-calibrated-to-truth than the (thin, laggy)
        # Kalshi in-play quote -- NOT an efficient-close beat, NOT a $ edge. Diagnostic
        # only: reads local files + a labeled corpus, places NO bet, flips NO flag, no $
        # field. Running it continuously accrues games across slates so a single-window
        # lift can replicate (or wash out) honestly. Readiness NONE. Independent branch.
        ProcSpec(
            name="m25_ingame_outcome_verdict", kind="py",
            module="scripts.platformkit.ingame.ingame_outcome_verdict",
            argv=["--interval", "900"],
            restart_policy=_FOREVER,
        ),
        # M26 -- the IN-GAME SEGMENT-TRUST gate (the self-improving-execution loop). m25's
        # full-corpus verdict can be a single-fold artifact (the I5-I9 lift did NOT replicate
        # across an even/odd-day split). This every ~30min splits the labeled corpus into >=2
        # INDEPENDENT corpora, runs the outcome verdict on each, and marks a segment TRUSTED
        # (BETTER_THAN_VENUE in EVERY non-insufficient corpus) or ADVERSE (WORSE in every)
        # else NEUTRAL, writing data/frontend/ops/ingame_segment_trust.json. The in-game
        # capture loop reads it: an ADVERSE segment reverts to the STRICT pre-registered floor
        # (suppress its marginal relaxed bets), everything else keeps today's relaxed floor.
        # So execution improves on its own as games accrue, but changes ONLY on cross-corpus
        # PROOF -- thin/unreplicated data changes nothing (do-no-harm) and it is reversible
        # (CV_INGAME_SEGMENT_TRUST=0). Diagnostic+gate: flips NO flag, places NO bet, no $
        # field, edge_claimed=False; venue=thin Kalshi in-play (NOT an efficient close).
        # Readiness NONE. Independent branch (no depends_on).
        ProcSpec(
            name="m26_ingame_segment_trust", kind="py",
            module="scripts.platformkit.ingame.ingame_segment_trust",
            argv=["--interval", "1800"],
            restart_policy=_FOREVER,
        ),
        # M27 -- the IN-GAME PAPER SETTLE arm (the MISSING settle counterpart to the in-game
        # PLACE arm). inplay_daytrader placed in-game paper bets (channel=paper_ingame) but
        # NOTHING ever settled them: 82 placed, 0 ever graded -> no outcome, no CLV, no
        # bankroll impact. Root = the same id gap: in-game rows are keyed by the KALSHI
        # TICKER, so an ESPN-id settler never matched. Every ~15min this loads OPEN
        # paper_ingame rows, resolves each MLB bet's final score DIRECTLY from the ticker
        # (ingame_outcome_label.final_score -> local realized-box parquet) and calls
        # paper_ingame.grade_live so the row settles with a real outcome + unit_result.
        # Idempotent (already-settled edge_keys skipped); a game not yet final stays OPEN
        # (never force-settled); soccer stays open pending a soccer resolver. UNITS /
        # probability only, executed=False, flips NO flag, no $ field. Readiness NONE.
        # Independent branch (no depends_on) so a dead settle arm is ONE red status entry.
        ProcSpec(
            name="m27_ingame_paper_settle", kind="py",
            module="scripts.platformkit.ingame.ingame_paper_settle",
            argv=["--interval", "900"],
            restart_policy=_FOREVER,
        ),
        # M29 -- the OUTPUT-FRESHNESS sentinel (see the module-level comment above
        # _OUTPUT_FRESHNESS_HB). Every ~300s checks each of the 9 readiness=NONE
        # daemons' (m19-m27) declared output artifact against its expected cadence
        # and writes GREEN/RED per daemon. Read-only, NO restart authority -- it only
        # makes a wedged (alive-but-silent) tick VISIBLE; the supervisor +
        # heartbeat_reaper still own restarts. Independent branch (no depends_on) so
        # a dead sentinel tick is itself ONE red status entry. m29 beats at boot +
        # every tick; fresh_sec=660 (>2x the 300s cadence + margin) keeps a healthy
        # runner fresh while a genuinely dead/hung tick ages out. NO $ field, NO flag
        # flip, NO data/registry/ write, NO real-money action.
        ProcSpec(
            name="m29_output_freshness", kind="py",
            module="scripts.platformkit.ops_sentinel.output_freshness_runner",
            argv=["--interval", "300"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_OUTPUT_FRESHNESS_HB, fresh_sec=660.0),
            restart_policy=_FOREVER,
        ),
        ProcSpec(
            name="m30_feed_health", kind="py",
            module="scripts.platformkit.odds_provider.feed_health_runner",
            argv=["--interval", "600"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_FEED_HEALTH_HB, fresh_sec=1320.0),
            restart_policy=_FOREVER,
        ),
        # M31 -- MLB pregame-context snapshotter: probable pitchers + weather + HP
        # umpire (statsapi, today+tomorrow) and the ESPN injury report + deterministic
        # edge-fact extraction, every 6h. Snapshot-append parquets with captured_at
        # vintages (as-of joins only). KNOWLEDGE/SUBSTRATE, not a model feed; no $
        # field, no flag flip, no data/registry/ write. fresh_sec = 2x the 21600s
        # cadence + margin so a healthy tick stays fresh while a hung one ages out.
        ProcSpec(
            name="m31_mlb_context", kind="py",
            module="scripts.platformkit.mlb_context_runner",
            argv=["--interval", "21600"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_MLB_CONTEXT_HB, fresh_sec=45000.0),
            restart_policy=_FOREVER,
        ),
        # M32 -- MLB context autogate: nightly re-runs the SP-offset gate
        # (domains.mlb.sp_adjust_current) and the weather-totals gate
        # (domains.mlb.weather_totals_gate) end-to-end so their verdicts track
        # the growing M31 context corpus, then composes ONE ops summary doc
        # (data/frontend/ops/mlb_context_autogate.json) listing every candidate
        # + its verdict + a ship_review roster. VERDICTS ONLY -- this daemon
        # never wires, ships, or flips a flag for any candidate; SHIP_REVIEW/
        # SHIP-READY verdicts surface for a HUMAN to decide. No $ field, no
        # flag flip, no data/registry/ write, no real-money action. fresh_sec
        # = 2x the 86400s cadence + margin so a healthy tick stays fresh while
        # a hung one ages out.
        ProcSpec(
            name="m32_mlb_context_autogate", kind="py",
            module="scripts.platformkit.mlb_context_autogate_runner",
            argv=["--interval", "86400"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_MLB_CONTEXT_AUTOGATE_HB, fresh_sec=190000.0),
            restart_policy=_FOREVER,
        ),
        # M33 -- HTTP-readiness wedge reaper (see _HTTP_WEDGE_REAPER_HB comment
        # above). 30s cadence -- a wedge is a live-incident detector, not a slow
        # batch sentinel; fresh_sec=90 (3x cadence + margin) keeps a healthy
        # runner fresh while a genuinely dead/hung tick ages out quickly (this
        # sentinel itself must never silently wedge). Independent branch (no
        # depends_on) so a dead reaper tick is itself ONE red status entry.
        ProcSpec(
            name="m33_http_wedge_reaper", kind="py",
            module="scripts.platformkit.autonomy.http_wedge_reaper_runner",
            argv=["--interval", "30"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_HTTP_WEDGE_REAPER_HB, fresh_sec=90.0),
            restart_policy=_FOREVER,
        ),
        # M34 -- per-daemon freshness SLA scoreboard (see _FRESHNESS_SLA_HB
        # comment above). 300s cadence; fresh_sec=660 (2.2x cadence + margin,
        # matching M29's own margin convention). Independent branch (no
        # depends_on) so a dead scoreboard tick is itself ONE red status entry.
        ProcSpec(
            name="m34_freshness_sla", kind="py",
            module="scripts.platformkit.autonomy.freshness_sla_runner",
            argv=["--interval", "300"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_FRESHNESS_SLA_HB, fresh_sec=660.0),
            restart_policy=_FOREVER,
        ),
        # M35 -- LANE C cross-sport (tennis + soccer_intl/WC) in-play tail-band
        # scan + pre-registered forward gate + tick-latency scoreboard. Every 6h
        # re-runs ingame_tail_scan_multi (per-sport price-band calibration scan,
        # writes data/domains/<sport>/ingame_tail_scan.json), ingame_tail_gate_
        # multi (pre-registered H1/H2 forward-only gate, writes data/domains/
        # <sport>/ingame_tail_verdict.json), and inplay_tick_latency (cadence
        # scoreboard, writes data/frontend/ops/inplay_tick_latency.json), then
        # composes ONE ops summary (data/frontend/ops/ingame_tail_multi.json).
        # VERDICTS ONLY -- never wires, ships, or flips a flag; SHIP_REVIEW
        # surfaces for a HUMAN to decide. No $ field, no flag flip, no
        # data/registry/ write, no real-money action. NOT YET RUNNING --
        # registered here but requires a supervisor restart to take effect
        # (restart pending). fresh_sec = 2x the 21600s cadence + margin.
        ProcSpec(
            name="m35_ingame_tail_multi", kind="py",
            module="scripts.platformkit.ingame.ingame_tail_multi_runner",
            argv=["--interval", "21600"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INGAME_TAIL_MULTI_HB, fresh_sec=45000.0),
            restart_policy=_FOREVER,
        ),
        # M36 -- LANE 3 multi-sport in-game grading: the soccer_intl/tennis/wnba
        # counterpart to the MLB-only m25 (ingame_outcome_verdict) + m26
        # (ingame_segment_trust) pair. Every 900s (m25's cadence) re-runs
        # ingame_outcome_verdict_multi.build_verdict_all() (per-segment Brier of
        # the live model vs OUTCOME vs the venue in-play price, per capturing
        # sport, writes data/frontend/ops/ingame_outcome_verdict_multi.json) and
        # ingame_segment_trust_multi.build_trust_all() (cross-corpus TRUSTED/
        # ADVERSE/NEUTRAL replication gate per sport, writes data/frontend/ops/
        # ingame_segment_trust_multi.json), then composes one small tick summary.
        # MEASUREMENT ONLY -- wires no floor/execution routing anywhere; the
        # MLB-only m26 path remains the sole trust gate that affects execution,
        # pending a human review of extending routing to these sports. No $
        # field, no flag flip, no data/registry/ write, no real-money action.
        # INSUFFICIENT_N/NEUTRAL is the expected, honest readout for tennis/wnba
        # on day 1 of capture. NOT YET RUNNING -- registered here but requires a
        # supervisor restart to take effect (restart already pending; rides the
        # same restart as m33-m35 + the tennis/wnba capture sports). Readiness
        # NONE would also be defensible (mirrors m25/m26), but a heartbeat is
        # used here (mirrors m35) so the freshness sentinels can see it too.
        # fresh_sec = 2x the 900s cadence + margin. Independent branch (no
        # depends_on) so a dead grading tick is itself ONE red status entry.
        ProcSpec(
            name="m36_ingame_grading_multi", kind="py",
            module="scripts.platformkit.ingame.ingame_grading_multi_runner",
            argv=["--interval", "900"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INGAME_GRADING_MULTI_HB, fresh_sec=2000.0),
            restart_policy=_FOREVER,
        ),
        # M37 -- LANE 2 combined wave-10 enrichment tick (fotmob + gumbo +
        # book-depth). See _INGAME_ENRICHMENT_HB comment above for the full
        # spec. Independent branch (no depends_on) so a dead tick is itself
        # ONE red status entry. NOT YET RUNNING -- restart pending.
        ProcSpec(
            name="m37_ingame_enrichment", kind="py",
            module="scripts.platformkit.ingame.ingame_enrichment_runner",
            argv=["--interval", "30"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INGAME_ENRICHMENT_HB, fresh_sec=90.0),
            restart_policy=_FOREVER,
        ),
        # M38 -- the AUTOLOOP daemon. See _AUTOLOOP_HB comment above for the
        # full spec (AUTOLOOP_SPEC_2026-07-06.md, R-B/R-C/R-D/R-E rulings).
        # Independent branch (no depends_on) so a dead tick is itself ONE red
        # status entry. NOT YET RUNNING -- registered here but requires a
        # supervisor restart to take effect (R-C: this wave does NOT bounce
        # the supervisor).
        ProcSpec(
            name="m38_autoloop", kind="py",
            module="scripts.platformkit.autoloop.autoloop_runner",
            argv=["--interval", "86400"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_AUTOLOOP_HB, fresh_sec=190000.0),
            restart_policy=_FOREVER,
        ),
        # M39 -- NBA/WNBA injury-facts snapshotter (see _INJURY_FACTS_HB comment
        # above). Every 6h; the NBA sibling of m31's MLB injury snapshot. Independent
        # branch (no depends_on) so a dead tick is itself ONE red status entry. NOT
        # YET RUNNING -- registered here but requires a supervisor restart to take
        # effect. fresh_sec = 2x the 21600s cadence + margin (mirrors m31).
        ProcSpec(
            name="m39_injury_facts_nba", kind="py",
            module="scripts.platformkit.edge_engine.injury_daemon",
            argv=["--interval", "21600"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_INJURY_FACTS_HB, fresh_sec=45000.0),
            restart_policy=_FOREVER,
        ),
        # M40 -- the WEDGE-RESTARTER detector (see _WEDGE_RESTARTER_HB comment
        # above). Request-only: turns a persistent output-freshness RED into a
        # rate-limited RESTART_REQUEST the supervisor honors. Independent branch
        # (no depends_on) so a dead tick is itself ONE red status entry. NOT YET
        # RUNNING -- registered here but requires a supervisor restart to take
        # effect. fresh_sec=660 (>2x the 300s cadence + margin, mirrors m29).
        ProcSpec(
            name="m40_wedge_restarter", kind="py",
            module="scripts.platformkit.ops_sentinel.wedge_restarter",
            argv=["--interval", "300"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_WEDGE_RESTARTER_HB, fresh_sec=660.0),
            restart_policy=_FOREVER,
        ),
        # M41 -- Action Network public-splits daily capture (see _PUBLIC_SPLITS_HB
        # comment above). Independent branch (no depends_on) so a dead tick is
        # itself ONE red status entry. NOT YET RUNNING -- registered here but
        # requires a supervisor restart to take effect (this lane does NOT
        # bounce the supervisor).
        ProcSpec(
            name="m41_public_splits", kind="py",
            module="scripts.platformkit.data_frontier.an_public_splits",
            argv=["--interval", "86400"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_PUBLIC_SPLITS_HB, fresh_sec=190000.0),
            restart_policy=_FOREVER,
        ),
        # M42 -- the execution-quality tick (see _EXEC_QUALITY_HB comment above).
        # Independent branch (no depends_on) so a dead tick is itself ONE red
        # status entry. NOT YET RUNNING -- registered here but requires a
        # supervisor restart to take effect.
        ProcSpec(
            name="m42_exec_quality", kind="py",
            module="scripts.platformkit.execution.exec_quality_daemon",
            argv=["--interval", "120"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_EXEC_QUALITY_HB, fresh_sec=300.0),
            restart_policy=_FOREVER,
        ),
        # M43 -- the settlement-sweep tick (see _SETTLE_SWEEP_HB comment above).
        # Independent branch (no depends_on) so a dead tick is itself ONE red
        # status entry. NOT YET RUNNING -- registered here but requires a
        # supervisor restart to take effect.
        ProcSpec(
            name="m43_settle_sweep", kind="py",
            module="scripts.platformkit.paper.settle_sweep_daemon",
            argv=["--interval", "3600"],
            readiness=ReadinessSpec(
                kind=HEARTBEAT, heartbeat_path=_SETTLE_SWEEP_HB, fresh_sec=9000.0),
            restart_policy=_FOREVER,
        ),
    ]


__all__ = ["base_specs"]

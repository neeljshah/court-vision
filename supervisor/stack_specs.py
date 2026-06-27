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
# M14 -- the brain-rebuild cadence (brain_rebuild_runner loop-wrapper): rebuilds the
# organized, person-free Obsidian brain (vault/_Organized) from the deep
# _vault_legacy_archive source on a slow (default 6h) cadence so the knowledge graph
# stays FULLY REACHABLE + fresh WITHOUT a self-installing OS scheduler. It beats this
# heartbeat at boot + every boundary; absent/stale -> NOT-READY (never a stale-green).
_BRAIN_REBUILD_HB = "data/cache/daemon_heartbeats/m14_brain_rebuild.txt"

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
    ]


__all__ = ["base_specs"]

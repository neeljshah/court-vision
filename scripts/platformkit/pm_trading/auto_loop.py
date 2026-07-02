"""scripts.platformkit.pm_trading.auto_loop -- the always-on self-improving paper loop.

One honest cycle = (1) PAPER-trade today's real games -> CLV ledger (executed=False),
(2) GRADE finished games (win/loss + CLV vs close), (3) SELF-IMPROVE: recalibrate on
the accumulated REAL outcomes, gated by the eval-gate (only ever improve or hold) --
this IS the live self-improvement ratchet (scripts.platformkit.self_improve.improve_all),
(4) LINE TICK: capture a line/close snapshot via line_snapshot_daemon.poll_once for
each active sport, (5) SCOREBOARD: write grade_summary.json atomically so the UI and
the real-money gate always have a fresh view.

Steps (4) and (5) are independently guarded: one failing step never blocks the others.

This is measurement, not money: PAPER only, no network orders, no $-edge claimed. The
loop gets smarter strictly as real games settle. Run one cycle or --forever.

Usage:
  python -m scripts.platformkit.pm_trading.auto_loop                 # one cycle
  python -m scripts.platformkit.pm_trading.auto_loop --forever --interval 1200

INVARIANTS: build only under scripts/platformkit/; paper-only; ASCII; no edge claims.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

# Make the loop cwd-independent: add the repo root to sys.path so `python -m ...`
# works even if launched from a different directory (the bash cwd is flaky).
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.pm_trading.run_paper_today import run_paper_cycle
from scripts.platformkit.grade_paper import grade_open_bets, grade_summary
from scripts.platformkit.self_improve import improve_all

import logging

logger = logging.getLogger("auto_loop")

# Active sports for the line/close capture tick (matches odds_provider defaults).
_LINE_SPORTS: tuple = ("nba", "mlb", "soccer", "tennis")

# PREGAME prop discipline (REFOCUS 2026-06-24: fewer/better, in-game-first). The pregame
# prop channel is the realized BLEEDER on an efficient market (model-view flood vs vig), so
# it is now the LEAST-favored channel: tier-A only, calibration-gated (stake only families
# we have PROVEN we calibrate -- replicated SHIP), and a small cap. The EDGE focus is the
# in-game channel below. EV is MODEL_VIEW, never a proven $ edge; CLV is the judge.
# STARVE 2026-06-28: settled record shows the prop model OVERCONFIDENT (mean model_prob ~0.61
# realizes ~0.50) and props are the bulk of the realized losses -> cut the flood 8->2 to stop
# placing the systematically-overconfident bets. Reversible: CV_PROP_MAX=8 restores. This
# REDUCES losses; it does NOT create profit -- no $ edge is claimed. UNITS only.
_PROP_MAX_PER_SPORT: int = max(0, int(os.environ.get("CV_PROP_MAX", "2") or 2))
_PROP_MIN_TIER: str = "A"
# World Cup pregame props: settleable + tier-A best bets. NOT calibration-gated -- soccer is
# UNMEASURED (no leak-free verdict yet), not rejected. PRECAUTION 2026-06-28: this is the LAST
# ungated prop channel; rather than flood it while its CLV is unproven, starve it to a token
# cap (2) so the corpus still fills (we can measure later) without paying the efficient-market
# flood. Reversible: CV_WC_PROP_MAX=8 restores the prior cap. UNITS only, no $ edge claim.
_WC_PROP_MAX_PER_SPORT: int = max(0, int(os.environ.get("CV_WC_PROP_MAX", "2") or 2))
# in-game (the believed/validated freshness edge) stays at the A/B floor so it fires broadly.
_INGAME_MIN_TIER: str = "B"


def _place_props() -> Dict[str, Any]:
    """Paper-place today's PREGAME props as BEST BETS (UNITS, tightly capped). MLB is
    calibration-gated (only replicated-SHIP families) so the efficient-market flood can no
    longer bleed; World Cup (soccer_intl) is settleable + tier-A but NOT calibration-gated
    (unmeasured, not rejected). Guarded; idempotent per day."""
    out: Dict[str, Any] = {"status": "ok", "n_placed": 0, "by_sport": {}}
    try:
        from scripts.platformkit.bestbets.props_paper_placer import run as _place
        mlb = _place(sports=("mlb",), max_per_sport=_PROP_MAX_PER_SPORT,
                     min_tier=_PROP_MIN_TIER, calibration_only=True)
        wc = _place(sports=("soccer_intl",), max_per_sport=_WC_PROP_MAX_PER_SPORT,
                    min_tier=_PROP_MIN_TIER, calibration_only=False)
        for r in (mlb, wc):
            out["n_placed"] += int(r.get("n_placed", 0) or 0)
            out["by_sport"].update(r.get("by_sport", {}))
        return out
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


# Per-tick cap on NEW Kalshi/Polymarket GAME (moneyline) placements per sport (flood-bound;
# every placement already clears the A/B tier + plausibility guard). 25 covers a full slate.
# Kalshi PM is a realized-POSITIVE channel (small n) -> kept at the A/B floor (own constant,
# NOT coupled to the tightened pregame-prop tier) so we keep "pushing" it per the directive.
_PM_GAME_MAX_PER_SPORT: int = 25
_PM_MIN_TIER: str = "B"


def _place_pm_games() -> Dict[str, Any]:
    """Paper-place live Kalshi/Polymarket GAME moneyline (is_pm=True, venue-tagged): devig
    the exchange price, bet the +EV side vs our calibrated pregame prob. The real PM paper
    system. Guarded; min_tier='B'; idempotent per game/side; UNITS only; real-money DENY."""
    try:
        from scripts.platformkit.pm_trading.pm_game_placer import run as _place
        return _place(max_per_sport=_PM_GAME_MAX_PER_SPORT, min_tier=_PM_MIN_TIER)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


# Frontend per-sport board snapshots the UI reads (data/frontend/snapshots/<sport>.json,
# served by /api/v1/bestbets/<sport>). Nothing else regenerates them, so without this step
# they go stale (the prop board build is heavy ~2min/sport). Live sports only -- the FE shows
# these. Staleness-gated so rapid restarts don't hammer the build; a sport already fresh is
# skipped. UNITS only / calibration not edge -- this just refreshes what the loop already knows.
_SNAPSHOT_SPORTS: tuple = ("mlb", "soccer_intl")
_SNAPSHOT_MAX_AGE_SEC: float = 900.0


def _write_frontend_snapshots() -> Dict[str, Any]:
    """Rebuild each live sport's frontend board snapshot IFF missing or stale (> max age).

    Guarded + lazy import: a snapshot-build failure (slow feed, etc.) never sinks the loop.
    Returns a per-sport map of 'written' / 'fresh' / 'error: <type>'."""
    try:
        from scripts.platformkit.frontend import snapshot_writer as _sw
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": "%s: %s" % (type(exc).__name__, exc)}
    now = time.time()
    out: Dict[str, Any] = {}
    for sport in _SNAPSHOT_SPORTS:
        path = _sw.DEFAULT_OUT_DIR / ("%s.json" % sport)
        try:
            fresh = path.exists() and (now - path.stat().st_mtime) < _SNAPSHOT_MAX_AGE_SEC
            if fresh:
                out[sport] = "fresh"
                continue
            _sw.build_snapshot(sport)
            out[sport] = "written"
        except Exception as exc:  # noqa: BLE001 -- one sport must not stop the rest
            out[sport] = "error: %s" % type(exc).__name__
    return out


# Per-tick cap on NEW in-game prop placements per live game (flood-bound; each already
# clears the tier floor + freshness band). A position re-opens only on a new slate day.
# REFOCUS 2026-06-24: in-game is the FOCUS channel (the validated freshness lever) -> raised
# from 12 so a live game's edges are captured broadly, while pregame props are starved above.
_INGAME_PROP_MAX_PER_GAME: int = 20


def _place_ingame_props() -> Dict[str, Any]:
    """Paper-place IN-GAME player props: re-price each live prop on realized state +
    freshness, compare to the book's LIVE two-way line, record the +edge side (tier-gated,
    channel=paper_ingame_prop). Guarded + lazy import; settles via the SAME prop settler.
    Ticks mlb + soccer_intl (World Cup); each is an honest no-op unless that sport has a
    live game AND a live two-way prop source. UNITS only, no $ edge."""
    out: Dict[str, Any] = {"status": "ok", "placed": 0, "by_sport": {}}
    try:
        from scripts.platformkit.ingame.ingame_prop_trader import run as _run
        from scripts.platformkit.improve.ingame_prop_gate import gate_if_enabled
        from scripts.platformkit.improve.ingame_prop_clv_guard import clv_guard
        # CLV guard (default ON): the in-game prop channel is MEASURED CLV-adverse
        # (mean -31%, edge anti-correlated; see ingame_prop_clv_guard) -> suppress-only,
        # composes over the optional calib gate. CV_INGAME_PROP_CLV_GUARD=0 restores
        # the prior broad-capture behavior. Stops a measured bleed; claims no edge.
        gate = clv_guard(gate_if_enabled())
        for sp in ("mlb", "soccer_intl"):
            r = _run(sp, max_per_game=_INGAME_PROP_MAX_PER_GAME,
                     min_tier=_INGAME_MIN_TIER, gate=gate)
            out["by_sport"][sp] = r
            out["placed"] += int(r.get("placed", 0) or 0)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _capture_prop_closes() -> Dict[str, Any]:
    """Snapshot the LIVE two-way price of every open in-game prop so its CLOSE (the
    last quote before the market suspends) is captured -- this is what finally makes
    in-game props CLV-measurable (the prop settler reads prop_close_store at settle).
    Guarded + lazy import; honest no-op when nothing is live. UNITS/measurement only."""
    try:
        from scripts.platformkit.clv.prop_close_capture import capture_all as _cap
        return _cap(sports=("mlb", "soccer_intl"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _settle_props() -> Dict[str, Any]:
    """Settle OPEN props on their real post-game stat outcome (UNITS). Guarded."""
    try:
        from scripts.platformkit.bestbets.prop_settler import settle_open_props as _settle
        return _settle()
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_improve() -> Dict[str, Any]:
    """Run the leak-free PROP CALIBRATION ratchet on the accumulated settled props -- the
    props 'gets better' loop, the prop twin of the game self-improve ratchet (step 3).

    SHIP only when the eval-gate passes, the planted-null rejects, AND the walk-forward
    isotonic recal beats held-out Brier; else HOLD/REJECT; cold start = INSUFFICIENT_DATA.
    PROPOSE/RECORD ONLY: appends to prop_improve_ledger.jsonl, NEVER arms serving / flips
    a flag / writes data/registry/. Guarded so a ratchet error never sinks the loop."""
    try:
        from scripts.platformkit.improve.prop_calibration_ratchet import improve_all as _pi
        out = _pi()
        try:  # in-game prop ratchet (frac-bucketed) -> refreshes the calib-gate read-surface
            from scripts.platformkit.improve.ingame_prop_ratchet import improve_all_ingame
            out["ingame"] = improve_all_ingame().get("meta", {}).get("groups")
        except Exception as exc:  # noqa: BLE001 -- in-game arm must not sink the pregame arm
            out["ingame_error"] = "%s: %s" % (type(exc).__name__, exc)
        return out
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_history_improve() -> Dict[str, Any]:
    """Run ONE historical prop-calibration fold from the on-disk gamelogs (leak-free) so
    props get better from OLD games -- no live games needed. A FRESH random player sample
    each cycle (rotating seed) -> accumulating independent folds = honest replication
    (single-fold lifts are artifacts). PROPOSE/RECORD only (own corpus file + tagged verdict
    in prop_improve_ledger; never the units ledger / a flag / data/registry/). Guarded."""
    try:
        from scripts.platformkit.improve.prop_history_backtest import run_history_fold
        return run_history_fold(seed=int(time.time()) % 100000)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_history_multisport() -> Dict[str, Any]:
    """Run ONE historical prop-calibration fold for a NON-NBA sport (MLB / tennis / soccer)
    from the on-disk per-player gamelogs (leak-free), rotating the sport each cycle so all
    three accumulate independent folds overnight. Same SHIP/HOLD/REJECT/INSUFFICIENT ratchet
    + planted-null do-no-harm as NBA. Each sport writes its OWN corpus file; verdict tagged
    source=history + sport in prop_improve_ledger (never the units ledger / a flag /
    data/registry/). Honest INSUFFICIENT_DATA where the data is thin. Guarded."""
    try:
        from scripts.platformkit.improve.prop_history_multisport import (
            run_history_fold as _mf, sport_stat_pairs)
        pairs = sport_stat_pairs()
        sport, stat = pairs[(int(time.time()) // 60) % len(pairs)]  # rotate (sport,stat)
        return _mf(sport, seed=int(time.time()) % 100000, only_stat=stat)
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def _prop_history_meta() -> Dict[str, Any]:
    """READ-ONLY meta-aggregator: re-read the accumulated source=history folds and write the
    replicated-verdict-per-(sport,stat) read surface (prop_history_meta.json). A SHIP only
    counts when it replicates across >= 2 folds (single-fold lift = artifact); any reject or
    planted-null leak blocks the group. Never recalibrates / serves / flips a flag. Guarded."""
    try:
        from scripts.platformkit.improve.prop_history_meta import run as _meta_run
        rep = _meta_run(write=True)
        return {"status": "ok", "n_history_folds": rep.get("n_history_folds"),
                "groups": [{"sport": g["sport"], "stat": g["stat"],
                            "replicated_verdict": g["replicated_verdict"]}
                           for g in rep.get("groups", [])]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}

# Liveness heartbeat (RB-P0-03): this loop is supervised as m1_paper. It MUST beat
# its declared heartbeat every cycle so the supervisor's HEARTBEAT readiness reads
# this service not-ready when the heartbeat is absent (fresh boot) OR stale (a hung
# cycle) -- never a stale-green NONE that reads READY forever. Mirrors the
# inplay_runner / selfimprove_runner / m7 pattern (ops.liveness.heartbeat).
HEARTBEAT_COMPONENT = "m1_paper"


def _beat(now_epoch=None) -> None:
    """Write the m1_paper liveness heartbeat. Never raises (observability only)."""
    try:
        from ops.liveness import heartbeat
        heartbeat(HEARTBEAT_COMPONENT, _now=now_epoch)
    except Exception as exc:  # noqa: BLE001 -- a heartbeat write must never sink the loop
        logger.debug("auto_loop heartbeat skipped: %s", exc)


def _line_tick(sports: tuple = _LINE_SPORTS) -> Dict[str, Any]:
    """Capture one line/close snapshot tick for each active sport.

    Calls line_snapshot_daemon.poll_once per sport; isolated per-sport so a feed
    error on one sport never blocks the others. Import is lazy+guarded so a missing
    dependency never crashes the loop.
    """
    result: Dict[str, Any] = {"status": "ok", "sports": []}
    try:
        from scripts.platformkit.odds_provider.line_snapshot_daemon import poll_once
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "reason": "%s: %s" % (type(exc).__name__, exc)}
    for sport in sports:
        try:
            rep = poll_once(sport)
        except Exception as exc:  # noqa: BLE001 -- per-sport isolation
            rep = {"sport": sport, "status": "error: %s" % type(exc).__name__}
        result["sports"].append(rep)
    return result


def _write_scoreboard() -> Dict[str, Any]:
    """Write grade_summary.json via scoreboard.write_scoreboard. Guarded."""
    try:
        from scripts.platformkit.pm_trading.scoreboard import write_scoreboard
        out_path = write_scoreboard()
        return {"status": "ok", "path": str(out_path)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}


def run_once(line_sports: tuple = _LINE_SPORTS) -> Dict[str, Any]:
    """Run one full cycle. Each step is guarded so one failure never sinks the loop."""
    out: Dict[str, Any] = {}
    for name, fn in (("paper", run_paper_cycle),
                     ("place_props", _place_props),
                     ("place_pm_games", _place_pm_games),
                     ("place_ingame_props", _place_ingame_props),
                     ("capture_prop_closes", _capture_prop_closes),
                     ("snapshots", _write_frontend_snapshots),
                     ("grade", grade_open_bets),
                     ("settle_props", _settle_props),
                     ("improve", improve_all),
                     ("prop_improve", _prop_improve),
                     ("prop_history_improve", _prop_history_improve),
                     ("prop_history_multisport", _prop_history_multisport),
                     ("prop_history_meta", _prop_history_meta)):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 -- a step must never crash the loop
            out[name] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
            traceback.print_exc()
    try:
        out["summary"] = grade_summary()
    except Exception as exc:  # noqa: BLE001
        out["summary"] = {"status": "error", "reason": str(exc)}
    # Guarded step (4): line/close capture tick
    try:
        out["line_tick"] = _line_tick(line_sports)
    except Exception as exc:  # noqa: BLE001 -- must not stop the loop
        out["line_tick"] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
    # Guarded step (5): scoreboard write
    try:
        out["scoreboard"] = _write_scoreboard()
    except Exception as exc:  # noqa: BLE001 -- must not stop the loop
        out["scoreboard"] = {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc)}
    # NOTE: there is NO separate "ratchet" step. The live self-improvement ratchet
    # IS step (3) improve_all above (out["improve"]) -- the eval-gate-gated
    # recalibration that only ever improves or holds. An earlier _ratchet_tick that
    # imported a never-built ratchet_candidate.pending_candidate provider was a
    # permanent no-op and has been removed so the cycle's reported steps match what
    # actually runs (honesty: don't advertise a step that never executes).
    return out


def _print_cycle(out: Dict[str, Any]) -> None:
    s = out.get("summary") or {}
    paper = out.get("paper") or {}
    lt = out.get("line_tick") or {}
    sb = out.get("scoreboard") or {}
    pp = out.get("place_props") or {}
    sp = out.get("settle_props") or {}
    n = s.get("n", 0)
    print("[auto_loop] props | placed=%s settled=%s pending=%s"
          % (pp.get("n_placed", pp.get("status", "?")),
             sp.get("n_settled_now", sp.get("status", "?")),
             sp.get("n_pending", "?")))
    # improve=<verdicts> IS the live self-improvement ratchet (step 3, improve_all);
    # there is no separate ratchet field because no separate ratchet step runs.
    print("[auto_loop] cycle done | "
          "paper_recorded=%s | "
          "graded_n=%s hit_rate=%s mean_clv=%s | "
          "improve=%s | prop_improve=%s | line_tick=%s | scoreboard=%s"
          % (paper.get("recorded", paper.get("status", "?")),
             n, s.get("hit_rate"), s.get("mean_clv_pct"),
             _improve_brief(out.get("improve")),
             _improve_brief(out.get("prop_improve")),
             lt.get("status", "?"), sb.get("status", "?")))
    ph = out.get("prop_history_improve") or {}
    print("[auto_loop] prop_history (from old games) | verdict=%s n_rows=%s delta_brier=%s"
          % (ph.get("verdict", ph.get("status", "?")), ph.get("n_rows", "?"),
             ph.get("delta_brier", "?")))
    pm = out.get("prop_history_multisport") or {}
    print("[auto_loop] prop_history multisport | sport=%s verdict=%s n_rows=%s delta_brier=%s"
          % (pm.get("sport", "?"), pm.get("verdict", pm.get("status", "?")),
             pm.get("n_rows", "?"), pm.get("delta_brier", "?")))
    mta = out.get("prop_history_meta") or {}
    reps = ", ".join("%s/%s=%s" % (g["sport"], g["stat"], g["replicated_verdict"])
                     for g in (mta.get("groups") or [])) or "?"
    print("[auto_loop] prop_history meta (replicated) | folds=%s | %s"
          % (mta.get("n_history_folds", "?"), reps))
    print("HONEST: paper only (executed=False); calibration/CLV is the yardstick, NOT a $ edge.")


def _improve_brief(imp: Any) -> str:
    if not isinstance(imp, dict):
        return str(imp)
    verds = imp.get("verdicts") or imp.get("by_sport") or imp
    if isinstance(verds, dict):
        return ",".join(f"{k}={v.get('verdict', v) if isinstance(v, dict) else v}"
                        for k, v in verds.items())
    return str(verds)


def main(argv=None, *, run_fn=None, sleep=None, clock=None,
         max_cycles=None) -> int:
    """Run the paper loop, beating the m1_paper heartbeat every cycle.

    Defaults match the CLI (real run_once + time.sleep). Tests inject a fake
    ``run_fn`` / ``sleep`` / ``clock`` and a bounded ``max_cycles`` so the loop
    runs N cycles with NO real sleep and proves the heartbeat lands each cycle.
    """
    ap = argparse.ArgumentParser(description="Always-on self-improving paper loop.")
    ap.add_argument("--forever", action="store_true", help="loop until stopped")
    ap.add_argument("--interval", type=int, default=1200,
                    help="seconds between cycles in --forever mode (default 1200 = 20 min)")
    a = ap.parse_args(argv)
    _run = run_fn if run_fn is not None else run_once
    _sleep = sleep if sleep is not None else time.sleep
    _beat()  # live BEFORE the first (slow) cycle completes
    n = 0
    while True:
        out = _run()
        _beat(float(clock()) if clock is not None else None)
        _print_cycle(out)
        n += 1
        if not a.forever:
            return 0
        if max_cycles is not None and n >= max_cycles:
            return 0
        _sleep(max(60, a.interval))


if __name__ == "__main__":
    raise SystemExit(main())

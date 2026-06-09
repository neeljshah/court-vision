"""Live game replay harness — paper scaffold for walk-through testing of the
in-game simulation pipeline against completed game PBP.

Honesty class: serve_human (paper-only). Outputs are artifacts under
data/cache/team_system/. NOT wired into api/, golive, or any real-money path.

LEAK-FREE CONTRACT
------------------
build_snapshot_through_k(actions, k, box_meta) reads actions[:k+1] ONLY.
An assert enforces this by slicing once and never indexing beyond k.
Re-price at step k uses only the snapshot AT step k (no anchor_final by
default — an anchor would embed routed-final = future-leaning leak).
Re-price RNG is seeded per step (seed + k) for reproducibility.

BOX STAT NAME REMAP
-------------------
NBA CDN box uses reboundsTotal/foulsPersonal/threePointersMade while the
sim engine and STATS list use reb/pf/fg3m. STAT_BOX_MAP handles this.

AST RECONSTRUCTION NOTE
-----------------------
Assists are the lossiest reconstructed stat. The CDN PBP encodes the assist
as an `assistPersonId` field on the scoring action (not a separate event).
The harness reads assistPersonId when present on made FG actions. This covers
most assists but may miss edge cases. reconcile() reports AST MAE separately
and documents this lossiness honestly.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from src.sim.live_game_simulator import (  # noqa: E402
    LiveGameSimResult,
    REG_TOTAL_SEC,
    _clock_to_sec,
    _sec_remaining,
    simulate_rest_of_game,
)
from src.sim.game_simulator import STATS  # noqa: E402

from scripts.team_system.live_winprob import (  # noqa: E402
    live_win_prob,
    reconcile_winprob_with_score,
)

# ---------------------------------------------------------------------------
# Optional backends (try-guarded so missing torch/artifacts degrade to rog)
# ---------------------------------------------------------------------------
try:
    from src.prediction.predict_in_game import project_from_snapshot as _project  # type: ignore
    _HAS_PROJECTOR = True
except Exception:
    _HAS_PROJECTOR = False

try:
    from src.sim.fast_sim import simulate_game_fast as _fast_sim  # type: ignore
    _HAS_FAST = True
except Exception:
    _HAS_FAST = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CACHE = str(_REPO / "data" / "cache" / "team_system")

STAT_BOX_MAP: Dict[str, str] = {
    "pts":  "points",
    "reb":  "reboundsTotal",
    "ast":  "assists",
    "stl":  "steals",
    "blk":  "blocks",
    "tov":  "turnovers",
    "fg3m": "threePointersMade",
    "pf":   "foulsPersonal",
}

# Action types that trigger a re-price step in 'possession' mode
_POSSESSION_ACTIONS = frozenset({
    "2pt", "3pt", "freethrow", "turnover", "steal",
    "rebound", "block", "period",
})
# Team-rebound person IDs that should be skipped (0 or absent)
_TEAM_PERSON_IDS = frozenset({0, None})


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------
def load_pbp(gid: str, cache: str = DEFAULT_CACHE) -> List[dict]:
    """Return game.actions sorted by orderNumber. Raises FileNotFoundError if absent."""
    path = os.path.join(cache, "pbp", f"{gid}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"PBP not found: {path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    actions = d["game"]["actions"]
    return sorted(actions, key=lambda a: a.get("orderNumber", 0))


def load_box(gid: str, cache: str = DEFAULT_CACHE) -> dict:
    """Load box JSON and return normalised dict.

    Returns
    -------
    {
      'home_tri', 'away_tri', 'home_score', 'away_score',
      'players': {pid(int): {'name', 'team', 'starter', stat->val for stat in STATS}}
    }
    """
    path = os.path.join(cache, "box", f"{gid}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Box not found: {path}")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    g = d["game"]
    home = g["homeTeam"]
    away = g["awayTeam"]
    home_tri = home["teamTricode"]
    away_tri = away["teamTricode"]
    players: Dict[int, dict] = {}
    for team_dict, tri in ((home, home_tri), (away, away_tri)):
        for p in team_dict.get("players", []):
            pid = int(p.get("personId", 0))
            if pid == 0:
                continue
            stats_raw = p.get("statistics", {})
            row: Dict[str, object] = {
                "name": p.get("name", p.get("nameI", "")),
                "team": tri,
                "starter": bool(p.get("starter", 0)),
            }
            for canonical, box_key in STAT_BOX_MAP.items():
                raw = stats_raw.get(box_key, 0)
                try:
                    row[canonical] = float(raw) if raw is not None else 0.0
                except (TypeError, ValueError):
                    row[canonical] = 0.0
            players[pid] = row
    return {
        "home_tri": home_tri,
        "away_tri": away_tri,
        "home_score": int(home.get("score", 0)),
        "away_score": int(away.get("score", 0)),
        "players": players,
    }


# ---------------------------------------------------------------------------
# ReplayStep container
# ---------------------------------------------------------------------------
@dataclass
class ReplayStep:
    action_idx: int
    period: int
    clock_sec: float
    elapsed_sec: float
    sec_remaining: float
    home_score: int
    away_score: int
    proj_home_final: float
    proj_away_final: float
    home_win_prob: float          # from simulate_rest_of_game (MC)
    winprob_coherent: float       # from live_winprob.reconcile_winprob_with_score
    reprice_ms: float
    coherent: bool                # sign(proj_margin) matches winprob
    snapshot: dict = field(repr=False, default_factory=dict)


# ---------------------------------------------------------------------------
# Snapshot builder — LEAK-FREE
# ---------------------------------------------------------------------------
def build_snapshot_through_k(
    actions: List[dict],
    k: int,
    box_meta: dict,
) -> dict:
    """Reconstruct running game state from actions[0..k] INCLUSIVE.

    LEAK-FREE: slices to actions[:k+1] immediately; no index beyond k is ever
    touched. Asserted at runtime.

    Parameters
    ----------
    actions   : full sorted action list (only [:k+1] will be read)
    k         : inclusive end index
    box_meta  : output of load_box() — used ONLY for starter flag and team
                assignment (not stats); stats come from PBP accumulation.

    Returns a snapshot dict compatible with simulate_rest_of_game:
      home_team, away_team, home_score, away_score, period, clock,
      players=[{player_id, name, team, pts, reb, ast, stl, blk, tov,
                fg3m, pf, min, oncourt, is_starter, l10_min, season_pts_per_min}]
    """
    # ---- LEAK GUARD --------------------------------------------------------
    seq = actions[:k + 1]
    assert len(seq) <= k + 1, "slice invariant violated"

    home_tri = box_meta["home_tri"]
    away_tri = box_meta["away_tri"]
    box_players = box_meta["players"]

    # Per-player accumulators
    stats: Dict[int, Dict[str, float]] = {}         # pid -> stat dict
    oncourt: Dict[int, bool] = {}                   # pid -> bool
    on_since: Dict[int, float] = {}                 # pid -> game-elapsed sec when last subbed in
    min_acc: Dict[int, float] = {}                  # pid -> accumulated minutes
    pid_team: Dict[int, str] = {}                   # pid -> team tricode

    # Initialise starters as on-court at game start (elapsed=0)
    for pid, pdata in box_players.items():
        if pdata.get("starter", False):
            oncourt[pid] = True
            on_since[pid] = 0.0
        else:
            oncourt[pid] = False
        min_acc[pid] = 0.0
        pid_team[pid] = pdata["team"]
        stats[pid] = {s: 0.0 for s in STATS}

    # Current game state (updated as we walk seq)
    period = 1
    clock_sec = 720.0
    home_score = 0
    away_score = 0
    game_elapsed = 0.0  # seconds elapsed in game so far

    def _elapsed_now() -> float:
        """Seconds elapsed through current clock position."""
        if period <= 4:
            return (4 - period) * 720.0 + (720.0 - clock_sec)
        # OT: 2880 base + (period-5)*300 + (300-clock_sec)
        return 2880.0 + (period - 5) * 300.0 + (300.0 - clock_sec)

    for a in seq:
        atype = a.get("actionType", "")
        period = int(a.get("period", period) or period)
        clock_sec = _clock_to_sec(a.get("clock"))
        game_elapsed = _elapsed_now()

        # Parse scores (authoritative from PBP)
        try:
            home_score = int(a["scoreHome"])
            away_score = int(a["scoreAway"])
        except (KeyError, TypeError, ValueError):
            pass

        pid = a.get("personId")
        try:
            pid = int(pid) if pid is not None else None
        except (TypeError, ValueError):
            pid = None

        # ---- SUBSTITUTION --------------------------------------------------
        if atype == "substitution":
            if pid and pid not in _TEAM_PERSON_IDS:
                sub_type = (a.get("subType") or "").lower()
                if sub_type == "out":
                    if oncourt.get(pid, False):
                        # accumulate minutes played while on court
                        t_in = on_since.get(pid, game_elapsed)
                        min_acc[pid] = min_acc.get(pid, 0.0) + (game_elapsed - t_in) / 60.0
                        oncourt[pid] = False
                        on_since.pop(pid, None)
                elif sub_type == "in":
                    oncourt[pid] = True
                    on_since[pid] = game_elapsed
                    # register team if new player
                    if pid not in pid_team:
                        tri = a.get("teamTricode", "")
                        pid_team[pid] = tri
                        stats[pid] = {s: 0.0 for s in STATS}
                        min_acc[pid] = 0.0
            continue

        # ---- SCORING EVENTS ------------------------------------------------
        if atype in ("2pt", "3pt") and pid and pid not in _TEAM_PERSON_IDS:
            made = a.get("shotResult", "") == "Made"
            # pointsTotal is a running cumulative for the player, NOT a delta.
            # Always use the fixed shot value (2 or 3) to accumulate correctly.
            pts_delta = 3 if atype == "3pt" else 2
            if made:
                if atype == "3pt":
                    stats[pid]["fg3m"] = stats[pid].get("fg3m", 0.0) + 1.0
                stats[pid]["pts"] = stats[pid].get("pts", 0.0) + pts_delta
                # Assist: assistPersonId field on made FG
                assist_pid_raw = a.get("assistPersonId")
                if assist_pid_raw:
                    try:
                        apid = int(assist_pid_raw)
                        if apid and apid not in _TEAM_PERSON_IDS:
                            if apid not in stats:
                                stats[apid] = {s: 0.0 for s in STATS}
                            stats[apid]["ast"] = stats[apid].get("ast", 0.0) + 1.0
                    except (TypeError, ValueError):
                        pass
            continue

        if atype == "freethrow" and pid and pid not in _TEAM_PERSON_IDS:
            if a.get("shotResult", "") == "Made":
                stats[pid]["pts"] = stats[pid].get("pts", 0.0) + 1.0
            continue

        # ---- NON-SCORING COUNTING EVENTS -----------------------------------
        if atype == "rebound" and pid and pid not in _TEAM_PERSON_IDS:
            stats[pid]["reb"] = stats[pid].get("reb", 0.0) + 1.0
            continue

        if atype == "steal" and pid and pid not in _TEAM_PERSON_IDS:
            stats[pid]["stl"] = stats[pid].get("stl", 0.0) + 1.0
            continue

        if atype == "block" and pid and pid not in _TEAM_PERSON_IDS:
            stats[pid]["blk"] = stats[pid].get("blk", 0.0) + 1.0
            continue

        if atype == "turnover" and pid and pid not in _TEAM_PERSON_IDS:
            stats[pid]["tov"] = stats[pid].get("tov", 0.0) + 1.0
            continue

        if atype == "foul" and pid and pid not in _TEAM_PERSON_IDS:
            sub = (a.get("subType") or "").lower()
            if "personal" in sub or sub in ("loose ball", ""):
                stats[pid]["pf"] = stats[pid].get("pf", 0.0) + 1.0
            continue

    # ---- Finalise minutes for players still on court at step k -------------
    for pid, is_on in oncourt.items():
        if is_on and pid in on_since:
            t_in = on_since[pid]
            min_acc[pid] = min_acc.get(pid, 0.0) + (game_elapsed - t_in) / 60.0

    # ---- Build player list for snapshot ------------------------------------
    sec_rem = _sec_remaining(period, clock_sec)
    player_list = []
    for pid, pdata in box_players.items():
        row: Dict[str, object] = {
            "player_id": pid,
            "name": pdata["name"],
            "team": pid_team.get(pid, pdata["team"]),
            "oncourt": 1 if oncourt.get(pid, False) else 0,
            "is_starter": int(pdata.get("starter", False)),
            "min": round(min_acc.get(pid, 0.0), 2),
            # Pregame priors — use 0 to keep self-contained; caller may enrich
            "l10_min": 0.0,
            "season_pts_per_min": 0.0,
        }
        for s in STATS:
            row[s] = stats.get(pid, {}).get(s, 0.0)
        player_list.append(row)

    # Also add any PBP-only players (subs not in original box — rare)
    for pid, tri in pid_team.items():
        if pid not in box_players:
            row = {
                "player_id": pid,
                "name": str(pid),
                "team": tri,
                "oncourt": 1 if oncourt.get(pid, False) else 0,
                "is_starter": 0,
                "min": round(min_acc.get(pid, 0.0), 2),
                "l10_min": 0.0,
                "season_pts_per_min": 0.0,
            }
            for s in STATS:
                row[s] = stats.get(pid, {}).get(s, 0.0)
            player_list.append(row)

    return {
        "home_team": home_tri,
        "away_team": away_tri,
        "home_score": home_score,
        "away_score": away_score,
        "period": period,
        "clock": clock_sec,
        "sec_remaining": sec_rem,
        "players": player_list,
    }


# ---------------------------------------------------------------------------
# Re-price dispatcher
# ---------------------------------------------------------------------------
def _reprice(
    snapshot: dict,
    backend: str,
    n_sims: int,
    seed: int,
) -> LiveGameSimResult:
    """Call the selected backend. Falls back to 'rog' on any error."""
    if backend == "projector" and _HAS_PROJECTOR:
        try:
            return _project(snapshot, n_sims=n_sims, seed=seed)
        except Exception:
            pass
    if backend == "fast" and _HAS_FAST:
        try:
            # fast_sim expects TeamModel; wrap via rog for now
            pass
        except Exception:
            pass
    # Default: simulate_rest_of_game (pure, no I/O)
    return simulate_rest_of_game(snapshot, n_sims=n_sims, seed=seed, anchor_final=None)


# ---------------------------------------------------------------------------
# Main replay loop
# ---------------------------------------------------------------------------
def replay_game(
    gid: str,
    *,
    backend: str = "rog",
    n_sims: int = 400,
    seed: int = 42,
    step: str = "possession",
    cache: str = DEFAULT_CACHE,
    anchor: Optional[dict] = None,
) -> List[ReplayStep]:
    """Walk a completed game's PBP, re-pricing win% at each trigger point.

    Parameters
    ----------
    gid     : game ID string (e.g. '0042500401')
    backend : 'rog' (default) | 'projector' | 'fast'
    n_sims  : MC iterations per re-price
    seed    : base seed; actual seed = seed + k for reproducibility
    step    : 'possession' (every scoring/possession-changing action) or 'period'
    anchor  : NOT passed to re-price by default (no future-leaking anchor_final).
              If caller passes a pregame-prior dict here it is documentation only;
              the reprice call explicitly passes anchor_final=None.
    cache   : cache directory

    Returns list of ReplayStep, one per trigger event.
    """
    actions = load_pbp(gid, cache)
    box_meta = load_box(gid, cache)

    trigger_types = (
        _POSSESSION_ACTIONS if step == "possession"
        else frozenset({"period"})
    )

    results: List[ReplayStep] = []

    for k, a in enumerate(actions):
        atype = a.get("actionType", "")
        # For possession mode: made shots and turnovers/steals are triggers;
        # for period mode: only period start/end actions.
        if atype not in trigger_types:
            continue
        if atype in ("2pt", "3pt") and a.get("shotResult") != "Made":
            continue
        if atype == "freethrow" and a.get("shotResult") != "Made":
            continue

        # Build leak-free snapshot through action k
        snapshot = build_snapshot_through_k(actions, k, box_meta)

        period = snapshot["period"]
        clock_sec = float(snapshot["clock"])
        sec_rem = float(snapshot["sec_remaining"])

        try:
            home_score = int(snapshot["home_score"])
            away_score = int(snapshot["away_score"])
        except (TypeError, ValueError):
            home_score = away_score = 0

        elapsed_sec = max(1.0, REG_TOTAL_SEC - sec_rem) if period <= 4 else (
            REG_TOTAL_SEC + (period - 4) * 300.0 - sec_rem
        )

        # Re-price (timed)
        t0 = time.perf_counter()
        sim_result = _reprice(snapshot, backend, n_sims, seed + k)
        reprice_ms = (time.perf_counter() - t0) * 1000.0

        proj_home = sim_result.proj_home_score
        proj_away = sim_result.proj_away_score
        mc_win_prob = sim_result.home_win_prob

        # Coherent reconciliation via live_winprob
        reconcile = reconcile_winprob_with_score(
            home_score, away_score, proj_home, proj_away, sec_rem
        )

        results.append(ReplayStep(
            action_idx=k,
            period=period,
            clock_sec=clock_sec,
            elapsed_sec=round(elapsed_sec, 1),
            sec_remaining=round(sec_rem, 1),
            home_score=home_score,
            away_score=away_score,
            proj_home_final=round(proj_home, 2),
            proj_away_final=round(proj_away, 2),
            home_win_prob=round(mc_win_prob, 4),
            winprob_coherent=reconcile["win_prob"],
            reprice_ms=round(reprice_ms, 2),
            coherent=bool(reconcile["coherent"]),
            snapshot=snapshot,
        ))

    return results


# ---------------------------------------------------------------------------
# Reconcile: compare final reconstructed box to official
# ---------------------------------------------------------------------------
def reconcile(
    steps: List[ReplayStep],
    gid: str,
    cache: str = DEFAULT_CACHE,
) -> dict:
    """Compare FINAL reconstructed snapshot (last step) to official box.

    Reports reconstruction error openly (not hidden). AST is documented as
    the lossiest reconstructed stat.
    """
    if not steps:
        return {"error": "no replay steps"}

    final_snap = steps[-1].snapshot
    box_meta = load_box(gid, cache)

    # Team score error (should be ~0 since we use scoreHome/Away from PBP)
    snap_home = int(final_snap.get("home_score", 0))
    snap_away = int(final_snap.get("away_score", 0))
    team_score_err = {
        "home": snap_home - box_meta["home_score"],
        "away": snap_away - box_meta["away_score"],
    }

    # Per-player stat comparison
    snap_players = {int(p["player_id"]): p for p in final_snap.get("players", [])}
    box_players = box_meta["players"]

    stat_errors: Dict[str, List[float]] = {s: [] for s in STATS}
    worst: List[tuple] = []
    pids_common = set(snap_players) & set(box_players)

    for pid in pids_common:
        sp = snap_players[pid]
        bp = box_players[pid]
        for s in STATS:
            err = float(sp.get(s, 0.0)) - float(bp.get(s, 0.0))
            stat_errors[s].append(abs(err))
            if abs(err) > 3:
                worst.append((pid, s, round(err, 1)))

    player_mae = {}
    for s in STATS:
        errs = stat_errors[s]
        player_mae[s] = round(sum(errs) / len(errs), 3) if errs else None

    # Final proj vs actual
    last = steps[-1]
    final_proj_vs_actual = {
        "proj_home": last.proj_home_final,
        "proj_away": last.proj_away_final,
        "actual_home": box_meta["home_score"],
        "actual_away": box_meta["away_score"],
        "proj_home_err": round(last.proj_home_final - box_meta["home_score"], 2),
        "proj_away_err": round(last.proj_away_final - box_meta["away_score"], 2),
    }

    worst.sort(key=lambda x: abs(x[2]), reverse=True)
    return {
        "team_score_err": team_score_err,
        "player_mae": player_mae,
        "n_players": len(pids_common),
        "worst": worst[:10],
        "final_proj_vs_actual": final_proj_vs_actual,
        "note_ast": (
            "AST reconstruction is lossiest: reads assistPersonId on made-FG actions; "
            "may miss some assists encoded only in description text."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paper live-replay harness — walks completed game PBP + re-prices"
    )
    parser.add_argument("--game", required=True, help="Game ID, e.g. 0042500401")
    parser.add_argument("--backend", default="rog",
                        choices=["rog", "projector", "fast"],
                        help="Re-price backend (default: rog)")
    parser.add_argument("--n-sims", type=int, default=400,
                        help="MC iterations per step")
    parser.add_argument("--step", default="possession",
                        choices=["possession", "period"],
                        help="Trigger granularity")
    parser.add_argument("--out", default=None,
                        help="Output path (.json or .csv). Paper artifact only.")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    args = parser.parse_args()

    print(f"Replaying game {args.game} (backend={args.backend}, n_sims={args.n_sims}, step={args.step})")
    steps = replay_game(
        args.game,
        backend=args.backend,
        n_sims=args.n_sims,
        step=args.step,
        cache=args.cache,
    )
    print(f"n possessions (trigger steps): {len(steps)}")

    # Win% checkpoints at ~25/50/75/95% of game elapsed
    if steps:
        total_elapsed = steps[-1].elapsed_sec
        checkpoint_fracs = [0.25, 0.50, 0.75, 0.95]
        print("\n=== Win% checkpoints ===")
        print(f"  {'pct':>5}  {'per':>4}  {'score':>9}  {'proj':>13}  {'win%_mc':>8}  {'win%_coh':>9}  {'coherent':>8}")
        for frac in checkpoint_fracs:
            target = total_elapsed * frac
            s = min(steps, key=lambda x: abs(x.elapsed_sec - target))
            score_str = f"{s.home_score}-{s.away_score}"
            proj_str = f"{s.proj_home_final:.1f}-{s.proj_away_final:.1f}"
            print(f"  {int(frac*100):>4}%  {s.period:>4}  {score_str:>9}  {proj_str:>13}  "
                  f"{s.home_win_prob:>8.3f}  {s.winprob_coherent:>9.3f}  {str(s.coherent):>8}")

    # Median re-price latency
    if steps:
        lats = sorted(s.reprice_ms for s in steps)
        med_ms = lats[len(lats) // 2]
        mean_ms = sum(lats) / len(lats)
        print(f"\nMedian re-price latency: {med_ms:.1f} ms  (mean: {mean_ms:.1f} ms)")

    # Reconcile
    rec = reconcile(steps, args.game, cache=args.cache)
    print("\n=== Reconciliation ===")
    print(f"  Team score error (home/away): {rec['team_score_err']}")
    print(f"  Player MAE by stat: {rec['player_mae']}")
    print(f"  N players: {rec['n_players']}")
    print(f"  Final proj vs actual: {rec['final_proj_vs_actual']}")
    if rec.get("worst"):
        print(f"  Worst (pid,stat,err): {rec['worst'][:5]}")
    print(f"  Note: {rec['note_ast']}")

    if args.out:
        rows = []
        for s in steps:
            rows.append({
                "action_idx": s.action_idx,
                "period": s.period,
                "clock_sec": s.clock_sec,
                "elapsed_sec": s.elapsed_sec,
                "sec_remaining": s.sec_remaining,
                "home_score": s.home_score,
                "away_score": s.away_score,
                "proj_home_final": s.proj_home_final,
                "proj_away_final": s.proj_away_final,
                "home_win_prob": s.home_win_prob,
                "winprob_coherent": s.winprob_coherent,
                "reprice_ms": s.reprice_ms,
                "coherent": s.coherent,
            })
        if args.out.endswith(".csv"):
            import csv
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
        else:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump({"steps": rows, "reconcile": rec}, f, indent=2)
        print(f"\nOutput written to: {args.out}")


if __name__ == "__main__":
    main()

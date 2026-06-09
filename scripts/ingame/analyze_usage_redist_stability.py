"""analyze_usage_redist_stability.py — STEP 2 redistribution RULE + split-half
stability gate.

Step 1 established that when a high-usage creator is OFF / foul-compromised at a
quarter boundary, the engine UNDER-projects his ON-court teammates' remaining
PTS and AST (REB is null). Step 2 must (a) pin down the REDISTRIBUTION RULE the
enricher will use and (b) prove the per-creator off-effect is STABLE — not the
~0.06 split-half noise that sank the naive per-player in-game tilts.

WHAT IS MEASURED
----------------
For every (game, point) we form the leak-safe on-court absorber set of each
team whose top creator is COMPROMISED (off-court via next-quarter starters, or
deep foul trouble). For each such absorber we record the engine's *normalized*
under-projection on the redistributed stats:

    lift(absorber, stat) = (actual − projected) / proj_remaining_scale

i.e. how much MORE the absorber produced than the creator-blind engine
expected, expressed in the same remaining-production units the enricher will
boost. We aggregate this lift at the CREATOR level (the team's compromised
creator id) — "when creator C sits, his teammates collectively over-produce by
X". The RULE the enricher ships is: distribute a fraction of C's typical
remaining usage to the absorbers, weighted by each absorber's own in-game
playmaking/usage share.

SPLIT-HALF STABILITY (the gate)
-------------------------------
Randomly partition the creator-OFF *events* into two halves (seeded), compute
each creator's mean absorber-lift in each half, and correlate the two halves
over creators with >=MIN_EV events per half (Spearman + Pearson, with
Spearman-Brown step-up to full-length reliability). A rule with split-half
reliability >= 0.30 is admissible; ~0.06 is noise and must be REJECTED.

We ALSO report the stability of the SIMPLE pooled rule (one global lift, no
per-creator lookup) via odd/even event split — because the enricher ships a
POOLED constant boost (robust to small per-creator n), and that pooled estimate
must itself be stable across random data halves.

Leak-safety identical to Step 1 (lineup identity from next-quarter box only;
projection leak-free).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, FrozenSet, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
os.environ.setdefault("NBA_OFFLINE", "1")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

import numpy as np  # noqa: E402
import retro_inplay_mae as rim  # noqa: E402
from src.prediction.live_engine import project_from_snapshot  # noqa: E402
from analyze_usage_redist_residuals import (  # noqa: E402
    load_creator_index, oncourt_at_point, detect_creator_state,
)

try:
    from scipy.stats import spearmanr, pearsonr  # noqa: E402
    _HAVE_SCIPY = True
except Exception:
    _HAVE_SCIPY = False

PLAN_DIR = os.path.join(PROJECT_DIR, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

REDIST_STATS = ("pts", "ast")          # REB excluded (Step 1: null)
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
MIN_EV_PER_HALF = 3


def _spearman_brown(r: float, k: float = 2.0) -> float:
    """Step a split-half r up to full length: r_full = k r / (1+(k-1)r)."""
    if r is None:
        return None
    denom = 1.0 + (k - 1.0) * r
    return (k * r / denom) if denom != 0 else None


def _corr(xs: List[float], ys: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if len(xs) < 3:
        return None, None
    a, b = np.array(xs, float), np.array(ys, float)
    if a.std() == 0 or b.std() == 0:
        return None, None
    if _HAVE_SCIPY:
        sp = float(spearmanr(a, b).correlation)
        pe = float(pearsonr(a, b)[0])
        return sp, pe
    pe = float(np.corrcoef(a, b)[0, 1])
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    sp = float(np.corrcoef(ra, rb)[0, 1])
    return sp, pe


def run(max_games: int, usage_floor: float, seed: int) -> dict:
    creators = load_creator_index(usage_floor)
    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())
    if max_games:
        game_ids = game_ids[:max_games]

    # Each "event" = one (game, point, team) where the creator is compromised.
    # Store per-event the absorber lifts so we can split halves of EVENTS.
    # event = {creator_pid, lifts: {stat: [absorber lift, ...]}}
    events: List[dict] = []
    rng = np.random.RandomState(seed)

    n_games_ok = 0
    for gid in game_ids:
        gid_s = str(gid)
        actuals = rim.actuals_for_game(gid, qs)
        if not actuals:
            continue
        ok = False
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            oncourt = oncourt_at_point(gid_s, point)
            if not oncourt:
                continue
            cstate = detect_creator_state(snap, point, creators, oncourt)
            try:
                rows = project_from_snapshot(snap)
            except Exception:
                continue
            ok = True
            # index engine rows by (pid, stat)
            proj_by: Dict[Tuple[int, str], float] = {}
            cur_by: Dict[Tuple[int, str], float] = {}
            for r in rows:
                pid = r.get("player_id"); stat = r.get("stat")
                if pid is None or stat not in REDIST_STATS:
                    continue
                proj_by[(int(pid), stat)] = float(r.get("projected_final", 0.0) or 0.0)
                cur_by[(int(pid), stat)] = float(r.get("current", 0.0) or 0.0)

            for team, cs in cstate.items():
                if not cs.get("creator_compromised"):
                    continue
                cpid = cs.get("creator_pid")
                oncset = oncourt.get(team)
                if cpid is None or oncset is None:
                    continue
                lifts: Dict[str, List[float]] = {s: [] for s in REDIST_STATS}
                for pid in oncset:
                    if pid == cpid:
                        continue
                    for stat in REDIST_STATS:
                        proj = proj_by.get((pid, stat))
                        if proj is None:
                            continue
                        actual = actuals.get((pid, stat))
                        if actual is None:
                            continue
                        cur = cur_by.get((pid, stat), 0.0)
                        rem_proj = max(proj - cur, 0.0)
                        rem_actual = actual - cur
                        # normalized lift: extra remaining production per unit of
                        # remaining projection (dimensionless; >0 = under-projected)
                        scale = rem_proj if rem_proj > 0.5 else 0.5
                        lift = (rem_actual - rem_proj) / scale
                        lifts[stat].append(float(lift))
                if any(lifts[s] for s in REDIST_STATS):
                    events.append({"creator_pid": cpid, "point": point,
                                   "lifts": lifts})
        if ok:
            n_games_ok += 1

    return _stability(events, rng, n_games_ok)


def _stability(events: List[dict], rng, n_games) -> dict:
    out: dict = {"meta": {"n_games": n_games, "n_compromised_events": len(events),
                          "have_scipy": _HAVE_SCIPY}, "per_stat": {}}
    if not events:
        return out

    # random half assignment of EVENTS
    half = rng.randint(0, 2, size=len(events))

    for stat in REDIST_STATS:
        # ---- per-creator split-half ----
        # creator -> [lifts] in half0, half1
        c0: Dict[int, List[float]] = defaultdict(list)
        c1: Dict[int, List[float]] = defaultdict(list)
        # pooled odd/even
        pooled0: List[float] = []
        pooled1: List[float] = []
        for i, ev in enumerate(events):
            vals = ev["lifts"].get(stat, [])
            if not vals:
                continue
            mean_ev = float(np.mean(vals))
            if half[i] == 0:
                c0[ev["creator_pid"]].append(mean_ev)
                pooled0.append(mean_ev)
            else:
                c1[ev["creator_pid"]].append(mean_ev)
                pooled1.append(mean_ev)
        # creators with >= MIN_EV in BOTH halves
        xs, ys = [], []
        for cp in set(c0) & set(c1):
            if len(c0[cp]) >= MIN_EV_PER_HALF and len(c1[cp]) >= MIN_EV_PER_HALF:
                xs.append(float(np.mean(c0[cp])))
                ys.append(float(np.mean(c1[cp])))
        sp, pe = _corr(xs, ys)
        sp_full = _spearman_brown(sp) if sp is not None else None
        pe_full = _spearman_brown(pe) if pe is not None else None

        # ---- pooled estimate stability: mean lift in each random half ----
        m0 = float(np.mean(pooled0)) if pooled0 else None
        m1 = float(np.mean(pooled1)) if pooled1 else None
        # bootstrap CI on the pooled mean lift (all events) for ship calibration
        all_means = pooled0 + pooled1
        boot = []
        a = np.array(all_means, float)
        for _ in range(2000):
            boot.append(float(np.mean(rng.choice(a, size=a.size, replace=True))))
        ci = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5)))

        out["per_stat"][stat] = {
            "n_creators_paired": len(xs),
            "split_half_spearman": sp,
            "split_half_pearson": pe,
            "spearman_brown_full_spearman": sp_full,
            "spearman_brown_full_pearson": pe_full,
            "pooled_lift_half0": m0,
            "pooled_lift_half1": m1,
            "pooled_lift_all": float(np.mean(all_means)),
            "pooled_lift_ci95": ci,
            "n_events_with_stat": len(all_means),
        }
    return out


def _fmt(summary: dict) -> str:
    L = ["# STEP 2 — redistribution rule + split-half stability\n"]
    m = summary["meta"]
    L.append(f"- games: {m['n_games']}; compromised events: "
             f"{m['n_compromised_events']}; scipy={m['have_scipy']}\n")
    L.append("Normalized absorber LIFT = (actual_remaining − proj_remaining) / "
             "proj_remaining_scale; >0 means the engine UNDER-projected the "
             "absorber. Per-creator split-half over creator-mean lifts; "
             "Spearman-Brown steps a half-length r up to full length.\n")
    L.append("| stat | n_creators | split-half ρ | SB-full ρ | split-half r | "
             "pooled_lift | pooled CI95 | n_ev |")
    L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
    for stat in REDIST_STATS:
        d = summary["per_stat"].get(stat)
        if not d:
            continue
        def f(x): return f"{x:+.3f}" if isinstance(x, (int, float)) else "n/a"
        ci = d["pooled_lift_ci95"]
        L.append(f"| {stat} | {d['n_creators_paired']} | "
                 f"{f(d['split_half_spearman'])} | "
                 f"{f(d['spearman_brown_full_spearman'])} | "
                 f"{f(d['split_half_pearson'])} | "
                 f"{f(d['pooled_lift_all'])} | "
                 f"[{ci[0]:+.3f},{ci[1]:+.3f}] | {d['n_events_with_stat']} |")
    L.append("\nGATE: per-creator split-half (Spearman-Brown full) >= 0.30 "
             "admits a per-creator rule. If only the POOLED lift is stable "
             "(CI95 excludes 0) the enricher must ship a POOLED constant boost, "
             "not a per-creator lookup.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--usage-floor", type=float, default=0.24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default=os.path.join(
        PLAN_DIR, "usage_redist_stability.json"))
    args = ap.parse_args()
    summary = run(args.max_games, args.usage_floor, args.seed)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print("\n" + _fmt(summary))
    print(f"\n[redist-stab] wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

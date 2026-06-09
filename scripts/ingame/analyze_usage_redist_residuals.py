"""analyze_usage_redist_residuals.py — STEP 1 error analysis for in-game
usage-redistribution.

QUESTION
--------
The in-game engine projects each player's remaining production from HIS OWN
state (his fouls cut HIS minutes; a blowout cuts HIS minutes). It is blind to
the COMPLEMENTARY effect: when a high-usage CREATOR is OFF the floor (or in deep
foul trouble) at a quarter boundary, his usage REDISTRIBUTES to specific
on-court teammates — who should then SCORE/ASSIST MORE in the remaining
quarters than the engine (which never saw the creator leave) projects.

If that is real, the engine should systematically UNDER-project (residual =
projected_final − actual  <  0) the ON-court "absorber" teammates of a creator
who is OFF at end-of-Q(N), relative to when the creator is ON.

This script measures that conditional bias, leak-free, on the 954-game quarter
corpus. NO model is changed; this is pure instrumentation.

LEAK SAFETY
-----------
"Who is ON-court at end of Q(N)" is reconstructed from the STARTERS of Q(N+1)
(``data/cache/quarter_box/{gid}_q{N+1}.json``, start_position != "") — exactly
the snapshot_onoff_tilt_enricher precedent. That box is committed in the data
BEFORE we project; it encodes only the lineup that opened the next quarter,
which is the closing lineup of quarter N. No future STATS enter the snapshot or
the conditioning — only the lineup identity, and the engine projection itself
is leak-free (rim.build_snapshot uses only periods <= N).

"High-usage creator" identity comes from the season usage_role atlas
(usage_tier / usage_rate / creator_role) — a season-level descriptor, not the
target game.

OUTPUT
------
.planning/ingame/usage_redist_residuals.json  + console table.
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
from src.ingame.snapshot_onoff_tilt_enricher import (  # noqa: E402
    reconstruct_oncourt_pids, _DEFAULT_QB_DIR,
)

PLAN_DIR = os.path.join(PROJECT_DIR, ".planning", "ingame")
os.makedirs(PLAN_DIR, exist_ok=True)

STATS = ("pts", "reb", "ast")
SNAPSHOT_POINTS = ("endQ1", "endQ2", "endQ3")
_POINT_TO_NEXT_Q = {"endQ1": 2, "endQ2": 3, "endQ3": 4}
_ATLAS = os.path.join(PROJECT_DIR, "data", "cache", "atlas_player_usage_role.parquet")


# --------------------------------------------------------------------------- #
# Usage-role atlas: identify the high-usage creators (season descriptor).
# --------------------------------------------------------------------------- #
def load_creator_index(usage_floor: float = 0.24) -> Dict[int, dict]:
    """Return {player_id: {usage_rate, usage_tier, creator_role, ast_pct}}.

    A player counts as a CREATOR (usage-absorption trigger when he leaves) if
    his season usage_tier is 'primary'/'secondary' OR usage_rate >= usage_floor.
    """
    import pandas as pd
    if not os.path.exists(_ATLAS):
        return {}
    df = pd.read_parquet(_ATLAS, columns=[
        "player_id", "usage_rate", "usage_l10_mean", "usage_tier",
        "ast_pct", "creator_role"])
    out: Dict[int, dict] = {}
    for r in df.itertuples(index=False):
        try:
            pid = int(r.player_id)
        except (TypeError, ValueError):
            continue
        ur = float(r.usage_rate) if r.usage_rate is not None else 0.0
        tier = str(r.usage_tier or "")
        out[pid] = {
            "usage_rate": ur,
            "usage_tier": tier,
            "creator_role": str(r.creator_role or ""),
            "ast_pct": float(r.ast_pct) if r.ast_pct is not None else 0.0,
            "is_creator": (tier in ("primary", "secondary")) or (ur >= usage_floor),
            "is_primary": tier == "primary" or ur >= 0.28,
        }
    return out


# --------------------------------------------------------------------------- #
# Leak-safe oncourt reconstruction + minutes-in-current-quarter.
# --------------------------------------------------------------------------- #
def oncourt_at_point(game_id: str, point: str) -> Dict[str, FrozenSet[int]]:
    """{TEAM: frozenset(pid)} on-court at end of Q(N) via Q(N+1) starters."""
    return reconstruct_oncourt_pids(game_id, point, _DEFAULT_QB_DIR)


def _played_recent_quarter(prow: dict, point: str) -> float:
    """Minutes the player logged in the MOST RECENT completed quarter (Q N)."""
    q = {"endQ1": 1, "endQ2": 2, "endQ3": 3}[point]
    return float(prow.get(f"min_q{q}", 0.0) or 0.0)


# --------------------------------------------------------------------------- #
# Per-team creator-state detection at the snapshot.
# --------------------------------------------------------------------------- #
def detect_creator_state(
    snap: dict,
    point: str,
    creators: Dict[int, dict],
    oncourt: Dict[str, FrozenSet[int]],
) -> Dict[str, dict]:
    """For each team in the snapshot, find the top creator and whether he is
    OFF-court / in deep foul trouble at the snapshot.

    Returns {team: {creator_pid, creator_usage, creator_off, creator_foul_tr,
                    creator_compromised}}.
    A creator is 'compromised' if (off-court) OR (deep foul trouble) at end Q(N).
    foul-trouble threshold scales with quarter: pf >= period+1 by end of Q(N)
    (the classic '3 in the 1st half / 4 by end of 3rd' bench rule).
    """
    period = int(snap.get("period") or 0)        # snapshot period = N+1
    # players by team
    by_team: Dict[str, List[dict]] = defaultdict(list)
    for p in snap.get("players") or []:
        t = str(p.get("team") or "")
        if t:
            by_team[t].append(p)

    foul_floor = {2: 3, 3: 4, 4: 4}.get(period, 4)  # by endQ1->3, endQ2/Q3->4
    out: Dict[str, dict] = {}
    for team, plist in by_team.items():
        # pick the highest season-usage creator who actually PLAYED this game
        best = None
        best_ur = -1.0
        for p in plist:
            pid = int(p.get("player_id"))
            info = creators.get(pid)
            if not info or not info["is_creator"]:
                continue
            if float(p.get("min", 0) or 0) < 6.0:
                continue  # didn't meaningfully play => not the engine of the offense
            if info["usage_rate"] > best_ur:
                best_ur = info["usage_rate"]
                best = (pid, p, info)
        if best is None:
            out[team] = {"creator_pid": None, "creator_compromised": False}
            continue
        cpid, cprow, cinfo = best
        oncset = oncourt.get(team)
        # OFF-court at end Q(N): not in next-quarter starters AND logged ~0 min
        # in the most recent quarter (robust to incomplete box).
        recent_min = _played_recent_quarter(cprow, point)
        if oncset is not None:
            off = cpid not in oncset
        else:
            off = recent_min < 1.0  # fallback when next-Q box missing
        foul_tr = float(cprow.get("pf", 0) or 0) >= foul_floor
        out[team] = {
            "creator_pid": cpid,
            "creator_usage": cinfo["usage_rate"],
            "creator_off": bool(off),
            "creator_recent_min": recent_min,
            "creator_foul_tr": bool(foul_tr),
            "creator_compromised": bool(off or foul_tr),
        }
    return out


# --------------------------------------------------------------------------- #
# Main residual collection.
# --------------------------------------------------------------------------- #
def run(max_games: int, usage_floor: float) -> dict:
    creators = load_creator_index(usage_floor)
    print(f"[redist-resid] {len(creators)} players in usage atlas; "
          f"{sum(1 for v in creators.values() if v['is_creator'])} creators "
          f"(usage_floor={usage_floor})")
    qs = rim.load_quarter_stats()
    game_ids = sorted(qs["game_id"].unique().tolist())
    if max_games:
        game_ids = game_ids[:max_games]

    # residual accumulators.
    #   key = (group, point, stat) -> list of residuals (proj - actual)
    # groups:
    #   absorber_creator_off  : on-court teammate, his team's creator is OFF
    #   absorber_creator_on   : on-court teammate, his team's creator is ON
    #   absorber_creator_comp : on-court teammate, creator OFF or foul-trouble
    #   absorber_creator_ok   : on-court teammate, creator on & not foul-trouble
    resid: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    # blowout slice: |margin| at snapshot >= 15
    resid_blow: Dict[Tuple[str, str, str], List[float]] = defaultdict(list)
    n_games_ok = 0
    n_off_events = 0

    for gid in game_ids:
        gid_s = str(gid)
        actuals = rim.actuals_for_game(gid, qs)
        if not actuals:
            continue
        any_point = False
        for point in SNAPSHOT_POINTS:
            snap = rim.build_snapshot(gid, point, qs)
            if snap is None:
                continue
            oncourt = oncourt_at_point(gid_s, point)
            if not oncourt:
                continue  # need leak-safe lineup to define on-court absorbers
            cstate = detect_creator_state(snap, point, creators, oncourt)
            # snapshot margin (blowout slice)
            margin = abs(float(snap.get("home_score", 0) or 0)
                         - float(snap.get("away_score", 0) or 0))
            is_blow = margin >= 15.0

            try:
                rows = project_from_snapshot(snap)
            except Exception:
                continue
            any_point = True

            # team -> creator pid (to exclude the creator himself from absorbers)
            for r in rows:
                stat = r.get("stat")
                if stat not in STATS:
                    continue
                pid = r.get("player_id")
                if pid is None:
                    continue
                pid = int(pid)
                team = str(r.get("team") or "")
                cs = cstate.get(team)
                if cs is None or cs.get("creator_pid") is None:
                    continue
                if pid == cs["creator_pid"]:
                    continue  # the creator himself is not an absorber
                oncset = oncourt.get(team)
                if oncset is None or pid not in oncset:
                    continue  # only ON-court teammates can absorb usage
                actual = actuals.get((pid, stat))
                if actual is None:
                    continue
                proj = float(r.get("projected_final", 0.0) or 0.0)
                res = proj - actual          # <0 => engine UNDER-projects

                off = cs["creator_off"]
                comp = cs["creator_compromised"]
                grp_off = "absorber_creator_off" if off else "absorber_creator_on"
                grp_comp = ("absorber_creator_comp" if comp
                            else "absorber_creator_ok")
                resid[(grp_off, point, stat)].append(res)
                resid[(grp_comp, point, stat)].append(res)
                if is_blow:
                    resid_blow[(grp_off, point, stat)].append(res)
                if off and stat == "pts":
                    pass
            # count off events
            for cs in cstate.values():
                if cs.get("creator_off"):
                    n_off_events += 1
        if any_point:
            n_games_ok += 1
        if n_games_ok % 100 == 0 and any_point:
            print(f"  [{n_games_ok}] games processed", flush=True)

    return _summarize(resid, resid_blow, n_games_ok, n_off_events)


def _stats(xs: List[float]) -> dict:
    if not xs:
        return {"n": 0, "mean": None, "mae": None}
    a = np.array(xs, dtype=float)
    return {
        "n": int(a.size),
        "mean_resid": float(a.mean()),     # proj - actual; <0 = under-projection
        "median_resid": float(np.median(a)),
        "mae": float(np.abs(a).mean()),
        "sd": float(a.std(ddof=1)) if a.size > 1 else 0.0,
        "se": float(a.std(ddof=1) / np.sqrt(a.size)) if a.size > 1 else 0.0,
    }


def _summarize(resid, resid_blow, n_games, n_off_events) -> dict:
    out: dict = {
        "meta": {"n_games": n_games, "n_creator_off_events": n_off_events},
        "by_group_point_stat": {},
        "pooled_by_group_stat": {},
        "contrast_off_minus_on": {},
        "blowout_by_group_stat": {},
    }
    # per (group, point, stat)
    for (grp, point, stat), xs in resid.items():
        out["by_group_point_stat"][f"{grp}/{point}/{stat}"] = _stats(xs)
    # pooled over points
    pooled: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for (grp, point, stat), xs in resid.items():
        pooled[(grp, stat)].extend(xs)
    for (grp, stat), xs in pooled.items():
        out["pooled_by_group_stat"][f"{grp}/{stat}"] = _stats(xs)
    # contrast: creator-off vs creator-on (and comp vs ok) per stat
    for stat in STATS:
        off = pooled.get(("absorber_creator_off", stat), [])
        on = pooled.get(("absorber_creator_on", stat), [])
        comp = pooled.get(("absorber_creator_comp", stat), [])
        ok = pooled.get(("absorber_creator_ok", stat), [])
        c = {}
        if off and on:
            so, sn = _stats(off), _stats(on)
            diff = so["mean_resid"] - sn["mean_resid"]
            # 2-sample SE
            se = float(np.sqrt(so["se"] ** 2 + sn["se"] ** 2))
            c["off_minus_on_mean_resid"] = diff
            c["off_mean_resid"] = so["mean_resid"]
            c["on_mean_resid"] = sn["mean_resid"]
            c["z"] = (diff / se) if se > 0 else None
            c["n_off"] = so["n"]
            c["n_on"] = sn["n"]
        if comp and ok:
            sc, sk = _stats(comp), _stats(ok)
            diffc = sc["mean_resid"] - sk["mean_resid"]
            sec = float(np.sqrt(sc["se"] ** 2 + sk["se"] ** 2))
            c["comp_minus_ok_mean_resid"] = diffc
            c["comp_mean_resid"] = sc["mean_resid"]
            c["z_comp"] = (diffc / sec) if sec > 0 else None
            c["n_comp"] = sc["n"]
        out["contrast_off_minus_on"][stat] = c
    # blowout slice pooled
    bpooled: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for (grp, point, stat), xs in resid_blow.items():
        bpooled[(grp, stat)].extend(xs)
    for (grp, stat), xs in bpooled.items():
        out["blowout_by_group_stat"][f"{grp}/{stat}"] = _stats(xs)
    return out


def _fmt(summary: dict) -> str:
    L = ["# STEP 1 — usage-redistribution residual analysis\n"]
    m = summary["meta"]
    L.append(f"- games: {m['n_games']}; creator-OFF events (team-points): "
             f"{m['n_creator_off_events']}\n")
    L.append("## Contrast: engine residual (proj − actual) for ON-court "
             "absorbers,\n## creator OFF vs creator ON  (negative = engine "
             "UNDER-projects)\n")
    L.append("| stat | off_resid | on_resid | off−on | z | n_off | n_on |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for stat in STATS:
        c = summary["contrast_off_minus_on"].get(stat, {})
        if "off_minus_on_mean_resid" not in c:
            continue
        L.append(f"| {stat} | {c['off_mean_resid']:+.3f} | "
                 f"{c['on_mean_resid']:+.3f} | "
                 f"{c['off_minus_on_mean_resid']:+.3f} | "
                 f"{(c['z'] or 0):+.2f} | {c['n_off']} | {c['n_on']} |")
    L.append("")
    L.append("## Contrast: creator COMPROMISED (off OR foul-trouble) vs OK\n")
    L.append("| stat | comp_resid | comp−ok | z | n_comp |")
    L.append("|---|--:|--:|--:|--:|")
    for stat in STATS:
        c = summary["contrast_off_minus_on"].get(stat, {})
        if "comp_minus_ok_mean_resid" not in c:
            continue
        L.append(f"| {stat} | {c['comp_mean_resid']:+.3f} | "
                 f"{c['comp_minus_ok_mean_resid']:+.3f} | "
                 f"{(c.get('z_comp') or 0):+.2f} | {c['n_comp']} |")
    L.append("")
    L.append("## Pooled mean residual by group/stat\n")
    L.append("| group/stat | n | mean_resid | mae |")
    L.append("|---|--:|--:|--:|")
    for k in sorted(summary["pooled_by_group_stat"]):
        d = summary["pooled_by_group_stat"][k]
        if d["n"] == 0:
            continue
        L.append(f"| {k} | {d['n']} | {d['mean_resid']:+.3f} | {d['mae']:.3f} |")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=0)
    ap.add_argument("--usage-floor", type=float, default=0.24)
    ap.add_argument("--json", default=os.path.join(
        PLAN_DIR, "usage_redist_residuals.json"))
    args = ap.parse_args()
    summary = run(args.max_games, args.usage_floor)
    with open(args.json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=str)
    print("\n" + _fmt(summary))
    print(f"\n[redist-resid] wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""build_cv_board.py — emit the authoritative NYK/SAS roster map for the CV board,
and (sub-command) re-derive the TOTAL-based market-board scenarios at the SAME
de-biased (~212.5) level the CV page displays so the board is internally coherent.

The CV board (api/_cv_board.py) previously split the box score with HAND-TYPED
player-id frozensets, which contained errors (e.g. Luke Kornet on NYK — he is SAS).
This script derives the team for every sim_slate player from the SIM'S OWN roster
source — data/cache/team_system/player_rates.parquet, the exact table
sim.basketball_sim.TeamModel.from_cache filters by `team == tri` — so the board
splits players exactly the way the simulation does.

TOTAL DE-BIAS (added 2026-06-10, user-caught coherence bug):
  The CV page (api/_cv_board.py) DEFLATES the projected score + per-player pts by
  defl = target_total / total_raw, target_total = (210+215)/2 = 212.5, total_raw =
  the possession_mc engine total (233.2766) — the documented "+12..22 Finals total
  over-prediction" correction. But the market board's TOTAL-threshold scenarios
  (>=230, >=240, <205, <195) were still priced off the RAW (~234) sim total, so a
  projected ~213 total coexisted with a 58% chance of 230+. `debias_total_scenarios`
  re-derives those four scenarios (plus the per-player hot-game / explosion overs,
  which inherit the SAME per-player pts inflation) at the de-biased level by scaling
  every simulated total / player-pts sample by `defl` and re-thresholding. MARGIN-
  based scenarios (blowout / nail-biter / OT-likely) and win% are NOT touched — a
  symmetric total scale leaves the margin distribution (and the ~49% home win-prob)
  unchanged. Per-player DD/blocks/longshots/tiers are left intact. This is the
  documented de-bias applied consistently — NOT a new edge. Bias-corrected, not advice.

Output (roster sub-command): data/cache/team_system/roster_NYK_SAS_2026.json
  {"by_pid": {pid: "NYK"|"SAS"}, "by_name": {...}, "source": ..., "discrepancies": [...]}

Run:
  python scripts/team_system/build_cv_board.py                 # rebuild roster map
  python scripts/team_system/build_cv_board.py --debias-total  # re-derive total scenarios
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TS = ROOT / "data" / "cache" / "team_system"
RATES = TS / "player_rates.parquet"
OUT = TS / "roster_NYK_SAS_2026.json"
TEAMS = ("NYK", "SAS")

# --- total de-bias constants (mirror api/_cv_board.py exactly) ---
MARKET_BOARD = TS / "market_board_NYK_SAS_2026-06-10.json"
# total_raw is the possession_mc engine total the CV page deflates against; pulled
# from data/cache/team_system/g3page_NYK_SAS_2026-06-10.json (ensemble16.preds).
_TOTAL_RAW = 233.27657604962587
_TARGET_TOTAL = (210 + 215) / 2.0          # = 212.5, the same (low+high)/2 the page uses
_DEBIAS_FACTOR = _TARGET_TOTAL / _TOTAL_RAW  # ~0.910936
# scenario labels that key off the (inflated) TOTAL or per-player pts -> must de-bias
_TOTAL_SCENARIOS = {
    "shootout (total 230+)": (">=", 230, "total"),
    "track-meet (total 240+)": (">=", 240, "total"),
    "rock-fight (total < 205)": ("<", 205, "total"),
    "low game (total < 195)": ("<", 195, "total"),
    "hot game (a 35+ scorer)": (">=", 35, "anyplayer"),
    "explosion (a 40+ scorer)": (">=", 40, "anyplayer"),
}

# Known sim-vs-external-claim discrepancies, resolved against in-universe game data
# (data/live G1-G3 boxscores + nyksas_player_gamelog.parquet). Kept here so the
# emitted file documents them; the SIM roster is authoritative for predictions.
DISCREPANCIES = [
    "Trey Jemison III (1641998): external 2025-26 list claimed SAS; sim gamelogs "
    "(29 rows) + player_rates all say NYK. Sim roster (NYK) kept — flag if a real "
    "roster feed ever contradicts.",
    "Jordan Clarkson (203903): 'verify' flag resolved NYK (played for NYK in G3 "
    "live boxscore 0042500403).",
    "Jose Alvarado (1630631): 'verify' flag resolved NYK (played for NYK in G3 "
    "live boxscore 0042500403).",
    "Luke Kornet (1628436): SAS (signed San Antonio 2025) — was wrongly in the "
    "old hand-typed _NYK_IDS; confirmed SAS by player_rates + G3 boxscore.",
]


def build_roster(slate_pids=None) -> dict:
    """Return the roster map dict. slate_pids (optional) restricts to those pids;
    default = every NYK/SAS player in player_rates.parquet."""
    df = pd.read_parquet(RATES)
    df = df[df.team.isin(TEAMS)]
    if slate_pids is not None:
        keep = {int(p) for p in slate_pids}
        df = df[df.pid.isin(keep)]
        missing = keep - {int(p) for p in df.pid}
        if missing:
            raise ValueError(f"pids not on either sim roster: {sorted(missing)}")
    by_pid = {str(int(r.pid)): str(r.team) for r in df.itertuples(index=False)}
    by_name = {str(r.player): str(r.team) for r in df.itertuples(index=False)}
    return {
        "by_pid": by_pid,
        "by_name": by_name,
        "source": (
            "data/cache/team_system/player_rates.parquet (the sim's TeamModel.from_cache "
            "roster source), cross-checked vs market_board_NYK_SAS_2026-06-10.json (14/14 "
            "match) and the G3 live boxscore data/live/0042500403_*.json"
        ),
        "discrepancies": DISCREPANCIES,
    }


def _sim_total_and_pts(nsims: int = 20000, seed: int = 2026):
    """Re-run the EXACT board sim (seed=2026, anchor+defense, CV_MIN_VAR joint-fix)
    and return (total_samples, [per-player pts sample arrays]). Deterministic, so it
    reproduces the same RAW scenario probs the market board was built with."""
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "scripts" / "team_system"))
    import numpy as np  # noqa: E402
    from sim.basketball_sim import TeamModel  # noqa: E402
    from sim.fast_sim import simulate_game_fast  # noqa: E402
    from min_var_layer import apply_min_var, min_cv_map  # noqa: E402
    from market_intelligence import _JOINT_FIX  # noqa: E402

    h = TeamModel.from_cache("NYK")
    a = TeamModel.from_cache("SAS")
    res = simulate_game_fast(h, a, n_sims=nsims, seed=seed, anchor=True, defense=True)
    _JOINT_FIX["on"] = True
    apply_min_var(res, min_cv_map(), seed=seed)  # marginals preserved EXACTLY
    total = np.asarray(res.home_total) + np.asarray(res.away_total)
    pts = [np.asarray(d["samples"]["pts"]) for d in res.players.values()]
    return total, pts


def _scenario_prob(label, total, player_pts, factor):
    """Re-derive a TOTAL-/per-player-pts-based scenario prob at the de-biased level
    by scaling every sample by `factor` before thresholding."""
    import numpy as np  # noqa: E402

    op, thr, kind = _TOTAL_SCENARIOS[label]
    if kind == "total":
        arr = total * factor
        return float(np.mean(arr >= thr) if op == ">=" else np.mean(arr < thr))
    # anyplayer: a 35+/40+ scorer using de-biased per-player pts
    n = len(total)
    hit = np.zeros(n, dtype=bool)
    for arr in player_pts:
        hit |= (arr * factor) >= thr
    return float(hit.mean())


def debias_total_scenarios(nsims: int = 20000, seed: int = 2026) -> dict:
    """Re-derive the TOTAL-/per-player-pts-based scenarios in the market board JSON at
    the SAME de-biased (~212.5) level the CV page displays. Margin scenarios + win%
    are left untouched (symmetric total scale -> margin distribution unchanged).
    Returns the updated board dict (and writes it back)."""
    board = json.loads(MARKET_BOARD.read_text(encoding="utf-8"))
    total, player_pts = _sim_total_and_pts(nsims=nsims, seed=seed)
    factor = _DEBIAS_FACTOR

    changes = []
    for sc in board.get("scenarios", []):
        label = sc.get("label", "")
        if label in _TOTAL_SCENARIOS:
            before = float(sc.get("p", 0.0))
            after = round(_scenario_prob(label, total, player_pts, factor), 4)
            sc["p"] = after
            changes.append((label, before, after))

    board["total_debiased"] = True
    board["debias_factor"] = round(factor, 6)
    board["debias_note"] = (
        "TOTAL-based scenarios (>=230, >=240, <205, <195) and the per-player hot-game/"
        "explosion overs were re-derived at the de-biased ~212.5 total level "
        f"(factor={factor:.6f} = 212.5/233.2766, the same defl the CV page applies to "
        "the score + box pts). Documented Finals total +12..22 over-prediction "
        "correction, applied consistently — NOT a new edge. Margin scenarios + win% "
        "are intentionally unchanged (symmetric total scale leaves the margin "
        "distribution and the ~49% home win-prob fixed)."
    )
    MARKET_BOARD.write_text(json.dumps(board, indent=2), encoding="utf-8")
    print(f"de-biased {len(changes)} total/pts scenarios (factor={factor:.6f}):")
    for label, b, a in changes:
        print(f"   {label:30s} {b:.4f} -> {a:.4f}")
    print(f"wrote {MARKET_BOARD}")
    return board


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--debias-total", action="store_true",
                    help="re-derive the market-board total scenarios at the de-biased "
                         "~212.5 level (coherent with the CV page); does NOT rebuild roster")
    ap.add_argument("--nsims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    if args.debias_total:
        debias_total_scenarios(nsims=args.nsims, seed=args.seed)
        return

    roster = build_roster()
    OUT.write_text(json.dumps(roster, indent=2), encoding="utf-8")
    nyk = sum(1 for t in roster["by_pid"].values() if t == "NYK")
    sas = sum(1 for t in roster["by_pid"].values() if t == "SAS")
    print(f"wrote {OUT}  NYK={nyk} SAS={sas} total={len(roster['by_pid'])}")


if __name__ == "__main__":
    main()

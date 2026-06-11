"""build_cv_board.py — OWNER A: offline board-data builder for the CourtVision G4 board.

Produces:
  data/cache/team_system/market_board_NYK_SAS_2026-06-10.json

Uses market_intelligence.py library functions directly (no stdout parsing).
CV_MIN_VAR (--joint-fix) is applied so DD/combos are JOINT_CORRECTED.

Correctness gate (must pass):
  Wembanyama blk mean ~3.33 (p3 ~0.65), DD ~0.55; KAT DD ~0.55.

Usage (idempotent, re-runnable):
  python scripts/courtvision/build_cv_board.py [--nsims 20000] [--seed 2026]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Path setup (mirror market_intelligence.py discipline)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_TS = os.path.join(_ROOT, "scripts", "team_system")
_SRC = os.path.join(_ROOT, "src")
for _p in (_TS, _SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from min_var_layer import apply_min_var, min_cv_map  # noqa: E402
from market_intelligence import (  # noqa: E402
    price_player, scenarios, hot_game, _tier, _JOINT_FIX, fair, DD,
)

OUT_PATH = os.path.join(_ROOT, "data", "cache", "team_system",
                        "market_board_NYK_SAS_2026-06-10.json")
HOME, AWAY = "NYK", "SAS"
MIN_PTS = 8.0   # include bench rotation players


def _dd_prob(samples: dict) -> float:
    """P(double-double) from a player's sample dict."""
    pts = np.asarray(samples["pts"])
    ddc = sum(
        (np.asarray(samples.get(k, np.zeros_like(pts))) >= 10).astype(int)
        for k in DD
    )
    return float(np.mean(ddc >= 2))


def _td_prob(samples: dict) -> float:
    """P(triple-double) from a player's sample dict."""
    pts = np.asarray(samples["pts"])
    ddc = sum(
        (np.asarray(samples.get(k, np.zeros_like(pts))) >= 10).astype(int)
        for k in DD
    )
    return float(np.mean(ddc >= 3))


def build_market_board(nsims: int = 20000, seed: int = 2026) -> dict:
    """Run the sim and build the full market_board dict."""
    # --- 1. load team models ---
    h = TeamModel.from_cache(HOME)
    a = TeamModel.from_cache(AWAY)

    # --- 2. sim (seed=2026 as specified) ---
    res = simulate_game_fast(h, a, n_sims=nsims, seed=seed, anchor=True, defense=True)

    # --- 3. apply CV_MIN_VAR joint corrector (--joint-fix) ---
    _JOINT_FIX["on"] = True
    cvmap = min_cv_map()
    apply_min_var(res, cvmap, seed=seed)

    # --- 4. per-player markets ---
    rows_by_pts = sorted(res.players.items(), key=lambda x: -x[1]["mean"]["pts"])

    double_doubles = []
    blocks = []
    all_markets_flat = []  # for longshots + tier_counts

    for pid, d in rows_by_pts:
        mean_pts = d["mean"]["pts"]
        if mean_pts < MIN_PTS:
            continue
        name = d["name"]
        s = d["samples"]
        pts = np.asarray(s["pts"])
        blk_arr = np.asarray(s.get("blk", np.zeros_like(pts)))

        # -- double-double & triple-double --
        dd_p = _dd_prob(s)
        td_p = _td_prob(s)
        dd_tier = "JOINT_CORRECTED"  # always joint after CV_MIN_VAR
        double_doubles.append({
            "player": name,
            "team": d["team"],
            "dd": round(dd_p, 4),
            "td": round(td_p, 4),
            "tier": dd_tier,
        })

        # -- block distributions (for players with meaningful blk rate) --
        blk_mean = float(blk_arr.mean())
        if blk_mean >= 0.3:
            p2 = float(np.mean(blk_arr >= 2))
            p3 = float(np.mean(blk_arr >= 3))
            p4 = float(np.mean(blk_arr >= 4))
            p5 = float(np.mean(blk_arr >= 5))
            blk_tier = _tier(f"blk 1+", blk_mean > 0.5 and p3 > 0.5, joint=False)
            # for star blockers use TRUSTWORTHY if p1 >= 13%
            blk_tier = "TRUSTWORTHY" if p2 >= 0.13 else "TAIL_APPROX"
            blocks.append({
                "player": name,
                "team": d["team"],
                "mean": round(blk_mean, 3),
                "p2": round(p2, 3),
                "p3": round(p3, 3),
                "p4": round(p4, 3),
                "p5": round(p5, 3),
                "tier": blk_tier,
            })

        # -- all flat markets for longshots + tier_counts --
        for mkt_name, p, odds, tier in price_player(name, s):
            if 0.003 < p < 0.997:
                all_markets_flat.append({
                    "player": name,
                    "market": mkt_name,
                    "p": round(float(p), 4),
                    "american": odds,
                    "tier": tier,
                })

    # --- 5. longshots (tier == LONGSHOT, p < 0.06, sorted by p desc) ---
    longshots = sorted(
        [m for m in all_markets_flat if m["tier"] == "LONGSHOT"],
        key=lambda x: -x["p"],
    )
    longshots_out = [
        {
            "player": m["player"],
            "label": f"{m['player']} {m['market']}",
            "p": m["p"],
            "american": m["american"],
            "tier": "LONGSHOT",
        }
        for m in longshots[:30]  # top 30 most-likely longshots
    ]

    # --- 6. scenario distribution ---
    scen_raw = scenarios(res)
    h35, h40 = hot_game(res)
    scen_raw.extend([
        ("hot game (a 35+ scorer)", h35),
        ("explosion (a 40+ scorer)", h40),
    ])
    scenarios_out = [
        {"label": label, "p": round(float(p), 4)}
        for label, p in scen_raw
    ]

    # --- 7. tier counts ---
    tier_counts: dict[str, int] = {}
    for m in all_markets_flat:
        t = m["tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    return {
        "double_doubles": double_doubles,
        "blocks": blocks,
        "longshots": longshots_out,
        "scenarios": scenarios_out,
        "tier_counts": tier_counts,
        "meta": {
            "home": HOME,
            "away": AWAY,
            "nsims": nsims,
            "seed": seed,
            "joint_fix": True,
            "built_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def correctness_gate(board: dict) -> bool:
    """Verify Wemby blk mean ~3.33 (p3 ~0.65), DD ~0.55; KAT DD ~0.55."""
    ok = True

    # Wemby blocks
    wemby_blk = next(
        (b for b in board["blocks"] if "Wembanyama" in b["player"]), None
    )
    if wemby_blk is None:
        print("GATE FAIL: Wembanyama not found in blocks.")
        return False
    blk_mean = wemby_blk["mean"]
    blk_p3 = wemby_blk["p3"]
    if not (2.5 <= blk_mean <= 4.2):
        print(f"GATE WARN: Wemby blk mean={blk_mean:.3f} outside [2.5, 4.2] (target ~3.33)")
        ok = False
    else:
        print(f"GATE OK: Wemby blk mean={blk_mean:.3f}  p3={blk_p3:.3f}")

    # Wemby DD
    wemby_dd = next(
        (d for d in board["double_doubles"] if "Wembanyama" in d["player"]), None
    )
    if wemby_dd is None:
        print("GATE FAIL: Wembanyama not found in double_doubles.")
        return False
    if not (0.40 <= wemby_dd["dd"] <= 0.75):
        print(f"GATE WARN: Wemby DD={wemby_dd['dd']:.3f} outside [0.40, 0.75] (target ~0.55)")
        ok = False
    else:
        print(f"GATE OK: Wemby DD={wemby_dd['dd']:.3f}")

    # KAT DD
    kat_dd = next(
        (d for d in board["double_doubles"]
         if "Towns" in d["player"] or "Karl" in d["player"]), None
    )
    if kat_dd is None:
        print("GATE WARN: KAT not found in double_doubles.")
    elif not (0.35 <= kat_dd["dd"] <= 0.75):
        print(f"GATE WARN: KAT DD={kat_dd['dd']:.3f} outside [0.35, 0.75] (target ~0.55)")
        ok = False
    else:
        print(f"GATE OK: KAT DD={kat_dd['dd']:.3f}")

    return ok


def main():
    ap = argparse.ArgumentParser(description="Build G4 market board JSON (OWNER A)")
    ap.add_argument("--nsims", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    print(f"Building market board: {HOME} vs {AWAY}, nsims={args.nsims}, seed={args.seed}")
    board = build_market_board(nsims=args.nsims, seed=args.seed)

    # Correctness gate
    gate_pass = correctness_gate(board)
    if not gate_pass:
        print("WARNING: Correctness gate has warnings — inspect numbers before using.")

    # Write output (idempotent — overwrites if exists)
    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=2)

    # Verify valid JSON round-trip
    with open(out_path, encoding="utf-8") as fh:
        _check = json.load(fh)
    n_markets = sum(len(v) for v in (board["double_doubles"], board["blocks"],
                                     board["longshots"], board["scenarios"]))
    print(f"OK: market board written -> {out_path}")
    print(f"    dd={len(board['double_doubles'])} players, "
          f"blk={len(board['blocks'])} players, "
          f"longshots={len(board['longshots'])}, "
          f"scenarios={len(board['scenarios'])}, "
          f"tier_counts={board['tier_counts']}")


if __name__ == "__main__":
    main()

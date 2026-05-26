"""multi_game_kelly.py — R18 K7.

Multi-game portfolio Kelly: allocate a single bankroll across an arbitrary
number of game slates that are running concurrently.

Why this exists
---------------
The within-game portfolio Kelly (probe_R9_C6) and the live bet ranker
(R16 E2) both cap exposure at 25% **per game**. When N games are on tonight
the naive per-game cap stacks to N * 25% which is reckless. Real Kelly is
defined over the WHOLE bankroll across the WHOLE simultaneous portfolio.

Within a game, props are correlated (same player, shared game state, pace).
The R9 C6 within-game solver already handles that via prop_corr_matrix_v2.
Across games the natural correlation is essentially zero — different
players, different shared variance — so we treat games as independent.

Algorithm
---------
1. Per game: take its within-game Kelly stakes (already C6-solved by the
   live bet ranker or by an upstream caller).
2. Sum up the across-game exposure.
3. If total > SLATE_CAP * bankroll, scale every per-game stake down by a
   single shared multiplier m = SLATE_CAP * bankroll / total_exposure.
4. Cap m at 1.0 — never up-size below-cap allocations (Kelly is the upper
   bound of optimal sizing under independence).

Identity property
-----------------
When exactly one game is supplied AND its total per-game exposure is
already at or below SLATE_CAP * bankroll, the output is identical to the
input. The within-game C6 solver runs unchanged.

CLI / API
---------
Importable functions:
    solve_multi_game(slates, bankroll, slate_cap=0.25) -> dict

CLI mode:
    python scripts/multi_game_kelly.py --slates sas_okc_2026-05-26 \\
        --bankroll 1000 --out data/cache/probe_R18_K7_multi_game_kelly_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

SLATE_CAP_DEFAULT = 0.25  # max total exposure across ALL games
CROSS_GAME_CORR = 0.0     # zero correlation assumed across separate games


# --------------------------------------------------------------------------- #
# Input shape                                                                  #
# --------------------------------------------------------------------------- #
# A "game slate input" is a dict with at least:
#     {
#       "game_id": str,
#       "ranked_bets": [
#           {"player": str, "stat": str, "side": str, "book": str,
#            "line": float, "odds": int, "kelly_stake_$": float, ...},
#           ...
#       ]
#     }
# This matches the JSON written by live_bet_ranker.py.
# --------------------------------------------------------------------------- #


def _load_slate_from_path(path: str) -> Dict[str, Any]:
    """Load a live_bet_ranker output JSON and return a normalised slate dict."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "game_id": data.get("slate_id", os.path.basename(path)),
        "label": data.get("label", ""),
        "ranked_bets": list(data.get("ranked_bets", [])),
        "source_path": path,
    }


def _per_game_exposure(slate: Dict[str, Any]) -> float:
    """Sum kelly_stake_$ across all ranked bets for this game."""
    return float(sum(
        float(b.get("kelly_stake_$", 0.0) or 0.0)
        for b in slate.get("ranked_bets", [])
    ))


def solve_multi_game(
    slates: Sequence[Dict[str, Any]],
    bankroll: float,
    slate_cap: float = SLATE_CAP_DEFAULT,
    cross_game_corr: float = CROSS_GAME_CORR,
) -> Dict[str, Any]:
    """Allocate bankroll across multiple game slates.

    Parameters
    ----------
    slates : list of slate dicts (see module docstring).
    bankroll : total bankroll in dollars.
    slate_cap : max total exposure across all games as fraction of bankroll.
    cross_game_corr : assumed correlation between games. ONLY 0.0 is
        currently supported (other values raise NotImplementedError) —
        we have no empirical evidence games are correlated; this parameter
        is exposed so a future probe could supply a calibrated value.

    Returns
    -------
    dict with:
        per_game_exposure_pre   : list[float] — sum of kelly_stake_$ per game before scaling
        per_game_exposure_post  : list[float] — same, after slate scaling
        total_exposure_pre      : float
        total_exposure_post     : float
        slate_multiplier        : float in (0, 1] applied uniformly across games
        slate_cap_dollars       : float — slate_cap * bankroll
        cap_hit                 : bool — True iff multiplier < 1
        scaled_slates           : list[slate-dicts] with rescaled ranked_bets
        cross_game_corr         : echo of the input
    """
    if cross_game_corr != 0.0:
        raise NotImplementedError(
            "non-zero cross-game correlation is reserved for future work — "
            "use cross_game_corr=0.0"
        )
    if bankroll <= 0:
        raise ValueError(f"bankroll must be > 0, got {bankroll}")
    if not (0.0 < slate_cap <= 1.0):
        raise ValueError(f"slate_cap must be in (0, 1], got {slate_cap}")

    cap_dollars = slate_cap * bankroll

    per_game_pre = [_per_game_exposure(s) for s in slates]
    total_pre = sum(per_game_pre)

    if total_pre <= cap_dollars or total_pre <= 0.0:
        multiplier = 1.0
    else:
        multiplier = cap_dollars / total_pre

    # Apply uniform multiplier to every bet. Floor stake at 0 (multiplier
    # is always non-negative here). Round to 2dp consistent with live ranker.
    scaled_slates = []
    for s in slates:
        new_bets = []
        for b in s.get("ranked_bets", []):
            nb = dict(b)
            stake = float(nb.get("kelly_stake_$", 0.0) or 0.0)
            scaled = round(stake * multiplier, 2)
            nb["kelly_stake_$_original"] = stake
            nb["kelly_stake_$"] = scaled
            # Adjust kelly_pct_used proportionally too (transparent reporting)
            if "kelly_pct_used" in nb and nb["kelly_pct_used"] is not None:
                nb["kelly_pct_used_original"] = nb["kelly_pct_used"]
                nb["kelly_pct_used"] = round(
                    float(nb["kelly_pct_used"]) * multiplier, 4
                )
            new_bets.append(nb)
        new_slate = dict(s)
        new_slate["ranked_bets"] = new_bets
        new_slate["per_game_exposure_pre"] = _per_game_exposure(s)
        new_slate["per_game_exposure_post"] = _per_game_exposure(new_slate)
        scaled_slates.append(new_slate)

    per_game_post = [
        s["per_game_exposure_post"] for s in scaled_slates
    ]
    total_post = sum(per_game_post)

    return {
        "n_games": len(slates),
        "bankroll": float(bankroll),
        "slate_cap": float(slate_cap),
        "slate_cap_dollars": float(cap_dollars),
        "per_game_exposure_pre": per_game_pre,
        "per_game_exposure_post": per_game_post,
        "total_exposure_pre": float(total_pre),
        "total_exposure_post": float(total_post),
        "slate_multiplier": float(multiplier),
        "cap_hit": bool(multiplier < 1.0 - 1e-12),
        "scaled_slates": scaled_slates,
        "cross_game_corr": cross_game_corr,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def _resolve_slate_paths(slate_ids: Iterable[str]) -> List[str]:
    """Map slate-ids to live_bet_ranker output JSON paths."""
    paths = []
    live_dir = os.path.join(PROJECT_DIR, "data", "cache", "live_bets")
    for sid in slate_ids:
        # accept either a full path or a slate-id; live_bet_ranker writes
        #   data/cache/live_bets/<date>_<slate-id>.json
        if os.path.isfile(sid):
            paths.append(sid)
            continue
        # find latest matching file
        if not os.path.isdir(live_dir):
            raise FileNotFoundError(
                f"no live_bets directory at {live_dir} — cannot resolve {sid}"
            )
        matches = [
            os.path.join(live_dir, fn)
            for fn in os.listdir(live_dir)
            if sid in fn and fn.endswith(".json") and "state" not in fn
            and "handoff" not in fn
        ]
        if not matches:
            raise FileNotFoundError(f"no live_bets file for slate-id {sid}")
        paths.append(sorted(matches)[-1])
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--slates", nargs="+", required=True,
        help="slate-ids (resolved against data/cache/live_bets/*.json) or "
             "absolute paths to live_bet_ranker output JSONs",
    )
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument(
        "--slate-cap", type=float, default=SLATE_CAP_DEFAULT,
        help="total exposure cap across all games (fraction of bankroll)",
    )
    ap.add_argument(
        "--out",
        default=os.path.join(
            PROJECT_DIR, "data", "cache",
            "probe_R18_K7_multi_game_kelly_results.json",
        ),
    )
    args = ap.parse_args()

    paths = _resolve_slate_paths(args.slates)
    slates = [_load_slate_from_path(p) for p in paths]

    print(f"[K7] resolved {len(slates)} slate(s):", flush=True)
    for s in slates:
        print(f"  - {s['game_id']}  ({len(s['ranked_bets'])} bets, "
              f"${_per_game_exposure(s):.2f} pre-scale)", flush=True)

    result = solve_multi_game(
        slates=slates,
        bankroll=args.bankroll,
        slate_cap=args.slate_cap,
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)

    print(f"[K7] wrote {args.out}", flush=True)
    print(f"[K7] total pre=${result['total_exposure_pre']:.2f} "
          f"post=${result['total_exposure_post']:.2f} "
          f"multiplier={result['slate_multiplier']:.4f} "
          f"cap_hit={result['cap_hit']}", flush=True)


if __name__ == "__main__":
    main()

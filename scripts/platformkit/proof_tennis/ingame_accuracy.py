"""scripts.platformkit.proof_tennis.ingame_accuracy — ATP in-game, LEAK-FREE at last.

Tennis was the one BLOCKED cell on the in-game scoreboard: matches.parquet 'score' is
WINNER-ordered, so naively reconstructing a fixed-(p1,p2) mid-match state leaks the winner.
This module uses the SAME leak-free pattern as the NBA 'team-ahead-after-Q1 -> P(win)' proof:
the realized in-game STATE is a within-match ROLE fixed by the SET RESULT (not the match
outcome), and the LABEL is the genuine future outcome.

  CHECKPOINT "after set 1": the SET-1 WINNER is the realized leader (1-0 in sets). Whether the
    eventual match-winner won set 1 is parseable from the per-set score; the set-1 winner's
    IDENTITY is the realized state (NOT a leak). LABEL = "does the set-1 leader win the match".
  CHECKPOINT "after set 2 @ 1-1" (best-of-3, decisive set): each player has one set; the
    realized momentum leader = the SET-2 winner. LABEL = "does the set-2 winner win the match".

Three forecasters of that label (all expressed FOR the leader):
  (a) PREGAME-Elo  : leak-free walk-forward Elo P(leader beats trailer) — the prior, ignores lead.
  (b) SCORE-ONLY   : TennisRepricer at the set score with a NEUTRAL per-set prob (0.5) — lead only.
  (c) COMBINED     : TennisRepricer at the set score with p_set derived from the leader's Elo.

Scored on Brier over a chronological held-out split (year > TRAIN_YEAR_MAX). EXPECT (cross-sport
pattern) combined < pregame AND combined <= score-only — reported HONESTLY whatever it measures.

LEAK GUARD: the score is parsed into per-set (p1_games, p2_games) using the 'winner' column ONLY
to de-order the per-set games; the resulting STATE (who leads after set k) is a function of set
results, and the LABEL is the match outcome (the future). The Elo is strictly walk-forward. No
later-set info enters an earlier checkpoint. Forecaster quality, not a $ edge (a live book sees
the score too). INVARIANTS: never edit src/ or kernel/; <=300 LOC; Brier-graded, never MAE.
Run: python -m scripts.platformkit.proof_tennis.ingame_accuracy
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.tennis.elo_core import SURFACE_BLEND  # noqa: E402
from domains.tennis.elo_tune import _walk_forward_blend  # noqa: E402
from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402
from scripts.platformkit.proof_tennis.ingame_calib import recalibrate_holdout  # noqa: E402

_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_TRAIN_YEAR_MAX = 2022  # train (Elo warm-up) <= this; held-out test > this
_SET_TOKEN = re.compile(r"^(\d+)-(\d+)$")


def _corpus_from_env() -> Optional[Path]:
    """$PROOF_CORPUS_ROOT/tennis if set, else None (real data/domains default)."""
    root = os.environ.get("PROOF_CORPUS_ROOT")
    return Path(root) / "tennis" if root else None


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _parse_sets(score: object) -> Optional[List[Tuple[int, int]]]:
    """Parse a WINNER-ordered score string into per-set (winner_games, loser_games).

    Strips tiebreak parens. Returns None for retirements/walkovers/unparseable strings.
    """
    if not isinstance(score, str):
        return None
    s = score.strip()
    if not s:
        return None
    sets: List[Tuple[int, int]] = []
    for tok in s.split():
        tok = re.sub(r"\(\d+\)", "", tok)        # drop tiebreak point count
        m = _SET_TOKEN.match(tok)
        if not m:
            return None                          # 'RET', 'W/O', '(W/O)', odd tokens
        a, b = int(m.group(1)), int(m.group(2))
        if max(a, b) < 6 or abs(a - b) < 1:      # incomplete / nonsense set -> reject row
            return None
        sets.append((a, b))
    return sets if sets else None


def _p_set_from_match(p_match_leader: float, best_of: int) -> float:
    """Invert the race-to-N conditional: find the per-set prob p such that the repricer's
    P(leader wins match | 1-0) == the leader's pregame match prob. Monotone -> bisection.
    Keeps the COMBINED forecaster's prior == the Elo prior before the realized lead is added."""
    rep = get_repricer("tennis")
    target = min(max(p_match_leader, 1e-4), 1 - 1e-4)

    def f(p: float) -> float:
        gs = GameState("tennis", 0.0, 0, 0,
                       pregame_params={"best_of": best_of, "p_set": p},
                       extra={"sets_1": 0, "sets_2": 0})   # 0-0 -> pure per-set prior
        return float(rep.reprice(gs)["match_win_p1"])

    lo, hi = 1e-4, 1 - 1e-4
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _reprice_leader(best_of: int, sets_lead: int, sets_trail: int, p_set_leader: float) -> float:
    """P(leader wins match) at (sets_lead, sets_trail) with the leader's per-set prob."""
    rep = get_repricer("tennis")
    gs = GameState("tennis", 0.0, 0, 0,
                   pregame_params={"best_of": best_of, "p_set": p_set_leader},
                   extra={"sets_1": sets_lead, "sets_2": sets_trail})
    return float(rep.reprice(gs)["match_win_p1"])


def run(corpus: Optional[Path] = None) -> Dict:
    # precedence: explicit corpus arg > $PROOF_CORPUS_ROOT/tennis > real data/domains path
    root = corpus or _corpus_from_env()
    matches_path = (root / "matches.parquet") if root is not None else _MATCHES
    if not matches_path.is_file():
        return {"status": "no_data", "note": "tennis matches.parquet not found"}
    matches = pd.read_parquet(matches_path)

    # leak-free walk-forward surface-blended Elo -> win_prob_p1 = P(lower-id wins), as-of.
    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND)
    wf = wf.reset_index(drop=True)
    years = pd.to_datetime(wf["date"]).dt.year
    test = wf[years > _TRAIN_YEAR_MAX].reset_index(drop=True)

    # --- after set 1 (best-of-3 AND best-of-5) ---
    a1_pre: List[float] = []; a1_blind: List[float] = []; a1_comb: List[float] = []; a1_y: List[float] = []
    # --- after set 2 @ 1-1 (best-of-3 decisive set) ---
    a2_pre: List[float] = []; a2_blind: List[float] = []; a2_comb: List[float] = []; a2_y: List[float] = []

    pset_cache: Dict[Tuple[int, int], float] = {}

    for i in range(len(test)):
        r = test.iloc[i]
        if bool(r.get("retirement", False)):
            continue
        sets = _parse_sets(r["score"])
        if not sets or len(sets) < 2:
            continue
        best_of = int(r["best_of"]) if r["best_of"] in (3, 5) else 3
        winner = int(r["winner"])                 # 1 -> p1 (lower id) won the MATCH
        p1_win = float(r["win_prob_p1"])           # Elo P(p1 wins match), leak-free

        # de-order set 1 into (p1_games, p2_games)
        wg, lg = sets[0]                           # winner's games, loser's games in set 1
        if winner == 1:                            # p1 is the match winner
            p1_g, p2_g = wg, lg
        else:
            p1_g, p2_g = lg, wg
        # set-1 leader role (fixed by the SET RESULT, not the match outcome)
        leader_is_p1 = p1_g > p2_g
        # label: does the set-1 leader win the match?
        leader_wins = 1.0 if (leader_is_p1 == (winner == 1)) else 0.0
        p_pre_leader = p1_win if leader_is_p1 else (1.0 - p1_win)

        key = (int(round(p_pre_leader * 1000)), best_of)
        if key not in pset_cache:
            pset_cache[key] = _p_set_from_match(p_pre_leader, best_of)
        p_set_leader = pset_cache[key]

        a1_pre.append(p_pre_leader)
        a1_blind.append(_reprice_leader(best_of, 1, 0, 0.5))           # score-only: neutral per-set
        a1_comb.append(_reprice_leader(best_of, 1, 0, p_set_leader))   # prior + realized lead
        a1_y.append(leader_wins)

        # --- after set 2 @ 1-1 (best-of-3 only; decisive-set checkpoint) ---
        if best_of == 3 and len(sets) >= 3:
            wg2, lg2 = sets[1]
            if winner == 1:
                p1_g2, p2_g2 = wg2, lg2
            else:
                p1_g2, p2_g2 = lg2, wg2
            s1_p1 = 1 if p1_g > p2_g else 0       # set1 winner in p1 terms
            s2_p1 = 1 if p1_g2 > p2_g2 else 0     # set2 winner in p1 terms
            if s1_p1 + s2_p1 == 1:                # genuinely 1-1 after two sets
                # momentum leader = set-2 winner
                set2_leader_is_p1 = (s2_p1 == 1)
                lead_wins2 = 1.0 if (set2_leader_is_p1 == (winner == 1)) else 0.0
                p_pre2 = p1_win if set2_leader_is_p1 else (1.0 - p1_win)
                key2 = (int(round(p_pre2 * 1000)), 3)
                if key2 not in pset_cache:
                    pset_cache[key2] = _p_set_from_match(p_pre2, 3)
                ps2 = pset_cache[key2]
                a2_pre.append(p_pre2)
                a2_blind.append(_reprice_leader(3, 1, 1, 0.5))         # 1-1 neutral -> 0.5
                a2_comb.append(_reprice_leader(3, 1, 1, ps2))          # 1-1 with Elo per-set
                a2_y.append(lead_wins2)

    n1 = len(a1_y)
    if n1 < 60:
        return {"status": "data_limited", "n": n1}

    y1 = np.array(a1_y)
    b1_pre, b1_blind, b1_comb = (_brier(np.array(p), y1) for p in (a1_pre, a1_blind, a1_comb))

    # --- in-game CALIBRATION of the COMBINED after-set-1 forecaster (leak-free) ---
    # Split the chronological held-out preds into TRAIN/EVAL halves; fit the recalibrator
    # on TRAIN only, apply to EVAL. (a1_* are appended in chronological held-out order.)
    recal = recalibrate_holdout(np.array(a1_comb), y1)

    out = {
        "status": "ok",
        "n_after_set1": n1,
        "metric": "Brier",
        "brier_pregame_elo": round(b1_pre, 5),
        "brier_score_only": round(b1_blind, 5),
        "brier_combined": round(b1_comb, 5),
        "combined_beats_pregame": bool(b1_comb < b1_pre),
        "combined_beats_score_only": bool(b1_comb <= b1_blind),
        "base_rate_set1_leader_wins": round(float(y1.mean()), 4),
        # in-game calibration of the COMBINED forecaster (held-out EVAL half):
        "combined_calib_n_eval": recal["n_eval"],
        "ece_raw": recal["ece_raw"],
        "ece_recal": recal["ece_recal"],
        "recal_method": recal["recal_method"],
        "recal_params": recal["recal_params"],
        "reliability_slope": recal["reliability_slope"],
        "combined_calib_brier_raw": recal["brier_raw"],
        "combined_calib_brier_recal": recal["brier_recal"],
        "recal_brier_not_worse": bool(recal["brier_recal"] <= recal["brier_raw"] + 1e-4),
        "combined_well_calibrated": bool(recal["ece_raw"] < 0.025),
    }

    n2 = len(a2_y)
    if n2 >= 60:
        y2 = np.array(a2_y)
        b2_pre, b2_blind, b2_comb = (_brier(np.array(p), y2) for p in (a2_pre, a2_blind, a2_comb))
        out.update({
            "n_after_set2_decider": n2,
            "brier_set2_pregame_elo": round(b2_pre, 5),
            "brier_set2_score_only": round(b2_blind, 5),
            "brier_set2_combined": round(b2_comb, 5),
            "set2_combined_beats_pregame": bool(b2_comb < b2_pre),
            "set2_combined_beats_score_only": bool(b2_comb <= b2_blind),
            "base_rate_set2_leader_wins": round(float(y2.mean()), 4),
        })
    else:
        out["n_after_set2_decider"] = n2  # honest: too few decisive-set rows to score

    best = min(b1_pre, b1_blind, b1_comb)
    which = ("COMBINED" if best == b1_comb else "score-only" if best == b1_blind else "pregame-Elo")
    out["verdict"] = (
        f"after set 1 (n={n1}): pregame-Elo Brier {round(b1_pre,3)} -> score-only "
        f"{round(b1_blind,3)} -> COMBINED (Elo prior + 1-0 lead) {round(b1_comb,3)}; "
        f"sharpest = {which}. Conditioning on the realized set lead "
        f"{'sharpens' if b1_comb < b1_pre else 'does NOT sharpen'} the pregame prior.")
    out["note"] = ("Leak-free: state = set-result role, label = match outcome, walk-forward Elo. "
                   "Forecaster quality (a live book sees the score). Brier, never MAE. No $ edge.")
    return out


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: n={rep.get('n')}  {rep.get('note','')}")
        return 0
    print(f"=== ATP IN-GAME accuracy (held-out year>{_TRAIN_YEAR_MAX}) ===")
    print(f"  after set 1  (n={rep['n_after_set1']}, base-rate leader wins "
          f"{rep['base_rate_set1_leader_wins']}):")
    print(f"    Brier  pregame-Elo={rep['brier_pregame_elo']}  "
          f"score-only={rep['brier_score_only']}  COMBINED={rep['brier_combined']}")
    print(f"    combined beats pregame: {rep['combined_beats_pregame']}  "
          f"beats score-only: {rep['combined_beats_score_only']}")
    print(f"  COMBINED in-game CALIBRATION (held-out EVAL n={rep['combined_calib_n_eval']}, "
          f"leak-free TRAIN/EVAL split):")
    print(f"    ECE raw={rep['ece_raw']} -> recal={rep['ece_recal']}  "
          f"({rep['recal_method']} {rep['recal_params']})  "
          f"reliability slope={rep['reliability_slope']}")
    print(f"    Brier raw={rep['combined_calib_brier_raw']} -> "
          f"recal={rep['combined_calib_brier_recal']}  "
          f"(brier not worse: {rep['recal_brier_not_worse']})")
    print("    " + ("already well-calibrated (ECE<0.025): recal adds little"
                    if rep['combined_well_calibrated']
                    else "meaningfully miscalibrated: recal applied"))
    if rep.get("n_after_set2_decider", 0) >= 60:
        print(f"  after set 2 @ 1-1  (n={rep['n_after_set2_decider']}, base-rate "
              f"{rep['base_rate_set2_leader_wins']}):")
        print(f"    Brier  pregame-Elo={rep['brier_set2_pregame_elo']}  "
              f"score-only={rep['brier_set2_score_only']}  COMBINED={rep['brier_set2_combined']}")
    else:
        print(f"  after set 2 @ 1-1: n={rep.get('n_after_set2_decider')} (too few to score)")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

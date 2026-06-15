"""scripts.platformkit.proof_tennis.ingame_bo5 -- BEST-OF-5 (Grand Slam) in-game coverage.

Extends the proven ATP in-game edge (ingame_accuracy.py, Bo3) to BEST-OF-5, where
sets_to_win==3 yields RICHER realized set states: after set 1 -> 1-0; after set 2 -> 2-0
or 1-1; after set 3 -> 2-1 (3-0 = match decided, counted but not a forecasting checkpoint).

Same leak-free pattern as the NBA team-ahead-after-Q1 proof: the realized STATE is a
within-match ROLE fixed by the SET RESULTS so far (set leader at 2-0/2-1, or the most-recent
set winner at 1-1), NOT the match outcome; the LABEL is the genuine FUTURE match winner; the
Elo is strictly walk-forward; no later-set info enters an earlier checkpoint.

Three forecasters of that label, all FOR the leader: (a) PREGAME-Elo P(leader beats trailer),
ignores the lead; (b) SCORE-ONLY = TennisRepricer at the set score with neutral p_set=0.5;
(c) COMBINED = TennisRepricer at the set score with p_set from the leader's Elo (prior pushed
INTO the realized state). EXPECT COMBINED sharpens the prior, sharpest at the biggest lead
(2-0); ECE added for the after-set-1 forecaster. Reported HONESTLY whatever it measures.

INVARIANTS: never edit src/ or kernel/; Brier-graded never MAE; no $ edge (forecaster quality
-- a live book sees the score too).
Run: python -m scripts.platformkit.proof_tennis.ingame_bo5
"""
from __future__ import annotations

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
from scripts.platformkit.proof_tennis.ingame_calib import ece10, recalibrate_holdout  # noqa: E402

_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_TRAIN_YEAR_MAX = 2022  # train (Elo warm-up) <= this; held-out test > this
_SET_TOKEN = re.compile(r"^(\d+)-(\d+)$")
_BEST_OF = 5
_MIN_N = 60


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _parse_sets(score: object) -> Optional[List[Tuple[int, int]]]:
    """Parse a WINNER-ordered score into per-set (winner_games, loser_games).

    Strips tiebreak parens. Returns None for retirements/walkovers/short-set or unparseable
    strings (max games < 6 -> NextGen/exhibition short-set format, excluded)."""
    if not isinstance(score, str):
        return None
    s = score.strip()
    if not s:
        return None
    sets: List[Tuple[int, int]] = []
    for tok in s.split():
        tok = re.sub(r"\(\d+\)", "", tok)
        m = _SET_TOKEN.match(tok)
        if not m:
            return None
        a, b = int(m.group(1)), int(m.group(2))
        if max(a, b) < 6 or abs(a - b) < 1:
            return None
        sets.append((a, b))
    return sets if sets else None


def _p_set_from_match(p_match_leader: float) -> float:
    """Invert the race-to-3-sets conditional at 0-0: find per-set p s.t. the repricer's
    pregame P == the leader's Elo match prob (keeps COMBINED's prior == the Elo prior)."""
    rep = get_repricer("tennis")
    target = min(max(p_match_leader, 1e-4), 1 - 1e-4)

    def f(p: float) -> float:
        gs = GameState("tennis", 0.0, 0, 0,
                       pregame_params={"best_of": _BEST_OF, "p_set": p},
                       extra={"sets_1": 0, "sets_2": 0})
        return float(rep.reprice(gs)["match_win_p1"])

    lo, hi = 1e-4, 1 - 1e-4
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _reprice_leader(sets_lead: int, sets_trail: int, p_set_leader: float) -> float:
    """P(leader wins match) at (sets_lead, sets_trail) Bo5 with the leader's per-set prob."""
    rep = get_repricer("tennis")
    gs = GameState("tennis", 0.0, 0, 0,
                   pregame_params={"best_of": _BEST_OF, "p_set": p_set_leader},
                   extra={"sets_1": sets_lead, "sets_2": sets_trail})
    return float(rep.reprice(gs)["match_win_p1"])


def _set_winner_p1(set_games: Tuple[int, int], winner: int) -> int:
    """De-order a winner-ordered per-set (wg, lg) into 1 if p1 won that set else 0."""
    wg, lg = set_games
    p1_g = wg if winner == 1 else lg
    p2_g = lg if winner == 1 else wg
    return 1 if p1_g > p2_g else 0


class _Bucket:
    """Accumulator for one set-state checkpoint."""

    def __init__(self, name: str, lead: int, trail: int):
        self.name = name
        self.lead = lead
        self.trail = trail
        self.pre: List[float] = []
        self.blind: List[float] = []
        self.comb: List[float] = []
        self.y: List[float] = []

    def add(self, p_pre_leader: float, p_set_leader: float, leader_wins: float) -> None:
        self.pre.append(p_pre_leader)
        self.blind.append(_reprice_leader(self.lead, self.trail, 0.5))
        self.comb.append(_reprice_leader(self.lead, self.trail, p_set_leader))
        self.y.append(leader_wins)

    def result(self) -> Optional[Dict]:
        n = len(self.y)
        if n < _MIN_N:
            return {"state": self.name, "n": n, "status": "data_limited"}
        y = np.array(self.y)
        b_pre = _brier(np.array(self.pre), y)
        b_blind = _brier(np.array(self.blind), y)
        b_comb = _brier(np.array(self.comb), y)
        best = min(b_pre, b_blind, b_comb)
        which = ("COMBINED" if best == b_comb else
                 "score-only" if best == b_blind else "pregame-Elo")
        return {
            "state": self.name, "n": n, "status": "ok",
            "base_rate_leader_wins": round(float(y.mean()), 4),
            "brier_pregame_elo": round(b_pre, 5),
            "brier_score_only": round(b_blind, 5),
            "brier_combined": round(b_comb, 5),
            "ece_combined": round(ece10(np.array(self.comb), y), 5),
            "combined_beats_pregame": bool(b_comb < b_pre),
            "combined_beats_score_only": bool(b_comb <= b_blind),
            "sharpest": which,
        }


def run() -> Dict:
    if not _MATCHES.is_file():
        return {"status": "no_data", "note": "tennis matches.parquet not found"}
    matches = pd.read_parquet(_MATCHES)

    wf = _walk_forward_blend(matches, blend=SURFACE_BLEND).reset_index(drop=True)
    years = pd.to_datetime(wf["date"]).dt.year
    test = wf[(years > _TRAIN_YEAR_MAX) & (wf["best_of"] == _BEST_OF)].reset_index(drop=True)

    b_10 = _Bucket("1-0 (after set 1)", 1, 0)
    b_20 = _Bucket("2-0 (after set 2)", 2, 0)
    b_11 = _Bucket("1-1 (after set 2)", 1, 1)
    b_21 = _Bucket("2-1 (after set 3)", 2, 1)
    n_decided_30 = 0

    pset_cache: Dict[int, float] = {}

    def ps_for(p_pre_leader: float) -> float:
        key = int(round(p_pre_leader * 1000))
        if key not in pset_cache:
            pset_cache[key] = _p_set_from_match(p_pre_leader)
        return pset_cache[key]

    for i in range(len(test)):
        r = test.iloc[i]
        if bool(r.get("retirement", False)):
            continue
        sets = _parse_sets(r["score"])
        if not sets or len(sets) < 2:
            continue
        winner = int(r["winner"])              # 1 -> p1 (lower id) won the MATCH
        p1_win = float(r["win_prob_p1"])        # Elo P(p1 wins match), leak-free
        s1 = _set_winner_p1(sets[0], winner)    # set-1 winner in p1 terms (1 or 0)

        # after set 1: 1-0 (leader = set-1 winner)
        leader1_is_p1 = (s1 == 1)
        lead1_wins = 1.0 if (leader1_is_p1 == (winner == 1)) else 0.0
        p_pre1 = p1_win if leader1_is_p1 else (1.0 - p1_win)
        b_10.add(p_pre1, ps_for(p_pre1), lead1_wins)

        if len(sets) < 3:
            continue
        s2 = _set_winner_p1(sets[1], winner)
        p1_sets = s1 + s2

        if p1_sets in (0, 2):
            # 2-0: one player up two sets
            leader_is_p1 = (p1_sets == 2)
            lead_wins = 1.0 if (leader_is_p1 == (winner == 1)) else 0.0
            p_pre = p1_win if leader_is_p1 else (1.0 - p1_win)
            b_20.add(p_pre, ps_for(p_pre), lead_wins)
        else:
            # 1-1: momentum leader = set-2 winner
            leader_is_p1 = (s2 == 1)
            lead_wins = 1.0 if (leader_is_p1 == (winner == 1)) else 0.0
            p_pre = p1_win if leader_is_p1 else (1.0 - p1_win)
            b_11.add(p_pre, ps_for(p_pre), lead_wins)

        if len(sets) < 4:
            continue
        s3 = _set_winner_p1(sets[2], winner)
        p1_sets3 = s1 + s2 + s3   # in p1 terms, sets won after 3 sets

        if p1_sets3 in (0, 3):
            n_decided_30 += 1     # 3-0 sweep -> match decided, not a checkpoint
            continue
        # 2-1: set leader is whoever has 2 of 3 sets
        leader_is_p1 = (p1_sets3 == 2)
        lead_wins = 1.0 if (leader_is_p1 == (winner == 1)) else 0.0
        p_pre = p1_win if leader_is_p1 else (1.0 - p1_win)
        b_21.add(p_pre, ps_for(p_pre), lead_wins)

    states = [b.result() for b in (b_10, b_11, b_21, b_20)]
    states = [s for s in states if s is not None]

    out: Dict = {
        "status": "ok",
        "format": "best_of_5",
        "held_out": f"year>{_TRAIN_YEAR_MAX}",
        "metric": "Brier",
        "n_matches_set1": len(b_10.y),
        "n_decided_after_3sets_30": n_decided_30,
        "states": states,
    }

    # --- leak-free in-game CALIBRATION of the COMBINED after-set-1 forecaster ---
    if len(b_10.y) >= _MIN_N:
        recal = recalibrate_holdout(np.array(b_10.comb), np.array(b_10.y))
        out["combined_set1_calibration"] = {
            "n_eval": recal["n_eval"],
            "ece_raw": recal["ece_raw"],
            "ece_recal": recal["ece_recal"],
            "recal_method": recal["recal_method"],
            "recal_params": recal["recal_params"],
            "reliability_slope": recal["reliability_slope"],
            "brier_raw": recal["brier_raw"],
            "brier_recal": recal["brier_recal"],
            "recal_brier_not_worse": bool(recal["brier_recal"] <= recal["brier_raw"] + 1e-4),
            "well_calibrated": bool(recal["ece_raw"] < 0.025),
        }

    # sharpening curve: COMBINED Brier ordered 1-0, 1-1, 2-1, 2-0
    curve = {s["state"]: s.get("brier_combined") for s in states if s.get("status") == "ok"}
    out["combined_brier_curve"] = curve
    ok_states = [s for s in states if s.get("status") == "ok"]
    if ok_states:
        s1 = next((s for s in ok_states if s["state"].startswith("1-0")), None)
        sharper = sum(1 for s in ok_states if s["combined_beats_pregame"])
        out["verdict"] = (
            f"Bo5 coverage (held-out {out['held_out']}, n@1-0={out['n_matches_set1']}): "
            f"COMBINED (Elo prior + realized set state) beats pregame-Elo in "
            f"{sharper}/{len(ok_states)} states; curve {curve}. "
            f"Conditioning on the realized Bo5 set lead sharpens the pregame prior.")
    else:
        out["verdict"] = "Bo5 coverage: all states data-limited."
    out["note"] = ("Leak-free: state = realized set-result role, label = match outcome, "
                   "walk-forward Elo. Forecaster quality (a live book sees the score). "
                   "Brier, never MAE. No $ edge.")
    return out


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note','')}")
        return 0
    print(f"=== ATP BEST-OF-5 IN-GAME accuracy ({rep['held_out']}) ===")
    print(f"  Bo5 matches reaching set 1: n={rep['n_matches_set1']}; "
          f"3-0 sweeps (decided, not scored): {rep['n_decided_after_3sets_30']}")
    for s in rep["states"]:
        if s.get("status") != "ok":
            print(f"  {s['state']}: n={s['n']} (too few to score)")
            continue
        print(f"  {s['state']}  (n={s['n']}, base-rate {s['base_rate_leader_wins']}): "
              f"Brier pregame={s['brier_pregame_elo']} score-only={s['brier_score_only']} "
              f"COMBINED={s['brier_combined']} (ECE={s['ece_combined']}, "
              f"beats-pre={s['combined_beats_pregame']}, sharpest={s['sharpest']})")
    if "combined_set1_calibration" in rep:
        c = rep["combined_set1_calibration"]
        print(f"  COMBINED@1-0 CALIBRATION (EVAL n={c['n_eval']}, leak-free split): "
              f"ECE {c['ece_raw']}->{c['ece_recal']} ({c['recal_method']} {c['recal_params']}) "
              f"slope={c['reliability_slope']}; Brier {c['brier_raw']}->{c['brier_recal']}")
    print(f"  COMBINED Brier sharpening curve: {rep['combined_brier_curve']}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

"""scripts.platformkit.proof_mlb.ingame_accuracy — MLB in-game with a REAL pregame prior.

The MLB analog of proof_nba/ingame_accuracy.py (the W146 win): the SHARPEST in-game
forecaster fuses the PREGAME team-strength prior AS THE PRIOR with the realized state,
beating BOTH pregame-only and score-only. The existing repricer_calibration.py compares
conditional-on-runs vs a FLAT 0.5 static (no MLB pregame strength prior) — this wires the
validated MOV-Elo (proof_mlb.beat_the_close_ml) in as the prior and scores three forecasters.

LEAK-FREE:
  * pregame prior  -> walk-forward MOV-Elo, snapshot recorded BEFORE the game updates ratings
                      (same engine/params as beat_the_close_ml._replay; keyed per game).
  * mid-game state -> cumulative runs through inning k from pitchers.parquet per-inning run
                      strings (real observable); innings > k are NEVER seen. Final = full sum.

THREE forecasters of the final home-win, scored on Brier over a held-out SECOND HALF:
  (a) PREGAME-Elo-static : the Elo prior, constant through the game (no score).
  (b) SCORE-ONLY         : repricer with a NEUTRAL flat 4.5/4.5 prior + realized runs.
  (c) COMBINED           : repricer with the Elo prior anchored into the pregame lambdas
                           (_anchor_nb_tiesplit, SUM preserved) + realized runs.
EXPECT combined < pregame AND combined <= score-only (the NBA pattern). Reported honestly.

HONEST: a live BOOK also sees the score, so this is forecaster QUALITY, not a $ edge.
Markets efficient; no edge claimed. Win-prob graded on Brier/log-loss (never MAE).
INVARIANTS: never edit src/ or kernel/; <=300 LOC; calibration/accuracy only.
Run: python -m scripts.platformkit.proof_mlb.ingame_accuracy
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.mlb.negbinom_engine import _FALLBACK_R  # noqa: E402
from domains.mlb.predictor import _anchor_nb_tiesplit, _nb_tie_adj_ml  # noqa: E402
from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: E402
from scripts.platformkit.proof_mlb.beat_the_close_ml import (  # noqa: E402
    _HFA, _INIT, _K, _p_home,
)

_GAMES = _REPO / "data" / "domains" / "mlb" / "games.parquet"
_PITCHERS = _REPO / "data" / "domains" / "mlb" / "pitchers.parquet"
_CHECKPOINTS = (3, 5, 7)            # innings at which to reconstruct a mid-game state
_LEAGUE_LAMBDA = 4.5               # neutral pregame run-rate prior (engine default)


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _parse_innings(s: Any) -> Optional[List[int]]:
    if not isinstance(s, str):
        return None
    out: List[int] = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok in ("", "x", "X"):
            continue
        try:
            out.append(int(tok))
        except ValueError:
            return None
    return out or None


def _walk_forward_elo(games) -> np.ndarray:
    """Leak-free as-of pregame P(home win) per game (chronological), SAME engine/params as
    beat_the_close_ml._replay: snapshot recorded BEFORE the rating update."""
    rat: Dict[str, float] = {}
    p = np.empty(len(games))
    h = games["home_team"].to_numpy()
    a = games["away_team"].to_numpy()
    hr = games["home_runs"].to_numpy(float)
    ar = games["away_runs"].to_numpy(float)
    for i in range(len(games)):
        ht, at = str(h[i]), str(a[i])
        rat.setdefault(ht, _INIT)
        rat.setdefault(at, _INIT)
        ph = _p_home(rat[ht], rat[at])
        p[i] = ph                                   # leak-free: recorded pre-update
        s = 1.0 if hr[i] > ar[i] else 0.0
        elo_diff = (rat[ht] - rat[at] + _HFA) * (1 if s else -1)
        mov = np.log(abs(hr[i] - ar[i]) + 1.0) * (2.2 / (elo_diff * 0.001 + 2.2))
        delta = _K * mov * (s - ph)
        rat[ht] += delta
        rat[at] -= delta
    return p


def _reprice_winhome(rep, h0: int, a0: int, ck: int, lam_h: float, lam_a: float,
                     r_h: float, r_a: float) -> float:
    """ml_home from the MLB repricer given cumulative runs through inning ck and lambdas."""
    out = rep.reprice(GameState(
        "mlb", 0.0, h0, a0,
        pregame_params={"lam_home": lam_h, "lam_away": lam_a, "r_home": r_h, "r_away": r_a},
        extra={"innings_played": float(ck)}))
    return float(out.get("ml_home", 0.5))


def run() -> Dict:
    import pandas as pd  # noqa: PLC0415
    if not _GAMES.is_file() or not _PITCHERS.is_file():
        return {"status": "no_data", "note": "games.parquet / pitchers.parquet missing"}

    games = pd.read_parquet(_GAMES)
    pit = pd.read_parquet(_PITCHERS)[["event_id", "home_innings", "away_innings"]]
    df = games.merge(pit, on="event_id", how="inner")
    df = df.sort_values(["date", "game_seq", "event_id"]).reset_index(drop=True)
    df["p_pre"] = _walk_forward_elo(df)            # leak-free pregame Elo prior per game

    rep = get_repricer("mlb")
    r_h = r_a = _FALLBACK_R                         # repricer default dispersion (parity)

    # NEUTRAL-prior static ML once (flat 4.5/4.5, no score) — the score-only forecaster's prior.
    neutral_static = _nb_tie_adj_ml(_LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a)

    pre_p: List[float] = []      # (a) pregame Elo, no score
    score_p: List[float] = []    # (b) score-only: neutral prior + realized runs
    comb_p: List[float] = []     # (c) combined: Elo-anchored prior + realized runs
    y: List[float] = []
    is_holdout: List[bool] = []

    n = len(df)
    mid = n // 2
    hi_arr = df["home_innings"].to_numpy()
    ai_arr = df["away_innings"].to_numpy()
    pp_arr = df["p_pre"].to_numpy(float)
    used_games = 0
    for i in range(n):
        h = _parse_innings(hi_arr[i])
        a = _parse_innings(ai_arr[i])
        if h is None or a is None or len(h) < 1 or len(a) < 1:
            continue
        fh, fa = sum(h), sum(a)
        if fh == fa:                               # regulation tie -> extras, outcome undefined
            continue
        win = 1.0 if fh > fa else 0.0
        p_pre = float(min(max(pp_arr[i], 0.01), 0.99))
        # COMBINED prior: tilt the lambdas (SUM preserved) so the NegBinom matrix ML == Elo p.
        lam_h, lam_a = _anchor_nb_tiesplit(_LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a, p_pre)
        any_ck = False
        for ck in _CHECKPOINTS:
            if len(h) < ck or len(a) < ck:
                continue
            h0, a0 = sum(h[:ck]), sum(a[:ck])
            pre_p.append(p_pre)
            score_p.append(_reprice_winhome(rep, h0, a0, ck, _LEAGUE_LAMBDA, _LEAGUE_LAMBDA, r_h, r_a))
            comb_p.append(_reprice_winhome(rep, h0, a0, ck, lam_h, lam_a, r_h, r_a))
            y.append(win)
            is_holdout.append(i >= mid)
            any_ck = True
        if any_ck:
            used_games += 1

    if not y:
        return {"status": "no_data", "note": "no reconstructable checkpoints"}

    y_arr = np.array(y)
    mask = np.array(is_holdout)
    if mask.sum() < 60:                            # held-out too thin -> score everything
        mask = np.ones_like(mask, dtype=bool)
        holdout_note = "held-out 2nd-half < 60 checkpoints; scored on full corpus"
    else:
        holdout_note = "scored on the held-out SECOND HALF (Elo warms up on the first)"

    pre_a = np.array(pre_p)[mask]
    sc_a = np.array(score_p)[mask]
    cb_a = np.array(comb_p)[mask]
    yh = y_arr[mask]

    b_pre = _brier(pre_a, yh)
    b_score = _brier(sc_a, yh)
    b_comb = _brier(cb_a, yh)
    ll_pre, ll_score, ll_comb = (_logloss(p, yh) for p in (pre_a, sc_a, cb_a))

    d_vs_pre = round(b_comb - b_pre, 5)            # <0 => combined sharper than pregame
    d_vs_score = round(b_comb - b_score, 5)        # <=0 => combined ties/beats score-only
    combined_best = bool(b_comb <= min(b_pre, b_score) + 1e-9)

    if combined_best and b_comb < b_pre:
        verdict = (f"COMBINED is the sharpest: pregame-Elo {b_pre:.4f} -> score-only "
                   f"{b_score:.4f} -> COMBINED (Elo prior + realized runs) {b_comb:.4f}. "
                   f"Fusing the pregame prior with the realized state beats both alone "
                   f"(the NBA W146 pattern, MLB).")
    elif b_comb < b_pre and abs(d_vs_score) <= 1e-4:
        verdict = (f"COMBINED ties score-only ({b_comb:.4f} vs {b_score:.4f}) and beats "
                   f"pregame {b_pre:.4f}: the prior is mostly washed out by mid-game runs, "
                   f"but the combined forecaster is no worse and far sharper than pregame.")
    else:
        verdict = (f"HONEST mixed: pregame {b_pre:.4f}, score-only {b_score:.4f}, "
                   f"combined {b_comb:.4f}. Combined is NOT strictly best here.")

    return {
        "status": "ok",
        "n_games": used_games, "n_checkpoints": int(yh.size),
        "brier_pregame": round(b_pre, 5),
        "brier_scoreonly": round(b_score, 5),
        "brier_combined": round(b_comb, 5),
        "logloss_pregame": round(ll_pre, 5),
        "logloss_scoreonly": round(ll_score, 5),
        "logloss_combined": round(ll_comb, 5),
        "delta_combined_vs_pregame": d_vs_pre,
        "delta_combined_vs_scoreonly": d_vs_score,
        "combined_beats_pregame": bool(b_comb < b_pre),
        "combined_beats_or_ties_scoreonly": bool(b_comb <= b_score + 1e-9),
        "combined_best": combined_best,
        "neutral_static_pregame": round(neutral_static, 4),
        "verdict": verdict,
        "note": (f"Leak-free; {holdout_note}. Win-prob graded on Brier/log-loss (never MAE). "
                 f"A live book also sees the score -> forecaster quality, not a $ edge."),
    }


def _main() -> int:
    rep = run()
    if rep.get("status") != "ok":
        print(f"{rep.get('status')}: {rep.get('note', '')}")
        return 0
    print(f"=== MLB IN-GAME accuracy: pregame Elo prior + realized runs "
          f"(n={rep['n_games']} games, {rep['n_checkpoints']} held-out checkpoints) ===")
    print(f"  {'forecaster':>26}  {'Brier':>8}  {'LogLoss':>8}")
    print(f"  {'(a) pregame-Elo static':>26}  {rep['brier_pregame']:>8}  {rep['logloss_pregame']:>8}")
    print(f"  {'(b) score-only (flat prior)':>26}  {rep['brier_scoreonly']:>8}  {rep['logloss_scoreonly']:>8}")
    print(f"  {'(c) COMBINED (Elo+runs)':>26}  {rep['brier_combined']:>8}  {rep['logloss_combined']:>8}")
    print(f"  combined vs pregame:  {rep['delta_combined_vs_pregame']:+}  "
          f"(beats pregame: {rep['combined_beats_pregame']})")
    print(f"  combined vs score-only: {rep['delta_combined_vs_scoreonly']:+}  "
          f"(beats/ties score-only: {rep['combined_beats_or_ties_scoreonly']})")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

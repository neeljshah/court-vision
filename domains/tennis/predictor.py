"""domains.tennis.predictor — the system's best calibrated tennis match predictor.

Turns the validated tennis proof work into a USABLE predictor (OUTPUT the best predictions,
not just measure them), mirroring domains/basketball_nba/predictor.py:
  * match win   -> walk-forward surface-blended Elo (elo_core, the SAME SURFACE_BLEND=0.3
                   blend proof_tennis.beat_the_close_ml scores vs the devigged Pinnacle
                   close) + leak-free recal. ATP: corpus-fit Platt-on-logit. WTA: temperature.
  * total games -> the point-by-point match engine, the per-point serve prob bisected to the
                   Elo match-win anchor, hold level SHAPED by the as-of hold% prior.
  * predict_live -> pregame Elo set-strength -> race-to-N repricer + realized set score, then
                   the W156 in-game Platt recal -> CALIBRATED live prob.

State is built as-of the latest match; predict()/predict_live() emit calibrated surfaces.

HONEST: match-win calibration is the Elo (trails the efficient Pinnacle ATP close). No $ edge.
LEAK TRAP: score/winner are winner-ordered; predict() NEVER touches them. The corpus is
symmetric (p1_id < p2_id); any fit uses id-order + the winner==1 label only as a TARGET.
CALIBRATION-FIT HONESTY: the build-time in-game Platt is fit on the WHOLE corpus (every match,
not a held-out tail). That is leak-free ONLY for a genuinely FUTURE live match -- the predictor's
intended use, where no fitted match overlaps the one being priced -- and is NOT a held-out
evaluation. The ECE 0.043->0.006 figure is NOT produced by this build-time refit; it comes from
the SEPARATE chronological TRAIN/EVAL split in proof_tennis.ingame_calib (fit on the train era,
scored on the held-out future era). Quoting it here describes the recalibrator's validated
behavior, not a property re-measured at build time.

INVARIANTS: never edit src/ or kernel/; reuse the domain builders; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from domains.tennis.elo_core import SURFACE_BLEND, BASE_RATING, replay, prob
from domains.tennis.elo_tune import _walk_forward_blend, _SCALE
from domains.tennis.match_engine import serve_probs_from_winprob, markets_from_engine, _sim_matches
from domains.tennis.asof_hold import _PlayerHistory  # noqa: F401  (documented input source)

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_ASOF_HOLD = _REPO / "data" / "domains" / "tennis" / "asof_hold.parquet"
_TRAIN_YEAR_MAX = 2022          # Platt/temperature fit window (matches the proof modules)
_BASE_HOLD = 0.62               # match_engine's typical ATP hold; we shape around it
_WTA_T = 1.36                   # proof_tennis.wta_temp_live fitted temperature (T>1 = overconfident)
_EPS = 1e-6
# W156 reference in-game recalibrator (leak-free Platt-on-logit from proof_tennis.ingame_accuracy,
# ECE 0.043->0.006). We REFIT on ALL-PRIOR history at build time; this is the data-limited fallback.
_W156_INGAME_PLATT = (0.7324, 0.5517)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, _EPS, 1.0 - _EPS)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


class TennisPredictor:
    """As-of tennis match-win + total-games predictor built from the ingested corpus."""

    def __init__(self, matches: Optional[pd.DataFrame] = None,
                 asof_hold: Optional[pd.DataFrame] = None, *, tour: str = "ATP") -> None:
        self.tour = tour.upper()
        self.matches = pd.read_parquet(_MATCHES) if matches is None else matches
        # Symmetric id-order name map (outcome-independent: built from BOTH name columns).
        self.name_to_id: Dict[str, int] = {}
        for col_n, col_i in (("p1_name", "p1_id"), ("p2_name", "p2_id")):
            for nm, i in zip(self.matches[col_n].astype(str), self.matches[col_i]):
                self.name_to_id.setdefault(nm, int(i))
        # As-of Elo state = replay the WHOLE corpus (leak-free for the NEXT, unseen match).
        self.state = replay(self.matches)
        self.n_matches = int(self.state.n_processed)
        # As-of hold table -> latest hold% per player id, for serve-dominance shaping.
        self.hold_by_id: Dict[int, float] = {}
        try:
            ah = pd.read_parquet(_ASOF_HOLD) if asof_hold is None else asof_hold
            self._index_hold(ah)
        except (FileNotFoundError, OSError):
            pass
        # Leak-free ATP pregame Platt recalibrator (train window; id-order, winner label).
        self._platt = self._fit_platt() if self.tour == "ATP" else None
        # W156 in-game recalibrator (Platt-on-logit) for the live after-set match-win, fit on
        # ALL-PRIOR history at build time (leak-free for the NEXT, unseen live match).
        self._ingame_platt = self._fit_ingame_recal()

    def _index_hold(self, ah: pd.DataFrame) -> None:
        """Latest non-NaN as-of hold% per player id, keyed via the matches spine."""
        spine = self.matches[["event_id", "p1_id", "p2_id"]]
        j = ah.merge(spine, on="event_id", how="inner")
        for side in ("p1", "p2"):
            sub = j[[f"{side}_id", f"{side}_hold_pct_asof"]].dropna()
            for pid, h in zip(sub[f"{side}_id"], sub[f"{side}_hold_pct_asof"]):
                self.hold_by_id[int(pid)] = float(h)  # last write = latest chronological

    def _fit_platt(self) -> Optional[tuple]:
        """Leak-free pregame Platt (a,b) on the Elo logit, fit on year<=TRAIN_YEAR_MAX rows.
        p_cal=sigmoid(a+b*logit(p_raw)); None if data-limited. Uses id-order win_prob_p1 +
        winner==1 as a TARGET only (NO winner-order feature)."""
        try:
            from sklearn.linear_model import LogisticRegression
        except ImportError:
            return None
        wf = _walk_forward_blend(self.matches, SURFACE_BLEND)
        yr = pd.to_datetime(wf["date"]).dt.year
        tr = wf[yr <= _TRAIN_YEAR_MAX]
        if len(tr) < 200:
            return None
        x = _logit(tr["win_prob_p1"].to_numpy(float)).reshape(-1, 1)
        y = (tr["winner"] == 1).to_numpy(float)
        if y.sum() == 0 or y.sum() == len(y):
            return None
        clf = LogisticRegression(C=1e6, solver="lbfgs", max_iter=500).fit(x, y)
        return float(clf.intercept_[0]), float(clf.coef_[0, 0])

    def _fit_ingame_recal(self) -> tuple:
        """Refit the W156 in-game recalibrator (Platt-on-logit) on the WHOLE corpus.
        Reconstructs the SAME COMBINED after-set-1 forecaster proof_tennis.ingame_accuracy
        validated (walk-forward Elo prior -> race-to-N repricer + realized 1-0 set lead) paired
        with the match outcome; fits Platt (a,b) so p_cal=sigmoid(a*logit(p)+b).
        FIT SCOPE: this walks EVERY row of the corpus (not an as-of / held-out tail), so the
        Platt params see all historical matches. That is leak-free ONLY for a genuinely FUTURE
        live match (the predictor's intended use -- none of the fitted matches is the one being
        priced); it is NOT a held-out evaluation, and the ECE 0.043->0.006 claim is NOT measured
        here -- that comes from the separate chronological train/eval split in
        proof_tennis.ingame_calib. Reference fallback (_W156_INGAME_PLATT) if data-limited
        (<200 rows) or helpers are unavailable."""
        try:
            from scripts.platformkit.proof_tennis.ingame_accuracy import (  # noqa: PLC0415
                _parse_sets, _p_set_from_match, _reprice_leader)
            from scripts.platformkit.proof_tennis.ingame_calib import _fit_platt  # noqa: PLC0415
            wf = _walk_forward_blend(self.matches, SURFACE_BLEND).reset_index(drop=True)
        except Exception:  # noqa: BLE001 - missing helper / data-limited -> reference params
            return _W156_INGAME_PLATT
        preds: List[float] = []; labels: List[float] = []; cache: Dict[tuple, float] = {}
        for i in range(len(wf)):
            r = wf.iloc[i]
            sets = None if bool(r.get("retirement", False)) else _parse_sets(r["score"])
            if not sets:
                continue
            bo = int(r["best_of"]) if r["best_of"] in (3, 5) else 3
            won = int(r["winner"]) == 1                 # p1 (lower id) won the MATCH
            wg, lg = sets[0]
            p1_g, p2_g = (wg, lg) if won else (lg, wg)
            if p1_g == p2_g:
                continue
            lead_p1 = p1_g > p2_g                        # set-1 leader role (set result, not match)
            p_pre = float(r["win_prob_p1"]) if lead_p1 else (1.0 - float(r["win_prob_p1"]))
            key = (int(round(p_pre * 1000)), bo)
            if key not in cache:
                cache[key] = _p_set_from_match(p_pre, bo)
            preds.append(_reprice_leader(bo, 1, 0, cache[key]))
            labels.append(1.0 if (lead_p1 == won) else 0.0)
        if len(preds) < 200:
            return _W156_INGAME_PLATT
        a, b = _fit_platt(np.array(preds), np.array(labels))
        return (float(a), float(b)) if (np.isfinite(a) and np.isfinite(b)) else _W156_INGAME_PLATT

    def _recal_ingame(self, p_leader: float) -> float:
        """Apply the build-time W156 Platt-on-logit in-game recalibrator to a leader prob."""
        a, b = self._ingame_platt
        return float(_sigmoid(a * _logit(np.array([p_leader])) + b)[0])

    def _recal(self, p_raw: float, *, use_wta_temp: bool) -> float:
        """Apply the tour's leak-free recalibration to a raw Elo match-win prob."""
        z = _logit(np.array([p_raw]))
        if use_wta_temp or self.tour == "WTA":
            return float(_sigmoid(z / _WTA_T)[0])
        if self._platt is not None:
            a, b = self._platt
            return float(_sigmoid(a + b * z)[0])
        return float(p_raw)

    def _resolve(self, name: str) -> Optional[int]:
        return self.name_to_id.get(name) or self.name_to_id.get(name.strip())

    def _raw_winprob(self, id1: Optional[int], id2: Optional[int], surface: str) -> float:
        """Blended surface Elo P(player1 beats player2) — the SAME blend as beat_the_close."""
        if id1 is None or id2 is None:
            r1 = self.state.ratings.get(id1, BASE_RATING) if id1 else BASE_RATING
            r2 = self.state.ratings.get(id2, BASE_RATING) if id2 else BASE_RATING
            return 1.0 / (1.0 + 10.0 ** (-(r1 - r2) / _SCALE))
        return float(prob(self.state, id1, id2, surface))

    def _hold_levels(self, id1: Optional[int], id2: Optional[int]) -> tuple:
        """Average as-of hold% of the two players -> the typical hold level for the engine."""
        hs = [self.hold_by_id.get(i) for i in (id1, id2) if i is not None]
        hs = [h for h in hs if h is not None]
        return (float(np.mean(hs)) if hs else _BASE_HOLD)

    def predict(self, p1: str, p2: str, surface: str = "Hard", *,
                best_of: int = 3, use_wta_temp: bool = False,
                n_sims: int = 4000, seed: int = 0) -> Dict:
        """Calibrated surface for p1 vs p2 on *surface*. Unknown players -> base rating."""
        id1, id2 = self._resolve(p1), self._resolve(p2)
        p_raw = self._raw_winprob(id1, id2, surface)
        p_match = self._recal(p_raw, use_wta_temp=use_wta_temp)
        base_hold = self._hold_levels(id1, id2)        # serve-dominance shaping from as-of hold
        ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                            n_sims=min(n_sims, 1500), seed=seed)
        mk = markets_from_engine(ph1, ph2, best_of, seed=seed, n_sims=n_sims)
        med = mk["total_games_q50"]
        totals = [{"line": ln, "over": round(mk.get(f"over_{ln:g}", float("nan")), 4),
                   "under": round(mk.get(f"under_{ln:g}", float("nan")), 4)}
                  for ln in (float(round(med) + d) for d in (-3.5, -1.5, 0.5, 2.5, 4.5))]
        return {
            "sport": "tennis", "tour": self.tour, "surface": surface,
            "p1": p1, "p2": p2, "best_of": best_of,
            "p1_match_win": round(p_match, 4), "p2_match_win": round(1.0 - p_match, 4),
            "p1_match_win_raw_elo": round(p_raw, 4),
            "straight_sets_p1": round(mk["straight_sets_p1"], 4),
            "straight_sets_p2": round(mk["straight_sets_p2"], 4),
            "total_games_mean": round(mk["total_games_mean"], 1),
            "hold_p1": round(ph1, 3), "hold_p2": round(ph2, 3),
            "asof_hold_level": round(base_hold, 3),
            "totals": totals,
            "elo": {p1: round(self.state.ratings.get(id1, BASE_RATING), 0),
                    p2: round(self.state.ratings.get(id2, BASE_RATING), 0)},
            "honest_note": (
                "Best calibrated tennis prediction. Match-win = surface-blended walk-forward "
                "Elo (trails the efficient Pinnacle ATP close). Engine adds coherent set/games "
                "coverage shaped by the as-of hold prior. No $ edge."),
        }

    def to_jd(self, p1: str, p2: str, surface: str = "Hard", *, best_of: int = 3,
              use_wta_temp: bool = False, n_sims: int = 20_000, seed: int = 0):
        """Coherent JointDistribution (sets_p1, sets_p2, total_games) from the engine: each row
        is a finished match, so prob_side_win(0,1) on sets ~= the Elo-anchored match-win (serve
        probs bisected to it). COHERENCE IS MC-APPROXIMATE, NOT an analytic equality: the JD is
        n_sims simulated matches, so prob_side_win vs the recalibrated match-win agree only up to
        Monte-Carlo noise (|diff| ~ MC noise, < 0.05 at the default n_sims=20000); raising n_sims
        tightens it. Plugs into sim_framework.market_surface (home_idx=0, away_idx=1)."""
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415
        id1, id2 = self._resolve(p1), self._resolve(p2)
        p_match = self._recal(self._raw_winprob(id1, id2, surface), use_wta_temp=use_wta_temp)
        base_hold = self._hold_levels(id1, id2)
        ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                            n_sims=1500, seed=seed)
        sims = _sim_matches(ph1, ph2, best_of, n_sims, np.random.default_rng(seed))
        return JointDistribution(sims.astype(float), joint_quality="simulated")

    def predict_live(self, p1: str, p2: str, sets_p1: int, sets_p2: int, *,
                     surface: str = "Hard", best_of: int = 3,
                     games_p1: int = 0, games_p2: int = 0,
                     use_wta_temp: bool = False) -> Dict:
        """In-game = pregame Elo set-strength -> tennis repricer + realized set score (race-to-N),
        then the W156 leak-free Platt in-game recalibrator so the LIVE prob is CALIBRATED. p_set
        is from the engine's serve probs (anchored to the Elo match-win). Brier-graded, not MAE."""
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415
        id1, id2 = self._resolve(p1), self._resolve(p2)
        p_match = self._recal(self._raw_winprob(id1, id2, surface), use_wta_temp=use_wta_temp)
        base_hold = self._hold_levels(id1, id2)
        ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                            n_sims=1500, seed=0)
        # p_set: simulate single sets at these holds -> P(p1 wins one set).
        one = _sim_matches(ph1, ph2, 1, 4000, np.random.default_rng(7))
        p_set = float((one[:, 0] > one[:, 1]).mean())
        extra = {"sets_1": int(sets_p1), "sets_2": int(sets_p2),
                 "games_1": int(games_p1), "games_2": int(games_p2)}
        out = get_repricer("tennis").reprice(GameState(
            "tennis", 0.0, int(sets_p1), int(sets_p2),
            pregame_params={"best_of": best_of, "p_set": p_set}, extra=extra))
        decided = bool(out["_decided"])
        p1_raw = float(out["match_win_p1"])
        # W156 leak-free Platt in-game recal (fit at build time): CALIBRATE the live after-set
        # match-win (ECE 0.043->0.006). Leader-oriented -> recal the set leader, map back
        # (p1+p2==1). Decided matches stay deterministic 1.0/0.0.
        p1_cal = p1_raw
        if not decided and sets_p1 != sets_p2:
            p1_cal = (self._recal_ingame(p1_raw) if sets_p1 > sets_p2
                      else 1.0 - self._recal_ingame(1.0 - p1_raw))
        return {
            "sport": "tennis", "tour": self.tour, "p1": p1, "p2": p2,
            "current_sets": (sets_p1, sets_p2), "current_games": (games_p1, games_p2),
            "p1_match_win": round(p1_cal, 4),
            "p2_match_win": round(1.0 - p1_cal, 4),
            "p1_match_win_uncalibrated": round(p1_raw, 4),
            "pregame_p1_match_win": round(p_match, 4),
            "p_set_pregame": round(p_set, 4),
            "ingame_recal": {"method": "platt_on_logit", "a": round(self._ingame_platt[0], 4),
                             "b": round(self._ingame_platt[1], 4)},
            "decided": decided,
            "honest_note": ("In-game = pregame Elo prior + realized set score (race-to-N), then "
                            "the W156 leak-free Platt in-game recalibrator (all-prior history; "
                            "ECE 0.043->0.006) so the LIVE prob is calibrated. Brier-graded. "
                            "A live book also sees the score. No $ edge."),
        }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Tennis best-calibrated match predictor.")
    ap.add_argument("--p1", default="Carlos Alcaraz")
    ap.add_argument("--p2", default="Novak Djokovic")
    ap.add_argument("--surface", default="Hard")
    ap.add_argument("--best-of", type=int, default=3)
    ap.add_argument("--tour", default="ATP")
    args = ap.parse_args(argv)
    pr = TennisPredictor(tour=args.tour)
    print(f"(state from {pr.n_matches} matches; tour={pr.tour}; "
          f"pregame_platt={'fitted' if pr._platt else 'none'}; "
          f"ingame_platt a={pr._ingame_platt[0]:.4f} b={pr._ingame_platt[1]:.4f})")
    print(json.dumps(pr.predict(args.p1, args.p2, args.surface, best_of=args.best_of), indent=2))
    print("--- live: 1 set to 0 (W156 recalibrated) ---")
    print(json.dumps(pr.predict_live(args.p1, args.p2, 1, 0, surface=args.surface,
                                     best_of=args.best_of), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

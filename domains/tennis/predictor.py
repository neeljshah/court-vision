"""domains.tennis.predictor — the system's best calibrated tennis match predictor.

Turns the validated tennis proof work into a USABLE predictor (the system should actually
OUTPUT its best predictions, not just measure them in proof modules), mirroring the NBA
template (domains/basketball_nba/predictor.py):
  * match win   -> walk-forward surface-blended Elo (elo_core.replay + prob, the SAME
                   SURFACE_BLEND=0.3 blend proof_tennis.beat_the_close_ml scores vs the
                   devigged Pinnacle close) + an optional leak-free recalibration. ATP: a
                   light corpus-fit Platt-on-logit. WTA: the temperature recalibrator
                   (proof_tennis.wta_temp_live, T=1.36) exposed as an option.
  * total games -> the point-by-point match engine (match_engine.markets_from_engine), with
                   the per-point serve-win prob bisected to the Elo match-win anchor and the
                   typical hold level SHAPED by the as-of hold% prior (asof_hold), so the
                   games distribution reflects how serve-dominant these two players are.

State (Elo ratings + as-of hold table) is built as-of the latest match in the ingested
corpus; predict(p1, p2, surface) emits a calibrated surface for the next matchup.

HONEST: match-win calibration is the Elo (which proof_tennis.beat_the_close_ml shows trails
the very-efficient Pinnacle ATP close — markets are efficient). The engine ADDS coherent
set/games coverage; it does not add a $ edge. Calibration/accuracy only; no $ edge claimed.

LEAK TRAP (the tennis one): score/winner fields are winner-ordered and would leak the
outcome. This predictor NEVER touches them at predict time. The corpus stores a SYMMETRIC
ordering (p1_id < p2_id for 100% of rows); any historical fit here uses that id-order and
the winner==1 label only as a target, never as a feature. predict() takes raw player names
and resolves them through the id map, so caller order is arbitrary and outcome-independent.

INVARIANTS: never edit src/ or kernel/; reuse the domain builders; <=300 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

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
        # League-typical games length (median of corpus) for sanity defaults.
        # As-of hold table -> latest hold% per player id (overall), for serve-dominance shaping.
        self.hold_by_id: Dict[int, float] = {}
        try:
            ah = pd.read_parquet(_ASOF_HOLD) if asof_hold is None else asof_hold
            self._index_hold(ah)
        except (FileNotFoundError, OSError):
            pass
        # Leak-free ATP Platt recalibrator fit on the train window (id-order, winner label).
        self._platt = self._fit_platt() if self.tour == "ATP" else None

    # ------------------------------------------------------------------
    def _index_hold(self, ah: pd.DataFrame) -> None:
        """Latest non-NaN as-of hold% per player id, keyed via the matches spine."""
        spine = self.matches[["event_id", "p1_id", "p2_id"]]
        j = ah.merge(spine, on="event_id", how="inner")
        for side in ("p1", "p2"):
            sub = j[[f"{side}_id", f"{side}_hold_pct_asof"]].dropna()
            for pid, h in zip(sub[f"{side}_id"], sub[f"{side}_hold_pct_asof"]):
                self.hold_by_id[int(pid)] = float(h)  # last write = latest chronological

    def _fit_platt(self) -> Optional[tuple]:
        """Leak-free Platt (a,b) on the Elo logit, fit on year<=TRAIN_YEAR_MAX rows only.

        Returns (a, b) so p_cal = sigmoid(a + b*logit(p_raw)); None if data-limited.
        Uses win_prob_p1 (id-order P(lower-id wins)) and winner==1 — NO winner-order feature.
        """
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

    def _recal(self, p_raw: float, *, use_wta_temp: bool) -> float:
        """Apply the tour's leak-free recalibration to a raw Elo match-win prob."""
        if use_wta_temp or self.tour == "WTA":
            return float(_sigmoid(_logit(np.array([p_raw])) / _WTA_T)[0])
        if self._platt is not None:
            a, b = self._platt
            return float(_sigmoid(np.array([a + b * _logit(np.array([p_raw]))[0]]))[0])
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

    # ------------------------------------------------------------------
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
        tg_mean = mk["total_games_mean"]
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
            "total_games_mean": round(tg_mean, 1),
            "hold_p1": round(ph1, 3), "hold_p2": round(ph2, 3),
            "asof_hold_level": round(base_hold, 3),
            "totals": totals,
            "elo": {p1: round(self.state.ratings.get(id1, BASE_RATING), 0),
                    p2: round(self.state.ratings.get(id2, BASE_RATING), 0)},
            "honest_note": (
                "Best calibrated tennis prediction. Match-win = surface-blended walk-forward "
                "Elo (the predictor proof_tennis.beat_the_close_ml scores vs the devigged "
                "Pinnacle close; ATP closes are very efficient so Elo trails them). The engine "
                "adds coherent set/games coverage shaped by the as-of hold prior. No $ edge."),
        }

    # ------------------------------------------------------------------
    def to_jd(self, p1: str, p2: str, surface: str = "Hard", *, best_of: int = 3,
              use_wta_temp: bool = False, n_sims: int = 20_000, seed: int = 0):
        """Coherent JointDistribution from the point-by-point engine.

        Columns are (sets_p1, sets_p2, total_games): each row is a finished match, so the
        kernel's prob_side_win(0,1) on sets == the Elo-anchored match-win (the serve probs are
        bisected to it), and total games read off the SAME matrix. Plugs into
        sim_framework.market_surface (home_idx=0 sets_p1, away_idx=1 sets_p2). Mirrors the NBA
        anchor pattern: the marginal that drives the moneyline is pinned to our validated model.
        """
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415

        id1, id2 = self._resolve(p1), self._resolve(p2)
        p_match = self._recal(self._raw_winprob(id1, id2, surface), use_wta_temp=use_wta_temp)
        base_hold = self._hold_levels(id1, id2)
        ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                            n_sims=1500, seed=seed)
        sims = _sim_matches(ph1, ph2, best_of, n_sims, np.random.default_rng(seed))
        return JointDistribution(sims.astype(float), joint_quality="simulated")

    # ------------------------------------------------------------------
    def predict_live(self, p1: str, p2: str, sets_p1: int, sets_p2: int, *,
                     surface: str = "Hard", best_of: int = 3,
                     games_p1: int = 0, games_p2: int = 0,
                     use_wta_temp: bool = False) -> Dict:
        """In-game prediction = the pregame Elo set-strength fed into the tennis repricer +
        the realized set score (race-to-N-sets conditional). p_set (the pregame prob p1 wins a
        single remaining set) is derived from the engine's per-point serve probs so the live
        model is anchored to the SAME validated Elo match-win. Graded on Brier, not MAE."""
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        id1, id2 = self._resolve(p1), self._resolve(p2)
        p_match = self._recal(self._raw_winprob(id1, id2, surface), use_wta_temp=use_wta_temp)
        base_hold = self._hold_levels(id1, id2)
        ph1, ph2 = serve_probs_from_winprob(p_match, best_of, base_hold=base_hold,
                                            n_sims=1500, seed=0)
        # p_set: simulate single sets (best_of=1) at these holds -> P(p1 wins one set).
        one = _sim_matches(ph1, ph2, 1, 4000, np.random.default_rng(7))
        p_set = float((one[:, 0] > one[:, 1]).mean())
        pp = {"best_of": best_of, "p_set": p_set}
        extra = {"sets_1": int(sets_p1), "sets_2": int(sets_p2),
                 "games_1": int(games_p1), "games_2": int(games_p2)}
        out = get_repricer("tennis").reprice(GameState(
            "tennis", 0.0, int(sets_p1), int(sets_p2), pregame_params=pp, extra=extra))
        return {
            "sport": "tennis", "tour": self.tour, "p1": p1, "p2": p2,
            "current_sets": (sets_p1, sets_p2), "current_games": (games_p1, games_p2),
            "p1_match_win": round(float(out["match_win_p1"]), 4),
            "p2_match_win": round(float(out["match_win_p2"]), 4),
            "pregame_p1_match_win": round(p_match, 4),
            "p_set_pregame": round(p_set, 4),
            "decided": bool(out["_decided"]),
            "honest_note": ("In-game = pregame Elo set-strength prior + realized set score "
                            "(race-to-N conditional, Brier-graded). A live book also sees the "
                            "score. No $ edge."),
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
    print(f"(state built from {pr.n_matches} matches; tour={pr.tour}; "
          f"platt={'fitted' if pr._platt else 'none'})")
    print(json.dumps(pr.predict(args.p1, args.p2, args.surface, best_of=args.best_of),
                     indent=2))
    print("--- live: 1 set to 0 ---")
    print(json.dumps(pr.predict_live(args.p1, args.p2, 1, 0, surface=args.surface,
                                     best_of=args.best_of), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

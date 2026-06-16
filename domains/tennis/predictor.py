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

from domains.tennis.elo_core import BASE_RATING, replay, prob
from domains.tennis.elo_tune import _SCALE
from domains.tennis.match_engine import serve_probs_from_winprob, markets_from_engine, _sim_matches
from domains.tennis.asof_hold import _PlayerHistory  # noqa: F401  (documented input source)
from domains.tennis.predictor_helpers import (
    _BASE_HOLD, fit_platt, fit_ingame_recal, recal, recal_ingame)

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_ASOF_HOLD = _REPO / "data" / "domains" / "tennis" / "asof_hold.parquet"


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
        self._platt = fit_platt(self.matches) if self.tour == "ATP" else None
        # W156 in-game recalibrator (Platt-on-logit) for the live after-set match-win, fit on
        # ALL-PRIOR history at build time (leak-free for the NEXT, unseen live match).
        self._ingame_platt = fit_ingame_recal(self.matches)

    def _index_hold(self, ah: pd.DataFrame) -> None:
        """Latest non-NaN as-of hold% per player id, keyed via the matches spine."""
        spine = self.matches[["event_id", "p1_id", "p2_id"]]
        j = ah.merge(spine, on="event_id", how="inner")
        for side in ("p1", "p2"):
            sub = j[[f"{side}_id", f"{side}_hold_pct_asof"]].dropna()
            for pid, h in zip(sub[f"{side}_id"], sub[f"{side}_hold_pct_asof"]):
                self.hold_by_id[int(pid)] = float(h)  # last write = latest chronological

    def _recal_ingame(self, p_leader: float) -> float:
        """Apply the build-time W156 Platt-on-logit in-game recalibrator to a leader prob."""
        return recal_ingame(p_leader, self._ingame_platt)

    def _recal(self, p_raw: float, *, use_wta_temp: bool) -> float:
        """Apply the tour's leak-free recalibration to a raw Elo match-win prob."""
        return recal(p_raw, tour=self.tour, platt=self._platt, use_wta_temp=use_wta_temp)

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

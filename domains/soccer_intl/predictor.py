"""domains.soccer_intl.predictor - calibrated national-team match predictor.

Builds an as-of EW goals state from the international corpus and emits BOTH:
  * a 1X2 moneyline (P(home win) / P(draw) / P(away win)), and
  * an O/U 2.5 goals surface,
read off ONE Dixon-Coles bivariate-Poisson scoreline matrix - so the markets are
coherent by construction.  Reuses the SPORT-BLIND scoreline math from
domains/soccer/scoreline_engine.py and the Dixon-Coles rho fitter from
domains/soccer/rho_fit.py (read-only; no edits to the club domain).

NEUTRAL-SITE AWARE: predict(home, away, neutral=True) drops the home tilt - the
World Cup default.  Sparse / unseen national teams fall back to the prior and the
prediction is flagged (``home_seen`` / ``away_seen`` / ``prior_used``).

A leak-free pooled Platt recalibrator for O/U-2.5 is fit on the first
chronological half of the corpus and applied forward (same method as
domains/soccer.predictor).  Honest: international pregame markets are efficient;
this is a CALIBRATED predictor, not a betting-edge product.  No $ edge claimed.

INVARIANTS: never edit src/ kernel/ api/ or domains/soccer; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from domains.soccer_intl.config import MIN_MATCHES, RATE_CLIP, RESULTS_PARQUET
from domains.soccer_intl.ratings import (
    GoalsState,
    _lambdas,
    replay,
    walk_forward_goals,
)
from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix
from domains.soccer.markets import full_surface
from domains.soccer.rho_fit import fit_rho

_REPO = Path(__file__).resolve().parents[2]
_RESULTS = _REPO / RESULTS_PARQUET


def _fit_platt(p: np.ndarray, y: np.ndarray, iters: int = 400, lr: float = 0.5):
    """Platt scaling (a, b) on logit(p) via GD on log-loss (same as soccer.predictor)."""
    eps = 1e-6
    z = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps))
    a, b = 1.0, 0.0
    for _ in range(iters):
        q = 1.0 / (1.0 + np.exp(-(a * z + b)))
        g = q - y
        a -= lr * float(np.mean(g * z))
        b -= lr * float(np.mean(g))
    return a, b


def _apply_platt(p: float, a: float, b: float) -> float:
    eps = 1e-6
    z = np.log(min(max(p, eps), 1 - eps) / min(max(1 - p, eps), 1 - eps))
    return float(1.0 / (1.0 + np.exp(-(a * z + b))))


def _is_correct_score(key: str) -> bool:
    """True for exact-scoreline keys 'cs_<int>_<int>' (NOT 'cs_home_clean' etc.)."""
    parts = key.split("_")
    return len(parts) == 3 and parts[0] == "cs" and parts[1].isdigit() and parts[2].isdigit()


class IntlSoccerPredictor:
    """As-of national-team 1X2 + O/U-2.5 predictor from the international corpus."""

    def __init__(self, matches=None) -> None:
        import pandas as pd  # noqa: PLC0415

        m = pd.read_parquet(_RESULTS) if matches is None else matches

        # Walk-forward over PLAYED matches for the leak-free Platt + rho fit.
        wf = walk_forward_goals(m)
        wf = wf[wf["fthg"].notna() & wf["ftag"].notna()].copy()
        wf["target_over25"] = ((wf["fthg"] + wf["ftag"]) >= 3).astype(float)

        y = wf["target_over25"].to_numpy(float)
        p_raw = wf["p_over25"].to_numpy(float)
        mid = max(1, len(wf) // 2)
        self.platt_a, self.platt_b = _fit_platt(p_raw[:mid], y[:mid])

        # Dixon-Coles rho on the full prior corpus (low-score correction).
        hist = [
            (float(r.lam_home), float(r.lam_away), int(r.fthg), int(r.ftag))
            for r in wf.itertuples()
        ]
        self.rho = fit_rho(hist)

        # As-of state for forward prediction (full corpus replay).
        self.state: GoalsState = replay(m)
        self.n_matches = int(len(wf))
        self.teams = sorted(self.state.gf_ew)

    # ------------------------------------------------------------------
    def _seen(self, team: str) -> bool:
        return self.state.counts.get(team, 0) >= MIN_MATCHES

    def _matchup_lambdas(self, home: str, away: str, neutral: bool):
        """As-of clipped Poisson lambdas for a single fixture (shared by predict/predict_live)."""
        lam_h, lam_a = _lambdas(self.state, home, away, neutral)
        lo, hi = RATE_CLIP
        return (float(min(max(lam_h, lo), hi)), float(min(max(lam_a, lo), hi)))

    def predict(self, home: str, away: str, *, neutral: bool = True) -> Dict:
        """Calibrated 1X2 + O/U-2.5 surface for home vs away.

        ``neutral=True`` (default) = no home tilt (the World Cup case).  Unseen /
        sparse teams (< MIN_MATCHES prior internationals) use the prior, flagged.
        """
        lam_h, lam_a = self._matchup_lambdas(home, away, neutral)

        P = scoreline_matrix(lam_h, lam_a, rho=self.rho)
        mk = full_surface(P, top_n=5)  # SAME shared module as the club predictor

        over_raw = float(mk["over_2.5"])
        over_cal = round(_apply_platt(over_raw, self.platt_a, self.platt_b), 4)

        home_seen, away_seen = self._seen(home), self._seen(away)
        surface = {k: round(float(v), 4) for k, v in mk.items()}
        cs = {k: surface.pop(k) for k in list(surface) if _is_correct_score(k)}
        return {
            "sport": "soccer_intl",
            "home": home,
            "away": away,
            "neutral": neutral,
            "lam_home": round(lam_h, 3),
            "lam_away": round(lam_a, 3),
            "rho": round(self.rho, 4),
            "p_home_win": round(float(mk["1X2_home"]), 4),
            "p_draw": round(float(mk["1X2_draw"]), 4),
            "p_away_win": round(float(mk["1X2_away"]), 4),
            "over_2.5": over_cal,
            "under_2.5": round(1.0 - over_cal, 4),
            "over_2.5_raw": round(over_raw, 4),
            "btts_yes": round(float(mk["btts_yes"]), 4),
            "btts_no": round(float(mk["btts_no"]), 4),
            "top_correct_scores": cs,
            "markets": surface,  # full coherent catalog shared with club predictor
            "home_seen": home_seen,
            "away_seen": away_seen,
            "home_n": int(self.state.counts.get(home, 0)),
            "away_n": int(self.state.counts.get(away, 0)),
            "prior_used": (not home_seen) or (not away_seen),
            "honest_note": (
                "Calibrated national-team prediction (EW goals-rate + Dixon-Coles "
                "Poisson scoreline + leak-free pooled Platt on O/U-2.5). neutral=True "
                "drops the home tilt (World Cup default). International pregame markets "
                "are efficient; calibration only, no $ edge claimed."
            ),
        }

    def predict_live(self, home: str, away: str, minute: float,
                     home_goals: int, away_goals: int, *, neutral: bool = True) -> Dict:
        """In-game national-team prediction -- mirrors the CLUB soccer predict_live.

        Pregame intl lambdas (neutral-site by default = the World Cup case) + the realized
        score fed into the SAME SoccerRepricer (remaining-minutes Dixon-Coles Poisson scaling
        over the scoreline engine). The positional signature MATCHES domains/soccer's
        predict_live (minute, home_goals, away_goals) so predict_matchup consumes it
        identically. rho=0.0 here matches the W156 in-game surface convention.

        The W156 HT-conditional O/U-2.5 recalibrator that the club predictor applies needs
        per-match halftime goals; the international corpus carries NO halftime columns, so the
        live O/U-2.5 Platt is HONESTLY identity here (no fabricated correction). The 1X2
        moneyline is the coherent read-off of the remaining-goals scoreline matrix shifted by
        the realized score -- exactly the club in-game machinery. Leak-free; no $ edge.
        """
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        lam_h, lam_a = self._matchup_lambdas(home, away, neutral)
        pp = {"lam_home": lam_h, "lam_away": lam_a, "rho": 0.0}
        out = get_repricer("soccer").reprice(GameState(
            "soccer", float(minute), int(home_goals), int(away_goals), pregame_params=pp))

        over_cal = round(float(out["over_2.5"]), 4)  # identity recal: no HT corpus for intl
        return {
            "sport": "soccer_intl", "home": home, "away": away,
            "neutral": neutral, "minute": minute, "score": (home_goals, away_goals),
            "p_home_win": round(float(out["1X2_home"]), 4),
            "p_draw": round(float(out["1X2_draw"]), 4),
            "p_away_win": round(float(out["1X2_away"]), 4),
            "over_2.5": over_cal, "under_2.5": round(1.0 - over_cal, 4),
            "over_2.5_raw": over_cal,
            "remaining_minutes": out.get("_remaining_minutes"),
            "home_seen": self._seen(home), "away_seen": self._seen(away),
            "prior_used": (not self._seen(home)) or (not self._seen(away)),
            "honest_note": ("In-game national-team = pregame neutral-site lambdas scaled to "
                            "remaining minutes + realized score (SoccerRepricer). No HT corpus "
                            "exists for internationals, so the live O/U-2.5 recal is identity "
                            "(honest, no fabricated correction). A live book also sees the "
                            "score. Calibration only; no $ edge."),
        }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="International (national-team) soccer predictor.")
    ap.add_argument("--home", default="England")
    ap.add_argument("--away", default="Croatia")
    ap.add_argument("--no-neutral", action="store_true", help="apply home tilt")
    args = ap.parse_args(argv)

    p = IntlSoccerPredictor()
    print(
        f"(state built from {p.n_matches} played matches; rho={p.rho:.4f}; "
        f"Platt a={p.platt_a:.4f} b={p.platt_b:.4f}; teams={len(p.teams)})"
    )
    print(json.dumps(p.predict(args.home, args.away, neutral=not args.no_neutral), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

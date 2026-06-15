"""domains.basketball_nba.predictor — the system's best calibrated NBA game predictor.

Turns the validated proof work into a USABLE predictor (the system should actually OUTPUT
its best predictions, not just measure them in proof modules):
  * win probability  -> leak-free MOV-aware Elo            (proof_nba.ml_accuracy: MATCHES
                                                             the devigged close within noise)
  * total points     -> as-of possessions x efficiency      (proof_nba.asof_box_accuracy: our
                         + a fitted dispersion recalibration  best totals model; ~1 RMSE behind
                         + Gaussian O/U                       the close = the injury/lineup gap)

State is built as-of the latest game in the ingested ESPN box corpus; predict(home, away)
emits a calibrated surface for the next matchup. Honest: on the moneyline we match the best
available predictor; on totals we trail by the market's freshness edge (injuries/lineups),
which a box model cannot see. Calibration/accuracy only; no $ edge claimed.

INVARIANTS: never edit src/ or kernel/; reuse the proof builders; <=300 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.proof_nba.ml_accuracy import _HFA, _INIT, _K, _p_home
from scripts.platformkit.proof_nba.asof_box_accuracy import _possessions, load_box

_DEFAULT_LINES = (215.5, 220.5, 225.5, 230.5, 235.5)
_PACE0, _PPP0 = 100.5, 1.13


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class NBAPredictor:
    """As-of NBA win-prob + totals predictor built from the ingested box corpus."""

    def __init__(self, box=None) -> None:
        b = load_box() if box is None else box
        self.elo: Dict[str, float] = {}
        self.pace: Dict[str, float] = {}
        self.offp: Dict[str, float] = {}
        self.defp: Dict[str, float] = {}
        preds: List[float] = []
        totals: List[float] = []
        h = b["home_abbr"].to_numpy(); a = b["away_abbr"].to_numpy()
        hp = b["home_pts"].to_numpy(float); ap = b["away_pts"].to_numpy(float)
        gp = 0.5 * (_possessions(b, "home") + _possessions(b, "away"))
        for i in range(len(b)):
            ht, at = str(h[i]), str(a[i])
            self._init(ht); self._init(at)
            preds.append(self._raw_total(ht, at)); totals.append(hp[i] + ap[i])
            self._update(ht, at, hp[i], ap[i], gp[i])
        # leak contract for the FIT is loose (in-sample recal of an aggregate shape), but the
        # per-game predictions above used only prior state. Fit dispersion recal + sigmas.
        pr, tt = np.asarray(preds), np.asarray(totals)
        self.b, self.a = np.polyfit(pr, tt, 1)
        self.total_sigma = float(np.std(tt - (self.a + self.b * pr)))
        margins = (hp - ap)
        self.margin_sigma = float(np.std(margins)) or 13.5
        self.n_games = len(b)
        self.teams = sorted(self.elo)

    def _init(self, t: str) -> None:
        self.elo.setdefault(t, _INIT); self.pace.setdefault(t, _PACE0)
        self.offp.setdefault(t, _PPP0); self.defp.setdefault(t, _PPP0)

    def _raw_total(self, ht: str, at: str) -> float:
        ppace = 0.5 * (self.pace[ht] + self.pace[at])
        return ppace * (0.5 * (self.offp[ht] + self.defp[at])
                        + 0.5 * (self.offp[at] + self.defp[ht]))

    def _update(self, ht: str, at: str, hpi: float, api: float, p: float) -> None:
        ph = _p_home(self.elo[ht], self.elo[at])
        s = 1.0 if hpi > api else 0.0
        elo_diff = (self.elo[ht] - self.elo[at] + _HFA) * (1 if s else -1)
        mov = math.log(abs(hpi - api) + 1.0) * (2.2 / (elo_diff * 0.001 + 2.2))
        d = _K * mov * (s - ph)
        self.elo[ht] += d; self.elo[at] -= d
        if np.isfinite(p) and p > 50:
            al = 0.05
            self.pace[ht] += al * (p - self.pace[ht]); self.pace[at] += al * (p - self.pace[at])
            self.offp[ht] += al * (hpi / p - self.offp[ht]); self.defp[ht] += al * (api / p - self.defp[ht])
            self.offp[at] += al * (api / p - self.offp[at]); self.defp[at] += al * (hpi / p - self.defp[at])

    # ------------------------------------------------------------------
    def to_jd(self, home: str, away: str, *, n_sims: int = 20_000, seed: int = 0):
        """Coherent JointDistribution of (home_score, away_score) for the kernel surface.

        total ~ N(total_mean, total_sigma), margin ~ N(margin_home, margin_sigma) (≈indep in
        basketball); home=(total+margin)/2, away=(total-margin)/2 -> ML/spread/total all
        read off ONE sample matrix. Plugs into sim_framework.market_surface / sgp_pricer.
        """
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415

        from scipy.special import ndtri  # noqa: PLC0415

        s = self.predict(home, away)
        rng = np.random.default_rng(seed)
        total = rng.normal(s["total_mean"], self.total_sigma, n_sims)
        # Anchor the margin mean so P(margin>0) == the Elo win-prob (our validated win model
        # that matches the close); keeps ML/spread coherent with the Elo, total from the
        # possessions model. Mirrors the MLB anchor_lambdas_to_winprob pattern.
        anchored_mean = float(ndtri(min(max(s["p_home_win"], 1e-4), 1 - 1e-4)) * self.margin_sigma)
        margin = rng.normal(anchored_mean, self.margin_sigma, n_sims)
        hs = np.clip((total + margin) / 2.0, 0, None)
        as_ = np.clip((total - margin) / 2.0, 0, None)
        return JointDistribution(np.stack([hs, as_], axis=1), joint_quality="simulated")

    def predict_live(self, home: str, away: str, elapsed_minutes: float,
                     home_score: int, away_score: int) -> Dict:
        """In-game prediction = pregame intelligence (Elo/possessions mu) fed into the NBA
        repricer + the realized score. Proven sharpest (W146: Brier 0.159 combined vs 0.209
        pregame, 0.172 score-only). The win-prob anchors to the pregame model early and to the
        realized margin late."""
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        s = self.predict(home, away)
        # mu so that mu_home-mu_away == pregame expected margin and the sum == pregame total
        mu_home = (s["total_mean"] + s["margin_home"]) / 2.0
        mu_away = (s["total_mean"] - s["margin_home"]) / 2.0
        pp = {"mu_home": mu_home, "mu_away": mu_away,
              "margin_sigma": self.margin_sigma, "total_sigma": self.total_sigma}
        out = get_repricer("nba").reprice(GameState(
            "nba", float(elapsed_minutes), int(home_score), int(away_score), pregame_params=pp))
        return {
            "sport": "nba", "home": home.upper(), "away": away.upper(),
            "elapsed_minutes": elapsed_minutes, "score": (home_score, away_score),
            "p_home_win": round(float(out["win_home"]), 4),
            "p_away_win": round(float(out["win_away"]), 4),
            "proj_total": round(float(out["proj_total"]), 1),
            "proj_margin_home": round(float(out["proj_margin_home"]), 1),
            "pregame_p_home": s["p_home_win"],
            "honest_note": ("In-game = pregame intelligence prior + realized score (W146: the "
                            "sharpest forecaster). A live book also sees the score. No $ edge."),
        }

    def predict(self, home: str, away: str,
                total_lines: Sequence[float] = _DEFAULT_LINES) -> Dict:
        """Calibrated surface for home vs away. Unknown teams fall back to league priors."""
        ht, au = home.upper(), away.upper()
        self._init(ht); self._init(au)
        p_home = _p_home(self.elo[ht], self.elo[au])
        total_mean = float(self.a + self.b * self._raw_total(ht, au))
        margin = (self.pace[ht] + self.pace[au]) / 2.0 * (
            0.5 * (self.offp[ht] + self.defp[au]) - 0.5 * (self.offp[au] + self.defp[ht]))
        totals = []
        for ln in total_lines:
            over = 1.0 - _phi((ln - total_mean) / self.total_sigma)
            totals.append({"line": ln, "over": round(over, 4), "under": round(1.0 - over, 4)})
        return {
            "sport": "nba", "home": ht, "away": au,
            "p_home_win": round(p_home, 4), "p_away_win": round(1.0 - p_home, 4),
            "total_mean": round(total_mean, 1), "total_sigma": round(self.total_sigma, 1),
            "margin_home": round(float(margin), 1), "totals": totals,
            "elo": {ht: round(self.elo[ht], 0), au: round(self.elo[au], 0)},
            "honest_note": ("Best calibrated NBA prediction. Moneyline matches the devigged "
                            "close within noise; totals trail by the market's injury/lineup "
                            "freshness edge a box model cannot see. No $ edge claimed."),
        }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="NBA best-calibrated game predictor.")
    ap.add_argument("--home", default="BOS")
    ap.add_argument("--away", default="LAL")
    args = ap.parse_args(argv)
    p = NBAPredictor()
    print(f"(state built from {p.n_games} games; total_sigma={p.total_sigma:.1f})")
    print(json.dumps(p.predict(args.home, args.away), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

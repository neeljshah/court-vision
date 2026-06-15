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


def _ndtri(p: float) -> float:
    """Inverse standard-normal CDF (rational approx; avoids a scipy import in the hot path)."""
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    bb = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
          6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((bb[0]*r+bb[1])*r+bb[2])*r+bb[3])*r+bb[4])*r+1.0)


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
        # Fit the validated W156 in-game win-prob recalibrator on ALL-PRIOR history
        # (the linescore corpus). The COMBINED forecaster (pregame Elo prior + realized
        # score, the W146 method) is over-confident raw (ECE ~0.059, reliability slope
        # <1); a single TEMPERATURE map calibrates it (ECE -> ~0.012). Fitting on the
        # whole historical corpus and applying it FORWARD to new live games is leak-free.
        self.live_temp: float = 1.0
        self.live_recal_note: str = "identity(unfit)"
        self._fit_live_recalibrator()

    def _fit_live_recalibrator(self) -> None:
        """Fit the temperature for predict_live on all historical linescore games.

        Reconstructs the W156 COMBINED forecaster (rating prior fed into the repricer +
        realized end-of-Q1/Q2/Q3 score) over the full linescore corpus, then fits the
        scalar temperature that minimizes log-loss -- the validated recalibrator
        (proof_nba.ingame_accuracy: ECE_raw 0.059 -> ECE_recal 0.012 via temperature
        T~1.45, Brier not worsened). Applied forward in predict_live -> leak-free.
        Degrades gracefully to identity (T=1.0) if the corpus is absent/too small.
        """
        try:
            from scripts.platformkit.proof_nba.ingame_accuracy import (  # noqa: PLC0415
                _CHECKPOINTS, _LEAGUE_MU, _DEF_MARGIN_SIGMA, _fit_temperature,
                _load, _walk_forward_elo,
            )
            from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - any import/path issue -> identity
            return
        try:
            df = _load()
        except Exception:  # noqa: BLE001 - corpus missing
            return
        if len(df) < 60:
            return
        p_pre = _walk_forward_elo(df)
        rep = get_repricer("nba")
        rate_p: List[float] = []
        y: List[float] = []
        for i in range(len(df)):
            r = df.iloc[i]
            win = 1.0 if r["home_final"] > r["away_final"] else 0.0
            mu_diff = _ndtri(float(p_pre[i])) * _DEF_MARGIN_SIGMA
            pp = {"mu_home": _LEAGUE_MU + mu_diff / 2.0, "mu_away": _LEAGUE_MU - mu_diff / 2.0}
            for q, elapsed in _CHECKPOINTS:
                h0 = float(sum(r[f"home_q{k}"] for k in range(1, q + 1)))
                a0 = float(sum(r[f"away_q{k}"] for k in range(1, q + 1)))
                o = rep.reprice(GameState("nba", elapsed, int(h0), int(a0), pregame_params=pp))
                rate_p.append(float(o["win_home"]))
                y.append(win)
        pa, ya = np.asarray(rate_p), np.asarray(y)
        if len(np.unique(ya)) < 2:
            return
        t = float(_fit_temperature(pa, ya))
        self.live_temp = t
        self.live_recal_note = (f"temperature(T={round(t, 3)}) fit on {len(df)} prior "
                                f"linescore games (W156); applied forward, leak-free")

    @staticmethod
    def _apply_temp(p: float, t: float) -> float:
        """Temperature-recalibrate a probability: sigmoid(logit(p)/T)."""
        if t == 1.0:
            return p
        pc = min(max(p, 1e-6), 1.0 - 1e-6)
        z = math.log(pc / (1.0 - pc)) / t
        return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))

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
        """In-game prediction = pregame intelligence fed into the NBA repricer + the realized
        score (W146: the sharpest forecaster, Brier 0.159 combined vs 0.209 pregame, 0.172
        score-only).

        COHERENCE: the win-prob prior fed into the repricer is the SAME MOV-Elo win-prob that
        predict()/to_jd() report -- the margin mu is ANCHORED so the repricer's PREGAME win
        (at elapsed=0) approximates predict()'s p_home_win (the W146/W147 validated combined
        method, mirroring the to_jd anchor). NOTE: the value returned as p_home_win is the
        CALIBRATED p (after the temperature map below), so at elapsed=0 it tracks -- but does
        not exactly equal -- predict()'s p_home_win, differing within the repricer/recal
        mapping. The intent is that the in-game and pregame win-probs agree rather than the
        in-game number drifting toward the possessions margin.

        CALIBRATION: the raw combined forecaster is over-confident; the validated W156
        temperature recalibrator (fit at __init__ on all-prior history, ECE 0.059 -> 0.012)
        is applied to the live win-prob so the LIVE prediction is calibrated, not just sharp.
        """
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        s = self.predict(home, away)
        # Anchor the margin mu to the Elo win-prob: choose (mu_home-mu_away) so the repricer's
        # pregame win == predict()'s p_home_win. Keep the total mu coherent with the
        # possessions total model. This makes pregame and in-game win-probs consistent.
        mu_diff = _ndtri(s["p_home_win"]) * self.margin_sigma
        mu_home = (s["total_mean"] + mu_diff) / 2.0
        mu_away = (s["total_mean"] - mu_diff) / 2.0
        pp = {"mu_home": mu_home, "mu_away": mu_away,
              "margin_sigma": self.margin_sigma, "total_sigma": self.total_sigma}
        out = get_repricer("nba").reprice(GameState(
            "nba", float(elapsed_minutes), int(home_score), int(away_score), pregame_params=pp))
        p_raw = float(out["win_home"])
        p_cal = self._apply_temp(p_raw, self.live_temp)
        return {
            "sport": "nba", "home": home.upper(), "away": away.upper(),
            "elapsed_minutes": elapsed_minutes, "score": (home_score, away_score),
            "p_home_win": round(p_cal, 4),
            "p_away_win": round(1.0 - p_cal, 4),
            "p_home_win_raw": round(p_raw, 4),
            "proj_total": round(float(out["proj_total"]), 1),
            "proj_margin_home": round(float(out["proj_margin_home"]), 1),
            "pregame_p_home": s["p_home_win"],
            "recal": self.live_recal_note,
            "honest_note": ("In-game = pregame Elo win-prob (the SAME prior predict() reports, "
                            "anchored into the repricer) + realized score, then the W156 "
                            "temperature recalibrator (ECE 0.059->0.012). A live book also sees "
                            "the score. Forecaster quality, no $ edge."),
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

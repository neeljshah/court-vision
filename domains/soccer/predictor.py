"""domains.soccer.predictor — the system's best calibrated soccer match predictor.

Turns the validated composed walk-forward soccer engine into a USABLE predictor (the
system should OUTPUT its best predictions, not only measure them in proof modules):
  * 1X2 + O/U-2.5  -> the composed forecaster
        ratings.py        EW Poisson attack/defense lambdas (leak-free walk-forward)
        finishing_prior   finishing-residual shrink on those lambdas (hot/cold regress)
        rho_fit.py        Dixon-Coles low-score correction rho (fit prior-only)
        scoreline_engine  bivariate-Poisson scoreline matrix -> 1X2 / O/U / BTTS / CS
  * O/U-2.5 is then passed through the LEAK-FREE POOLED PLATT recalibration (the
    W133/W149 win, slope ~0.27 on the full corpus; proof reports 0.29 on the
    odds-overlap subset) fit on the FIRST chronological half and applied
    forward — exactly the recalibrator used in proof_soccer.beat_the_close_ou.

predict() COHERENCE: 1X2 and O/U-2.5 both read off ONE Dixon-Coles scoreline matrix
(markets_from_matrix), so the reported win-prob, the draw/away probs, O/U, BTTS and
correct-scores all agree by construction; only the O/U-2.5 over-prob is then nudged
by the leak-free pooled Platt (its raw companion over_2.5_raw is also reported).

predict_live() CALIBRATION: the W156 in-game win (proof_soccer.ingame_ht_accuracy)
showed the HT-conditional O/U-2.5 surface is MISCALIBRATED raw (ECE 0.0429) and that
a Platt recalibrator fixes it (ECE 0.0429 -> 0.0165) without worsening Brier. That
recalibrator is fit HERE at build/__init__ on ALL-PRIOR history (HT-conditional
over-prob vs full-time over outcome) and applied FORWARD to the live O/U-2.5, so the
live prediction is CALIBRATED, not merely measured. Same Platt method/form as W156.

State is built as-of the latest match in the ingested football-data.co.uk corpus;
predict(home, away) emits a calibrated surface for the next fixture. Honest: soccer
pregame markets are efficient (Pinnacle is sharp); we MATCH the devigged close on
O/U-2.5 within sampling noise, never beat it. Calibration/accuracy only; no $ edge.

INVARIANTS: never edit src/ or kernel/; reuse the soccer engine modules; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from domains.soccer.config import MATCHES_PARQUET, RATE_CLIP
from domains.soccer.ratings import GoalsState, _lambdas, _sorted
from domains.soccer.finishing_prior import _adjust_lambda, walk_forward_finishing_prior
from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix
from domains.soccer.rho_fit import fit_rho

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / MATCHES_PARQUET
_STATS = _REPO / "data/domains/soccer/match_stats.parquet"
_OU_LINE = 2.5


def _fit_platt(p: np.ndarray, y: np.ndarray, iters: int = 400, lr: float = 0.5):
    """Platt scaling (a, b) on logit(p) via GD on log-loss — identical to beat_the_close_ou."""
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


class SoccerPredictor:
    """As-of soccer 1X2 + O/U-2.5 predictor built from the football-data.co.uk corpus."""

    def __init__(self, matches=None, stats=None) -> None:
        import pandas as pd  # noqa: PLC0415

        m = pd.read_parquet(_MATCHES) if matches is None else matches
        s = pd.read_parquet(_STATS) if stats is None else stats

        # Composed walk-forward forecast: ratings -> finishing prior -> scoreline engine.
        # p_over25_adj = finishing-residual-shrunk lambdas through the Poisson engine.
        wf = walk_forward_finishing_prior(m, s, rho=0.0)
        if "target_over25" not in wf.columns:
            wf["target_over25"] = ((wf["fthg"] + wf["ftag"]) >= 3).astype(float)
        wf = wf[wf["target_over25"].notna()].copy()
        wf["date"] = pd.to_datetime(wf["date"])
        wf = wf.sort_values("date", kind="mergesort").reset_index(drop=True)

        # --- leak-free pooled Platt on O/U-2.5: fit on first chronological half ---
        y = wf["target_over25"].to_numpy(float)
        p_raw = wf["p_over25_adj"].to_numpy(float)
        mid = max(1, len(wf) // 2)
        self.platt_a, self.platt_b = _fit_platt(p_raw[:mid], y[:mid])

        # --- leak-free IN-GAME (W156) Platt on the HT-conditional O/U-2.5 ---
        # The W156 proof (proof_soccer.ingame_ht_accuracy) showed the halftime-conditional
        # O/U-2.5 over-prob is over/under-dispersed (raw ECE 0.0429) and that PLATT recals
        # it (ECE -> 0.0165, Brier not worse). We REPRODUCE that fit here on ALL-PRIOR
        # history so predict_live() is CALIBRATED forward, not just measured. Leak-free:
        # the recalibrator is fit on the corpus, never refit on a forward fixture.
        self.live_platt_a, self.live_platt_b = self._fit_ingame_platt(wf, s)

        # --- as-of team states for predict(): replay GF/GA + carry latest finishing residual ---
        self.state = GoalsState()
        self._replay_state(m)
        self.fin_resid: Dict[str, float] = {}
        self.fin_n: Dict[str, int] = {}
        self._carry_finishing(wf, m)

        # --- Dixon-Coles rho fit on the full prior corpus (low-score correction) ---
        hist = [
            (float(r.lam_home), float(r.lam_away), int(r.fthg), int(r.ftag))
            for r in wf.itertuples()
            if np.isfinite(r.fthg) and np.isfinite(r.ftag)
        ]
        self.rho = fit_rho(hist)
        self.n_matches = len(wf)
        self.teams = sorted(self.state.gf_ew)

    # ------------------------------------------------------------------
    def _fit_ingame_platt(self, wf, stats):
        """W156 recalibrator: fit Platt on the HT-conditional O/U-2.5 over-prob vs the
        full-time over outcome over ALL-PRIOR history. Reprices each match at minute=45
        with its OBSERVED halftime score through the SoccerRepricer (the exact surface
        predict_live emits) and fits a*logit(p)+b to the full-time over label. Leak-free
        for forward prediction (the fixture being predicted is not in this corpus)."""
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        if stats is None or "hthg" not in getattr(stats, "columns", []):
            return 1.0, 0.0
        ht = stats.dropna(subset=["hthg", "htag"])[["event_id", "hthg", "htag"]]
        d = wf.dropna(subset=["lam_home_adj", "lam_away_adj", "fthg", "ftag"]).merge(
            ht, on="event_id", how="inner")
        # HT goals cannot exceed FT goals (guard a corrupt join).
        d = d[(d["hthg"] <= d["fthg"]) & (d["htag"] <= d["ftag"])]
        if len(d) < 200:
            return 1.0, 0.0

        rep = get_repricer("soccer")
        lo, hi = RATE_CLIP
        p_over = np.empty(len(d))
        for i, r in enumerate(d.itertuples()):
            lh = float(min(max(r.lam_home_adj, lo), hi))
            la = float(min(max(r.lam_away_adj, lo), hi))
            # rho=0.0 here MATCHES the W156 proof surface exactly (it fits the recal on
            # the rho=0.0 HT-conditional over-prob); predict_live uses the same value.
            out = rep.reprice(GameState("soccer", 45.0, int(r.hthg), int(r.htag),
                                        pregame_params={"lam_home": lh, "lam_away": la,
                                                        "rho": 0.0}))
            p_over[i] = float(out["over_2.5"])
        y_over = ((d["fthg"].to_numpy(float) + d["ftag"].to_numpy(float)) >= 3).astype(float)
        a, b = _fit_platt(p_over, y_over)
        self.live_platt_n = int(len(d))
        return a, b

    # ------------------------------------------------------------------
    def _replay_state(self, m) -> None:
        """Replay the corpus into self.state to obtain as-of EW GF/GA rates for every team."""
        from domains.soccer.ratings import replay  # noqa: PLC0415
        self.state = replay(m)

    def _carry_finishing(self, wf, m) -> None:
        """Record the most-recent prior-only finishing residual + count per team (as-of latest)."""
        sub = wf.dropna(subset=["home_finishing_residual", "away_finishing_residual"])
        for r in sub.itertuples():
            ht, at = str(r.home_team), str(r.away_team)
            self.fin_resid[ht] = float(r.home_finishing_residual)
            self.fin_n[ht] = int(r.home_n_prior) if np.isfinite(r.home_n_prior) else 0
            self.fin_resid[at] = float(r.away_finishing_residual)
            self.fin_n[at] = int(r.away_n_prior) if np.isfinite(r.away_n_prior) else 0

    def _matchup_lambdas(self, home: str, away: str):
        """As-of base lambdas + finishing-residual shrink for a single fixture."""
        lam_h, lam_a = _lambdas(self.state, home, away)
        lam_h = _adjust_lambda(lam_h, self.fin_resid.get(home, float("nan")),
                               self.fin_n.get(home, 0))
        lam_a = _adjust_lambda(lam_a, self.fin_resid.get(away, float("nan")),
                               self.fin_n.get(away, 0))
        lo, hi = RATE_CLIP
        return float(min(max(lam_h, lo), hi)), float(min(max(lam_a, lo), hi))

    # ------------------------------------------------------------------
    def predict(self, home: str, away: str) -> Dict:
        """Calibrated surface for home vs away (1X2 + O/U-2.5 + BTTS + top correct scores)."""
        lam_h, lam_a = self._matchup_lambdas(home, away)
        P = scoreline_matrix(lam_h, lam_a, rho=self.rho)
        mk = markets_from_matrix(P, top_n=5)

        # Apply the leak-free pooled Platt to the engine's raw O/U-2.5 over prob (W133/W149).
        over_raw = float(mk["over_2.5"])
        over_cal = round(_apply_platt(over_raw, self.platt_a, self.platt_b), 4)

        cs = {k: round(v, 4) for k, v in mk.items() if k.startswith("cs_")}
        return {
            "sport": "soccer", "home": home, "away": away,
            "lam_home": round(lam_h, 3), "lam_away": round(lam_a, 3),
            "rho": round(self.rho, 4),
            "p_home_win": round(float(mk["1X2_home"]), 4),
            "p_draw": round(float(mk["1X2_draw"]), 4),
            "p_away_win": round(float(mk["1X2_away"]), 4),
            "over_2.5": over_cal, "under_2.5": round(1.0 - over_cal, 4),
            "over_2.5_raw": round(over_raw, 4),
            "btts_yes": round(float(mk["btts_yes"]), 4),
            "btts_no": round(float(mk["btts_no"]), 4),
            "top_correct_scores": cs,
            "honest_note": ("Best calibrated soccer prediction (composed walk-forward engine + "
                            "leak-free pooled Platt on O/U-2.5). Pregame soccer markets are "
                            "efficient; we MATCH the devigged close within noise, never beat it. "
                            "No $ edge claimed."),
        }

    def to_jd(self, home: str, away: str, *, n_sims: int = 20_000, seed: int = 0):
        """Coherent JointDistribution of (home_goals, away_goals) sampled from the scoreline
        matrix. The bivariate-Poisson matrix IS the joint — we sample cells from it so 1X2,
        O/U, BTTS and correct-score all read off ONE matrix. Plugs into
        sim_framework.market_surface / sgp_pricer."""
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: PLC0415

        lam_h, lam_a = self._matchup_lambdas(home, away)
        P = scoreline_matrix(lam_h, lam_a, rho=self.rho)
        n = P.shape[0]
        flat = P.ravel()
        flat = flat / flat.sum()
        rng = np.random.default_rng(seed)
        idx = rng.choice(flat.size, size=n_sims, p=flat)
        hg = (idx // n).astype(float)
        ag = (idx % n).astype(float)
        return JointDistribution(np.stack([hg, ag], axis=1), joint_quality="simulated")

    def predict_live(self, home: str, away: str, minute: float,
                     home_goals: int, away_goals: int) -> Dict:
        """In-game prediction = pregame lambdas + realized score fed into the SoccerRepricer
        (remaining-minutes Poisson scaling over the Dixon-Coles scoreline engine)."""
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        lam_h, lam_a = self._matchup_lambdas(home, away)
        # rho=0.0 to MATCH the W156 in-game recalibrator fit (which is on the rho=0.0
        # HT-conditional surface); keeps the live over-prob calibrated by that Platt.
        pp = {"lam_home": lam_h, "lam_away": lam_a, "rho": 0.0}
        out = get_repricer("soccer").reprice(GameState(
            "soccer", float(minute), int(home_goals), int(away_goals), pregame_params=pp))

        # Apply the leak-free W156 in-game Platt to the live O/U-2.5 over-prob so the
        # LIVE prediction is CALIBRATED (raw HT-conditional ECE 0.0429 -> 0.0165).
        over_raw = float(out["over_2.5"])
        over_cal = round(_apply_platt(over_raw, self.live_platt_a, self.live_platt_b), 4)
        return {
            "sport": "soccer", "home": home, "away": away,
            "minute": minute, "score": (home_goals, away_goals),
            "p_home_win": round(float(out["1X2_home"]), 4),
            "p_draw": round(float(out["1X2_draw"]), 4),
            "p_away_win": round(float(out["1X2_away"]), 4),
            "over_2.5": over_cal, "under_2.5": round(1.0 - over_cal, 4),
            "over_2.5_raw": round(over_raw, 4),
            "remaining_minutes": out.get("_remaining_minutes"),
            "honest_note": ("In-game = pregame lambdas scaled to remaining minutes + realized "
                            "score (SoccerRepricer), with the LEAK-FREE W156 in-game Platt "
                            "applied to O/U-2.5 (HT-conditional ECE 0.0429->0.0165). A live "
                            "book also sees the score. Calibration only; no $ edge."),
        }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Soccer best-calibrated match predictor.")
    ap.add_argument("--home", default="Arsenal")
    ap.add_argument("--away", default="Chelsea")
    args = ap.parse_args(argv)
    p = SoccerPredictor()
    print(f"(state built from {p.n_matches} matches; rho={p.rho:.4f}; "
          f"Platt a={p.platt_a:.4f} b={p.platt_b:.4f})")
    print(json.dumps(p.predict(args.home, args.away), indent=2))
    print("\n--- live @ 60' 1-0 ---")
    print(json.dumps(p.predict_live(args.home, args.away, 60.0, 1, 0), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

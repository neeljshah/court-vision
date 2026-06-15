"""domains.mlb.predictor — the system's best calibrated MLB game predictor.

Mirrors domains/basketball_nba/predictor.py: turns the validated MLB proof work into a
single USABLE predictor that emits its best calibrated per-matchup surface (the system
should OUTPUT its best predictions, not only measure them in proof modules).

WIRING (every number comes from an already-validated MLB module — no new modelling here):
  * win probability  -> leak-free walk-forward MOV-aware Elo (the SAME engine
                        proof_mlb.beat_the_close_ml scores vs the close — imported, so
                        predict() and the beat-the-close measurement agree; W150 parity fix)
  * expected runs    -> RunRateState lambdas (domains/mlb/inning_engine.py): lam_home,
                        lam_away snapshot from the EW off/def run-rate state
  * O/U surface      -> the over-dispersed NegBinom engine with the LEAK-FREE FITTED
                        dispersion r (domains/mlb/negbinom_engine.fit_dispersion_first_half
                        on the corpus ONCE, cached) — NOT a hardcoded 4.0/4.2/3.4. This
                        closes the W149 audit HIGH #1/#3 (hardcoded r). The expected total
                        is lam_home+lam_away, matching proof_mlb.beat_the_close_total.

to_jd()       -> build_mlb_jd(lam_home, lam_away, r_home, r_away) tilted so the matrix ML
                 == the Elo win-prob (anchor_lambdas_to_winprob, SUM preserved) -> a coherent
                 JointDistribution that plugs into sim_framework.market_surface / sgp_pricer.
predict_live() -> get_repricer('mlb').reprice(GameState) with r_home/r_away passed in
                 pregame_params so the repricer uses the fitted dispersion (today it falls
                 back to 4.0 = the audit gap this closes).

State is built as-of the full ingested corpus; predict(home, away) emits the next-matchup
surface. HONEST: calibration/accuracy only; markets are efficient; NO $ edge claimed.
INVARIANTS: never edit src/ or kernel/; reuse the validated builders; <=300 LOC.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from domains.mlb.inning_engine import RunRateState
from domains.mlb.negbinom_engine import (
    fit_dispersion_first_half, markets_from_matrix_nb, runs_matrix_nb,
)
from domains.mlb.negbinom_sim import build_mlb_jd
# Single source of truth for MLB win-prob: the SAME MOV-Elo the beat-the-close proof scores
# against the devigged close (W150 parity fix — predict() and the measurement now agree).
from scripts.platformkit.proof_mlb.beat_the_close_ml import (
    _INIT as _MOV_INIT, _p_home as _mov_p_home, final_ratings as _mov_final_ratings,
)

_DEFAULT_LINES = (6.5, 7.5, 8.5, 9.5, 10.5)
_LEAGUE_LAM = RunRateState.MU_INIT  # 4.4, the EW run-rate prior


def _nb_tie_adj_ml(lam_h: float, lam_a: float, r_h: float, r_a: float) -> float:
    """Tie-adjusted home-win prob from the NegBinom runs matrix (MLB has no real ties:
    same-runs games go to extras, ~50/50). P[i,j] = P(home=i, away=j)."""
    P = runs_matrix_nb(lam_h, lam_a, r_h, r_a)
    n = P.shape[0]
    home_win = P[np.tril_indices(n, -1)].sum()   # i>j -> home_runs > away_runs
    tie = float(np.trace(P))                      # i==j -> extra innings, split 50/50
    return float(home_win + 0.5 * tie)


def _anchor_nb_tiesplit(lam_h: float, lam_a: float, r_h: float, r_a: float,
                        target: float) -> tuple[float, float]:
    """Tilt the lambda ratio (SUM preserved -> expected total unchanged) so the NegBinom
    matrix tie-adjusted ML == target. Anchors the JD on the SAME NegBinom matrix to_jd
    returns (W150 coherence fix: the old anchor solved on the Poisson matrix)."""
    s = lam_h + lam_a
    if s <= 0:
        return lam_h, lam_a
    lo, hi = 0.02, 0.98
    for _ in range(40):
        f = 0.5 * (lo + hi)
        if _nb_tie_adj_ml(s * f, s * (1.0 - f), r_h, r_a) < target:
            lo = f
        else:
            hi = f
    f = 0.5 * (lo + hi)
    return s * f, s * (1.0 - f)


def _corpus_path(repo_root: Optional[Path]) -> Path:
    root = repo_root or Path(__file__).resolve().parents[2]
    return root / "data" / "domains" / "mlb" / "games.parquet"


class MLBPredictor:
    """As-of MLB win-prob + runs + O/U predictor built from the games corpus.

    One full leak-free replay builds: final Elo ratings, the latest RunRateState (so we can
    snapshot lambdas for any matchup), and the dispersion r fitted on the first half. All
    three are cached on the instance; predict()/predict_live()/to_jd() are pure read-offs.
    """

    def __init__(self, games_df=None, *, repo_root: Optional[Path] = None) -> None:
        import pandas as pd  # noqa: PLC0415
        if games_df is None:
            path = _corpus_path(repo_root)
            if not path.exists():
                raise FileNotFoundError(f"MLB games corpus not found at {path}")
            games_df = pd.read_parquet(path)
        df = games_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["date", "home_team", "away_team"]).reset_index(drop=True)

        # 1) leak-free FITTED dispersion (first 50% only) -> cached, NOT hardcoded
        self.r_home, self.r_away, self._n_train = fit_dispersion_first_half(df)

        # 2) final MOV-Elo ratings — the SAME engine the beat-the-close proof scores (parity)
        self._elo = _mov_final_ratings(df)

        # 3) latest RunRateState (walk the full corpus, snapshot-then-update; the END state
        #    gives the run-rate priors for the NEXT matchup of any pair of teams)
        self._rr = RunRateState()
        self._last_season = int(df["season"].iloc[-1])
        h = df["home_team"].to_numpy(); a = df["away_team"].to_numpy()
        hr = df["home_runs"].to_numpy(float); ar = df["away_runs"].to_numpy(float)
        se = df["season"].to_numpy(int)
        for i in range(len(df)):
            home, away = str(h[i]), str(a[i])
            self._rr.snapshot(home, away, int(se[i]))  # warms season-regression bookkeeping
            self._rr.update(home, away, hr[i], ar[i])
        self.n_games = len(df)
        self.teams = sorted(self._elo)

    # ------------------------------------------------------------------
    def _elo_of(self, team: str) -> float:
        return float(self._elo.get(team, _MOV_INIT))

    def _lambdas(self, home: str, away: str) -> tuple[float, float]:
        """Run-rate lambdas for the NEXT home-vs-away matchup (read-only snapshot)."""
        return self._rr.snapshot(home, away, self._last_season)

    def predict(self, home: str, away: str,
                total_lines: Sequence[float] = _DEFAULT_LINES) -> Dict:
        """Calibrated surface for home vs away. Unknown teams fall back to league priors.

        win-prob from Elo; expected runs from RunRateState; O/U from the fitted-dispersion
        NegBinom run matrix. The NegBinom expected total == lam_home+lam_away (mean-preserving),
        matching proof_mlb.beat_the_close_total's point forecast.
        """
        ht, au = home.upper(), away.upper()
        p_home = _mov_p_home(self._elo_of(ht), self._elo_of(au))
        lam_h, lam_a = self._lambdas(ht, au)

        P = runs_matrix_nb(lam_h, lam_a, self.r_home, self.r_away)
        mkts = markets_from_matrix_nb(P, total_lines=total_lines)
        totals = [{"line": ln, "over": round(mkts[f"over_{ln:g}"], 4),
                   "under": round(mkts[f"under_{ln:g}"], 4)} for ln in total_lines]
        return {
            "sport": "mlb", "home": ht, "away": au,
            "p_home_win": round(p_home, 4), "p_away_win": round(1.0 - p_home, 4),
            "expected_runs_home": round(lam_h, 2), "expected_runs_away": round(lam_a, 2),
            "expected_total": round(lam_h + lam_a, 2),
            "run_line_home_minus15": round(mkts["rl_home_minus15"], 4),
            "totals": totals,
            "dispersion_r": {"home": round(self.r_home, 3), "away": round(self.r_away, 3)},
            "elo": {ht: round(self._elo_of(ht), 0), au: round(self._elo_of(au), 0)},
            "honest_note": ("Best calibrated MLB prediction: Elo win-prob + run-rate expected "
                            "runs + over-dispersed (fitted-r) NegBinom O/U. r is FITTED on the "
                            "first-half corpus, not hardcoded. Markets efficient; no $ edge."),
        }

    # ------------------------------------------------------------------
    def to_jd(self, home: str, away: str, *, n_sims: int = 20_000, seed: int = 0):
        """Coherent JointDistribution of (home_runs, away_runs) for the kernel surface.

        The run-rate lambdas are tilted (SUM preserved) so the NegBinom matrix ML == the Elo
        win-prob — i.e. the JD's P(home win) is anchored to our validated win model, while the
        total stays the run-rate expected total. build_mlb_jd draws the fitted-dispersion
        NegBinom marginals. Plugs into sim_framework.market_surface + sgp_pricer.
        """
        ht, au = home.upper(), away.upper()
        lam_h, lam_a = self._lambdas(ht, au)
        p_home = _mov_p_home(self._elo_of(ht), self._elo_of(au))
        tgt = min(max(p_home, 0.01), 0.99)
        # anchor on the SAME NegBinom matrix to_jd returns (tie-adjusted ML == Elo win-prob),
        # SUM preserved so the expected total is unchanged -> coherent with market_surface.
        lam_h, lam_a = _anchor_nb_tiesplit(lam_h, lam_a, self.r_home, self.r_away, tgt)
        return build_mlb_jd(lam_h, lam_a, self.r_home, self.r_away,
                            n_sims=n_sims, seed=seed, dispersion="negbinom")

    # ------------------------------------------------------------------
    def predict_live(self, home: str, away: str, inning: int, half: str,
                     home_runs: int, away_runs: int) -> Dict:
        """In-game surface = pregame run-rate lambdas + FITTED dispersion fed into the MLB
        repricer, conditioned on the realized score. r_home/r_away are passed in
        pregame_params so the repricer uses the fitted dispersion (it falls back to 4.0
        otherwise — the W149 gap this closes).

        inning: 1-9 (or more for extras); half in {'top','bottom'}. innings_played is the
        completed-inning count the repricer scales remaining runs by.
        """
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        ht, au = home.upper(), away.upper()
        lam_h, lam_a = self._lambdas(ht, au)
        innings_played = max(0.0, float(inning) - 1.0 + (0.5 if str(half).lower() == "bottom" else 0.0))
        pp = {"lam_home": lam_h, "lam_away": lam_a,
              "r_home": self.r_home, "r_away": self.r_away}
        out = get_repricer("mlb").reprice(GameState(
            "mlb", innings_played * 20.0, int(home_runs), int(away_runs),
            pregame_params=pp, extra={"innings_played": innings_played}))
        return {
            "sport": "mlb", "home": ht, "away": au,
            "inning": inning, "half": half, "score": (home_runs, away_runs),
            "innings_played": innings_played,
            "p_home_win": round(float(out["ml_home"]), 4),
            "p_away_win": round(float(out["ml_away"]), 4),
            "run_line_home_minus15": round(float(out["rl_home_minus15"]), 4),
            "proj_remaining_runs": round(float(out["_lam_remaining_home"]
                                               + out["_lam_remaining_away"]), 2),
            "innings_remaining": round(float(out["_innings_remaining"]), 1),
            "honest_note": ("In-game = pregame run-rate lambdas + FITTED dispersion r in the "
                            "NegBinom repricer + realized score. A live book also sees the "
                            "score; this is forecaster quality, not a $ edge."),
        }


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="MLB best-calibrated game predictor.")
    ap.add_argument("--home", default="NYY")
    ap.add_argument("--away", default="BOS")
    args = ap.parse_args(argv)
    p = MLBPredictor()
    print(f"(state built from {p.n_games} games; fitted r_home={p.r_home:.3f} "
          f"r_away={p.r_away:.3f}; {len(p.teams)} teams)")
    pre = p.predict(args.home, args.away)
    print("PREGAME:"); print(json.dumps(pre, indent=2))
    live = p.predict_live(args.home, args.away, inning=6, half="top",
                          home_runs=4, away_runs=2)
    print("\nLIVE (bot 5th done, top 6th, 4-2 home):")
    print(json.dumps(live, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

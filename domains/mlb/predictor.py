"""domains.mlb.predictor -- best calibrated MLB game predictor.

WIRING (validated modules only, no new modelling):
  * win prob    -> MOV-Elo (same engine proof_mlb.beat_the_close_ml scores; W150 parity)
  * runs        -> RunRateState lambdas (EW off/def rate state)
  * O/U surface -> NegBinom with leak-free FITTED dispersion r (first-half corpus, not
                   hardcoded); closes W149 audit HIGH #1/#3.
  * coherence   -> lambdas tilted (SUM preserved -> total unchanged) so NegBinom
                   tie-adj ML == Elo win-prob across every market (ML/RL/O-U).
  * live        -> Elo-anchored lambdas + fitted r -> repricer -> W156 recal (identity:
                   forecaster already calibrated; a fitted Platt worsens ECE).

P0 NAME-RESOLUTION FIX: predict()/to_jd()/predict_live() now call _resolve_or_upper()
before Elo + run-rate lookups so ESPN display names ("New York Yankees") and
non-corpus abbreviations (KC->KAN, TB->TAM, SF->SFG, SD->SDG, WSH->WAS) produce
game-specific calibrated probs instead of the uniform init-rating collapse (0.5345).

HONEST: calibration/accuracy only; markets efficient; NO $ edge.
INVARIANTS: never edit src/ or kernel/; reuse validated builders; <=300 LOC.
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
from domains.mlb.team_name_resolver import resolve as _resolve_mlb
# Single source of truth for MLB win-prob: the SAME MOV-Elo the beat-the-close proof scores
# against the devigged close (W150 parity fix -- predict() and the measurement now agree).
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

        # 1) fitted dispersion (first 50% only); 2) final MOV-Elo; 3) run-rate state
        self.r_home, self.r_away, self._n_train = fit_dispersion_first_half(df)
        self._elo = _mov_final_ratings(df)
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

        # W156: forecaster already calibrated (ECE 0.0085, slope 0.98); Platt WORSENS -> identity.
        self.ingame_recal = lambda p: float(min(max(p, 0.0), 1.0))  # identity (W156 NULL)
        self.ingame_recal_method = "identity"
        self.ingame_recal_note = "W156: in-game forecaster calibrated (ECE 0.0085, slope 0.98); recal=identity."

    # ------------------------------------------------------------------
    def _resolve(self, name: str) -> Optional[str]:
        """Resolve a slate team name (ESPN displayName or abbreviation) to a corpus key.

        Returns the corpus key on success, or None if the name cannot be resolved
        to any known MLB franchise.  None MUST be treated as unmatched by callers
        (no init-rating fallback).
        """
        # Try corpus key directly (fast path for callers already using corpus keys)
        candidate = name.strip().upper() if isinstance(name, str) else ""
        if candidate in self._elo:
            return candidate
        return _resolve_mlb(name)

    def _resolve_or_upper(self, name: str) -> str:
        """Map ESPN display name / abbreviation to corpus key; else return name.upper().

        Fixes the P0 bug: without this, non-corpus names caused _elo_of to return
        _MOV_INIT for both sides -> uniform p_home=0.5345 for every matchup.
        Genuinely unknown names fall back to uppercase (league-prior) as before.
        """
        resolved = self._resolve(name)
        return resolved if resolved is not None else name.strip().upper()

    def _elo_of(self, team: str) -> float:
        return float(self._elo.get(team, _MOV_INIT))

    def _lambdas(self, home: str, away: str) -> tuple[float, float]:
        """Run-rate lambdas for the NEXT home-vs-away matchup (read-only snapshot)."""
        return self._rr.snapshot(home, away, self._last_season)

    def predict(self, home: str, away: str,
                total_lines: Sequence[float] = _DEFAULT_LINES) -> Dict:
        """Calibrated surface for home vs away (corpus keys, ESPN abbrs, or displayNames ok).

        P0 fix: _resolve_or_upper() maps all name forms to corpus keys before Elo and
        run-rate lookups; without it non-corpus names collapsed to uniform 0.5345.
        Unknown teams still fall back to league priors (init-rating pair).
        """
        ht = self._resolve_or_upper(home)
        au = self._resolve_or_upper(away)
        p_home = _mov_p_home(self._elo_of(ht), self._elo_of(au))
        lam_raw_h, lam_raw_a = self._lambdas(ht, au)

        # COHERENCE: tilt the lambdas (SUM preserved -> expected total unchanged) so the
        # NegBinom matrix tie-adjusted ML == the reported Elo win-prob. Without this the
        # run-line/O-U were built off RAW lambdas -> a SECOND, contradictory win-prob. Now
        # every market (ML, run-line, O/U) is anchored to the one reported p_home. Same
        # anchor to_jd() uses, so predict() and to_jd() agree.
        tgt = min(max(p_home, 0.01), 0.99)
        lam_h, lam_a = _anchor_nb_tiesplit(lam_raw_h, lam_raw_a, self.r_home, self.r_away, tgt)

        P = runs_matrix_nb(lam_h, lam_a, self.r_home, self.r_away)
        mkts = markets_from_matrix_nb(P, total_lines=total_lines)
        totals = [{"line": ln, "over": round(mkts[f"over_{ln:g}"], 4),
                   "under": round(mkts[f"under_{ln:g}"], 4)} for ln in total_lines]
        # COMPLETE derivable market surface (run line + alternates, team totals, F5,
        # any-line game totals) -- a PURE read-off of the SAME anchored NegBinom run
        # distribution, so every market shares this one p_home and expected total.
        from domains.mlb.markets import full_market_surface  # noqa: PLC0415
        markets = full_market_surface(lam_h, lam_a, self.r_home, self.r_away,
                                      total_lines=total_lines)
        return {
            "sport": "mlb", "home": ht, "away": au,
            "p_home_win": round(p_home, 4), "p_away_win": round(1.0 - p_home, 4),
            "expected_runs_home": round(lam_h, 2), "expected_runs_away": round(lam_a, 2),
            "expected_total": round(lam_h + lam_a, 2),
            "run_line_home_minus15": round(mkts["rl_home_minus15"], 4),
            "totals": totals,
            "markets": markets,
            "dispersion_r": {"home": round(self.r_home, 3), "away": round(self.r_away, 3)},
            "elo": {ht: round(self._elo_of(ht), 0), au: round(self._elo_of(au), 0)},
            "honest_note": ("ONE Elo win-prob anchors all markets (NegBinom tie-adj ML == "
                            "p_home_win, SUM preserved). r FITTED first-half corpus. No $ edge."),
        }

    # ------------------------------------------------------------------
    def predict_safe(self, home_raw: str, away_raw: str,
                     total_lines: Sequence[float] = _DEFAULT_LINES) -> Dict:
        """Resolve ESPN slate names then predict; unmatched=True when a name is unknown.

        Delegates to predict() on success. On any unresolved name returns an honest
        unmatched dict rather than emitting a fabricated init-rating probability.
        """
        h_key = self._resolve(home_raw)
        a_key = self._resolve(away_raw)
        unmatched_names = []
        if h_key is None:
            unmatched_names.append(home_raw)
        if a_key is None:
            unmatched_names.append(away_raw)
        if unmatched_names:
            return {
                "sport": "mlb",
                "home_raw": home_raw, "away_raw": away_raw,
                "unmatched": True,
                "unmatched_names": unmatched_names,
                "home_key": h_key, "away_key": a_key,
                "honest_note": (
                    "Team name(s) could not be resolved to the MLB Elo corpus. "
                    "No prediction emitted -- init-rating fabrication suppressed. "
                    "Calibration only; no $ edge."),
            }
        return {**self.predict(h_key, a_key, total_lines),
                "home_raw": home_raw, "away_raw": away_raw,
                "unmatched": False}

    # ------------------------------------------------------------------
    def to_jd(self, home: str, away: str, *, n_sims: int = 20_000, seed: int = 0):
        """Coherent JD (home_runs, away_runs): lambdas tilted so NegBinom ML == Elo win-prob."""
        ht = self._resolve_or_upper(home)
        au = self._resolve_or_upper(away)
        lam_h, lam_a = self._lambdas(ht, au)
        p_home = _mov_p_home(self._elo_of(ht), self._elo_of(au))
        tgt = min(max(p_home, 0.01), 0.99)
        lam_h, lam_a = _anchor_nb_tiesplit(lam_h, lam_a, self.r_home, self.r_away, tgt)
        return build_mlb_jd(lam_h, lam_a, self.r_home, self.r_away,
                            n_sims=n_sims, seed=seed, dispersion="negbinom")

    # ------------------------------------------------------------------
    def predict_live(self, home: str, away: str, inning: int, half: str,
                     home_runs: int, away_runs: int) -> Dict:
        """In-game = Elo-ANCHORED lambdas + fitted r -> repricer -> W156 recal (identity).
        inning: 1-9+ ; half in {'top','bottom'}; innings_played = completed-inning count.
        """
        from scripts.platformkit.live_repricer import GameState, get_repricer  # noqa: PLC0415

        ht = self._resolve_or_upper(home)
        au = self._resolve_or_upper(away)
        lam_raw_h, lam_raw_a = self._lambdas(ht, au)
        # Anchor lambdas to Elo win-prob so live ML@tip agrees with pregame ML.
        tgt = min(max(_mov_p_home(self._elo_of(ht), self._elo_of(au)), 0.01), 0.99)
        lam_h, lam_a = _anchor_nb_tiesplit(lam_raw_h, lam_raw_a, self.r_home, self.r_away, tgt)
        innings_played = max(0.0, float(inning) - 1.0 + (0.5 if str(half).lower() == "bottom" else 0.0))
        pp = {"lam_home": lam_h, "lam_away": lam_a,
              "r_home": self.r_home, "r_away": self.r_away}
        out = get_repricer("mlb").reprice(GameState(
            "mlb", innings_played * 20.0, int(home_runs), int(away_runs),
            pregame_params=pp, extra={"innings_played": innings_played}))
        p_home_raw = float(out["ml_home"])
        p_home_cal = self.ingame_recal(p_home_raw)
        return {
            "sport": "mlb", "home": ht, "away": au,
            "inning": inning, "half": half, "score": (home_runs, away_runs),
            "innings_played": innings_played,
            "p_home_win": round(p_home_cal, 4),
            "p_away_win": round(1.0 - p_home_cal, 4),
            "p_home_win_raw": round(p_home_raw, 4),
            "recal_method": self.ingame_recal_method,
            "run_line_home_minus15": round(float(out["rl_home_minus15"]), 4),
            "proj_remaining_runs": round(float(out["_lam_remaining_home"]
                                               + out["_lam_remaining_away"]), 2),
            "innings_remaining": round(float(out["_innings_remaining"]), 1),
            "recal_note": self.ingame_recal_note,
            "honest_note": "In-game = Elo-anchored lambdas + fitted r + repricer + W156 recal (id). No $ edge.",
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
    # COHERENCE: re-read the home-win event off the same NegBinom matrix the run-line/O-U use.
    lam_h, lam_a = p._lambdas(p._resolve_or_upper(args.home), p._resolve_or_upper(args.away))
    alh, ala = _anchor_nb_tiesplit(lam_h, lam_a, p.r_home, p.r_away,
                                   min(max(pre["p_home_win"], 0.01), 0.99))
    matrix_ml = _nb_tie_adj_ml(alh, ala, p.r_home, p.r_away)
    print(f"\nCOHERENCE: p_home_win={pre['p_home_win']:.4f} run-matrix ML={matrix_ml:.4f} "
          f"|diff|={abs(matrix_ml - pre['p_home_win']):.4f}")
    live = p.predict_live(args.home, args.away, inning=6, half="top", home_runs=4, away_runs=2)
    print("\nLIVE (top 6th, 4-2 home):"); print(json.dumps(live, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

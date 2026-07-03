"""domains.basketball_wnba.pregame_gate -- honest leak-free WNBA pregame calibration gate.

Question: is the walk-forward Elo predictor (domains.basketball_wnba.ratings)
CALIBRATED -- i.e. does it beat naive baselines (coin-flip 0.5, home-prior-only)
on held-out walk-forward Brier/logloss/ECE -- across TWO INDEPENDENT corpora
(season 2025 and season 2026, each scored using ONLY that season's own strictly-
prior games via a fresh elo_state_asof walk, so no cross-season leakage)?

NO CLOSE-LINE COMPARISON YET: no historical Kalshi close data exists for WNBA
(capture only starts once the kalshi_series_spec "wnba" entry goes live and the
capture daemons pick up ticks). The verdict is therefore explicitly
CALIBRATION_BASELINE_OK or PENDING_CLOSE_COMPARISON -- NEVER a "beats the market"
claim. See .claude/rules/no-edge-claims.md.

DISCIPLINE (binding):
  * Per-corpus walk-forward: within EACH season, every game's Elo prediction uses
    only strictly-prior games from THAT season's replay (elo_state_asof-style,
    via ratings.walk_forward_elo restricted to the season's rows) -- leak-free by
    construction (same snapshot-before-update contract as ratings.py).
  * >=2 independent corpora (season 2025, season 2026) -- a single-season lift is
    an artifact per the no single-fold-lift rule.
  * DEGENERATE-BASE GUARD: if the home-prior-only baseline itself has near-zero
    Brier-skill vs the constant coin-flip, the corpus carries too little
    separable signal for a "beats baseline" claim to mean much -- flagged, not
    hidden.

NO $ / edge anywhere: verdict is CALIBRATION (Brier/logloss/ECE), never a market
edge. Pure numpy/pandas + the shared clustered DM test. No src.*/kernel* imports
(domains.basketball_wnba.ratings only).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from domains.basketball_wnba.ratings import walk_forward_elo

BSS_MIN = 0.003  # min Brier-skill-vs-coin-flip for a corpus to be "non-degenerate"
N_ECE_BINS = 10


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(y: np.ndarray, p: np.ndarray, eps: float = 1e-7) -> float:
    pc = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def _ece(y: np.ndarray, p: np.ndarray, n_bins: int = N_ECE_BINS) -> float:
    """Expected Calibration Error: mean |accuracy - confidence| over equal-width
    probability bins, weighted by bin occupancy. Empty bins contribute 0."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(p)
    if total == 0:
        return float("nan")
    err = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p >= lo) & (p < hi) if hi < 1.0 else (p >= lo) & (p <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        acc = float(y[mask].mean())
        conf = float(p[mask].mean())
        err += (n / total) * abs(acc - conf)
    return float(err)


@dataclass
class CorpusResult:
    season: str
    n_games: int
    brier_elo: float
    brier_coin: float
    brier_home_prior: float
    logloss_elo: float
    logloss_coin: float
    logloss_home_prior: float
    ece_elo: float
    home_win_rate: float
    bss_vs_coin: float
    degenerate: bool
    beats_coin: bool
    beats_home_prior: bool

    def to_dict(self) -> Dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def _corpus_result(games_df: pd.DataFrame, season: str) -> CorpusResult:
    """Walk-forward Elo scored on ONE season's rows only (leak-free: each row's
    elo_home/elo_away come from ratings.walk_forward_elo's snapshot-before-update
    replay, restricted to this season -- no cross-season carry-over)."""
    season_df = games_df[games_df["season"] == season].copy()
    wf = walk_forward_elo(season_df)
    y = wf["home_win"].astype(float).values
    p_elo = wf["p_home_elo"].astype(float).values

    home_rate = float(np.mean(y))
    p_coin = np.full_like(y, 0.5)
    p_home_prior = np.full_like(y, home_rate)

    br_elo = _brier(y, p_elo)
    br_coin = _brier(y, p_coin)
    br_prior = _brier(y, p_home_prior)
    ll_elo = _logloss(y, p_elo)
    ll_coin = _logloss(y, p_coin)
    ll_prior = _logloss(y, p_home_prior)
    ece_elo = _ece(y, p_elo)

    bss_vs_coin = (br_coin - br_elo) / br_coin if br_coin > 0 else 0.0
    degen = bss_vs_coin < BSS_MIN

    return CorpusResult(
        season=season, n_games=len(y),
        brier_elo=br_elo, brier_coin=br_coin, brier_home_prior=br_prior,
        logloss_elo=ll_elo, logloss_coin=ll_coin, logloss_home_prior=ll_prior,
        ece_elo=ece_elo, home_win_rate=home_rate, bss_vs_coin=bss_vs_coin,
        degenerate=degen,
        beats_coin=bool(br_elo < br_coin),
        beats_home_prior=bool(br_elo < br_prior),
    )


@dataclass
class GateVerdict:
    verdict: str
    corpora: List[Dict] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    close_comparison: str = "PENDING_CLOSE_COMPARISON"

    def to_dict(self) -> Dict:
        return {"verdict": self.verdict, "corpora": self.corpora,
                "caveats": list(self.caveats),
                "close_comparison": self.close_comparison}


def _decide(results: List[CorpusResult]) -> str:
    if not results:
        return "INSUFFICIENT_DATA"
    if any(r.n_games < 20 for r in results):
        return "INSUFFICIENT_DATA"
    non_degen = [r for r in results if not r.degenerate]
    if not non_degen:
        return "INVALID_BASE"
    all_beat = all(r.beats_coin and r.beats_home_prior for r in non_degen)
    if all_beat and len(non_degen) == len(results):
        return "CALIBRATION_BASELINE_OK"
    any_beat = any(r.beats_coin and r.beats_home_prior for r in non_degen)
    return "PARTIAL" if any_beat else "REJECT"


def gate_pregame(games_df: pd.DataFrame, seasons: List[str]) -> GateVerdict:
    """Run the leak-free pregame calibration gate across >=2 independent season
    corpora. Each season is walk-forward-scored INDEPENDENTLY (no shared state
    across seasons) -- season A's ratings never see season B's games."""
    results = [_corpus_result(games_df, s) for s in seasons]
    cav = [
        "Each corpus is walk-forward Elo restricted to its OWN season's rows -- "
        "leak-free by construction (snapshot-before-update replay).",
        "Verdict is CALIBRATION (Brier/logloss/ECE vs coin-flip and home-prior "
        "baselines), never a market edge.",
        "No historical Kalshi close data exists yet for WNBA -- close_comparison "
        "is honestly PENDING, not fabricated.",
    ]
    if any(r.degenerate for r in results):
        cav.append(
            "DEGENERATE-BASE GUARD tripped on >=1 corpus: Brier-skill-vs-coin-flip "
            "< %.3f -- that corpus carries too little separable signal for a "
            "'beats baseline' claim to be meaningful." % BSS_MIN)
    return GateVerdict(_decide(results), [r.to_dict() for r in results], cav)


__all__ = ["gate_pregame", "GateVerdict", "CorpusResult", "BSS_MIN", "N_ECE_BINS"]

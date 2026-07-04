"""domains.baseball_npb.pregame_gate -- honest leak-free NPB pregame calibration gate.

Question: is the walk-forward Elo predictor (domains.baseball_npb.ratings)
CALIBRATED -- i.e. does it beat naive baselines (coin-flip 0.5, home-prior-
only) on held-out walk-forward Brier/logloss/ECE -- across >=2 INDEPENDENT
corpora (2024 and 2025+2026 combined per the lane spec: fit on 2022-2023,
gate on 2024 as one corpus and 2025+2026 as a second, each scored using ONLY
that corpus's own strictly-prior games via a fresh walk, so no cross-corpus
leakage)?

TIES EXCLUDED FROM SCORING: NPB allows draws (home_win=NaN). A tied row still
gets a walk-forward pre-game Elo prediction (see ratings.py) but is dropped
from the Brier/logloss/ECE arithmetic here -- there is no {0,1} label to score
against. The exclusion rate is reported per corpus so it is never silently
hidden.

NO CLOSE-LINE COMPARISON YET: no historical Kalshi close-price capture exists
for NPB (KXNPBGAME is live NOW per the lane's probe, but capture only starts
once a capture daemon is wired to it). The verdict is therefore explicitly
CALIBRATION_BASELINE_OK / PARTIAL / REJECT / INSUFFICIENT_DATA -- NEVER a
"beats the market" claim. See .claude/rules/no-edge-claims.md.

Mirrors domains.basketball_wnba.pregame_gate structure/thresholds exactly
(same BSS_MIN degenerate-base guard, same N_ECE_BINS, same _decide() logic) --
the gate math itself is sport-blind; only the tie-exclusion step is NPB-
specific.

Pure numpy/pandas + local helpers. No src.*/kernel.* imports.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_npb/test_pregame_gate.py -q
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from domains.baseball_npb.ratings import walk_forward_elo

BSS_MIN = 0.003  # min Brier-skill-vs-coin-flip for a corpus to be "non-degenerate"
N_ECE_BINS = 10


def _brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(y: np.ndarray, p: np.ndarray, eps: float = 1e-7) -> float:
    pc = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))


def _ece(y: np.ndarray, p: np.ndarray, n_bins: int = N_ECE_BINS) -> float:
    """Expected Calibration Error: mean |accuracy - confidence| over
    equal-width probability bins, weighted by bin occupancy. Empty bins
    contribute 0."""
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
    corpus: str
    n_games: int
    n_ties_excluded: int
    tie_rate: float
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


def _corpus_result(games_df: pd.DataFrame, seasons: List[str], corpus_label: str) -> CorpusResult:
    """Walk-forward Elo scored on the rows belonging to *seasons*, ties
    EXCLUDED from scoring (leak-free: each row's elo_home/elo_away come from
    ratings.walk_forward_elo's snapshot-before-update replay, restricted to
    these seasons -- no carry-over from a different corpus)."""
    corpus_df = games_df[games_df["season"].isin(seasons)].copy()
    wf = walk_forward_elo(corpus_df)

    n_total = len(wf)
    tied_mask = wf["home_win"].isna()
    n_tied = int(tied_mask.sum())
    scored = wf[~tied_mask]

    y = scored["home_win"].astype(float).values
    p_elo = scored["p_home_elo"].astype(float).values

    home_rate = float(np.mean(y)) if len(y) else float("nan")
    p_coin = np.full_like(y, 0.5) if len(y) else np.array([])
    p_home_prior = np.full_like(y, home_rate) if len(y) else np.array([])

    br_elo = _brier(y, p_elo) if len(y) else float("nan")
    br_coin = _brier(y, p_coin) if len(y) else float("nan")
    br_prior = _brier(y, p_home_prior) if len(y) else float("nan")
    ll_elo = _logloss(y, p_elo) if len(y) else float("nan")
    ll_coin = _logloss(y, p_coin) if len(y) else float("nan")
    ll_prior = _logloss(y, p_home_prior) if len(y) else float("nan")
    ece_elo = _ece(y, p_elo)

    bss_vs_coin = (br_coin - br_elo) / br_coin if (br_coin and br_coin > 0) else 0.0
    degen = bool(np.isnan(bss_vs_coin)) or bss_vs_coin < BSS_MIN

    return CorpusResult(
        corpus=corpus_label, n_games=n_total,
        n_ties_excluded=n_tied,
        tie_rate=(n_tied / n_total) if n_total else 0.0,
        brier_elo=br_elo, brier_coin=br_coin, brier_home_prior=br_prior,
        logloss_elo=ll_elo, logloss_coin=ll_coin, logloss_home_prior=ll_prior,
        ece_elo=ece_elo, home_win_rate=home_rate, bss_vs_coin=bss_vs_coin,
        degenerate=degen,
        beats_coin=bool(len(y) and br_elo < br_coin),
        beats_home_prior=bool(len(y) and br_elo < br_prior),
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
    if any(r.n_games - r.n_ties_excluded < 20 for r in results):
        return "INSUFFICIENT_DATA"
    non_degen = [r for r in results if not r.degenerate]
    if not non_degen:
        return "INVALID_BASE"
    all_beat = all(r.beats_coin and r.beats_home_prior for r in non_degen)
    if all_beat and len(non_degen) == len(results):
        return "CALIBRATION_BASELINE_OK"
    any_beat = any(r.beats_coin and r.beats_home_prior for r in non_degen)
    return "PARTIAL" if any_beat else "REJECT"


def gate_pregame(games_df: pd.DataFrame, corpora: Dict[str, List[str]]) -> GateVerdict:
    """Run the leak-free pregame calibration gate across >=2 independent
    corpora, each a dict entry {corpus_label: [season, ...]}. Each corpus is
    walk-forward-scored INDEPENDENTLY (no shared state across corpora) --
    corpus A's ratings never see corpus B's games."""
    results = [_corpus_result(games_df, seasons, label) for label, seasons in corpora.items()]
    cav = [
        "Each corpus is walk-forward Elo restricted to its OWN season(s) -- "
        "leak-free by construction (snapshot-before-update replay).",
        "Verdict is CALIBRATION (Brier/logloss/ECE vs coin-flip and home-prior "
        "baselines), never a market edge.",
        "NPB draws (home_win=NaN) are EXCLUDED from Brier/logloss/ECE scoring "
        "in every corpus -- see n_ties_excluded/tie_rate per corpus.",
        "No historical Kalshi close-price capture exists yet for NPB -- "
        "close_comparison is honestly PENDING, not fabricated.",
    ]
    if any(r.degenerate for r in results):
        cav.append(
            "DEGENERATE-BASE GUARD tripped on >=1 corpus: Brier-skill-vs-coin-flip "
            "< %.3f -- that corpus carries too little separable signal for a "
            "'beats baseline' claim to be meaningful." % BSS_MIN)
    return GateVerdict(_decide(results), [r.to_dict() for r in results], cav)


__all__ = ["gate_pregame", "GateVerdict", "CorpusResult", "BSS_MIN", "N_ECE_BINS"]

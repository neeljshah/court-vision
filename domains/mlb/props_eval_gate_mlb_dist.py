"""LANE 3 -- distribution math + leak-free walk-forward opportunity builder for
props_eval_gate_mlb.py (WAKE-31, queue item 3). Split out to respect the 300 LOC
cap; props_eval_gate_mlb.py imports everything it needs from here (PROPS/CORPORA/
dispersion_for live in the sibling props_eval_gate_mlb_constants.py to avoid a
circular import between this file and props_eval_gate_mlb.py).

Distribution math (Poisson/NegBin pmf, discrete CRPS, median+/-1) mirrors
domains/soccer/prop_engine.py's _poisson_pmf/_negbin_pmf (local copy avoids a
cross-sport import for a 6-line fn -- kept byte-comparable so the two engines
never drift).

STARTER IDENTITY: reuses domains/mlb/sp_adjust_current._identify_starts (a
player_gamelogs pitcher row counts as a START only when player_id matches
probables' home_sp_id/away_sp_id for the SAME game_pk -- nothing guessed).

LEAK CONTRACT: walk-forward, snapshot-before-update -- see props_eval_gate_mlb.py's
module docstring for the full discipline writeup (this module implements it; that
one documents + scores + verdicts it).

PURE pandas/numpy/stdlib; no src/kernel/api imports. ASCII only.
Public functions NEVER raise (score_prop / build_opportunities degrade to []/errors
are handled by the caller in props_eval_gate_mlb.py). Per-file test only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_props_eval_gate_mlb.py -q
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.mlb.props_eval_gate_mlb_constants import CORPORA, PROPS
from domains.mlb.sp_adjust_current import _identify_starts

_EPS = 1e-9
_MAX_K = 500  # pmf summation cap (mirrors soccer prop_engine's _MAX_K discipline)

EW_ALPHA = 0.35          # matches asof_sp_form.py / sp_adjust_current.py
MIN_PRIOR_STARTS = 3     # matches asof_sp_form.py / sp_adjust_current.py
_RECENT_BF_STARTS = 15   # expected-BF window (mirrors exposure_mlb._RECENT_GAMES)
_DEFAULT_BF = 24.0       # mirrors exposure_mlb._DEFAULT_STARTER_BF

# Distribution math (Poisson / NegBin pmf, CRPS, pinball) -- pure stdlib/numpy.


def _poisson_pmf(k: int, lam: float) -> float:
    if lam < 0 or k < 0:
        return 0.0
    if lam == 0.0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1.0))


def _negbin_pmf(k: int, mean: float, r: float) -> float:
    if mean < 0 or k < 0 or r <= 0:
        return 0.0
    if mean == 0.0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mean)
    log_coef = math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1.0)
    return math.exp(log_coef + r * math.log(p) + k * math.log(1.0 - p))


def _pmf_fn(lam: float, dispersion: Optional[float]):
    if dispersion is not None and dispersion > 0.0:
        r = float(dispersion)
        return lambda k: _negbin_pmf(k, lam, r)
    return lambda k: _poisson_pmf(k, lam)


def _cdf_table(pmf, k_max: int) -> List[float]:
    """Cumulative P(X <= k) for k in [0, k_max]."""
    table = []
    running = 0.0
    for k in range(k_max + 1):
        running += pmf(k)
        table.append(min(running, 1.0))
    return table


def median_and_pm1(lam: float, dispersion: Optional[float]) -> Tuple[float, float, float]:
    """Discrete median (smallest integer k with CDF(k) >= 0.5) and median+/-1.
    These are the three SYNTHETIC lines the eval scores coverage at."""
    pmf = _pmf_fn(lam, dispersion)
    k_max = min(_MAX_K, max(int(lam * 6) + 20, 20))
    cdf = _cdf_table(pmf, k_max)
    med = k_max
    for k, c in enumerate(cdf):
        if c >= 0.5:
            med = k
            break
    return float(max(med - 1, 0)), float(med), float(med + 1)


def crps_discrete(lam: float, dispersion: Optional[float], y: float) -> float:
    """CRPS for a discrete Poisson/NegBin predictive distribution vs realized y.

    CRPS = sum_k [F(k) - 1{k >= y}]^2 over k=0..k_max (standard discrete-CDF form;
    Gneiting & Raftery 2007 sec 4.2). Truncated at k_max (past lam, or past y)
    with the tail's contribution negligible for the lam ranges here (SP
    strikeouts/hits/walks per start, lam typically 1-9).
    """
    pmf = _pmf_fn(lam, dispersion)
    k_max = min(_MAX_K, max(int(lam * 8) + 30, 30, int(y) + 10))
    cdf = _cdf_table(pmf, k_max)
    total = 0.0
    for k in range(k_max + 1):
        indicator = 1.0 if k >= y else 0.0
        total += (cdf[k] - indicator) ** 2
    return float(total)


def pinball_at_quantile(y: float, q_pred: float, quantile: float) -> float:
    """Single-observation pinball (quantile) loss; averaged by the caller."""
    diff = y - q_pred
    return float(max(quantile * diff, (quantile - 1.0) * diff))


# Leak-free walk-forward per-start rate trackers (EW model + season-mean
# baseline share this state machine; only the update rule differs).


class _RateState:
    """Online per-pitcher rate tracker. alpha=0 -> cumulative mean (baseline);
    alpha in (0,1) -> exponential-weighted (model). snapshot() is leak-free:
    called BEFORE update() folds in the current start (snapshot-before-update,
    identical discipline to sp_adjust_current._EWState)."""

    __slots__ = ("_alpha", "_mean", "_n")

    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._mean: Optional[float] = None
        self._n = 0

    def snapshot(self) -> Tuple[Optional[float], int]:
        if self._n < MIN_PRIOR_STARTS or self._mean is None:
            return None, self._n
        return self._mean, self._n

    def update(self, per_bf_rate: float, weight_n: int = 1) -> None:
        if self._mean is None:
            self._mean = per_bf_rate
        elif self._alpha > 0.0:
            self._mean = (1.0 - self._alpha) * self._mean + self._alpha * per_bf_rate
        else:
            # cumulative mean, weighted by this start's own BF count so a long
            # relief-length outing does not count the same as a 3-BF cameo
            total = self._mean * self._n + per_bf_rate * weight_n
            self._mean = total / (self._n + weight_n)
        self._n += 1


class _LeagueRateState:
    """Pooled league per-BF rate for a stat, leak-free (updated after every
    identified start across ALL pitchers, in date order)."""

    __slots__ = ("_stat_total", "_bf_total")

    def __init__(self) -> None:
        self._stat_total = 0.0
        self._bf_total = 0.0

    def snapshot(self) -> Optional[float]:
        if self._bf_total <= _EPS:
            return None
        return self._stat_total / self._bf_total

    def update(self, stat_count: float, bf: float) -> None:
        self._stat_total += stat_count
        self._bf_total += bf


def _expected_bf_snapshot(hist: List[float]) -> float:
    """Mean BF over the pitcher's last _RECENT_BF_STARTS prior starts; default
    when empty. Leak-free by construction (hist holds only PRIOR starts)."""
    if not hist:
        return _DEFAULT_BF
    window = hist[-_RECENT_BF_STARTS:]
    return float(sum(window) / len(window))


# Per-start opportunity extraction (reuses sp_adjust_current._identify_starts,
# then adds the per-prop realized counts + battersFaced needed here).

_OPP_COLS = ["game_pk", "date", "player_id", "battersFaced",
             "pitch_strikeOuts", "hits_allowed", "baseOnBalls_allowed"]


def _identify_start_opportunities(gamelogs_df: pd.DataFrame,
                                   probables_df: pd.DataFrame) -> pd.DataFrame:
    """One row per identified SP start with realized counts. Reuses
    sp_adjust_current._identify_starts for START identity (never re-derives it),
    then joins back to player_gamelogs for the per-prop realized columns +
    battersFaced. Rows with missing battersFaced (no BF recorded) are dropped --
    exposure cannot be projected without it."""
    starts = _identify_starts(gamelogs_df, probables_df)
    if len(starts) == 0:
        return pd.DataFrame(columns=_OPP_COLS)
    need = set(_OPP_COLS) - {"date"}
    gl = gamelogs_df[[c for c in gamelogs_df.columns if c in need or c == "date"]].copy()
    merged = starts[["game_pk", "player_id"]].merge(
        gl, on=["game_pk", "player_id"], how="left")
    merged = merged[merged["battersFaced"].notna() & (merged["battersFaced"] > 0)]
    merged = merged.drop_duplicates(["game_pk", "player_id"])
    return merged[_OPP_COLS].reset_index(drop=True)


def _corpus_label(date_val, corpora: Dict[str, Tuple[int, int]]) -> Optional[str]:
    year = pd.Timestamp(date_val).year
    for label, (lo, hi) in corpora.items():
        if lo <= year <= hi:
            return label
    return None


@dataclass
class OpportunityRecord:
    game_pk: int
    player_id: int
    date: str
    corpus: str
    y: float
    lam_model: float
    lam_season_mean: float
    lam_league_avg: float
    n_prior_starts: int


def build_opportunities(gamelogs_df: pd.DataFrame, probables_df: pd.DataFrame,
                        stat_key: str, corpora: Dict[str, Tuple[int, int]] = CORPORA
                        ) -> List[OpportunityRecord]:
    """Leak-free walk-forward pass over all identified SP starts for one prop.

    For each start (date order): snapshot the model's EW rate, the season-mean
    (alpha=0) rate, and the league-average rate -- ALL strictly before this
    start's date -- multiply by the SAME expected-BF exposure (mean of the
    pitcher's own last _RECENT_BF_STARTS PRIOR starts, leak-free), producing
    three lam candidates. Records the realized count y. Then updates all three
    states with THIS start (snapshot-before-update). Starts before
    MIN_PRIOR_STARTS prior starts exist are recorded with n_prior_starts < 3 and
    the caller should filter them (no baseline-vs-model comparison is meaningful
    with zero prior information).
    """
    col = PROPS.get(stat_key)
    if col is None:
        raise KeyError(f"unknown stat_key {stat_key!r}, expected one of {list(PROPS)}")
    opp = _identify_start_opportunities(gamelogs_df, probables_df)
    if len(opp) == 0:
        return []
    opp = opp.copy()
    opp["_d"] = pd.to_datetime(opp["date"])
    opp = opp.sort_values(["_d", "game_pk", "player_id"], kind="mergesort").reset_index(drop=True)

    model_states: Dict[int, _RateState] = {}
    season_states: Dict[int, _RateState] = {}
    league_state = _LeagueRateState()
    bf_hist: Dict[int, List[float]] = {}

    out: List[OpportunityRecord] = []
    for _, row in opp.iterrows():
        pid = int(row["player_id"])
        bf = float(row["battersFaced"])
        y = row.get(col)
        y = float(y) if y is not None and not (isinstance(y, float) and math.isnan(y)) else None
        if y is None:
            continue
        corpus = _corpus_label(row["_d"], corpora)
        if corpus is None:
            continue

        m_state = model_states.setdefault(pid, _RateState(EW_ALPHA))
        s_state = season_states.setdefault(pid, _RateState(0.0))
        m_rate, n_prior = m_state.snapshot()
        s_rate, _ = s_state.snapshot()
        l_rate = league_state.snapshot()
        e_bf = _expected_bf_snapshot(bf_hist.get(pid, []))

        lam_model = m_rate * e_bf if m_rate is not None else None
        lam_season = s_rate * e_bf if s_rate is not None else None
        lam_league = l_rate * e_bf if l_rate is not None else None

        out.append(OpportunityRecord(
            game_pk=int(row["game_pk"]), player_id=pid, date=str(row["date"]),
            corpus=corpus, y=y,
            lam_model=lam_model if lam_model is not None else float("nan"),
            lam_season_mean=lam_season if lam_season is not None else float("nan"),
            lam_league_avg=lam_league if lam_league is not None else float("nan"),
            n_prior_starts=n_prior,
        ))

        per_bf_rate = y / bf if bf > _EPS else 0.0
        m_state.update(per_bf_rate)
        s_state.update(per_bf_rate, weight_n=1)
        league_state.update(y, bf)
        bf_hist.setdefault(pid, []).append(bf)
    return out

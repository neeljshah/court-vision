"""parlay_engine.py — Monte-Carlo joint sampler for multi-leg prop parlays."""
from __future__ import annotations

import functools
import hashlib
import itertools
import json
import logging
import os
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np

from src.prediction.betting_portfolio import _american_to_prob, kelly_corr

# F2 (CV_SGP_PAYOUT_PENALTY): flat same-game-parlay payout shortening, mirrors
# src.prediction.parlay_constructor.SGP_PENALTY (Iter-42/43). Real books shorten
# an SGP's combined payout vs the independent leg product because the legs are
# correlated; pricing EV at the un-shortened product double-counts the
# correlation already in p_hit_model. Heuristic magnitude — the validated fix is
# the book's real SGP price (owner-gated FD SGP capture, SGP_EDGE.md).
_SGP_PENALTY: float = 0.15

# CV_ARCHETYPE_CORR (default OFF = byte-identical).
# Import lazily inside _correlation so that the module is never loaded when the
# flag is OFF — zero overhead and zero import side-effects in the default path.
# See src/prediction/correlation_recal.py for full documentation.

log = logging.getLogger(__name__)

# Per-stat residual sigma. Imported from courtvision_router (single source).
try:
    from api.courtvision_router import _STAT_SIGMA as _SIGMA_TABLE
except Exception:
    # Fallback: empirical tail-aware sigma from pregame_oof.parquet calibration.
    _SIGMA_TABLE = {"pts": 6.2, "reb": 2.6, "ast": 2.0, "fg3m": 1.4,
                    "stl": 1.0, "blk": 0.9, "tov": 1.2}

DEFAULT_N_DRAWS = 10_000
DEFAULT_MAX_LEGS = 5
DEFAULT_MIN_EV_PCT = 5.0
TOP_K_BY_LEG_COUNT = {2: 15, 3: 12, 4: 10, 5: 8}
MAX_LEGS_SAME_GAME = 3
MAX_LEGS_SAME_PLAYER = 2
_BANKROLL_DEFAULT = 100.0

_CORR_MATRIX_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "prop_corr_matrix.json"

# CV_PARLAY_FIX_MIXED_SIDE (default OFF = byte-identical to current behavior).
# BUG (hardening sweep 2026-06-02, adversarially confirmed): for a mixed
# OVER/UNDER same-game parlay, _correlation() flips the sign of rho (`rho = -rho`).
# But rho here is the covariance of the LATENT stat draws (sample_outcomes draws
# mu+z@L.T then thresholds each leg with the correct direction, > for OVER, < for
# UNDER). The OVER/UNDER joint-hit reduction is ALREADY produced by those per-leg
# thresholds; flipping rho in the covariance double-counts it with the wrong sign,
# overstating joint hit prob / EV ~3x on mixed same-game parlays (e.g. pts OVER +
# reb UNDER: engine +61% EV vs correct +20%; 2M-draw MC). When the flag is ON the
# flip is skipped so the covariance stays physically correct. Real-money parlay
# EV/edge/gating/Kelly change => RECOMMEND, validate on a mixed-side slate A/B
# before flipping the default. See docs/_audits/HARDENING_PUNCHLIST_2026-06-02.md.
_PARLAY_FIX_MIXED_SIDE = os.environ.get("CV_PARLAY_FIX_MIXED_SIDE", "").strip().lower() in (
    "1", "true", "yes", "on",
)

# Standard assumed two-way overround when only one side's odds are available.
# Typical sportsbook juice on player props is 4–5%; 4.76% matches the canonical
# -110/-110 market (implied sum = 2 * 110/210 ≈ 1.0476).
_ASSUMED_OVERROUND = 1.0476190476190477  # exact: 2 * 110/210 (-110/-110 market)


def _devig_prob(odds: int, other_odds: Optional[int] = None) -> float:
    """Return a vig-free probability for *one side* of a two-way market.

    When the other side's odds are supplied both raw implied probabilities are
    normalised to sum to 1 (exact two-sided de-vig).  When only one side is
    available the raw implied is divided by *_ASSUMED_OVERROUND* (~4.76%),
    which gives exactly 0.5 for a standard -110/-110 leg.
    """
    raw = _american_to_prob(odds)
    if other_odds is not None:
        raw_other = _american_to_prob(other_odds)
        overround = raw + raw_other
        if overround > 0.0:
            return raw / overround
    return raw / _ASSUMED_OVERROUND


_SAME_PLAYER_RHO = {
    frozenset(("pts", "ast")): 0.30,
    frozenset(("pts", "reb")): 0.40,
    frozenset(("pts", "fg3m")): 0.55,
    frozenset(("pts", "stl")): 0.20,
    frozenset(("pts", "blk")): 0.10,
    frozenset(("pts", "tov")): 0.35,
    frozenset(("reb", "blk")): 0.35,
    frozenset(("reb", "ast")): 0.15,
    frozenset(("ast", "tov")): 0.40,
    frozenset(("fg3m", "ast")): 0.20,
    frozenset(("stl", "blk")): 0.15,
}
_TEAMMATE_RHO = {
    frozenset(("pts", "pts")): -0.15,
    frozenset(("pts", "ast")): 0.20,
    frozenset(("reb", "reb")): -0.10,
    frozenset(("ast", "ast")): -0.10,
}
_OPPONENT_RHO = {
    frozenset(("pts", "pts")): 0.20,
    frozenset(("ast", "ast")): 0.15,
    frozenset(("reb", "reb")): 0.10,
}


@functools.lru_cache(maxsize=1)
def _load_matrix_fallback() -> dict[str, dict[str, float]]:
    if not _CORR_MATRIX_PATH.exists():
        return {}
    try:
        return json.loads(_CORR_MATRIX_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("parlay_engine: failed to read %s: %s", _CORR_MATRIX_PATH, exc)
        return {}


def _decimal_to_american(d: float) -> int:
    if d <= 1.0:
        return -10000
    if d >= 2.0:
        return int(round((d - 1.0) * 100.0))
    return int(round(-100.0 / (d - 1.0)))


def _correlation(bet_a: dict, bet_b: dict) -> float:
    if bet_a.get("game_id") != bet_b.get("game_id"):
        return 0.0
    sa, sb = bet_a["prop_stat"].lower(), bet_b["prop_stat"].lower()
    key = frozenset((sa, sb))
    same_player = bet_a.get("player_id") == bet_b.get("player_id")
    same_team = bet_a.get("team") == bet_b.get("team")

    # CV_ARCHETYPE_CORR — recalibrated/archetype-conditioned correlations.
    # Guard: only import + run when flag is ON. When OFF, zero overhead.
    # Opponent branch and the _PARLAY_FIX_MIXED_SIDE sign-flip are PRESERVED.
    if same_player or same_team:
        try:
            from src.prediction import correlation_recal as _recal
            if _recal.recal_enabled():
                if same_player:
                    pid = bet_a.get("player_id")
                    pid_int = int(pid) if pid is not None else None
                    recal_rho = _recal.same_player_rho(sa, sb, pid_int)
                    if recal_rho is not None:
                        rho = recal_rho
                    else:
                        # Fall through to naive same-player lookup below
                        rho = _SAME_PLAYER_RHO.get(key)
                        if rho is None:
                            matrix = _load_matrix_fallback()
                            try:
                                rho = float(matrix.get(sa, {}).get(sb, 0.0)) * 0.5
                            except (TypeError, ValueError):
                                rho = 0.0
                else:
                    # same_team (not same_player)
                    pid_a = bet_a.get("player_id")
                    pid_b = bet_b.get("player_id")
                    pid_a_int = int(pid_a) if pid_a is not None else None
                    pid_b_int = int(pid_b) if pid_b is not None else None
                    recal_rho = _recal.teammate_rho(sa, sb, pid_a_int, pid_b_int)
                    if recal_rho is not None:
                        rho = recal_rho
                    else:
                        rho = _TEAMMATE_RHO.get(key, 0.0)
                if not _PARLAY_FIX_MIXED_SIDE and bet_a.get("side") != bet_b.get("side"):
                    rho = -rho
                return max(-0.95, min(0.95, float(rho)))
        except Exception:
            pass  # Any import/lookup failure falls through to the original path below.

    # Original path (flag OFF or fallback on any exception above).
    if same_player:
        rho = _SAME_PLAYER_RHO.get(key)
        if rho is None:
            matrix = _load_matrix_fallback()
            try:
                rho = float(matrix.get(sa, {}).get(sb, 0.0)) * 0.5
            except (TypeError, ValueError):
                rho = 0.0
    elif same_team:
        rho = _TEAMMATE_RHO.get(key, 0.0)
    else:
        rho = _OPPONENT_RHO.get(key, 0.05)
    if not _PARLAY_FIX_MIXED_SIDE and bet_a.get("side") != bet_b.get("side"):
        # Default (flag OFF): preserve the existing (buggy) sign flip byte-identically.
        # Flag ON: skip it — the per-leg threshold direction in sample_outcomes already
        # encodes the OVER/UNDER joint-hit relationship; flipping rho double-counts it.
        rho = -rho
    return max(-0.95, min(0.95, float(rho)))


class ParlayEngine:
    """Joint-distribution sampler for prop parlays."""

    def __init__(self, bets: list[dict], rng_seed: int = 0,
                 sigma_multiplier: float = 1.0) -> None:
        seen: set[str] = set()
        clean: list[dict] = []
        for b in bets:
            stat = (b.get("prop_stat") or "").lower()
            if (
                b.get("q50") is None
                or b.get("best_price") is None
                or stat not in _SIGMA_TABLE
                or b.get("bet_id") in seen
            ):
                continue
            seen.add(b["bet_id"])
            clean.append(b)
        self.bets = clean
        self.n = len(clean)
        self.rng = np.random.default_rng(rng_seed)
        if self.n == 0:
            self._mu = np.zeros(0)
            self._sigma = np.zeros(0)
            self._cov = np.zeros((0, 0))
            self._hits: Optional[np.ndarray] = None
            return
        # sigma_multiplier widens the per-stat residual sigma — used to widen
        # joint hit-rate estimates in regimes the base table wasn't fit on
        # (e.g. playoffs vs the regular-season-trained residual).
        self._sigma = np.array(
            [_SIGMA_TABLE[b["prop_stat"].lower()] * sigma_multiplier for b in clean],
            dtype=float,
        )
        self._mu = np.array([float(b["q50"]) for b in clean], dtype=float)
        self._cov = self._build_covariance()
        self._hits = None

    def _build_covariance(self) -> np.ndarray:
        cov = np.zeros((self.n, self.n), dtype=float)
        for i in range(self.n):
            cov[i, i] = self._sigma[i] ** 2
            for j in range(i + 1, self.n):
                rho = _correlation(self.bets[i], self.bets[j])
                v = rho * self._sigma[i] * self._sigma[j]
                cov[i, j] = v
                cov[j, i] = v
        return cov

    def _cholesky_psd(self, cov: np.ndarray) -> np.ndarray:
        """Cholesky with two-stage PSD repair: jitter retry, then eigen-clip."""
        if cov.size == 0:
            return cov
        try:
            return np.linalg.cholesky(cov)
        except np.linalg.LinAlgError:
            pass
        jitter = 1e-8
        for _ in range(4):
            try:
                return np.linalg.cholesky(cov + jitter * np.eye(self.n))
            except np.linalg.LinAlgError:
                jitter *= 10
        # Eigen-clip: project onto PSD cone by flooring negative eigenvalues.
        w, V = np.linalg.eigh((cov + cov.T) / 2.0)
        w_clip = np.clip(w, 1e-8, None)
        psd = (V * w_clip) @ V.T
        try:
            return np.linalg.cholesky(psd + 1e-8 * np.eye(self.n))
        except np.linalg.LinAlgError:
            log.warning("parlay_engine: covariance still non-PSD after eigen-clip; "
                        "falling back to diagonal (independent legs).")
            return np.diag(self._sigma)

    def sample_outcomes(self, n: int = DEFAULT_N_DRAWS) -> np.ndarray:
        if self.n == 0:
            return np.zeros((n, 0))
        if self._hits is not None and self._hits.shape[0] == n:
            return self._draws
        L = self._cholesky_psd(self._cov)
        z = self.rng.standard_normal(size=(n, self.n))
        draws = self._mu + z @ L.T
        hits = np.zeros_like(draws, dtype=bool)
        for i, b in enumerate(self.bets):
            line = float(b["line"])
            if b["side"] == "OVER":
                hits[:, i] = draws[:, i] > line
            else:
                hits[:, i] = draws[:, i] < line
        self._draws = draws
        self._hits = hits
        return draws

    def _passes_diversification(self, legs: list[int], max_legs: int) -> bool:
        if not (2 <= len(legs) <= max_legs):
            return False
        players = Counter(self.bets[i].get("player_id") for i in legs)
        if any(c > MAX_LEGS_SAME_PLAYER for c in players.values()):
            return False
        games = Counter(self.bets[i].get("game_id") for i in legs)
        if any(c > MAX_LEGS_SAME_GAME for c in games.values()):
            return False
        seen_props: set[tuple] = set()
        for i in legs:
            b = self.bets[i]
            key = (b.get("player_id"), b["prop_stat"], float(b["line"]))
            if key in seen_props:
                # OVER + UNDER same prop will share key; reject.
                return False
            seen_props.add(key)
        return True

    def _combined_odds(self, legs: list[int]) -> tuple[int, float]:
        decimal = 1.0
        for i in legs:
            odds = int(self.bets[i]["best_price"])
            d = (odds / 100.0 + 1.0) if odds > 0 else (100.0 / abs(odds) + 1.0)
            decimal *= d
        return _decimal_to_american(decimal), decimal

    def _avg_pair_corr(self, legs: list[int]) -> float:
        if len(legs) < 2:
            return 0.0
        rhos: list[float] = []
        for i, j in itertools.combinations(legs, 2):
            rhos.append(_correlation(self.bets[i], self.bets[j]))
        return float(np.mean(rhos))

    def price_parlay(self, legs: list[int]) -> dict:
        if not legs:
            raise ValueError("legs must be non-empty")
        if self._hits is None:
            self.sample_outcomes()
        leg_hits = self._hits[:, legs]
        p_hit_model = float(leg_hits.all(axis=1).mean())
        american, decimal = self._combined_odds(legs)
        # De-vig each leg before multiplying so that a standard -110/-110
        # prop contributes 0.5 (not 0.524).  Use the stored other-side odds
        # when present; otherwise fall back to the assumed 4.76% overround.
        p_hit_market_naive = 1.0
        for i in legs:
            bet = self.bets[i]
            other_odds: Optional[int] = None
            raw_other = bet.get("other_side_price") or bet.get("alt_price")
            if raw_other is not None:
                try:
                    other_odds = int(raw_other)
                except (TypeError, ValueError):
                    other_odds = None
            p_hit_market_naive *= _devig_prob(int(bet["best_price"]), other_odds)
        same_game = Counter(self.bets[i].get("game_id") for i in legs).most_common(1)[0][1]
        # F2 (CV_SGP_PAYOUT_PENALTY): for a same-game parlay (same_game>=2) apply the
        # flat SGP payout shortening so EV is not overstated by pricing the
        # correlation-boosted p_hit_model against the un-shortened independent leg
        # product (~19pts on a 2-leg example: +76% -> +56.9%). Flow it through edge +
        # Kelly + the reported combined odds for coherence. Default OFF = byte-
        # identical; magnitude is heuristic (validated fix = real book SGP price).
        _sgp_pen = (same_game >= 2 and
                    os.environ.get("CV_SGP_PAYOUT_PENALTY", "").strip().lower()
                    not in ("", "0", "false", "no", "off"))
        payout_per_100 = (decimal - 1.0) * 100.0
        if _sgp_pen:
            payout_per_100 *= (1.0 - _SGP_PENALTY)
            decimal = payout_per_100 / 100.0 + 1.0
            american = _decimal_to_american(decimal)
        ev_pct = p_hit_model * payout_per_100 - (1.0 - p_hit_model) * 100.0
        edge = p_hit_model - (1.0 / decimal)
        avg_rho = self._avg_pair_corr(legs)
        if edge > 0:
            kelly_dollars = kelly_corr(edge, american, _BANKROLL_DEFAULT,
                                       corr_with_open=max(0.0, avg_rho))
        else:
            kelly_dollars = 0.0
        bet_ids = [self.bets[i]["bet_id"] for i in legs]
        parlay_id = hashlib.sha1("|".join(sorted(bet_ids)).encode()).hexdigest()[:12]
        leg_summary = " · ".join(
            f"{self.bets[i].get('player_name','?')} {self.bets[i]['prop_stat']} "
            f"{'o' if self.bets[i]['side']=='OVER' else 'u'}{self.bets[i]['line']:g}"
            for i in legs
        )
        narrative = (
            f"{len(legs)}-leg "
            f"{'SGP' if same_game >= 2 else 'multi-game'}: {leg_summary} — "
            f"model {p_hit_model*100:.1f}% vs market {p_hit_market_naive*100:.1f}%, "
            f"EV {ev_pct:+.1f}%."
        )
        return {
            "parlay_id": parlay_id, "legs": bet_ids, "n_legs": len(legs),
            "p_hit_model": round(p_hit_model, 4),
            "p_hit_market_naive": round(p_hit_market_naive, 4),
            "combined_odds_american": int(american),
            "combined_odds_decimal": round(decimal, 3),
            "ev_pct": round(ev_pct, 2),
            "kelly_stake_dollars": round(float(kelly_dollars), 2),
            "avg_pair_correlation": round(avg_rho, 3),
            "same_game_legs": int(same_game),
            "narrative": narrative,
        }

    def enumerate_parlays(self, max_legs: int = DEFAULT_MAX_LEGS,
                          min_ev_pct: float = DEFAULT_MIN_EV_PCT) -> list[dict]:
        if self.n < 2:
            return []
        self.sample_outcomes()
        ranked = sorted(
            range(self.n),
            key=lambda i: -(self.bets[i].get("ev_pct") or 0.0),
        )
        out: list[dict] = []
        seen_parlay_ids: set[str] = set()
        for k in range(2, max_legs + 1):
            top_k = ranked[: TOP_K_BY_LEG_COUNT.get(k, 8)]
            for combo in itertools.combinations(top_k, k):
                legs = list(combo)
                if not self._passes_diversification(legs, max_legs):
                    continue
                price = self.price_parlay(legs)
                if price["parlay_id"] in seen_parlay_ids:
                    continue
                if price["ev_pct"] >= min_ev_pct:
                    out.append(price)
                    seen_parlay_ids.add(price["parlay_id"])
        out.sort(key=lambda p: -p["ev_pct"])
        return out



"""edge_engine.score -- the candidate->gate SCORER (the JUDGE wired to a real signal).

THESIS (binding): a candidate information-edge signal earns SHIP only if it provably
LOWERS out-of-sample Brier vs the SHIN-devigged close, leak-free, on the
confirmed-BEFORE-line-move subset, with a significant CLUSTERED Diebold-Mariano test.
Anything else is an HONEST REJECT -- recorded as a success, never a failure. Markets are
efficient on price; most candidates reject. No $/ROI/+EV/edge language is produced here.

HOW IT WORKS (reuse, never reimplement -- eval_gate is READ-ONLY):
  - walk_forward (eval_gate.walkforward): the leak-free expanding-window split with purge +
    embargo + the vintage assertion. We pass a predict_fn that, for each test game, conditions
    the devigged-close prior with the signal value -- but ONLY when the signal FACT was
    available strictly before that game's line_move_ts (the confirmed-before subset). Off the
    subset, predict_fn returns the close unchanged, so the signal can never leak in.
  - The conditioning is a single BOUNDED net adjustment in logit space, slope fit INSIDE the
    training window only (no full-history selection) -- the scheme-prior pattern: the FACT
    selects/sizes an EXISTING knob; the slope is fit, never authored by an LLM.
  - scoring.brier / brier_skill_score and dm_test.diebold_mariano (clustered by game_id) judge
    the result. SHIP requires BSS>0 AND DM p<alpha AND n>=min_n on the subset; else REJECT.

HONESTY RAILS: the signal carries an availability_timestamp; the leak-free subset is built by
the SAME strictly-before rule the freshness vintage guard enforces. No number the LLM authored
enters a prediction -- only the FACT's presence/value conditions a fitted, bounded knob. The
deliverable is the SCORE (SHIP/REJECT + BSS + clustered DM p), never a fabricated found edge.

Stdlib + numpy. <=300 LOC. Per-file test: test_score.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import numpy as np

# --- READ-ONLY reuse of the eval gate (the JUDGE). Package + bare-run fallbacks. ---
try:  # package import
    from scripts.platformkit.eval_gate.walkforward import walk_forward
    from scripts.platformkit.eval_gate import scoring as S
    from scripts.platformkit.eval_gate.dm_test import diebold_mariano
except ImportError:  # direct-script / per-file-test fallback
    import sys
    from pathlib import Path

    _EG = Path(__file__).resolve().parents[1] / "eval_gate"
    sys.path.insert(0, str(_EG))
    from walkforward import walk_forward  # type: ignore
    import scoring as S  # type: ignore
    from dm_test import diebold_mariano  # type: ignore

# SHIP thresholds -- pre-registered, mirroring the eval gate's BEATS_CLOSE rule.
DEFAULT_ALPHA = 0.05
DEFAULT_MIN_N = 200
# The net adjustment is BOUNDED: a single signal may never swing a prediction by more than
# this in logit space (the scheme-prior rail -- bounded leak-flagged multiplier on a knob).
MAX_LOGIT_ADJ = 1.0


def _to_utc(ts: str) -> datetime:
    """Parse an ISO-8601 string to a UTC-aware datetime (Py3.9-safe; handles 'Z')."""
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _logit(p: float) -> float:
    p = min(max(float(p), 1e-6), 1.0 - 1e-6)
    return float(np.log(p / (1.0 - p)))


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


@dataclass(frozen=True)
class SignalRow:
    """One per-game candidate-signal observation, vintage-stamped.

    `value` is a numeric FEATURE derived from the LLM-extracted FACT (e.g. an encoded
    travel-disruption severity, or a standardized count) -- it is NOT a probability and
    NEVER enters a prediction directly; the scorer fits a bounded slope on it inside the
    training window. `available_ts` is the moment the FACT became public (the vintage key);
    `line_move_ts` is when the line moved. The game is in the confirmed-before subset
    iff available_ts < line_move_ts.
    """
    game_id: str
    value: float
    available_ts: str
    line_move_ts: str

    def confirmed_before(self) -> bool:
        return _to_utc(self.available_ts) < _to_utc(self.line_move_ts)


@dataclass(frozen=True)
class ScoreResult:
    verdict: str            # "SHIP" | "REJECT"
    n_subset: int           # games in the confirmed-before-line-move subset
    bss: float              # Brier skill score of conditioned forecast vs the close (subset)
    brier_signal: float     # Brier of the signal-conditioned forecast (subset)
    brier_close: float      # Brier of the Shin-devigged close (subset)
    dm_p: float             # clustered (by game_id) Diebold-Mariano two-tailed p
    dm_stat: float
    fitted_slope: float     # mean fitted slope across walk-forward steps (diagnostic)
    reason: str             # honest one-line explanation of the verdict

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict, "n_subset": self.n_subset, "bss": self.bss,
            "brier_signal": self.brier_signal, "brier_close": self.brier_close,
            "dm_p": self.dm_p, "dm_stat": self.dm_stat,
            "fitted_slope": self.fitted_slope, "reason": self.reason,
        }


def _build_states(states: Sequence[dict], signal_by_game: Dict[str, SignalRow]) -> List[dict]:
    """Attach each signal row to its state and stamp the leak-free vintage fields.

    A state lacking a confirmed-before signal row keeps signal_value=None: the predict_fn
    then returns the close unchanged, so off-subset games can never leak the signal in.
    """
    out: List[dict] = []
    for s in states:
        gid = s["game_id"]
        row = signal_by_game.get(gid)
        st = dict(s)
        if row is not None and row.confirmed_before():
            st["signal_value"] = float(row.value)
            # Vintage stamp: the feature is known only as of available_ts (< line move).
            fa = dict(st.get("feature_avail", {}))
            fa["signal_value"] = row.available_ts
            st["feature_avail"] = fa
            # state_ts must be the LINE-MOVE time so assert_vintage enforces avail < move.
            st["state_ts"] = row.line_move_ts
        else:
            st["signal_value"] = None
        out.append(st)
    return out


def _make_predict_fn(slope_box: List[float]):
    """Build the leak-free predict_fn: condition the devigged close with the signal, slope
    fit INSIDE the training window only. Records each step's slope into slope_box."""

    def _fit_slope(train: List[dict]) -> float:
        """OLS slope of (y - p_close) on the signal value, fit on training games that HAVE a
        confirmed-before signal value. No fit data -> slope 0 (signal does nothing)."""
        xs, ys = [], []
        for t in train:
            v = t.get("signal_value")
            pc = t.get("devig_close_prob")
            if v is None or pc is None:
                continue
            xs.append(float(v))
            ys.append(float(int(t["outcome"]) - float(pc)))  # residual vs the close
        if len(xs) < 2:
            return 0.0
        x = np.asarray(xs, dtype=float)
        yv = np.asarray(ys, dtype=float)
        xc = x - x.mean()
        denom = float(xc @ xc)
        if denom <= 0.0:
            return 0.0
        return float((xc @ (yv - yv.mean())) / denom)

    def predict_fn(train: List[dict], test: dict, select_inside: bool) -> float:
        pc = test.get("devig_close_prob")
        if pc is None:
            raise AssertionError("candidate scorer requires devig_close_prob on every state")
        v = test.get("signal_value")
        if v is None:                                # off the confirmed-before subset
            slope_box.append(0.0)
            return float(min(max(pc, 0.0), 1.0))
        slope = _fit_slope(train) if select_inside else 0.0
        slope_box.append(slope)
        # Bounded net adjustment in logit space (scheme-prior rail): never swing > MAX_LOGIT_ADJ.
        adj = float(np.clip(slope * float(v), -MAX_LOGIT_ADJ, MAX_LOGIT_ADJ))
        return _sigmoid(_logit(pc) + adj)

    return predict_fn


def score_candidate(states: Sequence[dict],
                    signal_rows: Sequence[SignalRow],
                    alpha: float = DEFAULT_ALPHA,
                    min_n: int = DEFAULT_MIN_N) -> ScoreResult:
    """Score ONE candidate signal through the real leak-free gate. SHIP/REJECT honestly.

    `states`: per-game dicts the eval gate understands -- each needs game_id, home, away,
    state_ts, outcome, devig_close_prob (the SHIN-devigged close prob for the modeled side).
    `signal_rows`: the candidate's per-game values + vintage timestamps.

    SHIP iff, on the confirmed-before-line-move subset: BSS>0 AND clustered-DM p<alpha AND
    n>=min_n. Otherwise REJECT -- an honest, recorded success (markets efficient on price).
    """
    sig_by_game: Dict[str, SignalRow] = {r.game_id: r for r in signal_rows}
    enriched = _build_states(states, sig_by_game)

    slope_box: List[float] = []
    res = walk_forward(enriched, _make_predict_fn(slope_box), select_inside=True)
    if res.select_inside is not True:            # selection-inside-window is non-negotiable
        return ScoreResult("REJECT", 0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
                           "REJECT: select_inside violated (lookahead in feature selection)")

    # Restrict scoring to the confirmed-before subset: games that actually carried the signal.
    sub = [r for r, st in zip(res.records, enriched) if st.get("signal_value") is not None]
    n = len(sub)
    fitted = float(np.mean([s for s in slope_box if s != 0.0])) if any(slope_box) else 0.0
    if n < min_n:
        return ScoreResult("REJECT", n, 0.0, 0.0, 0.0, 1.0, 0.0, fitted,
                           f"REJECT: confirmed-before subset n={n} < min_n={min_n} "
                           "(insufficient leak-free, timely sample)")

    pm = np.array([r["p_model"] for r in sub], dtype=float)
    pc = np.array([r["p_close"] for r in sub], dtype=float)
    y = np.array([r["y"] for r in sub], dtype=float)
    gid = [r["game_id"] for r in sub]

    bm = S.brier(pm, y)
    bc = S.brier(pc, y)
    bss = S.brier_skill_score(pm, pc, y)
    d = (pc - y) ** 2 - (pm - y) ** 2            # close loss - signal loss (>0 => signal better)
    dm = diebold_mariano(d, gid)

    ship = (bss > 0.0) and (dm.p_value < alpha) and (n >= min_n)
    if ship:
        reason = (f"SHIP: lowers OOS Brier vs the devigged close on the confirmed-before "
                  f"subset (BSS={bss:.4f}, clustered DM p={dm.p_value:.4f}, n={n}, "
                  f"clusters={dm.n_clusters})")
    elif bss <= 0.0:
        reason = (f"REJECT: does NOT beat the close (BSS={bss:.4f}<=0) -- honest null, "
                  "markets efficient on price")
    else:
        reason = (f"REJECT: lift not significant (BSS={bss:.4f} but clustered DM "
                  f"p={dm.p_value:.4f}>=alpha={alpha}) -- single-fold lift is an artifact")

    return ScoreResult("SHIP" if ship else "REJECT", n, float(bss), float(bm), float(bc),
                       float(dm.p_value), float(dm.dm_stat), fitted, reason)

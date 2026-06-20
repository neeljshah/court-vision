"""scripts.platformkit.gate_run_mlb_sp_fatigue_kprop -- GATE-RUN for the MLB
SP fatigue/velo-decline PROFILE prior vs the recent-K-rate BASE on a pitcher's
NEXT-start STRIKEOUT-prop, on held-out CALIBRATION (HYPOTHESIS, expected REJECT).

HYPOTHESIS (separate from the REJECTED game win-prob test): a pitcher's HISTORICAL
within-start fatigue/velo-decline PROFILE -- aggregated leak-free over PRIOR starts
(prof_* from domains.mlb.ingest_sp_fatigue_prop_states) -- may add calibration signal
for that pitcher's strikeout prop in the NEXT start, BEYOND a recent-K-rate prior.

THIS RUNNER (no weakening of the bar; consumes the leak-free builder):
  (a) LEAK-FREE LOAD: profile (prof_*, shift1 prior-N) + recent-K-rate BASE (shift1
      prior-N mean of the per-start K LABEL) + the per-start K LABEL itself, via the
      SINGLE train==inference builder. The LABEL is target-only, never a feature; the
      base excludes start N's own K. A missing prior -> NaN (debut), never a 0-fill win.
  (b) WALK-FORWARD within each season: at each start, fit BASE and BASE+PROFILE on
      STRICTLY-PRIOR starts only, predict the held-out start. CALIBRATION = Brier on
      the binarized over/under (median K line) AND pinball/CRPS on the count.
  (c) CROSS-CORPUS BOTH DIRECTIONS: 2022 and 2023 are the two INDEPENDENT corpora;
      SHIP requires the profile to LOWER held-out calibration error AND clear the DM
      in BOTH. A one-season-only win = PARTIAL = REJECT (single-fold lift = artifact).
  (d) CLUSTERED-DM BY (pitcher or start) BOTH DIRECTIONS on the per-start loss diffs.
  (e) DEGENERATE-BASE GUARD: the recent-K-rate base must already be skillful (beat a
      constant-mean baseline by >= MIN_BSS); a non-skillful base makes any "lift"
      meaningless. INVALID_BASE if it is degenerate.
  (f) PLANTED-NULL profile feature (pure noise) through the IDENTICAL gate, which MUST
      REJECT -- proving the gate can fail a worthless signal. If it does not, the run
      is NOT_TESTABLE and we say so.

HONEST DATA REALITY (verified live 2026-06-19, NOT fabricated / 0-filled):
  build_label_join returns INSUFFICIENT_DATA for the profile corpora -- the only
  on-disk per-pitcher K source (player_gamelogs.parquet) is 2026-ONLY (zero overlap
  with the 2022/2023 pitch-state corpora), AND the pitch parquet has no individual
  pitcher id / SP-vs-reliever boundary, so a (game,side) block cannot be keyed to one
  starter's K. The base + label are therefore unbuildable, so run() short-circuits to
  INSUFFICIENT_DATA. The FULL gate machinery below is real and runs the day a
  2022/2023 per-pitcher, SP-isolated K source lands on disk.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, no sentinel, NO $/ROI
/edge field. vs-close stays UNPROVEN -- CALIBRATION only. A truthful INSUFFICIENT_DATA
(or REJECT) is the EXPECTED, honest, SUCCESSFUL outcome. ASCII-only; <=300 LOC.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb import ingest_sp_fatigue_prop_states as M

_REPO = Path(__file__).resolve().parents[2]
_SEASONS = (2022, 2023)
# profile columns emitted by the builder (prof_<col>).
_PROFILE_FEATS = tuple(f"prof_{c}" for c in M._PROFILE_COLS)
_NULL_FEAT = "prof_planted_null"   # pure-noise control -- MUST reject
_MIN_BSS = 0.01                    # base must beat const-mean by >= this (skillful)
_MIN_STARTS = 60                   # per-corpus minimum to even attempt the gate
_LABEL_COL = "label_k"            # per-start strikeout total (target ONLY)
_BASE_COL = "base_recent_k_rate"  # shift1 prior-N mean of label_k


# --------------------------------------------------------------------------- #
# Leak-free load (consumes the builder; never fabricates a label).
# --------------------------------------------------------------------------- #
def load_corpus(season: int, seed: int = 0) -> Tuple[Optional[pd.DataFrame], dict]:
    """Build the leak-free profile, attempt the K LABEL join, attach the base + null.

    Returns (frame_or_None, label_status). If the leak-free per-start K label cannot
    be built on-disk, frame is None and label_status carries the reason codes -- we do
    NOT synthesize a label (that would be fabrication / would make the gate a lie).
    """
    prof = M.build_profile(season, prior_n=M._PRIOR_N)
    if prof.empty:
        return None, {"status": "INSUFFICIENT_DATA", "reasons": ["NO_PITCH_PARQUET"],
                      "season": season}
    label = M.build_label_join(prof)
    if label.get("status") != "OK" or _LABEL_COL not in prof.columns:
        # No leak-free per-start K label on disk -> cannot build base/label. HONEST stop.
        label = dict(label)
        label["season"] = season
        return None, label
    df = prof.copy()
    # planted null: pure noise, outcome-independent -> the gate MUST reject it.
    rng = np.random.default_rng(seed + season)
    df[_NULL_FEAT] = rng.standard_normal(len(df))
    return df, {"status": "OK", "season": season}


# --------------------------------------------------------------------------- #
# Calibration scoring (held-out): Brier on binarized line + pinball on count.
# --------------------------------------------------------------------------- #
def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _pinball(pred: np.ndarray, y: np.ndarray, q: float = 0.5) -> float:
    e = y - pred
    return float(np.mean(np.maximum(q * e, (q - 1.0) * e)))


def _bss(loss_model: float, loss_const: float) -> float:
    return 0.0 if loss_const <= 0 else 1.0 - loss_model / loss_const


def _wf_predict(df: pd.DataFrame, feats: List[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Walk-forward OLS on STRICTLY-PRIOR starts (leak-free) -> per-start count preds.

    Sorted by date; for start i, fit on starts [0, i) with a usable label + finite
    feats, predict start i. Returns (pred_count, y_count, mask_scored).
    """
    d = df.sort_values(["date", "game_id"]).reset_index(drop=True)
    y = d[_LABEL_COL].to_numpy(dtype=float)
    X = d[feats].to_numpy(dtype=float)
    n = len(d)
    pred = np.full(n, np.nan)
    for i in range(n):
        tr = np.arange(i)
        ok = tr[np.isfinite(y[tr]) & np.all(np.isfinite(X[tr]), axis=1)]
        if len(ok) < max(10, len(feats) + 2) or not np.all(np.isfinite(X[i])):
            continue
        A = np.column_stack([np.ones(len(ok)), X[ok]])
        coef, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
        pred[i] = coef[0] + float(np.dot(coef[1:], X[i]))
    mask = np.isfinite(pred) & np.isfinite(y)
    return pred, y, mask


def score_corpus(df: pd.DataFrame, feats: List[str]) -> dict:
    """Held-out Brier (binarized at the median line) + pinball(count) for a feature set."""
    pred, y, mask = _wf_predict(df, feats)
    pc, yc = pred[mask], y[mask]
    if len(yc) < 20:
        return {"n": int(len(yc)), "scored": False}
    line = float(np.median(yc))
    p_over = 1.0 / (1.0 + np.exp(-(pc - line)))   # logistic squash of count gap
    y_over = (yc > line).astype(float)
    return {"n": int(len(yc)), "scored": True, "line": line,
            "brier": _brier(p_over, y_over), "pinball": _pinball(pc, yc),
            "pred": pc, "y": yc, "mask_index": np.where(mask)[0]}


# --------------------------------------------------------------------------- #
# Clustered Diebold-Mariano on per-start loss diffs (cluster by pitch_team-side).
# --------------------------------------------------------------------------- #
def clustered_dm(base: dict, full: dict, df: pd.DataFrame) -> Tuple[float, float]:
    """Two-sided clustered DM p on pinball-loss diffs; cluster = (pitch_team,side).

    Negative mean diff = full LOWERS loss (better). Returns (mean_diff, p_two_sided).
    """
    if not (base.get("scored") and full.get("scored")):
        return float("nan"), float("nan")
    idx = base["mask_index"]
    d = df.sort_values(["date", "game_id"]).reset_index(drop=True).iloc[idx]
    yb, yf = base["pred"], full["pred"]
    yc = base["y"]
    lb = np.abs(yc - yb)        # |err| (pinball at q=0.5 ~ 0.5*|err|, monotone)
    lf = np.abs(yc - yf)
    diff = lf - lb              # <0 => full better
    clusters = (d["pitch_team"].astype(str) + "|" + d["pitch_side"].astype(str)).to_numpy()
    by = {}
    for c, v in zip(clusters, diff):
        by.setdefault(c, []).append(v)
    means = np.array([np.mean(v) for v in by.values()])
    g = len(means)
    if g < 3:
        return float(np.mean(diff)), float("nan")
    se = float(np.std(means, ddof=1) / np.sqrt(g))
    if se == 0.0:
        return float(np.mean(means)), float("nan")
    t = float(np.mean(means)) / se
    # normal-approx two-sided p
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))
    return float(np.mean(means)), float(p)


# --------------------------------------------------------------------------- #
# Per-corpus gate of one feature-set add (BASE vs BASE+feat).
# --------------------------------------------------------------------------- #
def gate_corpus(df: pd.DataFrame, add_feats: List[str], eps: float) -> dict:
    base = score_corpus(df, [_BASE_COL])
    full = score_corpus(df, [_BASE_COL, *add_feats])
    if not (base.get("scored") and full.get("scored")):
        return {"scored": False, "n_base": base.get("n", 0), "n_full": full.get("n", 0)}
    const_pin = _pinball(np.full_like(base["y"], np.mean(base["y"])), base["y"])
    base_bss = _bss(base["pinball"], const_pin)
    degenerate = base_bss < _MIN_BSS
    md, p = clustered_dm(base, full, df)
    feat_better = full["pinball"] < base["pinball"] and full["brier"] <= base["brier"]
    return {"scored": True, "n": base["n"], "base_bss": base_bss, "degenerate": degenerate,
            "brier_base": base["brier"], "brier_full": full["brier"],
            "pin_base": base["pinball"], "pin_full": full["pinball"],
            "dm_mean": md, "dm_p": p, "feat_better": feat_better,
            "wins": bool(feat_better and np.isfinite(p) and p < eps and not degenerate)}


def gate_both(c22: pd.DataFrame, c23: pd.DataFrame, add_feats: List[str], eps: float) -> dict:
    a = gate_corpus(c22, add_feats, eps)   # direction A (2022)
    b = gate_corpus(c23, add_feats, eps)   # direction B (2023)
    if not (a.get("scored") and b.get("scored")):
        return {"verdict": "INSUFFICIENT_DATA", "a": a, "b": b}
    if a["degenerate"] or b["degenerate"]:
        verdict = "INVALID_BASE"
    elif a["wins"] and b["wins"]:
        verdict = "SHIP"
    elif a["wins"] or b["wins"]:
        verdict = "PARTIAL"
    else:
        verdict = "REJECT"
    return {"verdict": verdict, "a": a, "b": b}


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def run(eps: float = 0.05, seed: int = 0) -> Dict[str, object]:
    """Load both corpora leak-free, gate PROFILE + planted-null; honest INSUFFICIENT_DATA."""
    frames: Dict[int, Optional[pd.DataFrame]] = {}
    labels: Dict[int, dict] = {}
    for s in _SEASONS:
        frames[s], labels[s] = load_corpus(s, seed=seed)
    missing = [s for s in _SEASONS if frames[s] is None or len(frames[s]) < _MIN_STARTS]
    if missing:
        reasons = sorted({r for s in _SEASONS for r in labels[s].get("reasons", [])})
        return {"layer": "mlb_sp_fatigue_kprop", "verdict": "INSUFFICIENT_DATA",
                "reasons": reasons or ["NO_LEAKFREE_K_LABEL"],
                "label_status": {s: labels[s] for s in _SEASONS},
                "n_starts": {s: (0 if frames[s] is None else len(frames[s])) for s in _SEASONS},
                "n_starts_with_label": {s: 0 for s in _SEASONS},
                "proposal_only": True,
                "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier/pinball), not a market edge"}
    c22, c23 = frames[_SEASONS[0]], frames[_SEASONS[1]]
    profile = gate_both(c22, c23, list(_PROFILE_FEATS), eps)
    null = gate_both(c22, c23, [_NULL_FEAT], eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL", "INSUFFICIENT_DATA")
    if not null_rejects:
        verdict = "NOT_TESTABLE"
    elif profile["verdict"] == "SHIP":
        verdict = "SHIP"
    else:
        verdict = profile["verdict"]
    return {"layer": "mlb_sp_fatigue_kprop", "verdict": verdict, "eps": eps,
            "profile": profile, "null": null, "null_rejects": null_rejects,
            "proposal_only": True,
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier/pinball), not a market edge"}


def _fmt(tag: str, d: dict) -> str:
    if not d.get("scored"):
        return f"  {tag}: not scored (n_base={d.get('n_base')}, n_full={d.get('n_full')})"
    return (f"  {tag}: Brier {d['brier_base']:.5f}->{d['brier_full']:.5f}  "
            f"pinball {d['pin_base']:.5f}->{d['pin_full']:.5f}  "
            f"DM mean={d['dm_mean']:+.5f} p={d['dm_p']:.4f}  "
            f"base_BSS={d['base_bss']:.4f} degenerate={d['degenerate']}  "
            f"feat_better={d['feat_better']}  n={d['n']}")


def _report(res: Dict[str, object]) -> str:
    L = ["=" * 76,
         "MLB SP FATIGUE/VELO PROFILE -> NEXT-START K-PROP GATE (vs recent-K-rate BASE)",
         "=" * 76,
         "GATE : walk-forward (strictly-prior OLS) | Brier(binarized line)+pinball(count)",
         "       | clustered-DM by (pitch_team,side) both dirs | degenerate-base guard",
         "       | cross-corpus 2022<->2023 both dirs | planted-null MUST reject. PROPOSAL-ONLY.",
         f"VERDICT: {res['verdict']}", "-" * 76]
    if res["verdict"] == "INSUFFICIENT_DATA":
        L.append(f"  reasons: {','.join(res.get('reasons', []))}")
        L.append(f"  n_starts: {res.get('n_starts')}")
        L.append(f"  n_starts_with_label: {res.get('n_starts_with_label')}")
        L.append("  The leak-free per-start K LABEL is unbuildable on-disk for the")
        L.append("  profile corpora -> the BASE + label cannot be built -> the gate")
        L.append("  CANNOT run. Reported truthfully; NOT 0-filled, NOT a forced SHIP.")
        L += ["=" * 76,
              "CALIBRATION only; NO $/ROI/edge. vs-close UNPROVEN. INSUFFICIENT_DATA = honest.",
              "=" * 76]
        return "\n".join(L)
    p = res["profile"]
    L.append(f"PROFILE add ({len(_PROFILE_FEATS)} feats)  VERDICT: {p['verdict']}")
    L.append(_fmt("2022 (dir A)", p["a"]))
    L.append(_fmt("2023 (dir B)", p["b"]))
    n = res["null"]
    L += ["-" * 76, f"PLANTED-NULL [{_NULL_FEAT}]: verdict {n['verdict']}  REJECTS={res['null_rejects']}",
          _fmt("2022 (dir A)", n["a"]), _fmt("2023 (dir B)", n["b"])]
    L.append("  null rejected -> gate CAN fail a signal." if res["null_rejects"]
             else "  *** GATE UNTRUSTWORTHY: noise did NOT reject. ***")
    L += ["=" * 76,
          "CALIBRATION only; NO $/ROI/edge. vs-close UNPROVEN. REJECT = honest success.",
          "=" * 76]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate MLB SP-fatigue K-prop profile (proposal-only).")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    print(_report(run(eps=a.eps, seed=a.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_corpus", "score_corpus", "clustered_dm", "gate_corpus",
           "gate_both", "run", "main", "_PROFILE_FEATS", "_NULL_FEAT"]

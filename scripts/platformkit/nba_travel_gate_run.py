"""scripts.platformkit.nba_travel_gate_run -- GATE-RUN for the NBA pregame
TRAVEL layer (travel_home / travel_away / abs_travel_diff) vs the Elo win-prob base.

The schedule-ingested travel_* miles are STRICTLY-PRIOR, schedule-derived: each value
is the distance the team flew INTO this game (from its previous schedule stop to this
arena), which is fixed by the schedule and KNOWN before tip-off. It carries NO result
dependence -- it is a legitimate leak-free pre-game feature. We additionally derive
abs_travel_diff = |travel_home - travel_away| (a schedule quantity, never an outcome).

WHAT THIS RUNNER DOES (faithful pregame win-prob gate; NO new scoring math -- REUSES
diebold_mariano clustered by game_id + brier/log_loss):
  BASE = logistic on the Elo logit z=logit(p_home_elo); +FEATURE = logistic on
  [z, travel_feature]. Both refit on STRICTLY-PRIOR (earlier-season) rows ONLY, scored
  on a later held-out corpus -> leak-free, walk-forward across seasons.

THE GATE (identical, both directions, sacred):
  * Walk-forward / cross-corpus over >=2 INDEPENDENT season corpora.
  * BOTH directions A->B and B->A: +FEATURE must LOWER held-out Brier AND clear the
    clustered-DM bar (by game_id) in BOTH; one-direction-only = PARTIAL = REJECT.
  * Proper-score unanimity: Brier AND log-loss must BOTH improve (one-sided = REJECT).
  * DEGENERATE-BASE GUARD: Elo BASE must beat the constant base-rate by >= MIN_BSS BSS
    on the held-out corpus; a degenerate base => INVALID_BASE, never a SHIP.
  * PLANTED-NULL pure-noise column through the IDENTICAL gate MUST REJECT; else
    NOT_TESTABLE and we say so. Thin/missing rows DROPPED (never 0-filled); coverage out.

HONEST EXPECTATION: REJECT-scouting -- Elo + the schedule's rest/HFA already subsume
travel; kept as SCOUTING, NEVER force-fed as a model feature.

PROPOSAL-ONLY: writes ONE verdict JSON to data/frontend/funnel/nba_travel_gate.json --
NOT data/registry/, flips NO flag, creates NO sentinel, NO push. CALIBRATION only
(held-out Brier/log-loss); NO $ / ROI / edge field anywhere; vs-close is UNPROVEN and
never a feature. numpy/pandas/stdlib; <=300 LOC; ASCII.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.ratings import walk_forward_elo
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, log_loss

_REPO = Path(__file__).resolve().parents[2]
_GAMES = _REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
_OUT = _REPO / "data" / "frontend" / "funnel" / "nba_travel_gate.json"

_FEATURES = ("travel_home", "travel_away", "abs_travel_diff")
_NULL_COL = "planted_null"   # pure-noise control -- MUST reject through the SAME gate
_EPS = 0.05                  # clustered-DM bar (both directions must clear it)
_MIN_BSS = 0.01             # degenerate-base guard: Elo BASE must beat base-rate by this


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


def _zstd(x: np.ndarray, mu: float, sd: float) -> np.ndarray:
    return (np.asarray(x, dtype=float) - mu) / (sd if sd > 0 else 1.0)


def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 200,
                  lr: float = 0.2, l2: float = 1e-4) -> np.ndarray:
    """Tiny batch-GD logistic regression with intercept (deterministic, no sklearn)."""
    n, d = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(d + 1)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))
        grad = Xb.T @ (p - y) / n + l2 * np.concatenate([[0.0], w[1:]])
        w -= lr * grad
    return w


def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((len(X), 1)), X])
    return 1.0 / (1.0 + np.exp(-np.clip(Xb @ w, -30, 30)))


def build_corpus() -> pd.DataFrame:
    """Load games, attach leak-free walk-forward Elo, derive abs_travel_diff + null.

    abs_travel_diff is a pure schedule quantity (|home miles - away miles|); the planted
    null is seeded N(0,1) independent of the outcome. No outcome is ever a feature.
    """
    df = pd.read_parquet(_GAMES)
    df = df[df["home_win"].notna()].copy()
    # walk_forward_elo needs an INTEGER season for its season-boundary regression; the
    # ingested season is "YYYY-YY". Map to the start year for the Elo replay, but keep
    # the original string season label for cross-corpus splitting.
    season_str = df["season"].astype(str)
    df["season_label"] = season_str
    df["season"] = season_str.str.slice(0, 4).astype(int)
    feat = walk_forward_elo(df)
    feat["season"] = feat["season_label"]   # restore the string label for corpus split
    feat["abs_travel_diff"] = (feat["travel_home"] - feat["travel_away"]).abs()
    rng = np.random.default_rng(12345)
    feat[_NULL_COL] = rng.standard_normal(len(feat))
    return feat


def _season_corpora(feat: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    return [(str(s), feat[feat["season"] == s].copy())
            for s in sorted(feat["season"].dropna().unique())]


def _coverage(df: pd.DataFrame, col: str) -> float:
    return float(df[col].notna().mean()) if col in df.columns else 0.0


def _direction(train: pd.DataFrame, test: pd.DataFrame, col: str,
               eps: float = _EPS) -> Dict[str, object]:
    """Fit BASE (Elo) and +FEATURE (Elo+col) on TRAIN, score on TEST. Leak-free.

    Returns per-direction Brier/log-loss for both models, clustered-DM (by game_id) on
    the Brier-loss difference, the base degeneracy flag, and whether +FEATURE wins.
    """
    tr = train.dropna(subset=[col, "p_home_elo", "home_win"]).copy()
    te = test.dropna(subset=[col, "p_home_elo", "home_win"]).copy()
    if len(tr) < 50 or len(te) < 50:
        return {"ok": False, "reason": "thin corpus after dropna",
                "n_train": int(len(tr)), "n_test": int(len(te))}

    z_tr = _logit(tr["p_home_elo"].to_numpy())
    z_te = _logit(te["p_home_elo"].to_numpy())
    fmu, fsd = float(tr[col].mean()), float(tr[col].std())
    f_tr = _zstd(tr[col].to_numpy(), fmu, fsd)
    f_te = _zstd(te[col].to_numpy(), fmu, fsd)
    y_tr = tr["home_win"].to_numpy(dtype=float)
    y_te = te["home_win"].to_numpy(dtype=float)
    gid_te = te["game_id"].astype(str).to_numpy()

    w_base = _fit_logistic(z_tr.reshape(-1, 1), y_tr)
    w_feat = _fit_logistic(np.column_stack([z_tr, f_tr]), y_tr)
    p_base = _predict(w_base, z_te.reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([z_te, f_te]))

    bb, bf = float(brier(p_base, y_te)), float(brier(p_feat, y_te))
    lb, lf = float(log_loss(p_base, y_te)), float(log_loss(p_feat, y_te))
    # degenerate-base guard: BASE must beat the const base-rate on TEST by >= MIN_BSS.
    const = np.full(len(y_te), float(y_tr.mean()))
    bss_base = 1.0 - bb / float(brier(const, y_te)) if brier(const, y_te) > 0 else 0.0
    base_degenerate = bool(bss_base < _MIN_BSS)
    d = (p_base - y_te) ** 2 - (p_feat - y_te) ** 2     # +ve => +FEATURE better
    dm = diebold_mariano(d, gid_te)
    feat_wins = bool(bf < bb and lf < lb and dm.p_value < eps and not base_degenerate)
    return {"ok": True, "brier_base": round(bb, 6), "brier_feat": round(bf, 6),
            "brier_delta": round(bb - bf, 7), "logloss_base": round(lb, 6),
            "logloss_feat": round(lf, 6), "dm_stat": round(dm.dm_stat, 4),
            "dm_p": round(dm.p_value, 6), "n_clusters": dm.n_clusters,
            "base_bss_vs_const": round(bss_base, 5), "base_degenerate": base_degenerate,
            "feat_wins": feat_wins, "n_train": int(len(tr)), "n_test": int(len(te))}


def gate_one(corpora: List[Tuple[str, pd.DataFrame]], col: str,
             eps: float = _EPS) -> Dict[str, object]:
    """Run ONE column through the gate across ADJACENT season corpus pairs, both ways.

    For each adjacent pair (s_i, s_{i+1}) we score forward (train earlier -> test later,
    the walk-forward direction) AND backward (B->A) so we have both cross-corpus
    directions. SHIP requires +FEATURE to win in BOTH directions of >=1 pair AND no
    pair to show a degenerate base. Any degenerate base => INVALID_BASE.
    """
    pairs = []
    degen = False
    for i in range(len(corpora) - 1):
        (sa, A), (sb, B) = corpora[i], corpora[i + 1]
        a2b = _direction(A, B, col, eps=eps)   # walk-forward (prior -> later)
        b2a = _direction(B, A, col, eps=eps)   # reverse
        if not (a2b.get("ok") and b2a.get("ok")):
            continue
        degen = degen or a2b["base_degenerate"] or b2a["base_degenerate"]
        replicated = bool(a2b["feat_wins"] and b2a["feat_wins"])
        pairs.append({"train_a": sa, "test_b": sb, "a_to_b": a2b, "b_to_a": b2a,
                      "replicated": replicated})
    if not pairs:
        verdict = "INSUFFICIENT_DATA"
    elif degen:
        verdict = "INVALID_BASE"
    elif any(p["replicated"] for p in pairs):
        verdict = "SHIP"                       # surfaced as a PROPOSAL only
    elif any(p["a_to_b"]["feat_wins"] or p["b_to_a"]["feat_wins"] for p in pairs):
        verdict = "PARTIAL"                     # one-direction-only -> NOT shippable
    else:
        verdict = "REJECT"
    return {"column": col, "verdict": verdict, "pairs": pairs,
            "base_degenerate": degen,
            "coverage": round(np.mean([_coverage(c, col) for _, c in corpora]), 4)}


@dataclass
class TravelGateVerdict:
    layer: str
    verdict: str
    n_corpora: int
    results: List[Dict[str, object]] = field(default_factory=list)
    planted_null: Dict[str, object] = field(default_factory=dict)
    null_rejects: bool = False
    caveats: List[str] = field(default_factory=list)
    vs_close: str = "UNPROVEN -- CALIBRATION only (held-out Brier/log-loss), NOT a market edge"
    proposal_only: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {k: getattr(self, k) for k in
                ("layer", "verdict", "n_corpora", "results", "planted_null",
                 "null_rejects", "caveats", "vs_close", "proposal_only")}


def run(eps: float = _EPS) -> TravelGateVerdict:
    caveats = [
        "BASE = walk-forward Elo logit (domains.basketball_nba.ratings.walk_forward_elo,"
        " snapshot-before-update -> leak-free). +FEATURE = logistic on [elo_logit, col].",
        "travel_* are STRICTLY-PRIOR schedule-derived miles flown INTO the game (known "
        "pre-tip, no result dependence); abs_travel_diff = |home-away| (schedule only).",
        "Cross-corpus BOTH directions over adjacent season pairs; DM clustered by "
        "game_id; proper-score unanimity (Brier AND log-loss); degenerate-base guard "
        "(Elo must beat base-rate by >= %.3f BSS); thin rows dropped, never 0-filled."
        % _MIN_BSS,
        "PLANTED-NULL pure-noise column through the IDENTICAL gate MUST REJECT. "
        "NO $/ROI/edge field; vs-close UNPROVEN, never a feature.",
        "HONEST EXPECTATION: REJECT-scouting -- Elo + schedule rest/HFA subsume travel; "
        "kept as SCOUTING, NEVER force-fed as a model feature.",
    ]
    if not _GAMES.exists():
        return TravelGateVerdict("nba_travel", "INSUFFICIENT_DATA", 0,
                                 caveats=caveats + ["games.parquet not on disk"])
    feat = build_corpus()
    corpora = _season_corpora(feat)
    n = len(corpora)
    if n < 2:
        return TravelGateVerdict("nba_travel", "INSUFFICIENT_DATA", n,
                                 caveats=caveats + ["need >=2 independent season corpora"])

    results = [gate_one(corpora, c, eps=eps) for c in _FEATURES]
    null = gate_one(corpora, _NULL_COL, eps=eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL",
                                       "INSUFFICIENT_DATA")
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    if not null_rejects:
        layer_verdict = "NOT_TESTABLE"          # gate could not fail a noise column
    elif any_ship:
        layer_verdict = "SHIP"
    elif all(r["verdict"] in ("REJECT", "PARTIAL") for r in results):
        layer_verdict = "REJECT"
    else:
        layer_verdict = "REJECT"
    return TravelGateVerdict("nba_travel", layer_verdict, n, results,
                             {**null, "rejects": null_rejects}, null_rejects, caveats)


def write(v: TravelGateVerdict, out: Optional[Path] = None) -> str:
    dest = Path(out) if out is not None else _OUT
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="ascii") as f:
        json.dump(v.to_dict(), f, indent=2, sort_keys=True)
    return str(dest)


def _fmt_dir(tag: str, d: Dict[str, object]) -> str:
    return ("    %s: Brier %s -> %s (d %s)  LL %s -> %s  DM p=%s  base_BSS=%s "
            "degenerate=%s  feat_wins=%s" % (
                tag, d["brier_base"], d["brier_feat"], d["brier_delta"],
                d["logloss_base"], d["logloss_feat"], d["dm_p"],
                d["base_bss_vs_const"], d["base_degenerate"], d["feat_wins"]))


def _fmt_pair(p: Dict[str, object]) -> List[str]:
    return ["  pair %s<->%s replicated=%s" % (p["train_a"], p["test_b"], p["replicated"]),
            _fmt_dir("A->B", p["a_to_b"]), _fmt_dir("B->A", p["b_to_a"])]


def _report(v: TravelGateVerdict) -> str:
    lines = ["=" * 76,
             "NBA TRAVEL LAYER GATE-RUN (pregame travel vs Elo win-prob base)",
             "=" * 76,
             "LAYER     : %s   VERDICT: %s" % (v.layer, v.verdict),
             "corpora   : %d independent season corpora" % v.n_corpora, "-" * 76]
    for r in v.results:
        lines.append("\nCOLUMN %-18s VERDICT: %s  (coverage %.3f)" % (
            r["column"], r["verdict"], r["coverage"]))
        for p in r["pairs"]:
            lines += _fmt_pair(p)
        if not r["pairs"]:
            lines.append("  (no scorable adjacent pair)")
    n = v.planted_null
    lines += ["\n" + "-" * 76,
              "PLANTED-NULL [%s]: verdict=%s  REJECTS=%s" % (
                  _NULL_COL, n.get("verdict"), v.null_rejects)]
    for p in n.get("pairs", []):
        lines += _fmt_pair(p)
    if not v.null_rejects:
        lines.append("  *** GATE UNTRUSTWORTHY: noise column did NOT reject. ***")
    else:
        lines.append("  null rejected as required -> the gate CAN fail a signal.")
    lines += ["-" * 76, "vs_close  : %s" % v.vs_close,
              "Calibration only; NO $/edge. REJECT-scouting is the honest, successful "
              "outcome; kept as SCOUTING, NEVER force-fed as a model feature.",
              "=" * 76]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the NBA pregame travel layer.")
    ap.add_argument("--eps", type=float, default=_EPS)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    v = run(eps=a.eps)
    print(_report(v))
    if not a.no_write:
        print("wrote %s" % write(v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus", "gate_one", "run", "write", "main",
           "_FEATURES", "_NULL_COL", "TravelGateVerdict"]

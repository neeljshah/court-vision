"""scripts.platformkit.gate_run_soccer_espn28 -- GATE-RUN for the soccer ESPN-28 /
football-data DISCIPLINE+POSSESSION as-of layer as PREGAME win-prob candidates.

THE QUESTION: does adding a strictly-prior trailing EW discipline/possession-proxy
diff (corners / fouls / yellow / red / SoT-ratio, from
domains.soccer.asof_discipline_features) to a leak-free EW-Poisson win-prob BASE lower
held-out P(home win) Brier, REPLICATED across >=2 INDEPENDENT league corpora, with the
DM CLUSTERED by match (event_id), the degenerate-base guard, BOTH directions, AND a
PLANTED-NULL pure-noise column that MUST reject through the IDENTICAL gate?

IT CONSUMES the proven machinery (adds no new scoring trick):
  (a) leak-free load via the SINGLE train==inference builder build_asof_disc_frame
      (snapshot-before-update, prior-only EW, NaN debut), aligned 1:1 by event_id; a
      NaN row is DROPPED (we REFUSE to 0-fill a debut).
  (b) BASE = leak-free EW-Poisson p_poisson (domains.soccer.pregame_winprob; a
      Dixon-Coles-class EW attack/defense Poisson). The gate refits a walk-forward
      logistic BASE = sigma(a+b*logit(p_poisson)) vs sigma(...+c*feature) on TRAIN.
  (c) cross-corpus BOTH directions: disjoint league pairs ({E0,E1} and {SP1,I1});
      SHIP requires LOWER Brier AND DM<eps in BOTH (one-corpus-only = PARTIAL=REJECT).
  (d) degenerate-base guard (BSS>=MIN_BSS each corpus, else INVALID_BASE);
      (e) a PLANTED-NULL noise column through the IDENTICAL gate, which MUST REJECT.

The ESPN-28 native feed (offsides/saves/possessionPct) is reported INSUFFICIENT_DATA
honestly (~185 graded matches -- too few for a leak-free cross-corpus walk-forward);
its DENSE football-data discipline/possession-proxy mirror is what the gate tests.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, creates NO sentinel.
CALIBRATION only (held-out Brier) -- NO $/ROI/edge field; vs-close is a yardstick, never
a feature. ASCII; numpy/pandas; <=300 LOC. HONEST EXPECTATION: REJECT-scouting (team
strength subsumes possession/discipline), kept as SCOUTING, never force-fed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier
from domains.soccer.asof_discipline_features import build_asof_disc_frame
from domains.soccer.pregame_winprob import walk_forward

_REPO = Path(__file__).resolve().parents[2]
_MATCHES = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
_MATCH_STATS = _REPO / "data" / "domains" / "soccer" / "match_stats.parquet"
_ESPN28 = _REPO / "data" / "domains" / "soccer" / "espn_matchstats.parquet"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "soccer_espn28_gate.json"

# Two DISJOINT league pairs = the two independent cross-corpus directions.
_CORPUS_A = ("E0", "E1")     # English top two tiers
_CORPUS_B = ("SP1", "I1")    # Spain + Italy
_WARMUP = 100                # leak-free walk-forward warmup rows skipped from scoring
_MIN_BSS = 0.01              # degenerate-base guard: BASE must beat base-rate by this
_ESPN28_MIN = 1000           # rows the ESPN-28 native feed would need to be gateable

_FEATURE_COLS = ("diff_corners_asof", "diff_fouls_asof", "diff_yellow_asof",
                 "diff_red_asof", "diff_sot_ratio_asof")
_NULL_COL = "planted_null_diff"   # pure-noise control -- MUST reject


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 200,
                  lr: float = 0.1) -> np.ndarray:
    """Plain L2-free Newton-ish GD logistic (intercept + X cols). Deterministic,
    leak-free (only ever fed strictly-prior TRAIN rows by the caller)."""
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)
    for _ in range(iters):
        p = _sigmoid(Xb @ w)
        grad = Xb.T @ (p - y) / n
        w -= lr * grad
    return w


def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return _sigmoid(Xb @ w)


def _gate_corpus(df: pd.DataFrame, col: str, eps: float) -> Dict[str, object]:
    """Leak-free single chronological split on ONE corpus: fit BASE and BASE+feat on
    the first half (after warmup), score the held-out second half. Both fit on the
    SAME TRAIN rows -> leak-free, like-for-like. Returns Brier(base/feat), clustered-DM
    p (by event_id), feat_better, and the degenerate-base flag.
    """
    sub = df.iloc[_WARMUP:].dropna(subset=[col]).reset_index(drop=True)
    n = len(sub)
    nan = float("nan")
    if n < 200:
        return {"n": n, "brier_base": nan, "brier_feat": nan, "brier_delta": nan,
                "dm_p": 1.0, "feat_better": False, "base_bss_vs_baserate": 0.0,
                "base_degenerate": True, "reason": "too few covered rows"}
    tr, te = sub.iloc[:n // 2], sub.iloc[n // 2:]
    y_tr, y_te = tr["y_home"].to_numpy(float), te["y_home"].to_numpy(float)
    lp_tr = _logit(tr["p_poisson"].to_numpy(float))
    lp_te = _logit(te["p_poisson"].to_numpy(float))
    f_tr, f_te = tr[col].to_numpy(float), te[col].to_numpy(float)
    # standardize the feature on TRAIN stats only (no test peeking)
    mu, sd = float(f_tr.mean()), float(f_tr.std() or 1.0)
    fz_tr, fz_te = (f_tr - mu) / sd, (f_te - mu) / sd

    w_base = _fit_logistic(lp_tr.reshape(-1, 1), y_tr)
    w_feat = _fit_logistic(np.column_stack([lp_tr, fz_tr]), y_tr)
    p_base = _predict(w_base, lp_te.reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([lp_te, fz_te]))

    bb, bf = float(brier(p_base, y_te)), float(brier(p_feat, y_te))
    ybar = float(y_tr.mean())
    const = float(brier(np.full(len(y_te), ybar), y_te))
    base_bss = (1.0 - bb / const) if const > 0 else 0.0
    ids = te["event_id"].astype(str).tolist()
    d = (p_base - y_te) ** 2 - (p_feat - y_te) ** 2   # +ve => feat beats base
    dm = diebold_mariano(d, ids)
    return {
        "n": int(n), "n_test": int(len(te)),
        "brier_base": round(bb, 6), "brier_feat": round(bf, 6),
        "brier_delta": round(bb - bf, 7),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "feat_better": bool(bf < bb),
        "base_bss_vs_baserate": round(base_bss, 5),
        "base_degenerate": bool(base_bss < _MIN_BSS),
    }


def _build_corpus(divs: Sequence[str], matches: pd.DataFrame,
                  match_stats: pd.DataFrame, layer: pd.DataFrame,
                  seed: int) -> pd.DataFrame:
    """EW-Poisson base (walk-forward per league, pooled chronologically) + as-of diffs
    + a planted-null noise column, joined leak-free by event_id."""
    g = matches[matches["div"].isin(divs)].copy()
    ms = match_stats[match_stats["div"].isin(divs)] if "div" in match_stats.columns else match_stats
    wf = walk_forward(g, ms)
    wf["event_id"] = wf["event_id"].astype(str)
    keep = ["event_id", *[c for c in _FEATURE_COLS if c in layer.columns]]
    merged = wf.merge(layer[keep], on="event_id", how="left")
    rng = np.random.default_rng(seed)
    merged[_NULL_COL] = rng.standard_normal(len(merged))
    return merged.sort_values(["date", "div", "home_team", "away_team"],
                              kind="mergesort").reset_index(drop=True)


def _coverage(df: pd.DataFrame, col: str) -> float:
    return float(df[col].notna().mean()) if col in df.columns else 0.0


def gate_one(corp_a: pd.DataFrame, corp_b: pd.DataFrame, col: str,
             eps: float) -> Dict[str, object]:
    """Run ONE column through the gate on BOTH corpora; replication verdict."""
    a = _gate_corpus(corp_a, col, eps)
    b = _gate_corpus(corp_b, col, eps)
    degen = bool(a["base_degenerate"] or b["base_degenerate"])
    a_wins = bool(a["feat_better"] and a["dm_p"] < eps)
    b_wins = bool(b["feat_better"] and b["dm_p"] < eps)
    if degen:
        verdict = "INVALID_BASE"
    elif a_wins and b_wins:
        verdict = "SHIP"
    elif a_wins or b_wins:
        verdict = "PARTIAL"
    else:
        verdict = "REJECT"
    return {"column": col, "verdict": verdict, "corpus_a": a, "corpus_b": b,
            "a_wins": a_wins, "b_wins": b_wins, "base_degenerate": degen,
            "cov_a": _coverage(corp_a, col), "cov_b": _coverage(corp_b, col)}


def _espn28_status() -> Dict[str, object]:
    """Honest INSUFFICIENT_DATA report on the ESPN-28 native feed."""
    if not _ESPN28.exists():
        return {"present": False, "n_rows": 0, "verdict": "INSUFFICIENT_DATA",
                "reason": "espn_matchstats.parquet absent"}
    n = len(pd.read_parquet(_ESPN28))
    ok = n >= _ESPN28_MIN
    return {"present": True, "n_rows": int(n), "min_required": _ESPN28_MIN,
            "verdict": "OK" if ok else "INSUFFICIENT_DATA",
            "reason": ("" if ok else f"only {n} graded ESPN-28 matches (< {_ESPN28_MIN}); "
                       "too few for a leak-free cross-corpus walk-forward -- the dense "
                       "football-data discipline/possession mirror is gated instead")}


def run(eps: float = 0.05, seed: int = 0,
        matches: Optional[pd.DataFrame] = None,
        match_stats: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """Build both league-pair corpora once, gate every as-of diff + the planted null,
    report the ESPN-28 native-feed data status, write the verdict JSON."""
    if matches is None:
        matches = pd.read_parquet(_MATCHES)
    if match_stats is None:
        match_stats = pd.read_parquet(_MATCH_STATS)
    matches = matches.copy()
    matches["event_id"] = matches["event_id"].astype(str)

    layer = build_asof_disc_frame(match_stats)
    layer["event_id"] = layer["event_id"].astype(str)

    corp_a = _build_corpus(_CORPUS_A, matches, match_stats, layer, seed)
    corp_b = _build_corpus(_CORPUS_B, matches, match_stats, layer, seed + 1)

    results = [gate_one(corp_a, corp_b, c, eps) for c in _FEATURE_COLS]
    null = gate_one(corp_a, corp_b, _NULL_COL, eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")

    any_ship = any(r["verdict"] == "SHIP" for r in results)
    base_ok = not any(r["base_degenerate"] for r in results)
    if not null_rejects:
        layer_verdict = "NOT_TESTABLE"
    elif not base_ok:
        layer_verdict = "INVALID_BASE"
    elif any_ship:
        layer_verdict = "SHIP"             # surfaced PROPOSAL-only, never force-fed
    else:
        layer_verdict = "REJECT"

    out = {
        "layer": "soccer_espn28_discipline_possession_asof",
        "verdict": layer_verdict, "n_corpora": 2, "eps": eps,
        "corpus_a_divs": list(_CORPUS_A), "corpus_b_divs": list(_CORPUS_B),
        "base": "ew_poisson_p_home (pregame_winprob; Dixon-Coles-class EW Poisson)",
        "base_skillful": base_ok,
        "design": "leak-free walk-forward logistic (BASE=logit(p_poisson), +feature "
                  "refit on TRAIN), DM clustered by event_id, degenerate guard, "
                  "cross-corpus BOTH directions over 2 disjoint league pairs, planted-null",
        "results": results, "null": null, "null_rejects": null_rejects,
        "espn28_native_feed": _espn28_status(),
        "proposal_only": True, "force_fed": False,
        "scouting_only": (layer_verdict != "SHIP"),
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge",
        "caveats": [
            "Any SHIP here is a single-fold (50/50 chronological split) per corpus + "
            "2 corpora -- a PROPOSAL kept as SCOUTING; promotion still needs nested-CV "
            "+ seed-ensemble. Never force-fed; no flag/registry/sentinel touched.",
            "Honest prior: discipline/possession largely subsumed by attack/defense "
            "strength; possession is a crude SoT-ratio proxy (no possessionPct on disk).",
            "ESPN-28 native feed (offsides/saves/possessionPct) is INSUFFICIENT_DATA "
            "(~185 rows); the dense football-data mirror is gated. NO $/ROI/edge anywhere.",
        ],
    }
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_VERDICT_OUT, "w", encoding="ascii") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    return out


def _fmt(tag: str, d: Dict[str, object]) -> str:
    return (f"  {tag}: Brier base {d['brier_base']} -> feat {d['brier_feat']}  "
            f"(delta {d.get('brier_delta')})  DM p={d['dm_p']}  "
            f"better={d['feat_better']}  base_BSS={d['base_bss_vs_baserate']}  "
            f"degenerate={d['base_degenerate']}")


def _report(res: Dict[str, object]) -> str:
    e = res["espn28_native_feed"]
    lines = ["=" * 78, "SOCCER ESPN-28 / DISCIPLINE+POSSESSION AS-OF GATE-RUN", "=" * 78,
             f"LAYER   : {res['layer']}",
             f"VERDICT : {res['verdict']}   corpora: {res['n_corpora']} "
             f"({'/'.join(res['corpus_a_divs'])} vs {'/'.join(res['corpus_b_divs'])})",
             f"base_skillful : {res['base_skillful']}    "
             f"ESPN-28 feed: {e['verdict']} (n={e['n_rows']})", "-" * 78]
    for r in list(res["results"]) + [res["null"]]:
        tag = "NULL " if r["column"] == _NULL_COL else "COL  "
        lines.append(f"\n{tag}{r['column']:<22} VERDICT: {r['verdict']}"
                     f"  (cov A {r['cov_a']:.2f} / B {r['cov_b']:.2f})")
        lines += [_fmt("A (E0/E1)  ", r["corpus_a"]), _fmt("B (SP1/I1) ", r["corpus_b"])]
    lines += ["\nnull rejected -> gate CAN fail a signal." if res["null_rejects"]
              else "\n*** GATE UNTRUSTWORTHY: noise did NOT reject. ***",
              "=" * 78, "Calibration only; NO $/edge. Nothing rejected is force-fed.",
              "=" * 78]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate the soccer ESPN-28/discipline+possession as-of layer.")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed)
    print(_report(res))
    print(f"wrote {_VERDICT_OUT}")
    return 0


__all__ = ["run", "gate_one", "_build_corpus", "_gate_corpus", "main",
           "_FEATURE_COLS", "_NULL_COL"]

if __name__ == "__main__":
    raise SystemExit(main())

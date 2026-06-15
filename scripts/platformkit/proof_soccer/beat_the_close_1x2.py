"""scripts.platformkit.proof_soccer.beat_the_close_1x2 — soccer 1X2 beat-the-close.

Mirrors proof_nba.ml_accuracy: a leak-free walk-forward model vs the DEVIGGED
closing line, scored on a held-out second half. NBA does win-prob (binary Brier);
here the market is 3-way (home / draw / away), so the metric is the MULTICLASS
Brier = sum over the 3 outcomes of (p - y)^2 (Brier's original definition; range
0..2). "Beat the close" = lower multiclass Brier than the devigged 3-way close on
the SAME realized outcomes. Markets are efficient, so a MATCH within sampling noise
is the realistic best case.

The model: leak-free EW-Poisson goals lambdas (domains.soccer.ratings) ->
Dixon-Coles scoreline matrix (domains.soccer.scoreline_engine) with a walk-forward
DC rho (domains.soccer.rho_fit) -> 1X2 probabilities read off the matrix.

Leak-free: lambdas/rho are strictly pre-match (the walk_forward_* helpers snapshot
before folding each result in); the closing line is ONLY the comparison forecaster,
NEVER a model input.

HONEST DATA FINDING: data/domains/soccer/odds.parquet is O/U-2.5-ONLY (over/under
decimal odds for pinnacle/avg/b365/max, open+close). There are NO 1X2 closing odds
(no PSCH/PSCD/PSCA, no AvgCH/AvgCD/AvgCA, no home/draw/away price columns) anywhere
in the corpus. So the close cannot be devigged for 1X2 and the comparison cannot be
run on this corpus -> run() returns ok=False with that explanation. This is an
honest finding, not a failure: the full leak-free 1X2 model below would execute the
moment 3-way closing odds are ingested. No $ edge claimed.

INVARIANTS: never edit src/ or kernel/; <=300 LOC.
Run: python -m scripts.platformkit.proof_soccer.beat_the_close_1x2
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Candidate 1X2 closing-odds column triples (decimal odds), in priority order.
# Pinnacle close (PSC*), then market average close (AvgC*), then Bet365 close (B365C*),
# then market max close (MaxC*) — the standard football-data.co.uk 1X2 close fields.
_TRIPLES: Tuple[Tuple[str, str, str], ...] = (
    ("psch", "pscd", "psca"),
    ("avgch", "avgcd", "avgca"),
    ("b365ch", "b365cd", "b365ca"),
    ("maxch", "maxcd", "maxca"),
    ("close_home", "close_draw", "close_away"),
    ("c_home", "c_draw", "c_away"),
)


def _find_1x2_triple(cols) -> Optional[Tuple[str, str, str]]:
    """Return the first present (home, draw, away) decimal-odds CLOSE triple, else None."""
    lower = {c.lower(): c for c in cols}
    for h, d, a in _TRIPLES:
        if h in lower and d in lower and a in lower:
            return lower[h], lower[d], lower[a]
    return None


def _devig_3way(oh: np.ndarray, od: np.ndarray, oa: np.ndarray) -> np.ndarray:
    """Normalize 1/odds across H/D/A -> (N,3) implied probabilities, vig removed."""
    ih, idd, ia = 1.0 / oh, 1.0 / od, 1.0 / oa
    s = ih + idd + ia
    return np.column_stack([ih / s, idd / s, ia / s])


def _multiclass_brier(p: np.ndarray, y: np.ndarray) -> float:
    """Brier (original 3-class): mean over samples of sum_k (p_k - y_k)^2. y is one-hot."""
    return float(np.mean(np.sum((p - y) ** 2, axis=1)))


def _model_1x2_probs(matches_df) -> np.ndarray:
    """Leak-free walk-forward 1X2 probabilities from the EW-Poisson + DC engine.

    Returns (N,3) [P(home), P(draw), P(away)] aligned to walk_forward_goals' output
    row order (chronological). Pre-match lambdas snapshot before each result is folded
    in; rho is fit strictly on prior matches.
    """
    from domains.soccer.ratings import walk_forward_goals
    from domains.soccer.rho_fit import walk_forward_rho
    from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix

    wf = walk_forward_goals(matches_df)
    lam_h = wf["lam_home"].to_numpy(float)
    lam_a = wf["lam_away"].to_numpy(float)
    fthg = wf["fthg"].to_numpy(float)
    ftag = wf["ftag"].to_numpy(float)
    rho = walk_forward_rho(lam_h, lam_a, fthg, ftag)

    probs = np.empty((len(wf), 3), dtype=float)
    for i in range(len(wf)):
        P = scoreline_matrix(lam_h[i], lam_a[i], rho=float(rho[i]))
        m = markets_from_matrix(P)
        probs[i] = (m["1X2_home"], m["1X2_draw"], m["1X2_away"])
    return probs, wf


def run() -> Dict:
    import pandas as pd

    odds_path = _REPO / "data" / "domains" / "soccer" / "odds.parquet"
    matches_path = _REPO / "data" / "domains" / "soccer" / "matches.parquet"
    if not odds_path.exists():
        return {"ok": False, "status": "no_data",
                "error": f"soccer odds parquet not found at {odds_path}"}

    odds = pd.read_parquet(odds_path)
    triple = _find_1x2_triple(odds.columns)
    if triple is None:
        # HONEST FINDING — the corpus has only O/U-2.5 closing odds, no 1X2 close.
        return {
            "ok": False,
            "status": "no_1x2_close",
            "error": (
                "data/domains/soccer/odds.parquet is O/U-2.5-ONLY (columns are "
                "over/under decimal odds: ou_*/p*/avg*/b365*/max*, open+close). "
                "There are NO 1X2 (home/draw/away) closing-odds columns anywhere in "
                "the soccer corpus (no PSCH/PSCD/PSCA, no AvgCH/AvgCD/AvgCA, no "
                "B365C/MaxC 1X2 triple), so the 3-way close cannot be devigged and "
                "the beat-the-close comparison cannot be run. Honest finding, not a "
                "failure: the leak-free EW-Poisson + Dixon-Coles 1X2 model in this "
                "module runs unchanged once 1X2 closing odds are ingested. "
                "No $ edge claimed."
            ),
            "odds_columns": list(map(str, odds.columns)),
        }

    # ---- 1X2 closing odds ARE present: run the full comparison. ----
    oh_c, od_c, oa_c = triple
    matches = pd.read_parquet(matches_path)
    if "ftr" not in matches.columns:
        return {"ok": False, "status": "no_outcomes",
                "error": "matches.parquet lacks 'ftr' (H/D/A) realized outcomes."}

    probs, wf = _model_1x2_probs(matches)
    wf = wf.reset_index(drop=True)
    wf["p_h"], wf["p_d"], wf["p_a"] = probs[:, 0], probs[:, 1], probs[:, 2]

    # Join model rows (keyed by event_id) to the closing odds.
    key = "event_id" if ("event_id" in wf.columns and "event_id" in odds.columns) else None
    if key is None:
        return {"ok": False, "status": "no_join_key",
                "error": "no shared 'event_id' to align model rows to closing odds."}
    od_sub = odds[[key, oh_c, od_c, oa_c]].dropna()
    m = wf.merge(od_sub, on=key, how="inner").reset_index(drop=True)
    m = m[m["ftr"].isin(["H", "D", "A"])].reset_index(drop=True)
    n = len(m)
    if n < 200:
        return {"ok": False, "status": "data_limited", "n": int(n),
                "error": f"only {n} matches with both a model row and 1X2 close."}

    y = np.zeros((n, 3), dtype=float)
    ftr = m["ftr"].to_numpy()
    y[ftr == "H", 0] = 1.0
    y[ftr == "D", 1] = 1.0
    y[ftr == "A", 2] = 1.0

    p_model = m[["p_h", "p_d", "p_a"]].to_numpy(float)
    p_close = _devig_3way(m[oh_c].to_numpy(float), m[od_c].to_numpy(float),
                          m[oa_c].to_numpy(float))

    # Held-out second half (model warms up on the first half; chronological order).
    mid = n // 2
    te = slice(mid, n)
    model_metric = round(_multiclass_brier(p_model[te], y[te]), 4)
    close_metric = round(_multiclass_brier(p_close[te], y[te]), 4)
    gap = round(model_metric - close_metric, 4)  # >0 => market sharper

    if gap < -0.003:
        verdict = (f"BEATS: model multiclass Brier {model_metric} < close {close_metric} "
                   f"(gap {gap:+}); inspect for leak before trusting")
    elif gap <= 0.01:
        verdict = (f"MATCH: model {model_metric} vs close {close_metric} (gap {gap:+}) "
                   f"within noise on an efficient 3-way market")
    else:
        verdict = (f"BEHIND: close sharper by {gap} multiclass Brier "
                   f"({model_metric} vs {close_metric})")

    return {
        "ok": True,
        "status": "ok",
        "n": int(n - mid),
        "n_total": int(n),
        "metric_name": "multiclass_brier_1x2",
        "model_metric": model_metric,
        "close_metric": close_metric,
        "gap": gap,
        "close_columns": [oh_c, od_c, oa_c],
        "verdict": verdict,
        "note": "1X2 calibration vs the devigged 3-way close on real outcomes. No $ edge claimed.",
    }


def _main() -> int:
    rep = run()
    if not rep.get("ok"):
        print(f"[{rep.get('status')}] {rep.get('error')}")
        return 0
    print(f"=== Soccer 1X2: model vs the devigged close "
          f"(holdout n={rep['n']} of {rep['n_total']}) ===")
    print(f"  {'predictor':>12}  {'multiclass Brier':>16}")
    print(f"  {'devig close':>12}  {rep['close_metric']:>16}")
    print(f"  {'our engine':>12}  {rep['model_metric']:>16}")
    print(f"\nclose cols: {rep['close_columns']}  |  gap (model-close): {rep['gap']:+}")
    print(f"VERDICT: {rep['verdict']}")
    print(rep["note"])
    return 0


if __name__ == "__main__":
    sys.exit(_main())

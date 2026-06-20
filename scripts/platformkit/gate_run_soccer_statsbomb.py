"""scripts.platformkit.gate_run_soccer_statsbomb -- GATE-RUN for the StatsBomb REAL
EVENT-LEVEL as-of layer (real shot xG, pressures, passes) as PREGAME win-prob AND
IN-GAME win-prob candidates, vs a goals-based base.

THE QUESTION (two heads, identical gate): (PREGAME) does a strictly-prior trailing
REAL-xG diff lower held-out P(home win) Brier OVER a goals-based EW-Poisson
(Dixon-Coles-class) BASE? (IN-GAME) does the AS-OF cumulative REAL-xG diff (folded BY
MINUTE, never the final total) lower it OVER a goal-diff in-game BASE? Each REPLICATED
across 2 INDEPENDENT corpora (A = Premier League 2015/16 men; B = FA Women's Super
League pooled), DM CLUSTERED by match_id, degenerate-base guard, BOTH directions, AND a
PLANTED-NULL that MUST reject through the IDENTICAL gate. The ESPN location xG-PROXY
already REJECTED; this tests the REAL StatsBomb xG -- the most credible candidate to
improve CALIBRATION over a goals-only base.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, creates NO sentinel. A
gate-REJECTED column is kept as SCOUTING, never force-fed. CALIBRATION only (held-out
Brier) -- NO $/ROI/edge field; vs-close UNPROVEN, never a feature. ASCII; <=300 LOC.
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

_REPO = Path(__file__).resolve().parents[2]
_CACHE = _REPO / "data" / "cache" / "statsbomb"
_INGAME = _CACHE / "asof_ingame.parquet"
_PREGAME = _CACHE / "asof_pregame.parquet"
_META = _CACHE / "match_meta.parquet"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "soccer_statsbomb_gate.json"

_WARMUP = 30          # leak-free warmup matches skipped (priors warming up)
_MIN_BSS = 0.01       # degenerate-base guard
_NULL_COL = "planted_null"


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1.0 - p))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def _fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 400,
                  lr: float = 0.2) -> np.ndarray:
    n, k = X.shape
    Xb = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)
    for _ in range(iters):
        p = _sigmoid(Xb @ w)
        w -= lr * (Xb.T @ (p - y) / n)
    return w


def _predict(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return _sigmoid(Xb @ w)


def _ew_poisson_base(meta: pd.DataFrame) -> pd.DataFrame:
    """Leak-free goals-based EW-Poisson (Dixon-Coles-class) home-win prob per match.
    Per-team strictly-prior expanding attack (goals-for) and defense (goals-against)
    means + a home-field constant; p_home from a Poisson-diff score grid. Debut team
    -> league-average fallback (NOT a future leak)."""
    m = meta.sort_values("match_date").reset_index(drop=True)
    atk: Dict[str, list] = {}
    dfn: Dict[str, list] = {}
    gf_all = []
    rows = []
    for _, r in m.iterrows():
        h, a = r["home_team"], r["away_team"]
        # League means (strictly-prior); avoid divide-by-zero with a soft floor.
        lg = max(0.4, np.mean(gf_all)) if gf_all else 1.35
        # Multiplicative Dixon-Coles-class strengths relative to the league mean:
        # attack = team's prior goals-FOR / lg ; defense = goals-AGAINST / lg.
        def _str(d: dict, t: str, default: float) -> float:
            v = np.mean(d.get(t, [])) if d.get(t) else None
            return (v / lg) if v is not None else default
        h_atk, a_atk = _str(atk, h, 1.0), _str(atk, a, 1.0)
        h_def, a_def = _str(dfn, h, 1.0), _str(dfn, a, 1.0)
        lam_h = max(0.15, lg * h_atk * a_def * 1.15)   # *1.15 home edge
        lam_a = max(0.15, lg * a_atk * h_def * 0.92)
        p_home = _poisson_home_win(lam_h, lam_a)
        rows.append({"match_id": str(r["match_id"]), "p_poisson": p_home,
                     "y_home": 1.0 if r["home_score"] > r["away_score"] else 0.0,
                     "date": r["match_date"]})
        # update AFTER scoring (snapshot-before-update)
        atk.setdefault(h, []).append(r["home_score"]); dfn.setdefault(h, []).append(r["away_score"])
        atk.setdefault(a, []).append(r["away_score"]); dfn.setdefault(a, []).append(r["home_score"])
        gf_all += [r["home_score"], r["away_score"]]
    return pd.DataFrame(rows)


def _poisson_home_win(lam_h: float, lam_a: float, k: int = 10) -> float:
    from math import exp, factorial
    ph = np.array([exp(-lam_h) * lam_h ** i / factorial(i) for i in range(k)])
    pa = np.array([exp(-lam_a) * lam_a ** j / factorial(j) for j in range(k)])
    grid = np.outer(ph, pa)
    return float(np.tril(grid, -1).sum())  # home goals > away goals


def _gate_corpus(df: pd.DataFrame, col: str, eps: float) -> Dict[str, object]:
    """Leak-free chronological 50/50 split: fit BASE=sigma(a+b*logit(p_base)) and
    BASE+feature on TRAIN, score held-out TEST. Clustered-DM by match_id. The base
    travels with its row via the `p_base` column so the feature-NaN dropna (debuts)
    cannot misalign base from outcome. `df` carries p_base/y_home/match_id/date/col."""
    sub = df.dropna(subset=[col, "p_base"]).sort_values("date").reset_index(drop=True)
    n = len(sub)
    nan = float("nan")
    if n < 120:
        return {"n": n, "brier_base": nan, "brier_feat": nan, "brier_delta": nan,
                "dm_p": 1.0, "feat_better": False, "base_bss_vs_baserate": 0.0,
                "base_degenerate": True, "reason": "too few covered rows"}
    bl = _logit(sub["p_base"].to_numpy(float))
    tr, te = slice(0, n // 2), slice(n // 2, n)
    y = sub["y_home"].to_numpy(float)
    f = sub[col].to_numpy(float)
    mu, sd = float(f[tr].mean()), float(f[tr].std() or 1.0)
    fz = (f - mu) / sd
    w_base = _fit_logistic(bl[tr].reshape(-1, 1), y[tr])
    w_feat = _fit_logistic(np.column_stack([bl[tr], fz[tr]]), y[tr])
    p_base = _predict(w_base, bl[te].reshape(-1, 1))
    p_feat = _predict(w_feat, np.column_stack([bl[te], fz[te]]))
    yte = y[te]
    bb, bf = float(brier(p_base, yte)), float(brier(p_feat, yte))
    ybar = float(y[tr].mean())
    const = float(brier(np.full(len(yte), ybar), yte))
    base_bss = (1.0 - bb / const) if const > 0 else 0.0
    ids = sub["match_id"].astype(str).to_numpy()[te]
    d = (p_base - yte) ** 2 - (p_feat - yte) ** 2
    dm = diebold_mariano(d, ids)
    return {"n": int(n), "n_test": int(len(yte)),
            "brier_base": round(bb, 6), "brier_feat": round(bf, 6),
            "brier_delta": round(bb - bf, 7),
            "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
            "feat_better": bool(bf < bb),
            "base_bss_vs_baserate": round(base_bss, 5),
            "base_degenerate": bool(base_bss < _MIN_BSS)}


def gate_one(a_df: pd.DataFrame, b_df: pd.DataFrame, col: str,
             eps: float) -> Dict[str, object]:
    a = _gate_corpus(a_df, col, eps)
    b = _gate_corpus(b_df, col, eps)
    degen = bool(a["base_degenerate"] or b["base_degenerate"])
    a_wins = bool(a["feat_better"] and a["dm_p"] < eps)
    b_wins = bool(b["feat_better"] and b["dm_p"] < eps)
    verdict = ("INVALID_BASE" if degen else "SHIP" if (a_wins and b_wins)
               else "PARTIAL" if (a_wins or b_wins) else "REJECT")
    return {"column": col, "verdict": verdict, "corpus_a": a, "corpus_b": b,
            "a_wins": a_wins, "b_wins": b_wins, "base_degenerate": degen}


def _pregame_frame(meta: pd.DataFrame, pre: pd.DataFrame, corpus: str,
                   seed: int) -> pd.DataFrame:
    """Goals-Poisson base + real-xG prior diff feature, leak-free by match_id."""
    mm = meta[meta["corpus"] == corpus].copy()
    base = _ew_poisson_base(mm)
    p = pre[pre["corpus"] == corpus].copy()
    p["match_id"] = p["match_id"].astype(str)
    p["xg_prior_diff"] = (p["home_prior_xg_for"] - p["home_prior_xg_against"]
                          ) - (p["away_prior_xg_for"] - p["away_prior_xg_against"])
    p["shot_prior_diff"] = p["home_prior_shots"] - p["away_prior_shots"]
    df = base.merge(p[["match_id", "xg_prior_diff", "shot_prior_diff"]],
                    on="match_id", how="left")
    df["p_base"] = df["p_poisson"]   # base travels with its row through any dropna
    df = df.sort_values("date").reset_index(drop=True).iloc[_WARMUP:].reset_index(drop=True)
    rng = np.random.default_rng(seed)
    df[_NULL_COL] = rng.standard_normal(len(df))
    return df


def _ingame_frame(meta: pd.DataFrame, ing: pd.DataFrame, corpus: str,
                  minute: int, seed: int) -> pd.DataFrame:
    """Goal-diff in-game base (logit of a goal-diff->winprob map) + as-of real-xG diff
    feature, at a fixed minute snapshot, leak-free by match_id."""
    ids = set(meta[meta["corpus"] == corpus]["match_id"].astype(str))
    g = ing[(ing["minute"] == minute) & (ing["match_id"].isin(ids))].copy()
    yh = meta.assign(match_id=meta["match_id"].astype(str)).set_index("match_id")
    g["y_home"] = g["match_id"].map(
        lambda mid: 1.0 if yh.loc[mid, "home_score"] > yh.loc[mid, "away_score"] else 0.0)
    g["date"] = g["match_id"].map(yh["match_date"])
    # base = a monotone goal-diff -> win-prob (a sane in-game base); refit on TRAIN
    g["p_base"] = _sigmoid(0.7 * g["goal_diff_asof"].to_numpy(float))
    g = g.sort_values("date").reset_index(drop=True)
    rng = np.random.default_rng(seed)
    g[_NULL_COL] = rng.standard_normal(len(g))
    return g


def run(eps: float = 0.05, seed: int = 0, ingame_minute: int = 60) -> Dict[str, object]:
    meta = pd.read_parquet(_META)
    pre = pd.read_parquet(_PREGAME)
    ing = pd.read_parquet(_INGAME)

    # PREGAME head: real-xG prior diff vs goals-Poisson base
    pa = _pregame_frame(meta, pre, "A", seed)
    pb = _pregame_frame(meta, pre, "B", seed + 1)
    pre_results = [gate_one(pa, pb, c, eps)
                   for c in ("xg_prior_diff", "shot_prior_diff")]
    pre_null = gate_one(pa, pb, _NULL_COL, eps)

    # IN-GAME head: as-of real-xG diff vs goal-diff base
    ia = _ingame_frame(meta, ing, "A", ingame_minute, seed + 2)
    ib = _ingame_frame(meta, ing, "B", ingame_minute, seed + 3)
    ing_results = [gate_one(ia, ib, c, eps)
                   for c in ("xg_diff_asof", "shot_diff_asof", "press_diff_asof")]
    ing_null = gate_one(ia, ib, _NULL_COL, eps)

    null_rejects = all(n["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")
                       for n in (pre_null, ing_null))
    all_res = pre_results + ing_results
    base_ok = not any(r["base_degenerate"] for r in all_res)
    any_ship = any(r["verdict"] == "SHIP" for r in all_res)
    layer_verdict = ("NOT_TESTABLE" if not null_rejects else
                     "INVALID_BASE" if not base_ok else
                     "SHIP" if any_ship else "REJECT")

    out = {
        "layer": "soccer_statsbomb_real_xg_event_asof",
        "verdict": layer_verdict, "n_corpora": 2, "eps": eps,
        "ingame_minute": ingame_minute,
        "corpus_a": "Premier League 2015/16 (men)", "corpus_b": "FA WSL pooled (women)",
        "corpus_a_matches": int((meta["corpus"] == "A").sum()),
        "corpus_b_matches": int((meta["corpus"] == "B").sum()),
        "base_pregame": "goals-based EW-Poisson (Dixon-Coles-class) home-win prob",
        "base_ingame": "goal-diff -> win-prob (monotone), refit logistic on TRAIN",
        "base_skillful": base_ok,
        "design": "leak-free chronological 50/50 logistic refit (BASE vs BASE+feature), "
                  "DM clustered by match_id, degenerate guard, cross-corpus BOTH "
                  "directions over 2 independent leagues, planted-null identical gate",
        "pregame_results": pre_results, "pregame_null": pre_null,
        "ingame_results": ing_results, "ingame_null": ing_null,
        "null_rejects": null_rejects,
        "real_statsbomb_xg": "shot.statsbomb_xg (REAL, not a location proxy)",
        "proposal_only": True, "force_fed": False,
        "scouting_only": (layer_verdict != "SHIP"),
        "vs_close": "UNPROVEN -- CALIBRATION only (held-out home-win Brier), not edge",
        "no_dollar_field": True,
        "caveats": [
            "Any SHIP is a single chronological split per corpus x 2 corpora -- a "
            "PROPOSAL kept as SCOUTING, never force-fed; promotion needs nested-CV + "
            "seed-ensemble. NO flag/registry/sentinel touched.",
            "Corpora are small (~190 + ~190 matches); thin pregame base BSS expected. "
            "REJECT-leaning for the close is the honest expectation; real xG is the most "
            "credible CALIBRATION candidate. NO $/ROI/edge anywhere.",
            "as-of in-game xG folded BY MINUTE (minute<=t), never the match-final total; "
            "the goal outcome is the LABEL only; the close is never a feature.",
        ],
    }
    _VERDICT_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(_VERDICT_OUT, "w", encoding="ascii") as f:
        json.dump(out, f, indent=2, sort_keys=True)
    return out


def _fmt(tag: str, d: Dict[str, object]) -> str:
    return (f"  {tag}: Brier base {d['brier_base']} -> feat {d['brier_feat']} "
            f"(d {d.get('brier_delta')}) DM p={d['dm_p']} better={d['feat_better']} "
            f"BSS={d['base_bss_vs_baserate']} degen={d['base_degenerate']}")


def _report(res: Dict[str, object]) -> str:
    L = ["=" * 78, "SOCCER STATSBOMB REAL-xG / EVENT AS-OF GATE-RUN", "=" * 78,
         f"VERDICT : {res['verdict']}  corpora: {res['corpus_a_matches']}A / "
         f"{res['corpus_b_matches']}B  base_skillful={res['base_skillful']}", "-" * 78]
    for head, key in (("PREGAME (real-xG prior diff vs goals-Poisson):", "pregame"),
                      (f"IN-GAME @min {res['ingame_minute']} (as-of xG vs goal-diff):",
                       "ingame")):
        L.append(head)
        for r in list(res[f"{key}_results"]) + [res[f"{key}_null"]]:
            L += [f"  {r['column']:<18} {r['verdict']}",
                  _fmt("A", r["corpus_a"]), _fmt("B", r["corpus_b"])]
    L += ["\nnull rejected -> gate CAN fail a signal." if res["null_rejects"]
          else "\n*** GATE UNTRUSTWORTHY: noise did NOT reject. ***",
          "Calibration only; NO $/edge. Nothing rejected is force-fed.", "=" * 78]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Gate the StatsBomb real-xG/event as-of layer.")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--minute", type=int, default=60)
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed, ingame_minute=a.minute)
    print(_report(res))
    print(f"wrote {_VERDICT_OUT}")
    return 0


__all__ = ["run", "gate_one", "_gate_corpus", "_ew_poisson_base", "main", "_NULL_COL"]

if __name__ == "__main__":
    raise SystemExit(main())

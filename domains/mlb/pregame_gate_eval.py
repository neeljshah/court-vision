"""domains.mlb.pregame_gate_eval -- run the cross-corpus pregame gate on real data.

Improvements gated (each vs the pitcher-blind Elo BASE):
  A1  MOV-Elo        : margin-of-victory-multiplied Elo update (cross-corpus 2010-21 <-> 22-26)
  A2  warm-Elo       : warm-start the recent corpus from the full prior-era Elo state
                       (more-seasons-for-power); cross-corpus.
  A3  SP-form        : EW first-6-innings SP form; SINGLE-corpus walk-forward DM gate
                       (pitcher line-scores exist only for 2010-2021, so no cross-corpus
                       direction is possible -> honestly a 1-corpus DM gate, never claimed
                       as cross-corpus replication).

Every prob column is strictly pre-game (snapshot-before-update walk-forward Elo).
No $ / edge anywhere; verdict is CALIBRATION (held-out Brier).

A1 MOV scale design note
-------------------------
mov_scale is PRE-REGISTERED at 1.0 (the approximate 538-style default for run-based
sports; NOT selected by test-set Brier).  Sweeping the grid and picking the winner
by held-out Brier is a best-of-K test-set selection artifact: at scale=2.0 the gate
reached REPLICATED while scales 0.5/1.0 = REJECT and 1.5 = PARTIAL.  That
cherry-pick is what the old code did; this version uses scale=1.0 regardless of
which scale wins on the held-out data, and reports the honest gate verdict.

To change the pre-registered scale: update _A1_MOV_SCALE and document the
principled justification (NOT test-set Brier) in a comment here.

CLI:  python -m domains.mlb.pregame_gate_eval
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.ratings_mov import walk_forward_elo_mov
from domains.mlb.pregame_gate import (
    gate_cross_corpus, _one_direction, _platt_fit, _logit, _sigmoid, _brier,
)
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_REPO = Path(__file__).resolve().parents[2]
_A_PATH = _REPO / "data/domains/mlb/games.parquet"          # 2010-2021
_B_PATH = _REPO / "data/domains/mlb/games_current.parquet"  # 2022-2026

# Pre-registered MOV scale -- NOT chosen by test-set Brier.
# 1.0 is the 538-style default for run-based sports (the original NFL paper uses
# a similar unit-scale multiplier; MLB run margins are smaller than NFL point
# margins, so no inflation above 1.0 is justified a priori).
_A1_MOV_SCALE: float = 1.0


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    return df[df["target_home_win"].notna()].reset_index(drop=True)


# --------------------------------------------------------------------------- A1
def _build_a1(df: pd.DataFrame, mov_scale: float) -> pd.DataFrame:
    base = walk_forward_elo_mov(df, mov_scale=0.0)[["event_id", "p_home_elo"]]
    cand = walk_forward_elo_mov(df, mov_scale=mov_scale)[["event_id", "p_home_elo"]]
    base = base.rename(columns={"p_home_elo": "p_base"})
    cand = cand.rename(columns={"p_home_elo": "p_cand"})
    out = df[["event_id", "target_home_win"]].merge(base, on="event_id").merge(
        cand, on="event_id")
    return out


# --------------------------------------------------------------------------- A2
def _build_warm(df_recent: pd.DataFrame, df_prior: pd.DataFrame) -> pd.DataFrame:
    """Warm-start: replay prior era + recent era continuously, keep recent rows.

    BASE p_base = cold Elo on recent corpus alone.
    CAND p_cand = Elo from a continuous replay of (prior ++ recent) -- the recent
    rows inherit the carried-over franchise ratings (more seasons of power), still
    snapshot-before-update so leak-free.
    """
    cold = walk_forward_elo_mov(df_recent, mov_scale=0.0)[["event_id", "p_home_elo"]]
    cold = cold.rename(columns={"p_home_elo": "p_base"})
    combo = pd.concat([df_prior, df_recent], ignore_index=True)
    warm = walk_forward_elo_mov(combo, mov_scale=0.0)[["event_id", "p_home_elo"]]
    warm = warm.rename(columns={"p_home_elo": "p_cand"})
    out = df_recent[["event_id", "target_home_win"]].merge(cold, on="event_id").merge(
        warm, on="event_id")
    return out


# --------------------------------------------------------------------------- A3
def _build_sp(df_prior: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Build (p_base, p_cand_logit_features) for the SP-form single-corpus gate.

    Returns a frame with event_id, target, p_base (calibrated-input prob), and the
    standardized sp diff feature; the gate fits a 2-feature logistic on train.
    """
    from domains.mlb.asof_sp_form import build_sp_form_features, MIN_PRIOR_STARTS
    elo = walk_forward_elo_mov(df_prior, mov_scale=0.0)[
        ["event_id", "p_home_elo"]].rename(columns={"p_home_elo": "p_base"})
    sp = build_sp_form_features(games=df_prior)
    sp = sp[["event_id", "sp_first6_diff_ew",
             "home_sp_starts_prior", "away_sp_starts_prior"]]
    out = df_prior[["event_id", "target_home_win", "date"]].merge(
        elo, on="event_id").merge(sp, on="event_id", how="left")
    out["_cov"] = ((out["home_sp_starts_prior"] >= MIN_PRIOR_STARTS) &
                   (out["away_sp_starts_prior"] >= MIN_PRIOR_STARTS))
    return out.sort_values("date").reset_index(drop=True)


def _gate_sp_single(sp_df: pd.DataFrame, eps: float = 0.05) -> dict:
    """Walk-forward single-corpus DM gate for SP-form (70/30 time split).

    BASE  = Platt(elo).  CAND = 2-feature logistic(elo_logit, sp_z) -- both fit on
    the first 70%, scored on the last 30% (leak-free time split). DM clustered by
    event_id on the SP-covered test rows only (where the feature is real signal).
    """
    from scipy.optimize import minimize
    n = len(sp_df)
    split = int(n * 0.70)
    tr, te = sp_df.iloc[:split], sp_df.iloc[split:]
    y_tr = tr["target_home_win"].values.astype(float)
    y_te = te["target_home_win"].values.astype(float)

    lz_tr = _logit(tr["p_base"].values.astype(float))
    lz_te = _logit(te["p_base"].values.astype(float))
    sp_tr = tr["sp_first6_diff_ew"].values.astype(float)
    sp_te = te["sp_first6_diff_ew"].values.astype(float)
    m, s = float(np.nanmean(sp_tr)), max(float(np.nanstd(sp_tr)), 1e-8)
    spz_tr = np.nan_to_num((sp_tr - m) / s)
    spz_te = np.nan_to_num((sp_te - m) / s)

    wb, bb_ = _platt_fit(lz_tr, y_tr)
    p_base = _sigmoid(wb * lz_te + bb_)

    def _nll(par: np.ndarray) -> float:
        w1, w2, b = par
        p = np.clip(_sigmoid(w1 * lz_tr + w2 * spz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.1, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 10), (-5, 5), (-3, 3)])
    w1, w2, b = res.x
    p_cand = _sigmoid(w1 * lz_te + w2 * spz_te + b)

    cov = te["_cov"].values.astype(bool)
    yb = y_te[cov]
    br_base = _brier(yb, p_base[cov])
    br_cand = _brier(yb, p_cand[cov])
    d = (p_base[cov] - yb) ** 2 - (p_cand[cov] - yb) ** 2
    dm = diebold_mariano(d, te["event_id"].astype(str).values[cov])

    base_rate = float(np.mean(y_tr))
    br_const = _brier(yb, np.full_like(yb, base_rate))
    bss = (br_const - br_base) / br_const if br_const > 0 else 0.0
    degen = bss < 0.003
    beats = bool((br_cand < br_base) and (dm.p_value < eps) and not degen)
    return {
        "n_cov_test": int(cov.sum()), "brier_base": round(br_base, 5),
        "brier_cand": round(br_cand, 5), "brier_delta": round(br_base - br_cand, 6),
        "dm_stat": round(dm.dm_stat, 4), "dm_p": round(dm.p_value, 6),
        "base_bss": round(bss, 5), "base_degenerate": degen,
        "sp_weight": round(float(w2), 5),
        "verdict": "SHIP" if beats else "REJECT",
    }


def run() -> dict:
    da = _load(_A_PATH)
    db = _load(_B_PATH)

    # ---- A1: MOV-Elo (pre-registered scale; NOT selected by test-set Brier) ----
    # Sweeping the grid and picking the winner by held-out Brier is a test-set
    # selection artifact (the old code found scale=2.0 REPLICATED while 0.5/1.0
    # REJECTED and 1.5 PARTIAL -- a best-of-4 cherry-pick).  We use _A1_MOV_SCALE
    # (pre-registered at 1.0) and report the verdict for that single scale only.
    fa = _build_a1(da, _A1_MOV_SCALE)
    fb = _build_a1(db, _A1_MOV_SCALE)
    a1_v = gate_cross_corpus(fa, fb, "p_base", "p_cand",
                             name=f"mov_elo[scale={_A1_MOV_SCALE}]")
    a1 = a1_v

    # ---- A2: warm-start Elo (more seasons) ----
    fwarm = _build_warm(db, da)
    # cross-corpus needs a SECOND warm corpus: warm the prior era from nothing
    # is identical to cold, so A2 is a single-corpus walk-forward gate on the
    # recent corpus (the only place warm differs from cold).
    a2 = _gate_warm_single(fwarm)

    # ---- A3: SP-form (single corpus, 2010-2021) ----
    sp_df = _build_sp(da)
    a3 = _gate_sp_single(sp_df)

    return {"A1_mov_elo": a1.to_dict(), "A1_mov_scale": _A1_MOV_SCALE,
            "A2_warm_elo": a2, "A3_sp_form": a3}


def _gate_warm_single(fwarm: pd.DataFrame, eps: float = 0.05) -> dict:
    """Single-corpus 70/30 walk-forward DM gate: warm-Elo vs cold-Elo on recent."""
    n = len(fwarm)
    split = int(n * 0.70)
    tr, te = fwarm.iloc[:split], fwarm.iloc[split:]
    r = _one_direction(tr, te, "p_base", "p_cand", eps)
    d = r.to_dict()
    d["verdict"] = "SHIP" if r.cand_beats_base else "REJECT"
    return d


def main() -> int:
    res = run()
    print("=" * 70)
    print("MLB PREGAME DEPTH GATE (cross-corpus 2010-21 <-> 22-26; vs Elo base)")
    print("=" * 70)

    a1 = res["A1_mov_elo"]
    print(f"\nA1 MOV-Elo (pre-registered scale={res['A1_mov_scale']})  VERDICT: {a1['verdict']}")
    for dlab, dd in (("A->B", a1["a_to_b"]), ("B->A", a1["b_to_a"])):
        print(f"   {dlab}: Brier base {dd['brier_base']:.5f} cand {dd['brier_cand']:.5f}"
              f" delta {dd['brier_delta']:+.6f}  DM p={dd['dm_p']:.4f}"
              f"  base_bss={dd['base_bss']:.4f} degen={dd['base_degenerate']}")

    a2 = res["A2_warm_elo"]
    print(f"\nA2 warm-Elo (more seasons, single-corpus WF)  VERDICT: {a2['verdict']}")
    print(f"   Brier base {a2['brier_base']:.5f} cand {a2['brier_cand']:.5f}"
          f" delta {a2['brier_delta']:+.6f}  DM p={a2['dm_p']:.4f}"
          f"  base_bss={a2['base_bss']:.4f} degen={a2['base_degenerate']}")

    a3 = res["A3_sp_form"]
    print(f"\nA3 SP-form (single-corpus 2010-21 WF)  VERDICT: {a3['verdict']}")
    print(f"   n_cov_test={a3['n_cov_test']}  Brier base {a3['brier_base']:.5f}"
          f" cand {a3['brier_cand']:.5f} delta {a3['brier_delta']:+.6f}"
          f"  DM p={a3['dm_p']:.4f}  sp_w={a3['sp_weight']:+.4f}"
          f"  base_bss={a3['base_bss']:.4f}")

    print("\n(REJECT = honest success; no edge ever claimed; calibration only.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""scripts.platformkit.gate_run_statcast_sp_fatigue_kprop -- run the EXISTING leak-free
K-prop gate machinery (gate_run_mlb_sp_fatigue_kprop) on the REAL Statcast starter_table
via domains.mlb.statcast_sp_fatigue_adapter, now that a true per-start pitcher_id + an
SP-isolated per-start K LABEL exist across two INDEPENDENT seasons (2022, 2023).

WHAT CHANGED vs the on-disk gate: only the DATA SOURCE. The scoring (walk-forward
strictly-prior OLS), the Brier(binarized at the median line)+pinball calibration, the
degenerate-base guard, the cross-corpus both-directions rule, and the PLANTED-NULL that
MUST reject are REUSED unchanged from gate_run_mlb_sp_fatigue_kprop. The ONE deliberate
strengthening: clustered-DM is by the REAL PITCHER (the spec's cluster), not by
(pitch_team,side) -- because we now have pitcher identity.

GATE (identical bar, never weakened): walk-forward leak-free OLS on strictly-prior
starts | Brier+pinball held-out | clustered-DM by PITCHER both directions | degenerate-
base guard | cross-corpus 2022<->2023 both dirs | planted-null MUST reject. SHIP iff the
profile LOWERS held-out calibration error AND clears DM in BOTH seasons AND the null
rejects AND the base is skillful. REJECT/INVALID_BASE/INSUFFICIENT_DATA are the expected
honest outcomes; a single-season/single-direction lift is an ARTIFACT -> not a SHIP.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, no $/ROI/edge. vs-close
UNPROVEN -- CALIBRATION only. ASCII only. <=300 LOC.
CLI: python -m scripts.platformkit.gate_run_statcast_sp_fatigue_kprop
"""
from __future__ import annotations

import argparse
import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb import statcast_sp_fatigue_adapter as A
from scripts.platformkit import gate_run_mlb_sp_fatigue_kprop as G

_MIN_STARTS = 150          # per-corpus floor (the spec's 150-start bar)
_MIN_BSS = G._MIN_BSS      # base must beat const-mean by >= this (skillful)


# --------------------------------------------------------------------------- #
# Clustered Diebold-Mariano by PITCHER (the spec cluster). Reuses the existing
# gate's score_corpus pred/y; only the cluster key differs.
# --------------------------------------------------------------------------- #
def clustered_dm_by_pitcher(base: dict, full: dict, df: pd.DataFrame
                            ) -> Tuple[float, float]:
    """Two-sided clustered-DM p on |err| pinball-loss diffs; cluster = PITCHER.

    Negative mean diff = full LOWERS loss (better). g<3 clusters -> p=NaN (untestable).
    """
    if not (base.get("scored") and full.get("scored")):
        return float("nan"), float("nan")
    idx = base["mask_index"]
    d = df.sort_values(["date", "game_id"]).reset_index(drop=True).iloc[idx]
    yc = base["y"]
    lb = np.abs(yc - base["pred"])
    lf = np.abs(yc - full["pred"])
    diff = lf - lb                      # <0 => full better
    clusters = d["pitcher"].astype(str).to_numpy()
    by: Dict[str, List[float]] = {}
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
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / math.sqrt(2.0))))
    return float(np.mean(means)), float(p)


def gate_corpus(df: pd.DataFrame, add_feats: List[str], eps: float) -> dict:
    """BASE vs BASE+add_feats on ONE corpus; clustered-DM by PITCHER."""
    base = G.score_corpus(df, [A._BASE_COL])
    full = G.score_corpus(df, [A._BASE_COL, *add_feats])
    if not (base.get("scored") and full.get("scored")):
        return {"scored": False, "n_base": base.get("n", 0), "n_full": full.get("n", 0)}
    const_pin = G._pinball(np.full_like(base["y"], np.mean(base["y"])), base["y"])
    base_bss = G._bss(base["pinball"], const_pin)
    degenerate = base_bss < _MIN_BSS
    md, p = clustered_dm_by_pitcher(base, full, df)
    feat_better = full["pinball"] < base["pinball"] and full["brier"] <= base["brier"]
    return {"scored": True, "n": base["n"], "base_bss": base_bss,
            "degenerate": degenerate, "n_clusters": int(df["pitcher"].nunique()),
            "brier_base": base["brier"], "brier_full": full["brier"],
            "pin_base": base["pinball"], "pin_full": full["pinball"],
            "dm_mean": md, "dm_p": p, "feat_better": feat_better,
            "wins": bool(feat_better and np.isfinite(p) and p < eps and not degenerate)}


def gate_both(a_df: pd.DataFrame, b_df: pd.DataFrame, add_feats: List[str],
              eps: float) -> dict:
    a = gate_corpus(a_df, add_feats, eps)
    b = gate_corpus(b_df, add_feats, eps)
    if not (a.get("scored") and b.get("scored")):
        return {"verdict": "INSUFFICIENT_DATA", "a": a, "b": b}
    if a["degenerate"] or b["degenerate"]:
        verdict = "INVALID_BASE"
    elif a["wins"] and b["wins"]:
        verdict = "SHIP"
    elif a["wins"] or b["wins"]:
        verdict = "PARTIAL"        # single-fold lift = artifact -> not a SHIP
    else:
        verdict = "REJECT"
    return {"verdict": verdict, "a": a, "b": b}


def run(eps: float = 0.05, seed: int = 0) -> Dict[str, object]:
    a_df, b_df, cov = A.load_both(seed=seed)
    seasons = A._SEASONS
    thin = [s for s, n in cov["n_starts"].items() if n < _MIN_STARTS]
    if a_df.empty or b_df.empty or thin:
        return {"layer": "statcast_sp_fatigue_kprop", "verdict": "INSUFFICIENT_DATA",
                "reasons": (["NO_STATCAST_STARTER_TABLE"] if (a_df.empty or b_df.empty)
                            else [f"THIN_CORPUS<{_MIN_STARTS}"]),
                "coverage": cov, "proposal_only": True,
                "vs_close": "UNPROVEN -- CALIBRATION only, not a market edge"}
    if A.label_is_degenerate(a_df) or A.label_is_degenerate(b_df):
        return {"layer": "statcast_sp_fatigue_kprop", "verdict": "INVALID_BASE",
                "reasons": ["DEGENERATE_LABEL"], "coverage": cov,
                "proposal_only": True,
                "vs_close": "UNPROVEN -- CALIBRATION only, not a market edge"}
    profile = gate_both(a_df, b_df, list(A._PROFILE_FEATS), eps)
    null = gate_both(a_df, b_df, [A._NULL_FEAT], eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL",
                                       "INSUFFICIENT_DATA")
    if not null_rejects:
        verdict = "NOT_TESTABLE"
    elif profile["verdict"] == "SHIP":
        verdict = "SHIP"
    else:
        verdict = profile["verdict"]
    # degenerate-base guard at top level
    base_skillful = (profile.get("a", {}).get("base_bss", 0) >= _MIN_BSS
                     and profile.get("b", {}).get("base_bss", 0) >= _MIN_BSS)
    return {"layer": "statcast_sp_fatigue_kprop", "verdict": verdict, "eps": eps,
            "coverage": cov, "profile": profile, "null": null,
            "null_rejects": null_rejects, "base_skillful": bool(base_skillful),
            "proposal_only": True,
            "vs_close": "UNPROVEN -- CALIBRATION only (held-out Brier/pinball), not a market edge"}


def _fmt(tag: str, d: dict) -> str:
    if not d.get("scored"):
        return f"  {tag}: not scored (n_base={d.get('n_base')}, n_full={d.get('n_full')})"
    return (f"  {tag}: Brier {d['brier_base']:.5f}->{d['brier_full']:.5f}  "
            f"pin {d['pin_base']:.5f}->{d['pin_full']:.5f}  "
            f"DM mean={d['dm_mean']:+.5f} p={d['dm_p']:.4f}  "
            f"baseBSS={d['base_bss']:.4f} degen={d['degenerate']}  "
            f"better={d['feat_better']}  n={d['n']} clusters={d.get('n_clusters')}")


def _report(res: Dict[str, object]) -> str:
    L = ["=" * 78,
         "STATCAST SP FATIGUE/VELO PROFILE -> NEXT-START K-PROP GATE (vs recent-K BASE)",
         "=" * 78,
         "GATE: walk-forward strictly-prior OLS | Brier(line)+pinball(count) | clustered-",
         "      DM by PITCHER both dirs | degenerate-base guard | cross-corpus 2022<->2023",
         "      both dirs | planted-null MUST reject. PROPOSAL-ONLY; NO $.",
         f"VERDICT: {res['verdict']}", "-" * 78,
         f"coverage: {res.get('coverage', {}).get('n_starts')}  "
         f"pitchers={res.get('coverage', {}).get('n_pitchers')}"]
    if res["verdict"] in ("INSUFFICIENT_DATA", "INVALID_BASE") and "profile" not in res:
        L.append(f"  reasons: {','.join(res.get('reasons', []))}")
        L += ["=" * 78,
              "CALIBRATION only; NO $/ROI/edge. vs-close UNPROVEN. Honest non-SHIP.",
              "=" * 78]
        return "\n".join(L)
    p = res["profile"]
    L += ["-" * 78, f"PROFILE add ({len(A._PROFILE_FEATS)} feats)  VERDICT: {p['verdict']}"
          f"  base_skillful={res.get('base_skillful')}",
          _fmt("2022 (dir A)", p["a"]), _fmt("2023 (dir B)", p["b"])]
    n = res["null"]
    L += ["-" * 78,
          f"PLANTED-NULL [{A._NULL_FEAT}]: verdict {n['verdict']}  REJECTS={res['null_rejects']}",
          _fmt("2022 (dir A)", n["a"]), _fmt("2023 (dir B)", n["b"]),
          ("  null rejected -> gate CAN fail a signal." if res["null_rejects"]
           else "  *** UNTRUSTWORTHY: noise did NOT reject. ***"),
          "=" * 78,
          "CALIBRATION only; NO $/ROI/edge. vs-close UNPROVEN. REJECT = honest success.",
          "=" * 78]
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Statcast SP-fatigue K-prop gate (proposal-only).")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    print(_report(run(eps=a.eps, seed=a.seed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["clustered_dm_by_pitcher", "gate_corpus", "gate_both", "run", "main"]

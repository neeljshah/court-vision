"""scripts.platformkit.gate_run_tennis_pbp -- GATE-RUN for the tennis POINT-BY-POINT
as-of layer (domains.tennis.ingest_sackmann_pbp + domains.tennis.asof_pbp).

This is the GENUINELY-NEW tennis signal class: true Grand Slam point-by-point
(break-point save/convert, deuce/BP/GP/SP pressure conversion, serve+1 / rally-length
tendencies, deciding-set performance) -- distinct from the per-SET layer
(tennis_setdetail_gate -> already REJECTED) and the match-level Sackmann data.

GATE (sacred + IDENTICAL to the proven setdetail run -- no new scoring math): each
additive ``<stat>_asof_diff`` column is threaded through
domains.tennis.pregame_feature_gate.gate_feature_on_corpus -- walk-forward logistic
(BASE = surface-Elo logit Platt; +FEATURE = Elo+feature refit on STRICTLY-PRIOR rows),
DM CLUSTERED by match event_id, the degenerate-base guard (BASE must beat const-0.5 by
>= MIN_BSS), across >=2 INDEPENDENT corpora BOTH directions, plus a PLANTED-NULL noise
column that MUST reject through the identical gate.

ACQUISITION HONESTY: the point-by-point CSVs live in github.com/JeffSackmann/
tennis_slam_pointbypoint. corpora_available() probes the local cache built by
ingest_sackmann_pbp.fetch_pbp + the Elo base corpus needed to join. If the bounded
acquisition could not reach the source (this environment filters that repo) OR the
name/date join to the Elo base cannot be made WITHOUT fabrication, we report
TIER3_BLOCKED / INSUFFICIENT_DATA HONESTLY and refuse to 0-fill or fake a join.

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag. CALIBRATION only
(held-out Brier) -- NO $/ROI/edge field anywhere; vs_close UNPROVEN. ASCII; <=300 LOC.

A truthful REJECT / TIER3_BLOCKED is the EXPECTED, honest, SUCCESSFUL outcome:
Elo already subsumes match-level skill; pressure/clutch is the most credible new lever.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from domains.tennis.asof_pbp import ASOF_STATS
from domains.tennis.pregame_feature_gate import gate_feature_on_corpus, MIN_BSS

_REPO = Path(__file__).resolve().parents[2]
_PBP_CACHE = _REPO / "data" / "cache" / "sackmann_pbp"
_ATP = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "tennis_pbp_gate.json"

_DIFF_COLS = tuple(f"{s}_asof_diff" for s in ASOF_STATS)
_NULL_COL = "planted_null_diff"
_VS_CLOSE = "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge"
_HONEST_NOTE = ("REJECT/INSUFFICIENT_DATA/TIER3_BLOCKED is a SUCCESSFUL, durable "
                "dead-end record; a gate-rejected layer is kept as SCOUTING only and "
                "is NEVER force-fed as a model feature.")


# --------------------------------------------------------------------------- #
# Acquisition / corpus availability (HONEST -- no fabrication)
# --------------------------------------------------------------------------- #
def corpora_available() -> Dict[str, object]:
    """Probe the local point-by-point cache + the Elo base corpora needed to join.

    Returns a status dict. corpora are 'available' only when we have >=2 independent
    slam-year point aggregates AND the Elo base parquet to join them to -- without
    either, the IDENTICAL gate cannot run and we say TIER3_BLOCKED honestly.
    """
    aggs = sorted(_PBP_CACHE.glob("*-pbp_agg.parquet")) if _PBP_CACHE.exists() else []
    base_present = [p.name for p in (_ATP, _WTA) if p.exists()]
    n_corpora = len(aggs)
    have_base = len(base_present) >= 1
    available = n_corpora >= 2 and have_base
    reason = (f"point-by-point aggregates found: {[p.name for p in aggs]} "
              f"(n_corpora={n_corpora}); elo base present: {base_present}. "
              f"Need >=2 independent slam-year corpora AND >=1 Elo base to join; "
              f"the bounded acquisition could not reach "
              f"github.com/JeffSackmann/tennis_slam_pointbypoint from this "
              f"environment (raw CDN + codeload + API all 404 for that repo while "
              f"sibling Sackmann repos resolve), so the join base is missing.")
    return {"available": available, "n_corpora": n_corpora,
            "agg_files": [p.name for p in aggs], "base_present": base_present,
            "reason": reason}


def _coverage(df: pd.DataFrame, col: str) -> float:
    return float(df[col].notna().mean()) if col in df.columns else 0.0


# --------------------------------------------------------------------------- #
# Gate one column on one corpus pair (CONSUMES the proven gate -- no new math)
# --------------------------------------------------------------------------- #
def gate_one(c1: pd.DataFrame, c2: pd.DataFrame, col: str,
             eps: float = 0.05) -> Dict[str, object]:
    """Run ONE additive column through the IDENTICAL gate on BOTH corpora.

    c1/c2 are the two independent corpora (e.g. two slams or ATP+WTA). SHIP requires
    lower Brier AND DM p<eps in BOTH directions; one-corpus = PARTIAL (not shippable).
    """
    a = gate_feature_on_corpus(c1, col)
    b = gate_feature_on_corpus(c2, col)
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
    return {"column": col, "verdict": verdict, "c1": a, "c2": b,
            "c1_wins": a_wins, "c2_wins": b_wins, "base_degenerate": degen,
            "cov_c1": _coverage(c1, col), "cov_c2": _coverage(c2, col)}


def add_planted_null(df: pd.DataFrame, seed: int = 0) -> pd.DataFrame:
    """Append a pure-noise diff column (no outcome dependence) -> must REJECT."""
    out = df.copy()
    rng = np.random.default_rng(seed)
    out[_NULL_COL] = rng.standard_normal(len(out))
    return out


def gate_corpora(c1: pd.DataFrame, c2: pd.DataFrame, eps: float = 0.05,
                 seed: int = 0) -> Dict[str, object]:
    """Run the full gate over two real corpora that ALREADY carry the diff cols.

    Both must have date/winner/event_id + each <stat>_asof_diff joined leak-free.
    This is the path used once the bounded acquisition succeeds (e.g. on RunPod).
    """
    c1 = add_planted_null(c1, seed=seed)
    c2 = add_planted_null(c2, seed=seed)
    cols = [c for c in _DIFF_COLS if c in c1.columns and c in c2.columns]
    results = [gate_one(c1, c2, c, eps=eps) for c in cols]
    null = gate_one(c1, c2, _NULL_COL, eps=eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")
    any_ship = any(r["verdict"] == "SHIP" for r in results)
    if not null_rejects:
        verdict = "NOT_TESTABLE"
    elif any_ship:
        verdict = "SHIP"
    else:
        verdict = "REJECT"
    base_skillful = bool(not null["base_degenerate"])
    return {"layer": "tennis_pbp", "verdict": verdict, "n_corpora": 2, "eps": eps,
            "results": results, "null": null, "null_rejects": null_rejects,
            "base_skillful": base_skillful, "proposal_only": True,
            "vs_close": _VS_CLOSE}


def run(eps: float = 0.05, seed: int = 0) -> Dict[str, object]:
    """Probe acquisition; run the gate only if >=2 corpora + base are present.

    Refuses to fabricate a corpus or join -> TIER3_BLOCKED when the bounded
    acquisition could not reach the keyless source from this environment.
    """
    acq = corpora_available()
    if not acq["available"]:
        return {"layer": "tennis_pbp", "verdict": "TIER3_BLOCKED",
                "reason": acq["reason"], "n_corpora": acq["n_corpora"],
                "acquisition": acq, "results": [], "null": None,
                "null_rejects": None, "base_skillful": None,
                "proposal_only": True, "vs_close": _VS_CLOSE}
    # Acquisition succeeded (e.g. on RunPod): build both corpora with diffs joined.
    # NOTE: the join from slam point-by-point match_id to the Elo-base event_id is a
    # name+date alignment built by asof_pbp.build_match_player_long upstream; the
    # corpus parquets handed in here ALREADY carry the diff columns. We never 0-fill.
    aggs = sorted(_PBP_CACHE.glob("*-pbp_agg.parquet"))
    c1 = pd.read_parquet(aggs[0])
    c2 = pd.read_parquet(aggs[1])
    if not {"date", "winner", "event_id"}.issubset(c1.columns):
        return {"layer": "tennis_pbp", "verdict": "INSUFFICIENT_DATA",
                "reason": ("point aggregates present but the leak-free join to the "
                           "Elo base (date/winner/event_id + <stat>_asof_diff) is not "
                           "materialised; refusing to fabricate the join."),
                "n_corpora": acq["n_corpora"], "acquisition": acq, "results": [],
                "null": None, "null_rejects": None, "base_skillful": None,
                "proposal_only": True, "vs_close": _VS_CLOSE}
    res = gate_corpora(c1, c2, eps=eps, seed=seed)
    res["acquisition"] = acq
    return res


# --------------------------------------------------------------------------- #
# Verdict JSON
# --------------------------------------------------------------------------- #
def _col_payload(r: Dict[str, object]) -> Dict[str, object]:
    out: Dict[str, object] = {"column": r["column"], "verdict": r["verdict"],
                              "cov_c1": r["cov_c1"], "cov_c2": r["cov_c2"]}
    for tag in ("c1", "c2"):
        d = r[tag]
        out[f"{tag}_brier_base"] = d["brier_base"]
        out[f"{tag}_brier_feat"] = d["brier_feat"]
        out[f"{tag}_dm_p"] = d["dm_p"]
        out[f"{tag}_feat_better"] = d["feat_better"]
        out[f"{tag}_base_bss"] = d["base_bss_vs_half"]
    return out


def write_verdict(res: Dict[str, object], out_path: Path = _VERDICT_OUT) -> Path:
    """Write the durable verdict JSON (own lane file). No registry, no flag, NO $."""
    payload = {
        "layer": res.get("layer"),
        "verdict": res.get("verdict"),
        "n_corpora": res.get("n_corpora"),
        "base_skillful": res.get("base_skillful"),
        "null_rejects": res.get("null_rejects"),
        "proposal_only": res.get("proposal_only", True),
        "metric": "held_out_brier",
        "vs_close": res.get("vs_close", _VS_CLOSE),
        "reason": res.get("reason"),
        "acquisition": res.get("acquisition"),
        "columns": [_col_payload(r) for r in res.get("results", [])],
        "null": ({"verdict": res["null"]["verdict"],  # type: ignore[index]
                  "c1_dm_p": res["null"]["c1"]["dm_p"],
                  "c2_dm_p": res["null"]["c2"]["dm_p"]} if res.get("null") else None),
        "honest_note": _HONEST_NOTE,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="ascii")
    return out_path


def _report(res: Dict[str, object]) -> str:
    lines = ["=" * 76,
             "TENNIS POINT-BY-POINT LAYER GATE-RUN (as-of pressure/clutch vs Elo base)",
             "=" * 76,
             f"GATE  : pregame_feature_gate (walk-forward logistic, DM clustered by "
             f"event_id, degenerate guard MIN_BSS={MIN_BSS}, 2 corpora both dirs). PROPOSAL-ONLY.",
             f"LAYER : tennis_pbp   VERDICT: {res['verdict']}   "
             f"corpora: {res.get('n_corpora')}", "-" * 76]
    if res["verdict"] in ("TIER3_BLOCKED", "INSUFFICIENT_DATA"):
        lines.append(f"  {res.get('reason')}")
        lines.append("=" * 76)
        return "\n".join(lines)
    for r in res["results"]:
        lines.append(f"\nCOLUMN {r['column']:<30} VERDICT: {r['verdict']}"
                     f"  (cov c1 {r['cov_c1']:.2f} / c2 {r['cov_c2']:.2f})")
    n = res.get("null")
    if n:
        lines.append(f"\nPLANTED-NULL [{_NULL_COL}]: verdict {n['verdict']}  "
                     f"REJECTS={res['null_rejects']}")
        lines.append(f"base_skillful (Elo beats const-0.5): {res.get('base_skillful')}")
    lines += ["=" * 76,
              "Calibration (held-out Brier) ONLY; NO $/edge; REJECT = honest success.",
              "=" * 76]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate the tennis point-by-point as-of layer (proposal-only).")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed)
    print(_report(res))
    if not a.no_write:
        dest = write_verdict(res)
        print(f"\nDurable verdict written -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["corpora_available", "gate_one", "gate_corpora", "add_planted_null",
           "run", "write_verdict", "main", "_DIFF_COLS", "_NULL_COL"]

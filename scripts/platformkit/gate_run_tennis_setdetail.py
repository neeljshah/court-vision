"""scripts.platformkit.gate_run_tennis_setdetail -- GATE-RUN for the tennis
per-SET / tiebreak as-of layer (domains.tennis.ingest_setdetail_states).

Threads each additive ``*_asof_diff`` column from the new setdetail layer through
the PROVEN, UNWEAKENED tennis pregame gate (domains.tennis.pregame_feature_gate),
which is itself: walk-forward logistic (BASE = Elo-only Platt, +FEATURE = Elo+feature
refit on STRICTLY-PRIOR rows only -> leak-free), DM CLUSTERED by match event_id, the
degenerate-base guard (BASE Elo must beat const-0.5 by >= MIN_BSS BSS), and a
cross-corpus replication verdict over >=2 INDEPENDENT corpora (ATP + WTA).

WHAT THIS RUNNER ADDS (no new scoring math -- it CONSUMES the gate):
  (a) leak-free load: additive layer built by the SINGLE train==inference builder
      build_asof_setdetail, aligned to the Elo base 1:1 by event_id (missing -> NaN,
      never a silent 0-fill into a win); coverage reported honestly.
  (b) cross-corpus BOTH directions: ATP + WTA are the two independent corpora; SHIP
      requires the feature to LOWER Brier AND clear DM in BOTH (one-corpus = PARTIAL).
  (c) a PLANTED-NULL pure-noise column through the IDENTICAL gate, which MUST REJECT;
      if it does not, the run is UNTRUSTWORTHY (NOT_TESTABLE) and we say so.
  (d) an ESPN orphan set-by-set corpus probe + a durable verdict JSON written to its
      OWN lane file data/frontend/funnel/tennis_setdetail_gate.json (no shared append).

PROPOSAL-ONLY: writes NOTHING to data/registry/, flips NO flag, creates NO sentinel.
CALIBRATION only (held-out Brier) -- NO $ / ROI / edge field anywhere; vs-close is a
held-out yardstick, never a feature. ASCII-only; numpy/pandas; <=300 LOC.

A truthful REJECT is the EXPECTED, honest, SUCCESSFUL outcome here: these per-set /
tiebreak rates largely re-express serve+return strength already priced into Elo.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from domains.tennis.ingest_setdetail_states import build_asof_setdetail
from domains.tennis.pregame_features import build_features
from domains.tennis.pregame_feature_gate import (
    gate_feature_on_corpus, MIN_BSS, TRAIN_YEAR_MAX)

_REPO = Path(__file__).resolve().parents[2]
_ATP = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_ESPN = _REPO / "data" / "domains" / "tennis" / "espn_matches.parquet"
_VERDICT_OUT = _REPO / "data" / "frontend" / "funnel" / "tennis_setdetail_gate.json"

# The four additive overall diff columns the layer emits (per-surface splits are
# absorbed into these overall diffs; we gate the load-bearing overall signals).
_DIFF_COLS = (
    "tiebreak_win_pct_asof_diff",
    "sets_dropped_rate_asof_diff",
    "close_set_rate_asof_diff",
    "avg_games_per_set_asof_diff",
)
_NULL_COL = "planted_null_diff"   # pure-noise control -- MUST reject
_VS_CLOSE = "UNPROVEN -- CALIBRATION only (held-out Brier), not a market edge"
_HONEST_NOTE = ("REJECT/INSUFFICIENT_DATA is a SUCCESSFUL, durable dead-end record; "
                "the gate-rejected layer is kept as SCOUTING only and is NEVER "
                "force-fed as a model feature.")


def build_corpus_with_layer(matches: pd.DataFrame,
                            seed: int = 0) -> pd.DataFrame:
    """Elo base features + the additive setdetail diffs, joined leak-free by event_id.

    Also injects a PLANTED-NULL pure-noise column (seeded N(0,1), independent of the
    outcome) so the IDENTICAL gate can be shown to FAIL a worthless signal.
    """
    feat = build_features(matches)
    layer = build_asof_setdetail(matches)
    keep = ["event_id", *[c for c in _DIFF_COLS if c in layer.columns]]
    merged = feat.merge(layer[keep], on="event_id", how="left")
    # planted null: pure noise, no outcome dependence, no leak -> must REJECT.
    rng = np.random.default_rng(seed)
    merged[_NULL_COL] = rng.standard_normal(len(merged))
    return merged


def _coverage(df: pd.DataFrame, col: str) -> float:
    return float(df[col].notna().mean()) if col in df.columns else 0.0


def gate_one(atp_feat: pd.DataFrame, wta_feat: pd.DataFrame, col: str,
             eps: float = 0.05) -> Dict[str, object]:
    """Run ONE additive column through the proven gate on BOTH corpora.

    ATP and WTA ARE the two cross-corpus directions; SHIP requires the feature to
    win (lower Brier AND DM p<eps) in BOTH (one-corpus = PARTIAL).
    """
    a = gate_feature_on_corpus(atp_feat, col)
    w = gate_feature_on_corpus(wta_feat, col)
    degen = bool(a["base_degenerate"] or w["base_degenerate"])
    a_wins = bool(a["feat_better"] and a["dm_p"] < eps)   # direction A (ATP)
    w_wins = bool(w["feat_better"] and w["dm_p"] < eps)   # direction B (WTA)
    if degen:
        verdict = "INVALID_BASE"
    elif a_wins and w_wins:
        verdict = "SHIP"
    elif a_wins or w_wins:
        verdict = "PARTIAL"          # one-corpus-only win -> NOT shippable
    else:
        verdict = "REJECT"
    return {"column": col, "verdict": verdict,
            "atp": a, "wta": w,
            "atp_wins": a_wins, "wta_wins": w_wins,
            "base_degenerate": degen,
            "cov_atp": _coverage(atp_feat, col), "cov_wta": _coverage(wta_feat, col)}


def espn_probe(train_year_max: int = TRAIN_YEAR_MAX) -> Dict[str, object]:
    """As-of gateability probe for the orphan ESPN set-by-set corpus.

    The IDENTICAL gate needs a walk-forward TRAIN->TEST *year* split AND an Elo/
    win-prob BASE to improve on. We check those HONESTLY and refuse to fabricate a
    base or 0-fill a split -> INSUFFICIENT_DATA (durable dead-end), never a faked SHIP.
    """
    if not _ESPN.exists():
        return {"corpus": "espn", "verdict": "INSUFFICIENT_DATA", "gateable": False,
                "reason": "espn_matches.parquet absent"}
    e = pd.read_parquet(_ESPN)
    yrs = pd.to_datetime(e["date"], errors="coerce").dt.year.dropna()
    n_years = int(yrs.nunique())
    n_train = int((yrs <= train_year_max).sum())
    n_test = int((yrs > train_year_max).sum())
    _singles = {"Men's Singles", "Women's Singles"}
    sf = e[(e.get("status") == "STATUS_FINAL") & (e.get("discipline").isin(_singles))] \
        if {"status", "discipline"}.issubset(e.columns) else e
    n_singles_final = int(sf["comp_id"].nunique()) if "comp_id" in e.columns else 0
    has_elo_base = any(c in e.columns for c in ("elo", "elo_logit", "win_prob"))
    # Gateable through the IDENTICAL gate iff it can fill BOTH split arms AND has
    # a real base to improve on. ESPN is a single 2026 season with no rating base.
    gateable = (n_years >= 2 and n_train >= 50 and n_test >= 50 and has_elo_base)
    reason = ("n_years=%d, train_rows=%d, test_rows=%d, has_elo_base=%s -> cannot "
              "feed the walk-forward year-split + degenerate-base gate; refuses to "
              "fabricate a base or 0-fill a split."
              % (n_years, n_train, n_test, has_elo_base))
    return {"corpus": "espn", "verdict": "INSUFFICIENT_DATA" if not gateable
            else "GATEABLE_PENDING", "gateable": bool(gateable),
            "n_rows": int(len(e)), "n_years": n_years, "n_train_rows": n_train,
            "n_test_rows": n_test, "n_singles_final_matches": n_singles_final,
            "has_elo_base": bool(has_elo_base), "reason": reason,
            "independent_signal": False}


def run(eps: float = 0.05, seed: int = 0) -> Dict[str, object]:
    """Build both corpora once, gate every additive diff + the planted null.

    Returns a verdict dict. If a corpus parquet is missing we report
    INSUFFICIENT_DATA honestly (need >=2 independent corpora to replicate).
    """
    espn = espn_probe()
    if not _ATP.exists() or not _WTA.exists():
        present = [p.name for p in (_ATP, _WTA) if p.exists()]
        return {"layer": "tennis_setdetail", "verdict": "INSUFFICIENT_DATA",
                "reason": f"need 2 independent corpora; found {present}",
                "n_corpora": len(present), "results": [], "null": None,
                "espn": espn}

    atp = build_corpus_with_layer(pd.read_parquet(_ATP), seed=seed)
    wta = build_corpus_with_layer(pd.read_parquet(_WTA), seed=seed)

    results = [gate_one(atp, wta, c, eps=eps) for c in _DIFF_COLS]

    # PLANTED-NULL control through the IDENTICAL gate -- MUST reject.
    null = gate_one(atp, wta, _NULL_COL, eps=eps)
    null_rejects = null["verdict"] in ("REJECT", "INVALID_BASE", "PARTIAL")

    any_ship = any(r["verdict"] == "SHIP" for r in results)
    if not null_rejects:
        layer_verdict = "NOT_TESTABLE"      # gate could not fail a noise column
    elif any_ship:
        layer_verdict = "SHIP"              # surfaced as a PROPOSAL only
    else:
        layer_verdict = "REJECT"

    # The BASE (Elo Platt) must itself be skillful in BOTH corpora for the verdict
    # to be trustworthy -- surface it explicitly from the planted-null run.
    base_skillful = bool(not null["base_degenerate"])

    return {"layer": "tennis_setdetail", "verdict": layer_verdict,
            "n_corpora": 2, "eps": eps, "results": results, "null": null,
            "null_rejects": null_rejects, "base_skillful": base_skillful,
            "proposal_only": True, "espn": espn, "vs_close": _VS_CLOSE}


def _col_payload(r: Dict[str, object]) -> Dict[str, object]:
    """Flatten one gated column's both-corpus metrics for the verdict JSON."""
    out: Dict[str, object] = {"column": r["column"], "verdict": r["verdict"],
                              "cov_atp": r["cov_atp"], "cov_wta": r["cov_wta"]}
    for tag in ("atp", "wta"):
        d = r[tag]
        out[f"{tag}_brier_base"] = d["brier_base"]
        out[f"{tag}_brier_feat"] = d["brier_feat"]
        out[f"{tag}_dm_p"] = d["dm_p"]
        out[f"{tag}_feat_better"] = d["feat_better"]
        out[f"{tag}_base_bss"] = d["base_bss_vs_half"]
    return out


def write_verdict(res: Dict[str, object],
                  out_path: Path = _VERDICT_OUT) -> Path:
    """Write the durable verdict JSON to data/frontend/funnel/ (own lane file).

    No shared append, no registry write, no flag flip. CALIBRATION only -- there
    is NO $/ROI/edge field anywhere in the payload (asserted in the test).
    """
    payload = {
        "layer": res.get("layer"),
        "verdict": res.get("verdict"),
        "n_corpora": res.get("n_corpora"),
        "base_skillful": res.get("base_skillful"),
        "null_rejects": res.get("null_rejects"),
        "proposal_only": res.get("proposal_only", True),
        "metric": "held_out_brier",
        "vs_close": res.get("vs_close", _VS_CLOSE),
        "columns": [_col_payload(r) for r in res.get("results", [])],
        "null": ({"verdict": res["null"]["verdict"],  # type: ignore[index]
                  "atp_dm_p": res["null"]["atp"]["dm_p"],
                  "wta_dm_p": res["null"]["wta"]["dm_p"]} if res.get("null") else None),
        "espn_orphan": res.get("espn"),
        "honest_note": _HONEST_NOTE,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="ascii")
    return out_path


def _fmt_corpus(tag: str, d: Dict[str, object]) -> str:
    return (f"  {tag}: Brier base {d['brier_base']:.5f} -> feat {d['brier_feat']:.5f}"
            f"  (delta {d['brier_delta']:+.5f})  DM p={d['dm_p']:.4f}"
            f"  feat_better={d['feat_better']}  base_BSS={d['base_bss_vs_half']:.4f}"
            f"  degenerate={d['base_degenerate']}")


def _report(res: Dict[str, object]) -> str:
    lines = ["=" * 76,
             "TENNIS SET-DETAIL LAYER GATE-RUN (per-set/tiebreak as-of vs Elo base)",
             "=" * 76,
             "GATE  : pregame_feature_gate (walk-forward logistic, DM clustered by "
             f"event_id, degenerate guard MIN_BSS={MIN_BSS}, ATP+WTA both dirs). PROPOSAL-ONLY.",
             f"LAYER : tennis_setdetail   VERDICT: {res['verdict']}   "
             f"corpora: {res.get('n_corpora')} (ATP + WTA, independent)", "-" * 76]
    if res["verdict"] == "INSUFFICIENT_DATA":
        lines.append(f"  {res.get('reason')}")
        lines.append("=" * 76)
        return "\n".join(lines)
    for r in res["results"]:
        lines.append(f"\nCOLUMN {r['column']:<28} VERDICT: {r['verdict']}"
                     f"  (cov ATP {r['cov_atp']:.2f} / WTA {r['cov_wta']:.2f})")
        lines.append(_fmt_corpus("ATP (dir A)", r["atp"]))
        lines.append(_fmt_corpus("WTA (dir B)", r["wta"]))
    n = res["null"]
    lines += ["\n" + "-" * 76,
              f"PLANTED-NULL control [{_NULL_COL}]: verdict {n['verdict']}  "
              f"REJECTS={res['null_rejects']}",
              _fmt_corpus("ATP (dir A)", n["atp"]),
              _fmt_corpus("WTA (dir B)", n["wta"])]
    lines.append("  *** GATE UNTRUSTWORTHY: noise did NOT reject ***"
                 if not res["null_rejects"]
                 else "  null rejected as required -> the gate CAN fail a signal.")
    lines.append(f"  base_skillful (Elo Platt beats const-0.5): {res.get('base_skillful')}")
    esp = res.get("espn") or {}
    if esp:
        lines += ["\n" + "-" * 76,
                  f"ORPHAN ESPN set-by-set corpus: verdict {esp.get('verdict')}  "
                  f"gateable={esp.get('gateable')}  rows={esp.get('n_rows')} "
                  f"years={esp.get('n_years')} singles_final={esp.get('n_singles_final_matches')} "
                  f"has_elo_base={esp.get('has_elo_base')}",
                  f"  {esp.get('reason')}"]
    lines += ["=" * 76,
              "Calibration (held-out Brier) ONLY; NO $/edge; vs-close = held-out "
              "yardstick, never a feature. REJECT = honest, successful outcome.", "=" * 76]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Gate the tennis per-set/tiebreak as-of layer (proposal-only).")
    ap.add_argument("--eps", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-write", action="store_true",
                    help="print only; do not write the durable verdict JSON")
    a = ap.parse_args(argv)
    res = run(eps=a.eps, seed=a.seed)
    print(_report(res))
    if not a.no_write:
        dest = write_verdict(res)
        print(f"\nDurable verdict written -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_corpus_with_layer", "gate_one", "run", "main",
           "espn_probe", "write_verdict", "_DIFF_COLS", "_NULL_COL"]

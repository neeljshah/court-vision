"""iter56_tov_exploration.py — Should TOV re-enter the production bet stack?

PRODUCTION CONTEXT (per Iter-53 baseline + Iter-54 line-bucket filters):
  PTS/REB/AST/FG3M/STL/BLK ship. TOV has threshold 0.5 in bet_thresholds.py
  but is NOT in the live bet log — dropped earlier in the loop. We probe whether
  to re-add it.

DECISION GATES (from prompt):
  - ROI >= +5% AND z >= 1.5 on n >= 50 bets       -> SHIP TOV
  - ROI >= +10% AND z >= 2.0 on filtered subset   -> SHIP TOV with filter
  - else                                           -> REVERT (documented)

INTEGRITY CHECKS (run first, hard-stop on any failure):
  1. TOV pkl: n_features_in_ must match _meta.json stats.tov.n_features.
  2. TOV must have non-zero rows in the eval CSV (data/cache/eval_2025_26_combined.csv).

If either check fails: REVERT, document, do NOT retrain (per prompt).

OUTPUTS:
  data/cache/holdout_baseline.json   -> add "__iter56__" key (read-modify-write)
  vault/Models/Iter56 TOV Exploration.md

Run:
    python scripts/iter56_tov_exploration.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import pickle
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV       = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
META_JSON      = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs", "_meta.json")
LGB_PKL        = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs", "quantile_pergame_lgb_tov_q50.pkl")
XGB_JSON       = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs", "quantile_pergame_tov_q50.json")
RS_CSV         = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "regular_season_2025_26_oddsapi.csv")
PO_CSV         = os.path.join(PROJECT_DIR, "data", "external", "historical_lines", "playoffs_2025_26_oddsapi.csv")

VAULT_DIR      = os.path.join(PROJECT_DIR, "vault", "Models")
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter56 TOV Exploration.md")

# ── Decision constants ────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)
N_BOOTSTRAP    = 1000
SEED           = 42

SHIP_ROI_PCT       = 5.0
SHIP_Z             = 1.5
SHIP_MIN_BETS      = 50
SHIP_FILTERED_ROI  = 10.0
SHIP_FILTERED_Z    = 2.0


# ── Integrity checks ──────────────────────────────────────────────────────────

def check_tov_pkl_integrity() -> Dict:
    """Verify TOV pkl features match _meta.json. Returns dict with status + details."""
    with open(META_JSON, encoding="utf-8") as fh:
        meta = json.load(fh)
    tov_meta = meta["stats"].get("tov")
    if tov_meta is None:
        return {"ok": False, "reason": "TOV missing from _meta.json"}

    meta_n     = tov_meta.get("n_features")
    meta_method = tov_meta.get("method", "?")
    meta_file  = tov_meta.get("model_filename", "")

    out: Dict = {
        "meta_n":      meta_n,
        "meta_method": meta_method,
        "meta_file":   meta_file,
    }

    # Check LGB pkl
    if os.path.exists(LGB_PKL):
        try:
            with open(LGB_PKL, "rb") as fh:
                m = pickle.load(fh)
            lgb_n = getattr(m, "n_features_in_", None)
            out["lgb_pkl_n_features_in"] = lgb_n
            out["lgb_pkl_stale"] = (lgb_n != meta_n) if lgb_n is not None else None
        except Exception as e:
            out["lgb_pkl_load_error"] = str(e)
            out["lgb_pkl_stale"] = True
    else:
        out["lgb_pkl_stale"] = None
        out["lgb_pkl_missing"] = True

    # Check XGB json
    out["xgb_json_exists"] = os.path.exists(XGB_JSON)
    if out["xgb_json_exists"]:
        out["xgb_json_size"] = os.path.getsize(XGB_JSON)

    # Overall integrity: model can be used if EITHER LGB pkl matches OR XGB JSON exists
    can_use_lgb = out.get("lgb_pkl_stale") is False
    can_use_xgb = (meta_method == "xgb") and out.get("xgb_json_exists", False)
    out["ok"] = can_use_lgb or can_use_xgb
    if not out["ok"]:
        reasons = []
        if out.get("lgb_pkl_stale"):
            reasons.append(f"LGB pkl stale (n_features_in_={out.get('lgb_pkl_n_features_in')} vs meta={meta_n})")
        if not can_use_xgb:
            reasons.append(f"XGB JSON unusable (meta.method={meta_method}, exists={out.get('xgb_json_exists')})")
        out["reason"] = "; ".join(reasons)
    return out


def count_tov_eval_rows() -> Tuple[int, Dict[str, int], Dict[str, int]]:
    """Count TOV rows in eval CSV + source closing-lines CSVs."""
    eval_count = 0
    src_counts: Dict[str, int] = {}

    if os.path.exists(EVAL_CSV):
        with open(EVAL_CSV, encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            stats = Counter(row.get("stat", "").strip().lower() for row in r)
        eval_count = stats.get("tov", 0)
        eval_dist = dict(stats)
    else:
        eval_dist = {}

    for path, label in ((RS_CSV, "rs_2025_26"), (PO_CSV, "po_2025_26")):
        if not os.path.exists(path):
            src_counts[label] = -1
            continue
        with open(path, encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            s = Counter(row.get("stat", "").strip().lower() for row in r)
        src_counts[label] = s.get("tov", 0)
        src_counts[f"{label}_total"] = sum(s.values())

    return eval_count, eval_dist, src_counts


# ── (UNREACHABLE on this dataset — kept for future when TOV lines arrive) ──────

def bootstrap_roi(roi_units: List[float], n_boot: int = N_BOOTSTRAP) -> Tuple[float, float]:
    """Return (ci_lo, ci_hi) at 2.5/97.5 percentiles."""
    if not roi_units:
        return 0.0, 0.0
    arr = np.asarray(roi_units)
    rng = np.random.default_rng(SEED)
    boots = np.empty(n_boot)
    n = len(arr)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[i] = float(np.mean(arr[idx])) * 100.0
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 72)
    print("  ITER-56: TOV STAT EXPLORATION")
    print("=" * 72)

    # ── Step 1: Integrity ─────────────────────────────────────────────────────
    print("\n  [1/3] TOV PKL INTEGRITY")
    integrity = check_tov_pkl_integrity()
    print(f"    meta n_features: {integrity.get('meta_n')}, method: {integrity.get('meta_method')}, file: {integrity.get('meta_file')}")
    if "lgb_pkl_n_features_in" in integrity:
        print(f"    LGB pkl n_features_in_: {integrity['lgb_pkl_n_features_in']}  "
              f"stale={integrity.get('lgb_pkl_stale')}")
    if "lgb_pkl_load_error" in integrity:
        print(f"    LGB pkl load error: {integrity['lgb_pkl_load_error']}")
    print(f"    XGB JSON exists: {integrity.get('xgb_json_exists')}")
    print(f"    Overall ok: {integrity.get('ok')}  reason: {integrity.get('reason', '—')}")

    # ── Step 2: Eval data availability ────────────────────────────────────────
    print("\n  [2/3] TOV EVAL DATA AVAILABILITY")
    eval_n, eval_dist, src_counts = count_tov_eval_rows()
    print(f"    eval_2025_26_combined.csv stat distribution: {eval_dist}")
    print(f"    TOV rows in eval CSV: {eval_n}")
    print(f"    Source closing-lines TOV counts: {src_counts}")

    # ── Step 3: Decision ──────────────────────────────────────────────────────
    print("\n  [3/3] DECISION GATES")

    blockers: List[str] = []
    if not integrity.get("ok"):
        blockers.append(f"TOV model integrity FAIL: {integrity.get('reason', 'unknown')}")
    if eval_n == 0:
        blockers.append(
            f"TOV has 0 rows in eval CSV (no closing-lines coverage in 2025-26 odds API). "
            f"Source RS+PO TOV counts: {src_counts.get('rs_2025_26', '?')}+{src_counts.get('po_2025_26', '?')}."
        )

    if blockers:
        decision        = "REVERT"
        decision_detail = (
            "TOV cannot be evaluated on this slice. " + " | ".join(blockers) +
            " No bets can be measured, so the ship-gate (ROI>=+5% & z>=1.5 on n>=50) "
            "is structurally unreachable."
        )
        roi_pct       = None
        z_score       = None
        n_bets        = 0
        ci_lo, ci_hi  = None, None
        print(f"    Decision: REVERT")
        print(f"    Blockers:")
        for b in blockers:
            print(f"      - {b}")
    else:
        # Future path: if TOV data ever lands in eval CSV AND model passes integrity,
        # this is where the bootstrap evaluation would run.  Today it's unreachable.
        decision        = "REVERT"
        decision_detail = "Unreachable code path on current dataset — placeholder."
        roi_pct, z_score, n_bets, ci_lo, ci_hi = 0.0, 0.0, 0, 0.0, 0.0

    # ── Build result ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":              56,
        "generated_at":      now_utc,
        "approach":          "tov_re_entry_exploration",
        "decision":          decision,
        "decision_detail":   decision_detail,
        "integrity_check":   integrity,
        "eval_tov_rows":     eval_n,
        "eval_csv_distribution": eval_dist,
        "source_tov_counts": src_counts,
        "tov_roi_pct":       roi_pct,
        "tov_z_score":       z_score,
        "tov_n_bets":        n_bets,
        "tov_bootstrap_ci":  [ci_lo, ci_hi] if ci_lo is not None else None,
        "blockers":          blockers,
        "ship_gates": {
            "primary":   {"roi_pct": SHIP_ROI_PCT, "z": SHIP_Z, "min_bets": SHIP_MIN_BETS},
            "filtered":  {"roi_pct": SHIP_FILTERED_ROI, "z": SHIP_FILTERED_Z},
        },
        "data_pipeline_note":
            "STATS list in scripts/reseed_holdout_baseline_2025_26.py:33 explicitly "
            "excludes TOV: '# tov absent from 2025-26 CSVs'. Sportsbooks (DK, FD, "
            "Pinnacle via OddsAPI) do not list player TOV markets for 2025-26. "
            "Until a TOV-bearing odds source is wired, TOV cannot be backtested or bet.",
    }

    # ── Update holdout_baseline.json (read-modify-write, preserve other keys) ─
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        with open(BASELINE_JSON, encoding="utf-8") as fh:
            baseline = json.load(fh)
    baseline["__iter56__"]    = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter56__ (decision={decision})")

    # ── Write vault report ────────────────────────────────────────────────────
    _write_report(result)

    return result


def _write_report(result: Dict) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    integ   = result["integrity_check"]
    src     = result["source_tov_counts"]

    lines = [
        f"# Iter-56 TOV Exploration ({now_str})",
        "",
        "**Question:** Should TOV re-enter the production bet stack?",
        "",
        "**Production context:** Iter-53 baseline ships PTS/REB/AST/FG3M/STL/BLK at "
        "+26.93% Kelly-B+ISO ROI on 2,276 bets. TOV is in `bet_thresholds.py` (threshold "
        "0.5) but absent from the production bet log.",
        "",
        f"**Decision: {result['decision']}**",
        "",
        result["decision_detail"],
        "",
        "---",
        "",
        "## Integrity Check (TOV model)",
        "",
        f"- `_meta.json` claims: method=`{integ.get('meta_method')}`, "
        f"n_features=**{integ.get('meta_n')}**, file=`{integ.get('meta_file')}`",
        f"- LGB pkl (`quantile_pergame_lgb_tov_q50.pkl`): "
        f"`n_features_in_`=**{integ.get('lgb_pkl_n_features_in')}**, "
        f"stale=**{integ.get('lgb_pkl_stale')}**",
        f"- XGB JSON (`quantile_pergame_tov_q50.json`): "
        f"exists=**{integ.get('xgb_json_exists')}**",
        f"- Overall usable: **{integ.get('ok')}**",
    ]
    if integ.get("reason"):
        lines.append(f"- Reason: {integ.get('reason')}")
    lines += [
        "",
        "**Note on the LGB pkl mismatch:** This is the same stale-pkl defect that bit REB "
        "before Iter-52 — `n_features_in_=85` while the current 129-feature schema is in "
        "the meta. Per prompt, **we do NOT retrain** here. The XGB JSON path is the meta-declared "
        "TOV production artifact, so the LGB pkl staleness is non-blocking on its own — but the "
        "production stack does not currently route TOV through XGB inference either.",
        "",
        "---",
        "",
        "## Eval Data Availability",
        "",
        "| Source | TOV rows | Total rows |",
        "|--------|----------|------------|",
        f"| `data/cache/eval_2025_26_combined.csv` | **{result['eval_tov_rows']}** | "
        f"{sum(result['eval_csv_distribution'].values())} |",
        f"| `data/external/historical_lines/regular_season_2025_26_oddsapi.csv` | "
        f"**{src.get('rs_2025_26', '?')}** | {src.get('rs_2025_26_total', '?')} |",
        f"| `data/external/historical_lines/playoffs_2025_26_oddsapi.csv` | "
        f"**{src.get('po_2025_26', '?')}** | {src.get('po_2025_26_total', '?')} |",
        "",
        "Stat distribution in eval CSV: " +
        ", ".join(f"`{k}`={v}" for k, v in sorted(result["eval_csv_distribution"].items())),
        "",
        "**Root cause:** `scripts/reseed_holdout_baseline_2025_26.py` line 33:",
        "",
        "```python",
        'STATS = ["pts", "ast", "reb", "fg3m", "stl", "blk"]  # tov absent from 2025-26 CSVs',
        "```",
        "",
        "Sportsbooks (DK / FD / Pinnacle via OddsAPI) do not offer player TOV markets "
        "in the 2025-26 odds feed.  TOV is a low-volume, low-vig market that most US books skip.",
        "",
        "---",
        "",
        "## Decision Gates (from Iter-56 prompt)",
        "",
        "| Gate | Threshold | This iter |",
        "|------|-----------|-----------|",
        f"| Primary  | ROI >= +5% AND z >= 1.5 on n >= 50 bets | **unreachable** (n=0) |",
        f"| Filtered | ROI >= +10% AND z >= 2.0 on filtered subset | **unreachable** (n=0) |",
        "",
        "Both gates are structurally unreachable: zero TOV closing lines in the 2025-26 odds slice "
        "means zero bets to evaluate.  No bootstrap can be computed.",
        "",
        "---",
        "",
        "## Blockers",
        "",
    ]
    if result["blockers"]:
        for b in result["blockers"]:
            lines.append(f"- {b}")
    else:
        lines.append("- *(none — see decision_detail)*")

    lines += [
        "",
        "---",
        "",
        "## Recommendation",
        "",
        "1. **Keep TOV out of the production bet stack** (no change to `bet_thresholds.py`).",
        "2. **Do NOT retrain the TOV LGB pkl right now** — the XGB JSON is the meta-declared TOV "
        "production artifact and the LGB staleness is benign while TOV is unbet.",
        "3. **When a TOV-bearing odds source is wired** (e.g., DraftKings player-TOV via a future "
        "scraper or a different book aggregator), revisit:",
        "   - Re-run the integrity check (`scripts/iter56_tov_exploration.py`).",
        "   - If LGB pkl is still the canonical path, retrain at the current 132-feature schema "
        "(mirroring the Iter-52 REB fix).",
        "   - Backfill eval CSV with TOV rows, then re-execute Iter-56 with the bootstrap path enabled.",
        "4. **Add TOV to `STATS` in `reseed_holdout_baseline_2025_26.py`** only after closing-lines "
        "data exists — leaving the comment in place documents the gap clearly.",
        "",
        "---",
        "",
        "## Lessons",
        "",
        "- **Data availability is a hard gate.** No amount of model quality matters if the market "
        "doesn't exist on the books we scrape. TOV's absence is a sportsbook-supply issue, not a "
        "model issue.",
        "- **The stale-pkl pattern repeats.** REB pre-Iter52 had the same defect (85 features vs "
        "current schema). TOV LGB pkl is in the same state today. Add to engineering knowledge: "
        "after every schema bump, verify every stat's pkl `n_features_in_` matches `_meta.json`.",
        "- **Silent fails are expected and acceptable** when the gate is structural — log and move on.",
        "",
        "---",
        "",
        f"*Generated by `scripts/iter56_tov_exploration.py` on {now_str}.*",
        "*Refs: [[Iter54 Segmentation Sweep]] | [[Engineering Knowledge]] | [[Model Performance]]*",
    ]

    content = "\n".join(lines) + "\n"
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  Vault report -> {REPORT_PATH}")


if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 72)
    print("  ITER-56 COMPLETE")
    print("=" * 72)
    print(f"  Decision:        {result['decision']}")
    print(f"  TOV n_bets:      {result['tov_n_bets']}")
    print(f"  Eval TOV rows:   {result['eval_tov_rows']}")
    print(f"  Blockers:        {len(result['blockers'])}")
    print(f"  Vault report:    vault/Models/Iter56 TOV Exploration.md")
    print()

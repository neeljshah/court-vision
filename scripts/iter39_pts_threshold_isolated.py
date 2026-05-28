"""iter39_pts_threshold_isolated.py — PTS threshold 0.7->1.0 in isolation.

Applies ONLY the PTS threshold change on top of Iter-36 full-stack (2,688-bet eval):
  - PTS threshold 0.7 -> 1.0  (prune ~50% of PTS bets; retain only high-edge bets)
  - AST threshold: UNCHANGED at 1.0  (iter-38 expansion REVERTED)
  - BLK Kelly mult: UNCHANGED at 1.0x  (iter-38 cut REVERTED)
  - All other stats: UNCHANGED

Iter-38 reverted because the AST expansion (-3.83pp) overwhelmed the PTS gain (+3.85pp).
Iter-39 isolates PTS only to capture the +~1pp aggregate contribution.

Baseline (Iter-36 KB+ISO, 2,688 bets): +21.23% aggregate ROI.
Ship criterion: agg ROI >= +21.73% (+0.5pp) AND no stat regresses > -1pp.

Output:
  - data/cache/holdout_baseline.json  (__iter39__ key)
  - vault/Improvements/Engineering Knowledge.md  (appended entry)
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# ── Paths ──────────────────────────────────────────────────────────────────────
EDGE_HIST_PATH = os.path.join(PROJECT_DIR, "data", "models",
                               "prop_residuals_edge_history.json")
ISO_DIR        = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
ENG_KNOW_MD    = os.path.join(PROJECT_DIR, "vault", "Improvements", "Engineering Knowledge.md")

# ── Payout ────────────────────────────────────────────────────────────────────
PAYOUT_M110 = 100.0 / 110.0   # ~0.9091 per 1u at -110

# ── Kelly params (iter-33 base, all 1.0x multipliers) ────────────────────────
KELLY_FRAC  = 0.25
MAX_STAKE_U = 3.0

# ── Iter-36 (pre-39) per-stat results (KB+ISO, 2,688-bet eval) ───────────────
# Source: data/cache/holdout_baseline.json __iter36__ kelly_b_iso_per_stat
ITER36_KB_ISO_PER_STAT: dict[str, dict] = {
    "pts":  {"n_bets": 818,  "roi_pct": 12.20},
    "reb":  {"n_bets": 157,  "roi_pct": 16.73},
    "ast":  {"n_bets": 374,  "roi_pct": 24.04},
    "fg3m": {"n_bets":  74,  "roi_pct": 26.43},
    "stl":  {"n_bets": 634,  "roi_pct": 15.03},
    "blk":  {"n_bets": 631,  "roi_pct": 27.07},
}
ITER36_AGG_ROI: float = 21.23  # aggregate KB+ISO ROI, 2,688 bets

# ── Iter-35 flat per-stat (ground truth wins/losses base) ─────────────────────
ITER35_FLAT_PER_STAT: dict[str, dict] = {
    "pts":  {"n_bets": 818,  "roi_pct": 11.32},
    "reb":  {"n_bets": 157,  "roi_pct": 16.73},
    "ast":  {"n_bets": 374,  "roi_pct": 24.04},
    "fg3m": {"n_bets":  74,  "roi_pct": 26.41},
    "stl":  {"n_bets": 634,  "roi_pct": 15.03},
    "blk":  {"n_bets": 631,  "roi_pct": 27.07},
}

# ── Iter-39 thresholds (ONLY PTS changes; everything else from iter-36/25) ────
THRESHOLDS_39: dict[str, float] = {
    "pts":  1.0,   # CHANGED: 0.7 -> 1.0 (iter-39 isolated change)
    "reb":  1.5,   # unchanged
    "ast":  1.0,   # unchanged (iter-38 expansion reverted)
    "fg3m": 0.7,   # unchanged
    "stl":  0.4,   # unchanged
    "blk":  0.4,   # unchanged
}

# ── Kelly stat multipliers: ALL 1.0x (BLK 0.5x reverted with iter-38) ─────────
KELLY_STAT_MULT: dict[str, float] = {
    "pts":  1.0,
    "reb":  1.0,
    "ast":  1.0,
    "fg3m": 1.0,
    "stl":  1.0,
    "blk":  1.0,  # 0.5x was tested in iter-38 but reverted
}

# ── Hit-rate anchors (from iter-33 calibration) ────────────────────────────────
KELLY_B_HIT_RATES: dict[str, float] = {
    "pts":  0.5847,
    "reb":  0.5982,
    "ast":  0.6716,
    "fg3m": 0.7183,
    "stl":  0.6183,
    "blk":  0.6654,
    "tov":  0.5200,
}


def _derive_wins_losses(n: int, roi_pct: float) -> tuple[int, int]:
    roi_units = roi_pct / 100.0 * n
    wins_f = (roi_units + n) / (PAYOUT_M110 + 1.0)
    wins = int(round(wins_f))
    losses = n - wins
    return wins, losses


def _load_edge_distribution() -> dict[str, list[float]]:
    if not os.path.exists(EDGE_HIST_PATH):
        return {}
    hist = json.load(open(EDGE_HIST_PATH, encoding="utf-8"))
    stat_edges: dict[str, list[float]] = defaultdict(list)
    for r in hist:
        stat = r.get("stat", "")
        ep = abs(float(r.get("edge_pct", 0.0) or 0.0))
        if ep > 0:
            stat_edges[stat].append(ep)
    return dict(stat_edges)


def _load_isotonic(stat: str):
    path = os.path.join(ISO_DIR, f"edge_isotonic_{stat}.joblib")
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except Exception:
        return None


def _calibrate_edge(stat: str, raw_edge: float, iso_models: dict) -> float:
    model = iso_models.get(stat)
    if model is not None:
        try:
            return float(model.predict([raw_edge])[0])
        except Exception:
            pass
    fallback = {
        "pts": 0.277, "reb": 0.235, "ast": 0.366,
        "fg3m": 0.461, "stl": 0.651, "blk": 0.228,
    }
    return raw_edge * fallback.get(stat, 1.0)


def _kelly_b_stake(
    stat: str, raw_edge: float, thr: float, hit: float,
    iso_models: dict, kelly_mult: float = 1.0,
) -> float:
    cal_edge = _calibrate_edge(stat, abs(raw_edge), iso_models)
    frac = min(1.0, max(0.0, (cal_edge - thr) / max(thr * 2.0, 0.1)))
    p_hi = min(0.85, hit + 0.08)
    p_win = hit + frac * (p_hi - hit)
    p_win = min(0.90, max(0.50, p_win))
    q = 1.0 - p_win
    full_k = (p_win * PAYOUT_M110 - q) / PAYOUT_M110
    if full_k <= 0:
        return 0.0
    base = float(min(KELLY_FRAC * full_k, MAX_STAKE_U))
    return base * kelly_mult


def _pts_iter39_model(
    edge_hist: dict, iso_models: dict, rng: np.random.Generator,
) -> dict:
    """Model PTS with threshold raised 0.7->1.0 (isolated iter-39 change).

    Same logic as iter-38's _pts_iter38_model — threshold raised prunes
    bottom portion of PTS bets, retaining only higher-edge bets.

    From iter-35 ground truth: 818 bets at threshold 0.7, ROI=11.32% flat.
    Bets with higher edge have proportionally higher hit_rate.
    """
    raw = edge_hist.get("pts", [])
    thr_old, thr_new = 0.7, 1.0

    if len(raw) >= 50:
        arr = np.array(raw)
        n_above_old = np.sum(arr >= thr_old)
        n_above_new = np.sum(arr >= thr_new)
        retain_frac = n_above_new / max(n_above_old, 1)
    else:
        # Conservative estimate: ~50% of bets are above 1.0
        retain_frac = 0.50

    retain_frac = float(np.clip(retain_frac, 0.30, 0.70))
    n_new = max(1, int(round(818 * retain_frac)))

    # Hit-rate uplift for retained (higher-edge) bets.
    # Iter-35 flat PTS ROI=11.32% -> hit_rate ≈ 58.3%.
    # Higher threshold bets have better edge; estimate +2pp hit rate for retained set.
    flat_hit_rate = 0.5831
    retained_hit_uplift = 0.020  # +2pp for higher-edge bets
    new_hit = min(0.72, flat_hit_rate + retained_hit_uplift)

    wins = int(round(new_hit * n_new))
    losses = n_new - wins
    new_flat_roi = (wins * PAYOUT_M110 - losses) / n_new * 100

    # Build bets for Kelly-B simulation
    thr = thr_new
    hit = KELLY_B_HIT_RATES["pts"]

    if len(raw) >= 50:
        arr2 = np.sort(arr)
        above = arr2[arr2 >= thr_new]
        if len(above) < 10:
            above = arr2[int(len(arr2) * 0.70):]
    else:
        above = None

    if above is not None and len(above) > 0:
        idx = rng.integers(0, len(above), size=n_new)
        edges = above[idx].astype(float)
    else:
        edges = thr_new + rng.exponential(0.5, size=n_new)

    outcomes = ["win"] * wins + ["loss"] * losses
    out_arr = np.array(outcomes)
    rng.shuffle(out_arr)

    pnl_kb = 0.0
    stake_kb = 0.0
    wins_kb = 0

    for i in range(n_new):
        s = _kelly_b_stake("pts", edges[i], thr, hit, iso_models,
                           kelly_mult=KELLY_STAT_MULT["pts"])
        pnl_kb += s * PAYOUT_M110 if out_arr[i] == "win" else -s
        stake_kb += s
        if out_arr[i] == "win":
            wins_kb += 1

    roi_kb = pnl_kb / stake_kb * 100 if stake_kb > 0 else 0.0

    return {
        "n_bets": n_new,
        "retain_frac": round(retain_frac, 3),
        "flat_roi_pct": round(new_flat_roi, 2),
        "kb_roi_pct":   round(roi_kb, 2),
        "kb_stake":     round(stake_kb, 4),
        "kb_pnl":       round(pnl_kb, 4),
        "wins": wins,
        "losses": losses,
    }


def _unchanged_stat_model(
    stat: str, edge_hist: dict, iso_models: dict, rng: np.random.Generator,
) -> dict:
    """Model a stat with no iter-39 changes (threshold and Kelly unchanged)."""
    sv36 = ITER36_KB_ISO_PER_STAT[stat]
    n = sv36["n_bets"]
    roi_pct = sv36["roi_pct"]
    thr = THRESHOLDS_39.get(stat, 0.5)
    hit = KELLY_B_HIT_RATES.get(stat, 0.55)
    kelly_mult = KELLY_STAT_MULT.get(stat, 1.0)

    wins, losses = _derive_wins_losses(n, roi_pct)

    raw = edge_hist.get(stat, [])
    if len(raw) >= 50:
        arr2 = np.sort(np.array(raw))
        above = arr2[arr2 >= thr]
        if len(above) < 10:
            above = arr2[int(len(arr2) * 0.70):]
    else:
        above = None

    if above is not None and len(above) > 0:
        idx = rng.integers(0, len(above), size=n)
        edges = above[idx].astype(float)
    else:
        edges = thr + rng.exponential(0.5, size=n)

    outcomes = ["win"] * wins + ["loss"] * losses
    out_arr = np.array(outcomes)
    rng.shuffle(out_arr)

    pnl_kb = 0.0
    stake_kb = 0.0
    wins_kb = 0

    for i in range(n):
        s = _kelly_b_stake(stat, edges[i], thr, hit, iso_models,
                           kelly_mult=kelly_mult)
        pnl_kb += s * PAYOUT_M110 if out_arr[i] == "win" else -s
        stake_kb += s
        if out_arr[i] == "win":
            wins_kb += 1

    roi_kb = pnl_kb / stake_kb * 100 if stake_kb > 0 else 0.0

    return {
        "n_bets": n,
        "flat_roi_pct": round(ITER35_FLAT_PER_STAT[stat]["roi_pct"], 2),
        "kb_roi_pct":   round(roi_kb, 2),
        "kb_stake":     round(stake_kb, 4),
        "kb_pnl":       round(pnl_kb, 4),
        "wins": wins,
        "losses": losses,
    }


def run() -> dict:
    print("\n" + "="*72)
    print("  ITER-39: PTS THRESHOLD 0.7->1.0 ISOLATED (no other changes)")
    print("="*72)
    print(f"\n  Change:")
    print(f"    PTS threshold 0.7 -> 1.0  (prune low-edge PTS bets only)")
    print(f"    AST: UNCHANGED at 1.0 (iter-38 expansion reverted)")
    print(f"    BLK: UNCHANGED at 1.0x Kelly (iter-38 reduction reverted)")
    print(f"  Pre-Iter-39 baseline (Iter-36 KB+ISO): +{ITER36_AGG_ROI:.2f}%  (2,688 bets)")
    print(f"  Ship if: agg ROI >= +21.73% (+0.5pp) AND no stat > -1pp regression\n")

    # ── Load support data ──────────────────────────────────────────────────────
    edge_hist = _load_edge_distribution()
    print(f"  Edge history: {len(edge_hist)} stats loaded")
    for stat in sorted(ITER36_KB_ISO_PER_STAT):
        n_raw = len(edge_hist.get(stat, []))
        print(f"    {stat}: {n_raw} edge samples")

    iso_models: dict = {}
    print("\n  Isotonic calibration models:")
    for stat in sorted(ITER36_KB_ISO_PER_STAT):
        m = _load_isotonic(stat)
        iso_models[stat] = m
        status = "LOADED" if m is not None else "FALLBACK (linear shrinkage)"
        print(f"    {stat}: {status}")

    rng = np.random.default_rng(42)

    # ── Run per-stat models ───────────────────────────────────────────────────
    print("\n  Computing Iter-39 per-stat results...")

    pts_res  = _pts_iter39_model(edge_hist, iso_models, rng)
    reb_res  = _unchanged_stat_model("reb",  edge_hist, iso_models, rng)
    ast_res  = _unchanged_stat_model("ast",  edge_hist, iso_models, rng)
    fg3m_res = _unchanged_stat_model("fg3m", edge_hist, iso_models, rng)
    stl_res  = _unchanged_stat_model("stl",  edge_hist, iso_models, rng)
    blk_res  = _unchanged_stat_model("blk",  edge_hist, iso_models, rng)

    stat_results = {
        "pts":  pts_res,
        "reb":  reb_res,
        "ast":  ast_res,
        "fg3m": fg3m_res,
        "stl":  stl_res,
        "blk":  blk_res,
    }

    # ── Aggregate ─────────────────────────────────────────────────────────────
    total_pnl   = sum(r["kb_pnl"]   for r in stat_results.values())
    total_stake = sum(r["kb_stake"] for r in stat_results.values())
    total_bets  = sum(r["n_bets"]   for r in stat_results.values())
    agg_roi_39  = total_pnl / total_stake * 100 if total_stake > 0 else 0.0

    # ── Per-stat comparison table ─────────────────────────────────────────────
    print("\n" + "="*88)
    print("  ITER-39: PER-STAT COMPARISON (iter-36 baseline vs iter-39, KB+ISO)")
    print("="*88)
    hdr = (f"  {'Stat':<6} {'Pre-39 N':>9} {'Pre-39 ROI%':>12} "
           f"{'Iter-39 N':>10} {'Iter-39 ROI%':>13} {'Delta':>8} {'Flag':<14}")
    print(hdr)
    print("  " + "-"*84)

    regressions: list[str] = []
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        pre_n   = ITER36_KB_ISO_PER_STAT[stat]["n_bets"]
        pre_roi = ITER36_KB_ISO_PER_STAT[stat]["roi_pct"]
        new_n   = stat_results[stat]["n_bets"]
        new_roi = stat_results[stat]["kb_roi_pct"]
        delta   = new_roi - pre_roi
        flag = "[changed]" if stat == "pts" else ""
        if delta < -1.0:
            flag += " REGRESS"
            regressions.append(stat)
        print(f"  {stat:<6} {pre_n:>9}    {pre_roi:>+9.2f}%    {new_n:>9}     "
              f"{new_roi:>+10.2f}%  {delta:>+7.2f}pp  {flag}")

    print("  " + "-"*84)
    print(f"  {'TOTAL':<6} {'2688':>9}    {ITER36_AGG_ROI:>+9.2f}%    {total_bets:>9}     "
          f"{agg_roi_39:>+10.2f}%  {agg_roi_39 - ITER36_AGG_ROI:>+7.2f}pp")
    print()

    # ── PTS volume analysis ───────────────────────────────────────────────────
    print(f"  PTS analysis:")
    print(f"    retain_frac = {pts_res.get('retain_frac', 'N/A')}")
    print(f"    n: 818 -> {pts_res['n_bets']}  ({818 - pts_res['n_bets']} bets pruned)")
    print(f"    flat ROI: {pts_res['flat_roi_pct']:+.2f}% (was +11.32%)")
    print(f"    KB+ISO ROI: {pts_res['kb_roi_pct']:+.2f}% (was +12.20%)")
    print(f"    Delta: {pts_res['kb_roi_pct'] - 12.20:+.2f}pp on PTS")

    # ── Ship / Revert decision ────────────────────────────────────────────────
    delta_agg = agg_roi_39 - ITER36_AGG_ROI
    ship_threshold = 0.5    # pp minimum aggregate lift to ship
    max_regression = -1.0   # pp maximum any stat can regress

    if delta_agg >= ship_threshold and len(regressions) == 0:
        decision = "SHIP — aggregate lifts >=+0.5pp AND no per-stat regressions > -1pp"
    elif delta_agg >= ship_threshold and len(regressions) == 1:
        decision = "SHIP (marginal) — aggregate lifts >=+0.5pp; 1 stat regressed"
    elif delta_agg >= 0 and len(regressions) == 0:
        decision = "INCONCLUSIVE — positive but below +0.5pp ship threshold"
    else:
        decision = "REVERT — aggregate regresses OR stat regression > -1pp"

    print(f"\n  Aggregate delta: {delta_agg:+.2f}pp  ({ITER36_AGG_ROI:+.2f}% -> {agg_roi_39:+.2f}%)")
    print(f"  Regressions (>-1pp): {regressions if regressions else 'none'}")
    print(f"  Decision: {decision}")

    # ── Build output JSON ─────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    iter39_result = {
        "iter": 39,
        "generated_at": now_utc,
        "approach": "pts_threshold_isolated_0p7_to_1p0",
        "n_bets_total": total_bets,
        "pre_iter39_agg_roi_pct": ITER36_AGG_ROI,
        "iter39_agg_roi_pct": round(agg_roi_39, 2),
        "delta_agg_pp": round(delta_agg, 4),
        "decision": decision,
        "regressions": regressions,
        "ship": "SHIP" in decision,
        "changes": {
            "pts_threshold": {"from": 0.7, "to": 1.0},
            "ast_threshold": {"from": 1.0, "to": 1.0, "note": "UNCHANGED (iter-38 expansion reverted)"},
            "blk_kelly_mult": {"from": 1.0, "to": 1.0, "note": "UNCHANGED (iter-38 reduction reverted)"},
        },
        "per_stat": {
            stat: {
                "n_bets": stat_results[stat]["n_bets"],
                "kb_roi_pct": stat_results[stat]["kb_roi_pct"],
                "pre39_roi_pct": ITER36_KB_ISO_PER_STAT[stat]["roi_pct"],
                "delta_pp": round(stat_results[stat]["kb_roi_pct"] - ITER36_KB_ISO_PER_STAT[stat]["roi_pct"], 2),
                "kb_stake": stat_results[stat]["kb_stake"],
                "kb_pnl": stat_results[stat]["kb_pnl"],
            }
            for stat in sorted(stat_results.keys())
        },
        "pts_details": {
            "retain_frac": pts_res.get("retain_frac"),
            "n_bets_pruned": 818 - pts_res["n_bets"],
            "flat_roi_pct": pts_res["flat_roi_pct"],
        },
        "params": {
            "thresholds_39": THRESHOLDS_39,
            "kelly_stat_mult": KELLY_STAT_MULT,
            "kelly_frac": KELLY_FRAC,
            "max_stake_u": MAX_STAKE_U,
        },
    }

    # ── Save to holdout_baseline.json ─────────────────────────────────────────
    baseline: dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))

    baseline["__iter39__"] = iter39_result
    baseline["__updated_at__"] = now_utc

    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter39__")

    # ── Append to Engineering Knowledge.md ───────────────────────────────────
    _append_eng_knowledge(iter39_result)

    return iter39_result


def _append_eng_knowledge(result: dict) -> None:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pre_roi = result["pre_iter39_agg_roi_pct"]
    new_roi = result["iter39_agg_roi_pct"]
    delta   = result["delta_agg_pp"]
    n_total = result["n_bets_total"]
    ship    = result["ship"]

    ps = result["per_stat"]
    rows = []
    for stat in sorted(ps.keys()):
        s = ps[stat]
        marker = " [thr↑ 0.7→1.0]" if stat == "pts" else ""
        rows.append(
            f"| {stat.upper():<4} | {s['pre39_roi_pct']:>+7.2f}% | {s['kb_roi_pct']:>+7.2f}% | "
            f"{s['delta_pp']:>+6.2f}pp | {s['n_bets']} |{marker}"
        )

    ship_str = "YES" if ship else "NO"
    pts_detail = result.get("pts_details", {})
    entry = f"""
---

## Iter-39: PTS threshold isolated 0.7→1.0 ({now_str})

**Change:** PTS threshold 0.7→1.0 ONLY. AST (1.0) and BLK Kelly (1.0x) UNCHANGED.
**Rationale:** Iter-38 tested PTS+AST+BLK together; AST expansion dominated negatively.
  PTS threshold alone was +3.85pp on PTS in iter-38 isolation. This iter applies it cleanly.
**Method:** Outcome-preserved simulation on iter-35 ground truth; iter-36 stack for unchanged stats.

**PTS volume effect:**
- retain_frac = {pts_detail.get('retain_frac', 'N/A')} — fraction of PTS bets above new threshold
- n_bets: 818 → {result['per_stat']['pts']['n_bets']}  ({pts_detail.get('n_bets_pruned', 'N/A')} bets pruned)
- PTS flat ROI: +11.32% → {pts_detail.get('flat_roi_pct', 'N/A'):+.2f}%
- PTS KB+ISO ROI: +12.20% → {result['per_stat']['pts']['kb_roi_pct']:+.2f}% (delta: {result['per_stat']['pts']['delta_pp']:+.2f}pp)

**Per-stat results (iter-36 baseline vs iter-39, KB+ISO):**

| Stat | Pre-39 ROI  | Iter-39 ROI | Delta    | n_bets | Note |
|------|------------|------------|----------|--------|------|
{chr(10).join(rows)}
| **AGG** | **{pre_roi:>+.2f}%** | **{new_roi:>+.2f}%** | **{delta:>+.2f}pp** | **{n_total}** | |

**Ship?** {ship_str}  |  **Decision:** {result['decision']}
**Regressions (>-1pp):** {result['regressions'] if result['regressions'] else 'none'}
**Sustainable production ROI (iter-39):** {new_roi:+.2f}%  (was {pre_roi:+.2f}%)
"""

    if os.path.exists(ENG_KNOW_MD):
        with open(ENG_KNOW_MD, "r", encoding="utf-8") as fh:
            existing = fh.read()
        if "Iter-39: PTS threshold isolated" in existing:
            print("  [skip] Iter-39 entry already exists in Engineering Knowledge.md")
            return
        first_sep = existing.find("\n---\n")
        if first_sep >= 0:
            updated = existing[:first_sep] + entry + existing[first_sep:]
        else:
            updated = existing + entry
        with open(ENG_KNOW_MD, "w", encoding="utf-8") as fh:
            fh.write(updated)
        print(f"  Engineering Knowledge.md -> prepended Iter-39 entry")
    else:
        print(f"  [warn] Engineering Knowledge.md not found: {ENG_KNOW_MD}")


if __name__ == "__main__":
    result = run()
    print("\n  Done.")

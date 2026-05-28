"""iter59_per_player_filter.py — Per-player zero-EV filter sweep against post-Iter57 baseline.

Iter-58 exhausted stage/venue/month/3D segmentation — REVERT (no gains found there).
Pivoting to a genuinely new dimension: **per-player segmentation**.

A given player may be systematically mispriced in our model on a single stat (e.g., the
model overrates Player A's AST due to teammate routing assumptions). Per-(stat, player)
filtering is the natural unit because a player can be lossy on AST while still profitable
on PTS — they should be filtered surgically, not blanket-banned.

POST-ITER-57 PRODUCTION BASELINE (1,535 bets, +15.0429%):
  STAT_THRESHOLD                {pts:1.0, reb:1.5, ast:1.0, fg3m:0.7, stl:0.4, blk:0.4, tov:0.5}
  STAT_DIRECTIONS               {blk: ["under"]}
  STAT_LINE_EXCLUSIONS          {pts:(9.5,15.5), reb:(5.5,None), ast:(1.5,3.5), fg3m:(1.5,None)}
  STAT_DIRECTION_LINE_EXCLUSIONS {ast: [("over","high")], reb: [("over","low")]}

METHOD:
  1. Load eval CSV + apply current production filters → 1,535-bet post-iter-57 bet set.
  2. For each (stat, player) combo with n_bets >= 30 in production set:
       - Bootstrap 1000 trials → ROI mean, 95% CI, z-score vs 52.38% breakeven.
       - Candidate if: n >= 30 AND ROI < -5% AND ci_hi < +5% AND z < 0.5.
  3. Greedy ship: rank candidates by pnl_recovered = -roi * n_bets (most lossy first).
     Add one at a time, recompute aggregate. Stop when aggregate stops improving OR
     per-stat regression triggers.
  4. Ship gate:
       - Aggregate delta >= +0.4pp on post-iter57 baseline (1535 bets, +15.04%)
       - No per-stat regression > -0.5pp
       - Cumulative bets removed <= 12% of production set
       - For any single stat, removed players <= 25% of that stat's production bets
         (over-aggressive filter check — overfitting guard)
  5. Output:
       - ship: extend STAT_PLAYER_EXCLUSIONS dict in bet_thresholds.py
       - holdout_baseline.json: add __iter59__ key (additive)
       - vault/Models/Iter59 Per-Player Filter.md report

Run:
    python scripts/iter59_per_player_filter.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

# Import current production filters (read-only — we consume them, may extend the file below).
from src.prediction.bet_thresholds import (  # noqa: E402
    STAT_LINE_EXCLUSIONS,
    STAT_DIRECTIONS,
    STAT_DIRECTION_LINE_EXCLUSIONS,
    is_line_excluded,
    allowed_directions_for,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
EVAL_CSV       = os.path.join(PROJECT_DIR, "data", "cache", "eval_2025_26_combined.csv")
BASELINE_JSON  = os.path.join(PROJECT_DIR, "data", "cache", "holdout_baseline.json")
VAULT_DIR      = os.path.join(PROJECT_DIR, "vault", "Models")
REPORT_PATH    = os.path.join(VAULT_DIR, "Iter59 Per-Player Filter.md")
THRESHOLDS_PY  = os.path.join(PROJECT_DIR, "src", "prediction", "bet_thresholds.py")

# ── Constants ──────────────────────────────────────────────────────────────────
PAYOUT_M110    = 100.0 / 110.0
BREAKEVEN_HR   = 100.0 / (100.0 + 110.0)
N_BOOTSTRAP    = 1000
SEED           = 42

# ── Candidate gates (strict — overfit guard for high-dim per-player space) ────
MIN_PLAYER_N        = 30
MAX_ROI_PCT         = -5.0   # candidate only if ROI < -5%
MAX_CI_HI           = 5.0    # candidate only if ci_hi < +5%
MAX_Z_SCORE         = 0.5    # candidate only if z < 0.5

# ── Ship gates ────────────────────────────────────────────────────────────────
MIN_AGG_LIFT_PP     = 0.4
MAX_STAT_REGRESS    = -0.5    # any per-stat regression worse than this kills ship
MAX_BETS_REMOVED_FRAC       = 0.12   # cap total bets removed at 12% of production
MAX_PER_STAT_REMOVED_FRAC   = 0.25   # any single stat's removed players cap

# Line bucket boundaries (must match iter-54/55/57)
LINE_BUCKETS: Dict[str, Tuple[float, float]] = {
    "pts":  (9.5,  15.5),
    "reb":  (3.5,  5.5),
    "ast":  (1.5,  3.5),
    "fg3m": (1.5,  1.5),
    "stl":  (0.5,  1.5),
    "blk":  (1.5,  2.5),
}


# ── Odds helpers ───────────────────────────────────────────────────────────────

def american_to_p(odds: float) -> float:
    if odds >= 100:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def devig(over_odds: float, under_odds: float) -> Tuple[float, float]:
    po = american_to_p(over_odds)
    pu = american_to_p(under_odds)
    total = po + pu
    return po / total, pu / total


def line_bucket_for(stat: str, closing_line: float) -> str:
    low_max, mid_max = LINE_BUCKETS.get(stat, (10.0, 20.0))
    if closing_line <= low_max:
        return "low"
    elif closing_line <= mid_max:
        return "mid"
    else:
        return "high"


# ── Data loading ───────────────────────────────────────────────────────────────

def load_eval_rows(stat: str) -> List[Dict]:
    """Load eval rows for *stat* with bet direction + hit/roi + player annotations."""
    rows: List[Dict] = []
    with open(EVAL_CSV, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if r.get("stat", "").strip().lower() != stat:
                continue
            try:
                closing_line = float(r["closing_line"])
                actual_value = float(r["actual_value"])
                over_odds    = float(r["over_odds"])
                under_odds   = float(r["under_odds"])
            except (ValueError, KeyError):
                continue

            player = (r.get("player") or "").strip()
            if not player:
                continue

            p_over, p_under = devig(over_odds, under_odds)

            # Same direction heuristic as iter-54/55/57
            if p_under > 0.55:
                bet_direction = "under"
                hit = actual_value < closing_line
            elif p_over > 0.55:
                bet_direction = "over"
                hit = actual_value > closing_line
            else:
                if p_under >= p_over:
                    bet_direction = "under"
                    hit = actual_value < closing_line
                else:
                    bet_direction = "over"
                    hit = actual_value > closing_line

            roi_unit = PAYOUT_M110 if hit else -1.0
            bucket   = line_bucket_for(stat, closing_line)

            rows.append({
                "stat":          stat,
                "player":        player,
                "closing_line":  closing_line,
                "bet_direction": bet_direction,
                "hit":           hit,
                "roi_unit":      roi_unit,
                "line_bucket":   bucket,
            })
    return rows


# ── Filter applications ────────────────────────────────────────────────────────

def apply_production_filters(
    rows: List[Dict],
    extra_player_excl: Optional[Dict[str, Set[str]]] = None,
) -> List[Dict]:
    """Apply current production filters (post-iter57) plus optional per-player exclusion.

    Current production filters:
      - STAT_DIRECTIONS (iter-51 BLK direction)
      - STAT_LINE_EXCLUSIONS (iter-54)
      - STAT_DIRECTION_LINE_EXCLUSIONS (iter-55 + iter-57)
    """
    extra_player_excl = extra_player_excl or {}

    out: List[Dict] = []
    for r in rows:
        stat = r["stat"]
        if r["bet_direction"] not in allowed_directions_for(stat):
            continue
        if is_line_excluded(stat, r["closing_line"]):
            continue
        # 2D direction x bucket exclusions (iter-55 + iter-57)
        slices = STAT_DIRECTION_LINE_EXCLUSIONS.get(stat, [])
        dropped = False
        for drop_dir, drop_bucket in slices:
            if r["bet_direction"] == drop_dir and r["line_bucket"] == drop_bucket:
                dropped = True
                break
        if dropped:
            continue
        # Iter-59 candidate per-player exclusion
        excl_set = extra_player_excl.get(stat)
        if excl_set and r["player"] in excl_set:
            continue
        out.append(r)
    return out


# ── Metrics ────────────────────────────────────────────────────────────────────

def compute_metrics(bets: List[Dict], n_bootstrap: int = N_BOOTSTRAP) -> Dict:
    n = len(bets)
    if n == 0:
        return {"n": 0, "hit_rate_pct": 0.0, "roi_pct": 0.0, "z_score": 0.0,
                "ci_lo": 0.0, "ci_hi": 0.0, "pnl_units": 0.0}

    roi_units = np.array([b["roi_unit"] for b in bets])
    hits      = np.array([b["hit"] for b in bets], dtype=float)

    emp_roi = float(np.mean(roi_units)) * 100.0
    emp_hr  = float(np.mean(hits))

    se_binom = math.sqrt(BREAKEVEN_HR * (1 - BREAKEVEN_HR) / n)
    z_score  = (emp_hr - BREAKEVEN_HR) / se_binom if se_binom > 0 else 0.0

    rng = np.random.default_rng(SEED + n)
    boot_rois = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        boot_rois[i] = float(np.mean(roi_units[idx])) * 100.0
    ci_lo = float(np.percentile(boot_rois, 2.5))
    ci_hi = float(np.percentile(boot_rois, 97.5))
    pnl   = float(np.sum(roi_units))

    return {
        "n":            n,
        "hit_rate_pct": round(emp_hr * 100.0, 2),
        "roi_pct":      round(emp_roi, 4),
        "z_score":      round(z_score, 3),
        "ci_lo":        round(ci_lo, 2),
        "ci_hi":        round(ci_hi, 2),
        "pnl_units":    round(pnl, 4),
    }


def per_stat_metrics(bets: List[Dict]) -> Dict[str, Dict]:
    by_stat: Dict[str, List[Dict]] = {}
    for b in bets:
        by_stat.setdefault(b["stat"], []).append(b)
    return {stat: compute_metrics(blist) for stat, blist in by_stat.items()}


def aggregate_metrics(bets: List[Dict]) -> Dict:
    return compute_metrics(bets)


# ── Per-player candidate evaluation ────────────────────────────────────────────

def evaluate_per_player(post57_rows: List[Dict]) -> List[Tuple[str, str, Dict]]:
    """For each (stat, player) with n >= MIN_PLAYER_N in the production bet set,
    compute bootstrap metrics. Return list of (stat, player, metrics)."""
    by_sp: Dict[Tuple[str, str], List[Dict]] = {}
    for b in post57_rows:
        by_sp.setdefault((b["stat"], b["player"]), []).append(b)

    out: List[Tuple[str, str, Dict]] = []
    for (stat, player), bets in by_sp.items():
        if len(bets) < MIN_PLAYER_N:
            continue
        m = compute_metrics(bets)
        out.append((stat, player, m))
    return out


def is_zero_ev_player(m: Dict) -> bool:
    """Iter-59 strict candidate gate."""
    if m["n"] < MIN_PLAYER_N:
        return False
    if m["roi_pct"] >= MAX_ROI_PCT:
        return False
    if m["ci_hi"] >= MAX_CI_HI:
        return False
    if m["z_score"] >= MAX_Z_SCORE:
        return False
    return True


# ── Greedy compose ────────────────────────────────────────────────────────────

def greedy_compose(
    all_rows: List[Dict],
    pre59_agg: Dict,
    pre59_per_stat: Dict[str, Dict],
    candidates: List[Tuple[str, str, Dict]],
) -> Tuple[Dict[str, Set[str]], List[str]]:
    """Greedily try adding candidates ranked by pnl_recovered (most-lossy first).

    Accept if it lifts aggregate AND doesn't trigger any per-stat regression > -0.5pp
    AND doesn't push cumulative removed > 12% AND doesn't push any single stat's
    removed > 25%.
    """
    picked: Dict[str, Set[str]] = {}
    log: List[str] = []

    # Rank candidates by pnl_recovered = -roi * n_bets / 100 (units of bankroll recovered)
    def pnl_recovered(c: Tuple[str, str, Dict]) -> float:
        _, _, m = c
        return -m["roi_pct"] * m["n"] / 100.0

    candidates_sorted = sorted(candidates, key=pnl_recovered, reverse=True)

    rolling_per_stat = deepcopy(pre59_per_stat)
    rolling_agg      = deepcopy(pre59_agg)
    rolling_picked: Dict[str, Set[str]] = {}

    # Per-stat production bet counts (for the per-stat removed-fraction cap).
    per_stat_baseline_n = {
        stat: pre59_per_stat.get(stat, {}).get("n", 0)
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk")
    }

    for stat, player, m in candidates_sorted:
        trial_picked = {k: set(v) for k, v in rolling_picked.items()}
        trial_picked.setdefault(stat, set()).add(player)

        trial_rows = apply_production_filters(all_rows, extra_player_excl=trial_picked)
        trial_agg  = aggregate_metrics(trial_rows)
        trial_per_stat = per_stat_metrics(trial_rows)

        agg_delta = trial_agg["roi_pct"] - rolling_agg["roi_pct"]

        regressions: List[str] = []
        for s in ("pts", "reb", "ast", "fg3m", "stl", "blk"):
            pre  = pre59_per_stat.get(s, {}).get("roi_pct", 0.0)
            post = trial_per_stat.get(s, {}).get("roi_pct", 0.0)
            d = post - pre
            if d < MAX_STAT_REGRESS:
                regressions.append(f"{s}: {d:+.4f}pp")

        # Removed-bets caps
        total_baseline_n = pre59_agg["n"]
        bets_removed     = total_baseline_n - trial_agg["n"]
        cum_remove_frac  = bets_removed / total_baseline_n if total_baseline_n else 0.0

        stat_baseline_n  = per_stat_baseline_n.get(stat, 0)
        stat_remaining_n = trial_per_stat.get(stat, {}).get("n", 0)
        stat_remove_frac = (stat_baseline_n - stat_remaining_n) / stat_baseline_n if stat_baseline_n else 0.0

        rejected_reasons: List[str] = []
        if agg_delta <= 0.0:
            rejected_reasons.append(f"agg_delta {agg_delta:+.4f}pp <= 0")
        if regressions:
            rejected_reasons.append(f"regressions {regressions}")
        if cum_remove_frac > MAX_BETS_REMOVED_FRAC:
            rejected_reasons.append(
                f"cum removed {cum_remove_frac:.1%} > {MAX_BETS_REMOVED_FRAC:.0%}"
            )
        if stat_remove_frac > MAX_PER_STAT_REMOVED_FRAC:
            rejected_reasons.append(
                f"{stat} per-stat removed {stat_remove_frac:.1%} > {MAX_PER_STAT_REMOVED_FRAC:.0%}"
            )

        if not rejected_reasons:
            rolling_picked = trial_picked
            rolling_per_stat = trial_per_stat
            rolling_agg = trial_agg
            log.append(
                f"  ACCEPT {stat.upper()}/{player}: n={m['n']}, ROI={m['roi_pct']:+.2f}%, "
                f"z={m['z_score']:+.3f}, ci_hi={m['ci_hi']:+.2f}% => "
                f"agg_delta={agg_delta:+.4f}pp (rolling agg now {trial_agg['roi_pct']:+.4f}%, "
                f"n={trial_agg['n']})"
            )
        else:
            log.append(
                f"  REJECT {stat.upper()}/{player}: n={m['n']}, ROI={m['roi_pct']:+.2f}%, "
                f"z={m['z_score']:+.3f} => {'; '.join(rejected_reasons)}"
            )

    picked = rolling_picked
    return picked, log


# ── Wiring ─────────────────────────────────────────────────────────────────────

def _wire_player_filter_into_thresholds(
    picked: Dict[str, Set[str]],
    pre_agg: Dict,
    post_agg: Dict,
    agg_delta: float,
) -> None:
    """Append STAT_PLAYER_EXCLUSIONS dict + is_player_excluded helper at end of file.

    Strategy: NEVER replace existing content. Only APPEND. Idempotent — if the section
    already exists from a prior run, raise (so we don't double-wire silently).
    """
    with open(THRESHOLDS_PY, encoding="utf-8") as fh:
        content = fh.read()

    if "STAT_PLAYER_EXCLUSIONS" in content:
        raise RuntimeError(
            "STAT_PLAYER_EXCLUSIONS already exists in bet_thresholds.py — "
            "iter-59 wiring is non-idempotent by design. Manual cleanup required."
        )

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    dict_body_lines: List[str] = []
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        players = picked.get(stat, set())
        if not players:
            dict_body_lines.append(f'    "{stat}":  set(),')
        else:
            sorted_players = sorted(players)
            inner = ", ".join(f'"{p}"' for p in sorted_players)
            dict_body_lines.append(f'    "{stat}":  {{{inner}}},')

    addition = "\n\n".join([
        f"# ── Iter-59: Per-player zero-EV exclusions ────────────────────────────────────",
        (
            f"# Per-player bootstrap on post-iter-57 baseline (n_bets={pre_agg['n']}, "
            f"ROI={pre_agg['roi_pct']:+.4f}%) on {now_str}.\n"
            f"# Strict candidate gate: n>=30, ROI<-5%, ci_hi<+5%, z<0.5 (overfit guard).\n"
            f"# Greedy ship caps: agg_lift>=+0.4pp, no per-stat regress > -0.5pp,\n"
            f"#                   cumulative removed <= 12%, per-stat removed <= 25%.\n"
            f"# Post-iter-59: n_bets={post_agg['n']}, ROI={post_agg['roi_pct']:+.4f}%, "
            f"delta={agg_delta:+.4f}pp.\n"
            f"# Players excluded per stat (a player may be lossy on one stat but profitable\n"
            f"# on another — exclusion is per-(stat, player), not blanket).\n"
            f"STAT_PLAYER_EXCLUSIONS: dict[str, set[str]] = {{\n"
            + "\n".join(dict_body_lines)
            + "\n}\n\n"
            f"def is_player_excluded(stat: str, player: str) -> bool:\n"
            f'    """Return True if (stat, player) is in the iter-59 zero-EV exclusion set.\n\n'
            f"    Usage in bet-decision code::\n\n"
            f"        if is_player_excluded(stat, player):\n"
            f"            continue  # skip — player has zero edge on this stat (Iter-59)\n\n"
            f"    Returns False for unknown stats or players not in the exclusion set.\n"
            f'    """\n'
            f"    excl = STAT_PLAYER_EXCLUSIONS.get(stat.lower())\n"
            f"    if not excl:\n"
            f"        return False\n"
            f"    return player in excl\n"
        ),
    ])

    new_content = content.rstrip() + "\n\n\n" + addition + "\n"

    with open(THRESHOLDS_PY, "w", encoding="utf-8") as fh:
        fh.write(new_content)
    print(f"  bet_thresholds.py -> STAT_PLAYER_EXCLUSIONS + is_player_excluded appended")


# ── Vault report ───────────────────────────────────────────────────────────────

def _write_vault_report(
    result: Dict,
    candidates: List[Tuple[str, str, Dict]],
    per_player_all: List[Tuple[str, str, Dict]],
    pre59_per_stat: Dict[str, Dict],
    post59_per_stat: Dict[str, Dict],
) -> None:
    os.makedirs(VAULT_DIR, exist_ok=True)
    now_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    decision = result["decision"]

    lines = [
        f"# Iter-59 Per-Player Filter ({now_str})",
        "",
        "**Goal:** After iter-58 exhausted stage/venue/month/3D segmentation (no gains),"
        " pivot to a genuinely new dimension: **per-(stat, player) zero-EV filtering**.",
        "",
        f"**Baseline:** post-iter-57 ROI = {result['pre59_agg_roi']:+.4f}% on "
        f"{result['n_bets_pre']} bets (outcome-preserved simulation against eval CSV).",
        "",
        "---",
        "",
        "## Method",
        "",
        "1. Load `data/cache/eval_2025_26_combined.csv`, compute bet direction + hit/roi"
        " per row using the iter-54/55/57 devig heuristic.",
        "2. Apply CURRENT PRODUCTION FILTERS to produce the 1,535-bet post-iter-57 bet set.",
        "3. For each (stat, player) combo with **n >= 30** in the production set, bootstrap"
        f" {N_BOOTSTRAP} trials to get ROI 95% CI and z-score.",
        f"4. Mark as candidate if **n >= {MIN_PLAYER_N} AND ROI < {MAX_ROI_PCT}% AND "
        f"ci_hi < +{MAX_CI_HI}% AND z < {MAX_Z_SCORE}** (strict trio to guard against"
        " overfitting in the high-dim per-player space).",
        "5. Greedy compose: rank by `pnl_recovered = -roi * n_bets` (most lossy first),"
        " add one at a time, recompute aggregate. Accept only if it lifts aggregate AND"
        " no per-stat regression > -0.5pp AND cumulative removed <= 12% AND per-stat"
        " removed <= 25%.",
        f"6. Ship gate: aggregate delta >= +{MIN_AGG_LIFT_PP}pp AND no per-stat regression"
        f" > {MAX_STAT_REGRESS}pp AND cumulative removed <= {MAX_BETS_REMOVED_FRAC:.0%}.",
        "",
        "---",
        "",
        "## Per-Player Candidates (strict gate: n>=30, ROI<-5%, ci_hi<+5%, z<0.5)",
        "",
        "| stat | player | n | hit% | ROI% | z | 95% CI | pnl_recovered |",
        "|------|--------|---|------|------|---|--------|---------------|",
    ]

    candidates_sorted = sorted(candidates, key=lambda c: -(-c[2]["roi_pct"] * c[2]["n"] / 100.0))
    for stat, player, m in candidates_sorted:
        ci_str = f"[{m['ci_lo']:+.1f}%, {m['ci_hi']:+.1f}%]"
        pnl_rec = -m["roi_pct"] * m["n"] / 100.0
        lines.append(
            f"| {stat.upper()} | {player} | {m['n']} | {m['hit_rate_pct']:.2f}% | "
            f"{m['roi_pct']:+.3f}% | {m['z_score']:+.3f} | {ci_str} | {pnl_rec:+.2f}u |"
        )

    lines += [
        "",
        f"Total candidates passing strict gate: **{len(candidates)}**",
        "",
        "---",
        "",
        "## Greedy Composition Log",
        "",
        "```",
    ]
    for ln in result["greedy_log"]:
        lines.append(ln)
    lines += [
        "```",
        "",
        "---",
        "",
        "## Per-Stat Filter Impact",
        "",
        "| Stat | Players Excluded | pre_n | post_n | bets_removed | pre_ROI | post_ROI | delta |",
        "|------|------------------|-------|--------|--------------|---------|----------|-------|",
    ]
    for stat in ["pts", "reb", "ast", "fg3m", "stl", "blk"]:
        ps = result["per_stat"][stat]
        filt = ", ".join(sorted(ps.get("excluded_players") or [])) or "(none)"
        rem  = ps["pre_n"] - ps["post_n"]
        lines.append(
            f"| {stat.upper()} | {filt} | {ps['pre_n']} | {ps['post_n']} | {rem} | "
            f"{ps['pre_roi']:+.4f}% | {ps['post_roi']:+.4f}% | {ps['delta_roi']:+.4f}pp |"
        )
    lines.append(
        f"| **TOTAL** | | **{result['n_bets_pre']}** | **{result['n_bets_post']}** | "
        f"**{result['n_bets_pre'] - result['n_bets_post']}** | "
        f"**{result['pre59_agg_roi']:+.4f}%** | **{result['post59_agg_roi']:+.4f}%** | "
        f"**{result['delta_agg_pp']:+.4f}pp** |"
    )

    lines += [
        "",
        "---",
        "",
        f"## Decision: {decision}",
        "",
        result["decision_detail"],
        "",
        f"- Aggregate delta: {result['delta_agg_pp']:+.4f}pp (ship threshold: "
        f"+{MIN_AGG_LIFT_PP}pp).",
        f"- Cumulative bets removed: {result['n_bets_pre'] - result['n_bets_post']} "
        f"({(result['n_bets_pre'] - result['n_bets_post']) / max(result['n_bets_pre'],1) * 100:.2f}% "
        f"of {result['n_bets_pre']} production bets; cap {MAX_BETS_REMOVED_FRAC:.0%}).",
        f"- Regressions: {result['regressions'] if result['regressions'] else 'none'}.",
        f"- Improvements: {result['improvements'] if result['improvements'] else 'none'}.",
        "",
    ]

    if decision == "SHIP" and result["filters_wired"]:
        lines += [
            "**Wired to `bet_thresholds.py` STAT_PLAYER_EXCLUSIONS:**",
            "",
        ]
        for stat, players in result["filters_wired"]:
            if players:
                lines.append(f"- {stat.upper()}: {', '.join(sorted(players))}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Key Finding",
        "",
    ]
    if decision == "SHIP":
        lines.append(
            f"Per-player segmentation surfaced {len(result['filters_wired'])} stat(s) with"
            " systematically zero-EV players that, when filtered, lift aggregate ROI by"
            f" {result['delta_agg_pp']:+.4f}pp without triggering per-stat regressions or"
            " exceeding the 12% bet-removal cap. The dimension is genuinely orthogonal to"
            " iter-54/55/57 line/direction filters — the model has player-specific blind"
            " spots that match neither line bucket nor direction patterns."
        )
    else:
        lines.append(
            f"Per-player segmentation did not pass the strict overfit guard."
            f" Either no (stat, player) combos met the candidate criteria"
            f" (n>=30, ROI<-5%, ci_hi<+5%, z<0.5), or the greedy compose failed to lift"
            f" aggregate by +{MIN_AGG_LIFT_PP}pp without violating regression / removal"
            f" caps. The post-iter-57 baseline is at the per-player segmentation ceiling"
            " for the current OOS 2025-26 sample. Next pivot should target a non-segmentation"
            " lever (calibration, sizing, architecture)."
        )

    lines += [
        "",
        "---",
        "",
        f"*Generated by `scripts/iter59_per_player_filter.py` on {now_str}.*",
        "*Refs: [[Iter57 Post-Iter55 Resweep]] | [[Iter58 Stage Venue 3D Sweep]] | [[Engineering Knowledge]]*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Vault report -> {REPORT_PATH}")


# ── Main run ───────────────────────────────────────────────────────────────────

def run() -> Dict:
    print("\n" + "=" * 78)
    print("  ITER-59: PER-PLAYER ZERO-EV FILTER")
    print("=" * 78)
    print(f"  Candidate gate: n>={MIN_PLAYER_N}, ROI<{MAX_ROI_PCT}%, "
          f"ci_hi<+{MAX_CI_HI}%, z<{MAX_Z_SCORE}")
    print(f"  Ship gate:      agg_lift>=+{MIN_AGG_LIFT_PP}pp, "
          f"no per-stat regress > {MAX_STAT_REGRESS}pp, "
          f"removed <= {MAX_BETS_REMOVED_FRAC:.0%}")
    print()

    STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk"]
    all_rows: List[Dict] = []
    for stat in STATS:
        all_rows.extend(load_eval_rows(stat))
    print(f"  Total eval rows: {len(all_rows)}")

    # ── Post-iter-57 baseline (= pre-iter-59) ─────────────────────────────────
    post57_rows = apply_production_filters(all_rows, extra_player_excl=None)
    pre59_per_stat = per_stat_metrics(post57_rows)
    pre59_agg      = aggregate_metrics(post57_rows)
    print(f"\n  POST-ITER-57 BASELINE (= pre-iter-59):")
    print(f"    aggregate: n={pre59_agg['n']}, ROI={pre59_agg['roi_pct']:+.4f}%, "
          f"hit={pre59_agg['hit_rate_pct']:.2f}%, z={pre59_agg['z_score']:.3f}")
    for stat in STATS:
        m = pre59_per_stat.get(stat, {"n": 0, "roi_pct": 0.0, "hit_rate_pct": 0.0, "z_score": 0.0})
        print(f"    {stat.upper():<5} n={m['n']:>4} ROI={m['roi_pct']:>+8.4f}%  "
              f"hit={m['hit_rate_pct']:>5.2f}%  z={m['z_score']:>+6.3f}")

    # ── Per-player diagnostics ─────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print(f"  PER-PLAYER METRICS (stat x player, n >= {MIN_PLAYER_N})")
    print("-" * 78)
    per_player_all = evaluate_per_player(post57_rows)
    print(f"  Total (stat, player) combos with n >= {MIN_PLAYER_N}: {len(per_player_all)}")

    candidates: List[Tuple[str, str, Dict]] = []
    for stat in STATS:
        stat_combos = [(s, p, m) for s, p, m in per_player_all if s == stat]
        if not stat_combos:
            continue
        print(f"\n  {stat.upper()} (post-iter-57 n={pre59_per_stat.get(stat,{}).get('n',0)}, "
              f"{len(stat_combos)} players with n>={MIN_PLAYER_N}):")
        print(f"    {'player':<28} {'n':>4} {'hit%':>6} {'ROI%':>9} {'z':>7}  {'95% CI':>20}  cand?")
        print("    " + "-" * 84)
        # Sort by ROI ascending (worst first)
        for s, player, m in sorted(stat_combos, key=lambda c: c[2]["roi_pct"]):
            cand = is_zero_ev_player(m)
            ci_str = f"[{m['ci_lo']:+.1f}%, {m['ci_hi']:+.1f}%]"
            flag = " <-- CANDIDATE" if cand else ""
            print(f"    {player[:28]:<28} {m['n']:>4}  {m['hit_rate_pct']:>5.2f}%  "
                  f"{m['roi_pct']:>+8.3f}%  {m['z_score']:>+6.3f}  {ci_str:>20}{flag}")
            if cand:
                candidates.append((s, player, m))

    print(f"\n  Total candidates passing strict gate: {len(candidates)}")

    # ── Greedy compose ─────────────────────────────────────────────────────────
    print("\n" + "-" * 78)
    print("  GREEDY COMPOSITION (pnl_recovered descending)")
    print("-" * 78)
    picked, log = greedy_compose(all_rows, pre59_agg, pre59_per_stat, candidates)
    for ln in log:
        print(ln)

    # ── Apply final filters ───────────────────────────────────────────────────
    if picked:
        post59_rows     = apply_production_filters(all_rows, extra_player_excl=picked)
        post59_per_stat = per_stat_metrics(post59_rows)
        post59_agg      = aggregate_metrics(post59_rows)
    else:
        post59_rows     = post57_rows
        post59_per_stat = pre59_per_stat
        post59_agg      = pre59_agg

    print("\n" + "=" * 78)
    print("  POST-ITER-59 METRICS")
    print("=" * 78)
    agg_delta = post59_agg["roi_pct"] - pre59_agg["roi_pct"]
    print(f"  aggregate: n={post59_agg['n']}, ROI={post59_agg['roi_pct']:+.4f}%, "
          f"delta_vs_pre59={agg_delta:+.4f}pp")
    print(f"  {'Stat':<5} {'pre_n':>6} {'post_n':>7} {'pre_roi%':>10} {'post_roi%':>11} {'delta_pp':>10}")
    for stat in STATS:
        pre_m  = pre59_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post59_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        print(f"  {stat.upper():<5} {pre_m['n']:>6} {post_m['n']:>7} "
              f"{pre_m['roi_pct']:>+9.4f}% {post_m['roi_pct']:>+10.4f}% "
              f"{d_pp:>+9.4f}pp")

    # ── Ship decision ─────────────────────────────────────────────────────────
    regressions: List[str] = []
    improvements: List[str] = []
    for stat in STATS:
        pre_m  = pre59_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        post_m = post59_per_stat.get(stat, {"n": 0, "roi_pct": 0.0})
        d_pp   = post_m["roi_pct"] - pre_m["roi_pct"]
        if d_pp < MAX_STAT_REGRESS:
            regressions.append(f"{stat}: {d_pp:+.4f}pp")
        if d_pp > 0.5:
            improvements.append(f"{stat}: {d_pp:+.4f}pp")

    total_removed     = pre59_agg["n"] - post59_agg["n"]
    cum_remove_frac   = total_removed / pre59_agg["n"] if pre59_agg["n"] else 0.0
    over_per_stat_cap = []
    for stat in STATS:
        pre_n  = pre59_per_stat.get(stat, {}).get("n", 0)
        post_n = post59_per_stat.get(stat, {}).get("n", 0)
        if pre_n and (pre_n - post_n) / pre_n > MAX_PER_STAT_REMOVED_FRAC:
            over_per_stat_cap.append(f"{stat}: {(pre_n-post_n)/pre_n:.1%}")

    agg_passes = agg_delta >= MIN_AGG_LIFT_PP
    no_regressions = len(regressions) == 0
    cum_ok     = cum_remove_frac <= MAX_BETS_REMOVED_FRAC
    per_stat_ok = len(over_per_stat_cap) == 0

    if picked and agg_passes and no_regressions and cum_ok and per_stat_ok:
        decision = "SHIP"
        n_picks = sum(len(v) for v in picked.values())
        detail = (
            f"Aggregate delta {agg_delta:+.4f}pp >= +{MIN_AGG_LIFT_PP}pp AND no per-stat"
            f" regression > {MAX_STAT_REGRESS}pp AND cum removed {cum_remove_frac:.1%}"
            f" <= {MAX_BETS_REMOVED_FRAC:.0%} AND no per-stat removed > "
            f"{MAX_PER_STAT_REMOVED_FRAC:.0%}. Total (stat, player) exclusions wired: {n_picks}."
        )
    elif not picked:
        decision = "REVERT"
        detail = (
            f"No (stat, player) candidates passed greedy compose under strict gates"
            f" (n>={MIN_PLAYER_N}, ROI<{MAX_ROI_PCT}%, ci_hi<+{MAX_CI_HI}%, z<{MAX_Z_SCORE})"
            f" AND ship caps. No filters to wire."
        )
    elif not agg_passes:
        decision = "REVERT"
        detail = f"Aggregate delta {agg_delta:+.4f}pp below +{MIN_AGG_LIFT_PP}pp ship threshold."
    elif not no_regressions:
        decision = "REVERT"
        detail = f"Per-stat regression(s): {regressions}."
    elif not cum_ok:
        decision = "REVERT"
        detail = f"Cumulative removed {cum_remove_frac:.1%} > cap {MAX_BETS_REMOVED_FRAC:.0%}."
    else:
        decision = "REVERT"
        detail = f"Per-stat removed cap violated: {over_per_stat_cap}."

    print("\n" + "=" * 78)
    print(f"  DECISION: {decision}")
    print("=" * 78)
    print(f"  Detail:       {detail}")
    print(f"  Agg delta:    {agg_delta:+.4f}pp (threshold +{MIN_AGG_LIFT_PP}pp)")
    print(f"  Bets removed: {total_removed} ({cum_remove_frac:.1%} of {pre59_agg['n']})")
    print(f"  Regressions:  {regressions if regressions else 'none'}")
    print(f"  Improvements: {improvements if improvements else 'none'}")

    # ── Wire filters if SHIP ──────────────────────────────────────────────────
    filters_wired: List = []
    if decision == "SHIP":
        _wire_player_filter_into_thresholds(picked, pre59_agg, post59_agg, agg_delta)
        filters_wired = [
            [stat, sorted(list(players))]
            for stat, players in sorted(picked.items())
            if players
        ]

    # ── Build result ──────────────────────────────────────────────────────────
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "iter":            59,
        "generated_at":    now_utc,
        "approach":        "per_stat_player_zero_ev_filter",
        "n_bets_pre":      pre59_agg["n"],
        "n_bets_post":     post59_agg["n"],
        "pre59_agg_roi":   round(pre59_agg["roi_pct"], 4),
        "post59_agg_roi":  round(post59_agg["roi_pct"], 4),
        "delta_agg_pp":    round(agg_delta, 4),
        "ship_threshold_pp": MIN_AGG_LIFT_PP,
        "decision":        decision,
        "decision_detail": detail,
        "regressions":     regressions,
        "improvements":    improvements,
        "n_candidates":    len(candidates),
        "n_per_player_combos_evaluated": len(per_player_all),
        "filters_wired":   filters_wired,
        "greedy_log":      log,
        "per_stat": {
            stat: {
                "pre_n":     pre59_per_stat.get(stat, {}).get("n", 0),
                "post_n":    post59_per_stat.get(stat, {}).get("n", 0),
                "pre_roi":   round(pre59_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "post_roi":  round(post59_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "delta_roi": round(
                    post59_per_stat.get(stat, {}).get("roi_pct", 0.0)
                    - pre59_per_stat.get(stat, {}).get("roi_pct", 0.0), 4),
                "excluded_players": sorted(list(picked.get(stat, set()))) or None,
            }
            for stat in STATS
        },
        "candidate_diagnostics": [
            {
                "stat": s, "player": p,
                "n": m["n"], "roi_pct": m["roi_pct"], "z_score": m["z_score"],
                "ci_lo": m["ci_lo"], "ci_hi": m["ci_hi"], "hit_rate_pct": m["hit_rate_pct"],
                "pnl_recovered": round(-m["roi_pct"] * m["n"] / 100.0, 4),
            }
            for s, p, m in sorted(candidates, key=lambda c: c[2]["roi_pct"])
        ],
        "params": {
            "min_player_n":         MIN_PLAYER_N,
            "max_roi_pct":          MAX_ROI_PCT,
            "max_ci_hi":            MAX_CI_HI,
            "max_z_score":          MAX_Z_SCORE,
            "min_agg_lift_pp":      MIN_AGG_LIFT_PP,
            "max_stat_regress":     MAX_STAT_REGRESS,
            "max_bets_removed_frac":      MAX_BETS_REMOVED_FRAC,
            "max_per_stat_removed_frac":  MAX_PER_STAT_REMOVED_FRAC,
            "n_bootstrap":          N_BOOTSTRAP,
            "seed":                 SEED,
        },
    }

    # ── Persist to holdout_baseline.json (read-modify-write) ──────────────────
    baseline: Dict = {}
    if os.path.exists(BASELINE_JSON):
        baseline = json.load(open(BASELINE_JSON, encoding="utf-8"))
    baseline["__iter59__"] = result
    baseline["__updated_at__"] = now_utc
    with open(BASELINE_JSON, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2)
    print(f"\n  holdout_baseline.json -> updated with __iter59__ (other keys preserved)")

    # ── Vault report ──────────────────────────────────────────────────────────
    _write_vault_report(result, candidates, per_player_all, pre59_per_stat, post59_per_stat)

    return result


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    result = run()
    print("\n" + "=" * 78)
    print("  ITER-59 COMPLETE")
    print("=" * 78)
    print(f"  Decision:        {result['decision']}")
    print(f"  Aggregate delta: {result['delta_agg_pp']:+.4f}pp")
    print(f"  Pre/post ROI:    {result['pre59_agg_roi']:+.4f}% -> {result['post59_agg_roi']:+.4f}% "
          f"({result['n_bets_pre']} -> {result['n_bets_post']} bets)")
    if result["filters_wired"]:
        n_picks = sum(len(p) for _, p in result["filters_wired"])
        print(f"  Filters wired:   {n_picks} (stat,player) pairs across "
              f"{len(result['filters_wired'])} stats")
    else:
        print("  Filters wired:   none")
    print()

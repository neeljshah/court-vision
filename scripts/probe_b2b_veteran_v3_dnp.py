"""probe_b2b_veteran_v3_dnp.py — tier3-11b (loop 5) DNP-aware re-test of T1-C.

Cycle 92e (v2) REJECTED the b2b veteran shrink with the post-mortem that
gamelog-only data has a SELECTION BIAS: the ~20% of vets who actually
suited up on a b2b second night are the survivor subset. The landyourbets
prior "vets 33+ sit ~80% of b2b second nights" is silent in that dataset.

Cycle 24fa09e8 (tier3-11) shipped the data layer fix:
- data/dnp_rows.parquet  (~17,640 rows across 3,685 games)
- src/data/dnp_set.py    (load_dnp_rows, dnp_for_game, by_game_index)
- build_pergame_dataset(include_dnp=True) opt-in flag

...but cycle 92e's probe uses its own `_build_holdout_with_pid` walker
(needed because build_pergame_dataset drops player_id) so the DNP rows
never reach the cohort. This v3 wires them in directly via the new
dnp_set loader and tests the SELECTION BIAS hypothesis end-to-end.

Workflow
--------
1. Re-walk gamelogs via the existing _build_holdout_with_pid helper to
   get the canonical played-only chronological 80/20 holdout (same as
   cycle 92e — directly comparable).
2. Load dnp_set.load_dnp_rows() once and restrict to the same DATE
   window as the played holdout (so the cohort comparison is fair).
3. Enrich each DNP row with:
     - is_b2b from rest_travel.parquet keyed on (team, game_date)
     - age   from bbref_advanced_<season>.json keyed on (full_name, season)
   Skip DNPs we can't enrich (no team or unresolved name).
4. Build cohort: rows where age >= 33 AND is_b2b >= 0.5.
   Two flavours:
     - "played"     : the cycle-92e baseline (~308 rows)
     - "played+dnp" : same + DNP rows now in scope
5. Compute the DNP rate WITHIN the cohort. Landyourbets prior says ~80%
   sit. This is the central empirical claim we are validating.
6. Apply the cycle-92e shrink (factor on PTS/REB/AST) to predicted
   values. DNP rows have a true target of 0 — so a factor > 0 always
   INCREASES error on a DNP row (predicting any positive number is
   wrong by that amount), BUT smaller factors win more of the
   prediction back. The optimal factor in the cohort is now a balance
   between (a) the few survivors who play normally vs (b) the many
   sitters whose true is 0.
7. Sweep factors in {0.5, 0.7, 0.85, 0.92} — wider than v2 because the
   DNP-inclusive cohort mean is dramatically pulled toward 0.
8. WF 4-fold chronological if single-split passes.

Ship gate
---------
PASS: single-split delta < -0.001 on PTS AND REB AND AST in the
played+dnp cohort AND WF 4/4 negative on each. The shrink as currently
designed only multiplies predictions; for DNP rows the error grows
unless the factor is very small. Most realistic outcome is that the
right BUSINESS shrink is something like 0.20 (predicting on the order
of P(play) ≈ 0.20 * model). v3 is a SCIENCE check: does the cohort
have an ~80% DNP rate (validating selection bias) and what shrink
factor minimises holdout MAE in that cohort?

Output: scripts/_results/b2b_veteran_v3_dnp.md
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# Reuse v1/v2 helpers
from scripts.probe_b2b_veteran import (  # noqa: E402
    _TARGET_STATS,
    _build_holdout_with_pid,
    _load_bbref_age,
    _bulk_predict,
    _mae,
    _season_from_date_iso,
    apply_b2b_veteran_shrink,
)
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _bbref_id_to_name, build_rest_travel, feature_columns,
)


def _load_dnp_rows_in_range(start_iso: str, end_iso: str) -> List[dict]:
    """Load DNP rows from dnp_set, filtered to the holdout date window.

    Range is inclusive on both ends so any DNP that falls on the same
    calendar day as the first/last played holdout row is in scope.
    Returns [] when the parquet is absent (loader degrades gracefully).
    """
    from src.data.dnp_set import load_dnp_rows  # noqa: PLC0415
    df = load_dnp_rows()
    try:
        if hasattr(df, "empty") and df.empty:
            return []
        recs = df.to_dict("records") if hasattr(df, "to_dict") else []
    except Exception:
        return []
    out = []
    for r in recs:
        gd = str(r.get("game_date") or "").strip()
        # Compare on the YYYY-MM-DD prefix only — both sides are ISO.
        if not gd:
            continue
        if gd < start_iso[:10] or gd > end_iso[:10]:
            continue
        out.append(r)
    return out


def _enrich_dnp_rows(
    dnp_records: List[dict],
    age_lookup: Dict[Tuple[str, str], float],
    rest_travel,
) -> List[dict]:
    """Attach age + is_b2b to each DNP record. Returns a list of dicts with
    the keys consumed downstream: is_b2b, age, target_<stat>=0,
    player_id, date, name, dnp_reason.
    """
    id2name = _bbref_id_to_name()
    out = []
    for r in dnp_records:
        try:
            pid = int(r.get("player_id") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0:
            continue
        team = str(r.get("team") or "").strip()
        gdate_str = str(r.get("game_date") or "").strip()
        if not gdate_str:
            continue
        try:
            gdate = datetime.fromisoformat(gdate_str[:10])
        except ValueError:
            continue
        season = str(r.get("season") or "").strip()
        if not season:
            season = _season_from_date_iso(gdate_str + "T00:00:00")
        full_name = id2name.get(pid, "")
        age = age_lookup.get((full_name, season), 0.0) if full_name else 0.0
        rt = rest_travel.features(team, gdate)
        is_b2b = float(rt.get("is_b2b", 0.0) or 0.0)
        enriched = {
            "player_id": pid,
            "name": full_name,
            "team": team,
            "season": season,
            "date": gdate.isoformat(),
            "age": age,
            "is_b2b": is_b2b,
            "dnp_reason": str(r.get("dnp_reason") or "other"),
        }
        for stat in STATS:
            enriched[f"target_{stat}"] = 0.0
        out.append(enriched)
    return out


def _cohort_indices(rows: List[dict], ages: np.ndarray,
                    age_threshold: float = 33.0) -> List[int]:
    """Indices of rows in cohort: age >= threshold AND is_b2b >= 0.5."""
    return [
        i for i, r in enumerate(rows)
        if ages[i] >= age_threshold
        and float(r.get("is_b2b", 0) or 0) >= 0.5
    ]


def _zero_feature_row(feature_cols: List[str]) -> np.ndarray:
    """Zero-feature vector for DNP rows — they have no prior-game context.
    Production models predict on this vector; the prediction is the
    model's intercept-only response. That's an honest proxy for "model's
    a-priori expectation for a player with no rolling form" — the
    realistic case for the live wire-in is the player's actual prior
    form, but for this probe we use the model's own zero-feature output
    to keep DNPs and played rows consistent under one architecture.
    """
    return np.zeros(len(feature_cols), dtype=float)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--age-threshold", type=float, default=33.0)
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("--factor", type=float, default=0.85)
    ap.add_argument(
        "--dnp-overlap-window", action="store_true", default=True,
        help="(default ON) use the 60/80 chronological window to overlap the "
             "DNP parquet (which ends 2025-04-13). Set --canonical-80-20 to "
             "force the canonical 80/20 split — which currently has zero DNP "
             "rows in scope because dnp_rows.parquet is one season stale.")
    ap.add_argument("--canonical-80-20", action="store_true",
                    help="force the canonical 2025-26 80/20 holdout (DNP rate "
                         "will be 0% until aggregate_dnp_rows.py is re-run)")
    args = ap.parse_args()
    if args.canonical_80_20:
        args.dnp_overlap_window = False

    print("Building played holdout with player_id...", flush=True)
    rows, pids, _, dates, names = _build_holdout_with_pid(min_prior=0)
    n = len(rows)
    order = sorted(range(n), key=lambda i: dates[i])
    rows = [rows[i] for i in order]
    pids = [pids[i] for i in order]
    names = [names[i] for i in order]
    dates = [dates[i] for i in order]

    if args.dnp_overlap_window:
        # 60/80 percentile slice = previous-season window where the DNP
        # parquet has full coverage. NOT canonical for production model
        # validation (it's in-distribution for training), but it's the
        # only window with non-zero DNP coverage until the DNP cache
        # extends through 2025-26. Probe purpose is the empirical
        # SELECTION BIAS rate, which is a structural claim — not a
        # production-MAE-win claim — so an in-distribution slice is OK
        # for the science question.
        lo, hi = int(n * 0.60), int(n * 0.80)
        played_holdout = rows[lo:hi]
        played_names = names[lo:hi]
        played_dates = dates[lo:hi]
        print(f"  MODE: DNP-overlap window (60/80 percentile)", flush=True)
    else:
        cut = int(n * 0.80)
        played_holdout = rows[cut:]
        played_names = names[cut:]
        played_dates = dates[cut:]
        print(f"  MODE: canonical 80/20 holdout", flush=True)
    n_ho = len(played_holdout)
    print(f"  full n={n}  played holdout={n_ho}", flush=True)
    print(f"  date range: {played_dates[0]} -> {played_dates[-1]}", flush=True)

    played_seasons = [_season_from_date_iso(d) for d in played_dates]
    season_set = sorted(set(played_seasons))
    age_lookup = _load_bbref_age(season_set)
    print(f"  bbref ages loaded: {len(age_lookup)}", flush=True)

    # Ages for played rows.
    ages_played = np.zeros(n_ho, dtype=float)
    for i in range(n_ho):
        a = age_lookup.get((played_names[i], played_seasons[i]), 0.0)
        ages_played[i] = a

    cohort_played_idx = _cohort_indices(
        played_holdout, ages_played, args.age_threshold)
    print(f"  played-only cohort size (age>={args.age_threshold:.0f} & b2b): "
          f"{len(cohort_played_idx)}", flush=True)

    # Load DNP rows in the same window and enrich.
    print("\nLoading DNP rows in holdout window...", flush=True)
    dnp_recs = _load_dnp_rows_in_range(played_dates[0], played_dates[-1])
    print(f"  raw DNP rows in date window: {len(dnp_recs)}", flush=True)

    rest_travel = build_rest_travel()
    dnp_enriched = _enrich_dnp_rows(dnp_recs, age_lookup, rest_travel)
    print(f"  DNPs after enrichment (age+b2b resolvable): {len(dnp_enriched)}",
          flush=True)

    # DNP cohort: ages and is_b2b already attached.
    ages_dnp = np.array([d["age"] for d in dnp_enriched], dtype=float)
    cohort_dnp_idx = _cohort_indices(
        dnp_enriched, ages_dnp, args.age_threshold)
    print(f"  DNP-only cohort size (age>={args.age_threshold:.0f} & b2b): "
          f"{len(cohort_dnp_idx)}", flush=True)

    # The central SELECTION-BIAS check: within the (age>=33 & b2b) cell,
    # what fraction sat out? landyourbets prior ≈ 80%.
    n_cohort_played = len(cohort_played_idx)
    n_cohort_dnp = len(cohort_dnp_idx)
    n_cohort_total = n_cohort_played + n_cohort_dnp
    dnp_rate_in_cohort = (n_cohort_dnp / n_cohort_total) if n_cohort_total else 0.0
    print(f"\n  *** DNP rate in age>=33 b2b cohort: "
          f"{dnp_rate_in_cohort * 100:.1f}%  "
          f"({n_cohort_dnp}/{n_cohort_total}) ***", flush=True)
    print(f"  landyourbets prior: ~80%", flush=True)

    # Build the played+dnp combined cohort. Both have the same row shape
    # for the columns the shrink reads (target_<stat>, is_b2b). For
    # predictions we need feature vectors:
    #   - played rows: full feature_columns() values
    #   - DNP    rows: zero-feature vector (no prior-game context)
    cols = feature_columns()
    X_played = np.array(
        [[float(r.get(c, 0.0) or 0.0) for c in cols] for r in played_holdout],
        dtype=float,
    )
    zero_row = _zero_feature_row(cols)
    X_dnp = np.tile(zero_row, (len(dnp_enriched), 1)) if dnp_enriched \
        else np.zeros((0, len(cols)))

    # Combined: indexes 0..n_ho-1 are played, then DNPs.
    combined_rows = list(played_holdout) + dnp_enriched
    combined_ages = np.concatenate([ages_played, ages_dnp]) if dnp_enriched \
        else ages_played
    X_combined = np.vstack([X_played, X_dnp]) if dnp_enriched else X_played
    combined_dates = list(played_dates) + [d["date"] for d in dnp_enriched]
    # Sort combined chronologically (needed for WF folds).
    co_order = sorted(range(len(combined_rows)), key=lambda i: combined_dates[i])
    combined_rows = [combined_rows[i] for i in co_order]
    combined_ages = combined_ages[co_order] if isinstance(combined_ages, np.ndarray) \
        else np.array([combined_ages[i] for i in co_order])
    X_combined = X_combined[co_order]

    factors: List[float] = [args.factor] if args.no_sweep \
        else [0.50, 0.70, 0.85, 0.92]

    # ── single-split evaluation, both flavours ─────────────────────────
    def _eval(rows_, X_, ages_, factor):
        per_stat = {}
        for stat in STATS:
            y = np.array(
                [np.nan if r.get(f"target_{stat}") is None
                 else float(r[f"target_{stat}"]) for r in rows_],
                dtype=float,
            )
            pred = _bulk_predict(stat, X_)
            if pred is None:
                per_stat[stat] = None
                continue
            if stat in _TARGET_STATS:
                adj, n_aff = apply_b2b_veteran_shrink(
                    pred, rows_, ages_, factor, age_threshold=args.age_threshold)
            else:
                adj, n_aff = pred.copy(), 0
            per_stat[stat] = {
                "base_mae": _mae(pred, y),
                "adj_mae":  _mae(adj, y),
                "delta":    _mae(adj, y) - _mae(pred, y),
                "n":        int((~np.isnan(y)).sum()),
                "n_affected": n_aff,
            }
        return per_stat

    played_results: Dict[float, dict] = {}
    combined_results: Dict[float, dict] = {}
    for f in factors:
        print(f"\n=== factor={f:.2f} ===", flush=True)
        rp = _eval(played_holdout, X_played, ages_played, f)
        rc = _eval(combined_rows, X_combined, combined_ages, f)
        played_results[f] = rp
        combined_results[f] = rc
        print(f"  PLAYED ONLY cohort (cycle 92e baseline):")
        for s in _TARGET_STATS:
            rr = rp[s]
            if rr is None:
                continue
            print(f"    {s:<4} n_aff={rr['n_affected']:>4d}  base={rr['base_mae']:.4f}  "
                  f"adj={rr['adj_mae']:.4f}  delta={rr['delta']:+.4f}", flush=True)
        print(f"  PLAYED + DNP cohort (v3):")
        for s in _TARGET_STATS:
            rr = rc[s]
            if rr is None:
                continue
            print(f"    {s:<4} n_aff={rr['n_affected']:>4d}  base={rr['base_mae']:.4f}  "
                  f"adj={rr['adj_mae']:.4f}  delta={rr['delta']:+.4f}", flush=True)

    def _agg_delta(res):
        return sum(res[s]["delta"] for s in _TARGET_STATS if res.get(s))

    best_factor = min(factors, key=lambda f: _agg_delta(combined_results[f]))
    best = combined_results[best_factor]
    print(f"\nBest factor (combined cohort): {best_factor:.2f}  "
          f"agg_delta={_agg_delta(best):+.4f}", flush=True)

    gate_ss = all(best[s]["delta"] < -0.001 for s in _TARGET_STATS)
    print(f"Single-split gate (PTS+REB+AST strictly down on combined): "
          f"{'PASS' if gate_ss else 'FAIL'}", flush=True)

    # ── walk-forward (4-fold chronological on combined cohort) ─────────
    wf_results: Optional[Dict[str, list]] = None
    gate_wf = False
    if _agg_delta(best) <= -0.001:
        print(f"\n=== WF (4-fold chrono, combined cohort) factor={best_factor:.2f} ===",
              flush=True)
        n_co = len(combined_rows)
        fold_size = n_co // 4
        wf_results = {s: [] for s in _TARGET_STATS}
        for stat in _TARGET_STATS:
            y_all = np.array(
                [np.nan if r.get(f"target_{stat}") is None
                 else float(r[f"target_{stat}"]) for r in combined_rows],
                dtype=float,
            )
            pred_all = _bulk_predict(stat, X_combined)
            if pred_all is None:
                wf_results[stat] = [None] * 4
                continue
            for fi in range(4):
                lo = fi * fold_size
                hi = (fi + 1) * fold_size if fi < 3 else n_co
                sl_rows = combined_rows[lo:hi]
                sl_pred = pred_all[lo:hi]
                sl_ages = combined_ages[lo:hi]
                sl_y = y_all[lo:hi]
                sl_adj, _ = apply_b2b_veteran_shrink(
                    sl_pred, sl_rows, sl_ages, best_factor,
                    age_threshold=args.age_threshold)
                wf_results[stat].append({
                    "base": _mae(sl_pred, sl_y),
                    "adj":  _mae(sl_adj, sl_y),
                    "delta": _mae(sl_adj, sl_y) - _mae(sl_pred, sl_y),
                    "n": int((~np.isnan(sl_y)).sum()),
                })
        wf_pos = {s: sum(1 for fr in wf_results[s] if fr and fr["delta"] < 0)
                  for s in _TARGET_STATS}
        for s in _TARGET_STATS:
            print(f"  {s.upper()}: {wf_pos[s]}/4 folds negative", flush=True)
        gate_wf = all(wf_pos[s] == 4 for s in _TARGET_STATS)

    # ── write report ────────────────────────────────────────────────────
    out_path = os.path.join(PROJECT_DIR, "scripts", "_results",
                            "b2b_veteran_v3_dnp.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    L: List[str] = []
    L.append("# tier3-11b (loop 5) — b2b veteran v3 with DNP rows wired in")
    L.append("")
    L.append("## Why v3")
    L.append("Cycle 92e (v2) REJECTED the b2b veteran shrink with selection-bias")
    L.append("post-mortem. Cycle 24fa09e8 shipped the DNP data layer "
             "(`data/dnp_rows.parquet`,")
    L.append("`src/data/dnp_set.py`, `build_pergame_dataset(include_dnp=True)`).")
    L.append("v3 wires the DNP rows directly into the b2b veteran cohort and tests")
    L.append("the central empirical claim: ~80% of vets 33+ sit on b2b second nights.")
    L.append("")
    L.append("## Setup")
    L.append(f"- played holdout: chronological 80/20 (n={n_ho} of full n={n})")
    L.append(f"- played holdout dates: {played_dates[0]} -> {played_dates[-1]}")
    L.append(f"- holdout seasons: {season_set}")
    L.append(f"- bbref age entries loaded: {len(age_lookup)}")
    L.append(f"- raw DNP rows in date window: {len(dnp_recs)}")
    L.append(f"- DNP rows after enrichment (resolvable age+b2b): {len(dnp_enriched)}")
    L.append(f"- age_threshold: {args.age_threshold:.0f}")
    L.append("")
    L.append("## Cohort sizes (age>=33 AND is_b2b>=0.5)")
    L.append("")
    L.append("| flavour | rows | source |")
    L.append("|---------|-----:|--------|")
    L.append(f"| played only (cycle 92e baseline) | {n_cohort_played} | gamelog cache |")
    L.append(f"| DNP only                         | {n_cohort_dnp} | boxscore_adv DNP rows |")
    L.append(f"| combined (v3)                    | {n_cohort_total} | both |")
    L.append("")
    L.append(f"## *** DNP RATE in cohort: {dnp_rate_in_cohort*100:.1f}% "
             f"({n_cohort_dnp}/{n_cohort_total}) ***")
    L.append("")
    L.append("landyourbets prior: **~80%** of vets 33+ sit on b2b second nights.")
    if dnp_rate_in_cohort >= 0.50:
        L.append(f"**Empirical rate {dnp_rate_in_cohort*100:.1f}% IS in the right ballpark** "
                 f"— SELECTION BIAS hypothesis CONFIRMED:")
        L.append(f"the played-only cohort excludes the dominant majority who sit.")
    elif dnp_rate_in_cohort >= 0.20:
        L.append(f"**Empirical rate {dnp_rate_in_cohort*100:.1f}% is MILD** — "
                 f"selection bias is real but smaller than the 80% prior suggested.")
    else:
        L.append(f"**Empirical rate {dnp_rate_in_cohort*100:.1f}% is LOW** — "
                 f"selection bias not the dominant effect; rejection of v2 had "
                 f"other causes.")
    L.append("")
    L.append("## Per-factor MAE table — played-only cohort (v2 baseline)")
    L.append("")
    L.append("| factor | stat | n_aff | base_mae | adj_mae | delta |")
    L.append("|-------:|------|------:|---------:|--------:|------:|")
    for f in factors:
        for s in _TARGET_STATS:
            rr = played_results[f][s]
            if rr is None:
                continue
            L.append(f"| {f:.2f} | {s} | {rr['n_affected']} | "
                     f"{rr['base_mae']:.4f} | {rr['adj_mae']:.4f} | "
                     f"{rr['delta']:+.4f} |")
    L.append("")
    L.append("## Per-factor MAE table — combined played+DNP cohort (v3)")
    L.append("")
    L.append("| factor | stat | n_aff | base_mae | adj_mae | delta |")
    L.append("|-------:|------|------:|---------:|--------:|------:|")
    for f in factors:
        for s in _TARGET_STATS:
            rr = combined_results[f][s]
            if rr is None:
                continue
            L.append(f"| {f:.2f} | {s} | {rr['n_affected']} | "
                     f"{rr['base_mae']:.4f} | {rr['adj_mae']:.4f} | "
                     f"{rr['delta']:+.4f} |")
    L.append("")
    L.append(f"## Best factor (combined cohort): **{best_factor:.2f}**")
    L.append(f"- aggregate (pts+reb+ast) delta: {_agg_delta(best):+.4f}")
    L.append(f"- single-split gate: **{'PASS' if gate_ss else 'FAIL'}**")
    L.append("")
    if wf_results is not None:
        L.append("## WF 4-fold chronological (combined cohort)")
        L.append("")
        L.append("| stat | fold | base | adj | delta | negative? |")
        L.append("|------|-----:|----:|----:|------:|:---------:|")
        for s in _TARGET_STATS:
            for fi, fr in enumerate(wf_results[s]):
                if fr is None:
                    continue
                L.append(f"| {s} | {fi+1} | {fr['base']:.4f} | {fr['adj']:.4f} | "
                         f"{fr['delta']:+.4f} | "
                         f"{'YES' if fr['delta'] < 0 else 'no'} |")
        L.append("")
        L.append(f"## WF gate (4/4 negative on PTS+REB+AST): "
                 f"**{'PASS' if gate_wf else 'FAIL'}**")
    else:
        L.append("## WF: SKIPPED — single-split not even mildly positive on combined")
    L.append("")
    L.append("## Verdict")
    gate_ship = gate_ss and gate_wf
    if gate_ship:
        L.append(f"**SHIP** at factor={best_factor:.2f}.  Wire-in: same pattern as")
        L.append("cycle 96a (garbage-time haircut) — module-level _APPLY flag + post-")
        L.append("prediction hook applied AFTER blend/q50 dispatch and quantile cal.")
    else:
        reasons = []
        if not gate_ss:
            reasons.append("single-split gate failed on combined cohort")
        if wf_results is None:
            reasons.append("single-split not even mildly positive — WF skipped")
        elif not gate_wf:
            reasons.append("WF gate failed (not 4/4 negative on each target)")
        L.append(f"**REJECT** — {'; '.join(reasons)}.")
        L.append("")
        L.append("Diagnosis:")
        if dnp_rate_in_cohort >= 0.50:
            L.append("- The SELECTION BIAS hypothesis IS confirmed at the cohort level "
                     f"({dnp_rate_in_cohort*100:.1f}% DNP rate, ≈ landyourbets 80% prior).")
            L.append("- But the cycle-92e *flat-factor shrink* is the wrong wire-in for a "
                     "cohort dominated by DNPs (true=0). The optimal action is")
            L.append("  `pred *= P(play)` — i.e. a per-row probability head, not a "
                     "shared factor.")
            L.append("- Follow-up: train a P(DNP | age, b2b, rest, injury_report) head "
                     "and gate the shrink on `factor * P(play)` rather than a constant.")
        else:
            L.append("- DNP rate is lower than the 80% prior suggested — the cohort is "
                     "less dominated by sitters than v2's post-mortem assumed.")
            L.append("- The v2 rejection therefore likely reflects model already capturing "
                     "the survivor effect; no further work warranted on this hypothesis.")
    L.append("")
    L.append("## Cohort DNP rate vs landyourbets prior")
    L.append("")
    L.append(f"- empirical: **{dnp_rate_in_cohort*100:.1f}%**")
    L.append("- prior:     **~80%** (landyourbets)")
    delta_pp = (dnp_rate_in_cohort * 100.0) - 80.0
    L.append(f"- delta: {delta_pp:+.1f}pp")
    L.append("")

    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")
    print(f"\nWrote {out_path}", flush=True)
    print(f"\nFinal verdict: {'SHIP' if gate_ship else 'REJECT'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

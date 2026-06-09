"""H4: pregame game TOTAL and |SPREAD| market-context test.

Hypothesis:
  (a) Point-feature: high total => more possessions => pts/reb/ast up;
      large abs_spread => blowout risk => star minutes cut.
      Expected: REJECT (production already applies garbage-time haircut).
  (b) Selection filter: dropping abs_spread > 14 (blowout games) improves ROI.
      Also: total tercile analysis.

DECISIVE SCREEN:
  - fit beta (on early half) -> grade late half (true held-out)
  - cross-season 2024-25 has NO pregame_spreads -> noted

DISCIPLINE:
  - all grading via intel_grade.roi / settle / coherence
  - drop |odds|<100 is handled by ig.prepare()
  - coherence guard checked
  - n reported on every number

Read-only except writing nothing (analysis only).
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

# -- path setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, SCRIPT_DIR)

import intel_grade as ig  # noqa: E402

MC_PATH = os.path.join(ROOT, "data", "cache", "pit", "market_context_2025_26.parquet")

# ---- helpers ----------------------------------------------------------------

def load_market_context() -> dict[tuple, dict]:
    """Load (game_date, team) -> {total, abs_spread} lookup."""
    mc = pd.read_parquet(MC_PATH)
    mc["d"] = pd.to_datetime(mc["game_date"]).dt.normalize()
    idx: dict[tuple, dict] = {}
    for r in mc.itertuples(index=False):
        idx[(r.team, r.d)] = {"total": r.total, "abs_spread": r.abs_spread}
    return idx


def attach_market_context(bets: list[dict], mc_idx: dict[tuple, dict]) -> tuple[list[dict], int]:
    """Attach total + abs_spread to each bet by (opp, gdate)."""
    matched = 0
    for b in bets:
        key = (b["opp"], b["gdate"])
        m = mc_idx.get(key)
        if m is not None:
            b["mc_total"] = m["total"]
            b["mc_abs_spread"] = m["abs_spread"]
            matched += 1
        else:
            b["mc_total"] = np.nan
            b["mc_abs_spread"] = np.nan
    return bets, matched


def split_halves(bets: list[dict]) -> tuple[list[dict], list[dict]]:
    ds = sorted(set(b["gdate"] for b in bets))
    mid = ds[len(ds) // 2]
    return [b for b in bets if b["gdate"] < mid], [b for b in bets if b["gdate"] >= mid]


def fit_beta(bets: list[dict], stat: str, key: str) -> tuple[float | None, int]:
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 50:
        return None, len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9:
        return None, len(sub)
    beta = np.cov(sig, resid)[0, 1] / np.var(sig)
    return float(beta), len(sub)


def grade_corrected(bets: list[dict], stat: str, key: str, beta: float) -> tuple[dict, dict, int, int]:
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    flips = 0
    for b in sub:
        b["_h4_corr"] = b["pred"] + beta * b[key]
        if (b["pred"] > b["line"]) != (b["_h4_corr"] > b["line"]):
            flips += 1
    raw = ig.roi(sub, predictor="pred")
    cor = ig.roi(sub, predictor="_h4_corr")
    return raw, cor, flips, len(sub)


def residual_corr(bets: list[dict], stat: str, key: str) -> tuple[float, int]:
    sub = [b for b in bets if b["stat"] == stat
           and np.isfinite(b.get(key, np.nan))
           and np.isfinite(b.get("pred", np.nan))]
    if len(sub) < 20:
        return float("nan"), len(sub)
    sig = np.array([b[key] for b in sub], float)
    resid = np.array([b["actual"] - b["pred"] for b in sub], float)
    if np.std(sig) < 1e-9 or np.std(resid) < 1e-9:
        return float("nan"), len(sub)
    return float(np.corrcoef(sig, resid)[0, 1]), len(sub)


# ---- main -------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("H4: pregame TOTAL + |SPREAD| market-context test")
    print("=" * 72)

    # -- load substrate
    print("\n[1] Loading market_context substrate ...")
    mc_idx = load_market_context()
    print(f"  {len(mc_idx):,} (team, game_date) entries in MC lookup")

    # -- primary corpus
    print("\n[2] Loading primary corpus: extended_oos_canonical.csv ...")
    bets = ig.prepare("extended_oos_canonical.csv")
    n_raw = len(bets)
    bets, mc_matched = attach_market_context(bets, mc_idx)
    n_mc = sum(1 for b in bets if np.isfinite(b.get("mc_total", np.nan)))
    print(f"  {n_raw} bets (after ig.prepare); market-context matched {mc_matched}/{n_raw} "
          f"({100 * mc_matched / max(n_raw, 1):.0f}%); total with finite mc_total: {n_mc}")

    # -- coherence check
    print("\n[3] Coherence guard ...")
    coh = ig.coherence(bets)
    print(f"  blind-over {coh['over']['roi_pct']:+.2f}% + blind-under {coh['under']['roi_pct']:+.2f}% "
          f"= {coh['sum']:+.2f}%  {'OK (coherent)' if coh['coherent'] else 'CORRUPT (positive!) — aborting'}")
    assert coh["coherent"], "Coherence guard failed — corpus odds are corrupt"

    # =========================================================================
    # SECTION A: Point-feature screen
    # Compute residual corr(total - league_mean_total, actual - pred) for each stat
    # then fit beta on early half, grade late half
    # =========================================================================
    print("\n" + "=" * 72)
    print("SECTION A: Point-feature screen (total and abs_spread as residual signals)")
    print("=" * 72)

    # Compute league average total from MC across all games
    mc_df = pd.read_parquet(MC_PATH)
    league_mean_total = mc_df["total"].mean()
    print(f"\n  League mean total (all games in MC): {league_mean_total:.2f}")

    # Add centered total signal
    for b in bets:
        if np.isfinite(b.get("mc_total", np.nan)):
            b["mc_total_centered"] = b["mc_total"] - league_mean_total
        else:
            b["mc_total_centered"] = np.nan

    early, late = split_halves(bets)
    print(f"  Split: early n={len(early)} ({len(set(b['gdate'] for b in early))} dates), "
          f"late n={len(late)} ({len(set(b['gdate'] for b in late))} dates)")

    stats_to_test = ["pts", "reb", "ast"]
    signals = [
        ("mc_total_centered", "total (centered)", "total"),
        ("mc_abs_spread", "|spread|", "abs_spread"),
    ]

    print("\n  --- In-sample residual correlations ---")
    for sig_key, sig_label, _ in signals:
        print(f"\n  Signal: {sig_label}")
        for stat in stats_to_test:
            corr, n = residual_corr(bets, stat, sig_key)
            print(f"    {stat:5s}: corr(signal, actual-pred) = {corr:+.4f}  (n={n})")

    print("\n  --- Held-out correction: fit EARLY -> grade LATE ---")
    for sig_key, sig_label, _ in signals:
        print(f"\n  Signal: {sig_label}")
        for stat in stats_to_test:
            beta_e, ne = fit_beta(early, stat, sig_key)
            if beta_e is None:
                print(f"    {stat:5s}: beta=None (n={ne} too small), SKIP")
                continue
            raw_late, cor_late, flips, n_late = grade_corrected(late, stat, sig_key, beta_e)
            delta = cor_late["roi_pct"] - raw_late["roi_pct"]
            verdict = "-> REJECT" if abs(delta) < 0.5 or delta <= 0 else "-> POSSIBLE"
            print(f"    {stat:5s}: beta(early n={ne})={beta_e:+.4f}  |  "
                  f"late(n={n_late}): raw {raw_late['roi_pct']:+.2f}% -> corr {cor_late['roi_pct']:+.2f}%  "
                  f"delta={delta:+.2f}pp  flips={flips}/{n_late}  {verdict}")

    # =========================================================================
    # SECTION B: Selection filter screen
    # Does dropping abs_spread > 14 (blowout games) improve ROI?
    # =========================================================================
    print("\n" + "=" * 72)
    print("SECTION B: Selection filter — drop blowout games (abs_spread > 14)")
    print("=" * 72)

    # ALL bets with MC match vs abs_spread <= 14
    bets_mc = [b for b in bets if np.isfinite(b.get("mc_abs_spread", np.nan))]
    bets_no_blowout = [b for b in bets_mc if b["mc_abs_spread"] <= 14.0]
    bets_blowout = [b for b in bets_mc if b["mc_abs_spread"] > 14.0]
    print(f"\n  All bets with MC match: n={len(bets_mc)}")
    print(f"  Non-blowout (abs_spread<=14): n={len(bets_no_blowout)}")
    print(f"  Blowout (abs_spread>14): n={len(bets_blowout)}")

    print("\n  --- Per-stat ROI: ALL vs abs_spread<=14 vs abs_spread>14 ---")
    for stat in ["pts", "reb", "ast", "blk", "stl"]:
        all_s = ig.roi(bets_mc, mask=lambda b, s=stat: b["stat"] == s)
        nob_s = ig.roi(bets_no_blowout, mask=lambda b, s=stat: b["stat"] == s)
        blow_s = ig.roi(bets_blowout, mask=lambda b, s=stat: b["stat"] == s)
        print(f"  {stat:5s}: ALL n={all_s['n']:4d} roi={all_s['roi_pct']:+6.2f}% | "
              f"no-blowout n={nob_s['n']:4d} roi={nob_s['roi_pct']:+6.2f}% | "
              f"blowout n={blow_s['n']:4d} roi={blow_s['roi_pct']:+6.2f}%")

    all_roi = ig.roi(bets_mc)
    nob_roi = ig.roi(bets_no_blowout)
    blow_roi = ig.roi(bets_blowout)
    print(f"\n  ALL stats: ALL n={all_roi['n']:4d} roi={all_roi['roi_pct']:+6.2f}% | "
          f"no-blowout n={nob_roi['n']:4d} roi={nob_roi['roi_pct']:+6.2f}% | "
          f"blowout n={blow_roi['n']:4d} roi={blow_roi['roi_pct']:+6.2f}%")

    # Both halves for selection filter
    print("\n  --- Selection filter by half (abs_spread<=14) ---")
    early_mc = [b for b in early if np.isfinite(b.get("mc_abs_spread", np.nan))]
    late_mc = [b for b in late if np.isfinite(b.get("mc_abs_spread", np.nan))]
    early_nob = [b for b in early_mc if b["mc_abs_spread"] <= 14.0]
    late_nob = [b for b in late_mc if b["mc_abs_spread"] <= 14.0]

    e_all = ig.roi(early_mc)
    e_nob = ig.roi(early_nob)
    l_all = ig.roi(late_mc)
    l_nob = ig.roi(late_nob)
    print(f"  Early: ALL n={e_all['n']:4d} roi={e_all['roi_pct']:+6.2f}%  | "
          f"no-blowout n={e_nob['n']:4d} roi={e_nob['roi_pct']:+6.2f}%  "
          f"delta={e_nob['roi_pct']-e_all['roi_pct']:+.2f}pp")
    print(f"  Late:  ALL n={l_all['n']:4d} roi={l_all['roi_pct']:+6.2f}%  | "
          f"no-blowout n={l_nob['n']:4d} roi={l_nob['roi_pct']:+6.2f}%  "
          f"delta={l_nob['roi_pct']-l_all['roi_pct']:+.2f}pp")

    # -- Total tercile analysis
    print("\n  --- Total tercile analysis ---")
    totals = np.array([b["mc_total"] for b in bets_mc])
    t33 = np.percentile(totals, 33.3)
    t67 = np.percentile(totals, 66.7)
    print(f"  Total terciles: low<=  {t33:.1f}, mid [{t33:.1f},{t67:.1f}], high>{t67:.1f}")

    for tier, mask in [
        ("low  ", lambda b: b["mc_total"] <= t33),
        ("mid  ", lambda b: t33 < b["mc_total"] <= t67),
        ("high ", lambda b: b["mc_total"] > t67),
    ]:
        sub = [b for b in bets_mc if mask(b)]
        r = ig.roi(sub)
        print(f"  total {tier}: n={r['n']:4d} roi={r['roi_pct']:+6.2f}%  win={r['win_pct']:.1f}%")

    # -- Different abs_spread thresholds
    print("\n  --- Abs_spread threshold sweep ---")
    for thresh in [8.0, 10.0, 12.0, 14.0, 16.0, 18.0]:
        sub = [b for b in bets_mc if b["mc_abs_spread"] <= thresh]
        r = ig.roi(sub)
        dropped = len(bets_mc) - len(sub)
        print(f"  abs_spread<={thresh:.0f}: n={r['n']:4d} roi={r['roi_pct']:+6.2f}%  "
              f"dropped={dropped}")

    # =========================================================================
    # Cross-season note
    # =========================================================================
    print("\n" + "=" * 72)
    print("CROSS-SEASON NOTE: regular_season_2024_25_oddsapi.csv")
    print("=" * 72)
    print("  pregame_spreads.parquet covers 2025-10-21..2026-05-25 only.")
    print("  The 2024-25 corpus has NO market context from this substrate.")
    print("  Cross-season test is SKIPPED — market-context signal cannot be")
    print("  validated cross-season with the available data.")

    # Also check 2024-25 corpus coverage
    try:
        cs = ig.prepare("regular_season_2024_25_oddsapi.csv")
        cs, cs_matched = attach_market_context(cs, mc_idx)
        cs_finite = sum(1 for b in cs if np.isfinite(b.get("mc_total", np.nan)))
        print(f"  Cross-season bets: {len(cs)}, MC match: {cs_matched}/{len(cs)} "
              f"(finite: {cs_finite}) — confirms NO overlap")
    except Exception as ex:
        print(f"  Cross-season load error: {ex}")

    # =========================================================================
    # Summary verdict
    # =========================================================================
    print("\n" + "=" * 72)
    print("SUMMARY VERDICT")
    print("=" * 72)

    # Compute key numbers for verdict
    # Point-feature: check if any held-out correction meaningfully helps
    any_point_positive = False
    for sig_key, _, _ in signals:
        for stat in stats_to_test:
            beta_e, ne = fit_beta(early, stat, sig_key)
            if beta_e is not None:
                _, cor_late, _, _ = grade_corrected(late, stat, sig_key, beta_e)
                raw_late_r = ig.roi([b for b in late if b["stat"] == stat
                                     and np.isfinite(b.get(sig_key, np.nan))
                                     and np.isfinite(b.get("pred", np.nan))])
                delta = cor_late["roi_pct"] - raw_late_r["roi_pct"]
                if delta > 0.5:
                    any_point_positive = True

    # Selection filter: does dropping blowouts help in BOTH halves?
    filter_both_halves = (
        e_nob["roi_pct"] > e_all["roi_pct"] and
        l_nob["roi_pct"] > l_all["roi_pct"]
    )
    filter_delta_late = l_nob["roi_pct"] - l_all["roi_pct"]

    print(f"\n  (a) Point-feature held-out delta > 0.5pp in any stat/signal: "
          f"{'YES' if any_point_positive else 'NO (REJECT)'}")
    print(f"  (b) Selection filter (abs_spread<=14) improves ROI in BOTH halves: "
          f"{'YES' if filter_both_halves else 'NO'}")
    print(f"      Early delta: {e_nob['roi_pct']-e_all['roi_pct']:+.2f}pp  "
          f"Late delta: {filter_delta_late:+.2f}pp")
    print(f"  (b) Cross-season validation: NOT AVAILABLE (substrate ends 2026-05-25)")

    if not any_point_positive and not filter_both_halves:
        print("\n  FINAL: REJECT — neither point-feature correction nor selection filter")
        print("         shows consistent improvement in held-out data.")
    elif filter_both_halves and abs(filter_delta_late) > 0.5:
        print("\n  FINAL: PROMISING (selection filter) — dropping abs_spread>14 improves")
        print("         ROI in both halves. No cross-season confirmation available.")
    else:
        print("\n  FINAL: INCONCLUSIVE — marginal or one-sided improvement only.")


if __name__ == "__main__":
    main()

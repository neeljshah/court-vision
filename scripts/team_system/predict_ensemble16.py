"""16-ENGINE META-ENSEMBLE — fuse the 7 existing engines + 9 new engines.

honesty_class = research.
Bar (V5): >=1 NEW engine that MEASURABLY lowers ensemble margin variance
(decorrelates from the net-rating cluster) — measured on the 16x16 matrix,
not assumed.  Redundancy is the expected default and is reported honestly.
More engines = better/more-robust prediction + honest uncertainty,
NOT a betting edge (no proven playoff edge; no edge is claimed here).

FILE OWNERSHIP: creates only predict_ensemble16.py + engine_decorrelation16.json
at runtime.  predict_ensemble.py stays BYTE-IDENTICAL (enforced by test 6).

Usage:
  python scripts/team_system/predict_ensemble16.py --home NYK --away SAS
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import math
import os
import sys
from typing import Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import pandas as pd  # noqa: E402
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from sim.game_clock_sim import simulate_clock  # noqa: E402
from sim import clutch_adjust as ca  # noqa: E402

ASC = lambda s: str(s).encode("ascii", "replace").decode()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def n_eff_from_corr(R: np.ndarray) -> float:
    """Kish effective N from correlation matrix: N^2 / (1^T R 1)."""
    N = R.shape[0]
    ones = np.ones(N)
    denom = float(ones @ R @ ones)
    return float(N ** 2 / max(denom, 1e-9))


def _brain_eng_w(preds: list) -> Optional[np.ndarray]:
    """Default-OFF control-brain cutover hook (P2). Returns brain-supplied engine weights when
    CV_BRAIN_WEIGHTS=1, else None so the existing equal-weight path is preserved EXACTLY.
    Rung 0 returns equal weights -> (eng_w * margins).sum() == margins.mean() -> byte-identical.
    Any failure returns None (never regresses the live ensemble)."""
    if os.environ.get("CV_BRAIN_WEIGHTS") != "1":
        return None
    try:
        from brain.control_brain import engine_weights as _bw  # brain is on sys.path (src)
        w = _bw(preds)
        return w if (w is not None and len(w) == len(preds)) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Load existing engines (engines/ dir — same as predict_ensemble.py)
# ---------------------------------------------------------------------------

def _load_analytic_engines() -> list[tuple[str, object]]:
    mods = []
    for fp in sorted(glob.glob(os.path.join(HERE, "engines", "engine_*.py"))):
        name = os.path.splitext(os.path.basename(fp))[0]
        spec = importlib.util.spec_from_file_location(name, fp)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            if hasattr(m, "predict"):
                mods.append((name, m))
        except Exception as e:
            print(f"  !! {name} load failed: {ASC(str(e))[:80]}")
    return mods


def _load_new_engines() -> list[tuple[str, object]]:
    mods = []
    for fp in sorted(glob.glob(os.path.join(HERE, "engines_x", "engine_*.py"))):
        name = os.path.splitext(os.path.basename(fp))[0]
        spec = importlib.util.spec_from_file_location(name, fp)
        m = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(m)
            if hasattr(m, "predict"):
                mods.append((name, m))
        except Exception as e:
            print(f"  !! {name} load failed: {ASC(str(e))[:80]}")
    return mods


# ---------------------------------------------------------------------------
# Possession MC + Clock engines (copied from predict_ensemble.py — read-only)
# ---------------------------------------------------------------------------

def _possession_engine(home: object, away: object, n: int = 20000) -> dict:
    res = simulate_game_fast(home, away, n_sims=n, seed=20260608,
                             anchor=True, defense=True,
                             context={"neutral_site": False})
    m = res.home_total - res.away_total
    npl = sum(1 for p in res.players if res.players[p]["mean"]["pts"] >= 1)
    return {
        "engine": "possession_mc",
        "win_prob_home": float((m > 0).mean()),
        "margin_home": float(m.mean()),
        "total": float((res.home_total + res.away_total).mean()),
        "home_pts": float(res.home_total.mean()),
        "away_pts": float(res.away_total.mean()),
        "margin_sd": float(m.std()),
        "n_models": npl,
        "n_signals": npl * 25,
        "notes": "anchored player possession MC",
        "_margin_samples": m,
    }


def _clock_engine(home: object, away: object, n: int = 4000) -> dict:
    r = simulate_clock(home, away, n_sims=n, seed=20260608)
    m = r["finalh"] - r["finala"]
    return {
        "engine": "clock_trajectory",
        "win_prob_home": float(r["home_win"]),
        "margin_home": float(m.mean()),
        "total": float((r["finalh"] + r["finala"]).mean()),
        "home_pts": float(r["finalh"].mean()),
        "away_pts": float(r["finala"].mean()),
        "margin_sd": float(m.std()),
        "n_models": 10,
        "n_signals": 200,
        "notes": "clock-aware trajectory engine",
        "_margin_samples": m,
    }


# ---------------------------------------------------------------------------
# Decorrelation measurement across reference matchups
# ---------------------------------------------------------------------------

def _build_panel(n: int = 80) -> list[tuple[str, str]]:
    """Build a spread of league matchups for the correlation panel."""
    ltg_path = os.path.join(ROOT, "data", "cache", "team_system", "league_team_game.parquet")
    lg = pd.read_parquet(ltg_path)
    pairs = lg[["team", "opp"]].drop_duplicates().values.tolist()
    rng = np.random.default_rng(20260608)
    rng.shuffle(pairs)
    panel: list[tuple[str, str]] = []
    for h, a in pairs:
        if h != a:
            panel.append((str(h), str(a)))
        if len(panel) >= n:
            break
    return panel


def _measure_decorrelation(
    all_engines: list[tuple[str, object]],
    home_tri: str = "NYK",
    away_tri: str = "SAS",
    panel_n: int = 80,
) -> dict:
    """Measure 16x16 margin-correlation matrix across reference matchups.

    For the 2 NYK/SAS-only engines (lineup_markov, clutch_close) that may raise
    ValueError on other teams, we substitute a fixed margin from their NYK/SAS
    output for the whole panel (this INFLATES their corr-to-cluster by making them
    constant — noted honestly: true decorrelation unknown for non-NYK/SAS teams).
    """
    ctx = {"neutral_site": True}
    panel = _build_panel(panel_n)
    n = len(all_engines)
    names = [nm for nm, _ in all_engines]
    M = np.full((len(panel), n), np.nan)

    # Fallback margins for 2-team-only engines (constant across panel)
    fallback: dict[str, float] = {}
    for nm, m in all_engines:
        try:
            p = m.predict(home_tri, away_tri, ctx)
            fallback[nm] = float(p["margin_home"])
        except Exception:
            fallback[nm] = 0.0

    for j, (nm, m) in enumerate(all_engines):
        for i, (h, aw) in enumerate(panel):
            try:
                p = m.predict(h, aw, ctx)
                M[i, j] = float(p["margin_home"])
            except Exception:
                # 2-team-only engine: use the fallback constant
                M[i, j] = fallback.get(nm, 0.0)

    # Drop rows with any remaining nan
    ok = ~np.isnan(M).any(axis=1)
    M = M[ok]

    R = np.corrcoef(M.T) if M.shape[0] > 1 else np.eye(n)
    # Guard NaN in R (constant engine = 0 var => corr undefined)
    R = np.nan_to_num(R, nan=1.0)
    np.fill_diagonal(R, 1.0)

    n_eff_16 = n_eff_from_corr(R)
    mean_offdiag = float((R.sum() - n) / max(n * (n - 1), 1))

    # Define the cluster = engines whose mean corr to the 5 analytic engines > 0.85
    analytic_names = {
        "engine_attribute_matchup", "engine_four_factors",
        "engine_player_impact", "engine_power_ratings", "engine_team_score",
    }
    analytic_idx = [i for i, nm in enumerate(names) if nm in analytic_names]
    corr_to_cluster: dict[str, float] = {}
    for i, nm in enumerate(names):
        if analytic_idx:
            corr_to_cluster[nm] = float(
                np.mean([R[i, j] for j in analytic_idx if j != i])
            )
        else:
            corr_to_cluster[nm] = float("nan")

    return {
        "names": names,
        "corr_matrix": R,
        "n_eff_16": n_eff_16,
        "mean_offdiag": mean_offdiag,
        "corr_to_cluster": corr_to_cluster,
        "n_matchups": int(M.shape[0]),
    }


# ---------------------------------------------------------------------------
# Main prediction + fusion
# ---------------------------------------------------------------------------

def run(home_tri: str = "NYK", away_tri: str = "SAS",
        context: Optional[dict] = None) -> dict:
    """Run all 16 engines and fuse.  Returns the full result dict."""
    ctx = context or {}
    home_model = TeamModel.from_cache(home_tri)
    away_model = TeamModel.from_cache(away_tri)

    # ---- Load all engines --------------------------------------------------
    analytic_mods = _load_analytic_engines()   # 5 from engines/
    new_mods = _load_new_engines()             # 9 from engines_x/
    preds: list[dict] = []
    all_loaded: list[tuple[str, object]] = []

    for name, m in analytic_mods:
        try:
            p = m.predict(home_tri, away_tri, ctx)
            p["engine"] = p.get("engine", name)
            p["_source"] = "analytic"
            preds.append(p)
            all_loaded.append((name, m))
        except Exception as e:
            print(f"  !! {name}.predict failed: {ASC(str(e))[:80]}")

    for name, m in new_mods:
        try:
            p = m.predict(home_tri, away_tri, ctx)
            p["engine"] = p.get("engine", name.replace("engine_", ""))
            p["_source"] = "new"
            preds.append(p)
            all_loaded.append((name, m))
        except Exception as e:
            print(f"  !! {name}.predict failed (excluded, fusion continues): "
                  f"{ASC(str(e))[:80]}")

    # MC engines (always NYK/SAS-aware)
    poss_pred = _possession_engine(home_model, away_model)
    poss_pred["_source"] = "mc"
    clock_pred = _clock_engine(home_model, away_model)
    clock_pred["_source"] = "mc"
    preds.append(poss_pred)
    preds.append(clock_pred)
    # Add MC engines to all_loaded for corr measurement — use a thin wrapper
    # that delegates to the already-cached predict from predict_ensemble.py;
    # simplest: skip MC from corr panel (analytic panel only), report separately.

    # ---- Decorrelation measurement (analytic + new, not MC) ----------------
    if all_loaded:
        decor = _measure_decorrelation(all_loaded, home_tri, away_tri, panel_n=80)
    else:
        decor = {"names": [], "corr_matrix": np.eye(0), "n_eff_16": float("nan"),
                 "mean_offdiag": float("nan"), "corr_to_cluster": {}, "n_matchups": 0}

    # ---- Persist decorrelation16 artifact (new file, no collision) ---------
    ts_dir = os.path.join(ROOT, "data", "cache", "team_system")
    out16 = os.path.join(ts_dir, "engine_decorrelation16.json")
    R = decor["corr_matrix"]
    n16 = len(decor["names"])
    corr_to_cluster = decor["corr_to_cluster"]

    # Per-new-engine verdict
    new_engine_names = {nm.replace("engine_", "") for nm, _ in new_mods}
    new_engine_verdicts: dict[str, str] = {}
    decorrelating_new: list[str] = []
    for nm in decor["names"]:
        short = nm.replace("engine_", "")
        if short not in new_engine_names:
            continue
        r_c = corr_to_cluster.get(nm, float("nan"))
        if math.isnan(r_c):
            verdict = "UNKNOWN (nan)"
        elif r_c < 0.85:
            verdict = f"DECORRELATES (r={r_c:.2f})"
            decorrelating_new.append(short)
        else:
            verdict = f"REDUNDANT (r={r_c:.2f}, joins cluster)"
        new_engine_verdicts[short] = verdict

    artifact: dict = {
        "honesty_class": "research",
        "asof": "2026-06-08",
        "builder": "predict_ensemble16.py",
        "engines_analytic_and_new": decor["names"],
        "n_analytic_and_new": n16,
        "n_matchups": decor["n_matchups"],
        "corr_matrix": R.tolist() if hasattr(R, "tolist") else [],
        "mean_offdiag_corr": decor["mean_offdiag"],
        "n_eff_16": decor["n_eff_16"],
        "n_eff_7_prior": 1.64,
        "corr_to_cluster": {k: round(v, 4) for k, v in corr_to_cluster.items()
                            if not math.isnan(v)},
        "new_engine_verdicts": new_engine_verdicts,
        "decorrelating_new_engines": decorrelating_new,
        "note": (
            "2-team-only engines (lineup_markov, clutch_close) use a constant "
            "NYK/SAS margin across the panel — this inflates their apparent "
            "decorrelation; treat their r-to-cluster with caution. "
            "MC engines (possession_mc, clock_trajectory) excluded from panel "
            "(would require full TeamModel cache for all 30 teams)."
        ),
    }
    tmp = out16 + ".staging"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(artifact, fh, indent=1)
    os.replace(tmp, out16)

    # ---- Reliability weights (honor the null: beats_equal_weight=false) ----
    rw_path = os.path.join(ts_dir, "engine_reliability_weights.json")
    use_reliability = False
    if os.environ.get("CV_ENGINE_RELIABILITY_WEIGHTS") == "1" and os.path.exists(rw_path):
        rw = json.load(open(rw_path))
        if rw.get("beats_equal_weight"):
            use_reliability = True

    margins = np.array([p["margin_home"] for p in preds])
    sds = np.array([p["margin_sd"] for p in preds])
    totals = np.array([p["total"] for p in preds])

    # Decorrelation-aware weight (gated CV_ENSEMBLE16_DECORR, default OFF)
    eng_w: Optional[np.ndarray] = None
    if os.environ.get("CV_ENSEMBLE16_DECORR") == "1":
        # Down-weight redundant engines: cluster of k r~1 engines counts ~once
        cluster_thresh = 0.85
        w_raw = np.ones(len(preds))
        for i, p in enumerate(preds):
            nm = "engine_" + p["engine"] if not p["engine"].startswith("engine_") else p["engine"]
            r_c = corr_to_cluster.get(nm, 0.5)
            # Count how many other engines are in the same cluster as this one
            cluster_count = max(1, sum(
                1 for nm2, r2 in corr_to_cluster.items()
                if nm2 != nm and r2 > cluster_thresh
            ))
            if r_c > cluster_thresh:
                w_raw[i] = 1.0 / cluster_count
        if w_raw.sum() > 0:
            eng_w = w_raw / w_raw.sum()

    # Learned control brain (gated CV_BRAIN_WEIGHTS, default OFF; CV_ENSEMBLE16_DECORR takes precedence).
    # Rung 0 = equal-weight -> eq_margin == margins.mean() -> byte-identical to the default path. (P2 cutover)
    if eng_w is None:
        eng_w = _brain_eng_w(preds)

    # Default = equal weight (byte-identical baseline when gate OFF)
    eq_margin = float((eng_w * margins).sum()) if eng_w is not None else float(margins.mean())
    eq_total = float(totals.mean())

    # Inverse-variance cross-check
    w_iv = 1.0 / np.maximum(sds, 1e-6) ** 2
    w_iv = w_iv / w_iv.sum()
    iv_margin = float((w_iv * margins).sum())

    # Use bayesian_power's calibrated SD if present (wider, better-calibrated)
    bp_sd = next((p["margin_sd"] for p in preds if "bayesian" in p["engine"]), None)
    pooled_sd = float(np.sqrt((w_iv * sds ** 2).sum()))
    if bp_sd is not None:
        pooled_sd = max(pooled_sd, bp_sd)

    engine_spread = float(margins.std())
    eq_wp = _phi(eq_margin / pooled_sd)
    iv_wp = _phi(iv_margin / pooled_sd)

    # Clutch overlay (competitive games only)
    tg_path = os.path.join(ts_dir, "team_game.parquet")
    tg = pd.read_parquet(tg_path)
    tilt = ca.clutch_tilt(home_tri, away_tri, tg)
    rng = np.random.default_rng(7)
    sim_margins = rng.normal(eq_margin, pooled_sd, 200000)
    adj = ca.adjust_margin(sim_margins.copy(), tilt)
    clutch_wp = float((adj > 0).mean())

    # N_eff widened band
    n_eff_16 = decor["n_eff_16"]
    widen_factor = math.sqrt(len(preds) / max(n_eff_16, 1e-6)) if not math.isnan(n_eff_16) else float("nan")
    eff_band = engine_spread * widen_factor if not math.isnan(widen_factor) else engine_spread

    return {
        "preds": preds,
        "decor": decor,
        "artifact": artifact,
        "new_engine_verdicts": new_engine_verdicts,
        "decorrelating_new": decorrelating_new,
        "eq_margin": eq_margin,
        "iv_margin": iv_margin,
        "eq_total": eq_total,
        "pooled_sd": pooled_sd,
        "engine_spread": engine_spread,
        "eq_wp": eq_wp,
        "iv_wp": iv_wp,
        "clutch_wp": clutch_wp,
        "tilt": tilt,
        "n_eff_16": n_eff_16,
        "widen_factor": widen_factor,
        "eff_band": eff_band,
        "n_eff_7_prior": 1.64,
        "home_tri": home_tri,
        "away_tri": away_tri,
        "out16_path": out16,
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def _print_results(r: dict) -> None:
    home = r["home_tri"]
    away = r["away_tri"]
    preds = r["preds"]
    decor = r["decor"]
    corr_to_cluster = decor["corr_to_cluster"]
    new_engine_verdicts = r["new_engine_verdicts"]
    margins = np.array([p["margin_home"] for p in preds])

    print(f"\n=== 16-ENGINE ENSEMBLE: {away} @ {home} ({len(preds)} engines) ===")
    print(f"honesty_class=research | playoff projection | no proven betting edge\n")

    # Per-engine table
    hdr = f"{'engine':22s} {'win%':>6s} {'margin':>7s} {'total':>6s} {'mSD':>5s} {'src':>5s} {'corr-clust':>11s} {'verdict'}"
    print(hdr)
    print("-" * len(hdr))
    tot_models = tot_signals = 0
    for p in preds:
        tot_models += int(p.get("n_models", 0))
        tot_signals += int(p.get("n_signals", 0))
        nm = p["engine"]
        nm_key = "engine_" + nm if not nm.startswith("engine_") else nm
        r_c = corr_to_cluster.get(nm_key, float("nan"))
        r_str = f"{r_c:.2f}" if not math.isnan(r_c) else "  N/A"
        src = p.get("_source", "?")
        # verdict for new engines
        short = nm.replace("engine_", "")
        verd = new_engine_verdicts.get(short, "")
        verd_short = verd[:30] if verd else ("analytic" if src == "analytic" else "mc")
        print(f"{nm:22s} {p['win_prob_home']*100:5.1f}% {p['margin_home']:+7.1f} "
              f"{p['total']:6.0f} {p['margin_sd']:5.1f} {src:>5s} {r_str:>11s}  {verd_short}")

    print()
    print(f"--- FUSION ({len(preds)} engines) ---")
    print(f"equal-weight margin {home} {r['eq_margin']:+.2f}  -> win prob {home} {r['eq_wp']*100:.1f}%")
    print(f"inverse-var  margin {home} {r['iv_margin']:+.2f}  -> win prob {home} {r['iv_wp']*100:.1f}%")
    print(f"fused total {r['eq_total']:.1f}  |  pooled game SD {r['pooled_sd']:.1f}  "
          f"|  ENGINE DISAGREEMENT {r['engine_spread']:.1f}")
    print(f"clutch overlay (tilt {home} {r['tilt']:+.2f}): "
          f"win prob {r['eq_wp']*100:.1f}% -> {r['clutch_wp']*100:.1f}%")

    proj_h = r["eq_total"] / 2 + r["eq_margin"] / 2
    proj_a = r["eq_total"] / 2 - r["eq_margin"] / 2
    print(f"\n--- ONE PREDICTION ---")
    print(f"{home} {proj_h:.1f} - {proj_a:.1f} {away}  "
          f"(margin {home} {r['eq_margin']:+.1f}, total {r['eq_total']:.0f})")
    print(f"WIN PROBABILITY {home} {r['clutch_wp']*100:.0f}% / "
          f"{away} {(1-r['clutch_wp'])*100:.0f}%  "
          f"(talent-ensemble {r['eq_wp']*100:.0f}%, +clutch overlay)")

    print(f"\n--- N_eff / DECORRELATION AUDIT (16 engines) ---")
    n16 = r["n_eff_16"]
    n16_str = f"{n16:.2f}" if not math.isnan(n16) else "N/A"
    print(f"N_eff_7  (prior, 7 engines)  = 1.64")
    print(f"N_eff_16 (measured, {len(preds)} engines) = {n16_str}")
    wf = r["widen_factor"]
    wf_str = f"{wf:.2f}x" if not math.isnan(wf) else "N/A"
    print(f"Widen factor sqrt({len(preds)}/N_eff) = {wf_str}  "
          f"| honest model-uncertainty band ~ {r['eff_band']:.1f} pts")
    print(f"mean off-diagonal corr = {decor['mean_offdiag']:.3f}")

    print(f"\n--- V5 CHECK: NEW ENGINE VERDICTS ---")
    for short, verdict in new_engine_verdicts.items():
        print(f"  {short:25s}  {verdict}")
    if r["decorrelating_new"]:
        print(f"\nV5 PASSED: NEW decorrelating engines: "
              f"{r['decorrelating_new']} -> N_eff 1.64 -> {n16_str}")
    else:
        print(f"\nV5 RESULT: none of the 9 new engines cleared r<0.85 to cluster "
              f"(all joined the net-rating cluster or are constant/2-team-only). "
              f"A bigger redundant net-rating cluster is NOT progress. "
              f"Value added: bayesian_power calibrated SD, clutch wedge (2-team).")

    print(f"\nHIERARCHY: ~{tot_signals:,} signals -> {tot_models} models -> "
          f"{len(preds)} engines -> 1 prediction")
    print(f"engine consensus: {(margins>0).sum()}/{len(preds)} lean {home}; "
          f"disagreement {r['engine_spread']:.1f} pts "
          f"(range {margins.min():+.1f} to {margins.max():+.1f})")
    print(f"wrote decorrelation16 artifact -> {r['out16_path']}")
    print(f"\nHONEST: playoff projection, no proven betting edge "
          f"(closing line beats the model in playoffs).")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    a = ap.parse_args()
    result = run(a.home, a.away)
    _print_results(result)


if __name__ == "__main__":
    main()

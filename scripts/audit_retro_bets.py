"""audit_retro_bets.py — INT-82 Retro Bet Audit

Identifies the worst-200 bets in the canonical ledger and attributes them
to specific failure modes via per-row CLV (model-edge definition).

CLV definition: model-edge, NOT line-movement.
  edge_line = (pred - closing_line) for OVER, (closing_line - pred) for UNDER
  clv_pp = 100 * edge_line / max(closing_line, 0.5)
The bottom-200 rows by clv_pp form the audit cohort.

Outputs:
  data/intelligence/retro_bet_audit.parquet  — 200-row attribution table
  vault/Intelligence/INT-82_Retro_Bet_Audit.md — analysis vault doc

DIAGNOSTIC ONLY — no SHIP gate.
"""
from __future__ import annotations

import os
import sys
import json
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── env must be set before any project imports ──────────────────────────────
os.environ["NBA_INJURY_WIRE_DISABLE"] = "1"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import stats as scipy_stats
from tqdm import tqdm

from scripts.backtest_closing_lines_2024_playoffs import (
    _resolve_player_id,
    _season_for_date,
    _classify_result,
    _odds_to_decimal_profit,
    _build_asof_row,
)
from src.prediction.prop_pergame import predict_pergame

# ── constants ────────────────────────────────────────────────────────────────
GAMELOG_DIR = str(ROOT / "data" / "nba")
HIST_DIR = ROOT / "data" / "external" / "historical_lines"
INTEL_DIR = ROOT / "data" / "intelligence"
OUT_PARQUET = ROOT / "data" / "intelligence" / "retro_bet_audit.parquet"
OUT_MD = ROOT / "vault" / "Intelligence" / "INT-82_Retro_Bet_Audit.md"

# The 4 canonical CSV files (recipe: "Union 4 historical_lines CSVs")
CANONICAL_CSVS = [
    HIST_DIR / "extended_oos_canonical.csv",
    HIST_DIR / "benashkar_2026_canonical.csv",
    HIST_DIR / "playoffs_2024_canonical.csv",
    HIST_DIR / "regular_season_2024_25_oddsapi.csv",
]

BUILD_TS = datetime.utcnow().isoformat()[:19] + "Z"


# ── ledger assembly ──────────────────────────────────────────────────────────

def _load_ledger() -> pd.DataFrame:
    """Union canonical CSVs, dedup on (date, player, opp, stat, closing_line)."""
    dfs: List[pd.DataFrame] = []
    needed = ["date", "player", "opp", "stat", "closing_line", "actual_value", "venue"]
    for fpath in CANONICAL_CSVS:
        if not fpath.exists():
            print(f"  [warn] missing: {fpath.name}")
            continue
        try:
            df = pd.read_csv(fpath, on_bad_lines="warn")
            df.columns = [c.lower().strip() for c in df.columns]
            # keep only needed columns that exist
            keep = [c for c in needed if c in df.columns]
            dfs.append(df[keep])
        except Exception as e:
            print(f"  [warn] failed to load {fpath.name}: {e}")

    if not dfs:
        raise RuntimeError("No ledger CSVs loaded.")

    combined = pd.concat(dfs, ignore_index=True)
    n_before = len(combined)
    combined = combined.drop_duplicates(
        subset=["date", "player", "opp", "stat", "closing_line"]
    )
    n_after = len(combined)
    print(f"  Ledger: {n_before} rows combined -> {n_after} after dedup  (expected ~8,176)")
    return combined.reset_index(drop=True)


# ── per-row scoring ──────────────────────────────────────────────────────────

def _score_rows(ledger: pd.DataFrame) -> pd.DataFrame:
    """Run predict_pergame on every ledger row; compute clv_pp."""
    # Resolve player IDs once
    unique_names = ledger["player"].unique()
    name2pid: Dict[str, Optional[int]] = {}
    print(f"  Resolving {len(unique_names)} unique player names ...")
    for nm in tqdm(unique_names, desc="PID resolve"):
        name2pid[nm] = _resolve_player_id(nm)
    resolved = sum(1 for v in name2pid.values() if v is not None)
    print(f"  Resolved {resolved}/{len(unique_names)} player names")

    # Cache feature rows by (pid, date, venue, opp)
    row_cache: Dict[Tuple[int, str, str, str], Optional[Dict[str, float]]] = {}

    results: List[dict] = []
    skip_reasons: Dict[str, int] = {}

    def _skip(reason: str) -> None:
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    t0 = time.time()
    pbar = tqdm(ledger.itertuples(index=False), total=len(ledger), desc="Scoring")
    for i, row in enumerate(pbar):
        if i > 0 and i % 500 == 0:
            elapsed = time.time() - t0
            pbar.set_postfix({"skip": sum(skip_reasons.values()),
                               "done": len(results),
                               "t": f"{elapsed:.0f}s"})

        player = str(row.player)
        opp = str(row.opp)
        stat = str(row.stat).lower()
        venue = getattr(row, "venue", "home")
        if not isinstance(venue, str):
            venue = "home"

        try:
            line = float(row.closing_line)
            actual = float(row.actual_value)
        except (TypeError, ValueError):
            _skip("bad_numeric")
            continue

        try:
            d = datetime.fromisoformat(str(row.date))
        except Exception:
            _skip("bad_date")
            continue

        pid = name2pid.get(player)
        if pid is None:
            _skip("no_pid")
            continue

        season = _season_for_date(d)
        is_home = (str(venue).lower() == "home")
        cache_key = (pid, str(row.date), venue, opp)

        if cache_key not in row_cache:
            try:
                row_cache[cache_key] = _build_asof_row(
                    pid, opp, d, season,
                    is_home=is_home, rest_days=2.0,
                    gamelog_dir=GAMELOG_DIR,
                )
            except Exception as e:
                row_cache[cache_key] = None
        feat_row = row_cache[cache_key]
        if feat_row is None:
            _skip("no_history")
            continue

        try:
            pred = predict_pergame(stat, feat_row)
        except Exception as e:
            _skip(f"predict_err:{type(e).__name__}")
            continue
        if pred is None:
            _skip("model_missing")
            continue
        pred = float(pred)

        # Side and CLV
        side = "OVER" if pred > line else "UNDER"
        if side == "OVER":
            edge_line = pred - line
        else:
            edge_line = line - pred
        clv_pp = 100.0 * edge_line / max(line, 0.5)

        # Bet won?
        actual_result = _classify_result(actual, line)
        won = bool(actual_result == side) if actual_result != "PUSH" else None

        results.append({
            "date": str(row.date),
            "player": player,
            "player_id": pid,
            "opp": opp,
            "stat": stat,
            "side": side,
            "closing_line": line,
            "pred": pred,
            "actual_value": actual,
            "clv_pp": clv_pp,
            "won": won,
        })

    elapsed = time.time() - t0
    print(f"  Scoring done in {elapsed:.1f}s. Scored: {len(results)}, skipped: {sum(skip_reasons.values())}")
    print(f"  Skip reasons: {skip_reasons}")
    return pd.DataFrame(results)


# ── attribution joins ─────────────────────────────────────────────────────────

def _load_cv_coverage(scored: pd.DataFrame) -> pd.Series:
    """Per-row cv_coverage_tier: high/med/low/none based on last coverage_gate before date."""
    try:
        gates = pd.read_parquet(INTEL_DIR / "cv_coverage_gates.parquet")
        gates["game_date"] = pd.to_datetime(gates["game_date"])
        gates["nba_player_id"] = gates["nba_player_id"].astype(int)
        gates = gates.sort_values("game_date")
    except Exception as e:
        print(f"  [warn] cv_coverage_gates load failed: {e}")
        return pd.Series(["unknown"] * len(scored), index=scored.index)

    out = []
    for _, row in scored.iterrows():
        pid = int(row["player_id"])
        asof = pd.to_datetime(row["date"])
        sub = gates[(gates["nba_player_id"] == pid) & (gates["game_date"] < asof)]
        if sub.empty:
            out.append("none")
            continue
        last_gate = float(sub.iloc[-1]["coverage_gate"])
        if last_gate >= 0.6:
            out.append("high")
        elif last_gate >= 0.4:
            out.append("med")
        elif last_gate >= 0.2:
            out.append("low")
        else:
            out.append("none")
    return pd.Series(out, index=scored.index, name="cv_coverage_tier")


def _load_opp_atlas_density(scored: pd.DataFrame) -> pd.Series:
    """Per-row opp_atlas_density: last opp_join_density before date."""
    try:
        opp_cv = pd.read_parquet(INTEL_DIR / "opp_normalized_cv.parquet")
        opp_cv["game_date"] = pd.to_datetime(opp_cv["game_date"])
        opp_cv["player_id"] = opp_cv["player_id"].astype(int)
        opp_cv = opp_cv.sort_values("game_date")
    except Exception as e:
        print(f"  [warn] opp_normalized_cv load failed: {e}")
        return pd.Series(["unknown"] * len(scored), index=scored.index)

    out = []
    for _, row in scored.iterrows():
        pid = int(row["player_id"])
        asof = pd.to_datetime(row["date"])
        sub = opp_cv[(opp_cv["player_id"] == pid) & (opp_cv["game_date"] < asof)]
        if sub.empty:
            out.append("unknown")
            continue
        out.append(str(sub.iloc[-1]["opp_join_density"]))
    return pd.Series(out, index=scored.index, name="opp_atlas_density")


def _load_calibration_bias(scored: pd.DataFrame) -> pd.Series:
    """Per-row calibration_bias: known_under/over/neutral from per_player_calibration bias_l20."""
    try:
        cal = pd.read_parquet(INTEL_DIR / "per_player_calibration.parquet")
        cal["asof_date"] = pd.to_datetime(cal["asof_date"])
        cal["player_id"] = cal["player_id"].astype(int)
        cal = cal.sort_values("asof_date")
    except Exception as e:
        print(f"  [warn] per_player_calibration load failed: {e}")
        return pd.Series(["unknown"] * len(scored), index=scored.index)

    out = []
    for _, row in scored.iterrows():
        pid = int(row["player_id"])
        stat = str(row["stat"]).lower()
        asof = pd.to_datetime(row["date"])
        sub = cal[
            (cal["player_id"] == pid) &
            (cal["stat"] == stat) &
            (cal["asof_date"] < asof)
        ]
        if sub.empty:
            out.append("unknown")
            continue
        bias = float(sub.iloc[-1]["bias_l20"])
        # threshold: ±0.3 residual units = meaningful bias
        if bias > 0.3:
            out.append("known_over")
        elif bias < -0.3:
            out.append("known_under")
        else:
            out.append("neutral")
    return pd.Series(out, index=scored.index, name="calibration_bias")


def _load_archetypes(scored: pd.DataFrame) -> pd.Series:
    """Per-row archetype label from player_fingerprints."""
    try:
        fp = pd.read_parquet(INTEL_DIR / "player_fingerprints.parquet")
        fp.index = fp.index.astype(int)
        # player_id is index
        pid_to_arch = fp["archetype_name"].to_dict()
    except Exception as e:
        print(f"  [warn] player_fingerprints load failed: {e}")
        return pd.Series(["unknown"] * len(scored), index=scored.index)

    out = []
    for pid in scored["player_id"]:
        out.append(pid_to_arch.get(int(pid), "unknown"))
    return pd.Series(out, index=scored.index, name="archetype")


def _load_gt_exposure(scored: pd.DataFrame) -> pd.Series:
    """Per-row gt_exposure: rolling mean pct_minutes_in_gt over 10 prior games."""
    try:
        gt = pd.read_parquet(INTEL_DIR / "garbage_time_player_aggregates.parquet")
        gt["game_date"] = pd.to_datetime(gt["game_date"])
        gt["player_id"] = gt["player_id"].astype(float).astype(int)
        gt = gt.sort_values("game_date")
    except Exception as e:
        print(f"  [warn] garbage_time_player_aggregates load failed: {e}")
        return pd.Series(["unknown"] * len(scored), index=scored.index)

    out = []
    for _, row in scored.iterrows():
        pid = int(row["player_id"])
        asof = pd.to_datetime(row["date"])
        sub = gt[(gt["player_id"] == pid) & (gt["game_date"] < asof)].tail(10)
        if sub.empty:
            out.append("unknown")
            continue
        mean_gt = sub["pct_minutes_in_gt"].mean()
        if mean_gt > 0.15:
            out.append("high")
        elif mean_gt > 0.05:
            out.append("med")
        else:
            out.append("low")
    return pd.Series(out, index=scored.index, name="gt_exposure")


def _load_blowout_flag(scored: pd.DataFrame) -> pd.Series:
    """Per-row blowout_flag: True if final margin >= 20 (from boxscore JSONs)."""
    # Build a date+team -> margin cache from boxscore files
    bs_dir = ROOT / "data" / "nba"
    bs_files = list(bs_dir.glob("boxscore_*.json"))

    # Cache: (date_str, home_team, away_team) -> margin
    margin_cache: Dict[Tuple[str, str, str], int] = {}
    # Also cache game_id to date
    gid_cache: Dict[str, dict] = {}  # game_id -> {date, home, away, home_score, away_score}

    print(f"  Loading {len(bs_files)} boxscore files for blowout detection ...")
    for fpath in bs_files:
        try:
            d = json.loads(fpath.read_text())
            gid = str(d.get("game_id", ""))
            home = str(d.get("home_team", "")).upper()
            away = str(d.get("away_team", "")).upper()
            hs = d.get("home_score")
            as_ = d.get("away_score")
            if hs is None or as_ is None:
                continue
            margin = abs(int(hs) - int(as_))
            gid_cache[gid] = {"home": home, "away": away, "margin": margin}
        except Exception:
            continue

    # We need game_id -> date mapping. Check player gamelog JSONs for GAME_DATE+MATCHUP
    # Build from scored dates + team info from gamelog files
    # Actually build a simpler: (approx_date, opp) -> margin lookup from gamelog
    # gamelog has MATCHUP like "BOS vs. NYK" or "BOS @ NYK"
    # We'll do a best-effort lookup: for each scored row, scan player's gamelog for the game

    # Preload player gamelogs used in scored rows
    pid_dates_needed = set()
    for _, row in scored.iterrows():
        pid_dates_needed.add((int(row["player_id"]), str(row["date"])))

    # Build (pid, date) -> margin from gamelog game_id + boxscore
    # gamelog has no game_id; use MATCHUP + GAME_DATE -> lookup boxscore

    # Simpler: build (home_team, away_team, date) -> margin
    # Since we don't have dates in boxscores directly, this is hard.
    # Use gamelog MATCHUP as proxy for date-team lookup
    # For blowout_flag, we'll do a weaker heuristic: if actual_value is very high/low
    # vs the line (outlier), flag potential blowout. This is imperfect.
    # Better: use gamelog to get game-level PTS for opponent estimate.

    # Actually: iterate gamelog for each player to find matching game by date
    # gamelog row has GAME_DATE and MATCHUP="BOS vs. NYK" or "BOS @ NYK"
    import re

    gamelog_dir_path = ROOT / "data" / "nba"

    def _parse_matchup(matchup: str):
        """Returns (team, is_home, opp) from MATCHUP string."""
        parts = matchup.strip().split()
        if len(parts) < 3:
            return None, None, None
        team = parts[0].upper()
        vs_or_at = parts[1]
        opp = parts[2].upper()
        is_home = ("vs" in vs_or_at.lower())
        return team, is_home, opp

    # Build gid->date from boxscore: we know ~5482 boxscores cover 2024-25 season
    # We can also infer date from gamelog by matching player_id+game context

    # Simplest workable approach: mark blowout if scored row has a game that's
    # in the gid_cache and margin >= 20. We need (player, date) -> game_id.
    # Load sample gamelog to check if game_id field exists
    sample_gl_files = list(gamelog_dir_path.glob("gamelog_*.json"))
    if sample_gl_files:
        try:
            sample = json.loads(sample_gl_files[0].read_text())
            if isinstance(sample, list) and sample:
                gl_keys = list(sample[0].keys())
            else:
                gl_keys = []
        except Exception:
            gl_keys = []
    else:
        gl_keys = []

    # gamelog keys: ['GAME_DATE', 'MATCHUP', 'PTS', 'REB', 'AST', 'MIN', 'FG3M', 'STL', 'BLK', 'TOV']
    # No GAME_ID in gamelog. Can't directly join to boxscores without it.
    # Alternative: use actual_value vs closing_line spread as proxy for blowout
    # OR: load player gamelog on the exact date, check if it was blowout via PTS swing
    # For now: mark blowout as True if the player's actual was >= 50% above line AND
    # game involved a dominant opp — this is too heuristic.
    # Better approximation: check if scored.actual_value deviates significantly from pred
    # in a direction consistent with garbage time.

    # Final decision: we'll compute a reliable blowout_flag using season + date + team
    # from the boxscore JSON gid -> extract date from game_id
    # NBA game_ids: 0022400061 -> 0 + 02 + 24 (season year) + 00061 (game num)
    # Use game date approximation from game_id is not reliable.
    # We'll note this limitation and mark all blowout_flags as False with unknown
    # for rows where we can't resolve (clear caveat in vault doc).

    # Actually, let's load a couple of gamelog files to find if they have any game_id
    # and if not, skip blowout detection properly
    print(f"  Gamelog keys: {gl_keys} - no GAME_ID present, blowout_flag = False (all rows)")
    return pd.Series([False] * len(scored), index=scored.index, name="blowout_flag")


def _time_of_season(date_str: str) -> str:
    """Bucket date into 4 season periods."""
    try:
        d = datetime.fromisoformat(date_str)
        month = d.month
        # Oct-Nov = early, Dec-Jan = mid, Feb-Mar = late, Apr-May = playoffs
        if month in (10, 11):
            return "early_regular"
        elif month in (12, 1):
            return "mid_regular"
        elif month in (2, 3):
            return "late_regular"
        else:
            return "playoffs"
    except Exception:
        return "unknown"


def _rest_days_bucket(rest: float) -> str:
    if pd.isna(rest):
        return "unknown"
    r = float(rest)
    if r < 1:
        return "0"
    elif r < 2:
        return "1"
    else:
        return "2+"


# ── main orchestration ────────────────────────────────────────────────────────

def build_audit() -> dict:
    print("\n=== INT-82 Retro Bet Audit ===")
    print(f"Build timestamp: {BUILD_TS}")

    # 1. Ledger assembly
    ledger = _load_ledger()
    n_ledger = len(ledger)
    print(f"  Ledger size: {n_ledger}")

    # 2. Score all rows
    scored = _score_rows(ledger)
    n_scored = len(scored)
    print(f"  Scored: {n_scored} / {n_ledger}")

    # 3. Bottom-200 by clv_pp (worst = most negative)
    bottom200 = scored.nsmallest(200, "clv_pp").copy().reset_index(drop=True)
    print(f"  Bottom-200 clv_pp: mean={bottom200.clv_pp.mean():.2f}pp "
          f"median={bottom200.clv_pp.median():.2f}pp "
          f"worst={bottom200.clv_pp.min():.2f}pp")

    # 4. Attribution joins on bottom200
    print("\n  Running attribution joins ...")
    bottom200["cv_coverage_tier"] = _load_cv_coverage(bottom200).values
    bottom200["opp_atlas_density"] = _load_opp_atlas_density(bottom200).values
    bottom200["calibration_bias"] = _load_calibration_bias(bottom200).values
    bottom200["archetype"] = _load_archetypes(bottom200).values
    bottom200["gt_exposure"] = _load_gt_exposure(bottom200).values
    bottom200["blowout_flag"] = _load_blowout_flag(bottom200).values
    bottom200["time_of_season"] = bottom200["date"].apply(_time_of_season)
    bottom200["rest_days"] = "2+"  # default used in _build_asof_row
    bottom200["build_ts"] = BUILD_TS

    # Fill NaN sentinels
    for col in ["cv_coverage_tier", "opp_atlas_density", "calibration_bias",
                "archetype", "gt_exposure", "time_of_season", "rest_days"]:
        bottom200[col] = bottom200[col].fillna("unknown")

    # 5. Save parquet
    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(bottom200, preserve_index=False)
    pq.write_table(table, str(OUT_PARQUET))
    print(f"  Saved parquet: {OUT_PARQUET} ({len(bottom200)} rows)")

    # 6. Chi-square test: archetype distribution
    overall_arch = scored["archetype"].value_counts() if "archetype" in scored.columns else pd.Series(dtype=int)
    # We need to recompute archetypes on full scored set for chi-square baseline
    print("  Computing archetypes on full scored set for chi-square baseline ...")
    full_arch = _load_archetypes(scored)
    scored["archetype"] = full_arch.values
    scored["time_of_season"] = scored["date"].apply(_time_of_season)

    arch_bottom200 = bottom200["archetype"].value_counts()
    arch_all = scored["archetype"].value_counts()

    # Chi-square: observed = bottom200 archetype counts, expected = proportional from overall
    archs = sorted(arch_all.index)
    total_all = n_scored
    total_b200 = 200
    observed = np.array([arch_bottom200.get(a, 0) for a in archs], dtype=float)
    expected_raw = np.array([arch_all.get(a, 0) / total_all * total_b200 for a in archs], dtype=float)
    # Remove zeros in expected to avoid division error
    mask = expected_raw > 0
    obs_masked = observed[mask]
    exp_masked = expected_raw[mask]
    chi2_stat, chi2_pval = scipy_stats.chisquare(obs_masked, f_exp=exp_masked)
    print(f"  Chi-square: stat={chi2_stat:.3f} p={chi2_pval:.4f}")

    # 7. Compute lift ratios for each dimension
    dimensions = ["stat", "cv_coverage_tier", "opp_atlas_density",
                  "calibration_bias", "archetype", "gt_exposure", "time_of_season"]

    def lift_table(col: str, scored_full: pd.DataFrame, b200: pd.DataFrame) -> pd.DataFrame:
        """Compute bottom200_share / overall_share per category."""
        overall_counts = scored_full[col].value_counts(normalize=True)
        b200_counts = b200[col].value_counts(normalize=True)
        all_cats = set(list(overall_counts.index) + list(b200_counts.index))
        rows = []
        for cat in sorted(all_cats):
            ov = overall_counts.get(cat, 1e-9)
            b2 = b200_counts.get(cat, 0.0)
            lift = b2 / max(ov, 1e-9)
            n_b200 = int(b200[col].value_counts().get(cat, 0))
            rows.append({"category": cat, "b200_share": b2, "overall_share": ov,
                         "lift": lift, "n_b200": n_b200})
        return pd.DataFrame(rows).sort_values("lift", ascending=False)

    lift_results: Dict[str, pd.DataFrame] = {}
    for col in dimensions:
        if col in bottom200.columns and col in scored.columns:
            lift_results[col] = lift_table(col, scored, bottom200)

    # 8. Top failure modes by frequency with lift
    failure_modes: List[dict] = []
    for col, df_lift in lift_results.items():
        top = df_lift[df_lift["lift"] > 1.3].head(2)
        for _, r in top.iterrows():
            failure_modes.append({
                "dimension": col,
                "category": r["category"],
                "n_b200": int(r["n_b200"]),
                "lift_ratio": round(float(r["lift"]), 2),
            })
    failure_modes.sort(key=lambda x: (-x["lift_ratio"], -x["n_b200"]))

    # 9. 2D cross-tab: archetype × opp_atlas_density
    cross_tab = (bottom200
                 .groupby(["archetype", "opp_atlas_density"])["clv_pp"]
                 .agg(["mean", "count"])
                 .reset_index()
                 .rename(columns={"mean": "mean_clv_pp", "count": "cell_n"}))
    cross_tab["exploratory"] = cross_tab["cell_n"] < 10

    return {
        "n_ledger": n_ledger,
        "n_scored": n_scored,
        "bottom200": bottom200,
        "scored": scored,
        "chi2_stat": chi2_stat,
        "chi2_pval": chi2_pval,
        "archs": archs,
        "observed": observed.tolist(),
        "expected": expected_raw.tolist(),
        "lift_results": lift_results,
        "failure_modes": failure_modes,
        "cross_tab": cross_tab,
    }


# ── vault doc generation ──────────────────────────────────────────────────────

def write_vault_doc(results: dict) -> None:
    b200 = results["bottom200"]
    scored = results["scored"]
    failure_modes = results["failure_modes"]
    cross_tab = results["cross_tab"]

    lines = []

    # Section 1: Header
    mean_clv = b200["clv_pp"].mean()
    med_clv = b200["clv_pp"].median()
    worst_clv = b200["clv_pp"].min()
    worst_row = b200.loc[b200["clv_pp"].idxmin()]

    lines += [
        "# INT-82 Retro Bet Audit",
        "",
        f"**Build:** {BUILD_TS}  ",
        f"**Status:** DIAGNOSTIC ONLY — no SHIP gate  ",
        f"**CLV definition:** model-edge (pred vs closing_line), not line-movement",
        "",
        "## 1. Cohort Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Ledger rows (canonical) | {results['n_ledger']:,} |",
        f"| Rows scored (model ran) | {results['n_scored']:,} |",
        f"| Bottom-200 mean clv_pp | {mean_clv:.2f}pp |",
        f"| Bottom-200 median clv_pp | {med_clv:.2f}pp |",
        f"| Worst single bet clv_pp | {worst_clv:.2f}pp |",
        f"| Worst bet | {worst_row['player']} {worst_row['stat'].upper()} vs {worst_row['opp']} on {worst_row['date']} |",
        "",
    ]

    # Section 2: Top 5 failure modes
    lines += ["## 2. Top Failure Modes (by lift_ratio)",""]
    lines += ["| Rank | Dimension | Category | n_bottom200 | lift_ratio |",
              "|------|-----------|----------|-------------|------------|"]
    for rank, fm in enumerate(failure_modes[:5], 1):
        lines.append(f"| {rank} | {fm['dimension']} | {fm['category']} | "
                     f"{fm['n_b200']} | {fm['lift_ratio']:.2f}x |")
    lines.append("")
    lines += [
        "lift_ratio = bottom200_share / overall_share. Values >1 are overrepresented in the worst bets.",
        "Values <10 cell N flagged as exploratory.",
        "",
    ]

    # Section 3: Per-dimension breakdown
    lines += ["## 3. Per-Dimension Breakdown", ""]
    for col, df_lift in results["lift_results"].items():
        lines.append(f"### {col}")
        lines.append("")
        lines.append("| Category | n_b200 | b200_share | overall_share | lift |")
        lines.append("|----------|--------|------------|---------------|------|")
        for _, r in df_lift.iterrows():
            flag = " ⚠ exploratory" if int(r["n_b200"]) < 10 else ""
            lines.append(f"| {r['category']} | {int(r['n_b200'])} | "
                         f"{r['b200_share']:.1%} | {r['overall_share']:.1%} | "
                         f"{r['lift']:.2f}x{flag} |")
        lines.append("")

    # Section 4: Chi-square
    lines += ["## 4. Chi-Square Test (Archetype Distribution)", ""]
    lines += [
        f"H0: archetype distribution in bottom-200 matches overall scored distribution.",
        f"",
        f"| Stat | Value |",
        f"|------|-------|",
        f"| chi2 | {results['chi2_stat']:.3f} |",
        f"| p-value | {results['chi2_pval']:.4f} |",
        f"| df | {len([x for x in results['expected'] if x > 0]) - 1} |",
        "",
    ]
    if results["chi2_pval"] < 0.05:
        lines.append("**Significant (p<0.05):** archetype is overrepresented in worst bets — not random.")
    else:
        lines.append("**Not significant (p>=0.05):** archetype distribution in bottom-200 consistent with null hypothesis.")
    lines.append("")

    # Section 5: Worst callouts
    lines += ["## 5. Worst Callouts", ""]

    worst_stat = b200.groupby("stat")["clv_pp"].mean().idxmin()
    worst_stat_val = b200.groupby("stat")["clv_pp"].mean().min()
    lines.append(f"- **Worst stat:** {worst_stat.upper()} (mean clv_pp = {worst_stat_val:.2f}pp in bottom-200)")

    worst_opp_dens = b200.groupby("opp_atlas_density")["clv_pp"].mean().idxmin()
    worst_opp_val = b200.groupby("opp_atlas_density")["clv_pp"].mean().min()
    lines.append(f"- **Worst opp-density tier:** {worst_opp_dens} (mean clv_pp = {worst_opp_val:.2f}pp)")

    worst_arch = b200.groupby("archetype")["clv_pp"].mean().idxmin()
    worst_arch_val = b200.groupby("archetype")["clv_pp"].mean().min()
    lines.append(f"- **Worst archetype:** {worst_arch} (mean clv_pp = {worst_arch_val:.2f}pp)")
    lines.append("")

    # Section 6: 2D cross-tab
    lines += ["## 6. 2D Cross-Tab: Archetype × Opp Atlas Density (mean clv_pp)", ""]
    archs = sorted(b200["archetype"].unique())
    dens = sorted(b200["opp_atlas_density"].unique())
    header_row = "| archetype |" + "".join(f" {d} |" for d in dens)
    sep_row = "|-----------|" + "".join("--------|" for _ in dens)
    lines += [header_row, sep_row]
    ct_lookup = {(r["archetype"], r["opp_atlas_density"]): (r["mean_clv_pp"], r["cell_n"])
                 for _, r in cross_tab.iterrows()}
    for arch in archs:
        cells = []
        for d in dens:
            val = ct_lookup.get((arch, d))
            if val is None:
                cells.append(" — |")
            else:
                mv, cn = val
                flag = "*" if cn < 10 else ""
                cells.append(f" {mv:.1f}{flag} |")
        lines.append(f"| {arch} |" + "".join(cells))
    lines.append("")
    lines.append("\\* = cell N < 10, exploratory only")
    lines.append("")

    # Section 7: Honest risks
    lines += [
        "## 7. Honest Risks",
        "",
        "- **Selection bias:** bottom-200 is a non-random tail sample. Patterns may not generalize to moderate-CLV bets.",
        "- **Correlation not causation:** overrepresentation in bottom-200 does not establish that the dimension caused the prediction failure.",
        "- **Small N:** cells with N<10 flagged. Conclusions from these should be treated as hypothesis-generating only.",
        "- **CLV definition divergence:** this uses model-edge (pred vs closing_line) not true line-movement CLV. A positive model-edge bet can still lose money if the model is miscalibrated.",
        "- **Blowout_flag unavailable:** gamelog files lack GAME_ID; boxscore join could not be completed. All blowout_flag values are False. This dimension omitted from lift analysis.",
        "- **cv_coverage_tier sparse:** coverage gates file has only 635 rows; most rows will land in 'none' tier. Avoid over-interpreting coverage-tier lift ratios.",
        "- **opp_atlas_density sparse:** only 207 rows in opp_normalized_cv; most rows land in 'unknown' tertile.",
        "",
    ]

    # Section 8: NO_SHIP + next-build candidates
    lines += [
        "## 8. NO_SHIP — Diagnostic Only",
        "",
        "This audit is diagnostic. No model change is recommended directly from these findings.",
        "",
        "**3 concrete next-build candidates:**",
        "",
    ]

    # Derive dynamically from top failure modes
    candidates = []
    top_fm = failure_modes[:3]
    for fm in top_fm:
        if fm["dimension"] == "stat":
            candidates.append(
                f"- **{fm['category'].upper()} model recalibration:** "
                f"{fm['category'].upper()} is overrepresented in worst bets (lift={fm['lift_ratio']:.2f}x, n={fm['n_b200']}). "
                f"Apply isotonic recalibration or quantile shift specifically for {fm['category'].upper()} q50 head."
            )
        elif fm["dimension"] == "calibration_bias":
            candidates.append(
                f"- **Calibration bias filter:** '{fm['category']}' bets are lift={fm['lift_ratio']:.2f}x in worst-200. "
                f"Add a pre-bet gate: skip bets where bias_l20 exceeds ±0.3 for the (player_id, stat) pair."
            )
        elif fm["dimension"] == "archetype":
            candidates.append(
                f"- **{fm['category']} archetype-specific model:** "
                f"Archetype '{fm['category']}' has lift={fm['lift_ratio']:.2f}x in worst bets. "
                f"Train a separate XGBoost leaf for this archetype or add archetype interaction features."
            )
        elif fm["dimension"] == "gt_exposure":
            candidates.append(
                f"- **Garbage time filter ({fm['category']} gt_exposure):** "
                f"gt_exposure='{fm['category']}' has lift={fm['lift_ratio']:.2f}x in worst-200. "
                f"Gate bets where rolling pct_minutes_in_gt > 0.15 (10-game window)."
            )
        elif fm["dimension"] == "opp_atlas_density":
            candidates.append(
                f"- **Opp density penalty ({fm['category']} tier):** "
                f"opp_atlas_density='{fm['category']}' has lift={fm['lift_ratio']:.2f}x. "
                f"Apply a 10pp clv_pp penalty for bets with low opp CV data density."
            )
        elif fm["dimension"] == "time_of_season":
            candidates.append(
                f"- **{fm['category']} season segment filter:** "
                f"'{fm['category']}' period has lift={fm['lift_ratio']:.2f}x in worst bets. "
                f"Reduce stake sizing or raise edge threshold during this period."
            )
        else:
            candidates.append(
                f"- **{fm['dimension']}={fm['category']} gate:** lift={fm['lift_ratio']:.2f}x in worst-200 (n={fm['n_b200']}). "
                f"Add as a pre-bet filter or sizing multiplier."
            )
    # Pad to at least 3
    while len(candidates) < 3:
        candidates.append(
            "- **Expand CV coverage:** Sparse cv_coverage_tier (only 635 gate rows) limits attribution resolution. "
            "Processing more games through the CV pipeline would enable this dimension as a real bet filter."
        )
    for c in candidates[:3]:
        lines.append(c)
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated: {BUILD_TS} | INT-82 | model-edge CLV, not line-movement*")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved vault doc: {OUT_MD}")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    results = build_audit()
    write_vault_doc(results)

    # Terminal summary
    b200 = results["bottom200"]
    fm = results["failure_modes"]
    print("\n=== INT-82 Summary ===")
    print(f"Ledger: {results['n_ledger']:,}  |  Scored: {results['n_scored']:,}")
    print(f"Bottom-200: mean clv_pp={b200.clv_pp.mean():.2f}pp "
          f"median={b200.clv_pp.median():.2f}pp "
          f"worst={b200.clv_pp.min():.2f}pp")
    print("\nTop failure modes:")
    for i, f in enumerate(fm[:5], 1):
        print(f"  {i}. {f['dimension']}={f['category']}  n={f['n_b200']}  lift={f['lift_ratio']:.2f}x")
    print(f"\nChi-square: stat={results['chi2_stat']:.3f}  p={results['chi2_pval']:.4f}")

    worst_stat = b200.groupby("stat")["clv_pp"].mean().idxmin()
    worst_arch = b200.groupby("archetype")["clv_pp"].mean().idxmin()
    worst_opp = b200.groupby("opp_atlas_density")["clv_pp"].mean().idxmin()
    print(f"\nWorst stat: {worst_stat.upper()}")
    print(f"Worst archetype: {worst_arch}")
    print(f"Worst opp_density: {worst_opp}")
    print(f"\nOutputs:")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_MD}")


if __name__ == "__main__":
    main()

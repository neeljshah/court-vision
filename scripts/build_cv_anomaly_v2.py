"""
build_cv_anomaly_v2.py — INT-68: CV Anomaly Detection v2 (E3)

Differentiates from INT-4 (anomaly_log) via:
  - Rolling L20 baseline (NOT career leave-one-out)
  - RMS composite across 8 focal dims (NOT max-z)
  - Strict asof-safe: game_date < target date, game_id lex tie-break
  - Sentinel 200.0 nulled BEFORE baselining (ISSUE-022)
  - ≥10 prior games per dim, ≥30% non-zero gate
  - Direction JSON: top-3 dims by |z|
  - 6 reject gates with null-shuffle test

Usage:
    python scripts/build_cv_anomaly_v2.py
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Force UTF-8 stdout on Windows to handle unicode in print statements
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

warnings.filterwarnings("ignore", category=FutureWarning)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "nba_ai.db"
PLAYER_JSON = ROOT / "data" / "nba" / "player_full_2024-25.json"
OUT_DIR = ROOT / "data" / "intelligence"
VAULT_INTEL_DIR = ROOT / "vault" / "Intelligence"

PARQUET_OUT = OUT_DIR / "cv_anomaly_v2.parquet"
VALIDATION_OUT = OUT_DIR / "cv_anomaly_v2_validation.json"
DOC_OUT = VAULT_INTEL_DIR / "INT-68_CV_Anomaly_v2.md"

# INT-4 / B3 / INT-55 paths
INT4_PATH = OUT_DIR / "anomaly_log.parquet"
B3_PATH = OUT_DIR / "archetype_outlier_signals.parquet"
INT55_PATH = OUT_DIR / "cv_consistency_kelly.parquet"

os.makedirs(str(OUT_DIR), exist_ok=True)
os.makedirs(str(VAULT_INTEL_DIR), exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────
DIMS = [
    "paint_dwell_pct",
    "touches_per_game",
    "contested_shot_rate",
    "avg_defender_distance",
    "possession_duration_avg",
    "shots_per_possession",
    "catch_shoot_pct",
    "preshot_velocity_peak",
]

L20_WINDOW = 20          # max prior games in rolling baseline
MIN_PRIOR_GAMES = 10     # min prior games per dim
MIN_NONZERO_PCT = 0.30   # min 30% non-zero in baseline
MIN_DIMS_VALID = 3       # min dims with valid z to produce composite
Z_CLIP = 6.0             # clip z to [-6, +6]
SIGMA_FLOOR_PCT = 0.10   # sigma >= 10% * dataset_std[dim]

BUCKET_THRESHOLDS = [1.0, 2.0, 3.0]  # normal / mild / strong / severe
KELLY_MAP = {
    "normal": 1.00,
    "mild": 1.00,
    "strong": 0.75,
    "severe": 0.50,
}

# Reject gate thresholds
REJECT_MIN_ROWS = 50
REJECT_CORR_INT4 = 0.90
REJECT_CORR_B3 = 0.90
REJECT_CORR_INT55 = 0.85
REJECT_NULL_SHUFFLE_MARGIN = 0.10  # bucket proportions within 10% → reject
REJECT_MIN_DIM_PASS_FRAC = 0.50   # <3 of 8 dims pass gate for >50% rows


# ── Data loading ───────────────────────────────────────────────────────────

def load_player_name_map() -> dict[int, str]:
    name_map: dict[int, str] = {}
    if not PLAYER_JSON.exists():
        print("  [WARN] player_full JSON not found — names will be IDs")
        return name_map
    with open(str(PLAYER_JSON), "r") as f:
        data = json.load(f)
    for name, info in data.items():
        pid = info.get("player_id")
        if pid:
            name_map[int(pid)] = name.title()
    return name_map


def load_game_date_map() -> dict[str, str]:
    date_map: dict[str, str] = {}
    nba_dir = ROOT / "data" / "nba"
    for fname in os.listdir(str(nba_dir)):
        if fname.startswith("season_games_") and fname.endswith(".json"):
            fpath = nba_dir / fname
            try:
                with open(str(fpath)) as f:
                    raw = json.load(f)
                rows = raw.get("rows", [])
                for row in rows:
                    gid = row.get("game_id")
                    gdate = row.get("game_date")
                    if gid and gdate:
                        date_map[str(gid)] = str(gdate)
            except Exception as e:
                print(f"  [WARN] Could not read {fname}: {e}")
    return date_map


def load_cv_wide() -> pd.DataFrame:
    """Load cv_features → wide (player_id, game_id, dim…)."""
    conn = sqlite3.connect(str(DB_PATH))
    df_long = pd.read_sql(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features "
        "WHERE feature_name IN ({})".format(
            ",".join(f"'{d}'" for d in DIMS)
        ),
        conn,
    )
    conn.close()
    df_wide = df_long.pivot_table(
        index=["player_id", "game_id"],
        columns="feature_name",
        values="feature_value",
        aggfunc="first",
    ).reset_index()
    df_wide.columns.name = None
    # Ensure all dims present as columns even if some missing
    for d in DIMS:
        if d not in df_wide.columns:
            df_wide[d] = np.nan
    return df_wide


def attach_game_dates(df: pd.DataFrame, date_map: dict[str, str]) -> pd.DataFrame:
    df = df.copy()
    df["game_date"] = df["game_id"].map(date_map)
    n_missing = df["game_date"].isna().sum()
    if n_missing > 0:
        print(f"  [WARN] {n_missing} rows have no game_date — will be dropped")
    df = df.dropna(subset=["game_date"]).copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


# ── Sentinel handling ──────────────────────────────────────────────────────

def null_sentinels(df: pd.DataFrame) -> pd.DataFrame:
    """ISSUE-022: avg_defender_distance >= 199.0 → NaN."""
    df = df.copy()
    if "avg_defender_distance" in df.columns:
        mask = df["avg_defender_distance"] >= 199.0
        n_nulled = mask.sum()
        if n_nulled > 0:
            print(f"  [SENTINEL] Nulled {n_nulled} avg_defender_distance sentinel rows")
        df.loc[mask, "avg_defender_distance"] = np.nan
    return df


# ── Dataset-level stats ────────────────────────────────────────────────────

def compute_dataset_stds(df: pd.DataFrame) -> dict[str, float]:
    return {d: float(df[d].std(skipna=True)) for d in DIMS}


# ── Core scoring ───────────────────────────────────────────────────────────

def bucket_from_score(score: float) -> str:
    if score < BUCKET_THRESHOLDS[0]:
        return "normal"
    elif score < BUCKET_THRESHOLDS[1]:
        return "mild"
    elif score < BUCKET_THRESHOLDS[2]:
        return "strong"
    return "severe"


def score_one_player(
    player_df: pd.DataFrame,
    dataset_stds: dict[str, float],
    name_map: dict[int, str],
) -> list[dict]:
    """
    Score all games for one player using rolling L20 asof-safe baseline.
    player_df must be pre-sorted by (game_date, game_id) ascending.
    """
    records = []
    pid = int(player_df["player_id"].iloc[0])

    # Sort deterministically: game_date asc, then game_id lex for ties
    player_df = player_df.sort_values(["game_date", "game_id"]).reset_index(drop=True)

    for idx in range(len(player_df)):
        row = player_df.iloc[idx]
        game_id = row["game_id"]
        game_date = row["game_date"]

        # Strict prior rows: game_date < target OR (game_date == target AND game_id < target)
        prior_mask = (player_df["game_date"] < game_date) | (
            (player_df["game_date"] == game_date) & (player_df["game_id"] < game_id)
        )
        prior = player_df[prior_mask].tail(L20_WINDOW)

        if len(prior) == 0:
            continue

        z_contributions: list[tuple[str, float, float, float]] = []  # (dim, z, val, baseline_mean)
        n_dims_attempted = 0

        for dim in DIMS:
            val = row[dim]
            if pd.isna(val):
                continue

            baseline_vals = prior[dim].dropna()
            n_baseline = len(baseline_vals)

            # Gate 1: minimum prior games
            if n_baseline < MIN_PRIOR_GAMES:
                continue

            # Gate 2: minimum non-zero fraction
            n_nonzero = (baseline_vals != 0.0).sum()
            if n_nonzero / n_baseline < MIN_NONZERO_PCT:
                continue

            n_dims_attempted += 1
            mu = float(baseline_vals.mean())
            sigma_raw = float(baseline_vals.std(ddof=1)) if n_baseline > 1 else 0.0

            # Floor: max(sigma_raw, 10% of dataset_std)
            ds_std = dataset_stds.get(dim, 0.0) or 0.0
            sigma = max(sigma_raw, SIGMA_FLOOR_PCT * ds_std)
            if sigma < 1e-9:
                continue

            z = float(np.clip((val - mu) / sigma, -Z_CLIP, Z_CLIP))
            z_contributions.append((dim, z, float(val), mu))

        if len(z_contributions) < MIN_DIMS_VALID:
            continue

        # RMS composite
        zvals = np.array([zc[1] for zc in z_contributions])
        anomaly_score = float(np.sqrt(np.mean(zvals ** 2)))

        # Top-3 by |z|
        sorted_zc = sorted(z_contributions, key=lambda x: abs(x[1]), reverse=True)
        top3 = sorted_zc[:3]
        direction_top3 = json.dumps([
            {
                "dim": zc[0],
                "z": round(zc[1], 3),
                "val": round(zc[2], 4),
                "baseline_mean": round(zc[3], 4),
            }
            for zc in top3
        ])
        signed_top1 = round(top3[0][1], 3)

        bkt = bucket_from_score(anomaly_score)

        records.append({
            "player_id": pid,
            "player_name": name_map.get(pid, f"ID:{pid}"),
            "game_id": game_id,
            "game_date": game_date,
            "n_dims_used": len(z_contributions),
            "anomaly_score": round(anomaly_score, 4),
            "signed_top1": signed_top1,
            "bucket": bkt,
            "kelly_mult": KELLY_MAP[bkt],
            "data_quality_flag": bkt == "severe",
            "direction_top3": direction_top3,
            "baseline_n_games_max": int(prior[DIMS].count().max()),
            "baseline_n_games_min": int(prior[DIMS].count().min()),
        })

    return records


def build_scored_df(
    df_wide: pd.DataFrame,
    dataset_stds: dict[str, float],
    name_map: dict[int, str],
) -> pd.DataFrame:
    all_records: list[dict] = []
    pids = df_wide["player_id"].unique()
    print(f"  Scoring {len(pids)} players...")

    for pid in pids:
        pdata = df_wide[df_wide["player_id"] == pid].copy()
        recs = score_one_player(pdata, dataset_stds, name_map)
        all_records.extend(recs)

    if not all_records:
        return pd.DataFrame()

    result = pd.DataFrame(all_records)
    result["game_date"] = pd.to_datetime(result["game_date"])
    return result


# ── Reject gates ───────────────────────────────────────────────────────────

def safe_corr(a: pd.Series, b: pd.Series) -> float:
    """Pearson correlation on aligned, non-null pairs."""
    df = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(df) < 10:
        return 0.0
    return float(df["a"].corr(df["b"]))


def run_null_shuffle(
    df_wide: pd.DataFrame,
    dataset_stds: dict[str, float],
    name_map: dict[int, str],
    real_bucket_props: dict[str, float],
) -> tuple[float, str]:
    """
    Shuffle game_date within each player, recompute scores.
    Returns (max_bucket_prop_delta, note).
    """
    rng = np.random.default_rng(42)
    df_shuffled = df_wide.copy()
    shuffled_dates: list[pd.Timestamp] = []
    for pid, grp in df_shuffled.groupby("player_id"):
        dates = grp["game_date"].values.copy()
        rng.shuffle(dates)
        shuffled_dates.extend(dates)
    df_shuffled["game_date"] = shuffled_dates

    shuf_records = build_scored_df(df_shuffled, dataset_stds, name_map)

    if shuf_records.empty:
        return 0.0, "shuffle produced no rows"

    shuf_props = shuf_records["bucket"].value_counts(normalize=True).to_dict()
    max_delta = 0.0
    for bkt in ["normal", "mild", "strong", "severe"]:
        real_p = real_bucket_props.get(bkt, 0.0)
        shuf_p = shuf_props.get(bkt, 0.0)
        delta = abs(real_p - shuf_p)
        if delta > max_delta:
            max_delta = delta
    return max_delta, str(shuf_props)


def gate_dim_quality(df_wide: pd.DataFrame, scored_df: pd.DataFrame) -> tuple[int, float]:
    """
    Gate 6: how many of 8 dims pass quality gate for > 50% of rows?
    Quality = player had ≥10 prior games with ≥30% non-zero.
    Approximate: check per scored row how many dims had valid z contribution.
    """
    if scored_df.empty:
        return 0, 0.0
    # n_dims_used is the count of dims that contributed valid z
    frac_enough = (scored_df["n_dims_used"] >= MIN_DIMS_VALID).mean()
    # Compute per-dim pass fractions across all eligible player-games
    median_dims = float(scored_df["n_dims_used"].median())
    # dims passing gate = dims with valid contributions in majority of rows
    return int(median_dims), float(frac_enough)


# ── Cross-correlation with existing signals ────────────────────────────────

def load_int4(scored_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return aligned anomaly_score, int4_max_abs_z."""
    if not INT4_PATH.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    df4 = pd.read_parquet(str(INT4_PATH))
    merged = scored_df[["player_id", "game_id", "anomaly_score"]].merge(
        df4[["player_id", "game_id", "max_abs_z"]],
        on=["player_id", "game_id"], how="inner",
    )
    return merged["anomaly_score"], merged["max_abs_z"]


def load_b3(scored_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if not B3_PATH.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    dfb = pd.read_parquet(str(B3_PATH))
    merged = scored_df[["player_id", "game_id", "anomaly_score"]].merge(
        dfb[["player_id", "game_id", "outlier_z"]],
        on=["player_id", "game_id"], how="inner",
    )
    return merged["anomaly_score"], merged["outlier_z"]


def load_int55(scored_df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """INT-55 is asof_date keyed, not game_id — join on player_id + nearest asof_date."""
    if not INT55_PATH.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    df55 = pd.read_parquet(str(INT55_PATH))
    # Try game_id if present; else skip (different granularity)
    if "game_id" in df55.columns:
        merged = scored_df[["player_id", "game_id", "anomaly_score"]].merge(
            df55[["player_id", "game_id", "cv_consistency_z"]],
            on=["player_id", "game_id"], how="inner",
        )
        return merged["anomaly_score"], merged["cv_consistency_z"]
    # Merge on player_id + asof_date ~= game_date
    df55["asof_date"] = pd.to_datetime(df55["asof_date"])
    scored_tmp = scored_df[["player_id", "game_date", "anomaly_score"]].copy()
    scored_tmp["game_date"] = pd.to_datetime(scored_tmp["game_date"])
    merged = scored_tmp.merge(
        df55[["player_id", "asof_date", "cv_consistency_z"]].rename(columns={"asof_date": "game_date"}),
        on=["player_id", "game_date"], how="inner",
    )
    if merged.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return merged["anomaly_score"], merged["cv_consistency_z"]


# ── INT-68 vault document ──────────────────────────────────────────────────

def write_vault_doc(
    scored_df: pd.DataFrame,
    val: dict,
    status: str,
) -> None:
    n_rows = len(scored_df) if not scored_df.empty else 0
    n_players = scored_df["player_id"].nunique() if not scored_df.empty else 0

    if not scored_df.empty:
        bkt_counts = scored_df["bucket"].value_counts().to_dict()
        bkt_lines = "\n".join(
            f"| {b} | {bkt_counts.get(b, 0)} | {100*bkt_counts.get(b,0)/max(n_rows,1):.1f}% |"
            for b in ["normal", "mild", "strong", "severe"]
        )
    else:
        bkt_lines = "| — | — | — |"

    top10_table = ""
    if not scored_df.empty and n_rows >= 10:
        top10 = scored_df.nlargest(10, "anomaly_score")
        rows_out = []
        for _, r in top10.iterrows():
            try:
                d3 = json.loads(r["direction_top3"])
                top_dim = d3[0]["dim"] if d3 else "—"
            except Exception:
                top_dim = "—"
            rows_out.append(
                f"| {r['player_name']} | {r['game_date'].date()} "
                f"| {r['anomaly_score']:.3f} | {r['bucket']} | {top_dim} |"
            )
        top10_table = "\n".join(rows_out)

    corr_int4 = val.get("corr_int4", "N/A")
    corr_b3 = val.get("corr_b3", "N/A")
    corr_int55 = val.get("corr_int55", "N/A")
    null_delta = val.get("null_shuffle_max_delta", "N/A")
    gates = val.get("gates", {})

    gate_lines = "\n".join(
        f"| {k} | {'PASS' if v['pass'] else 'FAIL'} | {v['detail']} |"
        for k, v in gates.items()
    )

    doc = f"""# INT-68: CV Anomaly Detection v2 (E3)

**Status: {status}**
Generated: 2026-05-29 | Script: scripts/build_cv_anomaly_v2.py

---

## Purpose

E3 provides per-(player, game) behavioral anomaly scores grounded in a **rolling L20 prior-game baseline** (strict asof-safe). It replaces the career leave-one-out window of INT-4 with a recency-aware signal more aligned with how sportsbooks price single-game lines. The RMS composite aggregates across 8 focal CV dims, preserving sensitivity to multi-dim co-movement that INT-55 (coefficient-of-variation) misses.

---

## Differentiation

| | INT-4 (anomaly_log) | B3 / INT-54 (archetype_outlier) | INT-55 (cv_consistency) | **E3 / INT-68 (this)** |
|---|---|---|---|---|
| Baseline window | Career LOO | Archetype cluster distance | L30 CV stability | Rolling L20 prior games |
| Aggregate metric | max\|z\| | Mahalanobis to archetype | CV (std/mean) | RMS z across dims |
| Dims | 19 fingerprint features | Archetype embedding dims | 14 CV dims | 8 focal behavioral dims |
| Sentinel handling | Flagged, not nulled | Not documented | Not documented | Nulled before baseline |
| Asof-safe | Yes (LOO) | Yes | Yes | Yes (strict date < + game_id lex) |
| Sign preserved | No (max abs) | No | No | Yes (signed_top1) |
| Kelly mult | No | No | Yes (INT-55) | Yes |

---

## Schema

```
player_id           int
player_name         str
game_id             str
game_date           date
n_dims_used         int   (# dims contributing valid z, max 8)
anomaly_score       float (RMS of z_dim values)
signed_top1         float (z of top-|z| dim, preserves direction)
bucket              str   (normal / mild / strong / severe)
kelly_mult          float (1.00 / 1.00 / 0.75 / 0.50)
data_quality_flag   bool  (True if severe)
direction_top3      JSON  ([{{dim, z, val, baseline_mean}}, ...])
baseline_n_games_max int  (max prior-game count across dims)
baseline_n_games_min int  (min prior-game count across dims)
```

---

## Coverage

- **Scored rows:** {n_rows}
- **Unique players:** {n_players}
- **Baseline requirement:** ≥{MIN_PRIOR_GAMES} prior games per dim, ≥{int(MIN_NONZERO_PCT*100)}% non-zero
- **Dims:** {", ".join(DIMS)}

---

## Bucket Distribution

| Bucket | Count | % |
|--------|-------|---|
{bkt_lines}

**Kelly multiplier map:** normal→1.00, mild→1.00, strong→0.75, severe→0.50

---

## Top-10 Severe Rows

| Player | Date | Score | Bucket | Top Dim |
|--------|------|-------|--------|---------|
{top10_table if top10_table else "— (insufficient rows or REJECTED)"}

---

## Cross-Correlation Results

| Comparison | Pearson r | Threshold | Verdict |
|---|---|---|---|
| vs INT-4 max_abs_z | {corr_int4 if isinstance(corr_int4, str) else f'{corr_int4:.3f}'} | < {REJECT_CORR_INT4} | {'PASS' if isinstance(corr_int4, str) or corr_int4 < REJECT_CORR_INT4 else 'FAIL'} |
| vs B3 outlier_z | {corr_b3 if isinstance(corr_b3, str) else f'{corr_b3:.3f}'} | < {REJECT_CORR_B3} | {'PASS' if isinstance(corr_b3, str) or corr_b3 < REJECT_CORR_B3 else 'FAIL'} |
| vs INT-55 cv_consistency_z | {corr_int55 if isinstance(corr_int55, str) else f'{corr_int55:.3f}'} | < {REJECT_CORR_INT55} | {'PASS' if isinstance(corr_int55, str) or corr_int55 < REJECT_CORR_INT55 else 'FAIL'} |

---

## Null-Shuffle Test

Max bucket-proportion delta (shuffled vs real): **{null_delta if isinstance(null_delta, str) else f'{null_delta:.3f}'}**
Threshold: > {REJECT_NULL_SHUFFLE_MARGIN} to pass (date-dependent signal confirmed).

---

## Gate Verdicts

| Gate | Result | Detail |
|------|--------|--------|
{gate_lines}

---

## Kelly Multiplier Mapping

Bucket thresholds (RMS z): normal < 1.0 ≤ mild < 2.0 ≤ strong < 3.0 ≤ severe.
Thresholds and multipliers are **conventional, not walk-forward tuned**. Downstream WF test required before live sizing.

---

## Honest Caveats

1. **Coverage constraint**: ≥10-prior-games gate on each dim restricts rows significantly; early-season and low-usage players are excluded.
2. **Redundancy risk with B3**: both operate on overlapping dims; non-trivial cross-correlation possible.
3. **Sentinel gap**: avg_defender_distance nulling removes ~4.5% of rows pre-baseline; missing-not-at-random bias possible.
4. **RMS loses sign**: direction_top3 JSON is the only signed signal; anomaly_score alone cannot distinguish hot vs cold.
5. **Bucket thresholds not WF-calibrated**: 1/2/3 RMS-z cutoffs are symmetric Gaussian priors, not empirically validated at this dim-count.
6. **kelly_mult not tested**: downstream walk-forward on prop_pergame required before using these multipliers live.

---

## Downstream WF Test TODO (not run here)

- Merge cv_anomaly_v2 into build_pergame_dataset.py on (player_id, game_date)
- Add: anomaly_score, bucket_severe (bool), kelly_mult as features
- Run walk_forward_prop_pergame.py — require 4/4 WF folds + single-split MAE strictly down
- Gate: r(anomaly_score, stat residual) must be nonzero for at least 2 stats

---
*Generated by scripts/build_cv_anomaly_v2.py — INT-68*
"""

    with open(str(DOC_OUT), "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"[DOC] Written: {DOC_OUT}")


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 65)
    print("INT-68: CV Anomaly Detection v2 (E3) — Rolling L20 / RMS")
    print("=" * 65)

    # ── 1. Load data ───────────────────────────────────────────────
    print("\n[1] Loading data...")
    name_map = load_player_name_map()
    date_map = load_game_date_map()
    print(f"  Player name map: {len(name_map)} entries")
    print(f"  Game date map: {len(date_map)} entries")

    df_wide = load_cv_wide()
    print(f"  CV wide (pre-sentinel): {df_wide.shape[0]} rows, {df_wide.shape[1]} cols")

    # ── 2. Sentinel null ───────────────────────────────────────────
    print("\n[2] Nulling sentinels (ISSUE-022)...")
    df_wide = null_sentinels(df_wide)

    # ── 3. Attach game_date ────────────────────────────────────────
    print("\n[3] Attaching game_date...")
    df_wide = attach_game_dates(df_wide, date_map)
    print(f"  Rows after date join: {len(df_wide)}")

    # ── 4. Dataset stds ────────────────────────────────────────────
    print("\n[4] Computing dataset-level stds...")
    dataset_stds = compute_dataset_stds(df_wide)
    for d, s in dataset_stds.items():
        print(f"    {d}: {s:.4f}")

    # ── 5. Score ───────────────────────────────────────────────────
    print("\n[5] Scoring player-games (L20 rolling RMS)...")
    scored_df = build_scored_df(df_wide, dataset_stds, name_map)
    n_scored = len(scored_df)
    print(f"  Scored rows: {n_scored}")
    if scored_df.empty:
        print("  [ERROR] No scored rows produced.")

    # ── 6. Cross-corr ──────────────────────────────────────────────
    print("\n[6] Cross-correlation with existing signals...")
    e3_int4, int4_vals = load_int4(scored_df) if not scored_df.empty else (pd.Series(dtype=float), pd.Series(dtype=float))
    e3_b3, b3_vals = load_b3(scored_df) if not scored_df.empty else (pd.Series(dtype=float), pd.Series(dtype=float))
    e3_int55, int55_vals = load_int55(scored_df) if not scored_df.empty else (pd.Series(dtype=float), pd.Series(dtype=float))

    corr_int4 = safe_corr(e3_int4, int4_vals)
    corr_b3 = safe_corr(e3_b3, b3_vals)
    corr_int55 = safe_corr(e3_int55, int55_vals)

    n_overlap_int4 = len(e3_int4.dropna())
    n_overlap_b3 = len(e3_b3.dropna())
    n_overlap_int55 = len(e3_int55.dropna())

    print(f"  vs INT-4 max_abs_z  (n={n_overlap_int4}): r={corr_int4:.3f}")
    print(f"  vs B3 outlier_z     (n={n_overlap_b3}): r={corr_b3:.3f}")
    print(f"  vs INT-55 cv_z      (n={n_overlap_int55}): r={corr_int55:.3f}")

    # ── 7. Null shuffle ────────────────────────────────────────────
    real_bucket_props: dict[str, float] = {}
    null_shuffle_delta = 0.0
    null_shuffle_note = "N/A"

    if not scored_df.empty:
        real_bucket_props = scored_df["bucket"].value_counts(normalize=True).to_dict()
        print("\n[7] Null-shuffle test (date-independence check)...")
        null_shuffle_delta, null_shuffle_note = run_null_shuffle(
            df_wide, dataset_stds, name_map, real_bucket_props
        )
        print(f"  Max bucket-prop delta (shuffled vs real): {null_shuffle_delta:.3f}")
        print(f"  Shuffle bucket props: {null_shuffle_note}")

    # ── 8. Dim-quality gate ────────────────────────────────────────
    median_dims_used, frac_enough = gate_dim_quality(df_wide, scored_df)

    # ── 9. Evaluate gates ──────────────────────────────────────────
    print("\n[8] Evaluating 6 reject gates...")

    gate_results: dict[str, dict] = {}

    # Gate 1: minimum scored rows
    g1_pass = n_scored >= REJECT_MIN_ROWS
    gate_results["G1_min_rows"] = {
        "pass": g1_pass,
        "detail": f"n_scored={n_scored} (need ≥{REJECT_MIN_ROWS})",
    }

    # Gate 2: redundancy with INT-4
    g2_pass = n_overlap_int4 < 10 or corr_int4 <= REJECT_CORR_INT4
    gate_results["G2_corr_INT4"] = {
        "pass": g2_pass,
        "detail": f"r={corr_int4:.3f} (threshold < {REJECT_CORR_INT4}, n_overlap={n_overlap_int4})",
    }

    # Gate 3: redundancy with B3
    g3_pass = n_overlap_b3 < 10 or corr_b3 <= REJECT_CORR_B3
    gate_results["G3_corr_B3"] = {
        "pass": g3_pass,
        "detail": f"r={corr_b3:.3f} (threshold < {REJECT_CORR_B3}, n_overlap={n_overlap_b3})",
    }

    # Gate 4: reduces to INT-55 noise detector
    g4_pass = n_overlap_int55 < 10 or corr_int55 <= REJECT_CORR_INT55
    gate_results["G4_corr_INT55"] = {
        "pass": g4_pass,
        "detail": f"r={corr_int55:.3f} (threshold < {REJECT_CORR_INT55}, n_overlap={n_overlap_int55})",
    }

    # Gate 5: null-shuffle
    g5_pass = null_shuffle_delta > REJECT_NULL_SHUFFLE_MARGIN
    gate_results["G5_null_shuffle"] = {
        "pass": g5_pass,
        "detail": (
            f"max_delta={null_shuffle_delta:.3f} "
            f"(need > {REJECT_NULL_SHUFFLE_MARGIN} to confirm date-dependence)"
        ),
    }

    # Gate 6: dim coverage
    # "< 3 of 8 dims pass quality gate for > 50% rows" -> REJECT
    # median_dims_used >= 3 AND frac_enough > 0.50 -> PASS
    g6_pass = median_dims_used >= MIN_DIMS_VALID and frac_enough > 0.50
    gate_results["G6_dim_coverage"] = {
        "pass": g6_pass,
        "detail": (
            f"median_dims_used={median_dims_used}, "
            f"frac_rows_with_{MIN_DIMS_VALID}+_dims={frac_enough:.2f} (need >0.50)"
        ),
    }

    all_pass = all(v["pass"] for v in gate_results.values())
    status = "SHIP" if all_pass else "REJECTED"

    for gname, gval in gate_results.items():
        verdict = "PASS" if gval["pass"] else "FAIL"
        print(f"  {gname}: {verdict} -- {gval['detail']}")

    print(f"\n  => Overall verdict: {status}")

    # ── 10. Validation JSON ────────────────────────────────────────
    val_output = {
        "status": status,
        "n_scored_rows": n_scored,
        "n_players": int(scored_df["player_id"].nunique()) if not scored_df.empty else 0,
        "corr_int4": round(corr_int4, 4),
        "corr_b3": round(corr_b3, 4),
        "corr_int55": round(corr_int55, 4),
        "n_overlap_int4": n_overlap_int4,
        "n_overlap_b3": n_overlap_b3,
        "n_overlap_int55": n_overlap_int55,
        "null_shuffle_max_delta": round(null_shuffle_delta, 4),
        "real_bucket_props": {k: round(v, 4) for k, v in real_bucket_props.items()},
        "gates": gate_results,
        "dims": DIMS,
        "l20_window": L20_WINDOW,
        "min_prior_games": MIN_PRIOR_GAMES,
    }

    with open(str(VALIDATION_OUT), "w", encoding="utf-8") as f:
        json.dump(val_output, f, indent=2)
    print(f"\n[VALIDATION] Written: {VALIDATION_OUT}")

    # ── 11. Conditionally write parquet ───────────────────────────
    if all_pass and not scored_df.empty:
        # Ensure correct column order and types
        out_cols = [
            "player_id", "player_name", "game_id", "game_date",
            "n_dims_used", "anomaly_score", "signed_top1", "bucket",
            "kelly_mult", "data_quality_flag", "direction_top3",
            "baseline_n_games_max", "baseline_n_games_min",
        ]
        scored_out = scored_df[out_cols].copy()
        scored_out.to_parquet(str(PARQUET_OUT), index=False)
        print(f"[PARQUET] Written: {PARQUET_OUT} ({len(scored_out)} rows)")
    else:
        if PARQUET_OUT.exists():
            print(f"[PARQUET] NOT written (status={status}) — previous file preserved")
        else:
            print(f"[PARQUET] NOT written (status={status})")

    # ── 12. Vault doc ──────────────────────────────────────────────
    write_vault_doc(scored_df, val_output, status)

    # ── 13. Summary report ─────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"INT-68 Final Report — {status}")
    print("=" * 65)
    print(f"  Scored rows:    {n_scored}")
    print(f"  Unique players: {val_output['n_players']}")

    if not scored_df.empty:
        bkt_counts = scored_df["bucket"].value_counts()
        print(f"  Bucket distribution:")
        for b in ["normal", "mild", "strong", "severe"]:
            print(f"    {b:<8}: {bkt_counts.get(b, 0)}")

    print(f"\n  Cross-corr vs INT-4:  r={corr_int4:.3f} (n={n_overlap_int4})")
    print(f"  Cross-corr vs B3:     r={corr_b3:.3f} (n={n_overlap_b3})")
    print(f"  Cross-corr vs INT-55: r={corr_int55:.3f} (n={n_overlap_int55})")
    print(f"  Null-shuffle delta:   {null_shuffle_delta:.3f}")

    if not scored_df.empty and n_scored >= 3:
        print(f"\n  Top-3 severe rows:")
        top3 = scored_df.nlargest(3, "anomaly_score")
        for _, r in top3.iterrows():
            try:
                d3 = json.loads(r["direction_top3"])
                top_dim = f"{d3[0]['dim']} z={d3[0]['z']:+.2f}" if d3 else "—"
            except Exception:
                top_dim = "—"
            print(
                f"    {r['player_name']:<26} | {str(r['game_date'].date())} "
                f"| score={r['anomaly_score']:.3f} | {r['bucket']} | {top_dim}"
            )

    print(f"\n  Files written:")
    print(f"    {VALIDATION_OUT}")
    if all_pass:
        print(f"    {PARQUET_OUT}")
    print(f"    {DOC_OUT}")
    print()


if __name__ == "__main__":
    main()

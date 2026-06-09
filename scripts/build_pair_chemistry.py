"""
INT-30  Player Pair Chemistry Intelligence
==========================================
For each pair (A, B) that appears together in >=500 frames across all CV-tracked games,
compute:
  - Player A weighted mean CV features WHEN on-court WITH player B
  - Player A weighted mean CV features WHEN on-court WITHOUT player B
  - Delta (with_B - without_B) and z-score using A's overall CV std
  - Chemistry score = sum of |z| across top-3 features

Inputs:
  - data/intelligence/lineup_chemistry.parquet

Outputs:
  - data/intelligence/pair_chemistry.parquet
  - data/intelligence/pair_signatures.json
  - vault/Intelligence/Pair_Chemistry_Atlas.md
  - vault/Intelligence/Pairs/<a>_<b>.md  (top 10 pairs)
"""

import os
import sys
import json
import warnings
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "data" / "intelligence"
VAULT_INTEL = ROOT / "vault" / "Intelligence"
PAIRS_DIR = VAULT_INTEL / "Pairs"

LC_PATH     = INTEL_DIR / "lineup_chemistry.parquet"
OUT_PARQUET = INTEL_DIR / "pair_chemistry.parquet"
OUT_JSON    = INTEL_DIR / "pair_signatures.json"
OUT_ATLAS   = VAULT_INTEL / "Pair_Chemistry_Atlas.md"

PAIRS_DIR.mkdir(parents=True, exist_ok=True)

CV_FEATURES = [
    "paint_dwell_pct",
    "touches_per_100frames",
    "preshot_velocity_peak",
    "drive_rate",
    "paint_approach_rate",
    "fast_break_rate",
    "potential_assists",
    "possession_duration_avg",
    "avg_spacing",
    "velocity_mean",
    "isolation_rate",
    "shot_zone_paint_pct",
    "shot_zone_3pt_pct",
    "contested_shot_rate",
]

MIN_FRAMES_PAIR = 500
TOP_N_PAIRS     = 20
TOP_PAIRS_NOTES = 10

FEATURE_LABELS = {
    "paint_dwell_pct"        : "paint dwell %",
    "touches_per_100frames"  : "touches per 100 frames",
    "preshot_velocity_peak"  : "pre-shot peak velocity",
    "drive_rate"             : "drive rate",
    "paint_approach_rate"    : "paint approach rate",
    "fast_break_rate"        : "fast-break rate",
    "potential_assists"      : "potential assists",
    "possession_duration_avg": "avg possession duration",
    "avg_spacing"            : "avg court spacing",
    "velocity_mean"          : "avg velocity",
    "isolation_rate"         : "isolation rate",
    "shot_zone_paint_pct"    : "paint shot %",
    "shot_zone_3pt_pct"      : "3-point shot %",
    "contested_shot_rate"    : "contested shot rate",
}


def _is_nan(v):
    try:
        return float(v) != float(v)
    except (TypeError, ValueError):
        return True


def load_lineup_chemistry():
    print(f"Loading {LC_PATH} ...")
    lc = pd.read_parquet(str(LC_PATH))
    val_cols  = [f"val_{f}" for f in CV_FEATURES]
    available = [c for c in val_cols if c in lc.columns]
    print(f"  Rows: {len(lc):,}  |  Players: {lc['player_id'].nunique()}  |  Games: {lc['game_id'].nunique()}")
    print(f"  CV features available: {len(available)}/{len(val_cols)}")
    return lc, [f.replace("val_", "") for f in available]


def compute_player_baselines(lc, features):
    dedup = lc.drop_duplicates(subset=["player_id", "game_id", "lineup_id"], keep="first")
    records = []
    for pid, grp in dedup.groupby("player_id"):
        row = {"player_id": pid, "player_name": grp["player_name"].iloc[0]}
        total_frames = float(grp["n_frames"].sum())
        row["total_frames"] = total_frames
        for feat in features:
            col = f"val_{feat}"
            if col not in grp.columns:
                continue
            vals  = grp[col].fillna(0).values.astype(float)
            wts   = grp["n_frames"].values.astype(float)
            wsum  = wts.sum()
            if wsum == 0:
                row[f"baseline_{feat}"] = 0.0
                row[f"std_{feat}"]      = 0.0
                continue
            wmean = float(np.average(vals, weights=wts))
            wstd  = float(np.sqrt(np.average((vals - wmean) ** 2, weights=wts)))
            row[f"baseline_{feat}"] = wmean
            row[f"std_{feat}"]      = wstd
        records.append(row)
    baselines = pd.DataFrame(records).set_index("player_id")
    print(f"  Player baselines computed: {len(baselines)} players")
    return baselines


def build_pair_aggregates(lc, features):
    dedup = lc.drop_duplicates(subset=["player_id", "game_id", "lineup_id"], keep="first")
    pair_frame_sums = {}
    pair_feat_wsum  = {}
    pair_game_set   = {}

    for (game_id, lineup_id), grp in dedup.groupby(["game_id", "lineup_id"]):
        player_rows = grp.set_index("player_id")
        pids = list(player_rows.index)
        if len(pids) < 2:
            continue
        for a_id, b_id in itertools.permutations(pids, 2):
            a_row    = player_rows.loc[a_id]
            n_frames = float(a_row["n_frames"])
            key      = (a_id, b_id)
            if key not in pair_frame_sums:
                pair_frame_sums[key] = 0.0
                pair_feat_wsum[key]  = {f: 0.0 for f in features}
                pair_game_set[key]   = set()
            pair_frame_sums[key] += n_frames
            pair_game_set[key].add(game_id)
            for feat in features:
                col = f"val_{feat}"
                if col in a_row.index:
                    v = a_row[col]
                    if pd.notna(v):
                        pair_feat_wsum[key][feat] += float(v) * n_frames

    print(f"  Raw ordered pairs with any co-occurrence: {len(pair_frame_sums):,}")

    records = []
    for (a_id, b_id), total_frames in pair_frame_sums.items():
        if total_frames < MIN_FRAMES_PAIR:
            continue
        rec = {
            "player_A_id"       : a_id,
            "player_B_id"       : b_id,
            "n_frames_together" : total_frames,
            "n_games"           : len(pair_game_set[(a_id, b_id)]),
        }
        for feat in features:
            wsum = pair_feat_wsum[(a_id, b_id)][feat]
            rec[f"with_B_{feat}"] = wsum / total_frames if total_frames > 0 else float("nan")
        records.append(rec)

    pairs_df = pd.DataFrame(records)
    print(f"  Pairs with >= {MIN_FRAMES_PAIR} frames: {len(pairs_df):,}")
    return pairs_df


def compute_deltas(pairs_df, baselines, features):
    result_rows = []
    for _, row in pairs_df.iterrows():
        a_id = row["player_A_id"]
        b_id = row["player_B_id"]
        if a_id not in baselines.index:
            continue
        a_base     = baselines.loc[a_id]
        total_a    = float(a_base["total_frames"])
        n_together = float(row["n_frames_together"])
        n_without  = max(total_a - n_together, 0.0)

        new_row = {
            "player_A_id"       : a_id,
            "player_A_name"     : str(a_base["player_name"]),
            "player_B_id"       : b_id,
            "player_B_name"     : str(baselines.loc[b_id, "player_name"]) if b_id in baselines.index else str(b_id),
            "n_frames_together" : n_together,
            "n_frames_without"  : n_without,
            "n_games"           : int(row["n_games"]),
        }

        for feat in features:
            overall_mean = float(a_base.get(f"baseline_{feat}", float("nan")))
            overall_std  = float(a_base.get(f"std_{feat}", float("nan")))
            wb_raw       = row.get(f"with_B_{feat}", float("nan"))
            with_b_mean  = float(wb_raw) if pd.notna(wb_raw) else float("nan")

            if n_without > 0 and not _is_nan(overall_mean) and not _is_nan(with_b_mean):
                without_b_mean = (total_a * overall_mean - n_together * with_b_mean) / n_without
            else:
                without_b_mean = overall_mean

            delta = (with_b_mean - without_b_mean) if not (_is_nan(with_b_mean) or _is_nan(without_b_mean)) else float("nan")
            z     = (delta / overall_std) if not (_is_nan(delta) or _is_nan(overall_std) or overall_std < 1e-9) else float("nan")

            new_row[f"mean_with_B_{feat}"]    = with_b_mean
            new_row[f"mean_without_B_{feat}"] = float(without_b_mean) if not _is_nan(without_b_mean) else float("nan")
            new_row[f"delta_{feat}"]          = delta
            new_row[f"z_{feat}"]              = z

        result_rows.append(new_row)
    return pd.DataFrame(result_rows)


def compute_chemistry_scores(pairs_df, features):
    z_cols = [f"z_{f}" for f in features if f"z_{f}" in pairs_df.columns]
    z_mat  = pairs_df[z_cols].abs()

    def top3_sum(row):
        vals = row.dropna().sort_values(ascending=False)
        return float(vals.iloc[:3].sum()) if len(vals) >= 1 else 0.0

    pairs_df = pairs_df.copy()
    pairs_df["chemistry_score"] = z_mat.apply(top3_sum, axis=1)
    pairs_df["max_abs_z"]       = z_mat.max(axis=1)

    def dominant_feature(row):
        best_feat, best_abs = "", 0.0
        for f in features:
            v = row.get(f"z_{f}", float("nan"))
            if not _is_nan(v) and abs(float(v)) > best_abs:
                best_abs, best_feat = abs(float(v)), f
        return best_feat

    def top3_features(row):
        pl = []
        for f in features:
            v = row.get(f"z_{f}", float("nan"))
            if not _is_nan(v):
                pl.append((f, float(v)))
        pl.sort(key=lambda x: abs(x[1]), reverse=True)
        return json.dumps([[f, round(z, 3)] for f, z in pl[:3]])

    pairs_df["dominant_feature"] = pairs_df.apply(dominant_feature, axis=1)
    pairs_df["top3_features"]    = pairs_df.apply(top3_features, axis=1)
    return pairs_df


def tag_symmetry(pairs_df):
    score_map = {(r["player_A_id"], r["player_B_id"]): float(r["chemistry_score"])
                 for _, r in pairs_df.iterrows()}
    tags = []
    for _, row in pairs_df.iterrows():
        a, b = row["player_A_id"], row["player_B_id"]
        s_ab = float(row["chemistry_score"])
        s_ba = score_map.get((b, a), 0.0)
        if s_ab >= 1.5 and s_ba >= 1.5:
            tags.append("symmetric")
        elif s_ab > 0 and s_ba > 0 and max(s_ab, s_ba) >= 2.0 * min(s_ab, s_ba):
            tags.append("asymmetric")
        else:
            tags.append("balanced")
    pairs_df = pairs_df.copy()
    pairs_df["symmetry"] = tags
    return pairs_df


def interpret_shift(feat, delta, z):
    label     = FEATURE_LABELS.get(feat, feat)
    direction = "rises" if delta > 0 else "drops"
    mag       = "sharply" if abs(z) >= 3 else ("meaningfully" if abs(z) >= 2 else "noticeably")
    return f"{label} {direction} {mag} ({z:+.2f}sigma)"


def pair_plain_english(row, features):
    a_name   = str(row["player_A_name"])
    b_name   = str(row["player_B_name"])
    symmetry = str(row["symmetry"])
    try:
        top3 = json.loads(row.get("top3_features", "[]"))
    except Exception:
        top3 = []

    lines = []
    for feat, z in top3:
        delta = row.get(f"delta_{feat}", float("nan"))
        if not _is_nan(z) and not _is_nan(delta):
            lines.append(f"  - {a_name}'s {interpret_shift(feat, float(delta), float(z))}")

    if symmetry == "symmetric":
        suffix = f"Both {a_name} and {b_name} adapt their roles -- symmetric chemistry."
    elif symmetry == "asymmetric":
        suffix = f"{a_name}'s role adapts more than {b_name}'s -- asymmetric."
    else:
        suffix = "Moderate bilateral adjustment."

    return "\n".join(lines) + f"\n  > {suffix}"


def save_parquet(pairs_df):
    pairs_df.to_parquet(str(OUT_PARQUET), index=False)
    print(f"  Saved: {OUT_PARQUET}  ({len(pairs_df):,} rows)")


def save_json(pairs_df, features):
    top  = pairs_df.sort_values("chemistry_score", ascending=False).head(TOP_N_PAIRS)
    sigs = {}
    for _, row in top.iterrows():
        key = f"{row['player_A_id']}_{row['player_B_id']}"
        try:
            top3 = json.loads(row.get("top3_features", "[]"))
        except Exception:
            top3 = []
        sigs[key] = {
            "player_A_id"       : int(row["player_A_id"]),
            "player_A_name"     : str(row["player_A_name"]),
            "player_B_id"       : int(row["player_B_id"]),
            "player_B_name"     : str(row["player_B_name"]),
            "n_frames_together" : int(row["n_frames_together"]),
            "n_games"           : int(row["n_games"]),
            "chemistry_score"   : round(float(row["chemistry_score"]), 4),
            "max_abs_z"         : round(float(row["max_abs_z"]), 4),
            "symmetry"          : str(row["symmetry"]),
            "dominant_feature"  : str(row["dominant_feature"]),
            "top3_features"     : top3,
        }
    with open(str(OUT_JSON), "w", encoding="utf-8") as f:
        json.dump(sigs, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {OUT_JSON}  ({len(sigs)} signatures)")


def save_pair_notes(pairs_df, features):
    top10     = pairs_df.sort_values("chemistry_score", ascending=False).head(TOP_PAIRS_NOTES)
    score_map = {(r["player_A_id"], r["player_B_id"]): r for _, r in pairs_df.iterrows()}

    for _, row in top10.iterrows():
        a_slug = str(row["player_A_name"]).lower().replace(" ", "_").replace("'", "").replace(".", "")
        b_slug = str(row["player_B_name"]).lower().replace(" ", "_").replace("'", "").replace(".", "")
        fname  = PAIRS_DIR / f"{a_slug}_{b_slug}.md"
        rev    = score_map.get((row["player_B_id"], row["player_A_id"]))

        lines = [
            f"# {row['player_A_name']} + {row['player_B_name']}",
            "",
            f"**Chemistry score (A perspective):** {row['chemistry_score']:.2f}",
            f"**Max |z|:** {row['max_abs_z']:.2f}",
            f"**Frames together:** {int(row['n_frames_together']):,}",
            f"**Games together:** {int(row['n_games'])}",
            f"**Symmetry:** {row['symmetry']}",
            "",
            f"## {row['player_A_name']} when on-court with {row['player_B_name']}",
            "",
        ]
        for feat in features:
            z     = row.get(f"z_{feat}", float("nan"))
            delta = row.get(f"delta_{feat}", float("nan"))
            wmean = row.get(f"mean_with_B_{feat}", float("nan"))
            wbase = row.get(f"mean_without_B_{feat}", float("nan"))
            if not _is_nan(z) and abs(float(z)) >= 0.5:
                label = FEATURE_LABELS.get(feat, feat)
                lines.append(f"- **{label}**: {float(wbase):.4f} -> {float(wmean):.4f}  (delta {float(delta):+.4f}, {float(z):+.2f}sigma)")

        if rev is not None:
            lines += ["", f"## {row['player_B_name']} when on-court with {row['player_A_name']}", ""]
            for feat in features:
                z     = rev.get(f"z_{feat}", float("nan"))
                delta = rev.get(f"delta_{feat}", float("nan"))
                wmean = rev.get(f"mean_with_B_{feat}", float("nan"))
                wbase = rev.get(f"mean_without_B_{feat}", float("nan"))
                if not _is_nan(z) and abs(float(z)) >= 0.5:
                    label = FEATURE_LABELS.get(feat, feat)
                    lines.append(f"- **{label}**: {float(wbase):.4f} -> {float(wmean):.4f}  (delta {float(delta):+.4f}, {float(z):+.2f}sigma)")

        lines += [
            "",
            "## Plain-language interpretation",
            "",
            pair_plain_english(row, features),
            "",
            "---",
            "*Generated by INT-30 build_pair_chemistry.py*",
        ]
        fname.write_text("\n".join(lines), encoding="utf-8")

    print(f"  Saved {TOP_PAIRS_NOTES} pair notes to {PAIRS_DIR}")


def save_atlas(pairs_df, features, n_processed_games):
    top10      = pairs_df.sort_values("chemistry_score", ascending=False).head(10)
    sym_total  = int((pairs_df["symmetry"] == "symmetric").sum())
    asym_total = int((pairs_df["symmetry"] == "asymmetric").sum())
    bal_total  = int((pairs_df["symmetry"] == "balanced").sum())
    players_in = set(pairs_df["player_A_id"].tolist()) | set(pairs_df["player_B_id"].tolist())
    asym_rows  = pairs_df[pairs_df["symmetry"] == "asymmetric"]
    asym_common = asym_rows["dominant_feature"].value_counts().index[0] if len(asym_rows) > 0 else "N/A"

    table_rows = []
    for _, row in top10.iterrows():
        dom_label = FEATURE_LABELS.get(str(row["dominant_feature"]), str(row["dominant_feature"]))
        table_rows.append(
            f"| {row['player_A_name']} w/ {row['player_B_name']} | {int(row['n_frames_together']):,} | "
            f"{row['chemistry_score']:.2f} | {row['symmetry']} | {dom_label} |"
        )

    top5 = pairs_df.sort_values("chemistry_score", ascending=False).head(5)
    findings = []
    for _, row in top5.iterrows():
        dom   = str(row["dominant_feature"])
        z     = row.get(f"z_{dom}", float("nan"))
        delta = row.get(f"delta_{dom}", float("nan"))
        if not _is_nan(z) and not _is_nan(delta):
            direction = "rises" if float(delta) > 0 else "drops"
            label = FEATURE_LABELS.get(dom, dom)
            findings.append(
                f"- **{row['player_A_name']} w/ {row['player_B_name']}**: "
                f"{row['player_A_name']}'s {label} {direction} "
                f"{abs(float(z)):.2f}sigma in {row['player_B_name']}'s presence ({row['symmetry']})"
            )

    top10_links = []
    for _, row in pairs_df.sort_values("chemistry_score", ascending=False).head(TOP_PAIRS_NOTES).iterrows():
        a_slug = str(row["player_A_name"]).lower().replace(" ", "_").replace("'","").replace(".","")
        b_slug = str(row["player_B_name"]).lower().replace(" ", "_").replace("'","").replace(".","")
        top10_links.append(f"- [[Pairs/{a_slug}_{b_slug}]]")

    lines = [
        "# Player Pair Chemistry Atlas",
        "",
        "## Methodology",
        "",
        "For each pair of CV-tracked players that shared >=500 frames of on-court time across tracked games,",
        "we compute the deviation in player A's CV profile when on-court with player B vs off-court with player B.",
        "",
        "**Approach:**",
        "1. Source: `data/intelligence/lineup_chemistry.parquet` -- per-player, per-lineup CV values with frame counts",
        "2. Self-join on (game_id, lineup_id) to enumerate all ordered pair co-occurrences",
        "3. Frame-weight player A's CV means: with B vs without B (back-calculated from overall baseline)",
        "4. Delta and z-score vs player A's overall per-feature std",
        "5. Chemistry score = sum of |z| across top-3 shifted features",
        "",
        "**Asymmetry:** Both directions (A on B, B on A) are computed independently.",
        "If both shift large -> symmetric. If only one shifts -> asymmetric.",
        "",
        "## Coverage",
        "",
        f"- Games in source lineup_chemistry: {n_processed_games}",
        f"- Distinct ordered pairs with >={MIN_FRAMES_PAIR} frames together: {len(pairs_df):,}",
        f"- Unique players involved: {len(players_in)}",
        f"- Symmetric pairs (both directions score >=1.5): {sym_total}",
        f"- Asymmetric pairs (one side >=2x the other, max >=2.0): {asym_total}",
        f"- Balanced/low pairs: {bal_total}",
        "",
        "## Top 10 Chemistry Pairs (by chemistry score)",
        "",
        "| Pair | Frames Together | Chemistry Score | Symmetry | Dominant Shift |",
        "|------|----------------|----------------|---------|----------------|",
    ] + table_rows + [
        "",
        "## Notable Findings",
        "",
    ] + findings + [
        "",
        "## Per-pair Detailed Notes",
        "",
    ] + top10_links + [
        "",
        "## How to Use",
        "",
        "- **Injury impact**: When player B is OUT, expect player A's CV profile to revert toward his solo baseline.",
        "  Check this pair's delta_* columns to quantify the expected shift.",
        "- **Roster scouting**: Identify pairs with high symmetric chemistry -- both players elevate when together.",
        "- **Trade evaluation**: Would acquiring player B improve target player A's CV signature?",
        "  Look up player_A_id rows in pair_chemistry.parquet sorted by chemistry_score.",
        "- **Lineup construction**: Pairs with high paint_dwell or drive_rate chemistry signal strong two-man-game.",
        "",
        "## Data Files",
        "",
        "- `data/intelligence/pair_chemistry.parquet` -- full pair x feature table",
        "- `data/intelligence/pair_signatures.json` -- compact top-20 signatures for fast lookup",
        "- `vault/Intelligence/Pairs/` -- per-pair .md notes for top 10",
        "",
        "## Honest Caveats",
        "",
        f"- {MIN_FRAMES_PAIR}-frame floor (~{MIN_FRAMES_PAIR//30}s at 30fps) may exclude real but sparse pairs",
        "- ISSUE-022: defender_distance=200.0 sentinel affects CV signal quality",
        "- Phantom/unresolved slots (jersey OCR failures) may create ghost players in lineup_chemistry",
        "- Back-calculated 'without B' baseline can be noisy when n_frames_without is small",
        "- lineup_id is game-local; short stints across many games may be noisier than few long stints",
        "",
        "---",
        "*Generated by INT-30 build_pair_chemistry.py*",
    ]
    OUT_ATLAS.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved atlas: {OUT_ATLAS}")


def print_report(pairs_df, features):
    top5       = pairs_df.sort_values("chemistry_score", ascending=False).head(5)
    players_in = set(pairs_df["player_A_id"].tolist()) | set(pairs_df["player_B_id"].tolist())
    sym_total  = int((pairs_df["symmetry"] == "symmetric").sum())
    asym_total = int((pairs_df["symmetry"] == "asymmetric").sum())

    print()
    print("=" * 70)
    print("INT-30 Player Pair Chemistry -- Final Report")
    print("=" * 70)
    print()
    print("### Coverage")
    print(f"  Distinct ordered pairs with >={MIN_FRAMES_PAIR} frames: {len(pairs_df):,}")
    print(f"  Players involved: {len(players_in)}")
    print()
    print("### Top 5 Pairs by Chemistry Score")
    print(f"  {'Pair':<44} {'Frames':>8}  {'Score':>6}  {'Symmetry':<12}  Top Feature")
    print("  " + "-" * 90)
    for _, row in top5.iterrows():
        pair_str = f"{row['player_A_name']} w/ {row['player_B_name']}"
        dom   = FEATURE_LABELS.get(str(row["dominant_feature"]), str(row["dominant_feature"]))
        z_raw = row.get(f"z_{row['dominant_feature']}", float("nan"))
        z_str = f"{float(z_raw):+.2f}sigma" if not _is_nan(z_raw) else "?"
        print(f"  {pair_str:<44} {int(row['n_frames_together']):>8,}  {row['chemistry_score']:>6.2f}  {row['symmetry']:<12}  {dom} ({z_str})")
    print()
    print("### Symmetric vs Asymmetric Breakdown")
    print(f"  Symmetric:  {sym_total}")
    print(f"  Asymmetric: {asym_total}")
    print(f"  Balanced:   {(pairs_df['symmetry'] == 'balanced').sum()}")
    asym_rows = pairs_df[pairs_df["symmetry"] == "asymmetric"]
    if len(asym_rows) > 0:
        common = asym_rows["dominant_feature"].value_counts().index[0]
        print(f"  Most common asymmetric pattern: {FEATURE_LABELS.get(common, common)}")
    print()
    print("### Files")
    print(f"  {OUT_PARQUET}")
    print(f"  {OUT_JSON}")
    print(f"  {OUT_ATLAS}")
    print(f"  {PAIRS_DIR} (top {TOP_PAIRS_NOTES} pair notes)")
    print()
    print("### How to Use")
    print("  - Player B out injured? Check pair_chemistry.parquet for A expected CV reversion")
    print("  - Trade eval: query pair_chemistry for target player top chemistry partners")
    print("  - Lineup construction: high paint_dwell or drive_rate chemistry = strong two-man game")
    print()
    print("### Honest Caveats")
    print(f"  - {MIN_FRAMES_PAIR}-frame floor may exclude real but sparse pairs")
    print("  - ISSUE-022: defender_distance=200 sentinel corrupts some CV features")
    print("  - Jersey OCR failures (phantom slots) can inflate lineup_chemistry noise")
    print("  - Back-calculated without_B baseline is noisier when n_frames_without is small")
    print("=" * 70)


def main():
    print()
    print("=== INT-30: Player Pair Chemistry Intelligence ===")
    print()
    lc, features = load_lineup_chemistry()
    n_games = int(lc["game_id"].nunique())

    print("\n[Step 2] Computing player baselines ...")
    baselines = compute_player_baselines(lc, features)

    print("\n[Step 3] Building pair aggregates ...")
    pairs_raw = build_pair_aggregates(lc, features)
    if len(pairs_raw) == 0:
        print("ERROR: No pairs found. Exiting.")
        sys.exit(1)

    print("\n[Step 4] Computing deltas and z-scores ...")
    pairs_df = compute_deltas(pairs_raw, baselines, features)
    print(f"  Pairs after delta computation: {len(pairs_df):,}")

    print("\n[Step 5] Computing chemistry scores ...")
    pairs_df = compute_chemistry_scores(pairs_df, features)

    print("\n[Step 6] Tagging symmetry ...")
    pairs_df = tag_symmetry(pairs_df)

    pairs_df = pairs_df.sort_values("chemistry_score", ascending=False).reset_index(drop=True)

    print("\n[Step 7] Saving parquet ...")
    save_parquet(pairs_df)

    print("\n[Step 8] Saving JSON signatures ...")
    save_json(pairs_df, features)

    print("\n[Step 9] Writing per-pair notes ...")
    save_pair_notes(pairs_df, features)

    print("\n[Step 10] Writing atlas ...")
    save_atlas(pairs_df, features, n_games)

    print_report(pairs_df, features)


if __name__ == "__main__":
    main()

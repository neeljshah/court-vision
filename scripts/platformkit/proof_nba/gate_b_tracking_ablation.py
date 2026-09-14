"""scripts.platformkit.proof_nba.gate_b_tracking_ablation -- Gate B: NBA tracking ceiling (Q06).

Challenger = the landed per-game prop champion (prop_game_model.py, Q15) plus a TRACKING
feature family, joined strictly as-of:
  - player_tracking_features.parquet (player-season) -- PRIOR season only, never current.
  - hustle_features.parquet + hustle_features_2025-26.parquet (player-season) -- PRIOR season only.
  - defender_matchup_states.parquet (player-game) -- *_asof columns only, joined on
    (def_player_id -> player_id, game_id); realized_* columns are LABELS and are never loaded.
Excluded (no as-of builder exists): atlas_player_spacing_gravity, atlas_player_matchup_splits,
catch_shoot_vs_pullup -- all single-snapshot as_of 2026-05-31.

A second ablation adds ONLY the defender_matchup *_asof columns (the per-game family) to
separate a per-game signal from the two prior-season aggregates.

Verdict per stat per corpus: CEILING_POSITIVE if the champion-minus-challenger CRPS CI
excludes 0 in the challenger's favour, CEILING_NEGATIVE if it excludes 0 against, else
CEILING_ZERO. Overall verdict per stat: CEILING_POSITIVE only if positive on BOTH corpora.

CALIBRATION ONLY -- see the project's calibration-claims rule doc under .claude/rules/. `edge_claimed` is fixed False.
INVARIANTS: no src/kernel/api/intel edits; <=300 LOC; ASCII only; n_jobs=2.
Run: python -m scripts.platformkit.proof_nba.gate_b_tracking_ablation --stats pts,reb,ast \
     --corpora 2023-24,2024-25 --out data/cache/gate_b/
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.platformkit.dist_metrics import crps_ensemble_rows  # noqa: E402
from scripts.platformkit.proof_nba.prop_game_model import (  # noqa: E402
    RNG_SEED, TAUS, _delta_ci, _pinball_rows, _rd, build_opp_allowed,
    build_player_features, clustered_ci, load_frame, lgb_quantiles, score_quantiles,
    split_corpus)
import lightgbm as lgb  # noqa: E402

_CACHE = _REPO / "data" / "cache"
_NBA = _REPO / "data" / "domains" / "basketball_nba"
EXCLUDED_ATLAS = [
    "atlas_player_spacing_gravity (as_of 2026-05-31, single snapshot -- no as-of builder, excluded)",
    "atlas_player_matchup_splits (as_of 2026-05-31, single snapshot -- excluded)",
    "catch_shoot_vs_pullup (as_of 2026-05-31, single snapshot -- excluded)",
]
NOT_VERIFIED = [
    "prior-season aggregates (player_tracking_features, hustle_features) are a proxy for what "
    "a broadcast teacher would emit in-season; not validated against a real broadcast signal.",
    *EXCLUDED_ATLAS,
    "win-prob challenger not run -- the pregame NBA harness has only one season of odds on disk.",
    "defender_matchup_states' *_asof columns are trusted as pre-computed prior-N-games-as-of-this-"
    "game by the upstream table producer; not independently re-derived here.",
    "defender_matchup_states covers games from 2024-10-22 onward; the 2023-24 corpus therefore has "
    "a 0 pct match rate for that table by construction, not a bug.",
]


def _prior_season(season: str) -> str:
    """'2024-25' -> '2023-24'. Season strings are YYYY-YY, so string comparison orders them."""
    start = int(str(season)[:4])
    return f"{start - 1}-{str(start)[-2:]}"


def join_prior_season(df: pd.DataFrame, table: pd.DataFrame, prefix: str) -> tuple:
    """Left-join a player-SEASON table onto df keyed by (player_id, df's PRIOR season).
    Asserts every matched row's table-season precedes the row's own season (no leakage).
    Returns (joined_df, feature_cols, match_rate)."""
    keep = [c for c in table.columns if c not in ("player_id", "season", "player_name")
            and pd.api.types.is_numeric_dtype(table[c])]
    t = table[["player_id", "season"] + keep].rename(columns={c: f"{prefix}_{c}" for c in keep})
    t = t.rename(columns={"season": "_table_season"})
    d = df.copy()
    d["_prior_season"] = d["season"].astype(str).map(_prior_season)
    merged = d.merge(t, left_on=["player_id", "_prior_season"], right_on=["player_id", "_table_season"],
                      how="left")
    matched = merged["_table_season"].notna()
    if matched.any():
        assert (merged.loc[matched, "_table_season"] < merged.loc[matched, "season"].astype(str)).all(), \
            f"{prefix}: prior-season join returned a same/future-season row"
    fcols = [f"{prefix}_{c}" for c in keep]
    match_rate = float(merged[fcols[0]].notna().mean()) if fcols else float("nan")
    merged = merged.drop(columns=["_prior_season", "_table_season"])
    return merged, fcols, match_rate


def join_game_asof(df: pd.DataFrame, table: pd.DataFrame, cols: list) -> tuple:
    """Left-join a player-GAME as-of table on (player_id, game_id). Returns (df, match_rate)."""
    merged = df.merge(table[["player_id", "game_id"] + cols], on=["player_id", "game_id"], how="left")
    match_rate = float(merged[cols[0]].notna().mean()) if cols else float("nan")
    return merged, match_rate


def load_tracking_family() -> dict:
    """The three IN-SCOPE tracking tables. defender_matchup: whitelist *_asof cols + def_n_prior
    only -- realized_* label columns are never loaded."""
    tracking = pd.read_parquet(_CACHE / "player_tracking_features.parquet")
    hustle = pd.concat([
        pd.read_parquet(_CACHE / "hustle_features.parquet"),
        pd.read_parquet(_CACHE / "hustle_features_2025-26.parquet"),
    ], ignore_index=True).drop_duplicates(["player_id", "season"])
    dmatch = pd.read_parquet(_NBA / "defender_matchup_states.parquet").rename(
        columns={"def_player_id": "player_id"})
    dm_cols = [c for c in dmatch.columns if c.endswith("_asof")] + ["def_n_prior"]
    dmatch = dmatch[["player_id", "game_id"] + dm_cols].drop_duplicates(["player_id", "game_id"])
    return {"tracking": tracking, "hustle": hustle, "defender_matchup": dmatch, "dm_cols": dm_cols}


def build_challenger_frame(df: pd.DataFrame, fam: dict) -> tuple:
    """champion frame + all tracking-family columns. Returns (df, trk_cols, hus_cols, dm_cols)."""
    df2, trk_cols, _ = join_prior_season(df, fam["tracking"], "trk")
    df2, hus_cols, _ = join_prior_season(df2, fam["hustle"], "hus")
    df2, _ = join_game_asof(df2, fam["defender_matchup"], fam["dm_cols"])
    dm_cols = [f"{c}" for c in fam["dm_cols"]]  # already unprefixed, joined verbatim
    return df2, trk_cols, hus_cols, dm_cols


def match_rates_for_corpus(df2: pd.DataFrame, corpus: str, trk_cols: list, hus_cols: list,
                            dm_cols: list) -> dict:
    sub = df2[df2["season"] == corpus]
    def _rate(cols):
        return float(sub[cols[0]].notna().mean()) if cols else float("nan")
    return {"player_tracking_prior_season": round(_rate(trk_cols), 4),
            "hustle_prior_season": round(_rate(hus_cols), 4),
            "defender_matchup_asof": round(_rate(dm_cols), 4), "n_rows": int(len(sub))}


def _fit_predict(xtr, ytr, xte) -> np.ndarray:
    return lgb_quantiles(xtr, ytr, xte)


def tracking_feature_importance(xtr: pd.DataFrame, ytr: pd.Series, tracking_cols: list) -> list:
    """Gain-based feature importance (median-quantile fit) restricted to tracking columns."""
    m = lgb.LGBMRegressor(objective="quantile", alpha=0.5, n_estimators=200, num_leaves=15,
                           min_child_samples=30, n_jobs=2, random_state=RNG_SEED,
                           deterministic=True, force_row_wise=True, verbosity=-1,
                           importance_type="gain")
    m.fit(xtr, ytr)
    imp = dict(zip(xtr.columns, m.feature_importances_.tolist()))
    ranked = sorted(((c, imp.get(c, 0.0)) for c in tracking_cols), key=lambda kv: -kv[1])
    return [{"feature": c, "gain": round(float(g), 2)} for c, g in ranked[:15]]


def ceiling_verdict(ci: dict) -> str:
    """CI is on (champion_loss - challenger_loss); positive = challenger better."""
    if ci["ci_lo"] > 0:
        return "CEILING_POSITIVE"
    if ci["ci_hi"] < 0:
        return "CEILING_NEGATIVE"
    return "CEILING_ZERO"


def run_stat(df2: pd.DataFrame, champ_cols: list, trk_cols: list, hus_cols: list, dm_cols: list,
             stat: str, corpus: str) -> dict:
    train_df, test_df, split_meta = split_corpus(df2, corpus)
    if len(train_df) < 200 or len(test_df) < 50:
        return {"stat": stat, "corpus": corpus, "status": "UNDERPOWERED_DATA",
                "n_train": int(len(train_df)), "n_test": int(len(test_df)), "edge_claimed": False}
    fcols_champ = champ_cols + [f"opp_allowed_{stat}_10"]
    fcols_chall = fcols_champ + trk_cols + hus_cols + dm_cols
    fcols_dm = fcols_champ + dm_cols
    ytr, yte = train_df[stat].astype(float), test_df[stat].astype(float).to_numpy()
    game_ids = test_df["game_id"].to_numpy()

    def _xy(cols):
        med = train_df[cols].median()
        return train_df[cols].fillna(med).fillna(0.0), test_df[cols].fillna(med).fillna(0.0)

    xtr_c, xte_c = _xy(fcols_champ)
    xtr_h, xte_h = _xy(fcols_chall)
    xtr_d, xte_d = _xy(fcols_dm)
    q_champ = _fit_predict(xtr_c, ytr, xte_c)
    q_chall = _fit_predict(xtr_h, ytr, xte_h)
    q_dm = _fit_predict(xtr_d, ytr, xte_d)
    ci_crps_full = _delta_ci(yte, q_champ, q_chall, game_ids, crps_ensemble_rows)
    ci_pb_full = _delta_ci(yte, q_champ, q_chall, game_ids, _pinball_rows)
    ci_crps_dm = _delta_ci(yte, q_champ, q_dm, game_ids, crps_ensemble_rows)
    ci_pb_dm = _delta_ci(yte, q_champ, q_dm, game_ids, _pinball_rows)
    return {
        "stat": stat, "corpus": corpus, "status": "OK", **split_meta,
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "n_games_test": int(pd.unique(game_ids).size),
        "imputed_share_challenger": round(float(test_df[fcols_chall].isna().any(axis=1).mean()), 4),
        "coverage_10_90_champion": score_quantiles(yte, q_champ)["coverage_10_90"],
        "coverage_10_90_challenger": score_quantiles(yte, q_chall)["coverage_10_90"],
        "champion_pinball": score_quantiles(yte, q_champ)["pinball_avg"],
        "challenger_pinball": score_quantiles(yte, q_chall)["pinball_avg"],
        "delta_crps_full": {"positive_means_challenger_better": True, **_rd(ci_crps_full)},
        "delta_pinball_full": {"positive_means_challenger_better": True, **_rd(ci_pb_full)},
        "verdict_crps_full": ceiling_verdict(ci_crps_full),
        "verdict_pinball_full": ceiling_verdict(ci_pb_full),
        "delta_crps_defender_matchup_only": {"positive_means_challenger_better": True, **_rd(ci_crps_dm)},
        "verdict_crps_defender_matchup_only": ceiling_verdict(ci_crps_dm),
        "tracking_feature_importance_gain": tracking_feature_importance(
            xtr_h, ytr, trk_cols + hus_cols + dm_cols),
        "edge_claimed": False,
    }


def markdown_table(results: list) -> str:
    lines = ["champion = landed per-game prop model (Q15); baseline comparison is champion vs "
             "champion+tracking; 2023-24 is a within-season fallback split; calibration only; "
             "no monetary claim.", "",
             "| stat | corpus | n_test | verdict_crps_full | delta_crps_full | "
             "verdict_crps_defmatch_only | cov_champ | cov_chall |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "OK":
            lines.append(f"| {r['stat']} | {r['corpus']} | {r.get('n_test', 0)} | "
                          f"{r['status']} | - | - | - | - |")
            continue
        d = r["delta_crps_full"]
        lines.append(f"| {r['stat']} | {r['corpus']} | {r['n_test']} | {r['verdict_crps_full']} | "
                      f"{d['point']:.4f} [{d['ci_lo']:.4f}, {d['ci_hi']:.4f}] | "
                      f"{r['verdict_crps_defender_matchup_only']} | "
                      f"{r['coverage_10_90_champion']:.3f} | {r['coverage_10_90_challenger']:.3f} |")
    return "\n".join(lines)


def overall_verdicts(results: list, stats: list) -> dict:
    out = {}
    for stat in stats:
        verdicts = [r["verdict_crps_full"] for r in results if r["stat"] == stat and r["status"] == "OK"]
        out[stat] = "CEILING_POSITIVE" if verdicts and all(v == "CEILING_POSITIVE" for v in verdicts) \
            else "CEILING_ZERO"
    return out


def run(stats: list, corpora: list, out_dir: Path) -> dict:
    df, adv_match_rate = load_frame()
    champ_cols = build_player_features(df)
    for stat in stats:
        df[f"opp_allowed_{stat}_10"] = build_opp_allowed(df, stat)
    fam = load_tracking_family()
    df2, trk_cols, hus_cols, dm_cols = build_challenger_frame(df, fam)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_results = []
    per_corpus_artifacts = {}
    for corpus in corpora:
        results = [run_stat(df2, champ_cols, trk_cols, hus_cols, dm_cols, stat, corpus) for stat in stats]
        all_results.extend(results)
        artifact = {
            "corpus": corpus, "match_rates": match_rates_for_corpus(df2, corpus, trk_cols, hus_cols, dm_cols),
            "adv_join_match_rate": round(adv_match_rate, 4),
            "tracking_columns": {"player_tracking_prior_season": trk_cols,
                                  "hustle_prior_season": hus_cols, "defender_matchup_asof": dm_cols},
            "excluded_atlas_tables": EXCLUDED_ATLAS, "results": results,
            "markdown_summary": markdown_table(results), "edge_claimed": False,
        }
        path = out_dir / f"gate_b_tracking_ablation_{corpus.replace('-', '_')}.json"
        path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
        per_corpus_artifacts[corpus] = artifact
        print(f"=== {corpus} ===\n{artifact['markdown_summary']}\nwrote {path}")
    summary = {"stats": stats, "corpora": corpora, "overall_verdict_per_stat": overall_verdicts(all_results, stats),
               "not_verified": NOT_VERIFIED, "markdown_summary": markdown_table(all_results), "edge_claimed": False}
    (out_dir / "gate_b_tracking_ablation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"=== OVERALL ===\n{summary['markdown_summary']}\nverdicts: {summary['overall_verdict_per_stat']}")
    return {"per_corpus": per_corpus_artifacts, "summary": summary}


def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stats", default="pts,reb,ast")
    p.add_argument("--corpora", default="2023-24,2024-25")
    p.add_argument("--out", default="data/cache/gate_b/")
    args = p.parse_args()
    run([s.strip() for s in args.stats.split(",") if s.strip()],
        [c.strip() for c in args.corpora.split(",") if c.strip()], Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

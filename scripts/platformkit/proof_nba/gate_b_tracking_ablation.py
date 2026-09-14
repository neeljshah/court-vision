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
CEILING_ZERO (no improvement bigger than mde_80pct_crps_full was detected -- not proof of
exactly zero). NOT_TESTED overrides either when a family's columns are ALL constant in the
TRAIN frame after imputation (dead weight, not a measurement) -- see gate_b_diagnostics.
Overall verdict per stat: CEILING_POSITIVE only if positive on BOTH corpora.

REVIEW-ROUND CORRECTIONS (vs the first landed cut, 08727448f): match rates now report both
join_rate (merge indicator) and nonnull_rate (first-column notna, can be lower when a row
joins but its as-of stat itself is null for lack of prior games); a constant-in-train guard
prevents a degenerate {0,0,0} CI from reading as CEILING_ZERO; --seeds adds a
colsample_bytree<1 multi-seed stability check (colsample=1.0 is deterministic, so repeating
RNG_SEED alone proved nothing); mde_80pct and absolute CRPS levels are reported beside every
delta; a 2025-26 corpus path exists but is gated on player_adv_stats.parquet coverage.

CALIBRATION ONLY -- see the project's calibration-claims rule doc under .claude/rules/. `edge_claimed` is fixed False.
INVARIANTS: no src/kernel/api/intel edits; <=300 LOC; ASCII only; n_jobs=2.
Run: python -m scripts.platformkit.proof_nba.gate_b_tracking_ablation --stats pts,reb,ast \
     --corpora 2023-24,2024-25 --out data/cache/gate_b/ --seeds 13,7,101
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
from typing import Optional
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.platformkit.dist_metrics import crps_ensemble_rows  # noqa: E402
from scripts.platformkit.proof_nba.prop_game_model import (  # noqa: E402
    _delta_ci, _pinball_rows, _rd, build_opp_allowed,
    build_player_features, load_frame, lgb_quantiles, score_quantiles, split_corpus)
from scripts.platformkit.proof_nba.gate_b_diagnostics import (  # noqa: E402
    adv_stats_covers_2025_26, constant_in_train_families, match_rates_for_corpus,
    mde_80pct, overall_verdicts, markdown_table, seed_stability, tracking_feature_importance,
    within_2025_26_dm_only)

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
    "a 0 pct join rate for that table by construction, not a bug.",
    "the 2024-25 corpus trains on 2023-24, which has 0 pct defender_matchup coverage -- the "
    "defender-matchup-only ablation for 2024-25 is NOT_TESTED as a result, not a negative finding.",
    "the 2023-24 within-season split trains and tests on the SAME season; a season-constant "
    "player-level feature (a prior-season aggregate) is effectively a player fixed effect shared "
    "between train and test there, not proof of true out-of-sample generalisation.",
    "def_priorN_switches_per_game_asof is constant (0.0) across every non-null row in the source "
    "table itself, not only after imputation.",
]


def _prior_season(season: str) -> str:
    """'2024-25' -> '2023-24'. Season strings are YYYY-YY, so string comparison orders them."""
    start = int(str(season)[:4])
    return f"{start - 1}-{str(start)[-2:]}"


def join_prior_season(df: pd.DataFrame, table: pd.DataFrame, prefix: str) -> tuple:
    """Left-join a player-SEASON table onto df keyed by (player_id, df's PRIOR season).
    Asserts every matched row's table-season precedes the row's own season (no leakage).
    Returns (joined_df, feature_cols, matched_col) -- matched_col is a bool column name
    (merge-indicator based, survives in the frame for per-corpus join-rate reporting)."""
    keep = [c for c in table.columns if c not in ("player_id", "season", "player_name")
            and pd.api.types.is_numeric_dtype(table[c])]
    t = table[["player_id", "season"] + keep].rename(columns={c: f"{prefix}_{c}" for c in keep})
    t = t.rename(columns={"season": "_table_season"})
    d = df.copy()
    d["_prior_season"] = d["season"].astype(str).map(_prior_season)
    matched_col = f"_{prefix}_matched"
    merged = d.merge(t, left_on=["player_id", "_prior_season"], right_on=["player_id", "_table_season"],
                      how="left", indicator=matched_col)
    merged[matched_col] = merged[matched_col] == "both"
    if merged[matched_col].any():
        m = merged[matched_col]
        assert (merged.loc[m, "_table_season"] < merged.loc[m, "season"].astype(str)).all(), \
            f"{prefix}: prior-season join returned a same/future-season row"
    fcols = [f"{prefix}_{c}" for c in keep]
    merged = merged.drop(columns=["_prior_season", "_table_season"])
    return merged, fcols, matched_col


def join_game_asof(df: pd.DataFrame, table: pd.DataFrame, cols: list, prefix: str) -> tuple:
    """Left-join a player-GAME as-of table on (player_id, game_id). Returns (df, cols, matched_col)."""
    matched_col = f"_{prefix}_matched"
    merged = df.merge(table[["player_id", "game_id"] + cols], on=["player_id", "game_id"],
                       how="left", indicator=matched_col)
    merged[matched_col] = merged[matched_col] == "both"
    return merged, cols, matched_col


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
    """champion frame + all tracking-family columns. Returns (df, trk_cols, hus_cols, dm_cols,
    matched_cols) -- matched_cols = {"trk": colname, "hus": colname, "dm": colname}."""
    df2, trk_cols, trk_m = join_prior_season(df, fam["tracking"], "trk")
    df2, hus_cols, hus_m = join_prior_season(df2, fam["hustle"], "hus")
    df2, dm_cols, dm_m = join_game_asof(df2, fam["defender_matchup"], fam["dm_cols"], "dm")
    return df2, trk_cols, hus_cols, dm_cols, {"trk": trk_m, "hus": hus_m, "dm": dm_m}


def ceiling_verdict(ci: dict) -> str:
    """CI is on (champion_loss - challenger_loss); positive = challenger better."""
    if ci["ci_lo"] > 0:
        return "CEILING_POSITIVE"
    if ci["ci_hi"] < 0:
        return "CEILING_NEGATIVE"
    return "CEILING_ZERO"


def run_stat(df2: pd.DataFrame, champ_cols: list, trk_cols: list, hus_cols: list, dm_cols: list,
             stat: str, corpus: str, seeds: Optional[list] = None) -> dict:
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
    q_champ, q_chall, q_dm = (lgb_quantiles(xtr_c, ytr, xte_c), lgb_quantiles(xtr_h, ytr, xte_h),
                               lgb_quantiles(xtr_d, ytr, xte_d))
    ci_crps_full = _delta_ci(yte, q_champ, q_chall, game_ids, crps_ensemble_rows)
    ci_pb_full = _delta_ci(yte, q_champ, q_chall, game_ids, _pinball_rows)
    ci_crps_dm = _delta_ci(yte, q_champ, q_dm, game_ids, crps_ensemble_rows)

    fam_const = constant_in_train_families(train_df, {"tracking": trk_cols, "hustle": hus_cols,
                                                        "defender_matchup": dm_cols})
    full_dead = all(fam_const[f]["all_constant"] for f in ("tracking", "hustle", "defender_matchup"))
    verdict_full = "NOT_TESTED" if full_dead else ceiling_verdict(ci_crps_full)
    verdict_dm = "NOT_TESTED" if fam_const["defender_matchup"]["all_constant"] else ceiling_verdict(ci_crps_dm)

    s_champ, s_chall = score_quantiles(yte, q_champ), score_quantiles(yte, q_chall)
    result = {
        "stat": stat, "corpus": corpus, "status": "OK", **split_meta,
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "n_games_test": int(pd.unique(game_ids).size),
        "imputed_share_challenger": round(float(test_df[fcols_chall].isna().any(axis=1).mean()), 4),
        "family_constant_in_train": fam_const,
        "coverage_10_90_champion": s_champ["coverage_10_90"], "coverage_10_90_challenger": s_chall["coverage_10_90"],
        "champion_crps_level": round(s_champ["crps_approx"], 4),
        "challenger_crps_level": round(s_chall["crps_approx"], 4),
        "champion_pinball": s_champ["pinball_avg"], "challenger_pinball": s_chall["pinball_avg"],
        "delta_crps_full": {"positive_means_challenger_better": True, **_rd(ci_crps_full)},
        "delta_pinball_full": {"positive_means_challenger_better": True, **_rd(ci_pb_full)},
        "mde_80pct_crps_full": mde_80pct(ci_crps_full),
        "verdict_crps_full": verdict_full, "verdict_pinball_full": ceiling_verdict(ci_pb_full),
        "delta_crps_defender_matchup_only": {"positive_means_challenger_better": True, **_rd(ci_crps_dm)},
        "verdict_crps_defender_matchup_only": verdict_dm,
        "tracking_feature_importance_gain": tracking_feature_importance(
            xtr_h, ytr, trk_cols + hus_cols + dm_cols),
        "edge_claimed": False,
    }
    if seeds:
        result["seed_stability_full"] = seed_stability(train_df, test_df, fcols_champ, fcols_chall, stat, seeds)
    return result


def run(stats: list, corpora: list, out_dir: Path, seeds: Optional[list] = None) -> dict:
    df, adv_match_rate = load_frame()
    champ_cols = build_player_features(df)
    for stat in stats:
        df[f"opp_allowed_{stat}_10"] = build_opp_allowed(df, stat)
    fam = load_tracking_family()
    df2, trk_cols, hus_cols, dm_cols, matched_cols = build_challenger_frame(df, fam)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_corpora, waiting = [], []
    for c in corpora:
        (waiting if c == "2025-26" and not adv_stats_covers_2025_26() else run_corpora).append(c)

    all_results, per_corpus_artifacts = [], {}
    for corpus in run_corpora:
        results = [run_stat(df2, champ_cols, trk_cols, hus_cols, dm_cols, stat, corpus, seeds)
                   for stat in stats]
        all_results.extend(results)
        artifact = {
            "corpus": corpus,
            "match_rates": match_rates_for_corpus(df2, corpus, trk_cols, hus_cols, dm_cols, matched_cols),
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

    within_2025_26 = None
    if "2025-26" in corpora:
        if "2025-26" in waiting:
            print("waiting_on_Q20: data/player_adv_stats.parquet does not yet cover 2025-26 "
                  "(max game_date < 2025-10-01) -- skipping the 2025-26 corpus and its "
                  "within-season per-game-family variant.")
        else:
            within_2025_26 = [r for r in (within_2025_26_dm_only(df2, champ_cols, dm_cols, s)
                                           for s in stats) if r is not None]

    summary = {"stats": stats, "corpora": run_corpora, "waiting_on": waiting,
               "overall_verdict_per_stat": overall_verdicts(all_results, stats),
               "not_verified": NOT_VERIFIED, "markdown_summary": markdown_table(all_results),
               "within_2025_26_dm_only": within_2025_26, "edge_claimed": False}
    (out_dir / "gate_b_tracking_ablation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"=== OVERALL ===\n{summary['markdown_summary']}\nverdicts: {summary['overall_verdict_per_stat']}")
    return {"per_corpus": per_corpus_artifacts, "summary": summary}


def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stats", default="pts,reb,ast")
    p.add_argument("--corpora", default="2023-24,2024-25")
    p.add_argument("--out", default="data/cache/gate_b/")
    p.add_argument("--seeds", default="", help="comma-separated seeds for the colsample_bytree=0.8 stability check")
    args = p.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()] or None
    run([s.strip() for s in args.stats.split(",") if s.strip()],
        [c.strip() for c in args.corpora.split(",") if c.strip()], Path(args.out), seeds)
    return 0


if __name__ == "__main__":
    sys.exit(_main())

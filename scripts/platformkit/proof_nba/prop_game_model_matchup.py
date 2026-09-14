"""scripts.platformkit.proof_nba.prop_game_model_matchup -- Q15c: prop champion + published
per-game defender-matchup as-of features (rebounds first).

Candidate = the landed per-game prop champion (prop_game_model.py, S332) plus
defender_matchup_states' *_asof columns and def_n_prior, joined strictly as-of on
(player_id, game_id). def_priorN_switches_per_game_asof is DROPPED -- constant (0.0) in the
source table itself, not only after imputation (see gate_b_tracking_ablation.py's own
NOT_VERIFIED list); it carries zero information by construction.

Three cuts, all built by calling prop_game_model.split_corpus unmodified with a different
input frame/test_season -- no new splitting logic:
  (A) cross-season 2025-26: split_corpus(df, "2025-26") -> train = 2023-24 + 2024-25,
      embargoed 3 days before the 2025-26 season starts. DECISIVE.
  (B) within-2025-26: filtering df to season=="2025-26" alone makes split_corpus fall into
      its own within_season_fallback (70/30 date split, embargoed) -- the only season with
      near-complete defender_matchup coverage (join rate 0.9765). DECISIVE.
  (C) 2024-25 cross-season: split_corpus(df, "2024-25") -> train = 2023-24 only, which has a
      0 pct defender_matchup join rate by construction (the table starts 2024-10-22, inside
      the 2024-25 season). This trips the constant-in-train guard -> NOT_TESTED, not a
      measured negative. REPORTED ONLY, labelled WEAK. The 41 pct coverage figure is the
      TEST side (the 2024-25 season itself), not the train side.

Verdict per stat: PROMOTE only if cuts A and B are BOTH verdict_crps == AHEAD (game-clustered
bootstrap CI on CRPS excludes 0 in the candidate's favour) AND seed_stable on both (seeds
13/7/101, colsample_bytree=0.8); else HOLD, with the reason(s). Cut C never drives PROMOTE.

CALIBRATION ONLY -- no market comparison; no line archive joined here. `edge_claimed` fixed
False. See .claude/rules/no-edge-claims.md.
INVARIANTS: no src/kernel/api/intel edits; <=300 LOC; ASCII only; n_jobs=2.
Run: python -m scripts.platformkit.proof_nba.prop_game_model_matchup --stats reb,pts,ast \
     --out data/cache/props_game_model_matchup/
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.platformkit.dist_metrics import crps_ensemble_rows  # noqa: E402
from scripts.platformkit.proof_nba.prop_game_model import (  # noqa: E402
    _delta_ci, _pinball_rows, _rd, build_opp_allowed, build_player_features,
    load_frame, lgb_quantiles, score_quantiles, split_corpus)
from scripts.platformkit.proof_nba.gate_b_tracking_ablation import join_game_asof  # noqa: E402
from scripts.platformkit.proof_nba.gate_b_diagnostics import (  # noqa: E402
    constant_in_train_families, mde_80pct, seed_stability, tracking_feature_importance)

_NBA = _REPO / "data" / "domains" / "basketball_nba"
CHAMPION_VERSION_INCUMBENT = "prop_game_model v1"
CHAMPION_VERSION_CANDIDATE = "v1+matchup"
DROPPED_CONSTANT_COL = "def_priorN_switches_per_game_asof"
SEEDS = (13, 7, 101)
COLSAMPLE = 0.8
CUT_A, CUT_B, CUT_C = "A_cross_season_2025_26", "B_within_2025_26", "C_cross_season_2024_25_WEAK"

NOT_VERIFIED = [
    "single full-coverage season (2025-26); no second full-coverage corpus exists yet to "
    "replicate cut B -- reopen only when 2026-27 accrues.",
    "byte-identity train/inference fixture not built (matches Q15's own open item).",
    "no market comparison -- no player-prop line archive joined in this row; calibration only.",
    f"{DROPPED_CONSTANT_COL} is constant (0.0) across every non-null row in the source table "
    "itself, not only after imputation (same finding as gate_b_tracking_ablation.py).",
    "cut C (2024-25 cross-season) trains on 2023-24, which has 0 pct defender_matchup join "
    "rate by construction -- its guard verdict is NOT_TESTED, not a measured negative.",
]


def load_matchup_columns() -> tuple:
    """defender_matchup_states.parquet, *_asof columns + def_n_prior, DROPPED_CONSTANT_COL
    excluded. Returns (table, dm_cols)."""
    dmatch = pd.read_parquet(_NBA / "defender_matchup_states.parquet").rename(
        columns={"def_player_id": "player_id"})
    dm_cols = [c for c in dmatch.columns if c.endswith("_asof") and c != DROPPED_CONSTANT_COL] + ["def_n_prior"]
    dmatch = dmatch[["player_id", "game_id"] + dm_cols].drop_duplicates(["player_id", "game_id"])
    return dmatch, dm_cols


def build_candidate_frame(df: pd.DataFrame, dmatch: pd.DataFrame, dm_cols: list) -> tuple:
    """champion frame + defender_matchup *_asof columns, joined on (player_id, game_id).
    Thin wrapper around gate_b's join_game_asof -- same as-of contract, no new join logic."""
    return join_game_asof(df, dmatch, dm_cols, "dm")


def train_side_coverage(train_df: pd.DataFrame, dm_cols: list, matched_col: str) -> dict:
    """Train-side matchup coverage: join_rate (merge indicator) + nonnull_rate (first-col notna)."""
    return {"join_rate": round(float(train_df[matched_col].mean()), 4),
            "nonnull_rate": round(float(train_df[dm_cols[0]].notna().mean()), 4)}


def promote_or_hold(cut_a: dict, cut_b: dict) -> dict:
    """PROMOTE only if both decisive cuts (A, B) are AHEAD on CRPS with CI and seed-stable;
    else HOLD with the reason(s). Cut C is reported-only and never consulted here."""
    reasons = []
    for name, cut in (("A", cut_a), ("B", cut_b)):
        if cut.get("status") != "OK":
            reasons.append(f"cut {name}: {cut.get('status')}"); continue
        if cut["verdict_crps"] != "AHEAD":
            reasons.append(f"cut {name}: verdict_crps={cut['verdict_crps']}")
        stab = cut.get("seed_stability")
        if not stab or not stab.get("seed_stable"):
            reasons.append(f"cut {name}: seed_stable=False")
    return {"verdict": "HOLD" if reasons else "PROMOTE",
            "reasons": reasons or ["both cuts AHEAD with CI and seed-stable"]}


def _run_cut(champ_cols: list, dm_cols: list, dm_matched: str, stat: str, cut_name: str,
             train_df: pd.DataFrame, test_df: pd.DataFrame, split_meta: dict, weak: bool) -> dict:
    if len(train_df) < 200 or len(test_df) < 50:
        return {"stat": stat, "cut": cut_name, "status": "UNDERPOWERED_DATA", "weak": weak,
                "n_train": int(len(train_df)), "n_test": int(len(test_df)), "edge_claimed": False}
    fcols_champ = champ_cols + [f"opp_allowed_{stat}_10"]
    fcols_cand = fcols_champ + dm_cols
    ytr = train_df[stat].astype(float)
    yte = test_df[stat].astype(float).to_numpy()
    game_ids = test_df["game_id"].to_numpy()

    def _xy(cols):
        med = train_df[cols].median()
        return train_df[cols].fillna(med).fillna(0.0), test_df[cols].fillna(med).fillna(0.0)

    xtr_c, xte_c = _xy(fcols_champ)
    xtr_m, xte_m = _xy(fcols_cand)
    q_champ = lgb_quantiles(xtr_c, ytr, xte_c)
    q_cand = lgb_quantiles(xtr_m, ytr, xte_m)
    ci_crps = _delta_ci(yte, q_champ, q_cand, game_ids, crps_ensemble_rows)
    ci_pb = _delta_ci(yte, q_champ, q_cand, game_ids, _pinball_rows)

    fam_const = constant_in_train_families(train_df, {"defender_matchup": dm_cols})
    guard_blocked = fam_const["defender_matchup"]["all_constant"]
    stability = None if guard_blocked else seed_stability(
        train_df, test_df, fcols_champ, fcols_cand, stat, SEEDS, COLSAMPLE)

    s_champ, s_cand = score_quantiles(yte, q_champ), score_quantiles(yte, q_cand)
    return {
        "stat": stat, "cut": cut_name, "status": "OK", "weak": weak, **split_meta,
        "n_train": int(len(train_df)), "n_test": int(len(test_df)),
        "n_games_test": int(pd.unique(game_ids).size),
        "train_side_matchup_coverage": train_side_coverage(train_df, dm_cols, dm_matched),
        "imputed_share_candidate": round(float(test_df[fcols_cand].isna().any(axis=1).mean()), 4),
        "family_constant_in_train": fam_const["defender_matchup"],
        "champion_pinball": s_champ["pinball_avg"], "candidate_pinball": s_cand["pinball_avg"],
        "champion_crps_level": round(s_champ["crps_approx"], 4),
        "candidate_crps_level": round(s_cand["crps_approx"], 4),
        "coverage_10_90_champion": s_champ["coverage_10_90"],
        "coverage_10_90_candidate": s_cand["coverage_10_90"],
        "delta_crps": {"positive_means_candidate_better": True, **_rd(ci_crps)},
        "delta_pinball": {"positive_means_candidate_better": True, **_rd(ci_pb)},
        "mde_80pct_crps": mde_80pct(ci_crps),
        "verdict_crps": "NOT_TESTED" if guard_blocked else ci_crps["verdict"],
        "verdict_pinball": "NOT_TESTED" if guard_blocked else ci_pb["verdict"],
        "seed_stability": stability,
        "matchup_feature_importance_gain": tracking_feature_importance(xtr_m, ytr, dm_cols),
        "edge_claimed": False,
    }


def markdown_table(results: list) -> str:
    lines = ["candidate = landed per-game champion + published per-game defender-matchup "
             "as-of features; no market line; calibration only.", "",
             "| stat | cut | n_test | verdict_crps | delta_crps_ci | mde_80pct | seed_stable | weak |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["status"] != "OK":
            lines.append(f"| {r['stat']} | {r['cut']} | {r.get('n_test', 0)} | {r['status']} | "
                          f"- | - | - | {r['weak']} |")
            continue
        d = r["delta_crps"]
        stab = r["seed_stability"]["seed_stable"] if r["seed_stability"] else "n/a"
        lines.append(f"| {r['stat']} | {r['cut']} | {r['n_test']} | {r['verdict_crps']} | "
                      f"{d['point']:.4f} [{d['ci_lo']:.4f}, {d['ci_hi']:.4f}] | "
                      f"{r['mde_80pct_crps']:.4f} | {stab} | {r['weak']} |")
    return "\n".join(lines)


def run(stats: list, out_dir: Path) -> dict:
    df, adv_match_rate = load_frame()
    champ_cols = build_player_features(df)
    for stat in stats:
        df[f"opp_allowed_{stat}_10"] = build_opp_allowed(df, stat)
    dmatch, dm_cols = load_matchup_columns()
    df2, _, dm_matched = build_candidate_frame(df, dmatch, dm_cols)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_a, test_a, meta_a = split_corpus(df2, "2025-26")
    sdf_b = df2[df2["season"] == "2025-26"].reset_index(drop=True)
    train_b, test_b, meta_b = split_corpus(sdf_b, "2025-26")
    train_c, test_c, meta_c = split_corpus(df2, "2024-25")

    cuts, verdicts = {CUT_A: [], CUT_B: [], CUT_C: []}, {}
    for stat in stats:
        cut_a = _run_cut(champ_cols, dm_cols, dm_matched, stat, CUT_A, train_a, test_a, meta_a, False)
        cut_b = _run_cut(champ_cols, dm_cols, dm_matched, stat, CUT_B, train_b, test_b, meta_b, False)
        cut_c = _run_cut(champ_cols, dm_cols, dm_matched, stat, CUT_C, train_c, test_c, meta_c, True)
        cuts[CUT_A].append(cut_a); cuts[CUT_B].append(cut_b); cuts[CUT_C].append(cut_c)
        verdicts[stat] = promote_or_hold(cut_a, cut_b)

    champion_version = {"incumbent": CHAMPION_VERSION_INCUMBENT, "candidate": CHAMPION_VERSION_CANDIDATE}
    artifacts = {}
    for label, results in cuts.items():
        artifact = {"cut": label, "champion_version": champion_version, "matchup_columns": dm_cols,
                    "dropped_constant_column": DROPPED_CONSTANT_COL, "results": results,
                    "markdown_summary": markdown_table(results), "edge_claimed": False}
        path = out_dir / f"prop_game_model_matchup_{label}.json"
        path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
        artifacts[label] = artifact
        print(f"=== {label} ===\n{artifact['markdown_summary']}\nwrote {path}")

    all_results = [r for rs in cuts.values() for r in rs]
    summary = {"stats": stats, "champion_version": champion_version,
               "adv_join_match_rate": round(adv_match_rate, 4), "verdict_per_stat": verdicts,
               "not_verified": NOT_VERIFIED, "markdown_summary": markdown_table(all_results),
               "edge_claimed": False}
    (out_dir / "prop_game_model_matchup_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"=== SUMMARY ===\n{summary['markdown_summary']}\nverdicts: {verdicts}")
    return {"per_cut": artifacts, "summary": summary}


def _main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--stats", default="reb,pts,ast")
    p.add_argument("--out", default="data/cache/props_game_model_matchup/")
    args = p.parse_args()
    run([s.strip() for s in args.stats.split(",") if s.strip()], Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(_main())

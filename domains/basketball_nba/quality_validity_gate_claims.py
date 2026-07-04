"""Claims emission for the 3a predictive-validity gate + quality-index rankings.

Companion to quality_validity_gate.py (gate core). Publishes through the
SHARED CLAIMS CONTRACT (entity_key=player_id, same shape as
player_intel_shooting_claims.py) to:
    data/cache/intel_claims/nba_quality_claims.jsonl
    data/cache/intel_claims/nba_quality_answers.md

Emits 3 claims: the 3a gate verdict (gate_verdict kind), the
shooter_quality_v1 top-10 ranking, and the scorer_quality_v1 top-10 ranking.
Each ranking claim carries the Curry/Ellis face-validity diagnostic as a
REPORTED field, never a fitting target (spec Section 3b).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from domains.basketball_nba.quality_indices import BOXSCORE_PATH, SCORER_WEIGHTS, SHOOTER_WEIGHTS, QUALIFY_MIN_FGA, QUALIFY_MIN_GAMES
from domains.basketball_nba.quality_indices_score import run as run_indices
from domains.basketball_nba.quality_validity_gate import GateResult, run_gate

CLAIMS_PATH = Path("data/cache/intel_claims/nba_quality_claims.jsonl")
ANSWERS_PATH = Path("data/cache/intel_claims/nba_quality_answers.md")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ranking_rows(df: pd.DataFrame, score_col: str, top_n: int = 10) -> list[dict]:
    rows = []
    for i, row in df.head(top_n).iterrows():
        rows.append({
            "rank": int(i) + 1,
            "player_id": int(row["player_id"]),
            "player_name": row["player_name"],
            "value": round(float(row[score_col]), 4),
            "n": int(row["games"]),
            "coverage": round(float(row["coverage"]), 4),
        })
    return rows


def rank_of(df: pd.DataFrame, score_col: str, name: str) -> int:
    ranked = df.sort_values(score_col, ascending=False, na_position="last").reset_index(drop=True)
    match = ranked[ranked["player_name"] == name]
    return int(match.index[0]) + 1 if len(match) else -1


def build_gate_claim(gate: GateResult, computed_at: str) -> dict:
    return {
        "claim_id": "nba_quality_predictive_validity_gate_3a",
        "kind": "gate_verdict",
        "question": "Does shooter_quality_v1 predict future TS% better than the naive composite (pre-registered walk-forward gate)?",
        "criteria": {
            "gate": "3a_predictive_validity",
            "primary_target": "realized_ts_pct over [T, T+30d], forward_games>=8, on 329-qualifier pool",
            "comparison_statistic": "mean Spearman rho across cutoffs; paired bootstrap clustered by player on rho(shooter)-rho(naive)",
            "win_rule": "CI excludes 0 in favor AND sign holds >=3/4 folds AND replicates in 2025-26",
        },
        "verdict": gate.verdict,
        "mean_rho_shooter_quality_v1": round(gate.mean_rho_shooter, 4) if not np.isnan(gate.mean_rho_shooter) else None,
        "mean_rho_naive": round(gate.mean_rho_naive, 4) if not np.isnan(gate.mean_rho_naive) else None,
        "bootstrap_delta_ci": (
            {k: (round(v, 4) if isinstance(v, float) else v) for k, v in gate.bootstrap.items()}
            if gate.bootstrap else None
        ),
        "sign_holds_folds": f"{gate.sign_holds_folds}/{gate.n_folds}",
        "per_cutoff": gate.per_cutoff,
        "replication_2025_26": gate.replication,
        "source_files": [
            BOXSCORE_PATH,
            "data/cache/atlas_player_catch_shoot_vs_pullup.parquet",
            "data/cache/atlas_player_spacing_gravity.parquet",
            "data/cache/atlas_player_scoring_creation.parquet",
        ],
        "computed_at": computed_at,
        "caveats": [
            "Honest-null clause is BINDING: if the gate REJECTs, the naive composite "
            "(0.55*TS%+0.30*eFG%+0.15*FT%) stays canonical. REJECT is a recorded SUCCESS, not a failure.",
            "DIFFICULTY/GRAVITY pillars at each pre-T cutoff use same-season atlas style-share "
            "fields (playtype mix, gravity_score) as stable style descriptors, not efficiency; "
            "EFFICIENCY/VOLUME pillars are recomputed exactly from pre-T boxscore rows only.",
        ],
    }


def build_ranking_claim(claim_id: str, question: str, weights: dict, ranking_df: pd.DataFrame,
                         score_col: str, ellis_rank: int, curry_rank: int, n_qualifying: int,
                         source_files: list[str], extra_caveat: str, computed_at: str) -> dict:
    return {
        "claim_id": claim_id,
        "kind": "ranking",
        "question": question,
        "criteria": {
            "metric": score_col,
            "weights": weights,
            "floors": {"min_games": QUALIFY_MIN_GAMES, "min_fga": QUALIFY_MIN_FGA},
            "direction": "desc",
        },
        "ranking": _ranking_rows(ranking_df, score_col),
        "face_validity_diagnostic": {
            "type": "reported_never_a_fitting_target",
            "stephen_curry_rank": curry_rank,
            "keon_ellis_rank": ellis_rank,
            "n_qualifying": n_qualifying,
            "top_decile_cutoff_rank": max(1, n_qualifying // 10),
        },
        "source_files": [BOXSCORE_PATH] + source_files,
        "computed_at": computed_at,
        "n_considered": n_qualifying,
        "caveats": [
            "Weights DECLARED and FROZEN before scoring (basketball_truth_spec.json); "
            "never tuned to a named player's rank.",
            extra_caveat,
        ],
    }


def write_claims(claims: list[dict]) -> None:
    CLAIMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAIMS_PATH, "w", encoding="ascii") as f:
        for c in claims:
            f.write(json.dumps(c, ensure_ascii=True) + "\n")


def write_answers_md(gate: GateResult, claims: list[dict]) -> None:
    lines = ["# NBA Quality Indices -- Answers (auto-generated, do not hand-edit)", ""]
    lines.append(
        "Frozen spec: docs/research/intel-layer/basketball_truth_spec.json. "
        "Weights DECLARED before any player scored; narrative-fitting BANNED."
    )
    lines.append("")
    lines.append(f"## 3a Predictive-Validity Gate Verdict: **{gate.verdict}**")
    lines.append("")
    rho_s = f"{gate.mean_rho_shooter:.4f}" if not np.isnan(gate.mean_rho_shooter) else "N/A"
    rho_n = f"{gate.mean_rho_naive:.4f}" if not np.isnan(gate.mean_rho_naive) else "N/A"
    lines.append(f"- mean Spearman rho, shooter_quality_v1 = {rho_s}")
    lines.append(f"- mean Spearman rho, naive composite = {rho_n}")
    if gate.bootstrap:
        lines.append(
            f"- bootstrap delta (shooter - naive): mean={gate.bootstrap['mean_delta']:.4f}, "
            f"95% CI=[{gate.bootstrap['ci_lo']:.4f}, {gate.bootstrap['ci_hi']:.4f}] "
            f"(n_boot={gate.bootstrap['n_boot_effective']})"
        )
    lines.append(f"- sign holds in {gate.sign_holds_folds}/{gate.n_folds} folds (need >=3/4)")
    if gate.replication:
        lines.append(f"- 2025-26 replication: {gate.replication}")
    lines.append("")
    lines.append("### Per-cutoff detail")
    lines.append("")
    lines.append("| cutoff | status | n | rho_shooter | rho_naive | delta |")
    lines.append("|---|---|---|---|---|---|")
    for f in gate.per_cutoff:
        if f["status"] == "OK":
            lines.append(
                f"| {f['cutoff']} | OK | {f['n_players']} | {f['rho_shooter']:.4f} | "
                f"{f['rho_naive']:.4f} | {f['delta']:+.4f} |"
            )
        else:
            lines.append(f"| {f['cutoff']} | {f['status']} | -- | -- | -- | -- |")
    lines.append("")
    lines.append(
        "**Honest-null clause (binding):** if this gate REJECTs, the naive composite "
        "(0.55*TS%+0.30*eFG%+0.15*FT%) stays canonical and this is a recorded SUCCESS."
    )
    lines.append("")
    for c in claims:
        if c["kind"] != "ranking":
            continue
        lines.append(f"## {c['question']}")
        fv = c.get("face_validity_diagnostic", {})
        if fv:
            lines.append(
                f"- FACE-VALIDITY DIAGNOSTIC (reported, never targeted): Stephen Curry rank "
                f"{fv['stephen_curry_rank']}/{fv['n_qualifying']}, Keon Ellis rank "
                f"{fv['keon_ellis_rank']}/{fv['n_qualifying']} (top-decile cutoff = rank <= {fv['top_decile_cutoff_rank']})"
            )
        lines.append("")
        lines.append("| rank | player | value | coverage | games |")
        lines.append("|---|---|---|---|---|")
        for r in c["ranking"]:
            lines.append(f"| {r['rank']} | {r['player_name']} | {r['value']} | {r['coverage']} | {r['n']} |")
        lines.append("")
    ANSWERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANSWERS_PATH.write_text("\n".join(lines), encoding="ascii")


def run() -> GateResult:
    gate = run_gate()
    idx = run_indices()
    computed_at = _now_iso()
    n_qualifying = len(idx.factor_table)

    claims = [build_gate_claim(gate, computed_at)]
    claims.append(build_ranking_claim(
        "nba_shooter_quality_v1_full_season_2024_25",
        "Top 10 shooter_quality_v1 (full season 2024-25, DECLARED/frozen weights, NOT market-fitted)",
        SHOOTER_WEIGHTS, idx.shooter, "shooter_quality_v1",
        ellis_rank=rank_of(idx.shooter, "shooter_quality_v1", "Keon Ellis"),
        curry_rank=rank_of(idx.shooter, "shooter_quality_v1", "Stephen Curry"),
        n_qualifying=n_qualifying,
        source_files=[
            "data/cache/atlas_player_shot_clock_scoring.parquet",
            "data/cache/atlas_player_catch_shoot_vs_pullup.parquet",
            "data/cache/atlas_player_spacing_gravity.parquet",
        ],
        extra_caveat=(
            "Adopted as canonical ONLY if gate 3a ships it (see "
            "nba_quality_predictive_validity_gate_3a claim); until then the naive composite is canonical."
        ),
        computed_at=computed_at,
    ))
    claims.append(build_ranking_claim(
        "nba_scorer_quality_v1_full_season_2024_25",
        "Top 10 scorer_quality_v1 (full season 2024-25, DECLARED/frozen weights, NOT market-fitted)",
        SCORER_WEIGHTS, idx.scorer, "scorer_quality_v1",
        ellis_rank=rank_of(idx.scorer, "scorer_quality_v1", "Keon Ellis"),
        curry_rank=rank_of(idx.scorer, "scorer_quality_v1", "Stephen Curry"),
        n_qualifying=n_qualifying,
        source_files=[
            "data/cache/atlas_player_usage_role.parquet",
            "data/cache/atlas_player_scoring_creation.parquet",
            "data/cache/atlas_player_vs_scheme_splits.parquet",
            "data/cache/atlas_player_score_margin_splits.parquet",
            "data/cache/atlas_player_clutch_scoring.parquet",
            "data/cache/atlas_player_situational_splits.parquet",
        ],
        extra_caveat=(
            "Not adopted as canonical unless a scorer-specific predictive gate is separately "
            "run (gate 3a tests shooter_quality_v1 only, per spec)."
        ),
        computed_at=computed_at,
    ))

    write_claims(claims)
    write_answers_md(gate, claims)
    return gate


if __name__ == "__main__":
    gate = run()
    print(f"VERDICT: {gate.verdict}")
    print(f"wrote claims to {CLAIMS_PATH}")
    print(f"wrote answers to {ANSWERS_PATH}")

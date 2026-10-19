"""S450: MLB starting-pitcher strikeout distribution -- three arms, REPORT ONLY.

CLI:
  python -m scripts.platformkit.eval_gate.mlb_pitcher_k_distribution \\
      --gamelogs <parquet> --fit-start 2022-01-01 --fit-end 2023-12-31 \\
      --holdout-a 2024-01-01 --holdout-b 2025-01-01 --out <json> \\
      --seed 13 --draws 2000
  ... --fixtures --out <json>   # tiny embedded dataset, no file read, for smoke-testing

Fold boundaries are the CLI's own day-level date flags (2026's holdout is a
partial year); fold LABELS reused from props_eval_gate_mlb_constants.CORPORA
(unedited) name this row's folds as Lane 3/Lane 4's are. Construct/fixture
module -- no network, no data/registry write, no financial vocabulary (Q6).
Verdict words: ACCEPT/REJECT/NULL/SINGLE-WINDOW/INSUFFICIENT. Run the
per-file test (full pytest freezes the box):
  python -m pytest tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from domains.mlb.props_eval_gate_mlb_constants import CORPORA
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_cpcv import (
    score_holdout_via_cpcv,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_fit import (
    enrich_manifest, fit_beta_grid, fit_r_grid, score_row_all_arms,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_launch import (
    launch_gate as _launch_gate, launch_gate_bound_check as _launch_gate_bound_check,
    launch_gate_charge as _launch_gate_charge, launch_gate_validate as _launch_gate_validate,
    parse_args as _parse_args, resolve_path_targets as _resolve_path_targets,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_history import clear_memo
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_manifest import (
    ORDINAL_COL, build_start_manifest, manifest_columns_refusal,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_realrun import (
    aggregate_arm, build_paired_losses, compute_c_vs_b, cpcv_derive_fit_rows,
    paired_ci, split_folds, verdict_for_pair,
)
from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_seal import (
    file_identity, raw_file_identity,
)

FOLD_LABELS = tuple(CORPORA.keys())  # ("fit_2022_2023", "holdout_2024", "holdout_2025_2026")
ARMS = ("A", "B", "C")


def observed_corpus_end(df: pd.DataFrame) -> Optional[str]:
    """AMENDMENT 10(b): the corpus's own observed max date (ISO YYYY-MM-DD),
    compared against the sealed holdout_b_end BEFORE any charge -- never used
    to derive the scored window (AMENDMENT 9(a): that stays --holdout-b-end).
    None if "date" is absent or not itself a Series (AMENDMENT 12(a): a
    date-free corpus used to crash here, `None` has no `.dropna()`); never
    raises."""
    col = df["date"] if "date" in df.columns else None
    if not isinstance(col, pd.Series):
        return None
    dates = pd.to_datetime(col, errors="coerce")
    valid = dates.dropna()
    if valid.empty:
        return None
    return str(valid.max().date())


def score_fold(fold_rows: List[dict], df: pd.DataFrame, r: float, beta: float) -> List[dict]:
    return [score_row_all_arms(df, row, r, beta) for row in fold_rows]


def fit_block(best_r, r_scores, r_meta, best_beta=None, beta_scores=None, beta_meta=None) -> dict:
    beta_scores = beta_scores or {}
    beta_meta = beta_meta or {"n_considered": 0, "n_common": 0, "grid_common_abstained": 0}
    return {
        "best_r": best_r, "r_grid_scores": {str(k): v for k, v in r_scores.items()},
        "r_grid_common_abstained": r_meta["grid_common_abstained"], "r_n_common": r_meta["n_common"],
        "best_beta": best_beta, "beta_grid_scores": {str(k): v for k, v in beta_scores.items()},
        "beta_grid_common_abstained": beta_meta["grid_common_abstained"],
        "beta_n_common": beta_meta["n_common"],
    }


def insufficient_fit_report(reason: str, fb: dict, manifest_refusals, fold_n_eligible,
                            fold_unassigned, n_fit_purged: int, seed: int, n_boot: int) -> dict:
    return {
        "verdict": "INSUFFICIENT", "verdict_reason": reason, "fit": fb,
        "manifest_refusals": manifest_refusals, "fold_n_eligible": fold_n_eligible,
        "fold_unassigned": fold_unassigned,
        "fit_rows_purged_near_boundary": n_fit_purged, "folds": {}, "paired_ci": {},
        "paired_losses": [], "null": {}, "seed": seed, "n_boot": n_boot}


def build_report(gamelogs_df: pd.DataFrame, fit_range, holdout_a_range, holdout_b_range,
                 *, seed: int, n_boot: int) -> dict:
    clear_memo()  # FIX 1q: never start or leave the history memo pinned (finding 1)
    try:
        manifest, manifest_refusals = build_start_manifest(gamelogs_df)
        rows = enrich_manifest(gamelogs_df, manifest)
        folds, fold_unassigned = split_folds(rows, fit_range, holdout_a_range, holdout_b_range, FOLD_LABELS)
        fold_n_eligible = {label: len(folds[label]) for label in FOLD_LABELS}

        fit_rows_raw = folds[FOLD_LABELS[0]]
        holdout_rows = folds[FOLD_LABELS[1]] + folds[FOLD_LABELS[2]]
        fit_rows, split_id, n_fit_purged = cpcv_derive_fit_rows(fit_rows_raw, holdout_rows)

        best_r, r_scores, r_meta = fit_r_grid(fit_rows, gamelogs_df)
        if best_r is None:
            return insufficient_fit_report("r_grid_insufficient", fit_block(best_r, r_scores, r_meta),
                                           manifest_refusals, fold_n_eligible, fold_unassigned,
                                           n_fit_purged, seed, n_boot)

        best_beta, beta_scores, beta_meta = fit_beta_grid(fit_rows, gamelogs_df, best_r)
        if best_beta is None:
            return insufficient_fit_report(
                "beta_grid_insufficient", fit_block(best_r, r_scores, r_meta, best_beta, beta_scores, beta_meta),
                manifest_refusals, fold_n_eligible, fold_unassigned, n_fit_purged, seed, n_boot)

        scored_by_fold: Dict[str, List[dict]] = {}
        scored_enriched_by_fold: Dict[str, List[dict]] = {}
        abstain_reasons: Dict[str, Dict[str, int]] = {}

        # FIT fold: descriptive-only scoring vs the full corpus (AMENDMENT 1(e)).
        label = FOLD_LABELS[0]
        results = score_fold(folds[label], gamelogs_df, best_r, best_beta)
        scored, scored_enriched, reasons = [], [], {}
        for row, res in zip(folds[label], results):
            if res["status"] == "scored":
                res["split_id"] = None
                scored.append(res)
                scored_enriched.append(row)
            else:
                reasons[res["reason"]] = reasons.get(res["reason"], 0) + 1
        scored_by_fold[label], scored_enriched_by_fold[label], abstain_reasons[label] = scored, scored_enriched, reasons

        # Holdout folds (AMENDMENT 6(a)/7(a)/8(a)): each row scored via its OWN
        # cpcv path's RAW-gamelog train-only df; K-rates recomputed from that df;
        # path-enriched state kept for the null. AMENDMENT 11(a): each holdout's
        # CPCV pool is every PRECEDING fold (raw_train_df's strict `< as_of` stays leak-free).
        train_dfs_by_fold: Dict[str, List[pd.DataFrame]] = {}
        cpcv_candidate_rows = list(fit_rows_raw)
        for label in FOLD_LABELS[1:]:
            holdout_rows = folds[label]
            path_results = score_holdout_via_cpcv(gamelogs_df, cpcv_candidate_rows, holdout_rows, best_r, best_beta)
            scored, scored_enriched, train_dfs, reasons = [], [], [], {}
            for res, path_id, train_df, path_row in path_results:
                if res["status"] == "scored":
                    res["split_id"] = path_id
                    scored.append(res)
                    scored_enriched.append(path_row)
                    train_dfs.append(train_df)
                else:
                    reasons[res["reason"]] = reasons.get(res["reason"], 0) + 1
            scored_by_fold[label], scored_enriched_by_fold[label], abstain_reasons[label] = scored, scored_enriched, reasons
            train_dfs_by_fold[label] = train_dfs
            cpcv_candidate_rows = cpcv_candidate_rows + holdout_rows

        fold_report: Dict[str, dict] = {}
        for label in FOLD_LABELS:
            scored = scored_by_fold[label]
            fold_report[label] = {
                "n_eligible": len(folds[label]), "n_scored": len(scored),
                "abstain_reasons": abstain_reasons[label],
                "arms": {arm: aggregate_arm(scored, arm) for arm in ARMS},
            }

        ci_holdout_a_ba = paired_ci(scored_by_fold[FOLD_LABELS[1]], "A", "B", seed, n_boot)
        ci_holdout_b_ba = paired_ci(scored_by_fold[FOLD_LABELS[2]], "A", "B", seed, n_boot)
        ci_holdout_a_cb = paired_ci(scored_by_fold[FOLD_LABELS[1]], "B", "C", seed, n_boot)
        ci_holdout_b_cb = paired_ci(scored_by_fold[FOLD_LABELS[2]], "B", "C", seed, n_boot)
        c_vs_b_verdict, null_block = compute_c_vs_b(
            train_dfs_by_fold[FOLD_LABELS[1]], scored_enriched_by_fold[FOLD_LABELS[1]], scored_by_fold[FOLD_LABELS[1]],
            train_dfs_by_fold[FOLD_LABELS[2]], scored_enriched_by_fold[FOLD_LABELS[2]], scored_by_fold[FOLD_LABELS[2]],
            best_r, best_beta, seed, ci_holdout_a_cb, ci_holdout_b_cb)

        return {
            "fit": fit_block(best_r, r_scores, r_meta, best_beta, beta_scores, beta_meta),
            "manifest_refusals": manifest_refusals, "fit_rows_purged_near_boundary": n_fit_purged,
            "fold_unassigned": fold_unassigned, "cpcv_fit_split_id": split_id,
            "folds": fold_report, "null": null_block,
            "paired_losses": build_paired_losses(scored_by_fold, best_r, best_beta),
            "paired_ci": {
                "B_vs_A": {"holdout_2024": ci_holdout_a_ba, "holdout_2025_2026": ci_holdout_b_ba,
                          "verdict": verdict_for_pair(ci_holdout_a_ba, ci_holdout_b_ba)},
                "C_vs_B": {"holdout_2024": ci_holdout_a_cb, "holdout_2025_2026": ci_holdout_b_cb,
                          "verdict": c_vs_b_verdict},
            },
            "seed": seed, "n_boot": n_boot,
        }
    finally:
        clear_memo()


def _fixture_gamelogs() -> pd.DataFrame:
    """Tiny embedded construct dataset (schema per S450_spec.md fact (f)); no
    parquet read, no network. Intentionally below MIN_FOLD_N per fold -- an
    INSUFFICIENT verdict here is the honest, expected outcome of a fixture run."""
    rows = []
    pid, opp_pid = 100, 200
    for i in range(6):
        date = f"2022-04-{10 + i:02d}"
        rows.append(dict(game_pk=1000 + i, date=date, team="A", player_id=pid,
                         is_pitcher=True, battersFaced=24, pitch_strikeOuts=6 + (i % 3),
                         hits_allowed=5, baseOnBalls_allowed=2, inningsPitched=6.0,
                         **{ORDINAL_COL: 0}))
        rows.append(dict(game_pk=1000 + i, date=date, team="B", player_id=opp_pid,
                         is_pitcher=True, battersFaced=23, pitch_strikeOuts=5,
                         hits_allowed=6, baseOnBalls_allowed=1, inningsPitched=5.2,
                         **{ORDINAL_COL: 0}))
        for b in range(4):
            rows.append(dict(game_pk=1000 + i, date=date, team="B", player_id=300 + b,
                             is_pitcher=False, atBats=4, baseOnBalls=0, hitByPitch=0,
                             strikeOuts=1, hits=1, totalBases=1, runs=0, rbi=0,
                             homeRuns=0, stolenBases=0))
    return pd.DataFrame(rows)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)

    # AMENDMENT 13(a): resolve paths first; refuse before any read/write.
    path_refusal = _resolve_path_targets(args)
    if path_refusal is not None:
        print(f"refused: {path_refusal}")
        return 1

    identity: Dict[str, dict] = {}
    if args.fixtures:
        # --fixtures stays explicitly uncharged/unsealed (no corpus bound).
        df = _fixture_gamelogs()
        identity["gamelogs"] = {"path": "FIXTURES (embedded, no file read)", "bytes": 0, "sha256": None}
        launch, refusal = _launch_gate(args)
        if refusal is not None:
            print(f"refused: {refusal}")
            return 1
    else:
        if not args.gamelogs:
            raise SystemExit("--gamelogs is required unless --fixtures is given")
        # AMENDMENT 10(b)/11(b): validate prereg (no charge), read the
        # corpus, compare its observed max date to sealed holdout_b_end,
        # ONLY THEN charge; any difference refuses holdout_b_end_mismatch.
        validated, refusal = _launch_gate_validate(args)
        if refusal is not None:
            print(f"refused: {refusal}")
            return 1
        path = Path(args.gamelogs)
        identity["gamelogs"] = raw_file_identity(path)
        df = pd.read_parquet(path)
        observed_end = observed_corpus_end(df)
        # AMENDMENT 14(c): the non-charging bound comparison runs right
        # after the corpus read, BEFORE the manifest-column guard -- a
        # date-free corpus refuses holdout_b_end_mismatch first, never
        # ordinal_column_absent.
        bound_refusal = _launch_gate_bound_check(validated, observed_end)
        if bound_refusal is not None:
            print(f"refused: {bound_refusal}")
            return 1
        # AMENDMENT 12(f)/13(b): pre-charge guard, no K on a certain
        # INSUFFICIENT -- see manifest_columns_refusal's docstring.
        column_refusal = manifest_columns_refusal(df)
        if column_refusal is not None:
            print(f"refused: {column_refusal}")
            return 1
        launch, refusal = _launch_gate_charge(args, validated, observed_end)
        if refusal is not None:
            print(f"refused: {refusal}")
            return 1

    fit_range = (pd.Timestamp(args.fit_start), pd.Timestamp(args.fit_end))
    holdout_a_start = pd.Timestamp(args.holdout_a)
    holdout_b_start = pd.Timestamp(args.holdout_b)
    holdout_a_range = (holdout_a_start, holdout_b_start - pd.Timedelta(days=1))
    # AMENDMENT 9(a): holdout_b's end is the SEALED value, never
    # df["date"].max() -- a row past this fixed bound is outside_declared_
    # corpora (split_folds), never scored (params_mismatch refused above).
    holdout_b_range = (holdout_b_start, pd.Timestamp(args.holdout_b_end))

    report = build_report(df, fit_range, holdout_a_range, holdout_b_range,
                          seed=args.seed, n_boot=args.draws)
    report["input_identity"] = identity
    report["launch"] = launch
    report["fold_date_ranges"] = {
        FOLD_LABELS[0]: [str(fit_range[0].date()), str(fit_range[1].date())],
        FOLD_LABELS[1]: [str(holdout_a_range[0].date()), str(holdout_a_range[1].date())],
        FOLD_LABELS[2]: [str(holdout_b_range[0].date()), str(holdout_b_range[1].date())],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, sort_keys=True, allow_nan=False, indent=2)
    out_path.write_text(text, encoding="ascii")
    print(f"wrote {out_path} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

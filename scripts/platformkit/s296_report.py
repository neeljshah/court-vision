"""S296 reporting leaf: seals, paths, paired-CI summary, fold table, artifacts, memo."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evidence/harness"
DATE = "2026-09-07"
FIELDS = ("min", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk", "tov", "fgm", "fga",
          "fg3m", "fg3a", "ftm", "fta", "pf", "plus_minus")
PREREGS = (OUT / "S296_full_boxscore_oof_2026-09-04_prereg.md",
           OUT / "S296_full_boxscore_oof_2026-09-04_prereg_attempt2.md",
           OUT / "S296_full_boxscore_oof_2026-09-07_prereg_supplement.md")
SAMPLES = OUT / "S296_full_boxscore_oof_{0}_samples.parquet".format(DATE)
PAIRED = OUT / "S296_full_boxscore_oof_{0}_paired_losses.parquet".format(DATE)
FOLDS = OUT / "S296_full_boxscore_oof_{0}_fold_dates.json".format(DATE)
SUMMARY = OUT / "S296_full_boxscore_oof_{0}.json".format(DATE)
MEMO = OUT / "S296_full_boxscore_oof_{0}.md".format(DATE)
BOOTSTRAPS, MIN_FOLD_GAMES = 500, 30
DIAGNOSTIC_SUFFIXES = ("_below_q10", "_above_q90", "_atom_q10_eq_q90")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal() -> dict[str, str]:
    """Verify every prereg seal against the file bytes above its seal line."""
    seals = {}
    for prereg in PREREGS:
        raw = prereg.read_bytes().replace(b"\r\n", b"\n")
        prefix, suffix = raw.split(b"SEAL_SHA256:", 1)
        value = suffix.splitlines()[0].strip().decode("ascii")
        if hashlib.sha256(prefix).hexdigest() != value:
            raise AssertionError("prereg seal mismatch: {0}".format(prereg.name))
        seals[prereg.relative_to(ROOT).as_posix()] = value
    return seals


def _summary(records: list[dict]) -> dict[str, Any]:
    scores = pd.DataFrame([record["scores"] for record in records])
    names = [name[len("candidate_"):] for name in scores.columns if name.startswith("candidate_")]
    delta = pd.DataFrame({name: scores["baseline_" + name].to_numpy() - scores["candidate_" + name].to_numpy()
                          for name in names})
    delta["game_id"] = [record["game_id"] for record in records]
    grouped = delta.groupby("game_id", sort=True).mean()
    matrix, n_games = grouped.to_numpy(), len(grouped)
    draws = np.random.default_rng(296).integers(0, n_games, size=(BOOTSTRAPS, n_games))
    summary: dict[str, Any] = {"metrics": {}, "coverage": {}, "diagnostics": {},
        "n_game_clusters": int(n_games), "n_rows": len(records)}
    for position, name in enumerate(grouped.columns):
        candidate, baseline = scores["candidate_" + name].to_numpy(), scores["baseline_" + name].to_numpy()
        boot = matrix[:, position][draws].mean(axis=1)
        if name.endswith("_inside80"):
            summary["coverage"][name[:-len("_inside80")]] = {"nominal": 0.80, "n": len(records),
                "n_game_clusters": int(n_games), "baseline": float(baseline.mean()),
                "candidate": float(candidate.mean()),
                "candidate_minus_baseline": float(candidate.mean() - baseline.mean()),
                "difference_ci95": [float(-np.quantile(boot, .975)), float(-np.quantile(boot, .025))]}
        elif name.endswith(DIAGNOSTIC_SUFFIXES):
            summary["diagnostics"][name] = {"n": len(records), "baseline": float(baseline.mean()),
                "candidate": float(candidate.mean())}
        else:
            summary["metrics"][name] = {"n": len(records), "n_game_clusters": int(n_games),
                "baseline": float(baseline.mean()), "candidate": float(candidate.mean()),
                "improvement": float(baseline.mean() - candidate.mean()),
                "improvement_ci95": [float(np.quantile(boot, .025)), float(np.quantile(boot, .975))]}
    return summary


def _fold_table(records: list[dict]) -> dict[str, Any]:
    folds = {}
    for split in sorted({record["split_id"] for record in records}):
        rows = [record for record in records if record["split_id"] == split]
        games = {record["game_id"] for record in rows}
        folds[str(split)] = {"min_date": min(row["ts"][:10] for row in rows),
            "max_date": max(row["ts"][:10] for row in rows), "n_rows": len(rows),
            "n_held_out_games": len(games),
            "status": "SCORED" if len(games) >= MIN_FOLD_GAMES else "NOT SCORABLE"}
    return folds


def _memo(summary: dict[str, Any], folds: dict[str, Any]) -> str:
    rows = ["# S296 strict-prior full-boxscore OOF (2026-09-07)", "", "## Result", "",
        "SINGLE-WINDOW calibration comparison. Improvement is baseline loss minus candidate loss; positive means",
        "candidate better. CRPS, pinball and energy carry their own units, so the frozen +0.004 bar is not their",
        "threshold and nothing here is compared against it. All comparative NULL results are valid.", "",
        "| Field | CRPS base | CRPS cand | CRPS improvement | CRPS 95 pct CI | q50 pinball improvement |"
        " Coverage base | Coverage cand | below q10 | above q90 | q10==q90 atom |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|"]
    for field in FIELDS:
        crps, pin = summary["metrics"][field + "_crps"], summary["metrics"][field + "_pinball_q50"]
        cov, diag = summary["coverage"][field], summary["diagnostics"]
        rows.append("| {0} | {1:.6f} | {2:.6f} | {3:.6f} | [{4:.6f}, {5:.6f}] | {6:.6f} | {7:.4f} | {8:.4f} |"
            " {9:.4f} | {10:.4f} | {11:.4f} |".format(field, crps["baseline"], crps["candidate"],
            crps["improvement"], crps["improvement_ci95"][0], crps["improvement_ci95"][1], pin["improvement"],
            cov["baseline"], cov["candidate"], diag[field + "_below_q10"]["candidate"],
            diag[field + "_above_q90"]["candidate"], diag[field + "_atom_q10_eq_q90"]["candidate"]))
    rows += ["", "Denominators: every field row scores n = {0} held-out player-games in {1} game clusters;"
        " nominal q10-q90 coverage is 0.80.".format(summary["n_rows"], summary["n_game_clusters"]), "",
        "| Joint metric | Baseline | Candidate | Improvement | Paired 95 pct CI |", "|---|---:|---:|---:|---|"]
    for name in ("energy", "energy_train_scaled", "coherence_violation"):
        metric = summary["metrics"][name]
        rows.append("| {0} | {1:.6f} | {2:.6f} | {3:.6f} | [{4:.6f}, {5:.6f}] |".format(name, metric["baseline"],
            metric["candidate"], metric["improvement"], metric["improvement_ci95"][0], metric["improvement_ci95"][1]))
    rows += ["", "## Folds", "", "| Split | Dates | Rows | Held-out games | Status |", "|---|---|---:|---:|---|"]
    for split, fold in sorted(folds.items()):
        rows.append("| {0} | {1} .. {2} | {3} | {4} | {5} |".format(split, fold["min_date"], fold["max_date"],
            fold["n_rows"], fold["n_held_out_games"], fold["status"]))
    rows += ["", "## Reproduction", "",
        "- Shared vector CPCV used one stable player-game state per scored tick, the inherited purge, and a",
        "  symmetric one-day embargo; every source tick is a test state exactly once.",
        "- Samples are archived as source-state keys and reconstruct from the re-emitted observed-field table.",
        "- No future-label reads: the predictor selects only evaluator-supplied states strictly earlier than each",
        "  test timestamp, and the test view has its outcome vector removed under strict redaction.",
        "- Every per-field q10/q50/q90, pinball, coverage, exceedance and atom figure is in the JSON summary;",
        "  the per-state paired losses are in the paired-losses parquet.", "",
        "## NOT VERIFIED", "",
        "- Sample box-score algebra holds by construction: both arms resample observed source vectors, so the",
        "  coherence-violation count is a property of the resampling, not evidence that a model learned coherence.",
        "- A second independent corpus, any AHEAD promotion, or anything beyond SINGLE-WINDOW calibration.",
        "- Missing roster records: neither source carries an as-of roster, so players with no row are unobservable.",
        "- Live, deployment or forward-operating behaviour."]
    return "\n".join(rows) + "\n"


def _write(frame: pd.DataFrame, records: list[dict], inputs: dict[str, Any], before: float, after: float,
           preflight_table: dict[str, Any], premise: dict[str, Any], route: Iterable[Path],
           config: dict[str, Any]) -> dict[str, Any]:
    record_by_key = {record["stable_key"]: record for record in records}
    if len(record_by_key) != len(frame) or not all(record["evaluator_output"] for record in records):
        raise AssertionError("every source tick must have exactly one evaluator record")
    sample_rows, paired_rows = [], []
    for row in frame.itertuples(index=False):
        key = "{0}|{1}".format(row.game_id, row.player_id)
        record = record_by_key[key]
        forecast = record["forecast"]
        sample = {"stable_key": key, "game_id": str(row.game_id), "player_id": int(row.player_id),
            "date": str(pd.Timestamp(row.date).date()), "starter": bool(row.starter),
            "cold_start_zero": forecast["cold_start_zero"], "used_player_prior": forecast["used_player_prior"],
            "observed_dnp": int(float(getattr(row, "min")) == 0.0),
            "candidate_sample_keys_json": json.dumps(forecast["candidate_keys"]),
            "baseline_sample_keys_json": json.dumps(forecast["baseline_keys"])}
        ordered = {arm: np.sort(forecast[arm], axis=0) for arm in ("candidate", "baseline")}
        for index, field in enumerate(FIELDS):
            sample["observed_" + field] = float(getattr(row, field))
            for arm in ("candidate", "baseline"):
                sample[arm + "_q10_" + field] = float(ordered[arm][2, index])
                sample[arm + "_q50_" + field] = float(ordered[arm][12, index])
                sample[arm + "_q90_" + field] = float(ordered[arm][22, index])
        sample_rows.append(sample)
        paired_rows.append({"stable_key": key, "game_id": str(row.game_id), "player_id": int(row.player_id),
            "ts": record["ts"], "split_id": record["split_id"], "n_train": record["n_train"],
            "losses_json": json.dumps(record["scores"], sort_keys=True),
            "candidate_sample_keys_json": sample["candidate_sample_keys_json"],
            "baseline_sample_keys_json": sample["baseline_sample_keys_json"]})
    pd.DataFrame(sample_rows).to_parquet(SAMPLES, index=False)
    pd.DataFrame(paired_rows).to_parquet(PAIRED, index=False)
    folds = _fold_table(records)
    FOLDS.write_text(json.dumps(folds, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    summary = _summary(records)
    summary.update({"gap_id": "S296", "date": DATE, "preregistration_seals": _seal(), "premise": premise,
        "s292_preflight": preflight_table, "inputs": inputs, "fields": list(FIELDS), "folds": folds,
        "n_dnp": premise["observed_dnp_zero_minute_rows"], "n_bench": premise["bench_rows"],
        "n_cold_start_zero": int(sum(row["cold_start_zero"] for row in sample_rows)),
        "n_league_fallback": int(sum(1 - row["used_player_prior"] for row in sample_rows)),
        "rss_mb_before": before, "rss_mb_after": after,
        "artifacts": {path.relative_to(ROOT).as_posix(): path.stat().st_size for path in (SAMPLES, PAIRED, FOLDS)},
        "route_sha256": {path.relative_to(ROOT).as_posix(): _sha(path) for path in route}})
    summary.update(config)
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    MEMO.write_text(_memo(summary, folds), encoding="utf-8", newline="\n")
    return summary

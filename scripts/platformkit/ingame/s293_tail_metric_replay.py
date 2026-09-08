"""Regenerate S272 per-tick calibration losses with S293 metric diagnostics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from scripts.platformkit.eval_gate.cpcv_tail_metrics import (
    EPSILON, log_loss_values, refuse_mixed_grain, reliability_table, trailing_side,
)
from scripts.platformkit.eval_gate.scoring import ece
from scripts.platformkit.ingame import s272_ingame_tail_recal as s272

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/evidence/harness"
STEM = "S293_tail_metric_rail_attempt2_2026-09-07"
PREREG = EVIDENCE / "S293_tail_metric_rail_prereg_attempt2_2026-09-07.md"
S272_CSV = EVIDENCE / "S272_ingame_tail_recal_screen_2026-09-04_paired_losses.csv"
S272_SUMMARY = EVIDENCE / "S272_ingame_tail_recal_screen_2026-09-04_summary.json"
FIXED = {
    "scripts/platformkit/eval_gate/cpcv_engine.py": "5accfbe490031acb084a8e4375a082b00d842cf4011a76c6d27dfc2c7db614a5",
    "scripts/platformkit/eval_gate/walkforward.py": "c8a9b5b0f0f7c84dc5fdb0c7a4a27e0f7f2040f99326ef5376cde011df27bc2e",
    "scripts/platformkit/ingame/s272_ingame_tail_recal.py": "83f86f6a653a364c3e8047b58f5976128d69daeecc2a882dc82deffb78ca7c30",
    "scripts/platformkit/foundry/ingame_incumbent_nba.py": "476ed9fdfb714b93c5b722f8e99fb1266cdb5987a729495f12e84d2b62ea08ed",
}
FINE_BINS = (0.01, 0.05, 0.10, 0.20, 0.80, 0.90, 0.95, 0.99)
S289_RANGES = ((0.01, 0.05), (0.05, 0.10), (0.10, 0.20), (0.80, 0.90), (0.90, 0.95), (0.95, 0.99))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    """Repo-relative when the path is inside the repo, else the absolute posix path."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _seal() -> str:
    data = PREREG.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, value = data.split(b"S293_PREREG_SEAL_SHA256=", 1)
    digest = hashlib.sha256(prefix).hexdigest()
    if value.splitlines()[0].decode("ascii") != digest:
        raise AssertionError("S293 preregistration seal mismatch")
    return digest


def _identities() -> dict[str, str]:
    values = {path: _sha(ROOT / path) for path in FIXED}
    if values != FIXED:
        raise AssertionError("a frozen source identity moved")
    return values


def _summary_arm(probabilities: pd.Series, outcomes: pd.Series) -> dict:
    losses, audit = log_loss_values(probabilities.to_numpy(float), outcomes.to_numpy(float))
    return {"log_loss": float(losses.mean()), "log_loss_sum": float(losses.sum()), **audit}


def _fine_table(rows: pd.DataFrame) -> list[dict]:
    output = []
    for left, right in S289_RANGES:
        mask = (rows["market_prob"] >= left) & (rows["market_prob"] < right)
        part = rows.loc[mask]
        table = {"bin": "[%0.2f,%0.2f)" % (left, right), "n_ticks": int(len(part)),
                 "n_games": int(part["game_id"].nunique())}
        for arm, column in (("recal_null", "p_close"), ("market", "market_prob")):
            values = reliability_table(part[column], part["y"], (0.0, 1.0))
            table[arm] = values[0]
        output.append(table)
    return output


def _comeback(rows: pd.DataFrame) -> dict:
    remaining = (4 - rows["period"].to_numpy(int)) * 720 + rows["game_clock_s"].to_numpy(float)
    mask = (rows["period"].to_numpy(int) <= 4) & (np.abs(rows["margin"].to_numpy(float)) >= 12) & (remaining <= 720)
    part = rows.loc[mask].copy()
    # Premise reconciliation: the same mask WITHOUT the period cap admits OT ticks. The
    # difference is the whole delta against the count quoted in the S293 spec text.
    ot = (rows["period"].to_numpy(int) > 4) & (np.abs(rows["margin"].to_numpy(float)) >= 12) & (remaining <= 720)
    result = {"mask": "period <= 4 and abs(margin) >= 12 and remaining_s <= 720",
              "n_ticks": int(len(part)), "n_games": int(part["game_id"].nunique()),
              "remaining_s_min": float(remaining[mask].min()), "remaining_s_max": float(remaining[mask].max()),
              "ot_ticks_excluded_by_period_cap": int(ot.sum()),
              "ot_games_excluded_by_period_cap": int(rows.loc[ot, "game_id"].nunique()),
              "ot_excluded_outcome_home_win_ticks": int(rows.loc[ot, "y"].sum()),
              "trailing_wins": 0, "trailing_losses": 0, "arms": {}}
    for arm, column in (("market", "market_prob"), ("recal_null", "p_close")):
        p, y, home_trailing = trailing_side(part[column], part["y"], part["margin"])
        losses, audit = log_loss_values(p, y)
        result["trailing_wins"] = int(y.sum())
        result["trailing_losses"] = int(len(y) - y.sum())
        result["home_trailing_ticks"] = int(home_trailing.sum())
        result["arms"][arm] = {"log_loss": float(losses.mean()), **audit,
                                "reliability": reliability_table(p, y, tuple(np.linspace(0.0, 1.0, 11)))}
    return result


def run(output_dir: Path = EVIDENCE) -> dict:
    """Run the unchanged S272 route once and write S293 additive evidence."""
    output_dir = Path(output_dir).resolve()
    before_rss = int(psutil.Process().memory_info().rss)
    seal, identities_before = _seal(), _identities()
    archive = pd.read_csv(S272_CSV)
    if len(archive) != 310349 or archive["record_type"].value_counts().to_dict() != {"tail_tick": 308756, "all_game": 1593}:
        raise AssertionError("S272 archive premise changed")
    try:
        refuse_mixed_grain(archive.to_dict("records"))
    except ValueError:
        pass
    else:
        raise AssertionError("mixed-grain archive was accepted")
    old = json.loads(S272_SUMMARY.read_text(encoding="ascii"))
    rows = pd.read_parquet(s272.SOURCE)
    rows["season"] = s272._season(rows["game_date"])
    prediction, folds = s272._predict(rows)
    evaluator = prediction.loc[:, ["game_id", "ts", "candidate", "incumbent", "outcome_home_win", "split_id", "n_train_shared", "tail"]].rename(columns={"candidate": "p_model", "incumbent": "p_close", "outcome_home_win": "y", "n_train_shared": "n_train"})
    candidate_loss, candidate_audit = log_loss_values(evaluator["p_model"], evaluator["y"])
    null_loss, null_audit = log_loss_values(evaluator["p_close"], evaluator["y"])
    evaluator["log_loss"] = candidate_loss
    evaluator["recal_null_log_loss"] = null_loss
    evaluator["tail_log_loss"] = np.where(evaluator["tail"], candidate_loss, np.nan)
    evaluator["tail_recal_null_log_loss"] = np.where(evaluator["tail"], null_loss, np.nan)
    evaluator["candidate_brier_loss"] = (evaluator["p_model"] - evaluator["y"]) ** 2
    evaluator["recal_null_brier_loss"] = (evaluator["p_close"] - evaluator["y"]) ** 2
    evaluator["delta_brier"] = evaluator["recal_null_brier_loss"] - evaluator["candidate_brier_loss"]
    evaluator["delta_log_loss"] = evaluator["recal_null_log_loss"] - evaluator["log_loss"]
    tick = prediction.loc[:, ["market_prob", "period", "game_clock_s", "margin", "game_date", "season"]].join(evaluator)
    def metric(part: pd.DataFrame, is_tail: bool) -> dict:
        candidate = _summary_arm(part["p_model"], part["y"])
        recal = _summary_arm(part["p_close"], part["y"])
        return {"n_ticks": int(len(part)), "n_games": int(part["game_id"].nunique()),
                "candidate_brier": float(part["candidate_brier_loss"].mean()), "recal_null_brier": float(part["recal_null_brier_loss"].mean()),
                "brier_improvement": float(part["delta_brier"].mean()), "candidate_log_loss": candidate["log_loss"],
                "recal_null_log_loss": recal["log_loss"], "log_loss_improvement": float(part["delta_log_loss"].mean()),
                "candidate_ece": float(ece(part["p_model"], part["y"])) if is_tail else None,
                "recal_null_ece": float(ece(part["p_close"], part["y"])) if is_tail else None}
    all_rows, tail_rows = tick, tick[tick["tail"]]
    metrics = {"all": metric(all_rows, False), "tail": metric(tail_rows, True)}
    replay = s272._metrics(prediction, False)
    metrics["all"]["brier_improvement_ci95"] = replay["improvement_ci95"]
    for name, key in (("candidate_brier", "candidate_brier"), ("recal_null_brier", "incumbent_brier")):
        if abs(metrics["all"][name] - old["metrics"]["all"][key]) > 1e-12:
            raise AssertionError("all-tick Brier replay drift")
    for name, key in (("candidate_brier", "candidate_brier"), ("recal_null_brier", "incumbent_brier"), ("candidate_ece", "candidate_ece"), ("recal_null_ece", "incumbent_ece")):
        if abs(metrics["tail"][name] - old["metrics"]["tail"][key]) > 1e-12:
            raise AssertionError("tail replay drift")
    output_dir.mkdir(parents=True, exist_ok=True)
    paired = output_dir / (STEM + "_paired_losses.csv.gz")
    tick.to_csv(paired, index=False, encoding="ascii")
    summary = {"mode": "ADDITIVE_METRIC_REPLAY", "verdict": "NOT_VALIDATED", "bar": 0.004, "epsilon": EPSILON,
               "preregistration_path": _rel(PREREG), "preregistration_seal": seal,
               "archive_rows": 310349, "archive_games": 1593, "s272_route_folds": folds, "source_identities_before": identities_before,
               "source_identities_after": _identities(), "metrics": metrics, "endpoint_accounting": {"candidate": candidate_audit, "recal_null": null_audit},
               "favorite_longshot_bins": _fine_table(tick), "comeback": _comeback(tick),
               "ot_periods_5_6_ticks": int(tick["period"].isin((5, 6)).sum()), "zero_clock_ticks": int((tick["game_clock_s"] == 0).sum()),
               "input": {"path": _rel(s272.SOURCE), "bytes": s272.SOURCE.stat().st_size, "rows": int(len(rows)), "resolution": "not applicable"},
               "paired_losses": _rel(paired), "rss_before_bytes": before_rss,
               "rss_after_bytes": int(psutil.Process().memory_info().rss)}
    # Only new dated artifacts are emitted; no existing memo is rewritten. The dated memo
    # is authored by hand from this summary.
    (output_dir / (STEM + "_summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="S293 additive tail metric replay")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    result = run(args.output_dir)
    print("S293 verdict=%s rss_before=%d rss_after=%d" % (result["verdict"], result["rss_before_bytes"], result["rss_after_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

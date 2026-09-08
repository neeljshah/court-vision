"""S310 sealed tail beta-offset calibration screen; calibration only."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
from sklearn.linear_model import LogisticRegression

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/cache/inplay_odds/nba_checkpoints_full.parquet"
PREREG = ROOT / "docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg.md"
SUPPLEMENT = ROOT / "docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg_supplement.md"
SUPPLEMENT_CORRECTED = ROOT / "docs/evidence/harness/S310_tail_beta_offset_2026-09-07_prereg_supplement_corrected.md"
OUT = ROOT / "docs/evidence/harness/S310_tail_beta_offset_2026-09-07"
EPS, RIDGE, EMBARGO_DAYS, BOOTSTRAPS, SEED = 1e-15, 100.0, 1, 10_000, 905
BUCKET_S = 30  # supplement amendment 1: evaluator-state clock bucket, in seconds


def _sigmoid(value: np.ndarray) -> np.ndarray:
    return np.where(value >= 0, 1.0 / (1.0 + np.exp(-value)), np.exp(value) / (1.0 + np.exp(value)))


def _logit(value: np.ndarray) -> np.ndarray:
    value = np.clip(np.asarray(value, dtype=float), EPS, 1.0 - EPS)
    return np.log(value / (1.0 - value))


def _season(dates: pd.Series) -> pd.Series:
    date = pd.to_datetime(dates, utc=True)
    start = date.dt.year.where(date.dt.month >= 7, date.dt.year - 1)
    return start.astype(str) + "-" + ((start + 1) % 100).astype(str).str.zfill(2)


def _verify_seal(path: Path) -> str:
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    prefix, seal = raw.split(b"Seal-SHA256-LF: ", 1)
    actual = hashlib.sha256(prefix).hexdigest()
    assert seal.decode("ascii").strip() == actual, "S310 seal mismatch: %s" % path.name
    return actual


def _verify_prereg() -> str:
    return _verify_seal(PREREG)


def _thin(frame: pd.DataFrame) -> pd.DataFrame:
    """Amendment 1: one evaluator state per game, period and BUCKET_S clock bucket.

    Deterministic and blind to outcome, probability and terminal status: the kept row
    is the lowest original parquet row index in each cell.
    """
    bucket = (frame.game_clock_s // BUCKET_S).astype(int)
    return (frame.assign(clock_bucket=bucket).sort_values("row_index")
            .drop_duplicates(["game_id", "period", "clock_bucket"], keep="first")
            .reset_index(drop=True))


def _fit_baseline(raw: np.ndarray, y: np.ndarray) -> LogisticRegression | None:
    if len(raw) < 2 or len(np.unique(y)) < 2:
        return None
    model = LogisticRegression(C=1e6, max_iter=500, solver="lbfgs")
    model.fit(_logit(raw).reshape(-1, 1), y)
    return model


def _predict_baseline(model: LogisticRegression | None, raw: np.ndarray) -> np.ndarray:
    return np.asarray(raw, dtype=float) if model is None else model.predict_proba(_logit(raw).reshape(-1, 1))[:, 1]


def _tail_bin(p: np.ndarray) -> np.ndarray:
    out = np.full(len(p), "outside", dtype=object)
    out[(p >= 0.01) & (p <= 0.05)] = "low_001_005"
    out[(p >= 0.95) & (p <= 0.99)] = "high_095_099"
    return out


def _apply_candidate(raw: np.ndarray, baseline: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """Apply the tail-only residual; zero beta is exactly the identity."""
    out = np.asarray(baseline, dtype=float).copy()
    if np.array_equal(beta, np.zeros(3)):
        return out
    mask = _tail_bin(out) != "outside"
    p = np.clip(np.asarray(raw, dtype=float)[mask], EPS, 1.0 - EPS)
    x = np.column_stack([np.ones(len(p)), np.log(p), np.log1p(-p)])
    out[mask] = _sigmoid(_logit(out[mask]) + x @ beta)
    return out


def _fit_residual(raw: np.ndarray, baseline: np.ndarray, y: np.ndarray) -> np.ndarray:
    tail = _tail_bin(baseline) != "outside"
    if tail.sum() < 3 or len(np.unique(y[tail])) < 2:
        return np.zeros(3)
    p = np.clip(raw[tail], EPS, 1.0 - EPS)
    x = np.column_stack([np.ones(len(p)), np.log(p), np.log1p(-p)])
    offset = _logit(baseline[tail])
    beta = np.zeros(3)
    penalty = np.diag([0.0, RIDGE, RIDGE])
    for _ in range(40):
        fitted = np.clip(_sigmoid(offset + x @ beta), EPS, 1.0 - EPS)
        grad = x.T @ (fitted - y[tail]) + penalty @ beta
        hess = (x.T * (fitted * (1.0 - fitted))) @ x + penalty + 1e-9 * np.eye(3)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if float(np.max(np.abs(step))) < 1e-10:
            break
    return beta


def _nested_oof(train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    out = np.full(len(train), np.nan)
    dates = np.array(sorted(train.game_date.unique()))
    for block in np.array_split(dates, 5):
        if not len(block):
            continue
        start = pd.Timestamp(block[0])
        test = train.game_date.isin(block)
        fit = train.game_date < (start - pd.Timedelta(days=EMBARGO_DAYS))
        model = _fit_baseline(train.loc[fit, "raw"].to_numpy(), train.loc[fit, "y"].to_numpy())
        out[test.to_numpy()] = _predict_baseline(model, train.loc[test, "raw"].to_numpy())
    valid = np.isfinite(out)
    return (train.loc[valid, "raw"].to_numpy(float), out[valid],
            train.loc[valid, "y"].to_numpy(float))


def _fit_outer(train: pd.DataFrame) -> tuple[LogisticRegression | None, np.ndarray]:
    baseline = _fit_baseline(train.raw.to_numpy(), train.y.to_numpy())
    raw, nested, nested_y = _nested_oof(train)
    return baseline, _fit_residual(raw, nested, nested_y)


def _states(frame: pd.DataFrame) -> list[dict]:
    """Build evaluator states.

    `ts` is int64 epoch SECONDS. `pd.Timestamp(int)` reads a bare integer as
    NANOSECONDS, which put every state on 1970-01-01, collapsed the corpus to a
    single calendar day, and made the shared calendar-day embargo block the entire
    train set on every path. The unit is therefore stated explicitly.
    """
    states = []
    for row in frame.itertuples(index=False):
        stamp = pd.Timestamp(int(row.ts), unit="s", tz="UTC").to_pydatetime()
        states.append({"game_id": row.state_key, "state_ts": stamp.isoformat(),
                       "home": "GAME_" + str(row.game_id), "away": "OPP_" + str(row.game_id),
                       "season": str(row.season),
                       "outcome": int(row.outcome_home_win),
                       "features": {"raw": float(row.market_prob), "game_date": str(row.game_date)},
                       "feature_avail": {"raw": (stamp - pd.Timedelta(microseconds=1)).isoformat(),
                                          "game_date": (stamp - pd.Timedelta(microseconds=1)).isoformat()}})
    return states


def _records(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], dict[str, float]]:
    """Amendment 2: one evaluator pass yields both arms.

    The two former passes shared identical splits, purges, train sets and baseline
    fits, so the baseline probability is captured here and the candidate derived from
    it in the same call. Each state is scored exactly once because the two frozen
    season test blocks are disjoint.
    """
    lookup = frame.set_index("state_key")
    caches: dict[int, tuple[LogisticRegression | None, np.ndarray, list[str]]] = {}
    audits: dict[int, dict] = {}
    baselines: dict[str, float] = {}
    start, seen = time.perf_counter(), [0]
    def predict(train_states: list[dict], test: dict, _inside: bool) -> float:
        game_date = str(test["features"]["game_date"])
        key = id(train_states)
        if key not in caches:
            ids = [state["game_id"] for state in train_states]
            train = lookup.loc[ids]
            train = train[train.game_date < game_date]
            baseline, beta = _fit_outer(train.rename(columns={"market_prob": "raw", "outcome_home_win": "y"})) if len(train) else (None, np.zeros(3))
            caches[key] = (baseline, beta, list(train.index))
            audits[key] = {"test_game_date": game_date, "n_train_ticks": int(len(train)),
                           "train_state_keys": list(train.index), "beta": beta.tolist()}
        baseline, beta, _ = caches[key]
        raw = np.asarray([float(test["features"]["raw"])])
        null = _predict_baseline(baseline, raw)
        assert test["game_id"] not in baselines, "a state was scored twice"
        baselines[test["game_id"]] = float(null[0])
        seen[0] += 1
        if seen[0] % 10_000 == 0:
            print("S310 scored %d states in %.0fs" % (seen[0], time.perf_counter() - start),
                  file=sys.stderr, flush=True)
        return float(_apply_candidate(raw, null, beta)[0])
    records = pd.DataFrame(cpcv_evaluate(_states(frame), predict, n_groups=2, n_test_groups=1,
                                         embargo_days=EMBARGO_DAYS, group_key="season", guard_state_keys=True))
    return records, list(audits.values()), baselines


def _interval(frame: pd.DataFrame, column: str, mask: pd.Series) -> tuple[float, list[float], int]:
    part = frame.loc[mask]
    grouped = part.groupby("cluster_id", sort=True)[column].agg(["sum", "count"])
    assert len(grouped) >= 30
    rng, n = np.random.default_rng(SEED + int(mask.sum())), len(grouped)
    draws = rng.integers(0, n, size=(BOOTSTRAPS, n))
    sums, counts = grouped["sum"].to_numpy(), grouped["count"].to_numpy()
    values = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return float(part[column].mean()), [float(np.quantile(values, .025)), float(np.quantile(values, .975))], int(len(grouped))


def _memo(summary: dict) -> str:
    rows = ["# S310 tail beta-offset calibration screen", "", "Verdict: %s" % summary["verdict"], "",
            "Preregistration: `%s`" % summary["preregistration"], "",
            "Preregistration SHA-256: `%s`" % summary["prereg_seal"], "",
            "Supplement: `%s`" % summary["supplement"], "",
            "Supplement SHA-256: `%s`" % summary["supplement_seal"], "",
            "Corrected supplement: `%s`" % summary["supplement_corrected"], "",
            "Corrected supplement SHA-256: `%s`" % summary["supplement_corrected_seal"], "",
            "Sign convention: improvement equals baseline loss minus candidate loss; positive means candidate better.", "",
            "| population | baseline log loss | candidate log loss | log-loss improvement 95 pct CI | Brier improvement 95 pct CI | game clusters |",
            "|---|---:|---:|---|---|---:|"]
    for name, metric in summary["metrics"].items():
        log_mean, log_ci, games = metric["log_improvement"]
        bri_mean, bri_ci, _ = metric["brier_improvement"]
        rows.append("| %s | %.9f | %.9f | %+.9f [%+.9f, %+.9f] | %+.9f [%+.9f, %+.9f] | %d |" %
                    (name, metric["log_loss"], metric["candidate_log_loss"], log_mean, log_ci[0], log_ci[1], bri_mean, bri_ci[0], bri_ci[1], games))
    rows += ["", "Input: `%s` (%d bytes; %d rows; tabular, resolution not applicable)." %
             (summary["input"]["path"], summary["input"]["bytes"], summary["input"]["rows"]),
             "Columns: %s. First three game ids: %s." % (", ".join(summary["input"]["columns"]), ", ".join(summary["input"]["first_three_game_ids"])),
             "Grain (supplement amendment 1): %s; %d source rows become %d evaluator states over %d game clusters." %
             (summary["grain"]["rule"], summary["grain"]["source_rows"], summary["grain"]["states"], summary["grain"]["clusters"]),
             "Binding premise remeasured on this grain: raw 0.01-0.05 contains %d states across %d game clusters and %d positive-outcome clusters (tick grain: 9226, 649, 29)." %
             (summary["grain"]["low_band_states"], summary["grain"]["low_band_clusters"], summary["grain"]["low_band_positive_clusters"]),
             "The low/high bin results are descriptive only; no separate bin conditional proposal is made, so Holm has no claimed-bin family to adjust.",
             "The S272 trainable-tail oracle cap 0.002534 remains a precision limit, not a global result.",
             "", "## NOT VERIFIED", "",
             "- The grain change itself: results are not comparable tick-for-tick with the original all-tick design, and the global guard denominator no longer contains the settled terminal snapshots.",
             "- Independent-corpus replication.", "- Any deployment, flag, registry, ledger, or global calibration claim."]
    return "\n".join(rows) + "\n"


def run(output: Path = OUT) -> dict:
    seal, supplement_seal = _verify_prereg(), _verify_seal(SUPPLEMENT)
    corrected_seal = _verify_seal(SUPPLEMENT_CORRECTED)
    source = pd.read_parquet(SOURCE).reset_index(names="row_index")
    frame = _thin(source)
    frame["game_date"] = pd.to_datetime(frame.game_date, utc=True).dt.normalize()
    frame["season"] = _season(frame.game_date)
    frame["state_key"] = frame.game_id.astype(str) + ":" + frame.ts.astype(str) + ":" + frame.row_index.astype(str)
    frame["cluster_id"] = frame.game_id.astype(str)
    assert frame.state_key.is_unique
    records, audits, baselines = _records(frame)
    records = records.rename(columns={"p_model": "p_model_candidate"})
    records["p_model_baseline"] = records.game_id.map(baselines)
    assert records.p_model_baseline.notna().all(), "a scored state has no baseline"
    result = frame.merge(records, left_on="state_key", right_on="game_id", validate="one_to_one")
    result["tail_bin"] = _tail_bin(result.p_model_baseline.to_numpy())
    result["loss_log_baseline"] = -(result.y * np.log(np.clip(result.p_model_baseline, EPS, 1-EPS)) + (1-result.y) * np.log(np.clip(1-result.p_model_baseline, EPS, 1-EPS)))
    result["loss_log_candidate"] = -(result.y * np.log(np.clip(result.p_model_candidate, EPS, 1-EPS)) + (1-result.y) * np.log(np.clip(1-result.p_model_candidate, EPS, 1-EPS)))
    result["delta_log"] = result.loss_log_baseline - result.loss_log_candidate
    result["loss_brier_baseline"] = (result.p_model_baseline-result.y)**2
    result["loss_brier_candidate"] = (result.p_model_candidate-result.y)**2
    result["delta_brier"] = result.loss_brier_baseline-result.loss_brier_candidate
    masks = {"low": result.tail_bin.eq("low_001_005"), "high": result.tail_bin.eq("high_095_099"),
             "tail": result.tail_bin.ne("outside"), "global": pd.Series(True, index=result.index)}
    metrics = {name: {"log_loss": _interval(result, "loss_log_baseline", mask)[0],
                      "candidate_log_loss": _interval(result, "loss_log_candidate", mask)[0],
                      "log_improvement": _interval(result, "delta_log", mask),
                      "brier_improvement": _interval(result, "delta_brier", mask)} for name, mask in masks.items()}
    tail_lo, global_lo = metrics["tail"]["log_improvement"][1][0], metrics["global"]["brier_improvement"][1][0]
    verdict = "CONDITIONAL_PROPOSAL" if tail_lo > 0 and global_lo > -0.0005 else "CLOSED_AT_LIMIT"
    output.mkdir(parents=True, exist_ok=True)
    paired = result[["state_key", "cluster_id", "ts_x", "split_id", "n_train", "y", "tail_bin", "p_model_baseline", "p_model_candidate", "loss_log_baseline", "loss_log_candidate", "delta_log", "loss_brier_baseline", "loss_brier_candidate", "delta_brier"]].rename(columns={"ts_x": "ts"})
    paired.to_csv(output / "paired_losses.csv", index=False, encoding="ascii")
    paired[["state_key", "cluster_id", "ts", "tail_bin", "p_model_baseline", "p_model_candidate"]].to_csv(output / "probabilities.csv", index=False, encoding="ascii")
    (output / "train_keys.json").write_text(json.dumps(audits, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    (output / "clips.json").write_text(json.dumps({"epsilon": EPS, "low": [0.01, .05], "high": [.95, .99]}, indent=2) + "\n", encoding="ascii", newline="\n")
    band = frame[(frame.market_prob >= 0.01) & (frame.market_prob <= 0.05)]
    summary = {"row": "S310", "verdict": verdict, "preregistration": str(PREREG.relative_to(ROOT)).replace("\\", "/"), "prereg_seal": seal, "supplement": str(SUPPLEMENT.relative_to(ROOT)).replace("\\", "/"), "supplement_seal": supplement_seal, "supplement_corrected": str(SUPPLEMENT_CORRECTED.relative_to(ROOT)).replace("\\", "/"), "supplement_corrected_seal": corrected_seal, "grain": {"rule": "one state per game_id, period and floor(game_clock_s / %d)" % BUCKET_S, "source_rows": len(source), "states": len(frame), "clusters": int(frame.game_id.nunique()), "low_band_states": len(band), "low_band_clusters": int(band.game_id.nunique()), "low_band_positive_clusters": int(band[band.outcome_home_win == 1].game_id.nunique())}, "input": {"path": str(SOURCE.relative_to(ROOT)).replace("\\", "/"), "bytes": SOURCE.stat().st_size, "rows": len(frame), "columns": list(frame.columns[:14]), "first_three_game_ids": list(frame.game_id.astype(str).iloc[:3]), "resolution": "not applicable"}, "evaluator": "scripts.platformkit.eval_gate.cpcv_engine.cpcv_evaluate", "embargo_days_symmetric_nonzero": EMBARGO_DAYS, "seed": SEED, "bootstraps": BOOTSTRAPS, "metrics": metrics, "rss_bytes": int(psutil.Process().memory_info().rss), "route_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    (output / "memo.md").write_text(_memo(summary), encoding="ascii", newline="\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    summary = run(args.output)
    print("S310 verdict=%s rss_bytes=%d" % (summary["verdict"], summary["rss_bytes"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

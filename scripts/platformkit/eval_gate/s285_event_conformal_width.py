"""S285: audit S265 STATIC conformal coverage by score-event proximity."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import resource
except ImportError:
    resource = None

from scripts.platformkit.eval_gate import s101_aci_coverage as s101
from scripts.platformkit.eval_gate import s265_incumbent_conformal_band_sample as s265
from scripts.platformkit.foundry import ingame_incumbent_nba as incumbent

REPO = Path(__file__).resolve().parents[3]
PREREG = REPO / "docs/evidence/harness/S285_preregistration_event_conformal_width_2026-09-04_v2.md"
OUT_JSON = REPO / "docs/evidence/harness/S285_event_conformal_width_2026-09-04_retry3.json"
PAIR_CSV = REPO / "docs/evidence/harness/S285_event_conformal_width_2026-09-04_retry3_paired_loss.csv"
MEMO = REPO / "docs/evidence/harness/S285_event_conformal_width_2026-09-04_retry3.md"
SEED, N_BOOT, MEMORY_LIMIT = 2850904, 2000, 600 * 1024 * 1024
NOMINALS = (0.90, 0.80)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prereg_seal() -> str:
    """Return the v2 seal over committed preregistration bytes."""
    if (REPO / ".git").exists():
        raw = subprocess.check_output(["git", "show", "HEAD:" + PREREG.relative_to(REPO).as_posix()], cwd=REPO)
    else:
        raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw.split(b"SEAL_SHA256:", 1)[0]).hexdigest()


def _rss() -> tuple[int | None, int | None]:
    """Return current/peak RSS on Windows or peak RSS in a Linux pod scratch run."""
    current, peak = s265._rss()
    if current is not None or peak is not None:
        return current, peak
    try:
        if resource is None:
            return None, None
        return None, int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (AttributeError, ValueError):
        return None, None


def derive_ticks_since_last_score_change(frame: pd.DataFrame) -> np.ndarray:
    """Return per-tick score-event distance without a future-row backfill."""
    required = {"game_id", "ts", "score_home", "score_away"}
    if not required.issubset(frame):
        raise ValueError("missing score derivation columns")
    ordered = frame.sort_values(["game_id", "ts"], kind="stable")
    out = pd.Series(np.empty(len(ordered), dtype=np.int64), index=ordered.index)
    for _, positions in ordered.groupby("game_id", sort=False).indices.items():
        prior, last_change = None, 0
        for offset, position in enumerate(np.asarray(positions)):
            row = ordered.iloc[position]
            score = (int(row["score_home"]), int(row["score_away"]))
            if prior is None or score != prior:
                last_change = offset
            out.iloc[position] = offset - last_change
            prior = score
    return out.reindex(frame.index).to_numpy()


def _future_row_plant(frame: pd.DataFrame) -> None:
    probe = frame.sort_values(["game_id", "ts"], kind="stable").iloc[:12].copy()
    base = derive_ticks_since_last_score_change(probe)
    planted = probe.copy()
    planted.loc[planted.index[-1], "score_home"] = int(planted.loc[planted.index[-2], "score_home"]) + 2
    assert np.array_equal(base[:-1], derive_ticks_since_last_score_change(planted)[:-1]), "future score backfilled"


def _walk_forward_static(rows: pd.DataFrame, nominal: float) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """S265's shared S101 walk-forward route with a stable state key retained."""
    held, folds = [], []
    alpha = round(1.0 - nominal, 10)
    for fold, block, cut in s101.fold_blocks(rows, s101.N_FOLDS):
        train, test = rows[rows["date"] < cut], rows[rows["date"].isin(set(block))]
        if train.empty or test.empty or train["y"].nunique() < 2:
            folds.append({"fold": fold, "status": "INSUFFICIENT", "n_train_ticks": int(len(train))})
            continue
        assert not set(train["game"]).intersection(test["game"]), "game purge violated"
        assert train["date"].max() < cut <= min(block), "symmetric embargo violated"
        scored, _ = s101.run_fold(train, test, "p_incumbent", alpha)
        scored["source_row"] = test["source_row"].to_numpy()
        scored["ticks_since_last_score_change"] = test["ticks_since_last_score_change"].to_numpy()
        scored["fold"] = fold
        held.append(scored)
        folds.append({"fold": fold, "status": "OK", "test_start": min(block), "test_end": max(block),
                      "embargo_cut": cut, "train_date_max": str(train["date"].max()),
                      "n_train_ticks": int(len(train)), "n_train_games": int(train["game"].nunique()),
                      "n_test_ticks": int(len(test)), "n_test_games": int(test["game"].nunique()),
                      "symmetric_embargo_days": s101.EMBARGO_DAYS})
    return pd.concat(held, ignore_index=True), folds


def _metric(ticks: pd.DataFrame, nominal: float) -> dict[str, Any]:
    grouped = s101.grouped_coverage(ticks["p"].to_numpy(float), ticks["y"].to_numpy(float),
                                    ticks["lo_static"].to_numpy(float), ticks["hi_static"].to_numpy(float), nominal)
    result = {"n_ticks": int(len(ticks)), "n_games": int(ticks["game"].nunique()),
              "n_groups": int(grouped["n_groups"]), "coverage": grouped["coverage"],
              "mean_half_width": None if grouped["coverage"] is None else grouped["mean_interval_width"] / 2.0,
              "absent_because": grouped.get("absent_because")}
    return result


def _ci(values: list[float]) -> list[float]:
    return [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]


def _bootstrap(ticks: pd.DataFrame, nominal: float) -> dict[str, Any]:
    groups = {str(game): part for game, part in ticks.groupby("game", sort=True)}
    names = sorted(groups)
    draws = {label: {"coverage": [], "mean_half_width": []} for label in ("near_event", "settled", "pooled")}
    gap, width_gap = [], []
    rng = np.random.default_rng(SEED)
    for _ in range(N_BOOT):
        sampled = pd.concat([groups[names[i]] for i in rng.integers(len(names), size=len(names))], ignore_index=True)
        values = {"near_event": _metric(sampled[sampled["bin"] == "near_event"], nominal),
                  "settled": _metric(sampled[sampled["bin"] == "settled"], nominal),
                  "pooled": _metric(sampled, nominal)}
        for label, value in values.items():
            draws[label]["coverage"].append(float(value["coverage"]))
            draws[label]["mean_half_width"].append(float(value["mean_half_width"]))
        gap.append(values["settled"]["coverage"] - values["near_event"]["coverage"])
        width_gap.append(values["near_event"]["mean_half_width"] - values["settled"]["mean_half_width"])
    return {"bins": {label: {key + "_ci95": _ci(value) for key, value in fields.items()}
                     for label, fields in draws.items()},
            "coverage_gap_settled_minus_near_ci95": _ci(gap),
            "half_width_gap_near_minus_settled_ci95": _ci(width_gap)}


def _bins(ticks: pd.DataFrame, p50: int, p90: int) -> pd.Series:
    return pd.Series(np.where(ticks["ticks_since_last_score_change"] <= p50, "near_event",
                              np.where(ticks["ticks_since_last_score_change"] > p90, "settled", "middle_exclusion")),
                     index=ticks.index)


def _memo(report: dict[str, Any]) -> str:
    lines = ["# S285 event-proximity audit of the S265 static conformal band", "",
             "## Result", "", "This is a calibration-only, sample-scale stratification audit of the unchanged S265 STATIC band.",
             "The source was `%s`, %d bytes, Parquet tabular data; pixel resolution is not applicable." % (report["source"]["path"], report["source"]["bytes"]),
             "The sealed 79,919-tick/269-game sample had p50=%d and p90=%d for the strictly-prior score-change derivation." % (report["premise"]["p50"], report["premise"]["p90"]),
             "", "| Nominal | Bin | Ticks | Games | Coverage (95 pct CI) | Mean half-width (95 pct CI) |", "| ---: | --- | ---: | ---: | --- | --- |"]
    for nominal, item in report["results"].items():
        for label in ("near_event", "settled", "pooled"):
            m = item["bins"][label]
            lines.append("| %s | %s | %d | %d | %.9f [%.9f, %.9f] | %.9f [%.9f, %.9f] |" %
                         (nominal, label, m["n_ticks"], m["n_games"], m["coverage"], *m["coverage_ci95"],
                          m["mean_half_width"], *m["mean_half_width_ci95"]))
        lines.append("| %s | settled-minus-near coverage | - | - | %.9f [%.9f, %.9f] | - |" %
                     (nominal, item["coverage_gap_settled_minus_near"], *item["coverage_gap_settled_minus_near_ci95"]))
        lines.append("| %s | near-minus-settled half-width | - | - | - | %.9f [%.9f, %.9f] |" %
                     (nominal, item["half_width_gap_near_minus_settled"], *item["half_width_gap_near_minus_settled_ci95"]))
    lines.extend(["", "## Reproduction and contract self-check", "",
                  "The scorer uses S265/S101 five-fold walk-forward scoring with game purge and a symmetric one-day embargo. One archived evaluator record exists for every scored tick, keyed by `game:source_row`; middle ticks are named exclusions.",
                  "The preregistration is `%s` with committed LF-byte seal `%s`. It predates scoring." % (report["prereg"]["path"], report["prereg"]["seal_sha256"]),
                  "The run executed in %s. Its peak RSS was %s bytes." % (report["machine"], report["rss"]["peak_bytes"]),
                  "Q1 sealed preregistration; Q2 uncharged/no ledger; Q3 fixed bar; Q4 shared walk-forward purge and embargo; Q5 no AHEAD claim; Q6 calibration language only; Q7 each scored comparison has at least 30 game clusters; Q8 premise measured first; Q9 stores evaluator records only.",
                  "", "Artifacts: `%s` and `%s`." % (OUT_JSON.relative_to(REPO).as_posix(), PAIR_CSV.relative_to(REPO).as_posix()),
                  "Focused test: `python -m pytest tests/platformkit/ingame/test_s285_event_conformal_width.py -q`."])
    return "\n".join(lines) + "\n"


def run() -> dict[str, Any]:
    """Measure the preregistered event-proximity bins and write new S285 artifacts."""
    before_current, before_peak = _rss()
    raw, _ = s265._sample_raw()
    raw = raw.sort_values(["game_id", "ts"], kind="stable").reset_index(drop=True)
    raw["source_row"] = np.arange(len(raw))
    raw["ticks_since_last_score_change"] = derive_ticks_since_last_score_change(raw)
    _future_row_plant(raw)
    p50, p90 = (int(np.quantile(raw["ticks_since_last_score_change"], q)) for q in (0.5, 0.9))
    assert (p50, p90) == (13, 136), "preregistered boundaries changed"
    event = raw[["source_row", "ticks_since_last_score_change"]].copy()
    rows = s265._rows(raw).merge(event, on="source_row", validate="one_to_one")
    del raw, event
    seeded = incumbent.apply_incumbent(rows, "ladder_base", s101.EMBARGO_DAYS).copy()
    seeded["p_incumbent"] = seeded["p_e4"]
    del rows
    reports, archived, folds = {}, [], None
    for nominal in NOMINALS:
        ticks, folds = _walk_forward_static(seeded, nominal)
        ticks["bin"] = _bins(ticks, p50, p90)
        ticks["state_key"] = ticks["game"].astype(str) + ":" + ticks["source_row"].astype(str)
        assert ticks["state_key"].is_unique, "one evaluator state per tick violated"
        b = {label: _metric(ticks if label == "pooled" else ticks[ticks["bin"] == label], nominal)
             for label in ("near_event", "settled", "pooled")}
        assert b["near_event"]["n_games"] >= 30 and b["settled"]["n_games"] >= 30
        boot = _bootstrap(ticks, nominal)
        for label in b:
            b[label].update(boot["bins"][label])
        gap = b["settled"]["coverage"] - b["near_event"]["coverage"]
        width = b["near_event"]["mean_half_width"] - b["settled"]["mean_half_width"]
        reports["%.2f" % nominal] = {"bins": b, "coverage_gap_settled_minus_near": gap,
            "coverage_gap_settled_minus_near_ci95": boot["coverage_gap_settled_minus_near_ci95"],
            "half_width_gap_near_minus_settled": width,
            "half_width_gap_near_minus_settled_ci95": boot["half_width_gap_near_minus_settled_ci95"],
            "verdict": "SIGNAL" if gap > 0.05 and boot["coverage_gap_settled_minus_near_ci95"][0] > 0 else "NULL"}
        archived.append(ticks[["state_key", "game", "date", "ts", "fold", "nominal", "bin", "p", "y", "lo_static", "hi_static", "ticks_since_last_score_change"]])
    pd.concat(archived, ignore_index=True).to_csv(PAIR_CSV, index=False, encoding="ascii")
    current, peak = _rss()
    if max(v or 0 for v in (current, peak)) >= MEMORY_LIMIT:
        raise MemoryError("MEMORY LIMIT at or above 600 MB")
    source_path = s265.s86.CHECKPOINTS.resolve()
    report = {"row": "S285 retry3", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "machine": "pod scratch /workspace/wt/a14",
              "prereg": {"path": PREREG.relative_to(REPO).as_posix(), "seal_sha256": prereg_seal()},
              "source": {"path": str(source_path), "bytes": source_path.stat().st_size,
                         "sample_ticks": 79919, "sample_games": 269},
              "premise": {"p50": p50, "p90": p90, "near_ticks": 40051, "settled_ticks": 7870,
                          "middle_ticks": 31998, "future_row_plant": "PASS"},
              "design": {"evaluator": "S265/S101 walk-forward", "folds": folds, "purge": "game-disjoint",
                         "symmetric_embargo_days": s101.EMBARGO_DAYS, "bootstrap_seed": SEED, "bootstrap_reps": N_BOOT,
                         "coverage_min_group": s101.COVERAGE_MIN_GROUP, "coverage_max_groups": s101.COVERAGE_MAX_GROUPS},
              "results": reports, "rss": {"before_current_bytes": before_current, "before_peak_bytes": before_peak,
                         "after_current_bytes": current, "peak_bytes": peak},
              "paired_loss_series": {"path": PAIR_CSV.relative_to(REPO).as_posix(), "sha256": _hash(PAIR_CSV)},
              "code_identity": {name: _hash(Path(module.__file__)) for name, module in
                  {"s285": __import__(__name__, fromlist=["x"]), "s265": s265, "s101": s101,
                   "s86": s265.s86, "s123": incumbent, "aci_online": s265.aci_online}.items()}}
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    MEMO.write_text(_memo(report), encoding="ascii")
    return report


if __name__ == "__main__":
    value = run()
    print("S285 p50=%d p90=%d peak_rss=%s" % (value["premise"]["p50"], value["premise"]["p90"], value["rss"]["peak_bytes"]))
    for nominal, result in value["results"].items():
        print("S285 nominal=%s gap=%.9f ci=%s verdict=%s" % (nominal, result["coverage_gap_settled_minus_near"], result["coverage_gap_settled_minus_near_ci95"], result["verdict"]))

"""S265 local STATIC conformal coverage measurement on a sealed game sample."""
from __future__ import annotations

import ctypes
import datetime as dt
import gc
import hashlib
import json
import subprocess
from collections import Counter
from ctypes import wintypes
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from scripts.platformkit.eval_gate import s101_aci_coverage as s101
from scripts.platformkit.eval_gate import s86_nba_every_tick as s86
from scripts.platformkit.foundry import ingame_incumbent_nba as incumbent
from scripts.platformkit.ingame import aci_online

REPO = Path(__file__).resolve().parents[3]
PREREG = REPO / "docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md"
OUT_JSON = REPO / "docs/evidence/harness/S265_incumbent_conformal_band_sample_2026-09-04_retry2.json"
PAIR_CSV = REPO / "docs/evidence/harness/S265_incumbent_conformal_band_sample_paired_loss_2026-09-04_retry2.csv"
S101_JSON = REPO / "data/cache/eval_gate/s101_aci_coverage_2026-09-03.json"
S101_TICKS = REPO / "data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz"
SEED, LIMIT, MEMORY_LIMIT = 258104, 80000, 600 * 1024 * 1024
PHASES = s101.PHASES + ("ALL",)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prereg_seal() -> str:
    """Return the required seal over committed preregistration bytes."""
    text = subprocess.check_output(["git", "show", "HEAD:" + PREREG.relative_to(REPO).as_posix()], cwd=REPO)
    return hashlib.sha256(text.split(b"SEAL_SHA256:", 1)[0]).hexdigest()


def _rss() -> tuple[int | None, int | None]:
    """Return current and peak working-set bytes on Windows."""
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                    ("peak", ctypes.c_size_t), ("current", ctypes.c_size_t),
                    ("qpeak", ctypes.c_size_t), ("q", ctypes.c_size_t),
                    ("npeak", ctypes.c_size_t), ("n", ctypes.c_size_t),
                    ("page", ctypes.c_size_t), ("pagepeak", ctypes.c_size_t),
                    ("private", ctypes.c_size_t)]
    try:
        value = Counters(ctypes.sizeof(Counters))
        psapi = ctypes.WinDLL("psapi")
        kernel = ctypes.windll.kernel32
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        ok = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(value), ctypes.sizeof(value))
        return (int(value.current), int(value.peak)) if ok else (None, None)
    except (AttributeError, OSError):
        return None, None


def _memory(label: str) -> tuple[int | None, int | None]:
    current, peak = _rss()
    print("RSS %s current=%s peak=%s" % (label, current, peak))
    if max(v or 0 for v in (current, peak)) > MEMORY_LIMIT:
        raise MemoryError("MEMORY LIMIT above 600 MB")
    return current, peak


def _sample_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stream source batches, retaining only preregistered complete games."""
    counts: Counter[str] = Counter()
    reader = pq.ParquetFile(s86.CHECKPOINTS)
    for batch in reader.iter_batches(columns=["game_id"], batch_size=65536):
        counts.update(map(str, batch.column(0).to_pylist()))
    order = np.random.default_rng(SEED).permutation(sorted(counts))
    games, ticks = [], 0
    for game in order:
        n = counts[str(game)]
        if ticks + n <= LIMIT:
            games.append(str(game))
            ticks += n
    assert ticks == 79919 and len(games) == 269
    selected = set(games)
    chunks = []
    for batch in pq.ParquetFile(s86.CHECKPOINTS).iter_batches(batch_size=65536):
        part = batch.to_pandas()
        part = part[part["game_id"].astype(str).isin(selected)]
        if not part.empty:
            chunks.append(part)
    raw = pd.concat(chunks, ignore_index=True).sort_values(["game_id", "ts"], kind="stable")
    assert len(raw) == ticks and raw["game_id"].nunique() == len(games)
    membership = pd.DataFrame({"game": sorted(selected), "n_ticks": [counts[g] for g in sorted(selected)]})
    membership["record_type"] = "sample_game"
    return raw.reset_index(drop=True), membership


def _rows(raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"source_row": np.arange(len(raw)), "game": raw["game_id"].astype(str),
                        "date": raw["game_date"].astype(str), "game_date": raw["game_date"].astype(str),
                        "ts": pd.to_datetime(raw["ts"], unit="s", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "y": raw["outcome_home_win"].astype(float), "market": raw["market_prob"].astype(float),
                        "margin": raw["margin"].astype(float),
                        "rem": [s86.rem_minutes(p, c) for p, c in zip(raw["period"], raw["game_clock_s"])],
                        "period_bucket": raw["period"].map(s86.period_bucket)})
    out["cell"] = out["period_bucket"]
    return out.sort_values(["ts", "game"], kind="stable").reset_index(drop=True)


def _walk_forward(rows: pd.DataFrame, nominal: float) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Call the shared S101 STATIC evaluator under its S86 fold contract."""
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
        scored["fold"] = fold
        held.append(scored)
        folds.append({"fold": fold, "status": "OK", "test_start": min(block), "test_end": max(block),
                      "embargo_cut": cut, "train_date_max": str(train["date"].max()),
                      "n_train_ticks": int(len(train)), "n_train_games": int(train["game"].nunique()),
                      "n_test_ticks": int(len(test)), "n_test_games": int(test["game"].nunique()),
                      "symmetric_embargo_days": s101.EMBARGO_DAYS})
    return pd.concat(held, ignore_index=True), folds


def _archive_groups(ticks: pd.DataFrame, nominal: float, cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for cell in PHASES:
        sub = ticks if cell == "ALL" else ticks[ticks["phase"] == cell]
        metric = cells[cell]
        if metric["coverage"] is None:
            continue
        ordered = sub.iloc[np.argsort(sub["p"].to_numpy(float), kind="mergesort")]
        gids = s101._gid(len(ordered), int(metric["n_groups"]))
        rows = []
        for group_id in range(int(metric["n_groups"])):
            part = ordered.iloc[gids == group_id]
            lo, hi, observed = float(part["lo_static"].mean()), float(part["hi_static"].mean()), float(part["y"].mean())
            row = {"record_type": "grouped_coverage", "arm": "ladder_base", "nominal": "%.2f" % nominal,
                   "cell": cell, "group_id": group_id, "n_ticks": int(len(part)),
                   "cluster_id": ";".join(sorted(part["game"].unique())), "timestamp_start": str(part["ts"].min()),
                   "timestamp_end": str(part["ts"].max()), "mean_probability": float(part["p"].mean()),
                   "observed_frequency": observed, "mean_lo": lo, "mean_hi": hi,
                   "covered": int(lo <= observed <= hi)}
            rows.append(row)
        assert abs(float(np.mean([r["covered"] for r in rows])) - float(metric["coverage"])) <= 1e-9
        assert abs(float(np.mean([(r["mean_hi"] - r["mean_lo"]) / 2.0 for r in rows])) -
                   float(metric["mean_interval_width"]) / 2.0) <= 1e-9
        records.extend(rows)
    return records


def _s101_regression() -> dict[str, Any]:
    with S101_JSON.open(encoding="ascii") as handle:
        reference = json.load(handle)["results"]
    usecols = ["game", "date", "ts", "phase", "arm", "nominal", "p", "y", "lo_static", "hi_static", "lo_aci", "hi_aci"]
    ticks = pd.read_csv(S101_TICKS, compression="gzip", usecols=usecols)
    cells, diffs = [], []
    for arm in s101.ARMS:
        for nominal in s101.NOMINALS:
            key = "%s|%.2f" % (arm, nominal)
            routed = s101.score(ticks[(ticks["arm"] == arm) & (ticks["nominal"] == nominal)], nominal)["static"]
            for cell in PHASES:
                expected, observed = reference[key]["static"][cell]["coverage"], routed[cell]["coverage"]
                diff = None if expected is None or observed is None else abs(float(expected) - float(observed))
                cells.append({"arm": arm, "nominal": nominal, "cell": cell, "committed_coverage": expected,
                              "replayed_coverage": observed, "abs_difference": diff})
                if diff is not None:
                    diffs.append(diff)
    maximum = max(diffs, default=0.0)
    return {"committed_json": str(S101_JSON.relative_to(REPO)), "retained_screen": str(S101_TICKS.relative_to(REPO)),
            "n_cells": len(cells), "max_abs_coverage_diff": maximum, "tolerance": 1e-9,
            "passes": maximum <= 1e-9, "cells": cells}


def run() -> dict[str, Any]:
    """Score the sealed sample and write only the new S265 archives."""
    before_current, before_peak = _memory("before_scoring")
    raw, membership = _sample_raw()
    rows = _rows(raw)
    del raw
    seeded = incumbent.apply_incumbent(rows, "ladder_base", s101.EMBARGO_DAYS).copy()
    seeded["p_incumbent"] = seeded["p_e4"]
    static, archive = {}, []
    for nominal in s101.NOMINALS:
        ticks, folds = _walk_forward(seeded, nominal)
        cells = s101.score(ticks, nominal)["static"]
        for cell in PHASES:
            cells[cell]["mean_interval_half_width"] = (None if cells[cell]["coverage"] is None
                                                         else float(cells[cell]["mean_interval_width"]) / 2.0)
        static["%.2f" % nominal] = {"n_scored_ticks": int(len(ticks)), "n_scored_games": int(ticks["game"].nunique()),
                                     "folds": folds, "cells": cells}
        archive.extend(_archive_groups(ticks, nominal, cells))
    paired = seeded.groupby("game", sort=True).agg(date=("date", "min"), timestamp_start=("ts", "min"),
        timestamp_end=("ts", "max"), n_ticks=("y", "size"), incumbent_brier=("p_incumbent", lambda p: float(np.mean((p - seeded.loc[p.index, "y"]) ** 2))),
        market_brier=("market", lambda p: float(np.mean((p - seeded.loc[p.index, "y"]) ** 2)))).reset_index()
    paired["record_type"] = "paired_loss"
    pd.concat([membership, paired, pd.DataFrame(archive)], ignore_index=True, sort=False).to_csv(PAIR_CSV, index=False, encoding="ascii")
    del rows, seeded, archive, paired, membership
    gc.collect()
    regression = _s101_regression()
    assert regression["passes"], "S101 regression did not match committed JSON"
    gc.collect()
    current, peak = _memory("after_scoring")
    report = {"row": "S265 attempt 1b", "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "prereg": {"path": str(PREREG.relative_to(REPO)), "seal_sha256": prereg_seal()},
              "source": {"path": str(s86.CHECKPOINTS.relative_to(REPO)), "n_ticks": 465249, "n_games": 1593,
                         "sample_seed": SEED, "sample_ticks": 79919, "sample_games": 269},
              "design": {"folds": s101.N_FOLDS, "purge": "game-disjoint", "symmetric_embargo_days": s101.EMBARGO_DAYS,
                         "coverage_min_group": s101.COVERAGE_MIN_GROUP, "coverage_max_groups": s101.COVERAGE_MAX_GROUPS,
                         "nominals": list(s101.NOMINALS), "grouped_cells": list(PHASES)},
              "rss": {"before_current_bytes": before_current, "before_peak_bytes": before_peak,
                      "after_current_bytes": current, "peak_bytes": peak}, "static": static,
              "s101_regression": regression, "paired_loss_series": {"path": str(PAIR_CSV.relative_to(REPO)), "sha256": _hash(PAIR_CSV)},
              "code_identity": {"s265": _hash(Path(__file__)), "s86": _hash(Path(s86.__file__)), "s101": _hash(Path(s101.__file__)),
                                "s123": _hash(Path(incumbent.__file__)), "aci_online": _hash(Path(aci_online.__file__))}}
    OUT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="ascii")
    return report


if __name__ == "__main__":
    report = run()
    print("S265 seed %d sample %d ticks / %d games" % (SEED, 79919, 269))
    for nominal, result in report["static"].items():
        for cell, value in result["cells"].items():
            print("STATIC nominal=%s cell=%s n=%s coverage=%s half_width=%s absent=%s" %
                  (nominal, cell, value["n"], value["coverage"], value.get("mean_interval_half_width"), value.get("absent_because")))
    print("S101 24-cell max_abs_coverage_diff=%s" % report["s101_regression"]["max_abs_coverage_diff"])

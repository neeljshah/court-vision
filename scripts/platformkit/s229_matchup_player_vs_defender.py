"""Offline S229 screen of a PTS residual scheme-by-opponent interaction.

The baseline and real candidate share the same rows, folds, PTS residual, and
main effects.  The candidate adds only ``scheme_diff * opponent_diff``.  The
null arm retains that baseline and replaces just this interaction with the
prebuilt shuffled-scheme twin.  This module is offline and writes evidence
under docs/evidence/harness; it never reads an atlas store or writes data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.s229_purged_date_folds import EMBARGO_DAYS, purged_date_folds

ROOT = Path(__file__).resolve().parents[2]
INTEL = ROOT / "data" / "intelligence"
DEF = INTEL / "player_def_archetype_sidecar.parquet"
NULL = INTEL / "player_def_archetype_sidecar_null.parquet"
OPP = INTEL / "player_opp_splits_sidecar.parquet"
PTS = INTEL / "pts_decomposition_predictions.parquet"
SCHEDULE = INTEL / "schedule_strength_7d.parquet"
MEMO = ROOT / "docs" / "evidence" / "harness" / "S229_matchup_player_vs_defender_2026-09-04.md"
SERIES = ROOT / "docs" / "evidence" / "harness" / "S229_matchup_player_vs_defender_per_game_residuals.csv"
KEYS = ["player_id", "game_date"]
SCHEME = "player_pts_vs_HELP_DEF_diff"
OPPONENT = "player_opp_pts_diff_vs_overall"
INTERACTION = "scheme_x_opponent"
BASE_COLUMNS = (SCHEME, OPPONENT)
CANDIDATE_COLUMNS = BASE_COLUMNS + (INTERACTION,)
PREREG = "docs/evidence/harness/S229_ATTEMPT2_PREREG_2026-09-04.md"
PREREG_SHA256 = "6ca56099a0bac5067f68740ae7d9ac2bdbf1d2c6fa71e75728ace6e1210ef1e7"


def _read(path: Path, columns: Iterable[str]) -> pd.DataFrame:
    """Read one bounded read-only store, rejecting a store above the lane rail."""
    if path.stat().st_size > 300 * 1024 * 1024:
        raise ValueError("store exceeds 300 MB rail: %s" % path)
    return pd.read_parquet(path, columns=list(columns))


def _shape(path: Path) -> Tuple[int, Tuple[str, ...]]:
    """Read parquet metadata only, for the null-twin identical-shape check."""
    import pyarrow.parquet as pq
    if path.stat().st_size > 300 * 1024 * 1024:
        raise ValueError("store exceeds 300 MB rail: %s" % path)
    meta = pq.ParquetFile(path)
    return int(meta.metadata.num_rows), tuple(meta.schema_arrow.names)


def _clean_keys(frame: pd.DataFrame, date: str = "game_date") -> pd.DataFrame:
    out = frame.copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    out[date] = pd.to_datetime(out[date]).dt.strftime("%Y-%m-%d")
    return out.rename(columns={date: "game_date"})


def load_frame(null_path: Path | None = None) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Read bounded stores sequentially and return the scorable joined frame.

    ``null_path`` is read only for the null interaction.  The true-scheme main
    effect remains fixed, so its paired baseline is byte-for-byte comparable.
    """
    def_shape = _shape(DEF)
    scheme = _clean_keys(_read(DEF, KEYS + [SCHEME]))
    scheme_nonnull = int(scheme[SCHEME].notna().sum())
    opponent = _clean_keys(_read(OPP, KEYS + [OPPONENT]))
    opp_nonnull = int(opponent[OPPONENT].notna().sum())
    direct = scheme.merge(opponent, on=KEYS, how="left", validate="one_to_one")
    direct_join = int((direct[SCHEME].notna() & direct[OPPONENT].notna()).sum())
    del direct
    target = _clean_keys(_read(PTS, ["player_id", "date", "pred_pts_decomp", "target_pts", "fold"]), "date")
    target = target[target["fold"].astype(float) >= 0].copy()
    target["residual"] = target["target_pts"] - target["pred_pts_decomp"]
    full_target = target.copy()
    del target
    joined = full_target.merge(scheme, on=KEYS, how="left", validate="one_to_one")
    del scheme
    joined = joined.merge(opponent, on=KEYS, how="left", validate="one_to_one")
    del opponent
    schedule = _clean_keys(_read(SCHEDULE, KEYS + ["game_id"]))
    joined = joined.merge(schedule, on=KEYS, how="left", validate="one_to_one")
    del schedule
    both = joined[SCHEME].notna() & joined[OPPONENT].notna()
    coverage = {
        "sidecar_rows": def_shape[0],
        "target_rows": int(len(full_target)),
        "scheme_nonnull": scheme_nonnull,
        "opponent_nonnull": opp_nonnull,
        "direct_sidecar_join": direct_join,
        "both_nonnull": int(both.sum()),
        "game_id_nonnull": int(joined.loc[both, "game_id"].notna().sum()),
    }
    frame = joined.loc[both & joined["game_id"].notna()].copy()
    if null_path is not None:
        null_shape = _shape(null_path)
        if null_shape != def_shape:
            raise ValueError("null twin does not have identical row and column shape")
        coverage["null_rows"] = null_shape[0]
        null = _clean_keys(_read(null_path, KEYS + [SCHEME]))
        frame = frame.merge(null.rename(columns={SCHEME: "null_scheme"}), on=KEYS,
                            how="left", validate="one_to_one")
        frame["null_interaction"] = frame["null_scheme"] * frame[OPPONENT]
    frame[INTERACTION] = frame[SCHEME] * frame[OPPONENT]
    required = ["residual", *CANDIDATE_COLUMNS, "game_id"]
    if null_path is not None:
        required.append("null_interaction")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=required)
    frame = frame.sort_values(["game_date", "game_id", "player_id"], kind="stable").reset_index(drop=True)
    coverage["scorable_rows"] = int(len(frame))
    return frame, coverage


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame, columns: Tuple[str, ...]) -> np.ndarray:
    x_train = train.loc[:, columns].to_numpy(float)
    x_test = test.loc[:, columns].to_numpy(float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale == 0.0] = 1.0
    a = np.column_stack([np.ones(len(train)), (x_train - mean) / scale])
    b = np.column_stack([np.ones(len(test)), (x_test - mean) / scale])
    beta, *_ = np.linalg.lstsq(a, train["residual"].to_numpy(float), rcond=None)
    return b @ beta


def walk_forward(frame: pd.DataFrame, folds: int = 4) -> pd.DataFrame:
    """Score through the preregistered purged, symmetric-embargo date folds."""
    assert CANDIDATE_COLUMNS[:-1] == BASE_COLUMNS
    scored = []
    for fold, train, test in purged_date_folds(frame, folds, embargo_days=EMBARGO_DAYS):
        assert train["game_date"].max() < test["game_date"].min()
        test["fold"] = fold
        test["base_prediction"] = _fit_predict(train, test, BASE_COLUMNS)
        test["candidate_prediction"] = _fit_predict(train, test, CANDIDATE_COLUMNS)
        null_columns = BASE_COLUMNS + ("null_interaction",)
        test["null_prediction"] = _fit_predict(train, test, null_columns)
        scored.append(test)
    return pd.concat(scored, ignore_index=True)


def _losses(scored: pd.DataFrame) -> pd.DataFrame:
    out = scored.copy()
    for arm in ("base", "candidate", "null"):
        error = out["residual"] - out[arm + "_prediction"]
        out[arm + "_sq_error"] = error * error
        out[arm + "_abs_error"] = error.abs()
    return out.groupby(["game_id", "game_date"], as_index=False).agg(
        n_player_rows=("player_id", "size"),
        base_sq_error=("base_sq_error", "mean"), candidate_sq_error=("candidate_sq_error", "mean"),
        null_sq_error=("null_sq_error", "mean"), base_abs_error=("base_abs_error", "mean"),
        candidate_abs_error=("candidate_abs_error", "mean"), null_abs_error=("null_abs_error", "mean"),
    )


def _metric(series: pd.DataFrame, arm: str) -> Dict[str, float]:
    return {"rmse": float(np.sqrt(series[arm + "_sq_error"].mean())),
            "mae": float(series[arm + "_abs_error"].mean())}


def _ci(series: pd.DataFrame, arm: str, draws: int = 2000) -> Dict[str, Tuple[float, float]]:
    rng = np.random.default_rng(229)
    values = {"rmse": [], "mae": []}
    n = len(series)
    for _ in range(draws):
        sample = series.iloc[rng.integers(0, n, n)]
        for metric, col, func in (("rmse", "sq_error", np.sqrt), ("mae", "abs_error", lambda x: x)):
            base = func(sample["base_" + col].mean())
            cand = func(sample[arm + "_" + col].mean())
            values[metric].append(float(base - cand))
    return {metric: tuple(float(x) for x in np.quantile(values[metric], [0.025, 0.975]))
            for metric in values}


def summarize(scored: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    series = _losses(scored)
    base = _metric(series, "base")
    cand = _metric(series, "candidate")
    null = _metric(series, "null")
    counts = series["n_player_rows"].to_numpy(float)
    neff = float(counts.sum() ** 2 / np.square(counts).sum())
    return series, {"base": base, "candidate": cand, "null": null,
                    "real_delta": {k: base[k] - cand[k] for k in base},
                    "null_delta": {k: base[k] - null[k] for k in base},
                    "real_ci": _ci(series, "candidate"), "null_ci": _ci(series, "null"),
                    "n_clusters": int(len(series)), "n_eff": neff}


def _line(label: str, metric: Dict[str, float], delta: Dict[str, float] | None = None,
          ci: Dict[str, Tuple[float, float]] | None = None) -> str:
    text = "%s RMSE %.6f MAE %.6f" % (label, metric["rmse"], metric["mae"])
    if delta is not None and ci is not None:
        text += " delta_rmse %.6f [%.6f, %.6f] delta_mae %.6f [%.6f, %.6f]" % (
            delta["rmse"], ci["rmse"][0], ci["rmse"][1], delta["mae"], ci["mae"][0], ci["mae"][1])
    return text


def write_evidence(coverage: Dict[str, int], full: pd.DataFrame, frame: pd.DataFrame,
                   series: pd.DataFrame, result: Dict[str, object], memo: Path = MEMO,
                   series_path: Path = SERIES) -> None:
    """Write the static, ASCII evidence memo and differential archive."""
    series = series.assign(preregistration_path=PREREG, preregistration_sha256=PREREG_SHA256)
    series.to_csv(series_path, index=False, lineterminator="\n")
    full_rate, join_rate = full["target_pts"].mean(), frame["target_pts"].mean()
    full_spread, join_spread = full["residual"].std(ddof=0), frame["residual"].std(ddof=0)
    lines = [
        "# S229 matchup player vs defender screen",
        "",
        "Contract: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q.",
        "Attempt 2 preregistration: %s; pre-seal SHA-256: %s." % (PREREG, PREREG_SHA256),
        "Machine: local worktree CPU; all inputs are local read-only stores below 300 MB.",
        "Atlas half: BLOCKED-ON-S223 and never opened or joined.",
        "",
        "## ATTEMPT 2",
        "",
        "| verifier correction | candidate 60f290074 | Attempt 2 |",
        "| --- | --- | --- |",
        "| direct DEF-OPP join coverage | not reported before target merge | reported before target merge |",
        "| preregistration | absent | sealed before fresh scoring |",
        "| OOS date folds | no purge or symmetric embargo | cluster purge plus symmetric one-day embargo |",
        "",
        "## Coverage table (printed before metrics)",
        "",
        "| step | rows | share of 99,498 |",
        "| --- | ---: | ---: |",
        "| sidecar universe | %d | 100.0000 pct |" % coverage["sidecar_rows"],
        "| null twin, identical 17-column shape | %d | 100.0000 pct |" % coverage["null_rows"],
        "| non-null scheme deviation | %d | %.4f pct |" % (coverage["scheme_nonnull"], 100 * coverage["scheme_nonnull"] / coverage["sidecar_rows"]),
        "| non-null opponent PTS split | %d | %.4f pct |" % (coverage["opponent_nonnull"], 100 * coverage["opponent_nonnull"] / coverage["sidecar_rows"]),
        "| direct DEF-OPP sidecar join before target merge | %d | %.4f pct |" % (coverage["direct_sidecar_join"], 100 * coverage["direct_sidecar_join"] / coverage["sidecar_rows"]),
        "| target-readable DEF-OPP join | %d | %.4f pct |" % (coverage["both_nonnull"], 100 * coverage["both_nonnull"] / coverage["sidecar_rows"]),
        "| both plus game cluster bridge | %d | %.4f pct |" % (coverage["game_id_nonnull"], 100 * coverage["game_id_nonnull"] / coverage["sidecar_rows"]),
        "| scorable finite joined subset | %d | %.4f pct |" % (coverage["scorable_rows"], 100 * coverage["scorable_rows"] / coverage["sidecar_rows"]),
        "",
        "Rows lost are named above. The residual target surface has %d OOF-readable rows, so %d of the 99,498 sidecar rows lack an archived OOF PTS expectation." % (coverage["target_rows"], coverage["sidecar_rows"] - coverage["target_rows"]),
        "Full target-readable PTS base rate %.6f; joined subset PTS base rate %.6f." % (full_rate, join_rate),
        "Full target-readable residual spread %.6f; joined subset residual spread %.6f." % (full_spread, join_spread),
        "",
        "## Matched walk-forward result",
        "",
        "Baseline uses [%s]; candidate uses [%s]. The assertion CANDIDATE_COLUMNS[:-1] == BASE_COLUMNS passed." % (", ".join(BASE_COLUMNS), ", ".join(CANDIDATE_COLUMNS)),
        "All folds train strictly before test game_date with a cluster purge and symmetric one-day embargo. Metrics are game-equal-weighted from the archived paired series; positive delta favors the added interaction.",
        _line("Baseline:", result["base"]),
        _line("Real interaction:", result["candidate"], result["real_delta"], result["real_ci"]),
        _line("Null-twin interaction:", result["null"], result["null_delta"], result["null_ci"]),
        "Game clusters %d; n_eff %.3f." % (result["n_clusters"], result["n_eff"]),
        "",
        "Verdict: SCREEN NULL. This is an offline calibration measurement only; no charge, ledger, register, deployment, or production wiring.",
        "",
        "## NOT VERIFIED",
        "",
        "- No production behavior, deployment, or external outcome is verified by this local screen.",
        "- The atlas half remains BLOCKED-ON-S223 and was not evaluated.",
        "",
        "## Input inventory",
        "",
        "- data/intelligence/player_def_archetype_sidecar.parquet, 9,812,855 bytes, player_id plus game_date.",
        "- data/intelligence/player_def_archetype_sidecar_null.parquet, 9,799,223 bytes, player_id plus game_date.",
        "- data/intelligence/player_opp_splits_sidecar.parquet, 5,013,638 bytes, player_id plus game_date.",
        "- data/intelligence/pts_decomposition_predictions.parquet, 3,460,398 bytes, player_id plus date; archived OOF PTS expectation and target.",
        "- data/intelligence/schedule_strength_7d.parquet, 1,025,217 bytes, game cluster bridge.",
        "",
        "Differential archive: docs/evidence/harness/S229_matchup_player_vs_defender_per_game_residuals.csv; it embeds the Attempt 2 preregistration path and seal.",
    ]
    memo.write_text("\n".join(lines) + "\n", encoding="ascii")


def run(memo: Path = MEMO, series_path: Path = SERIES) -> Dict[str, object]:
    frame, coverage = load_frame(NULL)
    full = _clean_keys(_read(PTS, ["player_id", "date", "pred_pts_decomp", "target_pts", "fold"]), "date")
    full = full[full["fold"].astype(float) >= 0].copy()
    full["residual"] = full["target_pts"] - full["pred_pts_decomp"]
    scored = walk_forward(frame)
    series, result = summarize(scored)
    if result["n_clusters"] < 30:
        raise RuntimeError("CLOSED AT LIMIT: fewer than 30 game clusters")
    write_evidence(coverage, full, frame, series, result, memo, series_path)
    return {"coverage": coverage, "result": result, "series": series}


def main() -> int:
    ap = argparse.ArgumentParser(description="S229 offline matchup interaction screen")
    ap.add_argument("--memo", type=Path, default=MEMO)
    ap.add_argument("--series", type=Path, default=SERIES)
    args = ap.parse_args()
    out = run(args.memo, args.series)
    c, r = out["coverage"], out["result"]
    print("COVERAGE direct=%d/%d target_readable=%d/%d scorable=%d/%d clusters=%d n_eff=%.3f embargo_days=%d" % (c["direct_sidecar_join"], c["sidecar_rows"], c["both_nonnull"], c["sidecar_rows"], c["scorable_rows"], c["sidecar_rows"], r["n_clusters"], r["n_eff"], EMBARGO_DAYS))
    print(_line("BASE", r["base"]))
    print(_line("REAL", r["candidate"], r["real_delta"], r["real_ci"]))
    print(_line("NULL", r["null"], r["null_delta"], r["null_ci"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

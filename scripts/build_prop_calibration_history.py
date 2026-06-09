"""Build per-player prop-calibration history from OOF prediction/actual pairs.

Source of truth: data/cache/pregame_oof.parquet -- long-format walk-forward OOF
with (player_id, stat, oof_pred, actual) for all 7 stats, fully populated.

Interval coverage: the OOF files do NOT carry per-prediction lower/upper bounds,
so we reconstruct a nominal Gaussian interval per (player_id, stat) using the
per-player `sigma` emitted in the live prediction cache
(predictions_cache_2026-05-26.parquet). q50 +/- z*sigma. This tests the model's
emitted uncertainty against OOF actuals where a sigma is available; it is a
reconstruction, not the literal interval emitted at each historical prediction.

Output: data/cache/prop_calibration_history.parquet  (one row per player_id x stat)
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"
OUT = CACHE / "prop_calibration_history.parquet"

MIN_OBS = 5
NOMINAL_LEVEL = 0.90  # two-sided gaussian interval reconstructed from sigma
Z = norm.ppf(0.5 + NOMINAL_LEVEL / 2.0)  # ~1.645 for 0.90

def main():
    oof = pd.read_parquet(CACHE / "pregame_oof.parquet")
    oof = oof[["player_id", "stat", "oof_pred", "actual"]].dropna(subset=["oof_pred", "actual"])

    # Per-player+stat sigma from live cache for reconstructed interval coverage
    cache = pd.read_parquet(CACHE / "predictions_cache_2026-05-26.parquet")
    sig = (cache[["player_id", "stat", "sigma"]]
           .dropna(subset=["sigma"])
           .drop_duplicates(["player_id", "stat"]))

    df = oof.merge(sig, on=["player_id", "stat"], how="left")
    df["err"] = df["oof_pred"] - df["actual"]
    df["abs_err"] = df["err"].abs()
    df["sq_err"] = df["err"] ** 2

    # in-interval flag only where sigma is available
    has_sig = df["sigma"].notna() & (df["sigma"] > 0)
    lower = df["oof_pred"] - Z * df["sigma"]
    upper = df["oof_pred"] + Z * df["sigma"]
    df["in_interval"] = np.where(
        has_sig, ((df["actual"] >= lower) & (df["actual"] <= upper)).astype(float), np.nan
    )

    rows = []
    for (pid, stat), g in df.groupby(["player_id", "stat"]):
        n = len(g)
        if n < MIN_OBS:
            continue
        cov_g = g["in_interval"].dropna()
        rows.append({
            "player_id": int(pid),
            "stat": stat,
            "n": int(n),
            "mean_pred": float(g["oof_pred"].mean()),
            "mean_actual": float(g["actual"].mean()),
            "bias": float(g["err"].mean()),  # mean_pred - mean_actual
            "mae": float(g["abs_err"].mean()),
            "rmse": float(np.sqrt(g["sq_err"].mean())),
            "n_interval": int(len(cov_g)),
            "interval_coverage": float(cov_g.mean()) if len(cov_g) else np.nan,
            "interval_nominal": NOMINAL_LEVEL,
        })

    out = pd.DataFrame(rows).sort_values(["player_id", "stat"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)

    # ---- verification ----
    print(f"WROTE {OUT}")
    print(f"total rows         : {len(out)}")
    print(f"distinct players   : {out['player_id'].nunique()}")
    print(f"stats covered      : {sorted(out['stat'].unique())}")
    print()
    # aggregate across player-stat rows weighted by n (matches raw-row aggregate)
    print("per-stat aggregate (obs-weighted across player-stat rows):")
    print(f"{'stat':<6}{'players':>8}{'tot_obs':>9}{'agg_MAE':>10}{'agg_RMSE':>10}"
          f"{'mean_bias':>11}{'mean_cov':>10}{'cov_n':>9}")
    for stat, gs in out.groupby("stat"):
        tot = gs["n"].sum()
        agg_mae = float((gs["mae"] * gs["n"]).sum() / tot)
        agg_rmse = float(np.sqrt((gs["rmse"] ** 2 * gs["n"]).sum() / tot))
        mean_bias = float((gs["bias"] * gs["n"]).sum() / tot)
        cv = gs.dropna(subset=["interval_coverage"])
        cov_tot = cv["n_interval"].sum()
        mean_cov = (float((cv["interval_coverage"] * cv["n_interval"]).sum() / cov_tot)
                    if cov_tot else float("nan"))
        print(f"{stat:<6}{gs['player_id'].nunique():>8}{int(tot):>9}{agg_mae:>10.4f}"
              f"{agg_rmse:>10.4f}{mean_bias:>11.4f}{mean_cov:>10.4f}{int(cov_tot):>9}")
    print(f"\n(interval = q50 +/- {Z:.3f}*sigma, reconstructed Gaussian, nominal={NOMINAL_LEVEL})")

if __name__ == "__main__":
    main()

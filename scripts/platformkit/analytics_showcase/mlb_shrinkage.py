"""
MLB empirical-Bayes shrinkage exhibit: for three small-sample rate leaderboards
(catcher out-of-zone strike rate, umpire out-of-zone strike rate, batter
on-base rate vs LHP) shows how the raw "leader" regresses toward the group
mean once a beta-binomial prior fit from the group itself is applied. This is
the honest companion to a raw leaderboard -- it is the DISCOUNT a small-n rate
deserves, not a new skill claim.

DESCRIPTIVE_ONLY, edge_claimed:false. Reads the same LOCAL Statcast-derived
parquets as mlb_descriptive_leaderboards.py under data/domains/mlb/, same
fixed 2022-2023 / statcast_fuller_v1 observation window, same clone-safe
recorded-artifact pattern (--check reloads the committed JSON and does not
require data/ locally).

Method (beta-binomial, method-of-moments prior fit per group):
  p_i = k_i/n_i (raw rate); m = sum(k_i)/sum(n_i) (pooled mean).
  Binomial sampling variance each rate would show under one shared true rate m
  is m*(1-m)/n_i; the EXCESS variance of the observed p_i over that binomial
  floor is attributed to a Beta(alpha, beta) prior on the true rate. Solving
  Var(p_i) = m*(1-m)/kappa (the Beta-Binomial moment identity, kappa=alpha+beta)
  for kappa given the observed excess gives:
    kappa = m*(1-m) / max(Var(p_i) - mean(m*(1-m)/n_i), tiny) - 1
  floored to a small positive constant if the estimate is <=0 or non-finite
  (i.e. the group shows no more spread than binomial noise alone -- shrink
  hard). alpha = m*kappa, beta = (1-m)*kappa.
  shrunk_i = (k_i + alpha) / (n_i + alpha + beta)   -- the posterior mean.
  regression_i = p_i - shrunk_i                      -- how far it moved.

Usage:
  python -m scripts.platformkit.analytics_showcase.mlb_shrinkage
  python -m scripts.platformkit.analytics_showcase.mlb_shrinkage --check
"""
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = Path(__file__).resolve().parents[3]
OUT_JSON = HERE / "out" / "mlb_shrinkage.json"

MLB_DIR = REPO / "data" / "domains" / "mlb"
CATCHER_PATH = MLB_DIR / "catcher_framing_index.parquet"
UMPIRE_PATH = MLB_DIR / "umpire_zone_index.parquet"
PLATOON_PATH = MLB_DIR / "platoon_split_index.parquet"
NEEDED = [CATCHER_PATH, UMPIRE_PATH, PLATOON_PATH]

PLATOON_PA_FLOOR = 20
TOP_N = 12
KAPPA_FLOOR = 1.0
TINY = 1e-9

METHOD = (
    "Beta-binomial prior fit per group by method of moments: pooled mean "
    "m = sum(k)/sum(n); kappa (=alpha+beta) solved from the Beta-Binomial "
    "moment identity Var(p_i) = m*(1-m)/kappa, i.e. "
    "kappa = m*(1-m) / max(Var(p_i) - mean(m*(1-m)/n_i), tiny) - 1, floored "
    "to 1.0 if the raw rates show no more spread than binomial sampling "
    "noise alone (non-finite or <=0 estimate). alpha=m*kappa, beta=(1-m)*kappa. "
    "shrunk_i = (k_i+alpha)/(n_i+alpha+beta) is the posterior mean; "
    "regression_i = p_i - shrunk_i."
)


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO)).replace("\\", "/")


def _fit_kappa(m: float, n: np.ndarray, p: np.ndarray) -> float:
    var_p = float(np.var(p, ddof=1))
    expected_binom_var = float(np.mean(m * (1.0 - m) / n))
    denom = var_p - expected_binom_var
    if denom > TINY:
        kappa = m * (1.0 - m) / denom - 1.0
    else:
        kappa = float("nan")
    if not math.isfinite(kappa) or kappa <= 0:
        kappa = KAPPA_FLOOR
    return kappa


def _assert_direction(p: np.ndarray, shrunk: np.ndarray, n: np.ndarray, m: float, label: str) -> None:
    above = p > m
    below = p < m
    assert np.all(shrunk[above] < p[above]), f"{label}: above-mean row did not shrink downward"
    assert np.all(shrunk[below] > p[below]), f"{label}: below-mean row did not shrink upward"
    median_n = float(np.median(n))
    small = np.abs(p - shrunk)[n < median_n]
    large = np.abs(p - shrunk)[n >= median_n]
    if len(small) and len(large):
        assert float(small.mean()) > float(large.mean()), f"{label}: small-n rows did not move more on average"


def _shrink_group(df: pd.DataFrame, name_col: str, k_col: str, n_col: str, rate_col: str, label: str) -> dict:
    n = df[n_col].to_numpy(dtype=float)
    k = df[k_col].to_numpy(dtype=float)
    p = df[rate_col].to_numpy(dtype=float)
    names = df[name_col].astype(str).to_numpy()

    m = float(k.sum() / n.sum())
    kappa = _fit_kappa(m, n, p)
    alpha = m * kappa
    beta = (1.0 - m) * kappa

    shrunk = (k + alpha) / (n + alpha + beta)
    regression = p - shrunk

    _assert_direction(p, shrunk, n, m, label)

    order = np.argsort(-np.abs(regression))
    biggest = [
        {
            "name": str(names[i]),
            "n": int(n[i]),
            "raw_rate": round(float(p[i]), 4),
            "shrunk_rate": round(float(shrunk[i]), 4),
            "regression": round(float(regression[i]), 4),
        }
        for i in order[:TOP_N]
    ]

    order_shrunk = np.argsort(-shrunk)
    top_shrunk = [
        {
            "name": str(names[i]),
            "n": int(n[i]),
            "raw_rate": round(float(p[i]), 4),
            "shrunk_rate": round(float(shrunk[i]), 4),
        }
        for i in order_shrunk[:TOP_N]
    ]

    return {
        "label": label,
        "n_entities": int(len(df)),
        "pooled_mean": round(m, 4),
        "alpha": round(alpha, 2),
        "beta": round(beta, 2),
        "kappa": round(kappa, 2),
        "biggest_regressors": biggest,
        "top_by_shrunk": top_shrunk,
    }


def build() -> dict:
    missing = [_rel(p) for p in NEEDED if not p.exists()]
    if missing:
        return {"status": "local_corpus_absent", "sport": "mlb", "needed_artifacts": missing}

    catcher = pd.read_parquet(CATCHER_PATH)
    umpire = pd.read_parquet(UMPIRE_PATH)
    platoon = pd.read_parquet(PLATOON_PATH)
    platoon_q = platoon[platoon["pa_vs_l"] >= PLATOON_PA_FLOOR]

    catcher_group = _shrink_group(
        catcher, "catcher_name", "ooz_strikes", "n_ooz_called", "ooz_strike_rate",
        "Catcher out-of-zone strike rate (NOT a framing/called-strike rate; descriptive)",
    )
    umpire_group = _shrink_group(
        umpire, "umpire_name", "ooz_strikes", "n_ooz_called", "ooz_strike_rate",
        "Umpire out-of-zone strike rate (NOT a framing/called-strike rate; descriptive)",
    )
    platoon_group = _shrink_group(
        platoon_q, "batter_name", "on_base_vs_l", "pa_vs_l", "rate_vs_l",
        "On-base rate vs LHP (descriptive)",
    )
    platoon_group["key"] = "platoon_vs_lhp"
    platoon_group["floor"] = f"pa_vs_l>={PLATOON_PA_FLOOR}"
    catcher_group["key"] = "catcher_ooz"
    umpire_group["key"] = "umpire_ooz"

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": (
            "Small-sample rate leaders regress toward the group mean under "
            "empirical-Bayes shrinkage; the raw leaderboard overstates them."
        ),
        "method": METHOD,
        "observation_window": {
            "seasons": str(catcher["season"].iloc[0]),
            "corpus_id": str(catcher["corpus_id"].iloc[0]),
            "as_of": str(catcher["as_of"].iloc[0]),
            "note": "fixed 2022-2023 slice",
        },
        "groups": [catcher_group, umpire_group, platoon_group],
        "confounds": [
            "shrinkage assumes the entities are exchangeable draws from one prior -- a modeling choice, not a fact;",
            "the OOZ rate is descriptive, NOT a called-strike/framing skill and NOT predictive;",
            "the raw vs shrunk gap is the point: it shows how much a small-sample rate should be discounted, it is not a new 'true skill' claim;",
            "fixed 2022-2023 window.",
        ],
    }


def main() -> dict:
    result = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    if result["status"] == "ok":
        for g in result["groups"]:
            top = g["biggest_regressors"][0]
            print(
                f"{g['key']}: pooled_mean={g['pooled_mean']} kappa={g['kappa']} "
                f"biggest_regressor={top['name']} n={top['n']} "
                f"raw={top['raw_rate']}->shrunk={top['shrunk_rate']}"
            )
    else:
        print(json.dumps(result, indent=2))
    print(f"wrote {OUT_JSON}")
    return result


_BANNED_TERMS = ("predictive_receipt", "correlation", "rho", "edge_receipt")


def _no_nan(obj) -> bool:
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(_no_nan(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_nan(v) for v in obj)
    return True


def _check():
    assert OUT_JSON.exists(), f"missing {OUT_JSON} -- run the module (no --check) first"
    assert OUT_JSON.stat().st_size > 0, f"{OUT_JSON} is empty"
    result = json.loads(OUT_JSON.read_text(encoding="ascii"))
    assert result["status"] in ("ok", "local_corpus_absent"), result["status"]

    if result["status"] == "ok":
        assert result["descriptive_only"] is True
        assert result["edge_claimed"] is False
        assert result["observation_window"]["seasons"] == "2022_2023"

        groups = result["groups"]
        assert len(groups) == 3, f"expected 3 groups, got {len(groups)}"

        for g in groups:
            m = g["pooled_mean"]
            assert math.isfinite(m) and 0 < m < 1, f"{g['key']}: bad pooled_mean {m}"
            assert g["alpha"] > 0 and g["beta"] > 0 and g["kappa"] > 0, f"{g['key']}: non-positive alpha/beta/kappa"

            rows = g["biggest_regressors"]
            assert len(rows) > 0
            prev_abs = None
            for r in rows:
                raw, shrunk = r["raw_rate"], r["shrunk_rate"]
                lo, hi = min(raw, m), max(raw, m)
                assert lo < shrunk < hi or raw == m, (
                    f"{g['key']}/{r['name']}: shrunk {shrunk} not strictly between "
                    f"raw {raw} and pooled_mean {m}"
                )
                cur_abs = abs(r["regression"])
                if prev_abs is not None:
                    assert cur_abs <= prev_abs + 1e-9, f"{g['key']}: |regression| not non-increasing"
                prev_abs = cur_abs

        blob = json.dumps(result).lower()
        for term in _BANNED_TERMS:
            assert term not in blob, f"banned predictive/edge term found: {term}"

        assert _no_nan(result), "NaN/inf found in emitted numbers"
    else:
        assert "needed_artifacts" in result
    print("OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        main()

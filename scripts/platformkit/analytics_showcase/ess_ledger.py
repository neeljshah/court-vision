"""Effective Sample Size (ESS) ledger -- how independent is our headline row count?

Pure composition of ONE already-committed artifact (residual_autocorrelation.json):
restates each corpus's n_records as how many effectively-independent observations
it really is, using the ALREADY-MEASURED within-game lag-1 residual autocorrelation
(rho). No new data, no new science -- just an honest re-statement of a number we
already produced.

Why this matters: the game outcome is TERMINAL and constant within a game, so the
win-prob path is smooth and consecutive rows are near-duplicates (that is exactly
what residual_autocorrelation.py measured). Two independence estimates:
  * ESS_AR1   -- standard AR(1) effective-sample-size approximation from rho.
  * n_games   -- the distinct within-game series count, a CONSERVATIVE anchor
                 (can never claim more independent points than distinct games).
The reported ess_anchor = min(ESS_AR1, n_games): never claim more independence
than either estimate allows.

DESCRIPTIVE_ONLY, edge_claimed=False -- this deflates our OWN sample sizes; it
is not a signal, an edge, or a $/ROI claim of any kind.

Usage:
    python -m scripts.platformkit.analytics_showcase.ess_ledger
    python -m scripts.platformkit.analytics_showcase.ess_ledger --check
"""
import json
import math
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHOWCASE = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase")
IN_JSON = os.path.join(SHOWCASE, "out", "residual_autocorrelation.json")
OUT_JSON = os.path.join(SHOWCASE, "out", "ess_ledger.json")

# Verified expected shape of the source artifact (guards against upstream drift).
EXPECTED = {
    "mlb": {"n_records": 78986, "n_series": 227, "model_median": 0.9809, "market_median": 0.9799,
            "model_n_games": 222, "market_n_games": 225},
    "soccer_intl": {"n_records": 9003, "n_series": 51, "model_median": 0.9624, "market_median": 0.9489,
                    "model_n_games": 51, "market_n_games": 51},
}


def _assert_expected(sports):
    for sport, exp in EXPECTED.items():
        assert sport in sports, f"expected corpus '{sport}' missing from source artifact"
        s = sports[sport]
        assert s["n_records"] == exp["n_records"], (sport, "n_records", s["n_records"])
        assert s["n_series"] == exp["n_series"], (sport, "n_series", s["n_series"])
        assert s["model"]["median"] == exp["model_median"], (sport, "model.median", s["model"]["median"])
        assert s["market"]["median"] == exp["market_median"], (sport, "market.median", s["market"]["median"])
        assert s["model"]["n_games"] == exp["model_n_games"], (sport, "model.n_games", s["model"]["n_games"])
        assert s["market"]["n_games"] == exp["market_n_games"], (sport, "market.n_games", s["market"]["n_games"])


def compute_corpus(sport, s):
    n_rows = s["n_records"]
    n_games = s["n_series"]
    rho = s["model"]["median"]
    rho_market = s["market"]["median"]

    ess_ar1 = int(n_rows * (1 - rho) / (1 + rho))  # AR(1) effective sample size, floored
    ess_anchor = min(ess_ar1, n_games)
    infl_ar1 = round(math.sqrt(n_rows / ess_ar1), 1)
    infl_anchor = round(math.sqrt(n_rows / ess_anchor), 1)

    return {
        "sport": sport,
        "n_rows": n_rows,
        "n_games": n_games,
        "rho_model": round(rho, 4),
        "rho_market": round(rho_market, 4),
        "ess_ar1": ess_ar1,
        "ess_anchor": ess_anchor,
        "infl_ar1": infl_ar1,
        "infl_anchor": infl_anchor,
    }


def _headline(corpora):
    worst = max(corpora, key=lambda c: c["infl_anchor"])
    return (f"{worst['sport']}: {worst['n_rows']:,} residual rows carry the independent "
            f"information of at most ~{worst['ess_anchor']} games.")


def build():
    with open(IN_JSON, encoding="utf-8") as f:
        source = json.load(f)
    sports = source["sports"]
    _assert_expected(sports)

    corpora = [compute_corpus(sport, sports[sport]) for sport in EXPECTED]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "descriptive_only": True,
        "edge_claimed": False,
        "headline": _headline(corpora),
        "method": ("ESS from the already-committed lag-1 within-game residual autocorrelation "
                   "(rho); because the game outcome is terminal-constant the probability path is "
                   "smooth, so consecutive rows are near-duplicates rather than independent draws. "
                   "The distinct-game count is the conservative anchor and the AR(1) figure is an "
                   "approximation, so the reported ess_anchor takes the minimum of the two."),
        "formula": "ESS_AR1 = n_rows * (1 - rho) / (1 + rho); CI inflation = sqrt(n_rows / ESS)",
        "source_artifact": "scripts/platformkit/analytics_showcase/out/residual_autocorrelation.json",
        "confound": ("AR(1) is a first-order approximation of a smooth terminal-constant path, not "
                     "a full independence model; the distinct-game count is the conservative anchor. "
                     "DESCRIPTIVE_ONLY -- this deflates our OWN sample sizes and makes no edge or ROI "
                     "claim."),
        "corpora": corpora,
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return payload


def _print_table(corpora):
    header = f"{'sport':<14}{'n_rows':>10}{'ess_ar1':>10}{'n_games':>10}{'ess_anchor':>12}{'infl_anchor':>13}"
    print(header)
    print("-" * len(header))
    for c in corpora:
        print(f"{c['sport']:<14}{c['n_rows']:>10}{c['ess_ar1']:>10}{c['n_games']:>10}"
              f"{c['ess_anchor']:>12}{c['infl_anchor']:>13}")


def check():
    payload = build()
    corpora = {c["sport"]: c for c in payload["corpora"]}
    assert set(corpora) == set(EXPECTED), corpora.keys()
    for sport, c in corpora.items():
        assert c["ess_anchor"] <= c["ess_ar1"], (sport, "ess_anchor > ess_ar1")
        assert c["ess_anchor"] <= c["n_games"], (sport, "ess_anchor > n_games")
        assert c["ess_ar1"] >= 1 and c["ess_anchor"] >= 1, (sport, "ess < 1")
        assert c["infl_anchor"] >= c["infl_ar1"], (sport, "infl_anchor < infl_ar1")
        assert c["infl_ar1"] > 1.0 and c["infl_anchor"] > 1.0, (sport, "inflation not > 1.0")
        for k in ("ess_ar1", "ess_anchor", "infl_ar1", "infl_anchor"):
            v = c[k]
            assert not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))), (sport, k, v)
    mlb = corpora["mlb"]
    assert mlb["ess_anchor"] == 227, mlb["ess_anchor"]
    assert abs(mlb["infl_anchor"] - 18.7) < 1e-9, mlb["infl_anchor"]
    print("OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        p = build()
        print(p["headline"])
        _print_table(p["corpora"])

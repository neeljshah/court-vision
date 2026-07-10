"""domains.mlb.knowledge.validate_contact_park_interaction -- mechanism #41
(C14): does a batter's trailing (as-of, strictly-prior) contact quality
interact with the park run-environment to predict batted-ball scoring
outcome (estimated_woba_using_speedangle), BEYOND what the two additive
(base) terms alone explain?

Scope: batted-ball PAs only (rows with a launch_speed reading), same
population `validate_contact_park.py`'s contact-quality checks use.

Leak audit: `trailing_contact` for a PA is an EXPANDING mean of that
batter's launch_speed over strictly-PRIOR batted balls (shift(1) after
`expanding().mean()`), sorted by (batter, game_date, game_pk,
at_bat_number) -- future-into-past leak-free by construction. `park_factor`
(avg total-runs/game per home_team) is computed separately PER HALF, using
ONLY that half's games, so a half's park factor never sees the other
half's data either.

Method: split-half by date (the same within-season reliability design as
the sibling park/contact checks) is used here as the >=2-corpora
replication requirement. Per half, the INTERACTION TERM's contribution
beyond the additive base is isolated by partial correlation: outcome and
(contact*park) are each residualized against the base design matrix
[1, contact, park] via OLS, then Pearson-correlated -- a standard
interaction-beyond-additive-terms test, using only numpy/scipy (already a
project dependency here, no statsmodels needed).

Run: python -m domains.mlb.knowledge.validate_contact_park_interaction
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.mlb.knowledge._data import DEFAULT_SEASON, LEDGER_PATH, load_season, pa_final_pitch
from scripts.platformkit.io_atomic import append_jsonl_atomic

ALPHA = 0.01
MIN_TRAILING_BBE = 15   # min prior batted-ball events for a trailing-contact estimate to count
MIN_ROWS = 200
MIN_EFFECT = 0.02       # partial-correlation bar (small by design -- an interaction term is a
                         # second-order effect on top of two already-explanatory base terms)


def build_pa_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per batted-ball PA with batter/date/park/outcome + as-of
    trailing_contact (strictly prior batted-ball launch_speed mean)."""
    pa = pa_final_pitch(df).dropna(
        subset=["estimated_woba_using_speedangle", "launch_speed", "game_date", "batter", "home_team"]).copy()
    pa["game_date"] = pd.to_datetime(pa["game_date"])
    pa = pa.sort_values(["batter", "game_date", "game_pk", "at_bat_number"]).reset_index(drop=True)
    pa["trailing_contact"] = pa.groupby("batter")["launch_speed"].transform(
        lambda s: s.expanding().mean().shift(1))
    pa["trailing_n"] = pa.groupby("batter")["launch_speed"].transform(
        lambda s: s.expanding().count().shift(1))
    return pa[pa["trailing_n"] >= MIN_TRAILING_BBE].copy()


def _park_factor(last_pitch: pd.DataFrame, mid, half_label: str) -> pd.Series:
    """Avg total-runs/game per home_team, computed from ONE half's games only."""
    half = last_pitch[last_pitch["game_date"] <= mid] if half_label == "h1" else last_pitch[last_pitch["game_date"] > mid]
    return half.groupby("home_team")["total_runs"].mean()


def _residualize(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def interaction_beyond_additive(pa_half: pd.DataFrame, half_label: str) -> Dict[str, Any]:
    n = len(pa_half)
    hyp = "contact_park_interaction__%s" % half_label
    if n < MIN_ROWS:
        return {"hypothesis": hyp, "n": int(n), "effect": None, "p": None, "verdict": "NOT_TESTABLE",
                "note": "insufficient rows after as-of trailing-contact + half-local park-factor join (n=%d)" % n}
    contact = pa_half["trailing_contact"].to_numpy(dtype=float)
    park = pa_half["park_factor"].to_numpy(dtype=float)
    outcome = pa_half["estimated_woba_using_speedangle"].to_numpy(dtype=float)
    interaction = contact * park
    X_base = np.column_stack([np.ones(n), contact, park])
    resid_out = _residualize(outcome, X_base)
    resid_int = _residualize(interaction, X_base)
    r, p = stats.pearsonr(resid_out, resid_int)
    return {"hypothesis": hyp, "n": int(n), "effect": round(float(r), 4), "p": float(p),
            "verdict": _verdict(p, r, MIN_EFFECT),
            "note": "partial corr of (trailing_contact x park_factor) vs wOBA outcome, controlling for "
                    "base terms [trailing_contact, park_factor], n=%d, half=%s" % (n, half_label)}


def _verdict(p: float, effect: float, min_abs_effect: float) -> str:
    if p is None or effect is None or (isinstance(p, float) and np.isnan(p)):
        return "NOT_TESTABLE"
    return "CONFIRMED_LOCAL" if (p < ALPHA and abs(effect) >= min_abs_effect) else "NULL_LOCAL"


def _combine(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    testable = [r for r in rows if r["verdict"] != "NOT_TESTABLE"]
    sig = [r for r in testable if r["p"] < ALPHA]
    if len(testable) < 2:
        verdict = "NOT_TESTABLE"
    elif len(sig) >= 2 and len({1 if r["effect"] > 0 else -1 for r in sig}) == 1:
        verdict = "CONFIRMED_LOCAL"
    elif len(sig) == 1:
        verdict = "PROVISIONAL"
    else:
        verdict = "NULL_LOCAL"
    return {"hypothesis": "contact_park_interaction__combined", "n": int(sum(r["n"] for r in rows)),
            "effect": None, "p": None, "verdict": verdict,
            "note": "split-half-by-date replication: %s"
                    % "; ".join("%s(p=%s,eff=%s)" % (r["hypothesis"], r["p"], r["effect"]) for r in rows)}


def run(season: int = DEFAULT_SEASON) -> List[Dict[str, Any]]:
    df = load_season(season)
    pa = build_pa_frame(df)
    mid = pa["game_date"].median()

    last_pitch = df.sort_values(["game_pk", "at_bat_number", "pitch_number"]).groupby(
        "game_pk", sort=False).tail(1)
    last_pitch = last_pitch.dropna(subset=["post_home_score", "post_away_score", "game_date", "home_team"]).copy()
    last_pitch["game_date"] = pd.to_datetime(last_pitch["game_date"])
    last_pitch["total_runs"] = last_pitch["post_home_score"] + last_pitch["post_away_score"]

    rows = []
    for half_label, mask in (("h1", pa["game_date"] <= mid), ("h2", pa["game_date"] > mid)):
        pa_half = pa[mask].copy()
        pf = _park_factor(last_pitch, mid, half_label)
        pa_half["park_factor"] = pa_half["home_team"].map(pf)
        pa_half = pa_half.dropna(subset=["park_factor"])
        rows.append(interaction_beyond_additive(pa_half, half_label))
    rows.append(_combine(rows))

    for r in rows:
        r["sport"] = "mlb"
        r["corpus"] = "savant_full__%d (split-half by date)" % season
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-38s %-16s n=%-8s effect=%s p=%s -- %s" % (
            r["hypothesis"], r["verdict"], r["n"], r["effect"], r["p"], r["note"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """Smallest runnable check: residualization removes the base terms'
    own linear signal, and verdict thresholds behave as declared."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=500)
    y = 3.0 * x + rng.normal(scale=0.01, size=500)
    X = np.column_stack([np.ones(500), x])
    resid = _residualize(y, X)
    assert abs(np.corrcoef(resid, x)[0, 1]) < 0.05  # residual no longer correlates with the regressor
    assert _verdict(0.001, 0.5, 0.02) == "CONFIRMED_LOCAL"
    assert _verdict(0.5, 0.5, 0.02) == "NULL_LOCAL"
    assert _verdict(float("nan"), 0.5, 0.02) == "NOT_TESTABLE"
    print("self-check OK")

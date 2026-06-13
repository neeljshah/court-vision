"""scripts.platformkit.proof_tennis.gate_test_asof — HONEST as-of serve/return gate test.

First time the tennis platform has player-level LEAK-FREE as-of serve/return form
(domains.tennis.asof_features, from the W59/W60 match_stats sidecar).  Threads those
prior-only trailing rates (diff_1st_win_asof, diff_ace_rate_asof, etc.) through the
REAL honest gate (src.loop.gate.evaluate) to test whether deeper tennis data raises
prediction quality beyond the Elo-only base.

DISCIPLINE (binding): expected verdict REJECT or DEFER (efficient market; prior-only
serve/return rates very likely REDUNDANT with the Elo base — player quality already
priced).  A SHIP verdict is logged as a PROBABLE ARTIFACT; NO edge is ever claimed
here.  Leak-freeness is INHERITED: base/target/closing come from the proven
TennisAdapter._feature_bundle_impl construction; the as-of column is prior-only
trailing aggregate (snapshot-before-update, guaranteed by asof_features.py).

_build_base_bundle_with_ids REPLICATES _feature_bundle_impl EXACTLY (5 base cols:
elo_diff, surface_elo_diff, best_of, rest_days_a, rest_days_b; target=winner;
dates, devigged closing; skip-winner-NaN, date order) but ALSO collects each kept
row's event_id 1:1 so the as-of table aligns by event_id.
Default seasons = [2022, 2023, 2024, 2025] (high match_stats coverage; honest).

F5: stdlib, numpy, pandas, domains.tennis.adapter (read-only), src.loop.{gate,signal},
    catalog_common.  PRIVATE: never committed publicly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.tennis.adapter import TennisAdapter
from domains.tennis.adapter_helpers import _add_rest_days, _devig_prob
from domains.tennis.elo import walk_forward_elo
from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import derive_bundle

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "tennis" / "asof_features.parquet"

# Recent seasons with highest match_stats sidecar coverage (honest restriction).
_ASOF_SEASONS: Tuple[int, ...] = (2022, 2023, 2024, 2025)

# Candidate as-of diff columns that the gate tests — pure transforms of leak-free
# prior-only player rates; selected dynamically from the parquet schema.
_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "diff_1st_win_asof",
    "diff_ace_rate_asof",
    "diff_1st_in_asof",
    "diff_2nd_win_asof",
    "diff_bp_saved_asof",
)


# --------------------------------------------------------------------------- #
# Base bundle construction (replicates adapter_helpers._feature_bundle_impl
# EXACTLY but also collects event_id 1:1 per kept row)
# --------------------------------------------------------------------------- #
def _build_base_bundle_with_ids(
    seasons: Optional[Sequence[int]] = None,
    adapter: Optional[TennisAdapter] = None,
) -> Tuple[FeatureBundle, List[str]]:
    """REPLICATE TennisAdapter._feature_bundle_impl EXACTLY + return per-kept-row event_ids.

    Same 5 base cols (elo_diff, surface_elo_diff, best_of, rest_days_a, rest_days_b),
    target=winner (1.0 = p1 wins), dates, closing=_devig_prob(row), same skip-winner-NaN,
    same date order — but also collect the event_id of every kept row, aligned 1:1 to the
    bundle rows.  Returns (bundle, event_ids).
    """
    adapter = adapter or TennisAdapter()
    matches_df = adapter._get_matches()

    _seasons = list(seasons) if seasons is not None else list(_ASOF_SEASONS)
    if _seasons:
        if "season" in matches_df.columns:
            matches_df = matches_df[matches_df["season"].isin(_seasons)]
        else:
            year_col = pd.to_datetime(matches_df["date"]).dt.year
            matches_df = matches_df[year_col.isin(_seasons)]

    wf = walk_forward_elo(matches_df)
    wf = _add_rest_days(wf)

    # Join odds (same as _feature_bundle_impl).
    try:
        odds_df = adapter._get_odds()
        has_odds = True
    except FileNotFoundError:
        has_odds = False
        odds_df = pd.DataFrame()

    _ODDS_COLS = ["event_id", "ps_p1", "ps_p2", "b365_p1", "b365_p2"]
    if has_odds and not odds_df.empty:
        _odds_sel = odds_df[[c for c in _ODDS_COLS if c in odds_df.columns]].copy()
        _odds_sel = _odds_sel.drop_duplicates("event_id", keep="first")
        wf = wf.merge(_odds_sel, on="event_id", how="left")
    else:
        for _c in _ODDS_COLS[1:]:
            if _c not in wf.columns:
                wf[_c] = np.nan

    rows_base: List[List[float]] = []
    rows_signal: List[float] = []
    rows_target: List[float] = []
    rows_dates: List[str] = []
    rows_closing: List[float] = []
    event_ids: List[str] = []

    for _, row in wf.iterrows():
        if pd.isna(row.get("winner", np.nan)):
            continue
        winner_val = float(row["winner"])
        target_val = 1.0 if winner_val == 1 else 0.0

        elo_diff = float(row.get("p1_elo", 1500.0)) - float(row.get("p2_elo", 1500.0))
        surf_diff = float(row.get("p1_surface_elo", 1500.0)) - float(
            row.get("p2_surface_elo", 1500.0))
        best_of = float(row.get("best_of", 3.0))
        rest_a = float(row.get("rest_days_a", 15.0))
        rest_b = float(row.get("rest_days_b", 15.0))

        close_val = _devig_prob(row, kind="close")

        rows_base.append([elo_diff, surf_diff, best_of, rest_a, rest_b])
        rows_signal.append(float(row.get("win_prob_p1", 0.5)))
        rows_target.append(target_val)
        rows_dates.append(str(pd.to_datetime(row["date"]).date()))
        rows_closing.append(close_val)
        event_ids.append(str(row["event_id"]))

    if not rows_base:
        raise ValueError(
            f"_build_base_bundle_with_ids: no rows for seasons={_seasons}.")

    closing_arr = np.array(rows_closing, dtype=float)
    bundle = FeatureBundle(
        base=np.array(rows_base, dtype=float),
        signal_col=np.array(rows_signal, dtype=float),
        target=np.array(rows_target, dtype=float),
        dates=rows_dates,
        lines=None,
        closing=closing_arr if not np.all(np.isnan(closing_arr)) else None,
    )
    return bundle, event_ids


# --------------------------------------------------------------------------- #
# As-of alignment
# --------------------------------------------------------------------------- #
def _align_asof(
    asof_df: pd.DataFrame, event_ids: Sequence[str], col: str
) -> np.ndarray:
    """Map event_id -> col value; return array aligned to event_ids (NaN where absent).

    No derived columns for tennis (all candidate cols are direct diff_* columns).
    """
    series = pd.to_numeric(asof_df[col], errors="coerce")
    lut: Dict[str, float] = dict(zip(asof_df["event_id"].astype(str), series))
    return np.array([lut.get(str(e), np.nan) for e in event_ids], dtype=float)


def _candidate_columns(asof_df: pd.DataFrame) -> List[str]:
    """Pick candidate as-of cols that the parquet schema actually supports."""
    cols = set(asof_df.columns)
    return [c for c in _PREFERRED_CANDIDATES if c in cols]


# --------------------------------------------------------------------------- #
# Minimal Signal subclass holding a candidate's name + REJECT hypothesis
# --------------------------------------------------------------------------- #
class _ArraySignal(Signal):
    """Carrier Signal: name set per candidate; gate reads its injected _gate_matrix."""
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas: List[str] = []
    emits: List[str] = []

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def build(self, ctx: AsOfContext) -> SignalValue:  # not used (matrix injected)
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name, target="winprob", scope="pregame",
            statement=f"As-of player serve/return rate '{self.name}' added to Elo base.",
            rationale=(
                "Prior-only trailing serve/return form; very likely REDUNDANT with "
                "Elo (player quality already priced). REJECT/DEFER expected; "
                "NO edge claimed.  Deeper data = calibration ceiling, not market edge."
            ),
            source="seed", expected_verdict="REJECT", priority="P2")


# --------------------------------------------------------------------------- #
# The honest gate test
# --------------------------------------------------------------------------- #
def run_gate_test(
    seasons: Optional[Sequence[int]] = None,
    asof_path: Optional[Path] = None,
) -> List[dict]:
    """Run each candidate as-of column through the REAL gate; return verdict rows.

    Builds the base bundle + aligned event_ids ONCE, then for each candidate column
    derives a bundle (Elo base + as-of signal_col) and calls evaluate(..., n_splits=3).
    SHIP verdicts are logged as PROBABLE ARTIFACT; no edge is claimed.
    """
    _seasons = list(seasons) if seasons is not None else list(_ASOF_SEASONS)
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_features.parquet not found at {apath}. Run "
            "domains.tennis.asof_features first.")
    asof_df = pd.read_parquet(apath)

    bb, event_ids = _build_base_bundle_with_ids(seasons=_seasons)
    n = bb.base.shape[0]
    candidates = _candidate_columns(asof_df)

    rows: List[dict] = []
    for col in candidates:
        sc = _align_asof(asof_df, event_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"tennis_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "TENNIS AS-OF SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
        rows.append({
            "name": sig.name, "column": col, "verdict": verdict,
            "coverage": round(coverage, 4), "n": n,
            "wf_folds": r.wf_folds, "wf_all_improve": r.wf_all_improve,
            "ablation_delta": r.ablation_delta, "ablation_pass": r.ablation_pass,
            "null_pass": r.null_pass, "calibration_ok": r.calibration_ok,
            "clv": r.clv, "p_value": r.p_value, "reason": r.reason,
        })
    return rows


def _summary_line(rows: List[dict]) -> str:
    """One honest headline summary line."""
    if not rows:
        return "Tennis as-of serve/return: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return (
            "Tennis as-of serve/return: SHIP flagged for " + ", ".join(ships) +
            " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return (
        "Tennis as-of serve/return: " + "/".join(verds) +
        " -> NO edge; markets efficient / redundant with Elo; "
        "calibration ceiling deepened only.")


def main() -> int:
    """CLI: run the as-of serve/return gate test on materialized parquets; print honestly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test()
    hdr = (f"{'Candidate':<30} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} "
           f"{'abl':>5} {'null':>5} {'calib':>6} {'p':>8}")
    print(
        "\nTennis as-of serve/return gate test "
        "(REAL gate; seasons=" + ",".join(str(s) for s in _ASOF_SEASONS) + ")")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        p = r["p_value"]
        print(f"{r['name']:<30} {r['verdict']:<8} {r['coverage']:>6.3f} "
              f"{str(r['wf_all_improve']):>7} {str(r['ablation_pass']):>5} "
              f"{str(r['null_pass']):>5} {str(r['calibration_ok']):>6} "
              f"{('%.4f' % p) if p is not None else '   -':>8}")
    print("-" * len(hdr))
    print(_summary_line(rows))
    print("(REJECT/DEFER = honest success; no edge is ever claimed here.)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "_build_base_bundle_with_ids", "_align_asof", "_candidate_columns",
    "_ArraySignal", "run_gate_test", "_summary_line", "main",
]

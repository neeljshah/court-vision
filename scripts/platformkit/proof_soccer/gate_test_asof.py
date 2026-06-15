"""scripts.platformkit.proof_soccer.gate_test_asof — HONEST as-of shot-quality gate test.

Materializes the soccer deep-data sidecar (match_stats + asof_features) and threads
prior-only rolling SoT / shot-quality form columns through the REAL honest gate
(src.loop.gate.evaluate).  Completes funnel validation for soccer.

DISCIPLINE (binding):
  Expected verdict REJECT or DEFER — deeper data raises calibration ceiling, NOT a
  market edge.  A REJECT is an honest success.  If SHIP fires it is logged as a
  PROBABLE ARTIFACT; NO edge is ever claimed here.
  Leak-freeness INHERITED: base/target/closing come from the proven SoccerAdapter
  feature_bundle construction; every as-of column is prior-only (snapshot-before-update
  walk-forward in domains.soccer.asof_features).

_build_base_bundle_with_ids REPLICATES SoccerAdapter.feature_bundle EXACTLY
(5 base cols [lam_home, lam_away, lam_total, rest_days_home, rest_days_away],
signal_col=p_over25, target=target_over25, dates, devigged open/close lines)
but ALSO collects each kept row's event_id 1:1 so the as-of table aligns by event_id.

F5: stdlib, numpy, pandas, domains.soccer.adapter (read-only),
    src.loop.{gate,signal}, scripts.platformkit.catalog_common.
PRIVATE: combined with odds this module is price-bearing; never committed publicly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.soccer.adapter import SoccerAdapter, _add_rest_days, _devig_over
from domains.soccer.ratings import walk_forward_goals
from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import derive_bundle

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "soccer" / "asof_features.parquet"

# Candidate as-of diff columns from ASOF_COLS contract (asof_features.py).
# All are pure transforms of prior-only team SoT / shot rates; expected REJECT.
# Selected dynamically from the parquet schema (see _candidate_columns).
_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "diff_sot_for_asof",       # home - away prior SoT-for diff (free xG proxy)
    "diff_sot_against_asof",   # home - away prior SoT-against diff (defensive proxy)
    "diff_shots_for_asof",     # home - away prior shots-for diff
    "home_sot_ratio_for_asof", # home SoT/shots ratio (prior attacking quality)
)


# --------------------------------------------------------------------------- #
# Base bundle construction (replicates adapter.feature_bundle + collects event_id)
# --------------------------------------------------------------------------- #

def _build_base_bundle_with_ids(
    seasons: Optional[Sequence[int]] = None,
    adapter: Optional[SoccerAdapter] = None,
) -> Tuple[FeatureBundle, List[str]]:
    """REPLICATE SoccerAdapter.feature_bundle EXACTLY + return per-kept-row event_ids.

    Same 5 base cols [lam_home, lam_away, lam_total, rest_days_home, rest_days_away],
    signal_col=p_over25, target=target_over25, dates, devigged open/close lines —
    but also collect the event_id of every kept row, aligned 1:1 to the bundle rows.
    Returns (bundle, event_ids).
    """
    adapter = adapter or SoccerAdapter()
    matches_df = adapter._get_matches()
    if seasons:
        matches_df = matches_df[matches_df["season"].isin(seasons)]

    wf = walk_forward_goals(matches_df)
    wf = _add_rest_days(wf)

    try:
        odds_df = adapter._get_odds()
        has_odds = not odds_df.empty
    except FileNotFoundError:
        has_odds = False
        odds_df = pd.DataFrame()

    _ODDS_COLS = ["event_id", "ou_prematch_over", "ou_prematch_under",
                  "ou_close_over", "ou_close_under"]
    if has_odds:
        _odds_sel = odds_df[[c for c in _ODDS_COLS if c in odds_df.columns]].copy()
        _odds_sel = _odds_sel.drop_duplicates("event_id", keep="first")
        wf = wf.merge(_odds_sel, on="event_id", how="left")
    else:
        for _c in _ODDS_COLS[1:]:
            if _c not in wf.columns:
                wf[_c] = np.nan

    rows_base: List[List[float]] = []
    rows_sig: List[float] = []
    rows_tgt: List[float] = []
    rows_dates: List[str] = []
    rows_lines: List[float] = []
    rows_closing: List[float] = []
    event_ids: List[str] = []

    for _, row in wf.iterrows():
        tgt_raw = row.get("target_over25", np.nan)
        if pd.isna(tgt_raw):
            continue
        line_val = _devig_over(row.get("ou_prematch_over"), row.get("ou_prematch_under"))
        close_val = _devig_over(row.get("ou_close_over"), row.get("ou_close_under"))
        rows_base.append([
            float(row["lam_home"]), float(row["lam_away"]),
            float(row["lam_total"]),
            float(row.get("rest_days_home", 15.0)),
            float(row.get("rest_days_away", 15.0)),
        ])
        rows_sig.append(float(row["p_over25"]))
        rows_tgt.append(float(tgt_raw))
        rows_dates.append(str(pd.to_datetime(row["date"]).date()))
        rows_lines.append(line_val)
        rows_closing.append(close_val)
        event_ids.append(str(row["event_id"]))

    if not rows_base:
        raise ValueError(
            f"_build_base_bundle_with_ids: no rows for seasons={list(seasons or [])}.")

    la = np.array(rows_lines, dtype=float)
    cl = np.array(rows_closing, dtype=float)
    bundle = FeatureBundle(
        base=np.array(rows_base, dtype=float),
        signal_col=np.array(rows_sig, dtype=float),
        target=np.array(rows_tgt, dtype=float),
        dates=rows_dates,
        lines=la if not np.all(np.isnan(la)) else None,
        closing=cl if not np.all(np.isnan(cl)) else None,
    )
    return bundle, event_ids


# --------------------------------------------------------------------------- #
# As-of alignment
# --------------------------------------------------------------------------- #

def _align_asof(
    asof_df: pd.DataFrame,
    event_ids: Sequence[str],
    col: str,
) -> np.ndarray:
    """Map event_id -> col value; return array aligned to event_ids (NaN where absent)."""
    series = pd.to_numeric(asof_df[col], errors="coerce")
    lut: Dict[str, float] = dict(zip(asof_df["event_id"].astype(str), series))
    return np.array([lut.get(str(eid), np.nan) for eid in event_ids], dtype=float)


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
            statement=f"As-of SoT/shot form '{self.name}' added to Poisson O/U 2.5 base.",
            rationale=(
                "Prior-only rolling SoT / shot-quality team form; very likely REDUNDANT "
                "with Poisson lambda (goal rates already price shot quality). "
                "REJECT/DEFER expected; NO edge claimed.  Deeper substrate only."
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
    derives a bundle (Poisson base + as-of signal_col) and calls
    evaluate(..., n_splits=3).  SHIP verdicts are logged as PROBABLE ARTIFACT; no
    edge is claimed.
    """
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_features.parquet not found at {apath}.  Run "
            "domains.soccer.asof_features first.")
    asof_df = pd.read_parquet(apath)

    bb, event_ids = _build_base_bundle_with_ids(seasons=seasons)
    n = bb.base.shape[0]
    candidates = _candidate_columns(asof_df)

    rows: List[dict] = []
    for col in candidates:
        sc = _align_asof(asof_df, event_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"soccer_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "SOCCER AS-OF SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
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
        return "Soccer SoT as-of: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return ("Soccer SoT as-of: SHIP flagged for " + ", ".join(ships) +
                " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return ("Soccer SoT as-of: " + "/".join(verds) +
            " -> NO edge; markets efficient / SoT rates redundant with Poisson lambda; "
            "calibration substrate deepened only.")


def main() -> int:
    """CLI: run the as-of shot-quality gate test on materialized parquets; print honestly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test()
    hdr = (f"{'Candidate':<30} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} "
           f"{'abl':>5} {'null':>5} {'calib':>6} {'p':>8}")
    print("\nSoccer as-of SoT/shot-quality gate test (REAL gate; all seasons)")
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

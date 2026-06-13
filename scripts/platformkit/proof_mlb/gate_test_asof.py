"""scripts.platformkit.proof_mlb.gate_test_asof — HONEST SP as-of gate test for MLB.

Starting pitcher is the #1 MLB predictor.  ``domains.mlb.asof_features`` builds
leak-free walk-forward SP-form signals (home/away trailing runs-allowed, diff) keyed
1:1 to ``games.parquet`` by ``event_id``.  This script threads those prior-only SP-form
features through the REAL honest gate (src.loop.gate.evaluate) to test whether
SP-form adds win-prediction value OVER the Elo base.

DISCIPLINE (binding): expected verdict REJECT or DEFER (efficient market; SP-form is
very likely priced into the line already, and the runs-allowed proxy mixes bullpen
innings with the starter's).  A SHIP verdict is logged as PROBABLE ARTIFACT.
NO edge is ever claimed here.  Leak-freeness is INHERITED: base/target/closing come
from the proven MLBAdapter.feature_bundle construction; the as-of columns are
prior-only walk-forward (snapshot-before-update).

_build_base_bundle_with_ids REPLICATES feature_bundle EXACTLY (6 base cols, all
pre-game: elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate;
target=target_home_win, dates, devigged dec_close_home/away; skip-target-NaN, date
order) but ALSO collects each kept row's event_id 1:1 so the as-of table aligns by
event_id.  Default seasons = all SBRO years (2010-2021).

F5: stdlib, numpy, pandas, domains.mlb.adapter (read-only), src.loop.{gate,signal},
catalog_common.  PRIVATE: never committed publicly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.mlb.adapter import MLBAdapter, _add_context, _devig2_home
from domains.mlb.ratings import walk_forward_elo
from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import derive_bundle

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "mlb" / "asof_features.parquet"

# Candidate as-of columns the gate tests, in order of informational priority.
# Each is a pure transform of prior-only walk-forward SP-form data.
# Selected dynamically from the parquet schema (see _candidate_columns).
_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "sp_ra_diff_asof",       # headline: away_sp_ra - home_sp_ra (higher -> home edge)
    "home_sp_ra_asof",       # home SP trailing runs-allowed mean
    "away_sp_ra_asof",       # away SP trailing runs-allowed mean
)


# --------------------------------------------------------------------------- #
# Base bundle construction (replicates adapter.feature_bundle + collects event_id)
# --------------------------------------------------------------------------- #

def _build_base_bundle_with_ids(
    seasons: Optional[Sequence[int]] = None,
    adapter: Optional[MLBAdapter] = None,
) -> Tuple[FeatureBundle, List[str]]:
    """REPLICATE MLBAdapter.feature_bundle EXACTLY + return per-kept-row event_ids.

    Same 6 base cols (elo_home, elo_away, elo_diff_hfa, rest_days_home,
    rest_days_away, h2h_rate), target=target_home_win, devigged dec_close closing,
    same skip-target-NaN, same date order — but also collect the event_id of every
    kept row, aligned 1:1 to the bundle rows.  Returns (bundle, event_ids).
    """
    adapter = adapter or MLBAdapter()
    games_df = adapter._get_games()
    if seasons:
        games_df = games_df[games_df["season"].isin(list(seasons))]

    wf = _add_context(walk_forward_elo(games_df))

    try:
        odds_df = adapter._get_odds()
        has_odds = not odds_df.empty
    except FileNotFoundError:
        has_odds = False
        odds_df = pd.DataFrame()

    _ODDS_COLS = ["event_id", "dec_open_home", "dec_open_away",
                  "dec_close_home", "dec_close_away"]
    if has_odds and not odds_df.empty:
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
    rows_close: List[float] = []
    event_ids: List[str] = []

    for _, row in wf.iterrows():
        tgt = row.get("target_home_win", np.nan)
        if pd.isna(tgt):
            continue
        lv = _devig2_home(row.get("dec_open_home"), row.get("dec_open_away"))
        cv = _devig2_home(row.get("dec_close_home"), row.get("dec_close_away"))
        rows_base.append([
            float(row["elo_home"]), float(row["elo_away"]),
            float(row["elo_diff_hfa"]),
            float(row.get("rest_days_home", 5.0)),
            float(row.get("rest_days_away", 5.0)),
            float(row.get("h2h_rate", 0.5)),
        ])
        rows_sig.append(float(row["p_home_elo"]))
        rows_tgt.append(float(tgt))
        rows_dates.append(str(pd.to_datetime(row["date"]).date()))
        rows_lines.append(lv)
        rows_close.append(cv)
        event_ids.append(str(row["event_id"]))

    if not rows_base:
        raise ValueError(
            f"_build_base_bundle_with_ids: no rows for seasons={list(seasons or [])}.")

    la = np.array(rows_lines, dtype=float)
    ca = np.array(rows_close, dtype=float)
    bundle = FeatureBundle(
        base=np.array(rows_base, dtype=float),
        signal_col=np.array(rows_sig, dtype=float),
        target=np.array(rows_tgt, dtype=float),
        dates=rows_dates,
        lines=la if not np.all(np.isnan(la)) else None,
        closing=ca if not np.all(np.isnan(ca)) else None,
    )
    return bundle, event_ids


# --------------------------------------------------------------------------- #
# As-of alignment
# --------------------------------------------------------------------------- #

def _align_asof(
    asof_df: pd.DataFrame, event_ids: Sequence[str], col: str
) -> np.ndarray:
    """Map event_id -> col value; return array aligned to event_ids (NaN where absent)."""
    series = pd.to_numeric(asof_df[col], errors="coerce")
    lut: Dict[str, float] = dict(zip(asof_df["event_id"].astype(str), series))
    return np.array([lut.get(str(e), np.nan) for e in event_ids], dtype=float)


def _candidate_columns(asof_df: pd.DataFrame) -> List[str]:
    """Return the candidate as-of cols that the parquet schema actually supports."""
    cols = set(asof_df.columns)
    return [c for c in _PREFERRED_CANDIDATES if c in cols]


# --------------------------------------------------------------------------- #
# Minimal Signal subclass (one per candidate column)
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
            statement=f"As-of SP-form '{self.name}' added to the Elo base matrix.",
            rationale=(
                "Prior-only SP trailing runs-allowed; likely REDUNDANT with Elo "
                "(team quality priced) and mixes bullpen innings. REJECT/DEFER "
                "expected; NO edge claimed.  REJECT = honest success."
            ),
            source="seed", expected_verdict="REJECT", priority="P2",
        )


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
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_features.parquet not found at {apath}. "
            "Run: python -m domains.mlb.asof_features")

    asof_df = pd.read_parquet(apath)
    bb, event_ids = _build_base_bundle_with_ids(seasons=seasons)
    n = bb.base.shape[0]
    candidates = _candidate_columns(asof_df)
    if not candidates:
        logger.warning("No candidate columns found in %s. Nothing to test.", apath)

    rows: List[dict] = []
    for col in candidates:
        sc = _align_asof(asof_df, event_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"mlb_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "MLB AS-OF SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
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
        return "MLB SP as-of: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return (
            "MLB SP as-of: SHIP flagged for " + ", ".join(ships) +
            " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required)."
        )
    return (
        "MLB SP as-of: " + "/".join(verds) +
        " -> NO edge; markets efficient / SP-form redundant with Elo; "
        "calibration deepened only."
    )


def main() -> int:
    """CLI: run the SP as-of gate test on the materialized parquets; print honestly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test()
    hdr = (f"{'Candidate':<28} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} "
           f"{'abl':>5} {'null':>5} {'calib':>6} {'p':>8}")
    print("\nMLB SP as-of gate test (REAL gate; seasons=2010-2021; SP-form vs Elo base)")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        p = r["p_value"]
        print(f"{r['name']:<28} {r['verdict']:<8} {r['coverage']:>6.3f} "
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

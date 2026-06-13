"""scripts.platformkit.proof_basketball_nba.gate_test_asof — HONEST as-of AST gate test.

First time the platform has box-score-derived LEAK-FREE as-of features
(domains.basketball_nba.asof_features, from the W59 box sidecar).  Threads those
prior-only team rates (assist-rate diff, home assist rate, pace, oreb-diff)
through the REAL honest gate (src.loop.gate.evaluate) to test the reg-season
ASSIST-RATE edge documented in MEMORY.md.

DISCIPLINE (binding): expected verdict REJECT or DEFER (efficient market; as-of
rates very likely REDUNDANT with the Elo base — team quality already priced).  A
SHIP verdict is logged as a PROBABLE ARTIFACT; NO edge is ever claimed here.
Leak-freeness is INHERITED: base/target/closing come from the proven
NBAAdapter.feature_bundle construction; the as-of column is prior-only.

_build_base_bundle_with_ids REPLICATES feature_bundle EXACTLY (8 base cols,
target=home_win, dates, devigged closing, skip-home_win-NaN, date order) but ALSO
collects each kept row's game_id 1:1 so the as-of table aligns by game_id.
Default seasons = box-covered ["2024-25","2025-26"] (high AST coverage; honest).

F5: stdlib, numpy, pandas, domains.basketball_nba.adapter (read-only),
    src.loop.{gate,signal}, catalog_common.  PRIVATE: never committed publicly.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from domains.basketball_nba.adapter import (
    NBAAdapter,
    _add_rolling_win10,
    _devig_am,
    _season_to_int,
)
from domains.basketball_nba.ratings import walk_forward_elo
from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue
from scripts.platformkit.catalog_common import derive_bundle

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_features.parquet"

# Box-score coverage is 2024-25 (~complete) + 2025-26 (partial) ONLY.  Restrict the
# base bundle to those seasons so the as-of AST column has high coverage and the
# gate test is meaningful.  (Stated honestly: outside these seasons there is no box.)
_BOX_SEASONS: Tuple[str, ...] = ("2024-25", "2025-26")

# Candidate as-of columns the gate tests.  Each is a pure transform of leak-free
# prior-only team rates; an "oreb_diff" derived column is added when the pg columns
# exist.  Selected dynamically from the parquet schema (see _candidate_columns).
_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "ast_rate_diff_asof",
    "home_ast_rate_asof",
    "home_pace_asof",
    "oreb_diff_asof",  # derived: home_oreb_pg_asof - away_oreb_pg_asof
)
_DERIVED = {
    "oreb_diff_asof": ("home_oreb_pg_asof", "away_oreb_pg_asof"),
}


# --------------------------------------------------------------------------- #
# Base bundle construction (replicates adapter.feature_bundle + collects game_id)
# --------------------------------------------------------------------------- #
def _build_base_bundle_with_ids(
    seasons: Optional[Sequence[str]] = None,
    adapter: Optional[NBAAdapter] = None,
) -> Tuple[FeatureBundle, List[str]]:
    """REPLICATE NBAAdapter.feature_bundle EXACTLY + return per-kept-row game_ids.

    Same 8 base cols, target=home_win, dates, closing=_devig_am(home_ml,away_ml),
    same skip-home_win-NaN, same date order — but also collect the game_id of every
    kept row, aligned 1:1 to the bundle rows.  Returns (bundle, game_ids).
    """
    adapter = adapter or NBAAdapter()
    games_df = adapter._get_games()  # read-only access to the adapter's corpus
    if seasons:
        games_df = games_df[games_df["season"].isin(seasons)]

    games_df = games_df.copy()
    games_df["_season_orig"] = games_df["season"]
    games_df["season"] = games_df["season"].apply(_season_to_int)
    wf = _add_rolling_win10(walk_forward_elo(games_df))
    wf["season"] = wf["_season_orig"]
    wf.drop(columns=["_season_orig"], inplace=True)

    try:
        odds_df = adapter._get_odds()
        has_odds = not odds_df.empty
    except FileNotFoundError:
        has_odds = False
        odds_df = pd.DataFrame()

    if has_odds:
        _o = odds_df[["date", "home_team", "away_team", "home_ml", "away_ml"]].copy()
        _o["date"] = _o["date"].astype(str)
        wf["_ds"] = pd.to_datetime(wf["date"]).dt.date.astype(str)
        wf = wf.merge(_o.rename(columns={"date": "_ds"}),
                      on=["_ds", "home_team", "away_team"], how="left")
        wf.drop(columns=["_ds"], inplace=True)
    else:
        wf["home_ml"] = np.nan
        wf["away_ml"] = np.nan

    rows_base, rows_sig, rows_tgt, rows_dates, rows_lv, game_ids = [], [], [], [], [], []
    for _, row in wf.iterrows():
        tgt = row.get("home_win", np.nan)
        if pd.isna(tgt):
            continue
        lv = _devig_am(row.get("home_ml"), row.get("away_ml"))
        rows_base.append([
            float(row["elo_home"]), float(row["elo_away"]),
            float(row["elo_diff_hfa"]),
            float(row.get("rest_days_home", 5.0)),
            float(row.get("rest_days_away", 5.0)),
            float(bool(row.get("home_b2b", False))),
            float(bool(row.get("away_b2b", False))),
            float(row.get("rolling_win10_home", 0.5)),
        ])
        rows_sig.append(float(row["p_home_elo"]))
        rows_tgt.append(float(tgt))
        rows_dates.append(str(pd.to_datetime(row["date"]).date()))
        rows_lv.append(lv)
        game_ids.append(str(row["game_id"]))

    if not rows_base:
        raise ValueError(
            f"_build_base_bundle_with_ids: no rows for seasons={list(seasons or [])}.")

    la = np.array(rows_lv, dtype=float)
    bundle = FeatureBundle(
        base=np.array(rows_base, dtype=float),
        signal_col=np.array(rows_sig, dtype=float),
        target=np.array(rows_tgt, dtype=float),
        dates=rows_dates,
        lines=None,
        closing=la if not np.all(np.isnan(la)) else None,
    )
    return bundle, game_ids


# --------------------------------------------------------------------------- #
# As-of alignment
# --------------------------------------------------------------------------- #
def _align_asof(asof_df: pd.DataFrame, game_ids: Sequence[str], col: str) -> np.ndarray:
    """Map game_id -> col value; return array aligned to game_ids (NaN where absent).

    Handles a derived 'oreb_diff_asof' column (home_oreb_pg_asof - away_oreb_pg_asof).
    """
    if col in _DERIVED:
        h, a = _DERIVED[col]
        series = pd.to_numeric(asof_df[h], errors="coerce") - pd.to_numeric(
            asof_df[a], errors="coerce")
    else:
        series = pd.to_numeric(asof_df[col], errors="coerce")
    lut: Dict[str, float] = dict(zip(asof_df["game_id"].astype(str), series))
    return np.array([lut.get(str(g), np.nan) for g in game_ids], dtype=float)


def _candidate_columns(asof_df: pd.DataFrame) -> List[str]:
    """Pick the candidate as-of cols that the parquet schema actually supports."""
    cols = set(asof_df.columns)
    out: List[str] = []
    for c in _PREFERRED_CANDIDATES:
        if c in _DERIVED:
            if all(src in cols for src in _DERIVED[c]):
                out.append(c)
        elif c in cols:
            out.append(c)
    return out


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
            statement=f"As-of team rate '{self.name}' added to the Elo base matrix.",
            rationale=("Prior-only box-derived team rate; very likely REDUNDANT with "
                       "Elo (team quality already priced). REJECT/DEFER expected; "
                       "NO edge claimed."),
            source="seed", expected_verdict="REJECT", priority="P2")


# --------------------------------------------------------------------------- #
# The honest gate test
# --------------------------------------------------------------------------- #
def run_gate_test(
    seasons: Optional[Sequence[str]] = None,
    asof_path: Optional[Path] = None,
) -> List[dict]:
    """Run each candidate as-of column through the REAL gate; return verdict rows.

    Builds the base bundle + aligned game_ids ONCE, then for each candidate column
    derives a bundle (Elo base + as-of signal_col) and calls evaluate(..., n_splits=3).
    SHIP verdicts are logged as PROBABLE ARTIFACT; no edge is claimed.
    """
    seasons = list(seasons) if seasons is not None else list(_BOX_SEASONS)
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_features.parquet not found at {apath}. Run "
            "domains.basketball_nba.asof_features first.")
    asof_df = pd.read_parquet(apath)

    bb, game_ids = _build_base_bundle_with_ids(seasons=seasons)
    n = bb.base.shape[0]
    candidates = _candidate_columns(asof_df)

    rows: List[dict] = []
    for col in candidates:
        sc = _align_asof(asof_df, game_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"nba_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "NBA AS-OF SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
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
        return "NBA AST as-of: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return ("NBA AST as-of: SHIP flagged for " + ", ".join(ships) +
                " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return ("NBA AST as-of: " + "/".join(verds) +
            " -> NO edge; markets efficient / redundant with Elo; "
            "calibration deepened only.")


def main() -> int:
    """CLI: run the as-of AST gate test on the materialized parquets; print honestly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test()
    hdr = (f"{'Candidate':<28} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} "
           f"{'abl':>5} {'null':>5} {'calib':>6} {'p':>8}")
    print("\nNBA as-of AST gate test (REAL gate; seasons=" + ",".join(_BOX_SEASONS) + ")")
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

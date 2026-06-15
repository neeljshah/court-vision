"""scripts.platformkit.proof_basketball_nba.gate_test_box_extra — HONEST extra-box as-of gate.

Tests leak-free prior-only trailing team rates for dreb_diff, fg3m_diff, stl_diff,
blk_diff (home-minus-away per-game means) through the REAL honest gate.

Mirrors gate_test_asof.py exactly: builds the NBAAdapter feature_bundle with 8 base
cols (Elo base), target=home_win, devigged closing odds, carries game_id 1:1, aligns
each as-of diff column as signal_col via derive_bundle, and runs src.loop.gate.evaluate
over seasons 2024-25 + 2025-26 (same box-covered seasons, n≈2386).

DISCIPLINE (binding): expected verdict REJECT for all four signals (dreb/fg3m/stl/blk
team differentials; box-derived rates very likely REDUNDANT with Elo; market efficient).
SHIP flagged = PROBABLE ARTIFACT; NO edge is ever claimed here.  A REJECT is a success.

F5: stdlib, numpy, pandas, domains.basketball_nba.adapter (read-only), src.loop.gate,
    src.loop.signal, catalog_common.  PRIVATE: never committed publicly.
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
_EXTRA_PARQUET = (
    _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_box_extra.parquet"
)

# Box-score coverage is 2024-25 (~complete) + 2025-26 (partial) ONLY.
_BOX_SEASONS: Tuple[str, ...] = ("2024-25", "2025-26")

# Candidate diff columns tested through the gate.
_CANDIDATES: Tuple[str, ...] = (
    "dreb_diff_asof",
    "fg3m_diff_asof",
    "stl_diff_asof",
    "blk_diff_asof",
)


# --------------------------------------------------------------------------- #
# Base bundle construction (replicates adapter.feature_bundle + game_id list)
# --------------------------------------------------------------------------- #
def _build_base_bundle_with_ids(
    seasons: Optional[Sequence[str]] = None,
    adapter: Optional[NBAAdapter] = None,
) -> Tuple[FeatureBundle, List[str]]:
    """Replicate NBAAdapter.feature_bundle + return aligned game_ids per row.

    8 base cols, target=home_win, dates, devigged closing odds.  Also returns
    the game_id of every kept row, 1:1 aligned to bundle rows, so as-of columns
    can be aligned by game_id without risk of ordering mismatch.
    """
    adapter = adapter or NBAAdapter()
    games_df = adapter._get_games()
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
        wf = wf.merge(
            _o.rename(columns={"date": "_ds"}),
            on=["_ds", "home_team", "away_team"], how="left",
        )
        wf.drop(columns=["_ds"], inplace=True)
    else:
        wf["home_ml"] = np.nan
        wf["away_ml"] = np.nan

    rows_base, rows_sig, rows_tgt = [], [], []
    rows_dates, rows_lv, game_ids = [], [], []
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
def _align_asof(extra_df: pd.DataFrame, game_ids: Sequence[str], col: str) -> np.ndarray:
    """Map game_id -> col value; NaN where absent."""
    series = pd.to_numeric(extra_df[col], errors="coerce")
    lut: Dict[str, float] = dict(zip(extra_df["game_id"].astype(str), series))
    return np.array([lut.get(str(g), np.nan) for g in game_ids], dtype=float)


# --------------------------------------------------------------------------- #
# Signal carrier
# --------------------------------------------------------------------------- #
class _ArraySignal(Signal):
    """Carrier Signal: one per candidate; gate reads injected _gate_matrix."""
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas: List[str] = []
    emits: List[str] = []

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name

    def build(self, ctx: AsOfContext) -> SignalValue:  # matrix injected; not called
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name, target="winprob", scope="pregame",
            statement=f"As-of extra-box team diff '{self.name}' added to the Elo base.",
            rationale=(
                "Prior-only trailing team rate (dreb/fg3m/stl/blk); very likely "
                "REDUNDANT with Elo (team quality already priced). REJECT expected; "
                "NO edge claimed."
            ),
            source="seed", expected_verdict="REJECT", priority="P2",
        )


# --------------------------------------------------------------------------- #
# The honest gate test
# --------------------------------------------------------------------------- #
def run_gate_test(
    seasons: Optional[Sequence[str]] = None,
    extra_path: Optional[Path] = None,
) -> List[dict]:
    """Run each extra-box diff column through the REAL gate; return verdict rows."""
    seasons = list(seasons) if seasons is not None else list(_BOX_SEASONS)
    apath = Path(extra_path) if extra_path is not None else _EXTRA_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_box_extra.parquet not found at {apath}. "
            "Run domains.basketball_nba.asof_box_extra first.")
    extra_df = pd.read_parquet(apath)

    bb, game_ids = _build_base_bundle_with_ids(seasons=seasons)
    n = bb.base.shape[0]

    rows: List[dict] = []
    for col in _CANDIDATES:
        if col not in extra_df.columns:
            logger.warning("Column %s absent from parquet; skipping.", col)
            continue
        sc = _align_asof(extra_df, game_ids, col)
        coverage = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig = _ArraySignal(name=f"nba_{col}")
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]
        r = evaluate(sig, device="cpu", n_splits=3)
        verdict = r.verdict.value
        if verdict == "SHIP":
            logger.warning(
                "NBA EXTRA-BOX SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
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
    if not rows:
        return "NBA extra-box as-of: NO evaluable columns -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return ("NBA extra-box as-of: SHIP flagged for " + ", ".join(ships) +
                " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return ("NBA extra-box as-of: " + "/".join(verds) +
            " -> NO edge; markets efficient / redundant with Elo; "
            "calibration context only.")


def main() -> int:
    """CLI: build asof_box_extra (if absent) then run the honest gate; print results."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Auto-build the parquet if it doesn't exist yet.
    if not _EXTRA_PARQUET.exists():
        from domains.basketball_nba.asof_box_extra import build_asof_box_extra
        logger.info("asof_box_extra.parquet not found — building now...")
        build_asof_box_extra()
        logger.info("Built %s", _EXTRA_PARQUET)

    rows = run_gate_test()
    hdr = (f"{'Candidate':<28} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} "
           f"{'abl':>5} {'null':>5} {'calib':>6} {'p':>8}")
    print("\nNBA extra-box as-of gate test (REAL gate; seasons=" +
          ",".join(_BOX_SEASONS) + ")")
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
    "_build_base_bundle_with_ids", "_align_asof", "_ArraySignal",
    "run_gate_test", "_summary_line", "main",
]

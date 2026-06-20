"""scripts.platformkit.proof_basketball_nba.gate_test_quarter_shape -- HONEST as-of gate test.

Threads the leak-free as-of QUARTER-SHAPE diffs (domains.basketball_nba.asof_quarter_shape)
through the REAL honest gate (src.loop.gate.evaluate) on top of the Elo base.

REUSES the proven base-bundle construction from gate_test_asof (_build_base_bundle_with_ids,
_align_asof, _ArraySignal) so the Elo/rest/b2b/rolling base stays byte-identical to
NBAAdapter; only the candidate columns + parquet differ.

DISCIPLINE (binding): expected verdict REJECT or DEFER -- team scoring-distribution
tendencies are very likely REDUNDANT with the Elo base (team quality already priced). A
SHIP is a PROBABLE ARTIFACT; NO edge is ever claimed. The real payoff of quarter-shape is
as an IN-GAME conditioning prior (offered to Lane A's M6 repricer), not a pregame edge.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.loop.gate import evaluate
from scripts.platformkit.catalog_common import derive_bundle
from scripts.platformkit.reject_ledger import record_proof_verdicts
from scripts.platformkit.proof_basketball_nba.gate_test_asof import (
    _ArraySignal,
    _align_asof,
    _build_base_bundle_with_ids,
)

logger = logging.getLogger(__name__)

# linescores.parquet covers ONLY 2025-26, so gate on that season for honest high coverage
# (the 2-season box default would leave ~half the base bundle as NaN quarter-shape).
_LINESCORE_SEASONS = ("2025-26",)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_ASOF_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "asof_quarter_shape.parquet"
_GAMES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"

# The quarter-shape builder is ESPN-keyed (event_id); the base bundle is NBA-Stats-keyed
# (game_id). Bridge them with a derived (date, teams) crosswalk -- the 6 abbr differences
# were derived empirically from the corpora (ESPN -> NBA).
_ESPN_TO_NBA_ABBR = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS", "UTAH": "UTA", "WSH": "WAS"}

_PREFERRED_CANDIDATES: Tuple[str, ...] = (
    "diff_q1_margin_asof",
    "diff_second_half_margin_asof",
    "diff_q4_margin_asof",
    "diff_quarter_volatility_asof",
)


def _resolve_game_ids(asof_df: pd.DataFrame) -> pd.DataFrame:
    """Attach NBA game_id to the ESPN-keyed rows via a (date, mapped-teams) crosswalk.

    Unresolved rows get a null game_id (they simply align to NaN in the gate -- honest).
    """
    if "game_id" in asof_df.columns:
        return asof_df
    g = pd.read_parquet(_GAMES_PARQUET)[["game_id", "date", "home_team", "away_team"]].copy()
    g = g.rename(columns={"home_team": "_h", "away_team": "_a"})
    g["_d"] = pd.to_datetime(g["date"]).dt.date.astype(str)
    df = asof_df.copy()
    df["_d"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["_h"] = df["home_abbr"].astype(str).map(lambda a: _ESPN_TO_NBA_ABBR.get(a, a))
    df["_a"] = df["away_abbr"].astype(str).map(lambda a: _ESPN_TO_NBA_ABBR.get(a, a))
    merged = df.merge(g[["_d", "_h", "_a", "game_id"]], on=["_d", "_h", "_a"], how="left")
    return merged.drop(columns=["_d", "_h", "_a"])


def _candidate_columns(asof_df: pd.DataFrame) -> List[str]:
    cols = set(asof_df.columns)
    return [c for c in _PREFERRED_CANDIDATES if c in cols]


def run_gate_test(
    seasons: Optional[Sequence[str]] = None,
    asof_path: Optional[Path] = None,
    record: bool = False,
) -> List[dict]:
    """Run each candidate quarter-shape diff through the REAL gate; return verdict rows.

    When ``record`` is True, the honest verdicts are appended to the reject ledger
    (the signal graveyard) via record_proof_verdicts -- a REJECT is market-efficiency
    evidence, recorded so the discovery loop never re-tests a known-dead signal.
    """
    _seasons = list(seasons) if seasons is not None else list(_LINESCORE_SEASONS)
    apath = Path(asof_path) if asof_path is not None else _ASOF_PARQUET
    if not apath.exists():
        raise FileNotFoundError(
            f"asof_quarter_shape.parquet not found at {apath}. Run "
            "domains.basketball_nba.asof_quarter_shape first.")
    asof_df = _resolve_game_ids(pd.read_parquet(apath))

    bb, game_ids = _build_base_bundle_with_ids(seasons=_seasons)
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
                "NBA QUARTER-SHAPE SHIP FLAG '%s': PROBABLE ARTIFACT. NO edge claimed.", col)
        rows.append({
            "name": sig.name, "column": col, "verdict": verdict,
            "coverage": round(coverage, 4), "n": n,
            "wf_all_improve": r.wf_all_improve, "ablation_pass": r.ablation_pass,
            "null_pass": r.null_pass, "calibration_ok": r.calibration_ok,
            "clv": r.clv, "p_value": r.p_value, "reason": r.reason,
        })
    if record and rows:
        record_proof_verdicts("nba", rows, corpus="linescores_quarter_shape_2025-26")
    return rows


def _summary_line(rows: List[dict]) -> str:
    if not rows:
        return "NBA as-of quarter-shape: NO candidate columns evaluable -> DEFER; no edge."
    ships = [r["name"] for r in rows if r["verdict"] == "SHIP"]
    verds = sorted({r["verdict"] for r in rows})
    if ships:
        return ("NBA as-of quarter-shape: SHIP flagged for " + ", ".join(ships) +
                " -> PROBABLE ARTIFACT, NO edge claimed (artifact-hunt required).")
    return ("NBA as-of quarter-shape: " + "/".join(verds) +
            " -> NO edge pregame; redundant with Elo. Value is the in-game prior only.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = run_gate_test(record=True)
    hdr = f"{'Candidate':<34} {'Verdict':<8} {'Cover':>6} {'wf_all':>7} {'abl':>5} {'null':>5} {'calib':>6} {'p':>8}"
    print("\nNBA as-of QUARTER-SHAPE gate test (REAL gate; seasons="
          + ",".join(_LINESCORE_SEASONS) + ")")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        p = r["p_value"]
        print(f"{r['name']:<34} {r['verdict']:<8} {r['coverage']:>6.3f} "
              f"{str(r['wf_all_improve']):>7} {str(r['ablation_pass']):>5} "
              f"{str(r['null_pass']):>5} {str(r['calibration_ok']):>6} "
              f"{('%.4f' % p) if p is not None else '   -':>8}")
    print("-" * len(hdr))
    print(_summary_line(rows))
    print("(REJECT/DEFER = honest success; no edge is ever claimed here.)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_gate_test", "_summary_line", "_candidate_columns", "main"]

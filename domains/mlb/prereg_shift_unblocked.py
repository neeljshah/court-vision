"""domains.mlb.prereg_shift_unblocked -- H1 UNBLOCKED: "pull-tendency x infield
alignment" on the hit-coordinate corpus (data/cache/statcast/savant_hitcoords__
{2023,2024}.parquet, 720984/711455 rows, 46 cols -- same events as savant_full,
now carrying hc_x/hc_y/hit_location/launch_speed_angle). This UNBLOCKS the
BLOCKED-on-premise H1 row prereg_shift_framing.run_h1 recorded (method=
savant_shift_framing_v1, ledger note: "no hc_x/hc_y/hit_location column") --
SAME preregistered hypothesis, SAME conjunctive bar (test on 2023, replicate
on 2024, same-sign AND p<alpha both), unchanged. Zero reimplementation of the
pull-share machinery: imports check_hit_coords, build_pull_share_asof, ALPHA,
SPORT, blocked_row/append_ledger/LEDGER_PATH straight from prereg_shift_framing,
and fit_interaction from stats_common (the shared OLS/Logit interaction fitter
every other prereg_* module in this family uses).

SPRAY ANGLE (declared BEFORE running, standard savant convention -- verified
against this corpus's own R/L mean split: R batters mean spray -12.3deg, L
batters mean spray +18.6deg on the 2023 ground-ball subset, both already on
the expected pull side with NO threshold applied yet):
    spray_angle_deg = atan((hc_x - 125.42) / (198.27 - hc_y)) * 180 / pi
    pulled = spray_angle_deg < -15deg   for stand == 'R' (pull = 3B/LF side)
    pulled = spray_angle_deg >  15deg   for stand == 'L' (pull = 1B/RF side)
(125.42, 198.27) is the fixed savant hc_x/hc_y home-plate origin used by every
public spray-angle recipe -- not re-derived here. Batted balls only (hc_x/hc_y
both non-null).

POPULATION: the ENTIRE hypothesis (see prereg_shift_framing's H1 declaration:
"a batter's AS-OF pull share ON GROUNDERS") is scoped to ground balls
(bb_type=='ground_ball') for BOTH legs -- the pull-share feature (prior
grounders only) and the gb_hit outcome (this grounder). Not two different
populations.

OUTCOME LEG: gb_hit = events in {single, double, triple, home_run} (the plain
non-error hit set; field_error scored as an out, matching standard
batting-average convention). is_shifted = if_fielding_alignment != 'Standard';
rows with alignment NaN (~0.7% of the corpus, unscoreable) are dropped, not
imputed.

MODEL: gb_hit ~ pull_share_asof * is_shifted + C(stand) (logit), per the
original H1 declaration ("main effects + stand control"). fit_interaction
(stats_common, unchanged) pulls the pull_share_asof:is_shifted coefficient.

PULL SHARE: build_pull_share_asof (imported, unchanged) on an is_pull column
derived from the spray-angle classification above -- strictly-prior
game_dates, expanding, per-batter, EXCLUSIVE cumsum (never nansum/rolling-mean
-- see prereg_shift_framing's LANDMINE note). This is that function's FIRST
real invocation; it was built + leak-guard-tested but never called until now.

Descriptive/measurement only. edge_claimed hard-wired False on every row.
NETWORK: zero. CLI: python -m domains.mlb.prereg_shift_unblocked
Per-file test: python -m pytest domains/mlb/test_prereg_shift_unblocked.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from domains.mlb.prereg.stats_common import fit_interaction, verdict as sc_verdict
from domains.mlb.prereg_shift_framing import (
    ALPHA,
    LEDGER_PATH,
    SPORT,
    append_ledger,
    build_pull_share_asof,
    check_hit_coords,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_HITCOORD_FP = {"2023": _STATCAST_DIR / "savant_hitcoords__2023.parquet",
                "2024": _STATCAST_DIR / "savant_hitcoords__2024.parquet"}

NAME = "pull-tendency x infield alignment"
METHOD = "savant_shift_unblocked_v1"
_HOME_X, _HOME_Y = 125.42, 198.27  # savant hc_x/hc_y home-plate origin, fixed constant
_PULL_THRESHOLD_DEG = 15.0
_HIT_EVENTS = ("single", "double", "triple", "home_run")


def load_hitcoords(season: str) -> pd.DataFrame:
    return pd.read_parquet(_HITCOORD_FP[season])


def spray_angle_deg(hc_x: pd.Series, hc_y: pd.Series) -> pd.Series:
    """Declared formula (module docstring): atan((hc_x-125.42)/(198.27-hc_y)), degrees."""
    return np.degrees(np.arctan((hc_x - _HOME_X) / (_HOME_Y - hc_y)))


def classify_pulled(spray_deg: pd.Series, stand: pd.Series) -> pd.Series:
    """RHB pulled = spray<-15deg (3B/LF side); LHB pulled = spray>15deg (1B/RF side)."""
    is_rhb = (stand == "R").to_numpy()
    pulled = np.where(is_rhb, spray_deg < -_PULL_THRESHOLD_DEG, spray_deg > _PULL_THRESHOLD_DEG)
    return pd.Series(pulled, index=spray_deg.index)


def build_gb_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Ground balls with hc_x/hc_y/stand/alignment all present -- the single
    population for both the AS-OF pull-share feature (prior grounders only)
    and the gb_hit outcome. Returns columns incl. gb_hit, pull_share_asof,
    is_shifted, stand (rows whose first game_date has no prior data are
    dropped by the merge's dropna -- the leak guard)."""
    gb = df[df["bb_type"] == "ground_ball"].dropna(
        subset=["hc_x", "hc_y", "stand", "if_fielding_alignment"]).copy()
    if gb.empty:
        return gb
    gb["spray_angle_deg"] = spray_angle_deg(gb["hc_x"], gb["hc_y"])
    gb["is_pull"] = classify_pulled(gb["spray_angle_deg"], gb["stand"]).astype(int)
    gb["gb_hit"] = gb["events"].isin(_HIT_EVENTS).astype(int)
    gb["is_shifted"] = (gb["if_fielding_alignment"] != "Standard").astype(int)
    share = build_pull_share_asof(gb, pulled_col="is_pull")
    gb = gb.merge(share, on=["batter", "game_date"], how="left")
    return gb.dropna(subset=["pull_share_asof"])


def _row(name: str, season: str, method: str, n: int, effect: Optional[float], p: Optional[float],
         verdict_str: str, note: str, term: Optional[str] = None) -> Dict[str, Any]:
    return {"hypothesis": name, "sport": SPORT, "atomic_unit": "batted ball", "method": method,
            "n": n, "effect": effect, "p": p, "alpha_fwer": ALPHA, "term": term,
            "verdict": verdict_str, "note": f"season={season}; {note}", "edge_claimed": False}


def run_h1_test(df23: pd.DataFrame) -> Dict[str, Any]:
    method = f"{METHOD}_test"
    if not check_hit_coords(df23):
        return _row(NAME, "2023", method, 0, None, None, "BLOCKED",
                    "hit-coordinate columns absent -- corpus regressed vs the verified schema")
    frame = build_gb_frame(df23)
    if len(frame) == 0:
        return _row(NAME, "2023", method, 0, None, None, "NOT_TESTABLE",
                    "0 ground balls with hc_x/hc_y + alignment + a scoreable prior-date pull share")
    fit = fit_interaction(frame, "gb_hit ~ pull_share_asof * is_shifted + C(stand)", kind="logit")
    v = sc_verdict(fit["p"], ALPHA)
    note = (f"UNBLOCKS prereg_shift_framing.run_h1's BLOCKED row (method=savant_shift_framing_v1, "
            f"lacked hc_x/hc_y) -- {frame['batter'].nunique()} batters, "
            f"{int(frame['is_shifted'].sum())} shifted-alignment GB vs "
            f"{int((1 - frame['is_shifted']).sum())} standard; term={fit['term']}")
    if v == "SURVIVES_PREREG":
        note += " -- PROVISIONAL, needs independent replication before belief"
    return _row(NAME, "2023", method, fit["n"], fit["effect"], fit["p"], v, note, term=fit["term"])


def run_h1_replicate(df24: pd.DataFrame, test_row: Dict[str, Any]) -> Dict[str, Any]:
    method = f"{METHOD}_replicate"
    if not check_hit_coords(df24):
        return _row(NAME, "2024", method, 0, None, None, "BLOCKED",
                    "hit-coordinate columns absent -- corpus regressed vs the verified schema")
    frame = build_gb_frame(df24)
    if len(frame) == 0:
        return _row(NAME, "2024", method, 0, None, None, "NOT_TESTABLE",
                    "0 ground balls with hc_x/hc_y + alignment + a scoreable prior-date pull share")
    fit = fit_interaction(frame, "gb_hit ~ pull_share_asof * is_shifted + C(stand)", kind="logit")
    if test_row["verdict"] != "SURVIVES_PREREG":
        v = "FAILED_REPLICATION"
        note = "2023 test row did not SURVIVE_PREREG -- replication not attempted on the merits"
    else:
        same_sign = (fit["effect"] > 0) == (test_row["effect"] > 0)
        v = "REPLICATED" if (same_sign and fit["p"] < ALPHA) else "FAILED_REPLICATION"
        note = (f"same-sign-and-p<alpha both required for REPLICATED (mirrors "
                f"third_season_2023_24.py's combination rule); same_sign={same_sign}")
    return _row(NAME, "2024", method, fit["n"], fit["effect"], fit["p"], v, note, term=fit["term"])


def run() -> list[Dict[str, Any]]:
    df23 = load_hitcoords("2023")
    df24 = load_hitcoords("2024")
    row_test = run_h1_test(df23)
    row_replicate = run_h1_replicate(df24, row_test)
    rows = [row_test, row_replicate]
    append_ledger(rows)
    return rows


def main() -> int:
    rows = run()
    print(f"H1 unblocked alpha={ALPHA:.4f} (method={METHOD})")
    for r in rows:
        print(f"  [{r['verdict']:>18}] {r['hypothesis']} ({r['method']}): "
              f"n={r['n']} effect={r['effect']} p={r['p']}")
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

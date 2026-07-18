"""domains.mlb.prereg_shift_framing -- 2 preregistered coach-mechanism hypotheses
(K=2, plain Bonferroni alpha=0.05/2=0.025, declared before running) on the
savant_full pitch-level corpus (data/cache/statcast/savant_full__{2023,2024}
.parquet, 720984/711455 rows, 42 cols, VERIFIED live this wave):

  H1 pull-tendency x infield alignment: a batter's AS-OF pull share on grounders
     INTERACTS with if_fielding_alignment (shifted vs standard) on ground-ball
     hit probability. PREMISE CHECK: BOTH seasons (and the older statcast_fuller
     corpus) carry NO hc_x/hc_y/hit_location/spray-angle column -- there is no way
     to determine which field a grounder was hit toward. BLOCKED-on-premise, no
     proxy invented (the "hit coords" the brief asked to VERIFY do not exist on
     this corpus). The leak-free AS-OF expanding-share machinery a real
     pull_share_asof feature would need is still built + leak-guard-tested below
     (build_pull_share_asof), exposed for a future corpus that adds hit
     coordinates -- it is NEVER invoked on faked/derived pull data here.

  H2 catcher framing x count leverage: PREMISE CHECK: fielder_2 (catcher id, 100%
     populated both seasons) AND `description` (real called_strike/ball/
     swinging_strike/foul sub-codes) are BOTH present -- premise HOLDS. This
     UNBLOCKS the framing hypothesis mlb_hypotheses.py / mlb_savant_2024.py both
     left BLOCKED for lack of an isolatable called-strike code (that corpus only
     had `type` in {S,B,X}, bundling called+swinging+foul into 'S'). On taken
     pitches (description in {called_strike, ball}) within a borderline "edge
     shell" (see classify_borderline), tested as TWO nested likelihood-ratio
     tests -- a frequentist stand-in for a catcher random-effect/variance test
     (no GLMM built; ponytail -- statsmodels logit + chi2 LR test, nothing new
     invented beyond what stats_common's fit_interaction already does for a
     2-level interaction, just extended to an N-level factor via nesting):
       (a) does called-strike rate vary BY CATCHER beyond a single binomial rate
           -- LR test: + C(catcher) over a pitcher_ahead-only null.
       (b) does that catcher effect INTERACT with pitcher-ahead count leverage
           -- LR test: + C(catcher):pitcher_ahead over the (a) model.
     H2 SURVIVES iff BOTH p<alpha (conjunctive -- mirrors third_season_2023_24's
     same-sign-AND-p<alpha combination rule; there is no single signed
     coefficient for an N-level LR stat, so this is the honest adaptation).
     TEST on 2023, REPLICATE on 2024 (both-p<alpha reapplied; "same-sign" from
     the brief does not literally apply to an LR chi2 stat -- deviation noted in
     the replicate row's own note, not silently dropped).

BORDERLINE SHELL (classify_borderline): a pitch is "borderline" iff its scalar
signed distance to the nearest strike-zone-rectangle edge is within SHELL_FT
(0.25 ft, ~3in, declared before running) of that edge -- plate_x vs
+-PLATE_HALF_WIDTH_FT and plate_z vs sz_top/sz_bot. Same geometric style as
catcher_framing_index.py's zone cross-check (max-of-3-axis-violations), not
reinvented, adapted from a single in/out split to a narrow edge BAND. NOTE: near
a true zone corner this max-of-3 distance is not the exact Euclidean distance to
the rectangle -- adequate for a narrow edge band, not claimed exact geometry.

CATCHER FLOOR: >=500 borderline takes/catcher (verified: 72/102 catchers clear
it in the 2023 borderline subset) -- the SAME 500 floor catcher_framing_index.py
already uses, reused not reinvented.

LANDMINE (flagged in the brief): np.nansum over an all-NaN reindexed slice is
0.0, not NaN. build_pull_share_asof avoids it entirely -- it uses an EXCLUSIVE
integer cumsum (prior-day pulled-count / prior-day total-count), never nansum or
a rolling-nanmean, so a batter's first game_date is a genuine 0/0 -> NaN, never a
silent 0.0 (see test_prereg_shift_framing.py's leak-guard test).

Descriptive/measurement only. edge_claimed hard-wired False on every row.
NETWORK: zero. CLI: python -m domains.mlb.prereg_shift_framing
Per-file test: python -m pytest domains/mlb/test_prereg_shift_framing.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import chi2

from domains.mlb.prereg.stats_common import LEDGER_PATH, append_ledger, blocked_row

REPO_ROOT = Path(__file__).resolve().parents[2]
_STATCAST_DIR = REPO_ROOT / "data" / "cache" / "statcast"
_SAVANT_FP = {"2023": _STATCAST_DIR / "savant_full__2023.parquet",
              "2024": _STATCAST_DIR / "savant_full__2024.parquet",
              "2025": _STATCAST_DIR / "savant_full__2025.parquet"}

SPORT = "mlb"
ALPHA = 0.05 / 2  # K=2, plain Bonferroni -- declared in the brief before running
CATCHER_FLOOR = 500  # min borderline takes/catcher -- same floor catcher_framing_index.py uses
PLATE_HALF_WIDTH_FT = 0.83  # same value as catcher_framing_index.py's _PLATE_HALF_WIDTH_FT
SHELL_FT = 0.25  # "edge shell" half-width (~3in) -- declared before running
_HIT_COORD_COLS = ("hc_x", "hc_y", "hit_location")
_SHIFTED_ALIGNMENTS = ("Infield shade", "Strategic")  # this corpus's non-Standard labels
# (no literal "Infield shift" string on savant_full -- unlike statcast_fuller's 2022 slice)


def load_savant(season: str) -> pd.DataFrame:
    return pd.read_parquet(_SAVANT_FP[season])


# --------------------------------------------------------------------------- #
# Premise checks
# --------------------------------------------------------------------------- #
def check_hit_coords(df: pd.DataFrame) -> bool:
    """H1 premise: a pull-direction source column (hc_x/hc_y/hit_location)."""
    return any(c in df.columns for c in _HIT_COORD_COLS)


def check_catcher_col(df: pd.DataFrame) -> bool:
    """H2 premise: fielder_2 (catcher id) present and non-null somewhere."""
    return "fielder_2" in df.columns and bool(df["fielder_2"].notna().any())


# --------------------------------------------------------------------------- #
# H1 machinery -- built + leak-guard-tested, NOT invoked on real data (BLOCKED).
# --------------------------------------------------------------------------- #
def build_pull_share_asof(df: pd.DataFrame, pulled_col: str = "is_pull",
                           batter_col: str = "batter", date_col: str = "game_date") -> pd.DataFrame:
    """Leak-free AS-OF expanding pull share: per (batter, game_date), the share of
    STRICTLY PRIOR game_dates' `pulled_col` rows (this date's own rows excluded).
    EXCLUSIVE cumsum on integer counts (never nansum/rolling-mean -- see module
    LANDMINE note): a batter's first game_date is a genuine 0/0 -> NaN."""
    daily = (df.groupby([batter_col, date_col])[pulled_col]
             .agg(n_pulled="sum", n_total="count").reset_index()
             .sort_values([batter_col, date_col]))
    grp = daily.groupby(batter_col)
    cum_pulled = grp["n_pulled"].cumsum()
    cum_total = grp["n_total"].cumsum()
    daily["pull_share_asof"] = (cum_pulled - daily["n_pulled"]) / (cum_total - daily["n_total"])
    return daily[[batter_col, date_col, "pull_share_asof"]]


def run_h1(df23: pd.DataFrame) -> Dict[str, Any]:
    name = "pull-tendency x infield alignment"
    if check_hit_coords(df23):
        raise AssertionError("check_hit_coords()==True but run_h1 hard-codes BLOCKED -- "
                              "corpus changed, this module needs a real build, not just a premise recheck")
    gb = df23[(df23["type"] == "X") & (df23["bb_type"] == "ground_ball")]
    is_shifted = gb["if_fielding_alignment"].isin(_SHIFTED_ALIGNMENTS)
    reason = (
        f"no hc_x/hc_y/hit_location (or any spray-angle) column on savant_full__2023 OR "
        f"__2024 (verified live, both seasons, 42 cols each, same schema) -- pull direction "
        f"on a grounder is not derivable; doc names no proxy, not inventing one. NOTE the "
        f"alignment split itself is NOT thin post-ban: shifted GB n={int(is_shifted.sum())} vs "
        f"standard GB n={int((~is_shifted).sum())} on 2023 alone -- 2023/2024 categories are "
        f"Standard/Infield shade/Strategic/None (no literal 'Infield shift' label here, unlike "
        f"the older statcast_fuller corpus). build_pull_share_asof exists (leak-guard tested) "
        f"for a future corpus that adds hit coordinates; not invoked here."
    )
    return blocked_row(name, SPORT, "batted ball", reason, method="savant_shift_framing_v1")


# --------------------------------------------------------------------------- #
# H2 machinery
# --------------------------------------------------------------------------- #
def classify_borderline(df: pd.DataFrame, shell_ft: float = SHELL_FT) -> pd.Series:
    """See module docstring BORDERLINE SHELL. Requires plate_x/plate_z/sz_top/
    sz_bot all non-null (caller filters first)."""
    dx = df["plate_x"].abs() - PLATE_HALF_WIDTH_FT
    dz_top = df["plate_z"] - df["sz_top"]
    dz_bot = df["sz_bot"] - df["plate_z"]
    edge_dist = np.maximum.reduce([dx.to_numpy(), dz_top.to_numpy(), dz_bot.to_numpy()])
    return pd.Series(np.abs(edge_dist) <= shell_ft, index=df.index)


def build_taken_pitches(df: pd.DataFrame) -> pd.DataFrame:
    """Taken pitches (description in {called_strike, ball}) with geometry +
    catcher id present. Keeps ALL source columns (game_date etc) for downstream
    claims use -- narrowing happens in build_borderline_catcher_frame."""
    taken = df[df["description"].isin(["called_strike", "ball"])].copy()
    taken = taken.dropna(subset=["plate_x", "plate_z", "sz_top", "sz_bot", "fielder_2"])
    taken["is_strike"] = (taken["description"] == "called_strike").astype(int)
    taken["pitcher_ahead"] = (taken["strikes"] > taken["balls"]).astype(int)
    return taken


def build_borderline_catcher_frame(df: pd.DataFrame, floor: Optional[int] = None) -> pd.DataFrame:
    """Borderline (classify_borderline) taken pitches, restricted to catchers
    clearing `floor` borderline takes -- the H2 statistical-test population.
    floor=None reads CATCHER_FLOOR live at call time (NOT a baked-in default --
    a `floor: int = CATCHER_FLOOR` default would freeze the value at def-time and
    break test monkeypatching of the module constant)."""
    floor = CATCHER_FLOOR if floor is None else floor
    taken = build_taken_pitches(df)
    border = taken[classify_borderline(taken)].copy()
    counts = border.groupby("fielder_2").size()
    qualifiers = counts[counts >= floor].index
    border = border[border["fielder_2"].isin(qualifiers)].copy()
    border["catcher"] = border["fielder_2"].astype(int).astype(str)  # patsy-friendly factor label
    return border[["is_strike", "pitcher_ahead", "catcher"]]


def _lr_test(df: pd.DataFrame, reduced: str, full: str) -> Dict[str, Any]:
    """Nested-model likelihood-ratio test (`full` must add terms on top of
    `reduced`'s formula). Returns the chi2 stat/df/p for the ADDED terms."""
    m0 = smf.logit(reduced, data=df).fit(disp=0)
    m1 = smf.logit(full, data=df).fit(disp=0)
    stat = 2.0 * (m1.llf - m0.llf)
    df_diff = int(round(m1.df_model - m0.df_model))
    p = float(chi2.sf(stat, df_diff)) if df_diff > 0 else float("nan")
    return {"stat": float(stat), "df": df_diff, "p": p, "n": int(m1.nobs)}


def _fit_h2(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """None -> caller reports NOT_TESTABLE (n=0 or <2 qualifying catchers)."""
    frame = build_borderline_catcher_frame(df)
    n_catchers = frame["catcher"].nunique()
    if len(frame) == 0 or n_catchers < 2:
        return None
    variance = _lr_test(frame, "is_strike ~ pitcher_ahead", "is_strike ~ pitcher_ahead + C(catcher)")
    interaction = _lr_test(frame, "is_strike ~ pitcher_ahead + C(catcher)", "is_strike ~ pitcher_ahead * C(catcher)")
    return {"variance": variance, "interaction": interaction, "n_catchers": n_catchers, "n": len(frame)}


def _h2_note(fit: Optional[Dict[str, Any]]) -> tuple[bool, str]:
    if fit is None:
        return False, f"0 or <2 catchers clearing the {CATCHER_FLOOR}-borderline-take floor -- no scoreable test"
    v, i = fit["variance"], fit["interaction"]
    survives = v["p"] < ALPHA and i["p"] < ALPHA
    note = (f"catcher-variance LR chi2={v['stat']:.2f} df={v['df']} p={v['p']:.3g}; "
            f"interaction LR chi2={i['stat']:.2f} df={i['df']} p={i['p']:.3g}; "
            f"n_qualifying_catchers={fit['n_catchers']} (>={CATCHER_FLOOR} borderline takes/catcher); "
            f"H2 verdict requires BOTH p<alpha (conjunctive -- no single signed coefficient for an N-level LR stat)")
    return survives, note


def _row(name: str, season: str, method: str, n: int, effect: Optional[float], p: Optional[float],
         verdict: str, note: str, term: Optional[str] = None) -> Dict[str, Any]:
    return {"hypothesis": name, "sport": SPORT, "atomic_unit": "pitch", "method": method,
            "n": n, "effect": effect, "p": p, "alpha_fwer": ALPHA, "term": term,
            "verdict": verdict, "note": f"season={season}; {note}", "edge_claimed": False}


def run_h2_test(df23: pd.DataFrame) -> Dict[str, Any]:
    name = "catcher framing x count leverage"
    if not check_catcher_col(df23):
        return blocked_row(name, SPORT, "pitch", "fielder_2 (catcher id) column absent.",
                            method="savant_shift_framing_v1_test")
    fit = _fit_h2(df23)
    survives, note = _h2_note(fit)
    verdict = "NOT_TESTABLE" if fit is None else ("SURVIVES_PREREG" if survives else "NULL")
    if verdict == "SURVIVES_PREREG":
        note += " -- PROVISIONAL, needs independent replication before belief"
    n = fit["n"] if fit else 0
    p = fit["interaction"]["p"] if fit else None
    effect = fit["interaction"]["stat"] if fit else None
    return _row(name, "2023", "savant_shift_framing_v1_test", n, effect, p, verdict, note,
                term="catcher:pitcher_ahead")


def run_h2_replicate(df24: pd.DataFrame, test_row: Dict[str, Any]) -> Dict[str, Any]:
    name = "catcher framing x count leverage"
    if not check_catcher_col(df24):
        return blocked_row(name, SPORT, "pitch", "fielder_2 (catcher id) column absent.",
                            method="savant_shift_framing_v1_replicate")
    fit = _fit_h2(df24)
    survives, note = _h2_note(fit)
    if fit is None:
        verdict = "NOT_TESTABLE"
    else:
        verdict = "REPLICATED" if (test_row["verdict"] == "SURVIVES_PREREG" and survives) else "FAILED_REPLICATION"
    note += ("; replication criterion: both-p<alpha again -- an LR chi2 stat has no single signed "
             "coefficient so the brief's 'same-sign' wording does not literally apply here (deviation)")
    n = fit["n"] if fit else 0
    p = fit["interaction"]["p"] if fit else None
    effect = fit["interaction"]["stat"] if fit else None
    return _row(name, "2024", "savant_shift_framing_v1_replicate", n, effect, p, verdict, note,
                term="catcher:pitcher_ahead")


def run() -> list[Dict[str, Any]]:
    df23 = load_savant("2023")
    df24 = load_savant("2024")
    row_h1 = run_h1(df23)
    row_h2_test = run_h2_test(df23)
    row_h2_replicate = run_h2_replicate(df24, row_h2_test)
    rows = [row_h1, row_h2_test, row_h2_replicate]
    append_ledger(rows)
    return rows


def main() -> int:
    rows = run()
    print(f"K=2 alpha={ALPHA:.4f} (savant_shift_framing_v1)")
    for r in rows:
        print(f"  [{r['verdict']:>18}] {r['hypothesis']} ({r['method']}): "
              f"n={r['n']} effect={r['effect']} p={r['p']}")
    print(f"appended {len(rows)} rows -> {LEDGER_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

"""Q8 (WEEKEND_PLAN_2026-07-10.md section 4): replication-power upgrade for
mechanisms.md #40 (largest_lead persistence + margin-relation), the ONE
box-detail-family row that #35/#44's 2026-07-10 PM replication wave (see
validate_replication_wave1.py) did NOT cover (it replicated fast_break_pts,
paint_pts, tov_pts, ast -- largest_lead was left single-corpus).

STEP 0 PREMISE CHECK (this session):
  - q2 lead-extension (mechanisms.md #51, `validate_q2_blowout_state.py::
    q2_lead_extension_beyond_ar`) does NOT qualify for this rerun -- its
    status is already "CONFIRMED (REPLICATED, both corpora)" (2024-25 +
    2025-26 seasons), not a single-corpus PROVISIONAL. Falls through to
    "highest-value PROVISIONAL the new data can test" per the Q8 brief.
  - The only mechanism literally labelled PROVISIONAL in mechanisms.md is
    #54 (whistle-tightness Poisson-dispersion, split-half-by-date within
    ONE season) -- its design does not use the box-detail per-season
    corpora at all, so the new backfill cannot power a rerun of it.
  - #40 largest_lead is the row the 3-season box-detail backfill visibly
    unlocks: it used the EXACT same design as #34/#35 (now REPLICATED) but
    was never ported to a second corpus. Disk check confirms 3 disjoint
    season corpora now exist with `largest_lead` populated:
      data/domains/basketball_nba/espn_boxscores.parquet          (675 non-null rows, >=2026-01-20 slice -- the ORIGINAL #40 corpus)
      data/domains/basketball_nba/espn_boxscores_2024_25.parquet  (1,229 non-null rows, 2024-10-22..2025-04-13)
      data/domains/basketball_nba/espn_boxscores_2023_24.parquet (1,230 non-null rows, 2023-10-24..2024-04-14 -- landed 2026-07-10, brand new)
    Zero date overlap across the three -- genuinely 3 independent season
    corpora, matching the WEEKEND_PLAN's "3-season box-detail backfill".
  - #40 is treated as this task's target PROVISIONAL-equivalent: its
    literal label was CONFIRMED_LOCAL (not the string "PROVISIONAL"), but
    in this file's own convention (see #34/#35's pre-replication history in
    validate_replication_wave1.py's docstring) a CONFIRMED_LOCAL row tested
    on exactly one season corpus is functionally single-corpus-provisional
    until a second corpus reproduces it -- that is the gap this script
    closes, mirroring #34/#35/#44's promotion path.

PRE-REGISTERED VERDICT RULE (before any number below was computed):
  For EACH leg (persistence, margin) independently: >=2/3 seasons
  sign-consistent with the original #40 sign (positive, both legs) AND
  Fisher-combined p < 0.01 AND the pooled-3-season Fisher-z 95% CI on the
  correlation excludes zero. Both legs must pass -> promote. If either leg's
  pooled CI straddles zero -> NULL_UNDERPOWERED for that leg. Per the family
  convention #34/#35/#44 established (a disjoint-season box-detail parquet
  counts as an independent corpus, promotion label is REPLICATED, not
  merely "same source pooled"), a pass on BOTH new season corpora
  individually reproducing sign+significance (same bar as the original:
  ALPHA=0.01, MIN_EFFECT=0.15) upgrades the mechanism label from
  CONFIRMED_LOCAL to REPLICATED; a pass by pooling/Fisher alone without both
  individual seasons clearing the original per-season bar is held at
  CONFIRMED_LOCAL (pooled evidence stronger, but not yet 2-for-2 replication
  in the file's established sense).

Reuses domains.basketball_nba.knowledge.validate_boxdetail_persistence's
`_load_team_games` / `hypothesis` / ALPHA / MIN_EFFECT unchanged (same leak
audit: same-game descriptive values only, never wired as a live feature) --
this script only adds the per-season rerun + pooling + Fisher combination
on top, mirroring scripts/platformkit/improve/d1_staff_dayafter_pool.py's
structure (new pooling glue, no new mechanism logic).

Run: python -m scripts.platformkit.improve.q8_largest_lead_pool
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy import stats

from domains.basketball_nba.knowledge.validate_boxdetail_persistence import (
    ALPHA, MIN_EFFECT, _load_team_games, hypothesis,
)
from domains.basketball_nba.knowledge._data import REPO, LEDGER_PATH
from scripts.platformkit.io_atomic import append_jsonl_atomic

STAT = "largest_lead"
FISHER_ALPHA = 0.01
CI_ALPHA = 0.05
ORIG_PERSIST_SIGN = 1  # #40 original: persist_r=+0.779
ORIG_MARGIN_SIGN = 1   # #40 original: margin_r=+0.845

SEASON_PATHS = {
    "orig_2026_slice": REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet",
    "2024_25": REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores_2024_25.parquet",
    "2023_24": REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores_2023_24.parquet",
}


def _fisher_z_ci(r: float, n: int, alpha: float = CI_ALPHA) -> Dict[str, float]:
    """Standard Fisher z-transform CI for a Pearson r (n = pair count)."""
    if n < 4 or r is None or (isinstance(r, float) and np.isnan(r)):
        return {"ci_lo": np.nan, "ci_hi": np.nan}
    z = np.arctanh(np.clip(r, -0.999999, 0.999999))
    se = 1.0 / np.sqrt(n - 3)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    return {"ci_lo": round(float(np.tanh(z - z_crit * se)), 4), "ci_hi": round(float(np.tanh(z + z_crit * se)), 4)}


def _season_tg(path: Path) -> pd.DataFrame:
    return _load_team_games(pd.read_parquet(path))


def _leg_verdict(seasons_r: List[float], fisher_p: float, pooled_r: float, pooled_ci: Dict[str, float],
                  orig_sign: int) -> str:
    sign_consistent = sum(1 for r in seasons_r if r is not None and not np.isnan(r) and r * orig_sign > 0)
    if pooled_ci["ci_lo"] <= 0 <= pooled_ci["ci_hi"] or np.isnan(pooled_ci["ci_lo"]):
        return "NULL_UNDERPOWERED"
    if sign_consistent >= 2 and fisher_p < FISHER_ALPHA and abs(pooled_r) >= MIN_EFFECT:
        return "PASS"
    return "NULL_LOCAL"


def main() -> int:
    per_season = {}
    tgs = {}
    for name, path in SEASON_PATHS.items():
        tg = _season_tg(path)
        tgs[name] = tg
        per_season[name] = hypothesis(tg, STAT)

    pooled_tg = pd.concat(tgs.values(), ignore_index=True)
    pooled = hypothesis(pooled_tg, STAT)

    persist_ps = [per_season[s]["persist_p"] for s in SEASON_PATHS]
    margin_ps = [per_season[s]["margin_p"] for s in SEASON_PATHS]
    persist_rs = [per_season[s]["persist_r"] for s in SEASON_PATHS]
    margin_rs = [per_season[s]["margin_r"] for s in SEASON_PATHS]

    _, fisher_persist_p = stats.combine_pvalues(persist_ps, method="fisher")
    _, fisher_margin_p = stats.combine_pvalues(margin_ps, method="fisher")

    persist_ci = _fisher_z_ci(pooled["persist_r"], pooled["n_persist_teams"])
    margin_ci = _fisher_z_ci(pooled["margin_r"], pooled["n_margin"])

    persist_verdict = _leg_verdict(persist_rs, float(fisher_persist_p), pooled["persist_r"], persist_ci, ORIG_PERSIST_SIGN)
    margin_verdict = _leg_verdict(margin_rs, float(fisher_margin_p), pooled["margin_r"], margin_ci, ORIG_MARGIN_SIGN)

    # per-season individual replication check (the file's established
    # promotion bar: p<ALPHA AND |r|>=MIN_EFFECT, same sign, on EACH new
    # season standalone -- not just pooled/Fisher evidence).
    new_seasons_individually_pass = all(
        per_season[s]["verdict"] == "CONFIRMED_LOCAL"
        and (per_season[s]["persist_r"] or 0) * ORIG_PERSIST_SIGN > 0
        and (per_season[s]["margin_r"] or 0) * ORIG_MARGIN_SIGN > 0
        for s in ("2024_25", "2023_24")
    )

    if persist_verdict == "PASS" and margin_verdict == "PASS":
        label = "REPLICATED" if new_seasons_individually_pass else "CONFIRMED_LOCAL"
    elif persist_verdict == "NULL_UNDERPOWERED" or margin_verdict == "NULL_UNDERPOWERED":
        label = "NULL_UNDERPOWERED"
    else:
        label = "NULL_LOCAL"

    rows = []
    for name in SEASON_PATHS:
        r = dict(per_season[name])
        r["hypothesis"] = "boxdetail_largest_lead_persistence_q8_%s" % name
        r["sport"] = "basketball_nba"
        r["corpus"] = "espn_boxscores_%s" % name
        r["edge_claimed"] = False
        rows.append(r)

    pooled_row = {
        "hypothesis": "boxdetail_largest_lead_persistence_q8_pooled3season",
        "verdict": label,
        "persist_r": pooled["persist_r"], "persist_fisher_p": float(fisher_persist_p),
        "persist_ci_lo": persist_ci["ci_lo"], "persist_ci_hi": persist_ci["ci_hi"],
        "margin_r": pooled["margin_r"], "margin_fisher_p": float(fisher_margin_p),
        "margin_ci_lo": margin_ci["ci_lo"], "margin_ci_hi": margin_ci["ci_hi"],
        "n_persist_teams": pooled["n_persist_teams"], "n_margin": pooled["n_margin"],
        "seasons": list(SEASON_PATHS), "new_seasons_individually_pass": new_seasons_individually_pass,
        "sport": "basketball_nba", "corpus": "espn_boxscores_3season_pooled_2023_24_thru_2026",
        "edge_claimed": False,
        "note": ("persist: seasons r=%s Fisher p=%.4g pooled r=%.4f CI95[%.4f,%.4f] -> %s; "
                 "margin: seasons r=%s Fisher p=%.4g pooled r=%.4f CI95[%.4f,%.4f] -> %s; "
                 "label old(CONFIRMED_LOCAL, 1 corpus)->new(%s)"
                 % (["%.4f" % (r or 0) for r in persist_rs], fisher_persist_p, pooled["persist_r"],
                    persist_ci["ci_lo"], persist_ci["ci_hi"], persist_verdict,
                    ["%.4f" % (r or 0) for r in margin_rs], fisher_margin_p, pooled["margin_r"],
                    margin_ci["ci_lo"], margin_ci["ci_hi"], margin_verdict, label)),
    }
    rows.append(pooled_row)

    for r in rows:
        append_jsonl_atomic(LEDGER_PATH, r)
        note = r.get("note", "")
        print("%-52s %-20s %s" % (r["hypothesis"], r["verdict"], note[:200]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """No disk/network dependency -- pure logic check on the leg-verdict
    combination rule used above."""
    ci_ok = {"ci_lo": 0.2, "ci_hi": 0.6}
    ci_straddle = {"ci_lo": -0.1, "ci_hi": 0.3}
    assert _leg_verdict([0.7, 0.6, 0.8], 0.0001, 0.7, ci_ok, 1) == "PASS"
    assert _leg_verdict([0.7, -0.1, 0.8], 0.0001, 0.7, ci_ok, 1) == "PASS"  # 2/3 sign-consistent still passes
    assert _leg_verdict([0.7, 0.6], 0.5, 0.7, ci_ok, 1) == "NULL_LOCAL"  # fisher p too high
    assert _leg_verdict([0.7, 0.6, 0.8], 0.0001, 0.1, ci_straddle, 1) == "NULL_UNDERPOWERED"  # CI crosses zero
    z_ci = _fisher_z_ci(0.7, 30)
    assert z_ci["ci_lo"] < 0.7 < z_ci["ci_hi"]
    print("self-check OK")

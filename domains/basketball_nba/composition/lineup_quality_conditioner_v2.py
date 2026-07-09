"""v2 of the composed lineup-quality conditioner (be9715a9). Two upgrades:
(1) EXACT pbp score attribution -- v1 apportioned a team-stint's pts_for
proportionally by time-overlap with the opponent's stints; v2 walks the raw
pbp action score log (cumulative scoreHome/scoreAway per action) and reads
the exact score at each merged segment's start/end abs clock, home/away
deltas attributed directly (no apportionment). Validated first against an
independent source (player_boxscores summed pts) -- validate_attribution().
(2) FULL BASKET -- v1's 12 attrs -> every as-of PLAYER attribute with a
basketball-prior-defensible DIRECTION (efficiency/rebounding/foul/defense-
allowed), equal-weight, not fit. Excludes shot-distribution "share" attrs and
clutch-volume attrs (no declared direction on a tendency). Reuses v1's
composition math (load_player_composite, now basket-parameterized).

PREREGISTERED (K=2, Bonferroni alpha=0.025), same walk-forward convention as
v1 (2025-26<-2024-25 test; 2024-25<-2023-24 train/replicate; 2023-24
excluded). Declared BEFORE running:
  H1 'v2 beats v1': does v2's OOS walk-forward wRMSE delta on TEST improve
     over v1's own reported delta (0.032, be9715a9)?
  H2 'v2 basket breadth matters': composite_diff coefficient/p on TEST,
     same segments/baseline, SURVIVES_PREREG test + train replication.

Descriptive/calibration only. edge_claimed hard-wired False. NULL = success.
NETWORK: zero. ASCII only.
CLI:  python -m domains.basketball_nba.composition.lineup_quality_conditioner_v2
Test: python -m pytest domains/basketball_nba/composition/test_lineup_quality_conditioner_v2.py -q
"""
from __future__ import annotations

import bisect
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_nba.composition.lineup_quality_conditioner import (
    ALPHA, BASKET as BASKET_V1, CLOSE_LATE_MIN_N, LEDGER_PATH, MIN_OVERLAP_S,
    PLAYER_PROFILES, PRIOR_WINDOW, REPO_ROOT, TEAM_PROFILES, TEST_TAG, TRAIN_TAG,
    _BASE, _abs_offset, _lineup_comp, _period_len, _verdict, fit_term,
    load_player_composite, load_team_strength, oos_delta,
)

REPORT_PATH = REPO_ROOT / "data" / "frontend" / "ops" / "nba_lineup_quality_composition_v2.json"
_BOX_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_GAMES_SRC = REPO_ROOT / "data" / "domains" / "basketball_nba" / "games.parquet"
_PBP_DIRS = {
    "2025_26": REPO_ROOT / "data" / "cache" / "team_system" / "pbp",
    "2024_25": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25",
    "2023_24": REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2023_24",
}
METHOD = "lineup_quality_composition_v2"

# v1's 12 (kept) + 13 new, DECLARED signs from basketball priors (never fit).
# Excluded: *_attempt_share / *_assisted_share (tendency, no directional
# prior), clutch_fga_per_game / clutch_ft_rate (volume not quality),
# shot_zone_two/three_* (coarser duplicate of zone_efg_* already in basket),
# stint_stamina_avg_s (ambiguous, redundant w/ stint_minutes_load).
BASKET: Tuple[Tuple[str, int], ...] = BASKET_V1 + (
    ("creation", 1),               # eFG lift generated for teammates via assists
    ("zone_efg_paint", 1), ("zone_efg_mid", 1), ("zone_efg_corner3", 1),
    ("zone_efg_above_break_3", 1),
    ("oreb_pct", 1), ("dreb_pct", 1),
    ("pf_per36", -1),              # more fouls/36 = liability
    ("zone_def_rim_efg_allowed_on", -1), ("zone_def_paint_efg_allowed_on", -1),
    ("zone_def_mid_efg_allowed_on", -1), ("zone_def_corner3_efg_allowed_on", -1),
    ("zone_def_above_break_3_efg_allowed_on", -1),
)


def _load_game_score_track(game_json: Dict[str, Any]) -> Tuple[List[float], List[Tuple[int, int]]]:
    """Cumulative (scoreHome, scoreAway) per action, indexed by abs game-
    clock. Mirrors pbp_lineups._score_index but keyed on abs time (not
    actionNumber) so it can be queried at a MERGED segment boundary."""
    from domains.basketball_nba.lineups.pbp_lineups import _elapsed_s
    rows = []
    for a in game_json["game"]["actions"]:
        if a.get("scoreHome") is None:
            continue
        t = _abs_offset(a["period"]) + _elapsed_s(a["period"], a["clock"])
        rows.append((t, a["actionNumber"], int(a["scoreHome"]), int(a["scoreAway"])))
    rows.sort(key=lambda r: (r[0], r[1]))
    return [r[0] for r in rows], [(r[2], r[3]) for r in rows]


def _score_at_abs(times: List[float], scores: List[Tuple[int, int]], t: float) -> Tuple[int, int]:
    if not times:
        return (0, 0)
    i = bisect.bisect_right(times, t) - 1
    return scores[i] if i >= 0 else (0, 0)


def _load_pbp_json(season_tag: str, game_id: str) -> Optional[Dict[str, Any]]:
    fp = _PBP_DIRS[season_tag] / f"{game_id}.json"
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def build_segments_exact(stints_df: pd.DataFrame, season_tag: str,
                         games_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Same merged segment boundaries as v1 (two-pointer interval merge over
    each team's on-court-5 stints), but pts_a/pts_b = EXACT home/away score
    delta off the raw pbp log at the segment's abs start/end clock (no
    apportionment). Games missing a pbp file are skipped, not zero-filled."""
    if games_df is None:
        games_df = pd.read_parquet(_GAMES_SRC)
    home_by_gid = dict(zip(games_df["game_id"].astype(str), games_df["home_team"]))
    rows: List[Dict[str, Any]] = []
    for game_id, g in stints_df.groupby("game_id"):
        teams = sorted(g["team_id"].unique())
        if len(teams) != 2:
            continue
        ta, tb = teams
        gj = _load_pbp_json(season_tag, str(game_id))
        if gj is None:
            continue
        team_tricode = {a["teamId"]: a["teamTricode"] for a in gj["game"]["actions"] if a.get("teamId")}
        home_tricode = home_by_gid.get(str(game_id))
        home_team_id = next((tid for tid, tri in team_tricode.items() if tri == home_tricode), None)
        if home_team_id not in (ta, tb):
            continue  # can't resolve home/away -> skip rather than guess
        times, scores = _load_game_score_track(gj)
        game_len = sum(_period_len(p) for p in sorted(g["period"].unique()))
        for period, pg in g.groupby("period"):
            A = pg[(pg["team_id"] == ta) & (pg["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            B = pg[(pg["team_id"] == tb) & (pg["n_on_court"] == 5)].sort_values("start_s").to_dict("records")
            off, i, j = _abs_offset(period), 0, 0
            while i < len(A) and j < len(B):
                a, b = A[i], B[j]
                s, e = max(a["start_s"], b["start_s"]), min(a["end_s"], b["end_s"])
                if s < e:
                    abs_s, abs_e = off + s, off + e
                    sh0, sa0 = _score_at_abs(times, scores, abs_s)
                    sh1, sa1 = _score_at_abs(times, scores, abs_e)
                    dh, da = sh1 - sh0, sa1 - sa0
                    pa, pb = (dh, da) if ta == home_team_id else (da, dh)
                    rows.append({"game_id": game_id, "team_id_a": ta, "team_id_b": tb,
                                 "lineup_key_a": a["lineup_key"], "lineup_key_b": b["lineup_key"],
                                 "overlap_s": e - s, "pts_a": pa, "pts_b": pb,
                                 "abs_start": abs_s, "game_len": game_len})
                if a["end_s"] < b["end_s"]:
                    i += 1
                elif b["end_s"] < a["end_s"]:
                    j += 1
                else:
                    i += 1
                    j += 1
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["game_id", "abs_start"]).reset_index(drop=True)
    df["net"] = df["pts_a"] - df["pts_b"]
    df["score_margin_start"] = df.groupby("game_id")["net"].cumsum() - df["net"]
    df["time_remaining"] = df["game_len"] - df["abs_start"]
    return df


def validate_attribution(season_tag: str, stints_df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    """Reconstructed final score (last score-track entry/game) vs
    player_boxscores summed pts -- an INDEPENDENT source (2024-25/2025-26
    only; player_boxscores has zero 2023-24 rows, a known landmine, and
    2023-24 is already excluded from modeling)."""
    if stints_df is None:
        stints_df = pd.read_parquet(REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / f"stints_{season_tag}.parquet")
    box = pd.read_parquet(_BOX_SRC)
    box_pts = box.groupby(["game_id", "team", "is_home"])["pts"].sum().reset_index()

    n_checked, n_match, mismatches = 0, 0, []
    for game_id in stints_df["game_id"].astype(str).unique():
        gj = _load_pbp_json(season_tag, game_id)
        if gj is None:
            continue
        rows = box_pts[box_pts["game_id"] == game_id]
        home_row, away_row = rows[rows["is_home"] == 1.0], rows[rows["is_home"] == 0.0]
        if home_row.empty or away_row.empty:
            continue
        times, scores = _load_game_score_track(gj)
        if not scores:
            continue
        recon_home, recon_away = scores[-1]
        n_checked += 1
        if recon_home == int(home_row["pts"].iloc[0]) and recon_away == int(away_row["pts"].iloc[0]):
            n_match += 1
        else:
            mismatches.append({"game_id": game_id, "recon": [recon_home, recon_away],
                               "actual": [int(home_row["pts"].iloc[0]), int(away_row["pts"].iloc[0])]})
    return {"season": season_tag, "n_checked": n_checked, "n_match": n_match,
            "match_rate": (n_match / n_checked) if n_checked else None, "mismatches_sample": mismatches[:5]}


_MODEL_COLS = ["y", "score_margin_start", "time_remaining", "strength_diff", "composite_diff", "overlap_s", "game_id"]


def build_frame(season_tag: str, stints_df: Optional[pd.DataFrame] = None,
                player_path: Path = PLAYER_PROFILES, team_path: Path = TEAM_PROFILES,
                games_df: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    prior = PRIOR_WINDOW.get(season_tag)
    if prior is None:
        return None
    if stints_df is None:
        stints_df = pd.read_parquet(REPO_ROOT / "data" / "cache" / "team_system" / "lineups" / f"stints_{season_tag}.parquet")
    comp, coverage = load_player_composite(prior, player_path, basket=BASKET)
    strength = load_team_strength(prior, team_path)
    seg = build_segments_exact(stints_df, season_tag, games_df)
    if seg.empty:
        return seg
    seg = seg[seg["overlap_s"] >= MIN_OVERLAP_S].copy()
    seg["composite_a"] = seg["lineup_key_a"].map(lambda k: _lineup_comp(k, comp))
    seg["composite_b"] = seg["lineup_key_b"].map(lambda k: _lineup_comp(k, comp))
    seg["composite_diff"] = seg["composite_a"] - seg["composite_b"]
    seg["strength_diff"] = seg["team_id_a"].map(strength) - seg["team_id_b"].map(strength)
    seg["y"] = (seg["pts_a"] - seg["pts_b"]) / seg["overlap_s"] * 2880.0
    seg["close_late"] = ((seg["score_margin_start"].abs() <= 6) & (seg["time_remaining"] <= 360)).astype(int)
    seg.attrs["coverage"] = coverage
    return seg


V1_OOS_DELTA_RMSE = 0.032  # be9715a9's own reported OOS delta, the H1 comparator


def run() -> Dict[str, Any]:
    val_train = validate_attribution(TRAIN_TAG)
    val_test = validate_attribution(TEST_TAG)

    train, test = build_frame(TRAIN_TAG), build_frame(TEST_TAG)
    cov_test = float(test.attrs.get("coverage", 0.0)) if test is not None else 0.0

    h1_v2 = fit_term(test, _BASE + " + composite_diff", "composite_diff")
    oos_v2 = oos_delta(train, test)
    h1r_v2 = fit_term(train, _BASE + " + composite_diff", "composite_diff")
    sign_ref = None if h1_v2["effect"] is None else (1 if h1_v2["effect"] > 0 else -1)
    v1r_verdict = _verdict(h1r_v2["p"], h1r_v2["n"], sign_ref=sign_ref, effect=h1r_v2["effect"])

    # H1: does v2's OOS wRMSE delta beat v1's own reported 0.032?
    h1_delta = oos_v2["delta_rmse"]
    h1_verdict = "NOT_TESTABLE" if h1_delta is None else ("BEATS_V1" if h1_delta > V1_OOS_DELTA_RMSE else "NO_IMPROVEMENT")

    # H2: does v2's composite_diff p-value on TEST beat a null? (basket breadth)
    v2_prereg_verdict = _verdict(h1_v2["p"], h1_v2["n"])

    n_cl = int(test["close_late"].sum()) if test is not None and len(test) else 0
    rows = [
        {"hypothesis": "H1_v2_beats_v1_oos_wrmse", "sport": "nba", "atomic_unit": "lineup_segment_asof_exact",
         "method": METHOD, "season": f"walkforward_train_{TRAIN_TAG}_test_{TEST_TAG}",
         "n": oos_v2["n_test"], "effect": h1_delta, "p": None, "alpha_fwer": ALPHA,
         "term": "oos_delta_rmse_vs_v1_0.032", "verdict": h1_verdict, "edge_claimed": False},
        {"hypothesis": "H2_v2_basket_breadth_composite_diff", "sport": "nba", "atomic_unit": "lineup_segment_asof_exact",
         "method": METHOD, "season": f"walkforward_train_{TRAIN_TAG}_test_{TEST_TAG}",
         "n": h1_v2["n"], "effect": h1_v2["effect"], "p": h1_v2["p"], "alpha_fwer": ALPHA,
         "term": "composite_diff", "verdict": v2_prereg_verdict, "edge_claimed": False},
        {"hypothesis": "H1_v2_replication_2024_25", "sport": "nba", "atomic_unit": "lineup_segment_asof_exact",
         "method": METHOD, "season": f"walkforward_train_{TRAIN_TAG}_test_{TEST_TAG}",
         "n": h1r_v2["n"], "effect": h1r_v2["effect"], "p": h1r_v2["p"], "alpha_fwer": ALPHA,
         "term": "composite_diff", "verdict": v1r_verdict, "edge_claimed": False},
    ]

    report = {
        "method": METHOD, "generated_by": "domains/basketball_nba/composition/lineup_quality_conditioner_v2.py",
        "atomic_unit": "lineup_segment_asof_exact", "alpha_fwer_K2": ALPHA,
        "attribution_validation": {"train": val_train, "test": val_test},
        "walkforward": {"train_season": TRAIN_TAG, "train_prior_window": PRIOR_WINDOW[TRAIN_TAG],
                        "test_season": TEST_TAG, "test_prior_window": PRIOR_WINDOW[TEST_TAG],
                        "excluded_season": "2023_24 (no season_2022_23 prior profiles)"},
        "basket_v1_size": len(BASKET_V1), "basket_v2_size": len(BASKET),
        "basket": [{"attribute": a, "sign": s} for a, s in BASKET],
        "coverage_mean_test": cov_test,
        "H1_beats_v1": {"verdict": h1_verdict, "oos": oos_v2, "v1_comparator_delta_rmse": V1_OOS_DELTA_RMSE},
        "H2_composite_diff": {"verdict": v2_prereg_verdict, **h1_v2, "replication_2024_25": {"verdict": v1r_verdict, **h1r_v2}},
        "close_late_n_test": n_cl,
        "edge_claimed": False,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="ascii")
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return report


def main() -> int:
    rep = run()
    av = rep["attribution_validation"]
    print(f"attribution match: train={av['train']['n_match']}/{av['train']['n_checked']} "
          f"test={av['test']['n_match']}/{av['test']['n_checked']}")
    print(f"basket v1={rep['basket_v1_size']} -> v2={rep['basket_v2_size']}  coverage_test={rep['coverage_mean_test']:.3f}")
    h1, oos = rep["H1_beats_v1"], rep["H1_beats_v1"]["oos"]
    print(f"  H1 [{h1['verdict']:>16}] oos wRMSE base={oos['rmse_base']} full={oos['rmse_full']} "
          f"delta={oos['delta_rmse']} (v1 comparator={h1['v1_comparator_delta_rmse']})")
    h2 = rep["H2_composite_diff"]
    print(f"  H2 [{h2['verdict']:>16}] composite_diff: n={h2['n']} effect={h2['effect']} p={h2['p']}")
    print(f"     replication_2024_25 [{h2['replication_2024_25']['verdict']}]")
    print(f"  report -> {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

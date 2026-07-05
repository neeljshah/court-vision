"""tests.soccer.test_asof_reclaim_leak_guard -- leak guard for the ON-DISK RECLAIM
gate harnesses that merge asof_features.parquet / asof_xg_proxy.parquet onto the
Poisson goals gate corpus (domains.soccer.asof_features_gate,
scripts.platformkit.proof_soccer.gate_test_asof,
scripts.platformkit.proof_soccer.gate_test_xg_proxy).

domains/soccer/asof_features.py already has its OWN leak-free unit tests
(tests/soccer/test_asof_features.py) proving the walk-forward builder is
strictly prior-only. This file proves the SEPARATE thing: that the RECLAIM
MERGE STEP -- left-joining a pre-built as-of parquet onto the gate's base
matrix by event_id -- cannot leak a later match's own stats into an earlier
match's candidate-feature row, end to end through the actual reclaim code
paths used to produce the SHIP/REJECT verdicts.

Two invariants, both offline / synthetic (no parquet reads):
  1. MUTATION INVARIANCE: changing a LATER match's realized shot/SoT/xG-proxy
     stats must not change an EARLIER match's merged candidate value, its
     coverage flag, or the gate frame's target/base columns for that row.
  2. STRICTLY-EARLIER-ONLY: every covered row's merged as-of value is
     reconstructible from ONLY the matches strictly before that row's date
     (recomputed independently here) -- i.e. the merge is not silently using
     a same-day or future snapshot.

PURE pandas/numpy + domains.soccer.* + scripts.platformkit.proof_soccer.*.
No network. No src.*/kernel.* edits; read-only against existing modules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import pytest

from domains.soccer.asof_features import build_asof_frame
from domains.soccer.asof_features_gate import build_candidate_frame
from scripts.platformkit.proof_soccer.gate_test_asof import (
    _align_asof,
    _build_base_bundle_with_ids,
)

_LEAGUES = ("E0",)


def _match_row(date: str, home: str, away: str, fthg: int, ftag: int,
                hs: float, as_: float, hst: float, ast: float,
                season: int = 2024, div: str = "E0") -> dict:
    return {
        "event_id": f"{date}-{div}-{home}-{away}",
        "date": pd.Timestamp(date), "div": div, "season": season,
        "home_team": home, "away_team": away,
        "fthg": fthg, "ftag": ftag,
        "total_goals": fthg + ftag,
        "target_over25": float((fthg + ftag) >= 3),
        "home_shots": hs, "away_shots": as_,
        "home_sot": hst, "away_sot": ast,
    }


@pytest.fixture()
def synthetic_corpus() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """8-match chronological corpus spanning 5 teams; enough for MIN_PRIOR=5 gaps.

    Returns (matches_df, match_stats_df) -- matches_df carries the columns
    domains.soccer.adapter.SoccerAdapter / ratings.walk_forward_goals expect;
    match_stats_df is the shots/SoT sidecar contract asof_features.py expects.
    Same event_id keys tie the two together, as in production.
    """
    rows = [
        _match_row("2024-01-01", "Arsenal", "Chelsea", 2, 1, 12, 8, 6, 3),
        _match_row("2024-01-08", "Chelsea", "Everton", 1, 1, 10, 9, 4, 4),
        _match_row("2024-01-15", "Arsenal", "Everton", 3, 0, 15, 5, 8, 2),
        _match_row("2024-01-22", "Fulham", "Arsenal", 0, 2, 6, 14, 2, 7),
        _match_row("2024-01-29", "Chelsea", "Fulham", 2, 2, 11, 10, 5, 5),
        _match_row("2024-02-05", "Everton", "Fulham", 1, 0, 9, 7, 4, 3),
        _match_row("2024-02-12", "Arsenal", "Chelsea", 1, 1, 13, 9, 6, 4),
        # PROBE: last match -- the one whose merged feature we lock down.
        _match_row("2024-02-19", "Everton", "Arsenal", 0, 3, 8, 16, 3, 9),
    ]
    df = pd.DataFrame(rows)
    match_cols = ["event_id", "date", "div", "season", "home_team", "away_team",
                  "fthg", "ftag", "total_goals", "target_over25"]
    stats_cols = ["event_id", "date", "div", "home_team", "away_team",
                  "home_shots", "away_shots", "home_sot", "away_sot"]
    return df[match_cols].copy(), df[stats_cols].copy()


_PROBE_EID = "2024-02-19-E0-Everton-Arsenal"


def test_mutation_invariance_asof_features_gate(
    synthetic_corpus: Tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """build_candidate_frame's PROBE row value is unchanged when the corpus is
    extended with a NEW match dated AFTER the probe (and future scores are
    changed on that new match) -- the reclaim merge must not leak it."""
    matches, stats = synthetic_corpus
    asof = build_asof_frame(stats)
    before = build_candidate_frame(matches=matches, asof=asof,
                                    feat_col="diff_sot_for_asof")
    probe_before = before.loc[before["event_id"] == _PROBE_EID, "diff_sot_for_asof"]
    assert len(probe_before) == 1 and not probe_before.isna().all()

    # Extend with a future match + wildly different stats -> re-run the FULL
    # pipeline (asof build + candidate merge) from scratch.
    future_match = _match_row("2024-03-01", "Arsenal", "Fulham", 9, 0, 40, 1, 30, 0)
    matches2 = pd.concat([matches, pd.DataFrame([{
        k: future_match[k] for k in matches.columns}])], ignore_index=True)
    stats2 = pd.concat([stats, pd.DataFrame([{
        k: future_match[k] for k in stats.columns}])], ignore_index=True)

    asof2 = build_asof_frame(stats2)
    after = build_candidate_frame(matches=matches2, asof=asof2,
                                   feat_col="diff_sot_for_asof")
    probe_after = after.loc[after["event_id"] == _PROBE_EID, "diff_sot_for_asof"]
    assert len(probe_after) == 1
    assert probe_before.iloc[0] == pytest.approx(probe_after.iloc[0])

    # Coverage flag and target for the probe row must also be untouched.
    cov_before = before.loc[before["event_id"] == _PROBE_EID, "_cov"].iloc[0]
    cov_after = after.loc[after["event_id"] == _PROBE_EID, "_cov"].iloc[0]
    assert bool(cov_before) == bool(cov_after)
    tgt_before = before.loc[before["event_id"] == _PROBE_EID, "target_over25"].iloc[0]
    tgt_after = after.loc[after["event_id"] == _PROBE_EID, "target_over25"].iloc[0]
    assert tgt_before == pytest.approx(tgt_after)


def test_mutation_invariance_xg_proxy_gate(
    synthetic_corpus: Tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """Same mutation-invariance check for the xG-proxy candidate family
    (diff_xg_for_asof) via build_candidate_frame pointed at an xg_proxy frame."""
    matches, stats = synthetic_corpus
    from domains.soccer.asof_xg_proxy import _derive_realized
    from scripts.platformkit.asof_common import AsofSpec, ExpandingMean, walk_forward_asof

    def _xg_frame(ms: pd.DataFrame) -> pd.DataFrame:
        spine = _derive_realized(ms)
        result = pd.DataFrame({"event_id": spine["event_id"].to_numpy()})
        for m in ("xg_for", "xg_against"):
            spec = AsofSpec(sort_keys=["date", "event_id"],
                             slots=[("home_team", f"home_{m}", f"home_{m}"),
                                    ("away_team", f"away_{m}", f"away_{m}")])
            res = walk_forward_asof(spine, spec, ExpandingMean)
            cols = ["event_id", f"home_{m}_asof", f"away_{m}_asof"]
            if m == "xg_for":
                res = res.rename(columns={f"home_{m}_n_prior": "home_n_prior",
                                          f"away_{m}_n_prior": "away_n_prior"})
                cols += ["home_n_prior", "away_n_prior"]
            result = result.merge(res[cols], on="event_id", how="left")
            result[f"diff_{m}_asof"] = result[f"home_{m}_asof"] - result[f"away_{m}_asof"]
        return result

    xg_before = _xg_frame(stats)
    before = build_candidate_frame(matches=matches, asof=xg_before,
                                    feat_col="diff_xg_for_asof")
    probe_before = before.loc[before["event_id"] == _PROBE_EID, "diff_xg_for_asof"]
    assert len(probe_before) == 1

    future_match = _match_row("2024-03-01", "Arsenal", "Fulham", 9, 0, 40, 1, 30, 0)
    matches2 = pd.concat([matches, pd.DataFrame([{
        k: future_match[k] for k in matches.columns}])], ignore_index=True)
    stats2 = pd.concat([stats, pd.DataFrame([{
        k: future_match[k] for k in stats.columns}])], ignore_index=True)

    xg_after = _xg_frame(stats2)
    after = build_candidate_frame(matches=matches2, asof=xg_after,
                                   feat_col="diff_xg_for_asof")
    probe_after = after.loc[after["event_id"] == _PROBE_EID, "diff_xg_for_asof"]
    assert len(probe_after) == 1
    assert probe_before.iloc[0] == pytest.approx(probe_after.iloc[0])


def test_align_asof_matches_recomputed_prior_only_value(
    synthetic_corpus: Tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """_align_asof (the gate_test_asof merge helper) returns EXACTLY the value
    recomputed independently from matches strictly before the probe's date --
    not a same-day or future snapshot."""
    matches, stats = synthetic_corpus
    asof = build_asof_frame(stats)

    # _build_base_bundle_with_ids reads from disk by default in real use;
    # construct a local SoccerAdapter over the synthetic frames instead
    # (matches its documented dependency-injection seam).
    from domains.soccer.adapter import SoccerAdapter
    adapter = SoccerAdapter(matches_df=matches, odds_df=pd.DataFrame(
        columns=["event_id", "ou_prematch_over", "ou_prematch_under",
                 "ou_close_over", "ou_close_under"]))
    bb, event_ids = _build_base_bundle_with_ids(adapter=adapter)
    aligned = _align_asof(asof, event_ids, "diff_sot_for_asof")

    probe_idx = event_ids.index(_PROBE_EID)
    merged_val = aligned[probe_idx]

    # Independently recompute the PRIOR-only diff for the probe row using only
    # matches with date strictly < the probe's date (2024-02-19).
    probe_date = pd.Timestamp("2024-02-19")
    prior = stats[pd.to_datetime(stats["date"]) < probe_date]

    def _team_sot_for(team: str) -> float:
        home_rows = prior[prior["home_team"] == team]["home_sot"].astype(float)
        away_rows = prior[prior["away_team"] == team]["away_sot"].astype(float)
        vals = pd.concat([home_rows, away_rows])
        return float(vals.mean())

    # PROBE match is Everton(home) vs Arsenal(away); diff = home - away.
    expected_diff = _team_sot_for("Everton") - _team_sot_for("Arsenal")
    assert merged_val == pytest.approx(expected_diff)


def test_no_row_uses_same_day_or_future_stats(
    synthetic_corpus: Tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """Sweep EVERY covered row (not just the probe): the merged as-of value must
    equal the value recomputed from strictly-earlier matches only."""
    matches, stats = synthetic_corpus
    asof = build_asof_frame(stats)
    cand = build_candidate_frame(matches=matches, asof=asof,
                                  feat_col="diff_sot_for_asof")
    stats_dated = stats.assign(date=pd.to_datetime(stats["date"]))

    def _recompute(team: str, before: pd.Timestamp) -> float:
        prior = stats_dated[stats_dated["date"] < before]
        home_rows = prior[prior["home_team"] == team]["home_sot"].astype(float)
        away_rows = prior[prior["away_team"] == team]["away_sot"].astype(float)
        vals = pd.concat([home_rows, away_rows])
        return float(vals.mean()) if len(vals) else float("nan")

    checked = 0
    for _, r in cand.iterrows():
        eid = str(r["event_id"])
        m = matches.loc[matches["event_id"] == eid]
        if m.empty:
            continue
        home, away = str(m.iloc[0]["home_team"]), str(m.iloc[0]["away_team"])
        d = pd.to_datetime(m.iloc[0]["date"])
        exp_home = _recompute(home, d)
        exp_away = _recompute(away, d)
        merged = r["diff_sot_for_asof"]
        if np.isnan(exp_home) or np.isnan(exp_away):
            assert pd.isna(merged), f"{eid}: expected NaN (no prior), got {merged}"
        else:
            assert merged == pytest.approx(exp_home - exp_away), eid
        checked += 1
    assert checked == len(matches)  # every row in the synthetic corpus was checked

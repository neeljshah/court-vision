"""Per-file tests for soccer_team_oppstrength_form_claims.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_soccer_team_oppstrength_form_claims.py -q

Acceptance:
  1. Tercile cut assigns the highest opponent-strength value "strong" and
     the lowest "weak" (dedicated, uncontaminated 9-row check).
  2. Floor exclusion is COUNTED (below-floor team excluded, honest tally).
  3. As-of shift excludes self-match: neither ppg_vs_strong nor sos_asof may
     reflect the team's own most-recent (sentinel) match.
  4. Identity round-trip: validator independently recomputes the exact same
     values straight from the snapshot parquet + criteria.formula (VERIFIED).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import soccer_team_oppstrength_form_claims as oc


def test_tercile_cut_assigns_extremes_correctly():
    df = pd.DataFrame({
        "team": [f"T{i}" for i in range(9)],
        "div": ["E0"] * 9, "season": [2020] * 9,
        "opp_xg_supremacy_asof": [float(i) for i in range(1, 10)],  # 1..9
    })
    labeled = oc.assign_opp_tercile(df)
    assert labeled.loc[labeled["opp_xg_supremacy_asof"] == 1.0, "opp_tercile"].iloc[0] == "weak"
    assert labeled.loc[labeled["opp_xg_supremacy_asof"] == 9.0, "opp_tercile"].iloc[0] == "strong"
    assert labeled.loc[labeled["opp_xg_supremacy_asof"] == 5.0, "opp_tercile"].iloc[0] == "mid"


def _synthetic_labeled_long() -> pd.DataFrame:
    """AAA: 6 prior matches vs WEAK opponents (always wins, pts=3) then 6
    prior matches vs STRONG opponents (always loses, pts=0), then a FINAL
    (most-recent) match vs a STRONG opponent that AAA wins (pts=3) with a
    sentinel opp_xg_supremacy_asof=999 -- if the as-of shift leaked this
    match in, ppg_vs_strong would rise above 0.0 and sos_asof would spike
    toward 999. BBB plays only 2 matches (below every floor). opp_tercile
    is PRE-LABELED here (assign_opp_tercile is monkeypatched to a no-op in
    the fixture using this frame, isolating this from the tercile-cut test
    above)."""
    rows = []
    day = 0
    for _ in range(6):
        rows.append({"team": "AAA", "div": "E0", "season": 2020,
                     "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "pts": 3, "opp_xg_supremacy_asof": -1.0, "opp_tercile": "weak"})
        day += 7
    for _ in range(6):
        rows.append({"team": "AAA", "div": "E0", "season": 2020,
                     "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "pts": 0, "opp_xg_supremacy_asof": 5.0, "opp_tercile": "strong"})
        day += 7
    rows.append({"team": "AAA", "div": "E0", "season": 2020,
                 "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                 "pts": 3, "opp_xg_supremacy_asof": 999.0, "opp_tercile": "strong"})
    day += 7
    for _ in range(2):
        rows.append({"team": "BBB", "div": "E0", "season": 2020,
                     "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=day),
                     "pts": 1, "opp_xg_supremacy_asof": 0.0, "opp_tercile": "mid"})
        day += 7
    df = pd.DataFrame(rows)
    return df.sample(frac=1.0, random_state=11).reset_index(drop=True)  # shuffled on-disk order


@pytest.fixture()
def synthetic_snapshot(monkeypatch, tmp_path):
    claims_dir = tmp_path / "intel_claims"
    claims_dir.mkdir(parents=True)
    monkeypatch.setattr(oc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(oc, "_OUT_DIR", claims_dir)
    monkeypatch.setattr(oc, "_SNAPSHOT", claims_dir / "soccer_team_oppstrength_form_snapshot.parquet")
    monkeypatch.setattr(oc, "assign_opp_tercile", lambda df: df)  # opp_tercile already pre-labeled
    return _synthetic_labeled_long()


def test_floor_excludes_below_floor_team_and_counts_it(synthetic_snapshot):
    snap = oc.build_snapshot(synthetic_snapshot)
    claims = oc.build_all_claims(snap)
    sos_claim = next(c for c in claims if c["criteria"]["metric"] == "sos_asof")
    ranked_teams = {r["team"] for r in sos_claim["ranking"]}
    assert "AAA" in ranked_teams          # n_prior = 12 >= floor 10
    assert "BBB" not in ranked_teams      # n_prior = 1 < floor 10
    assert sos_claim["n_excluded_below_floor"] == 1


def test_asof_shift_excludes_self_match(synthetic_snapshot):
    """AAA's final (sentinel) match is a WIN (pts=3) vs a STRONG opponent
    with opp_xg_supremacy_asof=999. If leaked, ppg_vs_strong would rise
    above 0.0 and sos_asof would spike toward 999; neither may happen."""
    snap = oc.build_snapshot(synthetic_snapshot)
    aaa = snap[snap["team"] == "AAA"].iloc[0]
    assert aaa["n_prior"] == 12  # the 13th (sentinel) match is dropped
    assert aaa["n_vs_strong"] == 6
    assert aaa["ppg_vs_strong"] == pytest.approx(0.0)   # NOT >0 -- sentinel win excluded
    assert aaa["n_vs_weak"] == 6
    assert aaa["ppg_vs_weak"] == pytest.approx(3.0)
    assert aaa["form_strength_gap"] == pytest.approx(-3.0)
    # trailing-10 of the 12 prior rows = [4 weak(-1.0) remaining, 6 strong(5.0)]
    assert aaa["sos_asof"] == pytest.approx(2.6)   # NOT near 999 -- sentinel excluded


def test_identity_roundtrip_validator_verifies(synthetic_snapshot):
    snap = oc.build_snapshot(synthetic_snapshot)
    oc.write_snapshot(snap, oc._SNAPSHOT)
    claims = oc.build_all_claims(snap)
    assert len(claims) > 0
    orig_root = claims_validator.REPO_ROOT
    claims_validator.REPO_ROOT = oc.REPO_ROOT
    try:
        for claim in claims:
            verdict = claims_validator.validate_claim(claim)
            assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"
    finally:
        claims_validator.REPO_ROOT = orig_root


def test_honest_caveats_and_edge_claimed_false(synthetic_snapshot):
    snap = oc.build_snapshot(synthetic_snapshot)
    claims = oc.build_all_claims(snap)
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll"):
            assert word not in blob
        assert "descriptive" in blob
        assert "floor" in blob
        assert claim["criteria"]["entity_key"] == "team"

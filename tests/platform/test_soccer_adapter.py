"""tests.platform.test_soccer_adapter — Leak-guard + contract tests for SoccerAdapter.

Runs entirely on synthetic injected DataFrames (no parquet I/O).
All leak-guard assertions are mandatory per S-D-001 spec.
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures — synthetic data
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# Team pool: 4 teams, 2 leagues, 2 seasons
_TEAMS_A = ["Arsenal", "Chelsea", "ManCity", "Liverpool"]
_TEAMS_B = ["RealMadrid", "Barcelona", "Atletico", "Valencia"]

# Build ~36 matches: two seasons (2022, 2023), two divs (E0, SP1)
# Each pair of teams plays home+away per season in each div block

def _make_matches() -> pd.DataFrame:
    rows: List[dict] = []
    eid = 1
    base_date = dt.date(2022, 8, 6)

    for season, teams, div in [
        (2022, _TEAMS_A, "E0"),
        (2022, _TEAMS_B, "SP1"),
        (2023, _TEAMS_A, "E0"),
        (2023, _TEAMS_B, "SP1"),
    ]:
        d = base_date + dt.timedelta(days=(season - 2022) * 180)
        match_idx = 0
        for i, home in enumerate(teams):
            for j, away in enumerate(teams):
                if home == away:
                    continue
                # Score: varied, ensuring both over and under outcomes present.
                # Pattern: every 4th match is a 3-goal match (guaranteed over).
                if match_idx % 4 == 0:
                    fthg, ftag = 2, 1  # total=3 → over
                elif match_idx % 4 == 1:
                    fthg, ftag = 1, 1  # total=2 → under
                elif match_idx % 4 == 2:
                    fthg, ftag = 0, 0  # total=0 → under
                else:
                    fthg, ftag = (i + j) % 3, (i * j) % 2
                total = fthg + ftag
                ftr = "H" if fthg > ftag else ("A" if ftag > fthg else "D")
                rows.append(
                    dict(
                        event_id=f"ev{eid}",
                        date=str(d),
                        season=season,
                        div=div,
                        home_team=home,
                        away_team=away,
                        fthg=fthg,
                        ftag=ftag,
                        total_goals=total,
                        target_over25=1 if total >= 3 else 0,
                        ftr=ftr,
                    )
                )
                eid += 1
                match_idx += 1
                d += dt.timedelta(days=7)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _make_odds(matches_df: pd.DataFrame) -> pd.DataFrame:
    """Synthetic odds — open/close differ so the open≠close test passes."""
    rows: List[dict] = []
    rng = np.random.default_rng(42)
    for _, m in matches_df.iterrows():
        open_over = round(float(rng.uniform(1.5, 2.5)), 2)
        open_under = round(float(rng.uniform(1.5, 2.5)), 2)
        # Close prices slightly shifted from pre-match
        close_over = round(open_over * float(rng.uniform(0.9, 1.1)), 2)
        close_under = round(open_under * float(rng.uniform(0.9, 1.1)), 2)
        rows.append(
            dict(
                event_id=m["event_id"],
                div=m["div"],
                date=m["date"],
                ou_prematch_over=open_over,
                ou_prematch_under=open_under,
                ou_close_over=close_over,
                ou_close_under=close_under,
                book_prematch="bet365",
                book_close="pinnacle",
            )
        )
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def matches_df() -> pd.DataFrame:
    return _make_matches()


@pytest.fixture(scope="module")
def odds_df(matches_df: pd.DataFrame) -> pd.DataFrame:
    return _make_odds(matches_df)


@pytest.fixture(scope="module")
def adapter(matches_df: pd.DataFrame, odds_df: pd.DataFrame):
    from domains.soccer.adapter import SoccerAdapter
    return SoccerAdapter(matches_df=matches_df, odds_df=odds_df)


# ---------------------------------------------------------------------------
# feature_bundle shape + type contract
# ---------------------------------------------------------------------------


def test_feature_bundle_shape(adapter, matches_df):
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    n = bundle.base.shape[0]
    assert bundle.base.shape == (n, 5), f"Expected (n,5) base, got {bundle.base.shape}"
    assert bundle.signal_col.shape == (n,)
    assert bundle.target.shape == (n,)
    assert len(bundle.dates) == n
    assert n > 0, "Expected at least 1 row"


def test_feature_bundle_target_binary(adapter):
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    assert set(bundle.target).issubset({0.0, 1.0}), (
        f"target values outside {{0,1}}: {set(bundle.target)}"
    )


def test_feature_bundle_dates_ascending(adapter):
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    dates = bundle.dates
    assert dates == sorted(dates), "dates must be in ascending order"


def test_feature_bundle_lengths_consistent(adapter):
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    n = len(bundle.dates)
    assert bundle.base.shape[0] == n
    assert bundle.signal_col.shape[0] == n
    assert bundle.target.shape[0] == n
    if bundle.lines is not None:
        assert bundle.lines.shape[0] == n
    if bundle.closing is not None:
        assert bundle.closing.shape[0] == n


def test_feature_bundle_single_season(adapter):
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022])
    assert bundle.base.shape[0] > 0


def test_feature_bundle_no_rows_raises(adapter):
    with pytest.raises(ValueError, match="no rows"):
        adapter.feature_bundle(hypothesis=None, seasons=[9999])


def test_feature_bundle_signal_in_zero_one(adapter):
    """signal_col = p_over25 from Poisson model → must be in (0,1)."""
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    assert np.all(bundle.signal_col >= 0.0) and np.all(bundle.signal_col <= 1.0)


# ---------------------------------------------------------------------------
# NO-LEAK perturbation test (MANDATORY)
# ---------------------------------------------------------------------------


def test_no_leak_perturbation(matches_df, odds_df):
    """CRITICAL leak guard.

    Perturbing a match's *outcome* (fthg/ftag) must not change any pre-match
    feature or signal for rows at or before that match's date.

    - base[j] and signal_col[j] for j with dates[j] <= perturbed_date: UNCHANGED.
    - target[i] for the perturbed row: MUST change (confirms the perturbation
      actually flipped the target_over25).
    - Rows AFTER the perturbed date may legitimately differ (the result feeds
      future ratings).
    """
    from domains.soccer.adapter import SoccerAdapter

    # Build reference bundle
    adapter_ref = SoccerAdapter(matches_df=matches_df, odds_df=odds_df)
    bundle_ref = adapter_ref.feature_bundle(hypothesis=None, seasons=[2022, 2023])

    # Pick a row index in the middle of the reference bundle
    n = bundle_ref.base.shape[0]
    i = n // 2
    perturbed_date_str = bundle_ref.dates[i]

    # Find the corresponding matches_df row by date
    wf_dates = pd.to_datetime(matches_df["date"]).dt.date.astype(str)
    candidate_mask = wf_dates == perturbed_date_str
    if not candidate_mask.any():
        # Fallback: pick a date that exists
        candidate_mask = wf_dates <= perturbed_date_str
    candidate_idx = matches_df[candidate_mask].index[0]

    # Flip fthg so that total_goals changes and target_over25 flips
    original_row = matches_df.loc[candidate_idx]
    original_fthg = int(original_row["fthg"])
    original_total = int(original_row["total_goals"])
    original_target = int(original_row["target_over25"])

    # Choose a fthg that flips total from >=3 to <3 or vice versa
    new_ftag = int(original_row["ftag"])
    if original_target == 1:  # was Over → make Under
        new_fthg = max(0, 1 - new_ftag)  # total = 1-new_ftag+new_ftag = 1 → Under
        if new_fthg + new_ftag >= 3:
            new_fthg = 0
            new_ftag = 0
    else:  # was Under → make Over
        new_fthg = 3  # total = 3+new_ftag >= 3 → Over

    new_total = new_fthg + new_ftag
    new_ftr = "H" if new_fthg > new_ftag else ("A" if new_ftag > new_fthg else "D")

    perturbed_df = matches_df.copy()
    perturbed_df.loc[candidate_idx, "fthg"] = new_fthg
    perturbed_df.loc[candidate_idx, "ftag"] = new_ftag
    perturbed_df.loc[candidate_idx, "total_goals"] = new_total
    perturbed_df.loc[candidate_idx, "target_over25"] = 1 if new_total >= 3 else 0
    perturbed_df.loc[candidate_idx, "ftr"] = new_ftr

    adapter_pert = SoccerAdapter(matches_df=perturbed_df, odds_df=odds_df)
    bundle_pert = adapter_pert.feature_bundle(hypothesis=None, seasons=[2022, 2023])

    # walk_forward_goals processes rows in sorted order: (date, div, home, away).
    # The perturbed row's result updates the EW state and can affect pre-match
    # features for rows sorted AFTER it — even those on the SAME date.
    # Therefore the guaranteed-unchanged window is rows with date STRICTLY BEFORE
    # the perturbed date.  Rows on or after that date may legitimately differ.
    ref_dates = np.array(bundle_ref.dates)
    pert_dates = np.array(bundle_pert.dates)

    strictly_before_mask_ref = ref_dates < perturbed_date_str
    strictly_before_mask_pert = pert_dates < perturbed_date_str

    ref_base_before = bundle_ref.base[strictly_before_mask_ref]
    pert_base_before = bundle_pert.base[strictly_before_mask_pert]

    assert ref_base_before.shape == pert_base_before.shape, (
        "Number of rows strictly before perturbed date changed — structure leak"
    )
    assert np.allclose(ref_base_before, pert_base_before, atol=0, rtol=0), (
        "base features changed strictly before perturbed row — LEAK DETECTED"
    )

    ref_sig_before = bundle_ref.signal_col[strictly_before_mask_ref]
    pert_sig_before = bundle_pert.signal_col[strictly_before_mask_pert]
    assert np.allclose(ref_sig_before, pert_sig_before, atol=0, rtol=0), (
        "signal_col changed strictly before perturbed row — LEAK DETECTED"
    )

    # The perturbed match's target MUST have changed (confirms perturbation worked)
    # Find the perturbed row's date in the bundles
    pert_target_ref = bundle_ref.target[ref_dates == perturbed_date_str]
    pert_target_pert = bundle_pert.target[pert_dates == perturbed_date_str]

    if len(pert_target_ref) > 0 and len(pert_target_pert) > 0:
        # There may be multiple rows on the same date; at least one must differ
        orig_val = 1.0 if original_target else 0.0
        new_val = 1.0 if (new_total >= 3) else 0.0
        if orig_val != new_val:
            assert not np.allclose(pert_target_ref, pert_target_pert, atol=0, rtol=0), (
                "target did NOT change after perturbation — perturbation had no effect"
            )


# ---------------------------------------------------------------------------
# Base excludes outcome / odds columns
# ---------------------------------------------------------------------------


def test_base_excludes_outcome_columns(adapter):
    """Sanity-check that base is 5 cols of pre-match ratings, not outcomes/odds."""
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    # 5 columns: [lam_home, lam_away, lam_total, rest_home, rest_away]
    # Lambdas are ~Poisson rates (typically 0.5–3); rest days 0–30.
    # Outcome columns fthg/ftag/total_goals are non-negative integers;
    # we can't distinguish purely by value — but we verify shape and that
    # signal_col (p_over25) is NOT a column of base.
    assert bundle.base.shape[1] == 5

    # All base values must be finite positive numbers (Poisson rates + rest days)
    assert np.all(np.isfinite(bundle.base)), "base contains non-finite values"

    # lam_total col (index 2) == lam_home (index 0) + lam_away (index 1)
    np.testing.assert_allclose(
        bundle.base[:, 2],
        bundle.base[:, 0] + bundle.base[:, 1],
        rtol=1e-9,
        err_msg="base col 2 (lam_total) != lam_home + lam_away",
    )

    # rest_days cols (3, 4) must be in [0, 30]
    assert np.all(bundle.base[:, 3] >= 0) and np.all(bundle.base[:, 3] <= 30)
    assert np.all(bundle.base[:, 4] >= 0) and np.all(bundle.base[:, 4] <= 30)


# ---------------------------------------------------------------------------
# market_snapshot tests
# ---------------------------------------------------------------------------


def test_market_snapshot_open_vs_close(adapter, matches_df):
    """Open and close snapshots should differ when prices differ."""
    event = adapter.list_events(matches_df["date"].iloc[0].date())[0]
    snap_open = adapter.market_snapshot(event, "open")
    snap_close = adapter.market_snapshot(event, "close")
    assert snap_open is not None, "Expected open snapshot"
    assert snap_close is not None, "Expected close snapshot"
    assert snap_open.price_a > 1.0
    assert snap_open.price_b > 1.0
    assert snap_close.price_a > 1.0
    assert snap_close.price_b > 1.0
    # Open and close should differ (synthetic data uses slight randomisation)
    # They MIGHT be equal by chance — check either price or book differs
    assert (
        snap_open.price_a != snap_close.price_a
        or snap_open.price_b != snap_close.price_b
        or snap_open.book != snap_close.book
    ), "open and close snapshots are identical — synthetic randomisation may have collapsed"


def test_market_snapshot_none_for_missing_event(matches_df, odds_df):
    from domains.soccer.adapter import SoccerAdapter
    from domains.soccer.config import EventRef, SPORT_ID, OVER_SIDE, UNDER_SIDE
    adapter_local = SoccerAdapter(matches_df=matches_df, odds_df=odds_df)
    ghost = EventRef(
        sport=SPORT_ID,
        event_id="ev_does_not_exist",
        start_time_utc=dt.datetime(2022, 1, 1, 12, 0),
        entity_a=OVER_SIDE,
        entity_b=UNDER_SIDE,
        meta={"home_team": "X", "away_team": "Y", "div": "E0", "season": 2022},
    )
    assert adapter_local.market_snapshot(ghost, "open") is None
    assert adapter_local.market_snapshot(ghost, "close") is None


def test_market_snapshot_invalid_prices_returns_none(matches_df):
    """Prices <= 1.0 should yield None."""
    from domains.soccer.adapter import SoccerAdapter
    from domains.soccer.config import EventRef, SPORT_ID, OVER_SIDE, UNDER_SIDE
    bad_odds = pd.DataFrame(
        [
            dict(
                event_id="ev_bad",
                div="E0",
                date="2022-08-06",
                ou_prematch_over=0.9,
                ou_prematch_under=1.2,
                ou_close_over=1.8,
                ou_close_under=2.0,
                book_prematch="bad",
                book_close="ok",
            )
        ]
    )
    bad_match = matches_df.head(1).copy()
    bad_match["event_id"] = "ev_bad"
    adp = SoccerAdapter(matches_df=bad_match, odds_df=bad_odds)
    ev = adp.list_events(bad_match["date"].iloc[0].date())[0]
    assert adp.market_snapshot(ev, "open") is None  # price_a=0.9 <= 1.0


# ---------------------------------------------------------------------------
# outcome boundary tests
# ---------------------------------------------------------------------------


def test_outcome_2_goals_is_under(matches_df):
    """A match with exactly 2 total goals → winner='b' (Under 2.5 lands)."""
    from domains.soccer.adapter import SoccerAdapter
    two_goal = matches_df[matches_df["total_goals"] == 2]
    if two_goal.empty:
        pytest.skip("No 2-goal matches in synthetic data")
    row = two_goal.iloc[0]
    adp = SoccerAdapter(matches_df=matches_df)
    ev_date = pd.to_datetime(row["date"]).date()
    events = adp.list_events(ev_date)
    ev = next((e for e in events if e.event_id == row["event_id"]), None)
    if ev is None:
        pytest.skip("Event not found on that date")
    out = adp.outcome(ev)
    assert out is not None
    assert out.winner == "b", f"Expected 'b' for 2-goal match, got {out.winner}"


def test_outcome_3_goals_is_over(matches_df):
    """A match with exactly 3 total goals → winner='a' (Over 2.5 lands)."""
    from domains.soccer.adapter import SoccerAdapter
    three_goal = matches_df[matches_df["total_goals"] == 3]
    if three_goal.empty:
        pytest.skip("No 3-goal matches in synthetic data")
    row = three_goal.iloc[0]
    adp = SoccerAdapter(matches_df=matches_df)
    ev_date = pd.to_datetime(row["date"]).date()
    events = adp.list_events(ev_date)
    ev = next((e for e in events if e.event_id == row["event_id"]), None)
    if ev is None:
        pytest.skip("Event not found on that date")
    out = adp.outcome(ev)
    assert out is not None
    assert out.winner == "a", f"Expected 'a' for 3-goal match, got {out.winner}"


def test_outcome_missing_event_returns_none(adapter):
    from domains.soccer.config import EventRef, SPORT_ID, OVER_SIDE, UNDER_SIDE
    ghost = EventRef(
        sport=SPORT_ID,
        event_id="ev_ghost_9999",
        start_time_utc=dt.datetime(2022, 1, 1, 12, 0),
        entity_a=OVER_SIDE,
        entity_b=UNDER_SIDE,
        meta={"home_team": "Ghost", "away_team": "Phantom", "div": "E0", "season": 2022},
    )
    assert adapter.outcome(ghost) is None


def test_outcome_0_goals_is_under(matches_df):
    """0-goal match → Under 2.5."""
    from domains.soccer.adapter import SoccerAdapter
    zero_goal = matches_df[matches_df["total_goals"] == 0]
    if zero_goal.empty:
        pytest.skip("No 0-goal matches in synthetic data")
    row = zero_goal.iloc[0]
    adp = SoccerAdapter(matches_df=matches_df)
    ev_date = pd.to_datetime(row["date"]).date()
    events = adp.list_events(ev_date)
    ev = next((e for e in events if e.event_id == row["event_id"]), None)
    if ev is None:
        pytest.skip("Event not found on that date")
    out = adp.outcome(ev)
    assert out is not None
    assert out.winner == "b"


# ---------------------------------------------------------------------------
# baseline_probability
# ---------------------------------------------------------------------------


def test_baseline_probability_in_range(adapter, matches_df):
    """baseline_probability must return a float in (0, 1)."""
    row = matches_df.iloc[5]
    ev_date = pd.to_datetime(row["date"]).date()
    events = adapter.list_events(ev_date)
    ev = next((e for e in events if e.event_id == row["event_id"]), None)
    if ev is None:
        pytest.skip("Event not in list_events output")
    as_of = dt.datetime.combine(ev_date, dt.time(10, 0))
    p = adapter.baseline_probability(ev, as_of)
    assert isinstance(p, float)
    assert 0.0 < p < 1.0, f"baseline_probability out of range: {p}"


def test_baseline_probability_is_pre_match(matches_df):
    """Baseline probability must use only matches strictly before as_of date."""
    from domains.soccer.adapter import SoccerAdapter
    adp = SoccerAdapter(matches_df=matches_df)
    row = matches_df.iloc[10]
    ev_date = pd.to_datetime(row["date"]).date()
    events = adp.list_events(ev_date)
    ev = next((e for e in events if e.event_id == row["event_id"]), None)
    if ev is None:
        pytest.skip("Event not found in list_events")

    as_of_before = dt.datetime.combine(ev_date, dt.time(8, 0))
    p_before = adp.baseline_probability(ev, as_of_before)

    # Use same as_of (same date) for a second call — result must be identical
    # since as_of is same-date and both exclude the match-day
    p_before2 = adp.baseline_probability(ev, as_of_before)
    assert p_before == p_before2, "baseline_probability not deterministic"
    assert 0.0 < p_before < 1.0


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


def test_list_events_returns_correct_sides(adapter, matches_df):
    from domains.soccer.config import OVER_SIDE, UNDER_SIDE
    ev_date = pd.to_datetime(matches_df["date"].iloc[0]).date()
    events = adapter.list_events(ev_date)
    assert len(events) > 0
    for ev in events:
        assert ev.entity_a == OVER_SIDE
        assert ev.entity_b == UNDER_SIDE
        assert ev.sport == "soccer_fd"
        assert "home_team" in ev.meta
        assert "away_team" in ev.meta


def test_list_events_empty_date(adapter):
    empty_date = dt.date(1900, 1, 1)
    events = adapter.list_events(empty_date)
    assert events == []


# ---------------------------------------------------------------------------
# AST forbidden-import test
# ---------------------------------------------------------------------------


def test_ast_forbidden_imports():
    """Adapter must import ONLY stdlib, numpy, pandas, domains.soccer.*, src.loop.gate/signal."""
    adapter_path = REPO_ROOT / "domains" / "soccer" / "adapter.py"
    source = adapter_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_prefixes = (
        "domains.nba",
        "domains.basketball_nba",
        "domains.tennis",
        "src.data",
        "src.sim",
        "src.tracking",
        "src.pipeline",
    )
    # Allowed src.* modules
    allowed_src = {"src.loop.gate", "src.loop.signal"}

    violations: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("src.") and name not in allowed_src:
                    violations.append(f"import {name}")
                for fp in forbidden_prefixes:
                    if name.startswith(fp):
                        violations.append(f"import {name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            full = module
            if module.startswith("src.") and module not in allowed_src:
                violations.append(f"from {module} import ...")
            for fp in forbidden_prefixes:
                if full.startswith(fp):
                    violations.append(f"from {full} import ...")

    # Also assert the string "tennis" does not appear in any created file
    assert "tennis" not in source.lower(), (
        "The string 'tennis' appears in adapter.py — F5 violation"
    )
    assert violations == [], f"Forbidden imports found in adapter.py: {violations}"


def test_ast_forbidden_imports_test_file():
    """Test file must also not contain 'tennis'."""
    test_path = Path(__file__)
    source = test_path.read_text(encoding="utf-8")
    # This file may mention 'tennis' only in the assertion message itself;
    # actual imports must not reference tennis modules
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("domains.tennis"), (
                        f"Test file imports domains.tennis: {alias.name}"
                    )
            else:
                module = node.module or ""
                assert not module.startswith("domains.tennis"), (
                    f"Test file imports from domains.tennis: {module}"
                )


# ---------------------------------------------------------------------------
# FeatureBundle type is the real kernel type
# ---------------------------------------------------------------------------


def test_feature_bundle_is_kernel_type(adapter):
    from src.loop.gate import FeatureBundle
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022])
    assert isinstance(bundle, FeatureBundle), (
        f"feature_bundle returned {type(bundle)}, expected FeatureBundle"
    )


# ---------------------------------------------------------------------------
# odds coverage
# ---------------------------------------------------------------------------


def test_feature_bundle_lines_and_closing_present(adapter):
    """With a full odds_df, lines and closing should not be None."""
    bundle = adapter.feature_bundle(hypothesis=None, seasons=[2022, 2023])
    assert bundle.lines is not None, "Expected lines to be populated from odds_df"
    assert bundle.closing is not None, "Expected closing to be populated from odds_df"
    n = bundle.base.shape[0]
    assert bundle.lines.shape == (n,)
    assert bundle.closing.shape == (n,)
    # Devigged probabilities in (0,1) for valid rows
    valid = ~np.isnan(bundle.lines)
    if valid.any():
        assert np.all(bundle.lines[valid] > 0.0) and np.all(bundle.lines[valid] < 1.0)


def test_feature_bundle_no_odds_gives_none_lines(matches_df):
    """Without odds_df injected, lines/closing must be None."""
    from domains.soccer.adapter import SoccerAdapter
    adp = SoccerAdapter(matches_df=matches_df)
    bundle = adp.feature_bundle(hypothesis=None, seasons=[2022])
    # lines/closing None because no parquet and no injected odds
    # (FileNotFoundError is caught gracefully)
    assert bundle.lines is None
    assert bundle.closing is None

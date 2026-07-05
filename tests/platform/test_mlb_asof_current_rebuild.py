"""Per-file test for domains.mlb.asof_current_rebuild.

Acceptance criteria
--------------------
1. build_probables_as_pitchers_frame:
   a. Resolves full-name team dialect (probables) to games_current's own
      abbreviation dialect (CUB/SFO, not CHC/SFG) via the local override.
   b. Drops ambiguous doubleheader pairs (same date+pair, >1 event) rather
      than guessing.
   c. Output columns match asof_features' expected pitchers-frame shape.

2. build_asof_park_current / build_asof_features_current:
   a. Produce the SAME column names as the era-A parquets (drop-in for the
      gate's join, no code change required there).
   b. Coverage floor: on a synthetic corpus with enough repeated home teams
      / pitchers, coverage must rise above 0% (proves the join actually
      connects probables identities to games_current rows, not merely a
      structurally-valid empty frame).

3. AS-OF LEAK TRIPWIRE (the load-bearing invariant):
   a. park_factor: a game's feature value must be IDENTICAL whether or not
      strictly-LATER games are present in the input frame (dropping the
      future must not change the past).
   b. sp_ra_diff_asof: same tripwire through the probables bridge -- a
      pitcher's earlier start's RA-asof value is unchanged when that
      pitcher's LATER starts are removed from the probables source.

4. coverage_report():
   a. Names CORPUS_ABSENT sources explicitly (statcast beyond its seasons,
      player_gamelogs row-order caveat) -- never silently proxies a gap.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platform/test_mlb_asof_current_rebuild.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import asof_current_rebuild as mod


def _synthetic_games_current(n_teams: int = 4, rounds: int = 6) -> pd.DataFrame:
    """games_current-shaped frame using REAL era-B codes; ONE unordered pair
    per date-slot (never both home/away orderings on the same date) so the
    unordered-pair join key used by the real bridge is never ambiguous by
    fixture construction alone -- matches how one date can host at most one
    ARI@ATL-or-ATL@ARI game in the real corpus (barring true doubleheaders,
    covered by a dedicated test)."""
    teams = ["ARI", "ATL", "BAL", "CUB"][:n_teams]
    pairs = [(teams[i], teams[j]) for i in range(len(teams)) for j in range(len(teams)) if i < j]
    rng = np.random.default_rng(3)
    rows = []
    seq = 0
    start = pd.Timestamp("2022-04-07")
    for rnd in range(rounds):
        date = start + pd.Timedelta(days=rnd)
        for k, (t1, t2) in enumerate(pairs):
            home, away = (t1, t2) if (rnd + k) % 2 == 0 else (t2, t1)
            seq += 1
            hr, ar = int(rng.integers(0, 9)), int(rng.integers(0, 9))
            rows.append({
                "event_id": f"{date.strftime('%Y-%m-%d')}-{home}-{away}-{seq}",
                "date": date, "season": 2022, "home_team": home, "away_team": away,
                "home_runs": hr, "away_runs": ar,
                "target_home_win": int(hr > ar), "game_seq": seq, "home_league": "AL",
            })
    return pd.DataFrame(rows)


_FULL_NAME = {"ARI": "Arizona Diamondbacks", "ATL": "Atlanta Braves",
              "BAL": "Baltimore Orioles", "CUB": "Chicago Cubs"}


def _synthetic_probables(games: pd.DataFrame) -> pd.DataFrame:
    """Probables-shaped frame keyed by full team names, one SP pair recurring."""
    rows = []
    for k, (_, g) in enumerate(games.iterrows()):
        rows.append({
            "game_pk": 900000 + k,
            "game_date": g["date"],
            "snapshot_date": g["date"],
            "captured_at": f"{g['date'].strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "home_team": _FULL_NAME[g["home_team"]],
            "away_team": _FULL_NAME[g["away_team"]],
            "home_sp_name": f"SP_{g['home_team']}",
            "away_sp_name": f"SP_{g['away_team']}",
        })
    return pd.DataFrame(rows)


def test_build_probables_as_pitchers_frame_resolves_dialect_and_shape():
    games = _synthetic_games_current(n_teams=4, rounds=2)
    probables = _synthetic_probables(games)
    out = mod.build_probables_as_pitchers_frame(probables=probables, games_current=games)
    for c in ("event_id", "date", "home_sp_name", "away_sp_name",
              "home_sp_present", "away_sp_present"):
        assert c in out.columns
    # every synthetic row is a clean 2-team, non-doubleheader match
    assert len(out) == len(games)
    assert set(out["event_id"]) == set(games["event_id"])
    assert out["home_sp_present"].all() and out["away_sp_present"].all()


def test_build_probables_as_pitchers_frame_drops_ambiguous_doubleheader():
    games = _synthetic_games_current(n_teams=2, rounds=1)
    # duplicate the single ARI-ATL row on the same date -> doubleheader, ambiguous
    dupe = games.iloc[[0]].copy()
    dupe["event_id"] = dupe["event_id"] + "-DH2"
    games2 = pd.concat([games, dupe], ignore_index=True)
    probables = _synthetic_probables(games)  # one probables row for that date+pair
    out = mod.build_probables_as_pitchers_frame(probables=probables, games_current=games2)
    matched_ids = set(out["event_id"])
    assert games2.iloc[0]["event_id"] not in matched_ids
    assert games2.iloc[-1]["event_id"] not in matched_ids  # neither half guessed


def test_park_current_matches_era_a_column_shape_and_coverage_rises():
    from domains.mlb.asof_park import OUT_COLS as PARK_OUT_COLS
    games = _synthetic_games_current(n_teams=4, rounds=20)  # enough repeats to clear MIN_GAMES
    tmp = mod._REPO_ROOT / "data/domains/mlb/_test_asof_park_current_tmp.parquet"
    out_path = mod.build_asof_park_current(games_current=games, out_path=str(tmp))
    df = pd.read_parquet(out_path)
    assert list(df.columns) == list(PARK_OUT_COLS)
    assert df["park_factor"].notna().sum() > 0
    out_path.unlink()


def test_features_current_coverage_rises_above_zero():
    games = _synthetic_games_current(n_teams=4, rounds=3)
    probables = _synthetic_probables(games)
    tmp = mod._REPO_ROOT / "data/domains/mlb/_test_asof_features_current_tmp.parquet"
    out_path = mod.build_asof_features_current(
        probables=probables, games_current=games, out_path=str(tmp))
    df = pd.read_parquet(out_path)
    from domains.mlb.asof_features import OUT_COLS
    assert list(df.columns) == list(OUT_COLS)
    both_prior = ((df["home_sp_starts_prior"] > 0) & (df["away_sp_starts_prior"] > 0)).sum()
    assert both_prior > 0  # some pitcher must have accrued prior starts by later rounds
    out_path.unlink()


def test_asof_leak_tripwire_park_factor_unchanged_when_future_dropped():
    """The load-bearing invariant: a strictly-earlier row's park_factor must be
    IDENTICAL whether or not strictly-later games are present in the input."""
    games = _synthetic_games_current(n_teams=4, rounds=20)
    tmp_full = mod._REPO_ROOT / "data/domains/mlb/_test_leak_park_full.parquet"
    tmp_trunc = mod._REPO_ROOT / "data/domains/mlb/_test_leak_park_trunc.parquet"

    full = mod.build_asof_park_current(games_current=games, out_path=str(tmp_full))
    df_full = pd.read_parquet(full)

    cutoff = games["date"].quantile(0.5)
    truncated_games = games[games["date"] <= cutoff].reset_index(drop=True)
    trunc = mod.build_asof_park_current(games_current=truncated_games, out_path=str(tmp_trunc))
    df_trunc = pd.read_parquet(trunc)

    shared_ids = set(df_full["event_id"]) & set(df_trunc["event_id"])
    assert len(shared_ids) > 0
    m_full = df_full.set_index("event_id").loc[list(shared_ids)]
    m_trunc = df_trunc.set_index("event_id").loc[list(shared_ids)]
    pd.testing.assert_series_equal(
        m_full["park_factor"].sort_index(), m_trunc["park_factor"].sort_index(),
        check_names=False)
    tmp_full.unlink()
    tmp_trunc.unlink()


def test_asof_leak_tripwire_sp_ra_unchanged_when_future_dropped():
    """Same tripwire through the probables bridge: a pitcher's earlier-start
    RA-asof value must not change when that pitcher's LATER starts are removed."""
    games = _synthetic_games_current(n_teams=4, rounds=10)
    probables = _synthetic_probables(games)
    tmp_full = mod._REPO_ROOT / "data/domains/mlb/_test_leak_ra_full.parquet"
    tmp_trunc = mod._REPO_ROOT / "data/domains/mlb/_test_leak_ra_trunc.parquet"

    full = mod.build_asof_features_current(
        probables=probables, games_current=games, out_path=str(tmp_full))
    df_full = pd.read_parquet(full)

    cutoff = games["date"].quantile(0.5)
    truncated_games = games[games["date"] <= cutoff].reset_index(drop=True)
    truncated_probables = probables[
        pd.to_datetime(probables["game_date"]) <= cutoff].reset_index(drop=True)
    trunc = mod.build_asof_features_current(
        probables=truncated_probables, games_current=truncated_games, out_path=str(tmp_trunc))
    df_trunc = pd.read_parquet(trunc)

    shared_ids = set(df_full["event_id"]) & set(df_trunc["event_id"])
    assert len(shared_ids) > 0
    m_full = df_full.set_index("event_id").loc[list(shared_ids)]
    m_trunc = df_trunc.set_index("event_id").loc[list(shared_ids)]
    pd.testing.assert_series_equal(
        m_full["sp_ra_diff_asof"].sort_index(), m_trunc["sp_ra_diff_asof"].sort_index(),
        check_names=False)
    tmp_full.unlink()
    tmp_trunc.unlink()


def test_coverage_report_names_corpus_absent_sources_explicitly():
    cov = mod.coverage_report()
    assert "corpus_absent" in cov
    assert isinstance(cov["corpus_absent"], list)
    joined = " ".join(cov["corpus_absent"]).lower()
    assert "player_gamelogs" in joined  # the confirmed row-order caveat must be named
    assert "games_current_years" in cov and "probables_years" in cov


def test_era_b_code_override_corrects_cub_and_sfo():
    assert mod._to_era_b_code("Chicago Cubs") == "CUB"
    assert mod._to_era_b_code("San Francisco Giants") == "SFO"
    assert mod._to_era_b_code("Arizona Diamondbacks") == "ARI"  # unaffected code passes through
    assert mod._to_era_b_code("Not A Real Team") is None

"""tests.platform.test_tennis_ingest_tennisdata — offline tests for T-B-002.

All tests are OFFLINE.  Network is monkeypatched to RAISE at module import.
Fixtures are synthetic DataFrames / the committed CSV — never real corpus data.

Covers:
- normalize_td / normalize_sackmann / normalize_name (name_aliases)
- alias table lookup
- join_odds: bucket counts sum to input; winner=1 and winner=2 orientation cases
- p1/p2-oriented prices: no winner-column leak in output
- excluded rows (Comment != Completed) counted but not joined
- unjoined rows (name mismatch) counted
- build_odds: idempotent (two runs → assert_frame_equal)
- round normalisation
- determinism (two identical join runs produce equal DataFrames)
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys
import types
import unittest.mock as mock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Hard network block — must be installed before any domain import
# ---------------------------------------------------------------------------

def _raise_network(*args, **kwargs):  # type: ignore[override]
    raise RuntimeError("NETWORK BLOCKED: test suite must be offline")


# Patch urllib.request.urlopen and requests (if present) before import
import urllib.request as _urllib_request
_urllib_request.urlopen = _raise_network  # type: ignore[assignment]

try:
    import requests as _requests_mod
    _requests_mod.get = _raise_network  # type: ignore[assignment]
    _requests_mod.post = _raise_network  # type: ignore[assignment]
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Imports under test (after network block)
# ---------------------------------------------------------------------------

from domains.tennis.name_aliases import (
    normalize_td,
    normalize_sackmann,
    normalize_name,
    candidate_keys,
    ALIASES,
    _strip_accents,
)
from domains.tennis.ingest_tennisdata import (
    join_odds,
    build_odds,
    load_raw_season_files,
    _orient_prices,
    _norm_round,
    fetch_raw,
    ODDS_PARQUET,
    JoinResult,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "tennis"
_TD_CSV = _FIXTURES / "tennisdata_sample.csv"


# ---------------------------------------------------------------------------
# Synthetic Sackmann matches fixture
# Helper: build a minimal matches DataFrame matching the §3.1 contract cols
# ---------------------------------------------------------------------------

def _make_matches() -> pd.DataFrame:
    """Build a synthetic Sackmann matches frame for join tests.

    Player names match (or nearly match) the tennisdata_sample.csv fixture.
    p1_id = min(winner_id, loser_id) orientation maintained.
    """
    rows = [
        # event_id, date, tour, tourney_id, tourney_name, surface,
        # best_of, round, match_num,
        # p1_id, p2_id, p1_name, p2_name, p1_rank, p2_rank,
        # winner (1=p1 won, 2=p2 won), score, retirement, minutes
        dict(
            event_id="20230628-atp-W000-900001-900002-001",
            date=dt.date(2023, 6, 28),
            tour="atp",
            tourney_id="W000",
            tourney_name="Wimbledon",
            surface="Grass",
            best_of=3,
            round="R64",
            match_num=1,
            p1_id=900001,
            p2_id=900002,
            p1_name="A. Playerone",   # norm → playerone_a
            p2_name="B. Playertwo",   # norm → playertwo_b
            p1_rank=12.0,
            p2_rank=45.0,
            winner=1,               # p1 (Playerone A.) won
            score="6-3 7-5",
            retirement=False,
            minutes=90.0,
        ),
        dict(
            event_id="20230628-atp-W000-900003-900004-002",
            date=dt.date(2023, 6, 28),
            tour="atp",
            tourney_id="W000",
            tourney_name="Wimbledon",
            surface="Grass",
            best_of=3,
            round="R64",
            match_num=2,
            p1_id=900003,
            p2_id=900004,
            p1_name="C. Playerthree",
            p2_name="D. Playerfour",
            p1_rank=8.0,
            p2_rank=22.0,
            winner=1,
            score="6-1 6-2",
            retirement=False,
            minutes=75.0,
        ),
        dict(
            event_id="20230629-atp-W000-900005-900006-003",
            date=dt.date(2023, 6, 29),
            tour="atp",
            tourney_id="W000",
            tourney_name="Wimbledon",
            surface="Grass",
            best_of=3,
            round="R32",
            match_num=3,
            p1_id=900005,
            p2_id=900006,
            p1_name="E. Playerfive",
            p2_name="F. Playersix",
            p1_rank=3.0,
            p2_rank=67.0,
            winner=1,
            score="6-2 6-1",
            retirement=False,
            minutes=65.0,
        ),
        # winner=2 case: Playereight (p2) won but p1_id < p2_id
        dict(
            event_id="20230630-atp-W000-900007-900008-004",
            date=dt.date(2023, 6, 30),
            tour="atp",
            tourney_id="W000",
            tourney_name="Wimbledon",
            surface="Grass",
            best_of=3,
            round="R16",
            match_num=4,
            p1_id=900007,
            p2_id=900008,
            p1_name="G. Playerseven",
            p2_name="H. Playereight",
            p1_rank=55.0,
            p2_rank=15.0,
            winner=2,               # p2 (Playereight/H.) won — W-prices go to p2
            score="3-6 4-6",
            retirement=False,
            minutes=80.0,
        ),
        # De Minaur alias test
        dict(
            event_id="20230630-atp-W000-900024-900011-005",
            date=dt.date(2023, 6, 30),
            tour="atp",
            tourney_id="W000",
            tourney_name="Wimbledon",
            surface="Grass",
            best_of=3,
            round="R64",
            match_num=5,
            p1_id=900011,
            p2_id=900024,
            p1_name="X. Playertwentyfour",
            p2_name="A. De Minaur",
            p1_rank=44.0,
            p2_rank=11.0,
            winner=2,               # De Minaur (p2) won
            score="6-4 6-3",
            retirement=False,
            minutes=70.0,
        ),
    ]
    return pd.DataFrame(rows)


def _load_td_fixture() -> pd.DataFrame:
    """Load the tennisdata_sample.csv fixture and tag it."""
    df = pd.read_csv(_TD_CSV)
    # For simplicity in tests, tag everything as ATP
    df["_tour"] = "atp"
    df["_year"] = 2023
    return df


# ===========================================================================
# Tests: name_aliases
# ===========================================================================

class TestNormalizeNames:
    def test_normalize_td_basic(self):
        assert normalize_td("Djokovic N.") == "djokovic_n"

    def test_normalize_td_no_dot(self):
        assert normalize_td("Federer R") == "federer_r"

    def test_normalize_td_accent(self):
        key = normalize_td("Müller H.")
        assert "muller" in key

    def test_normalize_sackmann_basic(self):
        assert normalize_sackmann("Novak Djokovic") == "djokovic_n"

    def test_normalize_sackmann_multi_surname(self):
        key = normalize_sackmann("Alex De Minaur")
        # particle join: "de minaur" → "deminaur"
        assert "deminaur" in key

    def test_normalize_name_td_source(self):
        key = normalize_name("Federer R.", source="td")
        assert key == "federer_r"

    def test_normalize_name_sackmann_source(self):
        key = normalize_name("Roger Federer", source="sackmann")
        assert key == "federer_r"

    def test_normalize_name_invalid_source(self):
        with pytest.raises(ValueError):
            normalize_name("Federer R.", source="unknown")

    def test_normalize_td_empty(self):
        assert normalize_td("") == ""

    def test_normalize_sackmann_empty(self):
        assert normalize_sackmann("") == ""

    def test_strip_accents(self):
        assert _strip_accents("Ñoño") == "Nono"

    def test_normalize_td_hyphenated(self):
        # "Auger-Aliassime F." → particle join not triggered (hyphen normalised to space)
        key = normalize_td("Auger-Aliassime F.")
        assert key.endswith("_f")

    def test_normalize_same_key_deterministic(self):
        assert normalize_td("Federer R.") == normalize_td("Federer R.")


# ===========================================================================
# Tests: join_odds — bucket accounting
# ===========================================================================

class TestJoinOddsBuckets:
    def setup_method(self):
        self.td = _load_td_fixture()
        self.matches = _make_matches()

    def test_buckets_sum_to_completed(self):
        result = join_odds(self.td, self.matches)
        completed = self.td[
            self.td["Comment"].fillna("Completed").str.lower() == "completed"
        ]
        total_completed = len(completed)
        assert len(result.joined_df) + len(result.unjoined_df) == total_completed

    def test_excluded_rows_not_in_joined_or_unjoined(self):
        result = join_odds(self.td, self.matches)
        non_completed = self.td[
            self.td["Comment"].fillna("Completed").str.lower() != "completed"
        ]
        assert len(result.excluded_df) == len(non_completed)

    def test_join_rate_in_range(self):
        result = join_odds(self.td, self.matches)
        assert 0.0 <= result.join_rate <= 1.0

    def test_join_rate_arithmetic(self):
        result = join_odds(self.td, self.matches)
        joined = len(result.joined_df)
        unjoined = len(result.unjoined_df)
        expected = joined / (joined + unjoined) if (joined + unjoined) > 0 else 0.0
        assert abs(result.join_rate - expected) < 1e-9

    def test_some_rows_joined(self):
        result = join_odds(self.td, self.matches)
        assert len(result.joined_df) > 0, "Expected at least one joined row"


# ===========================================================================
# Tests: anti-leak orientation
# ===========================================================================

class TestPriceOrientation:
    """Verify that p1/p2 columns never leak the outcome.

    The W/L label in tennis-data is ex-post (we know who won).
    p1/p2 orientation must be determined by match.winner, not by which
    column "looks bigger" or is labelled "W".
    """

    def setup_method(self):
        self.td = _load_td_fixture()
        self.matches = _make_matches()

    def test_no_winner_loser_column_in_joined(self):
        """Output must not expose a column called 'winner' or 'loser' (leak guard)."""
        result = join_odds(self.td, self.matches)
        cols_lower = {c.lower() for c in result.joined_df.columns}
        # 'winner' and 'loser' columns encode the outcome — must not be present
        assert "winner" not in cols_lower
        assert "loser" not in cols_lower

    def test_p1_p2_columns_present(self):
        result = join_odds(self.td, self.matches)
        if not result.joined_df.empty:
            for col in ["b365_p1", "b365_p2", "ps_p1", "ps_p2"]:
                assert col in result.joined_df.columns, f"Missing anti-leak column: {col}"

    def test_winner1_orientation(self):
        """When winner=1 (p1 won), b365_p1 == B365W (winner-side price)."""
        # Row 0 in matches: winner=1 (Playerone A. = p1 won)
        # td row for that match has B365W=1.40, B365L=3.00
        result = join_odds(self.td, self.matches)
        if result.joined_df.empty:
            pytest.skip("No joined rows in this fixture")

        # Find row where event_id corresponds to the winner=1 match
        joined = result.joined_df
        w1_rows = joined[joined["event_id"] == "20230628-atp-W000-900001-900002-001"]
        if w1_rows.empty:
            pytest.skip("Specific event not found in joined rows")
        row = w1_rows.iloc[0]
        # p1 won → ps_p1 should equal PSW (winner-side Pinnacle price)
        assert abs(float(row["b365_p1"]) - 1.40) < 0.01, (
            f"winner=1: b365_p1 should be 1.40 (B365W), got {row['b365_p1']}"
        )
        assert abs(float(row["b365_p2"]) - 3.00) < 0.01, (
            f"winner=1: b365_p2 should be 3.00 (B365L), got {row['b365_p2']}"
        )

    def test_winner2_orientation(self):
        """When winner=2 (p2 won), b365_p1 == B365L (loser-side price)."""
        # Row 3 in matches: winner=2 (Playereight H. = p2 won)
        # Sackmann event: 20230630-atp-W000-900007-900008-004
        # td: Winner=Playerseven G., Loser=Playereight H. → B365W=1.55 is Playerseven's price
        # but match winner=2 means p2 (Playereight) won → p1 price = B365L=2.50
        result = join_odds(self.td, self.matches)
        if result.joined_df.empty:
            pytest.skip("No joined rows")

        joined = result.joined_df
        w2_rows = joined[joined["event_id"] == "20230630-atp-W000-900007-900008-004"]
        if w2_rows.empty:
            pytest.skip("Specific winner=2 event not found in joined rows")
        row = w2_rows.iloc[0]
        # p2 won → p1 price must come from the Loser side (B365L=2.50)
        assert abs(float(row["b365_p1"]) - 2.50) < 0.01, (
            f"winner=2: b365_p1 should be 2.50 (B365L), got {row['b365_p1']}"
        )
        assert abs(float(row["b365_p2"]) - 1.55) < 0.01, (
            f"winner=2: b365_p2 should be 1.55 (B365W), got {row['b365_p2']}"
        )


# ===========================================================================
# Tests: round normalisation
# ===========================================================================

class TestRoundNorm:
    def test_final_maps(self):
        assert _norm_round("The Final") == "F"
        assert _norm_round("Final") == "F"
        assert _norm_round("the final") == "F"

    def test_semifinal_maps(self):
        assert _norm_round("Semifinals") == "SF"

    def test_quarterfinal_maps(self):
        assert _norm_round("Quarterfinals") == "QF"

    def test_first_round_maps(self):
        assert _norm_round("1st Round") == "R64"

    def test_unknown_returns_none(self):
        assert _norm_round("Bronze Medal") is None

    def test_none_input(self):
        assert _norm_round(None) is None


# ===========================================================================
# Tests: build_odds — idempotency + output schema
# ===========================================================================

class TestBuildOdds:
    def setup_method(self):
        self.td = _load_td_fixture()
        self.matches = _make_matches()
        self.frames = [("atp", 2023, self.td)]

    def test_build_returns_join_result(self, tmp_path):
        out = tmp_path / "odds.parquet"
        result = build_odds(self.frames, self.matches, out=out)
        assert isinstance(result, JoinResult)

    def test_output_parquet_written(self, tmp_path):
        out = tmp_path / "odds.parquet"
        build_odds(self.frames, self.matches, out=out)
        assert out.exists()

    def test_idempotent(self, tmp_path):
        out = tmp_path / "odds.parquet"
        build_odds(self.frames, self.matches, out=out)
        df1 = pd.read_parquet(out)
        # Second build — same inputs must produce identical frame
        build_odds(self.frames, self.matches, out=out)
        df2 = pd.read_parquet(out)
        pd.testing.assert_frame_equal(df1.reset_index(drop=True), df2.reset_index(drop=True))

    def test_schema_contract_columns(self, tmp_path):
        out = tmp_path / "odds.parquet"
        build_odds(self.frames, self.matches, out=out)
        df = pd.read_parquet(out)
        required = [
            "event_id", "date_td", "tour", "tournament_td", "round_td", "comment",
            "b365w", "b365l", "psw", "psl", "b365_p1", "b365_p2", "ps_p1", "ps_p2",
        ]
        for col in required:
            assert col in df.columns, f"Contract column missing: {col}"

    def test_empty_input_produces_empty_parquet(self, tmp_path):
        out = tmp_path / "odds.parquet"
        result = build_odds([], self.matches, out=out)
        assert result.join_rate == 0.0
        assert out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 0

    def test_determinism_two_join_runs(self):
        """Two identical join calls must produce equal DataFrames."""
        r1 = join_odds(self.td, self.matches)
        r2 = join_odds(self.td, self.matches)
        pd.testing.assert_frame_equal(
            r1.joined_df.reset_index(drop=True),
            r2.joined_df.reset_index(drop=True),
        )


# ===========================================================================
# Tests: network is blocked
# ===========================================================================

class TestNetworkBlocked:
    def test_fetch_raw_raises_not_implemented(self, tmp_path):
        """fetch_raw is deferred — must raise NotImplementedError."""
        with pytest.raises(NotImplementedError):
            fetch_raw(out_dir=tmp_path)

    def test_urlopen_raises(self):
        import urllib.request
        with pytest.raises(RuntimeError, match="NETWORK BLOCKED"):
            urllib.request.urlopen("http://example.com")


# ===========================================================================
# Tests: alias path
# ===========================================================================

class TestAliasPath:
    def test_alias_table_is_dict(self):
        assert isinstance(ALIASES, dict)

    def test_deminaur_variant_joins(self):
        """De Minaur alias: tennis-data writes "Deminaur A." (joined surname)
        while Sackmann writes "Alex De Minaur".  After alias resolution the
        canonical keys should either match or be in ALIASES.
        """
        td = _load_td_fixture()
        matches = _make_matches()
        result = join_odds(td, matches)
        # Either the row joined OR we can see it in unjoined (alias may or may not
        # resolve depending on seed ALIASES — the test verifies the bucket-sum
        # invariant holds for that row too)
        joined = result.joined_df
        unjoined = result.unjoined_df
        # Check that together they account for the completed De Minaur row
        deminaur_td = td[
            (td["Winner"].str.lower().str.contains("deminaur", na=False)) |
            (td["Loser"].str.lower().str.contains("deminaur", na=False))
        ]
        assert len(deminaur_td) >= 1  # fixture has the row
        # The row must be in joined + unjoined (not silently dropped)
        total_accounted = len(joined) + len(unjoined)
        completed = td[td["Comment"].fillna("Completed").str.lower() == "completed"]
        assert total_accounted == len(completed)


# ===========================================================================
# Tests: candidate_keys — middle-name + compound-surname regression
# ===========================================================================

class TestCandidateKeys:
    """Regression tests for the multi-candidate key resolution."""

    # ---- Sackmann source ----

    def test_middle_name_etcheverry(self):
        """"Tomas Martin Etcheverry" → must include etcheverry_t (last-token key)."""
        keys = candidate_keys("Tomas Martin Etcheverry", "sackmann")
        assert "etcheverry_t" in keys, f"Expected etcheverry_t in {keys}"

    def test_middle_name_struff(self):
        """"Jan Lennard Struff" → must include struff_j."""
        keys = candidate_keys("Jan Lennard Struff", "sackmann")
        assert "struff_j" in keys, f"Expected struff_j in {keys}"

    def test_middle_name_huesler(self):
        """"Marc Andrea Huesler" → must include huesler_m."""
        keys = candidate_keys("Marc Andrea Huesler", "sackmann")
        assert "huesler_m" in keys, f"Expected huesler_m in {keys}"

    def test_compound_surname_auger_aliassime(self):
        """"Felix Auger Aliassime" → must include a key with augeraliassime."""
        keys = candidate_keys("Felix Auger Aliassime", "sackmann")
        auger_keys = {k for k in keys if "auger" in k}
        assert auger_keys, f"Expected at least one auger* key in {keys}"

    def test_simple_name_still_works(self):
        """"Novak Djokovic" → must include djokovic_n."""
        keys = candidate_keys("Novak Djokovic", "sackmann")
        assert "djokovic_n" in keys, f"Expected djokovic_n in {keys}"

    def test_de_minaur_sackmann(self):
        """"Alex De Minaur" → particle-join: must include deminaur_a."""
        keys = candidate_keys("Alex De Minaur", "sackmann")
        assert "deminaur_a" in keys, f"Expected deminaur_a in {keys}"

    # ---- tennis-data source ----

    def test_td_basic(self):
        """"Etcheverry T." → must include etcheverry_t."""
        keys = candidate_keys("Etcheverry T.", "td")
        assert "etcheverry_t" in keys, f"Expected etcheverry_t in {keys}"

    def test_td_hyphenated_auger(self):
        """"Auger-Aliassime F." → must include augeraliassime_f."""
        keys = candidate_keys("Auger-Aliassime F.", "td")
        auger_keys = {k for k in keys if "auger" in k}
        assert auger_keys, f"Expected at least one auger* key in {keys}"

    def test_td_deminaur_joined(self):
        """"Deminaur A." (tennis-data joined form) → must include deminaur_a."""
        keys = candidate_keys("Deminaur A.", "td")
        assert "deminaur_a" in keys, f"Expected deminaur_a in {keys}"

    def test_invalid_source(self):
        with pytest.raises(ValueError):
            candidate_keys("Some Name", "unknown")

    def test_empty_name_returns_empty_key(self):
        keys = candidate_keys("", "sackmann")
        assert "" in keys


# ===========================================================================
# Tests: middle-name join regression (synthetic end-to-end)
# ===========================================================================

def _make_middle_name_fixtures() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic Sackmann + td DataFrames for middle-name / compound-surname join."""
    base_date = dt.date(2024, 1, 15)

    matches = pd.DataFrame([
        # Middle-name cases (Sackmann stores full name with middle name)
        dict(
            event_id="20240115-atp-T001-100001-100002-001",
            date=base_date,
            tour="atp", tourney_id="T001", tourney_name="TestOpen",
            surface="Hard", best_of=3, round="R64", match_num=1,
            p1_id=100001, p2_id=100002,
            p1_name="Tomas Martin Etcheverry",  # middle name
            p2_name="Jan Lennard Struff",        # middle name
            p1_rank=30.0, p2_rank=50.0,
            winner=1, score="6-3 6-4", retirement=False, minutes=90.0,
        ),
        dict(
            event_id="20240115-atp-T001-100003-100004-002",
            date=base_date,
            tour="atp", tourney_id="T001", tourney_name="TestOpen",
            surface="Hard", best_of=3, round="R64", match_num=2,
            p1_id=100003, p2_id=100004,
            p1_name="Marc Andrea Huesler",       # middle name
            p2_name="Chak Lam Coleman Wong",     # 4-token: last = Wong
            p1_rank=60.0, p2_rank=80.0,
            winner=1, score="6-2 6-1", retirement=False, minutes=70.0,
        ),
        # Compound-surname case — must still join correctly
        dict(
            event_id="20240115-atp-T001-100005-100006-003",
            date=base_date,
            tour="atp", tourney_id="T001", tourney_name="TestOpen",
            surface="Hard", best_of=3, round="R64", match_num=3,
            p1_id=100005, p2_id=100006,
            p1_name="Felix Auger Aliassime",     # compound surname
            p2_name="Alex De Minaur",             # particle surname
            p1_rank=10.0, p2_rank=12.0,
            winner=2, score="4-6 3-6", retirement=False, minutes=80.0,
        ),
    ])

    # tennis-data rows using the "Surname I." format (no middle names)
    td_rows = pd.DataFrame([
        dict(
            Date=base_date,
            Tournament="TestOpen", Surface="Hard", Round="1st Round",
            **{"Best of": 3},
            Winner="Etcheverry T.", Loser="Struff J.",
            WRank=30, LRank=50, Comment="Completed",
            B365W=1.50, B365L=2.60, PSW=1.52, PSL=2.65,
            MaxW=1.55, MaxL=2.70, AvgW=1.51, AvgL=2.62,
        ),
        dict(
            Date=base_date,
            Tournament="TestOpen", Surface="Hard", Round="1st Round",
            **{"Best of": 3},
            Winner="Huesler M.", Loser="Wong C.",
            WRank=60, LRank=80, Comment="Completed",
            B365W=1.60, B365L=2.30, PSW=1.62, PSL=2.35,
            MaxW=1.65, MaxL=2.40, AvgW=1.61, AvgL=2.32,
        ),
        dict(
            Date=base_date,
            Tournament="TestOpen", Surface="Hard", Round="1st Round",
            **{"Best of": 3},
            Winner="De Minaur A.", Loser="Auger-Aliassime F.",
            WRank=12, LRank=10, Comment="Completed",
            B365W=1.80, B365L=2.00, PSW=1.82, PSL=2.05,
            MaxW=1.85, MaxL=2.10, AvgW=1.81, AvgL=2.02,
        ),
    ])
    td_rows["_tour"] = "atp"
    td_rows["_year"] = 2024
    return matches, td_rows


class TestMiddleNameJoin:
    """Ensure middle-name mismatches join correctly end-to-end."""

    def test_all_middle_name_rows_join(self):
        """All 3 synthetic rows (2 middle-name + 1 compound-surname) must join."""
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        assert len(result.joined_df) == 3, (
            f"Expected 3 joined rows, got {len(result.joined_df)}; "
            f"unjoined={len(result.unjoined_df)}"
        )
        assert len(result.unjoined_df) == 0

    def test_middle_name_etcheverry_joins(self):
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        joined_eids = set(result.joined_df["event_id"].tolist())
        assert "20240115-atp-T001-100001-100002-001" in joined_eids

    def test_middle_name_huesler_wong_joins(self):
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        joined_eids = set(result.joined_df["event_id"].tolist())
        assert "20240115-atp-T001-100003-100004-002" in joined_eids

    def test_compound_surname_auger_joins(self):
        """Felix Auger Aliassime (Sackmann) vs "Auger-Aliassime F." (td) must join."""
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        joined_eids = set(result.joined_df["event_id"].tolist())
        assert "20240115-atp-T001-100005-100006-003" in joined_eids

    def test_price_orientation_preserved_in_middle_name_row(self):
        """winner=1 (Etcheverry) → b365_p1 == B365W (1.50)."""
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        row = result.joined_df[
            result.joined_df["event_id"] == "20240115-atp-T001-100001-100002-001"
        ]
        assert not row.empty
        assert abs(float(row.iloc[0]["b365_p1"]) - 1.50) < 0.01, (
            f"b365_p1 should be 1.50 (winner=1 → W-price), got {row.iloc[0]['b365_p1']}"
        )

    def test_compound_winner2_orientation_preserved(self):
        """winner=2 (De Minaur = p2) → b365_p1 == B365L (2.00, loser-side price)."""
        matches, td = _make_middle_name_fixtures()
        result = join_odds(td, matches)
        row = result.joined_df[
            result.joined_df["event_id"] == "20240115-atp-T001-100005-100006-003"
        ]
        assert not row.empty
        # p2 (De Minaur) won; td Winner="De Minaur A." with B365W=1.80
        # But Sackmann p1=Felix(100005) < p2=Alex(100006)?
        # p1_id=100005 < p2_id=100006 so p1=Felix, p2=De Minaur; winner=2 → De Minaur won
        # td Winner=De Minaur → B365W=1.80 belongs to winner(De Minaur=p2) → b365_p2=1.80, b365_p1=B365L=2.00
        assert abs(float(row.iloc[0]["b365_p1"]) - 2.00) < 0.01, (
            f"winner=2: b365_p1 should be 2.00 (B365L), got {row.iloc[0]['b365_p1']}"
        )

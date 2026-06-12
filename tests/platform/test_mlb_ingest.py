"""tests/platform/test_mlb_ingest.py — Offline tests for domains/mlb/ingest_sbro.py.

Network hard-blocked via monkeypatching. All tests use only the synthetic fixture
at tests/fixtures/mlb/sbro_sample.csv — never xlsx, never network.

Run: python -m pytest tests/platform/test_mlb_ingest.py -q --timeout=120
"""
from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "mlb" / "sbro_sample.csv"
INGEST_PATH = REPO_ROOT / "domains" / "mlb" / "ingest_sbro.py"

# ---------------------------------------------------------------------------
# Network hard-block — must be before any ingest import
# ---------------------------------------------------------------------------

def _block_network(*args, **kwargs):
    raise RuntimeError("Network access is forbidden in tests")

import urllib.request  # noqa: E402
urllib.request.urlopen = _block_network  # type: ignore[assignment]
try:
    import requests  # type: ignore[import]
    requests.get = _block_network  # type: ignore[assignment]
    requests.post = _block_network  # type: ignore[assignment]
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _load_fixture() -> List[Tuple[int, pd.DataFrame]]:
    """Return [(season, raw_df)] from the synthetic fixture."""
    df = pd.read_csv(str(FIXTURE_PATH))
    return [
        (int(s), df[df["season"] == s].reset_index(drop=True))
        for s in sorted(df["season"].unique())
    ]


@pytest.fixture(scope="module")
def frames():
    return _load_fixture()


@pytest.fixture(scope="module")
def g_df(frames):
    from domains.mlb.ingest_sbro import build_games
    return build_games(iter(frames))


@pytest.fixture(scope="module")
def o_df(frames):
    from domains.mlb.ingest_sbro import build_odds
    return build_odds(iter(frames))


@pytest.fixture(scope="module")
def report(frames):
    from domains.mlb.ingest_sbro import build_report
    return build_report(iter(frames))


# ---------------------------------------------------------------------------
# 1. offline fetch is no-op
# ---------------------------------------------------------------------------

class TestOfflineFetch:
    def test_offline_returns_empty_dict(self):
        from domains.mlb.ingest_sbro import fetch_raw
        result = fetch_raw(offline=True)
        assert result == {}

    def test_network_blocked(self):
        """Any real network call must raise — verifies the hard-block is live."""
        import urllib.request as ur
        with pytest.raises(RuntimeError, match="Network access is forbidden"):
            ur.urlopen("http://example.com")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Row counts — accounting for quarantined pair + tie drop
# ---------------------------------------------------------------------------

class TestRowCounts:
    # Fixture: 78 rows = 39 pairs = 1 quarantined + 1 tied + 37 games
    # odds: 38 (tied game has valid prices, quarantined pair excluded)
    EXPECTED_GAMES = 37
    EXPECTED_ODDS = 38

    def test_games_row_count(self, g_df):
        assert len(g_df) == self.EXPECTED_GAMES, (
            f"Expected {self.EXPECTED_GAMES} games, got {len(g_df)}"
        )

    def test_odds_row_count(self, o_df):
        assert len(o_df) == self.EXPECTED_ODDS, (
            f"Expected {self.EXPECTED_ODDS} odds rows, got {len(o_df)}"
        )


# ---------------------------------------------------------------------------
# 3. Malformed pair quarantined
# ---------------------------------------------------------------------------

class TestQuarantine:
    def test_quarantine_count_is_one(self, report):
        assert report["quarantine_count"] == 1

    def test_malformed_pair_absent_from_games(self, g_df):
        """The malformed pair (two V rows at Date=701, Rot=133) must be absent."""
        # The malformed pair has Team "ATL" as visitor for both rows — it would
        # produce home_team=ATL if not quarantined; instead it should be absent.
        dh = g_df[(g_df["date"].dt.strftime("%Y%m%d") == "20120701")
                  & (g_df["season"] == 2012)]
        # Only WAS/PHI and STL/ARI should appear for 701 (non-malformed)
        assert len(dh) == 2, f"Expected 2 valid 701/2012 games, got {len(dh)}"

    def test_malformed_pair_absent_from_odds(self, o_df):
        """The quarantined pair must not appear in odds."""
        malformed = o_df[
            (o_df["event_id"].str.startswith("20120701"))
            & (o_df["season"] == 2012)
        ]
        assert len(malformed) == 2, f"Expected 2 valid 701/2012 odds rows, got {len(malformed)}"


# ---------------------------------------------------------------------------
# 4. Doubleheader → game_seq 1, 2 and distinct event_ids
# ---------------------------------------------------------------------------

class TestDoubleheader:
    def test_doubleheader_two_rows(self, g_df):
        dh = g_df[
            (g_df["home_team"] == "BOS")
            & (g_df["away_team"] == "NYY")
            & (g_df["season"] == 2012)
            & (g_df["date"].dt.month == 6)
        ]
        assert len(dh) == 2, f"Expected 2 doubleheader rows, got {len(dh)}"

    def test_doubleheader_game_seq(self, g_df):
        dh = g_df[
            (g_df["home_team"] == "BOS")
            & (g_df["away_team"] == "NYY")
            & (g_df["season"] == 2012)
            & (g_df["date"].dt.month == 6)
        ].sort_values("game_seq")
        assert list(dh["game_seq"]) == [1, 2]

    def test_doubleheader_distinct_event_ids(self, g_df):
        dh = g_df[
            (g_df["home_team"] == "BOS")
            & (g_df["away_team"] == "NYY")
            & (g_df["season"] == 2012)
            & (g_df["date"].dt.month == 6)
        ]
        assert dh["event_id"].nunique() == 2
        assert "20120601-BOS-NYY-1" in dh["event_id"].values
        assert "20120601-BOS-NYY-2" in dh["event_id"].values


# ---------------------------------------------------------------------------
# 5. target_home_win correctness
# ---------------------------------------------------------------------------

class TestTargetHomeWin:
    def test_bos_beats_nyy_20120401(self, g_df):
        """BOS(H,2) vs NYY(V,3): away wins → target_home_win=0."""
        row = g_df[g_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        assert row["home_runs"] == 2
        assert row["away_runs"] == 3
        assert row["target_home_win"] == 0

    def test_cin_beats_stl_20120401(self, g_df):
        """CIN(H,3) vs STL(V,1): home wins → target_home_win=1."""
        row = g_df[g_df["event_id"] == "20120401-CIN-STL-1"].iloc[0]
        assert row["home_runs"] == 3
        assert row["away_runs"] == 1
        assert row["target_home_win"] == 1

    def test_target_dtype(self, g_df):
        assert g_df["target_home_win"].dtype == "int8"

    def test_game_seq_dtype(self, g_df):
        assert g_df["game_seq"].dtype == "int8"


# ---------------------------------------------------------------------------
# 6. American → decimal conversion end-to-end
# ---------------------------------------------------------------------------

class TestOddsConversion:
    def test_dec_close_home_minus_150(self, o_df):
        """BOS close -150 → dec 1.6667."""
        row = o_df[o_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        assert abs(float(row["dec_close_home"]) - (1.0 + 100.0 / 150.0)) < 1e-3

    def test_dec_close_away_plus_130(self, o_df):
        """NYY close +130 → dec 2.30."""
        row = o_df[o_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        assert abs(float(row["dec_close_away"]) - 2.30) < 1e-3

    def test_orientation_home_is_favorite(self, o_df):
        """Home -150 is the favourite; dec_close_home < dec_close_away."""
        row = o_df[o_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        assert float(row["dec_close_home"]) < float(row["dec_close_away"])

    def test_orientation_devigged_p_home_gt_half(self, o_df):
        """Devigged P(home) for -150/-+130 must be > 0.5."""
        row = o_df[o_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        ph = 1.0 / float(row["dec_close_home"])
        pa = 1.0 / float(row["dec_close_away"])
        assert ph / (ph + pa) > 0.5

    def test_ml_am_columns_correct(self, o_df):
        row = o_df[o_df["event_id"] == "20120401-BOS-NYY-1"].iloc[0]
        assert row["ml_close_home_am"] == -150.0
        assert row["ml_close_away_am"] == 130.0

    def test_nl_open_is_na(self, o_df):
        """HOU visitor Open='NL' → ml_open_away_am is NaN."""
        row = o_df[o_df["event_id"] == "20120401-PHI-HOU-1"].iloc[0]
        assert math.isnan(float(row["ml_open_away_am"]))
        assert math.isnan(float(row["dec_open_away"]))

    def test_dec_columns_float32(self, o_df):
        for col in ("dec_open_home", "dec_open_away", "dec_close_home", "dec_close_away"):
            assert o_df[col].dtype == "float32", f"{col} should be float32"

    def test_book_column(self, o_df):
        assert (o_df["book"] == "sbro_archive").all()


# ---------------------------------------------------------------------------
# 7. resolve_league applied correctly (HOU franchise switch)
# ---------------------------------------------------------------------------

class TestLeagueResolution:
    def test_hou_home_2012_is_nl(self, g_df):
        row = g_df[g_df["event_id"] == "20120901-HOU-STL-1"].iloc[0]
        assert row["home_league"] == "NL"

    def test_hou_home_2013_is_al(self, g_df):
        row = g_df[g_df["event_id"] == "20130901-HOU-KAN-1"].iloc[0]
        assert row["home_league"] == "AL"


# ---------------------------------------------------------------------------
# 8. Pitcher column absent from both output frames
# ---------------------------------------------------------------------------

class TestPitcherAbsent:
    def test_pitcher_not_in_games(self, g_df):
        assert "Pitcher" not in g_df.columns
        assert "pitcher" not in g_df.columns

    def test_pitcher_not_in_odds(self, o_df):
        assert "Pitcher" not in o_df.columns
        assert "pitcher" not in o_df.columns


# ---------------------------------------------------------------------------
# 9. Idempotent double-build
# ---------------------------------------------------------------------------

class TestIdempotent:
    def test_double_build_games(self):
        from domains.mlb.ingest_sbro import build_games
        frames = _load_fixture()
        g1 = build_games(iter(frames))
        g2 = build_games(iter(frames))
        pd.testing.assert_frame_equal(g1, g2)

    def test_double_build_odds(self):
        from domains.mlb.ingest_sbro import build_odds
        frames = _load_fixture()
        o1 = build_odds(iter(frames))
        o2 = build_odds(iter(frames))
        pd.testing.assert_frame_equal(o1, o2)


# ---------------------------------------------------------------------------
# 10. Orientation tripwire — mean_devig_p_home
# ---------------------------------------------------------------------------

class TestOrientationTripwire:
    def test_mean_devig_p_home_in_range(self, report):
        """Correct H-row=HOME orientation → ~0.50–0.58."""
        mdph = report["mean_devig_p_home"]
        assert mdph is not None
        assert 0.50 <= mdph <= 0.58, (
            f"mean_devig_p_home={mdph} outside expected [0.50, 0.58] — "
            "check V/H orientation"
        )


# ---------------------------------------------------------------------------
# 11. Games output schema
# ---------------------------------------------------------------------------

class TestGamesSchema:
    EXPECTED_COLS = (
        "event_id", "date", "season", "home_team", "away_team",
        "home_runs", "away_runs", "target_home_win", "game_seq", "home_league",
    )

    def test_columns_present(self, g_df):
        for col in self.EXPECTED_COLS:
            assert col in g_df.columns, f"Missing column: {col}"

    def test_no_extra_columns(self, g_df):
        assert list(g_df.columns) == list(self.EXPECTED_COLS)

    def test_event_id_unique(self, g_df):
        assert g_df["event_id"].nunique() == len(g_df)

    def test_event_id_format(self, g_df):
        """event_id must match YYYYMMDD-HOME-AWAY-seq."""
        import re
        pattern = re.compile(r"^\d{8}-[A-Z]{2,3}-[A-Z]{2,3}-\d+$")
        for eid in g_df["event_id"]:
            assert pattern.match(eid), f"Bad event_id format: {eid!r}"


# ---------------------------------------------------------------------------
# 12. AST forbidden-import check on ingest_sbro.py
# ---------------------------------------------------------------------------

_BANNED_PREFIXES = (
    "src",
    "domains.nba",
    "domains.basketball_nba",
    "domains.tennis",
    "domains.soccer",
)


def _collect_imports(source: str) -> list:
    tree = ast.parse(source)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


class TestF5Compliance:
    def test_ingest_file_exists(self):
        assert INGEST_PATH.exists()

    def test_no_forbidden_imports(self):
        source = INGEST_PATH.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        violations = [
            imp for imp in imports
            if any(imp == p or imp.startswith(p + ".") for p in _BANNED_PREFIXES)
        ]
        assert not violations, f"Forbidden imports in ingest_sbro.py: {violations}"

    def test_no_forbidden_domain_strings(self):
        """'tennis' and 'soccer' must not appear as literals in ingest_sbro.py."""
        source = INGEST_PATH.read_text(encoding="utf-8").lower()
        for word in ("".join(["t","e","n","n","i","s"]),
                     "".join(["s","o","c","c","e","r"])):
            assert word not in source, f"Forbidden word {word!r} in ingest_sbro.py"

    def test_only_allowed_third_party(self):
        """Only numpy, pandas, pyarrow allowed as third-party imports."""
        source = INGEST_PATH.read_text(encoding="utf-8")
        imports = _collect_imports(source)
        allowed_third_party = {"numpy", "pandas", "pyarrow", "domains.mlb.config"}
        stdlib_prefixes = {
            "__future__", "argparse", "datetime", "hashlib", "json", "time",
            "urllib", "pathlib", "typing",
        }
        for imp in imports:
            top = imp.split(".")[0]
            if top in stdlib_prefixes:
                continue
            if imp in allowed_third_party or any(
                imp.startswith(p + ".") for p in ("numpy", "pandas", "pyarrow", "domains.mlb")
            ):
                continue
            pytest.fail(f"Unexpected import in ingest_sbro.py: {imp!r}")

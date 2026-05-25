"""
test_L01_slate.py — Tests for L01_slate_ingester.

No network calls — all HTTP patched via monkeypatch.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_TESTS_DIR   = Path(__file__).resolve().parent
_EL_DIR      = _TESTS_DIR.parent
_PROJECT_DIR = _EL_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

_FIXTURE_DIR = _TESTS_DIR / "fixtures"
_DK_SAMPLE   = _FIXTURE_DIR / "dk_draftgroup_sample.json"

# ── import subject ────────────────────────────────────────────────────────────
from scripts.execute_loop.L01_slate_ingester import (  # noqa: E402
    SlateContest,
    get_dfs_slate,
    parse_dk_contest,
    parse_fd_contest,
    save_slate,
    main,
    _MIN_PLAYERS,
)


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def dk_sample() -> dict:
    return json.loads(_DK_SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def minimal_fd_payload() -> dict:
    return {
        "fixture_lists": [
            {
                "id": "fd-slate-001",
                "salary_cap": 60000,
                "sport": "NBA",
                "slate_type_name": "Main",
                "start_date": "2026-05-25T20:00:00+00:00",
                "roster_slots_count": {"PG": 2, "SG": 2, "SF": 2, "PF": 1, "C": 1},
                "fixtures": [{"id": "nba-game-001"}, {"id": "nba-game-002"}],
                "players": [
                    {
                        "id": "fd-p1", "full_name": "Player One",
                        "team": "LAL", "position": "PG", "salary": 8500, "injury_status": "",
                    },
                    {
                        "id": "fd-p2", "full_name": "Player Two",
                        "team": "BOS", "position": "SG", "salary": 7200, "injury_status": "Q",
                    },
                    {
                        "id": "fd-p3", "full_name": "Player Three",
                        "team": "MIA", "position": "SF", "salary": 6800, "injury_status": "",
                    },
                    {
                        "id": "fd-p4", "full_name": "Player Four",
                        "team": "MIL", "position": "PF", "salary": 9100, "injury_status": "",
                    },
                    {
                        "id": "fd-p5", "full_name": "Player Five",
                        "team": "LAL", "position": "C", "salary": 7600, "injury_status": "",
                    },
                    {
                        "id": "fd-p6", "full_name": "Player Six",
                        "team": "BOS", "position": "PG", "salary": 5500, "injury_status": "",
                    },
                    {
                        "id": "fd-p7", "full_name": "Player Seven",
                        "team": "MIA", "position": "SG", "salary": 5000, "injury_status": "",
                    },
                    {
                        "id": "fd-p8", "full_name": "Player Eight",
                        "team": "MIL", "position": "SF", "salary": 4800, "injury_status": "",
                    },
                ],
            }
        ]
    }


# ── SlateContest dataclass ─────────────────────────────────────────────────────
class TestSlateContestDataclass:
    def test_fields_present(self):
        sc = SlateContest(
            contest_id="abc",
            book="dk",
            sport="NBA",
            slate_type="classic",
            salary_cap=50000,
            roster_slots=["PG", "SG"],
            lock_time="2026-05-25T20:00:00+00:00",
            game_ids=["g1"],
            players=[],
        )
        assert sc.contest_id == "abc"
        assert sc.book == "dk"
        assert sc.sport == "NBA"
        assert sc.salary_cap == 50000
        assert sc.roster_slots == ["PG", "SG"]
        assert sc.players == []

    def test_default_players_empty(self):
        sc = SlateContest("x", "dk", "NBA", "classic", 50000, [], "t", [])
        assert sc.players == []


# ── parse_dk_contest ──────────────────────────────────────────────────────────
class TestParseDkContest:
    def test_basic_parse(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)

        assert slate.book == "dk"
        assert slate.sport == "NBA"
        assert slate.salary_cap == 50000
        assert slate.contest_id == "12345"
        assert slate.slate_type == "classic"

    def test_roster_slots_classic(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        assert "PG" in slate.roster_slots
        assert "C" in slate.roster_slots
        assert len(slate.roster_slots) == 8

    def test_game_ids_extracted(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        assert "0022501001" in slate.game_ids
        assert "0022501002" in slate.game_ids

    def test_zero_salary_player_skipped(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        player_names = [p["name"] for p in slate.players]
        assert "Zero Salary Player" not in player_names

    def test_player_count_correct(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        # 10 draftables, 1 has salary=0 → 9 players
        assert len(slate.players) == 9

    def test_player_fields(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        lebron = next(p for p in slate.players if p["name"] == "LeBron James")
        assert lebron["team"] == "LAL"
        assert lebron["salary"] == 9800
        assert lebron["player_id"] == "214152"

    def test_questionable_status_preserved(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        austin = next(p for p in slate.players if p["name"] == "Austin Reaves")
        assert austin["status"] == "QUESTIONABLE"

    def test_none_status_empty_string(self, dk_sample):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        lebron = next(p for p in slate.players if p["name"] == "LeBron James")
        assert lebron["status"] == ""

    def test_last_entry_wins_duplicate_player_id(self):
        """Player traded to new team — last entry wins."""
        group = {
            "draftGroupId": 99,
            "contestTypeId": 21,
            "salaryCap": 50000,
            "sport": "NBA",
            "startDate": "2026-05-25T23:00:00Z",
            "games": [],
        }
        draftables = {
            "draftables": [
                {"playerDkId": "111", "displayName": "Trade Guy", "teamAbbreviation": "OKC",
                 "rosterSlotId": 1, "salary": 6000, "status": "None"},
                {"playerDkId": "111", "displayName": "Trade Guy", "teamAbbreviation": "GSW",
                 "rosterSlotId": 1, "salary": 6000, "status": "None"},
            ]
        }
        slate = parse_dk_contest(group, draftables)
        # Only one entry for player_id 111, team should be last (GSW)
        matches = [p for p in slate.players if p["player_id"] == "111"]
        assert len(matches) == 1
        assert matches[0]["team"] == "GSW"

    def test_showdown_roster_slots(self):
        group = {
            "draftGroupId": 200,
            "contestTypeId": 96,
            "salaryCap": 50000,
            "sport": "NBA",
            "startDate": "2026-05-25T23:00:00Z",
            "games": [],
        }
        draftables = {"draftables": []}
        slate = parse_dk_contest(group, draftables)
        assert slate.slate_type == "showdown"
        assert "CPT" in slate.roster_slots


# ── parse_fd_contest ──────────────────────────────────────────────────────────
class TestParseFdContest:
    def test_basic_parse(self, minimal_fd_payload):
        slate = parse_fd_contest(minimal_fd_payload)
        assert slate.book == "fd"
        assert slate.sport == "NBA"
        assert slate.salary_cap == 60000
        assert slate.contest_id == "fd-slate-001"
        assert slate.slate_type == "main"

    def test_player_count(self, minimal_fd_payload):
        slate = parse_fd_contest(minimal_fd_payload)
        assert len(slate.players) == 8

    def test_game_ids(self, minimal_fd_payload):
        slate = parse_fd_contest(minimal_fd_payload)
        assert "nba-game-001" in slate.game_ids

    def test_roster_slots_built(self, minimal_fd_payload):
        slate = parse_fd_contest(minimal_fd_payload)
        assert len(slate.roster_slots) == 8  # sum(2+2+2+1+1)


# ── save_slate ────────────────────────────────────────────────────────────────
class TestSaveSlate:
    def test_writes_json(self, dk_sample, tmp_path):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        out = save_slate(slate, out_dir=str(tmp_path))
        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert data["book"] == "dk"
        assert data["contest_id"] == "12345"

    def test_filename_contains_slate_type(self, dk_sample, tmp_path):
        group = dk_sample["group"]
        draftables = {"draftables": dk_sample["draftables"]}
        slate = parse_dk_contest(group, draftables)
        out = save_slate(slate, out_dir=str(tmp_path))
        assert "classic" in Path(out).name


# ── get_dfs_slate (paper mode) ────────────────────────────────────────────────
class TestGetDfsSlate:
    def test_paper_mode_with_seed(self, dk_sample, tmp_path):
        """--paper loads from seed file, returns SlateContest list."""
        # Use far-future date matching fixture's lock_time (2099-12-31)
        seed_path = tmp_path / "seed_dk_2099-12-31.json"
        seed_path.write_text(json.dumps(dk_sample), encoding="utf-8")

        slates = get_dfs_slate(
            book="dk",
            date="2099-12-31",
            paper=True,
            out_dir=str(tmp_path),
        )
        assert slates is not None
        assert len(slates) >= 1
        assert slates[0].book == "dk"

    def test_paper_no_seed_returns_none(self, tmp_path):
        """--paper with no seed/cache returns None without raising."""
        slates = get_dfs_slate(
            book="dk",
            date="2099-01-01",
            paper=True,
            out_dir=str(tmp_path),
        )
        assert slates is None

    def test_uses_cache_when_fresh(self, dk_sample, tmp_path):
        cache_dir = tmp_path / ".cache"
        cache_dir.mkdir()
        # Cache file must use far-future date so lock_time filter passes
        cache_file = cache_dir / "dk_2099-12-31.json"
        cache_file.write_text(json.dumps(dk_sample), encoding="utf-8")

        slates = get_dfs_slate(
            book="dk",
            date="2099-12-31",
            paper=True,  # paper still reads cache tier
            out_dir=str(tmp_path),
        )
        assert slates is not None

    def test_locked_contest_dropped(self, dk_sample, tmp_path):
        """Contests whose lock_time is in the past must be filtered out.

        Patch _now_utc to a time AFTER the fixture's 2099-12-31 lock_time
        so the contest is treated as locked and dropped.
        """
        from datetime import datetime, timezone
        future_now = datetime(2100, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        seed_path = tmp_path / "seed_dk_2099-12-31.json"
        seed_path.write_text(json.dumps(dk_sample), encoding="utf-8")

        with patch(
            "scripts.execute_loop.L01_slate_ingester._now_utc",
            return_value=future_now,
        ):
            slates = get_dfs_slate(
                book="dk",
                date="2099-12-31",
                paper=True,
                out_dir=str(tmp_path),
            )

        # All contests locked (lock 2099-12-31 < now 2100-01-01) → empty list
        assert slates is not None
        assert len(slates) == 0


# ── main CLI ──────────────────────────────────────────────────────────────────
class TestMain:
    def test_paper_no_crash(self, tmp_path):
        """main(['--book','dk','--date','2026-05-25','--paper']) runs without error."""
        main(["--book", "dk", "--date", "2026-05-25", "--paper", "--out", str(tmp_path)])

    def test_paper_both_books_no_crash(self, tmp_path):
        main(["--book", "both", "--date", "2026-05-25", "--paper", "--out", str(tmp_path)])
